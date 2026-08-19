"""
Geteilte Helfer für den Sequenz-Editor.

apply_else_to_step + parse_else_condition werden überall dort gebraucht wo ein
Step einen optionalen `else <Bedingung>`-Suffix haben kann (scan, boss, watcher,
wait, pixel-click). capture_pixel_color liest die aktuelle Maus-Position+Farbe
und parse_uhrzeit parst eine HH:MM-Eingabe. Bewusst NICHT parse_time_input wie in
utils/parsing.py: die heisst gleich, nimmt auch einen String, gibt aber ein Tripel
(Sekunden, Text, Zeitstempel) fuer den Countdown zurueck. Zwei Vertraege, zwei Namen.
"""

import re
from typing import Optional

from ...imaging import PILLOW_AVAILABLE, get_pixel_color
from ...models import ElseConfig, SequenceStep, AutoClickerState
from ...persistence import get_point_by_id
from ...utils import err, safe_input, warn
from ...winapi import get_cursor_pos, KEY_NAMES


def apply_else_to_step(step: SequenceStep, else_parts: list, state: AutoClickerState) -> None:
    """Wendet eine geparste ELSE-Bedingung auf einen SequenceStep an.

    Vermeidet die 3-fache Duplizierung des Else-Anwendungscodes.

    Die Liste unten MUSS zu dem passen, was die Runtime tatsächlich auswertet
    (`step.else_config` in `runtime/steps.py`). Sie war stehengeblieben, während
    Boss- und Icon-Scan dazukamen: 'boss X else skip' wurde mit einer Warnung
    verworfen, obwohl der Scan die else-Aktion ausführt.
    """
    if not else_parts:
        return
    if not _kann_else(step):
        print(warn(f"  -> 'else' hat hier keine Wirkung: {_warum_kein_else(step)}"))
        return
    else_result = parse_else_condition(else_parts, state)
    if else_result:
        step.else_config = ElseConfig(
            action=else_result["else_action"],
            point_id=else_result.get("else_point_id"),
            x=else_result.get("else_x", 0),
            y=else_result.get("else_y", 0),
            delay=else_result.get("else_delay", 0),
            key=else_result.get("else_key"),
            name=else_result.get("else_name", "")
        )


def _kann_else(step: SequenceStep) -> bool:
    """True, wenn die Runtime für diesen Schritt-Typ eine else-Aktion auswertet.

    Ein 'else' braucht etwas, das danebengehen kann: eine Farb-Bedingung oder
    einen Scan, der nichts findet. Der Boss-Watcher zählt NICHT dazu — er wartet,
    bis ein Boss erscheint, und gibt bei Timeout/Max-Scans einfach auf, ohne
    else_config anzusehen.
    """
    return bool(step.wait_condition or step.item_scan or step.boss_scan
                or step.icon_scan)


def _warum_kein_else(step: SequenceStep) -> str:
    """Erklärt, warum 'else' an diesem Schritt nichts tut."""
    if step.boss_watcher:
        return ("ein Watcher wartet, bis ein Boss erscheint — er kann nicht "
                "'danebengehen'. Nimm 'boss <Name> else ...' für einen Einmal-Scan.")
    if step.screenshot_only:
        return "ein Screenshot-Schritt kann nicht fehlschlagen."
    return ("es fehlt eine Bedingung, die danebengehen kann — also ein Farb-Trigger "
            "(color/colorgone/checkcolor) oder ein scan/boss/icon.")


def capture_pixel_color() -> tuple:
    """Erfasst eine Pixelfarbe an der aktuellen Mausposition.

    Zeigt Anweisung an, wartet auf Enter, liest Farbe.

    Returns:
        (x, y, color) oder (None, None, None) wenn fehlgeschlagen.
    """
    if not PILLOW_AVAILABLE:
        print("  -> Pillow nicht installiert!")
        return None, None, None
    print("  Bewege Maus zum Pixel, dann Enter...")
    safe_input()
    x, y = get_cursor_pos()
    color = get_pixel_color(x, y)
    if not color:
        print("  -> Farbe konnte nicht gelesen werden!")
        return None, None, None
    return x, y, color


def parse_uhrzeit(time_str: str) -> Optional[str]:
    """Parst eine Uhrzeit-Eingabe (z.B. '12:30', '9:05') und gibt 'HH:MM' zurück oder None."""
    match = re.match(r'^(\d{1,2}):(\d{2})$', time_str.strip())
    if match:
        h, m = int(match.group(1)), int(match.group(2))
        if 0 <= h <= 23 and 0 <= m <= 59:
            return f"{h:02d}:{m:02d}"
    print(err(f"  Ungültige Zeit '{time_str}' – Format: HH:MM (z.B. 12:30)"))
    return None


def parse_else_condition(else_parts: list[str], state: AutoClickerState) -> dict:
    """Parst eine ELSE-Bedingung und gibt ein Dict mit den Else-Feldern zurück.

    Formate:
    - else skip          -> überspringen
    - else skip_cycle    -> aktuellen Zyklus abbrechen, nächster startet
    - else restart       -> Sequenz neu starten
    - else <Nr> [delay]  -> Punkt klicken (optional mit Verzögerung)
    - else key <Taste>   -> Taste drücken

    Gibt leeres Dict zurück wenn Parsing fehlschlägt.
    """
    if not else_parts:
        return {}

    first = else_parts[0].lower()

    if first == "skip":
        return {"else_action": "skip"}

    if first == "skip_cycle":
        return {"else_action": "skip_cycle"}

    if first == "restart":
        return {"else_action": "restart"}

    # else key <Taste>
    if first == "key" and len(else_parts) >= 2:
        key_name = else_parts[1].lower()
        if key_name in KEY_NAMES:
            return {"else_action": "key", "else_key": key_name}
        print(f"  -> Unbekannte Taste: '{key_name}'")
        return {}

    # else <ID> [delay] - Punkt klicken (per ID)
    try:
        point_id = int(first)
        with state.lock:
            point = get_point_by_id(state, point_id)
            if point:
                # Die ID ist das Ergebnis, nicht die Koordinate: der Nutzer hat ohnehin
                # einen Punkt genannt. x/y stehen nur als Arbeitswert daneben, damit der
                # Editor sie sofort anzeigen kann - gespeichert wird die ID.
                result = {
                    "else_action": "click",
                    "else_point_id": point_id,
                    "else_x": point.x,
                    "else_y": point.y,
                    "else_name": point.name or f"Punkt #{point_id}"
                }
                if len(else_parts) >= 2:
                    try:
                        result["else_delay"] = float(else_parts[1])
                    except ValueError:
                        pass
                return result
            print(f"  -> Punkt #{point_id} nicht gefunden!")
            return {}
    except ValueError:
        pass

    print(f"  -> Unbekanntes ELSE-Format: {' '.join(else_parts)}")
    print("     Formate: else skip | else skip_cycle | else restart | else <Nr> [delay] | else key <Taste>")
    return {}
