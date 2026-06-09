"""
Eigenschaften-Formulare je Block-Typ (Dear PyGui).

build_properties_panel() leert den Panel-Container und baut die zum aktuellen
Block-Typ passenden Formfelder neu auf. Jedes Feld schreibt seine Änderung
direkt in das SequenceStep-Objekt zurück und ruft on_changed() (aktualisiert
das Node-Label). Strukturändernde Aktionen (Typ-Wechsel, Löschen, Verschieben)
rufen on_structure() (Canvas neu zeichnen).

Dear PyGui wird hier importiert — dieses Modul läuft nur im Editor-Subprocess.
"""

import dearpygui.dearpygui as dpg

from ...models import (
    SCAN_MODE_ALL, SCAN_MODE_BEST, SCAN_MODE_EVERY,
    ELSE_SKIP, ELSE_SKIP_CYCLE, ELSE_RESTART, ELSE_CLICK, ELSE_KEY,
    WaitCondition,
)
from .model import (
    BLOCK_LABELS, BLOCK_CLICK, BLOCK_WAIT_CLICK, BLOCK_WAIT, BLOCK_KEY,
    BLOCK_ITEM_SCAN, BLOCK_ICON_SCAN, BLOCK_BOSS_SCAN, BLOCK_BOSS_WATCHER,
    BLOCK_SCREENSHOT,
    block_type, set_block_type, ensure_else,
)

# Reihenfolge der Typen im Auswahl-Combo
_TYPE_ORDER = [
    BLOCK_CLICK, BLOCK_WAIT_CLICK, BLOCK_WAIT, BLOCK_KEY,
    BLOCK_ITEM_SCAN, BLOCK_ICON_SCAN, BLOCK_BOSS_SCAN, BLOCK_BOSS_WATCHER,
    BLOCK_SCREENSHOT,
]
_TYPE_LABEL_TO_KEY = {BLOCK_LABELS[t]: t for t in _TYPE_ORDER}

_SCAN_MODES = [SCAN_MODE_ALL, SCAN_MODE_BEST, SCAN_MODE_EVERY]
_ELSE_ACTIONS = ["(keine)", ELSE_SKIP, ELSE_SKIP_CYCLE, ELSE_RESTART, ELSE_CLICK, ELSE_KEY]


def _clamp_color(app_data) -> tuple:
    """Dear-PyGui-Farbwert (Floats 0..255 oder 0..1) → (r,g,b) ints 0..255."""
    vals = list(app_data)[:3]
    out = []
    for v in vals:
        iv = int(round(v * 255)) if v <= 1.0 else int(round(v))
        out.append(max(0, min(255, iv)))
    while len(out) < 3:
        out.append(0)
    return tuple(out)


def _point_items(points) -> list[str]:
    """Hilfsliste für Punkt-Picker-Combos."""
    items = ["(manuell)"]
    for p in (points or []):
        items.append(f"#{p.id} {p.name or ''} ({p.x},{p.y})".strip())
    return items


def _apply_point(points, label: str, set_xy):
    """Überträgt die Koordinaten des gewählten Punkts via set_xy(x, y)."""
    if label == "(manuell)" or not points:
        return
    for p in points:
        entry = f"#{p.id} {p.name or ''} ({p.x},{p.y})".strip()
        if entry == label:
            set_xy(p.x, p.y)
            return


