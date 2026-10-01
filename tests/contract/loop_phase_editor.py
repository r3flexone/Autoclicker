"""Konsolen-Editor der Loop-Phasen (`sequence_editor/loops.py`), per Tastenfolge.

Geschrieben, BEVOR `edit_loop_phases()` in Stufen zerlegt wurde: 201 Zeilen,
Komplexität 52 — die verzweigteste Funktion des Repos —, und in keinem Test.
Der Editor braucht nur `safe_input`, `confirm` und den Schritt-Editor
`edit_phase`; alle drei werden hier gestellt, und geprüft wird, was danach in
der Liste der Phasen steht.
"""
import contextlib as _cl
import io as _io

from ._harness import check, section

section("Loop-Phasen-Editor: Befehle per Tastenfolge")

import autoclicker.editors.sequence_editor.loops as _LO
from autoclicker.models import AutoClickerState as _ST, LoopPhase as _LP, SequenceStep as _STEP


def _run(phases, inputs, steps_from_editor=None, answers=None):
    """Fährt den Editor mit einer Tastenfolge. Gibt (Ergebnis, Ausgabe, Aufrufe) zurück.

    `steps_from_editor`: was der gestellte Schritt-Editor zurückgibt — eine
    Liste, None (= dort abgebrochen) oder eine Funktion `(Schritte) -> …`.
    `answers`: die Antworten auf Rückfragen (`confirm`), der Reihe nach.
    """
    feed = list(inputs)
    replies = list(answers or [])
    calls = []

    def phase_editor(state, steps, name):
        calls.append((name, steps))
        if callable(steps_from_editor):
            return steps_from_editor(steps)
        return steps_from_editor

    old = (_LO.safe_input, _LO.confirm, _LO.edit_phase)
    _LO.safe_input = lambda _p="": feed.pop(0) if feed else "cancel"
    _LO.confirm = lambda _q, *a, **k: replies.pop(0) if replies else False
    _LO.edit_phase = phase_editor
    buffer = _io.StringIO()
    try:
        with _cl.redirect_stdout(buffer):
            result = _LO.edit_loop_phases(_ST(), phases)
    finally:
        _LO.safe_input, _LO.confirm, _LO.edit_phase = old
    return result, buffer.getvalue(), calls


def _phases(*names):
    return [_LP(name, [_STEP(wait_only=True)], 1) for name in names]


# --- Ende des Editors ---
_list = _phases("A")
_res, _out, _ = _run(_list, ["done"])
check("'done' gibt dieselbe Liste zurück", _res is _list)
check("'d' ebenso", _run(_phases("A"), ["d"])[0] is not None)
check("Grossschreibung stört nicht", _run(_phases("A"), ["DONE"])[0] is not None)
check("'cancel' gibt None", _run(_phases("A"), ["cancel"])[0] is None)
_res, _out, _ = _run(_phases("A"), ["", "quatsch", "done"])
check("eine leere Eingabe fragt weiter", _res is not None)
check("ein unbekannter Befehl wird gesagt", "Unbekannter Befehl" in _out)
_res, _out, _ = _run(_phases("A"), ["edit", "done"])
check("'edit' ohne Nummer ist ein unbekannter Befehl", "Unbekannter Befehl" in _out)

# --- add ---
_steps = [_STEP(wait_only=True), _STEP(wait_only=True)]
_res, _out, _calls = _run(_phases("Loop 1"), ["add", "", "3", "12:30", "done"],
                          steps_from_editor=_steps)
check("add schlägt den ersten freien Namen vor", _res[1].name == "Loop 2")
check("und öffnet den Schritt-Editor mit leerer Liste", _calls == [("Loop 2", [])])
check("die Schritte kommen aus dem Schritt-Editor", _res[1].steps == _steps)
check("Wiederholungen und Startzeit werden übernommen",
      (_res[1].repeat, _res[1].scheduled_start) == (3, "12:30"))
_res, _, _ = _run([], ["add", "Farmen", "", "", "done"], steps_from_editor=[])
check("ein getippter Name gilt", _res[0].name == "Farmen")
check("ohne Angaben: einmal, sofort", (_res[0].repeat, _res[0].scheduled_start) == (1, None))
_res, _, _ = _run([], ["add", "", "0", "", "done"], steps_from_editor=[])
check("0 Wiederholungen werden 1", _res[0].repeat == 1)
_res, _out, _ = _run([], ["add", "", "", "", "done"], steps_from_editor=None)
check("Abbruch im Schritt-Editor verwirft nur die neue Phase", _res == [])
check("und sagt es", "verworfen" in _out)

# --- edit ---
_list = _phases("A", "B")
_old_steps = _list[1].steps


def _change(steps):
    steps.append(_STEP(wait_only=True))
    return steps


