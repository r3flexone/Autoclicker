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
)
from ..persistence import SEQUENCE_SCREENSHOTS_DIR as SCREENSHOTS_DIR
from ..session_log import log_event
from ..utils import (
    clear_line, status_line, wait_while_paused, col, err, hint, info, dbg, warn,
)
from ..winapi import check_failsafe
from .actions import (
    safe_click, safe_key, safe_scroll, _step_status, _phase_color, is_verbose_debug,
    wait_with_pause_skip, execute_else_action,
)
from . import status
from .debug import (
    GATE_RUN, GATE_SKIP, GATE_STOP, color_comparison, color_swatch, describe_step,
    is_detail_debug, is_step_mode, print_step_detail, show_point, skip_waits,
    step_gate, step_label,
)
from .boss_detection import (
    execute_boss_scan, _execute_boss_action, _execute_detection_action,
    _should_run_async, _warn_llm_config_inconsistencies, _spawn_boss_async,
)
from .item_scan import (
    execute_item_scan, _click_scan_result, execute_icon_scan, lauffaehige_scan_config,
)


# =============================================================================
# ITEM-SCAN STEP
# =============================================================================

def _execute_item_scan_step(state: AutoClickerState, step: SequenceStep,
                            step_num: int, total_steps: int, phase: str) -> bool:
    """Führt einen Item-Scan Schritt aus."""
    debug = is_verbose_debug(state)
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
    # Dieselbe Prüfung wie im normalen Pfad — inklusive Meldung. Hier stand vorher
    # eine eigene, stumme Abbruchbedingung: sie verlangte Items (ein reiner Lern-Scan
    # tat damit gar nichts) und schwieg bei einem Tippfehler im Scan-Namen.
    with state.lock:
        config = lauffaehige_scan_config(state, step.item_scan)
        if config is None:
            return True
        slots = list(config.slots)
    if state.config.scan_reverse:
        slots = list(reversed(slots))

    # state.clicked_categories wird bewusst NICHT gesondert verwaltet: _click_scan_result
    # traegt jeden Klick selbst ein, _filter_scan_results liest nur. Damit ist der Stand
    # vor Slot N automatisch "Vorher-Stand + alles, was in diesem Step bisher geklickt
    # wurde" — genau die Baseline, die hier vorher aus einem Snapshot plus zwei
    # Merge-Schleifen nachgebaut wurde. Nachgerechnet: identisches Ergebnis, und das
    # Zurueckschreiben des Snapshots verwarf sogar Klicks des Async-Boss-Threads.
    total_clicked = 0
    for slot in slots:
        if state.stop_event.is_set():
            return False

        results = execute_item_scan(state, step.item_scan, mode, slots_override=[slot])
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
    debug = is_verbose_debug(state)

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
    debug = is_verbose_debug(state)

    _step_status(debug, phase, step_num, total_steps, f"Icon-Scan '{step.icon_scan}'...")
    found = execute_icon_scan(state, step.icon_scan)

    if found:
        with state.lock:
            config = state.icon_scans.get(step.icon_scan)
        if config is None:
            return True
        _step_status(debug, phase, step_num, total_steps,
                     f"Icon '{step.icon_scan}' erkannt")
        return _execute_detection_action(
            state, subject=f"Icon '{config.name}'", action=config.action,
            label=f"icon:{config.name}", step_num=step_num, total_steps=total_steps,
            phase=phase, debug=debug,
            x=config.action_x, y=config.action_y, key=config.action_key,
            delay=config.action_delay,
        )

    # Icon nicht erkannt → else-Config oder einfach weiter
    if step.else_config:
        if debug:
            print(dbg("Icon nicht erkannt → else-Aktion"))
        return execute_else_action(state, step, phase, step_num, total_steps)

    _step_status(debug, phase, step_num, total_steps,
                 f"Icon '{step.icon_scan}' nicht erkannt",
                 f"Icon '{step.icon_scan}' nicht erkannt → übersprungen")
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
    debug = is_verbose_debug(state)

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
        # Ein wartender Lauf ist kein toter Lauf — siehe status.lebenszeichen().
        status.lebenszeichen(state)

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