def build_properties_panel(parent: str, step, lane, graph, points,
                           on_changed, on_structure) -> None:
    """Baut das Eigenschaften-Formular für den gewählten Schritt neu auf."""
    for child in dpg.get_item_children(parent, 1) or []:
        dpg.delete_item(child)

    if step is None:
        dpg.add_text("Kein Block ausgewählt.", parent=parent, color=(150, 150, 150))
        dpg.add_text("'Bearbeiten' klicken.", parent=parent, color=(150, 150, 150))
        return

    cur_type = block_type(step)

    # --- Typ-Auswahl --------------------------------------------------------
    dpg.add_text("Block-Typ", parent=parent, color=(120, 180, 255))

    def _on_type(sender, app_data, user_data):
        set_block_type(step, _TYPE_LABEL_TO_KEY[app_data])
        on_structure()

    dpg.add_combo(
        items=[BLOCK_LABELS[t] for t in _TYPE_ORDER],
        default_value=BLOCK_LABELS[cur_type],
        parent=parent, width=-1, callback=_on_type,
    )
    dpg.add_separator(parent=parent)

    # --- Gemeinsame Felder: Name + Delay ------------------------------------
    if cur_type != BLOCK_SCREENSHOT:
        def _on_name(s, a, u):
            step.name = a
            on_changed()
        dpg.add_input_text(label="Name", default_value=step.name or "",
                           parent=parent, width=-80, callback=_on_name)

        def _on_delay(s, a, u):
            step.delay_before = max(0.0, float(a))
            on_changed()
        dpg.add_input_float(label="Delay (s)", default_value=float(step.delay_before or 0.0),
                            parent=parent, width=-80, min_value=0.0, step=0.1,
                            format="%.2f", callback=_on_delay)

        def _on_delay_max(s, a, u):
            v = float(a)
            step.delay_max = v if v > 0 else None
            on_changed()
        dpg.add_input_float(label="Delay max (0=fest)",
                            default_value=float(step.delay_max or 0.0),
                            parent=parent, width=-80, min_value=0.0, step=0.1,
                            format="%.2f", callback=_on_delay_max)
        dpg.add_separator(parent=parent)

    # --- Typ-spezifische Felder ---------------------------------------------
    if cur_type in (BLOCK_CLICK, BLOCK_WAIT_CLICK):
        _build_position(parent, step, points, on_changed)

    if cur_type == BLOCK_WAIT_CLICK:
        _build_wait_condition(parent, step, on_changed)

    if cur_type == BLOCK_WAIT:
        _build_wait_toggle(parent, step, on_changed, on_structure)

    if cur_type == BLOCK_KEY:
        _build_key(parent, step, on_changed)
    if cur_type == BLOCK_ITEM_SCAN:
        _build_named_scan(parent, step, "item_scan", "Item-Scan Name", on_changed)
        _build_scan_mode(parent, step, on_changed)
    if cur_type == BLOCK_ICON_SCAN:
        _build_named_scan(parent, step, "icon_scan", "Icon-Scan Name", on_changed)
    if cur_type == BLOCK_BOSS_SCAN:
        _build_named_scan(parent, step, "boss_scan", "Boss-Scan Name", on_changed)
    if cur_type == BLOCK_BOSS_WATCHER:
        _build_named_scan(parent, step, "boss_watcher", "Boss-Watcher Name", on_changed)
    if cur_type == BLOCK_SCREENSHOT:
        _build_screenshot(parent, step, on_changed, on_structure)

    # --- ELSE / Fallback ----------------------------------------------------
    dpg.add_separator(parent=parent)
    _build_else(parent, step, points, on_changed, on_structure)


def _build_position(parent, step, points, on_changed):
    dpg.add_text("Klick-Position", parent=parent, color=(120, 180, 255))

    if points:
        def _on_pt(s, a, u):
            def _set(x, y):
                step.x = x
                step.y = y
                on_changed()
            _apply_point(points, a, _set)
        dpg.add_combo(items=_point_items(points), default_value="(manuell)",
                      label="Punkt", parent=parent, width=-80, callback=_on_pt)

    def _on_x(s, a, u):
        step.x = int(a)
        on_changed()

    def _on_y(s, a, u):
        step.y = int(a)
        on_changed()
    dpg.add_input_int(label="X", default_value=int(step.x or 0), parent=parent,
                      width=-80, callback=_on_x)
    dpg.add_input_int(label="Y", default_value=int(step.y or 0), parent=parent,
                      width=-80, callback=_on_y)


def _build_wait_toggle(parent, step, on_changed, on_structure):
    """WARTEN-Block: optionalen Farb-Trigger ein-/ausschalten."""
    def _on_toggle(s, a, u):
        if a:
            step.wait_condition = WaitCondition(pixel=(step.x or 0, step.y or 0),
                                                color=(0, 0, 0))
        else:
            step.wait_condition = None
        on_structure()
    dpg.add_checkbox(label="Farb-Trigger verwenden",
                     default_value=step.wait_condition is not None,
                     parent=parent, callback=_on_toggle)
    if step.wait_condition:
        _build_wait_condition(parent, step, on_changed)
    else:
        dpg.add_text("Wartet nur die Delay-Zeit.", parent=parent, color=(150, 150, 150))


def _build_wait_condition(parent, step, on_changed):
    if step.wait_condition is None:
        step.wait_condition = WaitCondition(pixel=(step.x or 0, step.y or 0), color=(0, 0, 0))
    wc = step.wait_condition
    dpg.add_text("Farb-Trigger (warte auf Farbe)", parent=parent, color=(120, 180, 255))

    def _on_px(s, a, u):
        step.wait_condition.pixel = (int(a), step.wait_condition.pixel[1])
        on_changed()

    def _on_py(s, a, u):
        step.wait_condition.pixel = (step.wait_condition.pixel[0], int(a))
        on_changed()
    dpg.add_input_int(label="Pixel X", default_value=int(wc.pixel[0]), parent=parent,
                      width=-80, callback=_on_px)
    dpg.add_input_int(label="Pixel Y", default_value=int(wc.pixel[1]), parent=parent,
                      width=-80, callback=_on_py)

    def _on_color(s, a, u):
        step.wait_condition.color = _clamp_color(a)
        on_changed()
    dpg.add_color_edit(label="Farbe", default_value=tuple(wc.color) + (255,),
                       parent=parent, no_alpha=True, callback=_on_color)

    def _on_gone(s, a, u):
        step.wait_condition.until_gone = bool(a)
        on_changed()
    dpg.add_checkbox(label="bis Farbe WEG ist", default_value=wc.until_gone,
                     parent=parent, callback=_on_gone)

    if step.recorded_color:
        dpg.add_text(f"Aufgenommene Farbe: RGB{step.recorded_color}",
                     parent=parent, color=(150, 150, 150))

        def _use_recorded(s, a, u):
            step.wait_condition.color = tuple(step.recorded_color)
            on_changed()
        dpg.add_button(label="Aufgenommene Farbe übernehmen", parent=parent,
                       callback=_use_recorded)


