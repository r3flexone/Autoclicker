"""Wie ein Lauf endet und woran man sieht, dass er lebt.

**END nach einem harten Stopp.** `_run_end_phase` prüfte nur `quit_event`:
nach CTRL+ALT+S stand „Führe End-Sequenz aus … abgeschlossen" in der
Konsole, Klicks verweigerte `safe_click`, aber Erkennungs-Blöcke liefen — ein
Boss-Scan samt LLM-Aufruf, eine Minute nachdem gestoppt war. Das sanfte Ende
(CTRL+ALT+F, Zeitlimit) läuft weiter durch END; das misst `session_limit.py`.

**Ein Lauf, der in EINEM Aufruf hängt, ist nicht tot.** Das Studio erklärt
einen Lauf nach 5 s ohne neuen Stempel für verwaist. Die Warteschleifen
schreiben ein Lebenszeichen, aber ein synchroner LLM-Boss-Scan blockiert den
Worker über eine Minute in einer HTTP-Antwort (`llm_async` ist aus). Seitdem
hält `status.start_heartbeat()` den Stempel frisch — und muss VOR der
Zusammenfassung stehen, sonst schriebe ein letzter Takt über sie.

**Ein Fehler in einem Handler beendet nicht den Hauptprozess.** Die
Hauptschleife fing nur `PlatformError`; jede andere Ausnahme lief heraus, die
Hotkeys wurden abgemeldet und ein laufender Worker starb mitten im Klick.
"""
import contextlib as _cl
import io as _io
import json as _json
import os as _os
import shutil as _sh
import tempfile as _tmp
import threading as _th
import time as _time
from pathlib import Path as _P

from ._harness import check, section
from autoclicker.models import (
    AutoClickerState as _ST,
    LoopPhase as _PHASE,
    Sequence as _SEQ,
    SequenceStep as _STEP,
)
import autoclicker.runtime.worker as _W
import autoclicker.runtime.status as _status

_sandbox = _tmp.mkdtemp(prefix="laufende_")
_cwd = _os.getcwd()
_os.chdir(_sandbox)
_orig_execute = _W.execute_step
try:
    # =========================================================================
    section("Nach einem harten Stopp laeuft keine END-Phase")
    # =========================================================================
    _executed: list = []

    def _record(state, step, n, total, phase):
        _executed.append((phase, n))
        return True

    _W.execute_step = _record
    _seq = _SEQ("ende", loop_phases=[_PHASE("L", steps=[_STEP(key_press="a")])],
                end_steps=[_STEP(boss_scan="boss"), _STEP(key_press="z")])
    _st = _ST()
    _st.stop_event.set()                                   # CTRL+ALT+S
    _out = _io.StringIO()
    with _cl.redirect_stdout(_out):
        _W._run_end_phase(_st, _seq, None)
    check("kein END-Block laeuft — auch keine Erkennung", _executed == [])
    check("und die Konsole behauptet keine End-Sequenz", "End-Sequenz" not in _out.getvalue())

    _st = _ST()
    _st.finish_event.set()                                 # CTRL+ALT+F
    with _cl.redirect_stdout(_io.StringIO()):
        _W._run_end_phase(_st, _seq, None)
    check("das sanfte Ende laeuft weiter durch END", len(_executed) == 2)

    # Gestoppt mitten in END: der Rest entfaellt.
    _executed.clear()

    def _stop_in_end(state, step, n, total, phase):
        _executed.append((phase, n))
        state.stop_event.set()
        return True

    _W.execute_step = _stop_in_end
    _st = _ST()
    with _cl.redirect_stdout(_io.StringIO()):
        _W._run_end_phase(_st, _seq, None)
    check("ein Stopp mitten in END beendet sie", _executed == [("END", 1)])

    # =========================================================================
    section("Ein Lauf, der in EINEM Aufruf haengt, sieht lebendig aus")
    # =========================================================================
    _stamps: dict = {}

    def _read_stamp():
        try:
            return float(_json.loads(_P(_status.STATUS_PATH).read_text(encoding="utf-8"))
                         .get("stamp") or 0)
        except (OSError, ValueError):
            return 0.0

    def _hangs(state, step, n, total, phase):
        # Ein Block, der 1,6 s in einem Aufruf steckt und selbst nichts
        # schreibt — wie ein LLM-Aufruf an einem kalten Modell, nur kuerzer.
        _stamps["before"] = _read_stamp()
        _time.sleep(1.6)
        _stamps["during"] = _read_stamp()
        return True

    _W.execute_step = _hangs
    _status._state.clear()
    _st = _ST()
    _st.active_sequence = _SEQ("haengt", total_cycles=1,
                               loop_phases=[_PHASE("L", steps=[_STEP(key_press="a")])])
    _st.is_running = True
    with _cl.redirect_stdout(_io.StringIO()):
        _W.sequence_worker(_st)
    check("waehrend des Aufrufs wird der Stempel fortgeschrieben",
          _stamps.get("during", 0) - _stamps.get("before", 0) >= 0.5)
    _time.sleep(1.3)                                       # laenger als ein Takt
    _final = _json.loads(_P(_status.STATUS_PATH).read_text(encoding="utf-8"))
    check("nach dem Ende bleibt die Zusammenfassung stehen — kein Takt danach",
          _final.get("active") is False and _final.get("end"))

    # =========================================================================
    section("Der Laufstatus haelt mehrere Schreiber aus")
    # =========================================================================
    # Worker, Lebenszeichen und asynchroner Boss-Thread schreiben dieselbe
    # Momentaufnahme. Ohne Sperre wuchs das Dict, waehrend `compact_json` es
    # durchlief — `RuntimeError`, und der fiel durch jedes `except` dort.
    # Kein Stresstest: ob der Wettlauf auftritt, haengt am Interpreter (neuere
    # serialisieren in C unter dem GIL, Python 3.10 in reinem Python). Gemessen
    # wird die Eigenschaft selbst — waehrend serialisiert wird, kommt kein
    # zweiter Schreiber an die Momentaufnahme.
    _status._state.clear()
    _st = _ST()
    _probe: dict = {}
    _orig_compact = _status.compact_json

    def _serialize_slowly(data):
        if "other" not in _probe:
            other = _th.Thread(target=_status.write_status,
                               args=(_st, {"from_other": 1}), kwargs={"immediately": True})
            _probe["other"] = other
            other.start()
            other.join(timeout=0.3)                        # Zeit genug, um dazwischenzufunken
            _probe["changed_meanwhile"] = "from_other" in data
        return _orig_compact(data)

    _status.compact_json = _serialize_slowly
    try:
        _status.write_status(_st, {"first": 1}, immediately=True)
    finally:
        _status.compact_json = _orig_compact
    _probe["other"].join(timeout=2)
    check("waehrend serialisiert wird, aendert kein zweiter Schreiber die Momentaufnahme",
          _probe.get("changed_meanwhile") is False)
    check("und sein Eintrag kommt danach trotzdem an",
          _status._state.get("from_other") == 1 and not _probe["other"].is_alive())
    _status._state.clear()
