"""
Import/Export-Modul für den Autoclicker.
Exportiert komplette Setups als ZIP-Archiv und importiert sie
mit optionalem Koordinaten-Remapping für andere Bildschirme.
"""

import json
import logging
import zipfile
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .models import AutoClickerState

from .persistence import (
    TEMPLATES_DIR, _sequence_to_dict, _item_to_dict, _slot_to_dict,
    _boss_profile_to_dict, _point_to_dict,
    _item_scan_to_dict, _boss_scan_to_dict, _icon_scan_to_dict,
    load_sequence_file, _item_from_dict, _slot_from_dict, _boss_profile_from_dict,
    resolve_scan_references,
    KIND_ITEMS, KIND_ITEM_SCAN, KIND_POINTS, KIND_SLOTS, migrate,
    save_data, save_global_slots, save_global_items,
    save_item_scan, save_boss_scan, save_icon_scan, save_global_bosses,
)
from .models import (
    DEFAULT_MIN_CONFIDENCE,
    ClickPoint, ItemScanConfig, BossScanConfig, IconScanConfig,
    BOSS_ACTION_SKIP, BOSS_ACTION_CLICK, ICON_ACTION_CLICK, ACTION_CLICK,
)
from .utils import atomic_write, compact_json, sanitize_filename, warn

logger = logging.getLogger("autoclicker")

