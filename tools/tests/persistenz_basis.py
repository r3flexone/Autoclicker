"""Persistenz-Grundlagen: crash-sicheres Schreiben, Zeiten, Presets, Log.

`atomic_write()` soll einen Absturz mitten im Speichern ueberleben, und jeder
Saver geht durch sie. Dazu der Abgleich der ZWEI Schreibwege auf `slots.json`
und `items.json` (Hauptprozess ueber `persistence/globals.py`, Studio ueber
`scan_model.py`).
"""
import io as _io2, contextlib as _cl2, os as _os, tempfile
from pathlib import Path

from ._harness import check, section

section("Crash-sicheres Schreiben (atomic_write)")

from autoclicker.utils import atomic_write as _aw

_aw_dir = Path(tempfile.mkdtemp())
_ziel = _aw_dir / "daten.json"

_aw(_ziel, '{"a": 1}')
check("schreibt eine neue Datei", _ziel.read_text(encoding="utf-8") == '{"a": 1}')
_aw(_ziel, '{"a": 2}')
check("ueberschreibt eine vorhandene", _ziel.read_text(encoding="utf-8") == '{"a": 2}')
check("und laesst keine Temp-Datei liegen",
      [p.name for p in _aw_dir.iterdir()] == ["daten.json"])

# **Der eigentliche Zweck: geht das Schreiben schief, bleibt die ALTE Datei stehen.**
# Gestellt wird der Absturz genau dort, wo er im Ernstfall passiert - in der Temp-Datei,
# also nach dem Anlegen und vor dem `os.replace()`. Ohne die Temp-Datei-Technik stuende
# hier jetzt eine halb geschriebene, unlesbare `daten.json`.
import autoclicker.utils.parsing as _pmod
_echtes_fsync, _echtes_replace = _pmod.os.fsync, _pmod.os.replace

_pmod.os.fsync = lambda fd: (_ for _ in ()).throw(OSError("Platte voll"))
try:
    _aw(_ziel, '{"a": 3}')
except OSError:
    pass
finally:
    _pmod.os.fsync = _echtes_fsync
check("bricht das Schreiben ab, steht die alte Datei unveraendert da",
      _ziel.read_text(encoding="utf-8") == '{"a": 2}')

# Und wenn das Umbenennen selbst scheitert, ebenso.
_pmod.os.replace = lambda a, b: (_ for _ in ()).throw(OSError("gesperrt"))
try:
    _aw(_ziel, '{"a": 4}')
except OSError:
    pass
finally:
    _pmod.os.replace = _echtes_replace
check("scheitert das Umbenennen, bleibt die alte Datei ebenfalls intakt",
      _ziel.read_text(encoding="utf-8") == '{"a": 2}')

# Ein Verzeichnis, das es noch nicht gibt, wird angelegt - sonst muesste jeder
# Aufrufer selbst daran denken.
_tief = _aw_dir / "a" / "b" / "c.json"
_aw(_tief, "x")
check("legt fehlende Verzeichnisse an", _tief.read_text(encoding="utf-8") == "x")


section("Zeit-Eingaben (parse_time_input)")

from autoclicker.utils import parse_time_input as _pt

# Relative Angaben: die Zahl ist das Ergebnis, nicht die Uhrzeit.
check("30s sind 30 Sekunden", _pt("30s")[0] == 30)
check("30m sind 1800 Sekunden", _pt("30m")[0] == 1800)
check("30min ebenso", _pt("30min")[0] == 1800)
check("2h sind 7200 Sekunden", _pt("2h")[0] == 7200)
check("2std ebenso", _pt("2std")[0] == 7200)
check("+2 ohne Einheit sind Minuten", _pt("+2")[0] == 120)
check("+30m sind 1800 Sekunden", _pt("+30m")[0] == 1800)

# Absolute Uhrzeiten: das Ergebnis liegt in der Zukunft, hoechstens 24 h entfernt.
# Auf die Sekunde genau zu pruefen hiesse, die Uhr des Testlaufs festzuschreiben.
for _form in ("14:30", "1430"):
    _sek, _txt, _ziel_ts = _pt(_form)
    check(f"'{_form}' liegt in der Zukunft und hoechstens 24 h entfernt",
          0 <= _sek <= 24 * 3600)
    check(f"'{_form}' nennt einen Zeitpunkt", _ziel_ts is not None)
check("beide Schreibweisen meinen dieselbe Uhrzeit",
      abs(_pt("14:30")[0] - _pt("1430")[0]) <= 1)

