"""Folgesequenz: ist eine Sequenz fertig, startet die nächste — nach einer Pause.

Zwei eigenständige Sequenzen, verbunden über einen Namen (`next_sequence`) und
eine Pause (`next_delay`). Der Worker legt beim regulären Ende ab, was dran ist;
der Main-Thread lädt die Folgesequenz und stellt einen Countdown — derselbe
Start wie ein Druck auf CTRL+ALT+S, nur verzögert.

Gemessen wird der ganze Weg: Datei, echter Worker-Durchlauf, Abholung im
Main-Thread, Countdown. Dazu der Fehler, der dabei aufgefallen ist: ein
Countdown nach einem beendeten Lauf brach sofort ab, weil der Worker
`stop_event` gesetzt hinterlässt.
"""
from ._harness import check, section

import contextlib as _cl
import io as _io
import json as _json
import os as _os
import shutil as _sh
import tempfile as _tmp
import time as _time

from autoclicker.models import (
    AutoClickerState as _ST,
    LoopPhase as _PHASE,
    Sequence as _SEQ,
    SequenceStep as _STEP,
)
from autoclicker.persistence import (
    load_sequence_file, save_sequence_file, sequence_file,
)
from autoclicker.persistence.serialization import _sequence_to_dict
import autoclicker.handlers as _hnd
import autoclicker.runtime.worker as _W
from autoclicker.runtime import status as _run_status


def _quiet(fn):
    with _cl.redirect_stdout(_io.StringIO()):
        return fn()


