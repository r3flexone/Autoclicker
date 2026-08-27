"""Sequenz-Worker und Status-Ausgabe.

`sequence_worker` läuft als Worker-Thread: verarbeitet die aktive Sequenz
(INIT → LOOPs → END), behandelt Restart/Skip-Cycle/Quit und konsolidiert die
Session-Statistik. `_schedule_watcher` prüft nebenher, ob Loop-Phasen mit
`scheduled_start` ihren Zeitpunkt erreicht haben.
"""

import threading
import time
from datetime import datetime

from ..models import AutoClickerState
from ..session_log import log_event
from ..utils import (
    clear_line, col, ok, err, hint, dbg, warn,
    format_duration,
)
from ..utils.console import set_console_title
from . import status
from .actions import is_verbose_debug
from .boss_detection import _confirm_new_bosses
from .steps import execute_step


# =============================================================================
# ZEITGESTEUERTE PHASEN (Hilfs-Thread)
# =============================================================================

def _schedule_watcher(loop_phases, scheduled_pending: dict, scheduled_last_executed: dict,
                      stop_event: 'threading.Event', lock: 'threading.Lock',
                      shutdown_event: 'threading.Event') -> None:
    """Background-Thread: Überwacht Uhrzeiten und setzt pending-Flags.

    Prüft alle 10 Sekunden und setzt das Flag thread-safe, damit die Phase an
    ihrer natürlichen Position im Ablauf läuft.

    Beide Dicts sind über die POSITION der Phase indiziert, nicht über ihren
    Namen: Namen sind frei wählbar und doppelt vergebbar — bei zwei gleichnamigen
    Phasen räumte sonst die eine das Flag der anderen ab.

    Terminiert bei stop_event UND shutdown_event, sonst liefe der Timer als
    Geister-Thread weiter.
    """
    while not stop_event.is_set() and not shutdown_event.is_set():
        now = datetime.now()
        current_h, current_m = now.hour, now.minute
        today = now.strftime('%Y-%m-%d')

        for idx, lp in enumerate(loop_phases):
            if not lp.scheduled_start:
                continue

            try:
                h, m = map(int, lp.scheduled_start.split(":"))
            except (ValueError, AttributeError):
                print(col(f"\n[TIMER] Ungültige Startzeit '{lp.scheduled_start}' für '{lp.name}' — Phase wird ignoriert.", "yellow"), flush=True)
                continue

            if current_h == h and current_m == m:
                tracking_key = f"{lp.scheduled_start}_{today}"
                with lock:
                    if scheduled_last_executed.get(idx) != tracking_key:
                        scheduled_last_executed[idx] = tracking_key
                        scheduled_pending[idx] = True
                        print(col(f"\n[TIMER] {lp.name}: Startzeit {lp.scheduled_start} erreicht! (wird bei nächster Position ausgeführt)", "green"), flush=True)

        # Alle 10 Sekunden prüfen (reicht für Minuten-Genauigkeit).
        # shutdown_event beendet die Wartezeit sofort beim Sequenz-Ende.
        if stop_event.wait(10.0):
            break
        if shutdown_event.is_set():
            break


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
    debug = is_verbose_debug(state)
    show_preview = state.config.debug_detail
    print(col("\n[START] Sequenz gestartet.", "green"))

    sequence = _prepare_worker_state(state, show_preview)
    if sequence is None:
        set_console_title("Autoclicker - bereit")
        return

    global _last_pause_title_state
    _last_pause_title_state = False  # Start = laufend (Titel bereits gesetzt)
    set_console_title(f"> laeuft: {_ascii_title(sequence.name)}")

    # Session-Log starten (wenn aktiviert)
    from ..session_log import start_session_log
    state.session_log = start_session_log(state)
    if state.session_log is not None:
        print(col(f"[LOG] Session-Log: {state.session_log.path}", "cyan"))
        seq = state.active_sequence
        log_event(state, "session_start", detail=seq.name if seq and hasattr(seq, "name") else "")

    # Laufstatus für das Sequenz-Studio (anderer Prozess, sieht diesen State nicht).
    status.schreibe(state, {"aktiv": True, "sequenz": sequence.name,
                            "zyklen": sequence.total_cycles,
                            "phasen": _phasen_uebersicht(sequence),
                            "start": state.start_time}, sofort=True)

    # shutdown_event beendet den Schedule-Watcher IMMER am Worker-Ende (finally),
    # auch bei regulärem Sequenz-Ende — sonst läuft der Timer als Geister-Thread weiter.
    schedule_shutdown = threading.Event()
    cycle_count = 0
    try:
        _schedule_thread, scheduled_pending, schedule_lock = _maybe_start_schedule_watcher(
            state, sequence, schedule_shutdown)

        cycle_count = _run_main_loop(state, sequence, scheduled_pending, schedule_lock, debug)

        _run_end_phase(state, sequence)
    finally:
        schedule_shutdown.set()
        # Auch bei Abbruch: ein stehengebliebenes „aktiv" behauptet einen Lauf,
        # den es nicht gibt. Statt zu loeschen bleibt die Zusammenfassung stehen
        # — die Live-Ansicht war sonst genau in dem Moment leer, in dem man sie
        # ansieht: direkt nachdem etwas fertig geworden ist.
        status.beende(state, _ende_grund(state), cycle_count,
                      time.time() - state.start_time if state.start_time else 0)

    # Laufenden Async-LLM-Boss-Thread abwarten, bevor Log/Statistik abgeschlossen
    # werden. Sonst kann der Daemon-Thread nach Sequenz-Ende noch Klicks/Tasten
    # feuern (Phantom-Aktionen) und Zähler nach der Statistik-Ausgabe mutieren.
    llm_thread = state.llm_thread
    if llm_thread is not None and llm_thread.is_alive():
        join_timeout = state.config.llm_timeout + 5
        llm_thread.join(timeout=join_timeout)
        if llm_thread.is_alive() and debug:
            print(dbg(f"  → Async-LLM-Thread nach {join_timeout}s noch aktiv (Daemon, wird bei Beenden verworfen)"))

    with state.lock:
        state.is_running = False
        duration = time.time() - state.start_time if state.start_time else 0

    # Neu entdeckte Boss-Namen informieren (NACH is_running=False, damit der
    # Stop-Hotkey nicht durch einen blockierenden Prompt eingefroren wird).
    _confirm_new_bosses(state)

    # Session-Log schliessen
    if state.session_log is not None:
        log_event(state, "session_end",
                  extra=f"clicks={state.total_clicks},items={state.items_found},keys={state.key_presses}")
        state.session_log.close()
        state.session_log = None

    _print_session_summary(state, cycle_count, duration)
    set_console_title("Autoclicker - bereit")


