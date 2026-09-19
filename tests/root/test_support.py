"""Plattform-Stubs für per ``unittest discover`` gestartete Logiktests."""


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
