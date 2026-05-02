"""
Sequenz-Ausführung für den Autoclicker.
Enthält die Worker-Funktion und Step-Ausführungslogik.
"""

import ctypes
import os
import random
import threading
import time
from datetime import datetime
from pathlib import Path

from .config import CONFIG
from .models import (
    AutoClickerState, SequenceStep, BossScanConfig, BossProfile,
    ELSE_SKIP, ELSE_SKIP_CYCLE, ELSE_RESTART, ELSE_CLICK, ELSE_KEY,
    SCAN_MODE_ALL, SCAN_MODE_BEST, SCAN_MODE_EVERY,
    TIMEOUT_SKIP_CYCLE, TIMEOUT_RESTART,
    CONSEC_EXIT, CONSEC_QUIT,
    BOSS_ACTION_SCAN, BOSS_ACTION_CLICK, BOSS_ACTION_KEY,
    BOSS_ACTION_SKIP, BOSS_ACTION_SKIP_CYCLE, BOSS_ACTION_RESTART,
)
from .winapi import (
    send_click, send_key, check_failsafe, set_cursor_pos,
    is_target_window_active, get_foreground_window_title,
)
from .session_log import log_event
from .utils import clear_line, wait_while_paused, safe_input, format_duration, col, ok, err, info, hint, dbg
from .imaging import (
    PILLOW_AVAILABLE, take_screenshot, color_distance, get_color_name,
    find_color_in_image, match_template_in_image
)
from .persistence import SEQUENCE_SCREENSHOTS_DIR as SCREENSHOTS_DIR


# =============================================================================
# WINDOW-FOKUS + HUMANIZATION + LOGGING WRAPPERS
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
    if state.humanize_last_break <= 0:
        state.humanize_last_break = now
        return
    if now - state.humanize_last_break < interval_sec:
        return
    # Pause-Dauer bestimmen
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
    state.humanize_last_break = time.monotonic()
    log_event(state, "humanize_break_end")
    print(col(f"[HUMANIZE] Pause beendet.", "cyan"))


def safe_click(state: AutoClickerState, x: int, y: int, label: str = "") -> bool:
    """Wrapper für send_click mit Window-Fokus-Check, Humanization und Logging.

    Returns:
        True bei Erfolg, False wenn Stop/Fokus-Abbruch.
    """
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


def safe_key(state: AutoClickerState, key: str, label: str = "") -> bool:
    """Wrapper für send_key mit Window-Fokus-Check, Humanization und Logging."""
    if not _wait_for_target_window(state):
        return False
    _humanize_check_break(state)
    if state.stop_event.is_set():
        return False
    _humanize_delay(state)
    result = send_key(key)
    log_event(state, "key", detail=key, extra=label)
    return result


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


def wait_with_pause_skip(state: AutoClickerState, seconds: float, phase: str, step_num: int,
                         total_steps: int, message: str) -> bool:
    """Wartet die angegebene Zeit, respektiert Pause und Skip. Gibt False zurück wenn gestoppt."""
    remaining = seconds
    debug_active = state.config.debug_mode or state.config.debug_detection
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


def execute_else_action(state: AutoClickerState, step: SequenceStep, phase: str,
                        step_num: int, total_steps: int) -> bool:
    """Führt die Else-Aktion eines Schritts aus. Gibt False zurück wenn abgebrochen."""
    ec = step.else_config
    if not ec:
        return True

    debug = state.config.debug_mode

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


