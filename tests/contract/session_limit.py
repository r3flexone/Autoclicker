"""Session-Zeitlimit: nach `session_max_hours` endet der Lauf sanft.

Dasselbe Ereignis wie CTRL+ALT+F (`finish_event`), nur von der Uhr
ausgeloest: der laufende Zyklus wird fertig, danach laeuft die END-Phase.
Geprueft wird am Zyklus-Rand und beim Warten auf einen Zeitplan — ein harter
Stopp mitten im Zyklus liesse Items liegen und die END-Phase aus.
"""
import contextlib as _cl
import io as _io
import os as _os
import shutil as _sh
import tempfile as _tmp
import threading as _th
import time as _time

from ._harness import check, section
from autoclicker.config import AppConfig as _CFG, config_sections as _sections
from autoclicker.config_meta import META as _META
from autoclicker.models import (
    AutoClickerState as _ST,
    LoopPhase as _PHASE,
    Sequence as _SEQ,
    SequenceStep as _STEP,
)
import autoclicker.runtime.worker as _W
import autoclicker.runtime.status as _status


# =============================================================================
section("Session-Zeitlimit: das Feld und seine Grenzen")
# =============================================================================
check("Voreinstellung ist unbegrenzt (0)", _CFG().session_max_hours == 0)
with _cl.redirect_stdout(_io.StringIO()):
    _neg = _CFG(session_max_hours=-2)
check("ein negativer Wert wird auf 0 gehoben", _neg.session_max_hours == 0)
check("das Feld steht im Abschnitt SICHERHEIT",
      "session_max_hours" in dict(_sections())["SICHERHEIT"])
check("die Oberflaeche sagt, was 0 bedeutet",
      _META["session_max_hours"].empty == "unbegrenzt"
      and _META["session_max_hours"].unit == "h")

# =============================================================================
section("_check_session_limit setzt das sanfte Ende genau einmal")
# =============================================================================
_st = _ST()
_st.start_time = 1000.0
with _cl.redirect_stdout(_io.StringIO()):
    check("ohne Limit passiert nichts, egal wie lange",
          not _W._check_session_limit(_st, now=1000.0 + 10 * 86400)
          and not _st.finish_event.is_set())
    _st.config.session_max_hours = 2
    check("vor Ablauf passiert nichts",
          not _W._check_session_limit(_st, now=1000.0 + 2 * 3600 - 1)
          and not _st.finish_event.is_set())
_buf = _io.StringIO()
with _cl.redirect_stdout(_buf):
    _hit = _W._check_session_limit(_st, now=1000.0 + 2 * 3600)
    _W._check_session_limit(_st, now=1000.0 + 3 * 3600)
check("nach Ablauf wird finish_event gesetzt",
      _hit and _st.finish_event.is_set() and _st.session_limit_hit)
check("und genau einmal gemeldet", _buf.getvalue().count("ZEITLIMIT") == 1)
check("die Zusammenfassung nennt das Zeitlimit als Grund, nicht 'sanft beendet'",
      "Zeitlimit erreicht (2 h" in _W._end_reason(_st))

_st2 = _ST()
_st2.start_time = None
_st2.config.session_max_hours = 1
check("ohne Startzeit (Lauf nie angelaufen) greift nichts",
      not _W._check_session_limit(_st2, now=1e12))

# =============================================================================
section("Im Lauf: der Zyklus wird fertig, dann END")
# =============================================================================
_sandbox = _tmp.mkdtemp(prefix="zeitlimit_")
_cwd = _os.getcwd()
_os.chdir(_sandbox)
_executed: list = []
_orig_execute = _W.execute_step


def _fake_execute(state, step, n, total, phase):
    # Notbremse: greift das Limit nicht, liefe der endlose Lauf fuer immer —
    # die Gegenprobe soll rot werden, nicht die Suite anhalten.
    _executed.append((phase, n))
    if len(_executed) > 20:
        state.stop_event.set()
    return True


_W.execute_step = _fake_execute
try:
    _seq = _SEQ("zeitlimit", total_cycles=0,   # 0 = endlos — nur das Limit beendet ihn
                loop_phases=[_PHASE("L1", steps=[_STEP(key_press="a"), _STEP(key_press="b")])],
                end_steps=[_STEP(key_press="z")])
    _status._state.clear()
    _st3 = _ST()
    _st3.active_sequence = _seq
    _st3.is_running = True
    _st3.config.session_max_hours = 0.5
    _st3.start_time = _time.time() - 3600          # Limit ist laengst abgelaufen
    with _cl.redirect_stdout(_io.StringIO()):
        _cycles = _W._run_main_loop(_st3, _seq, {}, _th.Lock(), False, None)
        _W._run_end_phase(_st3, _seq, None)
    check("ein endloser Lauf endet nach dem ersten vollen Zyklus",
          _cycles == 1 and [p for p, _ in _executed].count("L1 #1/1") == 2)
    check("und die END-Phase laeuft danach",
          _executed[-1][0].startswith("END"))
    check("gestoppt wird nicht hart", not _st3.stop_event.is_set())
finally:
    _W.execute_step = _orig_execute
    _os.chdir(_cwd)
    _sh.rmtree(_sandbox, ignore_errors=True)
