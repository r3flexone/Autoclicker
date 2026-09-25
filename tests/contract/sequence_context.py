"""Sequenzwechsel: wer die Sequenz wechselt, wechselt Punkte UND Scans.

Die drei Zeilen dafür standen an fünf Stellen in `handlers.py` und im
Konsolen-Editor — und zweimal fehlte ein Teil. Das Punkte-Menü (CTRL+ALT+P)
setzte Sequenz und Punkte, liess aber die Scans der vorigen im Speicher: ein
Start danach lief mit B-Schritten gegen A-Scans. Der Konsolen-Editor
bearbeitete B mit den Punkten der gerade aktiven A und schrieb B mit A's Pool
zurück. Seit `activate_sequence()` gibt es die eine Stelle, und hier wird
gemessen, dass jeder Weg sie nimmt.
"""
import contextlib as _cl
import io as _io
import json as _json
import os as _os
import shutil as _sh
import tempfile as _tmp

from ._harness import check, section
from autoclicker.models import (
    AutoClickerState as _ST,
    ItemScanConfig as _ISC,
    ItemSlot as _SLOT,
    ClickPoint as _CP,
    LoopPhase as _PHASE,
    Sequence as _SEQ,
    SequenceStep as _STEP,
)
from autoclicker.persistence import (
    activate_sequence, save_sequence_file, sequence_file, save_item_scan,
)
import autoclicker.handlers as _hnd
import autoclicker.editors.sequence_editor.editor as _ed


