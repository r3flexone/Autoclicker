"""
Import/Export-Modul für den Autoclicker.
Exportiert komplette Setups als ZIP-Archiv und importiert sie
mit optionalem Koordinaten-Remapping für andere Bildschirme.
"""

import copy
import json
import logging
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .models import AutoClickerState

from .persistence import save_item_scan, save_boss_scan, save_icon_scan
from .utils import atomic_write, compact_json, sanitize_filename

logger = logging.getLogger("autoclicker")

EXPORT_VERSION = 1
MANIFEST_FILE = "manifest.json"

# Import-Dateien kommen von aussen. Diese Grenzen verhindern, dass ein kleines
# Archiv beim Prüfen/Entpacken unkontrolliert Speicher oder Platte belegt.
MAX_BUNDLE_FILES = 5000
MAX_BUNDLE_FILE_SIZE = 64 * 1024 * 1024
MAX_BUNDLE_TOTAL_SIZE = 512 * 1024 * 1024


# =============================================================================
# KOORDINATEN-REMAPPING
# =============================================================================

def compute_transform(src_ref1: tuple[int, int], src_ref2: tuple[int, int],
                      dst_ref1: tuple[int, int], dst_ref2: tuple[int, int]) -> dict:
    """Berechnet Skalierung + Offset aus 2 Referenzpunkt-Paaren.

    src_ref1/2: Referenzpunkte im Quell-Setup (aus dem Export)
    dst_ref1/2: Gleiche Punkte auf dem Ziel-Bildschirm
    """
    sx = src_ref2[0] - src_ref1[0]
    sy = src_ref2[1] - src_ref1[1]
    dx = dst_ref2[0] - dst_ref1[0]
    dy = dst_ref2[1] - dst_ref1[1]

    if sx != 0:
        scale_x = dx / sx
        offset_x = dst_ref1[0] - src_ref1[0] * scale_x
    else:
        scale_x = 1.0
        offset_x = dst_ref1[0] - src_ref1[0]

    if sy != 0:
        scale_y = dy / sy
        offset_y = dst_ref1[1] - src_ref1[1] * scale_y
    else:
        scale_y = 1.0
        offset_y = dst_ref1[1] - src_ref1[1]

    return {"scale_x": scale_x, "scale_y": scale_y,
            "offset_x": offset_x, "offset_y": offset_y}


def remap_point(x: int, y: int, transform: dict) -> tuple[int, int]:
    """Transformiert einen einzelnen Punkt."""
    new_x = round(x * transform["scale_x"] + transform["offset_x"])
    new_y = round(y * transform["scale_y"] + transform["offset_y"])
    return new_x, new_y


def remap_region(region: tuple[int, int, int, int], transform: dict) -> tuple[int, int, int, int]:
    """Transformiert eine Region (x1, y1, x2, y2). Normalisiert die Eckpunkte."""
    x1, y1 = remap_point(region[0], region[1], transform)
    x2, y2 = remap_point(region[2], region[3], transform)
    return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def collect_click_positions(state: 'AutoClickerState') -> list[tuple[str, int, int]]:
    """Die Klick-Koordinaten (Label, x, y) aus dem State: die Punkte der aktiven Sequenz.

    **Was an einem Punkt haengt, steht hier nur EINMAL — als Punkt.** Schritte, ihr
    Prüf-Pixel und Else-Klick sowie die Klicks von Items, Bossen und Icons haben keine
    eigene Stelle: `x/y` und Co. sind abgeleitete Arbeitswerte, und
    `_remap_sequence_obj` laesst sie deshalb in Ruhe. Sie neben ihrem Punkt zu listen
    hiesse, dieselbe Stelle doppelt zu zaehlen: in der Kalibrier-Vorschau stand jede
    Aenderung zweimal da (einmal "Punkt #1", einmal "Seq 'Farm'/A #1"), und die zweite
    Zeile versprach eine Umrechnung, die gar nicht stattfindet. Scan-interne Positionen
    (Slots) bleiben aussen vor — es geht um die eigentlichen Klick-Ziele.
    """
    with state.lock:
        return [(f"Punkt #{p.id}" + (f" {p.name}" if p.name else ""), p.x, p.y)
                for p in state.points]


def clicks_outside_window(state: 'AutoClickerState',
                          window_rect: tuple[int, int, int, int]) -> list[tuple[str, int, int]]:
    """Liefert die Klick-Positionen, die ausserhalb des Fenster-Rects (l, t, r, b) liegen."""
    l, t, r, b = window_rect
    lo_x, hi_x = min(l, r), max(l, r)
    lo_y, hi_y = min(t, b), max(t, b)
    return [(label, x, y) for label, x, y in collect_click_positions(state)
            if not (lo_x <= x <= hi_x and lo_y <= y <= hi_y)]


