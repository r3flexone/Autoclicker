"""
Sequenz-Worker und Status-Ausgabe.

sequence_worker ist die Hauptfunktion die als Worker-Thread läuft. Sie
verarbeitet die aktive Sequenz (INIT → LOOPs → END), behandelt
Restart/Skip-Cycle/Quit-Events und konsolidiert die Session-Statistik am Ende.

_schedule_watcher ist ein Hilfs-Thread der prüft ob Loop-Phasen mit
scheduled_start ihren Auslöse-Zeitpunkt erreicht haben.
"""

import threading
import time
from datetime import datetime

from ..models import AutoClickerState
from ..session_log import log_event
from ..utils import (
    clear_line, col, ok, err, hint, dbg,
    format_duration, safe_input,
)
from .boss_detection import _confirm_new_bosses
from .steps import execute_step


# =============================================================================
# ZEITGESTEUERTE PHASEN (Hilfs-Thread)
# =============================================================================

def _schedule_watcher(loop_phases, scheduled_pending: dict, scheduled_last_executed: dict,
                      stop_event: 'threading.Event', lock: 'threading.Lock') -> None:
    """Background-Thread: Überwacht Uhrzeiten und setzt pending-Flags.

    Prüft alle 10 Sekunden ob eine geplante Startzeit erreicht ist.
    Setzt das pending-Flag thread-safe, damit die Phase an ihrer
    natürlichen Position im Ablauf ausgeführt wird.
    """
    while not stop_event.is_set():
        now = datetime.now()
        current_h, current_m = now.hour, now.minute
        today = now.strftime('%Y-%m-%d')

        for lp in loop_phases:
            if not lp.scheduled_start:
                continue

            h, m = map(int, lp.scheduled_start.split(":"))

            if current_h == h and current_m == m:
                tracking_key = f"{lp.scheduled_start}_{today}"
                with lock:
                    if scheduled_last_executed.get(lp.name) != tracking_key:
                        scheduled_last_executed[lp.name] = tracking_key
                        scheduled_pending[lp.name] = True
                        print(col(f"\n[TIMER] {lp.name}: Startzeit {lp.scheduled_start} erreicht! (wird bei nächster Position ausgeführt)", "green"), flush=True)

        # Alle 10 Sekunden prüfen (reicht für Minuten-Genauigkeit)
        stop_event.wait(10.0)


# =============================================================================
# STATUS-AUSGABE
# =============================================================================

def print_status(state: AutoClickerState) -> None:
    """Gibt den aktuellen Status aus."""
    with state.lock:
        is_running = state.is_running
        active_seq = state.active_sequence
        seq_name = active_seq.name if active_seq else "Keine"
        points_str = f"{len(state.points)} Punkt(e)"

        clear_line()
        if is_running and active_seq:
            status_tag = col("[RUNNING]", "green")
            duration = format_duration(time.time() - state.start_time) if state.start_time else "0:00"
            stats = f"Klicks: {state.total_clicks}"
            if state.items_found > 0:
                stats += f" | Items: {state.items_found}"
            print(f"{status_tag} {seq_name} | {stats} | {hint(duration)}", flush=True)
        else:
            # "BEREIT" wenn noch nie gestartet, "STOPPED" wenn Sequenz lief und gestoppt wurde
            if state.total_clicks > 0:
                status_tag = col("[STOPPED]", "red")
            else:
                status_tag = col("[BEREIT]", "green")
            if active_seq:
                init_part = f"Init: {len(active_seq.init_steps)}, " if active_seq.init_steps else ""
                seq_info = f"{init_part}Loops: {len(active_seq.loop_phases)}"
                print(f"{status_tag} {points_str} | Sequenz: {col(seq_name, 'cyan')} ({seq_info})", flush=True)
            else:
                print(f"{status_tag} {points_str} | Sequenz: {seq_name}", flush=True)


# =============================================================================
# WORKER-HAUPTFUNKTION
# =============================================================================

