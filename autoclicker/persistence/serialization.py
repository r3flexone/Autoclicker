"""Serialisierungs-Helfer: konvertieren Dataclasses ↔ JSON-Dicts.

Genutzt von den anderen persistence-Modulen UND von import_export.py, damit
beide dasselbe Format schreiben. Die führenden Underscores sind historisch —
die Funktionen waren einmal modulprivat.
"""

from dataclasses import asdict
from typing import TYPE_CHECKING

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
_KEIN_DEFAULT = object()


# Schon gemeldete Altfelder - sonst steht dieselbe Zeile bei 40 Items vierzigmal da.
_ALT_GEMELDET: set = set()


def _klick_referenz(data: dict, wo: str, was_tun: str):
    """`action_point_id` lesen - und ein altes `action_x/y` melden statt es zu schlucken.

    Boss- und Icon-Aktionen klicken heute einen Punkt. Die alte Koordinate im Scan war
    zwar nie doppelt gespeichert, hing aber auch an keinem Punkt: sie folgte weder einer
    Reparatur im Punkte-Menue noch einer Kalibrierung ueber die Punkte.
    """
    if data.get("action_point_id") is None and (data.get("action_x") or data.get("action_y")):
        _alt_gemeldet(wo, "action_x/action_y", was_tun)
    return data.get("action_point_id")


def _alt_gemeldet(wo: str, feld: str, was_tun: str) -> None:
    """Meldet ein Feld, das der Loader nicht mehr liest - einmal pro Fundstelle.

    Fuer Koordinaten, die es vor der Umstellung auf Punkt-Referenzen gab. Bewusst
    keine Migration: sie liesse sich bauen, kostet aber mehr als das Feld einmal neu
    zu setzen - und ein Feld, das niemand hat, braucht keinen Migrationsschritt. Still
    verschwinden darf es trotzdem nicht.
    """
    from ..utils import hint, warn
    schluessel = f"{wo}:{feld}"
    if schluessel in _ALT_GEMELDET:
        return
    _ALT_GEMELDET.add(schluessel)
    print(warn(f"{wo}: '{feld}' wird nicht mehr gelesen - Koordinaten wohnen jetzt "
               f"in sequence.json."))
    print(hint(f"       {was_tun}."))


def _ist_default(wert, default) -> bool:
    """Trägt das Feld seinen Standardwert?

    In Python ist `0 == False` und `1 == True`. Ohne Typprüfung würde `"scroll": 0` als
    False durchgehen und `"screenshot_only": 0` als False gelten. Zahlen untereinander
    (0 vs 0.0) sollen dagegen als gleich zählen.
    """
    if isinstance(wert, bool) != isinstance(default, bool):
        return False
    if isinstance(wert, (int, float)) and isinstance(default, (int, float)):
        return wert == default
    return type(wert) is type(default) and wert == default


def _ohne_defaults(daten: dict, defaults: dict) -> dict:
    """Entfernt alle Felder, die ihren Standardwert tragen."""
    return {k: v for k, v in daten.items()
            if not (defaults.get(k, _KEIN_DEFAULT) is not _KEIN_DEFAULT
                    and _ist_default(v, defaults[k]))}


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
    return _ohne_defaults(d, _ITEM_DEFAULTS)


def _slot_to_dict(slot: 'ItemSlot') -> dict:
    """Serialisiert einen ItemSlot - ohne `name` (steht im Schlüssel)."""
    return _ohne_defaults({
        "scan_region": list(slot.scan_region),
        "click_pos": list(slot.click_pos),
        "slot_color": list(slot.slot_color) if slot.slot_color else None,
        "enabled": slot.enabled,
        "id": slot.id,
    }, _SLOT_DEFAULTS)


