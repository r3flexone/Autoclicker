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


def _defer(fn) -> None:
    """Verschiebt einen Panel-Rebuild auf den nächsten Frame.

    Wird ein Combo-/Checkbox-Callback genutzt, der das Panel neu baut, löscht der
    Rebuild das gerade laufende Widget mitten im eigenen Callback (DPG-undefiniert,
    Crash). Über set_frame_callback läuft der Rebuild erst nachdem der Callback
    fertig ist.
    """
    dpg.set_frame_callback(dpg.get_frame_count() + 1, callback=lambda: fn())


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


def _point_label(p) -> str:
    return f"#{p.id} {p.name or ''} ({p.x},{p.y})".strip()


def _point_items(points) -> list[str]:
    """Hilfsliste für Punkt-Picker-Combos."""
    return ["(manuell)"] + [_point_label(p) for p in (points or [])]


def _current_point_label(points, x, y) -> str:
    """Findet den Punkt-Eintrag dessen Koordinaten zu (x,y) passen, sonst '(manuell)'."""
    for p in (points or []):
        if p.x == x and p.y == y:
            return _point_label(p)
    return "(manuell)"


def _apply_point(points, label: str, set_xy):
    """Überträgt ID + Koordinaten + Name + Farbe via set_xy(id, x, y, name, color).

    Die ID muss mit: sie ist das, was gespeichert wird. Ohne sie hinterließ der
    Punkt-Picker eine Koordinaten-Kopie, die beim Speichern verlorenging.
    """
    if label == "(manuell)" or not points:
        return
    for p in points:
        if _point_label(p) == label:
            set_xy(p.id, p.x, p.y, p.name or "", p.color)
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
        _defer(on_structure)  # Rebuild würde dieses Combo im eigenen Callback löschen

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
        dpg.add_input_text(label="Name", tag="np_name", default_value=step.name or "",
                           parent=parent, width=-130, callback=_on_name)

        def _on_delay(s, a, u):
            step.delay_before = max(0.0, float(a))
            on_changed()
        dpg.add_input_float(label="Delay (s)", default_value=float(step.delay_before or 0.0),
                            parent=parent, width=-130, min_value=0.0, step=0.1,
                            format="%.2f", callback=_on_delay)

        def _on_delay_max(s, a, u):
            v = float(a)
            step.delay_max = v if v > 0 else None
            on_changed()
        dpg.add_input_float(label="Delay max (0=fest)",
                            default_value=float(step.delay_max or 0.0),
                            parent=parent, width=-130, min_value=0.0, step=0.1,
                            format="%.2f", callback=_on_delay_max)
        dpg.add_separator(parent=parent)

    # --- Typ-spezifische Felder ---------------------------------------------
    if cur_type in (BLOCK_CLICK, BLOCK_WAIT_CLICK):
        _build_position(parent, step, points, on_changed, on_structure)

    if cur_type == BLOCK_WAIT_CLICK:
        _build_wait_condition(parent, step, on_changed)

    if cur_type == BLOCK_WAIT:
        _build_wait_toggle(parent, step, points, on_changed, on_structure)

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


def _point_setter(step, on_changed):
    """Erzeugt die set_xy-Funktion für einen Punkt-Picker.

    Setzt Position, Name und recorded_color des Schritts – und falls der Schritt
    einen Farb-Trigger hat (FARBE+KLICK oder WARTEN-mit-Trigger), wird dessen
    Pixel + Farbe gleich mitgeführt, damit man die Farbe nicht extra abgreifen
    muss. Alle Felder werden in-place aktualisiert (kein Panel-Rebuild – ein
    Rebuild würde das auslösende Combo mitten im eigenen Callback löschen).
    """
    def _set(point_id, x, y, name, color):
        step.point_id = point_id
        step.x = x
        step.y = y
        # Prüft der Schritt seine eigene Stelle, zeigt der Trigger auf denselben Punkt.
        if step.wait_condition is not None:
            step.wait_condition.point_id = point_id
        if name:
            step.name = name
            if dpg.does_item_exist("np_name"):
                dpg.set_value("np_name", name)
        if color:
            step.recorded_color = tuple(color)
        if dpg.does_item_exist("np_pos_x"):
            dpg.set_value("np_pos_x", x)
        if dpg.does_item_exist("np_pos_y"):
            dpg.set_value("np_pos_y", y)
        if step.wait_condition is not None:
            step.wait_condition.pixel = (x, y)
            if color:
                step.wait_condition.color = tuple(color)
            if dpg.does_item_exist("np_wc_px"):
                dpg.set_value("np_wc_px", x)
                dpg.set_value("np_wc_py", y)
            if color and dpg.does_item_exist("np_wc_color"):
                dpg.set_value("np_wc_color", tuple(color) + (255,))
        on_changed()
    return _set