def execute_item_scan(state: AutoClickerState, scan_name: str, mode: str = SCAN_MODE_ALL,
                      slots_override: list = None) -> list:
    """Führt einen Item-Scan aus und gibt Liste von (position, item, priority) zurück.
    slots_override: Wenn gesetzt, werden nur diese Slots gescannt (ohne Reverse-Logik)."""
    if scan_name not in state.item_scans:
        print(err(f"Item-Scan '{scan_name}' nicht gefunden!"))
        return []

    config = state.item_scans[scan_name]
    if not config.slots or not config.items:
        print(err(f"Item-Scan '{scan_name}' hat keine Slots oder Items!"))
        return []

    found_items = []

    if slots_override is not None:
        slots_to_scan = list(slots_override)
    else:
        slots_to_scan = list(config.slots)
        if state.config.scan_reverse:
            slots_to_scan = list(reversed(slots_to_scan))

    scan_delay = state.config.scan_slot_delay
    debug = state.config.debug_detection

    # Maus vor dem Scannen wegparken (verhindert Tooltip/Hover-Störungen)
    park_pos = state.config.scan_park_mouse
    if park_pos:
        if isinstance(park_pos, (list, tuple)) and len(park_pos) == 2:
            px, py = int(park_pos[0]), int(park_pos[1])
        else:
            # true = Bildschirmmitte (virtueller Desktop für Multi-Monitor)
            try:
                SM_CXVIRTUALSCREEN = 78
                SM_CYVIRTUALSCREEN = 79
                SM_XVIRTUALSCREEN = 76
                SM_YVIRTUALSCREEN = 77
                vw = ctypes.windll.user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
                vh = ctypes.windll.user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
                vx = ctypes.windll.user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
                vy = ctypes.windll.user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
                px = vx + vw // 2
                py = vy + vh // 2
            except (AttributeError, OSError):
                # Letzter Fallback: Primärmonitor
                px = ctypes.windll.user32.GetSystemMetrics(0) // 2 if hasattr(ctypes, 'windll') else 960
                py = ctypes.windll.user32.GetSystemMetrics(1) // 2 if hasattr(ctypes, 'windll') else 540
        set_cursor_pos(px, py)
        time.sleep(0.05)  # Kurz warten bis Maus angekommen & Tooltip weg

    for idx, slot in enumerate(slots_to_scan):
        if state.stop_event.is_set() or state.skip_event.is_set():
            break

        # Pause respektieren zwischen Slots
        if state.pause_event.is_set():
            while state.pause_event.is_set() and not state.stop_event.is_set():
                state.stop_event.wait(0.2)
            if state.stop_event.is_set():
                break

        if scan_delay > 0 and idx > 0:
            if state.stop_event.wait(scan_delay):
                break

        screenshot_start = time.time()
        img = take_screenshot(slot.scan_region)
        screenshot_ms = (time.time() - screenshot_start) * 1000

        if img is None:
            continue

        if debug:
            size_info = f"{img.size[0]}x{img.size[1]}" if img else "?"
            print(dbg(f"Scanne {slot.name}... (Screenshot: {screenshot_ms:.0f}ms, {size_info}px)"))

        for item in config.items:
            if _check_profile_match(item, img, config.color_tolerance, state, debug, "gefunden!"):
                found_items.append((slot, item, item.priority))
                break

    if not found_items:
        return []

    if mode == SCAN_MODE_EVERY:
        print(col(f"[SCAN] {len(found_items)} Item(s) gefunden - klicke alle!", "cyan"))
        # Items werden in Scan-Reihenfolge geklickt (bei scan_reverse: von hinten nach vorne)
        return [(slot.click_pos, item, priority) for slot, item, priority in found_items]

    # Gruppiere nach Kategorie, aber behalte die Scan-Reihenfolge
    best_per_category = {}
    ordered_categories = []  # Reihenfolge merken
    for slot, item, priority in found_items:
        cat = item.category or item.name

        with state.lock:
            if cat in state.clicked_categories:
                best_clicked_prio = state.clicked_categories[cat]
                if priority >= best_clicked_prio:
                    if debug:
                        print(dbg(f"  → {item.name} übersprungen ('{cat}' bereits geklickt)"))
                    continue

        if cat not in best_per_category:
            ordered_categories.append(cat)  # Erste Kategorie-Erscheinung merken
            best_per_category[cat] = (slot, item, priority)
        elif priority < best_per_category[cat][2]:
            best_per_category[cat] = (slot, item, priority)

    # Items in Scan-Reihenfolge zurückgeben (bei scan_reverse: von hinten nach vorne)
    filtered_items = [best_per_category[cat] for cat in ordered_categories]

    if mode == SCAN_MODE_ALL:
        print(col(f"[SCAN] {len(filtered_items)} Item(s) gefunden - klicke alle!", "cyan"))
        return [(slot.click_pos, item, priority) for slot, item, priority in filtered_items]
    else:
        if not filtered_items:
            return []
        filtered_items.sort(key=lambda x: x[2])
        best_slot, best_item, best_priority = filtered_items[0]
        print(col(f"[SCAN] Bestes Item: {best_item.name} (P{best_priority})", "cyan"))
        return [(best_slot.click_pos, best_item, best_priority)]


def _click_scan_result(state: AutoClickerState, pos, item, priority, debug: bool) -> bool:
    """Klickt ein gefundenes Item (inkl. Confirm-Klick und Delays).
    Gibt False zurück wenn stop_event während Warten feuert."""
    if debug:
        print(dbg(f"Item-Klick: '{item.name}' (P{priority}) @ ({pos[0]}, {pos[1]})"))

    if not safe_click(state, pos[0], pos[1], label=f"item:{item.name}"):
        return False
    with state.lock:
        state.total_clicks += 1
        state.items_found += 1
        cat = item.category or item.name
        if cat not in state.clicked_categories or priority < state.clicked_categories[cat]:
            state.clicked_categories[cat] = priority

    if item.confirm_point is not None:
        if item.confirm_delay > 0:
            if debug:
                print(dbg(f"Warte {item.confirm_delay}s vor Confirm..."))
            if state.stop_event.wait(item.confirm_delay):
                return False

        if debug:
            print(dbg(f"Confirm-Klick @ ({item.confirm_point.x}, {item.confirm_point.y})"))

        if not safe_click(state, item.confirm_point.x, item.confirm_point.y,
                          label=f"confirm:{item.name}"):
            return False
        with state.lock:
            state.total_clicks += 1

    click_delay = state.config.scan_item_click_delay
    if click_delay > 0:
        if state.stop_event.wait(click_delay):
            return False
    return True


def _execute_item_scan_step(state: AutoClickerState, step: SequenceStep,
                            step_num: int, total_steps: int, phase: str) -> bool:
    """Führt einen Item-Scan Schritt aus."""
    debug = state.config.debug_mode
    mode = step.item_scan_mode
    mode_str = "alle" if mode == SCAN_MODE_ALL else "bestes"
    immediate = state.config.scan_click_immediate

    if debug:
        im_str = " [IMMEDIATE]" if immediate else ""
        _step_status(debug, phase, step_num, total_steps,
                     f"Scan '{step.item_scan}' ({mode_str})...",
                     f"Starte Scan '{step.item_scan}' ({mode_str}{im_str})...")
    else:
        _step_status(debug, phase, step_num, total_steps,
                     f"Scan '{step.item_scan}' ({mode_str})...",
                     f"Starte Scan '{step.item_scan}' ({mode_str})...")

    if immediate:
        return _execute_item_scan_immediate(state, step, step_num, total_steps, phase, mode, debug)

    scan_results = execute_item_scan(state, step.item_scan, mode)

    if scan_results:
        for i, (pos, item, priority) in enumerate(scan_results):
            if state.stop_event.is_set():
                return False
            if not _click_scan_result(state, pos, item, priority, debug):
                return False
        _step_status(debug, phase, step_num, total_steps,
                     f"{len(scan_results)} Item(s)!", f"Scan fertig: {len(scan_results)} Item(s) geklickt")
    else:
        if step.else_config:
            return execute_else_action(state, step, phase, step_num, total_steps)
        _step_status(debug, phase, step_num, total_steps,
                     "Scan: kein Item gefunden", "Scan fertig: kein Item gefunden")

    return True