def transform_from_windows(src_window: tuple[int, int, int, int],
                           dst_window: tuple[int, int, int, int]) -> dict:
    """Baut die Affin-Transformation aus zwei Fenster-Client-Rects (l, t, r, b).

    Verwendet obere-linke und untere-rechte Ecke des Fensters als die zwei
    Referenzpunkte — damit skalieren+verschieben sich alle Koordinaten passend
    zur (ggf. anderen) Spielfenster-Grösse/Position auf dem Zielsystem.
    """
    sl, st, sr, sb = src_window
    dl, dt, dr, db = dst_window
    return compute_transform((sl, st), (sr, sb), (dl, dt), (dr, db))


IDENTITY_TRANSFORM = {"scale_x": 1.0, "scale_y": 1.0, "offset_x": 0, "offset_y": 0}


def transform_from_offset(old: tuple[int, int], new: tuple[int, int]) -> dict:
    """Reine Verschiebung aus EINEM Referenzpunkt: wo er war, wo er hingehört.

    Ein Punkt kann nur verschieben, nicht skalieren (dafür `compute_transform`).
    Reicht, solange nur die Lage des Monitors im virtuellen Desktop sich
    geändert hat — genau das passiert beim Umordnen der Bildschirme.
    """
    return {"scale_x": 1.0, "scale_y": 1.0,
            "offset_x": new[0] - old[0], "offset_y": new[1] - old[1]}


def is_identity(transform: dict) -> bool:
    """True, wenn der Transform nichts verändern würde."""
    return (transform["scale_x"] == 1.0 and transform["scale_y"] == 1.0
            and round(transform["offset_x"]) == 0 and round(transform["offset_y"]) == 0)


# KALIBRIERUNG (Bildschirm-Layout hat sich geaendert)
# Dasselbe Remapping wie beim Import, nur auf den EIGENEN Bestand. Der Import
# kann das nicht ersetzen: er legt Daten an, statt vorhandene zu korrigieren.

def calibration_preview(state: 'AutoClickerState', transform: dict) -> list[tuple[str, tuple, tuple]]:
    """Was der Transform ändern würde — (Bezeichnung, vorher, nachher), ohne Mutation."""
    return [(label, (x, y), remap_point(x, y, transform))
            for label, x, y in collect_click_positions(state)]


def _remap_sequence_obj(seq, transform: dict) -> None:
    """Wie _remap_sequence_data, aber auf einer geladenen Sequenz (in-place).

    Die geladene Sequenz MUSS mitgezogen werden, nicht nur die Dateien: sonst
    schreibt das nächste `save_points()` den alten Stand aus dem Speicher wieder über
    die frisch umgerechnete Datei. Umgerechnet wird nur, was keinen Punkt haben kann:
    die Screenshot-Region. Klick, Prüf-Pixel und Else-Klick sind Punkte und oben
    schon umgerechnet; der naechste `resolve()`-Lauf holt ihre Werte von dort.
    """
    phases = [seq.init_steps, seq.end_steps] + [lp.steps for lp in seq.loop_phases]
    for steps in phases:
        for s in steps:
            if s.screenshot_region is not None:
                s.screenshot_region = remap_region(s.screenshot_region, transform)


def backup_before_calibration(state: 'AutoClickerState') -> str | None:
    """Legt vor dem Umrechnen ein vollständiges Export-ZIP als Sicherung an.

    Kein eigenes Backup-Format: der Export kann das längst, und der Import
    spielt es wieder ein. Gibt den Pfad zurück, oder None bei Fehlschlag.
    """
    import time as _time

    # Derselbe Ordner, in dem der Editor seine Exporte sucht — damit die Sicherung
    # im Import-Menue ohne Pfadeingabe auftaucht.
    target = Path("exports") / f"vor_kalibrierung_{_time.strftime('%Y%m%d_%H%M%S')}.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    # Referenzpunkte sind hier bedeutungslos (es wird nichts remappt beim
    # Zurückspielen), aber identisch dürfen sie nicht sein — sonst rechnet ein
    # späterer Import mit einer Nulldistanz.
    success, message = export_bundle(state, str(target), (0, 0), (1000, 1000))
    if not success:
        logger.warning("Sicherung vor Kalibrierung fehlgeschlagen: %s", message)
        return None
    return str(target)


