"""Bericht: die Laufzeit aufgeteilt in geplant, auf Farbe, Pause und Rest.

Bis hierhin stand im Log nur, WAS passierte — die Zeit dazwischen musste man aus
den Zeitstempeln erraten. Zwei Stellschrauben stecken darin, und sie gehören
verschiedenen Leuten: die Wartezeit am Block stellt man selbst ein, wie lange
ein Farb-Trigger braucht, entscheidet das Spiel. Deshalb schreibt der Lauf
beides getrennt mit (`wait`, `color_wait`) und die Pause dazu (`pause`), damit
sie aus beiden herausgerechnet werden kann.
"""
import contextlib as _cl
import csv as _csv
import io as _io
import shutil as _sh
import sys as _sys
import tempfile as _tmp
import threading as _th
from pathlib import Path as _P

from ._harness import check, section, studio_web_source
from autoclicker.models import (
    AutoClickerState as _ST, SequenceStep as _STEP, WaitCondition as _WC,
)
import autoclicker.runtime.actions as _A
import autoclicker.runtime.steps as _S

_ROOT = str(_P(__file__).resolve().parents[2])
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)
from tools.log_report import EVALUATED as _EVALUATED, evaluate as _evaluate  # noqa: E402

_COLUMNS = ["timestamp", "elapsed_sec", "event", "detail", "x", "y", "extra"]


def _log(path: _P, lines: list) -> _P:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = _csv.writer(f)
        w.writerow(_COLUMNS)
        w.writerows(lines)
    return path


class _Recorder:
    """Ein Session-Log, das nur mitschreibt, was ankommt."""

    def __init__(self):
        self.rows = []

    def log(self, event, detail="", x=None, y=None, extra=""):
        self.rows.append((event, detail, extra))

    def of(self, event):
        return [r for r in self.rows if r[0] == event]


def _secs(extra: str) -> float:
    return float(dict(p.split("=", 1) for p in extra.split(","))["s"])


# =============================================================================
section("Bericht: Wartezeiten getrennt nach geplant und auf Farbe")
# =============================================================================
_sandbox = _P(_tmp.mkdtemp(prefix="report_waits_"))
try:
    _new = _log(_sandbox / "2026-01-01_000000_farm.csv", [
        ("2026-01-01 00:00:00", 0, "session_start", "Farm", "", "", ""),
        ("2026-01-01 00:00:01", 1, "wait", "Bank", "", "", "s=10.00"),
        ("2026-01-01 00:00:02", 2, "wait", "Bank", "", "", "s=10.00"),
        ("2026-01-01 00:00:03", 3, "wait", "Truhe", "", "", "s=5.00"),
        ("2026-01-01 00:00:04", 4, "color_wait", "Kampf", 1, 2, "s=300.00,result=timeout"),
        ("2026-01-01 00:00:05", 5, "color_wait", "Kampf", 1, 2, "s=100.00,result=ok"),
        ("2026-01-01 00:00:06", 6, "color_wait", "Knopf", 1, 2, "s=2.00,result=ok"),
        ("2026-01-01 00:00:07", 7, "pause", "", "", "", "s=60.00"),
        ("2026-01-01 00:10:00", 600, "session_end", "Farm", "", "", ""),
    ])
    # Ein Log von vor der Erfassung: seine Laufzeit darf nicht als „Rest"
    # durchgehen, sonst sähe jeder alte Lauf aus wie einer, der nur klickt.
    _old = _log(_sandbox / "2025-12-31_000000_farm.csv", [
        ("2025-12-31 00:00:00", 0, "session_start", "Farm", "", "", ""),
        ("2025-12-31 00:00:01", 1, "click", "Bank", 1, 2, ""),
        ("2025-12-31 01:00:00", 3600, "session_end", "Farm", "", "", ""),
    ])
    _d = _evaluate([_old, _new])
    _w = _d["waits"]
    check("geplant zählt die Wartezeiten der Blöcke zusammen", _w["planned"] == 25.0)
    check("auf Farbe zählt die Farb-Trigger zusammen — ein Timeout mit",
          _w["color"] == 402.0)
    check("die Pause steht für sich", _w["pause"] == 60.0)
    check("gemessen wird nur die Sitzung, die Wartezeiten mitschreibt",
          _w["measured_sessions"] == 1 and _w["measured_duration"] == 600.0)
    check("die Sitzungen sagen, ob sie gemessen sind",
          [s["waits_measured"] for s in _d["sessions"]] == [False, True])
    check("und tragen ihre eigenen Summen",
          _d["sessions"][1]["planned"] == 25.0 and _d["sessions"][1]["color"] == 402.0)
    check("auf Farbe je Block, längste Summe zuerst, mit Anzahl, Maximum und Timeouts",
          _d["color_waits"] == [["Kampf", 400.0, 2, 300.0, 1], ["Knopf", 2.0, 1, 2.0, 0]])
    check("geplant je Block ebenso",
          _d["planned_waits"] == [["Bank", 20.0, 2, 10.0, 0], ["Truhe", 5.0, 1, 5.0, 0]])
    check("keine der neuen Ereignisarten gilt als unbekannt", _d["unknown"] == [])
    check("der Bericht kennt alle drei", {"wait", "color_wait", "pause"} <= _EVALUATED)