def _build_key(parent, step, on_changed):
    dpg.add_text("Tastendruck", parent=parent, color=(120, 180, 255))

    def _on_key(s, a, u):
        step.key_press = a
        on_changed()
    dpg.add_input_text(label="Taste", default_value=step.key_press or "",
                       parent=parent, width=-80, hint="z.B. enter, space, f1",
                       callback=_on_key)


def _build_named_scan(parent, step, attr, label, on_changed):
    dpg.add_text(label, parent=parent, color=(120, 180, 255))

    def _on_name(s, a, u):
        setattr(step, attr, a)
        on_changed()
    dpg.add_input_text(label="Name", default_value=getattr(step, attr) or "",
                       parent=parent, width=-80, callback=_on_name)
    dpg.add_text("(Name eines im Item-/Boss-/Icon-Editor angelegten Scans)",
                 parent=parent, color=(150, 150, 150), wrap=270)


def _build_scan_mode(parent, step, on_changed):
    def _on_mode(s, a, u):
        step.item_scan_mode = a
        on_changed()
    dpg.add_combo(items=_SCAN_MODES, label="Modus",
                  default_value=step.item_scan_mode or SCAN_MODE_ALL,
                  parent=parent, width=-80, callback=_on_mode)


def _build_screenshot(parent, step, on_changed, on_structure):
    dpg.add_text("Screenshot", parent=parent, color=(120, 180, 255))
    has_region = step.screenshot_region is not None

    def _on_toggle(s, a, u):
        if a:
            step.screenshot_region = step.screenshot_region or (0, 0, 100, 100)
        else:
            step.screenshot_region = None
        on_structure()
    dpg.add_checkbox(label="Bereich statt Vollbild", default_value=has_region,
                     parent=parent, callback=_on_toggle)
    if has_region:
        r = list(step.screenshot_region)

        def _mk(idx):
            def _cb(s, a, u):
                rr = list(step.screenshot_region)
                rr[idx] = int(a)
                step.screenshot_region = tuple(rr)
                on_changed()
            return _cb
        for i, lbl in enumerate(("X1", "Y1", "X2", "Y2")):
            dpg.add_input_int(label=lbl, default_value=int(r[i]), parent=parent,
                              width=-80, callback=_mk(i))


def _build_else(parent, step, points, on_changed, on_structure):
    dpg.add_text("ELSE / Fallback (wenn Trigger fehlschlägt)", parent=parent,
                 color=(220, 120, 120))
    cur = step.else_config.action if step.else_config else "(keine)"

    def _on_action(s, a, u):
        if a == "(keine)":
            step.else_config = None
        else:
            ensure_else(step, a)
        on_structure()
    dpg.add_combo(items=_ELSE_ACTIONS, default_value=cur, parent=parent,
                  width=-1, callback=_on_action)

    ec = step.else_config
    if not ec:
        return
    if ec.action == ELSE_CLICK:
        if points:
            def _on_pt(s, a, u):
                def _set(x, y):
                    ec.x = x
                    ec.y = y
                    on_changed()
                _apply_point(points, a, _set)
            dpg.add_combo(items=_point_items(points), default_value="(manuell)",
                          label="ELSE Punkt", parent=parent, width=-80, callback=_on_pt)

        def _ex(s, a, u):
            ec.x = int(a)
            on_changed()

        def _ey(s, a, u):
            ec.y = int(a)
            on_changed()
        dpg.add_input_int(label="ELSE X", default_value=int(ec.x or 0), parent=parent,
                          width=-80, callback=_ex)
        dpg.add_input_int(label="ELSE Y", default_value=int(ec.y or 0), parent=parent,
                          width=-80, callback=_ey)

        def _en(s, a, u):
            ec.name = a
            on_changed()
        dpg.add_input_text(label="ELSE Name", default_value=ec.name or "",
                           parent=parent, width=-80, callback=_en)
    elif ec.action == ELSE_KEY:
        def _ek(s, a, u):
            ec.key = a
            on_changed()
        dpg.add_input_text(label="ELSE Taste", default_value=ec.key or "",
                           parent=parent, width=-80, callback=_ek)
