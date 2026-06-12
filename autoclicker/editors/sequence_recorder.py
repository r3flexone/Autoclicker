"""
Sequenz-Aufnahme: Zeichnet echte Mausklicks auf und baut daraus eine Sequenz.

Start/Stop über CTRL+ALT+J. Jeder Linksklick wird mit Position, Zeitstempel
und Pixelfarbe am Klickpunkt aufgezeichnet. Nach dem Stoppen wird eine Sequenz
mit den aufgezeichneten Klicks erstellt und direkt geladen.
"""

import time
from datetime import datetime
from pathlib import Path

from ..models import AutoClickerState, Sequence, LoopPhase, SequenceStep, ClickPoint
from ..winapi import install_mouse_hook, remove_mouse_hook
from ..utils import safe_input, col, ok, err, is_cancel, hint, info, describe_color
from ..persistence.sequences import (
    save_sequence_file, ensure_sequences_dir, save_points, get_next_point_id,
)
from ..utils import sanitize_filename
from ..config import SEQUENCES_DIR


# Klicks die schneller als dieser Abstand (Sekunden) aufeinander folgen sind
# fast immer versehentliche Doppel-/Zitterklicks — beim Stoppen wird darauf
# hingewiesen (nicht automatisch gelöscht, um echte Doppelklicks zu erhalten).
_FAST_CLICK_GAP = 0.08


def _on_click_factory(state: AutoClickerState):
    """Erstellt den Klick-Callback für den Maus-Hook."""
    def _on_click(x: int, y: int, color) -> None:
        t = time.monotonic()
        with state.lock:
            if not state.recording_active or state.recording_paused:
                return
            idx = len(state.recording_events) + 1
            state.recording_events.append((t, x, y, color))
        color_str = f" {describe_color(color)}" if color else ""
        print(f"  {col('[REC]', 'red')} #{idx} ({x}, {y}){color_str}")
    return _on_click


def start_recording(state: AutoClickerState) -> None:
    """Startet die Sequenz-Aufnahme."""
    from ..execution import print_status
    with state.lock:
        if state.is_running:
            print(f"\n{err('Stoppe zuerst den Klicker')} {hint('(CTRL+ALT+S)')}")
            return
        if state.recording_active:
            return
        state.recording_active = True
        state.recording_paused = False
        state.recording_events = []

    callback = _on_click_factory(state)
    if install_mouse_hook(callback):
        print(f"\n{col('╔══ AUFNAHME GESTARTET ══╗', 'red')}")
        print(f"  Klicke die gewünschten Positionen im Spiel.")
        print(f"  Pausieren: {col('CTRL+ALT+H', 'yellow')} (navigieren ohne aufzuzeichnen)")
        print(f"  Stoppen:   {col('CTRL+ALT+J', 'yellow')} erneut drücken")
    else:
        with state.lock:
            state.recording_active = False
            state.recording_paused = False
            state.recording_events = []
        print(f"\n{err('Maus-Hook konnte nicht installiert werden!')}")
        print(f"  Mögliche Ursache: Administratorrechte erforderlich.")


