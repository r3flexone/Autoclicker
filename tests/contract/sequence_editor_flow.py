"""Der Sequenz-Editor im Ganzen (`edit_sequence`), per Tastenfolge.

Geschrieben, BEVOR `edit_sequence` (Komplexität 17) und
`_print_pre_save_summary` (14) zerlegt wurden. Die Phasen-Editoren darunter
sind gestellt — sie haben ihre eigenen Prüfungen (`phase_editor`,
`loop_phase_editor`); hier geht es um den Ablauf dazwischen: Name,
Beschreibung, Abbruch je Phase, Zyklen, Zusammenfassung, Speichern.
"""
import contextlib as _cl
import io as _io
import os as _os
import tempfile as _tmp

from ._harness import check, section

import autoclicker.editors.sequence_editor.editor as _ed
from autoclicker.models import (
    AutoClickerState as _ST, ClickPoint as _CP, LoopPhase as _LP,
    Sequence as _SEQ, SequenceStep as _STEP, WaitCondition as _WC,
)
from autoclicker.persistence import activate_sequence


def _step():
    return _STEP(point_id=1, delay_before=0)


class _Edit:
    """Ein Durchgang durch `edit_sequence` mit gestellten Phasen-Editoren.

    `phases` ist eine Liste von Antworten, der Reihe nach für INIT, LOOP, END;
    `None` = abgebrochen.
    """

    def __init__(self, inputs=(), phases=(None,), confirms=(), points=True,
                 existing=None, name_result="keep", save_ok=True):
        self.inputs, self.phases, self.confirms = list(inputs), list(phases), list(confirms)
        self.name_result, self.save_ok = name_result, save_ok
        self.saved, self.asked_cycles = 0, 0
        self.existing = existing
        self.state = _ST()
        if points:
            with _cl.redirect_stdout(_io.StringIO()):
                activate_sequence(self.state, _SEQ("Basis", points=[_CP(1, 2, "P1", 1)]))
        self.output = ""

    def _next_phase(self, *a):
        return self.phases.pop(0) if self.phases else None

    def _input(self, _prompt=""):
        if "Anzahl Zyklen" in _prompt:
            self.asked_cycles += 1
        return self.inputs.pop(0) if self.inputs else ""

    def _confirm_name(self, name):
        return name if self.name_result == "keep" else self.name_result

    def _save_points(self, state):
        self.saved += 1
        return self.save_ok

    def run(self):
        stubs = [
            (_ed, "safe_input", self._input),
            (_ed, "confirm", lambda *a, **k: self.confirms.pop(0) if self.confirms else False),
            (_ed, "edit_phase", lambda state, steps, label: self._next_phase()),
            (_ed, "edit_loop_phases", lambda state, phases: self._next_phase()),
            (_ed, "confirm_new_sequence_name", self._confirm_name),
            (_ed, "save_points", self._save_points),
        ]
        saved = [(m, n, getattr(m, n)) for m, n, _ in stubs]
        for module, name, value in stubs:
            setattr(module, name, value)
        buffer = _io.StringIO()
        try:
            with _cl.redirect_stdout(buffer):
                _ed.edit_sequence(self.state, self.existing)
        finally:
            for module, name, value in reversed(saved):
                setattr(module, name, value)
            self.output = buffer.getvalue()
        return self

    def active(self):
        return self.state.active_sequence


