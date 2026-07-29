"""
Boss-Erkennung und -Aktionen.

Drei Pfade:
  1. Template/Marker (synchron, schnell)
  2. OCR (synchron, langsamer)
  3. LLM Vision (synchron oder async via _boss_async_thread)

execute_boss_scan koordiniert alle drei (Reihenfolge gesteuert über
use_llm/llm_fallback/use_ocr/ocr_fallback in der BossScanConfig).
Neu entdeckte Boss-Namen werden zur User-Bestätigung am Sequenz-Ende
vorgemerkt (_handle_new_boss → _confirm_new_bosses).
"""

import threading
import time
from typing import Optional

from ..imaging import take_screenshot
from ..models import (
    AutoClickerState, SequenceStep, BossScanConfig, BossProfile,
    ELSE_CLICK, ELSE_KEY, SCAN_MODE_ALL,
    BOSS_ACTION_SCAN, BOSS_ACTION_CLICK, BOSS_ACTION_KEY,
    BOSS_ACTION_SKIP, BOSS_ACTION_SKIP_CYCLE, BOSS_ACTION_RESTART,
)
from ..utils import col, err, dbg, warn, wait_while_paused
from ..winapi import check_failsafe
from .actions import safe_click, safe_key, _step_status, is_verbose_debug
from .item_scan import execute_item_scan, _click_scan_result, _check_profile_match

# Mindest-Konfidenz für OCR-Boss-Erkennung. Unterhalb davon wird nichts gespeichert —
# sichert Zuverlässigkeit und verhindert dass Tippfehler/Garbled-Text als neuer Boss landen.
_OCR_MIN_BOSS_CONFIDENCE = 0.8


# =============================================================================
# BOSS-SCAN AUSFÜHRUNG
# =============================================================================

def execute_boss_scan(state: AutoClickerState, config_name: str) -> tuple[bool, BossProfile | None]:
    """Erkennt welcher Boss in der Scan-Region ist.

    Returns:
        (found, boss_profile) - True + BossProfile wenn Boss erkannt, sonst (False, None).
    """
    # Snapshot von config + bosses-Liste unter Lock — der Editor kann während Scans laufen
    with state.lock:
        config = state.boss_scans.get(config_name)
        if config is None:
            print(err(f"Boss-Scan '{config_name}' nicht gefunden!"))
            return False, None
        # Lokale Bosse + globale Bibliothek mergen (lokal hat Vorrang bei gleichem Namen)
        local_names = {b.name for b in config.bosses}
        bosses_snapshot = list(config.bosses) + [
            b for b in state.global_bosses if b.name not in local_names
        ]
        if not bosses_snapshot:
            print(err(f"Boss-Scan '{config_name}' hat keine Bosse definiert (auch keine globalen)!"))
            return False, None
        color_tolerance = config.color_tolerance
        scan_region = config.scan_region
        # Erkennungs-Flags im selben Lock-Snapshot einfrieren — sonst kann ein
        # Editor sie zwischen mehreren frischen Reads toggeln und das LLM läuft
        # doppelt (einmal primär, einmal als Fallback).
        cfg_use_llm = config.use_llm
        cfg_llm_fallback = config.llm_fallback
        cfg_use_ocr = config.use_ocr
        cfg_ocr_fallback = config.ocr_fallback

    debug = state.config.debug_log

    img = take_screenshot(scan_region)
    if img is None:
        if debug:
            print(dbg("Boss-Scan: Screenshot fehlgeschlagen!"))
        return False, None

    llm_active = cfg_use_llm and state.config.llm_enabled
    ocr_active = cfg_use_ocr and state.config.ocr_enabled

    if debug:
        r = scan_region
        tags = []
        if llm_active:
            tags.append("LLM")
        if ocr_active:
            tags.append("OCR")
        tag_str = f" [{'+'.join(tags)}]" if tags else ""
        print(dbg(f"Boss-Scan '{config_name}': Region ({r[0]},{r[1]})-({r[2]},{r[3]}), {len(bosses_snapshot)} Bosse{tag_str}"))

    # OCR als primäre Erkennung (wenn nicht Fallback-Modus)
    if ocr_active and not cfg_ocr_fallback:
        ocr_result = _execute_ocr_boss_detection(state, config, img, debug, bosses_snapshot)
        if ocr_result is not None:
            return True, ocr_result

    # LLM als primäre Erkennung (wenn nicht Fallback-Modus)
    if llm_active and not cfg_llm_fallback:
        llm_result = _execute_llm_boss_detection(state, config, img, debug, bosses_snapshot)
        if llm_result is not None:
            return True, llm_result

    # Bosse der Reihe nach prüfen (Reihenfolge = Priorität)
    for boss in bosses_snapshot:
        if _check_profile_match(boss, img, color_tolerance, state, debug, "ERKANNT!"):
            return True, boss

    # OCR als Fallback
    if ocr_active and cfg_ocr_fallback:
        ocr_result = _execute_ocr_boss_detection(state, config, img, debug, bosses_snapshot)
        if ocr_result is not None:
            return True, ocr_result

    # LLM Vision als Fallback (nur im Fallback-Modus - sonst lief es bereits oben als primär)
    if llm_active and cfg_llm_fallback:
        llm_result = _execute_llm_boss_detection(state, config, img, debug, bosses_snapshot)
        if llm_result is not None:
            return True, llm_result

    if debug:
        print(dbg("  → Kein Boss erkannt"))
    return False, None


