"""Eine NEUE Sequenz darf eine vorhandene nicht still überschreiben.

Drei Wege legen eine Sequenz unter einem getippten Namen an, und alle drei
schrieben über die `sequence.json` einer vorhandenen, wenn der Name vergeben
war: Schritte und Punkte weg, ihre Scans blieben daneben liegen und zeigten
auf Punkte, die es nicht mehr gibt.

- **Studio**: „Neu", den Namen einer vorhandenen eintippen, Speichern. Die
  Ordnerprüfung stand im Zweig „alte Datei existiert" — eine nie
  gespeicherte Sequenz kam daran vorbei, gemeldet wurde „Gespeichert".
  `scan_save()` speichert zuerst die Sequenz und schrieb danach auch noch
  die Scans in den fremden Ordner.
- **Konsolen-Aufnahme** mit getipptem Namen.
- **Konsolen-Editor** „Neue Sequenz erstellen".

Dieselbe Regel wie bei Slots und Items: ein getippter Name wird vor dem
Überschreiben erfragt; wo niemand gefragt werden kann (Aufnahme aus dem
Studio), wird ausgewichen.
"""
import contextlib as _cl
import io as _io
import os as _os
import shutil as _sh
import tempfile as _tmp
import time as _time
from pathlib import Path as _P

from ._harness import check, section
from autoclicker.models import (
    AutoClickerState as _ST,
    ClickPoint as _CP,
    LoopPhase as _PHASE,
    RecordEvent as _RE,
    REC_CLICK as _RC,
    Sequence as _SEQ,
    SequenceStep as _STEP,
)
from autoclicker.persistence import (
    activate_sequence, confirm_new_sequence_name, free_sequence_name,
    save_sequence_file, sequence_file,
)
import autoclicker.utils as _utils
import autoclicker.editors.sequence_recorder as _rec
import autoclicker.editors.sequence_editor.editor as _ed
from autoclicker.editors.sequence_studio.bridge import StudioBridge as _SB


