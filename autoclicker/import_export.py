"""
Import/Export-Modul für den Autoclicker.
Exportiert komplette Setups als ZIP-Archiv und importiert sie
mit optionalem Koordinaten-Remapping für andere Bildschirme.
"""

import json
import logging
import os
import zipfile
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .models import AutoClickerState

from .persistence import (
    TEMPLATES_DIR, _sequence_to_dict, _step_to_dict, _item_to_dict, _slot_to_dict,
    _boss_profile_to_dict,
    load_sequence_file, _item_from_dict, _boss_profile_from_dict,
    save_data, save_global_slots, save_global_items,
    save_item_scan, save_boss_scan,
)
from .models import (
    ClickPoint, ItemSlot, ItemScanConfig, BossScanConfig,
    BOSS_ACTION_SKIP, SCAN_MODE_ALL,
)
from .utils import compact_json, sanitize_filename

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


IDENTITY_TRANSFORM = {"scale_x": 1.0, "scale_y": 1.0, "offset_x": 0, "offset_y": 0}


# =============================================================================
# EXPORT
# =============================================================================

def export_bundle(state: 'AutoClickerState', filepath: str,
                  ref_point1: tuple[int, int], ref_point2: tuple[int, int],
                  include_points: bool = True, include_sequences: bool = True,
                  include_slots: bool = True, include_items: bool = True,
                  include_item_scans: bool = True, include_boss_scans: bool = True,
                  include_config: bool = True) -> tuple[bool, str]:
    """Exportiert Setup als ZIP-Archiv.

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

        with zipfile.ZipFile(filepath, "w", zipfile.ZIP_DEFLATED) as zf:
            # Punkte
            if include_points:
                with state.lock:
                    points_data = [{"id": p.id, "x": p.x, "y": p.y, "name": p.name}
                                   for p in state.points]
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
                    scan_data = {
                        "name": config.name,
                        "color_tolerance": config.color_tolerance,
                        "slots": [_slot_to_dict(s) for s in config.slots],
                        "items": [_item_to_dict(i) for i in config.items],
                    }
                    safe = sanitize_filename(name)
                    zf.writestr(f"item_scans/{safe}.json", compact_json(scan_data))
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
                    bscan_data = {
                        "name": config.name,
                        "scan_region": list(config.scan_region),
                        "color_tolerance": config.color_tolerance,
                        "default_action": config.default_action,
                        "default_scan": config.default_scan,
                        "bosses": [_boss_profile_to_dict(b) for b in config.bosses],
                        "use_llm": config.use_llm,
                        "llm_fallback": config.llm_fallback,
                        "use_ocr": config.use_ocr,
                        "ocr_fallback": config.ocr_fallback,
                    }
                    safe = sanitize_filename(name)
                    zf.writestr(f"boss_scans/{safe}.json", compact_json(bscan_data))
                    bscan_names.append(name)
                    for b in config.bosses:
                        if b.template:
                            template_files.add(b.template)
                if bscan_names:
                    manifest["contents"]["boss_scans"] = bscan_names

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


def _export_config(config) -> dict:
    """Exportiert relevante Config-Werte (ohne interne/Debug-Felder)."""
    d = config.to_dict()
    skip = {"debug_mode", "debug_detection", "debug_save_templates",
            "debug_show_pixel_position", "pixel_show_delay",
            "failsafe_enabled", "failsafe_x", "failsafe_y",
            "session_log_enabled", "session_log_dir"}
    return {k: v for k, v in d.items() if k not in skip and not k.startswith("_")}


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
                     "item_scans": 0, "boss_scans": 0, "templates": 0}

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
                    tpl_path.write_bytes(zf.read(name))
                    stats["templates"] += 1

            # Punkte
            if import_points and "points.json" in names:
                points_data = json.loads(zf.read("points.json").decode("utf-8"))
                with state.lock:
                    if not merge:
                        state.points.clear()
                    existing_ids = {p.id for p in state.points}
                    next_id = max(existing_ids) + 1 if existing_ids else 1
                    for p in points_data:
                        x, y = remap_point(p["x"], p["y"], transform)
                        pid = p.get("id", next_id)
                        while pid in existing_ids:
                            pid = next_id
                            next_id += 1
                        state.points.append(ClickPoint(x, y, p.get("name", ""), pid))
                        existing_ids.add(pid)
                        next_id = max(next_id, pid + 1)
                        stats["points"] += 1

            # Sequenzen
            if import_sequences:
                for name in names:
                    if name.startswith("sequences/") and name.endswith(".json"):
                        seq_data = json.loads(zf.read(name).decode("utf-8"))
                        _remap_sequence_data(seq_data, transform)
                        seq_name = seq_data.get("name", Path(name).stem)
                        safe = sanitize_filename(seq_name)
                        seq_path = Path("sequences") / f"{safe}.json"
                        seq_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(seq_path, "w", encoding="utf-8") as f:
                            f.write(compact_json(seq_data))
                        seq = load_sequence_file(seq_path)
                        if seq:
                            with state.lock:
                                state.sequences[seq.name] = seq
                            stats["sequences"] += 1

            # Slots
            if import_slots and "slots.json" in names:
                slots_data = json.loads(zf.read("slots.json").decode("utf-8"))
                with state.lock:
                    if not merge:
                        state.global_slots.clear()
                    for sname, s in slots_data.items():
                        region = remap_region(tuple(s["scan_region"]), transform)
                        click = remap_point(s["click_pos"][0], s["click_pos"][1], transform)
                        slot_color = tuple(s["slot_color"]) if s.get("slot_color") else None
                        state.global_slots[sname] = ItemSlot(
                            name=s["name"], scan_region=region,
                            click_pos=click, slot_color=slot_color
                        )
                        stats["slots"] += 1
                save_global_slots(state)

            # Items
            if import_items and "items.json" in names:
                items_data = json.loads(zf.read("items.json").decode("utf-8"))
                with state.lock:
                    if not merge:
                        state.global_items.clear()
                    for iname, i in items_data.items():
                        item = _item_from_dict(i)
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
                        slots = []
                        for s in scan_data.get("slots", []):
                            region = remap_region(tuple(s["scan_region"]), transform)
                            click = remap_point(s["click_pos"][0], s["click_pos"][1], transform)
                            slot_color = tuple(s["slot_color"]) if s.get("slot_color") else None
                            slots.append(ItemSlot(
                                name=s["name"], scan_region=region,
                                click_pos=click, slot_color=slot_color
                            ))
                        items = []
                        for i in scan_data.get("items", []):
                            item = _item_from_dict(i)
                            if item.confirm_point:
                                nx, ny = remap_point(item.confirm_point.x, item.confirm_point.y, transform)
                                item.confirm_point = ClickPoint(nx, ny)
                            items.append(item)
                        config = ItemScanConfig(
                            name=scan_data["name"],
                            slots=slots, items=items,
                            color_tolerance=scan_data.get("color_tolerance", 30),
                        )
                        with state.lock:
                            state.item_scans[config.name] = config
                        save_item_scan(config)
                        stats["item_scans"] += 1

            # Boss-Scans
            if import_boss_scans:
                for name in names:
                    if name.startswith("boss_scans/") and name.endswith(".json"):
                        bscan_data = json.loads(zf.read(name).decode("utf-8"))
                        bosses = []
                        for b in bscan_data.get("bosses", []):
                            boss = _boss_profile_from_dict(b)
                            if boss.action_x is not None or boss.action_y is not None:
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

            # Config
            if import_config and "config.json" in names:
                cfg_data = json.loads(zf.read("config.json").decode("utf-8"))
                _IMPORT_SKIP_KEYS = {"failsafe_enabled", "failsafe_x", "failsafe_y",
                                     "session_log_enabled", "session_log_dir"}
                for k in _IMPORT_SKIP_KEYS:
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
            if stats["templates"]:
                parts.append(f"{stats['templates']} Template(s)")

            return True, ", ".join(parts) if parts else "Nichts importiert"

    except (IOError, OSError, zipfile.BadZipFile, json.JSONDecodeError, KeyError) as e:
        logger.error(f"Import fehlgeschlagen: {e}")
        return False, str(e)


def _remap_sequence_data(seq_data: dict, transform: dict) -> None:
    """Transformiert alle Koordinaten in einer Sequenz-JSON-Struktur (in-place)."""
    def remap_steps(steps: list) -> None:
        for s in steps:
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

    for key in ("init_steps", "end_steps"):
        if key in seq_data:
            remap_steps(seq_data[key])
    for lp in seq_data.get("loop_phases", []):
        if "steps" in lp:
            remap_steps(lp["steps"])
