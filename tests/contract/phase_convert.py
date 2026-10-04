"""Phasen umstellen: START ↔ Loop-Phase ↔ ABSCHLUSS, hin und zurück.

Gemeldet an einer echten Sequenz: der Start lief nur einmal, muss aber in jedem
Zyklus laufen — und danach kam die Frage nach dem Rückweg und nach ABSCHLUSS.
Von Hand ging das nur über eine neue Loop-Phase, und die landete hinter allen
anderen: angelegt wird immer am Ende, und Phasen lassen sich nicht umsortieren.
"""
import contextlib as _cl
import io as _io
import os as _os
import shutil as _sh
import tempfile as _tmp
from pathlib import Path as _P

from ._harness import check, section, studio_web_source
from autoclicker.models import (
    LoopPhase as _PHASE,
    Sequence as _SEQ,
    SequenceStep as _STEP,
)
from autoclicker.editors.sequence_studio.bridge import StudioBridge as _SB
from autoclicker.editors.sequence_studio.model import board_to_sequence as _to_seq


def _board():
    seq = _SEQ("Raid",
               init_steps=[_STEP(wait_only=True, delay_before=5.0),
                           _STEP(key_press="a"), _STEP(key_press="b")],
               loop_phases=[_PHASE("Loop 1", [_STEP(key_press="c")], repeat=3,
                                   scheduled_start="07:00"),
                            _PHASE("Loop 2", [_STEP(key_press="d")])],
               end_steps=[], total_cycles=10)
    with _cl.redirect_stdout(_io.StringIO()):
        return _SB(seq, _P("sequences/raid/sequence.json"), "sequences")


def _layout(b):
    return [(ln.kind, ln.name, [s.key_press or "w" for s in ln.steps])
            for ln in b.board.lanes]


def _index(b, name):
    return next(i for i, ln in enumerate(b.board.lanes) if ln.name == name)


