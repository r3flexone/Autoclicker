"""Kompatible Fassade für die plattformspezifischen Systemfunktionen.

Der historische Modulname bleibt bestehen, damit Fachlogik und Editoren keine
Betriebssystemauswahl enthalten. Neue Systemaufrufe gehören in ein Backend.

Dazu kommen vier Helfer, die sich allein aus Systemaufrufen ergeben — Fenster
wiederfinden, Ursprung und Mitte des Desktops, Fail-Safe-Ecke. Sie stehen nur
hier und nicht im Vertrag, sonst stünden sie in jedem Backend gleichlautend
noch einmal da.
"""

from .config import CONFIG
from .platforms import load_backend
from .platforms.base import BACKEND_FUNCTIONS
from .platforms.common import *  # noqa: F401,F403 - öffentliche Konstanten
from .platforms.common import PlatformError, desktop_origin

_backend = load_backend()

_missing = [name for name in BACKEND_FUNCTIONS if not hasattr(_backend, name)]
if _missing:
    raise ImportError(
        f"Plattform-Backend {_backend.__name__} ist unvollständig: "
        + ", ".join(_missing))

globals().update({name: getattr(_backend, name) for name in BACKEND_FUNCTIONS})


def get_virtual_origin() -> tuple[int, int]:
    """Linke/obere Kante des virtuellen Desktops. (0, 0), wenn nicht ermittelbar."""
    return desktop_origin(_backend.get_virtual_desktop())


def get_screen_center() -> tuple[int, int]:
    """Mitte des virtuellen Desktops, sonst des Primärmonitors, sonst 960x540."""
    rect = _backend.get_virtual_desktop()
    if rect:
        return (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    size = _backend.get_screen_size()
    if size:
        return size[0] // 2, size[1] // 2
    return 960, 540


def resolve_window(title: str, instance: int = 0, reference_rect=None):
    """Findet eine gespeicherte Fensterquelle erneut.

    Ergebnis ist dasselbe Tupel wie ein Eintrag aus `list_windows()`.
    Exakte Titel gewinnen; bei mehreren gleichnamigen die gemerkte Instanz, und
    ist deren Index weg, das geometrisch ähnlichste Fenster.
    """
    if not isinstance(title, str) or not title.strip():
        return None
    windows = _backend.list_windows()
    target = title.strip().casefold()
    candidates = [e for e in windows if e[0].strip().casefold() == target]
    if not candidates:
        candidates = [e for e in windows if target in e[0].casefold()]
    if not candidates:
        return None
    try:
        index = int(instance)
    except (TypeError, ValueError):
        index = 0
    if 0 <= index < len(candidates):
        return candidates[index]
    if isinstance(reference_rect, (list, tuple)) and len(reference_rect) == 4:
        try:
            ref = tuple(int(v) for v in reference_rect)
            return min(candidates, key=lambda e: sum(
                abs(int(e[1][i]) - ref[i]) for i in range(4)))
        except (TypeError, ValueError):
            pass
    return candidates[0]


def check_failsafe(state=None) -> bool:
    """Prüft, ob die Maus in der Fail-Safe-Ecke ist."""
    cfg = state.config if state else CONFIG
    if not cfg.failsafe_enabled:
        return False
    try:
        x, y = _backend.get_cursor_pos()
    except PlatformError:
        # Ohne bekannte Mausposition ist Weiterklicken nicht sicher.
        return True
    return x <= cfg.failsafe_x and y <= cfg.failsafe_y
