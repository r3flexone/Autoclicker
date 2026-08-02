"""
Sequenz-Loader: lädt eine gespeicherte Sequenz und meldet, wenn Schritt-Koordinaten
nicht zum gleichnamigen lokalen Punkt passen (z.B. nach Kopie von einem anderen PC).
Geändert oder gespeichert wird dabei nichts - siehe _report_point_mismatches.
"""

from ...models import Sequence, AutoClickerState, ELSE_CLICK
from ...persistence import list_available_sequences, load_sequence_file
from ...utils import col, hint, info, interactive_select, warn


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
        seq = load_sequence_file(path, list(state.points))
        if seq:
            loaded_sequences.append((seq, path))
            active_marker = " *AKTIV*" if active_name and active_name == seq.name else ""
            menu_options.append(f"{seq}{active_marker}")

    choice = interactive_select(menu_options, title="\nSEQUENZ LADEN:")

    if choice == -1 or choice >= len(loaded_sequences):
        return

    seq, _seq_path = loaded_sequences[choice]

    _report_point_mismatches(state, seq)

    with state.lock:
        state.active_sequence = seq
    print(f"\n{col('[ERFOLG]', 'green')} Sequenz '{seq.name}' geladen!\n")


# Wie viele abweichende Schritte einzeln gezeigt werden, bevor nur noch gezählt wird.
_MAX_HINWEISE = 5


def _report_point_mismatches(state: AutoClickerState, sequence: Sequence) -> None:
    """Meldet Schritte, deren Koordinaten nicht zum gleichnamigen lokalen Punkt passen.

    Hier stand früher ein automatischer Remap: Schritte wurden über ihren NAMEN einem
    lokalen Punkt zugeordnet, auf dessen Koordinaten umgeschrieben und die Sequenzdatei
    sofort überschrieben. Das ist ersatzlos entfallen, aus zwei Gründen:

    1. Für "der Punkt ist die Wahrheit" gibt es die Referenz (`point_id`), die zur Laufzeit
       greift und nichts auf Platte anfasst. Zwei Mechanismen für dieselbe Aufgabe, einer
       davon still und schreibend - das war die Altlast.
    2. Der Name taugt nicht als Schlüssel: aufgenommene Punkte heißen per Default `P<id>`.
       Eine Sequenz von einem anderen Rechner bringt also Schritte namens "P3" mit, und der
       lokale "P3" liegt garantiert woanders. Der Remap hat solche Schritte stillschweigend
       verschoben und gespeichert.

    Geblieben ist die Diagnose. Zusammenführen kann man danach gezielt:
    Editor -> `link` (verknüpft über exakte Koordinaten, meldet Mehrdeutigkeiten), oder
    für einen anderen Bildschirm der Import mit Fenster-Remapping.
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

    abweichend = []   # (name, alt_xy, punkt_xy)
    fehlend = set()

    for step in all_steps:
        # Schritte MIT Referenz regelt resolve_point_references beim Start - und meldet
        # das dort auch. Hier nur die ohne.
        if step.point_id is None and not step.wait_only and not step.key_press \
                and not step.item_scan:
            if step.name and (step.x != 0 or step.y != 0):
                lp = local_by_name.get(step.name)
                if lp is None:
                    fehlend.add(step.name)
                elif (step.x, step.y) != (lp.x, lp.y):
                    abweichend.append((step.name, (step.x, step.y), (lp.x, lp.y)))

        ec = step.else_config
        if ec and ec.action == ELSE_CLICK and ec.name:
            lp = local_by_name.get(ec.name)
            if lp is None:
                if ec.x != 0 or ec.y != 0:
                    fehlend.add(ec.name)
            elif (ec.x, ec.y) != (lp.x, lp.y):
                abweichend.append((f"{ec.name} (else)", (ec.x, ec.y), (lp.x, lp.y)))

    if fehlend:
        print(f"\n{warn(f'{len(fehlend)} Punktname(n) gibt es lokal nicht:')}")
        for name in sorted(fehlend):
            print(f"    - '{name}'")
        print(f"    {hint('Die Schritte klicken auf ihre eigenen Koordinaten - oft völlig ok.')}")

    if abweichend:
        namen = {a[0] for a in abweichend}
        print(f"\n{info(f'{len(namen)} Schritt-Name(n) liegen woanders als der gleichnamige Punkt:')}")
        gezeigt = set()
        for name, alt, neu in abweichend:
            if name in gezeigt:
                continue
            gezeigt.add(name)
            if len(gezeigt) > _MAX_HINWEISE:
                print(f"    ... und {len(namen) - _MAX_HINWEISE} weitere")
                break
            print(f"    '{name}': Schritt {alt}, Punkt {neu}")
        print(f"    {hint('Nichts wurde geändert. Verknüpfen: Editor -> link (über Koordinaten).')}")