_sandbox = _tmp.mkdtemp(prefix="phase_convert_")
_cwd = _os.getcwd()
_os.chdir(_sandbox)
try:
    # =========================================================================
    section("START → Loop-Phase: die Blöcke laufen danach in jedem Zyklus")
    # =========================================================================
    _b = _board()
    _b.select({"phase": 0, "row": 1})
    _snap = _b.phase_convert({"phase": 0, "to": "loop"})
    check("aus START wird die ERSTE Loop-Phase, START bleibt leer",
          _layout(_b) == [("init", "INIT", []),
                          ("loop", "Start", ["w", "a", "b"]),
                          ("loop", "Loop 1", ["c"]),
                          ("loop", "Loop 2", ["d"]),
                          ("end", "END", [])])
    check("die neue Phase läuft einmal je Zyklus",
          _b.board.lanes[1].repeat == 1 and _b.board.lanes[1].scheduled_start is None)
    check("die Meldung sagt, wohin und wann, und bietet Zurück an",
          "Loop-Phase „Start“" in _snap["status"]["text"]
          and "in jedem Zyklus" in _snap["status"]["text"] and _snap["undo"]["can"])
    check("die Auswahl zeigt nicht mehr in die leere Phase",
          _snap["selection"]["count"] == 0)
    _seq = _to_seq(_b.board)
    check("gespeichert: keine INIT-Schritte, Start als erste Loop-Phase, Zyklen bleiben",
          _seq.init_steps == [] and [p.name for p in _seq.loop_phases]
          == ["Start", "Loop 1", "Loop 2"] and _seq.total_cycles == 10)

    # =========================================================================
    section("…und zurück: Loop-Phase → START, → ABSCHLUSS, START ↔ ABSCHLUSS")
    # =========================================================================
    _snap = _b.phase_convert({"phase": _index(_b, "Start"), "to": "init"})
    check("zurück nach START: die Loop-Phase verschwindet, die Blöcke stehen in START",
          _layout(_b) == [("init", "INIT", ["w", "a", "b"]),
                          ("loop", "Loop 1", ["c"]), ("loop", "Loop 2", ["d"]),
                          ("end", "END", [])])
    check("…und die übrigen Loop-Phasen behalten ihre Namen (keine Neunummerierung)",
          [ln.name for ln in _b.board.loop_lanes()] == ["Loop 1", "Loop 2"])

    _snap = _b.phase_convert({"phase": _index(_b, "Loop 1"), "to": "end"})
    check("Loop-Phase → ABSCHLUSS: läuft einmal nach dem letzten Zyklus",
          _layout(_b)[-1] == ("end", "END", ["c"])
          and "einmal nach dem letzten Zyklus" in _snap["status"]["text"])
    check("…und sagt, was eine Sonderphase nicht kennt (Läufe, Startzeit)",
          _snap["status"]["kind"] == "warn"
          and "3 Läufe je Zyklus" in _snap["status"]["text"]
          and "Start ab 07:00" in _snap["status"]["text"])

    _before = len(_b._edit_undo)
    _snap = _b.phase_convert({"phase": 0, "to": "end"})
    check("START → ABSCHLUSS wird abgelehnt, solange ABSCHLUSS Blöcke hat",
          _snap["status"]["kind"] == "warn" and "ABSCHLUSS hat schon" in _snap["status"]["text"]
          and _layout(_b)[0] == ("init", "INIT", ["w", "a", "b"])
          and len(_b._edit_undo) == _before)
    _snap = _b.phase_convert({"phase": _index(_b, "Loop 2"), "to": "init"})
    check("…ebenso Loop-Phase → START, solange START Blöcke hat",
          _snap["status"]["kind"] == "warn" and len(_b._edit_undo) == _before)

    _b.phase_convert({"phase": len(_b.board.lanes) - 1, "to": "loop"})
    check("ABSCHLUSS → Loop-Phase: wird die LETZTE Loop-Phase",
          _layout(_b)[-2:] == [("loop", "Abschluss", ["c"]), ("end", "END", [])])
    _b.phase_convert({"phase": 0, "to": "end"})
    check("START → ABSCHLUSS direkt, wenn ABSCHLUSS leer ist",
          _layout(_b)[0] == ("init", "INIT", [])
          and _layout(_b)[-1] == ("end", "END", ["w", "a", "b"]))

    for _ in range(6):
        _b.undo()
    check("STRG+Z dreht die ganze Kette zurück",
          _layout(_b) == _layout(_board()))

    _before = len(_b._edit_undo)
    for _data, _why in (({"phase": 1, "to": "loop"}, "gleiche Art"),
                        ({"phase": 4, "to": "loop"}, "leeres ABSCHLUSS"),
                        ({"phase": 1, "to": "quatsch"}, "unbekanntes Ziel")):
        _b.phase_convert(_data)
        check(f"{_why}: nichts passiert, kein Abzug", len(_b._edit_undo) == _before
              and _layout(_b) == _layout(_board()))

    _kinds = _b.snapshot()["phase_kinds"]
    check("die Seite bekommt Namen und Laufzeitpunkt der drei Arten aus der Brücke",
          [k["key"] for k in _kinds] == ["init", "loop", "end"]
          and _kinds[0]["label"] == "START" and "jedem Zyklus" in _kinds[1]["when"])
finally:
    _os.chdir(_cwd)
    _sh.rmtree(_sandbox, ignore_errors=True)

