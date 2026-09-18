"""Momentaufnahme und JSON-Projektionen der Studio-Brücke."""

from pathlib import Path
from typing import Optional

from ...models import (
    BLOCK_BOSS_SCAN,
    BLOCK_BOSS_WATCHER,
    BLOCK_ICON_SCAN,
    BLOCK_ITEM_SCAN,
    BLOCK_KEY,
    BLOCK_SCREENSHOT,
    BLOCK_WAIT,
    ELSE_CLICK,
    ELSE_KEY,
    ELSE_RESTART,
    ELSE_SKIP,
    ELSE_SKIP_CYCLE,
    SCAN_MODE_ALL,
    TIMEOUT_TEXT,
    SequenceStep,
    WaitCondition,
    block_type,
)
from ...persistence import (
    list_available_boss_scans,
    list_available_icon_scans,
    list_available_item_scans,
    list_available_sequences,
)
from .bridge_contract import (
    ELSE_AKTIONEN,
    SCAN_FELD,
    SCAN_MODES,
    TYP_REIHENFOLGE,
    WARTE_TIMEOUT,
    _hex,
    _stelle,
    _wartetext,
    else_greift,
    trigger_name,
)
from .model import (
    BLOCK_COLORS,
    BLOCK_LABELS,
    LANE_LOOP,
    Lane,
    PalettePoint,
)


