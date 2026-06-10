"""
Dear PyGui Canvas-Renderer für den visuellen Sequenz-Editor.

Zeichnet die Lane-Struktur (INIT / Loop-Phasen / END) als Spalten von Blöcken,
verbindet aufeinanderfolgende Blöcke mit Pfeilen (= Ausführungsreihenfolge) und
zeigt ELSE-Fallbacks als rote Abzweigung. Links: Punkte-Palette + Sequenz-
Einstellungen + Speichern. Rechts: Eigenschaften des gewählten Blocks.

Läuft ausschließlich im Editor-Subprocess (Dear PyGui import).
"""

import os
import re

import dearpygui.dearpygui as dpg

from pathlib import Path

from ...models import SequenceStep
from ...persistence import (
    save_sequence_file, list_available_sequences, load_sequence_file,
)
from ...utils import sanitize_filename
from .model import (
    BlockGraph, Lane,
    BLOCK_LABELS, BLOCK_COLORS,
    BLOCK_ITEM_SCAN, BLOCK_ICON_SCAN, BLOCK_BOSS_SCAN, BLOCK_BOSS_WATCHER,
    block_type, sequence_to_graph, graph_to_sequence,
    load_palette_points, step_from_point,
)
from .panels import build_properties_panel

# Feste Tags
_NODE_EDITOR = "ac_node_editor"
_PROPS_PANEL = "ac_props_panel"
_STATUS = "ac_status_text"
_LANE_PICK = "ac_lane_pick"
_SIDEBAR = "ac_sidebar_body"
_SEQ_PICK = "ac_seq_pick"

# Layout-Konstanten
_COL_W = 270    # horizontaler Abstand zwischen Lanes
_ROW_H = 130    # vertikaler Abstand zwischen Blöcken
_X0 = 30
_Y0 = 30


