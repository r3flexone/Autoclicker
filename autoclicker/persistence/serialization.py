"""Serialisierungs-Helfer: konvertieren Dataclasses ↔ JSON-Dicts.

Die EINE Quelle der Wahrheit fürs Dateiformat: die Saver und der Start-Durchgang
(`sweep.py`) laufen alle durch diese Funktionen. `import_export.py` rechnet das
Bündel dagegen auf den rohen Dicts um und kennt sie nicht. Die führenden
Underscores sind historisch — die Funktionen waren einmal modulprivat.
"""

from dataclasses import asdict
from typing import TYPE_CHECKING, Optional

from ..models import (
    DEFAULT_MIN_CONFIDENCE,
    ClickPoint, ElseConfig, WaitCondition, SequenceStep, Sequence,
    ItemProfile, ItemSlot, ItemScanConfig, BossProfile,
    BOSS_ACTION_SCAN, BOSS_ACTION_SKIP, ICON_ACTION_CLICK, SCAN_MODE_ALL,
)

if TYPE_CHECKING:  # nur fuer die Annotationen unten
    from ..models import BossScanConfig, IconScanConfig


# GESCHRIEBEN WIRD NUR, WAS GESETZT IST. Der Loader setzt ohnehin genau den
# Default, also ist ein Feld auf dem Standardwert in der Datei ueberfluessig -
# und was ueberfluessig ist, macht die Datei unlesbar. Die Tabellen hier und die
# Dataclasses muessen deshalb zusammenpassen; ein Test prueft das.

# Sentinel: unterscheidet "kein Default hinterlegt" von "Default ist None".
_NO_DEFAULT = object()


def _is_default(value, default) -> bool:
    """Trägt das Feld seinen Standardwert?

    In Python ist `0 == False` und `1 == True`. Ohne Typprüfung würde `"else_delay": 0`
    als False durchgehen und `"screenshot_only": 0` als False gelten. Zahlen untereinander
    (0 vs 0.0) sollen dagegen als gleich zählen.
    """
    if isinstance(value, bool) != isinstance(default, bool):
        return False
    if isinstance(value, (int, float)) and isinstance(default, (int, float)):
        return value == default
    return type(value) is type(default) and value == default


def _without_defaults(data: dict, defaults: dict) -> dict:
    """Entfernt alle Felder, die ihren Standardwert tragen."""
    return {k: v for k, v in data.items()
            if not (defaults.get(k, _NO_DEFAULT) is not _NO_DEFAULT
                    and _is_default(v, defaults[k]))}


# =============================================================================
# ITEM + SLOT
# =============================================================================
# Items und Slots liegen ausschliesslich in Name->Eintrag-Dicts (items.json, slots.json,
# die Preset-Ordner). Der Name steht damit schon im Schlüssel - ihn zusätzlich im Eintrag
# zu führen war doppelt, und genau die Stelle, an der ein Umbenennen inkonsistent wird.

_ITEM_DEFAULTS = {
    "marker_colors": [],
    "category": None,
    "priority": 1,
    "confirm_point_id": None,
    "confirm_delay": 0.5,
    "template": None,
    "min_confidence": DEFAULT_MIN_CONFIDENCE,
    "template_variants": [],
    "enabled": True,
}

_SLOT_DEFAULTS = {"slot_color": None, "enabled": True, "id": 0}


def _item_to_dict(item: ItemProfile) -> dict:
    """Serialisiert ein ItemProfile - ohne `name` (steht im Schlüssel) und ohne Defaults."""
    d = asdict(item)
    d.pop("name", None)
    # Der Bestätigungsklick steht als ID drin, nicht als Koordinate: die wohnt im Punkt.
    # `confirm_point` ist nur der aufgelöste Arbeitswert und wird nicht geschrieben.
    d.pop("confirm_point", None)
    return _without_defaults(d, _ITEM_DEFAULTS)


def _slot_to_dict(slot: 'ItemSlot') -> dict:
    """Serialisiert einen ItemSlot - ohne `name` (steht im Schlüssel)."""
    return _without_defaults({
        "scan_region": list(slot.scan_region),
        "click_pos": list(slot.click_pos),
        "slot_color": list(slot.slot_color) if slot.slot_color else None,
        "enabled": slot.enabled,
        "id": slot.id,
    }, _SLOT_DEFAULTS)


