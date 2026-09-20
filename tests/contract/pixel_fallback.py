"""`get_screen_pixel`: der Rückfall darf nicht wieder bei sich selbst landen.

Liefert GDI `CLR_INVALID` (Stelle ausserhalb jedes Monitors — auf einem
virtuellen Desktop aus drei verschieden hohen Bildschirmen gibt es solche
Zonen), fiel die Funktion auf `imaging.get_pixel_color()` zurück. Und die ist
`get_screen_pixel` über die Fassade: beide riefen einander bis zum
`RecursionError`, den jede Ebene mit `except Exception: return None`
schluckte. Gemessen: 3,5 s für ein `None` — im Maus-Hook hätte Windows den
Hook dafür ausgehängt. Jetzt geht der Rückfall über den Bildschirm-Aufnehmer
(1×1-Ausschnitt) und niemals über `imaging`.
"""
import time as _time

from ._harness import check, section
import autoclicker.platforms.windows as _win
import autoclicker.imaging as _imaging

section("get_screen_pixel ohne Rekursion")


class _Image:
    def getpixel(self, xy):
        return (11, 22, 33, 255)


_orig = (_win.gdi32.GetPixel, _win.capture_screen, _imaging.get_pixel_color)
_captured: list = []
try:
    # GDI kennt die Stelle nicht ...
    _win.gdi32.GetPixel = lambda hdc, x, y: 0xFFFFFFFF
    # ... der Aufnehmer schon.
    _win.capture_screen = lambda region=None: _captured.append(region) or _Image()

    def _forbidden(x, y):
        raise AssertionError("get_screen_pixel ruft imaging.get_pixel_color — der Kreis")
    _imaging.get_pixel_color = _forbidden

    _began = _time.perf_counter()
    _color = _win.get_screen_pixel(-1870, -342)
    _took = _time.perf_counter() - _began
    check("bei CLR_INVALID kommt die Farbe aus einem 1x1-Ausschnitt",
          _color == (11, 22, 33) and _captured == [(-1870, -342, -1869, -341)])
    check("und zwar sofort, ohne Rekursion", _took < 0.5)

    _win.capture_screen = lambda region=None: None
    check("kann auch der Aufnehmer nichts, ist es None — ohne Umweg",
          _win.get_screen_pixel(1, 1) is None)
finally:
    _win.gdi32.GetPixel, _win.capture_screen, _imaging.get_pixel_color = _orig

# Der Kreis darf nicht zurueckkommen: die Fassade zeigt auf das Backend, und
# das Backend darf `imaging` nicht kennen.
import inspect as _inspect
check("das Windows-Backend importiert nichts aus imaging",
      "from ..imaging import" not in _inspect.getsource(_win))