# =============================================================================
# NEU ENTDECKTE BOSSE: SPEICHERN + USER-BESTÄTIGUNG
# =============================================================================

def _handle_new_boss(state: AutoClickerState, config: BossScanConfig,
                      name: str, source: str, debug: bool) -> BossProfile | None:
    """Speichert einen neu entdeckten Boss und merkt ihn zur Bestätigung am Sequenz-Ende vor.

    Returns:
        Das neu angelegte BossProfile, oder None wenn der Name bereits bekannt/vorgemerkt ist.
    """
    from ..persistence import save_boss_scan, save_global_bosses

    learn_global = state.config.boss_learn_global

    # Check und Append atomar im selben Lock-Block — sonst kann zwischen Prüfung
    # und Mutation ein paralleler Pfad (Sync-Scan + Async-Watcher) denselben Boss
    # doppelt anhängen (TOCTOU).
    with state.lock:
        existing_names = ({b.name for b in config.bosses}
                          | {b.name for b in state.global_bosses})
        already_pending = any(n == name for _, n, _ in state.pending_new_bosses)
        if name in existing_names or already_pending:
            return None

        new_boss = BossProfile(name=name, action=BOSS_ACTION_SKIP)
        if learn_global:
            state.global_bosses.append(new_boss)
            target = "Bibliothek (global)"
        else:
            config.bosses.append(new_boss)
            state.boss_scans[config.name] = config
            target = f"Scan '{config.name}'"
        state.pending_new_bosses.append((target, name, source))

    print(col(f"[{source}] Neuer Boss entdeckt: '{name}' — gespeichert in {target}", "green"))
    if learn_global:
        save_global_bosses(state)
    else:
        save_boss_scan(config)

    if debug:
        print(dbg(f"  → {source}: Neuer Boss '{name}' gespeichert (Aktion: skip, Bestätigung ausstehend)"))
    return new_boss


def _confirm_new_bosses(state: AutoClickerState) -> None:
    """Informiert über neu entdeckte Boss-Namen dieser Session (nicht-blockierend).

    Unbekannte Bosse werden bereits beim Erkennen automatisch als SKIP gespeichert
    (_handle_new_boss). Früher fragte diese Funktion per safe_input nach Bestätigung —
    das blockierte den Worker, sodass der Stop-Hotkey wirkungslos blieb und die App
    eingefroren wirkte. Jetzt nur noch eine reine Info-Meldung; Korrekturen erfolgen
    im Boss-Editor.
    """
    with state.lock:
        pending = list(state.pending_new_bosses)
        state.pending_new_bosses.clear()

    if not pending:
        return

    print(col("\n" + "=" * 55, "yellow"))
    print(col(f"[NEUE BOSSE] {len(pending)} unbekannte(r) Boss(e) automatisch als SKIP gespeichert "
              f"— im Boss-Editor anpassbar.", "yellow"))
    for i, (target, boss_name, source) in enumerate(pending, 1):
        print(f"  {i}. [{source}] '{boss_name}'  → {target}")
    print(col("=" * 55, "yellow"))