def _ende_grund(state: AutoClickerState) -> str:
    """Warum der Lauf zu Ende ist — in einem Satzteil.

    Steht in der Zusammenfassung der Live-Ansicht: hat er die Zyklen geschafft
    oder hat ihn etwas abgebrochen? Die Reihenfolge ist die der Dringlichkeit —
    Notbremse, dann was der Nutzer ausgeloest hat, dann der Normalfall.
    """
    grenze = state.config.pixel_max_consecutive_timeouts
    if grenze > 0 and state.consecutive_timeouts >= grenze:
        return f"Notbremse nach {state.consecutive_timeouts} Timeouts in Folge"
    if state.quit_event.is_set():
        return "Programm wird beendet"
    if state.finish_event.is_set():
        return "sanft beendet (END-Phase gelaufen)"
    if state.stop_event.is_set():
        return "von Hand gestoppt"
    return "alle Zyklen durchgelaufen"


def _ascii_title(text: str) -> str:
    """Reduziert einen Text auf ASCII für den Konsolentitel (Umlaute → ?)."""
    return text.encode("ascii", "replace").decode("ascii")


# Letzter im Titel gespiegelter Pause-Zustand — verhindert SetConsoleTitle-Spam.
# None = noch nicht gesetzt (erzwingt erstes Update beim Worker-Start).
_last_pause_title_state = None


def _sync_pause_title(state: AutoClickerState, seq_name: str) -> None:
    """Aktualisiert den Konsolentitel bei Wechsel des Pause-Zustands (nicht jede Iteration)."""
    global _last_pause_title_state
    paused = state.pause_event.is_set()
    if paused == _last_pause_title_state:
        return
    _last_pause_title_state = paused
    if paused:
        set_console_title("|| pausiert")
    else:
        set_console_title(f"> laeuft: {_ascii_title(seq_name)}")


