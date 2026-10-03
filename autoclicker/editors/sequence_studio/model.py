"""
GUI-freier Modell-Layer für das Sequenz-Studio.

Übersetzt eine Sequence in eine flache Lane-Struktur (INIT / Loop-Phasen / END)
und zurück — verlustfrei. Die Blöcke SIND die originalen SequenceStep-Objekte
(keine Kopie, keine Konvertierung der Felder), darum geht beim Round-Trip kein
Feld verloren: Wir gruppieren nur um und bauen am Ende wieder dieselbe Sequence
zusammen.

Dieser Layer hat KEINE GUI-Abhängigkeit und ist isoliert testbar (ast.parse +
einfacher Round-Trip-Test ohne Dear PyGui).
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ...models import (
    BLOCK_BOSS_SCAN, BLOCK_BOSS_WATCHER, BLOCK_CLICK, BLOCK_ICON_SCAN,
    BLOCK_ITEM_SCAN, BLOCK_KEY, BLOCK_SCREENSHOT, BLOCK_WAIT, BLOCK_WAIT_CLICK,
    POSITIONLESS_BLOCKS, ElseConfig, LoopPhase, Sequence, SequenceStep, WaitCondition,
    drop_position,
)

# Die Block-Typen und `block_type()` selbst liegen in `models.py`: die Laufzeit
# schreibt den Typ des laufenden Blocks in den Laufstatus, damit die Live-Ansicht
# ihn genauso färben kann wie das Board — und `runtime/` darf die Ansicht nicht
# importieren. Beschriftung und Farbe bleiben hier, das ist Anzeige.

# Lane-Arten
LANE_INIT = "init"
LANE_LOOP = "loop"
LANE_END = "end"

# Die drei Arten einer Phase, wie die Oberfläche sie nennt, und wann sie laufen.
# Die Seite bekommt beides über die Momentaufnahme (`phase_kinds`) — sie
# erfindet keine eigenen Namen.
PHASE_KIND_NAMES = {LANE_INIT: "START", LANE_LOOP: "Loop-Phase", LANE_END: "ABSCHLUSS"}
PHASE_KIND_WHEN = {LANE_INIT: "einmal vor allen Zyklen",
                   LANE_LOOP: "in jedem Zyklus",
                   LANE_END: "einmal nach dem letzten Zyklus"}


# Anzeige-Label je Block-Typ (kurz, für die Listenzeile)
BLOCK_LABELS = {
    BLOCK_SCREENSHOT: "SCREENSHOT",
    BLOCK_BOSS_WATCHER: "BOSS-WATCHER",
    BLOCK_BOSS_SCAN: "BOSS-SCAN",
    BLOCK_ITEM_SCAN: "ITEM-SCAN",
    BLOCK_ICON_SCAN: "ICON-SCAN",
    BLOCK_KEY: "TASTE",
    BLOCK_WAIT: "WARTEN",
    BLOCK_WAIT_CLICK: "FARBE+KLICK",
    BLOCK_CLICK: "KLICK",
}

# RGB-Farbe je Block-Typ. Sie sitzt als kleines Quadrat vor der Listenzeile —
# frueher faerbte sie die Titelzeile einer Node.
# Neun Typen, neun unterscheidbare Farben. Taste, Item-Scan und Icon-Scan lagen
# vorher alle im Bereich Orange/Gelb (220,130,50 / 210,180,60 / 210,140,60) — auf
# einer Karte nebeneinander waren sie nicht auseinanderzuhalten, und genau das ist
# der Zweck der Farbe. Die beiden Boss-Typen bleiben bewusst verwandt (sie tun
# Verwandtes), unterscheiden sich aber jetzt deutlich in der Helligkeit.
# Grau und Blau sind um ein paar Stufen dunkler als zuerst (120er-Grau,
# 60/120/200): so knapp unter der Leuchtdichte 0,2, dass helle Schrift darauf
# 4,5:1 erreicht — auf dem alten Wert lagen beide Schriftfarben bei 4,4.
BLOCK_COLORS = {
    BLOCK_SCREENSHOT: (150, 90, 200),   # Lila
    BLOCK_BOSS_WATCHER: (140, 40, 45),  # Dunkelrot (dauerhaft beobachten)
    BLOCK_BOSS_SCAN: (205, 60, 60),     # Rot (einmal schauen)
    BLOCK_ITEM_SCAN: (215, 185, 60),    # Gelb
    BLOCK_ICON_SCAN: (45, 165, 160),    # Türkis
    BLOCK_KEY: (225, 115, 55),          # Orange
    BLOCK_WAIT: (110, 110, 110),        # Grau
    BLOCK_WAIT_CLICK: (60, 170, 110),   # Grün
    BLOCK_CLICK: (50, 110, 190),        # Blau
}


def hex_color(rgb) -> Optional[str]:
    """(r,g,b) -> '#RRGGBB'. Unbrauchbare Werte ergeben None statt einer Falschfarbe.

    Steht hier und nicht in `bridge.py`, weil der Scans-Reiter sie genauso
    braucht (Slot-Hintergrund, Marker-Farben) — und ein zweites Exemplar wäre
    genau die Kopie, die irgendwann anders rundet.
    """
    if not rgb:
        return None
    try:
        r, g, b = (max(0, min(255, int(v))) for v in tuple(rgb)[:3])
    except (TypeError, ValueError):
        return None
    return f"#{r:02X}{g:02X}{b:02X}"


# Schrift auf einer Typfarbe: die Grundfarbe ist dunkel (#0C0F14), und auf
# den dunklen Typfarben fiel sie durch — Boss-Watcher (140, 40, 45) kam auf
# 2,2:1, Boss-Scan auf 3,9, Klick/Warten/Screenshot auf ~4,2. Die Schwelle
# liegt bei einer relativen Leuchtdichte von 0,2 (WCAG-Formel): darunter hell,
# darüber dunkel. Auf allen neun Typfarben ergibt das mindestens 4,5:1.
INK_DARK = "#0C0F14"
INK_LIGHT = "#FFFFFF"
_INK_THRESHOLD = 0.2


def ink_color(rgb) -> str:
    """Schriftfarbe, die auf `rgb` lesbar ist: hell auf dunklen Flächen, sonst dunkel."""
    try:
        r, g, b = (max(0, min(255, int(v))) / 255 for v in tuple(rgb)[:3])
    except (TypeError, ValueError):
        return INK_DARK

    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    luminance = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
    return INK_LIGHT if luminance < _INK_THRESHOLD else INK_DARK


def rgb_value(hex_value) -> Optional[tuple]:
    """'#RRGGBB' -> (r, g, b). Alles Unbrauchbare ergibt None (= keine Farbe)."""
    raw = str(hex_value or "").strip().lstrip("#")
    if len(raw) != 6:
        return None
    try:
        return tuple(int(raw[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


@dataclass
class Lane:
    """Eine Spalte im Board: INIT, eine Loop-Phase oder END."""
    kind: str                              # LANE_INIT / LANE_LOOP / LANE_END
    name: str                              # Anzeigename ("INIT", "Loop 1", "END")
    steps: list[SequenceStep] = field(default_factory=list)
    repeat: int = 1                        # nur relevant für LANE_LOOP
    scheduled_start: Optional[str] = None  # nur LANE_LOOP, "HH:MM"

    def is_loop(self) -> bool:
        return self.kind == LANE_LOOP


@dataclass
class SequenceBoard:
    """GUI-agnostische Darstellung einer Sequence als Lanes von Blöcken."""
    name: str
    total_cycles: int = 1
    description: str = ""
    lanes: list[Lane] = field(default_factory=list)
    next_sequence: str = ""
    next_delay: float = 30.0

    # --- Mutationen (von der Ansicht aufgerufen) ---------------------------------

    def loop_lanes(self) -> list[Lane]:
        return [ln for ln in self.lanes if ln.is_loop()]

    def add_step(self, lane: Lane, step: SequenceStep, at: Optional[int] = None) -> None:
        """Fügt einen Schritt in eine Lane ein (ans Ende oder an Position at)."""
        if at is None or at >= len(lane.steps):
            lane.steps.append(step)
        else:
            lane.steps.insert(max(0, at), step)

    def delete_step(self, lane: Lane, idx: int) -> Optional[SequenceStep]:
        """Entfernt einen Schritt; gibt ihn zurück (oder None bei ungültigem Index)."""
        if 0 <= idx < len(lane.steps):
            return lane.steps.pop(idx)
        return None

    def move_step(self, lane: Lane, idx: int, delta: int) -> int:
        """Verschiebt einen Schritt um delta (−1 = hoch, +1 = runter). Gibt neuen Index zurück."""
        if not (0 <= idx < len(lane.steps)):
            return idx
        new_idx = max(0, min(len(lane.steps) - 1, idx + delta))
        if new_idx == idx:
            return idx
        step = lane.steps.pop(idx)
        lane.steps.insert(new_idx, step)
        return new_idx

    def add_loop_lane(self) -> Lane:
        """Hängt eine neue Loop-Phase an (vor der END-Lane, falls vorhanden)."""
        loop_count = len(self.loop_lanes())
        new_lane = Lane(kind=LANE_LOOP, name=f"Phase {loop_count + 1}", steps=[], repeat=1)
        # vor END einfügen
        end_idx = next((i for i, ln in enumerate(self.lanes) if ln.kind == LANE_END), len(self.lanes))
        self.lanes.insert(end_idx, new_lane)
        return new_lane

    def special_lane(self, kind: str) -> Optional[Lane]:
        """START bzw. ABSCHLUSS — beide gibt es in jeder Sequenz genau einmal."""
        return next((ln for ln in self.lanes if ln.kind == kind), None)

    def convert_lane(self, lane: Lane, kind: str) -> Optional[Lane]:
        """Stellt eine Phase auf eine andere Art um — die Lane, in der die Blöcke
        danach stehen, oder `None`, wenn es nicht geht.

        Drei Arten, jede in jede, und die Blöcke gehen mit:

        - **→ Loop**: eine NEUE Loop-Phase an derselben Stelle im Ablauf — aus
          START wird die erste, aus ABSCHLUSS die letzte. `add_loop_lane()`
          taugte dafür nicht: es hängt immer hinten an, und Phasen lassen sich
          nicht umsortieren.
        - **→ START / ABSCHLUSS**: nur, wenn das Ziel LEER ist. Beide gibt es
          genau einmal; zwei Blockfolgen zusammenzulegen hiesse zu raten, welche
          zuerst läuft. Eine Loop-Phase verschwindet dabei (samt Wiederholungen
          und Startzeit — die hat eine Sonderphase nicht), eine Sonderphase
          bleibt leer zurück, für einen neuen Aufbau.

        Umbenannt wird dabei nichts: `delete_loop_lane()` zählt Namen wie
        „Loop 2" neu durch — hier behalten die übrigen Phasen ihre Namen.
        """
        if self.position(lane) is None or kind == lane.kind \
                or kind not in (LANE_INIT, LANE_LOOP, LANE_END):
            return None
        if kind == LANE_LOOP:
            target = Lane(kind=LANE_LOOP,
                          name="Start" if lane.kind == LANE_INIT else "Abschluss",
                          steps=[], repeat=1)
            self.insert_loop_lane(target, near=lane)
        else:
            target = self.special_lane(kind)
            if target is None or target.steps:
                return None
        target.steps = list(lane.steps)
        if lane.kind == LANE_LOOP:
            del self.lanes[self.position(lane)]
        else:
            lane.steps = []
        return target

    def position(self, lane: Lane) -> Optional[int]:
        """Wo die Phase steht — über ihre IDENTITÄT, nicht über Gleichheit.

        `Lane` ist eine Dataclass: `lanes.index()` fände von zwei gleich
        aussehenden Phasen (nach einem Duplizieren der Normalfall) immer die
        erste.
        """
        return next((i for i, ln in enumerate(self.lanes) if ln is lane), None)

    def insert_loop_lane(self, new_lane: Lane, near: Lane) -> None:
        """Setzt eine Loop-Phase dorthin, wo `near` im Ablauf steht.

        Hinter eine Loop-Phase (Duplikat), als ERSTE hinter START, als LETZTE vor
        ABSCHLUSS — dieselbe Stelle, an der ihre Blöcke vorher liefen.
        """
        at = self.position(near)
        self.lanes.insert(at if near.kind == LANE_END else at + 1, new_lane)

    def move_loop_lane(self, lane: Lane, delta: int) -> bool:
        """Verschiebt eine Loop-Phase um eine Stelle unter den Loop-Phasen.

        START bleibt vorn und ABSCHLUSS hinten: an ihnen vorbei geht es nicht,
        sie SIND der Anfang und das Ende. Gibt zurück, ob sich etwas bewegt hat.
        """
        at = self.position(lane)
        if at is None or lane.kind != LANE_LOOP or delta not in (-1, 1):
            return False
        other = at + delta
        if not (0 <= other < len(self.lanes)) or self.lanes[other].kind != LANE_LOOP:
            return False
        self.lanes[at], self.lanes[other] = self.lanes[other], self.lanes[at]
        return True

    def delete_loop_lane(self, lane: Lane) -> None:
        """Entfernt eine Loop-Lane (INIT/END bleiben immer erhalten)."""
        if lane.kind == LANE_LOOP and lane in self.lanes:
            self.lanes.remove(lane)
            # Nur automatisch vergebene Default-Namen ("Loop N"/"Phase N") neu
            # durchnummerieren — benutzerdefinierte Namen ("Farmen") bleiben.
            n = 0
            for ln in self.lanes:
                if ln.is_loop():
                    n += 1
                    if re.fullmatch(r"(?:Loop|Phase) \d+", ln.name):
                        ln.name = f"Phase {n}"


def sequence_to_board(seq: Sequence) -> SequenceBoard:
    """Wandelt eine Sequence in eine Lane-Struktur (INIT, Loops…, END)."""
    lanes: list[Lane] = [Lane(kind=LANE_INIT, name="INIT", steps=list(seq.init_steps))]
    for lp in seq.loop_phases:
        lanes.append(Lane(
            kind=LANE_LOOP,
            name=lp.name,
            steps=list(lp.steps),
            repeat=lp.repeat,
            scheduled_start=lp.scheduled_start,
        ))
    lanes.append(Lane(kind=LANE_END, name="END", steps=list(seq.end_steps)))
    return SequenceBoard(
        name=seq.name,
        total_cycles=seq.total_cycles,
        description=seq.description,
        lanes=lanes,
        next_sequence=seq.next_sequence,
        next_delay=seq.next_delay,
    )


def board_to_sequence(graph: SequenceBoard) -> Sequence:
    """Baut aus der Lane-Struktur wieder eine Sequence (verlustfrei)."""
    init_steps: list[SequenceStep] = []
    end_steps: list[SequenceStep] = []
    loop_phases: list[LoopPhase] = []
    for ln in graph.lanes:
        if ln.kind == LANE_INIT:
            init_steps = list(ln.steps)
        elif ln.kind == LANE_END:
            end_steps = list(ln.steps)
        elif ln.kind == LANE_LOOP:
            loop_phases.append(LoopPhase(
                name=ln.name,
                steps=list(ln.steps),
                repeat=ln.repeat,
                scheduled_start=ln.scheduled_start,
            ))
    return Sequence(
        name=graph.name,
        init_steps=init_steps,
        loop_phases=loop_phases,
        end_steps=end_steps,
        total_cycles=graph.total_cycles,
        description=graph.description,
        next_sequence=graph.next_sequence,
        next_delay=graph.next_delay,
    )


def palette_from_sequence(seq: Sequence) -> list["PalettePoint"]:
    """Punkt-Palette direkt aus ihrer Sequenz."""
    return [PalettePoint(p.id, p.x, p.y, p.name, p.color, p.source)
            for p in seq.points]


def palette_to_points(points: list) -> list:
    """Studio-Punkte zurück in das Sequenzmodell."""
    from ...models import ClickPoint
    return [ClickPoint(p.x, p.y, p.name, p.id, color=p.color, source=p.source)
            for p in points]


# =============================================================================
# PUNKTE-PALETTE
# =============================================================================

@dataclass
class PalettePoint:
    """Ein aufgenommener ClickPoint für die Palette (read-only)."""
    id: int
    x: int
    y: int
    name: str
    color: Optional[tuple[int, int, int]] = None
    source: str = ""  # Herkunfts-Kommentar, z.B. "Aufnahme"


def load_palette_points(sequence_file) -> list[PalettePoint]:
    """Lädt die Punkte aus der geöffneten ``sequence.json``.

    Eigene schlanke Ladefunktion statt persistence.load_points, da letztere ein
    AutoClickerState-Objekt braucht — der Subprocess hat keinen State.
    """
    points_file = Path(sequence_file)
    if not points_file.exists():
        return []
    try:
        with open(points_file, "r", encoding="utf-8") as f:
            data = json.load(f).get("points") or []
    except (json.JSONDecodeError, IOError, OSError):
        return []
    points: list[PalettePoint] = []
    for i, p in enumerate(data):
        # Einzelne defekte Einträge (z.B. "color":"rot" oder Nicht-Dict) dürfen
        # den Editor-Start nicht crashen — solche Einträge werden übersprungen.
        try:
            color_raw = p.get("color")
            color = tuple(int(v) for v in color_raw) if color_raw else None
            points.append(PalettePoint(
                id=p.get("id", i + 1),
                x=p.get("x", 0),
                y=p.get("y", 0),
                name=p.get("name", ""),
                color=color,
                source=p.get("source", ""),
            ))
        except (TypeError, ValueError, AttributeError, KeyError):
            continue
    return points


# Die Block-Typen, nach denen `scan_mouse_after` greift (`_scan_handler` in
# runtime/steps.py) — nur dort steht die Einstellung am Block.
SCAN_BLOCKS = (BLOCK_ITEM_SCAN, BLOCK_ICON_SCAN, BLOCK_BOSS_SCAN, BLOCK_BOSS_WATCHER)


def set_block_type(step: SequenceStep, new_type: str) -> None:
    """Stellt die diskriminierenden Felder eines Schritts auf einen neuen Typ um.

    Setzt alle Typ-Felder zurück und aktiviert nur die zum gewählten Typ
    passenden. Zwischen den Typen MIT Stelle (Klick, Farbe+Klick, Warten) bleibt
    der Punkt stehen — das sind zwei Schalter an demselben Block, und ein Schalter
    darf die Stelle nicht wegwerfen.

    **Ein Typ ohne Stelle verliert den Punkt** (`POSITIONLESS_BLOCKS`). Er blieb
    hier stehen, „damit der Punkt seine Position behält", und landete damit als
    `point_id` an einem Scan in der Datei: Farbfeld auf der Karte neben dem
    Scan-Namen, der Punkt galt als „verwendet", und vor dem Scan zeigte die
    Live-Ansicht dessen Pixel. Zurück zum Klick holt ihn STRG+Z (bzw. der Knopf
    an der Meldung). Der Name bleibt — er ist dann der eigene des Blocks.

    **Derselbe Typ noch einmal ändert nichts.** Die Diskriminatoren wurden erst
    zurückgesetzt und danach mit `step.item_scan or ""` „erhalten" — da waren
    sie aber schon `None`: ein Klick auf die schon markierte Kachel löschte den
    Scan-Namen, und eine Taste wurde wieder „enter".
    """
    previous = {"item_scan": step.item_scan, "icon_scan": step.icon_scan,
                "boss_scan": step.boss_scan, "boss_watcher": step.boss_watcher,
                "key_press": step.key_press}
    # Alle Diskriminatoren zurücksetzen
    step.screenshot_only = False
    step.boss_watcher = None
    step.boss_scan = None
    step.item_scan = None
    step.icon_scan = None
    step.key_press = None
    step.wait_only = False

    # screenshot_region nur für den SCREENSHOT-Typ behalten — sonst aufräumen,
    # damit kein Rest-Feld den Round-Trip verschmutzt.
    if new_type != BLOCK_SCREENSHOT:
        step.screenshot_region = None

    named = _NAMED_BLOCK_FIELDS.get(new_type)
    if named is not None:
        # Taste und Scans: das eigene Feld behalten (oder vorbelegen), eine
        # Farb-Bedingung werten sie nicht aus.
        field, fallback = named
        setattr(step, field, previous[field] or fallback)
        step.wait_condition = None
    elif new_type in (BLOCK_CLICK, BLOCK_SCREENSHOT):
        step.wait_condition = None
        step.screenshot_only = new_type == BLOCK_SCREENSHOT
    elif new_type == BLOCK_WAIT_CLICK:
        # **Am Punkt, nicht an den rohen Koordinaten.** Eine Bedingung ohne
        # `point_id` landet als `wait_pixel`/`wait_color` in der Datei — eine
        # Koordinaten-Kopie ausserhalb der Punktliste, die keine Kalibrierung
        # je wieder einholt. Stelle und Farbe holt `resolve()` aus dem Punkt;
        # ohne Punkt entsteht gar keine Bedingung (der Aufrufer lehnt den
        # Typwechsel dann ab).
        if step.wait_condition is None and step.point_id is not None:
            step.wait_condition = WaitCondition(point_id=step.point_id)
    elif new_type == BLOCK_WAIT:
        # wait_condition bleibt optional erhalten (Farb-Trigger-Feature).
        step.wait_only = True

    if new_type in POSITIONLESS_BLOCKS:
        drop_position(step)
    # „Maus danach absetzen" wertet nur ein Scan aus. Bei einem anderen Typ
    # bliebe ein Aus unsichtbar in der Datei stehen — der Schalter faellt ja weg.
    if new_type not in SCAN_BLOCKS:
        step.mouse_return = True


# Block-Typen, die über EIN benanntes Feld bestimmt sind: (Feld, Vorbelegung).
_NAMED_BLOCK_FIELDS = {
    BLOCK_KEY: ("key_press", "enter"),
    BLOCK_ITEM_SCAN: ("item_scan", ""),
    BLOCK_ICON_SCAN: ("icon_scan", ""),
    BLOCK_BOSS_SCAN: ("boss_scan", ""),
    BLOCK_BOSS_WATCHER: ("boss_watcher", ""),
}


def ensure_else(step: SequenceStep, action: str) -> ElseConfig:
    """Stellt sicher, dass ein else_config existiert und setzt dessen Aktion."""
    if step.else_config is None:
        step.else_config = ElseConfig(action=action)
    else:
        step.else_config.action = action
    return step.else_config


def step_from_point(pt: PalettePoint) -> SequenceStep:
    """Erzeugt einen Klick-Block aus einem Palette-Punkt.

    `point_id` MUSS mit: der Block kommt aus einem Punkt, also soll er ihm auch
    folgen. Ohne die Referenz haelt er seine Koordinaten selbst, und ein spaeter
    verschobener Punkt zieht ihn nicht mit — obwohl er aus genau diesem Punkt
    entstanden ist. `resolve_point_references()` zieht x/y vor jedem Lauf nach.
    """
    return SequenceStep(
        x=pt.x,
        y=pt.y,
        delay_before=0.0,
        name=pt.name,
        recorded_color=pt.color,
        point_id=pt.id,
    )