EXPORT_VERSION = 1
MANIFEST_FILE = "manifest.json"


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

    Erfasst: Punkte, direkte Klick-Schritte in Sequenzen (inkl. else-Klick) sowie
    Klick-Aktionen von Boss- und Icon-Scans. Scan-interne Positionen (Slots,
    confirm_points) bleiben aussen vor — es geht um die eigentlichen Klick-Ziele.
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
                    # Echter Klick-Schritt: nicht wait-only / kein Scan/Key/Screenshot
                    if not (s.wait_only or s.item_scan or s.boss_scan or s.icon_scan
                            or s.screenshot_only or s.key_press):
                        positions.append((f"Seq '{name}'/{gname} #{i}", s.x, s.y))
                    ec = s.else_config
                    if ec and ec.action == ACTION_CLICK:
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

    Ein Punkt kann nur verschieben, nicht skalieren — dafür braucht es zwei
    (`compute_transform`). Das reicht, solange die Auflösung dieselbe ist und sich
    nur die Lage des Monitors im virtuellen Desktop geändert hat; genau das
    passiert, wenn Windows die Bildschirme neu anordnet.
    """
    return {"scale_x": 1.0, "scale_y": 1.0,
            "offset_x": neu[0] - alt[0], "offset_y": neu[1] - alt[1]}


def ist_identitaet(transform: dict) -> bool:
    """True, wenn der Transform nichts verändern würde."""
    return (transform["scale_x"] == 1.0 and transform["scale_y"] == 1.0
            and round(transform["offset_x"]) == 0 and round(transform["offset_y"]) == 0)


# =============================================================================
# KALIBRIERUNG (Bildschirm-Layout hat sich geändert)
# =============================================================================
#
# Dasselbe Remapping wie beim Import, nur auf den EIGENEN Bestand statt auf ein
# frisch entpacktes Bundle. Der Import kann das nicht ersetzen: er legt Daten an,
# statt vorhandene zu korrigieren — importiert man sein eigenes Export-ZIP zurück,
# steht am Ende alles doppelt da.

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

    Die Kalibrierung schreibt Punkte, Slots, Scans und Sequenzdateien in einem Rutsch
    um — ohne Rückweg, wenn der Referenzpunkt danebenlag. Ein eigenes Backup-Format
    dafür zu bauen wäre Doppelarbeit: der Export kann das längst, und der Import
    spielt es wieder ein.

    Gibt den Pfad zurück, oder None wenn die Sicherung fehlschlug.
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

    Punkte immer; `mit_scans` zieht Item-Bestätigungsklicks sowie Boss-/Icon-Scans
    mit; `mit_sequenzen` die Screenshot-Regionen in den Sequenz-DATEIEN.

    Die Klick-Stellen der Sequenzen stehen NICHT mehr in dieser Liste: sie sind
    Punkte, und die sind oben schon umgerechnet. Das ist der eigentliche Gewinn der
    Umstellung — vorher musste jede Kopie einzeln erwischt werden, und die eine, die
    man vergass, fiel erst beim nächsten Lauf auf.

    `mit_slots` steht bewusst getrennt, obwohl Slots zu den Scans gehören: eine
    aus einer Maus-Position abgeleitete Verschiebung ist für ein Klick-Ziel gut
    genug, für eine Scan-Region aber nur eine Näherung — ein paar Pixel daneben
    schneiden das Item-Icon an. Dafür gibt es `slot_repair()`, das die Slots misst
    statt sie zu verschieben. Deshalb muss sich beides einzeln schalten lassen:
    nach einer Reparatur dürfen die Slots kein zweites Mal wandern.

    Gibt eine Zählung nach Bereich zurück.
    """
    from .persistence import list_available_sequences, save_points
    from .utils import atomic_write, compact_json

    zahl = {"punkte": 0, "slots": 0, "items": 0, "boss_scans": 0,
            "icon_scans": 0, "bosse": 0, "sequenzen": 0}

    # --- alles, was im State liegt: unter Lock mutieren, ausserhalb speichern ---
    with state.lock:
        for p in state.points:
            p.x, p.y = remap_point(p.x, p.y, transform)
            zahl["punkte"] += 1

        if mit_scans and mit_slots:
            for slot in state.global_slots.values():
                slot.scan_region = remap_region(slot.scan_region, transform)
                slot.click_pos = remap_point(slot.click_pos[0], slot.click_pos[1], transform)
                zahl["slots"] += 1

        if mit_scans:
            for item in state.global_items.values():
                if item.confirm_point is not None:
                    cp = item.confirm_point
                    cp.x, cp.y = remap_point(cp.x, cp.y, transform)
                    zahl["items"] += 1

            for cfg in state.boss_scans.values():
                cfg.scan_region = remap_region(cfg.scan_region, transform)
                for b in cfg.bosses:
                    b.action_x, b.action_y = remap_point(b.action_x, b.action_y, transform)
                zahl["boss_scans"] += 1

            for b in state.global_bosses:
                b.action_x, b.action_y = remap_point(b.action_x, b.action_y, transform)
                zahl["bosse"] += 1

            for cfg in state.icon_scans.values():
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

    save_points(state)
    if mit_scans and mit_slots:
        save_global_slots(state)
    if mit_scans:
        save_global_items(state)
        save_global_bosses(state)
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
    try:
        manifest = {
            "version": EXPORT_VERSION,
            "reference_points": {
                "point1": list(ref_point1),
                "point2": list(ref_point2),
            },
            "contents": {},
        }
        if source_window:
            manifest["source_window"] = list(source_window)

        with zipfile.ZipFile(filepath, "w", zipfile.ZIP_DEFLATED) as zf:
            # Punkte
            if include_points:
                with state.lock:
                    points_data = [_point_to_dict(p) for p in state.points]
                if points_data:
                    zf.writestr("points.json", compact_json(points_data))
                    manifest["contents"]["points"] = len(points_data)

            # Sequenzen
            if include_sequences:
                with state.lock:
                    seqs = {name: _sequence_to_dict(seq)
                            for name, seq in state.sequences.items()}
                for name, seq_data in seqs.items():
                    safe = sanitize_filename(name)
                    zf.writestr(f"sequences/{safe}.json", compact_json(seq_data))
                manifest["contents"]["sequences"] = list(seqs.keys())
                # Beschreibungen separat ins Manifest, damit der Empfänger sie
                # vor dem Import sieht (ohne jede Sequenz-Datei öffnen zu müssen)
                descriptions = {name: seq_data["description"]
                                for name, seq_data in seqs.items()
                                if seq_data.get("description")}
                if descriptions:
                    manifest["sequence_descriptions"] = descriptions

            # Slots
            if include_slots:
                with state.lock:
                    slots_data = {name: _slot_to_dict(slot) for name, slot in state.global_slots.items()}
                if slots_data:
                    zf.writestr("slots.json", compact_json(slots_data))
                    manifest["contents"]["slots"] = len(slots_data)

            # Items + Templates
            template_files = set()
            if include_items:
                with state.lock:
                    items_data = {name: _item_to_dict(item)
                                  for name, item in state.global_items.items()}
                if items_data:
                    zf.writestr("items.json", compact_json(items_data))
                    manifest["contents"]["items"] = len(items_data)
                    for item_data in items_data.values():
                        if item_data.get("template"):
                            template_files.add(item_data["template"])

            # Item-Scans
            if include_item_scans:
                with state.lock:
                    scans = dict(state.item_scans)
                scan_names = []
                for name, config in scans.items():
                    safe = sanitize_filename(name)
                    zf.writestr(f"item_scans/{safe}.json", compact_json(_item_scan_to_dict(config)))
                    scan_names.append(name)
                    for i in config.items:
                        if i.template:
                            template_files.add(i.template)
                if scan_names:
                    manifest["contents"]["item_scans"] = scan_names

            # Boss-Scans
            if include_boss_scans:
                with state.lock:
                    bscans = dict(state.boss_scans)
                bscan_names = []
                for name, config in bscans.items():
                    safe = sanitize_filename(name)
                    zf.writestr(f"boss_scans/{safe}.json", compact_json(_boss_scan_to_dict(config)))
                    bscan_names.append(name)
                    for b in config.bosses:
                        if b.template:
                            template_files.add(b.template)
                if bscan_names:
                    manifest["contents"]["boss_scans"] = bscan_names

                # Globale Boss-Bibliothek (gilt in jedem Boss-Scan)
                with state.lock:
                    gbosses = list(state.global_bosses)
                if gbosses:
                    zf.writestr("global_bosses.json",
                                compact_json([_boss_profile_to_dict(b) for b in gbosses]))
                    manifest["contents"]["global_bosses"] = len(gbosses)
                    for b in gbosses:
                        if b.template:
                            template_files.add(b.template)

            # Icon-Scans
            if include_icon_scans:
                with state.lock:
                    iscans = dict(state.icon_scans)
                iscan_names = []
                for name, config in iscans.items():
                    safe = sanitize_filename(name)
                    zf.writestr(f"icon_scans/{safe}.json", compact_json(_icon_scan_to_dict(config)))
                    iscan_names.append(name)
                    if config.template:
                        template_files.add(config.template)
                if iscan_names:
                    manifest["contents"]["icon_scans"] = iscan_names

            # Template-PNGs einpacken
            packed_templates = 0
            for tpl in template_files:
                tpl_path = Path(TEMPLATES_DIR) / tpl
                if tpl_path.exists():
                    zf.write(tpl_path, f"templates/{tpl}")
                    packed_templates += 1
            if packed_templates:
                manifest["contents"]["templates"] = packed_templates

            # Config (gefiltert)
            if include_config:
                cfg_data = _export_config(state.config)
                zf.writestr("config.json", compact_json(cfg_data))
                manifest["contents"]["config"] = True

            # Manifest schreiben
            zf.writestr(MANIFEST_FILE, compact_json(manifest))

        return True, filepath

    except (IOError, OSError, zipfile.BadZipFile) as e:
        logger.error(f"Export fehlgeschlagen: {e}")
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
            if manifest.get("version") != EXPORT_VERSION:
                return False, f"Unbekannte Version: {manifest.get('version')} (erwartet: {EXPORT_VERSION})"
            return True, manifest
    except zipfile.BadZipFile:
        return False, "Datei ist kein gültiges ZIP-Archiv"
    except (IOError, OSError, json.JSONDecodeError) as e:
        return False, str(e)