_res, _, _calls = _run(_list, ["edit 2", "4", "7:05", "done"], steps_from_editor=_change)
check("edit gibt dem Schritt-Editor eine KOPIE", _calls[0][1] is not _old_steps)
check("und übernimmt das Ergebnis", len(_res[1].steps) == 2)
check("Wiederholungen und Startzeit werden gesetzt",
      (_res[1].repeat, _res[1].scheduled_start) == (4, "07:05"))
_list = _phases("A")
_list[0].repeat, _list[0].scheduled_start = 3, "08:00"
_res, _, _ = _run(_list, ["edit 1", "", "", "done"], steps_from_editor=lambda s: s)
check("Enter behält Wiederholungen und Startzeit",
      (_res[0].repeat, _res[0].scheduled_start) == (3, "08:00"))
_res, _, _ = _run(_list, ["edit 1", "", "0", "done"], steps_from_editor=lambda s: s)
check("'0' entfernt die Startzeit", _res[0].scheduled_start is None)
_list = _phases("A")
_orig = _list[0].steps


def _change_then_cancel(steps):
    steps.append(_STEP(wait_only=True))
    return None


_res, _out, _ = _run(_list, ["edit 1", "done"], steps_from_editor=_change_then_cancel)
check("Abbruch im Schritt-Editor lässt die alten Schritte stehen",
      _res[0].steps is _orig and len(_orig) == 1)
check("und sagt es", "verworfen" in _out)
_res, _out, _ = _run(_phases("A"), ["edit 5", "done"])
check("edit mit Nummer ausserhalb wird gesagt", "Ungültige Nr" in _out)
_res, _out, _ = _run(_phases("A"), ["edit x", "done"])
check("edit mit Buchstaben nennt das Format", "Format: edit <Nr>" in _out)

# --- del ---
_res, _, _ = _run(_phases("A", "B", "C"), ["del 2", "done"])
check("del <Nr> löscht genau diese Phase", [p.name for p in _res] == ["A", "C"])
_res, _out, _ = _run(_phases("A"), ["del 3", "done"])
check("del ausserhalb wird gesagt", "Ungültige Nr" in _out and len(_res) == 1)
_res, _out, _ = _run(_phases("A"), ["del x", "done"])
check("del mit Buchstaben nennt das Format", "Format: del <Nr>" in _out)
_res, _, _ = _run(_phases("A", "B", "C", "D"), ["del 2-3", "done"], answers=[True])
check("del <Von>-<Bis> löscht den Bereich nach Rückfrage", [p.name for p in _res] == ["A", "D"])
_res, _, _ = _run(_phases("A", "B", "C"), ["del 1-2", "done"], answers=[False])
check("ohne Zustimmung bleibt alles", len(_res) == 3)
_res, _out, _ = _run(_phases("A", "B"), ["del 2-1", "del 1-5", "done"])
check("ein verdrehter oder zu langer Bereich wird abgelehnt",
      _out.count("Ungültiger Bereich") == 2 and len(_res) == 2)
_res, _out, _ = _run(_phases("A"), ["del a-b", "done"])
check("ein Bereich aus Buchstaben nennt das Format", "Format: del <Nr>-<Nr>" in _out)
_res, _, _ = _run(_phases("A", "B"), ["del all", "done"], answers=[True])
check("del all leert nach Rückfrage", _res == [])
_res, _, _ = _run(_phases("A", "B"), ["del all", "done"], answers=[False])
check("ohne Zustimmung bleibt alles", len(_res) == 2)
_res, _out, _ = _run([], ["del all", "done"])
check("del all ohne Phasen sagt es", "Keine Loop-Phasen" in _out)

# --- time ---
_res, _out, _ = _run(_phases("A"), ["time 1", "9:15", "done"])
check("time setzt die Startzeit", _res[0].scheduled_start == "09:15")
_list = _phases("A")
_list[0].scheduled_start = "10:00"
_res, _, _ = _run(_list, ["time 1", "", "done"])
check("Enter behält sie", _res[0].scheduled_start == "10:00")
_res, _, _ = _run(_list, ["time 1", "0", "done"])
check("'0' entfernt sie", _res[0].scheduled_start is None)
_res, _out, _ = _run(_phases("A"), ["time 4", "time x", "done"])
check("time ausserhalb oder mit Buchstaben wird gesagt",
      "Ungültige Nr" in _out and "Format: time <Nr>" in _out)

# --- show ---
_res, _out, _ = _run(_phases("Erste", "Zweite"), ["show", "done"])
check("show nennt alle Phasen", "Erste" in _out and "Zweite" in _out)
_res, _out, _ = _run([], ["s", "done"])
check("ohne Phasen sagt show das", "Keine Loop-Phasen" in _out)
