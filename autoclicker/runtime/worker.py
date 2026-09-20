"""Sequenz-Worker und Status-Ausgabe.

`sequence_worker` läuft als Worker-Thread: verarbeitet die aktive Sequenz
(INIT → LOOPs → END), behandelt Restart/Skip-Cycle/Quit und konsolidiert die
Session-Statistik. `_schedule_watcher` prüft nebenher, ob Loop-Phasen mit
`scheduled_start` ihren Zeitpunkt erreicht haben.
"""

import threading
import time
from datetime import datetime, timedelta
from typing import Optional

from ..models import AutoClickerState
from ..session_log import log_event
from ..utils import (
    clear_line, col, ok, err, hint, dbg, warn,
    format_duration,
)
from ..utils.console import set_console_title
from . import status
from .actions import is_verbose_debug, wait_while_paused
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
    reported: set = set()   # ungueltige Zeiten einmal melden, nicht alle 10 s
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
                if idx not in reported:
                    reported.add(idx)
                    print(col(f"\n[TIMER] Ungültige Startzeit '{lp.scheduled_start}' für "
                              f"'{lp.name}' — Phase wird ignoriert.", "yellow"), flush=True)
                continue

            if current_h == h and current_m == m:
                tracking_key = f"{lp.scheduled_start}_{today}"
                with lock:
                    if scheduled_last_executed.get(idx) != tracking_key:
                        scheduled_last_executed[idx] = tracking_key
                        scheduled_pending[idx] = True
                        print(col(f"\n[TIMER] {lp.name}: Startzeit {lp.scheduled_start} erreicht! (wird bei nächster Position ausgeführt)", "green"), flush=True)

        # Alle 10 Sekunden prüfen (reicht für Minuten-Genauigkeit). Gewartet
        # wird auf stop_event — das setzt `sequence_worker` in seinem `finally`
        # direkt nach shutdown_event, also endet auch die Wartezeit dort sofort.
        # shutdown_event allein weckt NICHT; es fängt nur den Fall, dass der
        # Lauf regulär endet, ohne dass jemand Stop gedrückt hat.
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
    """Führt einen Lauf aus und räumt auch nach einem Schrittfehler vollständig auf."""
    from ..session_log import start_session_log
    import logging

    debug = is_verbose_debug(state)
    schedule_shutdown = threading.Event()
    sequence = None
    cycle_count = 0
    error = ""
    try:
        print(col("\n[START] Sequenz gestartet.", "green"))
        sequence = _prepare_worker_state(state, state.config.debug_detail)
        if sequence is None:
            return

        global _last_pause_title_state
        _last_pause_title_state = False
        set_console_title(f"> laeuft: {_ascii_title(sequence.name)}")
        state.session_log = start_session_log(state)
        if state.session_log is not None:
            print(col(f"[LOG] Session-Log: {state.session_log.path}", "cyan"))
            log_event(state, "session_start", detail=sequence.name)
        start_from = _take_start_from(state, sequence)
        status.write_status(state, {"active": True, "sequence": sequence.name,
                                "cycles": sequence.total_cycles,
                                "phases": _phase_overview(sequence),
                                "started_from": _start_from_label(sequence, start_from),
                                "start": state.start_time}, immediately=True)
        _schedule_thread, scheduled_pending, schedule_lock = _maybe_start_schedule_watcher(
            state, sequence, schedule_shutdown)
        cycle_count = _run_main_loop(state, sequence, scheduled_pending, schedule_lock, debug,
                                     start_from)
        _run_end_phase(state, sequence, start_from)
    except Exception as exc:
        error = f"Fehler: {type(exc).__name__}: {exc}"
        logging.getLogger("autoclicker").exception("Sequenzlauf fehlgeschlagen")
        print(err(error))
    finally:
        # Grund vor dem internen Stop festhalten: ein reguläres Ende bleibt ein
        # reguläres Ende. Auch ein noch wartender Async-Scan darf danach nicht klicken.
        reason = error or _end_reason(state)
        schedule_shutdown.set()
        state.stop_event.set()
        try:
            llm_thread = state.llm_thread
            if llm_thread is not None and llm_thread.is_alive():
                llm_thread.join(timeout=state.config.llm_timeout + 5)
            if sequence is not None:
                status.finish_run(state, reason, cycle_count,
                              time.time() - state.start_time if state.start_time else 0)
        finally:
            # Der gespeicherte Log-Verweis wird selbst bei einem Close-Fehler
            # gelöst. is_running bleibt bis zum Ende der Bereinigung gesetzt.
            try:
                if state.session_log is not None:
                    try:
                        log_event(state, "session_error" if error else "session_end",
                                  detail=error,
                                  extra=f"clicks={state.total_clicks},items={state.items_found},keys={state.key_presses}")
                    finally:
                        state.session_log.close()
            finally:
                with state.lock:
                    state.session_log = None
                    state.is_running = False
                set_console_title("Autoclicker - bereit")

    if sequence is not None:
        _confirm_new_bosses(state)
        _print_session_summary(state, cycle_count,
                               time.time() - state.start_time if state.start_time else 0)


