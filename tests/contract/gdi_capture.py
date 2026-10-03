"""Bildschirm- und Fensteraufnahme über GDI, vor dem Zerlegen festgehalten.

Beide Aufnehmer holen sich vier GDI-Handles und müssen sie auf JEDEM Weg
wieder abgeben — auch wenn mittendrin ein Aufruf scheitert. Ein Leck sieht man
nicht sofort: Windows erlaubt je Prozess rund zehntausend GDI-Objekte, und ein
Item-Scan nimmt mehrere Aufnahmen je Zyklus. Geprüft wird mit einem
nachgebauten `user32`/`gdi32`, deshalb läuft das auch ohne Windows.
"""
import contextlib as _cl
import io as _io

from ._harness import check, section
import autoclicker.platforms.windows as _win


class _Bitmap:
    def __init__(self, width, height):
        self.size = (width, height)
        self.box = None

    def crop(self, box):
        self.box = box
        return self


class _Gdi:
    """Ein user32 UND gdi32 zugleich: zählt, was ausgegeben und abgegeben wird."""

    def __init__(self, fail=(), window=(100, 50, 500, 350), client=(0, 0, 380, 260),
                 origin=(110, 80)):
        self.fail = set(fail)
        self.window, self.client, self.origin = window, client, origin
        self.calls = []
        self.handed_out = set()

    def _answer(self, name, value):
        self.calls.append(name)
        if name in self.fail:
            return 0
        return value

    def _hand_out(self, name, handle):
        value = self._answer(name, handle)
        if value:
            self.handed_out.add(handle)
        return value

    # user32
    def GetDesktopWindow(self):
        return self._answer("GetDesktopWindow", 1)

    def GetWindowRect(self, hwnd, ref):
        r = ref._obj
        r.left, r.top, r.right, r.bottom = self.window
        return self._answer("GetWindowRect", 1)

    def GetClientRect(self, hwnd, ref):
        r = ref._obj
        r.left, r.top, r.right, r.bottom = self.client
        return self._answer("GetClientRect", 1)

    def ClientToScreen(self, hwnd, ref):
        ref._obj.x, ref._obj.y = self.origin
        return self._answer("ClientToScreen", 1)

    def GetWindowDC(self, hwnd):
        return self._hand_out("GetWindowDC", "window_dc")

    def ReleaseDC(self, hwnd, dc):
        self.handed_out.discard(dc)

    def PrintWindow(self, hwnd, dc, flags):
        if "PrintWindow!" in self.fail:
            raise OSError("Zugriff verweigert")
        return self._answer("PrintWindow", 1)

    # gdi32
    def CreateCompatibleDC(self, dc):
        return self._hand_out("CreateCompatibleDC", "mem_dc")

    def CreateCompatibleBitmap(self, dc, width, height):
        self.bitmap_size = (width, height)
        return self._hand_out("CreateCompatibleBitmap", "bitmap")

    def SelectObject(self, dc, obj):
        if obj == "bitmap":
            self.handed_out.add("selected")
            return self._answer("SelectObject", "old_bitmap")
        if obj == "old_bitmap":
            self.handed_out.discard("selected")
        return 1

    def DeleteObject(self, obj):
        self.handed_out.discard(obj)

    def DeleteDC(self, dc):
        self.handed_out.discard(dc)

    def BitBlt(self, dst, x, y, width, height, src, left, top, rop):
        self.blit = (width, height, left, top)
        return self._answer("BitBlt", 1)


@_cl.contextmanager
def _gdi(fake, image=True, desktop=(-1920, 0, 1920, 1080)):
    saved = (_win.user32, _win.gdi32, _win._bitmap_to_image, _win.get_virtual_desktop)
    _win.user32 = _win.gdi32 = fake
    _win._bitmap_to_image = (lambda dc, bmp, w, h: _Bitmap(w, h)) if image else (lambda *a: None)
    _win.get_virtual_desktop = lambda: desktop
    try:
        with _cl.redirect_stderr(_io.StringIO()):
            yield fake
    finally:
        _win.user32, _win.gdi32, _win._bitmap_to_image, _win.get_virtual_desktop = saved


# =============================================================================
section("Fensteraufnahme: Client-Bereich und Bildschirmlage")
# =============================================================================
check("ohne Fenster keine Aufnahme", _win.capture_window(0) is None)

