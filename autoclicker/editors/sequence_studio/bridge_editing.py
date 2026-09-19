"""Editor-Kommandos für Phasen, Blöcke, Auswahl und Punkte."""

import copy
import re
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


class BridgeEditingMixin:
    """Bearbeitet die Sequenz ausschließlich über klar benannte Kommandos."""

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
        return self._changed(f"Phase '{lane.name}' gelöscht.")

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
        self.sel_anchor = None

    def _selection_set(self, lane: Lane, row: int) -> None:
        self.sel_lane, self.sel_rows = lane, {row}
        self.sel_anchor = row

    def select(self, data: dict) -> dict:
        """Klick auf eine Karte. `mode`: einzeln / dazu / bereich.

        Die Auswahl fängt in einer anderen Phase immer neu an — siehe
        Klassen-Docstring: Sammelaktionen brauchen genau eine Phase.
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
        mode = data.get("mode") or "einzeln"
        if mode == "dazu" and self.sel_lane is lane:
            self.sel_rows.symmetric_difference_update({row})
            if not self.sel_rows:
                self._selection_clear()
            else:
                self.sel_anchor = row
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
            if not self.sel_rows:
                self._selection_clear()
        else:
            self._selection_set(lane, row)
        return self.snapshot()

    def selection_clear(self, data: Optional[dict] = None) -> dict:
        self._selection_clear()
        return self.snapshot()

    def phase_selection(self, data: dict) -> dict:
        """Wählt alle Blöcke einer Phase oder hebt deren Auswahl auf."""
        lane = self._lane((data or {}).get("phase"))
        if lane is None or not lane.steps:
            self._selection_clear()
            return self.snapshot()
        all_selected = self.sel_lane is lane and self.sel_rows == set(range(len(lane.steps)))
        if all_selected:
            self._selection_clear()
        else:
            self.sel_lane = lane
            self.sel_rows = set(range(len(lane.steps)))
            self.sel_anchor = 0
        return self.snapshot()

    def selection_set(self, data: dict) -> dict:
        """Setzt ein gemeinsames Feld auf allen gewählten Blöcken."""
        data = data or {}
        lane = self.sel_lane
        field = data.get("field")
        if lane is None or not self.sel_rows:
            return self._report("Keine Blöcke ausgewählt.", "warn")
        if field not in ("delay_before", "delay_max"):
            return self._report(f"'{field}' lässt sich nicht gesammelt setzen.", "warn")
        try:
            value = _FIELDS[field](data.get("value"))
        except (TypeError, ValueError):
            return self._report("Die Wartezeit muss eine Zahl sein.", "warn")
        rows = [row for row in sorted(self.sel_rows) if 0 <= row < len(lane.steps)]
        for row in rows:
            setattr(lane.steps[row], field, value)
        return self._changed(
            f"Wartezeit für {_blocks(len(rows))} gemeinsam gesetzt.")

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

    def _move(self, source: Lane, rows: list[int], target: Lane, at: int) -> None:
        """Trägt `rows` aus `source` in `target` ab Position `at` ein.

        Der eine Weg für beides: Umsortieren innerhalb einer Phase und Verschieben
        zwischen Phasen — Letzteres gibt es im Konsolen-Editor gar nicht.
        """
        steps_list = [source.steps[i] for i in sorted(rows)]
        if not steps_list:
            return
        # Wie viele der entfernten Schritte lagen VOR der Zielposition? Um so viele
        # rutscht sie nach vorne — aber nur, wenn aus derselben Phase entfernt wird.
        if source is target:
            at -= sum(1 for i in rows if i < at)
        for i in sorted(rows, reverse=True):
            self.board.delete_step(source, i)
        at = max(0, min(at, len(target.steps)))
        for offset, step in enumerate(steps_list):
            self.board.add_step(target, step, at=at + offset)
        self.sel_lane = target
        self.sel_rows = set(range(at, at + len(steps_list)))
        self.sel_anchor = at
        self._dirty = True

    def drag(self, data: dict) -> dict:
        """Ziel eines Drag&Drop mit Karten."""
        data = data or {}
        source = self._lane(data.get("von_phase"))
        target = self._lane(data.get("to_phase"))
        if source is None or target is None:
            return self.snapshot()
        from_row = int(data.get("from_row", 0))
        at = int(data.get("to_row", 0))
        # Wird ein Schritt aus der aktuellen Auswahl gezogen, wandert die ganze
        # Auswahl mit — sonst nur der angefasste.
        rows = (sorted(self.sel_rows)
                if (self.sel_lane is source and from_row in self.sel_rows)
                else [from_row])
        self._move(source, rows, target, at)
        return self._report("")

    def selection_move(self, data: dict) -> dict:
        """Verschiebt die Auswahl als Block um eine Position (−1 hoch, +1 runter)."""
        delta = int((data or {}).get("delta", 0))
        lane = self.sel_lane
        if lane is None or not self.sel_rows or delta == 0:
            return self.snapshot()
        rows = sorted(self.sel_rows)
        if delta < 0 and rows[0] == 0:
            return self.snapshot()
        if delta > 0 and rows[-1] == len(lane.steps) - 1:
            return self.snapshot()
        # Beim Hochschieben von vorne abarbeiten, beim Runterschieben von hinten —
        # sonst überholen sich die Elemente gegenseitig.
        consequence = rows if delta < 0 else list(reversed(rows))
        self.sel_rows = {self.board.move_step(lane, idx, delta) for idx in consequence}
        self.sel_anchor = min(self.sel_rows) if self.sel_rows else None
        return self._changed()

    _REF_FIELDS = ("wait_condition", "verify_condition", "else_config")

    def _points_copy_along(self, step, mapping: dict) -> None:
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
        """
        def new_for(old_id):
            if old_id is None:
                return None
            if old_id not in mapping:
                template_value = self._point(old_id)
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
        lane = self.sel_lane
        if lane is None or not self.sel_rows:
            return self._report("Nichts ausgewählt — erst einen Block anklicken.", "warn")
        rows = sorted(self.sel_rows)
        # Alle Kopien hinter den LETZTEN Gewählten, in der Reihenfolge der
        # Vorlagen. Jede einzeln hinter ihr Original zu setzen zerrisse eine
        # Mehrfachauswahl in abwechselnd Original/Kopie.
        target = rows[-1] + 1
        before = len(self.points)
        mapping: dict = {}
        for offset, idx in enumerate(rows):
            copy_of = copy.deepcopy(lane.steps[idx])
            self._points_copy_along(copy_of, mapping)
            self.board.add_step(lane, copy_of, target + offset)
        # Die Kopien sind die neue Auswahl: man will sie gleich verschieben oder
        # umstellen, nicht erneut suchen.
        self.sel_rows = {target + i for i in range(len(rows))}
        self.sel_anchor = target
        self._points_apply()
        fresh = len(self.points) - before
        return self._changed(
            f"{_blocks(len(rows))} dupliziert."
            + (f" {fresh} eigene(r) Punkt(e) angelegt — die Kopie lässt sich "
               f"verschieben, ohne das Original mitzunehmen." if fresh else ""))

    def selection_delete(self, data: Optional[dict] = None) -> dict:
        lane = self.sel_lane
        if lane is None or not self.sel_rows:
            return self.snapshot()
        # Von hinten löschen, sonst verschieben sich die noch offenen Indizes.
        for idx in sorted(self.sel_rows, reverse=True):
            self.board.delete_step(lane, idx)
        count = len(self.sel_rows)
        self._selection_clear()
        return self._changed(f"{_blocks(count)} gelöscht.")

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
        return self._changed(gone, "warn" if gone else "ok")

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
        self._dirty = True
        return self._report(f"Bereich {x2 - x1}×{y2 - y1} bei ({x1},{y1}).", "ok")

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
