"""Pause und Block-Skip: zwei Ereignisse, die von aussen in einen Block fallen.

**Block-Skip mitten in der Aktion.** CTRL+ALT+K kann kommen, während
`safe_click` gerade in der Humanize-Pause oder im Fokus-Warten steht. Dort
brach `_input_allowed` ab, die Aktion meldete `False` wie bei einem Stopp —
und der Worker warf den Rest des Durchgangs weg. Das Event blieb dabei
gesetzt, und der ERSTE Block des nächsten Durchgangs wurde verschluckt.
Gemessen: Block A `False`, Block B „übersprungen" ohne Klick.

**Pause ohne Lebenszeichen.** `wait_while_paused` schlief mit `time.sleep`
und schrieb nichts in den Laufstatus. Der Zeitstempel alterte, und nach fünf
Sekunden Pause zeigte das Studio „KEIN HAUPTPROZESS" — für einen Lauf, der
nur auf CTRL+ALT+G wartete. Ein Stopp griff zudem erst nach
`timing_pause_interval`.
"""
import contextlib as _cl
import io as _io
import json as _json
import os as _os
import shutil as _sh
import tempfile as _tmp
import threading as _th
import time as _time

from ._harness import check, section, studio_web_source
from autoclicker.models import AutoClickerState as _ST, SequenceStep as _STEP
import autoclicker.runtime.steps as _S
import autoclicker.runtime.actions as _A
import autoclicker.runtime.status as _status
import autoclicker.utils as _utils

_sandbox = _tmp.mkdtemp(prefix="pause_skip_")
_cwd = _os.getcwd()
_os.chdir(_sandbox)
_orig_click, _orig_failsafe = _A.send_click, _S.check_failsafe
_clicks: list = []
_A.send_click = lambda x, y, *a: _clicks.append((x, y)) or True
_S.check_failsafe = lambda s: False


def _run_step(st, step, n, total, out):
    with _cl.redirect_stdout(out):
        return _S.execute_step(st, step, n, total, "Loop")