def _fuehre_taste_aus(state: AutoClickerState, step: SequenceStep,
                      step_num: int, total_steps: int, phase: str) -> bool:
    """Drückt die Taste. Gewartet (Zeit oder Farb-Bedingung) hat execute_step bereits."""
    debug = is_verbose_debug(state)
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

def _fuehre_scroll_aus(state: AutoClickerState, step: SequenceStep,
                       step_num: int, total_steps: int, phase: str) -> bool:
    """Dreht das Mausrad. Gewartet (Zeit oder Farb-Bedingung) hat execute_step bereits."""
    debug = is_verbose_debug(state)
    richtung = "hoch" if step.scroll > 0 else "runter"
    label = step.name or f"Scroll {richtung}"
    _step_status(debug, phase, step_num, total_steps,
                 f"Scroll {richtung} x{abs(step.scroll)}",
                 f"Scroll {richtung} x{abs(step.scroll)} an ({step.x}, {step.y})")
    if not safe_scroll(state, step.scroll, step.x, step.y, label):
        return False
    with state.lock:
        state.total_clicks += 1
    return True


def _execute_wait_for_color(state: AutoClickerState, step: SequenceStep,
                            step_num: int, total_steps: int, phase: str) -> str:
    """Wartet auf eine Farbe an einer Pixel-Position.

    Gibt GATE_RUN / GATE_SKIP / GATE_STOP zurück:
      GATE_RUN  = Bedingung erfüllt → der Schritt darf seinen Klick ausführen
      GATE_SKIP = Schritt ist erledigt (else-Aktion lief / übersprungen) → nächster Schritt
      GATE_STOP = Sequenz abbrechen (Stop, Notbremse, restart/skip_cycle)

    Die Unterscheidung SKIP vs. STOP ist der Kern: mit einem bool klickte der Schritt
    nach 'else skip'/'else <Punkt>'/'else key' zusätzlich noch sein eigenes Ziel, und
    ein nicht erfüllter checkcolor-Schritt riss den Rest der Phase mit ab.
    """
    debug = is_verbose_debug(state)
    wc = step.wait_condition
    actual_delay = 0 if skip_waits(state) else step.get_actual_delay()
    if actual_delay > 0:
        if not wait_with_pause_skip(state, actual_delay, phase, step_num, total_steps, "Vor Farbprüfung"):
            return False

    # Zeiger auf den Prüf-Pixel. Detail-Stufe und manueller Modus haben ihn schon
    # dorthin gesetzt - ein zweiter Sprung wäre nur eine weitere Wartezeit.
    if (state.config.debug_show_pixel_position
            and not is_step_mode(state) and not is_detail_debug(state)):
        show_point(state, wc.pixel[0], wc.pixel[1], "Prüf-Pixel")

    if not PILLOW_AVAILABLE:
        print(col("\n[FEHLER] Pillow nicht installiert - Farbprüfung nicht möglich!", "red"))
        if step.else_config:
            return _gate_nach_else(state, step, phase, step_num, total_steps)
        state.stop_event.set()
        return GATE_STOP

    # check_only: einmal prüfen statt warten. Passt die Farbe nicht, greift sofort
    # else_config (Standard skip) - kein Blockieren bis zum Timeout.
    if getattr(wc, "check_only", False):
        return _check_color_once(state, step, step_num, total_steps, phase)

    timeout = state.config.pixel_wait_timeout
    start_time = time.time()
    expected_name = get_color_name(wc.color)
    if debug:
        print(dbg(f"Farbprüfung an {wc.pixel}: {color_swatch(wc.color)}"))
    # Verb je nach Trigger-Richtung: bis Farbe DA (auf) vs. bis Farbe WEG (bis ... weg ist)
    wait_verb = "bis weg:" if wc.until_gone else "auf"

    while not state.stop_event.is_set():
        # Ein wartender Lauf ist kein toter Lauf — siehe status.lebenszeichen().
        status.lebenszeichen(state)

        if state.skip_event.is_set():
            state.skip_event.clear()
            # SKIP überspringt das WARTEN, nicht den Schritt — der Klick folgt.
            _step_status(debug, phase, step_num, total_steps, "SKIP Farbwarten!")
            return GATE_RUN

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

            if condition_met:
                with state.lock:
                    state.consecutive_timeouts = 0
                msg = "Farbe weg!" if wc.until_gone else "Farbe erkannt!"
                _step_status(debug, phase, step_num, total_steps, msg,
                             f"{msg} | " + color_comparison(wc.color, current_color, dist, pixel_tolerance))
                return GATE_RUN

            _step_status(debug, phase, step_num, total_steps,
                         f"Warte {wait_verb} {expected_name}... ({elapsed:.0f}s)",
                         f"Warte {wait_verb} ({elapsed:.0f}s) | "
                         + color_comparison(wc.color, current_color, dist, pixel_tolerance))

        elapsed = time.time() - start_time
        if timeout > 0 and elapsed >= timeout:
            return _handle_color_wait_timeout(state, step, phase, step_num, total_steps, timeout)

        check_interval = state.config.pixel_check_interval
        if state.stop_event.wait(check_interval):
            return GATE_STOP

    return GATE_STOP


