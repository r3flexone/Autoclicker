"""Einstieg mitten in der Sequenz: einen Block waehlen und ab dort starten.

Bis dahin gab es nur „von vorn" und „diesen einen Block testen". Wer den
dritten Loop-Block einer langen Aufnahme pruefen wollte, spielte INIT und die
zwei Bloecke davor jedes Mal mit. `state.start_from` = `(Art, Phasen-Index,
Block)` gilt fuer genau einen Start und wird vom Worker verbraucht: alles
davor wird uebersprungen (bei einem Loop-Block auch INIT), ab dort laeuft die
Sequenz normal — der zweite Zyklus wieder von vorn, ein Neustart bei INIT.
"""
import contextlib as _cl
import io as _io
import os as _os
import shutil as _sh
import tempfile as _tmp
import threading as _th
import time as _time
from pathlib import Path as _P

from ._harness import check, section, studio_web_source
from autoclicker.models import (
    AutoClickerState as _ST,
    LoopPhase as _PHASE,
    Sequence as _SEQ,
    SequenceStep as _STEP,
)
import autoclicker.runtime.worker as _W
import autoclicker.runtime.status as _status
import autoclicker.handlers as _hnd
import autoclicker.mailbox as _mb
from autoclicker.persistence import save_sequence_file, sequence_file
from autoclicker.editors.sequence_studio.bridge import StudioBridge as _SB


def _sequence(cycles: int = 2) -> _SEQ:
    return _SEQ("einstieg", total_cycles=cycles,
                init_steps=[_STEP(key_press="a"), _STEP(key_press="b")],
                loop_phases=[
                    _PHASE("L1", repeat=2, steps=[_STEP(key_press="c"), _STEP(key_press="d"),
                                                  _STEP(key_press="e")]),
                    _PHASE("L2", steps=[_STEP(key_press="f")])],
                end_steps=[_STEP(key_press="g"), _STEP(key_press="h")])


_executed: list = []
_orig_execute = _W.execute_step
_W.execute_step = lambda state, step, n, total, phase: _executed.append((phase, n)) or True


def _run(seq, start_from):
    """Ein kompletter Lauf (Hauptschleife + END) mit Einstieg, ohne Worker-Thread."""
    _executed.clear()
    _status._state.clear()
    st = _ST()
    st.active_sequence = seq
    st.is_running = True
    st.start_time = _time.time()
    buf = _io.StringIO()
    with _cl.redirect_stdout(buf):
        cycles = _W._run_main_loop(st, seq, {}, _th.Lock(), False, start_from)
        _W._run_end_phase(st, seq, start_from)
    return cycles, list(_executed), buf.getvalue()


