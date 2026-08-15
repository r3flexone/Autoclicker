"""
Brücke zwischen der Weboberfläche und der Sequenz — die einzige Verbindung.

Die Oberfläche kennt keine `SequenceStep`s. Sie bekommt eine Momentaufnahme aus
reinen JSON-Werten (`snapshot()`) und schickt Befehle zurück ("wähle Zeile 3",
"setze delay_before auf 1.5"); jeder Befehl gibt die nächste Momentaufnahme
zurück. Die Schritte selbst bleiben hier im Prozess liegen und werden nur
umgruppiert, nie konvertiert — deshalb überlebt auch ein Feld den Round-Trip,
das die Oberfläche gar nicht anzeigt (`scroll`, `verify_condition`).

**Warum die Editor-Logik hier liegt und nicht im JavaScript.** Dieses Modul
braucht kein Fenster und wird in `tools/test_logic.py` gemessen. Beim
Dear-PyGui-Vorgänger stand dieselbe Rechnung in der Ansicht: prüfbar war sie
nur, indem der Test die halbe Ansicht stilllegte (`rebuild_board`,
`_update_title` — letzteres, weil ein `dpg`-Aufruf ohne Kontext die Suite mit
einem Segfault mitriss). Was hier liegt, kostet keinen solchen Aufwand.

Regel beim Erweitern: **jede Zustandsänderung geht durch eine Methode dieser
Klasse.** Die Oberfläche hält keinen eigenen Sequenz-Zustand, sie rendert nur,
was `snapshot()` sagt. Sonst gibt es wieder zwei Wahrheiten — und die eine wäre
die, die gespeichert wird.
"""

import copy
import os
import re
import time
from pathlib import Path
from typing import Optional

from ...models import (
    BLOCK_BOSS_SCAN, BLOCK_BOSS_WATCHER, BLOCK_CLICK, BLOCK_ICON_SCAN,
    BLOCK_ITEM_SCAN, BLOCK_KEY, BLOCK_SCREENSHOT, BLOCK_WAIT, BLOCK_WAIT_CLICK,
    ELSE_CLICK, ELSE_KEY, ELSE_RESTART, ELSE_SKIP, ELSE_SKIP_CYCLE,
    SCAN_MODE_ALL, SCAN_MODE_BEST, SCAN_MODE_EVERY, TIMEOUT_TEXT,
    LoopPhase, Sequence, SequenceStep, WaitCondition, block_type,
)
from ...persistence import (
    list_available_boss_scans, list_available_icon_scans, list_available_item_scans,
    list_available_sequences, load_sequence_file, save_sequence_file,
)
from ...utils import sanitize_filename
from .model import (
    BLOCK_COLORS, BLOCK_LABELS,
    LANE_LOOP, Lane, PalettePoint, SequenceBoard,
    board_to_sequence, ensure_else, hexfarbe, load_palette_points,
    rgbwert, save_palette_points, sequence_to_board, set_block_type,
    step_from_point,
)
from .scans import ScanTeil

# Reihenfolge der Block-Typen in der Typ-Auswahl: erst die drei Klick-Formen,
# dann Taste, dann die Scans, zuletzt der Screenshot.
TYP_REIHENFOLGE = [
    BLOCK_CLICK, BLOCK_WAIT_CLICK, BLOCK_WAIT, BLOCK_KEY,
    BLOCK_ITEM_SCAN, BLOCK_ICON_SCAN, BLOCK_BOSS_SCAN, BLOCK_BOSS_WATCHER,
    BLOCK_SCREENSHOT,
]

# Farb-Trigger: die drei Zustände, die ein Schritt haben kann. Werte statt
# Beschriftungen — die Beschriftung steht in der Oberfläche, hier steht das
# Protokoll. (Beim DPG-Vorgänger waren beide dasselbe, und der Test verglich
# gegen deutsche Anzeigetexte.)
TRIGGER_KEIN = "kein"
TRIGGER_DA = "da"
TRIGGER_WEG = "weg"

SCAN_MODI = [SCAN_MODE_ALL, SCAN_MODE_BEST, SCAN_MODE_EVERY]
ELSE_AKTIONEN = [ELSE_SKIP, ELSE_SKIP_CYCLE, ELSE_RESTART, ELSE_CLICK, ELSE_KEY]

# Welches Feld hält den Namen eines Scan-Blocks? Ein Scan-Block mit leerem Namen
# fällt beim Executor durch den Truthiness-Dispatch und degradiert still zu einem
# Klick auf (0,0) — deshalb steht die Zuordnung hier einmal und wird an zwei
# Stellen benutzt (Warnung am Block, Sperre beim Speichern).
SCAN_FELD = {
    BLOCK_ITEM_SCAN: "item_scan",
    BLOCK_ICON_SCAN: "icon_scan",
    BLOCK_BOSS_SCAN: "boss_scan",
    BLOCK_BOSS_WATCHER: "boss_watcher",
}

# Einfache Felder eines Schritts: Name -> Umwandlung des Werts aus der Oberfläche.
# Alles, was eine Stelle betrifft (Punkt, Trigger, else), hat eine eigene Methode —
# dort hängt mehr dran als eine Zuweisung.
_FELDER = {
    "name": lambda v: str(v or ""),
    "delay_before": lambda v: max(0.0, float(v or 0)),
    "delay_max": lambda v: (float(v) if float(v or 0) > 0 else None),
    "key_press": lambda v: (str(v).strip() or None),
    "item_scan": lambda v: str(v or ""),
    "item_scan_mode": lambda v: (str(v) if v in SCAN_MODI else SCAN_MODE_ALL),
    "icon_scan": lambda v: str(v or ""),
    "boss_scan": lambda v: str(v or ""),
    "boss_watcher": lambda v: str(v or ""),
    "wait_only": lambda v: bool(v),
    "scroll": lambda v: (int(v) if int(v or 0) != 0 else None),
}


