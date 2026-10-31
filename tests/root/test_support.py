"""Plattform-Stubs und Bild-Skip für per ``unittest discover`` gestartete Logiktests."""

import unittest

# Pillow ist optional, wie überall im Baum. Der Import stand in den Modulen
# selbst oben, und ohne Pillow starben sie schon beim LADEN - womit
# `python -m unittest test_*.py` gar nicht erst sammelte und es zwei
# Testkommandos brauchte. Übersprungen wird jetzt, was Bilder braucht; der Rest
# läuft.
try:
    from PIL import Image
    PILLOW = True
except ImportError:                                              # pragma: no cover
    Image = None
    PILLOW = False

needs_pillow = unittest.skipUnless(PILLOW, "Pillow nicht installiert")


def install_platform_stubs() -> None:
    import subprocess  # noqa: F401 - muss vor dem msvcrt-Stub geladen sein
    import ctypes
    import sys
    import types

    try:
        import msvcrt  # noqa: F401
    except ImportError:
        sys.modules.setdefault("msvcrt", types.ModuleType("msvcrt"))

    if hasattr(ctypes, "windll"):
        return

    class StubFunction:
        argtypes = None
        restype = None

        def __call__(self, *args, **kwargs):
            return 0

    class StubLibrary:
        def __getattr__(self, name):
            value = StubFunction()
            setattr(self, name, value)
            return value

    class StubWinDLL:
        def __getattr__(self, name):
            value = StubLibrary()
            setattr(self, name, value)
            return value

        def LoadLibrary(self, name):
            return StubLibrary()

    ctypes.windll = StubWinDLL()
    ctypes.WinDLL = lambda *args, **kwargs: StubLibrary()
    ctypes.WINFUNCTYPE = ctypes.CFUNCTYPE
