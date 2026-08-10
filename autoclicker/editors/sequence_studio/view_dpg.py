"""
Dear PyGui Ansicht für den visuellen Sequenz-Editor.

Zeigt die Phasen (INIT / Loop-Phasen / END) als Spalten nebeneinander, jede eine
Liste ihrer Schritte. Links: Sequenz-Einstellungen, Punkte-Palette, Speichern und
die Eigenschaften des gewählten Schritts.

**Warum Listen und kein Node-Graph.** Bis Schema 4 war das hier ein
`dpg.node_editor` mit frei liegenden Kacheln — und das war der Grund, warum sich
der Editor unbedienbar anfühlte: ein Node-Graph verspricht mit jedem Pixel, dass
man Verbindungen ziehen darf. Es gab aber keinen einzigen Link-Callback (die
Pfeile waren Dekoration), die Positionen wurden bei jedem Neuaufbau aus
(Spalte, Zeile) neu gerechnet (verschobene Blöcke sprangen zurück), und
umsortiert wurde mit `^`/`v` — ein Schritt pro Klick, jedes Mal mit komplettem
Neuaufbau des Editors.

Eine Sequenz **ist** kein Graph: pro Phase ist sie eine lineare Liste, und die
einzige Verzweigung (`else_config`) ist ein Attribut, keine Kante. Die Liste
verspricht deshalb nur, was sie einlösen kann — kann das dafür richtig: Ziehen
sortiert um, auch über Phasengrenzen hinweg (das kann der Konsolen-Editor bis
heute nicht), Mehrfachauswahl mit STRG, und 50 aufgenommene Schritte passen
untereinander auf einen Blick.

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
    SequenceBoard, Lane, LANE_INIT, LANE_LOOP, LANE_END,
    BLOCK_LABELS, BLOCK_COLORS,
    BLOCK_ITEM_SCAN, BLOCK_ICON_SCAN, BLOCK_BOSS_SCAN, BLOCK_BOSS_WATCHER,
    block_type, sequence_to_board, board_to_sequence,
    load_palette_points, save_palette_points, step_from_point,
)
from .panels import build_properties_panel

# Feste Tags
_PROPS_PANEL = "ac_props_panel"
_STATUS = "ac_status_text"
_LANE_PICK = "ac_lane_pick"
_SIDEBAR = "ac_sidebar_body"
_SEQ_PICK = "ac_seq_pick"

# Breite einer Phasen-Spalte. Der Rest (Zeilenhoehe, Ursprung) entfiel mit dem
# frueheren Node-Canvas: eine Liste setzt ihre Zeilen selbst, ohne Positionsrechnung.
_COL_W = 270


class SequenceStudioApp:
    """Hält den Editor-Zustand und rendert die Phasen-Spalten."""

    def __init__(self, seq, filepath: Path, sequences_dir: str):
        self.board: SequenceBoard = sequence_to_board(seq)
        self.filepath = Path(filepath)
        self.sequences_dir = sequences_dir
        self.points = load_palette_points(sequences_dir)
        # Auswahl lebt immer in GENAU EINER Phase (siehe _on_row_click).
        self.sel_lane: Lane | None = None
        self.sel_rows: set[int] = set()
        self._dirty = False
        # Welche Aktion (_on_load_sequence/_on_new_sequence) auf Bestätigung
        # wartet, weil ungespeicherte Änderungen existieren (2-Klick-Schutz).
        self._pending_discard: str | None = None

    # ---------------------------------------------------------------- Setup
    def run(self) -> None:
        dpg.create_context()
        self._build_ui()
        dpg.create_viewport(title=f"Sequenz-Studio – {self.board.name}", width=1400, height=820)
        dpg.setup_dearpygui()
        dpg.show_viewport()
        dpg.set_primary_window("ac_root", True)
        self._update_title()
        self.rebuild_board()
        self.refresh_properties()
        dpg.start_dearpygui()
        dpg.destroy_context()

    def _build_ui(self) -> None:
        with dpg.window(tag="ac_root"):
            with dpg.group(horizontal=True):
                # --- linke Seitenleiste (Sequenz-Info + Palette + Eigenschaften) ---
                with dpg.child_window(width=310, tag="ac_left"):
                    self._build_loader()
                    dpg.add_separator()
                    dpg.add_group(tag=_SIDEBAR)
                    self._build_sidebar()
                # --- Phasen-Spalten (Mitte, füllen den Rest) ---
                # Inhalt entsteht in rebuild_board().
                dpg.add_child_window(tag="ac_center", border=False)

    def _build_loader(self) -> None:
        """Dropdown zum Laden einer gespeicherten Sequenz direkt im Editor."""
        dpg.add_text("Sequenz laden", color=(120, 180, 255))
        names = self._available_names()
        with dpg.group(horizontal=True):
            dpg.add_combo(items=names, default_value=self.board.name if self.board.name in names else "",
                          tag=_SEQ_PICK, width=-60)
            dpg.add_button(label="Neu", callback=self._on_new_sequence)
        dpg.add_button(label="Laden", width=-1, callback=self._on_load_sequence)

    def _available_names(self) -> list[str]:
        return sorted(name for name, _ in list_available_sequences())

    def _refresh_seq_pick(self) -> None:
        if dpg.does_item_exist(_SEQ_PICK):
            names = self._available_names()
            cur = self.board.name if self.board.name in names else (names[0] if names else "")
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
        self.board = sequence_to_board(seq)
        self.filepath = Path(path)
        self._clear_selection()
        self._reload_view()
        self._clear_dirty()
        self._set_status(f"Geladen: {name}")

    def _on_new_sequence(self, *_):
        import time
        from ...models import Sequence
        if not self._confirm_discard("new"):
            return
        base = f"Sequenz_{int(time.time())}"
        self.board = sequence_to_board(Sequence(name=base))
        self.filepath = Path(self.sequences_dir) / f"{sanitize_filename(base)}.json"
        self._clear_selection()
        self._reload_view()
        self._clear_dirty()
        self._set_status("Neue Sequenz - noch nicht gespeichert.", color=(220, 180, 90))

    def _reload_view(self) -> None:
        """Baut Seitenleiste, Spalten und Eigenschaften nach einem Sequenz-Wechsel neu auf."""
        if dpg.does_item_exist(_SIDEBAR):
            for child in dpg.get_item_children(_SIDEBAR, 1) or []:
                dpg.delete_item(child)
            self._build_sidebar()
        self._refresh_seq_pick()
        self.rebuild_board()
        self.refresh_properties()

    def _build_sidebar(self) -> None:
        board = self.board
        # Alle Widgets in den _SIDEBAR-Container hängen (nicht ins ac_left direkt),
        # damit _reload_view die Seitenleiste sauber neu aufbauen kann.
        dpg.push_container_stack(_SIDEBAR)
        try:
            dpg.add_text("Sequenz", color=(120, 180, 255))

            def _on_name(s, a, u):
                board.name = a
                self._mark_dirty()
            dpg.add_input_text(label="Name", default_value=board.name, width=-90, callback=_on_name)

            def _on_cycles(s, a, u):
                board.total_cycles = max(0, int(a))
                self._mark_dirty()
            dpg.add_input_int(label="Zyklen (0=inf)", default_value=board.total_cycles,
                              width=-100, min_value=0, callback=_on_cycles)

            def _on_desc(s, a, u):
                board.description = a
                self._mark_dirty()
            dpg.add_input_text(label="Info", default_value=board.description, width=-60,
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
                        btn = dpg.add_button(label=label, width=-1, user_data=pt,
                                             callback=self._on_add_point)
                        if pt.source:
                            with dpg.tooltip(btn):
                                dpg.add_text(pt.source, color=(150, 150, 150))

            dpg.add_separator()
            dpg.add_text("Eigenschaften", color=(120, 180, 255))
            dpg.add_group(tag=_PROPS_PANEL)
        finally:
            dpg.pop_container_stack()

    # --------------------------------------------------------- Hilfsfunktionen
    def _lane_names(self) -> list[str]:
        return [ln.name for ln in self.board.lanes]

    def _lane_by_name(self, name: str) -> Lane | None:
        return next((ln for ln in self.board.lanes if ln.name == name), None)

    def _target_lane(self) -> Lane:
        name = dpg.get_value(_LANE_PICK) if dpg.does_item_exist(_LANE_PICK) else None
        return self._lane_by_name(name) or self.board.lanes[0]

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
            dpg.set_viewport_title(f"Sequenz-Studio - {star}{self.board.name}")
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
        for lane in self.board.lanes:
            for row, step in enumerate(lane.steps, start=1):
                btype = block_type(step)
                attr = attr_by_type.get(btype)
                if attr is not None and not (getattr(step, attr) or "").strip():
                    return f"{BLOCK_LABELS[btype]} in '{lane.name}' (Block #{row})"
        return None

    def _on_save(self, *_):
        if not (self.board.name or "").strip():
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
        new_path = Path(self.sequences_dir) / f"{sanitize_filename(self.board.name)}.json"
        renamed = new_path != old_path

        seq = board_to_sequence(self.board)
        # Punkte ZUERST: die Sequenz verweist nur noch auf sie. Schlaegt das fehl,
        # zeigten frisch angelegte Referenzen ins Leere - dann lieber gar nicht
        # speichern, als eine Sequenz mit toten Verweisen zu hinterlassen.
        if not save_palette_points(self.sequences_dir, self.points):
            self._set_status("points.json nicht schreibbar - nichts gespeichert.",
                             color=(220, 90, 90))
            return
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
        lane = self.board.add_loop_lane()
        self._mark_dirty()
        self._refresh_lane_pick()
        if dpg.does_item_exist(_LANE_PICK):
            dpg.set_value(_LANE_PICK, lane.name)
        self.rebuild_board()

    def _on_add_point(self, sender, app_data, user_data):
        lane = self._target_lane()
        self.board.add_step(lane, step_from_point(user_data))
        self._select_only(lane, len(lane.steps) - 1)
        self._mark_dirty()
        self.rebuild_board()
        self.refresh_properties()

    def _on_add_blank(self, sender, app_data, user_data):
        lane: Lane = user_data
        self.board.add_step(lane, SequenceStep(x=0, y=0, delay_before=0.0))
        self._select_only(lane, len(lane.steps) - 1)
        self._mark_dirty()
        self.rebuild_board()
        self.refresh_properties()

    def _on_delete_lane(self, sender, app_data, user_data):
        lane: Lane = user_data
        self.board.delete_loop_lane(lane)
        self._clear_selection()
        self._mark_dirty()
        self._refresh_lane_pick()
        self.rebuild_board()
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
    #
    # Phasen als Spalten, jede eine Liste. Warum keine Nodes mehr: siehe
    # Modul-Docstring - kurz, eine Sequenz ist pro Phase eine lineare Liste, und
    # die einzige Verzweigung (else_config) ist ein Attribut, keine Kante.

    def refresh_properties(self) -> None:
        """Zeigt den gewaehlten Schritt - aber nur, wenn es genau EINER ist."""
        step = lane = None
        if self.sel_lane is not None and len(self.sel_rows) == 1:
            idx = next(iter(self.sel_rows))
            if 0 <= idx < len(self.sel_lane.steps):
                lane, step = self.sel_lane, self.sel_lane.steps[idx]
        build_properties_panel(
            _PROPS_PANEL, step, lane, self.board, self.points,
            on_changed=self._on_step_changed,
            on_structure=self._on_structure_changed,
        )

    def _on_step_changed(self) -> None:
        self._mark_dirty()
        self.rebuild_board()

    def _on_structure_changed(self) -> None:
        self._mark_dirty()
        self.rebuild_board()
        self.refresh_properties()

    # ---- Auswahl ---------------------------------------------------------
    def _select_only(self, lane: Lane, row: int) -> None:
        self.sel_lane, self.sel_rows = lane, {row}

    def _clear_selection(self) -> None:
        self.sel_lane, self.sel_rows = None, set()

    def _on_row_click(self, sender, app_data, user_data) -> None:
        """Klick = nur dieser Schritt. STRG+Klick = dazu bzw. weg.

        Die Auswahl lebt immer in GENAU EINER Phase: sobald in einer anderen Spalte
        geklickt wird, faengt sie dort neu an. Das haelt die Sammelaktionen
        eindeutig - eine Auswahl quer ueber INIT und END haette bei "eine Position
        hoch" keine sinnvolle Bedeutung.
        """
        lane, row = user_data
        strg = dpg.is_key_down(dpg.mvKey_LControl) or dpg.is_key_down(dpg.mvKey_RControl)
        if strg and self.sel_lane is lane:
            self.sel_rows.symmetric_difference_update({row})
            if not self.sel_rows:
                self._clear_selection()
        else:
            self._select_only(lane, row)
        self.rebuild_board()
        self.refresh_properties()

    def _sel_sorted(self) -> list[int]:
        return sorted(self.sel_rows)

    # ---- Sammelaktionen --------------------------------------------------
    def _on_sel_delete(self, sender, app_data, user_data) -> None:
        lane: Lane = user_data
        if self.sel_lane is not lane or not self.sel_rows:
            return
        # Von hinten loeschen, sonst verschieben sich die noch offenen Indizes.
        for idx in sorted(self.sel_rows, reverse=True):
            self.board.delete_step(lane, idx)
        n = len(self.sel_rows)
        self._clear_selection()
        self._mark_dirty()
        self.rebuild_board()
        self.refresh_properties()
        self._set_status(f"{n} Block/Bloecke geloescht.")

    def _on_sel_move(self, sender, app_data, user_data) -> None:
        """Verschiebt die Auswahl als BLOCK um eine Position."""
        lane, delta = user_data
        if self.sel_lane is not lane or not self.sel_rows:
            return
        rows = self._sel_sorted()
        if delta < 0 and rows[0] == 0:
            return
        if delta > 0 and rows[-1] == len(lane.steps) - 1:
            return
        # Beim Hochschieben von vorne abarbeiten, beim Runterschieben von hinten -
        # sonst ueberholen sich die Elemente gegenseitig.
        folge = rows if delta < 0 else list(reversed(rows))
        self.sel_rows = {self.board.move_step(lane, idx, delta) for idx in folge}
        self._mark_dirty()
        self.rebuild_board()
        self.refresh_properties()

    def _verschiebe(self, quelle: Lane, rows: list[int], ziel: Lane, at: int) -> None:
        """Traegt `rows` aus `quelle` in `ziel` ab Position `at` ein.

        Der eine Weg fuer beides: Umsortieren innerhalb einer Phase und Verschieben
        zwischen Phasen. Letzteres gibt es im Konsolen-Editor gar nicht - eine
        Aufnahme nachtraeglich in INIT/LOOP/END aufzuteilen hiess dort loeschen und
        neu anlegen.
        """
        schritte = [quelle.steps[i] for i in sorted(rows)]
        if not schritte:
            return
        # Wie viele der entfernten Schritte lagen VOR der Zielposition? Um so viele
        # rutscht sie nach vorne - aber nur, wenn aus derselben Phase entfernt wird.
        if quelle is ziel:
            at -= sum(1 for i in rows if i < at)
        for i in sorted(rows, reverse=True):
            self.board.delete_step(quelle, i)
        at = max(0, min(at, len(ziel.steps)))
        for versatz, schritt in enumerate(schritte):
            self.board.add_step(ziel, schritt, at=at + versatz)
        self.sel_lane = ziel
        self.sel_rows = set(range(at, at + len(schritte)))
        self._mark_dirty()

    def _on_drop(self, sender, app_data, user_data) -> None:
        """Ziel eines Drag&Drop. `app_data` ist die drag_data der Quelle."""
        if not app_data:
            return
        ziel_lane, ziel_row = user_data
        quelle_lane, quelle_row = app_data
        # Wird ein Schritt aus der aktuellen Auswahl gezogen, wandert die ganze
        # Auswahl mit - sonst nur der angefasste.
        rows = (self._sel_sorted()
                if (self.sel_lane is quelle_lane and quelle_row in self.sel_rows)
                else [quelle_row])
        self._verschiebe(quelle_lane, rows, ziel_lane, ziel_row)
        self.rebuild_board()
        self.refresh_properties()

    # ---- Aufbau ----------------------------------------------------------
    def rebuild_board(self) -> None:
        """Baut die Spalten neu.

        Billig genug fuer jeden Klick - anders als der alte node_editor, der komplett
        verworfen werden musste, weil das Loeschen einzelner Nodes mit bestehenden
        Links abstuerzte.
        """
        for child in dpg.get_item_children("ac_center", 1) or []:
            dpg.delete_item(child)
        with dpg.group(horizontal=True, parent="ac_center"):
            for lane in self.board.lanes:
                self._build_phase_column(lane)

    def _build_phase_column(self, lane: Lane) -> None:
        gewaehlt = self.sel_lane is lane and bool(self.sel_rows)
        with dpg.child_window(width=_COL_W, border=True):
            titel = lane.name + (f"   x{lane.repeat}" if lane.is_loop() else "")
            dpg.add_text(titel, color=_LANE_FARBE.get(lane.kind, (200, 200, 200)))
            dpg.add_text(f"{len(lane.steps)} Schritt(e)", color=(130, 130, 130))
            dpg.add_separator()

            with dpg.group(horizontal=True):
                dpg.add_button(label="+ Block", width=78, user_data=lane,
                               callback=self._on_add_blank)
                dpg.add_button(label=" ^ ", user_data=(lane, -1),
                               callback=self._on_sel_move, enabled=gewaehlt)
                dpg.add_button(label=" v ", user_data=(lane, 1),
                               callback=self._on_sel_move, enabled=gewaehlt)
                dpg.add_button(label=" X ", user_data=lane,
                               callback=self._on_sel_delete, enabled=gewaehlt)
            if lane.is_loop():
                with dpg.group(horizontal=True):
                    dpg.add_input_int(label="x", default_value=lane.repeat, width=70,
                                      min_value=1, user_data=lane,
                                      callback=self._on_repeat)
                    dpg.add_input_text(default_value=lane.scheduled_start or "",
                                       width=60, hint="HH:MM", user_data=lane,
                                       callback=self._on_schedule)
                dpg.add_button(label="Phase loeschen", width=-1, user_data=lane,
                               callback=self._on_delete_lane)
            dpg.add_separator()

            with dpg.child_window(border=False):
                if not lane.steps:
                    dpg.add_text("(leer)", color=(120, 120, 120))
                for row, step in enumerate(lane.steps):
                    self._build_row(lane, row, step)
                # Ablage unter der Liste: haengt ans Ende an. Ohne sie gaebe es keine
                # Moeglichkeit, einen Schritt HINTER den letzten zu ziehen.
                ende = dpg.add_selectable(label="", span_columns=True,
                                          user_data=(lane, len(lane.steps)))
                dpg.configure_item(ende, drop_callback=self._on_drop)

    def _build_row(self, lane: Lane, row: int, step: SequenceStep) -> None:
        btype = block_type(step)
        ist_gewaehlt = self.sel_lane is lane and row in self.sel_rows
        with dpg.group(horizontal=True):
            dpg.add_text(f"{row + 1:>3}", color=(120, 120, 120))
            # Farbquadrat statt eingefaerbter Titelzeile: in einer Liste traegt die
            # Farbe dieselbe Information auf einem Bruchteil der Flaeche.
            dpg.add_color_button(
                default_value=tuple(BLOCK_COLORS.get(btype, (120, 120, 120))) + (255,),
                width=12, height=12, no_border=True, no_drag_drop=True)
            sel = dpg.add_selectable(label=_zeilen_text(step, btype),
                                     default_value=ist_gewaehlt, span_columns=True,
                                     user_data=(lane, row), callback=self._on_row_click)
        with dpg.drag_payload(parent=sel, drag_data=(lane, row)):
            dpg.add_text(_zeilen_text(step, btype))
        dpg.configure_item(sel, drop_callback=self._on_drop)
        with dpg.tooltip(sel):
            dpg.add_text(_wrap(_ascii(str(step)), 60))


# Farbe pro Phasenart - INIT/LOOP/END sollen sich auf einen Blick unterscheiden.
_LANE_FARBE = {
    LANE_INIT: (120, 220, 120),
    LANE_LOOP: (220, 160, 220),
    LANE_END: (120, 200, 220),
}


def _zeilen_text(step: SequenceStep, btype: str) -> str:
    """Eine Zeile pro Schritt: Typ, Ziel, Wartezeit - in dieser Reihenfolge.

    Bewusst knapp: die vollstaendige Beschreibung steht im Tooltip und im
    Eigenschaften-Feld. In der Liste zaehlt, dass 50 Zeilen untereinander passen.
    """
    teile = [BLOCK_LABELS.get(btype, "?")]
    if step.name:
        teile.append(_ascii(step.name))
    elif not step.wait_only and not step.screenshot_only and (step.x or step.y):
        teile.append(f"({step.x},{step.y})")
    if step.delay_before:
        teile.append(f"+{step.delay_before:g}s")
    if step.verify_condition is not None:
        teile.append("[prueft]")
    if step.else_config is not None:
        teile.append("[else]")
    return "  ".join(teile)


def _wrap(text: str, width: int) -> str:
    """Einfaches Wort-Wrapping fuer den Tooltip."""
    worte, zeilen, aktuell = text.split(), [], ""
    for w in worte:
        if len(aktuell) + len(w) + 1 > width:
            zeilen.append(aktuell)
            aktuell = w
        else:
            aktuell = f"{aktuell} {w}".strip()
    if aktuell:
        zeilen.append(aktuell)
    return "\n".join(zeilen)


def _ascii(text: str) -> str:
    """Ersetzt Zeichen, die der DPG-Standardfont als '?' rendert."""
    return (text.replace("→", "->").replace("×", "x")
                .replace("ü", "ue").replace("ö", "oe").replace("ä", "ae")
                .replace("Ü", "Ue").replace("Ö", "Oe").replace("Ä", "Ae")
                .replace("ß", "ss"))