finally:
    _W.execute_step = _orig_execute
    _os.chdir(_cwd)
    _sh.rmtree(_sandbox, ignore_errors=True)

# =============================================================================
section("Ein Fehler in einem Handler beendet nicht den Hauptprozess")
# =============================================================================
import main as _main                                       # noqa: E402
from autoclicker.winapi import PlatformError as _PE        # noqa: E402


def _broken(*_a):
    raise KeyError("kaputt")


_out = _io.StringIO()
_survived = True
with _cl.redirect_stdout(_out), _cl.redirect_stderr(_io.StringIO()):
    try:
        _main.run_safely("Hotkey-Aktion", _broken, _ST())
    except Exception:                                      # noqa: BLE001
        _survived = False
check("eine beliebige Ausnahme wird gemeldet statt durchgereicht",
      _survived and "Hotkey-Aktion fehlgeschlagen" in _out.getvalue()
      and "KeyError" in _out.getvalue())


def _platform(*_a):
    raise _PE("kein Fenster")


_out = _io.StringIO()
with _cl.redirect_stdout(_out):
    _main.run_safely("Hotkey-Aktion", _platform, _ST())
check("eine Systemaktion meldet sich wie bisher",
      "Systemaktion fehlgeschlagen" in _out.getvalue())


def _interrupt(*_a):
    raise KeyboardInterrupt


try:
    _main.run_safely("Hotkey-Aktion", _interrupt, _ST())
    _passed_through = False
except KeyboardInterrupt:
    _passed_through = True
check("STRG+C geht weiter durch — beenden muss beenden koennen", _passed_through)

# Der Studio-Weg: ein Befehl aus dem Briefkasten, dessen Handler wirft.
_orig_fetch, _orig_last = _main.fetch_command, _main._command_last
_main.fetch_command = lambda: {"command": "block_test", "arguments": {}}
_main._command_last = 0.0
_orig_handler = _main.COMMANDS["block_test"]
_main.COMMANDS["block_test"] = _broken
_survived = True
try:
    with _cl.redirect_stdout(_io.StringIO()), _cl.redirect_stderr(_io.StringIO()):
        _main._check_commands(_ST())
except Exception:                                          # noqa: BLE001
    _survived = False
finally:
    _main.COMMANDS["block_test"] = _orig_handler
    _main.fetch_command, _main._command_last = _orig_fetch, _orig_last
check("ein Studio-Befehl, der wirft, laesst die Schleife stehen", _survived)
check("und die Hotkeys gehen denselben Weg",
      'run_safely("Hotkey-Aktion", hotkey_handlers[hk_id], state)'
      in _P(_main.__file__).read_text(encoding="utf-8"))