def _point_combo(parent, step, points, on_changed, label="Punkt"):
    """Punkt-Picker-Combo: wählt einen ClickPoint und überträgt Position +
    Farbe in den Schritt (in-place, siehe _point_setter)."""
    if not points:
        return

    def _on_pt(s, a, u):
        _apply_point(points, a, _point_setter(step, on_changed))
    dpg.add_combo(items=_point_items(points),
                  default_value=_current_point_label(points, step.x, step.y),
                  label=label, parent=parent, width=-130, callback=_on_pt)


def _build_position(parent, step, points, on_changed, on_structure=None):
    dpg.add_text("Klick-Position", parent=parent, color=(120, 180, 255))
    _point_combo(parent, step, points, on_changed)

    # Die Zahlenfelder verschieben den PUNKT, nicht den Schritt. Nur so ueberlebt die
    # Eingabe das Speichern - die Sequenz haelt keine Koordinaten mehr. Teilen sich
    # mehrere Schritte den Punkt, wandern sie mit; das ist gewollt und im Punkte-Menue
    # nachvollziehbar. Hat der Block noch keinen Punkt (Blanko), entsteht einer.
    def _setze(achse, wert):
        setattr(step, achse, int(wert))
        punkt = _punkt_von(points, step.point_id)
        if punkt is None:
            punkt = _neuer_palette_punkt(points, step)
            step.point_id = punkt.id
        setattr(punkt, achse, int(wert))
        if step.wait_condition is not None and step.wait_condition.point_id == punkt.id:
            step.wait_condition.pixel = (step.x, step.y)
        on_changed()

    dpg.add_input_int(label="X", tag="np_pos_x", default_value=int(step.x or 0),
                      parent=parent, width=-130,
                      callback=lambda s, a, u: _setze("x", a))
    dpg.add_input_int(label="Y", tag="np_pos_y", default_value=int(step.y or 0),
                      parent=parent, width=-130,
                      callback=lambda s, a, u: _setze("y", a))
    dpg.add_text("Verschiebt den Punkt - alle Schritte darauf ziehen mit.",
                 parent=parent, color=(150, 150, 150))


def _punkt_von(points, point_id):
    return next((p for p in points if p.id == point_id), None) if point_id else None


def _neuer_palette_punkt(points, step):
    """Legt einen Palette-Punkt fuer einen Block an, der noch keinen hat."""
    from .model import PalettePoint
    neu = PalettePoint(id=max([p.id for p in points], default=0) + 1,
                       x=int(step.x or 0), y=int(step.y or 0),
                       name=step.name or "Node-Editor",
                       color=tuple(step.recorded_color) if step.recorded_color else None,
                       source="Node-Editor")
    points.append(neu)
    return neu


def _default_color(step) -> tuple:
    """Aufgenommene Farbe des Schritts, sonst schwarz als Fallback."""
    return tuple(step.recorded_color) if step.recorded_color else (0, 0, 0)


def _build_wait_toggle(parent, step, points, on_changed, on_structure):
    """WARTEN-Block: optionalen Farb-Trigger ein-/ausschalten."""
    def _on_toggle(s, a, u):
        if a:
            step.wait_condition = WaitCondition(pixel=(step.x or 0, step.y or 0),
                                                color=_default_color(step))
        else:
            step.wait_condition = None
        _defer(on_structure)  # Rebuild würde diese Checkbox im eigenen Callback löschen
    dpg.add_checkbox(label="Farb-Trigger verwenden",
                     default_value=step.wait_condition is not None,
                     parent=parent, callback=_on_toggle)
    if step.wait_condition:
        # Punkt-Picker zuerst – beim Auswählen werden Pixel + Farbe des Punkts
        # in den Trigger übernommen (genau für aufgenommene Punkte gedacht, bei
        # denen Position + Farbe abgelegt sind, ohne dass geklickt werden soll).
        _point_combo(parent, step, points, on_changed)
        _build_wait_condition(parent, step, on_changed)
    else:
        dpg.add_text("Wartet nur die Delay-Zeit.", parent=parent, color=(150, 150, 150))


