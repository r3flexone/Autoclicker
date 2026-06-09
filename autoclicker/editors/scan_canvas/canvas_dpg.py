"""
Dear-PyGui-Canvas fürs Scan-Studio (Fundament: Slots auf dem Screenshot).

Zeigt einen eingefrorenen Vollbild-Screenshot als Textur. Im Modus "Slot" zieht
man Rechtecke auf → werden zu ItemSlots (scan_region in Bildschirm-Koordinaten).
Modus "Klickpunkt" setzt die click_pos des gewählten Slots, Modus "Farbe" pickt
die slot_color aus dem Screenshot. Speichern schreibt slots/slots.json — dieselbe
Datei, die der Konsolen-Slot-Editor nutzt.

Läuft nur im Subprocess (Dear PyGui import).
"""

import dearpygui.dearpygui as dpg

from ...config import DEFAULT_MIN_CONFIDENCE
from ...models import ItemSlot, ItemProfile, ItemScanConfig
from ...imaging import OPENCV_AVAILABLE
from ...persistence import (
    save_item_scan, ensure_item_scans_dir,
    list_available_item_scans, load_item_scan_file,
)
from ...editors.item_editor.markers import _collect_markers_silent, _find_matching_existing_item
from .texture import ViewTransform, pil_to_texture, fit_scale
from .model import (
    load_slots, save_slots, next_slot_name, normalize_region,
    load_items, save_items, next_item_name, existing_categories,
    crop_region, save_template,
)

# Feste Tags
_DRAWLIST = "ac_ss_drawlist"
_OVERLAY = "ac_ss_overlay"
_TEX = "ac_ss_texture"
_SLOT_LIST = "ac_ss_slotlist"
_ITEM_LIST = "ac_ss_itemlist"
_PROPS = "ac_ss_props"
_SCAN = "ac_ss_scan"
_SCAN_PICK = "ac_ss_scanpick"
_STATUS = "ac_ss_status"

# Modi
MODE_SLOT = "slot"
MODE_CLICK = "click"
MODE_COLOR = "color"

# Auswahl-Art
KIND_SLOT = "slot"
KIND_ITEM = "item"

_MIN_DRAW_PX = 4  # kleinste sinnvolle Rechteck-Kantenlänge in Anzeige-Pixeln


