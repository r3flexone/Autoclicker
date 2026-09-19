"""Haltepunkt: der Lauf geht bis zu einem Block und hält dort an.

**Ein Haltepunkt ist das Gate des manuellen Modus an genau EINER Stelle.** Der
manuelle Modus hält vor jedem Block und fragt; `step.breakpoint` hält vor
diesem einen — und danach läuft die Sequenz normal weiter. Gemessen wird
alles, was daran hängt: dass das Feld die Datei überlebt, dass das Gate ohne
Schrittmodus anhält, dass die fünf Entscheidungen dasselbe tun, egal ob sie
per Taste, per Hotkey (CTRL+ALT+G) oder aus dem Studio kommen — und dass
„ab hier schrittweise" wirklich in den Schrittmodus führt.
"""
import threading
import time
from pathlib import Path

from ._harness import check, section
from autoclicker.models import (
    AutoClickerState as _ST,
    LoopPhase as _PHASE,
    Sequence as _SEQ,
    SequenceStep as _STEP,
)
import autoclicker.runtime.debug as _dbg
import autoclicker.runtime.status as _status
import autoclicker.handlers as _hnd
from autoclicker.persistence.serialization import (
    _step_to_dict as _s2d, _parse_steps as _p2s, _STEP_DEFAULTS as _SD)


# =============================================================================
section("Haltepunkt: Modell und Datei")
# =============================================================================

check("ein neuer Schritt hat keinen Haltepunkt", _STEP(x=1, y=2).breakpoint is False)
check("der Datei-Default steht in der Tabelle", _SD.get("breakpoint") is False)
_ohne = _s2d(_STEP(x=1, y=2, delay_before=0, point_id=3))
check("ohne Haltepunkt steht nichts davon in der Datei", "breakpoint" not in _ohne)
_mit = _s2d(_STEP(x=1, y=2, delay_before=0, point_id=3, breakpoint=True))
check("mit Haltepunkt wird er geschrieben", _mit.get("breakpoint") is True)
_zurueck = _p2s([_mit])[0]
check("und kommt beim Laden wieder", _zurueck.breakpoint is True)
check("ein fehlendes Feld in einer alten Datei heisst: kein Haltepunkt",
      _p2s([{"point_id": 3, "delay_before": 0}])[0].breakpoint is False)
check("die Schrittbeschreibung sagt es vorneweg",
      str(_STEP(x=1, y=2, delay_before=0, breakpoint=True)).startswith("[HALT] ")
      and not str(_STEP(x=1, y=2, delay_before=0)).startswith("[HALT]"))


# =============================================================================
section("Haltepunkt: das Gate haelt ohne Schrittmodus an")
# =============================================================================

def _state():
    st = _ST()
    st.step_mode = False
    st.step_via_studio = False
    st.run_from_studio = False
    st.stop_event.clear()
    return st


