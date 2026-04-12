"""
Persistenz-Funktionen für den Autoclicker.
Speichern/Laden von Sequenzen, Punkten, Slots, Items, Scans.
"""

import json
import logging
import os
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from .config import SEQUENCES_DIR, DEFAULT_MIN_CONFIDENCE
from .models import (
    ClickPoint, ElseConfig, WaitCondition, SequenceStep, LoopPhase, Sequence,
    ItemProfile, ItemSlot, ItemScanConfig, BossProfile, BossScanConfig, AutoClickerState,
    BOSS_ACTION_SCAN, SCAN_MODE_ALL
)
from .utils import compact_json, sanitize_filename, save_tag, load_tag, delete_tag, err, info, warn

# Logger
logger = logging.getLogger("autoclicker")

# Verzeichnisse
BOSS_SCANS_DIR: str = "boss_scans"
ITEM_SCANS_DIR: str = "item_scans"
SLOTS_DIR: str = "slots"
ITEMS_DIR: str = "items"
SCREENSHOTS_DIR: str = os.path.join(SLOTS_DIR, "Screenshots")
SEQUENCE_SCREENSHOTS_DIR: str = "screenshots"
TEMPLATES_DIR: str = os.path.join(ITEMS_DIR, "templates")
SLOTS_FILE: str = os.path.join(SLOTS_DIR, "slots.json")
ITEMS_FILE: str = os.path.join(ITEMS_DIR, "items.json")
SLOT_PRESETS_DIR: str = os.path.join(SLOTS_DIR, "presets")
ITEM_PRESETS_DIR: str = os.path.join(ITEMS_DIR, "presets")


def init_directories() -> None:
    """Erstellt alle benötigten Verzeichnisse."""
    for folder in [ITEM_SCANS_DIR, BOSS_SCANS_DIR, SLOTS_DIR, ITEMS_DIR, SCREENSHOTS_DIR,
                   SEQUENCE_SCREENSHOTS_DIR, TEMPLATES_DIR, SLOT_PRESETS_DIR, ITEM_PRESETS_DIR]:
        os.makedirs(folder, exist_ok=True)


# =============================================================================
# ITEM SERIALISIERUNG (gemeinsame Helfer)
# =============================================================================

def _item_to_dict(item: ItemProfile) -> dict:
    """Serialisiert ein ItemProfile zu einem Dict (via dataclasses.asdict)."""
    d = asdict(item)
    # confirm_point: ClickPoint → nur {x, y} behalten (id/name nicht relevant)
    if d["confirm_point"]:
        d["confirm_point"] = {"x": d["confirm_point"]["x"], "y": d["confirm_point"]["y"]}
    return d


def _item_from_dict(data: dict) -> ItemProfile:
    """Deserialisiert ein ItemProfile aus einem Dict."""
    # confirm_point: kann {x, y} Dict, [x,y] Liste (alt) oder None sein
    cp_data = data.get("confirm_point")
    cp = None
    if cp_data:
        if isinstance(cp_data, dict) and "x" in cp_data and "y" in cp_data:
            cp = ClickPoint(cp_data["x"], cp_data["y"])
        elif isinstance(cp_data, list) and len(cp_data) == 2:
            cp = ClickPoint(cp_data[0], cp_data[1])  # Alte Format-Unterstützung
    return ItemProfile(
        name=data["name"],
        marker_colors=[tuple(c) for c in data.get("marker_colors", [])],
        category=data.get("category"),
        priority=data.get("priority", 1),
        confirm_point=cp,
        confirm_delay=data.get("confirm_delay", 0.5),
        template=data.get("template"),
        min_confidence=data.get("min_confidence", DEFAULT_MIN_CONFIDENCE)
    )


# =============================================================================
# SEQUENZ-PERSISTENZ
# =============================================================================
def ensure_sequences_dir() -> Path:
    """Stellt sicher, dass der Sequenzen-Ordner existiert."""
    path = Path(SEQUENCES_DIR)
    path.mkdir(exist_ok=True)
    return path