def calibrate_inventory(state: 'AutoClickerState', transform: dict,
                       with_scans: bool = True, with_sequences: bool = True,
                       with_slots: bool = True) -> dict:
    """Rechnet den gespeicherten Bestand auf das neue Bildschirm-Layout um.

    Die Punkte der geladenen Sequenz immer; `with_scans` zieht die Slots und
    Fenster-Anker der Item-Scans sowie die Regionen der Boss-/Icon-Scans mit,
    `with_sequences` die Screenshot-Regionen und **alle übrigen Sequenzen auf der
    Platte** — dort mit denselben beiden Schaltern (`_remap_sequence_files`).
    Alles, was auf einen Punkt zeigt — Klick-Stellen der Sequenzen, Bestätigungsklick
    der Items, Klicks von Bossen und Icons —, wird NICHT angefasst: der Punkt ist
    schon umgerechnet, und die abgeleiteten Werte holt `resolve()` bzw.
    `resolve_click_references()` von dort.

    `with_slots` ist getrennt schaltbar, obwohl Slots zu den Scans gehören: nach
    einer `slot_repair()`-Reparatur dürfen sie kein zweites Mal wandern.

    Gibt eine Zählung nach Bereich zurück.
    """
    from .persistence import sequence_file

    number = {"points": 0, "slots": 0, "item_scans": 0,
            "boss_scans": 0, "icon_scans": 0, "sequences": 0}

    # --- alles, was im State liegt: unter Lock mutieren, ausserhalb speichern ---
    with state.lock:
        for p in state.points:
            p.x, p.y = remap_point(p.x, p.y, transform)
            number["points"] += 1

        if with_scans:
            owner = state.active_sequence.name if state.active_sequence is not None else None
            _remap_item_scans(state, transform, with_slots, owner, number)
            _remap_detection_scans(state, transform, owner, number)

        # Geladene Sequenzen im selben Lock mitziehen — sonst ueberschreibt der
        # naechste save_points() die umgerechneten Dateien mit dem alten Stand.
        if with_sequences and state.active_sequence is not None:
            # Die geladene Sequenz im Speicher mitziehen — genau ihre
            # Screenshot-Regionen schreibt `save_points()` unten zurueck; alle
            # anderen Sequenzen werden ueber ihre Dateien umgerechnet.
            _remap_sequence_obj(state.active_sequence, transform)

        scans = ((list(state.item_scans.values()), list(state.boss_scans.values()),
                  list(state.icon_scans.values())) if with_scans else None)
        written_from_memory = (sequence_file(state.active_sequence.name).resolve()
                               if state.active_sequence is not None else None)

    _save_calibrated(state, scans)
    if with_sequences:
        number["sequences"] = _remap_sequence_files(transform, written_from_memory,
                                                    with_scans, with_slots)
    return number


def _own(cfg, owner: Optional[str]) -> None:
    """Ein Scan ohne Besitzerin gehört der aktiven Sequenz — sonst liesse er sich nicht speichern."""
    if not cfg.owner_sequence and owner is not None:
        cfg.owner_sequence = owner


def _remap_item_scans(state: 'AutoClickerState', transform: dict, with_slots: bool,
                      owner: Optional[str], number: dict) -> None:
    for cfg in state.item_scans.values():
        _own(cfg, owner)
        if with_slots:
            for slot in cfg.slots:
                slot.scan_region = remap_region(slot.scan_region, transform)
                slot.click_pos = remap_point(slot.click_pos[0], slot.click_pos[1], transform)
                number["slots"] += 1
        # Die Slot-Koordinaten und ihr Fenster-Anker bilden ein Paar.
        # Wird nur eine Hälfte transformiert, würde die Runtime beim
        # nächsten Lauf ein zweites, falsches Remapping anwenden.
        if cfg.capture_window_rect:
            cfg.capture_window_rect = remap_region(cfg.capture_window_rect, transform)
            number["item_scans"] += 1


def _remap_detection_scans(state: 'AutoClickerState', transform: dict,
                           owner: Optional[str], number: dict) -> None:
    """Die Regionen der Boss- und Icon-Scans. Ihre Klicks sind Punkte (s. oben)."""
    for cfg in state.boss_scans.values():
        _own(cfg, owner)
        cfg.scan_region = remap_region(cfg.scan_region, transform)
        number["boss_scans"] += 1
    for cfg in state.icon_scans.values():
        _own(cfg, owner)
        cfg.scan_region = remap_region(cfg.scan_region, transform)
        number["icon_scans"] += 1