_halt = _STEP(x=100, y=200, delay_before=0, name="Halt hier", breakpoint=True)
_frei = _STEP(x=100, y=200, delay_before=0, name="Laeuft durch")
_orig_read = _dbg.read_command
_orig_cursor = _dbg.set_cursor_pos
_dbg.set_cursor_pos = lambda *a, **k: None
try:
    # Ohne Haltepunkt und ohne Schrittmodus fragt niemand — und liest auch keine Taste.
    _gefragt = []
    _dbg.read_command = lambda *a, **k: _gefragt.append(1) or "w"
    _st = _state()
    check("ein Block ohne Haltepunkt laeuft ungefragt durch",
          _dbg.step_gate(_st, _frei, "LOOP", 1, 2) == _dbg.GATE_RUN and not _gefragt)

    # Mit Haltepunkt haelt das Gate — dieselben Tasten wie im manuellen Modus.
    _ergebnis = {}
    for _taste in ("w", "s", "q"):
        _st = _state()
        _dbg.read_command = (lambda *a, _t=_taste, **k: _t)
        _ergebnis[_taste] = (_dbg.step_gate(_st, _halt, "LOOP", 1, 2), _st.step_mode)
    check("'w' laesst den Block laufen — und der Lauf bleibt normal",
          _ergebnis["w"] == (_dbg.GATE_RUN, False))
    check("'s' ueberspringt ihn", _ergebnis["s"][0] == _dbg.GATE_SKIP)
    check("'q' bricht ab", _ergebnis["q"][0] == _dbg.GATE_STOP)

    # 'm' ist neu und gibt es nur am Haltepunkt: ab hier Schritt fuer Schritt.
    _st = _state()
    _dbg.read_command = lambda *a, **k: "m"
    check("'m' fuehrt den Block aus UND schaltet den Schrittmodus ein",
          _dbg.step_gate(_st, _halt, "LOOP", 1, 2) == _dbg.GATE_RUN
          and _st.step_mode is True and _st.step_via_studio is False)
    check("das Gate ist danach nicht mehr als wartend markiert", _st.gate_waiting is False)

    # Im Schrittmodus ist der Haltepunkt kein zweites Gate — es fragt ohnehin.
    _st = _state()
    _st.step_mode = True
    _dbg.read_command = lambda *a, **k: "w"
    check("im Schrittmodus fragt der Haltepunkt nicht doppelt (ein 'w' reicht)",
          _dbg.step_gate(_st, _halt, "LOOP", 1, 2) == _dbg.GATE_RUN)

    # ---- CTRL+ALT+G gibt das Gate frei -------------------------------------
    # Der Hotkey ist die Taste, nach der man greift, wenn etwas steht. Die
    # Konsole liefert dabei keine Taste (leerer String = Zeitablauf), und das
    # Gate sieht zwischen zwei Abfragen nach, ob jemand "weiter" gesagt hat.
    _st = _state()
    _st.is_running = True
    _dbg.read_command = lambda *a, **k: ""
    _erg = {}
    _t = threading.Thread(target=lambda: _erg.setdefault(
        "value", _dbg.step_gate(_st, _halt, "LOOP", 1, 2)))
    _t.start()
    _frist = time.time() + 1.0
    while not _st.gate_waiting and time.time() < _frist:
        time.sleep(0.01)
    check("waehrend das Gate wartet, ist es als wartend markiert", _st.gate_waiting is True)
    # Auch ein Lauf aus der Konsole zeigt dem Studio, warum er steht.
    check("und die Tafel steht auch beim Konsolen-Gate im Laufstatus",
          (_status._state.get("manual") or {}).get("breakpoint") is True)
    _hnd.handle_pause(_st)
    _t.join(1.5)
    check("CTRL+ALT+G laesst den Block laufen statt zu pausieren",
          _erg.get("value") == _dbg.GATE_RUN and not _st.pause_event.is_set())
    check("und der Lauf bleibt danach normal", _st.step_mode is False)

    # Ohne wartendes Gate bleibt CTRL+ALT+G die Pause, die es immer war.
    _st = _state()
    _st.is_running = True
    _hnd.handle_pause(_st)
    check("ohne Gate pausiert CTRL+ALT+G wie bisher", _st.pause_event.is_set())
    _hnd.handle_pause(_st)
    check("und setzt fort", not _st.pause_event.is_set())
finally:
    _dbg.read_command = _orig_read
    _dbg.set_cursor_pos = _orig_cursor


# =============================================================================
section("Haltepunkt: aus dem Studio gestartet, im Studio beantwortet")
# =============================================================================

def _studio_gate(st, step):
    """Das Gate in einem Thread, bis die Tafel im Laufstatus steht."""
    res = {}
    t = threading.Thread(target=lambda: res.setdefault(
        "value", _dbg.step_gate(st, step, "LOOP", 1, 2)))
    t.start()
    deadline = time.time() + 1.0
    while not _status._state.get("manual") and time.time() < deadline:
        time.sleep(0.01)
    return t, res


_orig_read = _dbg.read_command
_dbg.read_command = lambda *a, **k: (_ for _ in ()).throw(AssertionError("Studio-Gate liest die Konsole"))
_dbg.set_cursor_pos = lambda *a, **k: None
try:
    _st = _state()
    _st.run_from_studio = True
    _st.is_running = True
    _t, _erg = _studio_gate(_st, _halt)
    _tafel = _status._state.get("manual") or {}
    check("die Tafel im Live-Run sagt, dass es ein Haltepunkt ist",
          _tafel.get("active") is True and _tafel.get("breakpoint") is True
          and _tafel.get("block") == 1)
    # Die Antwort kommt als Briefkasten-Befehl — auch ohne Schrittmodus.
    _hnd.command_manual_action(_st, {"action": "step"})
    _t.join(1.5)
    check("'ab hier schrittweise' aus dem Studio fuehrt aus und schaltet um",
          _erg.get("value") == _dbg.GATE_RUN and _st.step_mode is True
          and _st.step_via_studio is True)
    check("und raeumt die Tafel weg", _status._state.get("manual") is None)

    # Im Schrittmodus meldet die Tafel KEINEN Haltepunkt — es ist das normale Gate.
    _t, _erg = _studio_gate(_st, _halt)
    check("im Schrittmodus traegt die Tafel keine Haltepunkt-Marke",
          (_status._state.get("manual") or {}).get("breakpoint") is False)
    _hnd.command_manual_action(_st, {"action": "continue"})
    _t.join(1.5)
    check("'Normal weiter' schaltet den Schrittmodus wieder aus",
          _erg.get("value") == _dbg.GATE_RUN and _st.step_mode is False)

    # Ein Befehl ohne wartendes Gate wird nicht vorgemerkt — er feuerte sonst
    # beim naechsten Halt nach.
    _st.step_command = ""
    _st.step_command_event.clear()
    _hnd.command_manual_action(_st, {"action": "run"})
    check("ohne wartendes Gate wird kein Befehl vorgemerkt",
          _st.step_command == "" and not _st.step_command_event.is_set())
    _hnd.command_manual_action(_st, {"action": "kaputt"})
    check("ein unbekannter Befehl wird abgewiesen", _st.step_command == "")