def _prepare_worker_state(state: AutoClickerState, show_preview: bool):
    """Validiert die Sequenz, resettet Zähler/Events. Gibt die Sequence oder None bei Fehler zurück.

    Die Schritt-Übersicht (nur bei debug_detail) wird bewusst AUSSERHALB von state.lock
    ausgegeben — Konsolen-Ausgabe unter Lock hält die Hotkeys unnötig auf.
    """
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
        # Stale Events aus der Vorsession löschen — sonst Phantom-Skip/Restart
        state.restart_event.clear()
        state.skip_cycle_event.clear()
        state.pending_new_bosses.clear()

        # Punkt-Referenzen aufloesen: Schritte mit point_id folgen dem Punkte-Pool.
        # Hier statt beim Laden, damit ein zwischenzeitlich korrigierter Punkt garantiert
        # greift - egal ob die Sequenz per Laden, Quick-Switch oder Zeitplan aktiv wurde.
        from ..persistence import resolve_point_references
        punkt_meldungen = resolve_point_references(state, sequence)

    # Item-/Slot-Referenzen der Scans frisch auflösen: ein Editor kann zwischendurch ein
    # globales Item geändert haben, und der Scan soll dem folgen. Ausserhalb des Locks,
    # weil resolve_scan_references selbst lockt.
    from ..persistence import resolve_scan_references
    scan_meldungen = resolve_scan_references(state, sequence)

    # Nachgezogene Punkte melden: sonst wundert man sich, warum ein Schritt anderswo
    # klickt als in der Sequenzdatei steht.
    if punkt_meldungen:
        print(col(f"\n[PUNKTE] {len(punkt_meldungen)} Schritt(e) folgen ihrem Punkt:", "cyan"))
        for m in punkt_meldungen:
            print(f"         {m}")

    for m in scan_meldungen:
        print(warn(m))

    # Schritt-Uebersicht ausgeben (nur Detail-Stufe). Bewusst OHNE Enter-Prompt: die
    # Ausgabe-Stufen aendern nur, was man sieht. Wer Schritt fuer Schritt bestaetigen
    # will, nimmt den manuellen Modus (Punkte-Menue -> 'manuell').
    if show_preview:
        print("\n" + col("=" * 60, 'gray'))
        print(dbg("GELADENE SEQUENZ-SCHRITTE:"))
        for i, step in enumerate(sequence.init_steps):
            print(col(f"  INIT[{i+1}]: {step.name or 'unnamed'}", 'green'))
        for lp in sequence.loop_phases:
            print(col(f"  --- {lp.name} (x{lp.repeat}) ---", 'magenta'))
            for i, step in enumerate(lp.steps):
                print(col(f"  {lp.name}[{i+1}]: {step.name or 'unnamed'}", 'magenta'))
        print(col("=" * 60, 'gray'))

    return sequence


def _maybe_start_schedule_watcher(state: AutoClickerState, sequence,
                                  shutdown_event: threading.Event):
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
                  state.stop_event, schedule_lock, shutdown_event),
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
            status.schreibe(state, {"phase": "INIT", "phase_index": -1,
                                    "phase_pos": _phase_pos(sequence, "init"),
                                    "durchlauf": 1, "wiederholungen": 1,
                                    "bloecke": total_init}, sofort=True)
            for i, step in enumerate(sequence.init_steps):
                if state.stop_event.is_set() or state.quit_event.is_set():
                    break
                if not execute_step(state, step, i + 1, total_init, "INIT"):
                    break
            if not state.stop_event.is_set() and not state.quit_event.is_set():
                print(col("\n[INIT] Initialisierung abgeschlossen.", "green"))

        cycle_count = 0

        while not state.stop_event.is_set() and not state.quit_event.is_set():
            # Pause-Status im Konsolentitel spiegeln (nur bei Wechsel, nicht
            # jede Iteration). Mid-Step-Pausen behandelt wait_while_paused selbst —
            # hier wird der Titel am Zyklus-Rand konsolidiert.
            _sync_pause_title(state, sequence.name)

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
                break  # Bricht innere Schleife ab → äussere Schleife startet INIT erneut

            # Limit VOR dem Inkrement prüfen — sonst zeigt die Statistik N+1 Zyklen
            if total_cycles > 0 and cycle_count >= total_cycles:
                print(f"\n{ok(f'Alle {total_cycles} Zyklen abgeschlossen!')}")
                break

            cycle_count += 1

            with state.lock:
                state.clicked_categories.clear()

            cycle_str = f"Zyklus {cycle_count}" if total_cycles == 0 else f"Zyklus {cycle_count}/{total_cycles}"
            status.schreibe(state, {"zyklus": cycle_count, "zyklen": total_cycles},
                            sofort=True)

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


