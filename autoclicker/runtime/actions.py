"""
Aktions-Wrapper für den Worker-Thread.

Alle Klicks und Tastendrücke aus dem Worker laufen über safe_click/safe_key —
die bündeln Window-Fokus-Check, Humanization und Session-Logging. Niemals
direkt send_click/send_key aus winapi.py aufrufen, sonst werden diese
Querschnitts-Aspekte umgangen.

Außerdem hier: das Status-Output-Helper, die Wait-Mit-Pause-Skip-Schleife
und die generische else_config-Aktion (Fallback bei Trigger-Miss).
"""

import random
import time

from ..models import (
    AutoClickerState, SequenceStep,
    ELSE_SKIP, ELSE_SKIP_CYCLE, ELSE_RESTART, ELSE_CLICK, ELSE_KEY,
)
from ..session_log import log_event
from ..utils import clear_line, wait_while_paused, col, dbg
from ..winapi import (
    send_click, send_key, send_scroll,
    is_target_window_active, get_foreground_window_title,
)


# =============================================================================
# WINDOW-FOKUS-CHECK
# =============================================================================

def _wait_for_target_window(state: AutoClickerState, phase: str = "") -> bool:
    """Wartet bis das Ziel-Fenster den Fokus hat. Respektiert stop/pause.

    Returns:
        True wenn Fenster aktiv (oder Check deaktiviert) - Aktion darf weiterlaufen.
        False wenn gestoppt oder Fokus-Action=stop ausgelöst.
    """
    cfg = state.config
    if not cfg.window_focus_check or not cfg.window_focus_title:
        return True

    if is_target_window_active(cfg.window_focus_title):
        return True

    if cfg.window_focus_action == "stop":
        current = get_foreground_window_title()
        print(col(f"\n[FOKUS-CHECK] Ziel-Fenster '{cfg.window_focus_title}' nicht aktiv (aktuell: '{current}') - STOP!", "red"))
        log_event(state, "focus_lost_stop", detail=current)
        state.stop_event.set()
        return False

    # Pause-Modus: warten bis Fenster wieder aktiv
    log_event(state, "focus_lost_pause", detail=get_foreground_window_title())
    print(col(f"\n[FOKUS-CHECK] Ziel-Fenster '{cfg.window_focus_title}' nicht aktiv - pausiert bis Re-Fokus...", "yellow"))
    while not state.stop_event.is_set():
        if is_target_window_active(cfg.window_focus_title):
            log_event(state, "focus_restored")
            print(col(f"[FOKUS-CHECK] Fenster wieder aktiv - weiter.", "green"))
            return True
        if state.stop_event.wait(cfg.timing_pause_interval):
            return False
    return False


# =============================================================================
# HUMANIZATION
# =============================================================================

def _humanize_delay(state: AutoClickerState) -> None:
    """Fügt einen zufälligen Mikro-Delay vor einer Aktion ein (wenn aktiviert)."""
    cfg = state.config
    if not cfg.humanize_enabled:
        return
    lo = cfg.humanize_micro_delay_min
    hi = cfg.humanize_micro_delay_max
    if hi <= 0 or hi < lo:
        return
    delay = random.uniform(lo, hi)
    if delay > 0:
        state.stop_event.wait(delay)


def _humanize_jitter(x: int, y: int, state: AutoClickerState) -> tuple[int, int]:
    """Fügt einem Klick-Punkt einen zufälligen Pixel-Offset hinzu."""
    cfg = state.config
    if not cfg.humanize_enabled or cfg.humanize_click_jitter <= 0:
        return x, y
    j = cfg.humanize_click_jitter
    return x + random.randint(-j, j), y + random.randint(-j, j)


def _humanize_check_break(state: AutoClickerState) -> None:
    """Prüft ob eine Humanize-Pause eingelegt werden sollte."""
    cfg = state.config
    if not cfg.humanize_enabled or cfg.humanize_break_interval_min <= 0:
        return
    interval_sec = cfg.humanize_break_interval_min * 60
    now = time.monotonic()
    # Read-modify-write auf humanize_last_break unter state.lock (zwei Threads
    # können safe_click/safe_key gleichzeitig erreichen).
    with state.lock:
        if state.humanize_last_break <= 0:
            state.humanize_last_break = now
            return
        if now - state.humanize_last_break < interval_sec:
            return
    dur_min = cfg.humanize_break_duration_min * 60
    dur_max = max(cfg.humanize_break_duration_max * 60, dur_min)
    if dur_max <= 0:
        return
    duration = random.uniform(dur_min, dur_max)
    print(col(f"\n[HUMANIZE] Pause für {duration/60:.1f} Minuten...", "cyan"))
    log_event(state, "humanize_break_start", extra=f"{duration:.0f}s")
    if state.stop_event.wait(duration):
        log_event(state, "humanize_break_interrupted")
        return
    with state.lock:
        state.humanize_last_break = time.monotonic()
    log_event(state, "humanize_break_end")
    print(col(f"[HUMANIZE] Pause beendet.", "cyan"))


