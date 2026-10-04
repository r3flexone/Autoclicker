"""Punkte-Menü (CTRL+ALT+P) und Zeitplan (CTRL+ALT+T), per Tastenfolge.

Geschrieben, BEVOR `handle_show` (Komplexität 35) und `handle_schedule` (15)
zerlegt wurden. Gefahren wird über die Handler selbst; gestellt sind Auswahl,
Eingabe, Maus, Speichern und alles, was ein Befehl nur weiterreicht (Runde,
Diagnose, Kalibrierung, Countdown) — gemessen wird, DASS es gerufen wird.
"""
import contextlib as _cl
import io as _io
import os as _os
import tempfile as _tmp

from ._harness import check, section

import autoclicker.diagnostics as _DIAG
import autoclicker.editors.import_export_editor as _IEE
import autoclicker.editors.reclick as _RC
import autoclicker.editors.sequence_editor as _SE
import autoclicker.handlers as _hnd
import autoclicker.runtime.debug as _DBG
from autoclicker.models import (
    AutoClickerState as _ST, ClickPoint as _CP, LoopPhase as _PHASE,
    Sequence as _SEQ, SequenceStep as _STEP,
)
from autoclicker.persistence import activate_sequence, save_sequence_file, sequence_file


def _points():
    return [_CP(10, 20, "Knopf", 1, color=(1, 2, 3), source="Aufnahme"),
            _CP(30, 40, "Zwei", 2)]