def _step_to_dict(s: SequenceStep) -> dict:
    """Konvertiert einen SequenceStep in ein JSON-serialisierbares dict."""
    wc = s.wait_condition
    ec = s.else_config
    return {"x": s.x, "y": s.y, "name": s.name, "delay_before": s.delay_before,
            "wait_pixel": wc.pixel if wc else None,
            "wait_color": wc.color if wc else None,
            "wait_until_gone": wc.until_gone if wc else False,
            "item_scan": s.item_scan, "item_scan_mode": s.item_scan_mode,
            "boss_scan": s.boss_scan,
            "wait_only": s.wait_only, "delay_max": s.delay_max,
            "key_press": s.key_press,
            "else_action": ec.action if ec else None,
            "else_x": ec.x if ec else 0, "else_y": ec.y if ec else 0,
            "else_delay": ec.delay if ec else 0,
            "else_key": ec.key if ec else None, "else_name": ec.name if ec else "",
            "screenshot_only": s.screenshot_only,
            "screenshot_region": list(s.screenshot_region) if s.screenshot_region else None}


def _sequence_to_dict(seq: Sequence) -> dict:
    """Konvertiert eine Sequence in ein JSON-serialisierbares dict."""
    return {
        "name": seq.name,
        "total_cycles": seq.total_cycles,
        "init_steps": [_step_to_dict(s) for s in seq.init_steps],
        "loop_phases": [
            {
                "name": lp.name,
                "repeat": lp.repeat,
                "steps": [_step_to_dict(s) for s in lp.steps],
                **({"scheduled_start": lp.scheduled_start} if lp.scheduled_start else {})
            }
            for lp in seq.loop_phases
        ],
        "end_steps": [_step_to_dict(s) for s in seq.end_steps]
    }


def save_sequence_file(seq: Sequence, filepath: Path) -> bool:
    """Speichert eine einzelne Sequenz direkt in die angegebene Datei."""
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(compact_json(_sequence_to_dict(seq)))
        return True
    except (IOError, OSError) as e:
        print(err(f"Sequenz konnte nicht gespeichert werden: {e}"))
        return False


def save_data(state: AutoClickerState) -> None:
    """Speichert Punkte und Sequenzen in JSON-Dateien."""
    ensure_sequences_dir()

    # Punkte speichern (mit stabiler ID)
    try:
        points_data = [{"id": p.id, "x": p.x, "y": p.y, "name": p.name} for p in state.points]
        with open(Path(SEQUENCES_DIR) / "points.json", "w", encoding="utf-8") as f:
            f.write(compact_json(points_data))
    except (IOError, OSError) as e:
        print(err(f"Punkte konnten nicht gespeichert werden: {e}"))

    # Sequenzen speichern
    for name, seq in state.sequences.items():
        filename = f"{sanitize_filename(name)}.json"
        save_sequence_file(seq, Path(SEQUENCES_DIR) / filename)

    print(save_tag(f"Daten gespeichert in '{SEQUENCES_DIR}/'"))