class BridgeViewMixin:
    """Erzeugt den vollständigen, JSON-fähigen Zustand für die Weboberfläche."""

    def snapshot(self, data: Optional[dict] = None) -> dict:
        """Der komplette Zustand als JSON-Werte — alles, was die Ansicht braucht.

        `data` wird nicht gelesen, muss aber dastehen: die Oberfläche ruft jede
        Brücken-Methode über denselben Helfer (`call()`), und der reicht `null`
        durch, wenn es nichts zu übergeben gibt. Ohne den Parameter scheitert der
        allererste Aufruf mit „takes 1 positional argument" — und weil das der
        Aufruf ist, der die Ansicht überhaupt erst füllt, bleibt das Fenster leer.
        """
        text, kind = self._status
        ask, self._ask = self._ask, None
        return {
            "file": str(self.filepath),
            "start_view": self.start_view,
            "name": self.board.name,
            "description": self.board.description,
            "cycles": self.board.total_cycles,
            "dirty": self._dirty,
            # Die Seite zeigt waehrend eines Maus-Griffs einen Countdown.
            # Die Zahl kommt von hier, damit er nicht neben dem echten
            # Zeitablauf der Bruecke laeuft.
            "wait_timeout": WARTE_TIMEOUT,
            "status": {"text": text, "kind": kind},
            "question": ask,
            "sequences": sorted(name for name, _ in list_available_sequences()),
            "scan_names": self._scan_names(),
            "types": [{"key": t, "label": BLOCK_LABELS[t],
                       "color": _hex(BLOCK_COLORS[t])} for t in TYP_REIHENFOLGE],
            "scan_modes": SCAN_MODES,
            "else_actions": ELSE_AKTIONEN,
            "without_else": self._without_else(),
            "phases": [self._phase_json(i, ln) for i, ln in enumerate(self.board.lanes)],
            "points": [self._point_json(p) for p in self.points],
            "selection": self._selection_json(),
            "block": self._block_detail(),
        }

    def _without_else(self) -> dict:
        """Was ohne ELSE nach dem Timeout passiert — laut `config.json`.

        Die Antwort steht in der Config des Hauptprozesses (`pixel_wait_timeout`,
        `pixel_timeout_action`), und die Voreinstellung bricht den GANZEN Zyklus ab,
        nicht nur den Schritt — genau der Unterschied entscheidet, ob man ELSE braucht.

        Gelesen wird am Zeitstempel der Datei, nicht bei jeder Momentaufnahme; und
        über `_config_file()` statt `load_config()`, denn die schreibt die Datei und
        gibt eine Konsolenzeile aus. Scheitert das Lesen, bleibt das Feld leer.
        """
        try:
            from ...config import CONFIG_FILE
            stamp = Path(CONFIG_FILE).stat().st_mtime
        except OSError:
            stamp = 0.0
        if stamp != self._cfg_stand:
            self._cfg_stand = stamp
            from ...config import CONFIG
            raw, fehler = self._config_file()
            if fehler:
                self._cfg_info = {}
            else:
                action = raw.get("pixel_timeout_action", CONFIG.pixel_timeout_action)
                self._cfg_info = {
                    "sekunden": raw.get("pixel_wait_timeout", CONFIG.pixel_wait_timeout),
                    "folge": TIMEOUT_TEXT.get(action, action),
                    "notbremse": raw.get("pixel_max_consecutive_timeouts",
                                         CONFIG.pixel_max_consecutive_timeouts)}
        return self._cfg_info

    def _scan_names(self) -> dict:
        """Welche Scan-Konfigurationen es gibt — je Block-Typ eine Liste.

        Ein Scan-Block verweist per Name auf eine Datei; ein Tippfehler ergab einen
        Block, den der Executor stillschweigend nicht ausführt. Hier steht, was
        tatsächlich auf Platte liegt — auswählen statt abschreiben.

        Der Boss-Watcher zieht dieselben Konfigurationen wie der Boss-Scan. Gelesen
        wird bei jeder Momentaufnahme, damit eine im Hauptprozess angelegte
        Konfiguration beim nächsten Klick auftaucht.
        """
        def names(auflisten) -> list[str]:
            try:
                return sorted(name for name, _ in auflisten(self.board.name))
            except OSError:
                return []

        bosse = names(list_available_boss_scans)
        return {
            BLOCK_ITEM_SCAN: names(list_available_item_scans),
            BLOCK_ICON_SCAN: names(list_available_icon_scans),
            BLOCK_BOSS_SCAN: bosse,
            BLOCK_BOSS_WATCHER: bosse,
        }

    def _sel_index(self) -> Optional[int]:
        if self.sel_lane is None or self.sel_lane not in self.board.lanes:
            return None
        return self.board.lanes.index(self.sel_lane)

    def _point_json(self, p: PalettePoint) -> dict:
        return {"id": p.id, "name": p.name or f"Punkt {p.id}", "x": p.x, "y": p.y,
                "color": _hex(p.color), "source": p.source}

    def _phase_json(self, index: int, lane: Lane) -> dict:
        return {
            "index": index,
            "kind": lane.kind,
            "name": lane.name,
            "wiederholungen": lane.repeat,
            "start": lane.scheduled_start or "",
            "deletable": lane.kind == LANE_LOOP,
            "blocks": [self._block_json(lane, row, s) for row, s in enumerate(lane.steps)],
        }

    def _selection_json(self) -> dict:
        """Auswahl samt gemeinsamen Werten für den Sammel-Inspektor."""
        rows = sorted(self.sel_rows)
        steps = [] if self.sel_lane is None else [
            self.sel_lane.steps[row] for row in rows
            if 0 <= row < len(self.sel_lane.steps)
        ]

        def gemeinsam(field: str):
            values = [getattr(step, field) for step in steps]
            gemischt = bool(values) and any(value != values[0] for value in values[1:])
            return (None if gemischt or not values else values[0]), gemischt

        delay_before, before_gemischt = gemeinsam("delay_before")
        delay_max, max_gemischt = gemeinsam("delay_max")
        return {
            "phase": self._sel_index(),
            "rows": rows,
            "delay_before": delay_before,
            "delay_before_gemischt": before_gemischt,
            "delay_max": delay_max,
            "delay_max_gemischt": max_gemischt,
        }

    def _block_json(self, lane: Lane, row: int, step: SequenceStep) -> dict:
        """Eine Karte im Board — knapp genug, dass 50 davon untereinander passen."""
        typ = block_type(step)
        wc = step.wait_condition
        field = SCAN_FELD.get(typ)
        point = self._point(step.point_id)
        block = {
            "row": row,
            "typ": typ,
            "label": BLOCK_LABELS[typ],
            "color": _hex(BLOCK_COLORS[typ]),
            # Kein Rückfall aufs Typ-Label: das steht schon als Marke daneben, und
            # zweimal dasselbe Wort auf einer Karte ist keine Information.
            "title": step.name or "",
            "rows": self._lines(step, typ),
            "checks": step.verify_condition is not None,
            "breakpoint": bool(step.breakpoint),
            "selected": self.sel_lane is lane and row in self.sel_rows,
            # **Die Farbe des Punkts steht auf jeder Karte, die einen hat.** Sie
            # stand nur an der Farb-Bedingung („wartet bis RGB(…) da"); ein reiner
            # Klick zeigte Koordinaten — und Koordinaten unterscheidet niemand
            # beim Überfliegen von 50 Karten, die Farbe des Knopfs schon. Die
            # Ansicht hängt sie an die erste Zeile, denn dort steht die Stelle
            # (`_lines`). Ohne gemessene Farbe kein Feldchen: ein leeres
            # Kästchen sagt nichts, was der Inspektor nicht besser sagt.
            "point_color": _hex(point.color) if point is not None else None,
            "color_swatch": _hex(wc.color) if wc else None,
            "color_text": self._trigger_text(wc) if wc else "",
            "else_text": self._else_text(step),
            # Ein ELSE, das nie feuern kann, steht sonst als Zusage auf der Karte.
            "else_greift": else_greift(step),
            # Ein Scan ohne Namen wird beim Speichern abgelehnt — die Karte sagt
            # das schon vorher, sonst sucht man den Block hinterher in vier Phasen.
            "warnung": ("Name fehlt" if field and not (getattr(step, field) or "").strip()
                        else None),
        }
        return block

    def _lines(self, step: SequenceStep, typ: str) -> list[str]:
        """Ein bis drei knappe Zeilen im Kartenkörper.

        Die Wartezeit steht nur da, wenn es eine gibt: „sofort" unter jedem
        zweiten Block ist Rauschen, und in der Liste zählt, dass 50 Karten
        untereinander lesbar bleiben.

        Bei einem Block mit Punkt ist die **erste** Zeile seine Stelle — daran
        hängt die Ansicht das Farbfeldchen des Punkts (`point_color`).
        """
        if typ == BLOCK_SCREENSHOT:
            r = step.screenshot_region
            return [f"Bereich {r[0]},{r[1]} → {r[2]},{r[3]}" if r else "Vollbild"]
        if typ in SCAN_FELD:
            name = (getattr(step, SCAN_FELD[typ]) or "").strip() or "(kein Name)"
            modus = f" · {step.item_scan_mode}" if typ == BLOCK_ITEM_SCAN else ""
            lines = [f"{name}{modus}"]
        elif typ == BLOCK_KEY:
            lines = [f"Taste „{step.key_press}“"]
        elif typ == BLOCK_WAIT:
            lines = []
        else:
            lines = [_stelle(step)]
        if step.scroll:
            # Das Rad kann kein Editor setzen, eine Aufnahme bringt es aber mit.
            # Ungenannt sähe der Block aus wie ein gewöhnlicher Klick.
            lines.append(f"Rad {step.scroll:+d}")
        if step.delay_before or step.delay_max or not lines:
            lines.append(_wartetext(step))
        return lines

    def _trigger_text(self, wc: WaitCondition) -> str:
        was = "prüft" if wc.check_only else "wartet bis"
        wohin = "weg" if wc.until_gone else "da"
        return f"{was} RGB{tuple(wc.color)} {wohin}"

    def _else_text(self, step: SequenceStep) -> str:
        ec = step.else_config
        if ec is None:
            return ""
        if ec.action == ELSE_CLICK:
            target = f"#{ec.point_id}" if ec.point_id is not None else "(kein Punkt)"
            return f"sonst: klick {target}"
        if ec.action == ELSE_KEY:
            return f"sonst: Taste „{ec.key or '?'}“"
        return {ELSE_SKIP: "sonst: Schritt überspringen",
                ELSE_SKIP_CYCLE: "sonst: Zyklus abbrechen",
                ELSE_RESTART: "sonst: Sequenz neu starten"}.get(ec.action, f"sonst: {ec.action}")

    def _single(self) -> tuple[Optional[Lane], int, Optional[SequenceStep]]:
        """Der eine gewählte Schritt — oder nichts, wenn es keiner oder mehrere sind."""
        if self.sel_lane is None or len(self.sel_rows) != 1:
            return None, -1, None
        row = next(iter(self.sel_rows))
        if not (0 <= row < len(self.sel_lane.steps)):
            return None, -1, None
        return self.sel_lane, row, self.sel_lane.steps[row]

    def _block_detail(self) -> Optional[dict]:
        """Alle Felder des gewählten Schritts für die Eigenschaften-Spalte."""
        lane, row, step = self._single()
        if step is None:
            return None
        typ = block_type(step)
        wc, vc, ec = step.wait_condition, step.verify_condition, step.else_config
        return {
            "phase": self.board.lanes.index(lane),
            "row": row,
            "typ": typ,
            "label": BLOCK_LABELS[typ],
            "color": _hex(BLOCK_COLORS[typ]),
            "name": step.name or "",
            "point_id": step.point_id,
            # **Wer den Punkt SONST noch benutzt, steht am Block.** X/Y und
            # „Stelle setzen" verschieben den Punkt, und jeder Block darauf
            # zieht mit — das stand nur im ⓘ. An einer echten Aufnahme hatte
            # `point_at_position()` den Klick auf denselben Knopf in Loop 1 und
            # Loop 4 zu EINEM Punkt zusammengelegt; wer dann Loop 1 eine
            # andere Stelle gab, verstellte Loop 4 mit und suchte den Fehler
            # in der Aufnahme („der Punkt war im Loop 4 an einer völlig
            # falschen Stelle"). Die Liste ist Zustand, also Text — nicht ⓘ.
            "point_others": (self._point_usages(step.point_id, ausser=step)
                             if step.point_id is not None else []),
            "x": step.x,
            "y": step.y,
            "captured_color": _hex(step.recorded_color),
            "delay_before": step.delay_before,
            "delay_max": step.delay_max or 0,
            "key_press": step.key_press or "",
            "item_scan": step.item_scan or "",
            "item_scan_mode": step.item_scan_mode or SCAN_MODE_ALL,
            "icon_scan": step.icon_scan or "",
            "boss_scan": step.boss_scan or "",
            "boss_watcher": step.boss_watcher or "",
            "wait_only": step.wait_only,
            "breakpoint": bool(step.breakpoint),
            "scroll": step.scroll or 0,
            "screenshot_region": list(step.screenshot_region) if step.screenshot_region else None,
            "trigger": trigger_name(wc),
            "trigger_point": wc.point_id if wc else None,
            "trigger_check": wc.check_only if wc else False,
            "verify": trigger_name(vc),
            "verify_point": vc.point_id if vc else None,
            "else_action": ec.action if ec else "",
            "else_greift": else_greift(step),
            "else_point": ec.point_id if ec else None,
            "else_taste": (ec.key or "") if ec else "",
            "else_delay": ec.delay if ec else 0,
        }

    # --------------------------------------------------------------- Zustand

    def _report(self, text: str, kind: str = "ok") -> dict:
        self._status = (text, kind)
        return self.snapshot()

    def _changed(self, text: str = "", kind: str = "ok") -> dict:
        self._dirty = True
        return self._report(text, kind)

    def _point(self, point_id) -> Optional[PalettePoint]:
        if point_id is None:
            return None
        return next((p for p in self.points if p.id == int(point_id)), None)

    def _points_apply(self) -> None:
        """Zieht die abgeleiteten Werte aller Schritte aus der Palette nach.

        Dasselbe, was `resolve_point_references()` vor jedem Lauf tut — nur hier
        im Editor, damit ein verschobener Punkt sofort an JEDEM Schritt sichtbar
        wird, der auf ihn zeigt. Der DPG-Vorgänger aktualisierte nur den gerade
        bearbeiteten Schritt; die übrigen zeigten bis zum nächsten Öffnen die
        alte Koordinate an, obwohl gespeichert längst die neue galt.
        """
        for lane in self.board.lanes:
            for step in lane.steps:
                p = self._point(step.point_id)
                if p is not None:
                    step.x, step.y = p.x, p.y
                    step.name = p.name or step.name
                    step.recorded_color = p.color
                for cond in (step.wait_condition, step.verify_condition):
                    q = self._point(cond.point_id) if cond is not None else None
                    if q is not None:
                        cond.pixel = (q.x, q.y)
                        if q.color:
                            cond.color = tuple(q.color)
                ec = step.else_config
                r = self._point(ec.point_id) if ec is not None else None
                if r is not None:
                    ec.x, ec.y, ec.name = r.x, r.y, r.name or ""

    # ------------------------------------------------------------ Sequenz-Ebene