class NodeEditorApp:
    """Hält den Editor-Zustand und rendert das Canvas."""

    def __init__(self, seq, filepath: Path, sequences_dir: str):
        self.graph: BlockGraph = sequence_to_graph(seq)
        self.filepath = Path(filepath)
        self.sequences_dir = sequences_dir
        self.points = load_palette_points(sequences_dir)
        self.selected: tuple[Lane, int] | None = None
        self._themes: dict[str, int] = {}
        self._dirty = False
        # Welche Aktion (_on_load_sequence/_on_new_sequence) auf Bestätigung
        # wartet, weil ungespeicherte Änderungen existieren (2-Klick-Schutz).
        self._pending_discard: str | None = None

    # ---------------------------------------------------------------- Setup
    def run(self) -> None:
        dpg.create_context()
        self._build_themes()
        self._build_ui()
        dpg.create_viewport(title=f"Node-Editor – {self.graph.name}", width=1400, height=820)
        dpg.setup_dearpygui()
        dpg.show_viewport()
        dpg.set_primary_window("ac_root", True)
        self._update_title()
        self.rebuild_canvas()
        self.refresh_properties()
        dpg.start_dearpygui()
        dpg.destroy_context()

    def _build_themes(self) -> None:
        """Ein Theme pro Block-Typ für eine farbige Node-Titelzeile."""
        for btype, color in BLOCK_COLORS.items():
            hover = tuple(min(255, c + 30) for c in color)
            with dpg.theme() as theme:
                with dpg.theme_component(dpg.mvNode):
                    dpg.add_theme_color(dpg.mvNodeCol_TitleBar, color,
                                        category=dpg.mvThemeCat_Nodes)
                    dpg.add_theme_color(dpg.mvNodeCol_TitleBarHovered, hover,
                                        category=dpg.mvThemeCat_Nodes)
                    dpg.add_theme_color(dpg.mvNodeCol_TitleBarSelected, hover,
                                        category=dpg.mvThemeCat_Nodes)
            self._themes[btype] = theme

    def _build_ui(self) -> None:
        with dpg.window(tag="ac_root"):
            with dpg.group(horizontal=True):
                # --- linke Seitenleiste (Sequenz-Info + Palette + Eigenschaften) ---
                with dpg.child_window(width=310, tag="ac_left"):
                    self._build_loader()
                    dpg.add_separator()
                    dpg.add_group(tag=_SIDEBAR)
                    self._build_sidebar()
                # --- Canvas (Mitte, füllt den Rest) ---
                # node_editor wird in rebuild_canvas frisch erzeugt (DPG-Crashfix).
                dpg.add_child_window(tag="ac_center", border=False)

    def _build_loader(self) -> None:
        """Dropdown zum Laden einer gespeicherten Sequenz direkt im Editor."""
        dpg.add_text("Sequenz laden", color=(120, 180, 255))
        names = self._available_names()
        with dpg.group(horizontal=True):
            dpg.add_combo(items=names, default_value=self.graph.name if self.graph.name in names else "",
                          tag=_SEQ_PICK, width=-60)
            dpg.add_button(label="Neu", callback=self._on_new_sequence)
        dpg.add_button(label="Laden", width=-1, callback=self._on_load_sequence)

    def _available_names(self) -> list[str]:
        return sorted(name for name, _ in list_available_sequences())

    def _refresh_seq_pick(self) -> None:
        if dpg.does_item_exist(_SEQ_PICK):
            names = self._available_names()
            cur = self.graph.name if self.graph.name in names else (names[0] if names else "")
            dpg.configure_item(_SEQ_PICK, items=names, default_value=cur)

    def _on_load_sequence(self, *_):
        name = dpg.get_value(_SEQ_PICK) if dpg.does_item_exist(_SEQ_PICK) else ""
        if not name:
            self._set_status("Keine Sequenz gewählt.", color=(220, 180, 90))
            return
        if not self._confirm_discard("load"):
            return
        path = next((p for n, p in list_available_sequences() if n == name), None)
        seq = load_sequence_file(path) if path else None
        if not seq:
            self._set_status(f"Konnte '{name}' nicht laden.", color=(220, 90, 90))
            return
        self.graph = sequence_to_graph(seq)
        self.filepath = Path(path)
        self.selected = None
        self._reload_view()
        self._clear_dirty()
        self._set_status(f"Geladen: {name}")

    def _on_new_sequence(self, *_):
        import time
        from ...models import Sequence
        if not self._confirm_discard("new"):
            return
        base = f"Sequenz_{int(time.time())}"
        self.graph = sequence_to_graph(Sequence(name=base))
        self.filepath = Path(self.sequences_dir) / f"{sanitize_filename(base)}.json"
        self.selected = None
        self._reload_view()
        self._clear_dirty()
        self._set_status("Neue Sequenz - noch nicht gespeichert.", color=(220, 180, 90))

    def _reload_view(self) -> None:
        """Baut Seitenleiste, Canvas und Eigenschaften nach einem Sequenz-Wechsel neu auf."""
        if dpg.does_item_exist(_SIDEBAR):
            for child in dpg.get_item_children(_SIDEBAR, 1) or []:
                dpg.delete_item(child)
            self._build_sidebar()
        self._refresh_seq_pick()
        self.rebuild_canvas()
        self.refresh_properties()

    def _build_sidebar(self) -> None:
        g = self.graph
        # Alle Widgets in den _SIDEBAR-Container hängen (nicht ins ac_left direkt),
        # damit _reload_view die Seitenleiste sauber neu aufbauen kann.
        dpg.push_container_stack(_SIDEBAR)
        try:
            dpg.add_text("Sequenz", color=(120, 180, 255))

            def _on_name(s, a, u):
                g.name = a
                self._mark_dirty()
            dpg.add_input_text(label="Name", default_value=g.name, width=-90, callback=_on_name)

            def _on_cycles(s, a, u):
                g.total_cycles = max(0, int(a))
                self._mark_dirty()
            dpg.add_input_int(label="Zyklen (0=inf)", default_value=g.total_cycles,
                              width=-100, min_value=0, callback=_on_cycles)

            def _on_desc(s, a, u):
                g.description = a
                self._mark_dirty()
            dpg.add_input_text(label="Info", default_value=g.description, width=-60,
                               multiline=True, height=50, callback=_on_desc)

            dpg.add_separator()
            dpg.add_button(label="Speichern", width=-1, callback=self._on_save)
            dpg.add_text("", tag=_STATUS, color=(110, 200, 110))

            dpg.add_separator()
            dpg.add_text("Ziel-Lane für neue Blöcke", color=(120, 180, 255))
            dpg.add_combo(items=self._lane_names(), default_value=self._lane_names()[0],
                          tag=_LANE_PICK, width=-1)

            dpg.add_button(label="+ Loop-Phase", width=-1, callback=self._on_add_loop)

            dpg.add_separator()
            dpg.add_text("Punkte-Palette", color=(120, 180, 255))
            dpg.add_text("Klick fügt einen KLICK-Block\nin die Ziel-Lane ein.",
                         color=(150, 150, 150))
            with dpg.child_window(height=160, border=True):
                if not self.points:
                    dpg.add_text("Keine Punkte aufgenommen.", color=(150, 150, 150))
                for pt in self.points:
                    label = f"#{pt.id} {pt.name or ''} ({pt.x},{pt.y})".strip()
                    with dpg.group(horizontal=True):
                        if pt.color:
                            dpg.add_color_button(default_value=tuple(pt.color) + (255,),
                                                 width=18, height=18, no_border=True)
                        dpg.add_button(label=label, width=-1, user_data=pt,
                                       callback=self._on_add_point)

            dpg.add_separator()
            dpg.add_text("Eigenschaften", color=(120, 180, 255))
            dpg.add_group(tag=_PROPS_PANEL)
        finally:
            dpg.pop_container_stack()

    # --------------------------------------------------------- Hilfsfunktionen
    def _lane_names(self) -> list[str]:
        return [ln.name for ln in self.graph.lanes]

    def _lane_by_name(self, name: str) -> Lane | None:
        return next((ln for ln in self.graph.lanes if ln.name == name), None)

    def _target_lane(self) -> Lane:
        name = dpg.get_value(_LANE_PICK) if dpg.does_item_exist(_LANE_PICK) else None
        return self._lane_by_name(name) or self.graph.lanes[0]

    def _refresh_lane_pick(self) -> None:
        if dpg.does_item_exist(_LANE_PICK):
            names = self._lane_names()
            cur = dpg.get_value(_LANE_PICK)
            dpg.configure_item(_LANE_PICK, items=names,
                               default_value=cur if cur in names else names[0])

    def _set_status(self, text: str, color=(110, 200, 110)) -> None:
        if dpg.does_item_exist(_STATUS):
            dpg.set_value(_STATUS, text)
            dpg.configure_item(_STATUS, color=color)

    def _update_title(self) -> None:
        """Spiegelt das Dirty-Flag in den Viewport-Titel (Stern = ungespeichert)."""
        star = "*" if self._dirty else ""
        try:
            dpg.set_viewport_title(f"Node-Editor - {star}{self.graph.name}")
        except Exception:
            pass

    def _mark_dirty(self) -> None:
        if not self._dirty:
            self._dirty = True
            self._update_title()
        # Jede Änderung verwirft eine ausstehende Discard-Bestätigung wieder.
        self._pending_discard = None

    def _clear_dirty(self) -> None:
        self._dirty = False
        self._pending_discard = None
        self._update_title()

    def _confirm_discard(self, action: str) -> bool:
        """2-Klick-Schutz vor Datenverlust bei Laden/Neu mit ungespeicherten Änderungen.

        Gibt True zurück wenn ausgeführt werden darf; sonst (erster Klick) wird
        nur eine Warnung gesetzt und der Aufrufer soll abbrechen.
        """
        if not self._dirty:
            return True
        if self._pending_discard == action:
            self._pending_discard = None
            return True
        self._pending_discard = action
        self._set_status("Ungespeicherte Aenderungen - nochmal klicken zum Verwerfen.",
                         color=(220, 180, 90))
        return False

    # --------------------------------------------------------------- Callbacks
    def _find_empty_scan_block(self) -> str | None:
        """Sucht einen Scan-Block mit leerem Namen.

        Ein leerer Scan-Name würde beim Executor (Truthiness-Dispatch in
        runtime/steps.py) durchfallen und der Block stillschweigend zu einem
        Klick auf (0,0) degradieren. Gibt eine Beschreibung des ersten solchen
        Blocks zurück, sonst None.
        """
        attr_by_type = {
            BLOCK_ITEM_SCAN: "item_scan",
            BLOCK_ICON_SCAN: "icon_scan",
            BLOCK_BOSS_SCAN: "boss_scan",
            BLOCK_BOSS_WATCHER: "boss_watcher",
        }
        for lane in self.graph.lanes:
            for row, step in enumerate(lane.steps, start=1):
                btype = block_type(step)
                attr = attr_by_type.get(btype)
                if attr is not None and not (getattr(step, attr) or "").strip():
                    return f"{BLOCK_LABELS[btype]} in '{lane.name}' (Block #{row})"
        return None

    def _on_save(self, *_):
        if not (self.graph.name or "").strip():
            self._set_status("Sequenz-Name fehlt - Speichern abgebrochen.",
                             color=(220, 90, 90))
            return
        empty = self._find_empty_scan_block()
        if empty:
            self._set_status(f"Scan ohne Namen: {empty} - Speichern abgebrochen.",
                             color=(220, 90, 90))
            return

        # Datei folgt dem (sanitisierten) Sequenz-Namen. Bei Umbenennung wird die
        # alte Datei nach erfolgreichem Speichern entfernt (sonst Duplikate).
        old_path = self.filepath
        new_path = Path(self.sequences_dir) / f"{sanitize_filename(self.graph.name)}.json"
        renamed = new_path != old_path

        seq = graph_to_sequence(self.graph)
        ok = save_sequence_file(seq, new_path)
        if not ok:
            self._set_status("Speichern fehlgeschlagen!", color=(220, 90, 90))
            return

        self.filepath = new_path
        msg = f"Gespeichert: {new_path.name}"
        if renamed and old_path.exists():
            try:
                os.remove(old_path)
                msg = f"Umbenannt -> {new_path.name} (alte Datei entfernt)"
            except OSError:
                msg = f"Gespeichert: {new_path.name} (alte Datei {old_path.name} blieb)"
        self._clear_dirty()
        self._refresh_seq_pick()
        self._set_status(msg)

    def _on_add_loop(self, *_):
        lane = self.graph.add_loop_lane()
        self._mark_dirty()
        self._refresh_lane_pick()
        if dpg.does_item_exist(_LANE_PICK):
            dpg.set_value(_LANE_PICK, lane.name)
        self.rebuild_canvas()

    def _on_add_point(self, sender, app_data, user_data):
        lane = self._target_lane()
        self.graph.add_step(lane, step_from_point(user_data))
        self.selected = (lane, len(lane.steps) - 1)
        self._mark_dirty()
        self.rebuild_canvas()
        self.refresh_properties()

    def _on_add_blank(self, sender, app_data, user_data):
        lane: Lane = user_data
        self.graph.add_step(lane, SequenceStep(x=0, y=0, delay_before=0.0))
        self.selected = (lane, len(lane.steps) - 1)
        self._mark_dirty()
        self.rebuild_canvas()
        self.refresh_properties()

    def _on_select(self, sender, app_data, user_data):
        self.selected = user_data
        self.rebuild_canvas()
        self.refresh_properties()

    def _on_move(self, sender, app_data, user_data):
        lane, idx, delta = user_data
        new_idx = self.graph.move_step(lane, idx, delta)
        self.selected = (lane, new_idx)
        self._mark_dirty()
        self.rebuild_canvas()
        self.refresh_properties()

    def _on_delete(self, sender, app_data, user_data):
        lane, idx = user_data
        self.graph.delete_step(lane, idx)
        self.selected = None
        self._mark_dirty()
        self.rebuild_canvas()
        self.refresh_properties()

    def _on_delete_lane(self, sender, app_data, user_data):
        lane: Lane = user_data
        self.graph.delete_loop_lane(lane)
        self.selected = None
        self._mark_dirty()
        self._refresh_lane_pick()
        self.rebuild_canvas()
        self.refresh_properties()

    def _on_repeat(self, sender, app_data, user_data):
        lane: Lane = user_data
        lane.repeat = max(1, int(app_data))
        # Lane-Header-Label sofort aktualisieren (sonst zeigt es die alte xN an).
        tag = self._lane_header_tag(lane)
        if dpg.does_item_exist(tag):
            dpg.configure_item(tag, label=self._lane_header_title(lane))
        self._mark_dirty()

    def _on_schedule(self, sender, app_data, user_data):
        lane: Lane = user_data
        raw = (app_data or "").strip()
        if not raw:
            lane.scheduled_start = None
            self._mark_dirty()
            return
        m = re.fullmatch(r"(\d{1,2}):(\d{2})", raw)
        if not m:
            self._set_status(f"Ungueltige Startzeit '{raw}' - Format HH:MM.",
                             color=(220, 180, 90))
            return
        hh, mm = int(m.group(1)), int(m.group(2))
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            self._set_status(f"Startzeit '{raw}' ausserhalb 00:00-23:59.",
                             color=(220, 180, 90))
            return
        lane.scheduled_start = f"{hh:02d}:{mm:02d}"
        self._mark_dirty()

    # --------------------------------------------------------------- Rendering
    def refresh_properties(self) -> None:
        step = None
        lane = None
        if self.selected:
            lane, idx = self.selected
            if 0 <= idx < len(lane.steps):
                step = lane.steps[idx]
            else:
                self.selected = None
        build_properties_panel(
            _PROPS_PANEL, step, lane, self.graph, self.points,
            on_changed=self._on_step_changed,
            on_structure=self._on_structure_changed,
        )

    def _on_step_changed(self) -> None:
        # Nur das Label des ausgewählten Nodes betroffen → günstiger Voll-Rebuild.
        self._mark_dirty()
        self.rebuild_canvas()

    def _on_structure_changed(self) -> None:
        self._mark_dirty()
        self.rebuild_canvas()
        self.refresh_properties()

    def rebuild_canvas(self) -> None:
        # Ganzen Editor verwerfen und neu anlegen (statt einzelne Nodes zu
        # löschen — das würde mit bestehenden Links zum Absturz führen).
        if dpg.does_item_exist(_NODE_EDITOR):
            dpg.delete_item(_NODE_EDITOR)
        dpg.add_node_editor(
            tag=_NODE_EDITOR, parent="ac_center", minimap=True,
            minimap_location=dpg.mvNodeMiniMap_Location_BottomRight,
        )

        links: list[tuple[int, int]] = []  # (out_attr, in_attr) Paare

        for col, lane in enumerate(self.graph.lanes):
            x = _X0 + col * _COL_W
            # Lane-Kopf-Node
            self._build_lane_header(lane, x, _Y0)

            prev_out = None
            for row, step in enumerate(lane.steps):
                y = _Y0 + (row + 1) * _ROW_H
                in_attr, out_attr = self._build_step_node(lane, row, step, x, y)
                if prev_out is not None:
                    links.append((prev_out, in_attr))
                prev_out = out_attr

        # Verbindungen zeichnen (nach allen Nodes)
        for out_attr, in_attr in links:
            dpg.add_node_link(out_attr, in_attr, parent=_NODE_EDITOR)

    def _lane_header_tag(self, lane: Lane) -> str:
        """Stabiler Tag für den Lane-Kopf-Node (für In-place-Label-Update)."""
        return f"ac_lane_hdr_{id(lane)}"

    def _lane_header_title(self, lane: Lane) -> str:
        # × → x: das ×-Zeichen rendert mit dem DPG-Default-Font als "?".
        if lane.is_loop():
            return f"{lane.name}  (x{lane.repeat})"
        return lane.name

    def _build_lane_header(self, lane: Lane, x: int, y: int) -> None:
        title = self._lane_header_title(lane)
        with dpg.node(label=title, parent=_NODE_EDITOR, pos=[x, y],
                      tag=self._lane_header_tag(lane)):
            with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Static):
                dpg.add_button(label="+ Block", width=160, user_data=lane,
                               callback=self._on_add_blank)
                if lane.is_loop():
                    dpg.add_input_int(label="x", default_value=lane.repeat, width=90,
                                      min_value=1, user_data=lane, callback=self._on_repeat)
                    dpg.add_input_text(label="Start", default_value=lane.scheduled_start or "",
                                       width=90, hint="HH:MM", user_data=lane,
                                       callback=self._on_schedule)
                    dpg.add_button(label="Lane löschen", width=160, user_data=lane,
                                   callback=self._on_delete_lane)

    def _build_step_node(self, lane: Lane, row: int, step: SequenceStep,
                         x: int, y: int) -> tuple[int, int]:
        btype = block_type(step)
        label = f"{BLOCK_LABELS[btype]}"
        if step.name:
            label += f": {step.name}"
        is_sel = self.selected == (lane, row)
        with dpg.node(label=label, parent=_NODE_EDITOR, pos=[x, y]) as node_id:
            in_attr = dpg.add_node_attribute(attribute_type=dpg.mvNode_Attr_Input)
            with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Static):
                # ELSE-Suffix aus der Beschreibung entfernen – wird separat als
                # amber-farbene Zeile angezeigt.
                desc = _ascii(str(step)).split(" | ELSE:")[0]
                dpg.add_text(_wrap(desc, 34), color=(210, 210, 210))
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Bearbeiten", user_data=(lane, row),
                                   callback=self._on_select)
                    dpg.add_button(label=" ^ ", user_data=(lane, row, -1),
                                   callback=self._on_move)
                    dpg.add_button(label=" v ", user_data=(lane, row, 1),
                                   callback=self._on_move)
                    dpg.add_button(label=" X ", user_data=(lane, row),
                                   callback=self._on_delete)
                if step.else_config:
                    dpg.add_text(_else_label(step.else_config), color=(230, 180, 90))
            out_attr = dpg.add_node_attribute(attribute_type=dpg.mvNode_Attr_Output)
        # Theme (Farbe) binden
        if btype in self._themes:
            dpg.bind_item_theme(node_id, self._themes[btype])
        if is_sel:
            # ausgewählten Node optisch hervorheben (Node im Editor selektieren)
            try:
                dpg.configure_item(node_id, label=f"> {label}")
            except Exception:
                pass
        return in_attr, out_attr


