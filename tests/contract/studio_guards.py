"""Sicherungen des Studios, die bis zum Umbau keine Prüfung hatten.

Aufgefallen bei der Gegenprobe nach dem Zerlegen der letzten Brücken-Methoden:
an diesen Stellen konnte man die Sicherung entfernen, und Vertragssuite wie
Wurzelmodule blieben grün. Jede Prüfung hier wird auf der entschärften Fassung
rot. (Die Slot-Suche „war schon dabei" steht im Szenario in `studio_scans.py`,
dort gibt es das Gitterbild schon.)
"""
import contextlib as _cl
import io as _io
import os as _os
import tempfile as _tmp
from pathlib import Path as _P
from types import SimpleNamespace as _NS

from ._harness import check, section

from autoclicker.editors.sequence_studio.bridge import StudioBridge as _SB
from autoclicker.editors.sequence_studio.scan_learning import _LearnResult
from autoclicker.models import ItemProfile as _ITEM, Sequence as _SEQ

_cwd = _os.getcwd()
_os.chdir(_tmp.mkdtemp(prefix="studio_guards_"))
try:
    _P("sequences").mkdir()
    with _cl.redirect_stdout(_io.StringIO()):
        _b = _SB(_SEQ(name="S"), _P("sequences/s/sequence.json"), "sequences")
        _b.scan_data()
        _b.scan_new({"name": "Inv"})
    _b.items["Bogen"] = _ITEM(name="Bogen", priority=1)
    _b._sync_objects()

    # =========================================================================
    section("Studio: Item-Felder — was abgelehnt wird und was nichts ablegt")
    # =========================================================================
    _depth = len(_b._undo)
    _b.scan_item_set({"name": "Bogen", "field": "active", "value": True})
    check("ein Schalter auf seinem Wert legt keinen Rückgängig-Stand ab",
          len(_b._undo) == _depth)
    _z = _b.scan_item_set({"name": "Bogen", "field": "priority", "value": 0})
    check("„ganz nach vorn“ ohne Kategorie wird gesagt",
          _z["status"]["kind"] == "warn" and "erst eine Kategorie" in _z["status"]["text"])

    _b.items["Bogen"].confirm_point_id = 5
    _z = _b.scan_item_set({"name": "Bogen", "field": "confirmation", "value": "0"})
    check("„0“ heisst keine Bestätigung — nicht Punkt 0",
          _b.items["Bogen"].confirm_point_id is None
          and "kein Bestätigungsklick mehr" in _z["status"]["text"])

    _b.items["Bogen"].confirm_delay = 0.5
    _z = _b.scan_item_set({"name": "Bogen", "field": "confirmation_delay", "value": -1})
    check("eine negative Wartezeit wird abgelehnt",
          _z["status"]["kind"] == "err" and _b.items["Bogen"].confirm_delay == 0.5)

    # =========================================================================
    section("Studio: ein umbenannter Scan bleibt der offene")
    # =========================================================================
    _z = _b.scan_set({"name": "Inv", "field": "name", "value": "Inventar"})
    check("der offene Scan folgt seinem neuen Namen",
          _b.open_scan == "Inventar" and "Inventar" in _b.scans)

    # =========================================================================
    section("Studio: Lernen meldet, was es getan hat")
    # =========================================================================
    check("jede Art von Ergebnis steht in der Meldung",
          _LearnResult(assigned=set(), new=["A"], variants=["B"], edited=["C"],
                       unchanged={"D"}).text()
          == ("1 neue Item(s), 1 Grössenvariante(n) ergänzt, "
              "1 bestehende Item(s) bearbeitet, 1 bereits vollständig eingerichtet."))
    check("ohne Ergebnis: keine Änderungen", _LearnResult(assigned=set()).text()
          == "Keine Änderungen.")

    try:
        from PIL import Image as _PIL
    except ImportError:
        _PIL = None
    if _PIL is None:
        print("  ----  Vorlagen-Teil uebersprungen (Pillow nicht installiert)")
    else:
        # Eine Vorlage in genau dieser Slot-Grösse gibt es schon — eine zweite
        # wäre eine Kopie, keine Variante.
        _templates = _b.filepath.parent / "templates"
        _templates.mkdir(parents=True, exist_ok=True)
        _PIL.new("RGB", (12, 10), (1, 2, 3)).save(_templates / "bogen.png")
        _b.items["Bogen"].template = "bogen.png"
        _result = _LearnResult(assigned=set())
        _line = {"crop": _PIL.new("RGB", (12, 10), (9, 9, 9)), "category": None, "priority": 1}
        _b._learn_into_existing(_b.items["Bogen"], "Bogen", _line, {}, False, _result)
        check("eine Vorlage in derselben Grösse kommt nicht doppelt dazu",
              _b.items["Bogen"].template_variants == [] and _result.variants == []
              and _result.unchanged == {"Bogen"})

    # =========================================================================
    section("Studio: ein Fund übernimmt die schon feststehende Slot-Grösse")
    # =========================================================================
    _fit = _b._fit_found_region((100, 100, 160, 157), (62, 60))
    check("ein paar Pixel daneben: die feste Grösse gilt",
          (_fit[2] - _fit[0], _fit[3] - _fit[1]) == (62, 60))
    check("deutlich anders gross: der Fund bleibt, wie er ist",
          _b._fit_found_region((100, 100, 140, 140), (62, 60)) == (100, 100, 140, 140))
    check("ohne feste Grösse ebenso",
          _b._fit_found_region((100, 100, 160, 157), None) == (100, 100, 160, 157))

    # =========================================================================
    section("Studio: ein gescheitertes Speichern der Erkennungs-Scans wird gemeldet")
    # =========================================================================
    _cfgs = {"Drache": _NS(name="Drache", owner_sequence=None)}
    check("ein Saver, der False sagt, steht in der Fehlerliste",
          _b._detection_save_each(_cfgs, lambda cfg: False, "boss_scans")
          == ["boss_scans/Drache.json"])

    def _refuse(cfg):
        raise OSError("Platte voll")

    check("ebenso einer, der wirft",
          _b._detection_save_each(_cfgs, _refuse, "boss_scans") == ["boss_scans/Drache.json"])
    check("und wer speichert, fehlt dort",
          _b._detection_save_each(_cfgs, lambda cfg: True, "boss_scans") == []
          and _cfgs["Drache"].owner_sequence == "S")

    # =========================================================================
    section("Studio: Farben eines Bereichs — zu klein ist kein Bereich")
    # =========================================================================
    _corners = [(10, 10, ""), (11, 50, "")]
    _b._await_position = lambda: _corners.pop(0)
    _b._running = lambda: False
    _res = _b.tool_colors({"kind": "region"})
    check("ein Bereich unter zwei Pixeln Breite wird abgelehnt",
          _res == {"ok": False, "message": "Der gewählte Bereich ist zu klein."})
finally:
    _os.chdir(_cwd)
