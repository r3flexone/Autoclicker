"""
Serialisierungs-Helfer: konvertieren Dataclasses ↔ JSON-Dicts.

Werden sowohl intern von den anderen persistence-Modulen genutzt als auch
extern von import_export.py (für die ZIP-Bundle-Erstellung).

Die führenden Underscores in den Funktionsnamen sind historisch — sie waren
ursprünglich modulprivat bevor import_export.py sie übernommen hat. Namen
bleiben stabil, um nicht alle Callsites anfassen zu müssen.
"""

from dataclasses import asdict

from ..config import DEFAULT_MIN_CONFIDENCE
from ..models import (
    ClickPoint, ElseConfig, WaitCondition, SequenceStep, Sequence,
    ItemProfile, ItemSlot, BossProfile,
    BOSS_ACTION_SCAN, SCAN_MODE_ALL,
)


# =============================================================================
# ITEM + SLOT
# =============================================================================

def _item_to_dict(item: ItemProfile) -> dict:
    """Serialisiert ein ItemProfile zu einem Dict (via dataclasses.asdict)."""
    d = asdict(item)
    # confirm_point: ClickPoint → nur {x, y} behalten (id/name nicht relevant)
    if d["confirm_point"]:
        d["confirm_point"] = {"x": d["confirm_point"]["x"], "y": d["confirm_point"]["y"]}
    return d


def _slot_to_dict(slot: 'ItemSlot') -> dict:
    """Serialisiert einen ItemSlot zu einem Dict."""
    return {
        "name": slot.name,
        "scan_region": list(slot.scan_region),
        "click_pos": list(slot.click_pos),
        "slot_color": list(slot.slot_color) if slot.slot_color else None,
    }


def _point_to_dict(p: 'ClickPoint') -> dict:
    """Serialisiert einen ClickPoint zu einem Dict (points.json / Export).

    color/source nur wenn gesetzt — hält alte Dateien schlank und vermeidet
    leere Felder. Zentral, damit points.json-Writer und Export identisch sind.
    """
    return {
        "id": p.id, "x": p.x, "y": p.y, "name": p.name,
        **({"color": list(p.color)} if p.color else {}),
        **({"source": p.source} if p.source else {}),
    }


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
# BOSS-PROFILE
# =============================================================================

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


# =============================================================================
# SCAN-KONFIGURATIONEN (eine JSON pro Scan)
# =============================================================================
# Diese Funktionen sind die EINE Quelle der Wahrheit für das Dateiformat der
# Scans — genutzt von den persistence-Savern UND vom ZIP-Export, damit beide
# garantiert dasselbe schreiben.

def _item_scan_to_dict(config: 'ItemScanConfig') -> dict:
    """Serialisiert eine ItemScanConfig zu einem Dict."""
    return {
        "name": config.name,
        "color_tolerance": config.color_tolerance,
        "learn_unknown": config.learn_unknown,
        "slots": [_slot_to_dict(slot) for slot in config.slots],
        "items": [_item_to_dict(item) for item in config.items],
    }