def _gate_nach_else(state: AutoClickerState, step: SequenceStep, phase: str,
                    step_num: int, total_steps: int) -> str:
    """Führt die else-Aktion aus und übersetzt ihr Ergebnis in ein Gate.

    else ist laut Hilfe ein *stattdessen*: skip/Klick/Taste erledigen den Schritt,
    sein eigener Klick entfällt (GATE_SKIP). restart/skip_cycle brechen ab (GATE_STOP).
    """
    if execute_else_action(state, step, phase, step_num, total_steps):
        return GATE_SKIP
    return GATE_STOP


def _check_color_once(state: AutoClickerState, step: SequenceStep,
                      step_num: int, total_steps: int, phase: str) -> str:
    """Einmalige Farbprüfung (WaitCondition.check_only).

    Trifft sie zu, darf der Schritt klicken (GATE_RUN). Trifft sie nicht zu, entscheidet
    else_config - ohne else_config wird nur DIESER Schritt übersprungen (GATE_SKIP),
    die Phase läuft weiter.
    """
    debug = is_verbose_debug(state)
    wc = step.wait_condition
    tol = state.config.pixel_wait_tolerance

    img = take_screenshot((wc.pixel[0], wc.pixel[1], wc.pixel[0] + 1, wc.pixel[1] + 1))
    if img is None:
        print(col("\n[FEHLER] Screenshot für Farbprüfung fehlgeschlagen!", "red"))
        return GATE_STOP

    current = img.getpixel((0, 0))[:3]
    dist = color_distance(current, wc.color)
    passt = dist <= tol
    if wc.until_gone:
        passt = not passt

    vergleich = color_comparison(wc.color, current, dist, tol)
    if passt:
        _step_status(debug, phase, step_num, total_steps, "Farbe passt",
                     f"Farbprüfung erfüllt | {vergleich}")
        return GATE_RUN

    _step_status(debug, phase, step_num, total_steps, "Farbe passt nicht - übersprungen",
                 f"Farbprüfung NICHT erfüllt | {vergleich}")
    if step.else_config is not None:
        return _gate_nach_else(state, step, phase, step_num, total_steps)
    return GATE_SKIP


