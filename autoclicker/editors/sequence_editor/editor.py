"""
Top-Level-Sequenz-Editor.

run_sequence_editor zeigt das Auswahl-Menü (neu / bestehende laden) und
delegiert an edit_sequence. edit_sequence führt durch die drei Phasen
(INIT → LOOPs → END), fragt Total-Cycles ab, druckt eine Pre-Save-Summary
und speichert die fertige Sequenz.
"""

import time
from typing import Optional

from ...models import LoopPhase, Sequence, AutoClickerState
from ...persistence import (
    list_available_sequences, load_sequence_file, save_data,
)
from ...utils import (
    breadcrumb, col, err, header, hint, interactive_select, safe_input,
)
from .loops import edit_loop_phases
from .steps import edit_phase


def run_sequence_editor(state: AutoClickerState) -> None:
    """Interaktiver Sequenz-Editor - neu erstellen oder bestehende bearbeiten."""
    print(header("SEQUENZ-EDITOR"))
    print(f"  {breadcrumb('Hauptmenü', 'Sequenz-Editor')}")

    with state.lock:
        if not state.points:
            print(f"\n{err('Erst Punkte aufnehmen')} {hint('(CTRL+ALT+A)')}")
            return

    # Bestehende Sequenzen einmal laden und cachen
    available_sequences = list_available_sequences()
    loaded_sequences = []
    menu_options = ["Neue Sequenz erstellen"]
    for name, path in available_sequences:
        seq = load_sequence_file(path)
        if seq:
            loaded_sequences.append(seq)
            menu_options.append(str(seq))

    choice = interactive_select(menu_options, title="\nWas möchtest du tun?")

    if choice == -1:
        print(f"{col('[CANCEL]', 'yellow')} Editor beendet.")
        return
    if choice == 0:
        edit_sequence(state, None)
    elif 1 <= choice < len(menu_options):
        edit_sequence(state, loaded_sequences[choice - 1])


def edit_sequence(state: AutoClickerState, existing: Optional[Sequence]) -> None:
    """Bearbeitet eine Sequenz (neu oder bestehend) mit Start + mehreren Loop-Phasen."""

    if existing:
        print(f"\n--- Bearbeite Sequenz: {existing.name} ---")
        seq_name = existing.name
        init_steps = list(existing.init_steps)
        loop_phases = [LoopPhase(lp.name, list(lp.steps), lp.repeat, lp.scheduled_start) for lp in existing.loop_phases]
        end_steps = list(existing.end_steps)
        total_cycles = existing.total_cycles
        description = existing.description
    else:
        print("\n--- Neue Sequenz erstellen ---")
        seq_name = safe_input("Name der Sequenz: ").strip()
        if not seq_name:
            seq_name = f"Sequenz_{int(time.time())}"
        init_steps = []
        loop_phases = []
        end_steps = []
        total_cycles = 1
        description = ""

    # Beschreibung (optional) — hilft beim Wiederfinden und beim Weitergeben
    if existing and description:
        print(f"\nBeschreibung: {description}")
        desc_input = safe_input("Neue Beschreibung (Enter = behalten, '-' = löschen): ").strip()
        if desc_input == "-":
            description = ""
        elif desc_input:
            description = desc_input
    else:
        desc_input = safe_input("Beschreibung (optional, Enter = keine): ").strip()
        if desc_input:
            description = desc_input

    # Verfügbare Punkte anzeigen
    with state.lock:
        print("\nVerfügbare Punkte:")
        for p in state.points:
            print(f"  {p}")

    # INIT-Phase bearbeiten (einmalig vor allen Zyklen)
    print(header("PHASE 0: INIT-SEQUENZ (wird einmalig vor allen Zyklen ausgeführt)"))
    print("  (Optional: Login, Vorbereitung, etc. – läuft nur beim allerersten Start)")
    result = edit_phase(state, init_steps, "INIT")
    if result is None:
        print(f"{col('[ABBRUCH]', 'yellow')} Sequenz nicht gespeichert.")
        return
    init_steps = result

    # LOOP-Phasen bearbeiten (mehrere möglich)
    print(header("PHASE 1: LOOP-PHASEN (können mehrere sein)"))
    loop_phases = edit_loop_phases(state, loop_phases)
    if loop_phases is None:
        print(f"{col('[ABBRUCH]', 'yellow')} Sequenz nicht gespeichert.")
        return

    # Gesamt-Zyklen abfragen
    if loop_phases:
        total_cycles = _ask_total_cycles(total_cycles)

    # END-Phase bearbeiten (optional)
    print("\n" + "=" * 60)
    print("  PHASE 3: END-SEQUENZ (wird einmal am Ende ausgeführt)")
    print("=" * 60)
    print("\n  (Optional: Aufräumen, Logout, etc.)")
    result = edit_phase(state, end_steps, "END")
    if result is None:
        print(f"{col('[ABBRUCH]', 'yellow')} Sequenz nicht gespeichert.")
        return
    end_steps = result

    _print_pre_save_summary(existing, seq_name, init_steps, loop_phases, end_steps, total_cycles)

    # Sequenz erstellen und speichern
    new_sequence = Sequence(
        name=seq_name,
        init_steps=init_steps,
        loop_phases=loop_phases,
        end_steps=end_steps,
        total_cycles=total_cycles,
        description=description
    )

    with state.lock:
        state.sequences[seq_name] = new_sequence
        state.active_sequence = new_sequence

    save_data(state)

    _print_post_save_summary(seq_name, init_steps, loop_phases, end_steps, total_cycles)