def _execute_item_scan_immediate(state: AutoClickerState, step: SequenceStep,
                                  step_num: int, total_steps: int, phase: str,
                                  mode: str, debug: bool) -> bool:
    """Immediate-Modus: Scan→Klick pro Slot statt alle scannen, dann alle klicken."""
    config = state.item_scans.get(step.item_scan)
    if not config or not config.slots or not config.items:
        return True

    slots = list(config.slots)
    if state.config.scan_reverse:
        slots = list(reversed(slots))

    # clicked_categories VOR dem Loop sichern, damit Klicks innerhalb
    # dieses Scan-Schritts sich nicht gegenseitig ausfiltern
    with state.lock:
        saved_categories = dict(state.clicked_categories)

    total_clicked = 0
    for slot in slots:
        if state.stop_event.is_set():
            return False

        # Für jeden Slot den Ausgangszustand wiederherstellen
        with state.lock:
            state.clicked_categories = dict(saved_categories)

        # Einen einzelnen Slot scannen
        results = execute_item_scan(state, step.item_scan, mode, slots_override=[slot])

        if results:
            for pos, item, priority in results:
                if state.stop_event.is_set():
                    return False
                if not _click_scan_result(state, pos, item, priority, debug):
                    return False
                total_clicked += 1

    if total_clicked > 0:
        _step_status(debug, phase, step_num, total_steps,
                     f"{total_clicked} Item(s)!", f"Scan fertig: {total_clicked} Item(s) geklickt (immediate)")
    else:
        if step.else_config:
            return execute_else_action(state, step, phase, step_num, total_steps)
        _step_status(debug, phase, step_num, total_steps,
                     "Scan: kein Item gefunden", "Scan fertig: kein Item gefunden (immediate)")

    return True


# =============================================================================
# PROFIL-MATCHING HELPER (gemeinsam für Item- und Boss-Erkennung)
# =============================================================================

def _check_profile_match(profile, img, color_tolerance: int,
                          state: 'AutoClickerState', debug: bool,
                          found_label: str = "gefunden") -> bool:
    """Prüft ob ein Profil (Item oder Boss) per Template/Marker im Screenshot erkannt wird.

    Returns: True wenn Template UND Marker OK und mindestens eines definiert ist.
    """
    template_ok = True
    template_info = ""
    marker_ok = True
    marker_info = ""

    if profile.template:
        match, confidence, _pos = match_template_in_image(
            img, profile.template, profile.min_confidence
        )
        template_ok = match
        template_info = (f"Template {confidence:.1%}" if match
                         else f"Template {confidence:.1%} (min: {profile.min_confidence:.0%})")

    if profile.marker_colors:
        markers_total = len(profile.marker_colors)
        markers_found = sum(1 for marker in profile.marker_colors
                            if find_color_in_image(img, marker, color_tolerance))

        require_all = state.config.scan_require_all_markers
        min_required = state.config.scan_min_markers_required

        marker_ok = (markers_found == markers_total) if require_all else (markers_found >= min_required)
        marker_info = f"Marker {markers_found}/{markers_total}"

    if debug:
        info_parts = []
        if profile.template:
            info_parts.append(template_info)
        if profile.marker_colors:
            info_parts.append(marker_info)

        if not info_parts:
            print(dbg(f"  → {profile.name}: kein Template/Marker definiert"))
        elif template_ok and marker_ok:
            print(dbg(f"  → {profile.name} {found_label} ({', '.join(info_parts)})"))
        else:
            print(dbg(f"  → {profile.name}: {', '.join(info_parts)}"))

    return template_ok and marker_ok and bool(profile.template or profile.marker_colors)


