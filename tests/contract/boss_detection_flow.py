"""Boss-Erkennung (`runtime/boss_detection.py`): Reihenfolge, Wiederholungen, Aktionen.

Geschrieben, BEVOR sechs Funktionen dort zerlegt wurden — `execute_boss_scan`
(19), die OCR- und LLM-Erkennung (20/23), `_execute_detection_action` (25),
der Async-Thread (20) und das Async-ELSE (13). Zwei davon standen in keinem
Test (OCR, Async-ELSE), die Aktionen nur mit einem Fall. Gestellt sind
Screenshot, Template-Vergleich, OCR- und LLM-Backend, Klick/Taste und der
Item-Scan; gemessen wird, wer in welcher Reihenfolge gefragt wird und was
herauskommt.
"""
import contextlib as _cl
import io as _io

from ._harness import check, section

import autoclicker.llm_vision as _LLM
import autoclicker.ocr as _OCR
import autoclicker.runtime.boss_detection as _BD
from autoclicker.models import (
    AutoClickerState as _ST, BossProfile as _BP, BossScanConfig as _BSC, ClickPoint as _CP,
    ElseConfig as _EC, Sequence as _SEQ, SequenceStep as _STEP,
)


@_cl.contextmanager
def _patched(*stubs):
    saved = [(module, name, getattr(module, name)) for module, name, _ in stubs]
    for module, name, value in stubs:
        setattr(module, name, value)
    try:
        yield
    finally:
        for module, name, value in reversed(saved):
            setattr(module, name, value)


def _quiet(fn, *args, **kwargs):
    buffer = _io.StringIO()
    with _cl.redirect_stdout(buffer):
        result = fn(*args, **kwargs)
    return result, buffer.getvalue()


def _state(bosses=("Drache",), use_ocr=False, ocr_fb=True, use_llm=False, llm_fb=True,
           global_bosses=(), ocr=True, llm=True):
    st = _ST()
    st.config.ocr_enabled, st.config.llm_enabled = ocr, llm
    st.boss_scans["B"] = _BSC("B", bosses=[_BP(n) for n in bosses],
                              use_ocr=use_ocr, ocr_fallback=ocr_fb,
                              use_llm=use_llm, llm_fallback=llm_fb)
    st.global_bosses = [_BP(n) for n in global_bosses]
    return st


# =============================================================================
section("Boss-Scan: wer in welcher Reihenfolge gefragt wird")
# =============================================================================
def _order(st, hits=()):
    """Ruft execute_boss_scan; jeder Erkenner meldet sich, `hits` nennt, wer trifft."""
    calls = []

    def _ocr(state, config, img, debug, snapshot):
        calls.append("ocr")
        return snapshot[0] if "ocr" in hits else None

    def _llm(state, config, img, debug, snapshot):
        calls.append("llm")
        return snapshot[0] if "llm" in hits else None

    def _template(boss, img, tol, state, debug, label):
        calls.append(f"tpl:{boss.name}")
        return f"tpl:{boss.name}" in hits

    with _patched((_BD, "take_screenshot", lambda region: object()),
                  (_BD, "_execute_ocr_boss_detection", _ocr),
                  (_BD, "_execute_llm_boss_detection", _llm),
                  (_BD, "_check_profile_match", _template)):
        result, _out = _quiet(_BD.execute_boss_scan, st, "B")
    return calls, result


_r, _out = _quiet(_BD.execute_boss_scan, _ST(), "fehlt")
check("ein unbekannter Scan wird gesagt", _r == (False, None) and "nicht gefunden" in _out)
_r, _out = _quiet(_BD.execute_boss_scan, _state(bosses=()), "B")
check("ein Scan ohne Bosse (auch ohne globale) wird gesagt",
      _r == (False, None) and "keine Bosse" in _out)
with _patched((_BD, "take_screenshot", lambda region: None)):
    check("ohne Screenshot nichts", _quiet(_BD.execute_boss_scan, _state(), "B")[0] == (False, None))

_calls, _r = _order(_state(use_ocr=True, ocr_fb=False, use_llm=True, llm_fb=False))
check("primär: erst OCR, dann LLM, dann die Vorlagen", _calls == ["ocr", "llm", "tpl:Drache"]
      and _r == (False, None))
