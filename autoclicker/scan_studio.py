"""
Einstiegspunkt fürs visuelle Scan-Studio (eigener Subprocess).

Aufruf:
    python -m autoclicker.scan_studio

Nimmt einen Vollbild-Screenshot auf, ermittelt den Ursprung des virtuellen
Desktops (für korrektes Koordinaten-Mapping) und öffnet den Screenshot-Canvas.
Wird vom Hotkey-Handler (handle_scan_studio) per subprocess.Popen gestartet,
damit der Dear-PyGui-Event-Loop nicht mit der Hotkey-Message-Pump kollidiert.
Liest/schreibt slots/slots.json — dieselbe Datei wie der Konsolen-Slot-Editor.
"""

import sys

from .persistence import init_directories
from .persistence.paths import SLOTS_FILE


def _virtual_origin() -> tuple[int, int]:
    """Linke/obere Kante des virtuellen Desktops (Multi-Monitor-Offset)."""
    try:
        import ctypes
        SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
        u = ctypes.windll.user32
        return u.GetSystemMetrics(SM_XVIRTUALSCREEN), u.GetSystemMetrics(SM_YVIRTUALSCREEN)
    except (AttributeError, OSError):
        return 0, 0


def main(argv: list[str]) -> int:
    try:
        import dearpygui.dearpygui  # noqa: F401
    except ImportError:
        print("Dear PyGui ist nicht installiert. Installieren mit:")
        print("    pip install dearpygui")
        return 1

    from .imaging import take_screenshot, PILLOW_AVAILABLE
    if not PILLOW_AVAILABLE:
        print("Pillow ist nicht installiert. Installieren mit:")
        print("    pip install pillow")
        return 1

    init_directories()
    img = take_screenshot(None)
    if img is None:
        print("Screenshot fehlgeschlagen — Scan-Studio kann nicht starten.")
        return 1

    vleft, vtop = _virtual_origin()

    from .editors.scan_canvas.canvas_dpg import ScanStudioApp
    app = ScanStudioApp(img, vleft, vtop, SLOTS_FILE)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