def _handle_color_wait_timeout(state: AutoClickerState, step: SequenceStep, phase: str,
                                step_num: int, total_steps: int, timeout: float) -> str:
    """Reagiert auf einen Pixel-Wait-Timeout: Notbremse → else_config → globale Timeout-Aktion.

    Gibt GATE_SKIP zurück, wenn die else-Aktion den Schritt erledigt hat (Sequenz läuft
    weiter), sonst GATE_STOP. GATE_RUN kommt hier nie vor: nach einem Timeout ist die
    Farb-Bedingung nicht erfüllt, der eigene Klick des Schritts also nicht gerechtfertigt.
    """
    with state.lock:
        state.timeouts += 1
        state.consecutive_timeouts += 1
        consec = state.consecutive_timeouts
    max_consec = state.config.pixel_max_consecutive_timeouts
    # Meldung an Trigger-Richtung anpassen: bei until_gone wartet der Schritt
    # darauf dass die Farbe VERSCHWINDET — "nicht erkannt" wäre dann irreführend.
    wc = step.wait_condition
    reason = "Farbe nicht verschwunden" if (wc and wc.until_gone) else "Farbe nicht erkannt"
    # Das diagnostisch wertvollste Ereignis ueberhaupt: WELCHER Schritt haengt.
    # Ohne diese Zeile stand im Log nur die Klick-Folge, und die Luecke dazwischen
    # musste man aus den Zeitstempeln erraten.
    log_event(state, "timeout", detail=step.name or f"{phase}[{step_num}]",
              x=wc.pixel[0] if wc else 0, y=wc.pixel[1] if wc else 0,
              extra=f"nach={timeout}s,in_folge={consec}")
    if max_consec > 0:
        status_line(col(f"\n[TIMEOUT] {reason} nach {timeout}s! ({consec}/{max_consec} in Folge)", "red"))
    else:
        status_line(col(f"\n[TIMEOUT] {reason} nach {timeout}s!", "red"))

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
        return GATE_STOP

    if step.else_config:
        print()  # Newline nach TIMEOUT-Zeile (end="" oben)
        return _gate_nach_else(state, step, phase, step_num, total_steps)

    # Kein else definiert → globale Config-Option auswerten
    timeout_action = state.config.pixel_timeout_action
    if timeout_action == TIMEOUT_SKIP_CYCLE:
        print(col(" → Zyklus wird übersprungen", "yellow"))
        state.skip_cycle_event.set()
    elif timeout_action == TIMEOUT_RESTART:
        print(col(" → Sequenz wird neu gestartet (inkl. INIT)", "yellow"))
        state.restart_event.set()
    else:
        print(col(" → Stoppe.", "red"))
        state.stop_event.set()
    return GATE_STOP


# =============================================================================
# KLICK STEP
# =============================================================================

def _execute_click(state: AutoClickerState, step: SequenceStep,
                   step_num: int, total_steps: int, phase: str) -> bool:
    """Führt den eigentlichen Klick aus."""
    debug = is_verbose_debug(state)
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

        # Inkrement + Max-Check atomar unter Lock (check-then-act ohne Lock wäre
        # eine Race-Condition zwischen Worker und Async-LLM-Thread).
        with state.lock:
            state.total_clicks += 1
            total_now = state.total_clicks
            max_clicks = state.config.click_max_total
            limit_reached = bool(max_clicks) and total_now >= max_clicks

        name = step.name or "Punkt"
        # In Detail-Stufe steht Name und Ziel schon in der Kopfzeile darüber - die
        # Ergebnis-Zeile trägt dann nur noch bei, DASS geklickt wurde, und den Zähler.
        if is_detail_debug(state):
            ergebnis = f"geklickt | Gesamt: {total_now}"
        else:
            ergebnis = f"Klick auf '{name}' ({step.x}, {step.y}) | Gesamt: {total_now}"
        _step_status(debug, phase, step_num, total_steps,
                     f"Klick '{name}' ({step.x},{step.y}) | Gesamt: {total_now}",
                     ergebnis)

        if limit_reached:
            print(f"\n{info(f'Maximum von {max_clicks} Klicks erreicht.')}")
            state.stop_event.set()
            return False

    return True


# =============================================================================
# SCREENSHOT STEP
# =============================================================================

