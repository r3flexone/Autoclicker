"""Das Ende einer Aufnahme (`stop_recording` → `_build_recording`), per Ereignisfolge.

Geschrieben, BEVOR `_build_recording` (Komplexität 35) zerlegt wurde. Gefahren
wird über `stop_recording`, wie es der Hotkey und das Studio tun; gestellt sind
nur die Hooks, die Konsoleneingabe und — für einen Fall — das Speichern bzw.
die Einfüge-Aufnahme.
"""
import contextlib as _cl
import io as _io
import os as _os
import tempfile as _tmp

from ._harness import check, section

import autoclicker.editors.sequence_recorder as _rec
import autoclicker.utils as _utils
from autoclicker.models import (
    AutoClickerState as _ST, RecordEvent as _RE,
    REC_CLICK as _CLICK, REC_KEY as _KEY, REC_PHASE as _PHASE, REC_REGION as _REGION,
    REC_SCREENSHOT as _SHOT, REC_WAIT_COLOR as _WAIT,
)
from autoclicker.persistence import load_sequence_file, sequence_file


def _click(t, x=10, y=20, color=(1, 2, 3)):
    return _RE(_CLICK, t, x, y, color)


class _Stop:
    """Eine gestoppte Aufnahme mit gestellter Eingabe."""

    def __init__(self, events, inputs=(), right_clicks=0, ui=None, insert=None, save_ok=True):
        self.inputs = list(inputs)
        self.save_ok = save_ok
        self.inserted = []
        self.state = _ST()
        self.state.recording_active = True
        self.state.recording_events = list(events)
        self.state.recording_right_clicks = right_clicks
        if ui:
            (self.state.recording_ui_name, self.state.recording_ui_cycles,
             self.state.recording_ui_description) = ui
        self.state.recording_insert = insert
        self.output = ""

    def _input(self, _prompt=""):
        value = self.inputs.pop(0) if self.inputs else ""
        if isinstance(value, BaseException):
            raise value
        return value

    def run(self):
        stubs = [
            (_rec, "remove_mouse_hook", lambda: None),
            (_rec, "remove_keyboard_hook", lambda: None),
            (_rec, "safe_input", self._input),
            (_utils, "safe_input", self._input),
            (_rec, "_finish_insert_recording",
             lambda state, events, target: self.inserted.append((len(events), target)) or "eingefügt"),
        ]
        if not self.save_ok:
            stubs.append((_rec, "save_sequence_file", lambda seq, path: False))
        saved = [(m, n, getattr(m, n)) for m, n, _ in stubs]
        for module, name, value in stubs:
            setattr(module, name, value)
        buffer = _io.StringIO()
        try:
            with _cl.redirect_stdout(buffer):
                self.result = _rec.stop_recording(self.state)
        finally:
            for module, name, value in reversed(saved):
                setattr(module, name, value)
            self.output = buffer.getvalue()
        return self

    def saved(self):
        return load_sequence_file(sequence_file(self.result)) if self.result else None