def _end_reason(state: AutoClickerState) -> str:
    """Warum der Lauf zu Ende ist — in einem Satzteil.

    Steht in der Zusammenfassung der Live-Ansicht: hat er die Zyklen geschafft
    oder hat ihn etwas abgebrochen? Die Reihenfolge ist die der Dringlichkeit —
    Notbremse, dann was der Nutzer ausgeloest hat, dann der Normalfall.
    """
    limit = state.config.pixel_max_consecutive_timeouts
    if limit > 0 and state.consecutive_timeouts >= limit:
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


def _take_start_from(state: AutoClickerState, sequence) -> Optional[tuple]:
    """Holt den Einstieg `(Art, Phasen-Index, Block)` ab — und verbraucht ihn.

    Gilt fuer genau diesen Start: der naechste Druck auf CTRL+ALT+S faengt
    wieder vorn an. Zeigt er auf einen Block, den es nicht (mehr) gibt, wird
    das gesagt und normal gestartet — ein stiller Einstieg irgendwo waere
    schlimmer als keiner.
    """
    with state.lock:
        start_from = state.start_from
        state.start_from = None
    if start_from is None:
        return None
    if _start_from_steps(sequence, start_from) is None:
        print(warn("Der gewählte Einstiegs-Block existiert nicht mehr — Start von vorn."))
        return None
    print(col(f"[START] Einstieg: {_start_from_label(sequence, start_from)} — "
              f"alles davor wird übersprungen.", "cyan"))
    return start_from


def _start_from_steps(sequence, start_from: Optional[tuple]) -> Optional[list]:
    """Die Schrittliste, in die der Einstieg zeigt — oder None, wenn er ins Leere geht."""
    if start_from is None:
        return None
    try:
        kind, phase_index, block = start_from
        steps = (sequence.init_steps if kind == "init" else sequence.end_steps
                 if kind == "end" else sequence.loop_phases[int(phase_index)].steps)
        return steps if 0 <= int(block) < len(steps) else None
    except (TypeError, ValueError, IndexError):
        return None


