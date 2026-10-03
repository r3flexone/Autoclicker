"""Die Kommandozeilen von `tools/test_ocr.py` und der Farbname im Slot-Tester.

Beide Werkzeuge hatten keinen Test, und beide wurden zerlegt: was ein
Aufruf aus der Kommandozeile macht, ist ihre ganze Oberfläche. Der Slot-Tester
wird nicht importiert — er legt beim Laden einen Ordner neben sich an und
stellt die DPI-Behandlung des Prozesses um. Sein Farbname wird deshalb aus dem
Quelltext geholt und gegen `imaging.get_color_name` gehalten: zwei Kopien
derselben Regel, und die Prüfung sorgt dafür, dass sie es bleiben.
"""
import ast as _ast
import contextlib as _cl
import io as _io
import sys as _sys
from pathlib import Path as _P

from ._harness import check, section, REPO as _REPO

if str(_REPO) not in _sys.path:
    _sys.path.insert(0, str(_REPO))
import tools.test_ocr as _OCR                                       # noqa: E402
from autoclicker.imaging import get_color_name as _imaging_color   # noqa: E402


def _parse(*argv):
    saved = _sys.argv
    _sys.argv = ["test_ocr.py", *argv]
    out = _io.StringIO()
    try:
        with _cl.redirect_stdout(out):
            return _OCR.parse_args(), out.getvalue()
    except SystemExit as e:
        return ("exit", e.code), out.getvalue()
    except Exception as e:                                  # noqa: BLE001
        return ("Absturz", repr(e)), out.getvalue()
    finally:
        _sys.argv = saved


# =============================================================================
section("OCR-Werkzeug: Argumente")
# =============================================================================
check("ohne Argumente: Region per Maus, Englisch, kein Backend",
      _parse()[0] == (None, "screenshot", [], None, ["en"]))
check("alle Optionen zusammen",
      _parse("--backend", "tesseract", "--bosses", "Dragon, Goblin", "--languages", "en, de",
             "--region", "10,20,110,220", "test")[0]
      == ("tesseract", "test", ["Dragon", "Goblin"], (10, 20, 110, 220), ["en", "de"]))
check("eine verdrehte Region wird gerade gerückt",
      _parse("--region", "110,220,10,20")[0][3] == (10, 20, 110, 220))
_res, _out = _parse("--region", "1,2,3")
check("drei Werte: Abbruch mit Grund", _res == ("exit", 1) and "Erwarte 4 Werte" in _out)
_res, _out = _parse("--region", "a,b,c,d")
check("keine Zahlen: Abbruch", _res == ("exit", 1) and "Ungültige --region" in _out)
check("eine Option ohne Wert wird zur Bild-Datei",
      _parse("--backend")[0][1] == "--backend")
check("-h und --help zeigen die Hilfe",
      _parse("-h")[0][1] == "help" and _parse("--help")[0][1] == "help")
check("ein Dateiname ist die Aktion", _parse("boss.png")[0][1] == "boss.png")
check("das Letzte gewinnt", _parse("test", "screenshot")[0][1] == "screenshot")

# =============================================================================
section("OCR-Werkzeug: Ablauf")
# =============================================================================


class _Img:
    size = (4, 3)


# Ohne Pillow bricht `main()` schon vor dem Öffnen einer Datei ab; dann gibt
# es auch nichts zu ersetzen. Gefragt wird VOR `_run()`, nicht darin — dort
# stand ein nackter Import, und die Suite starb in den CI-Jobs ohne Pillow.
try:
    import PIL.Image as _pil
except ImportError:
    _pil = None
_has_pil = _pil is not None


def _run(*argv, available=True, screen=_Img(), region_pick=(0, 0, 5, 5), exists=True,
         open_image=_Img):
    """Führt `main()` mit allem Systemnahen ersetzt aus — `(analysiert mit, Ausgabe)`."""
    import autoclicker.imaging as imaging
    calls = {}
    saved = (_sys.argv, _OCR.is_available, _OCR.analyze, _OCR.test_backends, _OCR.print_help,
             imaging.take_screenshot, imaging.select_region, _OCR.os.path.exists,
             _pil.open if _has_pil else None)

    def shoot(region=None):
        calls["region"] = region
        if isinstance(screen, BaseException):
            raise screen
        return screen

    def opened(path):
        if isinstance(open_image, BaseException):
            raise open_image
        return open_image()

    _sys.argv = ["test_ocr.py", *argv]
    _OCR.is_available = lambda: available
    _OCR.analyze = lambda backend, img, bosses, languages: calls.update(analyzed=(backend, img, bosses))
    _OCR.test_backends = lambda: calls.update(tested=True)
    _OCR.print_help = lambda: calls.update(helped=True)
    imaging.take_screenshot = shoot
    imaging.select_region = lambda: region_pick
    _OCR.os.path.exists = lambda path: exists
    if _has_pil:
        _pil.open = opened
    out = _io.StringIO()
    try:
        with _cl.redirect_stdout(out):
            _OCR.main()
    finally:
        (_sys.argv, _OCR.is_available, _OCR.analyze, _OCR.test_backends, _OCR.print_help,
         imaging.take_screenshot, imaging.select_region, _OCR.os.path.exists,
         pil_open) = saved
        if _has_pil:
            _pil.open = pil_open
    return calls, out.getvalue()


