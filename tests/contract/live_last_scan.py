"""Live-Run: was der letzte Item-Scan gesehen hat.

Im Live-Run stand während eines Scans nur „Item-Scan 'Inventar' (alle)" und
danach der Zähler „Items". Welche Items er erkannt hat — und ob das, was da
liegt, überhaupt erkannt wird —, sah man nur in der Konsole. Der Block schreibt
deshalb nach jedem Scan `last_scan` in den Laufstatus (der nächste überschreibt
ihn), die Brücke hängt die Vorlagenbilder an, und die Seite zeigt je Item eine
Kachel.
"""
import contextlib as _cl
import io as _io
import os as _os
import shutil as _sh
import tempfile as _tmp
from pathlib import Path as _P

from ._harness import check, section, studio_web_source
from autoclicker.models import (
    AutoClickerState as _ST, ItemProfile as _IP, ItemScanConfig as _ISC,
    ItemSlot as _SLOT, Sequence as _SEQ, SequenceStep as _STEP,
)
import autoclicker.runtime.item_scan as _IS
import autoclicker.runtime.steps as _S

# =============================================================================
section("Laufzeit: der Scan meldet, was er gesehen und geklickt hat")
# =============================================================================
_written = []
_clicked = []
# Ein „Bild" je Slot ist hier seine Region; erkannt wird über eine Tabelle.
_sees = {}


def _match(item, img, tol, state, debug, label="gefunden", return_score=False):
    fits = _sees.get(img) == item.name
    return (fits, 1.0 if fits else 0.0) if return_score else fits


_orig = (_IS._check_profile_match, _IS.take_screenshot, _IS._park_mouse_for_scan,
         _IS.safe_click, _S.status.write_status, _S.check_failsafe)
_IS._check_profile_match = _match
_IS.take_screenshot = lambda region=None: region
_IS._park_mouse_for_scan = lambda p: None
_IS.safe_click = lambda st, x, y, label="": (_clicked.append(label), True)[1]
_S.status.write_status = lambda st, part, immediately=False: _written.append(part)
_S.check_failsafe = lambda st: False


def _run(immediate: bool, sees: dict):
    _written.clear()
    _clicked.clear()
    _sees.clear()
    _sees.update(sees)
    st = _ST()
    st.config.scan_click_immediate = immediate
    st.config.scan_item_click_delay = 0
    st.config.scan_slot_delay = 0
    st.active_sequence = _SEQ(name="Farm")
    slots = [_SLOT(name=f"S{i}", scan_region=(i, 0, i + 8, 8), click_pos=(i, i))
             for i in (1, 2, 3, 4)]
    items = [_IP(name="Kohle", marker_colors=[(1, 2, 3)], category="Erz", priority=1,
                 template="kohle.png"),
             _IP(name="Eisen", marker_colors=[(4, 5, 6)], category="Erz", priority=5),
             _IP(name="Fisch", marker_colors=[(7, 8, 9)], priority=2)]
    st.item_scans = {"inv": _ISC(name="inv", slots=slots, items=items, reverse=False)}
    with _cl.redirect_stdout(_io.StringIO()):
        _S._execute_item_scan_step(st, _STEP(item_scan="inv"), 1, 1, "L")
    reports = [p["last_scan"] for p in _written if "last_scan" in p]
    return reports[-1] if reports else None


