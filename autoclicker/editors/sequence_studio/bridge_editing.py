"""Editor-Kommandos für Phasen, Blöcke, Auswahl und Punkte."""

import copy
import re
import time
from typing import Optional

from ...models import BLOCK_WAIT_CLICK, SequenceStep, WaitCondition
from .bridge_contract import (
    ELSE_ACTIONS,
    TRIGGER_PRESENT,
    TRIGGER_NONE,
    TRIGGER_GONE,
    WAIT_TIMEOUT,
    _FIELDS,
    _blocks,
    _rgb,
    else_applies,
)
from .model import (
    BLOCK_LABELS,
    LANE_LOOP,
    Lane,
    PalettePoint,
    ensure_else,
    set_block_type,
    step_from_point,
)


# Wie viele Stände das Rückgängig hält — dieselbe Tiefe wie im Scans-Reiter.
EDIT_UNDO_DEPTH = 30
# Innerhalb dieser Spanne gilt eine wiederholte Aktion derselben Gruppe (eine
# gehaltene Pfeiltaste) als EIN Schritt.
EDIT_GROUP_SECONDS = 1.5


class BridgeEditingMixin:
    """Bearbeitet die Sequenz ausschließlich über klar benannte Kommandos.

    **Rückgängig ist ein vollständiger Abzug, kein Rückwärts-Schritt** — dieselbe
    Bauart wie `_remember()` im Scans-Reiter, und aus demselben Grund: fast
    jede Aktion hier rührt an mehrere Stellen (ein gelöschter Block nimmt
    seinen Punkt mit, ein Typwechsel räumt das ELSE), und ein vergessener
    Rückwärts-Schritt drehte die Daten halb zurück. Der Abzug umfasst Board,
    Punkte und Auswahl; er entsteht in `_changed()`, also bei JEDER Änderung,
    ohne dass ein Kommando daran denken muss. Speichern und Laden leeren den
    Stapel: ein Zurück über einen Ladevorgang hinweg beschriebe einen Stand,
    den es nicht mehr gibt.
    """

    # ------------------------------------------------------------ Rückgängig

    def _edit_init(self) -> None:
        self._edit_undo: list = []          # (was, Abzug) — ältester zuerst
        self._edit_redo: list = []
        self._edit_current: dict = self._edit_state()
        self._edit_offer = False
        self._edit_group: Optional[str] = None
        self._edit_time = 0.0

    def _edit_selection(self) -> tuple:
        """Die Auswahl als Indizes — ein Abzug darf keine Lane-Objekte halten."""
        others = [(self._lane_index(lane), set(rows)) for lane, rows in self.sel_other]
        return (self._sel_index(), set(self.sel_rows), self.sel_anchor,
                [(index, rows) for index, rows in others if index is not None])

    def _edit_state(self) -> dict:
        """Ein vollständiger Abzug: Board, Punkte und Auswahl (als Indizes)."""
        return {"board": copy.deepcopy(self.board),
                "points": copy.deepcopy(self.points),
                "sel": self._edit_selection()}

    def _edit_install(self, stamp: dict) -> None:
        """Stellt einen Abzug wieder her — als Kopie, damit der Stapel unberührt bleibt."""
        self.board = copy.deepcopy(stamp["board"])
        self.points = copy.deepcopy(stamp["points"])
        lane_index, rows, anchor, others = stamp["sel"]
        lanes = self.board.lanes
        self.sel_lane = (lanes[lane_index]
                         if lane_index is not None and lane_index < len(lanes) else None)
        self.sel_rows = set(rows) if self.sel_lane is not None else set()
        self.sel_other = [(lanes[index], set(r)) for index, r in others if index < len(lanes)]
        self.sel_anchor = anchor
        self._points_apply()
        self._dirty = True

    def _edit_commit(self, what: str = "", group: Optional[str] = None) -> None:
        """Legt den Stand VOR dieser Änderung ab und merkt sich den neuen.

        `group`: eine gehaltene Pfeiltaste ist EIN Verschieben — nur der erste
        Schritt einer Serie kommt auf den Stapel (dieselbe Regel wie `counts`
        beim Schieben der Slots), sonst läge er nach zwei Sekunden voll.
        """
        now = time.time()
        merged = (group is not None and group == self._edit_group
                  and now - self._edit_time < EDIT_GROUP_SECONDS)
        if not merged:
            # `_edit_current` trägt die Auswahl der letzten Momentaufnahme —
            # also die VOR dieser Änderung (Auswählen legt keinen Abzug ab,
            # `snapshot()` merkt sie sich). Nach dem Zurück steht man damit
            # wieder auf dem, was man gerade gelöscht hatte.
            self._edit_undo.append((what or "letzte Änderung", self._edit_current))
            del self._edit_undo[:-EDIT_UNDO_DEPTH]
            self._edit_redo = []
        self._edit_current = self._edit_state()
        self._edit_group, self._edit_time = group, now
        self._dirty = True

    def _edit_reset(self) -> None:
        """Nach Laden, Anlegen, Speichern, Import: der Stapel beschreibt nichts mehr."""
        self._edit_undo, self._edit_redo = [], []
        self._edit_current = self._edit_state()
        self._edit_offer = False
        self._edit_group = None

    def _edit_json(self) -> dict:
        return {"can": bool(self._edit_undo),
                "what": self._edit_undo[-1][0] if self._edit_undo else "",
                "redo": bool(self._edit_redo),
                "redo_what": self._edit_redo[-1][0] if self._edit_redo else "",
                # Die Meldung nach einer zerstörenden Aktion trägt den Rückweg
                # an sich — ein Klick, ohne die Tastenkombination zu kennen.
                "offer": self._edit_offer}

    def undo(self, data: Optional[dict] = None) -> dict:
        """Nimmt die letzte Änderung zurück (STRG+Z)."""
        if not self._edit_undo:
            return self._report("Nichts zum Rückgängigmachen.", "info")
        what, stamp = self._edit_undo.pop()
        self._edit_redo.append((what, self._edit_current))
        self._edit_current = stamp
        self._edit_install(stamp)
        self._edit_group = None
        return self._report(f"Rückgängig: {what}")

    def redo(self, data: Optional[dict] = None) -> dict:
        """Stellt die zuletzt zurückgenommene Änderung wieder her (STRG+Y)."""
        if not self._edit_redo:
            return self._report("Nichts zum Wiederherstellen.", "info")
        what, stamp = self._edit_redo.pop()
        self._edit_undo.append((what, self._edit_current))
        self._edit_current = stamp
        self._edit_install(stamp)
        self._edit_group = None
        return self._report(f"Wiederhergestellt: {what}")

    def _lane(self, index) -> Optional[Lane]:
        try:
            i = int(index)
        except (TypeError, ValueError):
            return None
        return self.board.lanes[i] if 0 <= i < len(self.board.lanes) else None

    def phase_append(self, data: Optional[dict] = None) -> dict:
        lane = self.board.add_loop_lane()
        return self._changed(f"Phase '{lane.name}' angelegt.")

    def phase_delete(self, data: dict) -> dict:
        lane = self._lane((data or {}).get("phase"))
        if lane is None or lane.kind != LANE_LOOP:
            return self._report("INIT und END lassen sich nicht löschen.", "warn")
        self.board.delete_loop_lane(lane)
        self._selection_clear()
        return self._changed(f"Phase '{lane.name}' gelöscht.", offer=True)

    def phase_set(self, data: dict) -> dict:
        """Name, Wiederholungen oder Startzeit einer Phase ändern."""
        data = data or {}
        lane = self._lane(data.get("phase"))
        if lane is None:
            return self._report("Phase nicht gefunden.", "err")
        field, value = data.get("field"), data.get("value")
        if field == "name":
            # Nur Loop-Phasen tragen einen Namen: INIT und END heissen in der Datei
            # gar nicht, `board_to_sequence()` wirft ihren Namen weg. Eine Umbenennung
            # dort anzunehmen hiesse, sie beim nächsten Öffnen still zu verlieren.
            if lane.kind != LANE_LOOP:
                return self._report("INIT und END tragen keinen eigenen Namen.", "warn")
            lane.name = str(value or "").strip() or lane.name
        elif field == "repeat":
            lane.repeat = max(1, int(value or 1))
        elif field == "start":
            raw = str(value or "").strip()
            if not raw:
                lane.scheduled_start = None
            else:
                m = re.fullmatch(r"(\d{1,2}):(\d{2})", raw)
                if not m:
                    return self._report(f"Startzeit '{raw}' — erwartet HH:MM.", "warn")
                hh, mm = int(m.group(1)), int(m.group(2))
                if not (0 <= hh <= 23 and 0 <= mm <= 59):
                    return self._report(f"Startzeit '{raw}' ausserhalb 00:00–23:59.", "warn")
                lane.scheduled_start = f"{hh:02d}:{mm:02d}"
        else:
            return self._report(f"Unbekanntes Feld '{field}'.", "err")
        return self._changed()

    def phase_scale(self, data: dict) -> dict:
        """Multipliziert alle Wartezeiten einer Phase mit demselben Faktor."""
        lane = self._lane((data or {}).get("phase"))
        if lane is None:
            return self._report("Phase nicht gefunden.", "err")
        try:
            factor = float(str((data or {}).get("factor") or "").replace(",", "."))
        except ValueError:
            return self._report("Der Faktor muss eine Zahl sein.", "warn")
        if factor <= 0:
            return self._report("Der Faktor muss grösser als 0 sein.", "warn")
        changed = 0
        for step in lane.steps:
            if step.delay_before > 0:
                step.delay_before = round(step.delay_before * factor, 2)
                changed += 1
            if step.delay_max:
                step.delay_max = round(step.delay_max * factor, 2)
        return self._changed(
            f"{changed} Wartezeit(en) in '{lane.name}' × {factor:g} skaliert.")

    # --------------------------------------------------------------- Auswahl

    def _selection_clear(self) -> None:
        self.sel_lane, self.sel_rows = None, set()
        self.sel_other = []
        self.sel_anchor = None

    def _selection_set(self, lane: Lane, row: int) -> None:
        self.sel_lane, self.sel_rows = lane, {row}
        self.sel_other = []
        self.sel_anchor = row

    def _selection_focus(self, lane: Lane) -> None:
        """Macht `lane` zur Phase, in der gerade gewählt wird — ohne etwas abzuwählen.

        Die bisherige Phase wandert zu den übrigen, die Zeilen von `lane` (falls
        sie schon dabei war) kommen von dort zurück.
        """
        if self.sel_lane is lane:
            return
        mine = next((rows for ln, rows in self.sel_other if ln is lane), set())
        others = [(ln, rows) for ln, rows in self.sel_other if ln is not lane]
        if self.sel_lane is not None and self.sel_rows:
            others.append((self.sel_lane, self.sel_rows))
        self.sel_lane, self.sel_rows, self.sel_other = lane, set(mine), others
        self.sel_anchor = min(mine) if mine else None

    def _selection_tidy(self) -> None:
        """Leere Phasen fallen heraus; ist die aktuelle leer, rückt eine andere nach."""
        self.sel_other = [(ln, rows) for ln, rows in self.sel_other
                          if rows and self._lane_index(ln) is not None]
        if self.sel_rows:
            return
        if self.sel_other:
            self.sel_lane, self.sel_rows = self.sel_other.pop()
            self.sel_anchor = min(self.sel_rows)
        else:
            self._selection_clear()

    def _selection_replace(self, groups, keep) -> None:
        """Setzt die Auswahl neu aus `[(Phase, Zeilen)]`.

        `keep` bleibt die Phase, in der gewählt wird, sofern sie dabei ist —
        sonst wanderte die Umschalt+Klick-Stelle nach jedem Duplizieren.
        """
        groups = [(lane, set(rows)) for lane, rows in groups if rows]
        if not groups:
            self._selection_clear()
            return
        main = next((g for g in groups if g[0] is keep), groups[-1])
        self.sel_lane, self.sel_rows = main
        self.sel_other = [g for g in groups if g is not main]
        self.sel_anchor = min(self.sel_rows)

    def select(self, data: dict) -> dict:
        """Klick auf eine Karte. `mode`: single / add / area.

        **Die Auswahl darf über Phasen reichen.** STRG+Klick in eine andere
        Phase nimmt den Block dazu, statt neu anzufangen — die Wartezeit von
        zehn Blöcken in vier Loops liess sich vorher nur Phase für Phase setzen.
        Hier stand „Sammelaktionen brauchen genau eine Phase"; sie arbeiten
        jetzt je Phase für sich (`_selection_groups()`), und damit hat auch
        „eine Position hoch" wieder eine Bedeutung: hoch in der eigenen Phase.

        Umschalt+Klick bleibt ein Bereich INNERHALB einer Phase. Die Phasen
        stehen nebeneinander, ein Bereich quer darüber hätte keine Reihenfolge,
        die man sieht — in einer anderen Phase nimmt er deshalb nur den Block
        dazu und setzt dort den Anker für den nächsten.
        """
        data = data or {}
        lane = self._lane(data.get("phase"))
        if lane is None:
            self._selection_clear()
            return self.snapshot()
        row = int(data.get("row", 0))
        if not (0 <= row < len(lane.steps)):
            self._selection_clear()
            return self.snapshot()
        mode = data.get("mode") or "single"
        if mode == "add":
            self._selection_focus(lane)
            self.sel_rows.symmetric_difference_update({row})
            self.sel_anchor = row
            self._selection_tidy()
        elif mode == "area" and self.sel_lane is lane and self.sel_rows:
            anchor = self.sel_anchor if self.sel_anchor is not None else row
            from_index, until = sorted((anchor, row))
            area = set(range(from_index, until + 1))
            # Derselbe Umschalt-Klick ist ein echter Schalter: ist der ganze
            # Bereich schon gewählt, wird er entfernt; sonst kommt er dazu.
            if area <= self.sel_rows:
                self.sel_rows.difference_update(area)
            else:
                self.sel_rows.update(area)
            self._selection_tidy()
        elif mode == "area" and (self.sel_rows or self.sel_other):
            self._selection_focus(lane)
            self.sel_rows.add(row)
            self.sel_anchor = row
        else:
            self._selection_set(lane, row)
        return self.snapshot()

    def select_range(self, data: dict) -> dict:
        """Wählt `count` Blöcke ab `row` in einer Phase — für die Seite nach einem
        Vorgang, der Blöcke eingefügt hat, von dem sie aber erst nach dem Neuladen
        erfährt (Einfüge-Aufnahme).

        Dieselbe Regel wie beim Duplizieren und bei „Blöcke einfügen": was gerade
        entstanden ist, ist die neue Auswahl — man will es verschieben oder
        löschen, nicht erst wiederfinden. Hier ist es zusätzlich der einzige
        verlässliche Weg: wer aus dem Spiel zurückkommt, dessen erster Klick ins
        Fenster aktiviert es womöglich nur, und dann fehlte in einer STRG-Auswahl
        genau der erste Block. Der Bereich wird auf die Phase beschnitten.
        """
        data = data or {}
        lane = self._lane(data.get("phase"))
        try:
            row, count = int(data.get("row", 0)), int(data.get("count", 0))
        except (TypeError, ValueError):
            return self.snapshot()
        rows = {r for r in range(row, row + count) if lane and 0 <= r < len(lane.steps)}
        if not rows:
            return self.snapshot()
        self._selection_replace([(lane, rows)], lane)
        return self.snapshot()

    def selection_clear(self, data: Optional[dict] = None) -> dict:
        self._selection_clear()
        return self.snapshot()

    def phase_selection(self, data: dict) -> dict:
        """Wählt alle Blöcke einer Phase oder hebt deren Auswahl auf.

        `add` (STRG am Knopf) nimmt die Phase zur bestehenden Auswahl dazu —
        dieselbe Geste wie STRG+Klick auf eine Karte. Abwählen trifft nur DIESE
        Phase: wer drei Phasen gewählt hat und eine loswerden will, soll nicht
        alle drei verlieren.
        """
        data = data or {}
        lane = self._lane(data.get("phase"))
        if lane is None or not lane.steps:
            self._selection_clear()
            return self.snapshot()
        every = list(range(len(lane.steps)))
        if self._selected_rows(lane) == every:
            if lane is self.sel_lane:
                self.sel_rows = set()
            else:
                self.sel_other = [(ln, r) for ln, r in self.sel_other if ln is not lane]
            self._selection_tidy()
        elif data.get("add"):
            self._selection_focus(lane)
            self.sel_rows, self.sel_anchor = set(every), 0
        else:
            self._selection_replace([(lane, every)], lane)
        return self.snapshot()

    def selection_set(self, data: dict) -> dict:
        """Setzt ein gemeinsames Feld auf allen gewählten Blöcken."""
        data = data or {}
        field = data.get("field")
        groups = self._selection_groups()
        if not groups:
            return self._report("Keine Blöcke ausgewählt.", "warn")
        if field not in ("delay_before", "delay_max"):
            return self._report(f"'{field}' lässt sich nicht gesammelt setzen.", "warn")
        try:
            value = _FIELDS[field](data.get("value"))
        except (TypeError, ValueError):
            return self._report("Die Wartezeit muss eine Zahl sein.", "warn")
        count = 0
        for lane, rows in groups:
            for row in rows:
                setattr(lane.steps[row], field, value)
                count += 1
        return self._changed(
            f"Wartezeit für {_blocks(count)} gemeinsam gesetzt"
            + (f" (in {len(groups)} Phasen)." if len(groups) > 1 else "."))

    # -------------------------------------------------------------- Struktur

    def block_append(self, data: dict) -> dict:
        """Blanko-Block ans Ende einer Phase. Hat noch keine Stelle — deshalb (0,0)."""
        lane = self._lane((data or {}).get("phase"))
        if lane is None:
            return self._report("Phase nicht gefunden.", "err")
        self.board.add_step(lane, SequenceStep(x=0, y=0, delay_before=0.0))
        self._selection_set(lane, len(lane.steps) - 1)
        return self._changed()

    def point_insert(self, data: dict) -> dict:
        """Punkt aus der Palette als Klick-Block einsetzen (mit `point_id`)."""
        data = data or {}
        lane = self._lane(data.get("phase"))
        point = self._point(data.get("point"))
        if lane is None or point is None:
            return self._report("Punkt oder Phase nicht gefunden.", "err")
        at = data.get("row")
        at = len(lane.steps) if at is None else max(0, min(int(at), len(lane.steps)))
        self.board.add_step(lane, step_from_point(point), at=at)
        self._selection_set(lane, at)
        return self._changed()

    def _move(self, groups, target: Lane, at: int) -> None:
        """Trägt die Zeilen aus `groups` (`[(Phase, Zeilen)]`) in `target` ab `at` ein.

        Der eine Weg für alles: Umsortieren innerhalb einer Phase, Verschieben
        zwischen Phasen — das gibt es im Konsolen-Editor gar nicht — und seit
        die Auswahl über Phasen reicht, auch das Einsammeln aus mehreren. Die
        Reihenfolge danach ist die des Boards: erst die Blöcke der linken Phase.
        """
        steps_list = [lane.steps[i] for lane, rows in groups for i in sorted(rows)]
        if not steps_list:
            return
        # Wie viele der entfernten Schritte lagen VOR der Zielposition? Um so viele
        # rutscht sie nach vorne — aber nur die, die aus der Zielphase selbst kommen.
        at -= sum(1 for lane, rows in groups if lane is target for i in rows if i < at)
        for lane, rows in groups:
            for i in sorted(rows, reverse=True):
                self.board.delete_step(lane, i)
        at = max(0, min(at, len(target.steps)))
        for offset, step in enumerate(steps_list):
            self.board.add_step(target, step, at=at + offset)
        self._selection_replace([(target, range(at, at + len(steps_list)))], target)

    def drag(self, data: dict) -> dict:
        """Ziel eines Drag&Drop mit Karten."""
        data = data or {}
        source = self._lane(data.get("from_phase"))
        target = self._lane(data.get("to_phase"))
        if source is None or target is None:
            return self.snapshot()
        from_row = int(data.get("from_row", 0))
        at = int(data.get("to_row", 0))
        # Wird ein Schritt aus der aktuellen Auswahl gezogen, wandert die ganze
        # Auswahl mit — auch aus anderen Phasen —, sonst nur der angefasste.
        groups = (self._selection_groups() if from_row in self._selected_rows(source)
                  else [(source, [from_row])])
        self._move(groups, target, at)
        count = sum(len(rows) for _lane, rows in groups)
        return self._changed("", offer=True, what=f"{_blocks(count)} verschoben")

    def selection_move(self, data: dict) -> dict:
        """Verschiebt die Auswahl als Block um eine Position (−1 hoch, +1 runter)."""
        delta = int((data or {}).get("delta", 0))
        groups = self._selection_groups()
        if not groups or delta == 0:
            return self.snapshot()
        # Jede Phase für sich: ihre Gewählten rücken als Block, und wer schon an
        # der Kante steht, bleibt stehen — ohne die anderen Phasen aufzuhalten.
        moved, count, result = False, 0, []
        for lane, rows in groups:
            at_edge = rows[0] == 0 if delta < 0 else rows[-1] == len(lane.steps) - 1
            if at_edge:
                result.append((lane, rows))
                continue
            # Beim Hochschieben von vorne abarbeiten, beim Runterschieben von
            # hinten — sonst überholen sich die Elemente gegenseitig.
            consequence = rows if delta < 0 else list(reversed(rows))
            result.append((lane, {self.board.move_step(lane, idx, delta)
                                  for idx in consequence}))
            moved, count = True, count + len(rows)
        if not moved:
            return self.snapshot()
        self._selection_replace(result, self.sel_lane)
        return self._changed(group="move", what=f"{_blocks(count)} verschoben")

    _REF_FIELDS = ("wait_condition", "verify_condition", "else_config")

    def _points_copy_along(self, step, mapping: dict, source=None) -> None:
        """Hängt alle Punkt-Referenzen eines kopierten Schritts auf eigene Punkte um.

        `mapping` gilt für den ganzen Durchgang: derselbe Ausgangspunkt ergibt
        denselben neuen. Zwei Wirkungen, und beide sind gewollt.

        **Innerhalb eines Blocks** bleibt zusammen, was zusammengehört: bei
        FARBE+KLICK sind Klick und Prüf-Pixel derselbe Punkt, und die Kopie soll
        das auch sein — sonst wartet sie auf eine andere Stelle, als sie klickt.

        **Zwischen mehreren kopierten Blöcken** bleibt die Beziehung erhalten:
        klicken zwei Gewählte denselben Knopf, tun ihre Kopien das auch. Sonst
        entstünden bei einer Mehrfachauswahl drei Punkte auf einem Knopf statt
        zwei.

        `source` sucht den Ausgangspunkt (Standard: die eigenen Punkte). Beim
        Einfügen aus einer anderen Sequenz ist es deren Punkte-Bestand — die
        IDs dort sind sequenzlokal und sagen hier nichts.
        """
        lookup = source or self._point

        def new_for(old_id):
            if old_id is None:
                return None
            if old_id not in mapping:
                template_value = lookup(old_id)
                if template_value is None:
                    return old_id          # zeigt schon ins Leere — nicht erfinden
                copy_of = PalettePoint(
                    id=max([p.id for p in self.points], default=0) + 1,
                    x=template_value.x, y=template_value.y, name=template_value.name,
                    color=template_value.color, source="Sequenz-Studio")
                self.points.append(copy_of)
                mapping[old_id] = copy_of.id
            return mapping[old_id]

        step.point_id = new_for(step.point_id)
        for field in self._REF_FIELDS:
            condition = getattr(step, field, None)
            if condition is not None and getattr(condition, "point_id", None) is not None:
                condition.point_id = new_for(condition.point_id)

    def selection_duplicate(self, data: Optional[dict] = None) -> dict:
        """Legt Kopien der gewählten Blöcke direkt hinter die Auswahl.

        **Die Kopie bekommt eigene Punkte.** Man dupliziert einen Block, um ihn
        zu ändern — und solange beide auf denselben Punkt zeigen, verstellt jede
        Korrektur an der Kopie auch das Original. Der Zusammenhang wäre also
        schon beim Anlegen falsch, und auffallen würde es erst viel später an
        einer Stelle, an der man ihn nicht mehr sucht.

        Hier stand einmal das Gegenteil („ein Duplikat ist erst mal derselbe
        Klick"), mit dem Argument, ein zweiter Punkt an derselben Stelle sei die
        Doppelung, die `point_at_position()` überall sonst vermeidet. Das stimmt —
        nur verhindert die Regel dort *unabsichtliche* Dubletten aus einer
        Aufnahme. Ein Duplikat ist eine Ansage, und der Preis dafür sind zwei
        Punkte auf einer Stelle, bis einer davon umzieht.

        Wer wirklich zweimal denselben Knopf klicken will, hat den kürzeren Weg:
        Block anlegen und im Inspektor den vorhandenen Punkt wählen.

        Kopiert wird tief — `else_config`, `wait_condition` und `verify_condition`
        sind eigene Objekte, sonst änderte ein Griff an der Kopie das Original mit.
        """
        groups = self._selection_groups()
        if not groups:
            return self._report("Nichts ausgewählt — erst einen Block anklicken.", "warn")
        before = len(self.points)
        # EINE Abbildung für den ganzen Durchgang, auch über Phasen hinweg:
        # klicken zwei Gewählte denselben Knopf, tun ihre Kopien das auch.
        mapping: dict = {}
        copies, count = [], 0
        for lane, rows in groups:
            # Alle Kopien hinter den LETZTEN Gewählten dieser Phase, in der
            # Reihenfolge der Vorlagen. Jede einzeln hinter ihr Original zu setzen
            # zerrisse eine Mehrfachauswahl in abwechselnd Original/Kopie.
            target = rows[-1] + 1
            for offset, idx in enumerate(rows):
                copy_of = copy.deepcopy(lane.steps[idx])
                self._points_copy_along(copy_of, mapping)
                self.board.add_step(lane, copy_of, target + offset)
            copies.append((lane, range(target, target + len(rows))))
            count += len(rows)
        # Die Kopien sind die neue Auswahl: man will sie gleich verschieben oder
        # umstellen, nicht erneut suchen.
        self._selection_replace(copies, self.sel_lane)
        self._points_apply()
        fresh = len(self.points) - before
        return self._changed(
            f"{_blocks(count)} dupliziert."
            + (f" {fresh} eigene(r) Punkt(e) angelegt — die Kopie lässt sich "
               f"verschieben, ohne das Original mitzunehmen." if fresh else ""))

    # Scan-Verweise eines Schritts und der Unterordner, in dem der Scan liegen
    # muss — Scans sind wie Punkte sequenzlokal.
    _SCAN_DIRS = (("item_scan", "item_scans"), ("boss_scan", "boss_scans"),
                  ("boss_watcher", "boss_scans"), ("icon_scan", "icon_scans"))

    def block_import(self, data: Optional[dict] = None) -> dict:
        """Fügt alle Blöcke einer anderen Sequenz hinter dem gewählten ein.

        Die billige Fassung von „Bausteine": keine Referenz auf die andere
        Sequenz, sondern eine **bewusste, einmalige Kopie** — der Weg zur Bank
        steht danach zweimal da, und wer ihn ändert, ändert ihn in beiden. Ein
        echter Aufruf bräuchte einen Stapel im Worker (Live-Run und Phasenleiste
        beschreiben genau eine Sequenz), Schutz vor Rekursion und eine Antwort
        darauf, was `restart` in einem Baustein heisst.

        Drei Regeln:

        - **Eigene Punkte, wie beim Duplizieren** (`_points_copy_along` mit dem
          Bestand der Quelle). Punkt-IDs sind sequenzlokal; eine übernommene
          `#3` zeigte hier auf einen ganz anderen Knopf.
        - **Ein Block, dessen Punkt schon in der Quelle fehlt, kommt nicht mit.**
          Er bliebe sonst mit einer fremden ID stehen, die hier zufällig
          vergeben sein kann — ein Klick auf eine falsche Stelle ist schlimmer
          als ein fehlender Block. Gezählt und gesagt.
        - **Scans kommen nicht mit, werden aber genannt.** Sie gehören der
          Quelle samt Vorlagen; fehlen sie hier, sagt die Meldung welche, und
          die Diagnose springt später genau dorthin.
        """
        from ...persistence import load_sequence_file
        from ...utils import sanitize_filename

        name = str((data or {}).get("name") or "").strip()
        if not name:
            return self._report("Erst eine Sequenz wählen, aus der eingefügt wird.", "warn")
        if name == self.board.name:
            return self._report("Das ist die offene Sequenz — dafür gibt es „duplizieren“.",
                                "warn")
        lane, row, step = self._single()
        if step is None or lane is None or row is None:
            return self._report("Bitte genau einen Block wählen — eingefügt wird dahinter.",
                                "warn")
        folder = self._sequence_folder(name)
        source = load_sequence_file(folder / "sequence.json") if folder else None
        if source is None:
            return self._report(f"'{name}' ist nicht lesbar.", "err")
        steps = [*source.init_steps,
                 *(s for phase in source.loop_phases for s in phase.steps),
                 *source.end_steps]
        if not steps:
            return self._report(f"'{name}' hat keine Blöcke.", "warn")

        pool = {p.id: p for p in source.points}

        def dangling(s) -> bool:
            ids = [s.point_id] + [getattr(getattr(s, f, None), "point_id", None)
                                  for f in self._REF_FIELDS]
            return any(i is not None and i not in pool for i in ids)

        before = len(self.points)
        mapping: dict = {}
        at = row + 1
        taken = 0
        skipped = 0
        missing_scans: list[str] = []
        base = self.filepath.parent
        for original in steps:
            if dangling(original):
                skipped += 1
                continue
            copy_of = copy.deepcopy(original)
            copy_of.unresolved = False
            self._points_copy_along(copy_of, mapping, source=pool.get)
            self.board.add_step(lane, copy_of, at + taken)
            taken += 1
            for field, subdir in self._SCAN_DIRS:
                scan = getattr(copy_of, field, None)
                if scan and scan not in missing_scans and not (
                        base / subdir / f"{sanitize_filename(scan)}.json").exists():
                    missing_scans.append(scan)
        if not taken:
            return self._report(f"Kein Block aus '{name}' übernommen — alle zeigen auf "
                                f"Punkte, die es dort nicht mehr gibt.", "warn")
        self._selection_replace([(lane, range(at, at + taken))], lane)
        self._points_apply()
        fresh = len(self.points) - before
        text = (f"{_blocks(taken)} aus '{name}' eingefügt"
                + (f", {fresh} eigene(r) Punkt(e) angelegt" if fresh else "") + ".")
        if skipped:
            text += f" {_blocks(skipped)} ausgelassen — ihr Punkt fehlt schon in '{name}'."
        if missing_scans:
            text += (" Scans fehlen hier und kommen nicht mit: "
                     + ", ".join(f"'{s}'" for s in missing_scans) + ".")
        return self._changed(text, "warn" if (skipped or missing_scans) else "ok",
                             offer=True, what=f"Blöcke aus '{name}' eingefügt")

    def selection_delete(self, data: Optional[dict] = None) -> dict:
        groups = self._selection_groups()
        if not groups:
            return self.snapshot()
        # Von hinten löschen, sonst verschieben sich die noch offenen Indizes.
        for lane, rows in groups:
            for idx in reversed(rows):
                self.board.delete_step(lane, idx)
        count = sum(len(rows) for _lane, rows in groups)
        self._selection_clear()
        return self._changed(f"{_blocks(count)} gelöscht.", offer=True)

    # ---------------------------------------------------------- Block-Felder

    def _else_cleanup(self, step: SequenceStep) -> str:
        """Entfernt ein ELSE, das nach dieser Änderung nichts mehr auslösen kann.

        Wer den Trigger wegnimmt oder den Typ umstellt, hat den einzigen Auslöser
        entfernt; stehenzulassen hiesse, die Ersatzaktion unsichtbar in der Datei zu
        behalten, denn der Abschnitt fällt mit dem Auslöser weg.

        Nur bei einer Änderung, nie beim Laden: eine Datei, die ein wirkungsloses
        ELSE mitbringt, wird nicht stillschweigend beschnitten.

        Gibt den Meldungstext zurück (leer, wenn nichts zu tun war).
        """
        if step.else_config is None or else_applies(step):
            return ""
        step.else_config = None
        return "ELSE entfernt — dieser Block kann es nicht mehr auslösen."

    def block_set_type(self, data: dict) -> dict:
        """Stellt den Block-Typ um.

        FARBE+KLICK braucht einen Punkt — er ist die Quelle für Stelle UND Farbe.
        Ohne Punkt wird der Wechsel abgelehnt: lieber gar keine Bedingung als eine,
        die niemand mehr nachziehen kann.
        """
        type_value = (data or {}).get("type")
        lane, row, step = self._single()
        if step is None or type_value not in BLOCK_LABELS:
            return self.snapshot()
        if (type_value == BLOCK_WAIT_CLICK and step.wait_condition is None
                and step.point_id is None):
            return self._report("FARBE+KLICK braucht einen Punkt — erst eine Stelle wählen.",
                               "warn")
        set_block_type(step, type_value)
        self._points_apply()
        gone = self._else_cleanup(step)
        return self._changed(gone, "warn" if gone else "ok", offer=True,
                             what=f"Typ → {BLOCK_LABELS[type_value]}")

    def block_set(self, data: dict) -> dict:
        """Ein einfaches Feld des gewählten Schritts setzen."""
        data = data or {}
        field, value = data.get("field"), data.get("value")
        lane, row, step = self._single()
        if step is None:
            return self.snapshot()
        convert = _FIELDS.get(field)
        if convert is None:
            return self._report(f"Unbekanntes Feld '{field}'.", "err")
        try:
            setattr(step, field, convert(value))
        except (TypeError, ValueError):
            return self._report(f"'{value}' passt nicht zu {field}.", "warn")
        return self._changed()

    def block_area(self, data: dict) -> dict:
        """Screenshot-Bereich setzen (`values` = [x1,y1,x2,y2]) oder auf Vollbild zurück."""
        data = data or {}
        lane, row, step = self._single()
        if step is None:
            return self.snapshot()
        values = data.get("values")
        if not values:
            step.screenshot_region = None
        else:
            try:
                step.screenshot_region = tuple(int(v) for v in values[:4])
            except (TypeError, ValueError):
                return self._report("Bereich braucht vier ganze Zahlen.", "warn")
        return self._changed()

    def area_capture(self, data: Optional[dict] = None) -> dict:
        """Beide Ecken des Screenshot-Bereichs mit der Maus setzen — in einem Zug.

        Vier Zahlenfelder sind kein Weg, einen Bildschirmbereich zu bestimmen: Maus
        hin, ENTER, zweite Ecke, ENTER. Beide Ecken in EINEM Aufruf, sonst müsste
        die Hand mitten in der Aufnahme zum Fenster zurückfahren.

        Abgebrochen wird bei ESC und Zeitablauf vollständig — auch nach der ersten
        Ecke bleibt der alte Bereich stehen. Der Zahlenweg bleibt daneben stehen.
        """
        lane, row, step = self._single()
        if step is None:
            return self.snapshot()

        # Erst hier importiert: das Modul soll ohne Windows ladbar bleiben, und
        # die Tests messen alles andere an dieser Klasse plattformfrei.
        from ...utils.io import wait_for_global_key
        from ...winapi import get_cursor_pos

        corners = []
        for _ in (1, 2):
            key = wait_for_global_key(("enter", "escape"),
                                    timeout=WAIT_TIMEOUT)
            if key != "enter":
                return self._report(
                    "Abgebrochen — der Bereich bleibt, wie er war."
                    if key == "escape" else
                    "Nichts gedrückt — der Bereich bleibt, wie er war.", "warn")
            corners.append(get_cursor_pos())

        (x1, y1), (x2, y2) = corners
        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)
        if x2 - x1 < 2 or y2 - y1 < 2:
            return self._report(
                f"Bereich zu klein: {x2 - x1}×{y2 - y1} Pixel — nichts geändert.", "warn")

        step.screenshot_region = (x1, y1, x2, y2)
        return self._changed(f"Bereich {x2 - x1}×{y2 - y1} bei ({x1},{y1}).", "ok")

    def _await_position(self) -> tuple:
        """Wartet auf ENTER und gibt `(x, y, "")` zurück — bei Abbruch `(None, None, Grund)`.

        Der gemeinsame Teil von „Stelle mit der Maus setzen" und „Maus parken": das
        Fenster hat den Fokus, das Spiel nicht — gefragt wird deshalb über eine
        globale Taste.
        """
        # Erst hier importiert — das Modul bleibt ohne Windows ladbar.
        from ...utils.io import wait_for_global_key
        from ...winapi import get_cursor_pos

        key = wait_for_global_key(("enter", "escape"), timeout=WAIT_TIMEOUT)
        if key != "enter":
            return None, None, ("Abgebrochen" if key == "escape" else "Nichts gedrückt")
        x, y = get_cursor_pos()
        return x, y, ""

    def mouse_position(self, data: Optional[dict] = None) -> dict:
        """Die aktuelle Mausposition — für die Einstellungen, ohne Punkt anzulegen.

        `point_capture()` ist der Weg für einen Block; `scan_park_mouse` ist
        aber kein Punkt und gehört nicht in die Punktliste der `sequence.json`. Übrig bleibt die
        Geste: Maus hin, ENTER.
        """
        x, y, message = self._await_position()
        if x is None:
            return {"ok": False, "message": message + " — nichts geändert."}
        return {"ok": True, "x": x, "y": y}

    def point_capture(self, data: Optional[dict] = None) -> dict:
        """Setzt die Stelle des Blocks auf die aktuelle Mausposition.

        Derselbe Weg wie `area_capture()`, nur mit einer Ecke. Gesetzt wird über
        dieselben Methoden wie sonst, damit die üblichen Regeln gelten: ein
        vorhandener Punkt an derselben Stelle wird wiederverwendet.
        """
        lane, row, step = self._single()
        if step is None:
            return self.snapshot()

        x, y, message = self._await_position()
        if x is None:
            return self._report(message + " — die Stelle bleibt, wie sie war.", "warn")
        from ...winapi import get_screen_pixel

        if step.point_id is not None:
            # Vorhandenen Punkt verschieben: dieselbe Regel wie beim Tippen der
            # Zahlen — der Punkt gehört nicht diesem Block allein.
            self.point_set({"point": step.point_id, "field": "x", "value": x})
            self.point_set({"point": step.point_id, "field": "y", "value": y})
        else:
            self.point_create({"x": x, "y": y})

        # Farbe gleich mitmessen: ein Punkt ohne Farbe taugt für keinen
        # Farb-Trigger, und der Bildschirm zeigt gerade genau das Richtige —
        # deshalb steht man ja mit der Maus dort.
        point = self._point(step.point_id)
        color = get_screen_pixel(x, y)
        if point is not None and color is not None:
            point.color = tuple(color)
            self._points_apply()
        measured = f" · Farbe {tuple(color)}" if color else ""
        return self._changed(f"Stelle: ({x}, {y}){measured}"
                               + self._moved_along(step.point_id, except_step=step))

    def _moved_along(self, point_id, except_step=None) -> str:
        """Nachsatz für eine Verschiebung: welche anderen Verwendungen mitziehen.

        Leer, wenn keine — dann ist die Meldung so kurz wie vorher.
        """
        other = self._point_usages(point_id, except_step=except_step)
        if not other:
            return ""
        return (f" — zieht {len(other)} weitere Verwendung(en) mit: "
                + ", ".join(other))

    def point_detach(self, data: Optional[dict] = None) -> dict:
        """Gibt dem gewählten Block einen eigenen Punkt — die anderen behalten den alten.

        Das Gegenstück zu „X/Y verschieben den Punkt": diese Regel ist richtig,
        wenn ein Knopf umgezogen ist (dann sollen alle mit), und falsch, wenn
        EIN Block einen anderen Knopf klicken soll. Für das Zweite gab es keinen
        Weg — man verstellte die anderen Blöcke mit, ohne es zu sehen. Dieselbe
        Bauart wie beim Duplizieren (`_points_copy_along`): Klick und Prüf-Pixel
        eines FARBE+KLICK-Blocks bleiben zusammen auf dem neuen Punkt.
        """
        lane, row, step = self._single()
        if step is None:
            return self.snapshot()
        if step.point_id is None:
            return self._report("Dieser Block hat keinen Punkt.", "warn")
        old = step.point_id
        other = self._point_usages(old, except_step=step)
        if not other:
            return self._report(f"Punkt #{old} wird nur von diesem Block benutzt — "
                               "nichts abzutrennen.", "info")
        self._points_copy_along(step, {})
        self._points_apply()
        return self._changed(f"Block hat jetzt seinen eigenen Punkt #{step.point_id}; "
                               f"#{old} bleibt bei: {', '.join(other)}")

    def point_delete(self, data: Optional[dict] = None) -> dict:
        """Löscht einen Punkt aus der Punkte-Liste des Editors.

        Dort stehen die Reste einer Aufnahme als „0×" — gelöscht werden konnten
        sie nur im Werkzeuge-Reiter, und der zog die Liste hier nicht nach: der
        Punkt stand weiter da, der Ungespeichert-Punkt fehlte, und es sah aus,
        als hätte das Löschen nicht gewirkt. Hier ist es ein Editor-Befehl wie
        jeder andere — Momentaufnahme, Rückgängig, Speichern mit der Sequenz.
        Dieselbe Regel wie im Werkzeug (`_point_remove`): ein Punkt, an dem
        noch etwas hängt, bleibt.
        """
        point_id = (data or {}).get("point_id")
        removed, message, _used = self._point_remove(point_id)
        if not removed:
            return self._report(message, "warn")
        return self._changed(message, offer=True, what=message.rstrip("."))

    def block_point(self, data: dict) -> dict:
        """Setzt den Punkt des Schritts — Stelle, Name und Farbe kommen mit.

        Prüft der Schritt seine eigene Stelle (Farb-Trigger auf demselben Punkt),
        zieht der Trigger mit: sonst klickt der Schritt woanders hin, als er
        vorher geprüft hat.
        """
        data = data or {}
        lane, row, step = self._single()
        if step is None:
            return self.snapshot()
        point = self._point(data.get("point"))
        if point is None:
            return self._report("Punkt nicht gefunden.", "warn")
        old = step.point_id
        step.point_id = point.id
        for cond in (step.wait_condition, step.verify_condition):
            if cond is not None and (cond.point_id == old or cond.point_id is None):
                cond.point_id = point.id
        self._points_apply()
        return self._changed()

    def block_trigger(self, data: dict) -> dict:
        """Farb-Trigger des Schritts: kein / da / weg, plus 'nur prüfen'.

        Der Punkt ist die Quelle für Stelle UND Farbe. Ohne `point_id` gibt es
        nichts zu prüfen — dann passiert nichts, statt eine Bedingung auf (0,0)
        anzulegen. Dieselbe Haltung wie „es gibt bewusst keinen Rückfallwert".
        """
        data = data or {}
        lane, row, step = self._single()
        if step is None:
            return self.snapshot()
        field = "verify_condition" if data.get("which") == "verify" else "wait_condition"
        return self._trigger_set(step, field, data)

    def _trigger_set(self, step: SequenceStep, field: str, data: dict) -> dict:
        choice = data.get("choice")
        cond: Optional[WaitCondition] = getattr(step, field)
        if choice == TRIGGER_NONE:
            setattr(step, field, None)
            gone = self._else_cleanup(step)
            return self._changed(gone, "warn" if gone else "ok")
        if cond is None:
            point_id = data.get("point", step.point_id)
            point = self._point(point_id)
            if point is None:
                return self._report(
                    "Ohne Punkt gibt es nichts zu prüfen — erst einen wählen.", "warn")
            cond = WaitCondition(point_id=point.id, pixel=(point.x, point.y),
                                 color=tuple(point.color) if point.color else (0, 0, 0))
            setattr(step, field, cond)
        if choice in (TRIGGER_PRESENT, TRIGGER_GONE):
            cond.until_gone = (choice == TRIGGER_GONE)
        if "check_only" in data:
            cond.check_only = bool(data["check_only"])
        if data.get("point") is not None:
            point = self._point(data["point"])
            if point is not None:
                cond.point_id = point.id
                self._points_apply()
        return self._changed()

    def block_else(self, data: dict) -> dict:
        """ELSE-Aktion setzen oder entfernen (leere Aktion = keine)."""
        data = data or {}
        lane, row, step = self._single()
        if step is None:
            return self.snapshot()
        action = data.get("action") or ""
        if not action:
            step.else_config = None
            return self._changed()
        if action not in ELSE_ACTIONS:
            return self._report(f"Unbekannte ELSE-Aktion '{action}'.", "err")
        ec = ensure_else(step, action)
        if "point" in data and data["point"] is not None:
            point = self._point(data["point"])
            if point is None:
                return self._report("Punkt nicht gefunden.", "warn")
            # Nur die Referenz zählt: `x`/`y`/`name` sind abgeleitet und stehen
            # nicht in der Datei. Der DPG-Vorgänger liess genau diese drei von Hand
            # eintippen — beim nächsten Öffnen war die Eingabe weg.
            ec.point_id = point.id
            self._points_apply()
        if "action_key" in data:
            ec.key = str(data["action_key"] or "").strip() or None
        if "delay" in data:
            ec.delay = max(0.0, float(data["delay"] or 0))
        return self._changed()

    # ---------------------------------------------------------------- Punkte

    def point_set(self, data: dict) -> dict:
        """Verschiebt oder benennt einen Punkt — alle Schritte darauf ziehen mit.

        Die Zahlenfelder verschieben den PUNKT, nicht den Schritt: die Sequenz
        hält keine Koordinaten mehr, eine hier eingetippte Stelle wäre sonst beim
        Speichern verloren.
        """
        data = data or {}
        point = self._point(data.get("point"))
        if point is None:
            return self._report("Punkt nicht gefunden.", "warn")
        field, value = data.get("field"), data.get("value")
        try:
            if field in ("x", "y"):
                setattr(point, field, int(value))
                self._points_apply()
                # Wer SONST noch mitgezogen ist, steht in der Meldung — der
                # Inspektor zeigt nur den einen Block, an dem man gerade sitzt,
                # und der zählt nicht als „weiterer".
                _lane, _row, selected = self._single()
                return self._changed(f"Punkt #{point.id} verschoben"
                                       + self._moved_along(point.id, except_step=selected))
            elif field == "name":
                point.name = str(value or "")
            elif field == "color":
                # Die Farbe ist das, was ein Farb-Trigger prueft — sie von Hand zu
                # setzen ist deshalb eine echte Aenderung am Verhalten, nicht bloss
                # Anzeige. Leer heisst „keine gemessene Farbe", nicht Schwarz.
                point.color = _rgb(value)
            else:
                return self._report(f"Unbekanntes Feld '{field}'.", "err")
        except (TypeError, ValueError):
            return self._report(f"'{value}' ist keine Zahl.", "warn")
        self._points_apply()
        return self._changed()

    def point_create(self, data: dict) -> dict:
        """Legt einen Punkt an und hängt ihn an den gewählten Schritt.

        Für den Blanko-Block: er hat noch keine Stelle und bliebe ohne Punkt ein
        Klick auf (0,0).
        """
        data = data or {}
        lane, row, step = self._single()
        if step is None:
            return self.snapshot()
        try:
            x, y = int(data.get("x", 0)), int(data.get("y", 0))
        except (TypeError, ValueError):
            return self._report("Stelle braucht zwei ganze Zahlen.", "warn")
        # Denselben Punkt wiederverwenden, wenn schon einer dort liegt: klickt eine
        # Sequenz zweimal denselben Knopf, ist das EIN Punkt — sonst wandert beim
        # Nachjustieren nur die Hälfte mit.
        point = next((p for p in self.points if p.x == x and p.y == y), None)
        if point is None:
            point = PalettePoint(
                id=max([p.id for p in self.points], default=0) + 1,
                x=x, y=y,
                name=str(data.get("name") or step.name or "Sequenz-Studio"),
                color=tuple(step.recorded_color) if step.recorded_color else None,
                source="Sequenz-Studio")
            self.points.append(point)
        step.point_id = point.id
        self._points_apply()
        return self._changed(f"Punkt #{point.id} gesetzt.")