def _make(name: str, point_id: int, xy: tuple) -> _SEQ:
    """Eine Sequenz mit EINEM eigenen Punkt und einem Scan-Schritt."""
    seq = _SEQ(name, points=[_CP(xy[0], xy[1], f"P{point_id}", point_id)],
               loop_phases=[_PHASE("L", steps=[
                   _STEP(point_id=point_id, delay_before=0),
                   _STEP(item_scan="inv", delay_before=0)])])
    path = sequence_file(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    save_sequence_file(seq, path)
    cfg = _ISC("inv", slots=[_SLOT(f"Slot-{name}", (0, 0, 10, 10), (5, 5))],
               owner_sequence=name)
    with _cl.redirect_stdout(_io.StringIO()):
        save_item_scan(cfg)
    return seq


_sandbox = _tmp.mkdtemp(prefix="kontext_")
_cwd = _os.getcwd()
_os.chdir(_sandbox)
_quiet = _cl.redirect_stdout(_io.StringIO())
try:
    _a = _make("A", 1, (10, 10))
    _b = _make("B", 7, (70, 70))

    # =========================================================================
    section("activate_sequence: Punkte und Scans wechseln gemeinsam")
    # =========================================================================
    _st = _ST()
    with _quiet:
        activate_sequence(_st, _a)
    check("die Sequenz ist aktiv und ihre Punkte sind die Arbeitsansicht",
          _st.active_sequence is _a and _st.points is _a.points)
    check("ihre Scans sind geladen",
          [s.name for s in _st.item_scans["inv"].slots] == ["Slot-A"])
    with _quiet:
        activate_sequence(_st, _b)
    check("der Wechsel ersetzt die Scans vollstaendig",
          [s.name for s in _st.item_scans["inv"].slots] == ["Slot-B"]
          and _st.points is _b.points)
    check("und die Schritte kennen ihre Stelle",
          (_b.loop_phases[0].steps[0].x, _b.loop_phases[0].steps[0].y) == (70, 70))

    # =========================================================================
    section("CTRL+ALT+P wechselt die Scans mit")
    # =========================================================================
    _st = _ST()
    _orig_select, _orig_input = _hnd.interactive_select, _hnd.safe_input
    try:
        _hnd.interactive_select = lambda *a, **k: 0        # "A"
        with _quiet:
            _hnd.handle_switch(_st)
        _hnd.interactive_select = lambda *a, **k: 1        # "B"
        _hnd.safe_input = lambda *a, **k: "d"              # Menue gleich zu
        with _quiet:
            _hnd.handle_show(_st)
    finally:
        _hnd.interactive_select, _hnd.safe_input = _orig_select, _orig_input
    check("nach dem Punkte-Menue ist B aktiv",
          _st.active_sequence is not None and _st.active_sequence.name == "B")
    check("und die Scans gehoeren zu B — nicht mehr zu A",
          [s.name for s in _st.item_scans["inv"].slots] == ["Slot-B"])

    # =========================================================================
    section("Konsolen-Editor: B behaelt seine eigenen Punkte")
    # =========================================================================
    _st = _ST()
    with _quiet:
        activate_sequence(_st, _a)                         # A ist aktiv ...
    _a_file_before = sequence_file("A").read_text(encoding="utf-8")
    _a.description = "nur im Speicher geaendert"           # ... und im Speicher veraltet
    _orig = (_ed.edit_phase, _ed.edit_loop_phases, _ed._ask_total_cycles, _ed.safe_input)
    try:
        _ed.edit_phase = lambda state, steps, label: list(steps)
        _ed.edit_loop_phases = lambda state, phases: phases
        _ed._ask_total_cycles = lambda current: current
        _ed.safe_input = lambda *a, **k: ""
        with _quiet:
            _ed.edit_sequence(_st, _b)                     # ... waehrend B bearbeitet wird
    finally:
        _ed.edit_phase, _ed.edit_loop_phases, _ed._ask_total_cycles, _ed.safe_input = _orig
    _saved_b = _json.loads(sequence_file("B").read_text(encoding="utf-8"))
    check("B wird mit SEINEN Punkten gespeichert, nicht mit denen von A",
          [p["id"] for p in _saved_b["points"]] == [7]
          and _saved_b["points"][0]["x"] == 70)
    check("B ist danach die aktive Sequenz — samt ihren Scans",
          _st.active_sequence.name == "B"
          and [s.name for s in _st.item_scans["inv"].slots] == ["Slot-B"])
    check("A's Datei bleibt unangetastet — geschrieben wird nur, was bearbeitet wurde",
          sequence_file("A").read_text(encoding="utf-8") == _a_file_before)

    # Der Editor braucht Punkte — aber die der GEWAEHLTEN Sequenz.
    _st = _ST()
    _empty = _SEQ("leer")
    _p = sequence_file("leer")
    _p.parent.mkdir(parents=True, exist_ok=True)
    save_sequence_file(_empty, _p)
    with _quiet:
        activate_sequence(_st, _empty)                    # aktiv ist eine OHNE Punkte
    _out = _io.StringIO()
    _orig = (_ed.edit_phase, _ed.edit_loop_phases, _ed._ask_total_cycles, _ed.safe_input)
    try:
        _ed.edit_phase = lambda state, steps, label: list(steps)
        _ed.edit_loop_phases = lambda state, phases: phases
        _ed._ask_total_cycles = lambda current: current
        _ed.safe_input = lambda *a, **k: ""
        with _cl.redirect_stdout(_out):
            _ed.edit_sequence(_st, _b)
    finally:
        _ed.edit_phase, _ed.edit_loop_phases, _ed._ask_total_cycles, _ed.safe_input = _orig
    check("eine Sequenz mit Punkten laesst sich bearbeiten, auch wenn die aktive keine hat",
          "Erst Punkte aufnehmen" not in _out.getvalue()
          and _st.active_sequence.name == "B")

    # =========================================================================
    section("CTRL+ALT+L laedt die Scans mit")
    # =========================================================================
    # Der Konsolen-Loader — derselbe Weg liegt unter CTRL+ALT+S und CTRL+ALT+T,
    # wenn noch nichts geladen ist — setzte Sequenz und Punkte von Hand. Nach
    # einem frischen Start hatte der Lauf damit GAR keine Scans ("Item-Scan
    # nicht gefunden"), nach einem Wechsel die der vorigen Sequenz.
    import autoclicker.editors.sequence_editor.loader as _ld

    def _pick(name):
        return lambda opts, **k: next(i for i, o in enumerate(opts)
                                      if o.startswith(name + " ("))

    _orig_select = _ld.interactive_select
    try:
        _st = _ST()                                        # wie nach dem Programmstart
        _ld.interactive_select = _pick("A")
        with _quiet:
            _ld.run_sequence_loader(_st)
        check("nach einem frischen Start sind die Scans der geladenen Sequenz da",
              _st.active_sequence.name == "A" and "inv" in _st.item_scans
              and [s.name for s in _st.item_scans["inv"].slots] == ["Slot-A"])
        _ld.interactive_select = _pick("B")
        with _quiet:
            _ld.run_sequence_loader(_st)
        check("ein Wechsel ersetzt sie — keine Scans der vorigen Sequenz",
              _st.active_sequence.name == "B" and "inv" in _st.item_scans
              and [s.name for s in _st.item_scans["inv"].slots] == ["Slot-B"])
    finally:
        _ld.interactive_select = _orig_select

    # =========================================================================
    section("Nach einer Aufnahme gehoeren die Scans zur neuen Sequenz")
    # =========================================================================
    import time as _time
    import autoclicker.editors.sequence_recorder as _rec
    from autoclicker.models import RecordEvent as _RE, REC_CLICK as _RC

    _st = _ST()
    with _quiet:
        activate_sequence(_st, _a)                         # A mit Scan "inv" ist aktiv
    _st.recording_active = True
    _st.recording_events = [_RE(_RC, _time.monotonic(), 5, 6, (1, 2, 3))]
    _st.recording_ui_name = "Frisch"
    _hooks = (_rec.remove_mouse_hook, _rec.remove_keyboard_hook)
    _rec.remove_mouse_hook = _rec.remove_keyboard_hook = lambda: None
    try:
        with _quiet:
            _rec.stop_recording(_st)
    finally:
        _rec.remove_mouse_hook, _rec.remove_keyboard_hook = _hooks
    check("die Aufnahme ist die aktive Sequenz",
          _st.active_sequence is not None and _st.active_sequence.name == "Frisch")
    check("und die Scans von A sind nicht mehr geladen — die neue hat keine",
          _st.item_scans == {})
finally:
    _os.chdir(_cwd)
    _sh.rmtree(_sandbox, ignore_errors=True)

# =============================================================================
section("Niemand setzt die aktive Sequenz von Hand")
# =============================================================================
# Die Regel steht in CLAUDE.md, und zweimal hat sie ein Ladeweg trotzdem
# umgangen (Konsolen-Loader, Ende einer Aufnahme): beide Male blieben die
# Scans der vorigen Sequenz im Speicher. Eine Regel, an die man sich erinnern
# muss, ist keine — also misst sie dieser Test. `= None` (Factory-Reset) ist
# kein Wechsel und bleibt erlaubt.
import re as _re
from pathlib import Path as _P

_pkg = _P(__file__).resolve().parent.parent.parent / "autoclicker"
_owner = _pkg / "persistence" / "sequences.py"
_by_hand = [
    f"{_file.relative_to(_pkg)}:{_nr}"
    for _file in sorted(_pkg.rglob("*.py")) if _file != _owner
    for _nr, _line in enumerate(_file.read_text(encoding="utf-8").splitlines(), 1)
    if _re.search(r"\.active_sequence\s*=(?!=)\s*(?!None\b)\S", _line)
]
check("state.active_sequence wird nur in activate_sequence() gesetzt"
      + (f" — von Hand: {', '.join(_by_hand)}" if _by_hand else ""),
      not _by_hand)

# =============================================================================
section("Es gibt EINE geladene Sequenz — keinen Cache daneben")
# =============================================================================
# `state.sequences` war ein Dict, das nur ein Teil der Ladewege pflegte
# (Konsolen-Editor, Aufnahme, Import; Quick-Switch und Studio-Start nicht), und
# `save_data()` schrieb es KOMPLETT zurueck: eine Aufnahme von vorhin kam aus dem
# Speicher auf die Platte, obwohl das Studio sie laengst geaendert hatte.
import autoclicker.persistence as _pers
check("AutoClickerState hat keinen Sequenz-Cache mehr",
      not hasattr(_ST(), "sequences"))
check("und save_data() gibt es nicht mehr — geschrieben wird die aktive Sequenz",
      not hasattr(_pers, "save_data") and callable(_pers.save_points))