try:
    # S1 Kohle, S2 Eisen (gleiche Kategorie, schlechter), S3 Kohle, S4 leer.
    _sees_value = {(1, 0, 9, 8): "Kohle", (2, 0, 10, 8): "Eisen", (3, 0, 11, 8): "Kohle"}
    for _immediate in (False, True):
        _mode = "Immediate" if _immediate else "normal"
        _r = _run(_immediate, _sees_value)
        check(f"{_mode}: nach dem Scan steht er im Laufstatus",
              _r is not None and _r["name"] == "inv")
        check(f"{_mode}: gezählt wird jeder gescannte Slot, auch der leere",
              _r["slots"] == 4 and _r["recognized"] == 3)
        _by = {e["item"]: e for e in _r["items"]}
        check(f"{_mode}: je Item EIN Eintrag, mit seinen Slots",
              set(_by) == {"Kohle", "Eisen"} and _by["Kohle"]["slots"] == ["S1", "S3"])
        # Eisen ist gesehen, aber weggefiltert (Kategorie Erz, Kohle ist besser):
        # die Kachel steht trotzdem da — „erkennt er das?" ist die erste Frage.
        check(f"{_mode}: auch Weggefiltertes steht da, nur ohne Klick",
              _by["Eisen"]["clicked"] == 0 and _by["Kohle"]["clicked"] >= 1)
        check(f"{_mode}: Geklicktes steht vorn", _r["items"][0]["item"] == "Kohle")
        check(f"{_mode}: die Vorlage steht als Dateiname mit Ordner drin",
              _by["Kohle"]["template"] == "kohle.png"
              and _r["templates"].endswith(_os.path.join("farm", "templates")))

    # Im Immediate-Modus ruft der Block den Scan je Slot — die Aufnahme des
    # Bereichs darf trotzdem nur EINMAL passieren, und zwar vor dem ersten Klick:
    # danach sähe das Inventar anders aus als das, was gescannt wurde.
    _events = []
    _IS.take_screenshot = lambda region=None: (
        _events.append("frame" if region[2] - region[0] > 8 else "slot"), region)[1]
    _IS.safe_click = lambda st, x, y, label="": (_events.append("click"), True)[1]
    _run(True, _sees_value)
    check("Immediate: genau eine Bereichsaufnahme, vor dem ersten Klick",
          _events.count("frame") == 1 and _events.index("frame") < _events.index("click"))
    _IS.take_screenshot = lambda region=None: region
    _IS.safe_click = lambda st, x, y, label="": (_clicked.append(label), True)[1]

    _empty = _run(False, {})
    check("vier leere Slots sind trotzdem ein Scan — er steht da, ohne Items",
          _empty is not None and _empty["recognized"] == 0 and _empty["items"] == [])
    _written.clear()
    _st = _ST()
    _st.item_scans = {}
    with _cl.redirect_stdout(_io.StringIO()):
        _S._execute_item_scan_step(_st, _STEP(item_scan="fehlt"), 1, 1, "L")
    check("ein Scan, der gar nicht lief, überschreibt den letzten nicht",
          not any("last_scan" in p for p in _written))
finally:
    (_IS._check_profile_match, _IS.take_screenshot, _IS._park_mouse_for_scan,
     _IS.safe_click, _S.status.write_status, _S.check_failsafe) = _orig


# =============================================================================
section("Brücke: die Vorlagenbilder kommen dazu")
# =============================================================================
from autoclicker.editors.sequence_studio.bridge import StudioBridge as _SB  # noqa: E402

_sandbox = _P(_tmp.mkdtemp(prefix="last_scan_"))
try:
    (_sandbox / "templates").mkdir()
    (_sandbox / "templates" / "kohle.png").write_bytes(b"\x89PNG-kohle")
    _ls = {"templates": str(_sandbox / "templates"), "items": [
        {"item": "Kohle", "template": "kohle.png"},
        {"item": "Eisen", "template": "../../geheim.png"},
        {"item": "Fisch", "template": ""}]}
    _SB._last_scan_images(_SB.__new__(_SB), _ls)
    _img = _ls["items"][0].get("image", "")
    check("eine vorhandene Vorlage kommt als data:-URL an",
          _img.startswith("data:image/png;base64,"))
    check("ein Pfad mit .. führt nirgendwohin", "image" not in _ls["items"][1])
    check("ohne Vorlage kein Bild", "image" not in _ls["items"][2])
finally:
    _sh.rmtree(_sandbox, ignore_errors=True)

# =============================================================================
section("Seite: die Karte steht im Lauf und in der Zusammenfassung")
# =============================================================================
_web = studio_web_source()
check("im Lauf, unter dem Block", "z.last_scan ? lastScanPanel(z.last_scan, now) : null" in _web)
check("und nach dem Ende", "lastScanPanel(z.last_scan, Date.now() / 1000)" in _web)
check("geklickt ist ringsum markiert", ".last-scan-item.clicked{" in _web)
check("das Bild trägt je Slot einen Rahmen", "lastScanPicture(ls.picture)" in _web
      and ".last-scan-box.clicked{" in _web)

# =============================================================================
section("Bild: die Slot-Ausschnitte zusammengesetzt, mit Rahmen je Slot")
# =============================================================================
from autoclicker.imaging import PILLOW_AVAILABLE as _PIL, compose_regions as _compose  # noqa: E402

