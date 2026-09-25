"""Auswahl über Phasen hinweg: STRG+Klick in eine andere Phase nimmt dazu.

Die Auswahl lebte in genau EINER Phase, mit der Begründung, „eine Position
hoch" und die Sammelaktionen wären sonst nicht eindeutig. Das kostete genau den
Fall, für den man sie braucht: nach einer Aufnahme mit vier Loops dieselbe
Wartezeit an zehn Blöcke setzen — Phase für Phase, viermal. Die Sammelaktionen
arbeiten jetzt je Phase für sich (`_selection_groups()`), und damit hat auch
„hoch" eine Bedeutung: hoch in der eigenen Phase.
"""
from pathlib import Path

from ._harness import check, section, studio_web_source
from autoclicker.models import (
    ClickPoint as _CP,
    LoopPhase as _PHASE,
    Sequence as _SEQ,
    SequenceStep as _STEP,
)
from autoclicker.editors.sequence_studio.bridge import StudioBridge as _SB

INIT, A, B, END = 0, 1, 2, 3


def _bridge(shared: bool = False):
    """INIT leer, Loop A und Loop B mit je drei Klick-Blöcken, END leer.

    Jeder Block hat einen eigenen Punkt mit seinem Namen — der Name eines
    Klick-Blocks KOMMT vom Punkt, und so lässt sich jeder Block nach dem
    Umsortieren wiederfinden. Mit `shared` klickt b2 denselben Punkt wie a0.
    """
    names = ["a0", "a1", "a2", "b0", "b1", "b2"]
    points = [_CP(10 * i, 10 * i, name, i) for i, name in enumerate(names, 1)]
    ids = dict(zip(names, range(1, 7)))
    if shared:
        ids["b2"] = ids["a0"]
    seq = _SEQ("quer", loop_phases=[
        _PHASE("A", steps=[_STEP(point_id=ids[n]) for n in names[:3]]),
        _PHASE("B", steps=[_STEP(point_id=ids[n]) for n in names[3:]]),
    ], points=points)
    b = _SB(seq, Path("sequences/quer/sequence.json"), "sequences")
    b._dirty = False
    return b


def _names(b, lane):
    return [b._point(s.point_id).name for s in b.board.lanes[lane].steps]


def _picked(snap):
    """Gewählte Karten der Momentaufnahme als {(Phase, Zeile)}."""
    return {(p["index"], blk["row"]) for p in snap["phases"] for blk in p["blocks"]
            if blk["selected"]}


# =============================================================================
section("STRG+Klick in eine andere Phase nimmt dazu, statt neu anzufangen")
# =============================================================================
_b = _bridge()
_b.select({"phase": A, "row": 0, "mode": "single"})
_snap = _b.select({"phase": B, "row": 1, "mode": "add"})
check("beide Blöcke sind gewählt — in zwei Phasen", _picked(_snap) == {(A, 0), (B, 1)})
check("die Momentaufnahme zählt über alle Phasen",
      _snap["selection"]["count"] == 2 and _snap["selection"]["phases"] == 2)
check("zwei Gewählte sind kein Einzelblock — der Inspektor bleibt beim Sammeln",
      _b._single()[2] is None and _snap["block"] is None)
_snap = _b.select({"phase": B, "row": 1, "mode": "add"})
check("derselbe STRG+Klick nimmt ihn wieder heraus, die andere Phase bleibt",
      _picked(_snap) == {(A, 0)} and _b.sel_lane is _b.board.lanes[A])
_snap = _b.select({"phase": A, "row": 0, "mode": "add"})
check("wird der letzte herausgenommen, ist die Auswahl leer",
      _picked(_snap) == set() and _b.sel_lane is None and _b.sel_other == [])
_b.select({"phase": A, "row": 0, "mode": "single"})
_b.select({"phase": B, "row": 2, "mode": "add"})
_snap = _b.select({"phase": A, "row": 1, "mode": "single"})
check("ein einfacher Klick fängt wie bisher neu an", _picked(_snap) == {(A, 1)})

# =============================================================================
section("Umschalt+Klick bleibt ein Bereich innerhalb einer Phase")
# =============================================================================
_b = _bridge()
_b.select({"phase": A, "row": 0, "mode": "single"})
_snap = _b.select({"phase": B, "row": 2, "mode": "area"})
check("in einer anderen Phase nimmt er nur den Block dazu",
      _picked(_snap) == {(A, 0), (B, 2)})
