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
from pathlib import Path
from pathlib import PurePosixPath
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .models import AutoClickerState

from .persistence import (
    save_item_scan, save_boss_scan, save_icon_scan, save_global_bosses,
)
from .models import ACTION_CLICK
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
    """Sammelt die wichtigsten Klick-Koordinaten (Label, x, y) aus dem State.

    Erfasst: Punkte, Klick-Schritte OHNE Punkt-Referenz (inkl. else-Klick) sowie
    Klick-Aktionen von Boss- und Icon-Scans. Scan-interne Positionen (Slots,
    confirm_points) bleiben aussen vor — es geht um die eigentlichen Klick-Ziele.

    **Was an einem Punkt haengt, steht hier nur EINMAL — als Punkt.** Seit Schema 4
    sind `step.x/y` abgeleitete Arbeitswerte, und `_remap_sequence_obj` laesst sie
    deshalb in Ruhe. Beide zu listen hiesse, dieselbe Stelle doppelt zu zaehlen: in
    der Kalibrier-Vorschau stand jede Aenderung zweimal da (einmal "Punkt #1",
    einmal "Seq 'Farm'/A #1"), und die zweite Zeile versprach eine Umrechnung, die
    gar nicht stattfindet. Uebrig bleiben die Schritte ohne Referenz — die gibt es
    nur noch in von Hand geschriebenen Dateien, und genau die will man sehen.
    """
    positions: list[tuple[str, int, int]] = []
    with state.lock:
        for p in state.points:
            label = f"Punkt #{p.id}" + (f" {p.name}" if p.name else "")
            positions.append((label, p.x, p.y))

        for name, seq in state.sequences.items():
            groups = [("Init", seq.init_steps), ("End", seq.end_steps)]
            for lp in seq.loop_phases:
                groups.append((lp.name, lp.steps))
            for gname, steps in groups:
                for i, s in enumerate(steps, 1):
                    # Echter Klick-Schritt ohne Punkt: nicht wait-only, kein
                    # Scan/Key/Screenshot, und nicht schon ueber `point_id` erfasst.
                    if s.point_id is None and not (
                            s.wait_only or s.item_scan or s.boss_scan or s.icon_scan
                            or s.screenshot_only or s.key_press):
                        positions.append((f"Seq '{name}'/{gname} #{i}", s.x, s.y))
                    ec = s.else_config
                    if ec and ec.action == ACTION_CLICK and ec.point_id is None:
                        positions.append((f"Seq '{name}'/{gname} #{i} (else)", ec.x, ec.y))

        for cfg in state.boss_scans.values():
            for b in cfg.bosses:
                if b.action == ACTION_CLICK:
                    positions.append((f"Boss '{b.name}'", b.action_x, b.action_y))

        for b in state.global_bosses:
            if b.action == ACTION_CLICK:
                positions.append((f"Boss '{b.name}' (global)", b.action_x, b.action_y))

        for cfg in state.icon_scans.values():
            if cfg.action == ACTION_CLICK:
                positions.append((f"Icon '{cfg.name}'", cfg.action_x, cfg.action_y))

    return positions


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


def transform_aus_verschiebung(alt: tuple[int, int], neu: tuple[int, int]) -> dict:
    """Reine Verschiebung aus EINEM Referenzpunkt: wo er war, wo er hingehört.

    Ein Punkt kann nur verschieben, nicht skalieren (dafür `compute_transform`).
    Reicht, solange nur die Lage des Monitors im virtuellen Desktop sich
    geändert hat — genau das passiert beim Umordnen der Bildschirme.
    """
    return {"scale_x": 1.0, "scale_y": 1.0,
            "offset_x": neu[0] - alt[0], "offset_y": neu[1] - alt[1]}


def ist_identitaet(transform: dict) -> bool:
    """True, wenn der Transform nichts verändern würde."""
    return (transform["scale_x"] == 1.0 and transform["scale_y"] == 1.0
            and round(transform["offset_x"]) == 0 and round(transform["offset_y"]) == 0)


