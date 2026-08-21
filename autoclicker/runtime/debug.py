"""Debug-Hilfen für die Sequenz-Ausführung.

Drei Dinge, die auseinandergehalten werden müssen:

1. `debug_log` (Config) — jeder Schritt als eigene Zeile statt als
   überschreibbare Status-Zeile.
2. `debug_detail` (Config) — zusätzlich Zeiger auf das Ziel und ausschreiben,
   was kommt (Farbquadrat bei Farb-Bedingungen).
3. Manueller Modus (`state.step_mode`, Laufzeit, KEINE Config) — Wartezeiten
   werden übersprungen, jeder Schritt wartet auf Bestätigung.

Beide Stufen ändern nur die Ausgabe, nie den Ablauf, und nichts wird doppelt
ausgegeben. Stufe 2 zieht die persistente Ausgabe technisch mit: sie gibt
mehrzeilig aus, und eine Status-Zeile ohne Zeilenumbruch würde überklebt.

Der Tastendruck des manuellen Modus wird im WORKER-Thread gelesen — ist
gleichzeitig ein Editor offen, lesen zwei Threads von der Konsole.
"""

from __future__ import annotations

import time

from ..models import AutoClickerState, SequenceStep
from ..utils import col, dbg, describe_color, hint, read_command, warn
from ..winapi import get_cursor_pos, set_cursor_pos

# Ausgang einer Vorab-Entscheidung über einen Schritt (step_gate im manuellen Modus,
# _execute_wait_for_color bei Farb-Bedingungen). Drei Ausgänge, nicht zwei: ein bool
# kann "Schritt erledigt, weiter zum nächsten" nicht von "Sequenz abbrechen" trennen —
# genau daran klickte ein Farb-Schritt nach einer else-Aktion noch sein eigenes Ziel.
GATE_RUN = "run"        # Schritt normal ausführen
GATE_SKIP = "skip"      # Diesen Schritt überspringen, Sequenz läuft normal weiter
GATE_STOP = "stop"      # Sequenz abbrechen

# Tasten im manuellen Modus. Buchstabe UND Pfeiltaste, weil beides ankommt und
# niemand nachschlagen will, welche Variante gerade gilt.
_KEYS_RUN = ("w", "enter", " ", "right")
_KEYS_SKIP = ("s", "down")
_KEYS_CONTINUE = ("c",)
_KEYS_STOP = ("q", "escape")

# Tasten im Punkte-Durchgang
_KEYS_VOR = ("w", "d", "enter", " ", "right", "down")
_KEYS_ZURUECK = ("a", "left", "up")


def is_log_debug(state: AutoClickerState) -> bool:
    """Stufe 1: persistente Ausgabe statt überschreibbarer Status-Zeile.

    Detail-Stufe und manueller Modus erzwingen das zusätzlich — keine Kopplung
    der Schalter, sondern Darstellung: sobald oberhalb mehrzeilig ausgegeben
    wird, muss die Status-Zeile eine echte Zeile sein.
    """
    return state.config.debug_log or is_detail_debug(state) or is_step_mode(state)


def is_detail_debug(state: AutoClickerState) -> bool:
    """Stufe 2: Zeiger auf den Punkt + ausschreiben, was passieren soll."""
    return state.config.debug_detail


def is_step_mode(state: AutoClickerState) -> bool:
    """Manueller Modus: Schritt für Schritt auf Bestätigung, Wartezeiten übersprungen."""
    return bool(getattr(state, "step_mode", False))


def skip_waits(state: AutoClickerState) -> bool:
    """Im manuellen Modus wird nicht gewartet - du bist die Wartezeit."""
    return is_step_mode(state)


# ---------------------------------------------------------------------------
# Anzeige-Bausteine
# ---------------------------------------------------------------------------

def color_swatch(color) -> str:
    """Farbquadrat + Name + RGB. Ohne Farbe: leerer String."""
    if not color:
        return ""
    return describe_color(tuple(color))