_snap = _b.select({"phase": B, "row": 0, "mode": "area"})
check("und setzt dort den Anker — der nächste Umschalt+Klick zieht den Bereich",
      _picked(_snap) == {(A, 0), (B, 0), (B, 1), (B, 2)})

# =============================================================================
section("Sammelaktionen arbeiten je Phase")
# =============================================================================
_b = _bridge()
_b.select({"phase": A, "row": 0, "mode": "single"})
_b.select({"phase": B, "row": 1, "mode": "add"})
_snap = _b.selection_set({"field": "delay_before", "value": 30})
check("die Wartezeit landet in beiden Phasen",
      _b.board.lanes[A].steps[0].delay_before == 30
      and _b.board.lanes[B].steps[1].delay_before == 30
      and _b.board.lanes[A].steps[1].delay_before == 0)
check("und die Meldung sagt, dass es zwei Phasen waren",
      "2 Blöcke" in _snap["status"]["text"] and "2 Phasen" in _snap["status"]["text"])
check("der gemeinsame Wert steht danach im Sammel-Inspektor",
      _snap["selection"]["delay_before"] == 30
      and _snap["selection"]["delay_before_mixed"] is False)

# Hoch: wer schon oben steht, bleibt stehen — ohne die andere Phase aufzuhalten.
_b = _bridge()
_b.select({"phase": A, "row": 1, "mode": "single"})
_b.select({"phase": B, "row": 0, "mode": "add"})
_snap = _b.selection_move({"delta": -1})
check("ALT+↑ schiebt in Loop A hoch, Loop B steht schon oben und bleibt",
      _names(_b, A) == ["a1", "a0", "a2"] and _names(_b, B) == ["b0", "b1", "b2"])
check("die Auswahl wandert mit", _picked(_snap) == {(A, 0), (B, 0)})
_stack = len(_b._edit_undo)
_b.selection_move({"delta": -1})
check("stehen alle oben, passiert nichts — und es kommt kein Rückgängig-Stand dazu",
      _names(_b, A) == ["a1", "a0", "a2"] and len(_b._edit_undo) == _stack)

# Duplizieren: je Phase hinter die letzte Gewählte, EIN neuer Punkt je Knopf.
# b2 klickt hier denselben Punkt wie a0 — und heisst deshalb auch so.
_b = _bridge(shared=True)
_b.select({"phase": A, "row": 0, "mode": "single"})
_b.select({"phase": B, "row": 2, "mode": "add"})
_before = len(_b.points)
_snap = _b.selection_duplicate()
check("jede Phase bekommt ihre Kopie direkt hinter die eigene Auswahl",
      _names(_b, A) == ["a0", "a0", "a1", "a2"] and _names(_b, B) == ["b0", "b1", "a0", "a0"])
check("die Kopien sind die neue Auswahl", _picked(_snap) == {(A, 1), (B, 3)})
check("a0 und b2 klicken denselben Knopf — ihre Kopien teilen EINEN neuen Punkt",
      len(_b.points) == _before + 1
      and _b.board.lanes[A].steps[1].point_id == _b.board.lanes[B].steps[3].point_id != 1)

# Löschen und Zurück.
_b = _bridge()
_b.select({"phase": A, "row": 2, "mode": "single"})
_b.select({"phase": B, "row": 0, "mode": "add"})
_snap = _b.selection_delete()
check("Entf löscht in beiden Phasen",
      _names(_b, A) == ["a0", "a1"] and _names(_b, B) == ["b1", "b2"]
      and "2 Blöcke" in _snap["status"]["text"])
_snap = _b.undo()
check("STRG+Z holt beide zurück — samt der Auswahl über beide Phasen",
      _names(_b, A) == ["a0", "a1", "a2"] and _names(_b, B) == ["b0", "b1", "b2"]
      and _picked(_snap) == {(A, 2), (B, 0)})