class _Import:
    """Der Zustand EINES Import-Durchgangs — das, was alle Stufen teilen.

    **Der Import war eine Funktion mit 292 Zeilen und 69 Verzweigungen** — und
    zugleich die Stelle, die am meisten auf Platte schreibt (Templates, Slots,
    Items, drei Scan-Arten, Sequenzen, Punkte und die Config). Diese beiden
    Eigenschaften in einer Funktion sind die unangenehmste Kombination, die eine
    Codebasis haben kann: die Tests konnten unmöglich alle Pfade treffen, und
    jeder ungetroffene Pfad schrieb Dateien.

    Dasselbe Rezept wie bei `edit_item_scan()` im Item-Scan-Editor: Stufen statt
    eines Blocks. Jede Stufe ist eine eigene Funktion mit einem klaren Auftrag,
    nimmt diesen Durchgang entgegen und zählt in `stats` mit. Damit lässt sich
    jede einzeln prüfen — bis hierher ging das nur über das ZIP als Ganzes.
    """

    def __init__(self, zf, names: list, state, transform: dict, merge: bool):
        self.zf = zf
        self.names = names
        self.state = state
        self.transform = transform
        self.merge = merge
        self.stats: dict = {"points": 0, "sequences": 0, "slots": 0, "items": 0,
                            "item_scans": 0, "boss_scans": 0, "icon_scans": 0,
                            "templates": 0}
        # Kollidiert eine importierte Punkt-ID mit einer lokalen, bekommt der Punkt
        # eine neue — und diese Zuordnung merkt sich das, damit die Sequenz-Schritte
        # ihre `point_id` nachziehen können.
        self.id_map: dict[int, int] = {}

    def lies(self, name: str) -> dict:
        """Eine JSON-Datei aus dem Bundle."""
        return json.loads(self.zf.read(name).decode("utf-8"))

    def dateien(self, ordner: str, endung: str = ".json") -> list:
        """Alle Bundle-Einträge eines Ordners."""
        return [n for n in self.names
                if n.startswith(ordner) and n.endswith(endung)]