def _execute_screenshot_step(state: AutoClickerState, step: SequenceStep,
                              step_num: int, total_steps: int, phase: str) -> bool:
    """Führt einen Screenshot-Schritt aus: macht ein Bild und speichert es.

    Die drei Meldungen bleiben bewusst **stehen** (eigene Zeile statt Status-Zeile):
    welcher Dateiname geschrieben wurde, will man später noch lesen können. Sie
    räumen die laufende Status-Zeile aber vorher ab — ohne das schriebe die neue Zeile
    nur über deren Anfang und liesse den Rest daneben stehen.
    """
    if not PILLOW_AVAILABLE:
        clear_line()
        print(col(f"[{phase}] Schritt {step_num}/{total_steps} | SCREENSHOT übersprungen (Pillow fehlt)", "yellow"))
        return True

    region = step.screenshot_region  # (x1,y1,x2,y2) oder None
    img = take_screenshot(region)
    if img is None:
        clear_line()
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
    clear_line()
    print(col(f"[{phase}] Schritt {step_num}/{total_steps} | SCREENSHOT {region_str} → {filename}", _phase_color(phase)))
    return True


# =============================================================================
# TOP-LEVEL STEP-DISPATCHER
# =============================================================================

# Scan-Felder in derselben Reihenfolge, in der der Dispatcher sie abfragt, mit
# der Beschriftung fuer die Meldung. Eine neue Scan-Art gehoert hier ebenfalls
# hinein — sonst faellt sie ohne Konfiguration wieder bis zum Klick durch.
_SCAN_FELDER = (
    ("boss_watcher", "BOSS-WATCHER"),
    ("boss_scan", "BOSS-SCAN"),
    ("icon_scan", "ICON-SCAN"),
    ("item_scan", "ITEM-SCAN"),
)


def _scan_ohne_namen(step: SequenceStep) -> "str | None":
    """Beschriftung der Scan-Art, wenn deren Name gesetzt aber leer ist."""
    for feld, beschriftung in _SCAN_FELDER:
        wert = getattr(step, feld, None)
        if wert is not None and not str(wert).strip():
            return beschriftung
    return None