def _wrap(text: str, width: int) -> str:
    """Einfaches Wort-Wrapping für die Node-Beschreibung."""
    words = text.split()
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            if cur:
                lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return "\n".join(lines)


def _ascii(text: str) -> str:
    """Ersetzt Unicode-Zeichen die DPG nicht darstellen kann durch ASCII-Alternativen."""
    return (text
            .replace("→", "->")
            .replace("∞", "inf")
            .replace("≥", ">=")
            .replace("×", "x"))


def _else_label(ec) -> str:
    """Lesbarer ELSE-Text für den Block-Node."""
    from autoclicker.models import ELSE_CLICK, ELSE_KEY, ELSE_SKIP, ELSE_SKIP_CYCLE, ELSE_RESTART
    if ec.action == ELSE_CLICK:
        target = ec.name or f"({ec.x},{ec.y})"
        return f"ELSE: klicke {target}, weiter"
    if ec.action == ELSE_KEY:
        return f"ELSE: Taste '{ec.key}', weiter"
    if ec.action == ELSE_SKIP:
        return "ELSE: diesen Schritt überspringen"
    if ec.action == ELSE_SKIP_CYCLE:
        return "ELSE: Zyklus abbrechen"
    if ec.action == ELSE_RESTART:
        return "ELSE: Sequenz neu starten"
    return f"ELSE: {ec.action}"