try:
    # =========================================================================
    section("Block-Skip waehrend der Humanize-Pause")
    # =========================================================================
    _st = _ST()
    _st.is_running = True
    _st.config.humanize_enabled = True
    _st.config.humanize_micro_delay_min = 0.25
    _st.config.humanize_micro_delay_max = 0.25

    def _press():
        _time.sleep(0.05)                      # CTRL+ALT+K mitten im Mikro-Delay
        _st.skip_step_event.set()

    _th.Thread(target=_press, daemon=True).start()
    _out = _io.StringIO()
    _r1 = _run_step(_st, _STEP(x=1, y=1, name="A", point_id=1), 1, 2, _out)
    _r2 = _run_step(_st, _STEP(x=2, y=2, name="B", point_id=2), 2, 2, _out)
    _lines = [line for line in _out.getvalue().splitlines() if "bersprungen" in line]
    check("der Skip beendet Block A als 'uebersprungen' — kein Abbruch des Durchgangs",
          _r1 is True and "Schritt 1/2" in "".join(_lines))
    check("Block B laeuft normal und wird geklickt",
          _r2 is True and _clicks == [(2, 2)])
    check("das Event ist danach verbraucht", not _st.skip_step_event.is_set())
    check("und B wurde NICHT als uebersprungen gemeldet",
          not any("Schritt 2/2" in line for line in _lines))

    # =========================================================================
    section("Pause: Lebenszeichen, Zustand, Stopp")
    # =========================================================================
    _st = _ST()
    _st.is_running = True
    _st.config.timing_pause_interval = 0.1
    _status._state.clear()
    _status.write_status(_st, {"active": True, "sequence": "x",
                               "waiting": {"kind": "time", "text": "davor"}},
                         immediately=True)
    _st.pause_event.set()
    _seen: dict = {}

    def _watch():
        _time.sleep(0.6)
        try:
            _seen["mid"] = _json.load(open(".run.json", encoding="utf-8"))
            _seen["read_at"] = _time.time()
        except (OSError, ValueError):
            _seen["mid"] = None
        _time.sleep(0.6)
        _st.pause_event.clear()

    _th.Thread(target=_watch, daemon=True).start()
    with _cl.redirect_stdout(_io.StringIO()):
        _ok = _A.wait_while_paused(_st, "Klicke in")
    _after = _json.load(open(".run.json", encoding="utf-8"))
    _mid = _seen.get("mid") or {}
    check("die Pause kehrt mit True zurueck, sobald fortgesetzt wird", _ok is True)
    check("waehrend der Pause bleibt der Zeitstempel frisch (juenger als 0,4 s)",
          bool(_mid.get("stamp")) and _seen.get("read_at", 0) - _mid["stamp"] < 0.4)
    check("die Live-Ansicht sieht die Pause als Warte-Zustand",
          (_mid.get("waiting") or {}).get("kind") == "pause"
          and "Klicke in" in (_mid.get("waiting") or {}).get("text", ""))
    check("nach der Pause steht wieder das, worauf der Block vorher wartete",
          (_after.get("waiting") or {}).get("kind") == "time"
          and (_after.get("waiting") or {}).get("text") == "davor")

    # Ein Stopp greift sofort — nicht erst nach dem Pruef-Intervall.
    _st = _ST()
    _st.config.timing_pause_interval = 5.0
    _st.pause_event.set()
    _result: dict = {}

    def _stop_soon():
        _time.sleep(0.1)
        _st.stop_event.set()

    _th.Thread(target=_stop_soon, daemon=True).start()
    _began = _time.time()
    with _cl.redirect_stdout(_io.StringIO()):
        _result["ok"] = _A.wait_while_paused(_st, "x")
    _took = _time.time() - _began
    check("ein Stopp waehrend der Pause greift sofort statt nach dem Intervall",
          _result["ok"] is False and _took < 1.0)

    check("wait_while_paused wohnt bei der Laufzeit, nicht mehr in utils",
          not hasattr(_utils, "wait_while_paused"))

    # Die Seite zeigt die Pause — sonst schriebe der Worker ins Leere.
    _web = studio_web_source()
    check("der Live-Run zeigt PAUSIERT, wenn der Warte-Zustand eine Pause ist",
          'z.waiting.kind === "pause"' in _web and '"PAUSIERT"' in _web)

    # =========================================================================
    section("Block-Skip hat einen Hotkey, nicht nur einen Studio-Knopf")
    # =========================================================================
    # `handle_skip_step` gab es fuer den Knopf im Live-Run und den
    # Briefkasten-Befehl - aus der Konsole liess sich ein haengender Block nur
    # mit dem ganzen Lauf abbrechen. CTRL+ALT+SHIFT+K liegt auf der
    # SHIFT-Ebene (wirkt nur waehrend eines Laufs) und ruft DENSELBEN Handler.
    import re as _re
    from pathlib import Path as _P
    from autoclicker.platforms import common as _common
    import autoclicker.handlers as _hnd

    _root = _P(__file__).resolve().parent.parent.parent
    _main_src = (_root / "main.py").read_text(encoding="utf-8")
    _win_src = (_root / "autoclicker/platforms/windows.py").read_text(encoding="utf-8")
    check("die Hotkey-ID existiert und liegt auf CTRL+ALT+SHIFT+K",
          _common.HOTKEY_BINDINGS.get(getattr(_common, "HOTKEY_SKIP_STEP", None))
          == "<ctrl>+<alt>+<shift>+k")
    check("Windows registriert sie auf der SHIFT-Ebene (MOD_REC)",
          _re.search(r"\(HOTKEY_SKIP_STEP,\s*MOD_REC,\s*VK_K,", _win_src) is not None)
    check("main.py schickt sie an handle_skip_step",
          _re.search(r"HOTKEY_SKIP_STEP:\s*handle_skip_step,", _main_src) is not None
          and _re.search(r"col\('CTRL\+ALT\+SHIFT\+K'", _main_src) is not None)

    _st = _ST()
    with _cl.redirect_stdout(_io.StringIO()):
        _hnd.handle_skip_step(_st)
    check("ohne laufende Sequenz setzt der Handler nichts",
          not _st.skip_step_event.is_set())
    _st.is_running = True
    with _cl.redirect_stdout(_io.StringIO()):
        _hnd.handle_skip_step(_st)
    check("mit laufender Sequenz setzt er skip_step_event - denselben Weg wie der Knopf",
          _st.skip_step_event.is_set())
finally:
    _A.send_click, _S.check_failsafe = _orig_click, _orig_failsafe
    _status._state.clear()
    _os.chdir(_cwd)
    _sh.rmtree(_sandbox, ignore_errors=True)