_calls, _r = _order(_state(use_ocr=True, use_llm=True))
check("als Rückfall: erst die Vorlagen, dann OCR, dann LLM", _calls == ["tpl:Drache", "ocr", "llm"])
_calls, _r = _order(_state(use_ocr=True, use_llm=True, ocr=False, llm=False))
check("global ausgeschaltet läuft keiner der beiden", _calls == ["tpl:Drache"])
_calls, _r = _order(_state(use_ocr=True, ocr_fb=False, use_llm=True, llm_fb=False), hits=("ocr",))
check("der erste Treffer gewinnt", _calls == ["ocr"] and _r[0] is True and _r[1].name == "Drache")
_calls, _r = _order(_state(bosses=("Drache", "Wolf"), global_bosses=("Wolf", "Riese")),
                    hits=("tpl:Riese",))
check("lokale Bosse vor globalen, gleichnamige globale entfallen",
      _calls == ["tpl:Drache", "tpl:Wolf", "tpl:Riese"] and _r[1].name == "Riese")


# =============================================================================
section("Boss-Scan: OCR mit Wiederholungen")
# =============================================================================
def _ocr_run(answers, retry=2, available=True, screenshots=None, new_boss=None):
    st = _state(bosses=("Drache", "Wolf"))
    st.config.ocr_retry_count = retry
    asked, shots, handled = [], list(screenshots or []), []

    def _detect(**kw):
        asked.append(kw["min_confidence"])
        return answers.pop(0)

    def _shot(region):
        return shots.pop(0) if shots else object()

    def _new(state, config, name, source, debug):
        handled.append((name, source))
        return new_boss

    with _patched((_OCR, "is_available", lambda: available),
                  (_OCR, "detect_boss_name", _detect),
                  (_BD, "take_screenshot", _shot),
                  (_BD, "_handle_new_boss", _new)):
        boss, _out = _quiet(_BD._execute_ocr_boss_detection, st, st.boss_scans["B"], object(),
                            False, list(st.boss_scans["B"].bosses))
    return boss, asked, handled


_miss = (False, None, "", 1.0, None)
check("ohne OCR-Backend nichts", _ocr_run([], available=False)[0] is None)
_boss, _asked, _ = _ocr_run([(True, "Wolf", "Wolf", 1.0, None)])
check("ein Treffer im ersten Versuch", _boss.name == "Wolf" and len(_asked) == 1)
check("die Mindest-Konfidenz ist mindestens 0.8", _asked[0] >= 0.8)
_boss, _asked, _ = _ocr_run([_miss, (True, "Drache", "Drache", 1.0, None)])
check("unsicher → neuer Screenshot, zweiter Versuch trifft", _boss.name == "Drache" and len(_asked) == 2)
_boss, _asked, _ = _ocr_run([_miss, _miss, _miss, _miss], retry=2)
check("höchstens 1 + ocr_retry_count Versuche", _boss is None and len(_asked) == 3)
_boss, _asked, _ = _ocr_run([_miss], screenshots=[None])
check("scheitert der neue Screenshot, ist Schluss", _boss is None and len(_asked) == 1)
_new_profile = _BP("Hydra")
_boss, _asked, _handled = _ocr_run([(False, None, "Hydra", 1.0, "Hydra"), _miss, _miss],
                                   new_boss=_new_profile)
check("ein sicherer unbekannter Name wird ein neuer Boss, ohne weiteren Versuch",
      _boss is _new_profile and _handled == [("Hydra", "OCR")] and len(_asked) == 1)
_boss, _asked, _handled = _ocr_run([(False, None, "Hydra", 1.0, "Hydra"), _miss, _miss], new_boss=None)
check("ist er schon vorgemerkt, wird nicht weiter versucht", _boss is None and len(_asked) == 1)


