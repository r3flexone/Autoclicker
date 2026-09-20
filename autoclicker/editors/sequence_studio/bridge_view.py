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
    ELSE_ACTIONS,
    SCAN_FIELD,
    SCAN_MODES,
    TYPE_ORDER,
    WAIT_TIMEOUT,
    _hex,
    _position,
    _wait_text,
    else_applies,
    trigger_name,
)
from .model import (
    BLOCK_COLORS,
    BLOCK_LABELS,
    LANE_LOOP,
    Lane,
    PalettePoint,
    ink_color,
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
        # Die Auswahl gehört zum Stand, den die Seite gerade sieht: Auswählen
        # legt keinen Abzug ab, also merkt sich der nächste Abzug sie von hier.
        self._edit_current["sel"] = self._edit_selection()
        return {
            "file": str(self.filepath),
            "start_view": self.start_view,
            "name": self.board.name,
            "description": self.board.description,
            "cycles": self.board.total_cycles,
            "dirty": self._dirty,
            "undo": self._edit_json(),
            # Die Seite zeigt waehrend eines Maus-Griffs einen Countdown.
            # Die Zahl kommt von hier, damit er nicht neben dem echten
            # Zeitablauf der Bruecke laeuft.
            "wait_timeout": WAIT_TIMEOUT,
            "status": {"text": text, "kind": kind},
            "question": ask,
            "sequences": sorted(name for name, _ in list_available_sequences()),
            "scan_names": self._scan_names(),
            "types": [{"key": t, "label": BLOCK_LABELS[t],
                       "color": _hex(BLOCK_COLORS[t]),
                       "ink": ink_color(BLOCK_COLORS[t])} for t in TYPE_ORDER],
            "scan_modes": SCAN_MODES,
            "else_actions": ELSE_ACTIONS,
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
        if stamp != self._cfg_state:
            self._cfg_state = stamp
            from ...config import CONFIG
            raw, error = self._config_file()
            if error:
                self._cfg_info = {}
            else:
                action = raw.get("pixel_timeout_action", CONFIG.pixel_timeout_action)
                self._cfg_info = {
                    "seconds": raw.get("pixel_wait_timeout", CONFIG.pixel_wait_timeout),
                    "consequence": TIMEOUT_TEXT.get(action, action),
                    "emergency_stop": raw.get("pixel_max_consecutive_timeouts",
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
        def names(list_all) -> list[str]:
            try:
                return sorted(name for name, _ in list_all(self.board.name))
            except OSError:
                return []

        bosses = names(list_available_boss_scans)
        return {
            BLOCK_ITEM_SCAN: names(list_available_item_scans),
            BLOCK_ICON_SCAN: names(list_available_icon_scans),
            BLOCK_BOSS_SCAN: bosses,
            BLOCK_BOSS_WATCHER: bosses,
        }

    def _sel_index(self) -> Optional[int]:
        if self.sel_lane is None or self.sel_lane not in self.board.lanes:
            return None
        return self.board.lanes.index(self.sel_lane)

    def _point_json(self, p: PalettePoint) -> dict:
        # `usages`: wie oft der Punkt gebraucht wird — die Liste zeigte es nicht,
        # obwohl `_point_usages()` es fuer den Inspektor laengst rechnete. Ein
        # Punkt, den vier Bloecke teilen, ist genau der, den man vor dem
        # Verschieben kennen will; einer mit 0 ist ein Rest der Aufnahme.
        return {"id": p.id, "name": p.name or f"Punkt {p.id}", "x": p.x, "y": p.y,
                "color": _hex(p.color), "source": p.source,
                "usages": len(self._point_usages(p.id))}

    def _phase_json(self, index: int, lane: Lane) -> dict:
        return {
            "index": index,
            "kind": lane.kind,
            "name": lane.name,
            "repeat": lane.repeat,
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

        def shared(field: str):
            values = [getattr(step, field) for step in steps]
            mixed = bool(values) and any(value != values[0] for value in values[1:])
            return (None if mixed or not values else values[0]), mixed

        delay_before, before_mixed = shared("delay_before")
        delay_max, max_mixed = shared("delay_max")
        return {
            "phase": self._sel_index(),
            "rows": rows,
            "delay_before": delay_before,
            "delay_before_mixed": before_mixed,
            "delay_max": delay_max,
            "delay_max_mixed": max_mixed,
        }

    def _block_json(self, lane: Lane, row: int, step: SequenceStep) -> dict:
        """Eine Karte im Board — knapp genug, dass 50 davon untereinander passen."""
        type_value = block_type(step)
        wc = step.wait_condition
        field = SCAN_FIELD.get(type_value)
        point = self._point(step.point_id)
        block = {
            "row": row,
            "type": type_value,
            "label": BLOCK_LABELS[type_value],
            "color": _hex(BLOCK_COLORS[type_value]),
            # Die Schriftfarbe der Kopfzeile folgt der Typfarbe — fest dunkel
            # fiel sie auf Boss-Watcher (2,2:1) und vier weiteren Typen durch.
            "ink": ink_color(BLOCK_COLORS[type_value]),
            # Kein Rückfall aufs Typ-Label: das steht schon als Marke daneben, und
            # zweimal dasselbe Wort auf einer Karte ist keine Information.
            "title": step.name or "",
            "rows": self._lines(step, type_value),
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
            # Alle Punkte, an denen der Block haengt (Stelle, Pruef-Pixel,
            # Nachpruefung, ELSE): die Punkte-Liste markiert damit, wer einen
            # Punkt benutzt — in beide Richtungen.
            "points": sorted({pid for pid in (
                step.point_id, wc.point_id if wc else None,
                step.verify_condition.point_id if step.verify_condition else None,
                step.else_config.point_id if step.else_config else None,
            ) if pid is not None}),
            "color_swatch": _hex(wc.color) if wc else None,
            "color_text": self._trigger_text(wc) if wc else "",
            "else_text": self._else_text(step),
            # Ein ELSE, das nie feuern kann, steht sonst als Zusage auf der Karte.
            "else_applies": else_applies(step),
            # Ein Scan ohne Namen wird beim Speichern abgelehnt — die Karte sagt
            # das schon vorher, sonst sucht man den Block hinterher in vier Phasen.
            "warning": ("Name fehlt" if field and not (getattr(step, field) or "").strip()
                        else None),
        }
        return block

    def _lines(self, step: SequenceStep, type_value: str) -> list[dict]:
        """Ein bis drei knappe Zeilen im Kartenkörper, je `{label, text}`.

        Die Wartezeit steht nur da, wenn es eine gibt: „sofort" unter jedem
        zweiten Block ist Rauschen, und in der Liste zählt, dass 50 Karten
        untereinander lesbar bleiben.

        **Jede Zeile trägt ein Etikett** (STELLE, WARTE, …). Bei fünfzig Karten
        untereinander findet das Auge das Etikett schneller als den Wert — und
        „+1.5s" ohne Etikett musste man erst als Wartezeit erkennen.

        Bei einem Block mit Punkt ist die **erste** Zeile seine Stelle — daran
        hängt die Ansicht das Farbfeldchen des Punkts (`point_color`).
        """
        def row(label: str, text: str) -> dict:
            return {"label": label, "text": text}

        if type_value == BLOCK_SCREENSHOT:
            r = step.screenshot_region
            return [row("BEREICH", f"{r[0]},{r[1]} → {r[2]},{r[3]}" if r else "Vollbild")]
        if type_value in SCAN_FIELD:
            name = (getattr(step, SCAN_FIELD[type_value]) or "").strip() or "(kein Name)"
            mode = f" · {step.item_scan_mode}" if type_value == BLOCK_ITEM_SCAN else ""
            lines = [row("SCAN", f"{name}{mode}")]
        elif type_value == BLOCK_KEY:
            lines = [row("TASTE", f"„{step.key_press}“")]
        elif type_value == BLOCK_WAIT:
            lines = []
        else:
            lines = [row("STELLE", _position(step))]
        if step.scroll:
            # Das Rad kann kein Editor setzen, eine Aufnahme bringt es aber mit.
            # Ungenannt sähe der Block aus wie ein gewöhnlicher Klick.
            lines.append(row("RAD", f"{step.scroll:+d}"))
        if step.delay_before or step.delay_max or not lines:
            lines.append(row("WARTE", _wait_text(step)))
        return lines

    def _trigger_text(self, wc: WaitCondition) -> str:
        what = "prüft" if wc.check_only else "wartet bis"
        where_to = "weg" if wc.until_gone else "da"
        return f"{what} RGB{tuple(wc.color)} {where_to}"

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
        type_value = block_type(step)
        wc, vc, ec = step.wait_condition, step.verify_condition, step.else_config
        return {
            "phase": self.board.lanes.index(lane),
            "row": row,
            "type": type_value,
            "label": BLOCK_LABELS[type_value],
            "color": _hex(BLOCK_COLORS[type_value]),
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
            "point_others": (self._point_usages(step.point_id, except_step=step)
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
            "else_applies": else_applies(step),
            "else_point": ec.point_id if ec else None,
            "else_key": (ec.key or "") if ec else "",
            "else_delay": ec.delay if ec else 0,
        }

    # --------------------------------------------------------------- Zustand

    def _report(self, text: str, kind: str = "ok", *, offer: bool = False) -> dict:
        self._status = (text, kind)
        self._edit_offer = offer
        return self.snapshot()

    def _changed(self, text: str = "", kind: str = "ok", *, group: Optional[str] = None,
                 offer: bool = False, what: str = "") -> dict:
        """Eine Änderung an Board oder Punkten: Abzug ablegen, melden.

        `what` benennt den Schritt auf dem Rückgängig-Stapel, wenn der
        Meldungstext dafür nicht taugt (leer oder eine Warnung); `offer` hängt
        den Rückgängig-Knopf an die Meldung (löschen, Typwechsel, verschieben).
        """
        self._edit_commit(what or text.rstrip("."), group)
        return self._report(text, kind, offer=offer)

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