# =============================================================================
# BOSS-SCAN AUSFÜHRUNG
# =============================================================================
def execute_boss_scan(state: AutoClickerState, config_name: str) -> tuple[bool, BossProfile | None]:
    """Erkennt welcher Boss in der Scan-Region ist.

    Returns:
        (found, boss_profile) - True + BossProfile wenn Boss erkannt, sonst (False, None).
    """
    if config_name not in state.boss_scans:
        print(err(f"Boss-Scan '{config_name}' nicht gefunden!"))
        return False, None

    config = state.boss_scans[config_name]
    if not config.bosses:
        print(err(f"Boss-Scan '{config_name}' hat keine Bosse definiert!"))
        return False, None

    debug = state.config.debug_detection
    tolerance = config.color_tolerance

    # Screenshot der Boss-Region
    img = take_screenshot(config.scan_region)
    if img is None:
        if debug:
            print(dbg("Boss-Scan: Screenshot fehlgeschlagen!"))
        return False, None

    if debug:
        r = config.scan_region
        tags = []
        if config.use_llm and state.config.llm_enabled:
            tags.append("LLM")
        if config.use_ocr and state.config.ocr_enabled:
            tags.append("OCR")
        tag_str = f" [{'+'.join(tags)}]" if tags else ""
        print(dbg(f"Boss-Scan '{config_name}': Region ({r[0]},{r[1]})-({r[2]},{r[3]}), {len(config.bosses)} Bosse{tag_str}"))

    llm_active = config.use_llm and state.config.llm_enabled
    ocr_active = config.use_ocr and state.config.ocr_enabled

    # OCR als primäre Erkennung (wenn nicht Fallback-Modus)
    if ocr_active and not config.ocr_fallback:
        ocr_result = _execute_ocr_boss_detection(state, config, img, debug)
        if ocr_result is not None:
            return True, ocr_result

    # LLM als primäre Erkennung (wenn nicht Fallback-Modus)
    if llm_active and not config.llm_fallback:
        llm_result = _execute_llm_boss_detection(state, config, img, debug)
        if llm_result is not None:
            return True, llm_result

    # Bosse der Reihe nach prüfen (Reihenfolge = Priorität)
    for boss in config.bosses:
        if _check_profile_match(boss, img, tolerance, state, debug, "ERKANNT!"):
            return True, boss

    # 5. OCR als Fallback
    if ocr_active and config.ocr_fallback:
        ocr_result = _execute_ocr_boss_detection(state, config, img, debug)
        if ocr_result is not None:
            return True, ocr_result

    # 6. LLM Vision als Fallback (nur im Fallback-Modus - sonst lief es bereits oben als primär)
    if llm_active and config.llm_fallback:
        llm_result = _execute_llm_boss_detection(state, config, img, debug)
        if llm_result is not None:
            return True, llm_result

    if debug:
        print(dbg("  → Kein Boss erkannt"))
    return False, None


def _execute_ocr_boss_detection(state: AutoClickerState, config: BossScanConfig,
                                 img, debug: bool) -> BossProfile | None:
    """Versucht einen Boss per OCR-Texterkennung zu erkennen.

    Returns:
        BossProfile wenn Boss erkannt, sonst None.
    """
    try:
        from .ocr import detect_boss_name, is_available
    except ImportError:
        if debug:
            print(dbg("  → OCR: Import fehlgeschlagen"))
        return None

    if not is_available():
        if debug:
            print(dbg("  → OCR: kein Backend verfügbar"))
        return None

    boss_names = [boss.name for boss in config.bosses]
    languages = [l.strip() for l in state.config.ocr_languages.split(",")]

    if debug:
        print(dbg(f"  → OCR-Erkennung ({state.config.ocr_backend or 'Auto'})..."))

    success, matched_name, raw_text, duration = detect_boss_name(
        img=img,
        boss_names=boss_names,
        backend=state.config.ocr_backend,
        languages=languages,
        min_confidence=state.config.ocr_min_confidence,
    )

    if debug:
        if raw_text:
            print(dbg(f"  → OCR-Text: '{raw_text}' ({duration:.0f}ms)"))
        else:
            print(dbg(f"  → OCR: kein Text erkannt ({duration:.0f}ms)"))

    if not success or matched_name is None:
        return None

    for boss in config.bosses:
        if boss.name == matched_name:
            if debug:
                print(dbg(f"  → OCR: {boss.name} ERKANNT!"))
            return boss

    return None


def _execute_llm_boss_detection(state: AutoClickerState, config: BossScanConfig,
                                 img, debug: bool) -> BossProfile | None:
    """Versucht einen Boss per LLM Vision zu erkennen.

    Returns:
        BossProfile wenn Boss erkannt, sonst None.
    """
    try:
        from .llm_vision import analyze_image, match_boss_name
    except ImportError:
        if debug:
            print(dbg("  → LLM: Import fehlgeschlagen"))
        return None

    from .persistence import save_boss_scan

    boss_names = [boss.name for boss in config.bosses]

    if debug:
        print(dbg(f"  → LLM-Erkennung: {state.config.llm_provider} ({state.config.llm_model or 'Standard'})..."))

    success, response, duration = analyze_image(
        img=img,
        provider=state.config.llm_provider,
        endpoint=state.config.llm_endpoint,
        model=state.config.llm_model,
        prompt=state.config.llm_boss_prompt,
        boss_names=boss_names,
        timeout=state.config.llm_timeout,
    )

    if not success:
        if debug:
            print(dbg(f"  → LLM-Fehler: {response} ({duration:.0f}ms)"))
        return None

    if debug:
        print(dbg(f"  → LLM-Antwort: '{response}' ({duration:.0f}ms)"))

    # Antwort einem Boss zuordnen
    matched_name, is_new = match_boss_name(response, boss_names)

    if matched_name is None:
        if debug:
            print(dbg("  → LLM: kein Boss erkannt"))
        return None

    if not is_new:
        # Bekannter Boss
        for boss in config.bosses:
            if boss.name == matched_name:
                if debug:
                    print(dbg(f"  → LLM: {boss.name} ERKANNT!"))
                return boss

    # Neuer Boss - automatisch speichern!
    print(col(f"[LLM] Neuer Boss entdeckt: '{matched_name}' - wird gespeichert!", "green"))
    new_boss = BossProfile(
        name=matched_name,
        action=BOSS_ACTION_SKIP,  # Erstmal keine Aktion bis Benutzer eine zuweist
    )

    # Persistieren (Modifikation der Liste unter Lock, da andere Threads sie lesen)
    with state.lock:
        config.bosses.append(new_boss)
        state.boss_scans[config.name] = config
    save_boss_scan(config)

    if debug:
        print(dbg(f"  → LLM: Neuer Boss '{matched_name}' gespeichert (Aktion: skip)"))
    return new_boss


