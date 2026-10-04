"""
Loop-Phasen-Editor: verwaltet die Liste der LoopPhase-Objekte einer Sequenz.

Befehle: add/edit/del/time/show. Jeder Loop hat einen Namen, eine Schritt-Liste
(über edit_phase bearbeitet), eine repeat-Zahl und optional eine scheduled_start
Uhrzeit (HH:MM) bei der die Phase nur ausgeführt wird.

**Ein Befehl, eine Funktion.** `edit_loop_phases()` war ein einziges `if/elif`
über alle Befehle — 201 Zeilen, Komplexität 52 und in keinem Test. Heute liest
die Schleife nur die Eingabe und fragt `_command()`, wer zuständig ist; jeder
Befehl mutiert die übergebene Liste selbst. Die Liste wird dabei in place
geändert, wie vorher: bei einem Abbruch fragt `edit_sequence()`, ob die Arbeit
verworfen werden soll, und arbeitet sonst mit genau diesem Stand weiter.
"""

from typing import Callable, Optional

from ...models import LoopPhase, AutoClickerState
from ...utils import (
    cancel_hint, confirm, hint, is_cancel, next_free_name, safe_input,
    suggest_command,
)
from .helpers import parse_clock_time
from .steps import edit_phase

_KNOWN = ["add", "edit", "del", "show", "time", "help", "done", "cancel"]


def edit_loop_phases(state: AutoClickerState, loop_phases: list[LoopPhase]) -> Optional[list[LoopPhase]]:
    """Bearbeitet mehrere Loop-Phasen.

    Returns:
        Liste der Loop-Phasen bei 'fertig', None bei 'cancel'.
    """
    if loop_phases:
        print(f"\nAktuelle Loop-Phasen ({len(loop_phases)}):")
        for i, lp in enumerate(loop_phases):
            print(f"  {i+1}. {lp}")
    _print_loops_help()

    while True:
        user_input = safe_input(f"[LOOPS: {len(loop_phases)}] > ").strip().lower()
        if user_input in ("done", "d"):
            return loop_phases
        if is_cancel(user_input):
            return None  # Abbruch signalisieren
        if not user_input:
            continue
        found = _command(user_input)
        if found is None:
            suggestion = suggest_command(user_input, _KNOWN)
            print(f"  -> Unbekannter Befehl.{suggestion} {hint('(? = Hilfe)')}")
            continue
        handler, argument = found
        handler(state, loop_phases, argument)


def _command(user_input: str) -> Optional[tuple[Callable, str]]:
    """Wer für eine Eingabe zuständig ist, samt dem Rest der Eingabe — oder None.

    Die Reihenfolge ist die Regel: `del all` vor dem Bereich, der Bereich vor
    der einzelnen Nummer. Ein Befehl ohne Argument (`edit`) ist unbekannt, nicht
    ein `edit` mit leerer Nummer.
    """
    if user_input in ("help", "?"):
        return _cmd_help, ""
    if user_input in ("show", "s"):
        return _cmd_show, ""
    if user_input == "add":
        return _cmd_add, ""
    if user_input.startswith("edit "):
        return _cmd_edit, user_input[5:]
    if user_input == "del all":
        return _cmd_delete_all, ""
    if user_input.startswith("del ") and "-" in user_input[4:]:
        return _cmd_delete_range, user_input[4:]
    if user_input.startswith("del "):
        return _cmd_delete_one, user_input[4:]
    if user_input.startswith("time "):
        return _cmd_time, user_input[5:]
    return None


def _print_loops_help() -> None:
    print("\n" + "-" * 60)
    print("Befehle:")
    print("  add            - Neue Loop-Phase hinzufügen")
    print("  edit <Nr>      - Loop-Phase bearbeiten (z.B. 'edit 1')")
    print("  del <Nr>       - Loop-Phase löschen")
    print("  del <Nr>-<Nr>  - Bereich löschen (z.B. del 1-3)")
    print("  del all        - ALLE Loop-Phasen löschen")
    print("  time <Nr>      - Startzeit setzen/ändern (z.B. 'time 1')")
    print("  show / s       - Alle Loop-Phasen anzeigen")
    print(f"  help / ? | done / d | cancel / {cancel_hint()}")
    print("-" * 60)


def _phase_index(argument: str, loop_phases: list, usage: str) -> Optional[int]:
    """Die Nummer als Listenindex — oder None, und gesagt wird, warum."""
    try:
        number = int(argument)
    except ValueError:
        print(f"  -> Format: {usage}")
        return None
    if not 1 <= number <= len(loop_phases):
        print(f"  -> Ungültige Nr! Verfügbar: 1-{len(loop_phases)}")
        return None
    return number - 1


def _ask_number(prompt: str) -> Optional[int]:
    """Eine Zahl oder None (leer bzw. keine Zahl)."""
    try:
        text = safe_input(prompt).strip()
        return int(text) if text else None
    except ValueError:
        return None


def _cmd_help(state, loop_phases, argument) -> None:
    _print_loops_help()


def _cmd_show(state, loop_phases, argument) -> None:
    if not loop_phases:
        print("  (Keine Loop-Phasen)")
        return
    print("\nLoop-Phasen:")
    for i, lp in enumerate(loop_phases):
        print(f"  {i+1}. {lp}")
        for j, step in enumerate(lp.steps):
            print(f"       {j+1}. {step}")