def _slot_from_dict(name: str, data: dict) -> 'ItemSlot':
    """Deserialisiert einen ItemSlot. `name` kommt aus dem Schlüssel.

    Zentral, damit Item-Scan, Presets und Start-Durchgang dasselbe lesen - vorher
    stand dieselbe Schleife dreimal da.
    """
    if not isinstance(data, dict):
        raise TypeError("Slot muss ein JSON-Objekt sein")
    color = data.get("slot_color")
    return ItemSlot(
        name=name,
        scan_region=tuple(data["scan_region"]),
        click_pos=tuple(data["click_pos"]),
        slot_color=tuple(color) if color else None,
        # Nur ein echtes JSON-`false` schaltet aus. Kaputte oder alte Werte
        # fallen auf den sicheren bisherigen Standard „an" zurück.
        enabled=data.get("enabled", True) is not False,
        id=int(data.get("id", 0) or 0),
    )


def _point_to_dict(p: 'ClickPoint') -> dict:
    """Serialisiert einen ClickPoint für die Punktliste in sequence.json.

    color/source nur wenn gesetzt — hält alte Dateien schlank und vermeidet
    leere Felder. Zentral, damit Speichern und Export identisch sind.
    """
    return {
        "id": p.id, "x": p.x, "y": p.y,
        **({"name": p.name} if p.name else {}),
        **({"color": list(p.color)} if p.color else {}),
        **({"source": p.source} if p.source else {}),
    }


def _item_from_dict(data: dict, name: str) -> ItemProfile:
    """Deserialisiert ein ItemProfile. `name` kommt aus dem Schlüssel des Dicts."""
    if not isinstance(data, dict):
        raise TypeError("Item muss ein JSON-Objekt sein")
    # Ein altes `confirm_point` (Koordinate im Item) ist ein unbekannter Schlüssel
    # wie jeder andere: der Bestätigungsklick ist heute ein Punkt (`confirm_point_id`).
    variants = data.get("template_variants", [])
    if not isinstance(variants, list):
        variants = []
    primary = data.get("template")
    variants = [v for v in variants
                 if isinstance(v, str) and v and v != primary]
    return ItemProfile(
        name=name,
        marker_colors=[tuple(c) for c in data.get("marker_colors", [])],
        category=data.get("category"),
        priority=data.get("priority", 1),
        confirm_point_id=data.get("confirm_point_id"),
        confirm_delay=data.get("confirm_delay", 0.5),
        template=data.get("template"),
        min_confidence=data.get("min_confidence", DEFAULT_MIN_CONFIDENCE),
        template_variants=list(dict.fromkeys(variants)),
        enabled=data.get("enabled", True),
    )


# =============================================================================
# BOSS-PROFILE
# =============================================================================

# Bosse liegen in einer LISTE (Reihenfolge = Prioritaet), deshalb bleibt `name` hier drin.
_BOSS_DEFAULTS = {
    "marker_colors": [],
    "template": None,
    "min_confidence": DEFAULT_MIN_CONFIDENCE,
    "action": BOSS_ACTION_SCAN,
    "action_scan": None,
    "action_scan_mode": SCAN_MODE_ALL,
    "action_point_id": None,
    "action_key": None,
    "action_delay": 0,
}


def _boss_profile_to_dict(boss: BossProfile) -> dict:
    """Serialisiert ein BossProfile zu einem Dict."""
    return _without_defaults({
        "name": boss.name,
        "marker_colors": [list(c) for c in boss.marker_colors],
        "template": boss.template,
        "min_confidence": boss.min_confidence,
        "action": boss.action,
        "action_scan": boss.action_scan,
        "action_scan_mode": boss.action_scan_mode,
        "action_point_id": boss.action_point_id,
        "action_key": boss.action_key,
        "action_delay": boss.action_delay,
    }, _BOSS_DEFAULTS)


def _boss_profile_from_dict(data: dict) -> BossProfile:
    """Deserialisiert ein BossProfile aus einem Dict."""
    if not isinstance(data, dict):
        raise TypeError("Boss muss ein JSON-Objekt sein")
    return BossProfile(
        name=data["name"],
        marker_colors=[tuple(c) for c in data.get("marker_colors", [])],
        template=data.get("template"),
        min_confidence=data.get("min_confidence", DEFAULT_MIN_CONFIDENCE),
        action=data.get("action", BOSS_ACTION_SCAN),
        action_scan=data.get("action_scan"),
        action_scan_mode=data.get("action_scan_mode", SCAN_MODE_ALL),
        action_point_id=data.get("action_point_id"),
        action_key=data.get("action_key"),
        action_delay=data.get("action_delay", 0),
    )


