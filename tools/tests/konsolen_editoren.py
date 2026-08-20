"""Konsolen-Editoren: die geteilten Capture-Helfer und das Umbenennen.

Die Editoren unter `autoclicker/editors/` standen lange in keinem Test — rund
3.400 Zeilen, und darunter die Handgriffe, die man am haeufigsten macht. Sie
brauchen nur `safe_input`, lassen sich also mit einer Tastenfolge fuettern;
dasselbe Muster wie bei `mehrfach_auswahl` im Item-Scan-Assistenten.

Angefangen wird bei dem, was GETEILT ist: `_detection_capture.py` gehoert dem
Boss- UND dem Icon-Editor, ein Test deckt hier also zwei Editoren ab.
"""
import io as _io2, contextlib as _cl2, os as _os, tempfile
from pathlib import Path

from ._harness import check, section

section("Geteilte Capture-Helfer der Erkennungs-Editoren")

# **Boss- und Icon-Editor teilen sich diese drei Funktionen** — ein Test hier deckt
# also beide ab, und das ist der billigste Einstieg in die ~3.400 Zeilen
# Konsolen-Editoren, die in keinem Test standen. Sie brauchen nur `safe_input`,
# lassen sich also mit einer Tastenfolge fuettern (dasselbe Muster wie bei
# `mehrfach_auswahl` weiter oben).
#
# Die Eigenschaft, um die es geht, steht so in CLAUDE.md: **Fehleingabe wiederholen
# statt abbrechen.** Wer sich bei einer von vier Koordinaten vertippt, soll nicht
# den ganzen Editor verlieren.

import autoclicker.editors._detection_capture as _DC


def _dc_folge(fn, eingaben, **kw):
    """Ruft eine Capture-Funktion mit einer festen Tastenfolge auf."""
    folge = list(eingaben)
    _alt = _DC.safe_input
    _DC.safe_input = lambda _p="": folge.pop(0) if folge else "cancel"
    try:
        with _cl2.redirect_stdout(_io2.StringIO()):
            return fn(**kw)
    finally:
        _DC.safe_input = _alt


# --- prompt_key: nur Tasten, die send_key auch abspielen kann ---
check("eine gueltige Taste kommt zurueck",
      _dc_folge(_DC.prompt_key, ["enter"]) == "enter")
check("Grossschreibung stoert nicht", _dc_folge(_DC.prompt_key, ["ENTER"]) == "enter")
check("'cancel' bricht ab", _dc_folge(_DC.prompt_key, ["cancel"]) is None)
# Der Punkt der Uebung: ein Tippfehler kostet EINE Wiederholung, nicht den Editor.
check("eine unbekannte Taste fragt erneut",
      _dc_folge(_DC.prompt_key, ["gibtsnicht", "space"]) == "space")
check("eine leere Eingabe ebenso",
      _dc_folge(_DC.prompt_key, ["", "1"]) == "1")

# --- _prompt_region_coords: vier Zahlen, und x2>x1, y2>y1 ---
_pr = _DC._prompt_region_coords
check("vier Zahlen ergeben eine Region",
      _dc_folge(_pr, ["100,200,400,500"]) == (100, 200, 400, 500))
check("Leerzeichen dazwischen stoeren nicht",
      _dc_folge(_pr, [" 10 , 20 , 30 , 40 "]) == (10, 20, 30, 40))
check("zu wenige Werte fragen erneut",
      _dc_folge(_pr, ["1,2,3", "1,2,3,4"]) == (1, 2, 3, 4))
check("Buchstaben fragen erneut",
      _dc_folge(_pr, ["a,b,c,d", "1,2,3,4"]) == (1, 2, 3, 4))
# Ein verdrehtes Rechteck ist kein Rechteck - und faellt sonst erst beim Scannen auf.
check("x2 <= x1 wird abgelehnt",
      _dc_folge(_pr, ["400,200,100,500", "1,2,3,4"]) == (1, 2, 3, 4))
check("y2 <= y1 ebenso",
      _dc_folge(_pr, ["100,500,400,200", "1,2,3,4"]) == (1, 2, 3, 4))
check("'cancel' gibt None", _dc_folge(_pr, ["cancel"]) is None)

# --- select_scan_region: beim Bearbeiten ist "beibehalten" vorausgewaehlt ---
# `interactive_select` braucht eine Tastatur; gestellt wird deshalb die Auswahl,
# nicht die Eingabe. Geprueft wird, dass die BESTEHENDE Region unveraendert
# zurueckkommt - sonst verliert jedes Bearbeiten den Scan-Bereich.
_alt_sel = _DC.interactive_select
try:
    _DC.interactive_select = lambda opts, default=0: default
    with _cl2.redirect_stdout(_io2.StringIO()):
        _behalten = _DC.select_scan_region((5, 6, 7, 8))
    check("beim Bearbeiten ist 'beibehalten' vorausgewaehlt", _behalten == (5, 6, 7, 8))
    _DC.interactive_select = lambda opts, default=0: -1
    with _cl2.redirect_stdout(_io2.StringIO()):
        check("ESC im Menue bricht ab", _DC.select_scan_region((5, 6, 7, 8)) is None)
    # Ohne bestehende Region gibt es den dritten Eintrag gar nicht - dann darf
    # "beibehalten" auch nicht versehentlich erreichbar sein.
    _DC.interactive_select = lambda opts, default=0: len(opts) - 1
    _DC.safe_input = lambda _p="": "1,2,3,4"
    with _cl2.redirect_stdout(_io2.StringIO()):
        check("ohne bestehende Region fuehrt der letzte Eintrag zur Eingabe",
              _DC.select_scan_region(None) == (1, 2, 3, 4))