# KALIBRIERUNG (Bildschirm-Layout hat sich geaendert)
# Dasselbe Remapping wie beim Import, nur auf den EIGENEN Bestand. Der Import
# kann das nicht ersetzen: er legt Daten an, statt vorhandene zu korrigieren.

def kalibrier_vorschau(state: 'AutoClickerState', transform: dict) -> list[tuple[str, tuple, tuple]]:
    """Was der Transform ändern würde — (Bezeichnung, vorher, nachher), ohne Mutation."""
    return [(label, (x, y), remap_point(x, y, transform))
            for label, x, y in collect_click_positions(state)]


def _remap_sequence_obj(seq, transform: dict) -> None:
    """Wie _remap_sequence_data, aber auf einer geladenen Sequenz (in-place).

    Die geladenen Sequenzen MÜSSEN mitgezogen werden, nicht nur die Dateien: sonst
    schreibt der nächste `save_data()` den alten Stand aus dem Speicher wieder über
    die frisch umgerechnete Datei.
    """
    phasen = [seq.init_steps, seq.end_steps] + [lp.steps for lp in seq.loop_phases]
    for steps in phasen:
        for s in steps:
            # Referenzierte Stellen ueberspringen: ihr Punkt ist schon umgerechnet,
            # und der naechste `aufloesen()`-Lauf holt den Wert ohnehin von dort.
            if s.point_id is None:
                s.x, s.y = remap_point(s.x, s.y, transform)
            if s.wait_condition is not None and s.wait_condition.point_id is None:
                px = s.wait_condition.pixel
                s.wait_condition.pixel = remap_point(px[0], px[1], transform)
            if s.else_config is not None and s.else_config.point_id is None:
                ec = s.else_config
                ec.x, ec.y = remap_point(ec.x, ec.y, transform)
            if s.screenshot_region is not None:
                s.screenshot_region = remap_region(s.screenshot_region, transform)


def sichere_vor_kalibrierung(state: 'AutoClickerState') -> str | None:
    """Legt vor dem Umrechnen ein vollständiges Export-ZIP als Sicherung an.

    Kein eigenes Backup-Format: der Export kann das längst, und der Import
    spielt es wieder ein. Gibt den Pfad zurück, oder None bei Fehlschlag.
    """
    import time as _time

    # Derselbe Ordner, in dem der Editor seine Exporte sucht — damit die Sicherung
    # im Import-Menue ohne Pfadeingabe auftaucht.
    ziel = Path("exports") / f"vor_kalibrierung_{_time.strftime('%Y%m%d_%H%M%S')}.zip"
    ziel.parent.mkdir(parents=True, exist_ok=True)
    # Referenzpunkte sind hier bedeutungslos (es wird nichts remappt beim
    # Zurückspielen), aber identisch dürfen sie nicht sein — sonst rechnet ein
    # späterer Import mit einer Nulldistanz.
    erfolg, meldung = export_bundle(state, str(ziel), (0, 0), (1000, 1000))
    if not erfolg:
        logger.warning("Sicherung vor Kalibrierung fehlgeschlagen: %s", meldung)
        return None
    return str(ziel)