with _gdi(_Gdi()) as _fake:
    _shot = _win.capture_window(42)
_image, _rect = _shot
check("das Fensterbild hat die Grösse des ganzen Fensters", _image.size == (400, 300))
check("ausgeschnitten wird der Client-Bereich (Versatz zum Fensterrand)",
      _image.box == (10, 30, 390, 290))
check("und gemeldet, wo er am Bildschirm liegt", _rect == (110, 80, 490, 340))
check("alle Handles wieder abgegeben", _fake.handed_out == set())

for _step in ("GetWindowRect", "GetClientRect", "ClientToScreen"):
    with _gdi(_Gdi(fail={_step})) as _fake:
        _shot = _win.capture_window(42)
    check(f"scheitert {_step}: kein Bild und kein Handle geholt",
          _shot is None and "GetWindowDC" not in _fake.calls)

with _gdi(_Gdi(client=(0, 0, 0, 260))) as _fake:
    check("ein Client-Bereich ohne Fläche: kein Bild", _win.capture_window(42) is None)

for _step in ("GetWindowDC", "CreateCompatibleDC", "CreateCompatibleBitmap", "PrintWindow"):
    with _gdi(_Gdi(fail={_step})) as _fake:
        _shot = _win.capture_window(42)
    check(f"scheitert {_step}: kein Bild, alles abgegeben",
          _shot is None and _fake.handed_out == set())

with _gdi(_Gdi(fail={"PrintWindow!"})) as _fake:
    _shot = _win.capture_window(42)
check("eine Ausnahme mittendrin: kein Bild, alles abgegeben",
      _shot is None and _fake.handed_out == set())

with _gdi(_Gdi(), image=False) as _fake:
    _shot = _win.capture_window(42)
check("liefert GetDIBits nichts: kein Bild, alles abgegeben",
      _shot is None and _fake.handed_out == set())

# =============================================================================
section("Bildschirmaufnahme per BitBlt")
# =============================================================================
with _gdi(_Gdi()) as _fake:
    _shot = _win._capture_screen_bitblt()
check("ohne Region der ganze virtuelle Desktop, ab seiner linken Kante",
      _shot.size == (3840, 1080) and _fake.blit == (3840, 1080, -1920, 0))
check("alles abgegeben", _fake.handed_out == set())

with _gdi(_Gdi()) as _fake:
    _shot = _win._capture_screen_bitblt(("10", 20, 110.0, 70))
check("eine Region wird zu ganzen Zahlen", _shot.size == (100, 50) and _fake.blit[2:] == (10, 20))

with _gdi(_Gdi(), desktop=None) as _fake:
    check("ohne Desktop-Mass der Rückfall", _win._capture_screen_bitblt() is None)
for _bad in ((1, 2, 3), ("a", 0, 1, 1), 5):
    with _gdi(_Gdi()) as _fake:
        _shot = _win._capture_screen_bitblt(_bad)
    check(f"eine unlesbare Region ({_bad!r}): Rückfall ohne Handle",
          _shot is None and _fake.calls == [])
with _gdi(_Gdi()) as _fake:
    check("eine Region ohne Fläche: Rückfall",
          _win._capture_screen_bitblt((10, 10, 10, 50)) is None and _fake.calls == [])

for _step in ("GetWindowDC", "CreateCompatibleDC", "CreateCompatibleBitmap", "BitBlt"):
    with _gdi(_Gdi(fail={_step})) as _fake:
        _shot = _win._capture_screen_bitblt((0, 0, 10, 10))
    check(f"scheitert {_step}: Rückfall, alles abgegeben",
          _shot is None and _fake.handed_out == set())

with _gdi(_Gdi(), image=False) as _fake:
    _shot = _win._capture_screen_bitblt((0, 0, 10, 10))
check("liefert GetDIBits nichts: Rückfall, alles abgegeben",
      _shot is None and _fake.handed_out == set())


class _Exploding(_Gdi):
    def BitBlt(self, *a):
        raise OSError("Treiber")


with _gdi(_Exploding()) as _fake:
    _shot = _win._capture_screen_bitblt((0, 0, 10, 10))
check("eine Ausnahme mittendrin: Rückfall, alles abgegeben",
      _shot is None and _fake.handed_out == set())
