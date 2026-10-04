"""
Sequenz-Loader: lädt eine gespeicherte Sequenz und macht sie zur aktiven.

Hier stand zusätzlich eine Diagnose, die Schritte ohne `point_id` mit dem
gleichnamigen lokalen Punkt verglich. Seit Koordinaten nur noch im Punkt
stehen, kommt ein solcher Schritt mit (0, 0) aus dem Loader — es gab nichts
mehr zu vergleichen, und gerufen wurde sie auch nicht mehr. Gemeldet werden
fehlende Punkte von `resolve()`.
"""

from ...models import AutoClickerState
from ...persistence import activate_sequence, list_available_sequences, load_sequence_file
from ...utils import col, info, interactive_select


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

    seq, _seq_path = loaded_sequences[choice]

    # Samt Scans — hier standen nur Sequenz und Punkte. Nach einem frischen
    # Start hatte der Lauf damit GAR keine Scans ("Item-Scan nicht gefunden"),
    # nach einem Wechsel die der vorigen Sequenz. Derselbe Weg liegt unter
    # CTRL+ALT+L, CTRL+ALT+S und CTRL+ALT+T ohne geladene Sequenz.
    activate_sequence(state, seq)
    print(f"\n{col('[ERFOLG]', 'green')} Sequenz '{seq.name}' geladen!\n")