def _save_calibrated(state: 'AutoClickerState', scans: Optional[tuple]) -> None:
    """Punkte und (mit `scans`) alle Scans schreiben.

    Die Boss-Bibliothek gehört nicht dazu: sie trägt nur Punkt-IDs, und die Punkte
    stehen oben in der Sequenz.

    Jeder Saver meldet seinen Fehler selbst — dieselbe Zeile wie bei den
    Sequenzdateien, damit ein Fehlschlag im Log neben der Bilanz steht. Vor dem
    Durchgang liegt ohnehin ein Export-ZIP (backup_before_calibration).
    """
    from .persistence import save_points
    if not save_points(state):
        logger.warning("Kalibrierung: Punkte der aktiven Sequenz nicht geschrieben")
    if scans is None:
        return
    item_scans, boss_scans, icon_scans = scans
    for kind, saver, configs in (("Item-Scan", save_item_scan, item_scans),
                                 ("Boss-Scan", save_boss_scan, boss_scans),
                                 ("Icon-Scan", save_icon_scan, icon_scans)):
        for cfg in configs:
            if not saver(cfg):
                logger.warning("Kalibrierung: %s '%s' nicht geschrieben", kind, cfg.name)


def _remap_sequence_files(transform: dict, written_from_memory: Optional[Path],
                          with_scans: bool, with_slots: bool) -> int:
    """Die übrigen Sequenzen über ihre Ordner — vollständig, wie ein importierter.

    Hier wurde nur die `sequence.json` angefasst und darin nur die Screenshot-
    Regionen: ein Rest aus der Zeit einer gemeinsamen `points.json`, die „Punkte
    immer" schon für alle Sequenzen umrechnete. Seit Punkte und Scans im Ordner
    ihrer Sequenz stehen, blieb jede nicht geladene halb verschoben zurück —
    Screenshot-Bereiche am neuen Ort, Punkte, Slots und Scan-Regionen am alten.
    Jetzt dieselbe Rechnung wie für einen importierten Ordner, mit denselben
    Schaltern wie für die geladene Sequenz. Gibt zurück, wie viele umgerechnet sind.
    """
    from .persistence import list_available_sequences
    count = 0
    for _name, path in list_available_sequences():
        # Die aktive Sequenz kam eben aus dem Speicher — Punkte über
        # `save_points()`, Scans über `_save_calibrated()`, schon umgerechnet.
        # Ein zweiter Durchgang ueber ihren Ordner verschoebe alles doppelt.
        if written_from_memory is not None and Path(path).resolve() == written_from_memory:
            count += 1
            continue
        try:
            _remap_sequence_folder(Path(path).parent, transform,
                                   with_scans=with_scans, with_slots=with_slots)
            count += 1
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
            logger.warning("Kalibrierung: %s nicht umgerechnet (%s)", Path(path).parent.name, e)
    return count


# =============================================================================
# EXPORT
# =============================================================================

def export_bundle(state: 'AutoClickerState', filepath: str,
                  ref_point1: tuple[int, int], ref_point2: tuple[int, int],
                  include_sequences: bool = True, include_config: bool = True,
                  source_window: tuple[int, int, int, int] = None) -> tuple[bool, str]:
    """Exportiert Setup als ZIP-Archiv: die Sequenzordner unverändert, dazu die Config.

    include_sequences: die Sequenzordner. Eine Sequenz ist samt Punkten, Scans,
    Slots/Items, Vorlagen und Bildern eine Besitzeinheit — getrennt wird nicht.
    Hier standen sieben Schalter (Punkte, Sequenzen, Slots, Items, drei
    Scan-Arten) aus der Zeit der getrennten Bestände; die Funktion fasste sie
    längst zu einem ODER zusammen, und weil jeder auf True stand, schaltete ein
    vergessener den Export wieder ein. Drei Tests taten genau das, ohne es zu
    sagen.

    source_window: Client-Rect (l,t,r,b) des Spielfensters beim Export. Wird im
    Manifest abgelegt, damit der Import die Skalierung automatisch aus der
    Fenstergrösse ableiten kann (Fallback bleibt das 2-Punkt-Verfahren).

    Returns:
        (success, message)
    """
    from .persistence import list_available_sequences

    manifest = {
        "version": EXPORT_VERSION,
        "layout": "sequence-folders",
        "reference_points": {"point1": list(ref_point1), "point2": list(ref_point2)},
        "contents": {},
    }
    if source_window:
        manifest["source_window"] = list(source_window)

    try:
        with zipfile.ZipFile(filepath, "w", zipfile.ZIP_DEFLATED) as zf:
            names = []
            counters = {"item_scans": 0, "boss_scans": 0, "icon_scans": 0,
                       "templates": 0}
            if include_sequences:
                for name, main_file in list_available_sequences():
                    folder = Path(main_file).parent
                    archive_root = PurePosixPath("sequences", folder.name)
                    for source in sorted(p for p in folder.rglob("*") if p.is_file()):
                        rel_path = PurePosixPath(source.relative_to(folder).as_posix())
                        zf.write(source, str(archive_root / rel_path))
                        parts = rel_path.parts
                        if parts and parts[0] in counters and source.suffix.lower() == ".json":
                            counters[parts[0]] += 1
                        if parts and parts[0] == "templates" and source.suffix.lower() == ".png":
                            counters["templates"] += 1
                    names.append(name)
                manifest["contents"]["sequences"] = names
                manifest["contents"].update({k: v for k, v in counters.items() if v})
            if include_config:
                zf.writestr("config.json", compact_json(_export_config(state.config)))
                manifest["contents"]["config"] = True
            zf.writestr(MANIFEST_FILE, compact_json(manifest))
        return True, filepath
    except (IOError, OSError, zipfile.BadZipFile) as e:
        logger.error("Export fehlgeschlagen: %s", e)
        return False, str(e)