# =============================================================================
# SAFE-WRAPPER (Pflicht-Eintrittspunkte für Klick/Key im Worker)
# =============================================================================

def safe_click(state: AutoClickerState, x: int, y: int, label: str = "") -> bool:
    """Wrapper für send_click mit Window-Fokus-Check, Humanization und Logging.

    Returns:
        True bei Erfolg, False wenn Stop/Fokus-Abbruch.
    """
    # input_lock garantiert echte Mutual-Exclusion zwischen Sequenz-Worker und
    # dem asynchronen LLM-Boss-Thread: Fokus-Check, Humanize-Delays und der
    # SetCursorPos+SendInput-Block laufen atomar — kein interleaved Klick an
    # falscher Position mehr. input_lock NIEMALS unter state.lock nehmen
    # (Reihenfolge: input_lock zuerst, state.lock danach).
    with state.input_lock:
        if not _wait_for_target_window(state):
            return False
        _humanize_check_break(state)
        if state.stop_event.is_set():
            return False
        _humanize_delay(state)
        jx, jy = _humanize_jitter(x, y, state)
        send_click(jx, jy, state.config.click_move_delay, state.config.click_post_delay)
    log_event(state, "click", detail=label, x=jx, y=jy)
    return True


def safe_scroll(state: AutoClickerState, clicks: int, x: int = None, y: int = None,
                label: str = "") -> bool:
    """Wrapper für send_scroll mit Window-Fokus-Check, Humanization und Logging.

    Wie safe_click/safe_key: NIE send_scroll direkt aufrufen, sonst fehlen Fokus-Check,
    Humanize-Delays und der Log-Eintrag. Der Zeiger-Jitter greift hier ebenfalls, weil
    Windows das Rad-Event an das Fenster unter dem Cursor liefert.
    """
    with state.input_lock:
        if not _wait_for_target_window(state):
            return False
        _humanize_check_break(state)
        if state.stop_event.is_set():
            return False
        _humanize_delay(state)
        if x is not None and y is not None:
            x, y = _humanize_jitter(x, y, state)
        send_scroll(clicks, x, y, state.config.click_move_delay,
                    state.config.click_post_delay)
    log_event(state, "scroll", detail=str(clicks), x=x, y=y, extra=label)
    return True


def safe_key(state: AutoClickerState, key: str, label: str = "") -> bool:
    """Wrapper für send_key mit Window-Fokus-Check, Humanization und Logging."""
    # Siehe safe_click: input_lock sichert exklusiven Maus/Tastatur-Zugriff.
    with state.input_lock:
        if not _wait_for_target_window(state):
            return False
        _humanize_check_break(state)
        if state.stop_event.is_set():
            return False
        _humanize_delay(state)
        result = send_key(key)
    log_event(state, "key", detail=key, extra=label)
    return result


# =============================================================================
# STATUS-AUSGABE + PHASE-FARBEN
# =============================================================================

def is_verbose_debug(state: AutoClickerState) -> bool:
    """True = jeder Schritt wird persistent geloggt statt die Status-Zeile zu überschreiben.

    Der Einzelschritt-Modus impliziert das (eine überschreibbare Status-Zeile nützt beim
    Durchsteppen nichts). Definition liegt in runtime/debug.py, hier nur weitergereicht,
    damit bestehende Importe gültig bleiben.
    """
    from .debug import is_log_debug
    return is_log_debug(state)


def _step_status(debug: bool, phase: str, step_num: int, total_steps: int,
                  msg: str, dbg_msg: str = None) -> None:
    """Gibt Schritt-Status aus: debug-print ODER überschreibbare Status-Zeile."""
    if debug:
        print(dbg(dbg_msg if dbg_msg is not None else msg))
    else:
        clear_line()
        print(col(f"[{phase}] Schritt {step_num}/{total_steps} | {msg}",
                  _phase_color(phase)), end="", flush=True)


