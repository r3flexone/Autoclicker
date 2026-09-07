"""Das Gerüst, das alle Test-Module teilen: Stubs, Zähler, `check`, `section`.

Der Einstiegspunkt bleibt genau einer — `python tests/test_logic.py`. Neue
Sektionen kommen in ein eigenes Modul unter `tests/vertrag/`, das hier sein
Gerüst holt und am Ende von `test_logic.py` importiert wird. Die Zähler leben
in DIESEM Modul: sonst zählte jedes Modul für sich.

Die Stubs müssen vor dem ersten `autoclicker`-Import stehen, deshalb macht
dieses Modul sie beim Import. Ein Test-Modul, das vorher etwas aus
`autoclicker` importiert, bricht auf Linux mit `ModuleNotFoundError: msvcrt` ab.

So sieht ein neues Modul aus:

    from ._harness import check, section

    section("Was hier geprueft wird")
    from autoclicker.irgendwas import funktion
    check("die Eigenschaft, um die es geht", funktion(1) == 2)
"""
import sys
import types
from pathlib import Path

# MUSS vor dem msvcrt-Stub geladen werden: `subprocess` erkennt Windows daran,
# dass sich msvcrt importieren laesst, und zieht dann `_winapi` nach - das es auf
# Linux nicht gibt. Wer danach etwas importiert, das subprocess braucht (z.B.
# PIL.ImageGrab), bekommt einen ModuleNotFoundError und haelt Pillow faelschlich
# fuer nicht installiert. Genau daran lief der Bild-Teil der Scan-Tests ins Leere.
import subprocess  # noqa: F401

try:
    import msvcrt  # noqa: F401  (echtes Modul auf Windows)
except ImportError:
    sys.modules["msvcrt"] = types.ModuleType("msvcrt")  # Stub auf Linux/Mac

# ctypes.windll gibt es nur auf Windows. Damit auch die Runtime-/Debug-Schicht
# pruefbar ist (die importiert winapi), wird es auf Linux/Mac minimal gestubbt.
# Die Stubs tun nichts - geprueft wird ausschliesslich Logik, keine echten
# Maus-Aktionen.
import ctypes

if not hasattr(ctypes, "windll"):
    class _StubFn:
        def __init__(self, *a):
            self.argtypes = None
            self.restype = None

        def __call__(self, *a, **kw):
            return 0

    class _StubLib:
        def __getattr__(self, name):
            fn = _StubFn()
            setattr(self, name, fn)
            return fn

    class _StubWinDLL:
        def __getattr__(self, name):
            lib = _StubLib()
            setattr(self, name, lib)
            return lib

        def LoadLibrary(self, name):
            return _StubLib()

    ctypes.windll = _StubWinDLL()
    ctypes.WinDLL = lambda *a, **kw: _StubLib()
    ctypes.WINFUNCTYPE = ctypes.CFUNCTYPE

REPO = Path(__file__).resolve().parent.parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

PASS, FAIL = 0, 0


def check(name: str, cond) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}")


def section(titel: str) -> None:
    print(f"\n=== {titel} ===")


def studio_web_source() -> str:
    """Kompletter Studio-Quellvertrag aus HTML, CSS und JavaScript."""
    web = REPO / "autoclicker/editors/sequence_studio/web"
    return "\n".join(
        (web / name).read_text(encoding="utf-8")
        for name in ("index.html", "styles.css", "app.js")
        if (web / name).exists()
    )