# Maschinen-/sicherheitsspezifische Config-Felder, die NIE zwischen Setups
# wandern sollen (Failsafe-Position, Log-Pfad). Werden weder exportiert noch
# beim Import übernommen.
_SENSITIVE_CONFIG_KEYS = {
    "failsafe_enabled", "failsafe_x", "failsafe_y",
    "session_log_enabled", "session_log_dir",
}
# Beim Export zusätzlich weggelassen: Debug/Anzeige — für den Empfänger irrelevant.
_EXPORT_SKIP_CONFIG_KEYS = _SENSITIVE_CONFIG_KEYS | {
    "debug_log", "debug_detail", "debug_save_templates",
    "debug_show_pixel_position", "pixel_show_delay",
}


def _export_config(config) -> dict:
    """Exportiert relevante Config-Werte (ohne interne/Debug-Felder)."""
    d = config.to_dict()
    return {k: v for k, v in d.items()
            if k not in _EXPORT_SKIP_CONFIG_KEYS and not k.startswith("_")}


# =============================================================================
# IMPORT
# =============================================================================

def _manifest_problem(manifest) -> Optional[str]:
    """Was am Manifest nicht stimmt — None, wenn es in Ordnung ist.

    Die EINE Prüfung: `read_manifest` (Vorschau) und `_validate_bundle` (Import)
    stellten sie vorher je für sich, mit leicht anderem Wortlaut.
    """
    if not isinstance(manifest, dict):
        return "Ungültiges Manifest: Objekt erwartet"
    if manifest.get("version") != EXPORT_VERSION:
        return f"Unbekannte Version: {manifest.get('version')} (erwartet: {EXPORT_VERSION})"
    if not isinstance(manifest.get("contents", {}), dict):
        return "Ungültiges Manifest: 'contents' muss ein Objekt sein"
    return None


def read_manifest(filepath: str) -> tuple[bool, dict | str]:
    """Liest das Manifest aus einer ZIP-Datei.

    Returns:
        (success, manifest_dict | error_message)
    """
    try:
        with zipfile.ZipFile(filepath, "r") as zf:
            if MANIFEST_FILE not in zf.namelist():
                return False, "Keine gültige Export-Datei (manifest.json fehlt)"
            manifest = json.loads(zf.read(MANIFEST_FILE).decode("utf-8"))
            problem = _manifest_problem(manifest)
            return (False, problem) if problem else (True, manifest)
    except zipfile.BadZipFile:
        return False, "Datei ist kein gültiges ZIP-Archiv"
    except (IOError, OSError, json.JSONDecodeError) as e:
        return False, str(e)


def _validate_bundle(zf: zipfile.ZipFile, names: list[str]) -> dict:
    """Prüft Version, Größen, doppelte Namen und JSON-Grundstrukturen vor Mutation."""
    _check_bundle_sizes(zf, names)
    manifest = json.loads(zf.read(MANIFEST_FILE).decode("utf-8"))
    problem = _manifest_problem(manifest)
    if problem:
        raise ValueError(problem)

    # Alles im Bundle ist ein Objekt — bis auf die Boss-Bibliothek, die als
    # Liste in den Boss-Scans der Sequenz liegt. Die Sonderfaelle fuer
    # `points.json`, `slots.json` und `items.json` sind mit dem globalen
    # Bestand entfallen; die drei Dateien gibt es in keinem Bundle mehr.
    for name in names:
        if not name.lower().endswith(".json") or name == MANIFEST_FILE:
            continue
        data = json.loads(zf.read(name).decode("utf-8"))
        expected = list if name.endswith("/boss_scans/bibliothek.json") else dict
        if not isinstance(data, expected):
            raise ValueError(f"Ungültige Struktur in {name}")
    return manifest