def _start_from_label(sequence, start_from: Optional[tuple]) -> str:
    """„Loop 'X' · Block 3" — fuer Konsole und Laufstatus, leer ohne Einstieg."""
    if start_from is None:
        return ""
    kind, phase_index, block = start_from
    if kind == "loop":
        try:
            name = sequence.loop_phases[int(phase_index)].name
        except (TypeError, ValueError, IndexError):
            name = "?"
        where = f"Loop '{name}'"
    else:
        where = str(kind).upper()
    return f"{where} · Block {int(block) + 1}"


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
        state.skip_step_event.clear()
        state.pending_new_bosses.clear()

        # Punkt-Referenzen aufloesen: Schritte mit point_id folgen dem Punkte-Pool.
        # Hier statt beim Laden, damit ein zwischenzeitlich korrigierter Punkt garantiert
        # greift - egal ob die Sequenz per Laden, Quick-Switch oder Zeitplan aktiv wurde.
        from ..persistence import resolve_point_references
        point_messages = resolve_point_references(state, sequence)

    # Klick-Ziele der Scans frisch auflösen (Bestätigungsklick, Boss-/Icon-Aktion):
    # ein Editor kann zwischendurch einen Punkt verschoben haben, und der Scan soll
    # dem folgen. Ausserhalb des Locks, weil resolve_click_references selbst lockt.
    from ..persistence import resolve_click_references
    scan_messages = resolve_click_references(state, sequence)

    # Nachgezogene Punkte melden: sonst wundert man sich, warum ein Schritt anderswo
    # klickt als in der Sequenzdatei steht.
    if point_messages:
        print(col(f"\n[PUNKTE] {len(point_messages)} Schritt(e) folgen ihrem Punkt:", "cyan"))
        for m in point_messages:
            print(f"         {m}")

    for m in scan_messages:
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
                   schedule_lock: threading.Lock, debug: bool,
                   start_from: Optional[tuple] = None) -> int:
    """Führt INIT- + LOOP-Phasen aus, behandelt Restart/Skip-Cycle/Quit.

    Returns: Anzahl gelaufener Zyklen — über ALLE Anläufe. Ein Neustart
    (`restart_event`) fängt bei INIT und Zyklus 1 wieder an, denn die Grenze
    `total_cycles` meint den Durchgang ab dort; die Zusammenfassung nennt
    aber, was insgesamt gelaufen ist. Vorher stand dort nur der letzte Anlauf,
    und die Zyklen vor dem Neustart waren aus der Statistik verschwunden.

    `start_from` ist der Einstieg mitten in der Sequenz (s. `_take_start_from`):
    er gilt nur fuer den ERSTEN Anlauf und darin nur fuer den ersten Zyklus —
    danach laeuft alles wie immer, und ein Neustart faengt bei INIT an.
    """
    has_init = len(sequence.init_steps) > 0
    has_loops = len(sequence.loop_phases) > 0
    total_cycles = sequence.total_cycles

    cycle_count = 0
    cycles_before_restart = 0
    do_restart = True  # Erster Durchlauf startet immer

    while do_restart and not state.stop_event.is_set() and not state.quit_event.is_set():
        do_restart = False
        cycles_before_restart += cycle_count

        # Der Einstieg gilt fuer diesen einen Anlauf; ein Neustart nimmt ihn
        # nicht mit — „nochmal von vorn" heisst von vorn.
        entry, start_from = start_from, None
        entry_kind = entry[0] if entry else None
        first_init = int(entry[2]) if entry_kind == "init" else 0
        if entry_kind == "end":
            break               # nur die END-Phase — die uebernimmt _run_end_phase

        # INIT-Phase
        if has_init and entry_kind in (None, "init") and not state.stop_event.is_set():
            print(col("\n[INIT] Führe Initialisierung aus...", "green"))
            total_init = len(sequence.init_steps)
            status.write_status(state, {"phase": "INIT", "phase_index": -1,
                                    "phase_pos": _phase_pos(sequence, "init"),
                                    "pass_index": 1, "repeat": 1,
                                    "blocks": total_init}, immediately=True)
            for i, step in enumerate(sequence.init_steps):
                if i < first_init:
                    continue
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
            status.write_status(state, {"cycle": cycle_count, "cycles": total_cycles},
                            immediately=True)

            # LOOP-Phasen — der Einstieg gilt nur im ersten Zyklus
            if has_loops and not state.stop_event.is_set():
                loop_entry = entry if entry_kind == "loop" and cycle_count == 1 else None
                ran = _run_loop_phases(state, sequence, scheduled_pending, schedule_lock,
                                       cycle_str, debug, loop_entry)

                if state.skip_cycle_event.is_set():
                    continue
                if state.restart_event.is_set():
                    continue
                if state.stop_event.is_set():
                    break
                if ran == 0:
                    # Kein Schritt gelaufen — entweder warten alle Phasen auf
                    # ihre Uhrzeit, oder die Sequenz hat gar keine. Beides ist
                    # kein Zyklus: hier drehte die Schleife vorher ohne einen
                    # einzigen Schritt mit ~270 Umlaeufen je Sekunde (jeder mit
                    # einer Statusdatei), und `total_cycles=5` war vorbei, bevor
                    # die Uhrzeit je erreicht wurde.
                    cycle_count -= 1
                    if not _wait_for_schedule(state, sequence, scheduled_pending,
                                              schedule_lock):
                        break
                    continue

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

    return cycles_before_restart + cycle_count