def color_comparison(expected, actual, dist: float, tolerance: float) -> str:
    """Erwartete und tatsächliche Farbe nebeneinander - beim Warten auf eine Farbe die
    eigentliche Frage: sieht das Skript dasselbe wie ich?"""
    verdict = "passt" if dist <= tolerance else f"zu weit (Toleranz {tolerance:.0f})"
    return (f"erwartet {color_swatch(expected)}  |  aktuell {color_swatch(actual)}  "
            f"|  Abstand {dist:.0f} -> {verdict}")


def step_label(step: SequenceStep) -> str:
    """Name + Punkt-Referenz, damit man den Schritt in der JSON wiederfindet.

    Das war der eigentliche Schmerz: ohne ID musste man den falschen Schritt in der
    Sequenzdatei erst suchen und dann noch den passenden Punkt dazu. Mit "#3" steht die
    Referenz direkt da - suchbar in points.json UND in der Sequenzdatei ("point_id": 3).
    """
    name = step.name or "unbenannt"
    if step.point_id is None:
        return f"{name}  [ohne Stelle]"
    if step.unresolved:
        # Deutlich sagen, was los ist: der Schritt tut nichts, und der Grund liegt in
        # points.json, nicht in der Sequenz.
        return f"{name}  [Punkt #{step.point_id} FEHLT]"
    return f"{name}  [Punkt #{step.point_id}]"


def describe_step(step: SequenceStep) -> str:
    """Was tut dieser Schritt? Eine Zeile."""
    if step.key_press:
        return f"Taste '{step.key_press}' drücken"
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
    if step.scroll:
        richtung = "hoch" if step.scroll > 0 else "runter"
        return f"Mausrad {richtung} x{abs(step.scroll)} bei ({step.x}, {step.y})"
    if step.wait_only:
        return "nur warten, kein Klick"
    return f"Klick auf ({step.x}, {step.y})"


def target_of(step: SequenceStep):
    """Wohin der Zeiger für diesen Schritt zeigen soll - oder None, wenn es keinen Ort
    gibt (Tastendruck, Screenshot). Bei Farb-Bedingungen ist der Prüf-Pixel wichtiger
    als der Klickpunkt: dort entscheidet sich, ob der Schritt überhaupt läuft."""
    if step.unresolved:
        return None  # kein Ziel — sonst führe der Zeiger nach (0, 0)
    if step.wait_condition is not None:
        return step.wait_condition.pixel[0], step.wait_condition.pixel[1], "Prüf-Pixel"
    if step.key_press or step.screenshot_only:
        return None
    if step.wait_only:
        return None
    return step.x, step.y, "Klickpunkt"


def show_point(state: AutoClickerState, x: int, y: int, label: str = "",
               restore: bool = False) -> None:
    """Springt mit der Maus auf eine Position OHNE zu klicken. `restore=True` setzt den
    Cursor danach zurück - beim Beobachten sinnvoll, im manuellen Modus soll der Zeiger
    stehen bleiben."""
    vorher = get_cursor_pos() if restore else None
    set_cursor_pos(x, y)
    if label:
        print(dbg(f"Zeiger auf {label} ({x}, {y})"))
    delay = state.config.pixel_show_delay
    if delay > 0:
        time.sleep(delay)
    if vorher is not None:
        set_cursor_pos(vorher[0], vorher[1])