def _write(name: str, **fields) -> _SEQ:
    seq = _SEQ(name, loop_phases=[_PHASE("L", steps=[_STEP(key_press="a")])], **fields)
    path = sequence_file(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    save_sequence_file(seq, path)
    return seq


def _wait_countdown_end(state: _ST, seconds: float = 3.0) -> None:
    end = _time.time() + seconds
    while state.countdown_active and _time.time() < end:
        _time.sleep(0.02)


_sandbox = _tmp.mkdtemp(prefix="folgesequenz_")
_cwd = _os.getcwd()
_os.chdir(_sandbox)
_orig_step = _W.execute_step
try:
    # =====================================================================
    section("Folgesequenz: Dateiformat")

    check("ohne Folgesequenz steht nichts davon in der Datei",
          not ({"next_sequence", "next_delay"} & set(_sequence_to_dict(_SEQ("A")))))
    check("die Standardpause wird nicht geschrieben",
          "next_delay" not in _sequence_to_dict(_SEQ("A", next_sequence="B")))

    _write("B")
    _write("A", next_sequence="B", next_delay=45.0)
    _a = load_sequence_file(sequence_file("A"))
    check("Name und Pause überleben Speichern und Laden",
          _a.next_sequence == "B" and _a.next_delay == 45.0)

    _raw = _json.loads(sequence_file("A").read_text(encoding="utf-8"))
    _raw["next_delay"] = "kaputt"
    sequence_file("A").write_text(_json.dumps(_raw), encoding="utf-8")
    _a = _quiet(lambda: load_sequence_file(sequence_file("A")))
    check("eine unlesbare Pause wirft den Loader nicht, sondern wird 30 s",
          _a is not None and _a.next_delay == 30.0)
    _a = _write("A", next_sequence="B", next_delay=45.0)

    # =====================================================================
    section("Folgesequenz: nur nach einem regulären Ende")

    def _ended(**events):
        st = _ST()
        for name in events.get("set", ()):
            getattr(st, name).set()
        if events.get("limit"):
            st.session_limit_hit = True
        if events.get("brake"):
            st.consecutive_timeouts = st.config.pixel_max_consecutive_timeouts
        return _quiet(lambda: _W._follow_up(st, _a))

    check("alle Zyklen durch → B ist dran", _ended() == ("B", 45.0, "A"))
    check("CTRL+ALT+F → B ist dran", _ended(set=("finish_event", "stop_event")) is not None)
    check("Stopp von Hand → nichts", _ended(set=("stop_event",)) is None)
    check("Zeitlimit → nichts (es ist eine Obergrenze der Sitzung)", _ended(limit=True) is None)
    check("Notbremse → nichts", _ended(brake=True) is None)
    check("Programmende → nichts", _ended(set=("quit_event",)) is None)
    check("ohne eingetragene Folgesequenz → nichts",
          _quiet(lambda: _W._follow_up(_ST(), _SEQ("X"))) is None)

    # =====================================================================
    section("Folgesequenz: ein echter Durchlauf legt sie ab")

    _W.execute_step = lambda state, step, n, total, phase: True
    _st = _ST()
    _st.active_sequence = _a
    _st.is_running = True
    _quiet(lambda: _W.sequence_worker(_st))
    check("der Worker legt die Folgesequenz ab", _st.next_start == ("B", 45.0, "A"))
    check("und hinterlässt stop_event gesetzt — die Falle für den Countdown",
          _st.stop_event.is_set())

    # =====================================================================
    section("Folgesequenz: der Main-Thread lädt B und stellt den Countdown")

    _quiet(lambda: _hnd.start_next_if_pending(_st))
    check("B ist die aktive Sequenz", _st.active_sequence.name == "B")
    check("die Vormerkung ist verbraucht", _st.next_start is None)
    _time.sleep(0.3)
    check("der Countdown läuft — ein altes stop_event bricht ihn nicht mehr ab",
          _st.countdown_active is True)
    _status = _json.loads(_run_status.STATUS_PATH.read_text(encoding="utf-8"))
    check("die Live-Ansicht nennt B und die Sequenz davor",
          _status.get("countdown") and _status.get("sequence") == "B"
          and _status.get("after") == "A")
    check("die Wartezeit ist die eingetragene",
          40 < _status.get("target_time", 0) - _time.time() <= 45)

    _st.stop_event.set()                               # CTRL+ALT+S während der Pause
    _quiet(lambda: _wait_countdown_end(_st))
    check("CTRL+ALT+S in der Pause bricht ab, gestartet wird nichts",
          not _st.countdown_active and not _st.is_running)

    # =====================================================================
    section("Folgesequenz: was dazwischenkommt, gewinnt")

    _st = _ST()
    _st.next_start = ("B", 30.0, "A")
    _st.is_running = True                              # jemand hat schon gestartet
    _quiet(lambda: _hnd.start_next_if_pending(_st))
    check("ein inzwischen gestarteter Lauf wird nicht überstimmt",
          _st.next_start is None and not _st.countdown_active and _st.active_sequence is None)

    _st = _ST()
    _st.next_start = ("Gibt es nicht", 30.0, "A")
    _out = _io.StringIO()
    with _cl.redirect_stdout(_out):
        _hnd.start_next_if_pending(_st)
    check("eine fehlende Folgesequenz wird gemeldet, samt der Sequenz, die sie nennt",
          "Gibt es nicht" in _out.getvalue() and "'A'" in _out.getvalue())
    check("und es startet nichts", not _st.countdown_active and _st.active_sequence is None)

    # =====================================================================
    section("Folgesequenz: Diagnose und Studio")

    from autoclicker.diagnostics import CheckReport, _check_sequences
    _write("C", next_sequence="Weg")
    _report = CheckReport()
    _quiet(lambda: _check_sequences(_ST(), _report))
    _hits = [f for f in _report.findings if "Weg" in str(f)]
    check("die Diagnose meldet eine Folgesequenz, die es nicht gibt", len(_hits) == 1)
    check("und keine, die es gibt",
          not any("'B'" in str(f) and "Folgesequenz" in str(f) for f in _report.findings))

    from autoclicker.editors.sequence_studio.bridge import StudioBridge
    _b = _quiet(lambda: StudioBridge(load_sequence_file(sequence_file("A")),
                                     sequence_file("A"), "sequences"))
    _snap = _b.snapshot()
    check("die Momentaufnahme trägt Folgesequenz und Pause",
          _snap["next_sequence"] == "B" and _snap["next_delay"] == 45.0)
    _quiet(lambda: _b.sequence_set({"field": "next_sequence", "value": "Gibt es nicht"}))
    check("das Studio lehnt einen Namen ab, den es nicht gibt", _b.board.next_sequence == "B")
    _quiet(lambda: _b.sequence_set({"field": "next_delay", "value": -5}))
    check("eine negative Pause wird 0", _b.board.next_delay == 0.0)
    _quiet(lambda: _b.sequence_set({"field": "next_sequence", "value": "A"}))
    _quiet(lambda: _b.sequence_set({"field": "name", "value": "A neu"}))
    check("„danach diese nochmal“ zieht beim Umbenennen mit",
          _b.board.next_sequence == "A neu")
    _quiet(lambda: _b.sequence_set({"field": "next_sequence", "value": ""}))
    check("leer = keine Folgesequenz", _b.board.next_sequence == "")
finally:
    _W.execute_step = _orig_step
    _os.chdir(_cwd)
    _sh.rmtree(_sandbox, ignore_errors=True)
