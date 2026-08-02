"""
Import/Export-Modul für den Autoclicker.
Exportiert komplette Setups als ZIP-Archiv und importiert sie
mit optionalem Koordinaten-Remapping für andere Bildschirme.
"""

import json
import logging
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

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
    confirm_points) bleiben außen vor — es geht um die eigentlichen Klick-Ziele.
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
    """Liefert die Klick-Positionen, die außerhalb des Fenster-Rects (l, t, r, b) liegen."""
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
    zur (ggf. anderen) Spielfenster-Größe/Position auf dem Zielsystem.
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
            s.x, s.y = remap_point(s.x, s.y, transform)
            if s.wait_condition is not None:
                px = s.wait_condition.pixel
                s.wait_condition.pixel = remap_point(px[0], px[1], transform)
            if s.else_config is not None:
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
    mit; `mit_sequenzen` die Koordinaten in den Sequenz-DATEIEN (nicht nur den
    geladenen) — Trigger-Pixel, else-Klicks, Screenshot-Regionen.

    `mit_slots` steht bewusst getrennt, obwohl Slots zu den Scans gehören: eine
    aus einer Maus-Position abgeleitete Verschiebung ist für ein Klick-Ziel gut
    genug, für eine Scan-Region aber nur eine Näherung — ein paar Pixel daneben
    schneiden das Item-Icon an. Dafür gibt es `slot_repair()`, das die Slots misst
    statt sie zu verschieben. Deshalb muss sich beides einzeln schalten lassen:
    nach einer Reparatur dürfen die Slots kein zweites Mal wandern.

    Schritte mit `point_id` werden mit umgerechnet, obwohl `resolve_point_references()`
    sie beim nächsten Lauf ohnehin aus dem Punkt nachzieht: sonst stünde in der Datei
    bis dahin eine Koordinate, die zu keinem Bildschirm mehr passt, und ein Schritt,
    dessen Punkt fehlt, bliebe endgültig auf dem alten Wert stehen.

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
    Fenstergröße ableiten kann (Fallback bleibt das 2-Punkt-Verfahren).

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