def sequence_worker(state: AutoClickerState) -> None:
    """Worker-Thread, der die Sequenz ausführt."""
    debug = state.config.debug_mode
    print(col("\n[START] Sequenz gestartet.", "green"))

    sequence = _prepare_worker_state(state, debug)
    if sequence is None:
        return

    # Session-Log starten (wenn aktiviert)
    from ..session_log import start_session_log
    state.session_log = start_session_log(state)
    if state.session_log is not None:
        print(col(f"[LOG] Session-Log: {state.session_log.path}", "cyan"))
        seq = state.active_sequence
        log_event(state, "session_start", detail=seq.name if seq and hasattr(seq, "name") else "")

    schedule_thread, scheduled_pending, schedule_lock = _maybe_start_schedule_watcher(state, sequence)

    cycle_count = _run_main_loop(state, sequence, scheduled_pending, schedule_lock, debug)

    _run_end_phase(state, sequence)

    # Neu entdeckte Boss-Namen bestätigen (vor Statistik-Anzeige)
    _confirm_new_bosses(state)

    with state.lock:
        state.is_running = False
        duration = time.time() - state.start_time if state.start_time else 0

    # Session-Log schließen
    if state.session_log is not None:
        log_event(state, "session_end",
                  extra=f"clicks={state.total_clicks},items={state.items_found},keys={state.key_presses}")
        state.session_log.close()
        state.session_log = None

    _print_session_summary(state, cycle_count, duration)


def _prepare_worker_state(state: AutoClickerState, debug: bool):
    """Validiert die Sequenz, resettet Zähler/Events. Gibt die Sequence oder None bei Fehler zurück."""
    with state.lock:
        sequence = state.active_sequence
        if not sequence:
            print(err("Keine gültige Sequenz!"))
            state.is_running = False
            return None

        # Warning-Set für diese Sequenz zurücksetzen — Inkonsistenz-Warnungen einmalig
        state.warned_inconsistencies.clear()

        has_init = len(sequence.init_steps) > 0
        has_loops = len(sequence.loop_phases) > 0

        if not has_init and not has_loops:
            print(err("Sequenz ist leer!"))
            state.is_running = False
            return None

        if debug:
            print("\n" + col("=" * 60, 'gray'))
            print(dbg("GELADENE SEQUENZ-SCHRITTE:"))
            for i, step in enumerate(sequence.init_steps):
                print(col(f"  INIT[{i+1}]: {step.name or 'unnamed'}", 'green'))
            for lp in sequence.loop_phases:
                print(col(f"  --- {lp.name} (x{lp.repeat}) ---", 'magenta'))
                for i, step in enumerate(lp.steps):
                    print(col(f"  {lp.name}[{i+1}]: {step.name or 'unnamed'}", 'magenta'))
            print(col("=" * 60, 'gray'))
            if not state.scheduled_start:
                print(dbg("Drücke Enter zum Starten..."))
                time.sleep(0.3)  # Rest-Events von CTRL+ALT+S abklingen lassen
                safe_input()
            state.scheduled_start = False

        state.total_clicks = 0
        state.items_found = 0
        state.key_presses = 0
        state.skipped_cycles = 0
        state.restarts = 0
        state.timeouts = 0
        state.consecutive_timeouts = 0
        state.start_time = time.time()
        state.session_screenshots_dir = None  # Wird beim ersten Screenshot-Schritt angelegt
        state.humanize_last_break = time.monotonic()
        state.finish_event.clear()
        state.pending_new_bosses.clear()

    return sequence