def print_step_detail(state: AutoClickerState, step: SequenceStep, phase: str,
                      step_num: int, total_steps: int) -> None:
    """Stufe 2 (debug_detail): ausschreiben was passieren soll und den Zeiger hinsetzen.
    Blockiert nicht - der Lauf geht danach normal weiter."""
    if not is_detail_debug(state):
        return
    # Kopf und Beschreibung in EINER Zeile: getrennt sagten sie bei einem einfachen Klick
    # zweimal dasselbe. Zusatzzeilen kommen nur, wenn es wirklich mehr zu sagen gibt.
    print(col(f"── [{phase}] Schritt {step_num}/{total_steps}  {step_label(step)}"
              f"  →  {describe_step(step)}", "cyan"))

    wc = step.wait_condition
    if wc is not None:
        art = ("einmal prüfen" if wc.check_only
               else ("warten bis Farbe WEG" if wc.until_gone else "warten bis Farbe DA"))
        print(col(f"   Farbe an {wc.pixel}: {art}", "gray"))
        print(f"   {color_swatch(wc.color)}")
    if step.else_config is not None:
        print(col(f"   Fallback wenn nicht erfüllt: {step.else_config.action}", "gray"))

    ziel = target_of(step)
    if ziel is not None:
        # Im manuellen Modus setzt step_gate() den Zeiger - nicht doppelt springen.
        # Ohne Label: die Koordinaten stehen schon in der Kopfzeile.
        if not is_step_mode(state):
            show_point(state, ziel[0], ziel[1])


# ---------------------------------------------------------------------------
# Manueller Modus
# ---------------------------------------------------------------------------

def step_gate(state: AutoClickerState, step: SequenceStep, phase: str,
              step_num: int, total_steps: int) -> str:
    """Hält vor dem Schritt an, zeigt das Ziel und wartet auf Bestätigung.

    Gibt GATE_RUN / GATE_SKIP / GATE_STOP zurück; ohne manuellen Modus immer
    sofort GATE_RUN. Ausnahme: ein Schritt mit toter Punkt-Referenz läuft NIE —
    (0, 0) wäre ein Klick in die Bildschirmecke.
    """
    if step.unresolved:
        print(warn(f"[{phase}] Schritt {step_num}/{total_steps} übersprungen: "
                   f"{step_label(step)}"))
        print(hint("       Punkt fehlt in points.json — im Punkte-Menü neu setzen "
                   "oder den Schritt löschen."))
        return GATE_SKIP

    if not is_step_mode(state):
        return GATE_RUN

    print()
    print(col(f"■ MANUELL [{phase}] Schritt {step_num}/{total_steps}: {step_label(step)}",
              "yellow"))
    print(col(f"   {describe_step(step)}", "gray"))

    wc = step.wait_condition
    if wc is not None:
        art = ("einmal prüfen" if wc.check_only
               else ("bis Farbe WEG" if wc.until_gone else "bis Farbe DA"))
        print(col(f"   Farbe an {wc.pixel}: {art}", "gray"))
        print(f"   {color_swatch(wc.color)}")

    ziel = target_of(step)
    if ziel is not None:
        set_cursor_pos(ziel[0], ziel[1])
        print(col(f"   Zeiger steht auf {ziel[2]} ({ziel[0]}, {ziel[1]}) - stimmt die Stelle?",
                  "gray"))

    print(col("   [w /→] ausführen   [s /↓] überspringen   [c] normal weiterlaufen   "
              "[q /ESC] abbrechen", "yellow"))

    while not state.stop_event.is_set():
        taste = read_command()
        if taste in _KEYS_RUN:
            return GATE_RUN
        if taste in _KEYS_SKIP:
            print(dbg("übersprungen"))
            return GATE_SKIP
        if taste in _KEYS_CONTINUE:
            with state.lock:
                state.step_mode = False
            print(dbg("Manueller Modus aus - Sequenz läuft normal weiter"))
            return GATE_RUN
        if taste in _KEYS_STOP:
            print(col("   Abbruch im manuellen Modus", "red"))
            state.stop_event.set()
            return GATE_STOP
    return GATE_STOP