try:
    # =========================================================================
    section("Einstieg im Loop: INIT und die Bloecke davor fallen weg — einmal")
    # =========================================================================
    _cycles, _ran, _out = _run(_sequence(), ("loop", 0, 1))
    check("INIT laeuft nicht, wenn der Einstieg in einer Loop-Phase liegt",
          not any(p == "INIT" for p, _ in _ran))
    check("der erste Durchlauf der Einstiegsphase beginnt beim gewaehlten Block",
          _ran[:2] == [("L1 #1/2", 2), ("L1 #1/2", 3)])
    check("der zweite Durchlauf derselben Phase ist schon wieder vollstaendig",
          _ran[2:5] == [("L1 #2/2", 1), ("L1 #2/2", 2), ("L1 #2/2", 3)])
    check("die Phase danach laeuft normal", _ran[5] == ("L2 #1/1", 1))
    _second = _ran[6:]
    check("der zweite Zyklus faengt wieder bei Block 1 an",
          _second[:1] == [("L1 #1/2", 1)] and _cycles == 2)
    check("END laeuft danach vollstaendig", _ran[-2:] == [("END", 1), ("END", 2)])

    # =========================================================================
    section("Einstieg in INIT und in END")
    # =========================================================================
    _cycles, _ran, _out = _run(_sequence(cycles=1), ("init", -1, 1))
    check("in INIT wird nur der Block davor uebersprungen",
          _ran[:2] == [("INIT", 2), ("L1 #1/2", 1)])
    _cycles, _ran, _out = _run(_sequence(), ("end", -1, 1))
    check("ein Einstieg in END laesst INIT und alle Zyklen aus",
          _cycles == 0 and _ran == [("END", 2)])

    # =========================================================================
    section("Der Einstieg wird verbraucht und geprueft")
    # =========================================================================
    _st = _ST()
    _st.start_from = ("loop", 0, 2)
    with _cl.redirect_stdout(_io.StringIO()):
        _taken = _W._take_start_from(_st, _sequence())
    check("der Worker nimmt den Einstieg mit und loescht ihn im State",
          _taken == ("loop", 0, 2) and _st.start_from is None)
    _st.start_from = ("loop", 0, 99)
    _buf = _io.StringIO()
    with _cl.redirect_stdout(_buf):
        _taken = _W._take_start_from(_st, _sequence())
    check("ein Einstieg ins Leere wird gemeldet und der Lauf beginnt von vorn",
          _taken is None and "existiert nicht mehr" in _buf.getvalue())
    check("die Beschriftung nennt Phase und Block, wie sie im Studio stehen",
          _W._start_from_label(_sequence(), ("loop", 1, 0)) == "Loop 'L2' · Block 1"
          and _W._start_from_label(_sequence(), ("end", -1, 1)) == "END · Block 2")

    # Eine zeitgesteuerte Einstiegsphase laeuft JETZT — wer dort einsteigt,
    # will nicht bis zur Uhrzeit warten.
    _timed = _SEQ("t", total_cycles=1, loop_phases=[
        _PHASE("frueh", steps=[_STEP(key_press="a")], scheduled_start="23:59"),
        _PHASE("spaet", steps=[_STEP(key_press="b")])])
    _cycles, _ran, _out = _run(_timed, ("loop", 0, 0))
    check("die zeitgesteuerte Einstiegsphase laeuft ohne ihren Termin",
          _ran[:1] == [("frueh #1/1", 1)])

    # =========================================================================
    section("Briefkasten und Studio: 'start_from' vom gewaehlten Block")
    # =========================================================================
    _sandbox = _tmp.mkdtemp(prefix="einstieg_")
    _cwd = _os.getcwd()
    _os.chdir(_sandbox)
    try:
        _seq = _sequence()
        _path = sequence_file(_seq.name)
        _path.parent.mkdir(parents=True, exist_ok=True)
        save_sequence_file(_seq, _path)

        # Der Handler setzt den Einstieg und startet auf dem normalen Weg.
        _started: list = []
        _orig_toggle = _hnd.handle_toggle

        def _fake_toggle(state, from_studio=False):
            state.is_running = True
            _started.append(from_studio)

        _hnd.handle_toggle = _fake_toggle
        try:
            _st = _ST()
            with _cl.redirect_stdout(_io.StringIO()):
                _hnd.command_start_from(_st, {"file": str(_path), "phase": "loop",
                                              "phase_index": 0, "block": 1})
            check("command_start_from startet ueber denselben Weg wie 'start'",
                  _started == [True] and _st.active_sequence is not None)
            check("und hinterlaesst dem Worker den Einstieg",
                  _st.start_from == ("loop", 0, 1))

            _st = _ST()
            _buf = _io.StringIO()
            with _cl.redirect_stdout(_buf):
                _hnd.command_start_from(_st, {"file": str(_path), "phase": "loop",
                                              "phase_index": 0, "block": 7})
            check("ein Block, den es nicht gibt, startet nichts",
                  not _st.is_running and _st.start_from is None
                  and "existiert nicht mehr" in _buf.getvalue())

            # Ein abgelehnter Start darf den Einstieg nicht liegen lassen —
            # sonst spraenge der naechste Hotkey-Start mitten in die Sequenz.
            _hnd.handle_toggle = lambda state, from_studio=False: None
            _st = _ST()
            with _cl.redirect_stdout(_io.StringIO()):
                _hnd.command_start_from(_st, {"file": str(_path), "phase": "init",
                                              "phase_index": -1, "block": 0})
            check("wird der Start abgelehnt, ist der Einstieg wieder weg",
                  _st.start_from is None)
        finally:
            _hnd.handle_toggle = _orig_toggle

        # Das Studio schickt Datei und Position — nicht einen gebauten Schritt.
        _mb.COMMAND_PATH = _P("command.json")
        _b = _SB(_seq, _path, "sequences")
        _loop = next(i for i, ln in enumerate(_b.board.lanes) if ln.kind == "loop")
        _b.select({"phase": _loop, "row": 2})
        _res = _b.block_start()
        _job = _mb.fetch_command()
        check("block_start legt 'start_from' mit Datei und Position ab",
              _job and _job["command"] == "start_from"
              and _job["arguments"]["phase"] == "loop"
              and _job["arguments"]["phase_index"] == 0
              and _job["arguments"]["block"] == 2
              and _job["arguments"]["file"] == str(_path))
        check("und sagt, ab wo — mit der Nummer, die auf der Karte steht",
              "Block 3" in _res["status"]["text"] and "L1" in _res["status"]["text"])
        _b.select({"phase": _loop, "row": 0})
        _b.select({"phase": _loop, "row": 1, "mode": "add"})
        _res = _b.block_start()
        check("ohne eindeutige Auswahl wird nicht gestartet",
              _res["status"]["kind"] == "warn" and _mb.fetch_command() is None)
        check("'start_from' steht in der Befehlsliste beider Seiten",
              "start_from" in _SB.ALL_COMMANDS and "start_from" in _hnd.COMMANDS)
    finally:
        _os.chdir(_cwd)
        _sh.rmtree(_sandbox, ignore_errors=True)

    _web = studio_web_source()
    check("der Inspektor hat den Knopf 'Ab hier starten'",
          'call("block_start")' in _web and "Ab hier starten" in _web)
    check("und der Live-Run zeigt, wo eingestiegen wurde",
          "z.started_from" in _web)
finally:
    _W.execute_step = _orig_execute
    _status._state.clear()