def _imp_templates(lauf: _Import) -> None:
    """Bilddateien auspacken — zuerst, weil Items und Scans darauf verweisen."""
    templates_dir = Path(TEMPLATES_DIR)
    templates_dir.mkdir(parents=True, exist_ok=True)
    resolved_tpl_dir = templates_dir.resolve()
    for name in lauf.dateien("templates/", ".png"):
        tpl_name = name[len("templates/"):]
        tpl_path = templates_dir / tpl_name
        # Ein Bundle ist eine Datei von aussen: ein Eintrag wie `templates/../../x.png`
        # schriebe sonst irgendwohin. Nicht paranoid, sondern der Standardfehler beim
        # Auspacken von Archiven.
        if not tpl_path.resolve().is_relative_to(resolved_tpl_dir):
            logger.warning(f"Template-Pfad ausserhalb des Zielordners übersprungen: {name}")
            continue
        # Template kann in einem Unterordner liegen (templates/sub/x.png)
        # — Zielverzeichnis anlegen, sonst FileNotFoundError beim Schreiben.
        tpl_path.parent.mkdir(parents=True, exist_ok=True)
        tpl_path.write_bytes(lauf.zf.read(name))
        lauf.stats["templates"] += 1


def _imp_punkte(lauf: _Import, import_points: bool, import_sequences: bool) -> None:
    """Punkte übernehmen und dabei ID-Kollisionen auflösen.

    **Sequenzen ohne ihre Punkte gibt es nicht mehr**: seit die Koordinate nur noch
    im Punkt steht, wäre eine Sequenz ohne Punkte eine Liste von Schritten, die
    nirgendwohin zeigen. `import_points=False` heisst deshalb „keine Punkte, die
    niemand braucht" — die referenzierten kommen trotzdem mit.
    """
    gebraucht: Optional[set] = None
    if not import_points and import_sequences:
        gebraucht = set()
        for n in lauf.dateien("sequences/"):
            gebraucht |= _referenzierte_punkte(lauf.lies(n))

    if not (import_points or gebraucht) or "points.json" not in lauf.names:
        return

    points_data, _m = migrate(lauf.lies("points.json"), KIND_POINTS)
    if gebraucht is not None:
        points_data = [p for p in points_data if p.get("id") in gebraucht]
    with lauf.state.lock:
        if not lauf.merge:
            lauf.state.points.clear()
        existing_ids = {p.id for p in lauf.state.points}
        next_id = max(existing_ids) + 1 if existing_ids else 1
        for p in points_data:
            x, y = remap_point(p["x"], p["y"], lauf.transform)
            alt_id = p.get("id")
            pid = alt_id if alt_id is not None else next_id
            while pid in existing_ids:
                pid = next_id
                next_id += 1
            color_raw = p.get("color")
            color = tuple(int(v) for v in color_raw) if color_raw else None
            lauf.state.points.append(ClickPoint(x, y, p.get("name", ""), pid,
                                                color=color, source=p.get("source", "")))
            existing_ids.add(pid)
            next_id = max(next_id, pid + 1)
            if alt_id is not None:
                lauf.id_map[alt_id] = pid
            lauf.stats["points"] += 1


