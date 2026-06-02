"""
Gemeinsame Capture-Helfer für Erkennungs-Editoren (Boss-Scan, Icon-Scan).

Bündelt interaktive Aufnahme-Abläufe, die sonst mehrfach kopiert würden.
"""

from typing import Optional

from ..utils import safe_input, is_cancel, err
from ..winapi import get_cursor_pos
from ..imaging import get_pixel_color


def capture_markers() -> Optional[list[tuple[int, int, int]]]:
    """Nimmt Farb-Marker per Mausposition auf (Enter = Farbe unter Cursor lesen).

    Returns:
        Liste mit mindestens einem (r,g,b)-Marker, oder None bei Abbruch.
    """
    marker_colors: list[tuple[int, int, int]] = []
    print("\n  Farb-Marker aufnehmen (Maus auf Farbpunkt bewegen, Enter drücken)")
    print("  'done' oder 'd' wenn fertig, 'cancel' zum Abbrechen")
    while True:
        try:
            inp = safe_input(f"  Marker {len(marker_colors) + 1}: ").strip().lower()
            if inp in ("done", "d"):
                break
            if is_cancel(inp):
                return None
            if inp == "" or inp == "enter":
                x, y = get_cursor_pos()
                color = get_pixel_color(x, y)
                if color:
                    marker_colors.append(color)
                    print(f"    → RGB{color} bei ({x},{y})")
                else:
                    print("    → Konnte Farbe nicht lesen!")
        except (KeyboardInterrupt, EOFError):
            return None

    if not marker_colors:
        print(f"  {err('Mindestens 1 Marker benötigt!')}")
        return None
    return marker_colors