finally:
    _dbg.read_command = _orig_read
    _dbg.set_cursor_pos = _orig_cursor


# =============================================================================
section("Haltepunkt: der Start merkt sich, wer gefragt wird")
# =============================================================================

# Der Hotkey-Start fragt in der Konsole, der Studio-Start im Live-Run — die
# Herkunft steht am Lauf. Gemessen an der Zuweisung, nicht am Worker: der
# braeuchte eine Sequenz, ein Fenster und einen Bildschirm.
import inspect as _inspect
_quelle = _inspect.getsource(_hnd)
check("command_start startet mit aus_studio=True",
      "handle_toggle(state, aus_studio=True)" in _quelle)
check("der Countdown laesst die Herkunft stehen",
      _quelle.count("handle_toggle(state, aus_studio=None)") >= 2)
check("handle_toggle schreibt die Herkunft an den Lauf",
      "state.run_from_studio = bool(aus_studio)" in _quelle)


# =============================================================================
section("Haltepunkt: Studio-Bruecke und Konsolen-Editor")
# =============================================================================

from autoclicker.editors.sequence_studio.bridge import StudioBridge as _SB
from autoclicker.editors.sequence_studio.model import board_to_sequence as _b2s

_schritt = _STEP(x=5, y=6, delay_before=0, name="Bank", point_id=1)
_seq = _SEQ(name="H", loop_phases=[_PHASE(name="Loop", repeat=1, steps=[_schritt])])
_b = _SB(_seq, Path("sequences/H.json"), "sequences")
_b.select({"phase": 1, "row": 0})
_b.block_set({"field": "breakpoint", "value": True})
_karte = _b.snapshot()["phases"][1]["blocks"][0]
check("der Schalter setzt das Feld am Schritt", _schritt.breakpoint is True)
check("die Karte traegt die Marke", _karte.get("breakpoint") is True)
check("der Inspektor zeigt den Zustand", _b.snapshot()["block"]["breakpoint"] is True)
check("und das Speichern nimmt ihn mit",
      _b2s(_b.board).loop_phases[0].steps[0].breakpoint is True)
_b.block_set({"field": "breakpoint", "value": False})
check("der Schalter nimmt ihn auch wieder weg", _schritt.breakpoint is False)

# Die Seite ruft genau dieses Feld — sonst stuende ein Schalter da, der nichts tut.
_web = (Path(__file__).resolve().parents[2] / "autoclicker" / "editors"
        / "sequence_studio" / "web" / "app.js").read_text(encoding="utf-8")
check("der Inspektor schaltet ueber block_set/breakpoint",
      '{field: "breakpoint", value: on}' in _web)
check("die Karte zeigt die Marke", "block.breakpoint" in _web)
check("die Tafel im Live-Run kennt den Haltepunkt und 'ab hier schrittweise'",
      "m.breakpoint" in _web and '"step"' in _web)

# Konsolen-Editor: `break <Nr>` schaltet um.
from autoclicker.editors.sequence_editor.steps import _PhaseEditor as _PE, _KNOWN_COMMANDS as _KC
check("'break' ist ein bekannter Befehl", "break" in _KC)
_pe = _PE(_ST(), [_STEP(x=1, y=1, delay_before=0, name="A"),
                  _STEP(x=2, y=2, delay_before=0, name="B")], "Loop")
_pe._handle_breakpoint("break 2")
check("'break 2' setzt den Haltepunkt am zweiten Schritt",
      _pe.steps[1].breakpoint is True and _pe.steps[0].breakpoint is False)
_pe._handle_breakpoint("break 2")
check("nochmal 'break 2' nimmt ihn wieder weg", _pe.steps[1].breakpoint is False)
