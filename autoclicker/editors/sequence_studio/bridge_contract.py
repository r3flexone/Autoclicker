"""Öffentliches Protokoll und reine Helfer der Studio-Brücke."""

from pathlib import Path
from typing import Optional

from ...models import (
    BLOCK_BOSS_SCAN,
    BLOCK_BOSS_WATCHER,
    BLOCK_CLICK,
    BLOCK_ICON_SCAN,
    BLOCK_ITEM_SCAN,
    BLOCK_KEY,
    BLOCK_SCREENSHOT,
    BLOCK_WAIT,
    BLOCK_WAIT_CLICK,
    ELSE_CLICK,
    ELSE_KEY,
    ELSE_RESTART,
    ELSE_SKIP,
    ELSE_SKIP_CYCLE,
    SCAN_MODE_ALL,
    SCAN_MODE_BEST,
    SCAN_MODE_EVERY,
    SequenceStep,
    WaitCondition,
    block_type,
)
from .model import BLOCK_LABELS, SequenceBoard, hex_color, rgb_value

# Reihenfolge der Block-Typen in der Typ-Auswahl: erst die drei Klick-Formen,
# dann Taste, dann die Scans, zuletzt der Screenshot.
TYPE_ORDER = [
    BLOCK_CLICK, BLOCK_WAIT_CLICK, BLOCK_WAIT, BLOCK_KEY,
    BLOCK_ITEM_SCAN, BLOCK_ICON_SCAN, BLOCK_BOSS_SCAN, BLOCK_BOSS_WATCHER,
    BLOCK_SCREENSHOT,
]

# Farb-Trigger: die drei Zustände, die ein Schritt haben kann. Werte statt
# Beschriftungen — die Beschriftung steht in der Oberfläche, hier steht das
# Protokoll. (Beim DPG-Vorgänger waren beide dasselbe, und der Test verglich
# gegen deutsche Anzeigetexte.)
# Wie lange ein Griff mit der Maus auf ENTER wartet. **Der Aufruf blockiert die
# Bruecke so lange** — die Seite kann in dieser Zeit keine Antwort bekommen und
# muss deshalb selbst sagen, worauf gewartet wird. Damit ihr Countdown nicht
# neben der Wirklichkeit laeuft, steht die Zahl hier und wird mitgeliefert,
# statt in app.js ein zweites Mal zu stehen.
WAIT_TIMEOUT = 60.0

TRIGGER_NONE = "none"
TRIGGER_PRESENT = "present"
TRIGGER_GONE = "gone"

SCAN_MODES = [SCAN_MODE_ALL, SCAN_MODE_BEST, SCAN_MODE_EVERY]
ELSE_ACTIONS = [ELSE_SKIP, ELSE_SKIP_CYCLE, ELSE_RESTART, ELSE_CLICK, ELSE_KEY]

# Welches Feld hält den Namen eines Scan-Blocks? Ein Scan-Block mit leerem Namen
# fällt beim Executor durch den Truthiness-Dispatch und degradiert still zu einem
# Klick auf (0,0) — deshalb steht die Zuordnung hier einmal und wird an zwei
# Stellen benutzt (Warnung am Block, Sperre beim Speichern).
SCAN_FIELD = {
    BLOCK_ITEM_SCAN: "item_scan",
    BLOCK_ICON_SCAN: "icon_scan",
    BLOCK_BOSS_SCAN: "boss_scan",
    BLOCK_BOSS_WATCHER: "boss_watcher",
}

# Einfache Felder eines Schritts: Name -> Umwandlung des Werts aus der Oberfläche.
# Alles, was eine Stelle betrifft (Punkt, Trigger, else), hat eine eigene Methode —
# dort hängt mehr dran als eine Zuweisung.
_FIELDS = {
    "name": lambda v: str(v or ""),
    "delay_before": lambda v: max(0.0, float(v or 0)),
    "delay_max": lambda v: (float(v) if float(v or 0) > 0 else None),
    "key_press": lambda v: (str(v).strip() or None),
    "item_scan": lambda v: str(v or ""),
    "item_scan_mode": lambda v: (str(v) if v in SCAN_MODES else SCAN_MODE_ALL),
    "icon_scan": lambda v: str(v or ""),
    "boss_scan": lambda v: str(v or ""),
    "boss_watcher": lambda v: str(v or ""),
    "wait_only": lambda v: bool(v),
    "breakpoint": lambda v: bool(v),
}