def _maybe_start_schedule_watcher(state: AutoClickerState, sequence):
    """Startet den _schedule_watcher-Thread nur wenn mindestens eine Phase scheduled_start hat.

    Returns: (thread or None, scheduled_pending dict, schedule_lock)
    """
    scheduled_pending: dict = {}
    scheduled_last_executed: dict = {}
    schedule_lock = threading.Lock()
    has_scheduled = any(lp.scheduled_start for lp in sequence.loop_phases)
    schedule_thread = None
    if has_scheduled:
        schedule_thread = threading.Thread(
            target=_schedule_watcher,
            args=(sequence.loop_phases, scheduled_pending, scheduled_last_executed,
                  state.stop_event, schedule_lock),
            daemon=True
        )
        schedule_thread.start()
        scheduled_names = [f"'{lp.name}' um {lp.scheduled_start}" for lp in sequence.loop_phases if lp.scheduled_start]
        print(col(f"[TIMER] Zeitsteuerung aktiv: {', '.join(scheduled_names)}", "yellow"))
    return schedule_thread, scheduled_pending, schedule_lock


def _run_main_loop(state: AutoClickerState, sequence, scheduled_pending: dict,
                   schedule_lock: threading.Lock, debug: bool) -> int:
    """Führt INIT- + LOOP-Phasen aus, behandelt Restart/Skip-Cycle/Quit.

    Returns: Anzahl gelaufener Zyklen.
    """
    has_init = len(sequence.init_steps) > 0
    has_loops = len(sequence.loop_phases) > 0
    total_cycles = sequence.total_cycles

    cycle_count = 0
    do_restart = True  # Erster Durchlauf startet immer

    while do_restart and not state.stop_event.is_set() and not state.quit_event.is_set():
        do_restart = False

        # INIT-Phase
        if has_init and not state.stop_event.is_set():
            print(col("\n[INIT] Führe Initialisierung aus...", "green"))
            total_init = len(sequence.init_steps)
            for i, step in enumerate(sequence.init_steps):
                if state.stop_event.is_set() or state.quit_event.is_set():
                    break
                if not execute_step(state, step, i + 1, total_init, "INIT"):
                    break
            if not state.stop_event.is_set() and not state.quit_event.is_set():
                print(col("\n[INIT] Initialisierung abgeschlossen.", "green"))

        cycle_count = 0

        while not state.stop_event.is_set() and not state.quit_event.is_set():
            if state.skip_cycle_event.is_set():
                state.skip_cycle_event.clear()
                with state.lock:
                    state.skipped_cycles += 1
                print(col("\n[SKIP] Zyklus übersprungen, starte nächsten...", "yellow"))

            if state.restart_event.is_set():
                state.restart_event.clear()
                do_restart = True
                with state.lock:
                    state.restarts += 1
                print(col("\n[RESTART] Kompletter Neustart (inkl. INIT)...", "yellow"))
                break  # Bricht innere Schleife ab → äußere Schleife startet INIT erneut

            cycle_count += 1

            with state.lock:
                state.clicked_categories.clear()

            if total_cycles > 0 and cycle_count > total_cycles:
                print(f"\n{ok(f'Alle {total_cycles} Zyklen abgeschlossen!')}")
                break

            cycle_str = f"Zyklus {cycle_count}" if total_cycles == 0 else f"Zyklus {cycle_count}/{total_cycles}"

            # LOOP-Phasen
            if has_loops and not state.stop_event.is_set():
                _run_loop_phases(state, sequence, scheduled_pending, schedule_lock, cycle_str, debug)

                if state.skip_cycle_event.is_set():
                    continue
                if state.restart_event.is_set():
                    continue
                if state.stop_event.is_set():
                    break

            if state.skip_cycle_event.is_set():
                continue
            if state.restart_event.is_set():
                continue

            if not has_loops or total_cycles == 1:
                print(f"\n{ok('Sequenz einmal durchgelaufen.')}")
                break

            if state.finish_event.is_set():
                print(f"\n{ok('Sanfter Abbruch: Zyklus abgeschlossen.')}")
                break

    return cycle_count


