"""Einfüge-Aufnahme: aus einem Block heraus weitere Schritte aufnehmen und
genau HINTER ihm einfügen — vor dem, der als Nächstes kommt.

Bis dahin gab es nur "ganz neu aufnehmen" (eine komplette Sequenz) oder "von
Hand einen Block bauen". Der Studio-Knopf "Ab hier aufnehmen"
(`block_record_start` → Briefkasten `record_from` → `command_record_from`)
startet denselben Maus-/Tastatur-Hook wie jede andere Aufnahme — nur dass
`stop_recording()` am Ende keine neue Sequenz baut, sondern die Schritte in
die BESTEHENDE Datei spleisst (`_finish_insert_recording`). Vorhandene Punkte
an gleicher Stelle werden dabei wiederverwendet, eine neue Phasengrenze
(CTRL+ALT+SHIFT+P) ergibt in einer Einfügung keinen Sinn und wird abgelehnt.

Echte Hook-Installation wird hier nicht getestet (das täte auf echtem Windows
einen systemweiten Hook anlegen) — `start_recording` wird dafür durch einen
Fake ersetzt, genau wie `start_from.py` es mit `handle_toggle` macht.
"""
import contextlib as _cl
import io as _io
import os as _os
import shutil as _sh
import tempfile as _tmp
from pathlib import Path as _P

from ._harness import check, section, studio_web_source
from autoclicker.models import (
    AutoClickerState as _ST,
    LoopPhase as _PHASE,
    Sequence as _SEQ,
    SequenceStep as _STEP,
    ClickPoint as _CP,
    RecordEvent as _RE,
    REC_CLICK as _R_CLICK,
    REC_PHASE as _R_PHASE,
)
import autoclicker.handlers as _hnd
import autoclicker.mailbox as _mb
import autoclicker.editors.sequence_recorder as _rec
from autoclicker.persistence import save_sequence_file, load_sequence_file, sequence_file, locate_step
from autoclicker.editors.sequence_studio.bridge import StudioBridge as _SB


def _target_sequence() -> _SEQ:
    return _SEQ("ziel", total_cycles=1,
                loop_phases=[_PHASE("L1", steps=[
                    _STEP(x=10, y=10, point_id=1, name="Klick A"),
                    _STEP(x=20, y=20, point_id=2, name="Klick B"),
                ])],
                points=[_CP(10, 10, "P1", 1), _CP(20, 20, "P2", 2)])


# =============================================================================
section("Der gemeinsame Kern: locate_step lebt an EINER Stelle")
# =============================================================================
# Er stand einmal in handlers.py und wurde dort zweimal gebraucht (Einstieg,
# Block-Test) - jetzt liegt er in persistence/sequences.py, damit auch die
# Einfuege-Aufnahme ihn nutzen kann, ohne eine dritte Kopie zu ziehen.
check("handlers.locate_step ist dieselbe Funktion wie in persistence.sequences",
      _hnd.locate_step is locate_step)

# =============================================================================
section("_finish_insert_recording: Bloecke landen GENAU zwischen den beiden")
# =============================================================================
_sandbox = _tmp.mkdtemp(prefix="einfuegen_")
_cwd = _os.getcwd()
_os.chdir(_sandbox)
try:
    _seq = _target_sequence()
    _path = sequence_file(_seq.name)
    _path.parent.mkdir(parents=True, exist_ok=True)
    save_sequence_file(_seq, _path)

    _target = {"file": str(_path), "phase": "loop", "phase_index": 0, "block": 0}
    # Ein Klick auf eine neue Stelle, dann einer auf den VORHANDENEN Punkt
    # #2 (20,20) - der soll wiederverwendet werden, nicht verdoppelt.
    _events = [_RE(_R_CLICK, 0.0, 30, 30, (9, 9, 9)),
              _RE(_R_CLICK, 1.0, 20, 20, None)]

    _st = _ST()
    _st.active_sequence = _target_sequence()   # "gerade geladen" im Hauptprozess
    with _cl.redirect_stdout(_io.StringIO()):
        _name = _rec._finish_insert_recording(_st, _events, _target)
    check("gemeldet wird der Name der Zielsequenz", _name == "ziel")

    _reloaded = load_sequence_file(_path)
    _steps = _reloaded.loop_phases[0].steps
    # `step.name` ist bei einem Klick mit `point_id` ein abgeleiteter Arbeitswert
    # (kommt beim Laden vom PUNKT-Namen, s. `resolve()`) - verglichen wird deshalb
    # ueber die Punkt-IDs, nicht ueber den urspruenglich getippten Schrittnamen.
    check("die neuen Bloecke stehen GENAU zwischen dem gewaehlten und dem naechsten",
          len(_steps) == 4 and _steps[0].point_id == 1 and _steps[3].point_id == 2)
    check("ein Klick auf eine neue Stelle bekommt einen neuen Punkt (ID hinter der hoechsten)",
          len(_reloaded.points) == 3 and _steps[1].point_id == 3)
    check("ein Klick auf einen vorhandenen Punkt wird wiederverwendet, nicht verdoppelt",
          _steps[2].point_id == 2)

    check("die geladene aktive Sequenz wird mitgezogen (gleicher Name)",
          len(_st.active_sequence.loop_phases[0].steps) == 4
          and len(_st.points) == 3)

    # Eine ANDERE aktive Sequenz darf die Einfuegung nicht mitbekommen.
    _other = _SEQ("andere", loop_phases=[_PHASE("L1", steps=[])])
    _st2 = _ST()
    _st2.active_sequence = _other
    with _cl.redirect_stdout(_io.StringIO()):
        _rec._finish_insert_recording(_st2, _events, _target)
    check("eine andere geladene Sequenz bleibt unberuehrt",
          _st2.active_sequence is _other and _other.loop_phases[0].steps == [])