finally:
    _sh.rmtree(_sandbox, ignore_errors=True)


# =============================================================================
section("Laufzeit: die geplante Wartezeit wird mitgeschrieben — ohne Pause")
# =============================================================================
_orig_wait = _A.status.waiting_for
_A.status.waiting_for = lambda *a, **k: None
try:
    _st = _ST()
    _st.session_log = _Recorder()
    with _cl.redirect_stdout(_io.StringIO()):
        _A.wait_with_pause_skip(_st, 0.05, "Loop 1", 3, 5, "Warte", label="Bank")
        _A.wait_with_pause_skip(_st, 0.05, "Loop 1", 4, 5, "Warte")
    _rows = _st.session_log.of("wait")
    check("jede Wartezeit steht im Log, mit dem Namen des Blocks",
          [r[1] for r in _rows] == ["Bank", "Loop 1[4]"])
    check("und mit der Zeit, die wirklich gewartet wurde",
          all(0.04 <= _secs(r[2]) < 0.5 for r in _rows))

    # Eine Pause mitten im Warten zählt nicht als Wartezeit.
    _st = _ST()
    _st.session_log = _Recorder()
    _st.config.timing_pause_interval = 0.02
    _st.pause_event.set()
    _th.Timer(0.3, _st.pause_event.clear).start()
    with _cl.redirect_stdout(_io.StringIO()):
        _A.wait_with_pause_skip(_st, 0.05, "L", 1, 1, "Warte", label="Bank")
    _planned = _secs(_st.session_log.of("wait")[0][2])
    _paused = _secs(_st.session_log.of("pause")[0][2])
    check("die Pause steht als eigenes Ereignis im Log", 0.25 <= _paused < 1.0)
    check("und ist aus der geplanten Wartezeit herausgerechnet", _planned < 0.2)
    check("der Lauf merkt sich die Pausenzeit", _st.paused_seconds >= 0.25)
finally:
    _A.status.waiting_for = _orig_wait


# =============================================================================
section("Laufzeit: das Warten auf eine Farbe wird mitgeschrieben, samt Ergebnis")
# =============================================================================
class _Img:
    def __init__(self, color):
        self._color = color

    def getpixel(self, _xy):
        return self._color


_orig = (_S.take_screenshot, _S._handle_color_wait_timeout, _S.status.waiting_for,
         _S.pixel_crop, _S.PILLOW_AVAILABLE)
_S.status.waiting_for = lambda *a, **k: None
_S.pixel_crop = lambda x, y: None
_S.PILLOW_AVAILABLE = True
_S._handle_color_wait_timeout = lambda state, step, phase, n, t, timeout: "stop"
try:
    def _run(seen):
        st = _ST()
        st.session_log = _Recorder()
        st.config.pixel_check_interval = 0.01
        _S.take_screenshot = lambda region: _Img(seen)
        step = _STEP(x=5, y=5, point_id=1, name="Kampf",
                     wait_condition=_WC(point_id=1, pixel=(5, 5), color=(200, 0, 0),
                                        timeout=0.05))
        with _cl.redirect_stdout(_io.StringIO()):
            _S._execute_wait_for_color(st, step, 1, 1, "L")
        return st.session_log.of("color_wait")

    _hit = _run((200, 0, 0))
    check("eine aufgegangene Farbe steht als ok im Log",
          len(_hit) == 1 and _hit[0][1] == "Kampf" and "result=ok" in _hit[0][2])
    _miss = _run((0, 0, 0))
    check("ein Timeout steht als timeout im Log, mit seiner Wartezeit",
          len(_miss) == 1 and "result=timeout" in _miss[0][2]
          and 0.04 <= _secs(_miss[0][2]) < 0.8)
finally:
    (_S.take_screenshot, _S._handle_color_wait_timeout, _S.status.waiting_for,
     _S.pixel_crop, _S.PILLOW_AVAILABLE) = _orig


# =============================================================================
section("Reiter: die Aufteilung kommt an und wird gezeichnet")
# =============================================================================
_web = studio_web_source()
check("die Seite zeichnet die Aufteilung",
      "repWaitSplit(b.waits" in _web and "rep-split" in _web)
check("und beide Ranglisten",
      "b.color_waits" in _web and "b.planned_waits" in _web)
check("jede der vier Farben ist definiert",
      all(f"--wait-{k}:" in _web for k in ("planned", "color", "pause", "rest")))