# =============================================================================
# OCR-ERKENNUNG
# =============================================================================

def _execute_ocr_boss_detection(state: AutoClickerState, config: BossScanConfig,
                                 img, debug: bool,
                                 bosses_snapshot: list[BossProfile]) -> BossProfile | None:
    """Versucht einen Boss per OCR-Texterkennung zu erkennen.

    Mindestens 80 % Konfidenz erforderlich. Liegt die Sicherheit darunter, wird
    sofort ein neuer Screenshot gemacht und der Scan wiederholt — bis zu
    state.config.ocr_retry_count Mal.
    """
    try:
        from ..ocr import detect_boss_name, is_available
    except ImportError:
        if debug:
            print(dbg("  → OCR: Import fehlgeschlagen"))
        return None

    if not is_available():
        if debug:
            print(dbg("  → OCR: kein Backend verfügbar"))
        return None

    boss_names = [boss.name for boss in bosses_snapshot]
    languages = [l.strip() for l in state.config.ocr_languages.split(",")]

    # Mindestens _OCR_MIN_BOSS_CONFIDENCE erzwingen, auch wenn User-Config niedriger ist
    confidence_threshold = max(_OCR_MIN_BOSS_CONFIDENCE, state.config.ocr_min_confidence)
    max_attempts = 1 + max(0, state.config.ocr_retry_count)

    for attempt in range(1, max_attempts + 1):
        current_img = img if attempt == 1 else take_screenshot(config.scan_region)
        if current_img is None:
            if debug:
                print(dbg(f"  → OCR Versuch {attempt}/{max_attempts}: Screenshot fehlgeschlagen"))
            break

        if debug:
            attempt_info = f"Versuch {attempt}/{max_attempts}, " if max_attempts > 1 else ""
            print(dbg(f"  → OCR-Erkennung ({attempt_info}{state.config.ocr_backend or 'Auto'}, min. {confidence_threshold*100:.0f}%)..."))

        success, matched_name, raw_text, duration, new_candidate = detect_boss_name(
            img=current_img,
            boss_names=boss_names,
            backend=state.config.ocr_backend,
            languages=languages,
            min_confidence=confidence_threshold,
            new_boss_min_confidence=_OCR_MIN_BOSS_CONFIDENCE,
        )

        if debug:
            if raw_text:
                print(dbg(f"  → OCR-Text: '{raw_text}' ({duration:.0f}ms)"))
            else:
                print(dbg(f"  → OCR: kein Text erkannt ({duration:.0f}ms)"))

        if success and matched_name is not None:
            for boss in bosses_snapshot:
                if boss.name == matched_name:
                    if debug:
                        print(dbg(f"  → OCR: {boss.name} ERKANNT! (Versuch {attempt})"))
                    return boss

        if new_candidate:
            # Hohe Konfidenz aber unbekannter Name — sofort speichern, nicht weiter retry
            new_boss = _handle_new_boss(state, config, new_candidate, "OCR", debug)
            if new_boss is not None:
                return new_boss
            break

        if attempt < max_attempts:
            if debug:
                print(dbg(f"  → OCR: Konfidenz zu niedrig — Versuch {attempt + 1}/{max_attempts}..."))

    return None


# =============================================================================
# LLM-ERKENNUNG
# =============================================================================

