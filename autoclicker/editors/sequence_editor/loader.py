"""
Sequenz-Loader: lädt eine gespeicherte Sequenz und mappt deren Koordinaten
auf die lokalen Punkte (nützlich nach Kopie von einem anderen PC).
"""

from pathlib import Path

from ...models import Sequence, AutoClickerState, ELSE_CLICK
from ...persistence import (
    list_available_sequences, load_sequence_file, save_sequence_file,
)
from ...utils import col, info, interactive_select, ok, warn


def run_sequence_loader(state: AutoClickerState) -> None:
    """Lädt eine gespeicherte Sequenz."""
    sequences = list_available_sequences()

    if not sequences:
        print(f"\n{info('Keine Sequenzen gefunden!')}")
        print(f"       Erstelle eine mit {col('CTRL+ALT+E', 'yellow')} (Sequenz-Editor)")
        return

    with state.lock:
        active_name = state.active_sequence.name if state.active_sequence else None
    loaded_sequences = []  # (seq, filepath) Paare
    menu_options = []
    for name, path in sequences:
        seq = load_sequence_file(path)
        if seq:
            loaded_sequences.append((seq, path))
            active_marker = " *AKTIV*" if active_name and active_name == seq.name else ""
            menu_options.append(f"{seq}{active_marker}")

    choice = interactive_select(menu_options, title="\nSEQUENZ LADEN:")

    if choice == -1 or choice >= len(loaded_sequences):
        return

    seq, seq_path = loaded_sequences[choice]

    # Koordinaten auf lokale Punkte anpassen (z.B. nach Kopie von anderem PC)
    _remap_sequence_to_local_points(state, seq, seq_path)

    with state.lock:
        state.active_sequence = seq
    print(f"\n{col('[ERFOLG]', 'green')} Sequenz '{seq.name}' geladen!\n")


def _remap_sequence_to_local_points(state: AutoClickerState, sequence: Sequence,
                                    filepath: Path) -> None:
    """Mappt Sequenz-Koordinaten auf lokale Punkte (nach Name).

    Nützlich wenn eine Sequenz von einem anderen PC kopiert wurde und die
    Koordinaten an den lokalen Bildschirm angepasst werden müssen.
    Speichert direkt in die Originaldatei.
    """
    with state.lock:
        local_by_name = {p.name: p for p in state.points if p.name}

    if not local_by_name:
        return

    all_steps = (
        sequence.init_steps +
        [s for lp in sequence.loop_phases for s in lp.steps] +
        sequence.end_steps
    )

    # Erst analysieren: was würde sich ändern, was fehlt?
    updates = []  # (step, attr_prefix, old_x, old_y, new_x, new_y, name)
    missing = set()

    for step in all_steps:
        # Haupt-Klick-Punkt
        if not step.wait_only and not step.key_press and not step.item_scan:
            if step.name and (step.x != 0 or step.y != 0):
                if step.name in local_by_name:
                    lp = local_by_name[step.name]
                    if step.x != lp.x or step.y != lp.y:
                        updates.append((step, "main", step.x, step.y, lp.x, lp.y, step.name))
                else:
                    missing.add(step.name)

        # Else-Klick-Punkt
        ec = step.else_config
        if ec and ec.action == ELSE_CLICK and ec.name:
            if ec.name in local_by_name:
                lp = local_by_name[ec.name]
                if ec.x != lp.x or ec.y != lp.y:
                    updates.append((step, "else", ec.x, ec.y, lp.x, lp.y, ec.name))
            elif ec.x != 0 or ec.y != 0:
                missing.add(ec.name)

    if not updates and not missing:
        return

    if missing:
        print(f"\n{warn(f'{len(missing)} Punkt(e) fehlen lokal (bitte erst aufnehmen):')}")
        for name in sorted(missing):
            print(f"    - '{name}'")

    # Automatisch auf lokale Koordinaten aktualisieren
    if updates:
        unique_names = {u[6] for u in updates}
        print(f"\n{info(f'{len(unique_names)} Punkt(e) auf lokale Koordinaten aktualisiert:')}")
        shown = set()
        for _, _, old_x, old_y, new_x, new_y, name in updates:
            if name not in shown:
                shown.add(name)
                print(f"    '{name}': ({old_x},{old_y}) -> ({new_x},{new_y})")

        for step, prefix, _, _, new_x, new_y, _ in updates:
            if prefix == "main":
                step.x = new_x
                step.y = new_y
            else:
                step.else_config.x = new_x
                step.else_config.y = new_y
        save_sequence_file(sequence, filepath)
        print(f"    {ok('Gespeichert in')} {filepath.name}")
