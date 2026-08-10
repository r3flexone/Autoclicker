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
    ElseConfig, LoopPhase, Sequence, SequenceStep, WaitCondition,
)

# Block-Typ-Konstanten (für Farbkodierung + Labels in der Liste).
# Reihenfolge der Erkennung in block_type() entspricht der Executor-Priorität.
BLOCK_SCREENSHOT = "screenshot"
BLOCK_BOSS_WATCHER = "boss_watcher"
BLOCK_BOSS_SCAN = "boss_scan"
BLOCK_ITEM_SCAN = "item_scan"
BLOCK_ICON_SCAN = "icon_scan"
BLOCK_KEY = "key"
BLOCK_WAIT = "wait"          # wait_only ohne Klick
BLOCK_WAIT_CLICK = "wait_click"  # wait_condition + Klick
BLOCK_CLICK = "click"        # einfacher Klick (evtl. mit Zeit-Delay)

# Lane-Arten
LANE_INIT = "init"
LANE_LOOP = "loop"
LANE_END = "end"


def block_type(step: SequenceStep) -> str:
    """Bestimmt den Block-Typ eines Schritts (gleiche Priorität wie der Executor).

    Die String-Diskriminatoren werden mit `is not None` geprüft, nicht per
    Truthiness: ein frisch im Editor gewählter Scan-/Tasten-Block hat zunächst
    einen leeren Namen ("") und soll trotzdem als sein gewählter Typ angezeigt
    werden, bis der User den Namen einträgt. Geladene Sequenzen haben hier nie
    "" (nur None oder echte Namen), darum bleibt das Verhalten identisch.
    """
    if step.screenshot_only:
        return BLOCK_SCREENSHOT
    if step.boss_watcher is not None:
        return BLOCK_BOSS_WATCHER
    if step.boss_scan is not None:
        return BLOCK_BOSS_SCAN
    if step.icon_scan is not None:
        return BLOCK_ICON_SCAN
    if step.item_scan is not None:
        return BLOCK_ITEM_SCAN
    if step.key_press is not None:
        return BLOCK_KEY
    if step.wait_only:
        return BLOCK_WAIT
    if step.wait_condition:
        return BLOCK_WAIT_CLICK
    return BLOCK_CLICK


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
BLOCK_COLORS = {
    BLOCK_SCREENSHOT: (150, 90, 200),   # Lila
    BLOCK_BOSS_WATCHER: (200, 60, 60),  # Rot
    BLOCK_BOSS_SCAN: (200, 80, 80),     # Rot (heller)
    BLOCK_ITEM_SCAN: (210, 180, 60),    # Gelb
    BLOCK_ICON_SCAN: (210, 140, 60),    # Orange-Gelb
    BLOCK_KEY: (220, 130, 50),          # Orange
    BLOCK_WAIT: (120, 120, 120),        # Grau
    BLOCK_WAIT_CLICK: (60, 170, 110),   # Grün-Cyan
    BLOCK_CLICK: (60, 120, 200),        # Blau
}


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
        new_lane = Lane(kind=LANE_LOOP, name=f"Loop {loop_count + 1}", steps=[], repeat=1)
        # vor END einfügen
        end_idx = next((i for i, ln in enumerate(self.lanes) if ln.kind == LANE_END), len(self.lanes))
        self.lanes.insert(end_idx, new_lane)
        return new_lane

    def delete_loop_lane(self, lane: Lane) -> None:
        """Entfernt eine Loop-Lane (INIT/END bleiben immer erhalten)."""
        if lane.kind == LANE_LOOP and lane in self.lanes:
            self.lanes.remove(lane)
            # Nur automatisch vergebene Default-Namen ("Loop N") neu
            # durchnummerieren — benutzerdefinierte Namen ("Farmen") bleiben.
            n = 0
            for ln in self.lanes:
                if ln.is_loop():
                    n += 1
                    if re.fullmatch(r"Loop \d+", ln.name):
                        ln.name = f"Loop {n}"


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
    )


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
    source: str = ""  # Herkunfts-Kommentar, z.B. "Aufnahme 'Bossfarm'"


def save_palette_points(sequences_dir: str, points: list) -> bool:
    """Schreibt die Palette zurueck nach sequences/points.json.

    Frueher las das Studio die Punkte nur. Das ging, solange die Sequenz ihre
    Koordinaten selbst trug — seit sie das nicht mehr tut, waere eine hier eingetippte
    Position beim Speichern verloren. Deshalb wandert die Palette mit.

    Wie ueberall im Subprozess gilt: die Datei ist der gemeinsame Nenner. Wer im
    Hauptprozess gleichzeitig speichert, ueberschreibt eine der beiden Fassungen.
    """
    from ...models import ClickPoint
    from ...persistence.serialization import _point_to_dict
    from ...utils import atomic_write, compact_json
    try:
        daten = [_point_to_dict(ClickPoint(p.x, p.y, p.name, p.id,
                                           color=p.color, source=p.source))
                 for p in points]
        atomic_write(Path(sequences_dir) / "points.json", compact_json(daten))
        return True
    except (OSError, TypeError, ValueError):
        return False


def load_palette_points(sequences_dir: str) -> list[PalettePoint]:
    """Lädt die aufgenommenen Punkte aus sequences/points.json.

    Eigene schlanke Ladefunktion statt persistence.load_points, da letztere ein
    AutoClickerState-Objekt braucht — der Subprocess hat keinen State.
    """
    points_file = Path(sequences_dir) / "points.json"
    if not points_file.exists():
        return []
    try:
        with open(points_file, "r", encoding="utf-8") as f:
            data = json.load(f)
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


def set_block_type(step: SequenceStep, new_type: str) -> None:
    """Stellt die diskriminierenden Felder eines Schritts auf einen neuen Typ um.

    Setzt alle Typ-Felder zurück und aktiviert nur die zum gewählten Typ
    passenden. Erhaltene Felder (x, y, name, delay_before, else_config) bleiben
    unangetastet, damit ein in einen Block gesetzter Punkt seine Position behält.
    """
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

    if new_type == BLOCK_CLICK:
        step.wait_condition = None
    elif new_type == BLOCK_WAIT_CLICK:
        if step.wait_condition is None:
            color = tuple(step.recorded_color) if step.recorded_color else (0, 0, 0)
            step.wait_condition = WaitCondition(pixel=(step.x, step.y), color=color)
    elif new_type == BLOCK_WAIT:
        # wait_condition bleibt optional erhalten (Farb-Trigger-Feature).
        step.wait_only = True
    elif new_type == BLOCK_KEY:
        step.key_press = step.key_press or "enter"
        step.wait_condition = None
    elif new_type == BLOCK_ITEM_SCAN:
        step.item_scan = step.item_scan or ""
        step.wait_condition = None
    elif new_type == BLOCK_ICON_SCAN:
        step.icon_scan = step.icon_scan or ""
        step.wait_condition = None
    elif new_type == BLOCK_BOSS_SCAN:
        step.boss_scan = step.boss_scan or ""
        step.wait_condition = None
    elif new_type == BLOCK_BOSS_WATCHER:
        step.boss_watcher = step.boss_watcher or ""
        step.wait_condition = None
    elif new_type == BLOCK_SCREENSHOT:
        step.screenshot_only = True
        step.wait_condition = None


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
