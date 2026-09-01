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
ABBRUCH = object()


def frage_prioritaet(state: AutoClickerState, kategorie: Optional[str],
                     vorgabe: int = 1, *, abbrechbar: bool = False):
    """Fragt die Priorität ab. Gibt die Zahl zurück — oder `ABBRUCH`.

    `0` heisst „beste": das Item bekommt Priorität 1 und alle anderen derselben
    Kategorie rutschen einen Platz nach hinten. Ohne Kategorie ergibt das keinen
    Sinn (es gibt nichts zu verschieben) und wird gesagt statt still ignoriert.

    Eine Fehleingabe behält die Vorgabe — dieselbe Haltung wie überall in den
    Editoren: wiederholen statt abbrechen.
    """
    prioritaet = max(1, int(vorgabe or 1))
    eingabe = safe_input(
        f"  Priorität (1=beste, 0=beste+verschieben, Enter={prioritaet}): ").strip()
    if abbrechbar and is_cancel(eingabe):
        return ABBRUCH
    if not eingabe:
        return prioritaet
    try:
        wert = int(eingabe)
    except ValueError:
        return prioritaet
    if wert != 0:
        return max(1, wert)
    if not kategorie:
        print("  -> Priorität 0 nur mit Kategorie möglich!")
        return 1
    shift_category_priorities(state, kategorie)
    return 1


def frage_bestaetigungsklick(state: AutoClickerState, vorgabe_delay: float, *,
                             frage: str = "  Bestätigungs-Punkt-ID (Enter = keiner): ",
                             abbrechbar: bool = False):
    """Fragt Punkt-ID und Wartezeit eines Bestätigungs-Klicks ab.

    Manche Spiele fragen nach („wirklich verkaufen?"); ohne den Klick danach
    bleibt das Popup stehen, und der Scan erreicht den nächsten Slot nicht mehr.

    Rückgabe `(punkt_id, wartezeit)` — `punkt_id` ist `None`, wenn keiner gesetzt
    werden soll (leere Eingabe, unbekannte ID, Zahlensalat). Bei Abbruch
    `ABBRUCH`.

    **Der Punkt wird unter `state.lock` gesucht.** `get_point_by_id()` läuft über
    `state.points`, und die Liste kann sich unter einem laufenden Worker ändern.
    """
    wartezeit = vorgabe_delay
    eingabe = safe_input(frage).strip()
    if abbrechbar and is_cancel(eingabe):
        return ABBRUCH
    if not eingabe:
        return None, wartezeit
    try:
        punkt_id = int(eingabe)
    except ValueError:
        print("  -> Keine Zahl — kein Bestätigungs-Klick gesetzt")
        return None, wartezeit
    with state.lock:
        gefunden = get_point_by_id(state, punkt_id) is not None
    if not gefunden:
        print(f"  -> Punkt #{punkt_id} existiert nicht")
        return None, wartezeit
    dauer = safe_input(f"  Wartezeit vor Bestätigung (Enter = {wartezeit}s): ").strip()
    if dauer:
        wert, fehler = parse_non_negative_float(dauer, "Wartezeit")
        if fehler:
            print(f"  -> {fehler}, behalte {wartezeit}s")
        else:
            wartezeit = wert
    return punkt_id, wartezeit