def _check_bundle_sizes(zf: zipfile.ZipFile, names: list[str]) -> None:
    """Anzahl, doppelte Namen (ohne Gross/Klein) und entpackte Grösse."""
    if len(names) > MAX_BUNDLE_FILES:
        raise ValueError(f"Zu viele Dateien im Bundle ({len(names)})")
    folded = [name.casefold() for name in names]
    if len(folded) != len(set(folded)):
        raise ValueError("Bundle enthält doppelte Dateinamen")
    infos = zf.infolist()
    if sum(info.file_size for info in infos) > MAX_BUNDLE_TOTAL_SIZE:
        raise ValueError("Bundle ist entpackt zu groß")
    if any(info.file_size > MAX_BUNDLE_FILE_SIZE for info in infos):
        raise ValueError("Eine Datei im Bundle ist zu groß")


class _ImportTransaction:
    """Sichert die Config und die importrelevanten Dateien und rollt bei Fehlern zurück.

    Der State bleibt dabei ausser Betracht: ein Import schreibt Sequenzordner auf die
    Platte und die Config; Punkte, Scans und Bestand im Speicher fasst er nicht an
    (geladen wird danach von dort).
    """

    # Was ausserhalb der Sequenzordner liegt und ein Import anfassen kann.
    # Hier standen einmal `points.json`, `slots/slots.json`, `items/items.json`
    # und `boss_scans/global/bosses.json` — alle vier gibt es nicht mehr, sie
    # sind in die Besitzeinheit gewandert.
    _FIXED_FILES = ("config.json",)
    _ROOTS = ("sequences",)

    def __init__(self, state):
        self.state = state
        with state.lock:
            self.config_snapshot = copy.deepcopy(state.config)
        self.temp = tempfile.TemporaryDirectory(prefix="autoclicker_import_")
        self.backup_root = Path(self.temp.name)
        self.initial_dirs = {
            path.resolve()
            for raw in self._ROOTS
            for path in ([Path(raw)] + list(Path(raw).rglob("*")) if Path(raw).exists() else [])
            if path.is_dir()
        }
        self.backed_up_files: set[Path] = set()
        for source in self._managed_files():
            relative = source.resolve().relative_to(Path.cwd().resolve())
            self.backed_up_files.add(relative)
            target = self.backup_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    @classmethod
    def _managed_files(cls) -> set[Path]:
        files = {Path(raw) for raw in cls._FIXED_FILES if Path(raw).is_file()}
        # Ein Ordner-Bundle ersetzt ganze Sequenzordner, einschliesslich ihrer
        # Vorlagen und gemerkten Bilder. Fuer ein echtes Rollback werden deshalb
        # saemtliche Dateien darunter gesichert, nicht nur die JSON-Struktur —
        # ein `rglob("*.json")` liesse die PNGs zurueck.
        sequences = Path("sequences")
        if sequences.exists():
            files.update(path for path in sequences.rglob("*") if path.is_file())
        return files

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        if exc_type is not None:
            self.rollback()
        self.temp.cleanup()
        return False

    def rollback(self) -> None:
        from .config import apply_config

        with self.state.lock:
            apply_config(self.state.config, self.config_snapshot)

        for target in self._managed_files():
            target.unlink()
        for relative in self.backed_up_files:
            backup = self.backup_root / relative
            target = Path(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, target)

        # Nur vom fehlgeschlagenen Import neu angelegte, jetzt leere Ordner entfernen.
        current_dirs = [
            path
            for raw in self._ROOTS
            for path in ([Path(raw)] + list(Path(raw).rglob("*")) if Path(raw).exists() else [])
            if path.is_dir() and path.resolve() not in self.initial_dirs
        ]
        for path in sorted(current_dirs, key=lambda p: len(p.parts), reverse=True):
            try:
                path.rmdir()
            except OSError:
                pass


def _safe_bundle_path(name: str) -> Optional[PurePosixPath]:
    """Ein relativer Sequenzpfad im Archiv oder None."""
    path = PurePosixPath(name)
    if ("\\" in name or ":" in name or "\x00" in name
            or path.is_absolute() or ".." in path.parts or len(path.parts) < 3
            or path.parts[0] != "sequences"):
        return None
    return path