_calls, _out = _run("--help")
check("Hilfe: nur die Hilfe", _calls == {"helped": True})
_calls, _out = _run("test", available=False)
check("Statusprüfung läuft auch ohne Backend", _calls == {"tested": True})
_calls, _out = _run(available=False)
check("ohne Backend: Hinweis statt Analyse",
      "analyzed" not in _calls and "Kein OCR-Backend installiert" in _out)

if not _has_pil:
    print("  ----  uebersprungen (Pillow nicht installiert)")
else:
    _calls, _out = _run("--region", "1,2,3,4", "--bosses", "Hydra")
    check("mit Region: genau dieser Ausschnitt wird analysiert",
          _calls["region"] == (1, 2, 3, 4) and _calls["analyzed"][2] == ["Hydra"]
          and "Region (1, 2, 3, 4)" in _out)
    _calls, _out = _run()
    check("ohne Region: der gewählte Bereich",
          _calls["region"] == (0, 0, 5, 5) and "analyzed" in _calls)
    _calls, _out = _run(region_pick=None)
    check("abgebrochene Auswahl: keine Analyse",
          "analyzed" not in _calls and "Abgebrochen" in _out)
    _calls, _out = _run("--region", "1,2,3,4", screen=OSError("kein Bildschirm"))
    check("ein scheiternder Screenshot wird gemeldet",
          "analyzed" not in _calls and "Screenshot fehlgeschlagen: kein Bildschirm" in _out)
    _calls, _out = _run("--region", "1,2,3,4", screen=None)
    check("ein leerer Screenshot: kein Bild", "analyzed" not in _calls and "Kein Bild" in _out)
    _calls, _out = _run("boss.png", exists=False)
    check("fehlende Datei", "analyzed" not in _calls and "Datei nicht gefunden: boss.png" in _out)
    _calls, _out = _run("boss.png", open_image=OSError("kaputt"))
    check("unlesbare Datei", "analyzed" not in _calls and "konnte nicht geladen werden: kaputt" in _out)
    _calls, _out = _run("boss.png", "--backend", "easyocr")
    check("lesbare Datei: analysiert mit dem gewählten Backend",
          _calls["analyzed"][0] == "easyocr" and "Bild geladen: boss.png" in _out)

# =============================================================================
section("Slot-Tester: derselbe Farbname wie die App")
# =============================================================================


def _functions_from(path: _P, names: set) -> dict:
    """Die genannten Funktionen aus dem Quelltext, ohne das Modul zu laden."""
    tree = _ast.parse(path.read_text(encoding="utf-8"))
    module = _ast.Module(body=[node for node in tree.body
                               if isinstance(node, _ast.FunctionDef) and node.name in names
                               or isinstance(node, _ast.Assign)
                               and any(getattr(t, "id", "").startswith("_") for t in node.targets)],
                         type_ignores=[])
    namespace = {"Optional": __import__("typing").Optional}
    exec(compile(module, str(path), "exec"), namespace)
    return namespace


# Sie waren es nicht: die App kennt für zwei gleich starke Kanäle Gelb, Magenta
# und Cyan, der Slot-Tester sagte dort „Gemischt". Ein Debug-Werkzeug, das
# dieselbe Marker-Farbe anders nennt als der Item-Editor, lässt einen den
# Unterschied suchen, wo keiner ist.
_slot = _functions_from(_REPO / "tools" / "slot_tester.py",
                        {"get_color_name", "_dominant_color_name", "_mixed_color_name"})
_ascii = str.maketrans({"ü": "ue", "ö": "oe", "ä": "ae"})
_grid = range(0, 256, 17)
_differ = [(r, g, b) for r in _grid for g in _grid for b in _grid
           if _slot["get_color_name"]((r, g, b)) != _imaging_color((r, g, b)).translate(_ascii)]
check("auf einem Raster von 4096 Farben dieselben Namen wie imaging", _differ == [])
if _differ:
    print(f"        zuerst verschieden: {_differ[:3]}")