# =============================================================================
# SCAN-KONFIGURATIONEN (eine JSON pro Scan)
# =============================================================================
# Diese Funktionen sind die EINE Quelle der Wahrheit für das Dateiformat der
# Scans — die persistence-Saver und der Start-Durchgang laufen durch dieselben,
# damit beide garantiert dasselbe schreiben.

# Als benannte Tabelle wie alle anderen - inline stehende Literale waren der Grund, warum
# der Item-Scan als einziger Typ nicht vom Drift-Test gegen die Dataclass geprueft wurde.
_ITEM_SCAN_DEFAULTS = {
    "color_tolerance": 40,
    "learn_unknown": False,
    "slots": {},
    "items": {},
    "reverse": False,
    "use_catalog": False,
    "capture_window_title": None,
    "capture_window_index": 0,
    "capture_window_rect": None,
}


def _item_scan_to_dict(config: 'ItemScanConfig') -> dict:
    """Serialisiert einen vollständigen, eigenständigen Item-Scan."""
    return _without_defaults({
        "name": config.name,
        "color_tolerance": config.color_tolerance,
        "learn_unknown": config.learn_unknown,
        "slots": {s.name: _slot_to_dict(s) for s in config.slots},
        "items": {i.name: _item_to_dict(i) for i in config.items},
        "reverse": config.reverse,
        "use_catalog": config.use_catalog,
        "capture_window_title": config.capture_window_title,
        "capture_window_index": config.capture_window_index,
        "capture_window_rect": (list(config.capture_window_rect)
                                if config.capture_window_rect else None),
    }, _ITEM_SCAN_DEFAULTS)


def _item_scan_from_dict(data: dict) -> ItemScanConfig:
    """Deserialisiert das zentrale Item-Scan-Format.

    Loader und Start-Durchgang müssen durch dieselbe Stelle laufen. Sonst schriebe
    der Round-Trip ein neues Feld nicht zurück, obwohl eine normal geladene Datei
    es kennt.
    """
    if not isinstance(data, dict):
        raise TypeError("Item-Scan muss ein JSON-Objekt sein")
    slots_data = data.get("slots", {})
    items_data = data.get("items", {})
    if not isinstance(slots_data, dict) or not isinstance(items_data, dict):
        raise TypeError("slots/items müssen Objekte sein")
    window_rect = data.get("capture_window_rect")
    if not isinstance(window_rect, (list, tuple)) or len(window_rect) != 4:
        window_rect = None
    else:
        try:
            window_rect = tuple(int(value) for value in window_rect)
            if (window_rect[2] <= window_rect[0]
                    or window_rect[3] <= window_rect[1]):
                window_rect = None
        except (TypeError, ValueError):
            window_rect = None
    window_title = data.get("capture_window_title")
    if not isinstance(window_title, str) or not window_title.strip():
        window_title = None
    else:
        window_title = window_title.strip()
    try:
        window_index = max(0, int(data.get("capture_window_index", 0)))
    except (TypeError, ValueError):
        window_index = 0
    return ItemScanConfig(
        name=data["name"],
        slots=[_slot_from_dict(str(name), value)
               for name, value in slots_data.items()],
        items=[_item_from_dict(value, str(name))
               for name, value in items_data.items()],
        color_tolerance=data.get("color_tolerance", 40),
        learn_unknown=data.get("learn_unknown", False),
        reverse=data.get("reverse", False),
        use_catalog=data.get("use_catalog", False),
        capture_window_title=window_title,
        capture_window_index=window_index,
        capture_window_rect=window_rect,
    )


_BOSS_SCAN_DEFAULTS = {
    "color_tolerance": 30,
    "default_action": BOSS_ACTION_SKIP,
    "default_scan": None,
    "bosses": [],
    "use_llm": False,
    "llm_fallback": True,
    "use_ocr": False,
    "ocr_fallback": True,
}


def _boss_scan_to_dict(config: 'BossScanConfig') -> dict:
    """Serialisiert eine BossScanConfig zu einem Dict (ohne globale Bosse)."""
    return _without_defaults({
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
    }, _BOSS_SCAN_DEFAULTS)