def _execute_llm_boss_detection(state: AutoClickerState, config: BossScanConfig,
                                 img, debug: bool,
                                 bosses_snapshot: list[BossProfile]) -> BossProfile | None:
    """Versucht einen Boss per LLM Vision zu erkennen.

    Wiederholt den Scan bei KEIN_BOSS bis zu state.config.llm_retry_count Mal.
    """
    try:
        from ..llm_vision import analyze_image, match_boss_name
    except ImportError:
        if debug:
            print(dbg("  → LLM: Import fehlgeschlagen"))
        return None

    boss_names = [boss.name for boss in bosses_snapshot]
    max_attempts = 1 + max(0, state.config.llm_retry_count)

    for attempt in range(1, max_attempts + 1):
        current_img = img if attempt == 1 else take_screenshot(config.scan_region)
        if current_img is None:
            if debug:
                print(dbg(f"  → LLM Versuch {attempt}/{max_attempts}: Screenshot fehlgeschlagen"))
            break

        if debug:
            attempt_info = f"Versuch {attempt}/{max_attempts}, " if max_attempts > 1 else ""
            print(dbg(f"  → LLM-Erkennung ({attempt_info}{state.config.llm_provider}, {state.config.llm_model or 'Standard'})..."))

        success, response, duration = analyze_image(
            img=current_img,
            provider=state.config.llm_provider,
            endpoint=state.config.llm_endpoint,
            model=state.config.llm_model,
            prompt=state.config.llm_boss_prompt,
            boss_names=boss_names,
            timeout=state.config.llm_timeout,
            reasoning=state.config.llm_reasoning,
            max_tokens=state.config.llm_max_tokens,
        )

        if not success:
            if debug:
                print(dbg(f"  → LLM-Fehler: {response} ({duration:.0f}ms)"))
            break

        if debug:
            print(dbg(f"  → LLM-Antwort: '{response}' ({duration:.0f}ms)"))

        matched_name, is_new = match_boss_name(response, boss_names)

        if matched_name is None:
            if debug:
                retry_msg = f" — Versuch {attempt + 1}/{max_attempts}..." if attempt < max_attempts else ""
                print(dbg(f"  → LLM: kein Boss erkannt{retry_msg}"))
            continue

        if not is_new:
            for boss in bosses_snapshot:
                if boss.name == matched_name:
                    if debug:
                        print(dbg(f"  → LLM: {boss.name} ERKANNT! (Versuch {attempt})"))
                    return boss

        # Neuer Boss — über gemeinsamen Handler speichern und zur Bestätigung vormerken
        new_boss = _handle_new_boss(state, config, matched_name, "LLM", debug)
        if new_boss is not None:
            return new_boss

        # Falls _handle_new_boss None zurückgab (z.B. bereits vorgemerkt), Profil trotzdem liefern
        with state.lock:
            for boss in config.bosses:
                if boss.name == matched_name:
                    return boss
        return None

    return None


# =============================================================================
# BOSS-AKTION (führt die im BossProfile hinterlegte Aktion aus)
# =============================================================================

def _execute_detection_action(state: AutoClickerState, *, subject: str, action: str,
                              label: str, step_num: int, total_steps: int, phase: str,
                              debug: bool, x: int = 0, y: int = 0,
                              key: Optional[str] = None, delay: float = 0,
                              scan: Optional[str] = None,
                              scan_mode: str = SCAN_MODE_ALL) -> bool:
    """Führt eine Erkennungs-Aktion aus (geteilt von Boss-Scan und Icon-Scan).

    `subject` ist der Betreff für Status-Meldungen (z.B. "Boss 'Drache'" oder
    "Icon 'Mission'"), `label` das Tag für safe_click/safe_key. Gibt False zurück
    wenn die Sequenz abgebrochen werden soll (skip_cycle/restart/Stop).
    """
    if delay > 0:
        if debug:
            print(dbg(f"{subject}: Aktion-Delay {delay}s"))
        if state.stop_event.wait(delay):
            return False

    if action == BOSS_ACTION_SCAN:
        if not scan:
            print(err(f"{subject}: Kein Item-Scan definiert!"))
            return True
        _step_status(debug, phase, step_num, total_steps,
                     f"{subject} → Scan '{scan}'",
                     f"{subject} → Starte Scan '{scan}' ({scan_mode})")
        scan_results = execute_item_scan(state, scan, scan_mode)
        if scan_results:
            for pos, item, priority in scan_results:
                if state.stop_event.is_set():
                    return False
                if not _click_scan_result(state, pos, item, priority, debug):
                    return False
            if debug:
                print(dbg(f"Scan fertig: {len(scan_results)} Item(s) geklickt"))
        else:
            if debug:
                print(dbg("Scan: kein Item gefunden"))

    elif action == BOSS_ACTION_CLICK:
        _step_status(debug, phase, step_num, total_steps,
                     f"{subject} → Klick ({x},{y})")
        if not safe_click(state, x, y, label=label):
            return False
        with state.lock:
            state.total_clicks += 1

    elif action == BOSS_ACTION_KEY:
        _step_status(debug, phase, step_num, total_steps,
                     f"{subject} → Taste '{key}'")
        if key:
            if safe_key(state, key, label=label):
                with state.lock:
                    state.key_presses += 1

    elif action == BOSS_ACTION_SKIP:
        if debug:
            print(dbg(f"{subject} → Schritt überspringen"))

    elif action == BOSS_ACTION_SKIP_CYCLE:
        _step_status(debug, phase, step_num, total_steps,
                     f"{subject} → Zyklus überspringen")
        state.skip_cycle_event.set()
        return False

    elif action == BOSS_ACTION_RESTART:
        _step_status(debug, phase, step_num, total_steps,
                     f"{subject} → Neustart",
                     f"{subject} → Sequenz neustarten")
        state.restart_event.set()
        return False

    return True


