"""Boss-Scan- und Boss-Watcher-Schritt (`runtime/steps.py`), festgehalten.

Geschrieben, BEVOR `_execute_boss_scan_step` und `_execute_boss_watcher_step`
(je 16) zerlegt wurden — beide standen bis dahin nur mit je einem Fall in der
Suite. Die Erkennung selbst ist gestellt (sie hat `boss_detection_flow`);
gemessen wird, was der Schritt aus einem Treffer, einem Fehlschlag, einem
Fallback oder einer Grenze macht.
"""
import contextlib as _cl
import io as _io

from ._harness import check, section

import autoclicker.runtime.steps as _RS
from autoclicker.models import (
    AutoClickerState as _ST, BossProfile as _BP, BossScanConfig as _BSC,
    ElseConfig as _EC, SequenceStep as _STEP,
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


class _Step:
    """Ein Boss-Schritt mit gestellter Erkennung und gestellten Folgen."""

    def __init__(self, scans=(), default_action="skip", default_scan=None, known=True,
                 run_async=False, results=(), result_ok=True, paused_ok=True, interval_stop=False):
        self.state = _ST()
        if known:
            self.state.boss_scans["B"] = _BSC("B", bosses=[_BP("Drache")],
                                              default_action=default_action,
                                              default_scan=default_scan)
        self.scans, self.results = list(scans), list(results)
        self.run_async, self.result_ok, self.paused_ok = run_async, result_ok, paused_ok
        self.interval_stop = interval_stop
        self.calls, self.output = [], ""

    def _scan(self, state, name):
        self.calls.append("scan")
        if not self.scans:
            state.stop_event.set()         # mehr Scans als vorgesehen: anhalten statt drehen
            return False, None
        return self.scans.pop(0)

    def _click(self, state, pos, item, prio, debug):
        self.calls.append(f"klick:{item}")
        return self.result_ok

    def run(self, step, clock=None):
        stubs = [
            (_RS, "_should_run_async", lambda state, name: self.run_async),
            (_RS, "_spawn_boss_async", lambda *a: self.calls.append("async")),
            (_RS, "_warn_llm_config_inconsistencies", lambda *a: None),
            (_RS, "execute_boss_scan", self._scan),
            (_RS, "_execute_boss_action",
             lambda state, boss, *a: self.calls.append(f"aktion:{boss.name}") or "aktion"),
            (_RS, "execute_else_action", lambda *a: self.calls.append("else") or "else"),
            (_RS, "execute_item_scan",
             lambda state, name, *a: self.calls.append(f"itemscan:{name}") or list(self.results)),
            (_RS, "_click_scan_result", self._click),
            (_RS, "wait_while_paused", lambda state, msg: self.paused_ok),
            (_RS.status, "heartbeat", lambda state: self.calls.append("puls")),
        ]
        if clock is not None:
            stubs.append((_RS, "time", clock))
        if self.interval_stop:
            original_wait = self.state.stop_event.wait
            self.state.stop_event.wait = lambda t=None: True   # Stopp während des Intervalls
        buffer = _io.StringIO()
        with _patched(*stubs), _cl.redirect_stdout(buffer):
            if step.boss_watcher:
                self.result = _RS._execute_boss_watcher_step(self.state, step, 1, 1, "LOOP")
            else:
                self.result = _RS._execute_boss_scan_step(self.state, step, 1, 1, "LOOP")
        if self.interval_stop:
            self.state.stop_event.wait = original_wait
        self.output = buffer.getvalue()
        return self


_drache = _BP("Drache")

# =============================================================================
section("Boss-Scan-Schritt: Treffer, ELSE, Fallback")
# =============================================================================
_r = _Step(run_async=True).run(_STEP(boss_scan="B"))
check("asynchron: Thread starten und weiter", _r.result is True and _r.calls == ["async"])
_r = _Step(scans=[(True, _drache)]).run(_STEP(boss_scan="B"))
check("Treffer: die Aktion des Bosses entscheidet",
      _r.result == "aktion" and _r.calls == ["scan", "aktion:Drache"])
_r = _Step(scans=[(False, None)]).run(_STEP(boss_scan="B", else_config=_EC(action="skip")))
check("kein Treffer mit ELSE: das ELSE entscheidet", _r.result == "else" and _r.calls[-1] == "else")
_r = _Step(scans=[(False, None)]).run(_STEP(boss_scan="B"))
check("kein Treffer, Fallback skip: weiter", _r.result is True and "Kein Boss erkannt" in _r.output)
_r = _Step(scans=[(False, None)], default_action="skip_cycle").run(_STEP(boss_scan="B"))
check("Fallback skip_cycle: Ereignis und Abbruch",
      _r.result is False and _r.state.skip_cycle_event.is_set())
_r = _Step(scans=[(False, None)], default_action="restart").run(_STEP(boss_scan="B"))
check("Fallback restart: Ereignis und Abbruch", _r.result is False and _r.state.restart_event.is_set())
_r = _Step(scans=[(False, None)], default_action="item_scan", default_scan="inv",
           results=[((1, 1), "a", 1), ((2, 2), "b", 2)]).run(_STEP(boss_scan="B"))
check("Fallback Item-Scan: jeder Treffer wird geklickt",
      _r.result is True and _r.calls == ["scan", "itemscan:inv", "klick:a", "klick:b"])
_r = _Step(scans=[(False, None)], default_action="item_scan", default_scan="inv",
           results=[((1, 1), "a", 1), ((2, 2), "b", 2)], result_ok=False).run(_STEP(boss_scan="B"))
check("Fallback Item-Scan: ein abgebrochener Klick bricht ab",
      _r.result is False and _r.calls[-1] == "klick:a")
_r = _Step(scans=[(False, None)], default_action="item_scan", default_scan="inv",
           results=[((1, 1), "a", 1), ((2, 2), "b", 2)])
_r._click = lambda state, pos, item, prio, debug: (_r.calls.append(f"klick:{item}"),
                                                   state.stop_event.set()) and True
_r.run(_STEP(boss_scan="B"))
check("Fallback Item-Scan: nach einem Stopp wird nicht weitergeklickt",
      _r.result is False and _r.calls[-1] == "klick:a")
_r = _Step(scans=[(False, None)], default_action="item_scan").run(_STEP(boss_scan="B"))
check("Fallback Item-Scan ohne Scan-Namen: nichts", _r.result is True and "itemscan" not in str(_r.calls))
_r = _Step(scans=[(False, None)], default_action="click")
_r.run(_STEP(boss_scan="B"))
_first = _r.output
_r.scans = [(False, None)]
_r.run(_STEP(boss_scan="B"))
check("ein Fallback, den es ohne Boss nicht gibt, wird einmal je Lauf gesagt",
      "nicht ausfuehrbar" in _first and "nicht ausfuehrbar" not in _r.output and _r.result is True)
_r = _Step(scans=[(False, None)], known=False).run(_STEP(boss_scan="B"))
check("ein unbekannter Scan ohne ELSE läuft weiter", _r.result is True)

# =============================================================================
section("Boss-Watcher-Schritt: Grenzen, Überspringen, Pause")
# =============================================================================
_r = _Step(run_async=True).run(_STEP(boss_watcher="B"))
check("asynchron: Thread starten und weiter", _r.result is True and _r.calls == ["async"])
_r = _Step(known=False).run(_STEP(boss_watcher="B"))
check("unbekannter Watcher wird gesagt", _r.result is True and "nicht gefunden" in _r.output)
_r = _Step(scans=[(False, None), (True, _drache)])
_r.state.config.llm_watcher_interval = 0
_r.run(_STEP(boss_watcher="B"))
check("scannt bis zum Treffer, dann die Aktion; jeder Durchgang ein Lebenszeichen",
      _r.result == "aktion" and _r.calls == ["puls", "scan", "puls", "scan", "aktion:Drache"])
_r = _Step(scans=[(False, None)] * 5)
_r.state.config.llm_watcher_interval, _r.state.config.llm_watcher_max_scans = 0, 2
_r.run(_STEP(boss_watcher="B"))
check("max. Scans: hört auf und läuft weiter",
      _r.result is True and _r.calls.count("scan") == 2 and "max. Scans (2)" in _r.output)
_ticks = iter(range(100))
_r = _Step(scans=[(False, None)] * 5)
_r.state.config.llm_watcher_interval, _r.state.config.llm_watcher_timeout = 0, 1.5
_r.run(_STEP(boss_watcher="B"), clock=type("_Clock", (), {"time": staticmethod(lambda: next(_ticks))}))
check("Timeout: hört auf und läuft weiter (Uhr: 1 s je Blick)",
      _r.result is True and _r.calls.count("scan") == 2 and "Timeout (2s)" in _r.output)
_r = _Step(scans=[(False, None)] * 3)
_r.state.skip_event.set()
_r.run(_STEP(boss_watcher="B"))
check("CTRL+ALT+K überspringt und wird verbraucht",
      _r.result is True and not _r.state.skip_event.is_set() and "scan" not in _r.calls)
_r = _Step(scans=[(False, None)] * 3)
_r.state.skip_step_event.set()
_r.run(_STEP(boss_watcher="B"))
check("Block-Skip überspringt und wird verbraucht",
      _r.result is True and not _r.state.skip_step_event.is_set())
_r = _Step(scans=[(False, None)] * 3, paused_ok=False).run(_STEP(boss_watcher="B"))
check("eine gestoppte Pause bricht ab", _r.result is False and "scan" not in _r.calls)
_r = _Step(scans=[(False, None)] * 3, interval_stop=True)
_r.run(_STEP(boss_watcher="B"))
check("ein Stopp im Intervall bricht ab", _r.result is False and _r.calls.count("scan") == 1)