def _imp_sequenzen(lauf: _Import) -> None:
    """Sequenzdateien schreiben und geladen in den State legen."""
    for name in lauf.dateien("sequences/"):
        seq_data = lauf.lies(name)
        _remap_sequence_data(seq_data, lauf.transform)
        _remap_point_ids(seq_data, lauf.id_map)
        seq_name = seq_data.get("name", Path(name).stem)
        seq_path = Path("sequences") / f"{sanitize_filename(seq_name)}.json"
        seq_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(seq_path, compact_json(seq_data))
        # Mit den frisch importierten Punkten aufloesen, nicht mit denen von
        # Platte: points.json wird erst am Ende des Imports geschrieben.
        seq = load_sequence_file(seq_path, list(lauf.state.points))
        if seq:
            with lauf.state.lock:
                lauf.state.sequences[seq.name] = seq
            lauf.stats["sequences"] += 1


def _imp_slots(lauf: _Import) -> None:
    if "slots.json" not in lauf.names:
        return
    slots_data, _m = migrate(lauf.lies("slots.json"), KIND_SLOTS)
    with lauf.state.lock:
        if not lauf.merge:
            lauf.state.global_slots.clear()
        for sname, s in slots_data.items():
            slot = _slot_from_dict(sname, s)
            slot.scan_region = remap_region(slot.scan_region, lauf.transform)
            slot.click_pos = remap_point(slot.click_pos[0], slot.click_pos[1],
                                         lauf.transform)
            lauf.state.global_slots[sname] = slot
            lauf.stats["slots"] += 1
    save_global_slots(lauf.state)


def _imp_items(lauf: _Import) -> None:
    if "items.json" not in lauf.names:
        return
    items_data, _m = migrate(lauf.lies("items.json"), KIND_ITEMS)
    with lauf.state.lock:
        if not lauf.merge:
            lauf.state.global_items.clear()
        for iname, i in items_data.items():
            item = _item_from_dict(i, iname)
            if item.confirm_point:
                nx, ny = remap_point(item.confirm_point.x, item.confirm_point.y,
                                     lauf.transform)
                item.confirm_point = ClickPoint(nx, ny)
            lauf.state.global_items[iname] = item
            lauf.stats["items"] += 1
    save_global_items(lauf.state)


def _imp_item_scans(lauf: _Import) -> None:
    """Item-Scans — **nur Namen, keine Koordinaten.**

    Die Koordinaten der Slots werden beim Import von `slots.json` umgerechnet und
    nicht ein zweites Mal pro Scan. Genau diese Doppelpflege fiel mit der Referenz
    weg.
    """
    for name in lauf.dateien("item_scans/"):
        scan_data, _m = migrate(lauf.lies(name), KIND_ITEM_SCAN)
        config = ItemScanConfig(
            name=scan_data["name"],
            slot_names=[str(n) for n in scan_data.get("slot_names", [])],
            item_names=[str(n) for n in scan_data.get("item_names", [])],
            color_tolerance=scan_data.get("color_tolerance", 40),
            learn_unknown=scan_data.get("learn_unknown", False),
        )
        with lauf.state.lock:
            lauf.state.item_scans[config.name] = config
        save_item_scan(config)
        lauf.stats["item_scans"] += 1
    # Referenzen gegen die (gerade importierten) globalen Slots/Items auflösen -
    # sonst laufen die Scans bis zum nächsten Start leer.
    for meldung in resolve_scan_references(lauf.state):
        print(warn(meldung))