_cwd = _os.getcwd()
_os.chdir(_tmp.mkdtemp(prefix="sequenz_editor_"))
try:
    # =========================================================================
    section("Sequenz-Editor: neue Sequenz")
    # =========================================================================
    _r = _Edit(["Neu"], points=False).run()
    check("ohne Punkte geht es nicht weiter",
          "Erst Punkte aufnehmen" in _r.output and _r.saved == 0)
    _r = _Edit(["Neu"], name_result=None).run()
    check("ein abgebrochener Name beendet den Editor",
          "Editor beendet" in _r.output and _r.saved == 0)
    _r = _Edit(["Neu", "Meine Notiz", "3"],
               phases=[[_step()], [_LP("L", [_step()], 2)], []]).run()
    check("neu: alle drei Phasen, Zyklen und Beschreibung landen in der Sequenz",
          _r.saved == 1 and _r.active().name == "Neu" and _r.active().total_cycles == 3
          and _r.active().description == "Meine Notiz" and len(_r.active().init_steps) == 1
          and [lp.name for lp in _r.active().loop_phases] == ["L"])
    check("und bringt die Punkte mit", [p.id for p in _r.active().points] == [1])
    check("Zusammenfassung vorher: neue Sequenz mit Phasen und Zyklen",
          "Neue Sequenz: 'Neu'" in _r.output and "Init: 1 Schritte (einmalig)" in _r.output
          and "L: 1 Schritte x2" in _r.output and "Zyklen: 3x" in _r.output)
    check("Meldung nachher", "[ERFOLG]" in _r.output and "Gesamt: 3x wiederholen" in _r.output)
    _r = _Edit(["", ""], phases=[[], [], []]).run()
    check("ohne Namen: 'Neue Sequenz'; ohne Loop-Phasen wird nicht nach Zyklen gefragt",
          _r.active().name == "Neue Sequenz" and _r.asked_cycles == 0
          and "Zyklen: 1x" in _r.output and "Gesamt: Einmal durchlaufen" in _r.output)
    _r = _Edit(["Unendlich", "", "0"], phases=[[], [_LP("L", [_step()])], []]).run()
    check("0 Zyklen = unendlich", _r.active().total_cycles == 0
          and "Zyklen: Unendlich" in _r.output and "Gesamt: Unendlich wiederholen" in _r.output)
    _r = _Edit(["Minus", "", "-3"], phases=[[], [_LP("L", [_step()])], []]).run()
    check("negative Zyklen werden 0", _r.active().total_cycles == 0)
    _r = _Edit(["Tippfehler", "", "x"], phases=[[], [_LP("L", [_step()])], []]).run()
    check("unlesbare Zyklen behalten den bisherigen Wert",
          _r.active().total_cycles == 1 and "Ungültige Eingabe, behalte 1" in _r.output)
    _trig = _STEP(point_id=1, delay_before=0, wait_condition=_WC(point_id=1, pixel=(1, 2), color=(3, 4, 5)))
    _r = _Edit(["Trigger", ""], phases=[[_trig], [], [_step()]]).run()
    check("die Meldung nachher zählt Farb-Trigger und END",
          "Farb-Trigger: 1 Schritt(e)" in _r.output and "End: 1 Schritte (einmal am Ende)" in _r.output)

    # =========================================================================
    section("Sequenz-Editor: Abbruch je Phase")
    # =========================================================================
    _r = _Edit(["Leer", ""], phases=[None]).run()
    check("Abbruch in INIT ohne Schritte: nichts zu fragen, nicht gespeichert",
          "Sequenz nicht gespeichert" in _r.output and _r.saved == 0)
    _r = _Edit(["Weiter", ""], phases=[[_step()], None, []], confirms=[False]).run()
    check("Abbruch in LOOP, Verwerfen verneint: es geht weiter und wird gespeichert",
          _r.saved == 1 and len(_r.active().init_steps) == 1)
    _r = _Edit(["Weg", ""], phases=[[_step()], None], confirms=[True]).run()
    check("Abbruch in LOOP, Verwerfen bejaht: nicht gespeichert",
          _r.saved == 0 and "Sequenz nicht gespeichert" in _r.output)
    _r = _Edit(["EndeWeg", ""], phases=[[_step()], [], None], confirms=[True]).run()
    check("Abbruch in END, Verwerfen bejaht: nicht gespeichert", _r.saved == 0)

    # =========================================================================
    section("Sequenz-Editor: bestehende Sequenz")
    # =========================================================================
    def _existing():
        return _SEQ("Alt", points=[_CP(5, 6, "Eigen", 4)], description="Alte Notiz",
                    init_steps=[], loop_phases=[_LP("L", [_step()], 1)], end_steps=[],
                    total_cycles=2)

    _r = _Edit([""], phases=[[], [_LP("L", [_step()], 1)], []], existing=_existing(),
               points=False).run()
    check("bestehend: ihre eigenen Punkte gelten, Beschreibung bleibt bei Enter",
          _r.saved == 1 and [p.id for p in _r.active().points] == [4]
          and _r.active().description == "Alte Notiz")
    check("ohne Änderung steht 'Keine Änderungen' da", "Keine Änderungen" in _r.output)
    _r = _Edit(["-"], phases=[[], [_LP("L", [_step()], 1)], []], existing=_existing()).run()
    check("'-' löscht die Beschreibung", _r.active().description == "")
    _r = _Edit(["Neue Notiz", "5"],
               phases=[[_step()], [_LP("L", [_step(), _step()], 1), _LP("M", [_step()], 3)],
                       [_step()]],
               existing=_existing()).run()
    check("eine neue Beschreibung ersetzt die alte", _r.active().description == "Neue Notiz")
    check("die Änderungen werden einzeln genannt",
          "Init: 0 → 1 Schritte" in _r.output and "Loop-Phasen: 1 → 2" in _r.output
          and "L: 1x1 → 2x1" in _r.output and "NEU" in _r.output and "M" in _r.output
          and "End: 0 → 1 Schritte" in _r.output and "Zyklen: 2 → 5" in _r.output)
    _r = _Edit([""], phases=[[], [_LP("L", [_step()], 1)], []], existing=_existing(),
               save_ok=False).run()
    check("scheitert das Speichern, steht kein [ERFOLG] da",
          "NICHT auf Platte" in _r.output and "[ERFOLG]" not in _r.output)
finally:
    _os.chdir(_cwd)
