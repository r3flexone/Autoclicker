"""Zeitgesteuerte Phasen: ein Zyklus ohne Schritt ist kein Zyklus.

Eine Sequenz, deren Phasen ALLE auf eine Uhrzeit warten („täglich um 07:00"),
lief vorher in einer Schleife ohne einen einzigen Schritt — gemessen 133
Umläufe in einer halben Sekunde, jeder mit einer Statusdatei — und mit
`total_cycles=5` war sie vorbei, bevor die Uhrzeit je erreicht wurde. Dasselbe
bei einer Sequenz, deren Phasen leer sind (das Studio legt genau so eine an).

Die Regel jetzt: läuft in einem Zyklus keine Phase, zählt er nicht — und der
Worker schläft bis zum nächsten Termin (oder beendet den Lauf, wenn es gar
keinen Zeitplan gibt, statt endlos zu drehen).
"""
import io as _io
import contextlib as _cl
import os as _os
import shutil as _sh
import tempfile as _tmp
import threading as _th
import time as _time
from datetime import datetime as _dt

from ._harness import check, section
from autoclicker.models import (
    AutoClickerState as _ST,
    LoopPhase as _PHASE,
    Sequence as _SEQ,
    SequenceStep as _STEP,
)
import autoclicker.runtime.worker as _W
import autoclicker.runtime.status as _status


# =============================================================================
section("Zeitplan: die naechste faellige Phase")
# =============================================================================

_now = _dt(2026, 1, 1, 12, 0, 0)
_seq_t = _SEQ("t", loop_phases=[
    _PHASE("morgens", steps=[_STEP(key_press="a")], scheduled_start="07:00"),
    _PHASE("abends", steps=[_STEP(key_press="a")], scheduled_start="18:30"),
    _PHASE("kaputt", steps=[_STEP(key_press="a")], scheduled_start="x:y"),
])
_next = _W._next_schedule(_seq_t, _now)
check("die naechste Phase ist die, deren Uhrzeit heute noch kommt",
      _next is not None and _next[0] == "abends"
      and _dt.fromtimestamp(_next[1]) == _dt(2026, 1, 1, 18, 30))
_next = _W._next_schedule(_seq_t, _dt(2026, 1, 1, 20, 0, 0))
check("ist heute alles vorbei, meint die frueheste Uhrzeit morgen",
      _next is not None and _next[0] == "morgens"
      and _dt.fromtimestamp(_next[1]) == _dt(2026, 1, 2, 7, 0))
check("ohne Zeitplan gibt es keine naechste Phase",
      _W._next_schedule(_SEQ("o", loop_phases=[_PHASE("L", steps=[])]), _now) is None)


# =============================================================================
section("Zeitplan: der Worker dreht nicht leer")
# =============================================================================

_sandbox = _tmp.mkdtemp(prefix="zeitplan_")
_cwd = _os.getcwd()
_os.chdir(_sandbox)
_orig_execute = _W.execute_step
_executed = []
_W.execute_step = lambda state, step, n, total, phase: _executed.append((phase, n)) or True


def _run(seq, seconds: float, before=None):
    """Laesst `_run_main_loop` bis `seconds` laufen und zaehlt die Umlaeufe."""
    st = _ST()
    st.active_sequence = seq
    st.is_running = True
    st.start_time = _time.time()
    pending, lock = {}, _th.Lock()
    rounds = [0]
    orig = _W._run_loop_phases

    def counted(*a, **k):
        rounds[0] += 1
        return orig(*a, **k)

    _W._run_loop_phases = counted
    result = {}
    _status._state.clear()

    def body():
        buf = _io.StringIO()
        with _cl.redirect_stdout(buf):
            result["cycles"] = _W._run_main_loop(st, seq, pending, lock, False)
        result["out"] = buf.getvalue()

    t = _th.Thread(target=body, daemon=True)
    t.start()
    if before is not None:
        before(st, pending, lock)
    t.join(seconds)
    alive = t.is_alive()
    st.stop_event.set()
    t.join(3)
    _W._run_loop_phases = orig
    return st, result, rounds[0], alive