finally:
    _os.chdir(_cwd)
    _sh.rmtree(_sandbox, ignore_errors=True)

# =============================================================================
section("mark_phase lehnt eine neue Grenze waehrend der Einfuegung ab")
# =============================================================================
_st3 = _ST()
_st3.recording_active = True
_st3.recording_insert = {"file": "x", "phase": "loop", "phase_index": 0, "block": 0}
_buf3 = _io.StringIO()
with _cl.redirect_stdout(_buf3):
    _rec.mark_phase(_st3)
check("keine Phasengrenze wird angelegt",
      not any(e.kind == _R_PHASE for e in _st3.recording_events))
check("und der Grund steht in der Konsole", "keine neue Grenze" in _buf3.getvalue())
# Eine normale Aufnahme (kein Ziel) ist davon unberuehrt.
_st4 = _ST()
_st4.recording_active = True
with _cl.redirect_stdout(_io.StringIO()):
    _rec.mark_phase(_st4)
check("eine normale Aufnahme darf weiterhin Phasen setzen",
      any(e.kind == _R_PHASE for e in _st4.recording_events))

# =============================================================================
section("Briefkasten: 'record_from' startet und raeumt bei Fehlschlag auf")
# =============================================================================
_sandbox2 = _tmp.mkdtemp(prefix="einfuegen_cmd_")
_cwd2 = _os.getcwd()
_os.chdir(_sandbox2)
try:
    _seq2 = _target_sequence()
    _path2 = sequence_file(_seq2.name)
    _path2.parent.mkdir(parents=True, exist_ok=True)
    save_sequence_file(_seq2, _path2)
    _args = {"file": str(_path2), "phase": "loop", "phase_index": 0, "block": 0}

    _st5 = _ST()
    _st5.is_running = True
    _buf5 = _io.StringIO()
    with _cl.redirect_stdout(_buf5):
        _hnd.command_record_from(_st5, _args)
    check("laeuft der Klicker, wird die Einfuege-Aufnahme abgelehnt",
          _st5.recording_insert is None and "Läuft bereits" in _buf5.getvalue())

    _st6 = _ST()
    _st6.recording_active = True
    _buf6 = _io.StringIO()
    with _cl.redirect_stdout(_buf6):
        _hnd.command_record_from(_st6, _args)
    check("laeuft schon eine Aufnahme, wird eine zweite abgelehnt",
          _st6.recording_insert is None and "Aufnahme" in _buf6.getvalue())

    _orig_start_recording = _rec.start_recording
    _start_calls: list = []

    def _fake_start_recording(state, *, name="", cycles=0, description=""):
        _start_calls.append((name, cycles, description))
        state.recording_active = True

    _rec.start_recording = _fake_start_recording
    try:
        _st7 = _ST()
        _buf7 = _io.StringIO()
        with _cl.redirect_stdout(_buf7):
            _hnd.command_record_from(_st7, {**_args, "block": 99})
        check("ein Block, den es nicht gibt, startet keine Aufnahme",
              _st7.recording_insert is None and not _start_calls
              and "existiert nicht mehr" in _buf7.getvalue())

        _st8 = _ST()
        with _cl.redirect_stdout(_io.StringIO()):
            _hnd.command_record_from(_st8, _args)
        check("ein gueltiges Ziel wird VOR dem Start gesetzt und ausgefuehrt",
              _st8.recording_insert == _args and _start_calls == [("", 0, "")]
              and _st8.recording_active)

        def _fake_start_recording_fail(state, *, name="", cycles=0, description=""):
            state.recording_active = False

        _rec.start_recording = _fake_start_recording_fail
        _st9 = _ST()
        with _cl.redirect_stdout(_io.StringIO()):
            _hnd.command_record_from(_st9, _args)
        check("scheitert der Hook, bleibt kein Einfuege-Ziel liegen",
              _st9.recording_insert is None)
    finally:
        _rec.start_recording = _orig_start_recording