# Die beiden Farbhelfer liegen in `model.py` — der Scans-Reiter braucht sie
# genauso, und zwei Exemplare wären die Kopie, die irgendwann anders rundet.
_hex = hex_color
_rgb = rgb_value


def trigger_name(cond: Optional[WaitCondition]) -> str:
    """Zustand einer Farb-Bedingung als Protokollwert."""
    if cond is None:
        return TRIGGER_NONE
    return TRIGGER_GONE if cond.until_gone else TRIGGER_PRESENT


def _wait_text(step: SequenceStep) -> str:
    if step.delay_max and step.delay_max > step.delay_before:
        return f"{step.delay_before:g}–{step.delay_max:g}s zufällig"
    if step.delay_before:
        # Ohne „+": die Zeile trägt das Etikett WARTE, das Vorzeichen sagte
        # dasselbe noch einmal.
        return f"{step.delay_before:g}s"
    return "sofort"


def _position(step: SequenceStep) -> str:
    ref = f"#{step.point_id} " if step.point_id is not None else ""
    return f"{ref}({step.x},{step.y})"


# Welche Blöcke ELSE überhaupt auslösen können. ELSE ist eine Antwort auf eine
# **nicht erfüllte Bedingung** — hat ein Block keine, wird es nie ausgeführt:
# ein reiner Klick klickt, eine Taste drückt, ein Warten wartet, und danach geht
# es weiter. Ausgelöst wird es (siehe `runtime/steps.py`) von
#   - der Farb-Bedingung: Timeout bzw. „nur prüfen" nicht erfüllt,
#   - der Nachprüfung: keine Wirkung nach allen Versuchen,
#   - Item-/Boss-/Icon-Scan: nichts gefunden.
# Der Boss-**Watcher** steht bewusst nicht dabei: er läuft in seine eigenen
# Grenzen (max. Scans, Timeout) und macht danach weiter, ohne ELSE zu fragen.
_ELSE_SCANS = ("item_scan", "boss_scan", "icon_scan")


def else_applies(step: SequenceStep) -> bool:
    """Kann ELSE bei diesem Schritt überhaupt feuern?"""
    if step.wait_condition is not None or step.verify_condition is not None:
        return True
    return any(getattr(step, field, None) is not None for field in _ELSE_SCANS)


def _same_value(a, b) -> bool:
    """Ist das derselbe Config-Wert? Zahlen ohne Typunterschied, `bool` mit.

    JSON kennt nur eine Zahl: eine von Hand getippte `600` und die `600.0`, die
    nach dem Laden dasteht, sind dieselbe Einstellung — als Korrektur gemeldet
    wäre das eine Falschmeldung bei jedem zweiten Feld (dieselbe Rechnung wie
    `_equal()` im Start-Durchgang). `bool` bleibt ausgenommen: ein `True`, das
    als `1` durchginge, versteckte ein umgekipptes Flag.
    """
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_same_value(x, y) for x, y in zip(a, b))
    if not isinstance(a, bool) and isinstance(a, (int, float)) \
            and not isinstance(b, bool) and isinstance(b, (int, float)):
        return float(a) == float(b)
    return a == b


def _mtime(path) -> Optional[float]:
    """Zeitstempel einer Datei — `None`, wenn es sie (noch) nicht gibt."""
    try:
        return Path(path).stat().st_mtime
    except OSError:
        return None


def _blocks(count: int) -> str:
    """„1 Block" / „3 Blöcke" — in der Statusleiste stand vorher „1 Block/Blöcke"."""
    return "1 Block" if count == 1 else f"{count} Blöcke"


def scan_warnings(board: SequenceBoard) -> list[str]:
    """Alle Scan-Blöcke ohne Konfiguration, als lesbare Stellen.

    Steht ausserhalb der Klasse, weil es zwei Fragen beantwortet: „hat die
    OFFENE Sequenz noch einen leeren Scan?" (Meldung beim Speichern) und
    „hat DIESE Datei welche?" (Übersicht). Zweimal dieselbe Regel getrennt
    hinzuschreiben hiesse, dass eine Korrektur an der einen an der anderen
    vorbeigeht — dieselbe Begründung wie bei `multi_select()`.
    """
    out = []
    for lane in board.lanes:
        for row, step in enumerate(lane.steps, start=1):
            type_value = block_type(step)
            field = SCAN_FIELD.get(type_value)
            if field is not None and not (getattr(step, field) or "").strip():
                out.append(f"{BLOCK_LABELS[type_value]} in '{lane.name}' (Block {row})")
    return out
