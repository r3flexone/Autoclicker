"""
Loop-Phasen-Editor: verwaltet die Liste der LoopPhase-Objekte einer Sequenz.

Befehle: add/edit/del/time/show. Jeder Loop hat einen Namen, eine Schritt-Liste
(über edit_phase bearbeitet), eine repeat-Zahl und optional eine scheduled_start
Uhrzeit (HH:MM) bei der die Phase nur ausgeführt wird.
"""

from typing import Optional

from ...models import LoopPhase, AutoClickerState
from ...utils import (
    cancel_hint, confirm, hint, is_cancel, safe_input, suggest_command,
)
from .helpers import parse_time_input
from .steps import edit_phase


def edit_loop_phases(state: AutoClickerState, loop_phases: list[LoopPhase]) -> Optional[list[LoopPhase]]:
    """Bearbeitet mehrere Loop-Phasen.

    Returns:
        Liste der Loop-Phasen bei 'fertig', None bei 'cancel'.
    """

    if loop_phases:
        print(f"\nAktuelle Loop-Phasen ({len(loop_phases)}):")
        for i, lp in enumerate(loop_phases):
            print(f"  {i+1}. {lp}")

    def _print_loops_help():
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

    _print_loops_help()

    while True:
        try:
            prompt = f"[LOOPS: {len(loop_phases)}]"
            user_input = safe_input(f"{prompt} > ").strip().lower()

            if user_input in ("done", "d"):
                return loop_phases
            elif is_cancel(user_input):
                return None  # Abbruch signalisieren
            elif user_input == "":
                continue
            elif user_input in ("help", "?"):
                _print_loops_help()
                continue
            elif user_input in ("show", "s"):
                if loop_phases:
                    print(f"\nLoop-Phasen:")
                    for i, lp in enumerate(loop_phases):
                        print(f"  {i+1}. {lp}")
                        for j, step in enumerate(lp.steps):
                            print(f"       {j+1}. {step}")
                else:
                    print("  (Keine Loop-Phasen)")
                continue
            elif user_input == "add":
                # Neue Loop-Phase
                loop_num = len(loop_phases) + 1
                loop_name = safe_input(f"  Name der Loop-Phase (Enter = 'Loop {loop_num}'): ").strip()
                if not loop_name:
                    loop_name = f"Loop {loop_num}"

                print(f"\n  Schritte für {loop_name} hinzufügen:")
                steps = edit_phase(state, [], loop_name)
                if steps is None:
                    # Abbruch im Schritt-Editor verwirft NUR diese neue Phase,
                    # nicht die ganze Loop-Liste — zurück ins Loops-Menü.
                    print(f"  {hint('Neue Loop-Phase verworfen.')}")
                    continue

                repeat = 1
                try:
                    repeat_input = safe_input(f"  Wie oft soll {loop_name} wiederholt werden? (Enter = 1): ").strip()
                    if repeat_input:
                        repeat = max(1, int(repeat_input))
                except ValueError:
                    repeat = 1

                # Geplante Startzeit abfragen
                scheduled_start = None
                print(hint("  (Phase wird nur zur angegebenen Uhrzeit ausgeführt, sonst übersprungen)"))
                time_input = safe_input(f"  Startzeit? (z.B. '12:30', Enter = sofort): ").strip()
                if time_input:
                    scheduled_start = parse_time_input(time_input)  # None bei Tippfehler = sofort

                loop_phases.append(LoopPhase(loop_name, steps, repeat, scheduled_start=scheduled_start))
                time_info = f", Start: {scheduled_start}" if scheduled_start else ""
                print(f"  + {loop_name} hinzugefügt ({len(steps)} Schritte x{repeat}{time_info})")
                continue

            elif user_input.startswith("edit "):
                try:
                    edit_num = int(user_input[5:])
                    if 1 <= edit_num <= len(loop_phases):
                        lp = loop_phases[edit_num - 1]
                        print(f"\n  Bearbeite {lp.name}:")
                        # KOPIE übergeben: edit_phase mutiert die Schritt-Liste
                        # in-place (append/pop/clear). Bei Abbruch (None) müssen die
                        # Original-Schritte unangetastet bleiben — würden wir lp.steps
                        # direkt übergeben, blieben die Änderungen trotz 'verworfen'.
                        new_steps = edit_phase(state, list(lp.steps), lp.name)
                        if new_steps is None:
                            # Abbruch verwirft nur die Schritt-Änderungen dieser
                            # Phase (alte Schritte bleiben), zurück ins Loops-Menü.
                            print(f"  {hint(f'Änderungen an {lp.name} verworfen.')}")
                            continue
                        lp.steps = new_steps
                        try:
                            repeat_input = safe_input(f"  Wiederholungen (aktuell {lp.repeat}, Enter = behalten): ").strip()
                            if repeat_input:
                                lp.repeat = max(1, int(repeat_input))
                        except ValueError:
                            pass
                        # Geplante Startzeit bearbeiten
                        current_time = lp.scheduled_start or "sofort"
                        time_input = safe_input(f"  Startzeit (aktuell {current_time}, Enter = behalten, '0' = entfernen): ").strip()
                        if time_input == "0":
                            lp.scheduled_start = None
                        elif time_input:
                            parsed = parse_time_input(time_input)
                            if parsed:
                                lp.scheduled_start = parsed
                        print(f"  + {lp.name} aktualisiert")
                    else:
                        print(f"  -> Ungültige Nr! Verfügbar: 1-{len(loop_phases)}")
                except ValueError:
                    print("  -> Format: edit <Nr>")
                continue

            elif user_input == "del all":
                if not loop_phases:
                    print("  -> Keine Loop-Phasen vorhanden!")
                    continue
                if confirm(f"  {len(loop_phases)} Loop-Phase(n) wirklich löschen?"):
                    count = len(loop_phases)
                    loop_phases.clear()
                    print(f"  + {count} Loop-Phase(n) gelöscht!")
                else:
                    print("  -> Abgebrochen")
                continue

            elif user_input.startswith("del ") and "-" in user_input[4:]:
                # Bereich löschen: del 1-3
                try:
                    range_part = user_input[4:]
                    start, end = map(int, range_part.split("-"))
                    if start < 1 or end > len(loop_phases) or start > end:
                        print(f"  -> Ungültiger Bereich! Verfügbar: 1-{len(loop_phases)}")
                        continue
                    count = end - start + 1
                    if confirm(f"  {count} Loop-Phase(n) ({start}-{end}) wirklich löschen?"):
                        del loop_phases[start-1:end]
                        print(f"  + {count} Loop-Phase(n) gelöscht!")
                    else:
                        print("  -> Abgebrochen")
                except ValueError:
                    print("  -> Format: del <Nr>-<Nr>")
                continue

            elif user_input.startswith("del "):
                try:
                    del_num = int(user_input[4:])
                    if 1 <= del_num <= len(loop_phases):
                        removed = loop_phases.pop(del_num - 1)
                        print(f"  + {removed.name} gelöscht")
                    else:
                        print(f"  -> Ungültige Nr! Verfügbar: 1-{len(loop_phases)}")
                except ValueError:
                    print("  -> Format: del <Nr>")
                continue

            elif user_input.startswith("time "):
                try:
                    time_num = int(user_input[5:])
                    if 1 <= time_num <= len(loop_phases):
                        lp = loop_phases[time_num - 1]
                        current_time = lp.scheduled_start or "sofort"
                        time_input = safe_input(f"  Startzeit für '{lp.name}' (aktuell {current_time}, '0' = entfernen): ").strip()
                        if time_input == "0":
                            lp.scheduled_start = None
                            print(f"  + Startzeit für '{lp.name}' entfernt")
                        elif time_input:
                            parsed = parse_time_input(time_input)
                            if parsed:
                                lp.scheduled_start = parsed
                                print(f"  + '{lp.name}' startet ab jetzt um {parsed}")
                    else:
                        print(f"  -> Ungültige Nr! Verfügbar: 1-{len(loop_phases)}")
                except ValueError:
                    print("  -> Format: time <Nr>")
                continue

            else:
                _known = ["add", "edit", "del", "show", "time", "help", "done", "cancel"]
                suggestion = suggest_command(user_input, _known)
                print(f"  -> Unbekannter Befehl.{suggestion} {hint('(? = Hilfe)')}")

        except (KeyboardInterrupt, EOFError):
            raise