_cwd = _os.getcwd()
_os.chdir(_tmp.mkdtemp(prefix="aufnahme_ende_"))
try:
    # =========================================================================
    section("Aufnahme-Ende: nichts Verwertbares")
    # =========================================================================
    _r = _Stop([], right_clicks=2).run()
    check("nur Rechtsklicks: gesagt, und nichts aufgezeichnet",
          _r.result is None and "2 Rechtsklick(s) nicht aufgezeichnet" in _r.output
          and "nichts aufgezeichnet" in _r.output)
    check("die Rechtsklick-Meldung steht VOR der Auswertung",
          _r.output.index("Rechtsklick") < _r.output.index("nichts aufgezeichnet"))
    _r = _Stop([_RE(_REGION, 1.0, 5, 5)]).run()
    check("eine halbe Bereichs-Ecke wird verworfen und gesagt",
          _r.result is None and "Einzelne Bereichs-Ecke verworfen" in _r.output
          and "Nichts Verwertbares" in _r.output)
    _r = _Stop([_RE(_WAIT, 1.0)]).run()
    check("ein Warte-Marker ohne Klick danach wird verworfen",
          _r.result is None and "1 Warte-Marker verworfen" in _r.output)
    _r = _Stop([_RE(_PHASE, 1.0)]).run()
    check("eine Phasengrenze allein ist nichts", _r.result is None and "Nichts Verwertbares" in _r.output)

    # =========================================================================
    section("Aufnahme-Ende: Konsolen-Weg")
    # =========================================================================
    _r = _Stop([_click(1.0), _click(1.05, 11, 21), _RE(_KEY, 3.0, key="enter")],
               inputs=["Lauf A", "3", "Eine Beschreibung"]).run()
    _seq = _r.saved()
    check("Name, Zyklen und Beschreibung aus der Konsole",
          _r.result == "Lauf A" and _seq is not None and _seq.total_cycles == 3
          and _seq.description == "Eine Beschreibung")
    check("die Liste zeigt sofort / +Sekunden und markiert den schnellen Klick",
          "sofort" in _r.output and "⚡" in _r.output and "1 sehr schnelle(r) Klick(s)" in _r.output)
    check("die gespeicherte Sequenz ist die aktive",
          _r.state.active_sequence is not None and _r.state.active_sequence.name == "Lauf A")
    check("Abschlussmeldung nennt Schritte, Zyklen und Punkte",
          'Sequenz "Lauf A" gespeichert' in _r.output and "3 Schritte  |  Zyklen: 3" in _r.output
          and "Punkt(e) in dieser Sequenz gespeichert" in _r.output)
    _r = _Stop([_click(1.0)], inputs=["", "x", ""]).run()
    check("ohne Namen: 'Aufnahme <Uhrzeit>', unlesbare Zyklen = unendlich",
          _r.result is not None and _r.result.startswith("Aufnahme ")
          and "ungültig — nutze unendlich" in _r.output and "Zyklen: unendlich" in _r.output
          and _r.saved().total_cycles == 0)
    _r = _Stop([_click(1.0)], inputs=["cancel"]).run()
    check("cancel beim Namen verwirft", _r.result is None and "[VERWORFEN]" in _r.output)
    _r = _Stop([_click(1.0)], inputs=[KeyboardInterrupt()]).run()
    check("STRG+C beim Namen verwirft", _r.result is None and "[VERWORFEN]" in _r.output)
    _r = _Stop([_click(1.0)], inputs=["Lauf B", EOFError(), "q"]).run()
    check("EOF bei den Zyklen = unendlich, Abbruch bei der Beschreibung = keine",
          _r.result == "Lauf B" and _r.saved().total_cycles == 0 and _r.saved().description == "")

    # =========================================================================
    section("Aufnahme-Ende: Phasen, Marker, Screenshot")
    # =========================================================================
    _r = _Stop([_click(1.0), _RE(_PHASE, 2.0), _click(3.0, 50, 60)], inputs=["Phasen"]).run()
    _seq = _r.saved()
    check("eine Phasengrenze teilt in Loop und Loop 2",
          [lp.name for lp in _seq.loop_phases] == ["Loop", "Loop 2"]
          and [len(lp.steps) for lp in _seq.loop_phases] == [1, 1])
    check("die Liste zeigt die Grenzen",
          "┌─ Loop" in _r.output and "├─ Loop 2" in _r.output
          and "1 Loop  |  1 Loop 2" in _r.output)
    _r = _Stop([_RE(_WAIT, 1.0), _click(5.0)], inputs=["Marker"]).run()
    check("ein Warte-Marker vor dem Klick: 'wartet auf' statt Wartezeit, Hinweis auf colorgone",
          "wartet auf" in _r.output and "'colorgone <Nr>'" in _r.output
          and _r.saved().loop_phases[0].steps[0].wait_condition is not None)
    _r = _Stop([_RE(_SHOT, 1.0)], inputs=["Bild"]).run()
    check("ein Vollbild-Screenshot bekommt den Hinweis aufs Eingrenzen",
          _r.result == "Bild" and "'screenshot x1 y1 x2 y2'" in _r.output)

    # =========================================================================
    section("Aufnahme-Ende: Studio, Einfügen, Speicherfehler")
    # =========================================================================
    _r = _Stop([_click(1.0)], inputs=[AssertionError("das Studio fragt nichts")],
               ui=("Aus dem Studio", 7, "Notiz")).run()
    _seq = _r.saved()
    check("Studio-Aufnahme: Angaben vom Start, keine Konsolenfrage",
          _r.result == "Aus dem Studio" and _seq.total_cycles == 7 and _seq.description == "Notiz")
    _r = _Stop([_click(1.0), _RE(_KEY, 2.0, key="a")], insert={"file": "x"}).run()
    check("Einfüge-Aufnahme: keine neue Sequenz, die Ereignisse gehen ans Einfügen",
          _r.result == "eingefügt" and _r.inserted == [(2, {"file": "x"})])
    _r = _Stop([_click(1.0)], inputs=["Kaputt"], save_ok=False).run()
    check("scheitert das Speichern, wird es gesagt",
          _r.result is None and "konnte nicht gespeichert werden" in _r.output)
finally:
    _os.chdir(_cwd)