def _execute_boss_action(state: AutoClickerState, boss: BossProfile,
                         step: SequenceStep, step_num: int, total_steps: int,
                         phase: str, debug: bool) -> bool:
    """Führt die einem Boss zugeordnete Aktion aus."""
    _c = _phase_color(phase)

    if boss.action_delay > 0:
        if debug:
            print(dbg(f"Boss-Aktion Delay: {boss.action_delay}s"))
        if state.stop_event.wait(boss.action_delay):
            return False

    if boss.action == BOSS_ACTION_SCAN:
        if not boss.action_scan:
            print(err(f"Boss '{boss.name}': Kein Item-Scan definiert!"))
            return True
        _step_status(debug, phase, step_num, total_steps,
                     f"Boss '{boss.name}' → Scan '{boss.action_scan}'",
                     f"Boss '{boss.name}' → Starte Scan '{boss.action_scan}' ({boss.action_scan_mode})")
        scan_results = execute_item_scan(state, boss.action_scan, boss.action_scan_mode)
        if scan_results:
            for pos, item, priority in scan_results:
                if state.stop_event.is_set():
                    return False
                if not _click_scan_result(state, pos, item, priority, debug):
                    return False
            if debug:
                print(dbg(f"Boss-Scan fertig: {len(scan_results)} Item(s) geklickt"))
        else:
            if debug:
                print(dbg("Boss-Scan: kein Item gefunden"))

    elif boss.action == BOSS_ACTION_CLICK:
        _step_status(debug, phase, step_num, total_steps,
                     f"Boss '{boss.name}' → Klick ({boss.action_x},{boss.action_y})")
        if not safe_click(state, boss.action_x, boss.action_y, label=f"boss:{boss.name}"):
            return False
        with state.lock:
            state.total_clicks += 1

    elif boss.action == BOSS_ACTION_KEY:
        _step_status(debug, phase, step_num, total_steps,
                     f"Boss '{boss.name}' → Taste '{boss.action_key}'")
        if boss.action_key:
            if safe_key(state, boss.action_key, label=f"boss:{boss.name}"):
                with state.lock:
                    state.key_presses += 1

    elif boss.action == BOSS_ACTION_SKIP:
        if debug:
            print(dbg(f"Boss '{boss.name}' → Schritt überspringen"))

    elif boss.action == BOSS_ACTION_SKIP_CYCLE:
        _step_status(debug, phase, step_num, total_steps,
                     f"Boss '{boss.name}' → Zyklus überspringen")
        state.skip_cycle_event.set()
        return False

    elif boss.action == BOSS_ACTION_RESTART:
        _step_status(debug, phase, step_num, total_steps,
                     f"Boss '{boss.name}' → Neustart",
                     f"Boss '{boss.name}' → Sequenz neustarten")
        state.restart_event.set()
        return False

    return True


def _execute_boss_scan_step(state: AutoClickerState, step: SequenceStep,
                            step_num: int, total_steps: int, phase: str) -> bool:
    """Führt einen Boss-Scan Schritt aus."""
    debug = state.config.debug_mode

    _step_status(debug, phase, step_num, total_steps, f"Boss-Scan '{step.boss_scan}'...")
    found, boss = execute_boss_scan(state, step.boss_scan)

    if found and boss:
        _step_status(debug, phase, step_num, total_steps,
                     f"Boss: {boss.name}", f"Boss erkannt: {boss.name}")
        return _execute_boss_action(state, boss, step, step_num, total_steps, phase, debug)
    else:
        # Kein Boss erkannt → Else-Config oder Default-Aktion
        if step.else_config:
            if debug:
                print(dbg("Kein Boss erkannt → else-Aktion"))
            return execute_else_action(state, step, phase, step_num, total_steps)

        # Default-Aktion aus der BossScanConfig
        config = state.boss_scans.get(step.boss_scan)
        if config and config.default_action != BOSS_ACTION_SKIP:
            if config.default_action == BOSS_ACTION_SKIP_CYCLE:
                _step_status(debug, phase, step_num, total_steps,
                             "Kein Boss → Zyklus überspringen",
                             "Kein Boss erkannt → Zyklus überspringen (Default)")
                state.skip_cycle_event.set()
                return False
            elif config.default_action == BOSS_ACTION_RESTART:
                _step_status(debug, phase, step_num, total_steps,
                             "Kein Boss → Neustart",
                             "Kein Boss erkannt → Neustart (Default)")
                state.restart_event.set()
                return False
            elif config.default_action == BOSS_ACTION_SCAN and config.default_scan:
                if debug:
                    print(dbg(f"Kein Boss erkannt → Default-Scan '{config.default_scan}'"))
                scan_results = execute_item_scan(state, config.default_scan)
                if scan_results:
                    for pos, item, priority in scan_results:
                        if state.stop_event.is_set():
                            return False
                        if not _click_scan_result(state, pos, item, priority, debug):
                            return False

        _step_status(debug, phase, step_num, total_steps,
                     "Kein Boss erkannt", "Kein Boss erkannt → übersprungen")

    return True