def _next_schedule(sequence, now: datetime) -> Optional[tuple[str, float]]:
    """Die naechste faellige Phase: `(Name, Zeitstempel)` — oder None ohne Zeitplan.

    Eine Uhrzeit, die heute schon vorbei ist, meint morgen. Ungueltige
    Angaben ueberspringt die Rechnung; gemeldet hat sie der Timer-Thread.
    """
    best = None
    for lp in sequence.loop_phases:
        if not lp.scheduled_start:
            continue
        try:
            h, m = map(int, lp.scheduled_start.split(":"))
            target = now.replace(hour=h, minute=m, second=0, microsecond=0)
        except (ValueError, AttributeError):
            continue
        if target <= now:
            target += timedelta(days=1)
        stamp = target.timestamp()
        if best is None or stamp < best[1]:
            best = (lp.name, stamp)
    return best


def _wait_for_schedule(state: AutoClickerState, sequence, scheduled_pending: dict,
                       schedule_lock: threading.Lock) -> bool:
    """Schlaeft, bis eine zeitgesteuerte Phase faellig ist. False = Lauf beenden.

    Gerufen, wenn ein Zyklus ohne einen einzigen Schritt durch ist. Ohne
    Zeitplan gibt es dann nichts, worauf man warten koennte — die Sequenz hat
    keine Schritte, und das wird gesagt statt endlos gedreht. Mit Zeitplan
    wartet der Worker in Sekundenschritten, damit Stopp, Pause und das sanfte
    Ende weiter greifen, und sagt der Live-Ansicht, worauf er wartet.
    """
    if not any(lp.scheduled_start for lp in sequence.loop_phases):
        print(warn("Keine Phase hat Schritte — nichts auszufuehren."))
        return False
    upcoming = _next_schedule(sequence, datetime.now())
    label = (f"wartet auf {upcoming[0]} um {datetime.fromtimestamp(upcoming[1]):%H:%M}"
             if upcoming else "wartet auf den Zeitplan")
    print(col(f"\n[TIMER] {label}.", "yellow"))
    began = time.time()
    # Dieselben Felder wie beim Warten auf Zeit (`_wait_loop`), damit die
    # Live-Ansicht Restzeit und Balken ohne eigenen Zweig zeichnet.
    waiting = {"kind": "schedule", "text": label, "since": began,
               "until": upcoming[1] if upcoming else None,
               "total": round(upcoming[1] - began, 2) if upcoming else None}
    try:
        while not state.stop_event.is_set() and not state.quit_event.is_set():
            if state.finish_event.is_set():
                # Sanft beenden heisst: nicht mehr auf den naechsten Termin
                # warten. Die END-Phase laeuft danach wie sonst auch.
                return False
            if state.restart_event.is_set() or state.skip_cycle_event.is_set():
                return True
            if not wait_while_paused(state, label):
                return False
            with schedule_lock:
                if any(scheduled_pending.values()):
                    return True
            status.waiting_for(state, waiting)
            if state.stop_event.wait(1.0):
                return False
        return False
    finally:
        status.waiting_for(state, None)


def _phase_overview(sequence) -> list[dict]:
    """Alle Phasen des Laufs in der Reihenfolge, in der sie drankommen.

    Steht einmal beim Start im Laufstatus; aus der geöffneten Sequenz liesse sich
    das nicht holen, denn laufen kann eine ganz andere. Leere Loop-Phasen bleiben
    drin, damit die Positionen zu `_phase_pos()` passen.
    """
    out = []
    if sequence.init_steps:
        out.append({"name": "INIT", "kind": "init",
                     "steps": len(sequence.init_steps)})
    for phase in sequence.loop_phases:
        out.append({"name": phase.name, "kind": "loop",
                     "steps": len(phase.steps),
                     "repeat": phase.repeat,
                     "start": phase.scheduled_start or ""})
    if sequence.end_steps:
        out.append({"name": "END", "kind": "end",
                     "steps": len(sequence.end_steps)})
    return out