def load_points(state: AutoClickerState) -> None:
    """Lädt gespeicherte Punkte."""
    points_file = Path(SEQUENCES_DIR) / "points.json"
    if points_file.exists():
        try:
            with open(points_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Lade Punkte mit ID (Fallback für alte Dateien ohne ID)
                state.points = []
                for i, p in enumerate(data):
                    point_id = p.get("id", i + 1)  # Fallback: Index + 1 für alte Dateien
                    state.points.append(ClickPoint(p["x"], p["y"], p.get("name", ""), point_id))
            print(load_tag(f"{len(state.points)} Punkt(e) geladen"))
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            print(warn(f"points.json konnte nicht geladen werden: {e}"))
            print(info("Starte mit leerer Punktliste."))
            state.points = []
    else:
        print(info("Keine gespeicherten Punkte gefunden."))


def get_next_point_id(state: AutoClickerState) -> int:
    """Gibt die nächste freie Punkt-ID zurück."""
    if not state.points:
        return 1
    return max(p.id for p in state.points) + 1


def get_point_by_id(state: AutoClickerState, point_id: int) -> Optional[ClickPoint]:
    """Findet einen Punkt anhand seiner ID (O(1) Dict-Lookup mit Fallback)."""
    # Schneller Dict-Lookup
    points_by_id = {p.id: p for p in state.points}
    return points_by_id.get(point_id)


def load_sequence_file(filepath: Path) -> Optional[Sequence]:
    """Lädt eine einzelne Sequenz-Datei (mit Start + mehreren Loop-Phasen)."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

            def parse_steps(steps_data: list) -> list[SequenceStep]:
                steps = []
                for s in steps_data:
                    wait_pixel = s.get("wait_pixel")
                    if wait_pixel:
                        wait_pixel = tuple(int(v) for v in wait_pixel)
                    wait_color = s.get("wait_color")
                    if wait_color:
                        wait_color = tuple(int(v) for v in wait_color)
                    # Unterstütze beide Formate: delay_before (neu) und delay_after (alt)
                    delay_raw = s.get("delay_before")
                    if delay_raw is None:
                        delay_raw = s.get("delay_after")
                    if delay_raw is None:
                        delay_raw = 0
                    delay_max_raw = s.get("delay_max")
                    # WaitCondition zusammenbauen
                    wait_cond = None
                    if wait_pixel and wait_color:
                        wait_cond = WaitCondition(
                            pixel=wait_pixel, color=wait_color,
                            until_gone=s.get("wait_until_gone", False)
                        )
                    # ElseConfig zusammenbauen
                    else_cfg = None
                    else_action = s.get("else_action")
                    if else_action:
                        else_cfg = ElseConfig(
                            action=else_action,
                            x=s.get("else_x", 0), y=s.get("else_y", 0),
                            delay=s.get("else_delay", 0),
                            key=s.get("else_key"), name=s.get("else_name", "")
                        )
                    step = SequenceStep(
                        x=s.get("x", 0),
                        y=s.get("y", 0),
                        delay_before=float(delay_raw),
                        name=s.get("name", ""),
                        wait_condition=wait_cond,
                        item_scan=s.get("item_scan"),
                        item_scan_mode=s.get("item_scan_mode", "all"),
                        boss_scan=s.get("boss_scan"),
                        wait_only=s.get("wait_only", False),
                        delay_max=float(delay_max_raw) if delay_max_raw is not None else None,
                        key_press=s.get("key_press"),
                        else_config=else_cfg,
                        screenshot_only=s.get("screenshot_only", False),
                        screenshot_region=tuple(int(v) for v in s["screenshot_region"]) if s.get("screenshot_region") else None,
                    )
                    steps.append(step)
                return steps

            init_steps = parse_steps(data.get("init_steps", []))
            end_steps = parse_steps(data.get("end_steps", []))

            # Rückwärtskompatibilität: alte start_steps → erste LoopPhase mit repeat=1
            old_start_steps = parse_steps(data.get("start_steps", []))

            # Neues Format mit loop_phases (mehrere Loop-Phasen)
            if "loop_phases" in data:
                loop_phases = []
                if old_start_steps:
                    loop_phases.append(LoopPhase("Start", old_start_steps, 1))
                for lp_data in data["loop_phases"]:
                    lp = LoopPhase(
                        name=lp_data.get("name", "Loop"),
                        steps=parse_steps(lp_data.get("steps", [])),
                        repeat=lp_data.get("repeat", 1),
                        scheduled_start=lp_data.get("scheduled_start")
                    )
                    loop_phases.append(lp)
                total_cycles = data.get("total_cycles", 1)
                return Sequence(data["name"], init_steps, loop_phases, end_steps, total_cycles)

            # Altes Format mit loop_steps (eine Loop-Phase) - konvertieren
            elif "loop_steps" in data:
                loop_steps = parse_steps(data.get("loop_steps", []))
                max_loops = data.get("max_loops", 0)
                loop_phases = []
                if old_start_steps:
                    loop_phases.append(LoopPhase("Start", old_start_steps, 1))
                if loop_steps:
                    loop_phases.append(LoopPhase("Loop 1", loop_steps, max_loops if max_loops > 0 else 1))
                total_cycles = 0 if max_loops == 0 else 1
                return Sequence(data["name"], init_steps, loop_phases, end_steps, total_cycles)

            # Uraltes Format (nur steps) - konvertieren
            elif "steps" in data:
                loop_steps = parse_steps(data["steps"])
                loop_phases = [LoopPhase("Loop 1", loop_steps, 1)] if loop_steps else []
                return Sequence(data["name"], [], loop_phases, [], 0)

            else:
                return Sequence(data["name"], [], [], [], 1)

    except (json.JSONDecodeError, IOError, KeyError, TypeError) as e:
        logger.error(f"Konnte {filepath} nicht laden: {e}")
        return None


_seq_cache: list[tuple[str, Path]] = []
_seq_cache_mtime: float = 0


def list_available_sequences() -> list[tuple[str, Path]]:
    """Listet alle verfügbaren Sequenz-Dateien auf (mit mtime-Cache)."""
    global _seq_cache, _seq_cache_mtime
    seq_dir = Path(SEQUENCES_DIR)
    if not seq_dir.exists():
        return []

    try:
        current_mtime = seq_dir.stat().st_mtime
    except OSError:
        return []

    if _seq_cache and _seq_cache_mtime == current_mtime:
        return _seq_cache

    sequences = []
    for f in seq_dir.glob("*.json"):
        if f.name != "points.json":
            try:
                with open(f, "r", encoding="utf-8") as file:
                    data = json.load(file)
                    name = data.get("name", f.stem)
                    sequences.append((name, f))
            except (json.JSONDecodeError, IOError, KeyError, TypeError):
                pass  # Ungültige/korrupte Datei überspringen
    _seq_cache = sequences
    _seq_cache_mtime = current_mtime
    return sequences


# =============================================================================
# ITEM-SCAN PERSISTENZ
# =============================================================================
def ensure_item_scans_dir() -> Path:
    """Stellt sicher, dass der Item-Scans-Ordner existiert."""
    path = Path(ITEM_SCANS_DIR)
    path.mkdir(exist_ok=True)
    return path


def save_item_scan(config: ItemScanConfig) -> None:
    """Speichert eine Item-Scan Konfiguration."""
    ensure_item_scans_dir()

    data = {
        "name": config.name,
        "color_tolerance": config.color_tolerance,
        "slots": [
            {
                "name": slot.name,
                "scan_region": list(slot.scan_region),
                "click_pos": list(slot.click_pos),
                "slot_color": list(slot.slot_color) if slot.slot_color else None
            }
            for slot in config.slots
        ],
        "items": [_item_to_dict(item) for item in config.items]
    }

    filename = f"{sanitize_filename(config.name)}.json"
    try:
        with open(Path(ITEM_SCANS_DIR) / filename, "w", encoding="utf-8") as f:
            f.write(compact_json(data))
        print(save_tag(f"Item-Scan '{config.name}' gespeichert in '{ITEM_SCANS_DIR}/'"))
    except (IOError, OSError) as e:
        print(err(f"Item-Scan konnte nicht gespeichert werden: {e}"))


def load_item_scan_file(filepath: Path) -> Optional[ItemScanConfig]:
    """Lädt eine Item-Scan Konfiguration."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

            slots = []
            for s in data.get("slots", []):
                slot_color = s.get("slot_color")
                if slot_color:
                    slot_color = tuple(slot_color)
                slot = ItemSlot(
                    name=s["name"],
                    scan_region=tuple(s["scan_region"]),
                    click_pos=tuple(s["click_pos"]),
                    slot_color=slot_color
                )
                slots.append(slot)

            items = []
            for i in data.get("items", []):
                item = _item_from_dict(i)
                items.append(item)

            return ItemScanConfig(
                name=data["name"],
                slots=slots,
                items=items,
                color_tolerance=data.get("color_tolerance", 40)
            )

    except (json.JSONDecodeError, IOError, KeyError, TypeError) as e:
        logger.error(f"Konnte {filepath} nicht laden: {e}")
        return None


def list_available_item_scans() -> list[tuple[str, Path]]:
    """Listet alle verfügbaren Item-Scan Konfigurationen auf."""
    scan_dir = Path(ITEM_SCANS_DIR)
    if not scan_dir.exists():
        return []

    scans = []
    for f in scan_dir.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as file:
                data = json.load(file)
                name = data.get("name", f.stem)
                scans.append((name, f))
        except (json.JSONDecodeError, IOError, KeyError, TypeError):
            pass  # Ungültige/korrupte Datei überspringen
    return scans


def load_all_item_scans(state: AutoClickerState) -> None:
    """Lädt alle Item-Scan Konfigurationen."""
    for name, path in list_available_item_scans():
        config = load_item_scan_file(path)
        if config:
            state.item_scans[config.name] = config
    if state.item_scans:
        print(load_tag(f"{len(state.item_scans)} Item-Scan(s) geladen"))


# =============================================================================
# BOSS-SCAN PERSISTENZ
# =============================================================================
def ensure_boss_scans_dir() -> Path:
    """Stellt sicher, dass der Boss-Scans-Ordner existiert."""
    path = Path(BOSS_SCANS_DIR)
    path.mkdir(exist_ok=True)
    return path


def _boss_profile_to_dict(boss: BossProfile) -> dict:
    """Serialisiert ein BossProfile zu einem Dict."""
    return {
        "name": boss.name,
        "marker_colors": [list(c) for c in boss.marker_colors],
        "template": boss.template,
        "min_confidence": boss.min_confidence,
        "action": boss.action,
        "action_scan": boss.action_scan,
        "action_scan_mode": boss.action_scan_mode,
        "action_x": boss.action_x,
        "action_y": boss.action_y,
        "action_key": boss.action_key,
        "action_delay": boss.action_delay,
    }


def _boss_profile_from_dict(data: dict) -> BossProfile:
    """Deserialisiert ein BossProfile aus einem Dict."""
    return BossProfile(
        name=data["name"],
        marker_colors=[tuple(c) for c in data.get("marker_colors", [])],
        template=data.get("template"),
        min_confidence=data.get("min_confidence", DEFAULT_MIN_CONFIDENCE),
        action=data.get("action", BOSS_ACTION_SCAN),
        action_scan=data.get("action_scan"),
        action_scan_mode=data.get("action_scan_mode", SCAN_MODE_ALL),
        action_x=data.get("action_x", 0),
        action_y=data.get("action_y", 0),
        action_key=data.get("action_key"),
        action_delay=data.get("action_delay", 0),
    )


def save_boss_scan(config: BossScanConfig) -> None:
    """Speichert eine Boss-Scan Konfiguration."""
    ensure_boss_scans_dir()

    data = {
        "name": config.name,
        "scan_region": list(config.scan_region),
        "color_tolerance": config.color_tolerance,
        "default_action": config.default_action,
        "default_scan": config.default_scan,
        "bosses": [_boss_profile_to_dict(b) for b in config.bosses],
    }

    filename = f"{sanitize_filename(config.name)}.json"
    try:
        with open(Path(BOSS_SCANS_DIR) / filename, "w", encoding="utf-8") as f:
            f.write(compact_json(data))
        print(save_tag(f"Boss-Scan '{config.name}' gespeichert in '{BOSS_SCANS_DIR}/'"))
    except (IOError, OSError) as e:
        print(err(f"Boss-Scan konnte nicht gespeichert werden: {e}"))


def load_boss_scan_file(filepath: Path) -> Optional[BossScanConfig]:
    """Lädt eine Boss-Scan Konfiguration."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

            bosses = [_boss_profile_from_dict(b) for b in data.get("bosses", [])]

            return BossScanConfig(
                name=data["name"],
                scan_region=tuple(data["scan_region"]),
                color_tolerance=data.get("color_tolerance", 30),
                default_action=data.get("default_action", "skip"),
                default_scan=data.get("default_scan"),
                bosses=bosses,
            )

    except (json.JSONDecodeError, IOError, KeyError, TypeError) as e:
        logger.error(f"Konnte {filepath} nicht laden: {e}")
        return None


def list_available_boss_scans() -> list[tuple[str, Path]]:
    """Listet alle verfügbaren Boss-Scan Konfigurationen auf."""
    scan_dir = Path(BOSS_SCANS_DIR)
    if not scan_dir.exists():
        return []

    scans = []
    for f in scan_dir.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as file:
                data = json.load(file)
                name = data.get("name", f.stem)
                scans.append((name, f))
        except (json.JSONDecodeError, IOError, KeyError, TypeError):
            pass
    return scans


def load_all_boss_scans(state: AutoClickerState) -> None:
    """Lädt alle Boss-Scan Konfigurationen."""
    for name, path in list_available_boss_scans():
        config = load_boss_scan_file(path)
        if config:
            state.boss_scans[config.name] = config
    if state.boss_scans:
        print(load_tag(f"{len(state.boss_scans)} Boss-Scan(s) geladen"))


# =============================================================================
# GLOBALE SLOTS UND ITEMS PERSISTENZ
# =============================================================================
def save_global_slots(state: AutoClickerState) -> None:
    """Speichert alle globalen Slots."""
    data = {
        name: {
            "name": slot.name,
            "scan_region": list(slot.scan_region),
            "click_pos": list(slot.click_pos),
            "slot_color": list(slot.slot_color) if slot.slot_color else None
        }
        for name, slot in state.global_slots.items()
    }
    try:
        with open(SLOTS_FILE, "w", encoding="utf-8") as f:
            f.write(compact_json(data))
        print(save_tag(f"{len(state.global_slots)} Slot(s) gespeichert"))
    except (IOError, OSError) as e:
        print(err(f"Slots konnten nicht gespeichert werden: {e}"))


def load_global_slots(state: AutoClickerState) -> None:
    """Lädt alle globalen Slots."""
    if not Path(SLOTS_FILE).exists():
        return
    try:
        with open(SLOTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for name, s in data.items():
            slot_color = tuple(s["slot_color"]) if s.get("slot_color") else None
            state.global_slots[name] = ItemSlot(
                name=s["name"],
                scan_region=tuple(s["scan_region"]),
                click_pos=tuple(s["click_pos"]),
                slot_color=slot_color
            )
        if state.global_slots:
            print(load_tag(f"{len(state.global_slots)} Slot(s) geladen"))
    except (json.JSONDecodeError, IOError, KeyError, TypeError) as e:
        logger.error(f"Slots laden fehlgeschlagen: {e}")


def save_global_items(state: AutoClickerState) -> None:
    """Speichert alle globalen Items, sortiert nach Kategorie und Priorität."""
    sorted_items = sorted(state.global_items.items(),
                          key=lambda kv: (kv[1].category is None, kv[1].category or "", kv[1].priority))
    data = {name: _item_to_dict(item) for name, item in sorted_items}
    try:
        with open(ITEMS_FILE, "w", encoding="utf-8") as f:
            f.write(compact_json(data))
        print(save_tag(f"{len(state.global_items)} Item(s) gespeichert"))
    except (IOError, OSError) as e:
        print(err(f"Items konnten nicht gespeichert werden: {e}"))


def load_global_items(state: AutoClickerState) -> None:
    """Lädt alle globalen Items."""
    if not Path(ITEMS_FILE).exists():
        return
    try:
        with open(ITEMS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for name, i in data.items():
            state.global_items[name] = _item_from_dict(i)
        if state.global_items:
            print(load_tag(f"{len(state.global_items)} Item(s) geladen"))
    except (json.JSONDecodeError, IOError, KeyError, TypeError) as e:
        logger.error(f"Items laden fehlgeschlagen: {e}")


# =============================================================================
# GENERISCHE PRESET-FUNKTIONEN
# =============================================================================
def _list_presets(presets_dir: str) -> list[tuple[str, Path, int]]:
    """Listet alle verfügbaren Presets in einem Verzeichnis auf."""
    preset_dir = Path(presets_dir)
    if not preset_dir.exists():
        return []
    presets = []
    for f in preset_dir.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as file:
                data = json.load(file)
                presets.append((f.stem, f, len(data)))
        except (json.JSONDecodeError, IOError, KeyError, TypeError):
            pass
    return presets


def _save_preset(data: dict, preset_name: str, presets_dir: str, label: str) -> bool:
    """Speichert Daten als Preset-Datei."""
    safe_name = sanitize_filename(preset_name)
    filepath = Path(presets_dir) / f"{safe_name}.json"
    try:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(compact_json(data))
        print(save_tag(f"{label}-Preset '{preset_name}' gespeichert ({len(data)} {label}s)"))
        return True
    except (IOError, OSError) as e:
        print(err(f"{label}-Preset konnte nicht gespeichert werden: {e}"))
        return False


def _delete_preset(preset_name: str, presets_dir: str, label: str) -> bool:
    """Löscht eine Preset-Datei."""
    safe_name = sanitize_filename(preset_name)
    filepath = Path(presets_dir) / f"{safe_name}.json"
    if not filepath.exists():
        print(err(f"Preset '{preset_name}' nicht gefunden!"))
        return False
    try:
        filepath.unlink()
        print(delete_tag(f"{label}-Preset '{preset_name}' gelöscht"))
        return True
    except OSError as e:
        print(err(f"Preset konnte nicht gelöscht werden: {e}"))
        return False


# =============================================================================
# SLOT UND ITEM PRESETS (delegieren an generische Funktionen)
# =============================================================================
def list_slot_presets() -> list[tuple[str, Path, int]]:
    """Listet alle verfügbaren Slot-Presets auf."""
    return _list_presets(SLOT_PRESETS_DIR)


def save_slot_preset(state: AutoClickerState, preset_name: str) -> bool:
    """Speichert aktuelle Slots als Preset."""
    if not state.global_slots:
        print(err("Keine Slots vorhanden zum Speichern!"))
        return False
    data = {
        name: {
            "name": slot.name,
            "scan_region": list(slot.scan_region),
            "click_pos": list(slot.click_pos),
            "slot_color": list(slot.slot_color) if slot.slot_color else None
        }
        for name, slot in state.global_slots.items()
    }
    return _save_preset(data, preset_name, SLOT_PRESETS_DIR, "Slot")


def load_slot_preset(state: AutoClickerState, preset_name: str) -> bool:
    """Lädt ein Slot-Preset."""
    safe_name = sanitize_filename(preset_name)
    filepath = Path(SLOT_PRESETS_DIR) / f"{safe_name}.json"
    if not filepath.exists():
        print(err(f"Preset '{preset_name}' nicht gefunden!"))
        return False
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        with state.lock:
            state.global_slots.clear()
            for name, s in data.items():
                slot_color = tuple(s["slot_color"]) if s.get("slot_color") else None
                state.global_slots[name] = ItemSlot(
                    name=s["name"],
                    scan_region=tuple(s["scan_region"]),
                    click_pos=tuple(s["click_pos"]),
                    slot_color=slot_color
                )
        save_global_slots(state)
        print(load_tag(f"Slot-Preset '{preset_name}' geladen ({len(state.global_slots)} Slots)"))
        return True
    except (json.JSONDecodeError, IOError, KeyError, TypeError) as e:
        print(err(f"Preset laden fehlgeschlagen: {e}"))
        return False


def delete_slot_preset(preset_name: str) -> bool:
    """Löscht ein Slot-Preset."""
    return _delete_preset(preset_name, SLOT_PRESETS_DIR, "Slot")


def list_item_presets() -> list[tuple[str, Path, int]]:
    """Listet alle verfügbaren Item-Presets auf."""
    return _list_presets(ITEM_PRESETS_DIR)


def save_item_preset(state: AutoClickerState, preset_name: str) -> bool:
    """Speichert aktuelle Items als Preset."""
    if not state.global_items:
        print(err("Keine Items vorhanden zum Speichern!"))
        return False
    sorted_items = sorted(state.global_items.items(),
                          key=lambda kv: (kv[1].category is None, kv[1].category or "", kv[1].priority))
    data = {name: _item_to_dict(item) for name, item in sorted_items}
    return _save_preset(data, preset_name, ITEM_PRESETS_DIR, "Item")


def load_item_preset(state: AutoClickerState, preset_name: str) -> bool:
    """Lädt ein Item-Preset."""
    safe_name = sanitize_filename(preset_name)
    filepath = Path(ITEM_PRESETS_DIR) / f"{safe_name}.json"
    if not filepath.exists():
        print(err(f"Preset '{preset_name}' nicht gefunden!"))
        return False
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        with state.lock:
            state.global_items.clear()
            for name, i in data.items():
                state.global_items[name] = _item_from_dict(i)
        save_global_items(state)
        print(load_tag(f"Item-Preset '{preset_name}' geladen ({len(state.global_items)} Items)"))
        return True
    except (json.JSONDecodeError, IOError, KeyError, TypeError) as e:
        print(err(f"Preset laden fehlgeschlagen: {e}"))
        return False


def delete_item_preset(preset_name: str) -> bool:
    """Löscht ein Item-Preset."""
    return _delete_preset(preset_name, ITEM_PRESETS_DIR, "Item")


# =============================================================================
# HILFSFUNKTIONEN
# =============================================================================
def get_existing_categories(state: AutoClickerState) -> list[str]:
    """Sammelt alle existierenden Kategorien aus den Items."""
    categories = set()
    for item in state.global_items.values():
        if item.category:
            categories.add(item.category)
    return sorted(categories)


def shift_category_priorities(state: AutoClickerState, category: str) -> int:
    """Verschiebt alle Items einer Kategorie um +1 in der Priorität."""
    if not category:
        return 0

    shifted = 0
    with state.lock:
        for item in state.global_items.values():
            if item.category == category:
                item.priority += 1
                shifted += 1

    if shifted > 0:
        save_global_items(state)
        print(f"  → {shifted} Item(s) in Kategorie '{category}' nach hinten verschoben")

    return shifted


def update_item_in_scans(old_name: str, new_name: str, new_template: Optional[str] = None) -> tuple[int, int]:
    """Aktualisiert ein Item in allen Scan-Konfigurationen.

    Returns:
        (updated_count, failed_count) - Anzahl aktualisierter und fehlgeschlagener Scans.
    """
    updated_scans = 0
    failed_scans = 0
    scan_dir = Path(ITEM_SCANS_DIR)

    if not scan_dir.exists():
        return 0, 0

    for scan_file in scan_dir.glob("*.json"):
        try:
            with open(scan_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            modified = False
            for item in data.get("items", []):
                if item.get("name") == old_name:
                    item["name"] = new_name
                    if new_template:
                        item["template"] = new_template
                    modified = True

            if modified:
                with open(scan_file, "w", encoding="utf-8") as f:
                    f.write(compact_json(data))
                updated_scans += 1

        except (json.JSONDecodeError, IOError, KeyError, TypeError) as e:
            failed_scans += 1
            print(f"  {warn(f'Konnte {scan_file.name} nicht aktualisieren: {e}')}")

    return updated_scans, failed_scans


def print_points(state: AutoClickerState) -> None:
    """Zeigt alle gespeicherten Punkte an."""
    with state.lock:
        if not state.points:
            print(f"\n{info('Keine Punkte vorhanden.')}")
            print("       Punkte mit CTRL+ALT+A aufnehmen.")
            return

        print(f"\nGespeicherte Punkte ({len(state.points)}):")
        print("-" * 50)
        for p in state.points:
            print(f"  #{p.id:3d} {p.name:20s} ({p.x:4d}, {p.y:4d})")
        print("-" * 50)