# Die beiden Farbhelfer liegen in `model.py` — der Scans-Reiter braucht sie
# genauso, und zwei Exemplare wären die Kopie, die irgendwann anders rundet.
_hex = hexfarbe
_rgb = rgbwert


def trigger_name(cond: Optional[WaitCondition]) -> str:
    """Zustand einer Farb-Bedingung als Protokollwert."""
    if cond is None:
        return TRIGGER_KEIN
    return TRIGGER_WEG if cond.until_gone else TRIGGER_DA


def _wartetext(step: SequenceStep) -> str:
    if step.delay_max and step.delay_max > step.delay_before:
        return f"{step.delay_before:g}–{step.delay_max:g}s zufällig"
    if step.delay_before:
        return f"+{step.delay_before:g}s"
    return "sofort"


def _stelle(step: SequenceStep) -> str:
    ref = f"#{step.point_id} " if step.point_id is not None else ""
    return f"{ref}({step.x},{step.y})"


# Welche Blöcke ELSE überhaupt auslösen können. ELSE ist eine Antwort auf eine
# **nicht erfüllte Bedingung** — hat ein Block keine, wird es nie ausgeführt:
# ein reiner Klick klickt, eine Taste drückt, ein Warten wartet, und danach geht
# es weiter. Ausgelöst wird es (siehe `runtime/steps.py`) von
#   - der Farb-Bedingung: Timeout bzw. „nur prüfen" nicht erfüllt,
#   - der Nachprüfung: keine Wirkung nach allen Versuchen,
#   - Item-/Boss-/Icon-Scan: nichts gefunden.
# Der Boss-**Watcher** steht bewusst nicht dabei: er läuft in seine eigenen
# Grenzen (max. Scans, Timeout) und macht danach weiter, ohne ELSE zu fragen.
_ELSE_SCANS = ("item_scan", "boss_scan", "icon_scan")


def else_greift(step: SequenceStep) -> bool:
    """Kann ELSE bei diesem Schritt überhaupt feuern?"""
    if step.wait_condition is not None or step.verify_condition is not None:
        return True
    return any(getattr(step, feld, None) is not None for feld in _ELSE_SCANS)


def _gleicher_wert(a, b) -> bool:
    """Ist das derselbe Config-Wert? Zahlen ohne Typunterschied, `bool` mit.

    JSON kennt nur eine Zahl: eine von Hand getippte `600` und die `600.0`, die
    nach dem Laden dasteht, sind dieselbe Einstellung — als Korrektur gemeldet
    wäre das eine Falschmeldung bei jedem zweiten Feld (dieselbe Rechnung wie
    `_gleich()` im Start-Durchgang). `bool` bleibt ausgenommen: ein `True`, das
    als `1` durchginge, versteckte ein umgekipptes Flag.
    """
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_gleicher_wert(x, y) for x, y in zip(a, b))
    if not isinstance(a, bool) and isinstance(a, (int, float)) \
            and not isinstance(b, bool) and isinstance(b, (int, float)):
        return float(a) == float(b)
    return a == b


def _mtime(pfad) -> Optional[float]:
    """Zeitstempel einer Datei — `None`, wenn es sie (noch) nicht gibt."""
    try:
        return Path(pfad).stat().st_mtime
    except OSError:
        return None


def _punkte_pfad(sequences_dir) -> Path:
    """Wo `save_palette_points()` schreibt. Für den Stand-Vergleich."""
    return Path(sequences_dir) / "points.json"


def _bloecke(anzahl: int) -> str:
    """„1 Block" / „3 Blöcke" — in der Statusleiste stand vorher „1 Block/Blöcke"."""
    return "1 Block" if anzahl == 1 else f"{anzahl} Blöcke"


def scan_warnungen(board: SequenceBoard) -> list[str]:
    """Alle Scan-Blöcke ohne Konfiguration, als lesbare Stellen.

    Steht ausserhalb der Klasse, weil es zwei Fragen beantwortet: „hat die
    OFFENE Sequenz noch einen leeren Scan?" (Meldung beim Speichern) und
    „hat DIESE Datei welche?" (Übersicht). Zweimal dieselbe Regel getrennt
    hinzuschreiben hiesse, dass eine Korrektur an der einen an der anderen
    vorbeigeht — dieselbe Begründung wie bei `mehrfach_auswahl()`.
    """
    raus = []
    for lane in board.lanes:
        for row, step in enumerate(lane.steps, start=1):
            typ = block_type(step)
            feld = SCAN_FELD.get(typ)
            if feld is not None and not (getattr(step, feld) or "").strip():
                raus.append(f"{BLOCK_LABELS[typ]} in '{lane.name}' (Block {row})")
    return raus


