"""Laufstatus für Beobachter ausserhalb des Prozesses (Sequenz-Studio).

Kein Log: die Datei beschreibt den Zustand JETZT und wird überschrieben.
Am Ende bleibt die Zusammenfassung des letzten Laufs stehen (`finish_run()`).
Eine Datei statt eines Sockets, weil der gemeinsame Nenner der beiden
Prozesse überall sonst schon die Datei ist.

Drei Schreiber führen ihren Teil ein, statt ihn zu ersetzen: der Worker
kennt Zyklus und Phase, `execute_step` den Block, `waiting_for()` das Warten.
Höchstens alle 200 ms ein Schreibvorgang (`sofort=True` umgeht die Drossel);
Schreibfehler werden geschluckt — ein Beobachter darf den Lauf nie stören.
"""

import time
from pathlib import Path

from ..config import RUN_STATUS_FILE
from ..utils import atomic_write, compact_json

STATUS_PATH = Path(RUN_STATUS_FILE)

_MIN_INTERVAL = 0.2
_last = 0.0
_state: dict = {}


def _counters(state) -> dict:
    """Die Zähler aus dem State — unter Lock gelesen, wie überall."""
    with state.lock:
        return {"clicks": state.total_clicks, "items": state.items_found,
                "keys": state.key_presses, "timeouts": state.timeouts,
                "skipped": state.skipped_cycles, "restarts": state.restarts}


def write_status(state, part: dict, immediately: bool = False) -> None:
    """Führt `part` in den Laufzustand ein und schreibt ihn auf Platte.

    `sofort=True` umgeht die Drossel — für Ereignisse, die man nicht verpassen
    darf (Start, Phasen- und Zykluswechsel). Eingeführt wird immer, gedrosselt
    nur das Schreiben: sonst ginge die Information eines verworfenen Aufrufs
    verloren.
    """
    global _last
    _state.update(part)
    now = time.monotonic()
    if not immediately and now - _last < _MIN_INTERVAL:
        return
    _last = now
    try:
        _state["counters"] = _counters(state)
        _state["stamp"] = time.time()
        atomic_write(STATUS_PATH, compact_json(_state))
    except (OSError, TypeError, ValueError, AttributeError):
        pass


def waiting_for(state, part) -> None:
    """Worauf der laufende Block gerade wartet — oder `None`, wenn er fertig wartet.

    Zeiten stehen als absolute Zeitstempel darin (`since`, `until`), nicht als
    Restsekunden: mit Restwerten ruckelte der Countdown im Sekundenraster des
    Workers. Beide Prozesse laufen auf derselben Uhr.

    Das Abmelden schreibt sofort — zwischen „Farbe erkannt" und dem nächsten
    Block liegt noch die eigene Aktion des Schritts.
    """
    write_status(state, {"waiting": part}, immediately=part is None)


def heartbeat(state) -> None:
    """„Ich lebe noch" — schiebt `stamp` vor, ohne etwas zu ändern.

    Der Leser erkennt einen abgestürzten Lauf am Alter des Zeitstempels; ohne
    Lebenszeichen sähe genau der Lauf tot aus, der gerade wartet. Gehört
    deshalb in jede Schleife, die den Worker länger aufhält. Kostet nichts —
    die Drossel lässt höchstens fünf Schreibvorgänge pro Sekunde durch.
    """
    write_status(state, {})


def schedule_run(sequence: str, target_time: float) -> None:
    """Zeigt einen noch nicht gestarteten Zeitplan im Studio.

    Ein Countdown ist kein Lauf, aber auch nicht „es passiert nichts". Er steht
    deshalb in derselben Momentaufnahme mit `aktiv: False` und eigenem Feld.
    Vorheriger Laufzustand wird geleert: die nächste Worker-Meldung baut ihn
    ohnehin vollständig neu auf.
    """
    global _last
    _state.clear()
    _last = 0.0
    try:
        atomic_write(STATUS_PATH, compact_json({
            "active": False,
            "countdown": True,
            "sequence": sequence,
            "target_time": float(target_time),
            "stamp": time.time(),
        }))
    except (OSError, TypeError, ValueError):
        pass


def end_schedule() -> None:
    """Entfernt nur eine Countdown-Anzeige, nie die Laufzusammenfassung."""
    try:
        import json
        data = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("countdown"):
            STATUS_PATH.unlink(missing_ok=True)
    except (OSError, ValueError):
        pass


# Was beim Ende eines Laufs KEINEN Sinn mehr ergibt: alles, was einen Moment
# beschreibt statt den Durchgang. Ein „wartet auf Farbe" in einer Zusammenfassung
# wäre eine Behauptung über etwas, das längst vorbei ist.
# `phase`/`phase_pos` bleiben bewusst drin: WO ein Lauf aufgehoert hat, ist die
# zweite Frage nach "warum". Die Phasenleiste zeigt sie in der Zusammenfassung
# als Stelle, an der Schluss war.
_MOMENT_FIELDS = ("block", "blocks", "block_title", "block_label", "block_set_type",
                  "block_since", "waiting", "pass_index", "manual")


def finish_run(state=None, reason: str = "", cycles: int = 0, duration: float = 0.0) -> None:
    """Schliesst den Lauf ab — und lässt eine Zusammenfassung stehen.

    Der letzte Stand bleibt als abgeschlossener Lauf liegen (`aktiv: False`
    plus `end`), bis der nächste Start ihn überschreibt; sonst wäre die
    Live-Ansicht genau dann leer, wenn man sie ansieht. Der Leser unterscheidet
    drei Fälle am Inhalt:

    | Datei | bedeutet |
    |---|---|
    | `aktiv: True`, `stamp` frisch | läuft |
    | `aktiv: True`, `stamp` älter als 5 s | abgestürzt (verwaist) |
    | `aktiv: False` mit `end` | fertig, hier ist die Zusammenfassung |

    Die Altersregel gilt nur für den ersten Fall. Ohne `state` (der Lauf lief
    gar nicht erst an) wird gelöscht — eine Zusammenfassung ohne Zahlen wäre keine.
    """
    global _last
    last_one = dict(_state)
    _state.clear()
    _last = 0.0
    try:
        if state is None or not last_one.get("sequence"):
            STATUS_PATH.unlink(missing_ok=True)
            return
        for field in _MOMENT_FIELDS:
            last_one.pop(field, None)
        last_one.update({
            "active": False,
            "end": time.time(),
            "reason": reason,
            "elapsed_cycles": cycles,
            "duration": duration,
            "counters": _counters(state),
            "stamp": time.time(),
        })
        atomic_write(STATUS_PATH, compact_json(last_one))
    except (OSError, TypeError, ValueError, AttributeError):
        pass