def _execute_boss_watcher_step(state: AutoClickerState, step: SequenceStep,
                                step_num: int, total_steps: int, phase: str) -> bool:
    """Boss-Watcher: Wartet in einer Schleife bis ein Boss erkannt wird, dann Aktion.

    Der Watcher prüft periodisch die Boss-Region (Intervall aus config.llm_watcher_interval)
    und führt die dem Boss zugeordnete Aktion aus, sobald einer erkannt wird.
    """
    debug = state.config.debug_mode
    _c = _phase_color(phase)
    watcher_name = step.boss_watcher
    interval = state.config.llm_watcher_interval
    max_scans = state.config.llm_watcher_max_scans
    timeout = state.config.llm_watcher_timeout

    if watcher_name not in state.boss_scans:
        print(err(f"Boss-Watcher '{watcher_name}' nicht gefunden!"))
        return True

    limits = []
    if max_scans > 0:
        limits.append(f"max {max_scans} Scans")
    if timeout > 0:
        limits.append(f"Timeout {timeout:.0f}s")
    limit_str = f", {', '.join(limits)}" if limits else ""

    _step_status(debug, phase, step_num, total_steps,
                 f"Boss-Watcher '{watcher_name}' - warte auf Boss...",
                 f"Boss-Watcher '{watcher_name}' gestartet (Intervall: {interval}s{limit_str})")

    scan_count = 0
    start_time = time.time()
    while not state.stop_event.is_set():
        # Pause respektieren
        if state.pause_event.is_set():
            while state.pause_event.is_set() and not state.stop_event.is_set():
                state.stop_event.wait(0.2)
            if state.stop_event.is_set():
                return False

        # Skip prüfen
        if state.skip_event.is_set():
            state.skip_event.clear()
            _step_status(debug, phase, step_num, total_steps,
                         "Boss-Watcher: übersprungen", "Boss-Watcher: SKIP!")
            return True

        # Boss-Scan durchführen
        scan_count += 1
        found, boss = execute_boss_scan(state, watcher_name)

        if found and boss:
            _step_status(debug, phase, step_num, total_steps,
                         f"Boss erkannt: {boss.name}!",
                         f"Boss-Watcher: {boss.name} ERKANNT! (nach {scan_count} Scan(s))")
            return _execute_boss_action(state, boss, step, step_num, total_steps, phase, debug)

        # Limits prüfen
        elapsed = time.time() - start_time
        if max_scans > 0 and scan_count >= max_scans:
            _step_status(debug, phase, step_num, total_steps,
                         f"Boss-Watcher: max. Scans ({max_scans}) erreicht",
                         f"Boss-Watcher: max. Scans ({max_scans}) erreicht - Abbruch")
            return True
        if timeout > 0 and elapsed >= timeout:
            _step_status(debug, phase, step_num, total_steps,
                         f"Boss-Watcher: Timeout ({timeout:.0f}s) erreicht",
                         f"Boss-Watcher: Timeout ({timeout:.0f}s) erreicht - Abbruch")
            return True

        # Status anzeigen (nur ohne debug, da _step_status im debug eine neue Zeile ausgibt)
        if not debug:
            status_parts = [f"Scan #{scan_count}"]
            if max_scans > 0:
                status_parts.append(f"von {max_scans}")
            if timeout > 0:
                status_parts.append(f"{elapsed:.0f}/{timeout:.0f}s")
            _step_status(False, phase, step_num, total_steps,
                         f"Boss-Watcher: kein Boss... ({', '.join(status_parts)})")

        # Warten vor nächstem Scan
        if state.stop_event.wait(interval):
            return False

    return False


def _execute_key_press_step(state: AutoClickerState, step: SequenceStep,
                            step_num: int, total_steps: int, phase: str) -> bool:
    """Führt einen Tastendruck-Schritt aus."""
    debug = state.config.debug_mode
    actual_delay = step.get_actual_delay()
    if actual_delay > 0:
        if not wait_with_pause_skip(state, actual_delay, phase, step_num, total_steps,
                                    f"Taste '{step.key_press}' in"):
            return False

    if state.stop_event.is_set():
        return False

    if safe_key(state, step.key_press, label="step"):
        with state.lock:
            state.key_presses += 1
        _step_status(debug, phase, step_num, total_steps,
                     f"Taste '{step.key_press}'!",
                     f"Taste '{step.key_press}' | Gesamt: {state.key_presses}")

    return True


