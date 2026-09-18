"""
Befehle von aussen an den Hauptprozess — der Rückweg zu `runtime/status.py`.

Dort schreibt der Hauptprozess, **was läuft**; hier legt ein anderer Prozess ab,
**was passieren soll**. Beides sind Dateien, weil das zwischen diesen beiden
Prozessen der einzige gemeinsame Nenner ist: das Sequenz-Studio läuft als
`subprocess.Popen` und sieht `AutoClickerState` nicht.

**Ein Briefkasten, kein Log.** Wer liest, leert ihn (`fetch_command()` löscht die Datei) —
damit läuft ein Befehl genau einmal. Und er hat ein Verfallsdatum: ein Befehl,
der geschrieben wurde, während der Hauptprozess gar nicht lief, darf beim
nächsten Start **nicht** nachfeuern. Das ist hier der gefährlichste Fall
überhaupt — ein „starte" aus der letzten Sitzung würde sonst irgendwann später
unerwartet klicken. Deshalb `MAX_AGE`.

**Gelesen wird im Main-Thread**, in derselben Schleife, die auch die Hotkeys
abholt (`main.py`). Das ist kein Zufall, sondern der Grund, warum es hier keinen
Watcher-Thread gibt: ein Befehl aus dem Studio ist damit exakt dasselbe wie ein
Hotkey-Druck — dieselbe Reihenfolge, dieselben Sperren, keine zweite
Nebenläufigkeit im Programm.

Warum dieses Modul nicht unter `runtime/` liegt, wo sein Zwilling steht: das
Studio müsste dafür `autoclicker.runtime` importieren, und dessen `__init__`
zieht den Worker samt `imaging` und `winapi` nach. Das Fenster braucht nichts
davon. Aus demselben Grund liest `StudioBridge.run_status()` die Statusdatei
selbst, statt `runtime.status` zu importieren.
"""

import json
import time
import uuid
from pathlib import Path
from typing import Optional

from .config import COMMAND_FILE
from .utils import atomic_write, compact_json

COMMAND_PATH = Path(COMMAND_FILE)

# Älter als das heisst: der Hauptprozess war nicht da, als der Befehl geschrieben
# wurde. Grosszügig genug für einen Start, der auf einen langsamen Speichervorgang
# wartet, und kurz genug, dass niemand einen Befehl von gestern erwischt.
MAX_AGE = 30.0


def send_command(command: str, **arguments) -> bool:
    """Legt einen Befehl für den Hauptprozess ab. True, wenn geschrieben.

    Wird aus dem Studio-Subprozess gerufen. Ein bereits liegender Befehl wird
    überschrieben: es gibt nichts anzustauen — wer zweimal „stopp" drückt, meint
    einmal stoppen.
    """
    try:
        atomic_write(COMMAND_PATH, compact_json({
            "command": str(command),
            "arguments": dict(arguments),
            "sent_at": time.time(),
        }))
        return True
    except (OSError, TypeError, ValueError):
        return False


def fetch_command(max_alter: float = MAX_AGE) -> Optional[dict]:
    """Nimmt den nächsten Befehl aus dem Briefkasten — oder None.

    Leert ihn dabei **immer**, auch bei einem zu alten oder unlesbaren Eintrag:
    eine Datei, die nicht verarbeitet werden kann, aber liegen bleibt, würde bei
    jedem Durchlauf erneut gelesen und gemeldet.
    """
    # Erst atomar entnehmen, dann lesen: ein während des Lesens geschriebener
    # Befehl bleibt im Briefkasten. Der private Name wird nie erneut abgeholt.
    genommen = COMMAND_PATH.with_name(f".{COMMAND_PATH.name}.{uuid.uuid4().hex}.tmp")
    try:
        COMMAND_PATH.replace(genommen)
    except OSError:
        return None
    try:
        raw = genommen.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    finally:
        try:
            genommen.unlink(missing_ok=True)
        except OSError:
            pass
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict) or not data.get("command"):
        return None
    try:
        alter = time.time() - float(data.get("sent_at") or 0)
    except (TypeError, ValueError):
        return None
    if alter > max_alter:
        return None
    arguments = data.get("arguments")
    data["arguments"] = arguments if isinstance(arguments, dict) else {}
    return data


def discard_command() -> None:
    """Leert den Briefkasten, ohne zu lesen. Fehler werden geschluckt."""
    try:
        COMMAND_PATH.unlink(missing_ok=True)
    except OSError:
        pass
