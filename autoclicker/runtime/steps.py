"""
Step-Dispatch: alle _execute_*_step-Funktionen plus der Top-Level-Dispatcher
execute_step. Jede Step-Variante (Klick, Key-Press, Wait-Pixel, Item-Scan,
Boss-Scan/Watcher, Wait-only, Screenshot) hat hier ihren Handler.

execute_step routet einen SequenceStep zur passenden Handler-Funktion basierend
auf welche optionalen Felder gesetzt sind.
"""

import os
import time
from datetime import datetime
from pathlib import Path

from ..imaging import PILLOW_AVAILABLE, take_screenshot, color_distance, get_color_name
from ..models import (
    AutoClickerState, SequenceStep,
    SCAN_MODE_ALL,
    TIMEOUT_SKIP_CYCLE, TIMEOUT_RESTART,
    CONSEC_EXIT, CONSEC_QUIT,
    BOSS_ACTION_SCAN, BOSS_ACTION_SKIP, BOSS_ACTION_SKIP_CYCLE, BOSS_ACTION_RESTART,
    ICON_ACTION_CLICK, ICON_ACTION_KEY, ICON_ACTION_SKIP,
    ICON_ACTION_SKIP_CYCLE, ICON_ACTION_RESTART,
)
from ..persistence import SEQUENCE_SCREENSHOTS_DIR as SCREENSHOTS_DIR
from ..utils import clear_line, wait_while_paused, col, err, info, dbg
from ..winapi import check_failsafe, set_cursor_pos
from .actions import (
    safe_click, safe_key, _step_status, _phase_color,
    wait_with_pause_skip, execute_else_action,
)
from .boss_detection import (
    execute_boss_scan, _execute_boss_action,
    _should_run_async, _warn_llm_config_inconsistencies, _spawn_boss_async,
)
from .item_scan import execute_item_scan, _click_scan_result, execute_icon_scan


# =============================================================================
# ITEM-SCAN STEP
# =============================================================================

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
    with state.lock:
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

        with state.lock:
            state.clicked_categories = dict(saved_categories)

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
# BOSS-SCAN STEP
# =============================================================================

def _execute_boss_scan_step(state: AutoClickerState, step: SequenceStep,
                            step_num: int, total_steps: int, phase: str) -> bool:
    """Führt einen Boss-Scan Schritt aus."""
    debug = state.config.debug_mode

    _warn_llm_config_inconsistencies(state, step.boss_scan)

    # async lohnt sich nur wenn die Erkennung dieses Scans tatsächlich LLM nutzt —
    # reine Template/Marker-Scans sind schnell und der Sync-Pfad ist einfacher.
    if _should_run_async(state, step.boss_scan):
        _step_status(debug, phase, step_num, total_steps,
                     f"Boss-Scan '{step.boss_scan}' (async)...",
                     f"Boss-Scan '{step.boss_scan}' → Hintergrund-Thread gestartet")
        _spawn_boss_async(state, step, step_num, total_steps, phase)
        return True

    _step_status(debug, phase, step_num, total_steps, f"Boss-Scan '{step.boss_scan}'...")
    found, boss = execute_boss_scan(state, step.boss_scan)

    if found and boss:
        _step_status(debug, phase, step_num, total_steps,
                     f"Boss: {boss.name}", f"Boss erkannt: {boss.name}")
        return _execute_boss_action(state, boss, step, step_num, total_steps, phase, debug)

    # Kein Boss erkannt → Else-Config oder Default-Aktion
    if step.else_config:
        if debug:
            print(dbg("Kein Boss erkannt → else-Aktion"))
        return execute_else_action(state, step, phase, step_num, total_steps)

    # Default-Aktion aus der BossScanConfig
    with state.lock:
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


# =============================================================================
# ICON-SCAN STEP
# =============================================================================

def _execute_icon_scan_step(state: AutoClickerState, step: SequenceStep,
                            step_num: int, total_steps: int, phase: str) -> bool:
    """Führt einen Icon-Scan Schritt aus: Icon erkennen → Aktion, sonst else/weiter."""
    debug = state.config.debug_mode

    _step_status(debug, phase, step_num, total_steps, f"Icon-Scan '{step.icon_scan}'...")
    found = execute_icon_scan(state, step.icon_scan)

    if found:
        with state.lock:
            config = state.icon_scans.get(step.icon_scan)
        if config is None:
            return True
        _step_status(debug, phase, step_num, total_steps,
                     f"Icon '{step.icon_scan}' erkannt")
        return _execute_icon_action(state, config, step_num, total_steps, phase, debug)

    # Icon nicht erkannt → else-Config oder einfach weiter
    if step.else_config:
        if debug:
            print(dbg("Icon nicht erkannt → else-Aktion"))
        return execute_else_action(state, step, phase, step_num, total_steps)

    _step_status(debug, phase, step_num, total_steps,
                 f"Icon '{step.icon_scan}' nicht erkannt",
                 f"Icon '{step.icon_scan}' nicht erkannt → übersprungen")
    return True