def _boss_mit_remap(lauf: _Import, roh: dict):
    """Ein Boss-Profil aus dem Bundle, Klick-Koordinate umgerechnet.

    Nur Klick-Bosse haben sinnvolle Koordinaten — für skip/key-Bosse sind
    `action_x/y` bedeutungslos (Default 0) und dürfen nicht durch den
    Affine-Transform verschoben werden, sonst wandern sie von (0,0) irgendwohin.
    """
    boss = _boss_profile_from_dict(roh)
    if boss.action == BOSS_ACTION_CLICK:
        boss.action_x, boss.action_y = remap_point(boss.action_x, boss.action_y,
                                                   lauf.transform)
    return boss


def _imp_boss_scans(lauf: _Import) -> None:
    for name in lauf.dateien("boss_scans/"):
        bscan_data = lauf.lies(name)
        config = BossScanConfig(
            name=bscan_data["name"],
            scan_region=remap_region(tuple(bscan_data["scan_region"]), lauf.transform),
            color_tolerance=bscan_data.get("color_tolerance", 30),
            default_action=bscan_data.get("default_action", BOSS_ACTION_SKIP),
            default_scan=bscan_data.get("default_scan"),
            bosses=[_boss_mit_remap(lauf, b) for b in bscan_data.get("bosses", [])],
            use_llm=bscan_data.get("use_llm", False),
            llm_fallback=bscan_data.get("llm_fallback", True),
            use_ocr=bscan_data.get("use_ocr", False),
            ocr_fallback=bscan_data.get("ocr_fallback", True),
        )
        with lauf.state.lock:
            lauf.state.boss_scans[config.name] = config
        save_boss_scan(config)
        lauf.stats["boss_scans"] += 1

    _imp_globale_bosse(lauf)


def _imp_globale_bosse(lauf: _Import) -> None:
    """Die Boss-Bibliothek — Merge nach Name, der Import gewinnt."""
    if "global_bosses.json" not in lauf.names:
        return
    imported = [_boss_mit_remap(lauf, b) for b in lauf.lies("global_bosses.json")]
    if not imported:
        return
    with lauf.state.lock:
        imported_names = {b.name for b in imported}
        lauf.state.global_bosses = [
            b for b in lauf.state.global_bosses if b.name not in imported_names
        ] + imported
    save_global_bosses(lauf.state)
    lauf.stats["global_bosses"] = len(imported)


def _imp_icon_scans(lauf: _Import) -> None:
    for name in lauf.dateien("icon_scans/"):
        iscan_data = lauf.lies(name)
        action = iscan_data.get("action", ICON_ACTION_CLICK)
        ax, ay = iscan_data.get("action_x", 0), iscan_data.get("action_y", 0)
        # Wie beim Boss: nur Klick-Aktionen haben eine Stelle, die umzurechnen wäre.
        if action == ICON_ACTION_CLICK:
            ax, ay = remap_point(ax, ay, lauf.transform)
        config = IconScanConfig(
            name=iscan_data["name"],
            scan_region=remap_region(tuple(iscan_data["scan_region"]), lauf.transform),
            template=iscan_data.get("template"),
            min_confidence=iscan_data.get("min_confidence", DEFAULT_MIN_CONFIDENCE),
            marker_colors=[tuple(c) for c in iscan_data.get("marker_colors", [])],
            color_tolerance=iscan_data.get("color_tolerance", 30),
            action=action,
            action_x=ax,
            action_y=ay,
            action_key=iscan_data.get("action_key"),
            action_delay=iscan_data.get("action_delay", 0),
        )
        with lauf.state.lock:
            lauf.state.icon_scans[config.name] = config
        save_icon_scan(config)
        lauf.stats["icon_scans"] += 1


