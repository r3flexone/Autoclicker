"""
Gemeinsame Capture-Helfer für Erkennungs-Editoren (Boss-Scan, Icon-Scan).

Bündelt interaktive Aufnahme-Abläufe, die sonst mehrfach kopiert würden.
"""

from typing import Optional

from ..utils import safe_input, is_cancel, err, hint, interactive_select, col
from ..winapi import get_cursor_pos, VK_CODES
from ..imaging import get_pixel_color, select_region


def prompt_key(prompt: str = "  Taste (z.B. 'enter', 'space', '1'): ") -> Optional[str]:
    """Fragt eine gültige Taste ab und wiederholt bei Fehleingabe.

    Geteilt von Boss- und Icon-Editor, damit ein Tippfehler nicht die ganze
    Aktion abbricht (konsistent mit der Region-Eingabe).

    Returns:
        Gültiger Tastenname (in VK_CODES) oder None bei Abbruch.
    """
    while True:
        try:
            key = safe_input(f"{prompt}{hint('(cancel = zurück)')} ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            return None
        if is_cancel(key):
            return None
        if not key:
            print(f"  {err('Keine Taste angegeben!')}")
            continue
        if key not in VK_CODES:
            print(f"  {err(f'Unbekannte Taste: {key!r}')}")
            print(f"     {hint('Verfügbar u.a.: ' + ', '.join(sorted(VK_CODES.keys())[:20]) + ' ...')}")
            continue
        return key


def select_scan_region(existing_region: Optional[tuple] = None
                       ) -> Optional[tuple[int, int, int, int]]:
    """Lässt den User eine Scan-Region wählen (Maus / manuell / beibehalten).

    Die manuelle Koordinaten-Eingabe fragt bei Tippfehlern erneut, statt den
    ganzen Editor abzubrechen. ESC/cancel im Menü bricht ab (None); beim
    Bearbeiten ist "beibehalten" vorausgewählt.

    Returns:
        (x1,y1,x2,y2) oder None bei Abbruch.
    """
    options = ["Per Maus auswählen (2 Ecken)", "Koordinaten manuell eingeben"]
    if existing_region is not None:
        options.append("Bestehende Region beibehalten")

    while True:
        choice = interactive_select(
            options, default=len(options) - 1 if existing_region is not None else 0)
        if choice == -1:
            return None

        chosen = options[choice]
        if chosen == "Bestehende Region beibehalten":
            return existing_region

        if chosen == "Per Maus auswählen (2 Ecken)":
            result = select_region()
            if result:
                print(f"  → Region: ({result[0]},{result[1]}) → ({result[2]},{result[3]})")
                return tuple(result)
            print(f"  {err('Region-Auswahl fehlgeschlagen!')} {hint('(nochmal versuchen)')}")
            continue

        # Manuelle Eingabe — mit Wiederhol-Schleife bei Fehleingabe
        region = _prompt_region_coords()
        if region is not None:
            print(f"  → Region: ({region[0]},{region[1]}) → ({region[2]},{region[3]})")
            return region
        # _prompt_region_coords gab None zurück = Abbruch der Eingabe → zurück ins Menü


def _prompt_region_coords() -> Optional[tuple[int, int, int, int]]:
    """Fragt 'x1,y1,x2,y2' ab und wiederholt bei Fehleingabe. None = Abbruch."""
    while True:
        try:
            inp = safe_input(f"  Region (x1,y1,x2,y2) {hint('(cancel = zurück)')}: ").strip()
        except (KeyboardInterrupt, EOFError):
            return None
        if is_cancel(inp):
            return None
        if not inp:
            continue
        try:
            parts = [int(x.strip()) for x in inp.split(",")]
        except ValueError:
            print(f"  {err('Nur ganze Zahlen, durch Komma getrennt!')} {hint('z.B. 100,200,400,500')}")
            continue
        if len(parts) != 4:
            print(f"  {err('Bitte genau 4 Werte!')} {hint('x1,y1,x2,y2')}")
            continue
        if parts[2] <= parts[0] or parts[3] <= parts[1]:
            print(f"  {err('Ungültiger Bereich! x2>x1 und y2>y1 erforderlich.')}")
            continue
        return tuple(parts)


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
                if not marker_colors:
                    print("  " + err("Mindestens 1 Marker benötigt!") + " "
                          + hint("(Enter = Farbe aufnehmen, 'cancel' = abbrechen)"))
                    continue
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

    return marker_colors