def _ask_total_cycles(current_total: int) -> int:
    """Fragt den User nach der Anzahl Gesamt-Wiederholungen. Gibt current_total bei Eingabefehler zurück."""
    print(header("GESAMT-WIEDERHOLUNGEN"))
    print("\nAblauf: INIT (1x) -> Loop1 -> Loop2 -> ... -> (wieder von vorne?) -> END (1x)")
    print("\nWie oft soll der GESAMTE Ablauf wiederholt werden?")
    print("  0 = Unendlich (manuell stoppen)")
    print("  1 = Einmal durchlaufen und stoppen")
    print("  >1 = X-mal wiederholen (Loop1 -> Loop2 -> ... -> Loop1 -> ...)")
    try:
        cycles_input = safe_input(f"\nAnzahl Zyklen (Enter = {current_total}): ").strip()
        if cycles_input:
            total = int(cycles_input)
            if total < 0:
                return 0
            return total
    except ValueError:
        print(f"Ungültige Eingabe, behalte {current_total}.")
    return current_total


def _print_pre_save_summary(existing: Optional[Sequence], seq_name: str,
                             init_steps: list, loop_phases: list, end_steps: list,
                             total_cycles: int) -> None:
    """Druckt die Zusammenfassung VOR dem Speichern (zeigt Änderungen bei Edit)."""
    print(f"\n{col('Zusammenfassung:', 'bold')}")
    if not existing:
        print(f"  {col('Neue Sequenz:', 'green')} '{seq_name}'")
        if init_steps:
            print(f"    Init: {len(init_steps)} Schritte (einmalig)")
        for lp in loop_phases:
            print(f"    {lp.name}: {len(lp.steps)} Schritte x{lp.repeat}")
        if end_steps:
            print(f"    End: {len(end_steps)} Schritte")
        cycles_desc = "Unendlich" if total_cycles == 0 else f"{total_cycles}x"
        print(f"    Zyklen: {cycles_desc}")
        return

    changes = []
    old_i, new_i = len(existing.init_steps), len(init_steps)
    if old_i != new_i:
        changes.append(f"  Init: {old_i} → {new_i} Schritte")

    old_l, new_l = len(existing.loop_phases), len(loop_phases)
    if old_l != new_l:
        changes.append(f"  Loop-Phasen: {old_l} → {new_l}")
    for i, lp in enumerate(loop_phases):
        if i < len(existing.loop_phases):
            old_lp = existing.loop_phases[i]
            if len(lp.steps) != len(old_lp.steps) or lp.repeat != old_lp.repeat:
                changes.append(f"    {lp.name}: {len(old_lp.steps)}x{old_lp.repeat} → {len(lp.steps)}x{lp.repeat}")
        else:
            changes.append(f"    {lp.name}: {col('NEU', 'green')} ({len(lp.steps)} Schritte x{lp.repeat})")

    old_e, new_e = len(existing.end_steps), len(end_steps)
    if old_e != new_e:
        changes.append(f"  End: {old_e} → {new_e} Schritte")

    if existing.total_cycles != total_cycles:
        changes.append(f"  Zyklen: {existing.total_cycles} → {total_cycles}")

    if changes:
        print(col("  Änderungen:", "yellow"))
        for c in changes:
            print(f"  {c}")
    else:
        print(f"  {hint('Keine Änderungen')}")


def _print_post_save_summary(seq_name: str, init_steps: list, loop_phases: list,
                              end_steps: list, total_cycles: int) -> None:
    """Druckt die Erfolgsmeldung mit Stats nach dem Speichern."""
    all_steps = init_steps + [s for lp in loop_phases for s in lp.steps] + end_steps
    pixel_triggers = sum(1 for s in all_steps if s.wait_condition)

    print(f"\n{col('[ERFOLG]', 'green')} Sequenz '{seq_name}' gespeichert!")
    for i, lp in enumerate(loop_phases):
        print(f"         {lp.name}: {len(lp.steps)} Schritte x{lp.repeat}")
    if end_steps:
        print(f"         End: {len(end_steps)} Schritte (einmal am Ende)")
    if total_cycles == 0:
        print(f"         Gesamt: Unendlich wiederholen")
    elif total_cycles == 1:
        print(f"         Gesamt: Einmal durchlaufen")
    else:
        print(f"         Gesamt: {total_cycles}x wiederholen")
    if pixel_triggers > 0:
        print(f"         Farb-Trigger: {pixel_triggers} Schritt(e)")
    print()