def _build_wait_condition(parent, step, on_changed):
    if step.wait_condition is None:
        step.wait_condition = WaitCondition(pixel=(step.x or 0, step.y or 0),
                                            color=_default_color(step))
    wc = step.wait_condition
    dpg.add_text("Farb-Trigger (warte auf Farbe)", parent=parent, color=(120, 180, 255))

    def _on_px(s, a, u):
        step.wait_condition.pixel = (int(a), step.wait_condition.pixel[1])
        on_changed()

    def _on_py(s, a, u):
        step.wait_condition.pixel = (step.wait_condition.pixel[0], int(a))
        on_changed()
    dpg.add_input_int(label="Pixel X", tag="np_wc_px", default_value=int(wc.pixel[0]),
                      parent=parent, width=-130, callback=_on_px)
    dpg.add_input_int(label="Pixel Y", tag="np_wc_py", default_value=int(wc.pixel[1]),
                      parent=parent, width=-130, callback=_on_py)

    def _on_color(s, a, u):
        step.wait_condition.color = _clamp_color(a)
        on_changed()
    dpg.add_color_edit(label="Farbe", tag="np_wc_color", default_value=tuple(wc.color) + (255,),
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
                       parent=parent, width=-130, hint="z.B. enter, space, f1",
                       callback=_on_key)


def _build_named_scan(parent, step, attr, label, on_changed):
    dpg.add_text(label, parent=parent, color=(120, 180, 255))

    def _on_name(s, a, u):
        setattr(step, attr, a)
        on_changed()
    dpg.add_input_text(label="Name", default_value=getattr(step, attr) or "",
                       parent=parent, width=-130, callback=_on_name)
    dpg.add_text("(Name eines im Item-/Boss-/Icon-Editor angelegten Scans)",
                 parent=parent, color=(150, 150, 150), wrap=270)


def _build_scan_mode(parent, step, on_changed):
    def _on_mode(s, a, u):
        step.item_scan_mode = a
        on_changed()
    dpg.add_combo(items=_SCAN_MODES, label="Modus",
                  default_value=step.item_scan_mode or SCAN_MODE_ALL,
                  parent=parent, width=-130, callback=_on_mode)


def _build_screenshot(parent, step, on_changed, on_structure):
    dpg.add_text("Screenshot", parent=parent, color=(120, 180, 255))
    has_region = step.screenshot_region is not None

    def _on_toggle(s, a, u):
        if a:
            step.screenshot_region = step.screenshot_region or (0, 0, 100, 100)
        else:
            step.screenshot_region = None
        _defer(on_structure)  # Rebuild würde diese Checkbox im eigenen Callback löschen
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
                              width=-130, callback=_mk(i))


def _build_else(parent, step, points, on_changed, on_structure):
    dpg.add_text("ELSE / Fallback (wenn Trigger fehlschlägt)", parent=parent,
                 color=(230, 180, 90))
    cur = step.else_config.action if step.else_config else "(keine)"

    def _on_action(s, a, u):
        if a == "(keine)":
            step.else_config = None
        else:
            ensure_else(step, a)
        _defer(on_structure)  # Rebuild würde dieses Combo im eigenen Callback löschen
    dpg.add_combo(items=_ELSE_ACTIONS, default_value=cur, parent=parent,
                  width=-1, callback=_on_action)

    ec = step.else_config
    if not ec:
        return
    if ec.action == ELSE_CLICK:
        ex_tag, ey_tag, en_tag = "np_else_x", "np_else_y", "np_else_name"
        if points:
            # In-place setzen (kein Panel-Rebuild im Combo-Callback, sonst bricht
            # die Auswahl ab – siehe _build_position).
            def _on_pt(s, a, u):
                def _set(x, y, name, color):
                    ec.x = x
                    ec.y = y
                    ec.name = name
                    dpg.set_value(ex_tag, x)
                    dpg.set_value(ey_tag, y)
                    dpg.set_value(en_tag, name)
                    on_changed()
                _apply_point(points, a, _set)
            dpg.add_combo(items=_point_items(points),
                          default_value=_current_point_label(points, ec.x, ec.y),
                          label="ELSE Punkt", parent=parent, width=-130, callback=_on_pt)

        def _ex(s, a, u):
            ec.x = int(a)
            on_changed()

        def _ey(s, a, u):
            ec.y = int(a)
            on_changed()
        dpg.add_input_int(label="ELSE X", tag=ex_tag, default_value=int(ec.x or 0),
                          parent=parent, width=-130, callback=_ex)
        dpg.add_input_int(label="ELSE Y", tag=ey_tag, default_value=int(ec.y or 0),
                          parent=parent, width=-130, callback=_ey)

        def _en(s, a, u):
            ec.name = a
            on_changed()
        dpg.add_input_text(label="ELSE Name (für manuelle Punkte)", tag=en_tag,
                           default_value=ec.name or "", parent=parent,
                           width=-130, callback=_en)
    elif ec.action == ELSE_KEY:
        def _ek(s, a, u):
            ec.key = a
            on_changed()
        dpg.add_input_text(label="ELSE Taste", default_value=ec.key or "",
                           parent=parent, width=-130, callback=_ek)
