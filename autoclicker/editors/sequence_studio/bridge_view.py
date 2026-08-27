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
    SCAN_MODI,
    TYP_REIHENFOLGE,
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

    def snapshot(self, daten: Optional[dict] = None) -> dict:
        """Der komplette Zustand als JSON-Werte — alles, was die Ansicht braucht.

        `daten` wird nicht gelesen, muss aber dastehen: die Oberfläche ruft jede
        Brücken-Methode über denselben Helfer (`ruf()`), und der reicht `null`
        durch, wenn es nichts zu übergeben gibt. Ohne den Parameter scheitert der
        allererste Aufruf mit „takes 1 positional argument" — und weil das der
        Aufruf ist, der die Ansicht überhaupt erst füllt, bleibt das Fenster leer.
        """
        text, art = self._status
        frage, self._frage = self._frage, None
        return {
            "datei": str(self.filepath),
            "start_ansicht": self.start_ansicht,
            "name": self.board.name,
            "beschreibung": self.board.description,
            "zyklen": self.board.total_cycles,
            "dirty": self._dirty,
            "status": {"text": text, "art": art},
            "frage": frage,
            "sequenzen": sorted(name for name, _ in list_available_sequences()),
            "scan_namen": self._scan_namen(),
            "typen": [{"key": t, "label": BLOCK_LABELS[t],
                       "farbe": _hex(BLOCK_COLORS[t])} for t in TYP_REIHENFOLGE],
            "scan_modi": SCAN_MODI,
            "else_aktionen": ELSE_AKTIONEN,
            "ohne_else": self._ohne_else(),
            "phasen": [self._phase_json(i, ln) for i, ln in enumerate(self.board.lanes)],
            "punkte": [self._punkt_json(p) for p in self.points],
            "auswahl": {"phase": self._sel_index(), "zeilen": sorted(self.sel_rows)},
            "block": self._block_detail(),
        }

    def _ohne_else(self) -> dict:
        """Was ohne ELSE nach dem Timeout passiert — laut `config.json`.

        Die Antwort steht in der Config des Hauptprozesses (`pixel_wait_timeout`,
        `pixel_timeout_action`), und die Voreinstellung bricht den GANZEN Zyklus ab,
        nicht nur den Schritt — genau der Unterschied entscheidet, ob man ELSE braucht.

        Gelesen wird am Zeitstempel der Datei, nicht bei jeder Momentaufnahme; und
        über `_config_datei()` statt `load_config()`, denn die schreibt die Datei und
        gibt eine Konsolenzeile aus. Scheitert das Lesen, bleibt das Feld leer.
        """
        try:
            from ...config import CONFIG_FILE
            stand = Path(CONFIG_FILE).stat().st_mtime
        except OSError:
            stand = 0.0
        if stand != self._cfg_stand:
            self._cfg_stand = stand
            from ...config import CONFIG
            roh, fehler = self._config_datei()
            if fehler:
                self._cfg_info = {}
            else:
                aktion = roh.get("pixel_timeout_action", CONFIG.pixel_timeout_action)
                self._cfg_info = {
                    "sekunden": roh.get("pixel_wait_timeout", CONFIG.pixel_wait_timeout),
                    "folge": TIMEOUT_TEXT.get(aktion, aktion),
                    "notbremse": roh.get("pixel_max_consecutive_timeouts",
                                         CONFIG.pixel_max_consecutive_timeouts)}
        return self._cfg_info

    def _scan_namen(self) -> dict:
        """Welche Scan-Konfigurationen es gibt — je Block-Typ eine Liste.

        Ein Scan-Block verweist per Name auf eine Datei; ein Tippfehler ergab einen
        Block, den der Executor stillschweigend nicht ausführt. Hier steht, was
        tatsächlich auf Platte liegt — auswählen statt abschreiben.

        Der Boss-Watcher zieht dieselben Konfigurationen wie der Boss-Scan. Gelesen
        wird bei jeder Momentaufnahme, damit eine im Hauptprozess angelegte
        Konfiguration beim nächsten Klick auftaucht.
        """
        def namen(auflisten) -> list[str]:
            try:
                return sorted(name for name, _ in auflisten(self.board.name))
            except OSError:
                return []

        bosse = namen(list_available_boss_scans)
        return {
            BLOCK_ITEM_SCAN: namen(list_available_item_scans),
            BLOCK_ICON_SCAN: namen(list_available_icon_scans),
            BLOCK_BOSS_SCAN: bosse,
            BLOCK_BOSS_WATCHER: bosse,
        }

    def _sel_index(self) -> Optional[int]:
        if self.sel_lane is None or self.sel_lane not in self.board.lanes:
            return None
        return self.board.lanes.index(self.sel_lane)

    def _punkt_json(self, p: PalettePoint) -> dict:
        return {"id": p.id, "name": p.name or f"Punkt {p.id}", "x": p.x, "y": p.y,
                "farbe": _hex(p.color), "quelle": p.source}

    def _phase_json(self, index: int, lane: Lane) -> dict:
        return {
            "index": index,
            "art": lane.kind,
            "name": lane.name,
            "wiederholungen": lane.repeat,
            "start": lane.scheduled_start or "",
            "loeschbar": lane.kind == LANE_LOOP,
            "bloecke": [self._block_json(lane, row, s) for row, s in enumerate(lane.steps)],
        }

    def _block_json(self, lane: Lane, row: int, step: SequenceStep) -> dict:
        """Eine Karte im Board — knapp genug, dass 50 davon untereinander passen."""
        typ = block_type(step)
        wc = step.wait_condition
        feld = SCAN_FELD.get(typ)
        block = {
            "zeile": row,
            "typ": typ,
            "label": BLOCK_LABELS[typ],
            "farbe": _hex(BLOCK_COLORS[typ]),
            # Kein Rückfall aufs Typ-Label: das steht schon als Marke daneben, und
            # zweimal dasselbe Wort auf einer Karte ist keine Information.
            "titel": step.name or "",
            "zeilen": self._zeilen(step, typ),
            "prueft": step.verify_condition is not None,
            "gewaehlt": self.sel_lane is lane and row in self.sel_rows,
            "farbfeld": _hex(wc.color) if wc else None,
            "farbtext": self._trigger_text(wc) if wc else "",
            "else_text": self._else_text(step),
            # Ein ELSE, das nie feuern kann, steht sonst als Zusage auf der Karte.
            "else_greift": else_greift(step),
            # Ein Scan ohne Namen wird beim Speichern abgelehnt — die Karte sagt
            # das schon vorher, sonst sucht man den Block hinterher in vier Phasen.
            "warnung": ("Name fehlt" if feld and not (getattr(step, feld) or "").strip()
                        else None),
        }
        return block

    def _zeilen(self, step: SequenceStep, typ: str) -> list[str]:
        """Ein bis drei knappe Zeilen im Kartenkörper.

        Die Wartezeit steht nur da, wenn es eine gibt: „sofort" unter jedem
        zweiten Block ist Rauschen, und in der Liste zählt, dass 50 Karten
        untereinander lesbar bleiben.
        """
        if typ == BLOCK_SCREENSHOT:
            r = step.screenshot_region
            return [f"Bereich {r[0]},{r[1]} → {r[2]},{r[3]}" if r else "Vollbild"]
        if typ in SCAN_FELD:
            name = (getattr(step, SCAN_FELD[typ]) or "").strip() or "(kein Name)"
            modus = f" · {step.item_scan_mode}" if typ == BLOCK_ITEM_SCAN else ""
            zeilen = [f"{name}{modus}"]
        elif typ == BLOCK_KEY:
            zeilen = [f"Taste „{step.key_press}“"]
        elif typ == BLOCK_WAIT:
            zeilen = []
        else:
            zeilen = [_stelle(step)]
        if step.scroll:
            # Das Rad kann kein Editor setzen, eine Aufnahme bringt es aber mit.
            # Ungenannt sähe der Block aus wie ein gewöhnlicher Klick.
            zeilen.append(f"Rad {step.scroll:+d}")
        if step.delay_before or step.delay_max or not zeilen:
            zeilen.append(_wartetext(step))
        return zeilen

    def _trigger_text(self, wc: WaitCondition) -> str:
        was = "prüft" if wc.check_only else "wartet bis"
        wohin = "weg" if wc.until_gone else "da"
        return f"{was} RGB{tuple(wc.color)} {wohin}"

    def _else_text(self, step: SequenceStep) -> str:
        ec = step.else_config
        if ec is None:
            return ""
        if ec.action == ELSE_CLICK:
            ziel = f"#{ec.point_id}" if ec.point_id is not None else "(kein Punkt)"
            return f"sonst: klick {ziel}"
        if ec.action == ELSE_KEY:
            return f"sonst: Taste „{ec.key or '?'}“"
        return {ELSE_SKIP: "sonst: Schritt überspringen",
                ELSE_SKIP_CYCLE: "sonst: Zyklus abbrechen",
                ELSE_RESTART: "sonst: Sequenz neu starten"}.get(ec.action, f"sonst: {ec.action}")

    def _einzelner(self) -> tuple[Optional[Lane], int, Optional[SequenceStep]]:
        """Der eine gewählte Schritt — oder nichts, wenn es keiner oder mehrere sind."""
        if self.sel_lane is None or len(self.sel_rows) != 1:
            return None, -1, None
        row = next(iter(self.sel_rows))
        if not (0 <= row < len(self.sel_lane.steps)):
            return None, -1, None
        return self.sel_lane, row, self.sel_lane.steps[row]

    def _block_detail(self) -> Optional[dict]:
        """Alle Felder des gewählten Schritts für die Eigenschaften-Spalte."""
        lane, row, step = self._einzelner()
        if step is None:
            return None
        typ = block_type(step)
        wc, vc, ec = step.wait_condition, step.verify_condition, step.else_config
        return {
            "phase": self.board.lanes.index(lane),
            "zeile": row,
            "typ": typ,
            "label": BLOCK_LABELS[typ],
            "farbe": _hex(BLOCK_COLORS[typ]),
            "name": step.name or "",
            "point_id": step.point_id,
            "x": step.x,
            "y": step.y,
            "aufgenommene_farbe": _hex(step.recorded_color),
            "delay_before": step.delay_before,
            "delay_max": step.delay_max or 0,
            "key_press": step.key_press or "",
            "item_scan": step.item_scan or "",
            "item_scan_mode": step.item_scan_mode or SCAN_MODE_ALL,
            "icon_scan": step.icon_scan or "",
            "boss_scan": step.boss_scan or "",
            "boss_watcher": step.boss_watcher or "",
            "wait_only": step.wait_only,
            "scroll": step.scroll or 0,
            "screenshot_region": list(step.screenshot_region) if step.screenshot_region else None,
            "trigger": trigger_name(wc),
            "trigger_punkt": wc.point_id if wc else None,
            "trigger_pruefen": wc.check_only if wc else False,
            "verify": trigger_name(vc),
            "verify_punkt": vc.point_id if vc else None,
            "else_aktion": ec.action if ec else "",
            "else_greift": else_greift(step),
            "else_punkt": ec.point_id if ec else None,
            "else_taste": (ec.key or "") if ec else "",
            "else_delay": ec.delay if ec else 0,
        }

    # --------------------------------------------------------------- Zustand

    def _melde(self, text: str, art: str = "ok") -> dict:
        self._status = (text, art)
        return self.snapshot()

    def _geaendert(self, text: str = "", art: str = "ok") -> dict:
        self._dirty = True
        return self._melde(text, art)

    def _punkt(self, point_id) -> Optional[PalettePoint]:
        if point_id is None:
            return None
        return next((p for p in self.points if p.id == int(point_id)), None)

    def _punkte_anwenden(self) -> None:
        """Zieht die abgeleiteten Werte aller Schritte aus der Palette nach.

        Dasselbe, was `resolve_point_references()` vor jedem Lauf tut — nur hier
        im Editor, damit ein verschobener Punkt sofort an JEDEM Schritt sichtbar
        wird, der auf ihn zeigt. Der DPG-Vorgänger aktualisierte nur den gerade
        bearbeiteten Schritt; die übrigen zeigten bis zum nächsten Öffnen die
        alte Koordinate an, obwohl gespeichert längst die neue galt.
        """
        for lane in self.board.lanes:
            for step in lane.steps:
                p = self._punkt(step.point_id)
                if p is not None:
                    step.x, step.y = p.x, p.y
                    step.name = p.name or step.name
                    step.recorded_color = p.color
                for cond in (step.wait_condition, step.verify_condition):
                    q = self._punkt(cond.point_id) if cond is not None else None
                    if q is not None:
                        cond.pixel = (q.x, q.y)
                        if q.color:
                            cond.color = tuple(q.color)
                ec = step.else_config
                r = self._punkt(ec.point_id) if ec is not None else None
                if r is not None:
                    ec.x, ec.y, ec.name = r.x, r.y, r.name or ""

    # ------------------------------------------------------------ Sequenz-Ebene
