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

    # =========================================================================
    section("Block-Skip im Item-Scan gilt dem ganzen Block")
    # =========================================================================
    # `execute_item_scan` verbrauchte das Signal selbst. Im normalen Modus
    # wurden die bis dahin gefundenen Items trotzdem geklickt, im Immediate-
    # Modus (ein Aufruf je Slot) fiel nur EIN Slot weg — gemessen: 4 von 5
    # Slots geklickt nach „Block ueberspringen".
    import autoclicker.runtime.item_scan as _IS
    from autoclicker.models import (
        ElseConfig as _ELSE, ItemProfile as _ITEM, ItemScanConfig as _ISC,
        ItemSlot as _SLOT,
    )

    class _Shot:                                   # ein Bild, das niemand ansieht
        size = (8, 8)

    _shots: list = []

    def _screenshot(region=None):
        _shots.append(region)
        return _Shot()

    def _matches(hit):
        return lambda profile, img, *a, **k: (hit, 1.0 if hit else 0.0) \
            if k.get("return_score") else hit

    _orig_is = (_IS.take_screenshot, _IS._park_mouse_for_scan, _IS._check_profile_match)
    _IS._park_mouse_for_scan = lambda *a: None
    _IS._check_profile_match = _matches(True)

    def _scan_state(immediate):
        st = _ST()
        st.is_running = True
        st.config.scan_click_immediate = immediate
        st.config.scan_item_click_delay = 0
        st.config.scan_slot_delay = 0
        st.item_scans["inv"] = _ISC("inv", slots=[
            _SLOT(f"S{i}", (i * 10, 0, i * 10 + 8, 8), (100 + i, 0)) for i in range(5)],
            items=[_ITEM("Bogen", marker_colors=[(1, 2, 3)])])
        return st

    def _skip_at_second_slot(st):
        def shot(region=None):
            if len(_shots) == 1:
                st.skip_step_event.set()           # CTRL+ALT+SHIFT+K beim zweiten Slot
            return _screenshot(region)
        return shot

    try:
        # --- normal: Skip waehrend des zweiten Slots -----------------------
        _st = _scan_state(False)
        _clicks.clear()
        _shots.clear()
        _IS.take_screenshot = _skip_at_second_slot(_st)
        _out = _io.StringIO()
        _r1 = _run_step(_st, _STEP(item_scan="inv", item_scan_mode="every"), 1, 2, _out)
        check("normal: die bis dahin gefundenen Items werden NICHT geklickt",
              _r1 is True and _clicks == [])
        check("normal: das Signal ist verbraucht", not _st.skip_step_event.is_set())
        _r2 = _run_step(_st, _STEP(x=9, y=9, name="B", point_id=9), 2, 2, _out)
        check("normal: der naechste Block laeuft und klickt",
              _r2 is True and _clicks == [(9, 9)])

        # --- immediate: Skip zwischen zwei Slots ---------------------------
        _st = _scan_state(True)
        _clicks.clear()
        _shots.clear()
        _IS.take_screenshot = _screenshot
        _parks: list = []
        _IS._park_mouse_for_scan = lambda *a: _parks.append(1)

        def _click_then_skip(x, y, *a):
            _clicks.append((x, y))
            if len(_clicks) == 1:
                _st.skip_step_event.set()          # direkt nach dem ersten Item
            return True

        _A.send_click = _click_then_skip
        _r1 = _run_step(_st, _STEP(item_scan="inv", item_scan_mode="every"), 1, 2, _out)
        _A.send_click = lambda x, y, *a: _clicks.append((x, y)) or True
        check("immediate: nach dem Skip wird kein weiterer Slot geklickt",
              _r1 is True and _clicks == [(100, 0)])
        check("immediate: und keiner mehr angefasst — kein Parken, keine Aufnahme",
              len(_parks) == 1 and len(_shots) == 1)
        check("immediate: das Signal ist verbraucht", not _st.skip_step_event.is_set())

        # Skip WAEHREND des Scans eines Slots (beim Parken davor): dann faengt
        # ihn `execute_item_scan` — und darf ihn nicht verbrauchen, sonst
        # scannt der Durchgang mit dem naechsten Slot einfach weiter.
        def _skip_at_park(number):
            def park(*a):
                _parks.append(1)
                if len(_parks) == number:
                    _st.skip_step_event.set()
            return park

        _st = _scan_state(True)
        _clicks.clear()
        _parks.clear()
        _IS._park_mouse_for_scan = _skip_at_park(2)          # vor dem zweiten Slot
        _r1 = _run_step(_st, _STEP(item_scan="inv", item_scan_mode="every"), 1, 2, _out)
        check("immediate: ein Skip mitten im Scan beendet den ganzen Block",
              _r1 is True and _clicks == [(100, 0)] and not _st.skip_step_event.is_set())

        # Kommt er im LETZTEN Slot, endet die Schleife von selbst — danach darf
        # der Block nicht „erledigt" melden und das Signal liegen lassen.
        _st = _scan_state(True)
        _clicks.clear()
        _parks.clear()
        _IS._park_mouse_for_scan = _skip_at_park(5)          # vor dem fuenften Slot
        _r1 = _run_step(_st, _STEP(item_scan="inv", item_scan_mode="every"), 1, 2, _out)
        _r2 = _run_step(_st, _STEP(x=9, y=9, name="B", point_id=9), 2, 2, _out)
        check("immediate: Skip im letzten Slot — der naechste Block laeuft trotzdem",
              _r1 is True and _r2 is True and _clicks[-1] == (9, 9)
              and len(_clicks) == 5 and not _st.skip_step_event.is_set())
        _IS._park_mouse_for_scan = lambda *a: None

        # --- ELSE darf den Skip nicht schlucken ----------------------------
        # Ohne Treffer greift sonst ELSE — `skip` meldet „erledigt", und das
        # Signal blieb fuer den NAECHSTEN Block liegen.
        _st = _scan_state(False)
        _IS._check_profile_match = _matches(False)
        _clicks.clear()
        _shots.clear()
        _IS.take_screenshot = _skip_at_second_slot(_st)
        _r1 = _run_step(_st, _STEP(item_scan="inv", item_scan_mode="every",
                                   else_config=_ELSE(action="skip")), 1, 2, _out)
        _r2 = _run_step(_st, _STEP(x=9, y=9, name="B", point_id=9), 2, 2, _out)
        check("mit ELSE: der Skip wird verbraucht, der naechste Block klickt",
              _r1 is True and not _st.skip_step_event.is_set() and _clicks == [(9, 9)])
    finally:
        _IS.take_screenshot, _IS._park_mouse_for_scan, _IS._check_profile_match = _orig_is

    # =========================================================================
    section("Eine verweigerte Taste laesst keinen Block-Skip liegen")
    # =========================================================================
    # `_execute_key` meldete „erledigt", auch wenn `safe_key` die Taste wegen
    # des Skips verweigert hatte. Das Signal blieb gesetzt, und der NAECHSTE
    # Block wurde verschluckt. Dasselbe Muster stand bei der ELSE-Taste und
    # bei der Taste einer Boss-/Icon-Erkennung.
    import autoclicker.runtime.boss_detection as _BD
    from autoclicker.models import ElseConfig as _ELSE2, BOSS_ACTION_KEY as _BKEY

    _keys: list = []
    _orig_key, _orig_delay = _A.send_key, _A._humanize_delay
    _A.send_key = lambda key: _keys.append(key) or True

    def _skip_in_delay(st):
        # Der Skip kommt in der Humanize-Pause — zwischen der ersten und der
        # zweiten Pruefung in `safe_key`, deterministisch statt mit einer Uhr.
        st.skip_step_event.set()

    _A._humanize_delay = _skip_in_delay
    try:
        _st = _ST()
        _st.is_running = True
        _clicks.clear()
        _out = _io.StringIO()
        _r1 = _run_step(_st, _STEP(key_press="a", name="Taste"), 1, 2, _out)
        _A._humanize_delay = _orig_delay
        _r2 = _run_step(_st, _STEP(x=7, y=7, name="B", point_id=7), 2, 2, _out)
        check("die Taste wird nicht gedrueckt, der Block gilt als uebersprungen",
              _r1 is True and _keys == [])
        check("der naechste Block laeuft und klickt — er wird nicht verschluckt",
              _r2 is True and _clicks == [(7, 7)] and not _st.skip_step_event.is_set())

        _A._humanize_delay = _skip_in_delay
        _st = _ST()
        _st.is_running = True
        with _cl.redirect_stdout(_io.StringIO()):
            _else = _A.execute_else_action(
                _st, _STEP(else_config=_ELSE2(action="key", key="z")), "Loop", 1, 1)
        check("ELSE-Taste: verweigert heisst nicht erledigt", _else is False and _keys == [])

        _st = _ST()
        _st.is_running = True
        with _cl.redirect_stdout(_io.StringIO()):
            _det = _BD._execute_detection_action(
                _st, subject="Icon 'X'", action=_BKEY, label="icon:X", step_num=1,
                total_steps=1, phase="Loop", debug=False, key="q")
        check("Erkennungs-Taste: verweigert heisst nicht erledigt",
              _det is False and _keys == [])

        # Ein echter Fehlschlag des Systems (unbekannte Taste) ist KEIN Grund,
        # den Durchgang abzubrechen — das bleibt, wie es war.
        _A._humanize_delay = _orig_delay
        _A.send_key = lambda key: False
        _st = _ST()
        _st.is_running = True
        _r = _run_step(_st, _STEP(key_press="gibtsnicht"), 1, 1, _io.StringIO())
        check("eine vom System abgelehnte Taste laesst den Lauf weitergehen", _r is True)
    finally:
        _A.send_key, _A._humanize_delay = _orig_key, _orig_delay
finally:
    _A.send_click, _S.check_failsafe = _orig_click, _orig_failsafe
    _status._state.clear()
    _os.chdir(_cwd)
    _sh.rmtree(_sandbox, ignore_errors=True)
