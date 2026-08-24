"""Editor-Kommandos für Phasen, Blöcke, Auswahl und Punkte."""

import copy
import re
from typing import Optional

from ...models import BLOCK_WAIT_CLICK, SequenceStep, WaitCondition
from .bridge_contract import (
    ELSE_AKTIONEN,
    TRIGGER_DA,
    TRIGGER_KEIN,
    TRIGGER_WEG,
    _FELDER,
    _bloecke,
    _rgb,
    else_greift,
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

    def phase_anhaengen(self, daten: Optional[dict] = None) -> dict:
        lane = self.board.add_loop_lane()
        return self._geaendert(f"Phase '{lane.name}' angelegt.")

    def phase_loeschen(self, daten: dict) -> dict:
        lane = self._lane((daten or {}).get("phase"))
        if lane is None or lane.kind != LANE_LOOP:
            return self._melde("INIT und END lassen sich nicht löschen.", "warn")
        self.board.delete_loop_lane(lane)
        self._auswahl_leeren()
        return self._geaendert(f"Phase '{lane.name}' gelöscht.")

    def phase_setzen(self, daten: dict) -> dict:
        """Name, Wiederholungen oder Startzeit einer Phase ändern."""
        daten = daten or {}
        lane = self._lane(daten.get("phase"))
        if lane is None:
            return self._melde("Phase nicht gefunden.", "err")
        feld, wert = daten.get("feld"), daten.get("wert")
        if feld == "name":
            # Nur Loop-Phasen tragen einen Namen: INIT und END heissen in der Datei
            # gar nicht, `board_to_sequence()` wirft ihren Namen weg. Eine Umbenennung
            # dort anzunehmen hiesse, sie beim nächsten Öffnen still zu verlieren.
            if lane.kind != LANE_LOOP:
                return self._melde("INIT und END tragen keinen eigenen Namen.", "warn")
            lane.name = str(wert or "").strip() or lane.name
        elif feld == "wiederholungen":
            lane.repeat = max(1, int(wert or 1))
        elif feld == "start":
            roh = str(wert or "").strip()
            if not roh:
                lane.scheduled_start = None
            else:
                m = re.fullmatch(r"(\d{1,2}):(\d{2})", roh)
                if not m:
                    return self._melde(f"Startzeit '{roh}' — erwartet HH:MM.", "warn")
                hh, mm = int(m.group(1)), int(m.group(2))
                if not (0 <= hh <= 23 and 0 <= mm <= 59):
                    return self._melde(f"Startzeit '{roh}' ausserhalb 00:00–23:59.", "warn")
                lane.scheduled_start = f"{hh:02d}:{mm:02d}"
        else:
            return self._melde(f"Unbekanntes Feld '{feld}'.", "err")
        return self._geaendert()

    def phase_skalieren(self, daten: dict) -> dict:
        """Multipliziert alle Wartezeiten einer Phase mit demselben Faktor."""
        lane = self._lane((daten or {}).get("phase"))
        if lane is None:
            return self._melde("Phase nicht gefunden.", "err")
        try:
            faktor = float(str((daten or {}).get("faktor") or "").replace(",", "."))
        except ValueError:
            return self._melde("Der Faktor muss eine Zahl sein.", "warn")
        if faktor <= 0:
            return self._melde("Der Faktor muss grösser als 0 sein.", "warn")
        geaendert = 0
        for step in lane.steps:
            if step.delay_before > 0:
                step.delay_before = round(step.delay_before * faktor, 2)
                geaendert += 1
            if step.delay_max:
                step.delay_max = round(step.delay_max * faktor, 2)
        return self._geaendert(
            f"{geaendert} Wartezeit(en) in '{lane.name}' × {faktor:g} skaliert.")

    # --------------------------------------------------------------- Auswahl

    def _auswahl_leeren(self) -> None:
        self.sel_lane, self.sel_rows = None, set()

    def _auswahl_setzen(self, lane: Lane, row: int) -> None:
        self.sel_lane, self.sel_rows = lane, {row}

    def waehlen(self, daten: dict) -> dict:
        """Klick auf eine Karte. `modus`: einzeln / dazu / bereich.

        Die Auswahl fängt in einer anderen Phase immer neu an — siehe
        Klassen-Docstring: Sammelaktionen brauchen genau eine Phase.
        """
        daten = daten or {}
        lane = self._lane(daten.get("phase"))
        if lane is None:
            self._auswahl_leeren()
            return self.snapshot()
        row = int(daten.get("zeile", 0))
        if not (0 <= row < len(lane.steps)):
            self._auswahl_leeren()
            return self.snapshot()
        modus = daten.get("modus") or "einzeln"
        if modus == "dazu" and self.sel_lane is lane:
            self.sel_rows.symmetric_difference_update({row})
            if not self.sel_rows:
                self._auswahl_leeren()
        elif modus == "bereich" and self.sel_lane is lane and self.sel_rows:
            von, bis = min(self.sel_rows | {row}), max(self.sel_rows | {row})
            self.sel_rows = set(range(von, bis + 1))
        else:
            self._auswahl_setzen(lane, row)
        return self.snapshot()

    def auswahl_leeren(self, daten: Optional[dict] = None) -> dict:
        self._auswahl_leeren()
        return self.snapshot()

    # -------------------------------------------------------------- Struktur

    def block_anhaengen(self, daten: dict) -> dict:
        """Blanko-Block ans Ende einer Phase. Hat noch keine Stelle — deshalb (0,0)."""
        lane = self._lane((daten or {}).get("phase"))
        if lane is None:
            return self._melde("Phase nicht gefunden.", "err")
        self.board.add_step(lane, SequenceStep(x=0, y=0, delay_before=0.0))
        self._auswahl_setzen(lane, len(lane.steps) - 1)
        return self._geaendert()

    def punkt_einfuegen(self, daten: dict) -> dict:
        """Punkt aus der Palette als Klick-Block einsetzen (mit `point_id`)."""
        daten = daten or {}
        lane = self._lane(daten.get("phase"))
        punkt = self._punkt(daten.get("punkt"))
        if lane is None or punkt is None:
            return self._melde("Punkt oder Phase nicht gefunden.", "err")
        at = daten.get("zeile")
        at = len(lane.steps) if at is None else max(0, min(int(at), len(lane.steps)))
        self.board.add_step(lane, step_from_point(punkt), at=at)
        self._auswahl_setzen(lane, at)
        return self._geaendert()

    def _verschiebe(self, quelle: Lane, rows: list[int], ziel: Lane, at: int) -> None:
        """Trägt `rows` aus `quelle` in `ziel` ab Position `at` ein.

        Der eine Weg für beides: Umsortieren innerhalb einer Phase und Verschieben
        zwischen Phasen — Letzteres gibt es im Konsolen-Editor gar nicht.
        """
        schritte = [quelle.steps[i] for i in sorted(rows)]
        if not schritte:
            return
        # Wie viele der entfernten Schritte lagen VOR der Zielposition? Um so viele
        # rutscht sie nach vorne — aber nur, wenn aus derselben Phase entfernt wird.
        if quelle is ziel:
            at -= sum(1 for i in rows if i < at)
        for i in sorted(rows, reverse=True):
            self.board.delete_step(quelle, i)
        at = max(0, min(at, len(ziel.steps)))
        for versatz, schritt in enumerate(schritte):
            self.board.add_step(ziel, schritt, at=at + versatz)
        self.sel_lane = ziel
        self.sel_rows = set(range(at, at + len(schritte)))
        self._dirty = True

    def ziehen(self, daten: dict) -> dict:
        """Ziel eines Drag&Drop mit Karten."""
        daten = daten or {}
        quelle = self._lane(daten.get("von_phase"))
        ziel = self._lane(daten.get("nach_phase"))
        if quelle is None or ziel is None:
            return self.snapshot()
        von_zeile = int(daten.get("von_zeile", 0))
        at = int(daten.get("nach_zeile", 0))
        # Wird ein Schritt aus der aktuellen Auswahl gezogen, wandert die ganze
        # Auswahl mit — sonst nur der angefasste.
        rows = (sorted(self.sel_rows)
                if (self.sel_lane is quelle and von_zeile in self.sel_rows)
                else [von_zeile])
        self._verschiebe(quelle, rows, ziel, at)
        return self._melde("")

    def auswahl_verschieben(self, daten: dict) -> dict:
        """Verschiebt die Auswahl als Block um eine Position (−1 hoch, +1 runter)."""
        delta = int((daten or {}).get("delta", 0))
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
        folge = rows if delta < 0 else list(reversed(rows))
        self.sel_rows = {self.board.move_step(lane, idx, delta) for idx in folge}
        return self._geaendert()

    def auswahl_duplizieren(self, daten: Optional[dict] = None) -> dict:
        """Legt Kopien der gewählten Blöcke direkt hinter die Auswahl.

        Die Kopie zeigt auf denselben Punkt: ein Duplikat ist erst mal derselbe
        Klick, und ein zweiter Punkt an derselben Stelle wäre die Doppelung, die
        `punkt_fuer_stelle()` überall sonst vermeidet.

        Kopiert wird tief — `else_config`, `wait_condition` und `verify_condition`
        sind eigene Objekte, sonst änderte ein Griff an der Kopie das Original mit.
        """
        lane = self.sel_lane
        if lane is None or not self.sel_rows:
            return self._melde("Nichts ausgewählt — erst einen Block anklicken.", "warn")
        rows = sorted(self.sel_rows)
        # Alle Kopien hinter den LETZTEN Gewählten, in der Reihenfolge der
        # Vorlagen. Jede einzeln hinter ihr Original zu setzen zerrisse eine
        # Mehrfachauswahl in abwechselnd Original/Kopie.
        ziel = rows[-1] + 1
        for versatz, idx in enumerate(rows):
            self.board.add_step(lane, copy.deepcopy(lane.steps[idx]), ziel + versatz)
        # Die Kopien sind die neue Auswahl: man will sie gleich verschieben oder
        # umstellen, nicht erneut suchen.
        self.sel_rows = {ziel + i for i in range(len(rows))}
        return self._geaendert(f"{_bloecke(len(rows))} dupliziert.")

    def auswahl_loeschen(self, daten: Optional[dict] = None) -> dict:
        lane = self.sel_lane
        if lane is None or not self.sel_rows:
            return self.snapshot()
        # Von hinten löschen, sonst verschieben sich die noch offenen Indizes.
        for idx in sorted(self.sel_rows, reverse=True):
            self.board.delete_step(lane, idx)
        anzahl = len(self.sel_rows)
        self._auswahl_leeren()
        return self._geaendert(f"{_bloecke(anzahl)} gelöscht.")

    # ---------------------------------------------------------- Block-Felder

    def _else_aufraeumen(self, step: SequenceStep) -> str:
        """Entfernt ein ELSE, das nach dieser Änderung nichts mehr auslösen kann.

        Wer den Trigger wegnimmt oder den Typ umstellt, hat den einzigen Auslöser
        entfernt; stehenzulassen hiesse, die Ersatzaktion unsichtbar in der Datei zu
        behalten, denn der Abschnitt fällt mit dem Auslöser weg.

        Nur bei einer Änderung, nie beim Laden: eine Datei, die ein wirkungsloses
        ELSE mitbringt, wird nicht stillschweigend beschnitten.

        Gibt den Meldungstext zurück (leer, wenn nichts zu tun war).
        """
        if step.else_config is None or else_greift(step):
            return ""
        step.else_config = None
        return "ELSE entfernt — dieser Block kann es nicht mehr auslösen."

    def block_typ(self, daten: dict) -> dict:
        """Stellt den Block-Typ um.

        FARBE+KLICK braucht einen Punkt — er ist die Quelle für Stelle UND Farbe.
        Ohne Punkt wird der Wechsel abgelehnt: lieber gar keine Bedingung als eine,
        die niemand mehr nachziehen kann.
        """
        typ = (daten or {}).get("typ")
        lane, row, step = self._einzelner()
        if step is None or typ not in BLOCK_LABELS:
            return self.snapshot()
        if (typ == BLOCK_WAIT_CLICK and step.wait_condition is None
                and step.point_id is None):
            return self._melde("FARBE+KLICK braucht einen Punkt — erst eine Stelle wählen.",
                               "warn")
        set_block_type(step, typ)
        self._punkte_anwenden()
        weg = self._else_aufraeumen(step)
        return self._geaendert(weg, "warn" if weg else "ok")

    def block_setzen(self, daten: dict) -> dict:
        """Ein einfaches Feld des gewählten Schritts setzen."""
        daten = daten or {}
        feld, wert = daten.get("feld"), daten.get("wert")
        lane, row, step = self._einzelner()
        if step is None:
            return self.snapshot()
        wandeln = _FELDER.get(feld)
        if wandeln is None:
            return self._melde(f"Unbekanntes Feld '{feld}'.", "err")
        try:
            setattr(step, feld, wandeln(wert))
        except (TypeError, ValueError):
            return self._melde(f"'{wert}' passt nicht zu {feld}.", "warn")
        return self._geaendert()

    def block_bereich(self, daten: dict) -> dict:
        """Screenshot-Bereich setzen (`werte` = [x1,y1,x2,y2]) oder auf Vollbild zurück."""
        daten = daten or {}
        lane, row, step = self._einzelner()
        if step is None:
            return self.snapshot()
        werte = daten.get("werte")
        if not werte:
            step.screenshot_region = None
        else:
            try:
                step.screenshot_region = tuple(int(v) for v in werte[:4])
            except (TypeError, ValueError):
                return self._melde("Bereich braucht vier ganze Zahlen.", "warn")
        return self._geaendert()

    def bereich_aufnehmen(self, daten: Optional[dict] = None) -> dict:
        """Beide Ecken des Screenshot-Bereichs mit der Maus setzen — in einem Zug.

        Vier Zahlenfelder sind kein Weg, einen Bildschirmbereich zu bestimmen: Maus
        hin, ENTER, zweite Ecke, ENTER. Beide Ecken in EINEM Aufruf, sonst müsste
        die Hand mitten in der Aufnahme zum Fenster zurückfahren.

        Abgebrochen wird bei ESC und Zeitablauf vollständig — auch nach der ersten
        Ecke bleibt der alte Bereich stehen. Der Zahlenweg bleibt daneben stehen.
        """
        lane, row, step = self._einzelner()
        if step is None:
            return self.snapshot()

        # Erst hier importiert: das Modul soll ohne Windows ladbar bleiben, und
        # die Tests messen alles andere an dieser Klasse plattformfrei.
        from ...utils.io import warte_auf_taste
        from ...winapi import get_cursor_pos

        ecken = []
        for _ in (1, 2):
            taste = warte_auf_taste(("enter", "escape"), timeout=60.0)
            if taste != "enter":
                return self._melde(
                    "Abgebrochen — der Bereich bleibt, wie er war."
                    if taste == "escape" else
                    "Nichts gedrückt — der Bereich bleibt, wie er war.", "warn")
            ecken.append(get_cursor_pos())

        (x1, y1), (x2, y2) = ecken
        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)
        if x2 - x1 < 2 or y2 - y1 < 2:
            return self._melde(
                f"Bereich zu klein: {x2 - x1}×{y2 - y1} Pixel — nichts geändert.", "warn")

        step.screenshot_region = (x1, y1, x2, y2)
        self._dirty = True
        return self._melde(f"Bereich {x2 - x1}×{y2 - y1} bei ({x1},{y1}).", "ok")

    def _stelle_abwarten(self) -> tuple:
        """Wartet auf ENTER und gibt `(x, y, "")` zurück — bei Abbruch `(None, None, Grund)`.

        Der gemeinsame Teil von „Stelle mit der Maus setzen" und „Maus parken": das
        Fenster hat den Fokus, das Spiel nicht — gefragt wird deshalb über eine
        globale Taste.
        """
        # Erst hier importiert — das Modul bleibt ohne Windows ladbar.
        from ...utils.io import warte_auf_taste
        from ...winapi import get_cursor_pos

        taste = warte_auf_taste(("enter", "escape"), timeout=60.0)
        if taste != "enter":
            return None, None, ("Abgebrochen" if taste == "escape" else "Nichts gedrückt")
        x, y = get_cursor_pos()
        return x, y, ""

    def maus_stelle(self, daten: Optional[dict] = None) -> dict:
        """Die aktuelle Mausposition — für die Einstellungen, ohne Punkt anzulegen.

        `punkt_aufnehmen()` ist der Weg für einen Block; `scan_park_mouse` ist
        aber kein Punkt und gehört nicht in die Punktliste der `sequence.json`. Übrig bleibt die
        Geste: Maus hin, ENTER.
        """
        x, y, meldung = self._stelle_abwarten()
        if x is None:
            return {"ok": False, "meldung": meldung + " — nichts geändert."}
        return {"ok": True, "x": x, "y": y}

    def punkt_aufnehmen(self, daten: Optional[dict] = None) -> dict:
        """Setzt die Stelle des Blocks auf die aktuelle Mausposition.

        Derselbe Weg wie `bereich_aufnehmen()`, nur mit einer Ecke. Gesetzt wird über
        dieselben Methoden wie sonst, damit die üblichen Regeln gelten: ein
        vorhandener Punkt an derselben Stelle wird wiederverwendet.
        """
        lane, row, step = self._einzelner()
        if step is None:
            return self.snapshot()

        x, y, meldung = self._stelle_abwarten()
        if x is None:
            return self._melde(meldung + " — die Stelle bleibt, wie sie war.", "warn")
        from ...winapi import get_screen_pixel

        if step.point_id is not None:
            # Vorhandenen Punkt verschieben: dieselbe Regel wie beim Tippen der
            # Zahlen — der Punkt gehört nicht diesem Block allein.
            self.punkt_setzen({"punkt": step.point_id, "feld": "x", "wert": x})
            self.punkt_setzen({"punkt": step.point_id, "feld": "y", "wert": y})
        else:
            self.punkt_anlegen({"x": x, "y": y})

        # Farbe gleich mitmessen: ein Punkt ohne Farbe taugt für keinen
        # Farb-Trigger, und der Bildschirm zeigt gerade genau das Richtige —
        # deshalb steht man ja mit der Maus dort.
        punkt = self._punkt(step.point_id)
        farbe = get_screen_pixel(x, y)
        if punkt is not None and farbe is not None:
            punkt.color = tuple(farbe)
            self._punkte_anwenden()
        gemessen = f" · Farbe {tuple(farbe)}" if farbe else ""
        return self._geaendert(f"Stelle: ({x}, {y}){gemessen}")

    def block_punkt(self, daten: dict) -> dict:
        """Setzt den Punkt des Schritts — Stelle, Name und Farbe kommen mit.

        Prüft der Schritt seine eigene Stelle (Farb-Trigger auf demselben Punkt),
        zieht der Trigger mit: sonst klickt der Schritt woanders hin, als er
        vorher geprüft hat.
        """
        daten = daten or {}
        lane, row, step = self._einzelner()
        if step is None:
            return self.snapshot()
        punkt = self._punkt(daten.get("punkt"))
        if punkt is None:
            return self._melde("Punkt nicht gefunden.", "warn")
        alt = step.point_id
        step.point_id = punkt.id
        for cond in (step.wait_condition, step.verify_condition):
            if cond is not None and (cond.point_id == alt or cond.point_id is None):
                cond.point_id = punkt.id
        self._punkte_anwenden()
        return self._geaendert()

    def block_trigger(self, daten: dict) -> dict:
        """Farb-Trigger des Schritts: kein / da / weg, plus 'nur prüfen'.

        Der Punkt ist die Quelle für Stelle UND Farbe. Ohne `point_id` gibt es
        nichts zu prüfen — dann passiert nichts, statt eine Bedingung auf (0,0)
        anzulegen. Dieselbe Haltung wie „es gibt bewusst keinen Rückfallwert".
        """
        daten = daten or {}
        lane, row, step = self._einzelner()
        if step is None:
            return self.snapshot()
        feld = "verify_condition" if daten.get("welche") == "verify" else "wait_condition"
        return self._trigger_setzen(step, feld, daten)

    def _trigger_setzen(self, step: SequenceStep, feld: str, daten: dict) -> dict:
        wahl = daten.get("wahl")
        cond: Optional[WaitCondition] = getattr(step, feld)
        if wahl == TRIGGER_KEIN:
            setattr(step, feld, None)
            weg = self._else_aufraeumen(step)
            return self._geaendert(weg, "warn" if weg else "ok")
        if cond is None:
            punkt_id = daten.get("punkt", step.point_id)
            punkt = self._punkt(punkt_id)
            if punkt is None:
                return self._melde(
                    "Ohne Punkt gibt es nichts zu prüfen — erst einen wählen.", "warn")
            cond = WaitCondition(point_id=punkt.id, pixel=(punkt.x, punkt.y),
                                 color=tuple(punkt.color) if punkt.color else (0, 0, 0))
            setattr(step, feld, cond)
        if wahl in (TRIGGER_DA, TRIGGER_WEG):
            cond.until_gone = (wahl == TRIGGER_WEG)
        if "pruefen" in daten:
            cond.check_only = bool(daten["pruefen"])
        if daten.get("punkt") is not None:
            punkt = self._punkt(daten["punkt"])
            if punkt is not None:
                cond.point_id = punkt.id
                self._punkte_anwenden()
        return self._geaendert()

    def block_else(self, daten: dict) -> dict:
        """ELSE-Aktion setzen oder entfernen (leere Aktion = keine)."""
        daten = daten or {}
        lane, row, step = self._einzelner()
        if step is None:
            return self.snapshot()
        aktion = daten.get("aktion") or ""
        if not aktion:
            step.else_config = None
            return self._geaendert()
        if aktion not in ELSE_AKTIONEN:
            return self._melde(f"Unbekannte ELSE-Aktion '{aktion}'.", "err")
        ec = ensure_else(step, aktion)
        if "punkt" in daten and daten["punkt"] is not None:
            punkt = self._punkt(daten["punkt"])
            if punkt is None:
                return self._melde("Punkt nicht gefunden.", "warn")
            # Nur die Referenz zählt: `x`/`y`/`name` sind abgeleitet und stehen
            # nicht in der Datei. Der DPG-Vorgänger liess genau diese drei von Hand
            # eintippen — beim nächsten Öffnen war die Eingabe weg.
            ec.point_id = punkt.id
            self._punkte_anwenden()
        if "taste" in daten:
            ec.key = str(daten["taste"] or "").strip() or None
        if "delay" in daten:
            ec.delay = max(0.0, float(daten["delay"] or 0))
        return self._geaendert()

    # ---------------------------------------------------------------- Punkte

    def punkt_setzen(self, daten: dict) -> dict:
        """Verschiebt oder benennt einen Punkt — alle Schritte darauf ziehen mit.

        Die Zahlenfelder verschieben den PUNKT, nicht den Schritt: die Sequenz
        hält keine Koordinaten mehr, eine hier eingetippte Stelle wäre sonst beim
        Speichern verloren.
        """
        daten = daten or {}
        punkt = self._punkt(daten.get("punkt"))
        if punkt is None:
            return self._melde("Punkt nicht gefunden.", "warn")
        feld, wert = daten.get("feld"), daten.get("wert")
        try:
            if feld == "x":
                punkt.x = int(wert)
            elif feld == "y":
                punkt.y = int(wert)
            elif feld == "name":
                punkt.name = str(wert or "")
            elif feld == "farbe":
                # Die Farbe ist das, was ein Farb-Trigger prueft — sie von Hand zu
                # setzen ist deshalb eine echte Aenderung am Verhalten, nicht bloss
                # Anzeige. Leer heisst „keine gemessene Farbe", nicht Schwarz.
                punkt.color = _rgb(wert)
            else:
                return self._melde(f"Unbekanntes Feld '{feld}'.", "err")
        except (TypeError, ValueError):
            return self._melde(f"'{wert}' ist keine Zahl.", "warn")
        self._punkte_anwenden()
        return self._geaendert()

    def punkt_anlegen(self, daten: dict) -> dict:
        """Legt einen Punkt an und hängt ihn an den gewählten Schritt.

        Für den Blanko-Block: er hat noch keine Stelle und bliebe ohne Punkt ein
        Klick auf (0,0).
        """
        daten = daten or {}
        lane, row, step = self._einzelner()
        if step is None:
            return self.snapshot()
        try:
            x, y = int(daten.get("x", 0)), int(daten.get("y", 0))
        except (TypeError, ValueError):
            return self._melde("Stelle braucht zwei ganze Zahlen.", "warn")
        # Denselben Punkt wiederverwenden, wenn schon einer dort liegt: klickt eine
        # Sequenz zweimal denselben Knopf, ist das EIN Punkt — sonst wandert beim
        # Nachjustieren nur die Hälfte mit.
        punkt = next((p for p in self.points if p.x == x and p.y == y), None)
        if punkt is None:
            punkt = PalettePoint(
                id=max([p.id for p in self.points], default=0) + 1,
                x=x, y=y,
                name=str(daten.get("name") or step.name or "Sequenz-Studio"),
                color=tuple(step.recorded_color) if step.recorded_color else None,
                source="Sequenz-Studio")
            self.points.append(punkt)
        step.point_id = punkt.id
        self._punkte_anwenden()
        return self._geaendert(f"Punkt #{punkt.id} gesetzt.")