def _existing(name: str) -> _P:
    """Eine gespeicherte Sequenz mit drei Blöcken, drei Punkten und einem Scan."""
    seq = _SEQ(name, points=[_CP(i, i, f"P{i}", i) for i in (1, 2, 3)],
               loop_phases=[_PHASE("L", steps=[_STEP(point_id=i, x=i, y=i)
                                               for i in (1, 2, 3)])])
    path = sequence_file(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    save_sequence_file(seq, path)
    (path.parent / "item_scans").mkdir(exist_ok=True)
    (path.parent / "item_scans" / "inv.json").write_text('{"name": "inv"}', encoding="utf-8")
    return path


def _answers(confirm_value, inputs):
    """`confirm`/`safe_input` aus utils ersetzen — der Rückfrage-Helfer liest sie dort."""
    queue = list(inputs)
    return (lambda *a, **k: confirm_value,
            lambda *a, **k: queue.pop(0) if queue else "")


_quiet = _cl.redirect_stdout(_io.StringIO())
_sandbox = _tmp.mkdtemp(prefix="sequenznamen_")
_cwd = _os.getcwd()
_os.chdir(_sandbox)
_orig_utils = (_utils.confirm, _utils.safe_input)
try:
    _raid = _existing("Raid")
    _raid_before = _raid.read_text(encoding="utf-8")

    # =========================================================================
    section("Studio: eine neue Sequenz uebernimmt keinen vergebenen Namen")
    # =========================================================================
    _b = _SB(_SEQ("Andere"), _P("sequences/andere/sequence.json"), "sequences")
    with _quiet:
        _b.new({})
        _b.sequence_set({"field": "name", "value": "Raid"})
        _answer = _b.save({})
    _status = _answer.get("status") or {}
    check("Speichern unter einem vergebenen Namen wird abgelehnt",
          _status.get("kind") == "err" and "existiert bereits" in (_status.get("text") or ""))
    check("die vorhandene Sequenz bleibt Byte fuer Byte, wie sie war",
          _raid.read_text(encoding="utf-8") == _raid_before)
    check("und bleibt ungespeichert — nichts ist verloren", _b._dirty)

    # Anders geschrieben, derselbe Ordner: „raid" landet in sequences/raid.
    with _quiet:
        _b.sequence_set({"field": "name", "value": "RAID"})
        _answer = _b.save({})
    check("auch in anderer Schreibweise — verglichen wird der Ordner",
          (_answer.get("status") or {}).get("kind") == "err"
          and _raid.read_text(encoding="utf-8") == _raid_before)

    # scan_save() speichert zuerst die Sequenz — und schrieb danach die Scans
    # in den fremden Ordner.
    with _quiet:
        _answer = _b.scan_save({})
    check("der Speichern-Knopf der Scans erbt die Absage",
          _raid.read_text(encoding="utf-8") == _raid_before
          and (_raid.parent / "item_scans" / "inv.json").read_text(encoding="utf-8")
          == '{"name": "inv"}')

    # =========================================================================
    section("Studio: umbenannt wird der ORDNER, auch ohne gespeicherte Datei")
    # =========================================================================
    # Eine nie gespeicherte Sequenz kann schon einen Ordner haben — der Scans-
    # Reiter legt gemerkte Bildschirme dort ab. Verschoben wurde nur, wenn die
    # sequence.json existierte; die Bilder blieben im alten Ordner zurueck.
    _b = _SB(_SEQ("Andere"), _P("sequences/andere/sequence.json"), "sequences")
    with _quiet:
        _b.new({})
    _pictures = _b.filepath.parent / "bilder"
    _pictures.mkdir(parents=True)
    (_pictures / "inv.png").write_bytes(b"png")
    _old_folder = _b.filepath.parent
    # Der Scans-Reiter ist offen und hat Ungespeichertes — das darf das
    # Umbenennen nicht wegwerfen. Hier stand ein Neuaufbau des Reiters
    # (`_scan_init` + `_scan_load`): Auswahl, Rueckgaengig und ungespeicherte
    # Scan-Aenderungen waren weg, die rechte Spalte sprang auf „Slots".
    from autoclicker.models import ItemSlot as _SLOT
    with _quiet:
        _b._scan_load()
    _b.slots["Probe"] = _SLOT("Probe", (0, 0, 8, 8), (4, 4))
    _b.scan_kind, _b.scan_name = "item", "Bogen"
    _b._scan_dirty = True
    with _quiet:
        _b.sequence_set({"field": "name", "value": "Farm"})
        _answer = _b.save({})
    check("die neue Sequenz wird unter ihrem Namen gespeichert",
          sequence_file("Farm").exists()
          and (_answer.get("status") or {}).get("kind") != "err")
    check("und nimmt ihre gemerkten Bildschirme mit",
          (sequence_file("Farm").parent / "bilder" / "inv.png").exists()
          and not _old_folder.exists())
    check("der Scans-Reiter behaelt Auswahl und Ungespeichertes",
          "Probe" in _b.slots and _b._scan_dirty
          and (_b.scan_kind, _b.scan_name) == ("item", "Bogen"))
    check("und haelt den verschobenen Ordner nicht fuer fremd geaendert",
          not _b._disk_changed_externally())

    # =========================================================================
    section("free_sequence_name / confirm_new_sequence_name")
    # =========================================================================
    check("ein freier Name bleibt, wie er ist", free_sequence_name("Neu") == "Neu")
    check("ein vergebener bekommt einen Zaehler", free_sequence_name("Raid") == "Raid 2")
    check("verglichen wird der Ordner, nicht die Schreibweise",
          free_sequence_name("raid") == "raid 2")

    _utils.confirm, _utils.safe_input = _answers(False, ["x"])
    with _quiet:
        _free = confirm_new_sequence_name("Neu")
    check("ein freier Name wird ohne Rueckfrage uebernommen", _free == "Neu")

    _utils.confirm, _utils.safe_input = _answers(True, [])
    with _quiet:
        _yes = confirm_new_sequence_name("Raid")
    check("ueberschreiben geht — aber nur ausdruecklich", _yes == "Raid")

    _utils.confirm, _utils.safe_input = _answers(False, [""])
    with _quiet:
        _other = confirm_new_sequence_name("Raid")
    check("nein + Enter nimmt den freien Vorschlag", _other == "Raid 2")

    _utils.confirm, _utils.safe_input = _answers(False, ["cancel"])
    with _quiet:
        _cancel = confirm_new_sequence_name("Raid")
    check("cancel bricht ab", _cancel is None)

    # =========================================================================
    section("Konsolen-Aufnahme: getippter Name")
    # =========================================================================
    _st = _ST()
    _st.recording_active = True
    _st.recording_events = [_RE(_RC, _time.monotonic(), 5, 6, (1, 2, 3))]
    _typed = ["Raid", "", ""]                               # Name, Zyklen, Beschreibung
    _orig_rec = (_rec.safe_input, _rec.remove_mouse_hook, _rec.remove_keyboard_hook)
    _rec.safe_input = lambda *a, **k: _typed.pop(0) if _typed else ""
    _rec.remove_mouse_hook = _rec.remove_keyboard_hook = lambda: None
    _utils.confirm, _utils.safe_input = _answers(False, [""])   # nein, Vorschlag nehmen
    try:
        with _quiet:
            _saved = _rec.stop_recording(_st)
    finally:
        _rec.safe_input, _rec.remove_mouse_hook, _rec.remove_keyboard_hook = _orig_rec
    check("die Aufnahme ueberschreibt die vorhandene Sequenz nicht",
          _raid.read_text(encoding="utf-8") == _raid_before)
    check("sie landet unter dem freien Namen", _saved == "Raid 2"
          and sequence_file("Raid 2").exists())

    # =========================================================================
    section("Aufnahme aus dem Studio: ausweichen statt fragen")
    # =========================================================================
    # Das Studio prueft den Namen beim Start; zwischen Start und Stopp kann er
    # vergeben worden sein. Fragen geht dort nicht (niemand sieht die Konsole).
    _st = _ST()
    _st.recording_active = True
    _st.recording_events = [_RE(_RC, _time.monotonic(), 5, 6, (1, 2, 3))]
    _st.recording_ui_name = "Raid"
    _orig_rec = (_rec.safe_input, _rec.remove_mouse_hook, _rec.remove_keyboard_hook)
    _rec.safe_input = lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("die UI-Aufnahme darf nichts in der Konsole fragen"))
    _rec.remove_mouse_hook = _rec.remove_keyboard_hook = lambda: None
    try:
        with _quiet:
            _saved = _rec.stop_recording(_st)
    finally:
        _rec.safe_input, _rec.remove_mouse_hook, _rec.remove_keyboard_hook = _orig_rec
    check("die Studio-Aufnahme weicht auf einen freien Namen aus",
          _saved == "Raid 3" and _raid.read_text(encoding="utf-8") == _raid_before)

    # =========================================================================
    section("Konsolen-Editor: Neue Sequenz unter vergebenem Namen")
    # =========================================================================
    _st = _ST()
    with _quiet:
        from autoclicker.persistence import load_sequence_file as _load
        activate_sequence(_st, _load(_raid))                # der Editor braucht Punkte
    _orig_ed = (_ed.edit_phase, _ed.edit_loop_phases, _ed._ask_total_cycles, _ed.safe_input)
    _ed.edit_phase = lambda state, steps, label: list(steps)
    _ed.edit_loop_phases = lambda state, phases: phases
    _ed._ask_total_cycles = lambda current: current
    _ed.safe_input = lambda prompt="", *a, **k: "Raid" if "Name" in prompt else ""
    _utils.confirm, _utils.safe_input = _answers(False, ["Mine"])  # nein, eigener Name
    try:
        with _quiet:
            _ed.edit_sequence(_st, None)
    finally:
        _ed.edit_phase, _ed.edit_loop_phases, _ed._ask_total_cycles, _ed.safe_input = _orig_ed
    check("der Editor ueberschreibt die vorhandene Sequenz nicht",
          _raid.read_text(encoding="utf-8") == _raid_before)
    check("er speichert unter dem Namen aus der Rueckfrage",
          sequence_file("Mine").exists() and _st.active_sequence.name == "Mine")
finally:
    _utils.confirm, _utils.safe_input = _orig_utils
    _os.chdir(_cwd)
    _sh.rmtree(_sandbox, ignore_errors=True)