def _phasen_uebersicht(sequence) -> list[dict]:
    """Alle Phasen des Laufs in der Reihenfolge, in der sie drankommen.

    Steht einmal beim Start im Laufstatus; aus der geöffneten Sequenz liesse sich
    das nicht holen, denn laufen kann eine ganz andere. Leere Loop-Phasen bleiben
    drin, damit die Positionen zu `_phase_pos()` passen.
    """
    raus = []
    if sequence.init_steps:
        raus.append({"name": "INIT", "art": "init",
                     "schritte": len(sequence.init_steps)})
    for phase in sequence.loop_phases:
        raus.append({"name": phase.name, "art": "loop",
                     "schritte": len(phase.steps),
                     "wiederholungen": phase.repeat,
                     "start": phase.scheduled_start or ""})
    if sequence.end_steps:
        raus.append({"name": "END", "art": "end",
                     "schritte": len(sequence.end_steps)})
    return raus


def _phase_pos(sequence, art: str, idx: int = 0) -> int:
    """Position einer Phase in `_phasen_uebersicht()`.

    Die Ansicht kennt nur diese eine Liste; `phase_index` (−1 für INIT/END)
    reicht ihr nicht. Die Rechnung steht deshalb hier und nicht dreimal an den
    Schreibstellen — ein Versatz, der an einer davon fehlt, markierte die
    falsche Kachel als laufend.
    """
    versatz = 1 if sequence.init_steps else 0
    if art == "init":
        return 0
    if art == "end":
        return versatz + len(sequence.loop_phases)
    return versatz + idx


def _run_loop_phases(state: AutoClickerState, sequence, scheduled_pending: dict,
                     schedule_lock: threading.Lock, cycle_str: str, debug: bool) -> None:
    """Führt alle Loop-Phasen einmal aus."""
    for idx, loop_phase in enumerate(sequence.loop_phases):
        if state.stop_event.is_set() or state.quit_event.is_set():
            break

        total_steps = len(loop_phase.steps)
        if total_steps == 0:
            continue

        # Zeitgesteuerte Phase: nur ausführen wenn pending-Flag gesetzt (vom Timer-Thread).
        # Schlüssel ist die Position, nicht der Name — siehe _schedule_watcher.
        if loop_phase.scheduled_start:
            with schedule_lock:
                is_pending = scheduled_pending.pop(idx, False)
            if not is_pending:
                if debug:
                    print(dbg(f"'{loop_phase.name}' übersprungen (wartet auf {loop_phase.scheduled_start})"))
                continue

        print(col(f"\n[{loop_phase.name}] Starte ({loop_phase.repeat}x) | {cycle_str}", "magenta"))
        status.schreibe(state, {"phase": loop_phase.name, "phase_index": idx,
                                "phase_pos": _phase_pos(sequence, "loop", idx),
                                "wiederholungen": loop_phase.repeat,
                                "bloecke": total_steps}, sofort=True)

        for repeat_num in range(1, loop_phase.repeat + 1):
            if state.stop_event.is_set() or state.quit_event.is_set():
                break
            status.schreibe(state, {"durchlauf": repeat_num}, sofort=True)

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
    """Führt die END-Steps aus (ausser bei quit_event)."""
    if not sequence.end_steps or state.quit_event.is_set():
        return

    print(col("\n[END] Führe End-Sequenz aus...", "cyan"))
    total_end = len(sequence.end_steps)
    status.schreibe(state, {"phase": "END", "phase_index": -1,
                            "phase_pos": _phase_pos(sequence, "end"),
                            "durchlauf": 1, "wiederholungen": 1,
                            "bloecke": total_end}, sofort=True)

    for i, step in enumerate(sequence.end_steps):
        if state.quit_event.is_set():
            break
        execute_step(state, step, i + 1, total_end, "END")

    if not state.quit_event.is_set():
        print(col("\n[END] End-Sequenz abgeschlossen.", "cyan"))


def _print_session_summary(state: AutoClickerState, cycle_count: int, duration: float) -> None:
    """Druckt die abschliessende Statistik-Ausgabe inklusive print_status."""
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
