"""Live-Run: der Ausschnitt um die Stelle steht auch beim reinen Zeitwarten da.

Beim Farb-Warten zeigte der Warte-Kasten einen Live-Ausschnitt um den
Prüf-Pixel, samt Soll- und Ist-Farbe. Bei einer reinen Wartezeit („Klicke in
86 s") stand nur der Countdown — obwohl man mit derselben Frage hinsieht:
steht da, wo gleich geklickt wird, das Richtige? `wait_with_pause_skip`
bekommt dafür die Stelle des Blocks mit (`point`), und `_live_point` schreibt
dieselben Felder wie `_color_wait_status`, damit die Seite beide Kästen mit
EINER Funktion zeichnet (`livePixelBox`).
"""
import contextlib as _cl
import io as _io
import os as _os
import shutil as _sh
import tempfile as _tmp

from ._harness import check, section, studio_web_source
from autoclicker.models import AutoClickerState as _ST, SequenceStep as _STEP
import autoclicker.runtime.actions as _A
import autoclicker.runtime.steps as _S


class _Img:
    """Ein Ausschnitt ohne Pillow: Mittelpixel und ein PNG, das keins ist."""

    def __init__(self, color):
        self._color = color

    def getpixel(self, _xy):
        return self._color

    def save(self, buffer, format):
        buffer.write(b"png")


# =============================================================================
section("Zeitwarten mit Stelle: Bild, Punktfarbe, Ist-Farbe")
# =============================================================================
_orig_shot, _orig_wait = _A.take_screenshot, _A.status.waiting_for
_regions, _written = [], []
_A.take_screenshot = lambda region: _regions.append(region) or _Img((10, 20, 30))
_A.status.waiting_for = lambda state, part, immediately=False: _written.append(part)
try:
    _st = _ST()
    with _cl.redirect_stdout(_io.StringIO()):
        _A.wait_with_pause_skip(_st, 0.05, "L", 1, 1, "Klicke in", point=(100, 200, (10, 20, 40)))
    _box = next((w for w in _written if w), {})
    check("der Kasten bleibt ein Zeitwarten", _box.get("kind") == "time")
    check("mit der Stelle, der Punktfarbe und der gemessenen",
          _box.get("point") == [100, 200] and _box.get("target") == [10, 20, 40]
          and _box.get("actual") == [10, 20, 30] and _box.get("distance") == 10.0)
    check("und dem Ausschnitt als Bild", _box.get("image") == "data:image/png;base64,cG5n")
    check("der Ausschnitt liegt mittig um die Stelle",
          _regions and _regions[0] == (76, 176, 125, 225))
    check("am Ende meldet sich das Warten ab", _written[-1] is None)

    _written.clear()
    _regions.clear()
    with _cl.redirect_stdout(_io.StringIO()):
        _A.wait_with_pause_skip(_st, 0.05, "L", 1, 1, "Taste 'e' in")
    _box = next((w for w in _written if w), {})
    check("ohne Stelle (Taste) kein Bild — und keine Aufnahme dafür",
          "image" not in _box and _regions == [])

    _A.take_screenshot = lambda region: None
    _written.clear()
    with _cl.redirect_stdout(_io.StringIO()):
        _A.wait_with_pause_skip(_st, 0.05, "L", 1, 1, "Klicke in", point=(1, 2, None))
    _box = next((w for w in _written if w), {})
    check("ohne Bild (kein Pillow) bleibt die Stelle stehen, das Bild fehlt",
          _box.get("point") == [1, 2] and _box.get("image") is None
          and _box.get("distance") is None)
finally:
    _A.take_screenshot, _A.status.waiting_for = _orig_shot, _orig_wait

# =============================================================================
section("Welcher Block eine Stelle mitbringt")
# =============================================================================
_click = _STEP(x=5, y=6, point_id=3, recorded_color=(1, 2, 3), delay_before=1)
check("ein Klick bringt seinen Punkt mit", _S._live_target(_click) == (5, 6, (1, 2, 3)))
check("eine Taste nicht", _S._live_target(_STEP(key_press="e")) is None)
_dead = _STEP(x=0, y=0, point_id=9)
_dead.unresolved = True
check("ein Punkt ins Leere auch nicht — kein Bild von (0, 0)", _S._live_target(_dead) is None)

# Der Weg durch den Dispatcher: die Stelle kommt an der Wartezeit an.
_seen = {}
_orig = (_S.wait_with_pause_skip, _S.check_failsafe, _S.print_step_detail, _S._execute_click)
_S.wait_with_pause_skip = lambda *a, **k: _seen.update(k) or True
_S.check_failsafe = lambda state: False
_S.print_step_detail = lambda *a, **k: None
_S._execute_click = lambda *a, **k: True
# Der Dispatcher schreibt den Laufstatus — nicht in den echten `.run.json`.
_sandbox = _tmp.mkdtemp(prefix="live_wait_")
_cwd = _os.getcwd()
_os.chdir(_sandbox)
try:
    with _cl.redirect_stdout(_io.StringIO()):
        _S.execute_step(_ST(), _click, 1, 1, "L")
    check("execute_step reicht die Stelle an die Wartezeit weiter",
          _seen.get("point") == (5, 6, (1, 2, 3)))
finally:
    (_S.wait_with_pause_skip, _S.check_failsafe,
     _S.print_step_detail, _S._execute_click) = _orig
    _os.chdir(_cwd)
    _sh.rmtree(_sandbox, ignore_errors=True)

# =============================================================================
section("Die Seite zeichnet beide Kästen mit derselben Funktion")
# =============================================================================
_js = studio_web_source()
_wait_box = _js[_js.index("function waitBox("):]
_wait_box = _wait_box[:_wait_box.index("\nfunction ", 1)]
check("Farb- und Zeitwarten rufen beide livePixelBox",
      'livePixelBox(w, "target")' in _wait_box and 'livePixelBox(w, "Punkt")' in _wait_box)
check("das Zeitwarten nur, wenn eine Stelle mitkam", "if (w.point) boxEl.appendChild" in _wait_box)