# Unsinn wird abgelehnt statt geraten - eine falsch verstandene Wartezeit faellt
# erst Stunden spaeter auf.
for _mist in ("", "abc", "25:00", "2570", "-5", "12:99"):
    _erg = _pt(_mist)
    check(f"'{_mist}' wird nicht als Zeit akzeptiert", _erg[0] <= 0 or _erg[1] == "")


section("Presets: speichern, laden, loeschen")

from autoclicker.models import AutoClickerState as _ST_P, ItemSlot as _SL_P
import autoclicker.persistence.presets as _pp

_pre_tmp = Path(tempfile.mkdtemp())
_pre_cwd = _os.getcwd()
_os.chdir(_pre_tmp)
try:
    _stp = _ST_P()
    _stp.global_slots = {"Slot 1": _SL_P(name="Slot 1", scan_region=(1, 2, 3, 4),
                                         click_pos=(2, 3), slot_color=(9, 8, 7))}
    check("Preset wird geschrieben", _pp.save_slot_preset(_stp, "Spiel A") is True)
    # Der Dateiname wird entschaerft (`sanitize_filename`), und die Liste nennt den
    # DATEINAMEN - nicht den eingegebenen. Das ist kein Schoenheitsfehler: wer das
    # Preset spaeter laedt, tippt genau diesen Namen.
    check("und taucht unter dem entschaerften Namen in der Liste auf",
          [n for n, _p, _z in _pp.list_slot_presets()] == ["spiel_a"])
    check("die Liste zaehlt die Eintraege mit",
          [z for _n, _p, z in _pp.list_slot_presets()] == [1])

    # Laden ersetzt den Bestand - und zwar mit denselben Werten, nicht mit Defaults.
    _stp2 = _ST_P()
    check("Preset laedt zurueck", _pp.load_slot_preset(_stp2, "Spiel A") is True)
    check("und die Werte kommen unveraendert an",
          _stp2.global_slots["Slot 1"].scan_region == (1, 2, 3, 4)
          and _stp2.global_slots["Slot 1"].slot_color == (9, 8, 7))

    check("ein Preset, das es nicht gibt, wird gemeldet",
          _pp.load_slot_preset(_ST_P(), "gibt es nicht") is False)
    check("Loeschen meldet Erfolg", _pp.delete_slot_preset("Spiel A") is True)
    check("und danach ist die Liste leer", _pp.list_slot_presets() == [])
    check("zweimal loeschen ist kein Erfolg", _pp.delete_slot_preset("Spiel A") is False)
finally:
    _os.chdir(_pre_cwd)


section("Beide Schreibwege fuer slots.json und items.json stimmen ueberein")

# **Zwei Codewege auf dieselben zwei Dateien.** Der Hauptprozess schreibt ueber
# `persistence/globals.py`, das Studio (eigener Prozess, kein State) ueber
# `sequence_studio/scan_model.py`. Beide benutzen zwar dieselben Serialisierer -
# aber das war bisher eine Annahme, die niemand geprueft hat. Faellt dieser Test,
# schreiben die beiden Fenster verschiedene Dateien und der zuletzt gespeicherte
# Stand gewinnt mit anderen Werten.

from autoclicker.models import ItemProfile as _IP_R
import autoclicker.persistence.globals as _gl
from autoclicker.editors.sequence_studio.scan_model import (
    load_slots as _sm_ls, save_slots as _sm_ss,
    load_items as _sm_li, save_items as _sm_si)
from autoclicker.persistence.paths import SLOTS_FILE as _SF_R, ITEMS_FILE as _IF_R