# =============================================================================
section("Boss-Scan: LLM mit Wiederholungen und Aufwärmen")
# =============================================================================
def _llm_run(answers, matches=(), retry=1, new_boss=None, global_bosses=(), learn_global=False):
    st = _state(bosses=("Drache",), global_bosses=global_bosses)
    st.config.llm_retry_count, st.config.llm_timeout = retry, 30
    timeouts, matched, shots = [], list(matches), []

    def _analyze(**kw):
        timeouts.append(kw["timeout"])
        return answers.pop(0)

    def _shot(region):
        shots.append(region)
        return object()

    with _patched((_LLM, "analyze_image", _analyze),
                  (_LLM, "is_timeout", lambda answer: answer == "TIMEOUT"),
                  (_LLM, "match_boss_name", lambda response, names: matched.pop(0)),
                  (_BD, "take_screenshot", _shot),
                  (_BD, "_handle_new_boss", lambda *a: new_boss)):
        cfg = st.boss_scans["B"]
        snapshot = list(cfg.bosses) + list(st.global_bosses)
        boss, _out = _quiet(_BD._execute_llm_boss_detection, st, cfg, object(), False, snapshot)
    return boss, timeouts, shots


_boss, _timeouts, _ = _llm_run([(False, "kaputt", 5.0)])
check("ein Fehler beendet die LLM-Erkennung ohne Wiederholung", _boss is None and _timeouts == [30])
_boss, _timeouts, _ = _llm_run([(False, "TIMEOUT", 30000.0), (True, "Drache", 1.0)],
                               matches=[("Drache", False)])
check("ein Timeout bekommt einen zweiten Versuch mit mehr Zeit",
      _boss.name == "Drache" and _timeouts == [30, 120])
_boss, _timeouts, _ = _llm_run([(False, "TIMEOUT", 1.0), (False, "TIMEOUT", 1.0)])
check("aber nur einen", _boss is None and len(_timeouts) == 2)
_boss, _timeouts, _ = _llm_run([(False, "TIMEOUT", 1.0), (True, "nichts", 1.0),
                                (False, "TIMEOUT", 1.0), (True, "Drache", 1.0)],
                               matches=[(None, False), ("Drache", False)])
check("und nur einmal je Scan: ein späterer Timeout bricht ab",
      _boss is None and _timeouts == [30, 120, 30])
_boss, _timeouts, _shots = _llm_run([(True, "nichts", 1.0), (True, "Drache", 1.0)],
                                    matches=[(None, False), ("Drache", False)])
check("„kein Boss“ wiederholt mit neuem Screenshot",
      _boss.name == "Drache" and len(_timeouts) == 2 and len(_shots) == 1)
_hydra = _BP("Hydra")
_boss, _, _ = _llm_run([(True, "Hydra", 1.0)], matches=[("Hydra", True)], new_boss=_hydra)
check("ein neuer Name wird ein neuer Boss", _boss is _hydra)
_boss, _, _ = _llm_run([(True, "Riese", 1.0)], matches=[("Riese", True)], global_bosses=("Riese",))
check("ist er schon bekannt (auch global), wird das Profil geliefert",
      _boss is not None and _boss.name == "Riese")
_boss, _, _ = _llm_run([(True, "Geist", 1.0)], matches=[("Geist", True)])
check("ist er weder neu noch auffindbar, nichts", _boss is None)


# =============================================================================
section("Erkennungs-Aktion: jede Art")
# =============================================================================
def _act(action, *, point=None, stop=False, click_ok=True, key_ok=True, refused=False,
         scan=None, results=(), result_ok=True, delay=0, key="enter"):
    st = _ST()
    with _cl.redirect_stdout(_io.StringIO()):
        from autoclicker.persistence import activate_sequence
        activate_sequence(st, _SEQ("A", points=[_CP(40, 50, "Ziel", 7)]))
    if stop:
        st.stop_event.set()
    clicks, keys, clicked_results = [], [], []
    with _patched((_BD, "safe_click", lambda s, x, y, label="": clicks.append((x, y)) or click_ok),
                  (_BD, "safe_key", lambda s, k, label="": keys.append(k) or key_ok),
                  (_BD, "input_refused", lambda s: refused),
                  (_BD, "log_event", lambda *a, **k: None),
                  (_BD, "execute_item_scan", lambda s, name, mode: list(results)),
                  (_BD, "_click_scan_result",
                   lambda s, pos, item, prio, debug: clicked_results.append(item) or result_ok)):
        go_on, out = _quiet(_BD._execute_detection_action, st, subject="Boss 'X'", action=action,
                            label="boss:X", step_num=1, total_steps=1, phase="LOOP", debug=False,
                            key=key, delay=delay, point_id=point, scan=scan)
    return go_on, out, st, clicks, keys, clicked_results