def _execute_boss_action(state: AutoClickerState, boss: BossProfile,
                         step: SequenceStep, step_num: int, total_steps: int,
                         phase: str, debug: bool) -> bool:
    """Führt die einem Boss zugeordnete Aktion aus (dünner Adapter)."""
    return _execute_detection_action(
        state, subject=f"Boss '{boss.name}'", action=boss.action,
        label=f"boss:{boss.name}", step_num=step_num, total_steps=total_steps,
        phase=phase, debug=debug,
        x=boss.action_x, y=boss.action_y, key=boss.action_key,
        delay=boss.action_delay, scan=boss.action_scan, scan_mode=boss.action_scan_mode,
    )


# =============================================================================
# ASYNC-PFAD (Boss-Detection läuft im Hintergrund, Sequenz läuft weiter)
# =============================================================================

def _boss_async_thread(state: AutoClickerState, step: SequenceStep,
                       step_num: int, total_steps: int, phase: str) -> None:
    """Hintergrund-Thread: Boss-Detection + Aktion komplett asynchron.

    Sequenz-Worker läuft parallel weiter. Klick-Konflikte werden über
    state.input_lock in safe_click/safe_key garantiert: Worker und dieser Thread
    können nie gleichzeitig SetCursorPos+SendInput senden (echte Mutual-Exclusion).
    llm_action_event bleibt als Status-Marker erhalten.

    Respektiert pause_event und failsafe genau wie der Sync-Pfad — sonst würde
    der Watcher bei pausierter Sequenz weiter Bosse erkennen und Aktionen feuern.
    """
    debug = is_verbose_debug(state)
    try:
        if step.boss_scan:
            if check_failsafe(state):
                state.stop_event.set()
                return
            if not wait_while_paused(state, f"Async-Scan '{step.boss_scan}' pausiert..."):
                return

            found, boss = execute_boss_scan(state, step.boss_scan)
            if not found or not boss:
                # Für else_config: skip/skip_cycle/restart greifen zu spät (Sequenz
                # läuft schon weiter), aber click/key sind harmlose Idempotenz-Aktionen.
                _maybe_execute_async_else(state, step, step_num, total_steps, phase, debug)
                return

        else:
            # Watcher-Schleife bis Boss erkannt oder Limit erreicht
            watcher_name = step.boss_watcher
            interval = state.config.llm_watcher_interval
            max_scans = state.config.llm_watcher_max_scans
            timeout = state.config.llm_watcher_timeout
            scan_count = 0
            start_time = time.time()
            found = False
            boss = None

            while not state.stop_event.is_set():
                if check_failsafe(state):
                    state.stop_event.set()
                    return
                if not wait_while_paused(state, f"Async-Watcher '{watcher_name}' pausiert..."):
                    return

                scan_count += 1
                found, boss = execute_boss_scan(state, watcher_name)
                if found and boss:
                    break

                elapsed = time.time() - start_time
                if max_scans > 0 and scan_count >= max_scans:
                    if debug:
                        print(dbg(f"  → Async-Watcher '{watcher_name}': max. Scans ({max_scans}) erreicht"))
                    return
                if timeout > 0 and elapsed >= timeout:
                    if debug:
                        print(dbg(f"  → Async-Watcher '{watcher_name}': Timeout ({timeout:.0f}s) erreicht"))
                    return

                state.stop_event.wait(interval)

            if not found or not boss:
                return

        if state.stop_event.is_set():
            return
        if check_failsafe(state):
            state.stop_event.set()
            return
        if not wait_while_paused(state, "Async-Boss-Aktion pausiert..."):
            return

        # Boss erkannt → Aktion ausführen, Event sichert exklusiven Zugriff auf Maus/Tastatur
        state.llm_action_event.set()
        try:
            _execute_boss_action(state, boss, step, step_num, total_steps, phase, debug)
        finally:
            state.llm_action_event.clear()

    except Exception as e:
        if debug:
            print(dbg(f"  → LLM-Async Fehler: {e}"))
    finally:
        state.llm_action_event.clear()