finally:
    _os.chdir(_cwd2)
    _sh.rmtree(_sandbox2, ignore_errors=True)

# =============================================================================
section("Studio-Knopf: 'block_record_start' legt Datei und Position ab")
# =============================================================================
_sandbox3 = _tmp.mkdtemp(prefix="einfuegen_studio_")
_cwd3 = _os.getcwd()
_os.chdir(_sandbox3)
try:
    _seq3 = _target_sequence()
    _path3 = sequence_file(_seq3.name)
    _path3.parent.mkdir(parents=True, exist_ok=True)
    save_sequence_file(_seq3, _path3)

    _mb.COMMAND_PATH = _P("command.json")
    _b = _SB(_seq3, _path3, "sequences")
    _loop = next(i for i, ln in enumerate(_b.board.lanes) if ln.kind == "loop")
    _b.select({"phase": _loop, "row": 0})
    _res = _b.block_record_start()
    _job = _mb.fetch_command()
    check("block_record_start legt 'record_from' mit Datei und Position ab",
          _job and _job["command"] == "record_from"
          and _job["arguments"]["phase"] == "loop"
          and _job["arguments"]["phase_index"] == 0
          and _job["arguments"]["block"] == 0
          and _job["arguments"]["file"] == str(_path3))
    check("und sagt, wohinter eingefuegt wird",
          "eingefügt" in _res["status"]["text"] and "Block 1" in _res["status"]["text"])

    _b.select({"phase": _loop, "row": 0})
    _b.select({"phase": _loop, "row": 1, "mode": "add"})
    _res = _b.block_record_start()
    check("ohne eindeutige Auswahl wird nichts gestartet",
          _res["status"]["kind"] == "warn" and _mb.fetch_command() is None)
    check("'record_from' steht in der Befehlsliste beider Seiten",
          "record_from" in _SB.ALL_COMMANDS and "record_from" in _hnd.COMMANDS)
finally:
    _os.chdir(_cwd3)
    _sh.rmtree(_sandbox3, ignore_errors=True)

_web = studio_web_source()
check("der Inspektor hat den Knopf 'Ab hier aufnehmen'",
      'blockRecordStart' in _web and "Ab hier aufnehmen" in _web)
check("und ruft die passende Bruecken-Methode",
      'call("block_record_start")' in _web)

# Der Waechter darf "nicht aktiv" erst nach einem ersten Lebenszeichen als
# "fertig" lesen. Die erste Fassung fragte nach 500 ms einmal nach, sah die
# eben geloeschte Statusdatei, erklaerte die Aufnahme fuer beendet - und der
# Hook lief unsichtbar weiter, waehrend der Inspektor wieder "Ab hier
# aufnehmen" anbot.
_watch = _web[_web.index("function watchInsertRecording"):]
_watch = _watch[:_watch.index("\nfunction ", 1)]
check("der Waechter merkt sich, ob die Aufnahme schon einmal lief",
      "seen = true" in _watch and "if (!seen)" in _watch)
check("ohne Lebenszeichen gibt er nach einer Frist mit Meldung auf",
      "INSERT_RECORDING_START_ATTEMPTS" in _watch and "Hauptprozess" in _watch)
check("die Live-Ausgabe ist dieselbe Funktion wie im Werkzeuge-Reiter",
      "wzFillRecordingOutput($(\"insert-recording-output\")" in _watch
      and 'id: "insert-recording-output"' in _web)
check("ein fehlender Hauptprozess meldet sich nach dem Start",
      "mailboxFollowUp()" in _web[_web.index("async function blockRecordStart"):
                                  _web.index("async function blockRecordStop")])

# Die geladene Sequenz wird ueber den EINEN Weg ersetzt, der Punkte UND Scans
# gemeinsam umstellt (CLAUDE.md: "wer state.active_sequence setzt, ruft
# activate_sequence").
import inspect as _insp
_fin = _insp.getsource(_rec._finish_insert_recording)
check("die Einfuegung setzt active_sequence nicht von Hand",
      "state.active_sequence =" not in _fin and "activate_sequence(state, seq)" in _fin)