def _remap_sequence_folder(folder: Path, transform: dict,
                           with_scans: bool = True, with_slots: bool = True) -> None:
    """Transformiert alle koordinatenhaltigen JSON-Dateien eines Sequenzordners.

    Der Import nimmt alles mit; die Kalibrierung reicht ihre Schalter durch
    (`with_scans`, `with_slots` — dieselbe Bedeutung wie bei der geladenen Sequenz).
    Erst wird jede Datei gelesen, dann geschrieben: eine unlesbare Datei mitten im
    Ordner bricht ab, bevor etwas umgerechnet ist, statt die Sequenz halb verschoben
    zurückzulassen.
    """
    if is_identity(transform):
        return
    remapped = []
    for path in folder.rglob("*.json"):
        rel_path = path.relative_to(folder).parts
        if rel_path == ("boss_scans", "bibliothek.json"):
            # Die Bibliothek enthält Profile mit Punkt-IDs, keine Regionen.
            # Ihre Punkte werden in sequence.json genau einmal umgerechnet.
            continue
        is_scan = bool(rel_path) and rel_path[0] in ("item_scans", "boss_scans", "icon_scans")
        if is_scan and not with_scans:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if path.name == "sequence.json":
            for point in data.get("points") or []:
                point["x"], point["y"] = remap_point(
                    int(point.get("x", 0)), int(point.get("y", 0)), transform)
            _remap_sequence_data(data, transform)
        elif rel_path[0] == "item_scans":
            _remap_item_scan_data(data, transform, with_slots)
        elif is_scan:
            _remap_key(data, "scan_region", transform)
        remapped.append((path, data))
    for path, data in remapped:
        atomic_write(path, compact_json(data))


def _remap_key(data: dict, key: str, transform: dict) -> None:
    """Eine Region unter `key` umrechnen, wenn sie gesetzt ist."""
    if data.get(key):
        data[key] = list(remap_region(tuple(data[key]), transform))


def _remap_item_scan_data(data: dict, transform: dict, with_slots: bool = True) -> None:
    """Slots (Region und Klickstelle) und der Fenster-Anker eines Item-Scans.

    Ohne `with_slots` nur der Anker — genau wie `_remap_item_scans()` es mit der
    geladenen Sequenz tut.
    """
    if with_slots:
        for slot in (data.get("slots") or {}).values():
            _remap_key(slot, "scan_region", transform)
            if slot.get("click_pos"):
                slot["click_pos"] = list(remap_point(*slot["click_pos"], transform))
    _remap_key(data, "capture_window_rect", transform)


def _import_sequence_bundle(state: 'AutoClickerState', zf: zipfile.ZipFile,
                            names: list[str], transform: dict,
                            import_sequences: bool, import_config: bool,
                            merge: bool) -> tuple[bool, str]:
    """Importiert das nach Sequenzordnern geordnete Bundle."""
    imported_ones = []
    with tempfile.TemporaryDirectory(prefix="autoclicker_import_") as temp:
        temp_root = Path(temp)
        if import_sequences:
            _unpack_bundle(zf, names, temp_root)
            for source in sorted(p for p in temp_root.iterdir() if p.is_dir()):
                imported_ones.append(_import_sequence_folder(source, transform, merge))
        if import_config and "config.json" in names:
            _import_bundle_config(state, zf)

    parts = [f"{len(imported_ones)} Sequenz(en) mit zugehörigen Scans und Vorlagen"]
    if import_config and "config.json" in names:
        parts.append("Einstellungen")
    return True, ", ".join(parts)