check("ohne Ausschnitte kein Bild", _compose([]) is None)
check("was kein Bild ist, wird kein Bild", _compose([((0, 0, 8, 8), (0, 0, 8, 8))]) is None)
if _PIL:
    from PIL import Image as _Image
    from autoclicker.config import LAST_SCAN_IMAGE_FILE as _FILE

    _red = _Image.new("RGB", (10, 10), (200, 0, 0))
    _blue = _Image.new("RGB", (10, 10), (0, 0, 200))
    _png, _left, _top, _scale, _w, _h = _compose(
        [((100, 50, 110, 60), _red), ((130, 50, 140, 60), _blue)])
    _back = _Image.open(_io.BytesIO(_png)).convert("RGB")
    check("das Bild umschliesst genau die Ausschnitte",
          (_left, _top, _w, _h, _scale) == (100, 50, 40, 10, 1.0))
    check("jeder Ausschnitt steht an seiner Stelle",
          _back.getpixel((5, 5)) == (200, 0, 0) and _back.getpixel((35, 5)) == (0, 0, 200))
    check("dazwischen bleibt der Grund dunkel", sum(_back.getpixel((20, 5))) < 60)
    _big = _compose([((0, 0, 2000, 1000), _Image.new("RGB", (2000, 1000)))], max_side=900)
    check("verkleinert auf die längere Kante", (_big[4], _big[5]) == (900, 450))

    _cwd = _os.getcwd()
    _sandbox = _P(_tmp.mkdtemp(prefix="last_scan_pic_"))
    _os.chdir(_sandbox)
    try:
        _report = _S._ScanReport()
        _s1 = _SLOT(name="S1", scan_region=(100, 50, 110, 60), click_pos=(105, 55))
        _s2 = _SLOT(name="S2", scan_region=(130, 50, 140, 60), click_pos=(135, 55))
        _s3 = _SLOT(name="S3", scan_region=(160, 50, 170, 60), click_pos=(165, 55))
        _kohle = _IP(name="Kohle", marker_colors=[(1, 2, 3)])
        _report.seen = [(_s1, _kohle, _red), (_s2, _kohle, _blue), (_s3, None, _red)]
        _report.clicked = [("Kohle", (135, 55))]
        _pic = _S._scan_picture(_report)
        check("das Bild liegt als Datei neben dem Laufstatus", _P(_FILE).is_file())
        _boxes = {b["slot"]: b for b in _pic["boxes"]}
        check("je gescanntem Slot ein Rahmen, in Bildpixeln",
              _boxes["S2"]["x"] == 30 and _boxes["S2"]["w"] == 10 and len(_boxes) == 3)
        check("geklickt ist der Slot, auf den geklickt wurde — nicht jeder mit dem Item",
              _boxes["S2"]["clicked"] and not _boxes["S1"]["clicked"])
        check("ein leerer Slot sagt, dass nichts erkannt wurde",
              _boxes["S3"]["item"] == "" and not _boxes["S3"]["clicked"])
        # Mit Screenshot des Bereichs gilt der — die Ausschnitte sind nur Rückfall.
        _report.frame = (_Image.new("RGB", (94, 34), (0, 200, 0)), (88, 38, 182, 72))
        _framed = _S._scan_picture(_report)
        _shot = _Image.open(_FILE).convert("RGB")
        check("mit Screenshot zeigt das Bild den Screenshot, nicht die Ausschnitte",
              _shot.size == (94, 34) and _shot.getpixel((5, 5)) == (0, 200, 0))
        _fb = {b["slot"]: b for b in _framed["boxes"]}
        check("und die Rahmen stehen relativ zu seiner Ecke",
              (_fb["S1"]["x"], _fb["S1"]["y"]) == (12, 12))
        _ls = {"picture": dict(_pic)}
        _SB._last_scan_images(_SB.__new__(_SB), _ls)
        check("die Brücke hängt das Bild an",
              _ls["picture"].get("image", "").startswith("data:image/png;base64,"))
    finally:
        _os.chdir(_cwd)
        _sh.rmtree(_sandbox, ignore_errors=True)

    # --- Der Bereich um alle Slots, einmal je Block ---
    _regions = [(100, 50, 110, 60), (160, 90, 170, 100)]
    _shots = []
    _orig_shot = _IS.take_screenshot
    _IS.take_screenshot = lambda region=None: (_shots.append(region), _red)[1]
    try:
        _f = _IS._scan_frame(_regions, None, None)
        check("ohne Fenster: EINE Aufnahme um alle Slots, mit Rand",
              _shots == [(88, 38, 182, 112)] and _f[1] == (88, 38, 182, 112))
        _window = _Image.new("RGB", (120, 80), (9, 9, 9))
        _shots.clear()
        _f = _IS._scan_frame(_regions, _window, (95, 45, 215, 125))
        check("mit Fenster: aus der Fensteraufnahme, ohne zweite Aufnahme",
              _shots == [] and _f is not None)
        check("und am Fensterrand abgeschnitten statt über ihn hinaus",
              _f[1] == (95, 45, 182, 112) and _f[0].size == (87, 67))
    finally:
        _IS.take_screenshot = _orig_shot
else:
    print("  (Bild-Tests übersprungen: Pillow fehlt)")