try:
    # --- nur Zeitplan, unendlich: schlafen statt drehen --------------------
    _seq = _SEQ("nachts", total_cycles=0, loop_phases=[
        _PHASE("nachts", steps=[_STEP(key_press="a")], scheduled_start="23:59")])
    _st, _res, _rounds, _alive = _run(_seq, 0.6)
    check("eine rein zeitgesteuerte Sequenz laeuft weiter (wartet), statt fertig zu sein",
          _alive is True)
    check("in 0,6 s gibt es hoechstens zwei Umlaeufe — vorher waren es ueber hundert",
          _rounds <= 2)
    check("und kein Zyklus wird gezaehlt", _res.get("cycles") == 0)
    check("kein Schritt ist gelaufen", _executed == [])
    check("die Live-Ansicht weiss, worauf gewartet wird",
          "[TIMER] wartet auf nachts um 23:59" in _res.get("out", ""))

    # --- Zeitplan mit Zyklusgrenze: der Termin wird abgewartet ---------------
    _seq = _SEQ("einmal", total_cycles=1, loop_phases=[
        _PHASE("nachts", steps=[_STEP(key_press="a")], scheduled_start="23:59")])

    def _fire(st, pending, lock):
        _time.sleep(0.3)                       # der Timer-Thread meldet: faellig
        with lock:
            pending[0] = True

    _st, _res, _rounds, _alive = _run(_seq, 3.0, before=_fire)
    check("total_cycles=1 endet erst, nachdem die Phase wirklich lief",
          _alive is False and _res.get("cycles") == 1
          and [p for p, _ in _executed] == ["nachts #1/1"])
    check("die Wartezeit davor zaehlte nicht als Zyklus",
          "Sequenz einmal durchgelaufen" in _res.get("out", ""))

    # --- Zeitplan plus normale Phase: die normale laeuft jeden Zyklus --------
    _executed.clear()
    _seq = _SEQ("gemischt", total_cycles=2, loop_phases=[
        _PHASE("immer", steps=[_STEP(key_press="a")]),
        _PHASE("nachts", steps=[_STEP(key_press="b")], scheduled_start="23:59")])
    _st, _res, _rounds, _alive = _run(_seq, 3.0)
    check("mit einer normalen Phase zaehlt jeder Zyklus wie bisher",
          _alive is False and _res.get("cycles") == 2
          and [p for p, _ in _executed] == ["immer #1/1", "immer #1/1"])

    # --- leere Phasen ohne Zeitplan: Ende mit Ansage statt Endlosschleife -----
    _executed.clear()
    _seq = _SEQ("leer", total_cycles=0, loop_phases=[_PHASE("Ablauf", steps=[])])
    _st, _res, _rounds, _alive = _run(_seq, 2.0)
    check("eine Sequenz ohne Schritte beendet sich selbst — und sagt es",
          _alive is False and _res.get("cycles") == 0
          and "Keine Phase hat Schritte" in _res.get("out", ""))

    # --- sanftes Ende waehrend des Wartens -------------------------------------
    _seq = _SEQ("sanft", total_cycles=0, loop_phases=[
        _PHASE("nachts", steps=[_STEP(key_press="a")], scheduled_start="23:59")])

    def _finish(st, pending, lock):
        _time.sleep(0.3)
        st.finish_event.set()

    _st, _res, _rounds, _alive = _run(_seq, 3.0, before=_finish)
    check("CTRL+ALT+F beendet auch das Warten auf den Termin", _alive is False)
    check("und das Warten ist in der Statusdatei wieder abgemeldet",
          _status._state.get("waiting") is None)
finally:
    _W.execute_step = _orig_execute
    _os.chdir(_cwd)
    _sh.rmtree(_sandbox, ignore_errors=True)
