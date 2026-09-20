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
finally:
    _os.chdir(_cwd)
    _sh.rmtree(_sandbox, ignore_errors=True)

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