_rt_tmp = Path(tempfile.mkdtemp())
_rt_cwd = _os.getcwd()
_os.chdir(_rt_tmp)
try:
    _slots_soll = {"Beutel": _SL_P(name="Beutel", scan_region=(10, 20, 70, 80),
                                   click_pos=(40, 50), slot_color=(1, 2, 3))}
    _items_soll = {"Kohle": _IP_R(name="Kohle", marker_colors=[(4, 5, 6)],
                                  category="Erz", priority=7, min_confidence=0.9)}

    # Hauptprozess schreibt -> Studio liest
    _st_r = _ST_P()
    _st_r.global_slots = dict(_slots_soll)
    _st_r.global_items = dict(_items_soll)
    with _cl2.redirect_stdout(_io2.StringIO()):
        _gl.save_global_slots(_st_r)
        _gl.save_global_items(_st_r)
    _studio_slots, _studio_items = _sm_ls(_SF_R), _sm_li(_IF_R)
    check("das Studio liest, was der Hauptprozess geschrieben hat",
          list(_studio_slots) == ["Beutel"] and list(_studio_items) == ["Kohle"])
    check("und zwar mit denselben Werten",
          _studio_slots["Beutel"].scan_region == (10, 20, 70, 80)
          and _studio_slots["Beutel"].slot_color == (1, 2, 3)
          and _studio_items["Kohle"].priority == 7
          and _studio_items["Kohle"].min_confidence == 0.9
          and _studio_items["Kohle"].marker_colors == [(4, 5, 6)])

    # Studio schreibt -> Hauptprozess liest
    _slots_datei_vorher = Path(_SF_R).read_text(encoding="utf-8")
    _items_datei_vorher = Path(_IF_R).read_text(encoding="utf-8")
    _sm_ss(_studio_slots, _SF_R)
    _sm_si(_studio_items, _IF_R)
    # **Byte fuer Byte dieselbe Datei.** Das ist die eigentliche Aussage: beide Wege
    # gehen durch dieselben `_*_to_dict`, also darf ein Speichern im Studio die Datei
    # des Hauptprozesses nicht einmal formal veraendern.
    check("das Studio schreibt byteweise dieselbe slots.json",
          Path(_SF_R).read_text(encoding="utf-8") == _slots_datei_vorher)
    check("und dieselbe items.json",
          Path(_IF_R).read_text(encoding="utf-8") == _items_datei_vorher)

    _st_zurueck = _ST_P()
    with _cl2.redirect_stdout(_io2.StringIO()):
        _gl.load_global_slots(_st_zurueck)
        _gl.load_global_items(_st_zurueck)
    check("der Hauptprozess liest zurueck, was das Studio geschrieben hat",
          _st_zurueck.global_slots["Beutel"].scan_region == (10, 20, 70, 80)
          and _st_zurueck.global_items["Kohle"].category == "Erz")
finally:
    _os.chdir(_rt_cwd)


section("Session-Log schreibt, was es behauptet")

from autoclicker.session_log import start_session_log as _ssl, log_event as _le

_log_tmp = Path(tempfile.mkdtemp())
_log_cwd = _os.getcwd()
_os.chdir(_log_tmp)
try:
    _st_l = _ST_P()
    _st_l.config.session_log_enabled = False
    check("abgeschaltet entsteht kein Log", _ssl(_st_l) is None)

    _st_l.config.session_log_enabled = True
    _st_l.config.session_log_dir = "logs"
    _log = _ssl(_st_l)
    check("eingeschaltet entsteht eines", _log is not None)
    if _log is not None:
        _st_l.session_log = _log
        _le(_st_l, "click", "Bank", "ok")
        _le(_st_l, "timeout", "Ofen")
        _log.close()
        _zeilen = Path(_log.path).read_text(encoding="utf-8").splitlines()
        check("die Kopfzeile steht drin", _zeilen and "," in _zeilen[0])
        check("beide Ereignisse sind geschrieben", len(_zeilen) == 3)
        check("und das diagnostisch wichtigste ist dabei",
              any("timeout" in z for z in _zeilen))
        # `log_report.py` wertet genau diese Datei aus - ein Ereignis, das es nicht
        # kennt, meldet es als "nicht ausgewertete Ereignisart".
        from tools.log_report import AUSGEWERTET as _BE
        check("die geschriebenen Ereignisarten kennt der Bericht",
              {"click", "timeout"} <= set(_BE))
finally:
    _os.chdir(_log_cwd)


section("Eine frisch geschriebene Sequenz ist sofort sichtbar")

# `list_available_sequences()` cacht. War der Schluessel die mtime des ORDNERS,
# liessen zwei im selben Tick geschriebene Sequenzen die zweite unsichtbar werden
# (NTFS stempelt Verzeichnisse grob) - und `zuletzt_bearbeitet()` nannte die
# falsche. Der Test friert die Ordner-Zeit ein und bildet die grobe Aufloesung
# nach; mit dem alten Schluessel ist er auf jeder Plattform rot.
import json as _js_seq

from autoclicker.persistence import sequences as _seqmod
from autoclicker.sequence_studio import zuletzt_bearbeitet as _zb_seq