def _run_loop_phases(state: AutoClickerState, sequence, scheduled_pending: dict,
                     schedule_lock: threading.Lock, cycle_str: str, debug: bool) -> None:
    """Führt alle Loop-Phasen einmal aus."""
    for loop_phase in sequence.loop_phases:
        if state.stop_event.is_set() or state.quit_event.is_set():
            break

        total_steps = len(loop_phase.steps)
        if total_steps == 0:
            continue

        # Zeitgesteuerte Phase: nur ausführen wenn pending-Flag gesetzt (vom Timer-Thread)
        if loop_phase.scheduled_start:
            with schedule_lock:
                is_pending = scheduled_pending.pop(loop_phase.name, False)
            if not is_pending:
                if debug:
                    print(dbg(f"'{loop_phase.name}' übersprungen (wartet auf {loop_phase.scheduled_start})"))
                continue

        print(col(f"\n[{loop_phase.name}] Starte ({loop_phase.repeat}x) | {cycle_str}", "magenta"))

        for repeat_num in range(1, loop_phase.repeat + 1):
            if state.stop_event.is_set() or state.quit_event.is_set():
                break

            if debug:
                print(dbg(f"Loop {repeat_num}/{loop_phase.repeat} von '{loop_phase.name}'"))

            for i, step in enumerate(loop_phase.steps):
                if state.stop_event.is_set() or state.quit_event.is_set():
                    break

                phase_label = f"{loop_phase.name} #{repeat_num}/{loop_phase.repeat}"
                if not execute_step(state, step, i + 1, total_steps, phase_label):
                    break

            if state.skip_cycle_event.is_set() or state.restart_event.is_set():
                break

        if state.skip_cycle_event.is_set() or state.restart_event.is_set():
            break

        if not state.stop_event.is_set() and not state.skip_cycle_event.is_set():
            print(col(f"\n[{loop_phase.name}] Abgeschlossen.", "magenta"))


def _run_end_phase(state: AutoClickerState, sequence) -> None:
    """Führt die END-Steps aus (außer bei quit_event)."""
    if not sequence.end_steps or state.quit_event.is_set():
        return

    print(col("\n[END] Führe End-Sequenz aus...", "cyan"))
    total_end = len(sequence.end_steps)

    for i, step in enumerate(sequence.end_steps):
        if state.quit_event.is_set():
            break
        execute_step(state, step, i + 1, total_end, "END")

    if not state.quit_event.is_set():
        print(col("\n[END] End-Sequenz abgeschlossen.", "cyan"))


def _print_session_summary(state: AutoClickerState, cycle_count: int, duration: float) -> None:
    """Druckt die abschließende Statistik-Ausgabe inklusive print_status."""
    print(col("\n[STOP] Sequenz gestoppt.", "red"))
    print(col("-" * 50, 'cyan'))
    print(col("STATISTIKEN:", 'bold'))
    print(f"  {col('Laufzeit:', 'cyan'):22s} {format_duration(duration)}")
    print(f"  {col('Zyklen:', 'cyan'):22s} {cycle_count}")
    print(f"  {col('Klicks:', 'cyan'):22s} {state.total_clicks}")
    if state.items_found > 0:
        print(f"  {col('Items:', 'cyan'):22s} {state.items_found}")
    if state.key_presses > 0:
        print(f"  {col('Tasten:', 'cyan'):22s} {state.key_presses}")
    if state.timeouts > 0:
        print(f"  {col('Timeouts:', 'yellow'):22s} {state.timeouts}")
        max_consec = state.config.pixel_max_consecutive_timeouts
        if max_consec > 0 and state.consecutive_timeouts >= max_consec:
            print(f"  {col('Notbremse:', 'red'):22s} Ja ({state.consecutive_timeouts}x in Folge)")
    if state.skipped_cycles > 0:
        print(f"  {col('Übersprungen:', 'yellow'):22s} {state.skipped_cycles}")
    if state.restarts > 0:
        print(f"  {col('Neustarts:', 'yellow'):22s} {state.restarts}")
    print(col("-" * 50, 'cyan'))
    print_status(state)