def import_bundle(state: 'AutoClickerState', filepath: str,
                  transform: dict = None,
                  import_points: bool = True, import_sequences: bool = True,
                  import_slots: bool = True, import_items: bool = True,
                  import_item_scans: bool = True, import_boss_scans: bool = True,
                  import_icon_scans: bool = True,
                  import_config: bool = True, merge: bool = True) -> tuple[bool, str]:
    """Importiert ein Setup aus einer ZIP-Datei.

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

            stats = {"points": 0, "sequences": 0, "slots": 0, "items": 0,
                     "item_scans": 0, "boss_scans": 0, "icon_scans": 0, "templates": 0}

            # Templates zuerst extrahieren
            templates_dir = Path(TEMPLATES_DIR)
            templates_dir.mkdir(parents=True, exist_ok=True)
            resolved_tpl_dir = templates_dir.resolve()
            for name in names:
                if name.startswith("templates/") and name.endswith(".png"):
                    tpl_name = name[len("templates/"):]
                    tpl_path = templates_dir / tpl_name
                    if not tpl_path.resolve().is_relative_to(resolved_tpl_dir):
                        logger.warning(f"Template-Pfad außerhalb des Zielordners übersprungen: {name}")
                        continue
                    # Template kann in einem Unterordner liegen (templates/sub/x.png)
                    # — Zielverzeichnis anlegen, sonst FileNotFoundError beim Schreiben.
                    tpl_path.parent.mkdir(parents=True, exist_ok=True)
                    tpl_path.write_bytes(zf.read(name))
                    stats["templates"] += 1

            # Punkte. Kollidiert eine importierte ID mit einer lokalen, bekommt der Punkt
            # eine neue - und id_map merkt sich das, damit die Sequenz-Schritte ihren
            # point_id nachziehen koennen.
            id_map: dict[int, int] = {}
            if import_points and "points.json" in names:
                points_data = json.loads(zf.read("points.json").decode("utf-8"))
                points_data, _m = migrate(points_data, KIND_POINTS)
                with state.lock:
                    if not merge:
                        state.points.clear()
                    existing_ids = {p.id for p in state.points}
                    next_id = max(existing_ids) + 1 if existing_ids else 1
                    for p in points_data:
                        x, y = remap_point(p["x"], p["y"], transform)
                        alt_id = p.get("id")
                        pid = alt_id if alt_id is not None else next_id
                        while pid in existing_ids:
                            pid = next_id
                            next_id += 1
                        color_raw = p.get("color")
                        color = tuple(int(v) for v in color_raw) if color_raw else None
                        state.points.append(ClickPoint(x, y, p.get("name", ""), pid,
                                                       color=color, source=p.get("source", "")))
                        existing_ids.add(pid)
                        next_id = max(next_id, pid + 1)
                        if alt_id is not None:
                            id_map[alt_id] = pid
                        stats["points"] += 1

            # Sequenzen
            if import_sequences:
                for name in names:
                    if name.startswith("sequences/") and name.endswith(".json"):
                        seq_data = json.loads(zf.read(name).decode("utf-8"))
                        _remap_sequence_data(seq_data, transform)
                        _remap_point_ids(seq_data, id_map, bool(import_points))
                        seq_name = seq_data.get("name", Path(name).stem)
                        safe = sanitize_filename(seq_name)
                        seq_path = Path("sequences") / f"{safe}.json"
                        seq_path.parent.mkdir(parents=True, exist_ok=True)
                        atomic_write(seq_path, compact_json(seq_data))
                        seq = load_sequence_file(seq_path)
                        if seq:
                            with state.lock:
                                state.sequences[seq.name] = seq
                            stats["sequences"] += 1

            # Slots
            if import_slots and "slots.json" in names:
                slots_data = json.loads(zf.read("slots.json").decode("utf-8"))
                slots_data, _m = migrate(slots_data, KIND_SLOTS)
                with state.lock:
                    if not merge:
                        state.global_slots.clear()
                    for sname, s in slots_data.items():
                        slot = _slot_from_dict(sname, s)
                        slot.scan_region = remap_region(slot.scan_region, transform)
                        slot.click_pos = remap_point(slot.click_pos[0], slot.click_pos[1],
                                                     transform)
                        state.global_slots[sname] = slot
                        stats["slots"] += 1
                save_global_slots(state)

            # Items
            if import_items and "items.json" in names:
                items_data = json.loads(zf.read("items.json").decode("utf-8"))
                items_data, _m = migrate(items_data, KIND_ITEMS)
                with state.lock:
                    if not merge:
                        state.global_items.clear()
                    for iname, i in items_data.items():
                        item = _item_from_dict(i, iname)
                        if item.confirm_point:
                            nx, ny = remap_point(item.confirm_point.x, item.confirm_point.y, transform)
                            item.confirm_point = ClickPoint(nx, ny)
                        state.global_items[iname] = item
                        stats["items"] += 1
                save_global_items(state)

            # Item-Scans
            if import_item_scans:
                for name in names:
                    if name.startswith("item_scans/") and name.endswith(".json"):
                        scan_data = json.loads(zf.read(name).decode("utf-8"))
                        scan_data, _m = migrate(scan_data, KIND_ITEM_SCAN)
                        # Nur Namen - die Koordinaten der Slots werden beim Import von
                        # slots.json umgerechnet, nicht ein zweites Mal pro Scan. Genau
                        # diese Doppelpflege fiel mit der Referenz weg.
                        config = ItemScanConfig(
                            name=scan_data["name"],
                            slot_names=[str(n) for n in scan_data.get("slot_names", [])],
                            item_names=[str(n) for n in scan_data.get("item_names", [])],
                            color_tolerance=scan_data.get("color_tolerance", 40),
                            learn_unknown=scan_data.get("learn_unknown", False),
                        )
                        with state.lock:
                            state.item_scans[config.name] = config
                        save_item_scan(config)
                        stats["item_scans"] += 1
                # Referenzen gegen die (gerade importierten) globalen Slots/Items
                # auflösen - sonst laufen die Scans bis zum nächsten Start leer.
                for _meldung in resolve_scan_references(state):
                    print(warn(_meldung))

            # Boss-Scans
            if import_boss_scans:
                for name in names:
                    if name.startswith("boss_scans/") and name.endswith(".json"):
                        bscan_data = json.loads(zf.read(name).decode("utf-8"))
                        bosses = []
                        for b in bscan_data.get("bosses", []):
                            boss = _boss_profile_from_dict(b)
                            # Nur Klick-Bosse haben sinnvolle Koordinaten — für
                            # skip/key-Bosse sind action_x/y bedeutungslos (Default 0)
                            # und dürfen nicht durch den Affine-Transform verschoben werden.
                            if boss.action == BOSS_ACTION_CLICK:
                                boss.action_x, boss.action_y = remap_point(
                                    boss.action_x, boss.action_y, transform)
                            bosses.append(boss)
                        region = remap_region(tuple(bscan_data["scan_region"]), transform)
                        config = BossScanConfig(
                            name=bscan_data["name"],
                            scan_region=region,
                            color_tolerance=bscan_data.get("color_tolerance", 30),
                            default_action=bscan_data.get("default_action", BOSS_ACTION_SKIP),
                            default_scan=bscan_data.get("default_scan"),
                            bosses=bosses,
                            use_llm=bscan_data.get("use_llm", False),
                            llm_fallback=bscan_data.get("llm_fallback", True),
                            use_ocr=bscan_data.get("use_ocr", False),
                            ocr_fallback=bscan_data.get("ocr_fallback", True),
                        )
                        with state.lock:
                            state.boss_scans[config.name] = config
                        save_boss_scan(config)
                        stats["boss_scans"] += 1

                # Globale Boss-Bibliothek (Merge nach Name, Import gewinnt)
                if "global_bosses.json" in names:
                    gboss_data = json.loads(zf.read("global_bosses.json").decode("utf-8"))
                    imported = []
                    for b in gboss_data:
                        boss = _boss_profile_from_dict(b)
                        if boss.action == BOSS_ACTION_CLICK:
                            boss.action_x, boss.action_y = remap_point(
                                boss.action_x, boss.action_y, transform)
                        imported.append(boss)
                    if imported:
                        with state.lock:
                            imported_names = {b.name for b in imported}
                            state.global_bosses = [
                                b for b in state.global_bosses if b.name not in imported_names
                            ] + imported
                        save_global_bosses(state)
                        stats["global_bosses"] = len(imported)

            # Icon-Scans
            if import_icon_scans:
                for name in names:
                    if name.startswith("icon_scans/") and name.endswith(".json"):
                        iscan_data = json.loads(zf.read(name).decode("utf-8"))
                        action = iscan_data.get("action", ICON_ACTION_CLICK)
                        ax, ay = iscan_data.get("action_x", 0), iscan_data.get("action_y", 0)
                        # Nur Klick-Aktionen haben sinnvolle Koordinaten zum Remappen.
                        if action == ICON_ACTION_CLICK:
                            ax, ay = remap_point(ax, ay, transform)
                        region = remap_region(tuple(iscan_data["scan_region"]), transform)
                        config = IconScanConfig(
                            name=iscan_data["name"],
                            scan_region=region,
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
                        with state.lock:
                            state.icon_scans[config.name] = config
                        save_icon_scan(config)
                        stats["icon_scans"] += 1

            # Config
            if import_config and "config.json" in names:
                cfg_data = json.loads(zf.read("config.json").decode("utf-8"))
                # Sicherheits-/maschinenspezifische Felder nie übernehmen
                for k in _SENSITIVE_CONFIG_KEYS:
                    cfg_data.pop(k, None)
                current = state.config.to_dict()
                current.update(cfg_data)
                from .config import AppConfig
                with state.lock:
                    state.config = AppConfig.from_dict(current)
                from .config import save_config
                save_config(state.config)

            # Punkte + Sequenzen speichern
            if stats["points"] > 0 or stats["sequences"] > 0:
                save_data(state)

            parts = []
            if stats["points"]:
                parts.append(f"{stats['points']} Punkt(e)")
            if stats["sequences"]:
                parts.append(f"{stats['sequences']} Sequenz(en)")
            if stats["slots"]:
                parts.append(f"{stats['slots']} Slot(s)")
            if stats["items"]:
                parts.append(f"{stats['items']} Item(s)")
            if stats["item_scans"]:
                parts.append(f"{stats['item_scans']} Item-Scan(s)")
            if stats["boss_scans"]:
                parts.append(f"{stats['boss_scans']} Boss-Scan(s)")
            if stats.get("global_bosses"):
                parts.append(f"{stats['global_bosses']} globale(r) Boss(e)")
            if stats["icon_scans"]:
                parts.append(f"{stats['icon_scans']} Icon-Scan(s)")
            if stats["templates"]:
                parts.append(f"{stats['templates']} Template(s)")

            return True, ", ".join(parts) if parts else "Nichts importiert"

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
    """Transformiert alle Koordinaten in einer Sequenz-JSON-Struktur (in-place)."""
    for s in _iter_import_steps(seq_data):
        if s.get("x") is not None or s.get("y") is not None:
            s["x"], s["y"] = remap_point(s.get("x", 0), s.get("y", 0), transform)
        if s.get("wait_pixel"):
            wp = s["wait_pixel"]
            s["wait_pixel"] = list(remap_point(wp[0], wp[1], transform))
        if s.get("else_x") is not None or s.get("else_y") is not None:
            s["else_x"], s["else_y"] = remap_point(
                s.get("else_x", 0), s.get("else_y", 0), transform)
        if s.get("screenshot_region"):
            sr = s["screenshot_region"]
            s["screenshot_region"] = list(remap_region(tuple(sr), transform))


def _remap_point_ids(seq_data: dict, id_map: dict[int, int],
                     punkte_importiert: bool) -> None:
    """Zieht `point_id` der Schritte auf die IDs nach, die die Punkte hier bekommen haben.

    Der Import vergibt einem Punkt eine neue ID, wenn seine alte lokal schon belegt ist.
    Bleibt der Schritt dann auf der alten ID stehen, zeigt er auf einen FREMDEN lokalen
    Punkt - und `resolve_point_references()` zieht den Schritt beim naechsten Lauf brav
    dorthin und meldet das auch noch als Erfolg. Genau deshalb wird hier nachgezogen.

    Ohne Punkt-Import gibt es hier ueberhaupt keine passenden Punkte: dann faellt die
    Referenz weg und der Schritt bleibt bei seinen (umgerechneten) Koordinaten. Lieber
    keine Referenz als die falsche - dieselbe Regel wie in der Migration.
    """
    for s in _iter_import_steps(seq_data):
        alt = s.get("point_id")
        if alt is None:
            continue
        neu = id_map.get(alt) if punkte_importiert else None
        if neu is None:
            s.pop("point_id", None)
        elif neu != alt:
            s["point_id"] = neu