_ICON_SCAN_DEFAULTS = {
    "template": None,
    "min_confidence": DEFAULT_MIN_CONFIDENCE,
    "marker_colors": [],
    "color_tolerance": 30,
    "action": ICON_ACTION_CLICK,
    "action_point_id": None,
    "action_key": None,
    "action_delay": 0,
}


def _icon_scan_to_dict(config: 'IconScanConfig') -> dict:
    """Serialisiert eine IconScanConfig zu einem Dict."""
    return _without_defaults({
        "name": config.name,
        "scan_region": list(config.scan_region),
        "template": config.template,
        "min_confidence": config.min_confidence,
        "marker_colors": [list(c) for c in config.marker_colors],
        "color_tolerance": config.color_tolerance,
        "action": config.action,
        "action_point_id": config.action_point_id,
        "action_key": config.action_key,
        "action_delay": config.action_delay,
    }, _ICON_SCAN_DEFAULTS)


# =============================================================================
# SEQUENZ-SCHRITTE
# =============================================================================

def _step_to_dict(s: SequenceStep) -> dict:
    """Konvertiert einen SequenceStep in ein JSON-serialisierbares dict.

    **Koordinaten werden nie geschrieben.** Klick, Prüf-Pixel, Nachprüfung und
    Else-Klick stehen als Punkt-ID da; `x`/`y`, Pixel, Farben und der Name des
    Else-Klicks sind aus dem Punkt abgeleitete Arbeitswerte (`resolve()`).
    `name` bleibt nur an Schritten ohne Punkt — dort ist es der eigene Name des
    Blocks (Taste, Scans, Screenshot).
    """
    wc = s.wait_condition
    ec = s.else_config
    vc = s.verify_condition
    full_value = {"name": "" if s.point_id is not None else s.name,
            "point_id": s.point_id,
            "delay_before": s.delay_before,
            "wait_point_id": wc.point_id if wc else None,
            "wait_until_gone": wc.until_gone if wc else False,
            "wait_check_only": wc.check_only if wc else False,
            "wait_timeout": wc.timeout if wc else None,
            "item_scan": s.item_scan, "item_scan_mode": s.item_scan_mode,
            "boss_scan": s.boss_scan,
            "boss_watcher": s.boss_watcher,
            "icon_scan": s.icon_scan,
            "wait_only": s.wait_only, "delay_max": s.delay_max,
            "key_press": s.key_press,
            "else_action": ec.action if ec else None,
            "else_point_id": ec.point_id if ec else None,
            "else_delay": ec.delay if ec else 0,
            "else_key": ec.key if ec else None,
            "verify_point_id": vc.point_id if vc else None,
            "verify_until_gone": vc.until_gone if vc else False,
            "screenshot_only": s.screenshot_only,
            "screenshot_region": list(s.screenshot_region) if s.screenshot_region else None,
            "breakpoint": bool(s.breakpoint),
            "mouse_return": bool(s.mouse_return)}
    return _without_defaults(full_value, _STEP_DEFAULTS)


# Was ein Feld bedeutet, wenn es "nicht gesetzt" ist; steht der Wert drin, wird das
# Feld nicht geschrieben. Ein Klick-Schritt hat 25 Felder, davon 23 leer - und in
# einer Datei voller "wait_point_id": null findet man nichts mehr.
# `delay_before` steht NICHT hier: eine Wartezeit von 0 will man sehen.
_STEP_DEFAULTS = {
    "name": "",
    "point_id": None,
    "wait_point_id": None,
    "else_point_id": None,
    "wait_until_gone": False,
    "wait_check_only": False,
    "wait_timeout": None,
    "verify_point_id": None,
    "verify_until_gone": False,
    "item_scan": None,
    "item_scan_mode": "all",
    "boss_scan": None,
    "boss_watcher": None,
    "icon_scan": None,
    "wait_only": False,
    "delay_max": None,
    "key_press": None,
    "else_action": None,
    "else_delay": 0,
    "else_key": None,
    "screenshot_only": False,
    "screenshot_region": None,
    "breakpoint": False,
    "mouse_return": True,
}