def kalibriere_bestand(state: 'AutoClickerState', transform: dict,
                       mit_scans: bool = True, mit_sequenzen: bool = True,
                       mit_slots: bool = True) -> dict:
    """Rechnet den gespeicherten Bestand auf das neue Bildschirm-Layout um.

    Punkte immer; `mit_scans` zieht die vollständigen Bestände der Item-Scans
    sowie Boss-/Icon-Scans mit, `mit_sequenzen` die Screenshot-Regionen in den
    Sequenz-DATEIEN.
    Die Klick-Stellen der Sequenzen stehen NICHT in der Liste — sie sind Punkte
    und oben schon umgerechnet.

    `mit_slots` ist getrennt schaltbar, obwohl Slots zu den Scans gehören: nach
    einer `slot_repair()`-Reparatur dürfen sie kein zweites Mal wandern.

    Gibt eine Zählung nach Bereich zurück.
    """
    from .persistence import list_available_sequences, save_points
    from .utils import atomic_write, compact_json

    zahl = {"punkte": 0, "slots": 0, "items": 0, "item_scans": 0,
            "boss_scans": 0, "icon_scans": 0, "bosse": 0, "sequenzen": 0}

    # --- alles, was im State liegt: unter Lock mutieren, ausserhalb speichern ---
    with state.lock:
        for p in state.points:
            p.x, p.y = remap_point(p.x, p.y, transform)
            zahl["punkte"] += 1

        if mit_scans:
            for cfg in state.item_scans.values():
                if not cfg.owner_sequence and state.active_sequence is not None:
                    cfg.owner_sequence = state.active_sequence.name
                if mit_slots:
                    for slot in cfg.slots:
                        slot.scan_region = remap_region(slot.scan_region, transform)
                        slot.click_pos = remap_point(
                            slot.click_pos[0], slot.click_pos[1], transform)
                        zahl["slots"] += 1
                for item in cfg.items:
                    if item.confirm_point is not None:
                        cp = item.confirm_point
                        cp.x, cp.y = remap_point(cp.x, cp.y, transform)
                        zahl["items"] += 1
                # Die Slot-Koordinaten und ihr Fenster-Anker bilden ein Paar.
                # Wird nur eine Hälfte transformiert, würde die Runtime beim
                # nächsten Lauf ein zweites, falsches Remapping anwenden.
                if cfg.capture_window_rect:
                    cfg.capture_window_rect = remap_region(
                        cfg.capture_window_rect, transform)
                    zahl["item_scans"] += 1

            for cfg in state.boss_scans.values():
                if not cfg.owner_sequence and state.active_sequence is not None:
                    cfg.owner_sequence = state.active_sequence.name
                cfg.scan_region = remap_region(cfg.scan_region, transform)
                for b in cfg.bosses:
                    b.action_x, b.action_y = remap_point(b.action_x, b.action_y, transform)
                zahl["boss_scans"] += 1

            for b in state.global_bosses:
                b.action_x, b.action_y = remap_point(b.action_x, b.action_y, transform)
                zahl["bosse"] += 1

            for cfg in state.icon_scans.values():
                if not cfg.owner_sequence and state.active_sequence is not None:
                    cfg.owner_sequence = state.active_sequence.name
                cfg.scan_region = remap_region(cfg.scan_region, transform)
                cfg.action_x, cfg.action_y = remap_point(cfg.action_x, cfg.action_y, transform)
                zahl["icon_scans"] += 1

        # Geladene Sequenzen im selben Lock mitziehen — sonst ueberschreibt der
        # naechste save_data() die umgerechneten Dateien mit dem alten Stand.
        if mit_sequenzen:
            for seq in state.sequences.values():
                _remap_sequence_obj(seq, transform)

        boss_scans = list(state.boss_scans.values()) if mit_scans else []
        icon_scans = list(state.icon_scans.values()) if mit_scans else []
        item_scans = list(state.item_scans.values()) if mit_scans else []

    save_points(state)
    if mit_scans:
        save_global_bosses(state)
        for cfg in item_scans:
            save_item_scan(cfg)
        for cfg in boss_scans:
            save_boss_scan(cfg)
        for cfg in icon_scans:
            save_icon_scan(cfg)

    # --- Sequenzen über die Dateien, damit auch nicht geladene erfasst werden ---
    if mit_sequenzen:
        for _name, pfad in list_available_sequences():
            try:
                daten = json.loads(pfad.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
                logger.warning("Kalibrierung: %s nicht lesbar (%s)", pfad.name, e)
                continue
            _remap_sequence_data(daten, transform)
            try:
                atomic_write(pfad, compact_json(daten))
                zahl["sequenzen"] += 1
            except (IOError, OSError) as e:
                logger.warning("Kalibrierung: %s nicht schreibbar (%s)", pfad.name, e)

    return zahl


# =============================================================================
# EXPORT
# =============================================================================

def _export_sequence_bundle(state: 'AutoClickerState', filepath: str,
                            ref_point1, ref_point2, include_data: bool,
                            include_config: bool, source_window=None) -> tuple[bool, str]:
    """Schreibt Sequenzordner unverändert als geordnetes Bundle."""
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
            namen = []
            zaehler = {"item_scans": 0, "boss_scans": 0, "icon_scans": 0,
                       "templates": 0}
            if include_data:
                for name, hauptdatei in list_available_sequences():
                    ordner = Path(hauptdatei).parent
                    archiv_wurzel = PurePosixPath("sequences", ordner.name)
                    for quelle in sorted(p for p in ordner.rglob("*") if p.is_file()):
                        relativ = PurePosixPath(quelle.relative_to(ordner).as_posix())
                        zf.write(quelle, str(archiv_wurzel / relativ))
                        teile = relativ.parts
                        if teile and teile[0] in zaehler and quelle.suffix.lower() == ".json":
                            zaehler[teile[0]] += 1
                        if teile and teile[0] == "templates" and quelle.suffix.lower() == ".png":
                            zaehler["templates"] += 1
                    namen.append(name)
                manifest["contents"]["sequences"] = namen
                manifest["contents"].update({k: v for k, v in zaehler.items() if v})
            if include_config:
                zf.writestr("config.json", compact_json(_export_config(state.config)))
                manifest["contents"]["config"] = True
            zf.writestr(MANIFEST_FILE, compact_json(manifest))
        return True, filepath
    except (IOError, OSError, zipfile.BadZipFile) as e:
        logger.error("Export fehlgeschlagen: %s", e)
        return False, str(e)

def export_bundle(state: 'AutoClickerState', filepath: str,
                  ref_point1: tuple[int, int], ref_point2: tuple[int, int],
                  include_points: bool = True, include_sequences: bool = True,
                  include_slots: bool = True, include_items: bool = True,
                  include_item_scans: bool = True, include_boss_scans: bool = True,
                  include_icon_scans: bool = True,
                  include_config: bool = True,
                  source_window: tuple[int, int, int, int] = None) -> tuple[bool, str]:
    """Exportiert Setup als ZIP-Archiv.

    source_window: Client-Rect (l,t,r,b) des Spielfensters beim Export. Wird im
    Manifest abgelegt, damit der Import die Skalierung automatisch aus der
    Fenstergrösse ableiten kann (Fallback bleibt das 2-Punkt-Verfahren).

    Returns:
        (success, message)
    """
    # Daten werden nicht mehr nach Typ auseinandergerissen. Eine Sequenz ist
    # samt Punkten, Scans, Slots/Items, Vorlagen und Bildern eine Besitzeinheit.
    include_data = any((include_points, include_sequences, include_slots, include_items,
                        include_item_scans, include_boss_scans, include_icon_scans))
    return _export_sequence_bundle(state, filepath, ref_point1, ref_point2,
                                   include_data, include_config, source_window)

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
            if not isinstance(manifest, dict):
                return False, "Ungültiges Manifest: Objekt erwartet"
            if manifest.get("version") != EXPORT_VERSION:
                return False, f"Unbekannte Version: {manifest.get('version')} (erwartet: {EXPORT_VERSION})"
            if not isinstance(manifest.get("contents", {}), dict):
                return False, "Ungültiges Manifest: 'contents' muss ein Objekt sein"
            return True, manifest
    except zipfile.BadZipFile:
        return False, "Datei ist kein gültiges ZIP-Archiv"
    except (IOError, OSError, json.JSONDecodeError) as e:
        return False, str(e)




def _validate_bundle(zf: zipfile.ZipFile, names: list[str]) -> dict:
    """Prüft Version, Größen, doppelte Namen und JSON-Grundstrukturen vor Mutation."""
    if len(names) > MAX_BUNDLE_FILES:
        raise ValueError(f"Zu viele Dateien im Bundle ({len(names)})")
    folded = [name.casefold() for name in names]
    if len(folded) != len(set(folded)):
        raise ValueError("Bundle enthält doppelte Dateinamen")

    infos = zf.infolist()
    total_size = sum(info.file_size for info in infos)
    if total_size > MAX_BUNDLE_TOTAL_SIZE:
        raise ValueError("Bundle ist entpackt zu groß")
    if any(info.file_size > MAX_BUNDLE_FILE_SIZE for info in infos):
        raise ValueError("Eine Datei im Bundle ist zu groß")

    manifest = json.loads(zf.read(MANIFEST_FILE).decode("utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("Ungültiges Manifest: Objekt erwartet")
    if manifest.get("version") != EXPORT_VERSION:
        raise ValueError(
            f"Unbekannte Bundle-Version {manifest.get('version')} (erwartet {EXPORT_VERSION})")
    if not isinstance(manifest.get("contents", {}), dict):
        raise ValueError("Ungültiges Manifest: 'contents' muss ein Objekt sein")

    # Alles im Bundle ist ein Objekt — bis auf die Boss-Bibliothek, die als
    # Liste in den Boss-Scans der Sequenz liegt. Die Sonderfaelle fuer
    # `points.json`, `slots.json` und `items.json` sind mit dem globalen
    # Bestand entfallen; die drei Dateien gibt es in keinem Bundle mehr.
    for name in names:
        if not name.lower().endswith(".json"):
            continue
        data = json.loads(zf.read(name).decode("utf-8"))
        expected = list if name.endswith("/boss_scans/bibliothek.json") else None
        if expected is None and name != MANIFEST_FILE:
            expected = dict
        if expected is not None and not isinstance(data, expected):
            raise ValueError(f"Ungültige Struktur in {name}")
    return manifest


class _ImportTransaction:
    """Sichert State und importrelevante Dateien und rollt bei Fehlern zurück."""

    _STATE_FIELDS = (
        "points", "sequences", "global_slots", "global_items", "item_scans",
        "boss_scans", "icon_scans", "global_bosses",
    )
    # Was ausserhalb der Sequenzordner liegt und ein Import anfassen kann.
    # Hier standen einmal `points.json`, `slots/slots.json`, `items/items.json`
    # und `boss_scans/global/bosses.json` — alle vier gibt es nicht mehr, sie
    # sind in die Besitzeinheit gewandert.
    _FIXED_FILES = ("config.json",)
    _ROOTS = ("sequences",)

    def __init__(self, state):
        self.state = state
        with state.lock:
            self.state_snapshot = {
                field: copy.deepcopy(getattr(state, field)) for field in self._STATE_FIELDS
            }
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
        from .config import uebernehmen

        with self.state.lock:
            for field, value in self.state_snapshot.items():
                setattr(self.state, field, value)
            uebernehmen(self.state.config, self.config_snapshot)

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
























# Was in der Abschlussmeldung steht, in dieser Reihenfolge. Als Tabelle statt als
# neun `if`-Blöcke: eine neue Datenart ist damit eine Zeile, und niemand vergisst
# die Meldung — genau das war bei `global_bosses` schon einmal passiert (der
# Schlüssel fehlte im `stats`-Vorbelegung und wurde nur per `.get()` gerettet).




def _sicherer_bundle_pfad(name: str) -> Optional[PurePosixPath]:
    """Ein relativer Sequenzpfad im Archiv oder None."""
    pfad = PurePosixPath(name)
    if ("\\" in name or ":" in name or "\x00" in name
            or pfad.is_absolute() or ".." in pfad.parts or len(pfad.parts) < 3
            or pfad.parts[0] != "sequences"):
        return None
    return pfad


def _remap_sequence_folder(ordner: Path, transform: dict) -> None:
    """Transformiert alle koordinatenhaltigen JSON-Dateien eines Importordners."""
    if ist_identitaet(transform):
        return
    for pfad in ordner.rglob("*.json"):
        data = json.loads(pfad.read_text(encoding="utf-8"))
        relativ = pfad.relative_to(ordner).parts
        if relativ == ("boss_scans", "bibliothek.json"):
            # Die Bibliothek enthält Profile mit Punkt-IDs, keine Regionen.
            # Ihre Punkte werden in sequence.json genau einmal umgerechnet.
            continue
        if pfad.name == "sequence.json":
            for punkt in data.get("points") or []:
                punkt["x"], punkt["y"] = remap_point(
                    int(punkt.get("x", 0)), int(punkt.get("y", 0)), transform)
            _remap_sequence_data(data, transform)
        elif relativ and relativ[0] == "item_scans":
            for slot in (data.get("slots") or {}).values():
                if slot.get("scan_region"):
                    slot["scan_region"] = list(remap_region(tuple(slot["scan_region"]), transform))
                if slot.get("click_pos"):
                    slot["click_pos"] = list(remap_point(*slot["click_pos"], transform))
            if data.get("capture_window_rect"):
                data["capture_window_rect"] = list(
                    remap_region(tuple(data["capture_window_rect"]), transform))
        elif relativ and relativ[0] in ("boss_scans", "icon_scans"):
            if data.get("scan_region"):
                data["scan_region"] = list(remap_region(tuple(data["scan_region"]), transform))
        atomic_write(pfad, compact_json(data))


def _import_sequence_bundle(state: 'AutoClickerState', zf: zipfile.ZipFile,
                            names: list[str], manifest: dict, transform: dict,
                            import_sequences: bool, import_config: bool,
                            merge: bool) -> tuple[bool, str]:
    """Importiert das neue, nach Sequenzordnern geordnete Bundle."""
    from .config import save_config
    from .persistence import ensure_sequences_dir, load_sequence_file

    importierte = []
    with tempfile.TemporaryDirectory(prefix="autoclicker_import_") as temp:
        temp_root = Path(temp)
        if import_sequences:
            for name in names:
                archiv = _sicherer_bundle_pfad(name)
                if archiv is None or name.endswith("/"):
                    continue
                ziel = temp_root.joinpath(*archiv.parts[1:]).resolve()
                if not ziel.is_relative_to(temp_root.resolve()):
                    raise ValueError(f"Archivpfad verlässt den Importordner: {name}")
                ziel.parent.mkdir(parents=True, exist_ok=True)
                ziel.write_bytes(zf.read(name))

            for quelle in sorted(p for p in temp_root.iterdir() if p.is_dir()):
                hauptdatei = quelle / "sequence.json"
                if not hauptdatei.is_file():
                    raise ValueError(f"{quelle.name}: sequence.json fehlt")
                _remap_sequence_folder(quelle, transform)
                data = json.loads(hauptdatei.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError(f"{quelle.name}/sequence.json ist ungültig")

                basis = sanitize_filename(str(data.get("name") or quelle.name))
                ziel = ensure_sequences_dir() / basis
                if merge:
                    nummer = 2
                    while ziel.exists():
                        ziel = ensure_sequences_dir() / f"{basis}_{nummer}"
                        nummer += 1
                    if ziel.name != basis:
                        data["name"] = ziel.name
                        atomic_write(hauptdatei, compact_json(data))
                elif ziel.exists():
                    shutil.rmtree(ziel)
                shutil.copytree(quelle, ziel)
                seq = load_sequence_file(ziel / "sequence.json")
                if seq is None:
                    raise ValueError(f"{ziel.name}: importierte Sequenz ist nicht lesbar")
                with state.lock:
                    state.sequences[seq.name] = seq
                importierte.append(seq.name)

        if import_config and "config.json" in names:
            roh = json.loads(zf.read("config.json").decode("utf-8"))
            if isinstance(roh, dict):
                erlaubt = {k: v for k, v in roh.items() if k not in _SENSITIVE_CONFIG_KEYS}
                for key, wert in erlaubt.items():
                    if hasattr(state.config, key):
                        setattr(state.config, key, wert)
                save_config(state.config)

    teile = [f"{len(importierte)} Sequenz(en) mit zugehörigen Scans und Vorlagen"]
    if import_config and "config.json" in names:
        teile.append("Einstellungen")
    return True, ", ".join(teile)


def import_bundle(state: 'AutoClickerState', filepath: str,
                  transform: dict = None,
                  import_points: bool = True, import_sequences: bool = True,
                  import_slots: bool = True, import_items: bool = True,
                  import_item_scans: bool = True, import_boss_scans: bool = True,
                  import_icon_scans: bool = True,
                  import_config: bool = True, merge: bool = True) -> tuple[bool, str]:
    """Importiert ein Setup aus einer ZIP-Datei.

    Nur noch der Ablauf: **die Reihenfolge ist die eigentliche Aussage dieser
    Funktion**, und sie ist nicht beliebig. Templates zuerst (Items verweisen
    darauf), dann Punkte (Sequenzen verweisen darauf), dann die Sequenzen; Slots
    und Items vor den Item-Scans, weil die per Namen auf sie zeigen und am Ende
    aufgelöst werden. Zuletzt die Config und ein Speichern für Punkte + Sequenzen.

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

            _validate_bundle(zf, names)
            manifest = json.loads(zf.read(MANIFEST_FILE).decode("utf-8"))
            # **Es gibt genau einen Import-Weg.** Daneben stand bis hierher eine
            # zweite, vollstaendige Implementierung fuer Buendel aus der Zeit des
            # globalen Bestands (`points.json`, `slots.json`, `items.json`,
            # Scan-Ordner im Wurzelverzeichnis). Sie war nicht nur Altlast,
            # sondern **kaputt**: Vorlagen landeten in `items/templates/`, wo
            # seit dem Umzug auf Besitzeinheiten keine Sequenz mehr nachsieht,
            # und `_imp_items` schrieb ueber `save_global_items()`, das ohne
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
                    state, zf, names, manifest, transform,
                    import_sequences or import_points or import_slots or import_items
                    or import_item_scans or import_boss_scans or import_icon_scans,
                    import_config, merge)

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
    keinen Punkt haben kann: die Screenshot-Region.
    """
    for s in _iter_import_steps(seq_data):
        if s.get("point_id") is None and (s.get("x") is not None or s.get("y") is not None):
            s["x"], s["y"] = remap_point(s.get("x", 0), s.get("y", 0), transform)
        if s.get("wait_point_id") is None and s.get("wait_pixel"):
            wp = s["wait_pixel"]
            s["wait_pixel"] = list(remap_point(wp[0], wp[1], transform))
        if s.get("else_point_id") is None and (
                s.get("else_x") is not None or s.get("else_y") is not None):
            s["else_x"], s["else_y"] = remap_point(
                s.get("else_x", 0), s.get("else_y", 0), transform)
        if s.get("screenshot_region"):
            sr = s["screenshot_region"]
            s["screenshot_region"] = list(remap_region(tuple(sr), transform))


# Die drei Referenz-Felder eines Schritts. Wer eine vierte Stelle einbaut, traegt sie
# hier ein - sonst zeigt sie nach einem Import auf einen fremden lokalen Punkt.
_REF_KEYS = ("point_id", "wait_point_id", "else_point_id", "verify_point_id")




