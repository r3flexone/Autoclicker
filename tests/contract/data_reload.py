"""Studio speichert während eines Laufs: nachgeladen wird nach dem Stopp.

`command_data()` lehnte das Nachladen während eines Laufs ab und meldete
„Scan-Daten werden nach dem Stopp geladen" — getan hat es danach niemand. Ein
Start aus dem Studio fiel nicht auf (er liest die Datei ohnehin neu), ein
Start per CTRL+ALT+S lief still mit dem alten Stand. Gemessen wird deshalb der
Weg bis zum Speicher: Datei ändern, Lauf beenden, Stand prüfen.
"""
import contextlib as _cl
import io as _io
import os as _os
import shutil as _sh
import tempfile as _tmp
import threading as _th

from ._harness import check, section
from autoclicker.models import (
    AutoClickerState as _ST,
    ClickPoint as _CP,
    LoopPhase as _PHASE,
    Sequence as _SEQ,
    SequenceStep as _STEP,
)
from autoclicker.persistence import (
    activate_sequence, save_sequence_file, sequence_file,
)
import autoclicker.handlers as _hnd


def _write(x: int) -> _SEQ:
    """Sequenz „Lauf" mit EINEM Punkt an (x, x), auf Platte geschrieben."""
    seq = _SEQ("Lauf", points=[_CP(x, x, "P1", 1)],
               loop_phases=[_PHASE("L", steps=[_STEP(point_id=1, delay_before=0)])])
    path = sequence_file("Lauf")
    path.parent.mkdir(parents=True, exist_ok=True)
    save_sequence_file(seq, path)
    return seq


def _quiet(fn):
    """Die Handler schreiben in die Konsole — die Prüfzeilen sollen stehen bleiben."""
    with _cl.redirect_stdout(_io.StringIO()):
        return fn()


def _x(state: _ST) -> int:
    with state.lock:
        return state.points[0].x if state.points else -1


_sandbox = _tmp.mkdtemp(prefix="nachladen_")
_cwd = _os.getcwd()
_os.chdir(_sandbox)
try:
    _state = _ST()
    _quiet(lambda: activate_sequence(_state, _write(10)))

    # =====================================================================
    section("data_reload während eines Laufs wird vorgemerkt, nicht verworfen")

    _state.is_running = True
    _write(99)
    _quiet(lambda: _hnd.command_data(_state, {}))
    check("der laufende Stand bleibt unangetastet", _x(_state) == 10)
    check("das Nachladen ist vorgemerkt", _state.data_reload_pending is True)

    _quiet(lambda: _hnd.reload_if_pending(_state))
    check("solange der Lauf steht, lädt auch der Nachholer nicht",
          _x(_state) == 10 and _state.data_reload_pending)

    _state.is_running = False
    _quiet(lambda: _hnd.reload_if_pending(_state))
    check("nach dem Lauf steht der gespeicherte Stand im Speicher",
          _x(_state) == 99)
    check("und die Vormerkung ist verbraucht",
          _state.data_reload_pending is False)

    _write(55)
    _quiet(lambda: _hnd.reload_if_pending(_state))
    check("ohne Vormerkung lädt der Nachholer nichts", _x(_state) == 99)

    # =====================================================================
    section("ein Hotkey-Start holt die Vormerkung vor dem Start nach")

    # Zwischen Laufende und nächstem Briefkasten-Blick liegen bis zu 250 ms;
    # ein CTRL+ALT+S dort darf nicht mit dem alten Stand loslaufen. Der
    # lebende LLM-Thread hält `handle_toggle` VOR dem eigentlichen Start
    # an — hinter der Stelle, um die es geht.
    _state.is_running = True
    _write(77)
    _quiet(lambda: _hnd.command_data(_state, {}))
    _state.is_running = False
    _hold = _th.Event()
    _state.llm_thread = _th.Thread(target=_hold.wait, daemon=True)
    _state.llm_thread.start()
    try:
        _quiet(lambda: _hnd.handle_toggle(_state))
    finally:
        _hold.set()
        _state.llm_thread.join(1)
        _state.llm_thread = None
    check("handle_toggle lädt vor dem Start nach", _x(_state) == 77)
    check("und startet in diesem Aufbau nicht", _state.is_running is False)
finally:
    _os.chdir(_cwd)
    _sh.rmtree(_sandbox, ignore_errors=True)
