"""Debug-Hilfen für die Sequenz-Ausführung.

Es gibt ZWEI unabhängige Debug-Modi — vorher steckte beides in einem Flag:

  debug_log   Beobachten. Jeder Schritt wird persistent geloggt statt die Status-Zeile
              zu überschreiben, dazu Erkennungs-Details bei Item/Boss/Icon-Scans.
              Läuft ohne Eingriff durch, nur mehr Ausgabe.

  debug_step  Eingreifen. Vor jedem Schritt springt die Maus auf den Zielpunkt (ohne
              zu klicken), Farb-Bedingungen werden als Farbquadrat gezeigt, und der
              Worker wartet auf einen Tastendruck. So sieht man Schritt für Schritt,
              wo es hakt.

Beide lassen sich gemeinsam einschalten. debug_step impliziert die ausführliche
Ausgabe, weil eine überschreibbare Status-Zeile beim Einzelschritt-Durchgang nichts
nützt.

Hinweis zum Einzelschritt-Modus: der Tastendruck wird im WORKER-Thread gelesen. Solange
gleichzeitig ein Editor offen ist, lesen zwei Threads von der Konsole — dann lieber den
Editor schließen. Die Hotkey-Loop im Main-Thread stört nicht, die liest kein stdin.
"""

from __future__ import annotations

import time

from ..models import AutoClickerState, SequenceStep
from ..utils import col, dbg, describe_color, read_key
from ..winapi import get_cursor_pos, set_cursor_pos

# Rückgabewerte von step_gate()
GATE_RUN = "run"        # Schritt normal ausführen
GATE_SKIP = "skip"      # Diesen Schritt überspringen
GATE_STOP = "stop"      # Sequenz abbrechen


def is_log_debug(state: AutoClickerState) -> bool:
    """Ausführliche, persistente Ausgabe (auch im Einzelschritt-Modus aktiv)."""
    return state.config.debug_log or state.config.debug_step


def is_step_debug(state: AutoClickerState) -> bool:
    """Einzelschritt-Modus: vor jedem Schritt anhalten und den Punkt zeigen."""
    return state.config.debug_step


def color_swatch(color) -> str:
    """Farbquadrat + Name + RGB. Ohne Farbe: leerer String."""
    if not color:
        return ""
    return describe_color(tuple(color))


def color_comparison(expected, actual, dist: float, tolerance: float) -> str:
    """Erwartete und tatsächliche Farbe direkt nebeneinander - beim Warten auf eine
    Farbe die eigentliche Frage: sieht das Skript dasselbe wie ich?"""
    verdict = "passt" if dist <= tolerance else f"zu weit (Toleranz {tolerance:.0f})"
    return (f"erwartet {color_swatch(expected)}  |  aktuell {color_swatch(actual)}  "
            f"|  Abstand {dist:.0f} -> {verdict}")


def show_point(state: AutoClickerState, x: int, y: int, label: str = "",
               restore: bool = False) -> None:
    """Springt mit der Maus auf eine Position OHNE zu klicken, damit man sieht, wohin
    der Schritt zielt. `restore=True` setzt den Cursor danach zurück - sinnvoll beim
    Beobachten, während im Einzelschritt-Modus der Zeiger stehen bleiben soll."""
    vorher = get_cursor_pos() if restore else None
    set_cursor_pos(x, y)
    if label:
        print(dbg(f"Zeiger auf {label} ({x}, {y})"))
    delay = state.config.pixel_show_delay
    if delay > 0:
        time.sleep(delay)
    if vorher is not None:
        set_cursor_pos(vorher[0], vorher[1])


def describe_step(step: SequenceStep) -> str:
    """Was tut dieser Schritt? Eine Zeile, für die Einzelschritt-Anzeige."""
    if step.key_press:
        return f"Taste '{step.key_press}'"
    if step.item_scan:
        return f"Item-Scan '{step.item_scan}' ({step.item_scan_mode})"
    if step.boss_scan:
        return f"Boss-Scan '{step.boss_scan}'"
    if step.boss_watcher:
        return f"Boss-Watcher '{step.boss_watcher}'"
    if step.icon_scan:
        return f"Icon-Scan '{step.icon_scan}'"
    if step.screenshot_only:
        return "Screenshot"
    if getattr(step, "scroll", None):
        richtung = "hoch" if step.scroll > 0 else "runter"
        return f"Scroll {richtung} ({abs(step.scroll)})"
    if step.wait_only:
        return "nur warten"
    return f"Klick ({step.x}, {step.y})"


def _step_header(step: SequenceStep, phase: str, step_num: int, total_steps: int) -> None:
    name = step.name or "unbenannt"
    print()
    print(col(f"── [{phase}] Schritt {step_num}/{total_steps}: {name}", "cyan"))
    print(col(f"   {describe_step(step)}", "gray"))

    wc = step.wait_condition
    if wc is not None:
        richtung = "bis Farbe WEG" if wc.until_gone else "bis Farbe DA"
        pruef_art = "einmal prüfen" if getattr(wc, "check_only", False) else richtung
        print(col(f"   Farbprüfung an {wc.pixel}: {pruef_art}", "gray"))
        print(f"   {color_swatch(wc.color)}")
    if step.else_config is not None:
        print(col(f"   Fallback wenn nicht erfüllt: {step.else_config.action}", "gray"))


def step_gate(state: AutoClickerState, step: SequenceStep, phase: str,
              step_num: int, total_steps: int) -> str:
    """Einzelschritt-Gate: zeigt den Schritt, springt auf den Zielpunkt und wartet.

    Gibt GATE_RUN / GATE_SKIP / GATE_STOP zurück. Ist der Einzelschritt-Modus aus,
    kommt immer sofort GATE_RUN.
    """
    if not is_step_debug(state):
        return GATE_RUN

    _step_header(step, phase, step_num, total_steps)

    # Zielpunkt zeigen: beim Farb-Trigger den Prüf-Pixel, sonst den Klickpunkt.
    if step.wait_condition is not None:
        show_point(state, step.wait_condition.pixel[0], step.wait_condition.pixel[1],
                   "Prüf-Pixel")
    elif not (step.wait_only or step.key_press or step.screenshot_only):
        show_point(state, step.x, step.y, "Klickpunkt")

    print(col("   [Enter] ausführen   [s] überspringen   [w] weiter ohne Stopps   "
              "[q] abbrechen", "yellow"))

    while not state.stop_event.is_set():
        taste = (read_key() or "").lower()
        if taste in ("enter", " ", "r"):
            return GATE_RUN
        if taste == "s":
            print(dbg("Schritt übersprungen (Einzelschritt-Modus)"))
            return GATE_SKIP
        if taste == "w":
            state.config.debug_step = False
            print(dbg("Einzelschritt-Modus aus - Lauf geht ohne Stopps weiter"))
            return GATE_RUN
        if taste in ("q", "escape"):
            print(col("   Abbruch im Einzelschritt-Modus", "red"))
            state.stop_event.set()
            return GATE_STOP
    return GATE_STOP