def _unpack_bundle(zf: zipfile.ZipFile, names: list[str], temp_root: Path) -> None:
    """Die Sequenzordner in den Temp-Ordner — jeder Pfad geprüft, auch messbar."""
    for name in names:
        archive = _safe_bundle_path(name)
        if archive is None or name.endswith("/"):
            continue
        target = temp_root.joinpath(*archive.parts[1:]).resolve()
        if not target.is_relative_to(temp_root.resolve()):
            raise ValueError(f"Archivpfad verlässt den Importordner: {name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(zf.read(name))


def _import_sequence_folder(source: Path, transform: dict, merge: bool) -> str:
    """Einen entpackten Sequenzordner umrechnen und an seinen Platz bringen.

    Mit `merge` weicht ein vergebener Ordnername auf `<name>_2` aus, sonst
    wird der vorhandene ersetzt. Gibt den Namen der importierten Sequenz zurück.
    """
    from .persistence import ensure_sequences_dir, load_sequence_file
    main_file = source / "sequence.json"
    if not main_file.is_file():
        raise ValueError(f"{source.name}: sequence.json fehlt")
    _remap_sequence_folder(source, transform)
    data = json.loads(main_file.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{source.name}/sequence.json ist ungültig")

    base_name = sanitize_filename(str(data.get("name") or source.name))
    target = ensure_sequences_dir() / base_name
    if merge:
        number = 2
        while target.exists():
            target = ensure_sequences_dir() / f"{base_name}_{number}"
            number += 1
        if target.name != base_name:
            data["name"] = target.name
            atomic_write(main_file, compact_json(data))
    elif target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    seq = load_sequence_file(target / "sequence.json")
    if seq is None:
        raise ValueError(f"{target.name}: importierte Sequenz ist nicht lesbar")
    return seq.name


def _import_bundle_config(state: 'AutoClickerState', zf: zipfile.ZipFile) -> None:
    """Die Config des Bündels in die laufende schreiben — ohne die sensiblen Schlüssel."""
    from .config import AppConfig, apply_config, save_config
    raw = json.loads(zf.read("config.json").decode("utf-8"))
    if not isinstance(raw, dict):
        return
    allowed = {k: v for k, v in raw.items() if k not in _SENSITIVE_CONFIG_KEYS}
    # Ueber `from_dict`, nicht per `setattr`: nur so laeuft
    # `__post_init__` — ein Buendel mit `pixel_check_interval: 0`
    # oder einem Tippfehler in `pixel_timeout_action` landete sonst
    # ungeprueft im laufenden Config-Objekt, und unbekannte
    # Schluessel gleich mit. Hineingeschrieben statt getauscht,
    # weil `state.config` das Modul-CONFIG ist (s. apply_config).
    merged = AppConfig.from_dict({**state.config.to_dict(), **allowed})
    with state.lock:
        apply_config(state.config, merged)
    save_config(state.config)


def import_bundle(state: 'AutoClickerState', filepath: str,
                  transform: dict = None, import_sequences: bool = True,
                  import_config: bool = True, merge: bool = True) -> tuple[bool, str]:
    """Importiert ein Setup aus einer ZIP-Datei.

    Ein Buendel besteht aus Sequenzordnern (jeder mit Punkten, Scans und
    Vorlagen) und optional der Config — mehr Teile gibt es nicht, also auch
    nur diese zwei Schalter. Hier standen sieben (`import_points`,
    `import_slots`, `import_items`, …) aus der Zeit des globalen Bestands,
    die am Ende nur noch ver-odert wurden.

    Args:
        transform: Koordinaten-Transformation (None = keine Anpassung)
        merge: True = bestehende Daten behalten + ergänzen, False = ersetzen

    Returns:
        (success, message)
    """
    if transform is None:
        transform = IDENTITY_TRANSFORM

    try:
        with zipfile.ZipFile(filepath, "r") as zf:
            names = zf.namelist()
            if MANIFEST_FILE not in names:
                return False, "Keine gültige Export-Datei"

            manifest = _validate_bundle(zf, names)
            # **Es gibt genau einen Import-Weg.** Daneben stand bis hierher eine
            # zweite, vollstaendige Implementierung fuer Buendel aus der Zeit des
            # globalen Bestands (`points.json`, `slots.json`, `items.json`,
            # Scan-Ordner im Wurzelverzeichnis). Sie war nicht nur Altlast,
            # sondern **kaputt**: Vorlagen landeten in `items/templates/`, wo
            # seit dem Umzug auf Besitzeinheiten keine Sequenz mehr nachsieht,
            # und `_imp_items` schrieb ueber `save_scan_items()`, das ohne
            # aktiven Item-Scan folgenlos zurueckkehrt. Ein Import, der meldet
            # "hat geklappt" und nichts Brauchbares hinterlaesst, ist schlechter
            # als eine Absage.
            if manifest.get("layout") != "sequence-folders":
                return False, (
                    "Bundle aus einer aelteren Fassung (vor den Sequenzordnern) — "
                    "es laesst sich nicht mehr einlesen. Die Sequenz im Studio neu "
                    "bauen; das ist inzwischen billiger als der Umweg.")
            with _ImportTransaction(state):
                return _import_sequence_bundle(
                    state, zf, names, transform, import_sequences, import_config, merge)

    except Exception as e:
        logger.error(f"Import fehlgeschlagen: {e}")
        return False, str(e)


def _iter_import_steps(seq_data: dict):
    """Alle Schritt-Dicts einer Sequenz-JSON - egal in welcher Phase sie stehen."""
    for key in ("init_steps", "end_steps"):
        for s in seq_data.get(key) or []:
            yield s
    for lp in seq_data.get("loop_phases") or []:
        for s in lp.get("steps") or []:
            yield s


def _remap_sequence_data(seq_data: dict, transform: dict) -> None:
    """Transformiert die Koordinaten in einer Sequenz-JSON-Struktur (in-place).

    Was eine Punkt-Referenz hat, wird hier NICHT angefasst - der Punkt ist schon
    umgerechnet, und ein zweites Mal hiesse doppelt verschoben. Uebrig bleibt, was
    keinen Punkt haben kann: die Screenshot-Region. Koordinaten an den Schritten
    selbst kennt das Dateiformat nicht (sie stehen im Punkt).
    """
    for s in _iter_import_steps(seq_data):
        if s.get("screenshot_region"):
            sr = s["screenshot_region"]
            s["screenshot_region"] = list(remap_region(tuple(sr), transform))
