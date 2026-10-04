"""
Gemeinsame Capture-Helfer für Erkennungs-Editoren (Boss-Scan, Icon-Scan).

Bündelt interaktive Aufnahme-Abläufe, die sonst mehrfach kopiert würden.

**Und die Fragen, die beide Editoren stellen.** Aktionswahl, Klickpunkt,
Verzögerung, die Wahl der Erkennung, Konfidenz, Toleranz und das Ablegen eines
Templates standen in beiden Editoren als Kopie — Wort für Wort, bis auf die
Beschriftung. Eine Korrektur an der einen wäre an der anderen vorbeigegangen;
dieselbe Lage wie bei `ask_priority()` in `_item_fields.py`.
"""

from typing import Optional

from ..models import ACTION_CLICK, ACTION_KEY
from ..utils import (
    safe_input, is_cancel, err, hint, interactive_select, parse_non_negative_float,
    sanitize_filename,
)
from ..winapi import get_cursor_pos, KEY_NAMES
from ..imaging import OPENCV_AVAILABLE, get_pixel_color, select_region
from ..persistence import active_templates_dir, point_for_position

DETECT_TEMPLATE = "Template-Bild aufnehmen"
DETECT_MARKERS = "Farb-Marker setzen"
DETECT_KEEP = "Bestehende Erkennung beibehalten"


def prompt_key(prompt: str = "  Taste (z.B. 'enter', 'space', '1'): ") -> Optional[str]:
    """Fragt eine gültige Taste ab und wiederholt bei Fehleingabe.

    Geteilt von Boss- und Icon-Editor, damit ein Tippfehler nicht die ganze
    Aktion abbricht (konsistent mit der Region-Eingabe).

    Returns:
        Gültiger Tastenname (in KEY_NAMES) oder None bei Abbruch.
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
        if key not in KEY_NAMES:
            print(f"  {err(f'Unbekannte Taste: {key!r}')}")
            print(f"     {hint('Verfügbar u.a.: ' + ', '.join(sorted(KEY_NAMES)[:20]) + ' ...')}")
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


def choose_detection(title: str, can_keep: bool) -> Optional[str]:
    """Wie erkannt wird: Template (nur mit OpenCV), Farb-Marker oder beibehalten.

    Beim Bearbeiten ist „beibehalten" vorgewählt, damit Enter nichts verwirft.
    Gibt das gewählte `DETECT_*` zurück, None bei Abbruch.
    """
    options = ([DETECT_TEMPLATE] if OPENCV_AVAILABLE else []) + [DETECT_MARKERS]
    if can_keep:
        options.append(DETECT_KEEP)
    choice = interactive_select(options, title=title,
                                default=len(options) - 1 if can_keep else 0)
    return None if choice == -1 else options[choice]


def ask_min_confidence(current: float) -> float:
    """Mindest-Konfidenz in Prozent; leer oder unlesbar = der bisherige Wert."""
    try:
        text = safe_input(f"  Min. Konfidenz % (Enter={int(current * 100)}): ").strip()
        if text:
            return max(0.1, min(1.0, float(text) / 100))
    except ValueError:
        pass
    return current


def ask_tolerance(prompt: str, current: int) -> int:
    """Farbtoleranz 1–100; leer oder unlesbar = der bisherige Wert."""
    try:
        text = safe_input(prompt).strip()
        if text:
            return max(1, min(100, int(text)))
    except ValueError:
        pass
    return current


def store_template(state, img, base_name: str) -> str:
    """Legt ein Template im Vorlagenordner der Sequenz ab; gibt den Dateinamen zurück."""
    template_file = f"{sanitize_filename(base_name)}.png"
    template_path = active_templates_dir(state) / template_file
    template_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(template_path)
    print(f"  → Template gespeichert: {template_file}")
    return template_file


def select_action(options: list[tuple[str, str]], title: str,
                  current: Optional[str]) -> Optional[str]:
    """Eine Aktion aus `(Beschriftung, Aktion)`-Paaren; die bisherige ist vorgewählt."""
    actions = [action for _label, action in options]
    default = actions.index(current) if current in actions else 0
    choice = interactive_select([label for label, _action in options],
                                title=title, default=default)
    return None if choice == -1 else actions[choice]


def ask_action_details(state, action: str, result: dict, click_name: str,
                       click_source: str, with_delay: bool) -> bool:
    """Klickpunkt bzw. Taste zur Aktion, dazu die Verzögerung — in `result`.

    False = abgebrochen. Ein Klick wird ein Punkt, gespeichert wird nur seine
    ID: sonst hätte er eine Koordinate, die weder eine Reparatur im
    Punkte-Menü noch eine Kalibrierung über die Punkte je erreicht.
    """
    if action == ACTION_CLICK:
        print("\n  Bewege die Maus zum Klick-Punkt und drücke Enter...")
        try:
            safe_input()
            x, y = get_cursor_pos()
            with state.lock:
                pid = point_for_position(state, x, y, None, click_name, source=click_source)
        except (KeyboardInterrupt, EOFError):
            return False
        result["action_point_id"] = pid
        print(f"  → Klick-Position: ({x}, {y})  [Punkt #{pid}]")
    elif action == ACTION_KEY:
        key = prompt_key()
        if key is None:
            return False
        result["action_key"] = key
    if with_delay:
        result["action_delay"] = _ask_action_delay()
    return True


def _ask_action_delay() -> float:
    """Verzögerung vor der Aktion; leer = 0, ungültig = 0 und gesagt."""
    try:
        text = safe_input("  Verzögerung vor Aktion in Sekunden (Enter=0): ").strip()
    except (KeyboardInterrupt, EOFError):
        return 0
    if not text:
        return 0
    value, problem = parse_non_negative_float(text, "Verzögerung")
    if problem:
        print(f"  → {problem}, verwende 0s")
        return 0
    return value