_seq_cwd = _os.getcwd()
_seq_tmp = tempfile.mkdtemp()
_os.chdir(_seq_tmp)
try:
    Path("sequences").mkdir()

    def _schreibe_seq(datei, name):
        Path("sequences", datei).write_text(_js_seq.dumps({
            "name": name, "schema_version": 4, "total_cycles": 1,
            "init_steps": [], "end_steps": [], "loop_phases": []}),
            encoding="utf-8")

    _ordnerzeit = 1_700_000_000

    _schreibe_seq("erste.json", "erste")
    _os.utime("sequences", (_ordnerzeit, _ordnerzeit))
    _namen = [p.name for _, p in _seqmod.list_available_sequences()]
    check("die erste Sequenz steht in der Liste", _namen == ["erste.json"])

    # Zweite Datei, Ordner-Zeit absichtlich unveraendert.
    _schreibe_seq("zweite.json", "zweite")
    _os.utime("sequences", (_ordnerzeit, _ordnerzeit))
    _namen = [p.name for _, p in _seqmod.list_available_sequences()]
    check("die zweite auch, obwohl die Ordner-Zeit gleich blieb",
          _namen == ["erste.json", "zweite.json"])

    # Und die Folge, wegen der es weh tut: das Studio oeffnet die richtige.
    _os.utime(Path("sequences") / "erste.json", (_ordnerzeit, _ordnerzeit))
    _os.utime(Path("sequences") / "zweite.json",
              (_ordnerzeit + 100, _ordnerzeit + 100))
    check("und zuletzt_bearbeitet() findet die neuere",
          _zb_seq() == Path("sequences") / "zweite.json")

    # Der Cache soll trotzdem einer bleiben: gleiche Lage, gleiche Liste.
    check("unveraendert liefert der Cache dasselbe Objekt",
          _seqmod.list_available_sequences() is _seqmod.list_available_sequences())
finally:
    _os.chdir(_seq_cwd)


section("Beide Backends belegen dieselben Hotkeys")

# ZWEI Tabellen fuer dieselbe Sache: `HOTKEY_BINDINGS` (common.py, pynput) und
# `_HOTKEY_DEFINITIONS` (windows.py, Modifier + VK). Laufen sie auseinander,
# wirkt ein Hotkey auf einer Plattform und auf der anderen nicht - ohne dass ein
# Aufruf fehlschlaegt, die Taste tut einfach nichts.
import re as _re_hk

from pathlib import Path as _P_hk

from autoclicker.platforms.common import HOTKEY_BINDINGS as _BIND

_wurzel_hk = _P_hk(__file__).resolve().parent.parent.parent
_win_hk = (_wurzel_hk / "autoclicker/platforms/windows.py").read_text(encoding="utf-8")
_tab_hk = _re_hk.search(r"_HOTKEY_DEFINITIONS = \[(.*?)\n\]", _win_hk, _re_hk.S).group(1)

# Eintrag: (HOTKEY_ID, Modifier, VK, "CTRL+ALT+X (BESCHREIBUNG)")
_win_namen = dict(_re_hk.findall(
    r"\(\s*(HOTKEY_\w+),[^,]+,[^,]+,\s*\"([^\"]+)\"", _tab_hk))
check("der Test findet ueberhaupt Windows-Hotkeys", len(_win_namen) > 20)

from autoclicker.platforms import common as _common_hk
_id_name = {wert: name for name, wert in vars(_common_hk).items()
            if name.startswith("HOTKEY_") and isinstance(wert, int)}

_lin_ids = {_id_name[i] for i in _BIND if i in _id_name}
check("beide Backends kennen dieselben Hotkey-IDs",
      _lin_ids == set(_win_namen))
if _lin_ids != set(_win_namen):
    print("        nur Linux:   " + ", ".join(sorted(_lin_ids - set(_win_namen))))
    print("        nur Windows: " + ", ".join(sorted(set(_win_namen) - _lin_ids)))


def _kombi_linux(s):
    """'<ctrl>+<alt>+a' -> 'CTRL+ALT+A'"""
    return s.replace("<", "").replace(">", "").upper()


def _kombi_windows(s):
    """'CTRL+ALT+A (PUNKT SPEICHERN)' -> 'CTRL+ALT+A' — die Beschreibung faellt weg."""
    return s.split(" (")[0].strip().upper()


_ungleich = []
for _id, _kombi in _BIND.items():
    _name = _id_name.get(_id)
    if _name in _win_namen:
        _a, _b = _kombi_linux(_kombi), _kombi_windows(_win_namen[_name])
        if _a != _b:
            _ungleich.append(f"{_name}: Linux={_a} Windows={_b}")
check("und dieselbe Tastenkombination je Hotkey", _ungleich == [])
if _ungleich:
    print("        " + "; ".join(_ungleich))
