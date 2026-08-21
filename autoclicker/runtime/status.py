"""Laufstatus für Beobachter ausserhalb des Prozesses (Sequenz-Studio).

Kein Log: die Datei beschreibt den Zustand JETZT und wird überschrieben.
Am Ende bleibt die Zusammenfassung des letzten Laufs stehen (`beende()`).
Eine Datei statt eines Sockets, weil der gemeinsame Nenner der beiden
Prozesse überall sonst schon die Datei ist.

Drei Schreiber führen ihren Teil ein, statt ihn zu ersetzen: der Worker
kennt Zyklus und Phase, `execute_step` den Block, `wartet()` das Warten.
Höchstens alle 200 ms ein Schreibvorgang (`sofort=True` umgeht die Drossel);
Schreibfehler werden geschluckt — ein Beobachter darf den Lauf nie stören.
"""

import time
from pathlib import Path

from ..config import RUN_STATUS_FILE
from ..utils import atomic_write, compact_json

STATUS_DATEI = Path(RUN_STATUS_FILE)

_MINDESTABSTAND = 0.2
_zuletzt = 0.0
_zustand: dict = {}


def _zaehler(state) -> dict:
    """Die Zähler aus dem State — unter Lock gelesen, wie überall."""
    with state.lock:
        return {"klicks": state.total_clicks, "items": state.items_found,
                "tasten": state.key_presses, "timeouts": state.timeouts,
                "uebersprungen": state.skipped_cycles, "neustarts": state.restarts}


def schreibe(state, teil: dict, sofort: bool = False) -> None:
    """Führt `teil` in den Laufzustand ein und schreibt ihn auf Platte.

    `sofort=True` umgeht die Drossel — für Ereignisse, die man nicht verpassen
    darf (Start, Phasen- und Zykluswechsel). Eingeführt wird immer, gedrosselt
    nur das Schreiben: sonst ginge die Information eines verworfenen Aufrufs
    verloren.
    """
    global _zuletzt
    _zustand.update(teil)
    jetzt = time.monotonic()
    if not sofort and jetzt - _zuletzt < _MINDESTABSTAND:
        return
    _zuletzt = jetzt
    try:
        _zustand["zaehler"] = _zaehler(state)
        _zustand["stand"] = time.time()
        atomic_write(STATUS_DATEI, compact_json(_zustand))
    except (OSError, TypeError, ValueError, AttributeError):
        pass


def wartet(state, teil) -> None:
    """Worauf der laufende Block gerade wartet — oder `None`, wenn er fertig wartet.

    Zeiten stehen als absolute Zeitstempel darin (`seit`, `bis`), nicht als
    Restsekunden: mit Restwerten ruckelte der Countdown im Sekundenraster des
    Workers. Beide Prozesse laufen auf derselben Uhr.

    Das Abmelden schreibt sofort — zwischen „Farbe erkannt" und dem nächsten
    Block liegt noch die eigene Aktion des Schritts.
    """
    schreibe(state, {"warten": teil}, sofort=teil is None)


def lebenszeichen(state) -> None:
    """„Ich lebe noch" — schiebt `stand` vor, ohne etwas zu ändern.

    Der Leser erkennt einen abgestürzten Lauf am Alter des Zeitstempels; ohne
    Lebenszeichen sähe genau der Lauf tot aus, der gerade wartet. Gehört
    deshalb in jede Schleife, die den Worker länger aufhält. Kostet nichts —
    die Drossel lässt höchstens fünf Schreibvorgänge pro Sekunde durch.
    """
    schreibe(state, {})


# Was beim Ende eines Laufs KEINEN Sinn mehr ergibt: alles, was einen Moment
# beschreibt statt den Durchgang. Ein „wartet auf Farbe" in einer Zusammenfassung
# wäre eine Behauptung über etwas, das längst vorbei ist.
# `phase`/`phase_pos` bleiben bewusst drin: WO ein Lauf aufgehoert hat, ist die
# zweite Frage nach "warum". Die Phasenleiste zeigt sie in der Zusammenfassung
# als Stelle, an der Schluss war.
_MOMENT_FELDER = ("block", "bloecke", "block_titel", "block_label", "block_typ",
                  "block_seit", "warten", "durchlauf")


def beende(state=None, grund: str = "", zyklen: int = 0, dauer: float = 0.0) -> None:
    """Schliesst den Lauf ab — und lässt eine Zusammenfassung stehen.

    Der letzte Stand bleibt als abgeschlossener Lauf liegen (`aktiv: False`
    plus `ende`), bis der nächste Start ihn überschreibt; sonst wäre die
    Live-Ansicht genau dann leer, wenn man sie ansieht. Der Leser unterscheidet
    drei Fälle am Inhalt:

    | Datei | bedeutet |
    |---|---|
    | `aktiv: True`, `stand` frisch | läuft |
    | `aktiv: True`, `stand` älter als 5 s | abgestürzt (verwaist) |
    | `aktiv: False` mit `ende` | fertig, hier ist die Zusammenfassung |

    Die Altersregel gilt nur für den ersten Fall. Ohne `state` (der Lauf lief
    gar nicht erst an) wird gelöscht — eine Zusammenfassung ohne Zahlen wäre keine.
    """
    global _zuletzt
    letzter = dict(_zustand)
    _zustand.clear()
    _zuletzt = 0.0
    try:
        if state is None or not letzter.get("sequenz"):
            STATUS_DATEI.unlink(missing_ok=True)
            return
        for feld in _MOMENT_FELDER:
            letzter.pop(feld, None)
        letzter.update({
            "aktiv": False,
            "ende": time.time(),
            "grund": grund,
            "gelaufen": zyklen,
            "dauer": dauer,
            "zaehler": _zaehler(state),
            "stand": time.time(),
        })
        atomic_write(STATUS_DATEI, compact_json(letzter))
    except (OSError, TypeError, ValueError, AttributeError):
        pass