def _boss_scan_to_dict(config: 'BossScanConfig') -> dict:
    """Serialisiert eine BossScanConfig zu einem Dict (ohne globale Bosse)."""
    return {
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


def _icon_scan_to_dict(config: 'IconScanConfig') -> dict:
    """Serialisiert eine IconScanConfig zu einem Dict."""
    return {
        "name": config.name,
        "scan_region": list(config.scan_region),
        "template": config.template,
        "min_confidence": config.min_confidence,
        "marker_colors": [list(c) for c in config.marker_colors],
        "color_tolerance": config.color_tolerance,
        "action": config.action,
        "action_x": config.action_x,
        "action_y": config.action_y,
        "action_key": config.action_key,
        "action_delay": config.action_delay,
    }


# =============================================================================
# SEQUENZ-SCHRITTE
# =============================================================================

def _step_to_dict(s: SequenceStep) -> dict:
    """Konvertiert einen SequenceStep in ein JSON-serialisierbares dict."""
    wc = s.wait_condition
    ec = s.else_config
    return {"x": s.x, "y": s.y, "name": s.name, "delay_before": s.delay_before,
            "wait_pixel": wc.pixel if wc else None,
            "wait_color": wc.color if wc else None,
            "wait_until_gone": wc.until_gone if wc else False,
            "wait_check_only": wc.check_only if wc else False,
            "item_scan": s.item_scan, "item_scan_mode": s.item_scan_mode,
            "boss_scan": s.boss_scan,
            "boss_watcher": s.boss_watcher,
            "icon_scan": s.icon_scan,
            "wait_only": s.wait_only, "delay_max": s.delay_max,
            "key_press": s.key_press,
            "scroll": s.scroll,
            "else_action": ec.action if ec else None,
            "else_x": ec.x if ec else 0, "else_y": ec.y if ec else 0,
            "else_delay": ec.delay if ec else 0,
            "else_key": ec.key if ec else None, "else_name": ec.name if ec else "",
            "screenshot_only": s.screenshot_only,
            "screenshot_region": list(s.screenshot_region) if s.screenshot_region else None,
            "recorded_color": list(s.recorded_color) if s.recorded_color else None}


def _sequence_to_dict(seq: Sequence) -> dict:
    """Konvertiert eine Sequence in ein JSON-serialisierbares dict."""
    return {
        "name": seq.name,
        "total_cycles": seq.total_cycles,
        **({"description": seq.description} if seq.description else {}),
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


def _parse_steps(steps_data: list) -> list[SequenceStep]:
    """Parst die Schritt-Liste aus einer Sequence-JSON. Behandelt alle Legacy-Formate."""
    from ..utils import warn

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
                until_gone=s.get("wait_until_gone", False),
                check_only=s.get("wait_check_only", False),
            )
        # Aufgenommene Pixelfarbe (Referenzdatum für Nachbearbeitung)
        recorded_color_raw = s.get("recorded_color")
        recorded_color = tuple(int(v) for v in recorded_color_raw) if recorded_color_raw else None
        # Screenshot-Region validieren (muss 4 Werte haben)
        screenshot_region_raw = s.get("screenshot_region")
        screenshot_region = None
        if screenshot_region_raw:
            if len(screenshot_region_raw) == 4:
                screenshot_region = tuple(int(v) for v in screenshot_region_raw)
            else:
                print(warn(f"Ungültige screenshot_region (erwarte 4 Werte, habe {len(screenshot_region_raw)}) - ignoriert"))
        # ElseConfig zusammenbauen
        else_cfg = None
        else_action = s.get("else_action")
        if else_action:
            # Gegen explizites null in der JSON absichern: .get(key, default)
            # liefert bei "else_delay": null den Wert None (nicht den Default),
            # und None > 0 / safe_click(None, None) würde später crashen.
            else_x = s.get("else_x") if s.get("else_x") is not None else 0
            else_y = s.get("else_y") if s.get("else_y") is not None else 0
            else_delay = s.get("else_delay") if s.get("else_delay") is not None else 0
            else_cfg = ElseConfig(
                action=else_action,
                x=else_x, y=else_y,
                delay=else_delay,
                key=s.get("else_key"), name=s.get("else_name") or ""
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
            boss_watcher=s.get("boss_watcher"),
            icon_scan=s.get("icon_scan"),
            wait_only=s.get("wait_only", False),
            delay_max=float(delay_max_raw) if delay_max_raw is not None else None,
            key_press=s.get("key_press"),
            scroll=s.get("scroll"),
            else_config=else_cfg,
            screenshot_only=s.get("screenshot_only", False),
            screenshot_region=screenshot_region,
            recorded_color=recorded_color,
        )
        steps.append(step)
    return steps