def walk_points(state: AutoClickerState) -> None:
    """Punkte einzeln durchgehen — ansehen und bei Bedarf neu setzen.

    Der Zeiger springt auf jeden Punkt; sitzt er falsch: Maus an die richtige
    Stelle, `n` drücken. Nichts wird geklickt.

    Weil Schritte über `point_id` zeigen, repariert ein neu gesetzter Punkt jeden
    Schritt, der ihn benutzt. Schritte ohne `point_id` erreicht das nicht — die
    verknüpft man vorher mit `link`.

    Läuft im Main-Thread, blockiert also nur die Hotkey-Loop.
    """
    from ..imaging import get_pixel_color
    from ..persistence import save_points

    with state.lock:
        punkte = list(state.points)

    if not punkte:
        print(col("Keine Punkte vorhanden.", "yellow"))
        return

    print()
    print(col(f"■ PUNKTE DURCHGEHEN ({len(punkte)} Punkte) - es wird nichts geklickt",
              "cyan"))
    print(col("   [w /→] weiter   [a /←] zurück   [q /ESC] beenden", "yellow"))
    print(col("   [n] Maus an die richtige Stelle, dann n = Punkt neu setzen", "yellow"))
    print(col("   [f] nur die Farbe an dieser Stelle neu einlesen", "yellow"))
    print(col("   (einzelner Tastendruck, kein Enter nötig)", "gray"))

    geaendert = 0
    i = 0
    while 0 <= i < len(punkte):
        p = punkte[i]
        farbe = f"  {color_swatch(p.color)}" if p.color else ""
        quelle = f"  [{p.source}]" if p.source else ""
        set_cursor_pos(p.x, p.y)
        print(f"   {i + 1}/{len(punkte)}  #{p.id} {p.name or '(ohne Name)'} "
              f"({p.x}, {p.y}){farbe}{quelle}")

        taste = read_command()
        if taste in _KEYS_STOP:
            break
        if taste in _KEYS_ZURUECK:
            i = max(0, i - 1)
            continue

        if taste == "n":
            neu_x, neu_y = get_cursor_pos()
            if (neu_x, neu_y) == (p.x, p.y):
                print(col("      Maus steht noch auf der alten Stelle - nichts geändert.",
                          "yellow"))
                continue
            alt = (p.x, p.y)
            with state.lock:
                p.x, p.y = neu_x, neu_y
                # Die Farbe gehört zur Position. Hatte der Punkt eine, wird sie
                # mitgezogen — sonst zeigt ein Farb-Trigger auf die alte Farbe an
                # der neuen Stelle und schlägt bei jedem Lauf fehl.
                if p.color:
                    neue_farbe = get_pixel_color(neu_x, neu_y)
                    if neue_farbe:
                        p.color = neue_farbe
            save_points(state)
            geaendert += 1
            print(col(f"      gesetzt: {alt} -> ({neu_x}, {neu_y})"
                      f"{'  Farbe mitgezogen' if p.color else ''}", "green"))
            i += 1
            continue

        if taste == "f":
            neue_farbe = get_pixel_color(p.x, p.y)
            if not neue_farbe:
                print(col("      Farbe konnte nicht gelesen werden.", "yellow"))
                continue
            with state.lock:
                alt_farbe, p.color = p.color, neue_farbe
            save_points(state)
            geaendert += 1
            print(col(f"      Farbe: {color_swatch(alt_farbe) if alt_farbe else '(keine)'}"
                      f"  ->  {color_swatch(neue_farbe)}", "green"))
            continue

        if taste in _KEYS_VOR:
            i += 1
            continue
        # Unbekannte Taste: stehenbleiben statt blind weiterzublaettern — sonst
        # schiebt jeder Fehlgriff den Durchgang vor und man sucht die Stelle neu.

    if geaendert:
        print(col(f"   {geaendert} Punkt(e) neu gesetzt und gespeichert.", "green"))
        print(col("   Schritte mit point_id ziehen beim nächsten Lauf automatisch nach.",
                  "gray"))
    print(col("   Punkte-Durchgang beendet.", "cyan"))