def _cmd_add(state, loop_phases, argument) -> None:
    # Der Vorschlag nimmt die erste FREIE Nummer statt `len + 1`: nach dem
    # Loeschen der mittleren Phase schlug das sonst einen Namen vor, den es
    # schon gibt. Doppelte Phasennamen sind zwar erlaubt (der Zeitplan haengt
    # an der Position, nicht am Namen) - aber zwei Zeilen "Loop 3" in der
    # Liste sind trotzdem eine Zumutung.
    proposal = next_free_name("Loop", {p.name: p for p in loop_phases})
    loop_name = safe_input(f"  Name der Loop-Phase (Enter = '{proposal}'): ").strip() or proposal

    print(f"\n  Schritte für {loop_name} hinzufügen:")
    steps = edit_phase(state, [], loop_name)
    if steps is None:
        # Abbruch im Schritt-Editor verwirft NUR diese neue Phase,
        # nicht die ganze Loop-Liste — zurück ins Loops-Menü.
        print(f"  {hint('Neue Loop-Phase verworfen.')}")
        return

    repeat = _ask_number(f"  Wie oft soll {loop_name} wiederholt werden? (Enter = 1): ")
    repeat = max(1, repeat) if repeat is not None else 1

    print(hint("  (Phase wird nur zur angegebenen Uhrzeit ausgeführt, sonst übersprungen)"))
    time_input = safe_input("  Startzeit? (z.B. '12:30', Enter = sofort): ").strip()
    # None bei Tippfehler = sofort; parse_clock_time sagt es selbst.
    scheduled_start = parse_clock_time(time_input) if time_input else None

    loop_phases.append(LoopPhase(loop_name, steps, repeat, scheduled_start=scheduled_start))
    time_info = f", Start: {scheduled_start}" if scheduled_start else ""
    print(f"  + {loop_name} hinzugefügt ({len(steps)} Schritte x{repeat}{time_info})")


def _cmd_edit(state, loop_phases, argument) -> None:
    index = _phase_index(argument, loop_phases, "edit <Nr>")
    if index is None:
        return
    lp = loop_phases[index]
    print(f"\n  Bearbeite {lp.name}:")
    # KOPIE übergeben: edit_phase mutiert die Schritt-Liste in-place
    # (append/pop/clear). Bei Abbruch (None) müssen die Original-Schritte
    # unangetastet bleiben — würden wir lp.steps direkt übergeben, blieben
    # die Änderungen trotz 'verworfen'.
    new_steps = edit_phase(state, list(lp.steps), lp.name)
    if new_steps is None:
        # Abbruch verwirft nur die Schritt-Änderungen dieser Phase (alte
        # Schritte bleiben), zurück ins Loops-Menü.
        print(f"  {hint(f'Änderungen an {lp.name} verworfen.')}")
        return
    lp.steps = new_steps

    repeat = _ask_number(f"  Wiederholungen (aktuell {lp.repeat}, Enter = behalten): ")
    if repeat is not None:
        lp.repeat = max(1, repeat)

    current_time = lp.scheduled_start or "sofort"
    time_input = safe_input(f"  Startzeit (aktuell {current_time}, Enter = behalten, "
                            "'0' = entfernen): ").strip()
    if time_input == "0":
        lp.scheduled_start = None
    elif time_input:
        parsed = parse_clock_time(time_input)
        if parsed:
            lp.scheduled_start = parsed
    print(f"  + {lp.name} aktualisiert")


def _cmd_delete_all(state, loop_phases, argument) -> None:
    if not loop_phases:
        print("  -> Keine Loop-Phasen vorhanden!")
        return
    count = len(loop_phases)
    if confirm(f"  {count} Loop-Phase(n) wirklich löschen?"):
        loop_phases.clear()
        print(f"  + {count} Loop-Phase(n) gelöscht!")
    else:
        print("  -> Abgebrochen")


def _cmd_delete_range(state, loop_phases, argument) -> None:
    try:
        start, end = map(int, argument.split("-"))
    except ValueError:
        print("  -> Format: del <Nr>-<Nr>")
        return
    if start < 1 or end > len(loop_phases) or start > end:
        print(f"  -> Ungültiger Bereich! Verfügbar: 1-{len(loop_phases)}")
        return
    count = end - start + 1
    if confirm(f"  {count} Loop-Phase(n) ({start}-{end}) wirklich löschen?"):
        del loop_phases[start - 1:end]
        print(f"  + {count} Loop-Phase(n) gelöscht!")
    else:
        print("  -> Abgebrochen")


def _cmd_delete_one(state, loop_phases, argument) -> None:
    index = _phase_index(argument, loop_phases, "del <Nr>")
    if index is None:
        return
    removed = loop_phases.pop(index)
    print(f"  + {removed.name} gelöscht")


def _cmd_time(state, loop_phases, argument) -> None:
    index = _phase_index(argument, loop_phases, "time <Nr>")
    if index is None:
        return
    lp = loop_phases[index]
    current_time = lp.scheduled_start or "sofort"
    time_input = safe_input(f"  Startzeit für '{lp.name}' (aktuell {current_time}, "
                            "'0' = entfernen): ").strip()
    if time_input == "0":
        lp.scheduled_start = None
        print(f"  + Startzeit für '{lp.name}' entfernt")
    elif time_input:
        parsed = parse_clock_time(time_input)
        if parsed:
            lp.scheduled_start = parsed
            print(f"  + '{lp.name}' startet ab jetzt um {parsed}")