def _imp_config(lauf: _Import) -> None:
    """Die Config — ohne die Felder, die zur MASCHINE gehören, nicht zum Setup."""
    if "config.json" not in lauf.names:
        return
    cfg_data = lauf.lies("config.json")
    for k in _SENSITIVE_CONFIG_KEYS:
        cfg_data.pop(k, None)
    current = lauf.state.config.to_dict()
    current.update(cfg_data)
    from .config import AppConfig, save_config, uebernehmen
    with lauf.state.lock:
        # Hineinschreiben statt austauschen: state.config ist im Hauptprozess
        # dasselbe Objekt wie das Modul-CONFIG, und ein Austausch liesse jeden
        # Leser davon auf dem alten Stand.
        uebernehmen(lauf.state.config, AppConfig.from_dict(current))
    save_config(lauf.state.config)


# Was in der Abschlussmeldung steht, in dieser Reihenfolge. Als Tabelle statt als
# neun `if`-Blöcke: eine neue Datenart ist damit eine Zeile, und niemand vergisst
# die Meldung — genau das war bei `global_bosses` schon einmal passiert (der
# Schlüssel fehlte im `stats`-Vorbelegung und wurde nur per `.get()` gerettet).
_IMPORT_MELDUNG = (
    ("points", "Punkt(e)"), ("sequences", "Sequenz(en)"),
    ("slots", "Slot(s)"), ("items", "Item(s)"),
    ("item_scans", "Item-Scan(s)"), ("boss_scans", "Boss-Scan(s)"),
    ("global_bosses", "globale(r) Boss(e)"), ("icon_scans", "Icon-Scan(s)"),
    ("templates", "Template(s)"),
)


def _import_meldung(stats: dict) -> str:
    teile = [f"{stats[k]} {wort}" for k, wort in _IMPORT_MELDUNG if stats.get(k)]
    return ", ".join(teile) if teile else "Nichts importiert"


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

            lauf = _Import(zf, names, state, transform, merge)

            _imp_templates(lauf)
            _imp_punkte(lauf, import_points, import_sequences)
            if import_sequences:
                _imp_sequenzen(lauf)
            if import_slots:
                _imp_slots(lauf)
            if import_items:
                _imp_items(lauf)
            if import_item_scans:
                _imp_item_scans(lauf)
            if import_boss_scans:
                _imp_boss_scans(lauf)
            if import_icon_scans:
                _imp_icon_scans(lauf)
            if import_config:
                _imp_config(lauf)

            # Punkte und Sequenzen leben im State; alles andere hat seine Datei
            # schon in seiner Stufe geschrieben.
            if lauf.stats["points"] or lauf.stats["sequences"]:
                save_data(state)

            return True, _import_meldung(lauf.stats)

    except (IOError, OSError, zipfile.BadZipFile, json.JSONDecodeError, KeyError) as e:
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


def _referenzierte_punkte(seq_data: dict) -> set:
    """Alle Punkt-IDs, auf die diese Sequenz zeigt."""
    raus = set()
    for s in _iter_import_steps(seq_data):
        for key in _REF_KEYS:
            if s.get(key) is not None:
                raus.add(s[key])
    return raus


def _remap_point_ids(seq_data: dict, id_map: dict[int, int]) -> None:
    """Zieht die Punkt-Referenzen der Schritte auf die IDs nach, die die Punkte hier
    bekommen haben.

    Der Import vergibt einem Punkt eine neue ID, wenn seine alte lokal schon belegt ist.
    Bleibt der Schritt dann auf der alten ID stehen, zeigt er auf einen FREMDEN lokalen
    Punkt - und `resolve_point_references()` zieht den Schritt beim naechsten Lauf brav
    dorthin und meldet das auch noch als Erfolg. Genau deshalb wird hier nachgezogen.

    Eine Referenz wird NICHT mehr fallengelassen, wenn die Zuordnung fehlt: seit die
    Koordinate nur noch im Punkt steht, waere der Schritt danach ein Schritt ohne Ziel.
    Er behaelt die Referenz und wird beim Laden als verwaist gemeldet - das ist ein
    Problem, das man sieht und beheben kann.
    """
    for s in _iter_import_steps(seq_data):
        for key in _REF_KEYS:
            alt = s.get(key)
            if alt is None:
                continue
            neu = id_map.get(alt)
            if neu is not None and neu != alt:
                s[key] = neu