def stop_recording(state: AutoClickerState) -> None:
    """Stoppt die Aufnahme und baut eine Sequenz aus den Klicks."""
    with state.lock:
        if not state.recording_active:
            return
        state.recording_active = False
        state.recording_paused = False
        events = list(state.recording_events)
        state.recording_events = []

    remove_mouse_hook()

    if not events:
        print(f"\n{col('[AUFNAHME]', 'yellow')} Gestoppt — keine Klicks aufgezeichnet.")
        return

    print(f"\n{col('╚══ AUFNAHME GESTOPPT ══╝', 'green')} {len(events)} Klick(s) aufgezeichnet.")

    # Aufgezeichnete Klicks zeigen
    print(f"\n{col('Aufgezeichnete Klicks:', 'bold')}")
    fast_clicks = 0
    for i, (t, x, y, color) in enumerate(events):
        color_str = f"  {describe_color(color)}" if color else ""
        if i == 0:
            delay_str = "sofort"
        else:
            d = events[i][0] - events[i - 1][0]
            delay_str = f"+{d:.2f}s"
            if d < _FAST_CLICK_GAP:
                fast_clicks += 1
                delay_str = col(delay_str + " ⚡", "yellow")
        print(f"  {col(str(i+1), 'cyan'):>4}  ({x:5d}, {y:5d})  {delay_str}{color_str}")

    if fast_clicks:
        print(f"\n{col('Hinweis:', 'yellow')} {fast_clicks} sehr schnelle(r) Klick(s) (⚡, < {_FAST_CLICK_GAP:.2f}s Abstand).")
        print(hint("        Falls das versehentliche Doppelklicks waren: im Editor mit 'del <Nr>' entfernen."))

    # Sequenzname eingeben
    auto_name = f"Aufnahme_{datetime.now().strftime('%H%M%S')}"
    print(f"\nSequenz-Name (Enter = {col(auto_name, 'cyan')}, {col('cancel', 'yellow')} = verwerfen):")
    try:
        name_input = safe_input("> ").strip()
    except (KeyboardInterrupt, EOFError):
        print(f"\n{col('[VERWORFEN]', 'yellow')}")
        return

    if is_cancel(name_input):
        print(f"{col('[VERWORFEN]', 'yellow')} Aufnahme nicht gespeichert.")
        return

    seq_name = name_input if name_input else auto_name

    # Frage nach total_cycles
    print(f"\nZyklen (0 = unendlich, Enter = {col('unendlich', 'cyan')}):")
    try:
        cycles_input = safe_input("> ").strip()
    except (KeyboardInterrupt, EOFError):
        cycles_input = ""

    total_cycles = 0
    if cycles_input:
        try:
            total_cycles = max(0, int(cycles_input))
        except ValueError:
            print(f"  -> '{cycles_input}' ungültig — nutze unendlich")

    # Optionale Beschreibung (hilfreich beim späteren Wiederfinden / Weitergeben)
    print(f"\nBeschreibung (optional, Enter = {col('keine', 'cyan')}):")
    try:
        description = safe_input("> ").strip()
    except (KeyboardInterrupt, EOFError):
        description = ""
    if is_cancel(description):
        description = ""

    # SequenceSteps aus den Events bauen
    steps = []
    for i, (t, x, y, color) in enumerate(events):
        if i == 0:
            delay = 0.0
        else:
            delay = round(events[i][0] - events[i - 1][0], 2)
        step = SequenceStep(x=x, y=y, delay_before=delay, name=f"Klick {i + 1}",
                            recorded_color=color)
        steps.append(step)

    loop_phase = LoopPhase(name="Loop", steps=steps, repeat=1)
    seq = Sequence(name=seq_name, loop_phases=[loop_phase], total_cycles=total_cycles,
                   description=description)

    # Speichern
    ensure_sequences_dir()
    filename = sanitize_filename(seq_name) + ".json"
    filepath = Path(SEQUENCES_DIR) / filename

    if save_sequence_file(seq, filepath):
        with state.lock:
            state.sequences[seq_name] = seq
            state.active_sequence = seq

        # Klicks zusätzlich als globale Punkte ablegen, damit sie im normalen
        # Editor (TUI) und in der Node-Editor-Palette auftauchen. Dedup nach
        # exakter Position: bereits vorhandene Koordinaten werden nicht doppelt
        # angelegt.
        added = 0
        with state.lock:
            existing = {(p.x, p.y) for p in state.points}
            for i, (t, x, y, color) in enumerate(events):
                if (x, y) in existing:
                    continue
                pid = get_next_point_id(state)
                state.points.append(
                    ClickPoint(x, y, f"{seq_name} {i + 1}", pid, color=color,
                               source=f"Aufnahme '{seq_name}'")
                )
                existing.add((x, y))
                added += 1
        if added:
            save_points(state)

        cycles_str = "unendlich" if total_cycles == 0 else str(total_cycles)
        saved_msg = ok(f'Sequenz "{seq_name}" gespeichert!')
        print(f"\n{saved_msg}")
        print(f"  {len(steps)} Schritte  |  Zyklen: {cycles_str}")
        if added:
            print(f"  {added} neue(r) Punkt(e) global gespeichert {hint('(im Editor + Node-Palette nutzbar)')}")
        print(f"  Starten:    {col('CTRL+ALT+S', 'yellow')}")
        print(f"  Bearbeiten: {col('CTRL+ALT+E', 'yellow')}")
        print(hint("  Tipp: Im Editor wandelt 'pixel <Nr>' einen Klick in einen"))
        print(hint("        Farb-Trigger um (nutzt die aufgenommene Farbe),"))
        print(hint("        'noclick <Nr>' macht reines Warten daraus."))
    else:
        print(f"\n{err('Sequenz konnte nicht gespeichert werden!')}")


def handle_record_sequence(state: AutoClickerState) -> None:
    """Togglet die Sequenz-Aufnahme: erstes Drücken = Start, zweites = Stop."""
    with state.lock:
        is_recording = state.recording_active

    if is_recording:
        stop_recording(state)
    else:
        start_recording(state)


def handle_record_pause(state: AutoClickerState) -> None:
    """Togglet die Pause der laufenden Aufnahme (nur während einer Aufnahme aktiv)."""
    with state.lock:
        if not state.recording_active:
            print(f"\n{hint('Keine Aufnahme aktiv — CTRL+ALT+J startet eine.')}")
            return
        state.recording_paused = not state.recording_paused
        paused = state.recording_paused

    if paused:
        print(f"\n{col('[PAUSE]', 'yellow')} Aufnahme pausiert — Klicks werden NICHT aufgezeichnet.")
        print(f"  Fortsetzen: {col('CTRL+ALT+H', 'yellow')} erneut drücken")
    else:
        print(f"\n{col('[REC]', 'red')} Aufnahme fortgesetzt — Klicks werden wieder aufgezeichnet.")