def _maybe_execute_async_else(state: AutoClickerState, step: SequenceStep,
                              step_num: int, total_steps: int, phase: str,
                              debug: bool) -> None:
    """Führt die else_config-Aktion im Async-Pfad aus — nur click/key.

    skip/skip_cycle/restart werden bewusst verworfen, weil die Hauptsequenz
    schon weitergelaufen ist und ein verspäteter Zyklus-Reset Chaos stiften würde.
    """
    ec = step.else_config
    if ec is None:
        return
    if ec.action not in (ELSE_CLICK, ELSE_KEY):
        return
    if state.stop_event.is_set():
        return
    if check_failsafe(state):
        state.stop_event.set()
        return
    if not wait_while_paused(state, "Async-Else-Aktion pausiert..."):
        return

    state.llm_action_event.set()
    try:
        if ec.delay > 0:
            state.stop_event.wait(ec.delay)
            if state.stop_event.is_set():
                return
        if ec.action == ELSE_CLICK:
            safe_click(state, ec.x, ec.y, ec.name or "Async-Else-Klick")
            if debug:
                print(dbg(f"  → Async-Else: Klick ({ec.x},{ec.y})"))
        elif ec.action == ELSE_KEY and ec.key:
            safe_key(state, ec.key, ec.name or f"Async-Else-Taste {ec.key}")
            if debug:
                print(dbg(f"  → Async-Else: Taste '{ec.key}'"))
    finally:
        state.llm_action_event.clear()


def _spawn_boss_async(state: AutoClickerState, step: SequenceStep,
                      step_num: int, total_steps: int, phase: str) -> None:
    """Startet _boss_async_thread wenn kein Thread bereits läuft."""
    if state.llm_thread and state.llm_thread.is_alive():
        if is_verbose_debug(state):
            print(dbg("  → LLM-Async: vorheriger Thread noch aktiv, übersprungen"))
        return
    t = threading.Thread(
        target=_boss_async_thread,
        args=(state, step, step_num, total_steps, phase),
        daemon=True,
        name="llm-boss-async",
    )
    state.llm_thread = t
    t.start()


# =============================================================================
# ASYNC-ENTSCHEIDUNGEN + KONFIG-WARNUNGEN
# =============================================================================

def _should_run_async(state: AutoClickerState, config_name: Optional[str]) -> bool:
    """Async-Pfad nur wenn der konkrete Boss-Scan LLM nutzt UND LLM global aktiv ist.

    Vorher genügte globales llm_async+llm_enabled, was Template/Marker-Watcher
    unnötig in den Hintergrund-Thread schickte.
    """
    if not state.config.llm_async or not state.config.llm_enabled:
        return False
    if not config_name:
        return False
    with state.lock:
        cfg = state.boss_scans.get(config_name)
    return bool(cfg and cfg.use_llm)


def _warn_llm_config_inconsistencies(state: AutoClickerState, config_name: Optional[str]) -> None:
    """Einmalige Warnung wenn ein Boss-Scan use_llm=True hat, aber das globale
    llm_enabled aus ist — der User glaubt sonst, LLM würde laufen."""
    if not config_name:
        return
    with state.lock:
        cfg = state.boss_scans.get(config_name)
        if cfg is None:
            return
        key = f"llm_disabled:{config_name}"
        if cfg.use_llm and not state.config.llm_enabled and key not in state.warned_inconsistencies:
            state.warned_inconsistencies.add(key)
            should_warn = True
        else:
            should_warn = False
    if should_warn:
        print(warn(f"'{config_name}': use_llm aktiv, aber llm_enabled global aus — LLM wird ignoriert."))