def _save(name: str) -> _SEQ:
    seq = _SEQ(name, points=_points(),
               loop_phases=[_PHASE("L", steps=[_STEP(point_id=1, delay_before=0)])])
    path = sequence_file(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    save_sequence_file(seq, path)
    return seq


class _Menu:
    """Ein Durchgang durch `handle_show` mit gestellter Umgebung."""

    def __init__(self, inputs, select=0, reclick=True):
        self.inputs, self.select, self.reclick = list(inputs), select, reclick
        self.calls, self.cursor, self.saved = [], [], 0
        self.state = _ST()
        self.output = ""

    def _record(self, name):
        return lambda *a, **k: self.calls.append((name,) + tuple(a[1:]))

    def _input(self, _prompt=""):
        value = self.inputs.pop(0) if self.inputs else "d"
        if isinstance(value, BaseException):
            raise value
        return value

    def _save_points(self, state):
        self.saved += 1
        return True

    def run(self):
        stubs = [
            (_hnd, "interactive_select", lambda *a, **k: self.select),
            (_hnd, "safe_input", self._input),
            (_hnd, "set_cursor_pos", lambda x, y: self.cursor.append((x, y))),
            (_hnd, "save_points", self._save_points),
            (_hnd, "print_points", lambda state: self.calls.append(("list",))),
            (_hnd, "handle_step_mode", lambda state: self.calls.append(("manual",))),
            (_hnd, "handle_debug_toggle", lambda state, which: self.calls.append(("debug", which))),
            (_DBG, "walk_points", lambda state: self.calls.append(("walk",))),
            (_RC, "start_reclick", lambda state: self.calls.append(("reclick",)) or self.reclick),
            (_DIAG, "check_setup", lambda state: self.calls.append(("check",)) or []),
            (_DIAG, "print_report", lambda report: None),
            (_IEE, "run_calibration", lambda state: self.calls.append(("fix",))),
        ]
        saved = [(m, n, getattr(m, n)) for m, n, _ in stubs]
        for module, name, value in stubs:
            setattr(module, name, value)
        buffer = _io.StringIO()
        try:
            with _cl.redirect_stdout(buffer):
                _hnd.handle_show(self.state)
        finally:
            for module, name, value in reversed(saved):
                setattr(module, name, value)
            self.output = buffer.getvalue()
        return self

    def names(self):
        return [call[0] for call in self.calls]


class _Schedule:
    """Ein Durchgang durch `handle_schedule` mit gestellter Eingabe und Startern."""

    def __init__(self, inputs, sequence=True, loader_finds=False, countdown=False):
        self.inputs, self.started, self.toggled, self.loader = list(inputs), [], 0, 0
        self.loader_finds = loader_finds
        self.state = _ST()
        self.state.countdown_active = countdown
        if sequence:
            with _cl.redirect_stdout(_io.StringIO()):
                activate_sequence(self.state, _SEQ("Plan", points=[]))
        self.output = ""

    def _input(self, _prompt=""):
        value = self.inputs.pop(0) if self.inputs else ""
        if isinstance(value, BaseException):
            raise value
        return value

    def _loader(self, state):
        self.loader += 1
        if self.loader_finds:
            activate_sequence(state, _SEQ("Geladen", points=[]))

    def _toggle(self, state, *a, **k):
        self.toggled += 1

    def run(self):
        stubs = [
            (_hnd, "safe_input", self._input),
            (_hnd, "_start_schedule", lambda state, text: self.started.append(text) or True),
            (_hnd, "handle_toggle", self._toggle),
            (_SE, "run_sequence_loader", self._loader),
        ]
        saved = [(m, n, getattr(m, n)) for m, n, _ in stubs]
        for module, name, value in stubs:
            setattr(module, name, value)
        buffer = _io.StringIO()
        try:
            with _cl.redirect_stdout(buffer):
                _hnd.handle_schedule(self.state)
        finally:
            for module, name, value in reversed(saved):
                setattr(module, name, value)
            self.output = buffer.getvalue()
        return self


_cwd = _os.getcwd()
_os.chdir(_tmp.mkdtemp(prefix="punkte_menue_"))
try:
    # =========================================================================
    section("Punkte-Menü: Sequenz wählen, schliessen")
    # =========================================================================
    _r = _Menu(["d"]).run()
    check("ohne Sequenzen gibt es nichts zu wählen",
          "Keine Sequenzen vorhanden" in _r.output and _r.state.active_sequence is None)

    with _cl.redirect_stdout(_io.StringIO()):
        _save("Erste")
        _save("Zweite")
    _r = _Menu(["d"], select=-1).run()
    check("abgebrochene Auswahl lädt nichts", _r.state.active_sequence is None)
    _r = _Menu(["d"], select=1).run()
    check("die gewählte Sequenz wird aktiv",
          _r.state.active_sequence is not None and _r.state.active_sequence.name == "Zweite")
    check("done schliesst mit Meldung", "Editor geschlossen" in _r.output)
    for _word in ("", "cancel", "D"):
        _r = _Menu([_word]).run()
        check(f"'{_word}' schliesst", "Editor geschlossen" in _r.output)

    # =========================================================================
    section("Punkte-Menü: weitergereichte Befehle")
    # =========================================================================
    _r = _Menu(["walk", "w", "d"]).run()
    check("walk / w", _r.names().count("walk") == 2)
    _r = _Menu(["reclick", "d"], reclick=True).run()
    check("reclick schliesst das Menü, wenn die Runde läuft",
          _r.names() == ["list", "reclick"] and "Editor geschlossen" not in _r.output)
    _r = _Menu(["k", "klick", "nachklicken", "d"], reclick=False).run()
    check("k/klick/nachklicken bleiben im Menü, wenn die Runde nicht startet",
          _r.names().count("reclick") == 3 and "Editor geschlossen" in _r.output)
    _r = _Menu(["manual", "m", "MANUAL", "d"]).run()
    check("manual / m schaltet den manuellen Modus", _r.names().count("manual") == 3)
    _r = _Menu(["manuell", "d"]).run()
    check("'manuell' (so steht es in der Hilfe) schaltet ihn auch",
          _r.names().count("manual") == 1 and "Ungültige Eingabe" not in _r.output)
    _r = _Menu(["log", "detail", "d"]).run()
    check("log / detail", [c for c in _r.calls if c[0] == "debug"] == [("debug", "log"), ("debug", "detail")])
    _r = _Menu(["check", "pruefen", "prüfen", "d"]).run()
    check("check / prüfen", _r.names().count("check") == 3)
    _r = _Menu(["fix", "kalib", "d"]).run()
    check("fix kalibriert und zeigt die Liste danach neu",
          _r.names() == ["list", "fix", "list", "fix", "list"])
    _r = _Menu(["list", "l", "d"]).run()
    check("list / l", _r.names().count("list") == 3)

    # =========================================================================
    section("Punkte-Menü: zeigen, löschen, umbenennen")
    # =========================================================================
    _r = _Menu(["show 1", "d"]).run()
    check("show <Nr> setzt die Maus und nennt Farbe und Herkunft",
          _r.cursor == [(10, 20)] and "Farbe:" in _r.output and "Herkunft: Aufnahme" in _r.output)
    _r = _Menu(["show 2", "d"]).run()
    check("show <Nr> ohne Farbe und Herkunft", _r.cursor == [(30, 40)]
          and "Farbe:" not in _r.output and "Herkunft" not in _r.output)
    _r = _Menu(["show x", "show 9", "d"]).run()
    check("show: Format und unbekannter Punkt",
          "Format: show <Nr>" in _r.output and "Punkt #9 nicht gefunden" in _r.output and not _r.cursor)
    _r = _Menu(["del 2", "d"]).run()
    check("del <Nr> löscht und speichert",
          [p.id for p in _r.state.points] == [1] and _r.saved == 1 and "Punkt #2 gelöscht" in _r.output)
    _r = _Menu(["del 9", "del x", "d"]).run()
    check("del: unbekannt und Format", len(_r.state.points) == 2 and _r.saved == 0
          and "Punkt #9 nicht gefunden" in _r.output and "Format: del <ID>" in _r.output)
    _r = _Menu(["del 1", "del 2", "list"]).run()
    check("der letzte gelöschte Punkt schliesst das Menü",
          _r.state.points == [] and "Keine Punkte mehr vorhanden" in _r.output
          and _r.names() == ["list"])
    _r = _Menu(["1", "Neuer Name", "d"]).run()
    check("<Nr>: Maus hin, dann umbenennen",
          _r.cursor == [(10, 20)] and _r.state.points[0].name == "Neuer Name" and _r.saved == 1)
    _r = _Menu(["1", "", "1", "q", "d"]).run()
    check("<Nr>: leer oder Abbruch behält den Namen",
          _r.state.points[0].name == "Knopf" and _r.saved == 0
          and _r.output.count("Name 'Knopf' beibehalten") == 2)
    _r = _Menu(["2 Ganz neu", "d"]).run()
    check("<Nr> <Name> benennt direkt um", _r.state.points[1].name == "Ganz neu" and _r.saved == 1
          and not _r.cursor)
    _r = _Menu(["9", "abc", "d"]).run()
    check("unbekannter Punkt und Unsinn",
          "Punkt #9 nicht gefunden" in _r.output and "Ungültige Eingabe" in _r.output)

    # =========================================================================
    section("Zeitplan: vorher, Abbruch, Start")
    # =========================================================================
    _r = _Schedule(["+30s"], countdown=True).run()
    check("ein laufender Countdown verhindert einen zweiten",
          "bereits ein Countdown" in _r.output and _r.started == [])
    _r = _Schedule(["+30s"], sequence=False).run()
    check("ohne Sequenz öffnet sich das Lade-Menü — bleibt es leer, ist Schluss",
          _r.loader == 1 and _r.started == [] and "ZEITPLAN" not in _r.output)
    _r = _Schedule(["+30s", ""], sequence=False, loader_finds=True).run()
    check("lädt es eine Sequenz, geht es mit ihr weiter",
          _r.started == ["+30s"] and "Aktive Sequenz:" in _r.output and "Geladen" in _r.output)
    for _word in ("", "cancel"):
        _r = _Schedule([_word]).run()
        check(f"'{_word}' als Zeit bricht ab", "[ABBRUCH]" in _r.output and _r.started == [])
    _r = _Schedule(["xyz"]).run()
    check("eine Zeit ohne Einheit wird gesagt", "Einheit fehlt" in _r.output and _r.started == [])
    _r = _Schedule(["0s"]).run()
    check("unter einer Sekunde startet sofort", _r.toggled == 1 and _r.started == [])
    _r = _Schedule(["+30s", ""]).run()
    check("relative Zeit: Wartezeit ab Bestätigung, dann Countdown",
          "(ab Enter-Bestätigung)" in _r.output and _r.started == ["+30s"])
    _r = _Schedule(["14:30", ""]).run()
    check("Uhrzeit: mit Zielzeit", "Zielzeit:" in _r.output and _r.started == ["14:30"])
    _r = _Schedule(["+30s", "cancel"]).run()
    check("Abbruch bei der Bestätigung", "[ABBRUCH]" in _r.output and _r.started == [])
    _r = _Schedule([KeyboardInterrupt()]).run()
    check("STRG+C bricht ab", "[ABBRUCH]" in _r.output and _r.started == [])
finally:
    _os.chdir(_cwd)