class ScanStudioApp:
    """Screenshot-Canvas zum Anlegen/Bearbeiten von Slots."""

    def __init__(self, image, virtual_left: int, virtual_top: int,
                 slots_file: str, items_file: str | None = None,
                 max_canvas=(1100, 760)):
        self.image = image
        self.slots: dict[str, ItemSlot] = load_slots(slots_file)
        self.slots_file = slots_file
        # items_file optional ableiten, falls nicht übergeben (items/items.json)
        if items_file is None:
            from ...persistence.paths import ITEMS_FILE
            items_file = ITEMS_FILE
        self.items: dict[str, ItemProfile] = load_items(items_file)
        self.items_file = items_file
        self.selected: str | None = None
        self.selected_kind: str = KIND_SLOT
        # Scan-Zusammenbau: welche Slots/Items sind angehakt + Name/Toleranz
        self._slot_checked: dict[str, bool] = {}
        self._item_checked: dict[str, bool] = {}
        self._scan_name: str = ""
        self._scan_tol: int = 40
        self.mode = MODE_SLOT
        self._drawing = False
        self._draw_start = (0.0, 0.0)
        self._draw_cur = (0.0, 0.0)

        scale = fit_scale(image.width, image.height, max_canvas[0], max_canvas[1])
        self.transform = ViewTransform(
            scale=scale, virtual_left=virtual_left, virtual_top=virtual_top,
            img_w=image.width, img_h=image.height,
        )

    # ---------------------------------------------------------------- Setup
    def run(self) -> None:
        dpg.create_context()
        self._register_texture()
        self._build_ui()
        self._install_handlers()
        dpg.create_viewport(title="Scan-Studio – Slots", width=1500, height=860)
        dpg.setup_dearpygui()
        dpg.show_viewport()
        dpg.set_primary_window("ac_ss_root", True)
        self.redraw_overlay()
        self.refresh_slot_list()
        self.refresh_item_list()
        self.refresh_scan_panel()
        self.refresh_properties()
        dpg.start_dearpygui()
        dpg.destroy_context()

    def _register_texture(self) -> None:
        tex = pil_to_texture(self.image)
        if tex is None:
            raise RuntimeError("Textur-Konvertierung fehlgeschlagen (numpy fehlt?)")
        w, h, data = tex
        with dpg.texture_registry():
            dpg.add_raw_texture(w, h, data, format=dpg.mvFormat_Float_rgba, tag=_TEX)

    def _build_ui(self) -> None:
        disp_w, disp_h = self.transform.display_size
        with dpg.window(tag="ac_ss_root"):
            with dpg.group(horizontal=True):
                # linke Spalte
                with dpg.child_window(width=230):
                    dpg.add_button(label="Speichern", width=-1, callback=self._on_save)
                    dpg.add_text("", tag=_STATUS, color=(110, 200, 110))
                    dpg.add_separator()
                    dpg.add_text("Werkzeug", color=(120, 180, 255))
                    dpg.add_radio_button(
                        items=["Slot zeichnen", "Klickpunkt setzen", "Farbe picken"],
                        default_value="Slot zeichnen", callback=self._on_mode,
                        tag="ac_ss_mode",
                    )
                    dpg.add_separator()
                    dpg.add_text("Slots", color=(120, 180, 255))
                    dpg.add_text("Im Modus 'Slot zeichnen'\nRechteck aufziehen.",
                                 color=(150, 150, 150))
                    dpg.add_group(tag=_SLOT_LIST)
                    dpg.add_separator()
                    with dpg.group(horizontal=True):
                        dpg.add_text("Items", color=(120, 180, 255))
                        dpg.add_button(label="Autoscan", callback=self._on_autoscan)
                    dpg.add_text("'Autoscan' lernt aus allen\nSlots (Duplikate werden\nübersprungen).",
                                 color=(150, 150, 150))
                    dpg.add_group(tag=_ITEM_LIST)
                # Mitte: Canvas
                with dpg.child_window(border=False):
                    with dpg.drawlist(width=disp_w, height=disp_h, tag=_DRAWLIST):
                        dpg.draw_image(_TEX, (0, 0), (disp_w, disp_h))
                        dpg.add_draw_layer(tag=_OVERLAY)
                # rechts: Eigenschaften + Scan-Zusammenbau
                with dpg.child_window(width=320):
                    with dpg.tab_bar():
                        with dpg.tab(label="Eigenschaften"):
                            dpg.add_group(tag=_PROPS)
                        with dpg.tab(label="Scan bauen"):
                            dpg.add_group(tag=_SCAN)

    def _install_handlers(self) -> None:
        with dpg.handler_registry():
            dpg.add_mouse_down_handler(button=dpg.mvMouseButton_Left, callback=self._on_mouse_down)
            dpg.add_mouse_drag_handler(button=dpg.mvMouseButton_Left, callback=self._on_mouse_drag)
            dpg.add_mouse_release_handler(button=dpg.mvMouseButton_Left, callback=self._on_mouse_release)

    # --------------------------------------------------------- Maus-Handler
    def _canvas_pos(self) -> tuple[float, float] | None:
        """Mausposition im Drawlist-Koordinatensystem, oder None wenn außerhalb."""
        if not dpg.is_item_hovered(_DRAWLIST):
            return None
        return tuple(dpg.get_drawing_mouse_pos())

    def _on_mouse_down(self, sender, app_data):
        pos = self._canvas_pos()
        if pos is None:
            return
        if self.mode == MODE_SLOT:
            self._drawing = True
            self._draw_start = pos
            self._draw_cur = pos
            self.redraw_overlay()

    def _on_mouse_drag(self, sender, app_data):
        if self._drawing:
            pos = tuple(dpg.get_drawing_mouse_pos())
            self._draw_cur = pos
            self.redraw_overlay()

    def _on_mouse_release(self, sender, app_data):
        pos = self._canvas_pos()
        if self.mode == MODE_SLOT and self._drawing:
            self._drawing = False
            x0, y0 = self._draw_start
            x1, y1 = self._draw_cur
            self._finish_draw(x0, y0, x1, y1)
        elif pos is not None and self.mode in (MODE_CLICK, MODE_COLOR):
            self._handle_point(pos[0], pos[1])

    # --------------------------------------------------------- Kern-Aktionen
    def _finish_draw(self, dx0, dy0, dx1, dy1) -> None:
        """Erzeugt aus einem aufgezogenen Rechteck einen neuen Slot."""
        if abs(dx1 - dx0) < _MIN_DRAW_PX or abs(dy1 - dy0) < _MIN_DRAW_PX:
            self.redraw_overlay()
            return
        sx0, sy0 = self.transform.draw_to_screen(dx0, dy0)
        sx1, sy1 = self.transform.draw_to_screen(dx1, dy1)
        region = normalize_region(sx0, sy0, sx1, sy1)
        click = ((region[0] + region[2]) // 2, (region[1] + region[3]) // 2)
        name = next_slot_name(self.slots)
        self.slots[name] = ItemSlot(name=name, scan_region=region, click_pos=click,
                                    slot_color=None)
        self.selected = name
        self.selected_kind = KIND_SLOT
        self.redraw_overlay()
        self.refresh_slot_list()
        self.refresh_item_list()
        self.refresh_scan_panel()
        self.refresh_properties()
        self._set_status(f"Slot '{name}' angelegt.")

    def _handle_point(self, dx, dy) -> None:
        """Klick im Modus Klickpunkt/Farbe auf den gewählten Slot anwenden."""
        if self.selected_kind != KIND_SLOT or self.selected not in self.slots:
            self._set_status("Erst einen Slot wählen.", color=(220, 180, 90))
            return
        slot = self.slots[self.selected]
        if self.mode == MODE_CLICK:
            slot.click_pos = self.transform.draw_to_screen(dx, dy)
            self._set_status(f"Klickpunkt: {slot.click_pos}")
        elif self.mode == MODE_COLOR:
            ix, iy = self.transform.draw_to_image(dx, dy)
            px = self.image.convert("RGB").getpixel((ix, iy))
            slot.slot_color = (int(px[0]), int(px[1]), int(px[2]))
            self._set_status(f"Farbe: RGB{slot.slot_color}")
        self.redraw_overlay()
        self.refresh_properties()

    # --------------------------------------------------------------- Render
    def redraw_overlay(self) -> None:
        if not dpg.does_item_exist(_OVERLAY):
            return
        for child in dpg.get_item_children(_OVERLAY, 2) or []:
            dpg.delete_item(child)
        t = self.transform
        for name, slot in self.slots.items():
            x1, y1, x2, y2 = t.screen_region_to_draw(slot.scan_region)
            sel = (name == self.selected)
            color = (90, 200, 255) if sel else (70, 140, 220)
            dpg.draw_rectangle((x1, y1), (x2, y2), color=color,
                               thickness=2 if sel else 1, parent=_OVERLAY)
            dpg.draw_text((x1 + 3, y1 + 2), name, size=14, color=color, parent=_OVERLAY)
            # Klickpunkt markieren
            cx, cy = t.screen_to_draw(*slot.click_pos)
            dpg.draw_circle((cx, cy), 4, color=(255, 200, 60),
                            fill=(255, 200, 60), parent=_OVERLAY)
        # Vorschau-Rechteck beim Zeichnen
        if self._drawing:
            dpg.draw_rectangle(self._draw_start, self._draw_cur, color=(120, 255, 120),
                               thickness=1, parent=_OVERLAY)

    def refresh_slot_list(self) -> None:
        if not dpg.does_item_exist(_SLOT_LIST):
            return
        for child in dpg.get_item_children(_SLOT_LIST, 1) or []:
            dpg.delete_item(child)
        if not self.slots:
            dpg.add_text("Noch keine Slots.", parent=_SLOT_LIST, color=(150, 150, 150))
            return
        for name in self.slots:
            sel = (self.selected_kind == KIND_SLOT and name == self.selected)
            label = ("» " if sel else "") + name
            dpg.add_button(label=label, width=-1, parent=_SLOT_LIST,
                           user_data=name, callback=self._on_select_slot)

    def refresh_item_list(self) -> None:
        if not dpg.does_item_exist(_ITEM_LIST):
            return
        for child in dpg.get_item_children(_ITEM_LIST, 1) or []:
            dpg.delete_item(child)
        if not self.items:
            dpg.add_text("Noch keine Items.", parent=_ITEM_LIST, color=(150, 150, 150))
            return
        for name, item in self.items.items():
            sel = (self.selected_kind == KIND_ITEM and name == self.selected)
            cat = f" [{item.category}]" if item.category else ""
            label = ("» " if sel else "") + f"P{item.priority} {name}{cat}"
            dpg.add_button(label=label, width=-1, parent=_ITEM_LIST,
                           user_data=name, callback=self._on_select_item)

    def refresh_scan_panel(self) -> None:
        """Baut den 'Scan bauen'-Tab neu auf (Slots/Items anhaken → ItemScanConfig)."""
        if not dpg.does_item_exist(_SCAN):
            return
        for child in dpg.get_item_children(_SCAN, 1) or []:
            dpg.delete_item(child)

        # bestehenden Scan laden (vorbefüllen)
        scan_names = [n for n, _ in list_available_item_scans()]
        if scan_names:
            with dpg.group(horizontal=True, parent=_SCAN):
                dpg.add_combo(items=scan_names, width=-60, tag=_SCAN_PICK,
                              default_value=scan_names[0])
                dpg.add_button(label="Laden", callback=self._on_load_scan)
            dpg.add_separator(parent=_SCAN)

        def _on_name(s, a, u):
            self._scan_name = a.strip()
        dpg.add_input_text(label="Scan-Name", default_value=self._scan_name,
                           parent=_SCAN, width=-80, callback=_on_name)

        def _on_tol(s, a, u):
            self._scan_tol = max(1, min(100, int(a)))
        dpg.add_input_int(label="Farbtoleranz", default_value=self._scan_tol,
                          parent=_SCAN, width=-80, min_value=1, max_value=100,
                          callback=_on_tol)

        dpg.add_separator(parent=_SCAN)
        dpg.add_text(f"Slots im Scan ({len(self.slots)})", parent=_SCAN, color=(120, 180, 255))
        for name in self.slots:
            checked = self._slot_checked.get(name, True)
            dpg.add_checkbox(label=name, default_value=checked, parent=_SCAN,
                             user_data=("slot", name), callback=self._on_scan_check)

        dpg.add_text(f"Items im Scan ({len(self.items)})", parent=_SCAN, color=(120, 180, 255))
        for name, item in self.items.items():
            checked = self._item_checked.get(name, True)
            cat = f" [{item.category}]" if item.category else ""
            dpg.add_checkbox(label=f"P{item.priority} {name}{cat}", default_value=checked,
                             parent=_SCAN, user_data=("item", name), callback=self._on_scan_check)

        dpg.add_separator(parent=_SCAN)
        dpg.add_button(label="Scan speichern", width=-1, parent=_SCAN,
                       callback=self._on_save_scan)

    def _on_scan_check(self, sender, app_data, user_data):
        kind, name = user_data
        if kind == "slot":
            self._slot_checked[name] = bool(app_data)
        else:
            self._item_checked[name] = bool(app_data)

    def _on_load_scan(self, *_):
        if not dpg.does_item_exist(_SCAN_PICK):
            return
        name = dpg.get_value(_SCAN_PICK)
        path = next((p for n, p in list_available_item_scans() if n == name), None)
        cfg = load_item_scan_file(path) if path else None
        if not cfg:
            self._set_status(f"Scan '{name}' nicht ladbar.", color=(220, 90, 90))
            return
        self._scan_name = cfg.name
        self._scan_tol = cfg.color_tolerance
        scan_slot_names = {s.name for s in cfg.slots}
        scan_item_names = {i.name for i in cfg.items}
        self._slot_checked = {n: (n in scan_slot_names) for n in self.slots}
        self._item_checked = {n: (n in scan_item_names) for n in self.items}
        self.refresh_scan_panel()
        self._set_status(f"Scan '{name}' geladen.")

    def _on_save_scan(self, *_):
        if not self._scan_name:
            self._set_status("Bitte Scan-Namen eingeben.", color=(220, 180, 90))
            return
        slots = [self.slots[n] for n in self.slots if self._slot_checked.get(n, True)]
        items = [self.items[n] for n in self.items if self._item_checked.get(n, True)]
        if not slots:
            self._set_status("Mindestens 1 Slot anhaken.", color=(220, 180, 90))
            return
        ensure_item_scans_dir()
        cfg = ItemScanConfig(name=self._scan_name, slots=slots, items=items,
                             color_tolerance=self._scan_tol)
        save_item_scan(cfg)
        self._set_status(f"Scan '{self._scan_name}' gespeichert "
                         f"({len(slots)} Slots, {len(items)} Items).")
        self.refresh_scan_panel()

    def refresh_properties(self) -> None:
        if not dpg.does_item_exist(_PROPS):
            return
        for child in dpg.get_item_children(_PROPS, 1) or []:
            dpg.delete_item(child)
        if self.selected_kind == KIND_ITEM:
            self._props_item()
        else:
            self._props_slot()

    def _props_slot(self) -> None:
        if not self.selected or self.selected not in self.slots:
            dpg.add_text("Kein Slot gewählt.", parent=_PROPS, color=(150, 150, 150))
            return
        slot = self.slots[self.selected]
        old_name = self.selected

        def _on_name(s, a, u):
            a = a.strip()
            if a and a != old_name and a not in self.slots:
                self.slots[a] = self.slots.pop(old_name)
                self.slots[a].name = a
                self.selected = a
                self.redraw_overlay()
                self.refresh_slot_list()
                self.refresh_properties()
        dpg.add_input_text(label="Name", default_value=slot.name, parent=_PROPS,
                           width=-70, on_enter=True, callback=_on_name)
        r = slot.scan_region
        dpg.add_text(f"Region: ({r[0]},{r[1]})–({r[2]},{r[3]})", parent=_PROPS)
        dpg.add_text(f"Klickpunkt: {slot.click_pos}", parent=_PROPS)
        with dpg.group(horizontal=True, parent=_PROPS):
            if slot.slot_color:
                dpg.add_color_button(default_value=tuple(slot.slot_color) + (255,),
                                     width=20, height=20, no_border=True)
                dpg.add_text(f"RGB{slot.slot_color}")
            else:
                dpg.add_text("Farbe: keine", color=(150, 150, 150))
        dpg.add_text("→ Modus 'Klickpunkt'/'Farbe', dann\n   in den Slot klicken.",
                     parent=_PROPS, color=(150, 150, 150))
        dpg.add_separator(parent=_PROPS)
        dpg.add_button(label="→ Item aus diesem Slot lernen", width=-1, parent=_PROPS,
                       user_data=self.selected, callback=self._on_learn_item)
        dpg.add_button(label="Slot löschen", width=-1, parent=_PROPS,
                       callback=self._on_delete_slot)

    def _props_item(self) -> None:
        if not self.selected or self.selected not in self.items:
            dpg.add_text("Kein Item gewählt.", parent=_PROPS, color=(150, 150, 150))
            return
        item = self.items[self.selected]
        old_name = self.selected

        def _on_name(s, a, u):
            a = a.strip()
            if a and a != old_name and a not in self.items:
                self.items[a] = self.items.pop(old_name)
                self.items[a].name = a
                self.selected = a
                self.refresh_item_list()
                self.refresh_properties()
        dpg.add_input_text(label="Name", default_value=item.name, parent=_PROPS,
                           width=-70, on_enter=True, callback=_on_name)

        def _on_cat(s, a, u):
            item.category = a.strip() or None
            self.refresh_item_list()
        dpg.add_input_text(label="Kategorie", default_value=item.category or "",
                           parent=_PROPS, width=-70, on_enter=True, callback=_on_cat)
        cats = existing_categories(self.items)
        if cats:
            dpg.add_text("vorhanden: " + ", ".join(cats), parent=_PROPS,
                         color=(150, 150, 150), wrap=270)

        def _on_prio(s, a, u):
            item.priority = max(1, int(a))
            self.refresh_item_list()
        dpg.add_input_int(label="Priorität", default_value=item.priority, parent=_PROPS,
                          width=-70, min_value=1, callback=_on_prio)

        def _on_conf(s, a, u):
            item.min_confidence = max(0.1, min(1.0, float(a) / 100.0))
        dpg.add_input_int(label="Konfidenz %", default_value=int(item.min_confidence * 100),
                          parent=_PROPS, width=-70, min_value=10, max_value=100, callback=_on_conf)

        tpl = item.template or "—"
        dpg.add_text(f"Template: {tpl}", parent=_PROPS)
        dpg.add_text(f"Marker-Farben: {len(item.marker_colors)}", parent=_PROPS)
        if item.marker_colors:
            with dpg.group(horizontal=True, parent=_PROPS):
                for c in item.marker_colors[:6]:
                    dpg.add_color_button(default_value=tuple(c) + (255,),
                                         width=18, height=18, no_border=True)
        dpg.add_separator(parent=_PROPS)
        dpg.add_button(label="Item löschen", width=-1, parent=_PROPS,
                       callback=self._on_delete_item)

    # --------------------------------------------------------------- Callbacks
    def _on_mode(self, sender, app_data):
        self.mode = {"Slot zeichnen": MODE_SLOT, "Klickpunkt setzen": MODE_CLICK,
                     "Farbe picken": MODE_COLOR}.get(app_data, MODE_SLOT)

    def _on_select_slot(self, sender, app_data, user_data):
        self.selected = user_data
        self.selected_kind = KIND_SLOT
        self.redraw_overlay()
        self.refresh_slot_list()
        self.refresh_item_list()
        self.refresh_properties()

    def _on_select_item(self, sender, app_data, user_data):
        self.selected = user_data
        self.selected_kind = KIND_ITEM
        self.refresh_slot_list()
        self.refresh_item_list()
        self.refresh_properties()

    def _on_delete_slot(self, *_):
        if self.selected_kind == KIND_SLOT and self.selected in self.slots:
            del self.slots[self.selected]
            self.selected = None
            self.redraw_overlay()
            self.refresh_slot_list()
            self.refresh_scan_panel()
            self.refresh_properties()

    def _on_delete_item(self, *_):
        if self.selected_kind == KIND_ITEM and self.selected in self.items:
            del self.items[self.selected]
            self.selected = None
            self.refresh_item_list()
            self.refresh_scan_panel()
            self.refresh_properties()

    def _learn_from_slot(self, slot: ItemSlot, name: str | None = None,
                         dedup: bool = False) -> str | None:
        """Lernt ein Item aus einer Slot-Region: Template + Marker-Farben.

        Gibt den Item-Namen zurück, oder None (Crop fehlgeschlagen / Duplikat).
        """
        crop = crop_region(self.image, slot.scan_region,
                           self.transform.virtual_left, self.transform.virtual_top)
        if crop is None:
            return None
        if dedup:
            dup = _find_matching_existing_item(
                crop, list(self.items.items()), DEFAULT_MIN_CONFIDENCE)
            if dup:
                return None
        item_name = name or next_item_name(self.items)
        markers = _collect_markers_silent(crop, slot.slot_color)
        template = save_template(crop, item_name)
        self.items[item_name] = ItemProfile(
            name=item_name,
            marker_colors=[tuple(c) for c in markers],
            category=None,
            priority=len(self.items) + 1,
            template=template,
            min_confidence=DEFAULT_MIN_CONFIDENCE,
        )
        return item_name

    def _on_learn_item(self, sender, app_data, user_data):
        slot = self.slots.get(user_data)
        if not slot:
            return
        name = self._learn_from_slot(slot)
        if name:
            self.selected = name
            self.selected_kind = KIND_ITEM
            self.refresh_slot_list()
            self.refresh_item_list()
            self.refresh_scan_panel()
            self.refresh_properties()
            self._set_status(f"Item '{name}' aus '{slot.name}' gelernt.")
        else:
            self._set_status("Item lernen fehlgeschlagen.", color=(220, 90, 90))

    def _on_autoscan(self, *_):
        if not self.slots:
            self._set_status("Keine Slots zum Scannen.", color=(220, 180, 90))
            return
        created = 0
        skipped = 0
        for slot in list(self.slots.values()):
            name = self._learn_from_slot(slot, dedup=OPENCV_AVAILABLE)
            if name:
                created += 1
            else:
                skipped += 1
        self.refresh_item_list()
        self.refresh_scan_panel()
        self.refresh_properties()
        self._set_status(f"Autoscan: {created} neu, {skipped} übersprungen.")

    def _on_save(self, *_):
        ok_s = save_slots(self.slots, self.slots_file)
        ok_i = save_items(self.items, self.items_file)
        if ok_s and ok_i:
            self._set_status(f"{len(self.slots)} Slot(s), {len(self.items)} Item(s) gespeichert.")
        else:
            self._set_status("Speichern fehlgeschlagen!", color=(220, 90, 90))

    def _set_status(self, text: str, color=(110, 200, 110)) -> None:
        if dpg.does_item_exist(_STATUS):
            dpg.set_value(_STATUS, text)
            dpg.configure_item(_STATUS, color=color)