class StudioBridge(ScanTeil):
    """Hält Sequenz, Auswahl und Punkte-Palette. Jede Methode ist ein UI-Befehl.

    Der Scans-Reiter hängt als Mixin dran (`scans.py`): pywebview legt **ein**
    Objekt als `js_api` aus, also müssen alle Methoden hier zusammenlaufen —
    getrennte Dateien bleiben sie trotzdem.

    Alle Methoden, die etwas ÄNDERN, geben `snapshot()` zurück — die Oberfläche
    rendert nach jedem Befehl neu und muss nichts selbst nachhalten. Compound-
    Argumente kommen als **ein** dict: pywebview reicht je nach Version nur ein
    Argument durch, und ein dict bleibt lesbar, wenn ein Feld dazukommt.

    Einige Methoden fallen heraus und **fragen nur**: `sequenz_liste()`,
    `lauf_status()`, `befehl_offen()` und die beiden Config-Methoden. Ihre
    Antwort ist keine Momentaufnahme, sondern ein eigener Gegenstand — die
    Oberfläche holt sie über `frage()` statt über `ruf()`, sonst überschriebe
    die Antwort den Editor-Zustand.

    `config_schreiben()` ist die eine, die etwas ändert und trotzdem hierher
    gehört: sie ändert die **Config**, nicht die Sequenz. Ihre Antwort ist der
    geschriebene Stand samt Korrekturen — eine Momentaufnahme wäre dafür der
    falsche Gegenstand.
    """

    def __init__(self, seq: Sequence, filepath, sequences_dir: str):
        self.board: SequenceBoard = sequence_to_board(seq)
        self.filepath = Path(filepath)
        self.sequences_dir = sequences_dir
        self.points: list[PalettePoint] = load_palette_points(sequences_dir)
        # Was ohne ELSE passiert, steht in der config.json — gemerkt am
        # Zeitstempel, damit nicht jede Momentaufnahme die Datei liest.
        self._cfg_stand: float = -1.0
        self._cfg_info: dict = {}
        # Stand der Dateien beim Laden. Der Hauptprozess schreibt dieselben
        # Dateien (Aufnahme legt Punkte an, `save_data` schreibt die Sequenz) —
        # ohne diesen Vergleich überschreibt das Studio das kommentarlos.
        self._stand_datei: Optional[float] = _mtime(self.filepath)
        self._stand_punkte: Optional[float] = _mtime(_punkte_pfad(sequences_dir))
        # Die Auswahl lebt in GENAU EINER Phase. Eine Auswahl quer über INIT und
        # END hätte bei "eine Position hoch" keine Bedeutung, und die
        # Sammelaktionen wären nicht mehr eindeutig.
        self.sel_lane: Optional[Lane] = None
        self.sel_rows: set[int] = set()
        self._dirty = False
        # Wurde in dieser Sitzung mindestens einmal geschrieben? Nur dafür da,
        # dass die Schlussmeldung ans Neuladen im Hauptprozess erinnern kann.
        self._gespeichert = False
        self._status = ("", "info")
        self._frage: Optional[dict] = None
        # Welcher Reiter beim Start offen ist. Reiner Oberflächenzustand, aber
        # er kommt von aussen: CTRL+ALT+V startet denselben Prozess wie
        # CTRL+ALT+B, nur mit "scans".
        self.start_ansicht: str = "editor"
        self._scan_init()

    # ------------------------------------------------------------- Momentaufnahme

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

        Die Antwort steht nicht im Studio, sondern in der Config des
        Hauptprozesses (`pixel_wait_timeout`, `pixel_timeout_action`), und sie
        ist keine Kleinigkeit: die Voreinstellung bricht den **ganzen Zyklus**
        ab, nicht nur den Schritt. Der Hinweis im Inspektor behauptete das
        Gegenteil („die Sequenz macht weiter"), und der Unterschied entscheidet,
        ob man ELSE braucht oder nicht.

        Gelesen wird **am Zeitstempel der Datei**, nicht bei jeder Momentaufnahme:
        eine zwischenzeitlich geänderte Config soll nicht bis zum nächsten
        Fensterstart falsch angezeigt werden, aber jede Momentaufnahme neu zu
        lesen wäre eine Dateioperation pro Klick. Scheitert das Lesen, bleibt
        das Feld leer; dann sagt die Oberfläche nichts, statt zu raten.

        Gelesen wird über `_config_datei()` und **nicht** über `load_config()`:
        die schreibt die Datei, sobald ein Feld fehlt, und gibt dabei eine Zeile
        in der Konsole aus. Weil dieser Subprozess seine Ausgabe mit dem
        Hauptprozess teilt, stand dort beim Öffnen des Studios zweimal
        „[CONFIG] Geladen" — einmal vom Import, einmal von hier. Ein Leser
        schreibt weder Datei noch Konsole.
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

        Ein Scan-Block verweist **per Name** auf eine Datei in `item_scans/`,
        `boss_scans/` bzw. `icon_scans/`; der Name IST die Referenz. Getippt
        werden musste er trotzdem, und ein Tippfehler ergab einen Block, den der
        Executor stillschweigend nicht ausführt. Hier steht deshalb, was
        tatsächlich auf Platte liegt — auswählen statt abschreiben.

        Der Boss-Watcher zieht dieselben Konfigurationen wie der Boss-Scan
        (`state.boss_scans`), deshalb dieselbe Liste.

        Gelesen wird bei jeder Momentaufnahme, nicht einmal beim Start: legt man
        im Hauptprozess eine Konfiguration an, während das Studio offen ist,
        taucht sie beim nächsten Klick auf. Das ist der einzige Weg — geteilten
        Zustand gibt es zwischen den beiden Prozessen nicht.
        """
        def namen(auflisten) -> list[str]:
            try:
                return sorted(name for name, _ in auflisten())
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

    def sequenz_liste(self, daten: Optional[dict] = None) -> list[dict]:
        """Kennzahlen aller gespeicherten Sequenzen für die Übersicht.

        **Die eine Methode, die keine Momentaufnahme zurückgibt** (mit
        `lauf_status()`). Deshalb ruft die Oberfläche sie über `frage()` statt
        über `ruf()`: `ruf()` ersetzt `S` mit der Antwort, und eine Liste an
        dieser Stelle hiesse Editor-Zustand weg, sobald man die Übersicht
        aufmacht. Wer hier etwas ergänzt, prüft zuerst, welcher der beiden
        Kanäle gemeint ist.

        Bewusst über `load_sequence_file()` und nicht über einen eigenen
        JSON-Leser: so laufen Migration und Punkt-Auflösung mit, und die Zahlen
        hier sind dieselben, die der Editor beim Öffnen zeigt.

        Nur Kennzahlen, keine Schritte — die Liste soll auch bei 40 Sequenzen
        sofort stehen, und gelesen wird sie bei jedem Öffnen des Reiters neu
        (im Hauptprozess kann zwischendurch eine dazugekommen sein).

        **Der Ordner wird selbst durchgesehen, nicht `list_available_sequences()`
        gefragt.** Die überspringt unlesbare Dateien stillschweigend — richtig für
        ein Menü (laden liesse sie sich ohnehin nicht), falsch für eine Übersicht:
        genau dann sucht man die Datei im Explorer, weil sie nirgends auftaucht.
        Hier steht sie mit dem Vermerk, dass sie kaputt ist.
        """
        raus: list[dict] = []
        ordner = Path(self.sequences_dir)
        try:
            dateien = sorted(p for p in ordner.glob("*.json") if p.name != "points.json")
        except OSError:
            return []
        for pfad in dateien:
            try:
                geaendert = pfad.stat().st_mtime
            except OSError:
                geaendert = 0.0
            seq = load_sequence_file(pfad)
            if seq is None:
                raus.append({"name": pfad.stem, "datei": pfad.name, "defekt": True,
                             "geaendert": geaendert, "offen": pfad == self.filepath})
                continue
            raus.append({
                "name": seq.name,
                "datei": pfad.name,
                "defekt": False,
                "beschreibung": seq.description,
                "zyklen": seq.total_cycles,
                "init": len(seq.init_steps),
                "end": len(seq.end_steps),
                "phasen": [{"name": lp.name, "schritte": len(lp.steps),
                            "wiederholungen": lp.repeat,
                            "start": lp.scheduled_start or ""}
                           for lp in seq.loop_phases],
                "schritte": seq.total_steps(),
                "geaendert": geaendert,
                "offen": pfad == self.filepath,
                "warnungen": scan_warnungen(sequence_to_board(seq)),
            })
        return raus

    def lauf_status(self, daten: Optional[dict] = None) -> dict:
        """Was gerade läuft — gelesen aus der Statusdatei des Hauptprozesses.

        Der zweite Kanal neben `sequenz_liste()`: keine Momentaufnahme, deshalb
        über `frage()` abzuholen. Und **nie ein Fehler** — dass nichts läuft ist
        der Normalfall, nicht der Ausnahmefall.

        Der Hauptprozess und dieses Fenster teilen keinen Speicher; die Datei
        ist der gemeinsame Nenner, so wie überall sonst zwischen den beiden.
        """
        import json
        from ...config import RUN_STATUS_FILE
        try:
            with open(RUN_STATUS_FILE, "r", encoding="utf-8") as f:
                zustand = json.load(f)
        except (OSError, ValueError):
            return {"aktiv": False}
        if not isinstance(zustand, dict):
            return {"aktiv": False}
        # Ein abgeschlossener Lauf (`ende`) darf beliebig alt sein — er IST
        # Vergangenheit. Die Altersregel gilt nur für einen, der sich noch für
        # laufend hält.
        if not zustand.get("aktiv"):
            return zustand if zustand.get("ende") else {"aktiv": False}
        # Älter als 5 s heisst: der Schreiber lebt nicht mehr. Ein abgestürzter
        # Lauf soll nicht ewig als „läuft" in der Oberfläche stehen — der Worker
        # schreibt spätestens alle 200 ms, und selbst ein Schritt, der auf eine
        # Farbe wartet, geht durch `execute_step`.
        if time.time() - float(zustand.get("stand") or 0) > 5:
            return {"aktiv": False, "verwaist": True}
        # Typ → Farbe und Marke: die Laufzeit schreibt nur den Schlüssel, weil
        # `runtime/` die Ansicht nicht kennen darf. Übersetzt wird hier, damit
        # der laufende Block dieselbe Farbe trägt wie seine Karte im Board — die
        # Farbe ist die Legende, und sie muss in beiden Ansichten dieselbe sein.
        typ = zustand.get("block_typ")
        if typ in BLOCK_COLORS:
            zustand["block_farbe"] = _hex(BLOCK_COLORS[typ])
            zustand["block_marke"] = BLOCK_LABELS[typ]
        return zustand

    # Was das Studio dem Hauptprozess sagen darf. Die Gegenstelle ist `BEFEHLE`
    # in handlers.py — ein Test hält beide Listen gegeneinander, denn laufen sie
    # auseinander, tut ein Knopf einfach nichts und niemand merkt es.
    LAUF_BEFEHLE = ("start", "stop", "pause")
    # Alles, was das Studio dem Hauptprozess sagen darf. „zeigen" steuert keinen
    # Lauf, geht aber denselben Weg — der Test haelt DIESE Liste gegen `BEFEHLE`.
    ALLE_BEFEHLE = LAUF_BEFEHLE + ("zeigen", "config", "daten")

    def lauf_befehl(self, daten: dict) -> dict:
        """Start, Pause oder Stopp — als Auftrag an den Hauptprozess.

        Dieses Fenster kann die Sequenz nicht selbst ausführen: es ist ein eigener
        Prozess und sieht weder `AutoClickerState` noch `stop_event`. Es legt
        deshalb einen Befehl ab (`befehl.py`), den der Hauptprozess in derselben
        Schleife abholt, in der auch seine Hotkeys ankommen — ein Studio-Knopf ist
        damit genau so viel wert wie ein Tastendruck, nicht mehr und nicht weniger.

        **Vor dem Start wird gespeichert.** Der Hauptprozess lädt die Datei; was
        nur hier im Speicher steht, liefe nicht mit. Ein Start-Knopf, der eine
        ältere Fassung startet als die angezeigte, wäre schlimmer als keiner.
        """
        from ...befehl import sende
        befehl = (daten or {}).get("befehl") or ""
        if befehl not in self.LAUF_BEFEHLE:
            return self._melde(f"Unbekannter Lauf-Befehl '{befehl}'.", "err")

        argumente: dict = {}
        if befehl == "start":
            if self._dirty:
                zustand = self.speichern()
                if zustand["status"]["art"] == "err":
                    return zustand      # Meldung steht schon drin, Start faellt aus
            if not self.filepath.exists():
                return self._melde("Erst speichern — die Datei gibt es noch nicht.", "warn")
            argumente = {"datei": str(self.filepath), "sequenz": self.board.name}

        if not sende(befehl, **argumente):
            return self._melde("Befehl konnte nicht abgelegt werden.", "err")
        text = {"start": f"'{self.board.name}' gestartet.",
                "stop": "Stopp geschickt.",
                "pause": "Pause umgeschaltet."}[befehl]
        return self._melde(text)

    def punkt_zeigen(self, daten: Optional[dict] = None) -> dict:
        """Setzt die Maus im Hauptprozess auf die Stelle des gewählten Blocks.

        Der kürzeste Weg zu der Frage, die man beim Bauen einer Sequenz am
        häufigsten hat: **sitzt der Punkt da, wo ich denke?** Ein Blick auf
        „(4402,561)" beantwortet sie nicht, ein Mauszeiger im Spiel schon.

        Messen kann nur der Hauptprozess (dieses Fenster sieht den Bildschirm
        nicht), deshalb steht die Auswertung — gespeicherte gegen aktuelle Farbe —
        in dessen Konsole. Hier bleibt die Rückmeldung, dass der Auftrag raus ist.
        """
        lane, row, step = self._einzelner()
        if step is None:
            return self.snapshot()
        # Ein Block hat bis zu drei Stellen, und die Frage „sitzt das noch?"
        # stellt sich bei allen dreien: der Klick, der Prüf-Pixel des Triggers
        # und der ELSE-Klick. Welche gemeint ist, sagt der Aufrufer.
        welche = (daten or {}).get("welche") or "klick"
        quelle = {
            "trigger": lambda: step.wait_condition,
            "verify": lambda: step.verify_condition,
            "else": lambda: step.else_config,
        }.get(welche)
        punkt = self._punkt(quelle().point_id if quelle and quelle() else step.point_id)
        if punkt is None:
            return self._melde("Diese Stelle hat keinen Punkt zum Zeigen.", "warn")

        from ...befehl import sende
        if not sende("zeigen", x=punkt.x, y=punkt.y, punkt=punkt.id,
                     name=punkt.name or "", farbe=list(punkt.color) if punkt.color else None):
            return self._melde("Befehl konnte nicht abgelegt werden.", "err")
        return self._melde(f"Maus zu #{punkt.id} ({punkt.x},{punkt.y}) — im Spiel nachsehen.")

    # ------------------------------------------------------------ Einstellungen

    def _config_datei(self) -> tuple:
        """`config.json` als reine Werte — und was beim Lesen schiefging.

        Bewusst nicht `load_config()`: die **schreibt** die Datei, sobald ein
        Feld fehlt, und gibt bei jedem Aufruf eine Zeile in der Konsole des
        Hauptprozesses aus. Ein Leser tut weder das eine noch das andere.

        Drei Ergebnisse, und der Unterschied zwischen den letzten beiden ist der
        wichtige: `({}, "")` heisst „gibt es noch nicht" (dann legt das
        Speichern sie an), `({}, "…")` heisst „da liegt etwas, das ich nicht
        verstehe" — und darauf wird nicht geschrieben.
        """
        import json
        from ...config import CONFIG_FILE
        pfad = Path(CONFIG_FILE)
        try:
            roh = json.loads(pfad.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}, ""
        except (OSError, ValueError) as fehler:
            return {}, f"config.json ist nicht lesbar: {fehler}"
        if not isinstance(roh, dict):
            return {}, "config.json enthält kein Objekt."
        return roh, ""

    def config_lesen(self, daten: Optional[dict] = None) -> dict:
        """Werte, Standardwerte, Abschnitte und Beschreibungen in einem Rutsch.

        Der dritte `frage()`-Kanal: keine Momentaufnahme, sondern ein eigener
        Gegenstand — über `ruf()` geholt zerschösse die Antwort den
        Editor-Zustand.

        Der Pfad steht absolut dabei, weil `config.json` relativ zum
        Arbeitsverzeichnis liegt: wer die App aus einem anderen Ordner startet,
        bearbeitet eine andere Datei, und das darf man nicht raten müssen.
        """
        from ...config import (
            AppConfig, CONFIG_FILE, config_abschnitte, optionale_felder,
        )
        from ...config_meta import META
        roh, fehler = self._config_datei()
        return {
            "pfad": str(Path(CONFIG_FILE).resolve()),
            "werte": AppConfig.from_dict(roh).to_dict(),
            "standard": AppConfig().to_dict(),
            "abschnitte": [{"titel": t, "keys": list(k)} for t, k in config_abschnitte()],
            "meta": {k: m.as_dict() for k, m in META.items()},
            # Wo ein leeres Eingabefeld `null` heisst und nicht 0.
            "optional": optionale_felder(),
            "fehler": fehler,
        }

    def config_schreiben(self, daten: Optional[dict] = None) -> dict:
        """Schreibt geänderte Werte in `config.json` — und meldet Korrekturen.

        **Nur die geänderten Schlüssel**, nicht die ganze Config: der
        Hauptprozess schreibt dieselbe Datei (Debug-Stufen, Factory Reset,
        Import), und ein Fenster, das seit einer Stunde offensteht, soll dessen
        Änderungen nicht mit seinem alten Stand überbügeln. Gemischt wird
        deshalb gegen die Datei, wie sie **jetzt** aussieht.

        `AppConfig.__post_init__` korrigiert ungültige Werte still (Konfidenz
        über 1, max unter min, unbekannte Aktion). Im Hauptprozess sieht man das
        an einer Konsolenzeile — hier sähe sie niemand, deshalb wird der
        korrigierte Stand gegen das Gesendete gehalten und die Abweichung
        zurückgemeldet. Die Datei enthält dann etwas anderes als eingegeben, und
        das darf nicht stillschweigend passieren.
        """
        from ...config import AppConfig, save_config
        werte = (daten or {}).get("werte")
        if not isinstance(werte, dict) or not werte:
            return {"ok": False, "meldung": "Nichts zu speichern."}

        roh, fehler = self._config_datei()
        if fehler:
            # Kaputt ist nicht leer: draufschreiben würde den einzigen Rest
            # wegwerfen, den man noch von Hand reparieren kann.
            return {"ok": False, "meldung": fehler + " — nicht überschrieben."}

        neu = AppConfig.from_dict({**roh, **werte})
        fertig = neu.to_dict()
        korrekturen = [{"key": k, "gesendet": v, "wurde": fertig.get(k)}
                       for k, v in werte.items()
                       if k in fertig and not _gleicher_wert(v, fertig[k])]
        save_config(neu)
        # Der Hauptprozess hält seinen eigenen Stand im Speicher und merkt von
        # der geschriebenen Datei nichts. Derselbe Briefkasten wie bei Start und
        # Stopp — läuft gerade keiner, verfällt der Befehl (befehl.MAX_ALTER).
        from ...befehl import sende
        sende("config")
        # Was ohne ELSE passiert, steht in derselben Datei — der gemerkte
        # Zeitstempel ist damit veraltet.
        self._cfg_stand = -1.0
        return {"ok": True, "werte": fertig, "korrekturen": korrekturen}

    def befehl_offen(self, daten: Optional[dict] = None) -> bool:
        """Liegt der letzte Befehl noch im Briefkasten?

        Die einzige Rückmeldung, die dieses Fenster über den Hauptprozess bekommt:
        er leert den Kasten beim Lesen. Liegt der Befehl Sekunden später immer
        noch da, hört niemand zu — das Programm ist zu, oder es hängt. Ohne diese
        Frage meldete der Knopf „gestartet" und es passierte nichts, was von
        aussen wie ein kaputter Knopf aussieht.

        Fragt nur, ändert nichts: gehört zu `frage()`, nicht zu `ruf()`.
        """
        from ...befehl import BEFEHL_DATEI
        try:
            return BEFEHL_DATEI.exists()
        except OSError:
            return False

    def laden(self, daten: dict) -> dict:
        """Öffnet eine gespeicherte Sequenz. Fragt bei ungespeicherten Änderungen."""
        name = (daten or {}).get("name") or ""
        if not name:
            return self._melde("Keine Sequenz gewählt.", "warn")
        if self._dirty and not (daten or {}).get("verwerfen"):
            self._frage = {"art": "laden", "ziel": name,
                           "titel": "Ungespeicherte Änderungen",
                           "text": f"'{self.board.name}' hat ungespeicherte Änderungen. "
                                   "Vor dem Laden speichern?",
                           "weiter": "Verwerfen", "speichern": True}
            return self.snapshot()
        pfad = next((p for n, p in list_available_sequences() if n == name), None)
        seq = load_sequence_file(pfad) if pfad else None
        if seq is None:
            return self._melde(f"'{name}' konnte nicht geladen werden.", "err")
        self.board = sequence_to_board(seq)
        self.filepath = Path(pfad)
        # Punkte neu einlesen: zwischen zwei Sequenzen kann im Hauptprozess ein
        # Punkt dazugekommen sein.
        self.points = load_palette_points(self.sequences_dir)
        self._auswahl_leeren()
        self._dirty = False
        self._stand_merken()
        return self._melde(f"Geladen: {name}")

    def neu(self, daten: Optional[dict] = None) -> dict:
        """Legt eine leere Sequenz an (noch ohne Datei auf Platte)."""
        if self._dirty and not (daten or {}).get("verwerfen"):
            self._frage = {"art": "neu", "ziel": "",
                           "titel": "Ungespeicherte Änderungen",
                           "text": f"'{self.board.name}' hat ungespeicherte Änderungen. "
                                   "Vor dem Anlegen speichern?",
                           "weiter": "Verwerfen", "speichern": True}
            return self.snapshot()
        basis = f"Sequenz_{int(time.time())}"
        # Mit einer Loop-Phase, nicht nur INIT und END: fast jede Sequenz braucht
        # sie, und wer sie nicht braucht, laesst sie leer — eine leere Phase kostet
        # zur Laufzeit nichts (der Worker geht durch null Schritte). Ohne sie war
        # der erste Griff nach dem Anlegen immer derselbe: „+ Loop-Phase".
        self.board = sequence_to_board(Sequence(
            name=basis, loop_phases=[LoopPhase(name="Loop", repeat=1, steps=[])]))
        self.filepath = Path(self.sequences_dir) / f"{sanitize_filename(basis)}.json"
        self._auswahl_leeren()
        self._dirty = False
        self._stand_merken()
        return self._melde("Neue Sequenz — noch nicht gespeichert.", "warn")

    def sequenz_setzen(self, daten: dict) -> dict:
        """Name, Zyklen oder Beschreibung der Sequenz ändern."""
        feld, wert = (daten or {}).get("feld"), (daten or {}).get("wert")
        if feld == "name":
            self.board.name = str(wert or "")
        elif feld == "zyklen":
            self.board.total_cycles = max(0, int(wert or 0))
        elif feld == "beschreibung":
            self.board.description = str(wert or "")
        else:
            return self._melde(f"Unbekanntes Feld '{feld}'.", "err")
        return self._geaendert()

    def _scan_ohne_namen(self) -> Optional[str]:
        """Erster Scan-Block mit leerem Namen, als lesbare Stelle."""
        offen = scan_warnungen(self.board)
        return offen[0] if offen else None

    def speichern(self, daten: Optional[dict] = None) -> dict:
        """Schreibt Punkte und Sequenz. Die Datei folgt dem Sequenz-Namen.

        **Ein Scan ohne Konfiguration hält das Speichern nicht auf.** Das tat es
        einmal, und die Begründung war richtig, aber an der falschen Stelle: ein
        leerer Scan-Name fiel im Executor durch den Truthiness-Dispatch bis zum
        Klick durch und wurde zu einem Klick auf (0, 0). Nur hat das den Editor
        nichts anzugehen — wer einen Block anlegt, um seine Stelle im Ablauf
        festzuhalten, und die Konfiguration erst danach baut (die entsteht in
        einem anderen Prozess, mit CTRL+ALT+N), soll das speichern koennen.
        Repariert ist es jetzt dort, wo es kaputt war: `execute_step` ueberspringt
        so einen Block mit Ansage.

        Gemeldet wird er trotzdem — still soll er nicht bleiben.
        """
        if not (self.board.name or "").strip():
            # Der Name ist etwas anderes: er IST der Dateiname. Ohne ihn gibt es
            # kein Ziel, das Speichern ist nicht unvollstaendig, sondern unmoeglich.
            return self._melde("Nicht gespeichert: Sequenz-Name fehlt.", "err")

        alt = self.filepath
        neu = Path(self.sequences_dir) / f"{sanitize_filename(self.board.name)}.json"
        umbenannt = neu != alt

        # Hat der Hauptprozess dieselbe Datei zwischenzeitlich geschrieben?
        # Beide Prozesse teilen sich den Ordner: eine Aufnahme legt Punkte an,
        # `save_data()` schreibt die Sequenz. Ohne diese Frage gewinnt einfach
        # der Zweite, und die Arbeit des Ersten ist weg — ohne ein Wort.
        fremd = self._fremd_geaendert(neu if not umbenannt else None)
        if fremd and not (daten or {}).get("erzwingen"):
            self._frage = {
                "art": "speichern",
                "titel": "Ausserhalb geändert",
                "text": f"{fremd} wurde geändert, seit diese Sequenz geöffnet ist — "
                        "vermutlich vom Hauptprozess. Speichern überschreibt das.",
                "weiter": "Trotzdem speichern",
                "speichern": False,
            }
            return self.snapshot()

        # Punkte ZUERST: die Sequenz verweist nur noch auf sie. Schlägt das fehl,
        # zeigten frisch angelegte Referenzen ins Leere — dann lieber gar nicht
        # speichern, als eine Sequenz mit toten Verweisen zu hinterlassen.
        if not save_palette_points(self.sequences_dir, self.points):
            return self._melde("points.json nicht schreibbar — nichts gespeichert.", "err")
        if not save_sequence_file(board_to_sequence(self.board), neu):
            return self._melde("Speichern fehlgeschlagen!", "err")

        self.filepath = neu
        self._gespeichert = True
        self._dirty = False
        self._stand_merken()
        text = f"Gespeichert: {neu.name}"
        if umbenannt and alt.exists():
            try:
                os.remove(alt)
                text = f"Umbenannt → {neu.name} (alte Datei entfernt)"
            except OSError:
                text = f"Gespeichert: {neu.name} (alte Datei {alt.name} blieb)"

        leer = self._scan_ohne_namen()
        if leer:
            return self._melde(f"{text} — {leer} hat noch keine Konfiguration "
                               f"und wird übersprungen.", "warn")
        return self._melde(text)

    def _fremd_geaendert(self, ziel) -> str:
        """Welche Datei sich seit dem Laden von aussen geändert hat (leer = keine).

        `ziel` ist die Sequenzdatei, die gleich geschrieben wird — beim Umbenennen
        `None`, denn dann entsteht eine neue Datei und es gibt nichts zu
        überschreiben. `points.json` wird immer geprüft: die schreibt das Studio
        bei jedem Speichern mit, und der Hauptprozess legt dort während einer
        Aufnahme neue Punkte an.
        """
        if ziel is not None and _mtime(ziel) not in (None, self._stand_datei):
            return Path(ziel).name
        punkte = _punkte_pfad(self.sequences_dir)
        if _mtime(punkte) not in (None, self._stand_punkte):
            return "points.json"
        return ""

    def _stand_merken(self) -> None:
        """Nach dem Schreiben (oder Laden) den Stand der Dateien festhalten."""
        self._stand_datei = _mtime(self.filepath)
        self._stand_punkte = _mtime(_punkte_pfad(self.sequences_dir))

    def rettung_schreiben(self) -> Optional[Path]:
        """Sichert ungespeicherte Änderungen beim Schliessen des Fensters.

        Gefragt wird nicht: das Fenster ist zu diesem Zeitpunkt schon auf dem Weg
        nach draussen. Die Kopie landet unter `backups/`, nicht in `sequences/` —
        dort listet `list_available_sequences()` jede `*.json` als Sequenz auf,
        und eine halbfertige Rettungsdatei zwischen den echten wäre schlimmer als
        der Verlust.
        """
        if not self._dirty:
            return None
        from ...persistence.sweep import sicherungspfad
        # sicherungspfad() liefert "<name>.json.bak" — hier soll die Datei lesbar
        # heissen und eine echte .json-Endung tragen, damit man sie direkt
        # zurückkopieren kann.
        ziel = sicherungspfad(self.filepath).with_name(
            f"{self.filepath.stem}.ungespeichert.json")
        try:
            ziel.parent.mkdir(parents=True, exist_ok=True)
            if save_sequence_file(board_to_sequence(self.board), ziel):
                return ziel
        except (IOError, OSError):
            return None
        return None

    # ---------------------------------------------------------------- Phasen

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
        zwischen Phasen. Letzteres gibt es im Konsolen-Editor gar nicht — eine
        Aufnahme nachträglich in INIT/LOOP/END aufzuteilen hiess dort löschen und
        neu anlegen.
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

        Der schnellste Weg zu einem Block, der einem vorhandenen fast gleicht —
        und das ist beim Bauen einer Sequenz der Normalfall: dieselbe Wartezeit,
        derselbe Trigger, dieselbe Nachprüfung, nur eine andere Stelle. Alles
        von Hand nachzustellen ist ein Dutzend Klicks, von denen jeder vergessen
        werden kann.

        **Die Kopie zeigt auf denselben Punkt.** Ein Duplikat ist erst mal
        derselbe Klick; wer eine andere Stelle will, wählt einen anderen Punkt.
        Einen zweiten Punkt an derselben Stelle anzulegen wäre genau die
        Doppelung, die `punkt_fuer_stelle()` überall sonst vermeidet — beim
        Nachjustieren wanderte dann nur die Hälfte mit.

        Kopiert wird tief: `else_config`, `wait_condition` und
        `verify_condition` sind eigene Objekte, sonst änderte ein Griff an der
        Kopie zugleich das Original.
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
        entfernt — die Ersatzaktion ist damit wirkungslos. Sie stehenzulassen
        hiesse, sie unsichtbar in der Datei zu behalten (der Abschnitt fällt ja
        mit dem Auslöser weg); sie automatisch abzuschalten macht den Block zu
        dem, was er jetzt ist. Stellt man den Typ zurück, steht der Abschnitt
        wieder da — leer, zum frischen Auswählen.

        **Nur bei einer Änderung, nie beim Laden.** Eine Datei, die von Hand oder
        durch einen Import ein wirkungsloses ELSE mitbringt, wird nicht
        stillschweigend beschnitten: dort bleibt der Abschnitt samt Warnung
        stehen, und der Nutzer entscheidet.

        Gibt den Meldungstext zurück (leer, wenn nichts zu tun war).
        """
        if step.else_config is None or else_greift(step):
            return ""
        step.else_config = None
        return "ELSE entfernt — dieser Block kann es nicht mehr auslösen."

    def block_typ(self, daten: dict) -> dict:
        """Stellt den Block-Typ um.

        FARBE+KLICK braucht einen Punkt: die Bedingung hängt an ihm, er ist die
        Quelle für Stelle UND Farbe. Ohne Punkt wird der Typwechsel abgelehnt —
        dieselbe Haltung wie bei `block_trigger`: lieber gar keine Bedingung als
        eine, die niemand mehr nachziehen kann.
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

        Vier Zahlenfelder sind kein Weg, einen Bildschirmbereich zu bestimmen —
        niemand weiss auswendig, wo (1740, 300) liegt. Also dasselbe wie in den
        Konsolen-Editoren: Maus hinbewegen, ENTER, zweite Ecke, ENTER. Nur ohne
        Konsole, denn die hat dieses Fenster nicht.

        **Beide Ecken in EINEM Aufruf**, nicht zwei Knoepfe. Ein erster Entwurf
        hatte je einen Knopf pro Ecke, damit dazwischen eine Momentaufnahme
        zurueckkommt und sagen kann, welche Ecke schon steht. Der Preis dafuer ist
        aber, dass die Hand mitten in der Aufnahme von der Ecke zum Fenster
        zurueckfahren muss — genau der Weg, den die Maus-Aufnahme ersparen soll.
        Die Rueckmeldung ist es nicht wert: was dabei herauskam, steht danach in
        vier Feldern und in der Groessen-Zeile.

        Abgebrochen wird bei ESC und bei Zeitablauf, und zwar **vollstaendig** —
        auch nach der ersten Ecke bleibt der alte Bereich stehen. Ein halb
        gesetzter Bereich waere ein Bereich, den niemand so wollte.

        Der Zahlenweg bleibt daneben stehen — fuer den Fall, dass man eine
        Koordinate abschreibt statt sie anzufahren.
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

        Der gemeinsame Teil von „Stelle mit der Maus setzen" (Klick-Block) und
        „Maus parken" (Einstellungen): das Fenster hat den Fokus, das Spiel
        nicht — gefragt wird deshalb über eine globale Taste, nicht über einen
        Knopf, den man nur mit der Maus erreicht.
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
        aber kein Punkt und gehört nicht in `points.json`. Übrig bleibt die
        Geste: Maus hin, ENTER.
        """
        x, y, meldung = self._stelle_abwarten()
        if x is None:
            return {"ok": False, "meldung": meldung + " — nichts geändert."}
        return {"ok": True, "x": x, "y": y}

    def punkt_aufnehmen(self, daten: Optional[dict] = None) -> dict:
        """Setzt die Stelle des Blocks auf die aktuelle Mausposition.

        „(1204, 262)" sagt niemandem etwas — die Stelle fährt man an. Genau das
        macht `bereich_aufnehmen()` schon für Screenshot-Bereiche; hier ist es
        derselbe Weg mit einer Ecke statt zweier: Maus hin, ENTER.

        Angelegt bzw. gesetzt wird über dieselben Methoden wie sonst, damit die
        Regeln gelten, die überall gelten: ein vorhandener Punkt an derselben
        Stelle wird wiederverwendet, und ein Trigger auf demselben Punkt zieht
        mit.
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

        Für den Blanko-Block: er hat noch keine Stelle, und ohne Punkt bliebe er
        ein Klick auf (0,0). Aufgenommen wird sonst im Hauptprozess — hier geht es
        nur darum, dass ein im Studio entstandener Block überhaupt eine Stelle
        bekommen kann.
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