def _execute_wait_for_color(state: AutoClickerState, step: SequenceStep,
                            step_num: int, total_steps: int, phase: str) -> bool:
    """Wartet auf eine Farbe an einer Pixel-Position."""
    debug = state.config.debug_mode
    wc = step.wait_condition
    actual_delay = step.get_actual_delay()
    if actual_delay > 0:
        if not wait_with_pause_skip(state, actual_delay, phase, step_num, total_steps, "Vor Farbprüfung"):
            return False

    if state.config.debug_show_pixel_position:
        set_cursor_pos(wc.pixel[0], wc.pixel[1])
        time.sleep(state.config.pixel_show_delay)

    if not PILLOW_AVAILABLE:
        print(col(f"\n[FEHLER] Pillow nicht installiert - Farbprüfung nicht möglich!", "red"))
        if step.else_config:
            return execute_else_action(state, step, phase, step_num, total_steps)
        state.stop_event.set()
        return False

    timeout = state.config.pixel_wait_timeout
    start_time = time.time()
    expected_name = get_color_name(wc.color)

    while not state.stop_event.is_set():
        if state.skip_event.is_set():
            state.skip_event.clear()
            _step_status(debug, phase, step_num, total_steps, "SKIP Farbwarten!")
            break

        if not wait_while_paused(state, "Warte auf Farbe..."):
            break

        img = take_screenshot((wc.pixel[0], wc.pixel[1],
                               wc.pixel[0]+1, wc.pixel[1]+1))
        if img:
            current_color = img.getpixel((0, 0))[:3]
            dist = color_distance(current_color, wc.color)
            pixel_tolerance = state.config.pixel_wait_tolerance
            color_matches = dist <= pixel_tolerance
            condition_met = (not color_matches) if wc.until_gone else color_matches

            # Debug-Ausgabe: Zeige erwartete und aktuelle Farbe
            elapsed = time.time() - start_time
            current_name = get_color_name(current_color)

            if condition_met:
                # Erfolg → Consecutive-Timeout-Zähler zurücksetzen
                with state.lock:
                    state.consecutive_timeouts = 0
                msg = "Farbe weg!" if wc.until_gone else "Farbe erkannt!"
                _step_status(debug, phase, step_num, total_steps, msg,
                             f"{msg} | Erwartet: {expected_name} RGB{wc.color} | Aktuell: {current_name} RGB{current_color} Dist={dist:.0f}")
                break

            _step_status(debug, phase, step_num, total_steps,
                         f"Warte auf {expected_name}... ({elapsed:.0f}s)",
                         f"Warte auf {expected_name} RGB{wc.color} ({elapsed:.0f}s) | Aktuell: {current_name} RGB{current_color} Dist={dist:.0f}")

        elapsed = time.time() - start_time
        if timeout > 0 and elapsed >= timeout:
            with state.lock:
                state.timeouts += 1
                state.consecutive_timeouts += 1
                consec = state.consecutive_timeouts
            clear_line()
            max_consec = state.config.pixel_max_consecutive_timeouts
            if max_consec > 0:
                print(col(f"\n[TIMEOUT] Farbe nicht erkannt nach {timeout}s! ({consec}/{max_consec} in Folge)", "red"), end="", flush=True)
            else:
                print(col(f"\n[TIMEOUT] Farbe nicht erkannt nach {timeout}s!", "red"), end="", flush=True)

            # Notbremse: Zu viele aufeinanderfolgende Timeouts
            if max_consec > 0 and consec >= max_consec:
                consec_action = state.config.pixel_consecutive_action
                if consec_action == CONSEC_EXIT:
                    print(col(f"\n[NOTBREMSE] {consec}x Timeout in Folge → Python-Prozess wird beendet!", "red"))
                    print(col("[NOTBREMSE] Programm muss manuell neu gestartet werden.", "red"), flush=True)
                    time.sleep(1)  # Kurz warten damit Ausgabe sichtbar
                    os._exit(1)
                elif consec_action == CONSEC_QUIT:
                    print(col(f"\n[NOTBREMSE] {consec}x Timeout in Folge → Programm wird beendet!", "red"))
                    state.stop_event.set()
                    state.quit_event.set()
                else:
                    print(col(f"\n[NOTBREMSE] {consec}x Timeout in Folge → Stoppe Sequenz!", "red"))
                    state.stop_event.set()
                return False

            if step.else_config:
                print()  # Newline nach TIMEOUT-Zeile (end="" oben)
                return execute_else_action(state, step, phase, step_num, total_steps)
            # Kein else definiert → globale Config-Option auswerten
            timeout_action = state.config.pixel_timeout_action
            if timeout_action == TIMEOUT_SKIP_CYCLE:
                print(col(f" → Zyklus wird übersprungen", "yellow"))
                state.skip_cycle_event.set()
            elif timeout_action == TIMEOUT_RESTART:
                print(col(f" → Sequenz wird neu gestartet (inkl. INIT)", "yellow"))
                state.restart_event.set()
            else:
                print(col(f" → Stoppe.", "red"))
                state.stop_event.set()
            return False

        check_interval = state.config.pixel_check_interval
        if state.stop_event.wait(check_interval):
            return False

    # stop_event oder wait_while_paused-Abbruch → nicht weitermachen
    if state.stop_event.is_set():
        return False
    return True


def _execute_click(state: AutoClickerState, step: SequenceStep,
                   step_num: int, total_steps: int, phase: str) -> bool:
    """Führt den eigentlichen Klick aus."""
    debug = state.config.debug_mode
    clicks = state.config.click_per_point
    for _ in range(clicks):
        if state.stop_event.is_set():
            return False

        if check_failsafe(state):
            print(col("\n[FAILSAFE] Stoppe...", "red"))
            state.stop_event.set()
            return False

        if not safe_click(state, step.x, step.y, label=step.name or "step"):
            return False

        with state.lock:
            state.total_clicks += 1

        name = step.name or "Punkt"
        _step_status(debug, phase, step_num, total_steps,
                     f"Klick! (Gesamt: {state.total_clicks})",
                     f"Klick auf '{name}' ({step.x}, {step.y}) | Gesamt: {state.total_clicks}")

        max_clicks = state.config.click_max_total
        if max_clicks and state.total_clicks >= max_clicks:
            print(f"\n{info(f'Maximum von {max_clicks} Klicks erreicht.')}")
            state.stop_event.set()
            return False

    return True