_sandbox = _tmp.mkdtemp(prefix="phase_menu_")
_os.chdir(_sandbox)
try:
    # =========================================================================
    section("Phasen-Menü: duplizieren (mit eigenen Punkten) und verschieben")
    # =========================================================================
    from autoclicker.models import ClickPoint as _CP, WaitCondition as _WC
    _seq = _SEQ("Tag", loop_phases=[
        _PHASE("Sammeln", [_STEP(x=1, y=1, point_id=1, wait_condition=_WC(point_id=1)),
                           _STEP(x=1, y=1, point_id=1)], repeat=2),
        _PHASE("Kampf", [_STEP(key_press="k")])],
        points=[_CP(1, 1, "Knopf", 1, color=(1, 2, 3))])
    with _cl.redirect_stdout(_io.StringIO()):
        _b = _SB(_seq, _P("sequences/tag/sequence.json"), "sequences")
    _snap = _b.phase_duplicate({"phase": 1})
    _copy = _b.board.lanes[2]
    check("die Kopie steht direkt hinter dem Original und trägt einen eigenen Namen",
          [ln.name for ln in _b.board.lanes] == ["INIT", "Sammeln", "Sammeln (Kopie)", "Kampf", "END"]
          and _copy.repeat == 2)
    check("…und die Seite wählt sie (phase_focus)", _snap["phase_focus"] == 2)
    check("die Kopie hat EIGENE Punkte — und Klick + Prüf-Pixel bleiben EIN Punkt",
          _copy.steps[0].point_id not in (None, 1)
          and _copy.steps[0].wait_condition.point_id == _copy.steps[0].point_id
          and _copy.steps[1].point_id == _copy.steps[0].point_id
          and len(_b.points) == 2)
    check("das Original zeigt weiter auf seinen Punkt",
          [s.point_id for s in _b.board.lanes[1].steps] == [1, 1])
    check("phase_focus wird nur EINMAL ausgeliefert", _b.snapshot()["phase_focus"] is None)

    _snap = _b.phase_move({"phase": 2, "delta": 1})
    check("verschieben nach rechts: die Kopie läuft jetzt nach „Kampf“",
          [ln.name for ln in _b.board.lanes] == ["INIT", "Sammeln", "Kampf", "Sammeln (Kopie)", "END"]
          and _snap["phase_focus"] == 3)
    _before = len(_b._edit_undo)
    _snap = _b.phase_move({"phase": 3, "delta": 1})
    check("an ABSCHLUSS vorbei geht es nicht — nichts passiert, kein Abzug",
          _b.board.lanes[4].kind == "end" and len(_b._edit_undo) == _before
          and _snap["phase_focus"] == 3)
    _snap = _b.phase_move({"phase": 0, "delta": 1})
    check("START lässt sich nicht verschieben", _snap["status"]["kind"] == "warn")

    _b.phase_duplicate({"phase": 0})
    check("ein leeres START wird nicht dupliziert",
          len(_b.board.lanes) == 5)
    _b.select({"phase": 1, "row": 0})
    _b.phase_convert({"phase": 1, "to": "init"})
    _snap = _b.phase_duplicate({"phase": 0})
    check("START duplizieren ergibt eine Loop-Phase „Start (Kopie)“ als erste",
          _b.board.lanes[1].kind == "loop" and _b.board.lanes[1].name == "Start (Kopie)"
          and len(_b.board.lanes[0].steps) == 2 and _snap["phase_focus"] == 1)
finally:
    _os.chdir(_cwd)
    _sh.rmtree(_sandbox, ignore_errors=True)

_web = studio_web_source()
check("jeder Phasenkopf ist anklickbar und öffnet rechts das Phasen-Menü",
      "renderPhaseInspector(target, S.phases[selectedPhase])" in _web
      and 'call("phase_convert", {phase: phase.index, to: kind.key})' in _web
      and 'call("phase_move", {phase: phase.index, delta: -1})' in _web
      and 'call("phase_duplicate", {phase: selectedPhase})' in _web)
check("die Art steht NICHT mehr als Auswahl im Kopf (sie nahm dem Namen den Platz)",
      "phaseKindChooser" not in _web and "phase-kind" not in _web
      and "phase_to_loop" not in _web)
check("die Seite übernimmt den Fokus der Brücke nach einem Phasen-Befehl",
      "selectedPhase = S.phase_focus" in _web)


# =============================================================================
section("START und ABSCHLUSS lassen sich löschen — das heisst: leeren")
# =============================================================================
_sandbox = _tmp.mkdtemp(prefix="phase_delete_")
_os.chdir(_sandbox)
try:
    _b = _board()
    _snap = _b.phase_delete({"phase": 0})
    check("volles START: die Blöcke sind weg, die Phase bleibt als leere bestehen",
          _b.board.lanes[0].kind == "init" and _b.board.lanes[0].steps == []
          and "START gelöscht — 3 Blöcke entfernt" in _snap["status"]["text"]
          and _snap["undo"]["can"])
    _b.undo()
    check("STRG+Z holt die Blöcke zurück", len(_b.board.lanes[0].steps) == 3)
    _before = len(_b._edit_undo)
    _snap = _b.phase_delete({"phase": len(_b.board.lanes) - 1})
    check("leeres ABSCHLUSS: nur ausblenden, kein Abzug",
          _snap["status"]["kind"] == "info" and len(_b._edit_undo) == _before)
finally:
    _os.chdir(_cwd)
    _sh.rmtree(_sandbox, ignore_errors=True)

_web = studio_web_source()
_delete = _web[_web.index("function deleteSelectedPhase()"):]
_delete = _delete[:_delete.index("\n}\n")]
check("die Seite blendet eine gelöschte Sonderphase aus (sonst bleibt eine leere Hülle)",
      "openSpecialPhases.delete(kind)" in _delete)
check("„löschen“ ist im Phasen-Menü auch bei START und ABSCHLUSS aktiv",
      "deleteBtn.disabled = false" in _web)