def execute_step(state: AutoClickerState, step: SequenceStep, step_num: int,
                 total_steps: int, phase: str) -> bool:
    """Führt einen einzelnen Schritt aus: Erst warten/prüfen, DANN klicken."""
    if check_failsafe(state):
        print(col("\n[FAILSAFE] Maus in Ecke erkannt! Stoppe...", "red"))
        state.stop_event.set()
        return False

    # Laufstatus für das Sequenz-Studio. Gedrosselt (kein `sofort`): die Phasen-
    # und Zykluswechsel im Worker schreiben immer, ein einzelner Block darf
    # ausgelassen werden. `describe_step` statt eines Typ-Kürzels, weil es hier
    # schon steht und mehr sagt — "Item-Scan 'Beutel' (all)" gegen "ITEM-SCAN".
    status.schreibe(state, {"block": step_num, "bloecke": total_steps,
                            "block_label": describe_step(step),
                            "block_titel": step.name or "",
                            "block_seit": time.time()})

    # Ankündigung nur in Stufe 1 allein - die Detail-Kopfzeile darunter sagt dasselbe,
    # nur vollständiger. Beides wäre die Doppelung, die vorher jeden Schritt aufblähte.
    if is_verbose_debug(state) and not is_detail_debug(state):
        print(dbg(f"Step {step_num}: {step_label(step)}, x={step.x}, y={step.y}"))

    # Stufe 2: ausschreiben was kommt + Zeiger hinsetzen (blockiert nicht).
    print_step_detail(state, step, phase, step_num, total_steps)

    # Manueller Modus: Ziel zeigen und auf Bestätigung warten. GATE_SKIP behandelt den
    # Schritt wie erledigt, damit die Sequenz normal weiterläuft.
    gate = step_gate(state, step, phase, step_num, total_steps)
    if gate == GATE_SKIP:
        return True
    if gate != GATE_RUN:
        return False

    if step.screenshot_only:
        return _execute_screenshot_step(state, step, step_num, total_steps, phase)

    # Ein Scan-Feld, das gesetzt aber leer ist ("" statt None), meint einen Block,
    # dessen Konfiguration noch fehlt — im Editor angelegt, um die Stelle im Ablauf
    # zu markieren. Alle Scan-Zweige unten fragen per Truthiness ab, ein "" faellt
    # also durch bis zum Klick: der Schritt wuerde auf seine Koordinate klicken, und
    # die ist bei einem Scan-Block (0, 0) — die Bildschirmecke. Deshalb hier raus,
    # mit Ansage. Dieselbe Haltung wie bei einer toten `point_id`: ein Schritt, der
    # stehenbleibt, ist besser als einer, der irgendwohin klickt.
    unfertig = _scan_ohne_namen(step)
    if unfertig is not None:
        print(warn(f"[{phase}] Schritt {step_num}/{total_steps} übersprungen: "
                   f"{unfertig} ohne Konfiguration"))
        print(hint("       Im Sequenz-Editor oder -Studio eine Konfiguration "
                   "auswählen (angelegt mit CTRL+ALT+N)."))
        return True

    if step.boss_watcher:
        return _execute_boss_watcher_step(state, step, step_num, total_steps, phase)

    if step.boss_scan:
        return _execute_boss_scan_step(state, step, step_num, total_steps, phase)

    if step.icon_scan:
        return _execute_icon_scan_step(state, step, step_num, total_steps, phase)

    if step.item_scan:
        return _execute_item_scan_step(state, step, step_num, total_steps, phase)

    # Ab hier die Aktions-Schritte: Klick, Taste, Scroll, reines Warten. Sie
    # unterscheiden sich NUR in der Aktion am Ende — gewartet wird davor für alle
    # gleich, an genau einer Stelle. Vorher hatten Taste und Scroll ihre eigene
    # Wartezeit-Behandlung und wurden VOR der Farb-Bedingung abgefertigt: ein
    # Farb-Trigger an einem Tasten- oder Scroll-Schritt wurde dadurch stillschweigend
    # ignoriert (und mit ihm dessen else-Aktion).
    if step.wait_condition:
        farb_gate = _execute_wait_for_color(state, step, step_num, total_steps, phase)
        if farb_gate == GATE_SKIP:
            return True   # else-Aktion lief bzw. Prüfung nicht erfüllt — keine eigene Aktion
        if farb_gate != GATE_RUN:
            return False
    elif not skip_waits(state):
        actual_delay = step.get_actual_delay()
        if actual_delay > 0:
            if not wait_with_pause_skip(state, actual_delay, phase, step_num, total_steps,
                                        _warte_text(step)):
                return False

    if state.stop_event.is_set():
        return False

    if step.wait_only:
        # Reines Warten hat keine Wirkung, die man nachpruefen koennte.
        debug_active = is_verbose_debug(state)
        _step_status(debug_active, phase, step_num, total_steps, "Warten beendet (kein Klick)")
        return True

    if step.key_press:
        aktion = _fuehre_taste_aus
    elif step.scroll:
        aktion = _fuehre_scroll_aus
    else:
        aktion = _execute_click

    return _mit_nachpruefung(state, step, step_num, total_steps, phase, aktion)


# =============================================================================
# NACHPRUEFUNG ("hat die Aktion gewirkt?")
# =============================================================================

def _wirkung_eingetreten(state: AutoClickerState, vc, timeout: float) -> tuple[bool, str]:
    """Wartet bis `timeout`, ob die Nachpruef-Bedingung eintritt.

    Gibt `(erfuellt, beschreibung)` zurueck. Abbruch ueber stop_event wird als
    "nicht erfuellt" gemeldet — der Aufrufer prueft stop_event ohnehin selbst.
    """
    tol = state.config.pixel_wait_tolerance
    intervall = max(0.05, state.config.verify_interval)
    ende = time.time() + max(0.0, timeout)
    letzter = "kein Screenshot"
    while True:
        img = take_screenshot((vc.pixel[0], vc.pixel[1], vc.pixel[0] + 1, vc.pixel[1] + 1))
        if img is not None:
            aktuell = img.getpixel((0, 0))[:3]
            dist = color_distance(aktuell, vc.color)
            passt = dist <= tol
            if vc.until_gone:
                passt = not passt
            letzter = color_comparison(vc.color, aktuell, dist, tol)
            if passt:
                return True, letzter
        if time.time() >= ende or state.stop_event.is_set():
            return False, letzter
        if state.stop_event.wait(intervall):
            return False, letzter