def _phase_pos(sequence, kind: str, idx: int = 0) -> int:
    """Position einer Phase in `_phase_overview()`.

    Die Ansicht kennt nur diese eine Liste; `phase_index` (−1 für INIT/END)
    reicht ihr nicht. Die Rechnung steht deshalb hier und nicht dreimal an den
    Schreibstellen — ein Versatz, der an einer davon fehlt, markierte die
    falsche Kachel als laufend.
    """
    offset = 1 if sequence.init_steps else 0
    if kind == "init":
        return 0
    if kind == "end":
        return offset + len(sequence.loop_phases)
    return offset + idx


def _run_loop_phases(state: AutoClickerState, sequence, scheduled_pending: dict,
                     schedule_lock: threading.Lock, cycle_str: str, debug: bool,
                     entry: Optional[tuple] = None) -> int:
    """Führt alle Loop-Phasen einmal aus. Gibt zurück, wie viele davon liefen.

    Null heisst: kein einziger Schritt in diesem Zyklus — alle Phasen leer oder
    alle warten auf ihre Uhrzeit. Der Aufrufer zählt so einen Zyklus nicht.

    `entry` = `("loop", Phasen-Index, Block)`: Phasen davor werden
    uebersprungen, die Einstiegsphase laeuft auch dann, wenn sie sonst auf
    ihre Uhrzeit wartete (wer dort einsteigt, meint JETZT), und ihr erster
    Durchlauf beginnt beim Block — die weiteren Durchlaeufe und Phasen normal.
    """
    entry_phase = int(entry[1]) if entry else -1
    entry_block = int(entry[2]) if entry else 0
    ran = 0
    for idx, loop_phase in enumerate(sequence.loop_phases):
        if state.stop_event.is_set() or state.quit_event.is_set():
            break
        if idx < entry_phase:
            continue

        total_steps = len(loop_phase.steps)
        if total_steps == 0:
            continue

        # Zeitgesteuerte Phase: nur ausführen wenn pending-Flag gesetzt (vom Timer-Thread).
        # Schlüssel ist die Position, nicht der Name — siehe _schedule_watcher.
        if loop_phase.scheduled_start:
            with schedule_lock:
                is_pending = scheduled_pending.pop(idx, False) or idx == entry_phase
            if not is_pending:
                if debug:
                    print(dbg(f"'{loop_phase.name}' übersprungen (wartet auf {loop_phase.scheduled_start})"))
                continue

        ran += 1
        print(col(f"\n[{loop_phase.name}] Starte ({loop_phase.repeat}x) | {cycle_str}", "magenta"))
        status.write_status(state, {"phase": loop_phase.name, "phase_index": idx,
                                "phase_pos": _phase_pos(sequence, "loop", idx),
                                "repeat": loop_phase.repeat,
                                "blocks": total_steps}, immediately=True)

        for repeat_num in range(1, loop_phase.repeat + 1):
            if state.stop_event.is_set() or state.quit_event.is_set():
                break
            status.write_status(state, {"pass_index": repeat_num}, immediately=True)

            if debug:
                print(dbg(f"Loop {repeat_num}/{loop_phase.repeat} von '{loop_phase.name}'"))

            first = entry_block if idx == entry_phase and repeat_num == 1 else 0
            for i, step in enumerate(loop_phase.steps):
                if i < first:
                    continue
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
    return ran


def _run_end_phase(state: AutoClickerState, sequence,
                   start_from: Optional[tuple] = None) -> None:
    """Führt die END-Steps aus (ausser bei quit_event); mit Einstieg ab dessen Block."""
    if not sequence.end_steps or state.quit_event.is_set():
        return
    first = int(start_from[2]) if start_from and start_from[0] == "end" else 0

    print(col("\n[END] Führe End-Sequenz aus...", "cyan"))
    total_end = len(sequence.end_steps)
    status.write_status(state, {"phase": "END", "phase_index": -1,
                            "phase_pos": _phase_pos(sequence, "end"),
                            "pass_index": 1, "repeat": 1,
                            "blocks": total_end}, immediately=True)

    for i, step in enumerate(sequence.end_steps):
        if i < first:
            continue
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
