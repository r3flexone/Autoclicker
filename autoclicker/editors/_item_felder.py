"""
Gemeinsame Feld-Abfragen für Item-Editoren.

**Warum es diese Datei gibt.** Zwei Abfragen standen vier- bzw. sechsmal
nebeneinander: die Priorität (`items.py`, `learn.py`, `item_scan_editor.py`) und
der Bestätigungs-Klick (dieselben drei plus `autoscan.py`). Gemessen war das die
stärkste Duplikation des Repos — und sie war schon auseinandergelaufen:

- **Die Sperre fehlte an drei von vier Stellen.** `get_point_by_id()` liest
  `state.points` und sperrt nicht selbst; `items.py` hielt `state.lock`, die
  anderen nicht. Eine Kopie hatte die Regel, drei nicht.
- Die Fragetexte unterschieden sich in Kleinigkeiten („Enter=Nein" /
  „Enter = Nein" / „Enter = keine" / „Enter = keiner"), ohne dass ein
  Unterschied gemeint war.

Dasselbe Muster wie `_detection_capture.py`: ein Modul mit Unterstrich direkt
unter `editors/`, damit sowohl das `item_editor/`-Paket als auch das daneben
liegende `item_scan_editor.py` es benutzen können, ohne dass eines vom anderen
abhängt.
"""

from typing import Optional

from ..models import AutoClickerState
from ..persistence import get_point_by_id, shift_category_priorities
from ..utils import is_cancel, parse_non_negative_float, safe_input

# Ein Abbruch ist etwas anderes als „nichts eingegeben": beim Bestätigungs-Klick
# ist `None` als Punkt-ID ein gültiges Ergebnis („kein Bestätigungs-Klick"), also
# taugt es nicht zugleich als Abbruch-Zeichen. Deshalb ein eigener Wert statt
# eines zweiten `None`.
CANCELLED = object()


def ask_priority(state: AutoClickerState, category: Optional[str],
                     default_value: int = 1, *, cancellable: bool = False):
    """Fragt die Priorität ab. Gibt die Zahl zurück — oder `CANCELLED`.

    `0` heisst „beste": das Item bekommt Priorität 1 und alle anderen derselben
    Kategorie rutschen einen Platz nach hinten. Ohne Kategorie ergibt das keinen
    Sinn (es gibt nichts zu verschieben) und wird gesagt statt still ignoriert.

    Eine Fehleingabe behält die Vorgabe — dieselbe Haltung wie überall in den
    Editoren: wiederholen statt abbrechen.
    """
    priority = max(1, int(default_value or 1))
    user_input = safe_input(
        f"  Priorität (1=beste, 0=beste+verschieben, Enter={priority}): ").strip()
    if cancellable and is_cancel(user_input):
        return CANCELLED
    if not user_input:
        return priority
    try:
        value = int(user_input)
    except ValueError:
        return priority
    if value != 0:
        return max(1, value)
    if not category:
        print("  -> Priorität 0 nur mit Kategorie möglich!")
        return 1
    shift_category_priorities(state, category)
    return 1


def ask_confirm_click(state: AutoClickerState, default_delay: float, *,
                             prompt: str = "  Bestätigungs-Punkt-ID (Enter = keiner): ",
                             cancellable: bool = False):
    """Fragt Punkt-ID und Wartezeit eines Bestätigungs-Klicks ab.

    Manche Spiele fragen nach („wirklich verkaufen?"); ohne den Klick danach
    bleibt das Popup stehen, und der Scan erreicht den nächsten Slot nicht mehr.

    Rückgabe `(point_id, wartezeit)` — `point_id` ist `None`, wenn keiner gesetzt
    werden soll (leere Eingabe, unbekannte ID, Zahlensalat). Bei Abbruch
    `CANCELLED`.

    **Der Punkt wird unter `state.lock` gesucht.** `get_point_by_id()` läuft über
    `state.points`, und die Liste kann sich unter einem laufenden Worker ändern.
    """
    wait_time = default_delay
    user_input = safe_input(prompt).strip()
    if cancellable and is_cancel(user_input):
        return CANCELLED
    if not user_input:
        return None, wait_time
    try:
        point_id = int(user_input)
    except ValueError:
        print("  -> Keine Zahl — kein Bestätigungs-Klick gesetzt")
        return None, wait_time
    with state.lock:
        found = get_point_by_id(state, point_id) is not None
    if not found:
        print(f"  -> Punkt #{point_id} existiert nicht")
        return None, wait_time
    duration = safe_input(f"  Wartezeit vor Bestätigung (Enter = {wait_time}s): ").strip()
    if duration:
        value, error = parse_non_negative_float(duration, "Wartezeit")
        if error:
            print(f"  -> {error}, behalte {wait_time}s")
        else:
            wait_time = value
    return point_id, wait_time