finally:
    _DC.interactive_select = _alt_sel

# --- capture_markers: mindestens einer, sonst ist der Scan blind ---
_alt_cursor, _alt_pixel = _DC.get_cursor_pos, _DC.get_pixel_color
try:
    _stellen = [(10, 10), (20, 20), (30, 30)]
    _DC.get_cursor_pos = lambda: _stellen.pop(0) if _stellen else (0, 0)
    _DC.get_pixel_color = lambda x, y: (x, y, 99)
    check("Enter nimmt die Farbe unter dem Zeiger auf",
          _dc_folge(_DC.capture_markers, ["", "", "done"])
          == [(10, 10, 99), (20, 20, 99)])
    _stellen = [(1, 2)]
    # **'done' ohne einen einzigen Marker wird abgelehnt.** Ein Profil ohne Marker
    # und ohne Template wird nie erkannt - das faellt sonst erst im Lauf auf.
    check("'done' ohne Marker fragt erneut",
          _dc_folge(_DC.capture_markers, ["done", "", "done"]) == [(1, 2, 99)])
    _stellen = [(1, 2)]
    check("'cancel' gibt None", _dc_folge(_DC.capture_markers, ["cancel"]) is None)
    # Eine Stelle, an der sich nichts lesen laesst, legt KEINEN Marker an - sonst
    # stuende ein Profil mit einem Marker da, den es nie gab. Die Folge ist deshalb
    # dieselbe wie oben, nur liefert die Farbmessung nichts: zweimal Enter, dann
    # 'done' - und 'done' muss abgelehnt werden, weil die Liste leer geblieben ist.
    _DC.get_pixel_color = lambda x, y: None
    _stellen = [(1, 2), (3, 4)]
    check("eine unlesbare Stelle legt keinen Marker an",
          _dc_folge(_DC.capture_markers, ["", "", "done", "cancel"]) is None)
finally:
    _DC.get_cursor_pos, _DC.get_pixel_color = _alt_cursor, _alt_pixel


section("Item umbenennen: Template, Bestand und Scans ziehen mit")

# `_apply_item_rename` ist der stille Weg (fuer 'autoname'), und still heisst hier:
# keine Rueckfrage, aber auch keine halbe Aenderung. Drei Dinge haengen am Namen -
# der Eintrag im Bestand, die Template-DATEI und jede Scan-Referenz. Bleibt eines
# zurueck, zeigt der Scan ins Leere oder das Template gehoert zum falschen Item.

from autoclicker.editors.item_editor.commands import _apply_item_rename as _air
from autoclicker.models import (AutoClickerState as _ACS_R, ItemProfile as _IPR)
import autoclicker.persistence.item_scans as _ismod2

_ren_tmp = Path(tempfile.mkdtemp())
_ren_cwd = _os.getcwd()
_os.chdir(_ren_tmp)
try:
    Path("items/templates").mkdir(parents=True)
    Path("items/templates/alt.png").write_bytes(b"PNG")
    _st_r2 = _ACS_R()
    _st_r2.global_items = {"Alt": _IPR(name="Alt", template="alt.png",
                                       marker_colors=[(1, 2, 3)])}
    _gerufen = []
    _alt_uiis = _ismod2.update_item_in_scans
    _ismod2.update_item_in_scans = lambda a, n: _gerufen.append((a, n))
    import autoclicker.editors.item_editor.commands as _cmdmod
    _alt_uiis2 = _cmdmod.update_item_in_scans
    _cmdmod.update_item_in_scans = lambda a, n: _gerufen.append((a, n))
    try:
        with _cl2.redirect_stdout(_io2.StringIO()):
            _erfolg = _air(_st_r2, "Alt", "Neu")
    finally:
        _ismod2.update_item_in_scans = _alt_uiis
        _cmdmod.update_item_in_scans = _alt_uiis2

    check("das Umbenennen meldet Erfolg", _erfolg is True)
    check("der Eintrag heisst neu",
          "Neu" in _st_r2.global_items and "Alt" not in _st_r2.global_items)
    check("das Item traegt seinen neuen Namen auch im Objekt",
          _st_r2.global_items["Neu"].name == "Neu")
    # Die DATEI wandert mit - sonst zeigt das Profil auf einen Namen, den es nicht gibt.
    check("die Template-Datei wandert mit",
          Path("items/templates/neu.png").exists()
          and not Path("items/templates/alt.png").exists())
    check("und das Profil zeigt auf den neuen Dateinamen",
          _st_r2.global_items["Neu"].template == "neu.png")
    check("die Scans werden nachgezogen", _gerufen == [("Alt", "Neu")])
    check("ein Item, das es nicht gibt, meldet False",
          _air(_st_r2, "Gibt es nicht", "Egal") is False)
finally:
    _os.chdir(_ren_cwd)
