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

    # =========================================================================
    section("Sequenz-Editor: eine neue Sequenz fasst die aktive nicht an")
    # =========================================================================
    # Bei aktiver Sequenz A eine neue B anlegen und darin `learn` benutzen:
    # der Punkt landete in A's Liste, und `save_points` schrieb A — also die
    # falsche Datei. B bekam beim Speichern A's ganzen Bestand, auch Punkte,
    # die keiner ihrer Schritte benutzt. Im Studio ist dasselbe bei `new()`
    # schon behoben; der Konsolen-Editor ist der zweite Weg zur neuen Sequenz.
    # Gespeichert wird hier wirklich (in den Temp-Ordner), denn um die Datei geht es.
    import autoclicker.editors.sequence_editor.steps as _PS
    from autoclicker.persistence import (
        load_sequence_file as _load_seq, save_sequence_file as _save_seq,
        sequence_file as _seq_file,
    )

    def _learn_and_click(state, steps, label):
        """Der echte Phasen-Editor: ein `learn`, dann ein Klick auf Punkt 1."""
        editor = _PS._PhaseEditor(state, list(steps), label)
        originals = (_PS.safe_input, _PS.get_cursor_pos)
        _PS.safe_input, _PS.get_cursor_pos = (lambda *a, **k: ""), (lambda: (9, 9))
        try:
            with _cl.redirect_stdout(_io.StringIO()):
                editor._handle_learn("learn Gelernt")
        finally:
            _PS.safe_input, _PS.get_cursor_pos = originals
        editor.add_step(_step())
        return editor.steps

    def _new_beside_a(name, phases, discard=False):
        """A ist aktiv und gespeichert; der Editor legt B an. `phases` antwortet
        der Reihe nach für INIT, LOOP, END."""
        seq_a = _SEQ("A-Bestand", points=[_CP(1, 2, "Eins", 1), _CP(3, 4, "Zwei", 2)],
                     loop_phases=[_LP("L", [_step()])])
        _save_seq(seq_a, _seq_file("A-Bestand"))
        state = _ST()
        with _cl.redirect_stdout(_io.StringIO()):
            activate_sequence(state, seq_a)
        answers, typed = list(phases), [name, ""]
        stubs = [(_ed, "edit_phase", lambda s, st, lb: answers.pop(0)(s, st, lb)),
                 (_ed, "edit_loop_phases", lambda s, ph: answers.pop(0)(s, ph, "LOOP")),
                 (_ed, "safe_input", lambda *a, **k: typed.pop(0) if typed else ""),
                 (_ed, "confirm_new_sequence_name", lambda n: n),
                 (_ed, "confirm", lambda *a, **k: discard)]
        saved = [(m, n, getattr(m, n)) for m, n, _ in stubs]
        for module, attr, value in stubs:
            setattr(module, attr, value)
        try:
            with _cl.redirect_stdout(_io.StringIO()):
                _ed.edit_sequence(state, None)
        finally:
            for module, attr, value in reversed(saved):
                setattr(module, attr, value)
        return state, seq_a

    def _empty(*_a):
        return []

    def _cancelled(*_a):
        return None

    _state, _a = _new_beside_a("B-Neu", [_learn_and_click, _empty, _empty])
    _a_disk = _load_seq(_seq_file("A-Bestand"))
    _b_disk = _load_seq(_seq_file("B-Neu"))
    check("A auf der Platte behält genau seine Punkte",
          _a_disk is not None and [p.id for p in _a_disk.points] == [1, 2])
    check("A im Speicher ebenso", [p.id for p in _a.points] == [1, 2])
    check("B behält nur die benutzten übernommenen Punkte und den gelernten",
          _b_disk is not None and sorted(p.name for p in _b_disk.points) == ["Eins", "Gelernt"])
    check("B ist danach die aktive Sequenz", _state.active_sequence.name == "B-Neu")

    _state, _a = _new_beside_a("B-Weg", [_learn_and_click, _cancelled], discard=True)
    check("nach dem Abbruch ist A wieder aktiv, mit seinen Punkten",
          _state.active_sequence is _a and [p.id for p in _state.points] == [1, 2])
    check("B wurde nicht angelegt", not _seq_file("B-Weg").exists())
    check("und A auf der Platte ist unverändert",
          [p.id for p in _load_seq(_seq_file("A-Bestand")).points] == [1, 2])
finally:
    _os.chdir(_cwd)
