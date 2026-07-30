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

from ...config import CONFIG
from ...models import (
    ItemSlot, ItemProfile, ItemScanConfig,
    IconScanConfig, BossScanConfig, BossProfile,
)
from ...imaging import OPENCV_AVAILABLE
from ...persistence import (
    save_item_scan, ensure_item_scans_dir,
    list_available_item_scans, load_item_scan_file,
    save_icon_scan, ensure_icon_scans_dir,
    list_available_icon_scans, load_icon_scan_file,
    save_boss_scan, ensure_boss_scans_dir,
    list_available_boss_scans, load_boss_scan_file,
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
_ICON = "ac_ss_icon"
_ICON_PICK = "ac_ss_iconpick"
_BOSS = "ac_ss_boss"
_BOSS_PICK = "ac_ss_bosspick"
_STATUS = "ac_ss_status"

# Aktions-Auswahl (Anzeige ↔ Wert)
_ICON_ACTIONS = ["click", "key", "skip", "skip_cycle", "restart"]
_BOSS_ACTIONS = ["item_scan", "click", "key", "skip", "skip_cycle", "restart"]

# Modi
MODE_SLOT = "slot"
MODE_CLICK = "click"
MODE_COLOR = "color"
# Label im Werkzeug-Radio (für _set_mode, um das Widget mit dem Modus zu syncen)
_MODE_LABELS = {MODE_SLOT: "Slot zeichnen", MODE_CLICK: "Klickpunkt setzen",
                MODE_COLOR: "Farbe picken"}

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
        # Geführter Slot-Ablauf: nach dem Aufziehen automatisch durch
        # Klickpunkt → Farbe leiten (None = kein laufender geführter Schritt).
        self._guided_step: str | None = None
        self._drawing = False
        self._draw_start = (0.0, 0.0)
        self._draw_cur = (0.0, 0.0)
        # Boss/Icon: laufende Konfigurationen + Pick-Callbacks
        self._icon_cfg = IconScanConfig(name="")
        self._icon_region = None        # zuletzt gezeichnete Icon-Region (Screen)
        self._boss_cfg = BossScanConfig(name="")
        self._boss_region = None
        self._boss_sel: int | None = None
        # Generalisierte Canvas-Eingaben (für Boss/Icon-Tabs):
        self._region_cb = None          # naechstes Rechteck -> cb(region)
        self._marker_cb = None          # Klick pickt Farbe -> cb(rgb)
        self._marker_owner = None       # (kind, name)-Tupel der Marker-Ziel-Config
        self._point_cb = None           # naechster Klick -> cb((x,y))
        self._tex_data = None           # Anker fuer Textur-Daten (GC-Schutz)

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
        self.refresh_icon_panel()
        self.refresh_boss_panel()
        self.refresh_properties()
        dpg.start_dearpygui()
        dpg.destroy_context()

    def _register_texture(self) -> None:
        tex = pil_to_texture(self.image)
        if tex is None:
            raise RuntimeError("Textur-Konvertierung fehlgeschlagen (numpy fehlt?)")
        w, h, data = tex
        # Referenz halten: Der Screenshot wird nie in-place aktualisiert, daher
        # add_static_texture (DPG kopiert die Daten). Zusaetzlich self._tex_data
        # als Anker behalten, falls eine DPG-Version den Buffer doch referenziert.
        self._tex_data = data
        with dpg.texture_registry():
            dpg.add_static_texture(w, h, data, format=dpg.mvFormat_Float_rgba, tag=_TEX)

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
                    dpg.add_text("Rechteck aufziehen → führt\nautomatisch zu Klickpunkt\n+ Farbe (Status beachten).",
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
                        with dpg.tab(label="Icon-Scan"):
                            dpg.add_group(tag=_ICON)
                        with dpg.tab(label="Boss-Scan"):
                            dpg.add_group(tag=_BOSS)

    def _install_handlers(self) -> None:
        with dpg.handler_registry():
            dpg.add_mouse_down_handler(button=dpg.mvMouseButton_Left, callback=self._on_mouse_down)
            dpg.add_mouse_drag_handler(button=dpg.mvMouseButton_Left, callback=self._on_mouse_drag)
            dpg.add_mouse_release_handler(button=dpg.mvMouseButton_Left, callback=self._on_mouse_release)

    def _defer(self, fn) -> None:
        """Fuehrt fn im naechsten Frame aus.

        Noetig, wenn ein Widget-Callback sein eigenes Panel neu baut: ein Rebuild
        loescht das gerade laufende Widget mitten in dessen Callback -> Crash
        (besonders bei Combos mit offenem Popup). Der Aufschub um einen Frame
        laesst den Callback sauber zurueckkehren, bevor der Rebuild startet.
        """
        dpg.set_frame_callback(dpg.get_frame_count() + 1, callback=lambda: fn())

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
        # Rechteck ziehen: für Slots (Modus SLOT) oder wenn eine Region angefragt ist
        if self._region_cb is not None or self.mode == MODE_SLOT:
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
        if self._drawing:
            self._drawing = False
            x0, y0 = self._draw_start
            x1, y1 = self._draw_cur
            if self._region_cb is not None:
                cb, self._region_cb = self._region_cb, None
                sx0, sy0 = self.transform.draw_to_screen(x0, y0)
                sx1, sy1 = self.transform.draw_to_screen(x1, y1)
                cb(self._clamp_region(normalize_region(sx0, sy0, sx1, sy1)))
                self.redraw_overlay()
            else:
                self._finish_draw(x0, y0, x1, y1)
            return
        if pos is None:
            return
        # Einzelklick-Picks (Boss/Icon)
        if self._point_cb is not None:
            cb, self._point_cb = self._point_cb, None
            cb(self.transform.draw_to_screen(pos[0], pos[1]))
            return
        if self._marker_cb is not None:
            ix, iy = self.transform.draw_to_image(pos[0], pos[1])
            px = self.image.convert("RGB").getpixel((ix, iy))
            self._marker_cb((int(px[0]), int(px[1]), int(px[2])))
            return
        if self.mode in (MODE_CLICK, MODE_COLOR):
            self._handle_point(pos[0], pos[1])

    # --------------------------------------------------------- Kern-Aktionen
    def _clamp_region(self, region: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        """Klemmt eine Bildschirm-Region auf die Screenshot-Grenzen.

        Ueber den Screenshot hinausgezogene Rechtecke wuerden spaeter zu
        fehlerhaften take_screenshot-Ausschnitten fuehren.
        """
        t = self.transform
        left, top = t.virtual_left, t.virtual_top
        right, bottom = left + t.img_w, top + t.img_h
        x1 = max(left, min(right, region[0]))
        y1 = max(top, min(bottom, region[1]))
        x2 = max(left, min(right, region[2]))
        y2 = max(top, min(bottom, region[3]))
        return (x1, y1, x2, y2)

    def _finish_draw(self, dx0, dy0, dx1, dy1) -> None:
        """Erzeugt aus einem aufgezogenen Rechteck einen neuen Slot."""
        if abs(dx1 - dx0) < _MIN_DRAW_PX or abs(dy1 - dy0) < _MIN_DRAW_PX:
            self.redraw_overlay()
            return
        sx0, sy0 = self.transform.draw_to_screen(dx0, dy0)
        sx1, sy1 = self.transform.draw_to_screen(dx1, dy1)
        region = self._clamp_region(normalize_region(sx0, sy0, sx1, sy1))
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
        # Geführt weiter: direkt in den Klickpunkt-Schritt (Werkzeug springt mit),
        # damit man nicht manuell umschalten muss — wie der Konsolen-Ablauf.
        self._guided_step = "click"
        self._set_mode(MODE_CLICK)
        self._set_status(f"Slot '{name}' angelegt — jetzt Klickpunkt anklicken "
                         f"(oder Werkzeug wechseln zum Überspringen).")

    def _handle_point(self, dx, dy) -> None:
        """Klick im Modus Klickpunkt/Farbe auf den gewählten Slot anwenden."""
        if self.selected_kind != KIND_SLOT or self.selected not in self.slots:
            self._set_status("Erst einen Slot wählen.", color=(220, 180, 90))
            return
        slot = self.slots[self.selected]
        if self.mode == MODE_CLICK:
            slot.click_pos = self.transform.draw_to_screen(dx, dy)
            if self._guided_step == "click":
                # Weiter zum Farbe-Schritt
                self._guided_step = "color"
                self._set_mode(MODE_COLOR)
                self._set_status(f"Klickpunkt gesetzt — jetzt Hintergrundfarbe auf dem "
                                 f"leeren Slot anklicken (oder 'Slot zeichnen' = überspringen).")
            else:
                self._set_status(f"Klickpunkt: {slot.click_pos}")
        elif self.mode == MODE_COLOR:
            ix, iy = self.transform.draw_to_image(dx, dy)
            px = self.image.convert("RGB").getpixel((ix, iy))
            slot.slot_color = (int(px[0]), int(px[1]), int(px[2]))
            if self._guided_step == "color":
                # Ablauf fertig → zurück zum Zeichnen für den nächsten Slot
                self._guided_step = None
                self._set_mode(MODE_SLOT)
                self._set_status(f"Slot '{slot.name}' fertig (Region + Klickpunkt + Farbe). "
                                 f"Nächstes Rechteck ziehen.")
            else:
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
        # Icon-/Boss-Scan-Regionen (andere Farben, klar unterscheidbar)
        for region, color, label in (
            (self._icon_region, (230, 150, 60), "ICON"),
            (self._boss_region, (230, 70, 70), "BOSS"),
        ):
            if region:
                rx1, ry1, rx2, ry2 = t.screen_region_to_draw(region)
                dpg.draw_rectangle((rx1, ry1), (rx2, ry2), color=color, thickness=2,
                                   parent=_OVERLAY)
                dpg.draw_text((rx1 + 3, ry1 + 2), label, size=14, color=color, parent=_OVERLAY)
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
            label = ("> " if sel else "") + name
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
            label = ("> " if sel else "") + f"P{item.priority} {name}{cat}"
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

    # ----------------------------------------------------- generische Picks
    def _request_region(self, setter, refresh, label: str) -> None:
        def _cb(region):
            setter(region)
            self.redraw_overlay()
            refresh()
        self._region_cb = _cb
        self._set_status(f"{label}: Rechteck auf dem Screenshot aufziehen.",
                         color=(120, 200, 120))

    def _reset_picks(self) -> None:
        """Setzt alle haengenden Canvas-Pick-Modi zurueck.

        Wird beim Wechsel/Laden einer Config aufgerufen: ein noch aktiver
        Marker- oder Punkt-Pick wuerde sonst in die verwaiste alte Config bzw.
        Liste schreiben (Stale-Closure).
        """
        self._marker_cb = None
        self._marker_owner = None
        self._point_cb = None
        self._region_cb = None

    def _toggle_marker(self, target_list, refresh, owner) -> None:
        # owner = (kind, name)-Tupel, identifiziert die Ziel-Config stabil (statt
        # id(liste), das nach Config-Wechsel/Clear auf eine verwaiste Liste zeigt).
        # Schaltet aus, wenn bereits fuer DIESES Ziel aktiv -- sonst (auch bei
        # anderem Ziel) auf dieses Ziel umschalten.
        if self._marker_cb is not None and self._marker_owner == owner:
            self._marker_cb = None
            self._marker_owner = None
            self._set_status("Marker-Pick aus.")
        else:
            self._marker_owner = owner

            def _cb(rgb):
                target_list.append(rgb)
                refresh()
                self._set_status(f"Marker + RGB{rgb} (klicke weiter / Button = aus).",
                                 color=(120, 200, 120))
            self._marker_cb = _cb
            self._set_status("Klick auf den Screenshot pickt Marker-Farben.",
                             color=(120, 200, 120))
        refresh()

    # ----------------------------------------------------------- Icon-Scan
    def refresh_icon_panel(self) -> None:
        if not dpg.does_item_exist(_ICON):
            return
        for child in dpg.get_item_children(_ICON, 1) or []:
            dpg.delete_item(child)
        cfg = self._icon_cfg
        p = _ICON

        names = [n for n, _ in list_available_icon_scans()]
        if names:
            with dpg.group(horizontal=True, parent=p):
                dpg.add_combo(items=names, width=-60, tag=_ICON_PICK, default_value=names[0])
                dpg.add_button(label="Laden", callback=self._on_load_icon)
            dpg.add_separator(parent=p)

        def _name(s, a, u):
            cfg.name = a.strip()
        dpg.add_input_text(label="Name", default_value=cfg.name, parent=p, width=-80, callback=_name)

        dpg.add_button(label="Region aufziehen", width=-1, parent=p, callback=self._on_icon_region)
        r = cfg.scan_region
        dpg.add_text(f"Region: ({r[0]},{r[1]})-({r[2]},{r[3]})", parent=p)

        dpg.add_separator(parent=p)
        dpg.add_text("Erkennung", parent=p, color=(120, 180, 255))
        dpg.add_button(label="Template aus Region aufnehmen", width=-1, parent=p,
                       callback=self._on_icon_template)
        dpg.add_text(f"Template: {cfg.template or '-'}", parent=p)

        def _conf(s, a, u):
            cfg.min_confidence = max(0.1, min(1.0, float(a) / 100.0))
        dpg.add_input_int(label="Konfidenz %", default_value=int(cfg.min_confidence * 100),
                          parent=p, width=-80, min_value=10, max_value=100, callback=_conf)

        mk_on = self._marker_cb is not None
        dpg.add_button(label=("Marker-Pick: AN" if mk_on else "Marker hinzufügen"),
                       width=-1, parent=p, callback=self._on_icon_marker)
        dpg.add_text(f"Marker-Farben: {len(cfg.marker_colors)}", parent=p)
        if cfg.marker_colors:
            with dpg.group(horizontal=True, parent=p):
                for c in cfg.marker_colors[:8]:
                    dpg.add_color_button(default_value=tuple(c) + (255,), width=16, height=16,
                                         no_border=True)
            dpg.add_button(label="Marker löschen", parent=p, callback=self._on_icon_marker_clear)

        def _tol(s, a, u):
            cfg.color_tolerance = max(1, min(100, int(a)))
        dpg.add_input_int(label="Farbtoleranz", default_value=cfg.color_tolerance,
                          parent=p, width=-80, min_value=1, max_value=100, callback=_tol)

        dpg.add_separator(parent=p)
        dpg.add_text("Aktion bei Fund", parent=p, color=(120, 180, 255))

        def _act(s, a, u):
            cfg.action = a
            self._defer(self.refresh_icon_panel)
        dpg.add_combo(items=_ICON_ACTIONS, default_value=cfg.action, parent=p, width=-80,
                      callback=_act)
        self._build_action_params(p, cfg, with_scan=False)

        dpg.add_separator(parent=p)
        dpg.add_button(label="Icon-Scan speichern", width=-1, parent=p, callback=self._on_save_icon)

    def _build_action_params(self, parent, cfg, with_scan: bool) -> None:
        """Gemeinsame Aktions-Felder für Icon/Boss (click→x/y, key→Taste, delay, ggf. scan)."""
        if cfg.action == "click":
            def _ax(s, a, u): cfg.action_x = int(a)
            def _ay(s, a, u): cfg.action_y = int(a)
            dpg.add_input_int(label="Klick X", default_value=cfg.action_x, parent=parent,
                              width=-80, callback=_ax)
            dpg.add_input_int(label="Klick Y", default_value=cfg.action_y, parent=parent,
                              width=-80, callback=_ay)
            dpg.add_button(label="Punkt auf Canvas wählen", width=-1, parent=parent,
                           user_data=cfg, callback=self._on_pick_action_point)
        elif cfg.action == "key":
            def _ak(s, a, u): cfg.action_key = a
            dpg.add_input_text(label="Taste", default_value=cfg.action_key or "", parent=parent,
                               width=-80, callback=_ak)
        elif cfg.action == "item_scan" and with_scan:
            def _as(s, a, u): cfg.action_scan = a.strip() or None
            dpg.add_input_text(label="Item-Scan", default_value=cfg.action_scan or "",
                               parent=parent, width=-80, callback=_as)

        def _ad(s, a, u): cfg.action_delay = max(0.0, float(a))
        dpg.add_input_float(label="Delay (s)", default_value=float(cfg.action_delay),
                            parent=parent, width=-80, min_value=0.0, step=0.1,
                            format="%.2f", callback=_ad)

    def _on_icon_region(self, *_):
        def _set(region):
            self._icon_cfg.scan_region = region
            self._icon_region = region
        self._request_region(_set, self.refresh_icon_panel, "Icon-Region")

    def _on_icon_template(self, *_):
        crop = crop_region(self.image, self._icon_cfg.scan_region,
                           self.transform.virtual_left, self.transform.virtual_top)
        fn = save_template(crop, self._icon_cfg.name or "icon")
        if fn:
            self._icon_cfg.template = fn
            self._set_status(f"Template '{fn}' aufgenommen.")
        else:
            self._set_status("Template aufnehmen fehlgeschlagen.", color=(220, 90, 90))
        self.refresh_icon_panel()

    def _on_icon_marker(self, *_):
        self._toggle_marker(self._icon_cfg.marker_colors, self.refresh_icon_panel,
                            ("icon", self._icon_cfg.name))

    def _on_icon_marker_clear(self, *_):
        # In-place leeren (clear) statt Neuzuweisung: ein noch aktiver Marker-Pick
        # haelt eine Referenz auf genau diese Liste -- Neuzuweisung wuerde Picks
        # in eine verwaiste Liste schreiben.
        self._icon_cfg.marker_colors.clear()
        self.refresh_icon_panel()

    def _on_load_icon(self, *_):
        name = dpg.get_value(_ICON_PICK) if dpg.does_item_exist(_ICON_PICK) else ""
        path = next((p for n, p in list_available_icon_scans() if n == name), None)
        cfg = load_icon_scan_file(path) if path else None
        if cfg:
            self._reset_picks()
            self._icon_cfg = cfg
            self._icon_region = cfg.scan_region
            self.redraw_overlay()
            self.refresh_icon_panel()
            self._set_status(f"Icon-Scan '{name}' geladen.")

    def _on_save_icon(self, *_):
        if not self._icon_cfg.name:
            self._set_status("Bitte Icon-Scan-Namen eingeben.", color=(220, 180, 90))
            return
        ensure_icon_scans_dir()
        save_icon_scan(self._icon_cfg)
        self.refresh_icon_panel()
        self._set_status(f"Icon-Scan '{self._icon_cfg.name}' gespeichert.")

    def _on_pick_action_point(self, sender, app_data, user_data):
        cfg = user_data

        def _cb(pt):
            cfg.action_x, cfg.action_y = pt
            self.refresh_icon_panel()
            self.refresh_boss_panel()
            self._set_status(f"Aktions-Punkt: {pt}")
        self._point_cb = _cb
        self._set_status("Klick auf den Screenshot setzt den Aktions-Punkt.",
                         color=(120, 200, 120))

    # ----------------------------------------------------------- Boss-Scan
    def refresh_boss_panel(self) -> None:
        if not dpg.does_item_exist(_BOSS):
            return
        for child in dpg.get_item_children(_BOSS, 1) or []:
            dpg.delete_item(child)
        cfg = self._boss_cfg
        p = _BOSS

        names = [n for n, _ in list_available_boss_scans()]
        if names:
            with dpg.group(horizontal=True, parent=p):
                dpg.add_combo(items=names, width=-60, tag=_BOSS_PICK, default_value=names[0])
                dpg.add_button(label="Laden", callback=self._on_load_boss)
            dpg.add_separator(parent=p)

        def _name(s, a, u):
            cfg.name = a.strip()
        dpg.add_input_text(label="Name", default_value=cfg.name, parent=p, width=-80, callback=_name)
        dpg.add_button(label="Region aufziehen", width=-1, parent=p, callback=self._on_boss_region)
        r = cfg.scan_region
        dpg.add_text(f"Region: ({r[0]},{r[1]})-({r[2]},{r[3]})", parent=p)

        def _tol(s, a, u):
            cfg.color_tolerance = max(1, min(100, int(a)))
        dpg.add_input_int(label="Farbtoleranz", default_value=cfg.color_tolerance,
                          parent=p, width=-80, min_value=1, max_value=100, callback=_tol)

        def _def(s, a, u):
            cfg.default_action = a
        dpg.add_combo(items=["skip", "skip_cycle", "restart", "item_scan"],
                      default_value=cfg.default_action, label="Default", parent=p, width=-80,
                      callback=_def)

        def _llm(s, a, u): cfg.use_llm = bool(a)
        def _ocr(s, a, u): cfg.use_ocr = bool(a)
        dpg.add_checkbox(label="LLM-Vision nutzen", default_value=cfg.use_llm, parent=p, callback=_llm)
        dpg.add_checkbox(label="OCR nutzen", default_value=cfg.use_ocr, parent=p, callback=_ocr)

        dpg.add_separator(parent=p)
        with dpg.group(horizontal=True, parent=p):
            dpg.add_text("Bosse", color=(120, 180, 255))
            dpg.add_button(label="+ Boss", callback=self._on_boss_add)
        for idx, b in enumerate(cfg.bosses):
            label = ("> " if idx == self._boss_sel else "") + (b.name or f"Boss {idx+1}")
            dpg.add_button(label=label, width=-1, parent=p, user_data=idx,
                           callback=self._on_boss_select)

        if self._boss_sel is not None and 0 <= self._boss_sel < len(cfg.bosses):
            self._build_boss_editor(p, cfg.bosses[self._boss_sel])

        dpg.add_separator(parent=p)
        dpg.add_button(label="Boss-Scan speichern", width=-1, parent=p, callback=self._on_save_boss)

    def _build_boss_editor(self, parent, boss: BossProfile) -> None:
        dpg.add_separator(parent=parent)
        dpg.add_text(f"Boss: {boss.name}", parent=parent, color=(230, 140, 140))

        def _bn(s, a, u):
            boss.name = a.strip()
            self._defer(self.refresh_boss_panel)
        dpg.add_input_text(label="Boss-Name", default_value=boss.name, parent=parent,
                           width=-80, on_enter=True, callback=_bn)

        dpg.add_button(label="Template aus Region aufnehmen", width=-1, parent=parent,
                       callback=self._on_boss_template)
        dpg.add_text(f"Template: {boss.template or '-'}", parent=parent)

        mk_on = self._marker_cb is not None
        dpg.add_button(label=("Marker-Pick: AN" if mk_on else "Marker hinzufügen"),
                       width=-1, parent=parent, callback=self._on_boss_marker)
        dpg.add_text(f"Marker-Farben: {len(boss.marker_colors)}", parent=parent)
        if boss.marker_colors:
            with dpg.group(horizontal=True, parent=parent):
                for c in boss.marker_colors[:8]:
                    dpg.add_color_button(default_value=tuple(c) + (255,), width=16, height=16,
                                         no_border=True)
            dpg.add_button(label="Marker löschen", parent=parent, callback=self._on_boss_marker_clear)

        def _act(s, a, u):
            boss.action = a
            self._defer(self.refresh_boss_panel)
        dpg.add_combo(items=_BOSS_ACTIONS, default_value=boss.action, label="Aktion",
                      parent=parent, width=-80, callback=_act)
        self._build_action_params(parent, boss, with_scan=True)
        dpg.add_button(label="Boss löschen", width=-1, parent=parent, callback=self._on_boss_delete)

    def _selected_boss(self) -> BossProfile | None:
        if self._boss_sel is not None and 0 <= self._boss_sel < len(self._boss_cfg.bosses):
            return self._boss_cfg.bosses[self._boss_sel]
        return None

    def _on_boss_region(self, *_):
        def _set(region):
            self._boss_cfg.scan_region = region
            self._boss_region = region
        self._request_region(_set, self.refresh_boss_panel, "Boss-Region")

    def _on_boss_add(self, *_):
        self._boss_cfg.bosses.append(BossProfile(name=f"Boss {len(self._boss_cfg.bosses)+1}"))
        self._boss_sel = len(self._boss_cfg.bosses) - 1
        self.refresh_boss_panel()

    def _on_boss_select(self, sender, app_data, user_data):
        # Boss-Wechsel: haengenden Marker-Pick zuruecksetzen (Ziel war der alte Boss).
        self._reset_picks()
        self._boss_sel = user_data
        self.refresh_boss_panel()

    def _on_boss_delete(self, *_):
        b = self._selected_boss()
        if b is not None:
            self._reset_picks()
            self._boss_cfg.bosses.remove(b)
            self._boss_sel = None
            self.refresh_boss_panel()

    def _on_boss_template(self, *_):
        b = self._selected_boss()
        if b is None:
            return
        crop = crop_region(self.image, self._boss_cfg.scan_region,
                           self.transform.virtual_left, self.transform.virtual_top)
        fn = save_template(crop, b.name or "boss")
        if fn:
            b.template = fn
            self._set_status(f"Template '{fn}' aufgenommen.")
        self.refresh_boss_panel()

    def _on_boss_marker(self, *_):
        b = self._selected_boss()
        if b is not None:
            self._toggle_marker(b.marker_colors, self.refresh_boss_panel,
                                ("boss", self._boss_cfg.name, self._boss_sel))

    def _on_boss_marker_clear(self, *_):
        b = self._selected_boss()
        if b is not None:
            # In-place leeren (siehe _on_icon_marker_clear).
            b.marker_colors.clear()
            self.refresh_boss_panel()

    def _on_load_boss(self, *_):
        name = dpg.get_value(_BOSS_PICK) if dpg.does_item_exist(_BOSS_PICK) else ""
        path = next((p for n, p in list_available_boss_scans() if n == name), None)
        cfg = load_boss_scan_file(path) if path else None
        if cfg:
            self._reset_picks()
            self._boss_cfg = cfg
            self._boss_region = cfg.scan_region
            self._boss_sel = 0 if cfg.bosses else None
            self.redraw_overlay()
            self.refresh_boss_panel()
            self._set_status(f"Boss-Scan '{name}' geladen.")

    def _on_save_boss(self, *_):
        if not self._boss_cfg.name:
            self._set_status("Bitte Boss-Scan-Namen eingeben.", color=(220, 180, 90))
            return
        ensure_boss_scans_dir()
        save_boss_scan(self._boss_cfg)
        self.refresh_boss_panel()
        self._set_status(f"Boss-Scan '{self._boss_cfg.name}' gespeichert "
                         f"({len(self._boss_cfg.bosses)} Boss(e)).")

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
                # Checkbox-Status mit umziehen (Key-Rename)
                if old_name in self._slot_checked:
                    self._slot_checked[a] = self._slot_checked.pop(old_name)
                self.selected = a
                self.redraw_overlay()
                self.refresh_slot_list()
                self._defer(self.refresh_properties)
        dpg.add_input_text(label="Name", default_value=slot.name, parent=_PROPS,
                           width=-70, on_enter=True, callback=_on_name)
        r = slot.scan_region
        dpg.add_text(f"Region: ({r[0]},{r[1]})-({r[2]},{r[3]})", parent=_PROPS)
        dpg.add_text(f"Klickpunkt: {slot.click_pos}", parent=_PROPS)
        with dpg.group(horizontal=True, parent=_PROPS):
            if slot.slot_color:
                dpg.add_color_button(default_value=tuple(slot.slot_color) + (255,),
                                     width=20, height=20, no_border=True)
                dpg.add_text(f"RGB{slot.slot_color}")
            else:
                dpg.add_text("Farbe: keine", color=(150, 150, 150))
        dpg.add_text("-> Modus 'Klickpunkt'/'Farbe', dann\n   in den Slot klicken.",
                     parent=_PROPS, color=(150, 150, 150))
        dpg.add_separator(parent=_PROPS)
        dpg.add_button(label="-> Item aus diesem Slot lernen", width=-1, parent=_PROPS,
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
                # Checkbox-Status mit umziehen (Key-Rename)
                if old_name in self._item_checked:
                    self._item_checked[a] = self._item_checked.pop(old_name)
                self.selected = a
                self.refresh_item_list()
                self._defer(self.refresh_properties)
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

        tpl = item.template or "-"
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
    def _set_mode(self, mode: str) -> None:
        """Setzt das aktive Werkzeug und hält das Radio-Widget sichtbar in Sync."""
        self.mode = mode
        if dpg.does_item_exist("ac_ss_mode"):
            dpg.set_value("ac_ss_mode", _MODE_LABELS.get(mode, "Slot zeichnen"))

    def _on_mode(self, sender, app_data):
        # Manueller Werkzeug-Wechsel bricht einen laufenden geführten Ablauf ab,
        # damit das Auto-Weiterschalten den Nutzer nicht überstimmt.
        self._guided_step = None
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
                crop, list(self.items.items()), CONFIG.scan_min_confidence)
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
            min_confidence=CONFIG.scan_min_confidence,
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