def _slot_from_dict(name: str, data: dict) -> 'ItemSlot':
    """Deserialisiert einen ItemSlot. `name` kommt aus dem Schlüssel.

    Zentral, damit globals.py, presets.py und der Import dasselbe lesen - vorher stand
    dieselbe Schleife dreimal da.
    """
    if not isinstance(data, dict):
        raise TypeError("Slot muss ein JSON-Objekt sein")
    farbe = data.get("slot_color")
    return ItemSlot(
        name=name,
        scan_region=tuple(data["scan_region"]),
        click_pos=tuple(data["click_pos"]),
        slot_color=tuple(farbe) if farbe else None,
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
    # Ein altes `confirm_point` (Koordinate im Item) wird NICHT mehr gelesen - der
    # Bestätigungsklick ist heute ein Punkt. Bewusst ohne Migration: die Koordinate
    # liesse sich zwar in einen Punkt heben, aber der Weg dorthin (Punkte-Liste durch
    # alle Item-Loader reichen) kostet mehr, als das Feld neu zu setzen. Gemeldet wird
    # es, damit es nicht still verschwindet.
    if data.get("confirm_point") is not None and data.get("confirm_point_id") is None:
        _alt_gemeldet(f"Item '{name}'", "confirm_point",
                      "Bestätigungs-Punkt im Item-Editor neu setzen")
    varianten = data.get("template_variants", [])
    if not isinstance(varianten, list):
        varianten = []
    primaer = data.get("template")
    varianten = [v for v in varianten
                 if isinstance(v, str) and v and v != primaer]
    return ItemProfile(
        name=name,
        marker_colors=[tuple(c) for c in data.get("marker_colors", [])],
        category=data.get("category"),
        priority=data.get("priority", 1),
        confirm_point_id=data.get("confirm_point_id"),
        confirm_delay=data.get("confirm_delay", 0.5),
        template=data.get("template"),
        min_confidence=data.get("min_confidence", DEFAULT_MIN_CONFIDENCE),
        template_variants=list(dict.fromkeys(varianten)),
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
    return _ohne_defaults({
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
        action_point_id=_klick_referenz(data, f"Boss '{data.get('name', '?')}'",
                                        "Klick-Punkt im Boss-Scan-Editor neu setzen"),
        action_key=data.get("action_key"),
        action_delay=data.get("action_delay", 0),
    )


# =============================================================================
# SCAN-KONFIGURATIONEN (eine JSON pro Scan)
# =============================================================================
# Diese Funktionen sind die EINE Quelle der Wahrheit für das Dateiformat der
# Scans — genutzt von den persistence-Savern UND vom ZIP-Export, damit beide
# garantiert dasselbe schreiben.

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
    return _ohne_defaults({
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

    Loader und ZIP-Import müssen durch dieselbe Stelle laufen. Sonst verschwindet
    ein neues Feld beim Import still, obwohl eine normal geladene Datei es kennt.
    """
    if not isinstance(data, dict):
        raise TypeError("Item-Scan muss ein JSON-Objekt sein")
    slots_data = data.get("slots", {})
    items_data = data.get("items", {})
    if not isinstance(slots_data, dict) or not isinstance(items_data, dict):
        raise TypeError("slots/items müssen Objekte sein")
    fenster_rechteck = data.get("capture_window_rect")
    if not isinstance(fenster_rechteck, (list, tuple)) or len(fenster_rechteck) != 4:
        fenster_rechteck = None
    else:
        try:
            fenster_rechteck = tuple(int(wert) for wert in fenster_rechteck)
            if (fenster_rechteck[2] <= fenster_rechteck[0]
                    or fenster_rechteck[3] <= fenster_rechteck[1]):
                fenster_rechteck = None
        except (TypeError, ValueError):
            fenster_rechteck = None
    fenster_titel = data.get("capture_window_title")
    if not isinstance(fenster_titel, str) or not fenster_titel.strip():
        fenster_titel = None
    else:
        fenster_titel = fenster_titel.strip()
    try:
        fenster_index = max(0, int(data.get("capture_window_index", 0)))
    except (TypeError, ValueError):
        fenster_index = 0
    return ItemScanConfig(
        name=data["name"],
        slots=[_slot_from_dict(str(name), wert)
               for name, wert in slots_data.items()],
        items=[_item_from_dict(wert, str(name))
               for name, wert in items_data.items()],
        color_tolerance=data.get("color_tolerance", 40),
        learn_unknown=data.get("learn_unknown", False),
        reverse=data.get("reverse", False),
        use_catalog=data.get("use_catalog", False),
        capture_window_title=fenster_titel,
        capture_window_index=fenster_index,
        capture_window_rect=fenster_rechteck,
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
    return _ohne_defaults({
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
    return _ohne_defaults({
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

    Koordinaten werden NICHT geschrieben, solange eine `point_id` daneben steht;
    betrifft drei Paare — den Klick (x/y + recorded_color), den Pruef-Pixel
    (wait_pixel/wait_color) und den Else-Klick (else_x/else_y/else_name).

    `x`/`y` bleiben nur den Schritten, die gar keinen Punkt haben koennen (Taste,
    Scans, Screenshot) — dort sind sie 0 und fallen durch `_ohne_defaults` weg.
    """
    wc = s.wait_condition
    ec = s.else_config
    vc = s.verify_condition
    # Der Punkt traegt die Stelle: alles, was sich daraus ableiten laesst, entfaellt.
    klick_am_punkt = s.point_id is not None
    wait_am_punkt = wc is not None and wc.point_id is not None
    else_am_punkt = ec is not None and ec.point_id is not None
    verify_am_punkt = vc is not None and vc.point_id is not None
    voll = {"x": 0 if klick_am_punkt else s.x,
            "y": 0 if klick_am_punkt else s.y,
            "name": "" if klick_am_punkt else s.name,
            "point_id": s.point_id,
            "delay_before": s.delay_before,
            "wait_point_id": wc.point_id if wc else None,
            "wait_pixel": None if (wc is None or wait_am_punkt) else wc.pixel,
            "wait_color": None if (wc is None or wait_am_punkt) else wc.color,
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
            "else_point_id": ec.point_id if ec else None,
            "else_x": 0 if (ec is None or else_am_punkt) else ec.x,
            "else_y": 0 if (ec is None or else_am_punkt) else ec.y,
            "else_delay": ec.delay if ec else 0,
            "else_key": ec.key if ec else None,
            "else_name": "" if (ec is None or else_am_punkt) else ec.name,
            "verify_point_id": vc.point_id if vc else None,
            "verify_pixel": None if (vc is None or verify_am_punkt) else vc.pixel,
            "verify_color": None if (vc is None or verify_am_punkt) else vc.color,
            "verify_until_gone": vc.until_gone if vc else False,
            "screenshot_only": s.screenshot_only,
            "screenshot_region": list(s.screenshot_region) if s.screenshot_region else None,
            "recorded_color": None if klick_am_punkt or not s.recorded_color
                              else list(s.recorded_color)}
    return _ohne_defaults(voll, _STEP_DEFAULTS)


# Was ein Feld bedeutet, wenn es "nicht gesetzt" ist; steht der Wert drin, wird das
# Feld nicht geschrieben. Ein Klick-Schritt hat 27 Felder, davon 21 leer - und in
# einer Datei voller "wait_pixel": null findet man nichts mehr.
# `delay_before` steht NICHT hier: eine Wartezeit von 0 will man sehen.
_STEP_DEFAULTS = {
    "name": "",
    "x": 0,
    "y": 0,
    "point_id": None,
    "wait_point_id": None,
    "else_point_id": None,
    "wait_pixel": None,
    "wait_color": None,
    "wait_until_gone": False,
    "wait_check_only": False,
    "verify_point_id": None,
    "verify_pixel": None,
    "verify_color": None,
    "verify_until_gone": False,
    "item_scan": None,
    "item_scan_mode": "all",
    "boss_scan": None,
    "boss_watcher": None,
    "icon_scan": None,
    "wait_only": False,
    "delay_max": None,
    "key_press": None,
    "scroll": None,
    "else_action": None,
    "else_x": 0,
    "else_y": 0,
    "else_delay": 0,
    "else_key": None,
    "else_name": "",
    "screenshot_only": False,
    "screenshot_region": None,
    "recorded_color": None,
}





def _sequence_to_dict(seq: Sequence) -> dict:
    """Konvertiert eine Sequence in ein JSON-serialisierbares dict."""
    return {
        "name": seq.name,
        **({"total_cycles": seq.total_cycles} if seq.total_cycles != 1 else {}),
        **({"description": seq.description} if seq.description else {}),
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
    """Parst die Schritt-Liste aus einer Sequence-JSON. Behandelt alle Legacy-Formate."""
    from ..utils import warn

    if not isinstance(steps_data, list) or any(not isinstance(s, dict) for s in steps_data):
        raise ValueError("Schritte müssen eine Liste von Objekten sein")
    steps = []
    for s in steps_data:
        wait_pixel = s.get("wait_pixel")
        if wait_pixel:
            wait_pixel = tuple(int(v) for v in wait_pixel)
        wait_color = s.get("wait_color")
        if wait_color:
            wait_color = tuple(int(v) for v in wait_color)
        # delay_after (Vorlaeufer) hebt migration._seq_v1_to_v2, bevor hier gelesen wird.
        delay_raw = s.get("delay_before")
        if delay_raw is None:
            delay_raw = 0
        delay_max_raw = s.get("delay_max")
        # WaitCondition zusammenbauen. Mit `wait_point_id` liefert der Punkt Position UND
        # Farbe nach - pixel/color bleiben hier leer und fuellt resolve_point_references().
        wait_cond = None
        wait_point_id = s.get("wait_point_id")
        if wait_point_id is not None:
            wait_cond = WaitCondition(
                point_id=wait_point_id,
                until_gone=s.get("wait_until_gone", False),
                check_only=s.get("wait_check_only", False),
            )
        elif wait_pixel and wait_color:
            wait_cond = WaitCondition(
                pixel=wait_pixel, color=wait_color,
                until_gone=s.get("wait_until_gone", False),
                check_only=s.get("wait_check_only", False),
            )
        # Nachpruefung ("hat der Klick gewirkt?") - gleiche Bauart wie wait_condition.
        verify_cond = None
        verify_point_id = s.get("verify_point_id")
        verify_pixel = s.get("verify_pixel")
        verify_color = s.get("verify_color")
        if verify_point_id is not None:
            verify_cond = WaitCondition(
                point_id=verify_point_id,
                until_gone=s.get("verify_until_gone", False),
            )
        elif verify_pixel and verify_color:
            verify_cond = WaitCondition(
                pixel=tuple(int(v) for v in verify_pixel),
                color=tuple(int(v) for v in verify_color),
                until_gone=s.get("verify_until_gone", False),
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
                point_id=s.get("else_point_id"),
                x=else_x, y=else_y,
                delay=else_delay,
                key=s.get("else_key"), name=s.get("else_name") or ""
            )
        step = SequenceStep(
            x=s.get("x", 0),
            y=s.get("y", 0),
            delay_before=float(delay_raw),
            name=s.get("name", ""),
            point_id=s.get("point_id"),
            wait_condition=wait_cond,
            verify_condition=verify_cond,
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