def _mit_nachpruefung(state: AutoClickerState, step: SequenceStep, step_num: int,
                      total_steps: int, phase: str, aktion) -> bool:
    """Fuehrt `aktion` aus und prueft danach, ob sie gewirkt hat.

    Ohne `verify_condition` passiert genau das, was vorher passierte: die Aktion laeuft,
    fertig. Das ist der Normalfall und kostet keinen Screenshot.

    Mit Bedingung wird die Aktion bis zu `verify_retries` mal WIEDERHOLT, bevor
    `else_config` greift. Die Wiederholung ist der eigentliche Gewinn: der haeufigste
    Grund fuer einen wirkungslosen Klick (Lag, Fenster kurz nicht vorn, Popup davor) ist
    voruebergehend, und ein zweiter Klick loest ihn. Vorher lief die Sequenz einfach
    weiter und alles Folgende traf daneben.

    Bleibt die Wirkung auch nach allen Versuchen aus, entscheidet `else_config` —
    dieselbe Mechanik wie bei einer nicht erfuellten Vorbedingung. Ohne else wird der
    Schritt als erledigt behandelt (GATE_SKIP-Bedeutung: weiter, nicht abbrechen); eine
    ausgebliebene Wirkung ist ein Hinweis, kein Grund die Sequenz zu reissen.
    """
    vc = step.verify_condition
    if vc is None:
        return aktion(state, step, step_num, total_steps, phase)

    debug = is_verbose_debug(state)
    versuche = max(0, state.config.verify_retries) + 1
    timeout = state.config.verify_timeout

    for versuch in range(1, versuche + 1):
        if not aktion(state, step, step_num, total_steps, phase):
            return False
        if state.stop_event.is_set():
            return False

        erfuellt, vergleich = _wirkung_eingetreten(state, vc, timeout)
        if erfuellt:
            _step_status(debug, phase, step_num, total_steps, "Wirkung bestaetigt",
                         f"Nachpruefung erfuellt | {vergleich}")
            log_event(state, "verify_ok", detail=step.name or "step",
                      x=vc.pixel[0], y=vc.pixel[1], extra=f"versuch={versuch}")
            return True

        if state.stop_event.is_set():
            return False
        log_event(state, "verify_miss", detail=step.name or "step",
                  x=vc.pixel[0], y=vc.pixel[1],
                  extra=f"versuch={versuch}/{versuche}")
        if versuch < versuche:
            _step_status(debug, phase, step_num, total_steps,
                         f"keine Wirkung - wiederhole ({versuch}/{versuche - 1})",
                         f"Nachpruefung nicht erfuellt | {vergleich} - Wiederholung {versuch}")

    _step_status(debug, phase, step_num, total_steps,
                 "keine Wirkung - aufgegeben",
                 f"Nachpruefung nach {versuche} Versuch(en) nicht erfuellt")
    if step.else_config is not None:
        return _gate_nach_else(state, step, phase, step_num, total_steps) != GATE_STOP
    return True


def _warte_text(step: SequenceStep) -> str:
    """Beschriftung der Wartezeit-Anzeige, passend zur Aktion die danach kommt."""
    if step.key_press:
        return f"Taste '{step.key_press}' in"
    if step.scroll:
        return f"Scroll {'hoch' if step.scroll > 0 else 'runter'} in"
    if step.wait_only:
        return "Warten"
    return "Klicke in"