# Ziehen: die ganze Auswahl wandert mit, in Board-Reihenfolge.
_b = _bridge()
_b.select({"phase": B, "row": 2, "mode": "single"})
_b.select({"phase": A, "row": 1, "mode": "add"})
_snap = _b.drag({"from_phase": B, "from_row": 2, "to_phase": END, "to_row": 0})
check("gezogen wird die ganze Auswahl — erst die linke Phase, dann die rechte",
      _names(_b, END) == ["a1", "b2"] and _names(_b, A) == ["a0", "a2"]
      and _names(_b, B) == ["b0", "b1"])
check("und sie ist danach dort gewählt", _picked(_snap) == {(END, 0), (END, 1)})
# Ein NICHT gewählter Block nimmt beim Ziehen nur sich selbst mit.
_b.select({"phase": A, "row": 0, "mode": "single"})
_b.select({"phase": B, "row": 0, "mode": "add"})
_b.drag({"from_phase": B, "from_row": 1, "to_phase": B, "to_row": 0})
check("ein ungewählter Block zieht die Auswahl nicht mit",
      _names(_b, B) == ["b1", "b0"] and _names(_b, A) == ["a0", "a2"])
# Innerhalb der Zielphase zählt der Versatz nur für die Blöcke, die aus ihr kommen.
_b = _bridge()
_b.select({"phase": B, "row": 0, "mode": "single"})
_b.select({"phase": A, "row": 0, "mode": "add"})
_b.drag({"from_phase": B, "from_row": 0, "to_phase": B, "to_row": 3})
check("ans Ende der eigenen Phase: der Block aus B zählt beim Versatz, der aus A nicht",
      _names(_b, B) == ["b1", "b2", "a0", "b0"] and _names(_b, A) == ["a1", "a2"])

# =============================================================================
section("„Alle Blöcke wählen“: STRG nimmt die Phase dazu, Abwählen trifft nur sie")
# =============================================================================
_b = _bridge()
_b.select({"phase": A, "row": 0, "mode": "single"})
_snap = _b.phase_selection({"phase": B, "add": True})
check("mit STRG kommt Loop B dazu, der Block in Loop A bleibt",
      _picked(_snap) == {(A, 0), (B, 0), (B, 1), (B, 2)})
_snap = _b.phase_selection({"phase": B})
check("derselbe Knopf nimmt nur Loop B wieder heraus", _picked(_snap) == {(A, 0)})
_snap = _b.phase_selection({"phase": B})
check("ohne STRG ersetzt er die Auswahl wie bisher",
      _picked(_snap) == {(B, 0), (B, 1), (B, 2)})

# =============================================================================
section("Phasen werden an der Identität erkannt, nicht an der Gleichheit")
# =============================================================================
# `Lane` ist eine Dataclass: zwei gleich aussehende Phasen sind gleich, und
# `lanes.index()` fand immer die erste. Die Auswahl stand dann in der
# Momentaufnahme an der falschen Phase.
_twin = _SEQ("zwilling", loop_phases=[_PHASE("L", steps=[_STEP(key_press="e")]),
                                      _PHASE("L", steps=[_STEP(key_press="e")])])
_bt = _SB(_twin, Path("sequences/zwilling/sequence.json"), "sequences")
check("die beiden Phasen sind wirklich gleich", _bt.board.lanes[1] == _bt.board.lanes[2])
_snap = _bt.select({"phase": 2, "row": 0, "mode": "single"})
check("gewählt in der ZWEITEN — und die Momentaufnahme sagt die zweite",
      _snap["selection"]["phase"] == 2 and _picked(_snap) == {(2, 0)})

# =============================================================================
section("Die Seite zählt über alle Phasen")
# =============================================================================
_app = studio_web_source()
_inspector = _app[_app.index("function renderInspector"):]
_inspector = _inspector[:_inspector.index("\nfunction ", 1)]
check("der Inspektor zählt `count`, nicht die Zeilen der letzten Phase",
      "S.selection.count" in _inspector and "S.selection.rows.length" not in _inspector)
check("„Alle Blöcke wählen“ fragt die Karten und reicht STRG weiter",
      "phase.blocks.every((b) => b.selected)" in _app
      and 'call("phase_selection",\n                             {phase: phase.index, add: e.ctrlKey || e.metaKey})' in _app)
check("„Ab hier aufnehmen“ verlangt genau einen Block über alle Phasen",
      "S.selection.count === 1" in _app)
check("kein Rest liest mehr die Zeilenzahl der letzten Phase als Auswahlgrösse",
      "S.selection.rows.length" not in _app)