def _phase_color(phase: str) -> str:
    """Gibt die Farbe für eine Phase zurück."""
    p = phase.upper()
    if p.startswith("INIT"):
        return "green"
    if p.startswith("START"):
        return "blue"
    if p.startswith("END"):
        return "cyan"
    return "magenta"


# =============================================================================
# WAIT-MIT-PAUSE-SKIP
# =============================================================================

def wait_with_pause_skip(state: AutoClickerState, seconds: float, phase: str, step_num: int,
                         total_steps: int, message: str) -> bool:
    """Wartet die angegebene Zeit, respektiert Pause und Skip. Gibt False zurück wenn gestoppt."""
    remaining = seconds
    debug_active = is_verbose_debug(state)
    last_remaining = -1

    while remaining > 0:
        if state.stop_event.is_set():
            return False

        if state.skip_event.is_set():
            state.skip_event.clear()
            _c = _phase_color(phase)
            if debug_active:
                print(col(f"[{phase}] Schritt {step_num}/{total_steps} | SKIP!", _c))
            else:
                clear_line()
                print(col(f"[{phase}] Schritt {step_num}/{total_steps} | SKIP!", _c), end="", flush=True)
            return True

        if not wait_while_paused(state, message):
            return False

        current_remaining = int(remaining)
        if current_remaining != last_remaining:
            _c = _phase_color(phase)
            if debug_active:
                print(col(f"[{phase}] Schritt {step_num}/{total_steps} | {message} ({round(remaining, 1):g}s)...", _c))
            else:
                clear_line()
                print(col(f"[{phase}] Schritt {step_num}/{total_steps} | {message} ({round(remaining, 1):g}s)...", _c), end="", flush=True)
            last_remaining = current_remaining

        wait_time = min(1.0, remaining)
        if state.stop_event.wait(wait_time):
            return False
        remaining -= wait_time

    return True


# =============================================================================
# ELSE-AKTION (Fallback bei Trigger-Miss)
# =============================================================================

def execute_else_action(state: AutoClickerState, step: SequenceStep, phase: str,
                        step_num: int, total_steps: int) -> bool:
    """Führt die Else-Aktion eines Schritts aus. Gibt False zurück wenn abgebrochen.

    Teilt sich bewusst NICHT den Dispatcher mit Boss/Icon (_execute_detection_action):
    die Else-Verzögerung ist pause-/skip-aware (wait_with_pause_skip) statt eines
    einfachen stop_event.wait — anderes Verhalten, daher eigener Pfad.
    """
    ec = step.else_config
    if not ec:
        return True

    debug = is_verbose_debug(state)

    if ec.action == ELSE_SKIP:
        _step_status(debug, phase, step_num, total_steps, "ELSE: übersprungen")
        return True

    elif ec.action == ELSE_CLICK:
        if ec.delay > 0:
            if not wait_with_pause_skip(state, ec.delay, phase, step_num, total_steps,
                                        "ELSE: klicke in"):
                return False

        if state.stop_event.is_set():
            return False

        name = ec.name or f"({ec.x},{ec.y})"
        if not safe_click(state, ec.x, ec.y, label=f"else:{name}"):
            return False
        with state.lock:
            state.total_clicks += 1

        _step_status(debug, phase, step_num, total_steps,
                     f"ELSE: Klick auf {name}!", f"ELSE: Klick auf '{name}' ({ec.x}, {ec.y})")
        return True

    elif ec.action == ELSE_KEY:
        if ec.delay > 0:
            if not wait_with_pause_skip(state, ec.delay, phase, step_num, total_steps,
                                        "ELSE: Taste in"):
                return False

        if state.stop_event.is_set():
            return False

        if safe_key(state, ec.key, label="else"):
            with state.lock:
                state.key_presses += 1
            _step_status(debug, phase, step_num, total_steps, f"ELSE: Taste '{ec.key}'!")
        return True

    elif ec.action == ELSE_RESTART:
        _step_status(debug, phase, step_num, total_steps, "ELSE: Neustart!")
        state.restart_event.set()
        return False

    elif ec.action == ELSE_SKIP_CYCLE:
        _step_status(debug, phase, step_num, total_steps, "ELSE: Zyklus überspringen!")
        state.skip_cycle_event.set()
        return False

    return True