_go, _out, _st, _clicks, _, _ = _act("click", point=99)
check("Klick ohne Zielpunkt entfällt und wird gesagt",
      _go is True and not _clicks and "Zielpunkt fehlt" in _out)
_go, _out, _st, _clicks, _, _ = _act("click", point=7)
check("Klick auf den Punkt, gezählt", _go is True and _clicks == [(40, 50)] and _st.total_clicks == 1)
_go, *_ = _act("click", point=7, click_ok=False)
check("ein verweigerter Klick bricht ab", _go is False)
_go, _out, _st, _clicks, _, _ = _act("click", point=7, delay=5, stop=True)
check("ein Stopp in der Verzögerung bricht ab, ohne zu klicken", _go is False and not _clicks)
_go, _out, *_ = _act("item_scan")
check("Scan ohne Namen wird gesagt", _go is True and "Kein Item-Scan" in _out)
_go, _out, _st, _, _, _items = _act("item_scan", scan="inv", results=[((1, 1), "a", 1), ((2, 2), "b", 2)])
check("Scan: jeder Treffer wird geklickt", _go is True and _items == ["a", "b"])
_go, _out, _st, _, _, _items = _act("item_scan", scan="inv", results=[((1, 1), "a", 1), ((2, 2), "b", 2)],
                                    result_ok=False)
check("Scan: ein abgebrochener Klick bricht ab", _go is False and _items == ["a"])
_go, *_ = _act("item_scan", scan="inv")
check("Scan ohne Treffer läuft weiter", _go is True)
_go, _out, _st, _, _keys, _ = _act("key")
check("Taste, gezählt", _go is True and _keys == ["enter"] and _st.key_presses == 1)
_go, *_ = _act("key", key_ok=False, refused=True)
check("eine verweigerte Taste bricht ab", _go is False)
_go, _out, _st, _, _keys, _ = _act("key", key_ok=False, refused=False)
check("eine nicht angenommene Taste läuft weiter", _go is True and _st.key_presses == 0)
_go, _out, _st, _, _keys, _ = _act("key", key=None)
check("ohne Taste passiert nichts", _go is True and not _keys)
_go, *_ = _act("skip")
check("skip läuft weiter", _go is True)
_go, _out, _st, *_ = _act("skip_cycle")
check("skip_cycle setzt das Ereignis und bricht ab", _go is False and _st.skip_cycle_event.is_set())
_go, _out, _st, *_ = _act("restart")
check("restart setzt das Ereignis und bricht ab", _go is False and _st.restart_event.is_set())


# =============================================================================
section("Async-Pfad: ELSE und Thread")
# =============================================================================
def _async_else(else_config, stop=False, failsafe=False, paused_ok=True):
    st = _ST()
    if stop:
        st.stop_event.set()
    clicks, keys = [], []
    step = _STEP(boss_scan="B", else_config=else_config)
    with _patched((_BD, "safe_click", lambda s, x, y, label="": clicks.append((x, y)) or True),
                  (_BD, "safe_key", lambda s, k, label="": keys.append(k) or True),
                  (_BD, "check_failsafe", lambda s: failsafe),
                  (_BD, "wait_while_paused", lambda s, msg: paused_ok)):
        _quiet(_BD._maybe_execute_async_else, st, step, 1, 1, "LOOP", False)
    return clicks, keys, st