def _sequence_to_dict(seq: Sequence) -> dict:
    """Konvertiert eine Sequence in ein JSON-serialisierbares dict."""
    return {
        "name": seq.name,
        **({"total_cycles": seq.total_cycles} if seq.total_cycles != 1 else {}),
        **({"description": seq.description} if seq.description else {}),
        **({"next_sequence": seq.next_sequence} if seq.next_sequence else {}),
        **({"next_delay": seq.next_delay}
           if seq.next_sequence and seq.next_delay != 30.0 else {}),
        "points": [_point_to_dict(p) for p in seq.points],
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
    """Parst die Schritt-Liste aus einer Sequence-JSON."""
    if not isinstance(steps_data, list) or any(not isinstance(s, dict) for s in steps_data):
        raise ValueError("Schritte müssen eine Liste von Objekten sein")
    return [_parse_step(s) for s in steps_data]


def _parse_step(s: dict) -> SequenceStep:
    """Ein Schritt aus seinem Dict — Bedingung, Nachprüfung und ELSE je für sich."""
    # `delay_after` (der Vorlaeufer) kennt der Loader nicht mehr — der
    # Migrationsschritt dafuer ist mit seinem Altbestand geloescht.
    delay_raw = s.get("delay_before")
    if delay_raw is None:
        delay_raw = 0
    delay_max_raw = s.get("delay_max")
    # x/y, Farben und Pixel liest der Loader nicht: sie stehen im Punkt und kommen von
    # dort (`resolve()`).
    return SequenceStep(
        delay_before=float(delay_raw),
        name=s.get("name", ""),
        point_id=s.get("point_id"),
        wait_condition=_parse_wait_condition(s),
        verify_condition=_parse_verify_condition(s),
        item_scan=s.get("item_scan"),
        item_scan_mode=s.get("item_scan_mode", "all"),
        boss_scan=s.get("boss_scan"),
        boss_watcher=s.get("boss_watcher"),
        icon_scan=s.get("icon_scan"),
        wait_only=s.get("wait_only", False),
        delay_max=float(delay_max_raw) if delay_max_raw is not None else None,
        key_press=s.get("key_press"),
        else_config=_parse_else_config(s),
        screenshot_only=s.get("screenshot_only", False),
        screenshot_region=_parse_screenshot_region(s.get("screenshot_region")),
        breakpoint=bool(s.get("breakpoint", False)),
        mouse_return=bool(s.get("mouse_return", True)),
    )


def _parse_wait_condition(s: dict) -> Optional[WaitCondition]:
    """Die Vorbedingung. Der Punkt liefert Position UND Farbe nach — pixel/color
    bleiben hier leer und fuellt resolve_point_references(). Ohne `wait_point_id`
    gibt es keine Bedingung."""
    wait_point_id = s.get("wait_point_id")
    if wait_point_id is None:
        return None
    # Eigene Zeitgrenze des Blocks; fehlt sie oder ist sie unlesbar, gilt
    # die Config — ein kaputter Wert soll den Block nicht ohne Grenze lassen.
    wait_timeout = s.get("wait_timeout")
    try:
        wait_timeout = max(0.0, float(wait_timeout)) if wait_timeout is not None else None
    except (TypeError, ValueError):
        wait_timeout = None
    return WaitCondition(point_id=wait_point_id,
                         until_gone=s.get("wait_until_gone", False),
                         check_only=s.get("wait_check_only", False),
                         timeout=wait_timeout)


def _parse_verify_condition(s: dict) -> Optional[WaitCondition]:
    """Nachpruefung ("hat der Klick gewirkt?") - gleiche Bauart wie wait_condition."""
    verify_point_id = s.get("verify_point_id")
    if verify_point_id is None:
        return None
    return WaitCondition(point_id=verify_point_id,
                         until_gone=s.get("verify_until_gone", False))


def _parse_screenshot_region(raw) -> Optional[tuple]:
    """Screenshot-Region validieren (muss 4 Werte haben)."""
    if not raw:
        return None
    if len(raw) == 4:
        return tuple(int(v) for v in raw)
    from ..utils import warn
    print(warn(f"Ungültige screenshot_region (erwarte 4 Werte, habe {len(raw)}) - ignoriert"))
    return None


def _parse_else_config(s: dict) -> Optional[ElseConfig]:
    """ElseConfig zusammenbauen.

    Gegen explizites null in der JSON absichern: .get(key, default) liefert bei
    "else_delay": null den Wert None (nicht den Default), und None > 0 /
    safe_click(None, None) würde später crashen.
    """
    else_action = s.get("else_action")
    if not else_action:
        return None
    return ElseConfig(
        action=else_action,
        point_id=s.get("else_point_id"),
        delay=_or_zero(s.get("else_delay")),
        key=s.get("else_key"),
    )


def _or_zero(value):
    return value if value is not None else 0
