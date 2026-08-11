"""
Laufstatus für Beobachter ausserhalb des Prozesses (Sequenz-Studio).

Eine kleine Datei, die sagt, was gerade läuft. **Kein Log** — sie beschreibt den
Zustand JETZT und wird überschrieben, nicht angehängt. Beim Ende verschwindet
sie; eine nach einem Absturz liegengebliebene erkennt der Leser am Alter ihres
Zeitstempels (`stand`).

**Warum eine Datei und kein Socket.** Das Studio ist ein eigener Prozess
(`subprocess.Popen`), es sieht `AutoClickerState` nicht. Der gemeinsame Nenner
zwischen den beiden ist überall sonst schon die Datei; ein zweiter
Kommunikationsweg brächte Ports, Firewall-Fragen und ein Aufräumproblem beim
Absturz. Das Session-Log schied aus einem anderen Grund aus: es steht
standardmäßig auf `session_log_enabled: False`, wäre also meist leer — und ein
Log erzählt Vergangenheit, keinen Zustand.

**Zwei Schreiber, ein Zustand.** Der Worker weiss, welcher Zyklus und welche
Phase läuft; `execute_step` weiss, welcher Block dran ist. Keiner von beiden
kennt das Ganze, deshalb führt `schreibe()` seinen Teil in `_zustand` ein,
statt ihn zu ersetzen.

Kostenrahmen: höchstens alle 200 ms ein Schreibvorgang von ~400 Byte. Ein
Phasenwechsel schreibt immer (`sofort=True`), damit der Beobachter keinen
Sprung verpasst. Ein Fehler beim Schreiben wird geschluckt — ein Beobachter
darf den Lauf nie stören.
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
    darf (Start, Phasen- und Zykluswechsel).

    Eingeführt wird **immer**, gedrosselt wird nur das Schreiben: sonst ginge
    die Information eines verworfenen Aufrufs verloren, und der nächste
    Schreibvorgang zeigte einen Block, der längst durch ist.
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


def lebenszeichen(state) -> None:
    """„Ich lebe noch" — schiebt `stand` vor, ohne etwas zu ändern.

    Der Leser erkennt einen abgestürzten Lauf am Alter des Zeitstempels, und
    das geht nur, wenn ein LEBENDER Lauf ihn zuverlässig frisch hält. Geschrieben
    wird sonst pro Schritt — aber ein Schritt kann minutenlang dauern: ein
    Farb-Trigger wartet bis `pixel_wait_timeout`, ein Boss-Watcher bis
    `llm_watcher_timeout`. Ohne Lebenszeichen sähe genau der Lauf tot aus, der
    gerade auf etwas wartet, und das ist der Fall, für den man die Ansicht
    aufmacht.

    Gehört deshalb in jede Schleife, die den Worker länger als ein paar Sekunden
    aufhält (heute: `wait_with_pause_skip`, `_execute_wait_for_color`,
    Boss-Watcher). Kostet dort nichts — die Drossel in `schreibe()` lässt
    höchstens fünf Schreibvorgänge pro Sekunde durch, die Schleifen laufen mit
    etwa einem Durchgang pro Sekunde.
    """
    schreibe(state, {})


def beende() -> None:
    """Entfernt die Statusdatei am Ende eines Laufs und vergisst den Zustand.

    Das Vergessen gehört dazu: der nächste Lauf ist eine andere Sequenz mit
    anderen Phasen, und ein stehengebliebener Block aus dem letzten Lauf stünde
    sonst in der ersten Momentaufnahme des nächsten.
    """
    global _zuletzt
    _zustand.clear()
    _zuletzt = 0.0
    try:
        STATUS_DATEI.unlink(missing_ok=True)
    except OSError:
        pass