check("ohne ELSE nichts", _async_else(None)[:2] == ([], []))
check("skip wird im Async-Pfad verworfen", _async_else(_EC(action="skip"))[:2] == ([], []))
check("Klick", _async_else(_EC(action="click", x=3, y=4))[0] == [(3, 4)])
check("Taste", _async_else(_EC(action="key", key="space"))[1] == ["space"])
check("Taste ohne Namen: nichts", _async_else(_EC(action="key", key=None))[1] == [])
check("nach einem Stopp nichts", _async_else(_EC(action="click", x=3, y=4), stop=True)[0] == [])
_clicks, _keys, _st = _async_else(_EC(action="click", x=3, y=4), failsafe=True)
check("die Notbremse stoppt", _clicks == [] and _st.stop_event.is_set())
check("eine gestoppte Pause: nichts", _async_else(_EC(action="click", x=3, y=4), paused_ok=False)[0] == [])
check("das Aktions-Ereignis ist danach wieder frei",
      not _async_else(_EC(action="click", x=3, y=4))[2].llm_action_event.is_set())


def _thread(step, scans, failsafe=False, interval=0, max_scans=0, timeout=0, boom=False):
    st = _ST()
    st.config.llm_watcher_interval, st.config.llm_watcher_max_scans = interval, max_scans
    st.config.llm_watcher_timeout = timeout
    actions, elses, logged = [], [], []
    answers = list(scans)

    def _scan(state, name):
        if boom:
            raise ValueError("kaputt")
        if not answers:
            # Mehr Scans als vorgesehen: anhalten, statt endlos zu drehen —
            # sonst wäre eine fehlende Grenze ein Hänger statt eines roten Tests.
            state.stop_event.set()
            return False, None
        return answers.pop(0)

    with _patched((_BD, "execute_boss_scan", _scan),
                  (_BD, "check_failsafe", lambda s: failsafe),
                  (_BD, "wait_while_paused", lambda s, msg: True),
                  (_BD, "log_event", lambda s, kind, **k: logged.append(kind)),
                  (_BD, "_execute_boss_action", lambda s, boss, *a: actions.append(boss.name)),
                  (_BD, "_maybe_execute_async_else", lambda s, step, *a: elses.append(step)),
                  # Der Stack gehört in den Logger, nicht in die Testausgabe.
                  (_BD, "logger", type("_Silent", (), {"exception": staticmethod(lambda *a, **k: None)}))):
        _r, out = _quiet(_BD._boss_async_thread, st, step, 1, 1, "LOOP")
    return actions, elses, logged, out, st, answers


_drache = _BP("Drache")
_a, _e, *_ = _thread(_STEP(boss_scan="B"), [(True, _drache)])
check("Async-Scan: erkannt → Aktion", _a == ["Drache"] and not _e)
_a, _e, *_ = _thread(_STEP(boss_scan="B"), [(False, None)])
check("Async-Scan: nichts erkannt → ELSE", _a == [] and len(_e) == 1)
_a, _e, _l, _out, _st, _ = _thread(_STEP(boss_scan="B"), [], failsafe=True)
check("Async-Scan: die Notbremse stoppt vor dem Scan", _a == [] and _st.stop_event.is_set())
_a, _e, _l, _out, _st, _left = _thread(_STEP(boss_watcher="B"), [(False, None), (True, _drache)])
check("Watcher: scannt, bis ein Boss kommt, dann die Aktion", _a == ["Drache"] and _left == [])
_a, _e, _l, _out, _st, _left = _thread(_STEP(boss_watcher="B"), [(False, None)] * 5, max_scans=2)
check("Watcher: hört nach max. Scans auf, ohne Aktion", _a == [] and len(_left) == 3)
_ticks = iter(range(100))
with _patched((_BD, "time", type("_Clock", (), {"time": staticmethod(lambda: next(_ticks))}))):
    _a, _e, _l, _out, _st, _left = _thread(_STEP(boss_watcher="B"), [(False, None)] * 5, timeout=1.5)
check("Watcher: hört nach dem Timeout auf (Uhr: 1 s je Blick)", _a == [] and len(_left) == 3)
_a, _e, _l, _out, _st, _ = _thread(_STEP(boss_scan="B"), [], boom=True)
check("ein Fehler im Thread wird gemeldet und geloggt, nicht verschluckt",
      _l == ["boss_async_error"] and "fehlgeschlagen" in _out and not _st.llm_action_event.is_set())