def _execute_icon_action(state: AutoClickerState, config, step_num: int,
                         total_steps: int, phase: str, debug: bool) -> bool:
    """Führt die einem erkannten Icon zugeordnete Aktion aus."""
    if config.action_delay > 0:
        if debug:
            print(dbg(f"Icon-Aktion Delay: {config.action_delay}s"))
        if state.stop_event.wait(config.action_delay):
            return False

    if config.action == ICON_ACTION_CLICK:
        _step_status(debug, phase, step_num, total_steps,
                     f"Icon '{config.name}' → Klick ({config.action_x},{config.action_y})")
        if not safe_click(state, config.action_x, config.action_y, label=f"icon:{config.name}"):
            return False
        with state.lock:
            state.total_clicks += 1

    elif config.action == ICON_ACTION_KEY:
        _step_status(debug, phase, step_num, total_steps,
                     f"Icon '{config.name}' → Taste '{config.action_key}'")
        if config.action_key and safe_key(state, config.action_key, label=f"icon:{config.name}"):
            with state.lock:
                state.key_presses += 1

    elif config.action == ICON_ACTION_SKIP:
        if debug:
            print(dbg(f"Icon '{config.name}' → Schritt überspringen"))

    elif config.action == ICON_ACTION_SKIP_CYCLE:
        _step_status(debug, phase, step_num, total_steps,
                     f"Icon '{config.name}' → Zyklus überspringen")
        state.skip_cycle_event.set()
        return False

    elif config.action == ICON_ACTION_RESTART:
        _step_status(debug, phase, step_num, total_steps,
                     f"Icon '{config.name}' → Neustart")
        state.restart_event.set()
        return False

    return True


# =============================================================================
# BOSS-WATCHER STEP
# =============================================================================

def _execute_boss_watcher_step(state: AutoClickerState, step: SequenceStep,
                                step_num: int, total_steps: int, phase: str) -> bool:
    """Boss-Watcher: Wartet in einer Schleife bis ein Boss erkannt wird, dann Aktion.

    Der Watcher prüft periodisch die Boss-Region (Intervall aus config.llm_watcher_interval)
    und führt die dem Boss zugeordnete Aktion aus, sobald einer erkannt wird.
    """
    debug = state.config.debug_mode

    _warn_llm_config_inconsistencies(state, step.boss_watcher)

    if _should_run_async(state, step.boss_watcher):
        _step_status(debug, phase, step_num, total_steps,
                     f"Boss-Watcher '{step.boss_watcher}' (async)...",
                     f"Boss-Watcher '{step.boss_watcher}' → Hintergrund-Thread gestartet")
        _spawn_boss_async(state, step, step_num, total_steps, phase)
        return True

    watcher_name = step.boss_watcher
    interval = state.config.llm_watcher_interval
    max_scans = state.config.llm_watcher_max_scans
    timeout = state.config.llm_watcher_timeout

    with state.lock:
        watcher_known = watcher_name in state.boss_scans
    if not watcher_known:
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
        if not wait_while_paused(state, f"Boss-Watcher '{watcher_name}' pausiert..."):
            return False

        if state.skip_event.is_set():
            state.skip_event.clear()
            _step_status(debug, phase, step_num, total_steps,
                         "Boss-Watcher: übersprungen", "Boss-Watcher: SKIP!")
            return True

        scan_count += 1
        found, boss = execute_boss_scan(state, watcher_name)

        if found and boss:
            _step_status(debug, phase, step_num, total_steps,
                         f"Boss erkannt: {boss.name}!",
                         f"Boss-Watcher: {boss.name} ERKANNT! (nach {scan_count} Scan(s))")
            return _execute_boss_action(state, boss, step, step_num, total_steps, phase, debug)

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

        if state.stop_event.wait(interval):
            return False

    return False


# =============================================================================
# KEY-PRESS STEP
# =============================================================================

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


# =============================================================================
# WAIT-FOR-COLOR STEP
# =============================================================================

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
            color_present = dist <= pixel_tolerance
            # until_gone=True → warte bis Farbe WEG; until_gone=False → warte bis Farbe DA
            condition_met = (not color_present) if wc.until_gone else color_present

            elapsed = time.time() - start_time
            current_name = get_color_name(current_color)

            if condition_met:
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
            if not _handle_color_wait_timeout(state, step, phase, step_num, total_steps, timeout):
                return False
            break

        check_interval = state.config.pixel_check_interval
        if state.stop_event.wait(check_interval):
            return False

    if state.stop_event.is_set():
        return False
    return True


def _handle_color_wait_timeout(state: AutoClickerState, step: SequenceStep, phase: str,
                                step_num: int, total_steps: int, timeout: float) -> bool:
    """Reagiert auf einen Pixel-Wait-Timeout: Notbremse → else_config → globale Timeout-Aktion.

    Returns False wenn Sequenz abbrechen soll, True wenn weitermachen.
    """
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


# =============================================================================
# KLICK STEP
# =============================================================================

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


# =============================================================================
# SCREENSHOT STEP
# =============================================================================

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


# =============================================================================
# TOP-LEVEL STEP-DISPATCHER
# =============================================================================

def execute_step(state: AutoClickerState, step: SequenceStep, step_num: int,
                 total_steps: int, phase: str) -> bool:
    """Führt einen einzelnen Schritt aus: Erst warten/prüfen, DANN klicken."""
    if check_failsafe(state):
        print(col("\n[FAILSAFE] Maus in Ecke erkannt! Stoppe...", "red"))
        state.stop_event.set()
        return False

    if state.config.debug_mode:
        print(dbg(f"Step {step_num}: name='{step.name}', x={step.x}, y={step.y}"))

    if step.screenshot_only:
        return _execute_screenshot_step(state, step, step_num, total_steps, phase)

    if step.boss_watcher:
        return _execute_boss_watcher_step(state, step, step_num, total_steps, phase)

    if step.boss_scan:
        return _execute_boss_scan_step(state, step, step_num, total_steps, phase)

    if step.icon_scan:
        return _execute_icon_scan_step(state, step, step_num, total_steps, phase)

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
        _step_status(debug_active, phase, step_num, total_steps, "Warten beendet (kein Klick)")
        return True

    return _execute_click(state, step, step_num, total_steps, phase)