def _execute_screenshot_step(state: AutoClickerState, step: SequenceStep,
                              step_num: int, total_steps: int, phase: str) -> bool:
    """Führt einen Screenshot-Schritt aus: macht ein Bild und speichert es."""
    if not PILLOW_AVAILABLE:
        print(col(f"[{phase}] Schritt {step_num}/{total_steps} | SCREENSHOT übersprungen (Pillow fehlt)", "yellow"))
        return True

    region = step.screenshot_region  # (x1,y1,x2,y2) oder None
    img = take_screenshot(region)
    if img is None:
        print(col(f"[{phase}] Schritt {step_num}/{total_steps} | SCREENSHOT fehlgeschlagen", "red"))
        return True  # Nicht als Fehler werten, Sequenz läuft weiter

    with state.lock:
        if not state.session_screenshots_dir:
            # Session-Start-Datum verwenden (nicht aktuelles), damit über Mitternacht
            # alle Screenshots einer Session im selben Ordner landen
            session_dt = datetime.fromtimestamp(state.start_time) if state.start_time else datetime.now()
            session_ts = session_dt.strftime("%Y-%m-%d")
            state.session_screenshots_dir = Path(SCREENSHOTS_DIR) / session_ts
        screenshots_dir = state.session_screenshots_dir
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    filename = f"seq_{timestamp}.png"
    path = screenshots_dir / filename
    img.save(path)

    region_str = f"({region[0]},{region[1]})→({region[2]},{region[3]})" if region else "Vollbild"
    print(col(f"[{phase}] Schritt {step_num}/{total_steps} | SCREENSHOT {region_str} → {filename}", _phase_color(phase)))
    return True


def execute_step(state: AutoClickerState, step: SequenceStep, step_num: int,
                 total_steps: int, phase: str) -> bool:
    """Führt einen einzelnen Schritt aus: Erst warten/prüfen, DANN klicken."""
    if check_failsafe(state):
        print(col("\n[FAILSAFE] Maus in Ecke erkannt! Stoppe...", "red"))
        state.stop_event.set()
        return False

    if state.config.debug_mode:  # Kein lokaler Cache nötig - nur 1x pro Step
        print(dbg(f"Step {step_num}: name='{step.name}', x={step.x}, y={step.y}"))

    if step.screenshot_only:
        return _execute_screenshot_step(state, step, step_num, total_steps, phase)

    if step.boss_watcher:
        return _execute_boss_watcher_step(state, step, step_num, total_steps, phase)

    if step.boss_scan:
        return _execute_boss_scan_step(state, step, step_num, total_steps, phase)

    if step.item_scan:
        return _execute_item_scan_step(state, step, step_num, total_steps, phase)

    if step.key_press:
        return _execute_key_press_step(state, step, step_num, total_steps, phase)

    if step.wait_condition:
        if not _execute_wait_for_color(state, step, step_num, total_steps, phase):
            return False
    elif step.delay_before > 0 or step.delay_max:
        actual_delay = step.get_actual_delay()
        action = "Warten" if step.wait_only else "Klicke in"
        if not wait_with_pause_skip(state, actual_delay, phase, step_num, total_steps, action):
            return False

    if state.stop_event.is_set():
        return False

    if step.wait_only:
        debug_active = state.config.debug_mode or state.config.debug_detection
        if debug_active:
            print(col(f"[{phase}] Schritt {step_num}/{total_steps} | Warten beendet (kein Klick)", _phase_color(phase)))
        else:
            clear_line()
            print(col(f"[{phase}] Schritt {step_num}/{total_steps} | Warten beendet (kein Klick)", _phase_color(phase)), end="", flush=True)
        return True

    return _execute_click(state, step, step_num, total_steps, phase)


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


def sequence_worker(state: AutoClickerState) -> None:
    """Worker-Thread, der die Sequenz ausführt."""
    debug = state.config.debug_mode
    print(col("\n[START] Sequenz gestartet.", "green"))

    with state.lock:
        sequence = state.active_sequence
        if not sequence:
            print(err("Keine gültige Sequenz!"))
            state.is_running = False
            return

        has_init = len(sequence.init_steps) > 0
        has_loops = len(sequence.loop_phases) > 0
        has_end = len(sequence.end_steps) > 0
        total_cycles = sequence.total_cycles

        if not has_init and not has_loops:
            print(err("Sequenz ist leer!"))
            state.is_running = False
            return

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

    # Session-Log starten (wenn aktiviert)
    from .session_log import start_session_log
    state.session_log = start_session_log(state)
    if state.session_log is not None:
        print(col(f"[LOG] Session-Log: {state.session_log.path}", "cyan"))
        seq = state.active_sequence
        log_event(state, "session_start", detail=seq.name if seq and hasattr(seq, "name") else "")

    # Zeitgesteuerter Background-Thread (nur wenn nötig)
    scheduled_pending = {}
    scheduled_last_executed = {}
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

    # Äußere Schleife: Ermöglicht kompletten Neustart (inkl. INIT) bei restart_event
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

                if state.skip_cycle_event.is_set():
                    continue
                if state.restart_event.is_set():
                    continue  # → wird oben in der inneren Schleife per break behandelt
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

    # END-Phase
    if has_end and not state.quit_event.is_set():
        print(col("\n[END] Führe End-Sequenz aus...", "cyan"))
        total_end = len(sequence.end_steps)

        for i, step in enumerate(sequence.end_steps):
            if state.quit_event.is_set():
                break
            execute_step(state, step, i + 1, total_end, "END")

        if not state.quit_event.is_set():
            print(col("\n[END] End-Sequenz abgeschlossen.", "cyan"))

    with state.lock:
        state.is_running = False
        duration = time.time() - state.start_time if state.start_time else 0

    # Session-Log schließen
    if state.session_log is not None:
        log_event(state, "session_end",
                  extra=f"clicks={state.total_clicks},items={state.items_found},keys={state.key_presses}")
        state.session_log.close()
        state.session_log = None

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
