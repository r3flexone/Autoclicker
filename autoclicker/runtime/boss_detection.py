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

import logging
import threading
import time
from dataclasses import dataclass
from typing import Optional

from ..imaging import take_screenshot
from ..models import (
    AutoClickerState, SequenceStep, BossScanConfig, BossProfile,
    ELSE_CLICK, ELSE_KEY, SCAN_MODE_ALL,
    BOSS_ACTION_SCAN, BOSS_ACTION_CLICK, BOSS_ACTION_KEY,
    BOSS_ACTION_SKIP, BOSS_ACTION_SKIP_CYCLE, BOSS_ACTION_RESTART,
)
from ..session_log import log_event
from ..utils import col, err, dbg, warn
from ..winapi import check_failsafe
from .actions import (
    safe_click, safe_key, _step_status, is_verbose_debug, wait_while_paused, input_refused,
)
from .debug import is_log_debug
from .item_scan import execute_item_scan, _click_scan_result, _check_profile_match

# Mindest-Konfidenz für OCR-Boss-Erkennung. Unterhalb davon wird nichts gespeichert —
# sichert Zuverlässigkeit und verhindert dass Tippfehler/Garbled-Text als neuer Boss landen.
_OCR_MIN_BOSS_CONFIDENCE = 0.8
logger = logging.getLogger("autoclicker")


# =============================================================================
# BOSS-SCAN AUSFÜHRUNG
# =============================================================================

@dataclass
class _BossScanSnapshot:
    """Was ein Boss-Scan braucht, eingefroren unter Lock — der Editor kann
    während des Scans weiterarbeiten."""
    config: BossScanConfig
    bosses: list
    color_tolerance: int
    scan_region: tuple
    use_llm: bool
    llm_fallback: bool
    use_ocr: bool
    ocr_fallback: bool


def execute_boss_scan(state: AutoClickerState, config_name: str) -> tuple[bool, BossProfile | None]:
    """Erkennt welcher Boss in der Scan-Region ist.

    Returns:
        (found, boss_profile) - True + BossProfile wenn Boss erkannt, sonst (False, None).
    """
    snap = _boss_scan_snapshot(state, config_name)
    if snap is None:
        return False, None
    debug = is_log_debug(state)

    img = take_screenshot(snap.scan_region)
    if img is None:
        if debug:
            print(dbg("Boss-Scan: Screenshot fehlgeschlagen!"))
        return False, None

    llm_active = snap.use_llm and state.config.llm_enabled
    ocr_active = snap.use_ocr and state.config.ocr_enabled
    if debug:
        tags = [tag for tag, active in (("LLM", llm_active), ("OCR", ocr_active)) if active]
        tag_str = f" [{'+'.join(tags)}]" if tags else ""
        r = snap.scan_region
        print(dbg(f"Boss-Scan '{config_name}': Region ({r[0]},{r[1]})-({r[2]},{r[3]}), "
                  f"{len(snap.bosses)} Bosse{tag_str}"))

    for detect in _boss_detectors(state, snap, img, debug, ocr_active, llm_active):
        boss = detect()
        if boss is not None:
            return True, boss
    if debug:
        print(dbg("  → Kein Boss erkannt"))
    return False, None


def _boss_scan_snapshot(state: AutoClickerState, config_name: str) -> Optional[_BossScanSnapshot]:
    """Scan samt gemergter Boss-Liste — None, wenn es ihn oder seine Bosse nicht gibt (gesagt)."""
    with state.lock:
        config = state.boss_scans.get(config_name)
        if config is None:
            print(err(f"Boss-Scan '{config_name}' nicht gefunden!"))
            return None
        # Lokale Bosse + globale Bibliothek mergen (lokal hat Vorrang bei gleichem Namen)
        local_names = {b.name for b in config.bosses}
        bosses = list(config.bosses) + [
            b for b in state.global_bosses if b.name not in local_names
        ]
        if not bosses:
            print(err(f"Boss-Scan '{config_name}' hat keine Bosse definiert (auch keine globalen)!"))
            return None
        # Erkennungs-Flags im selben Lock-Snapshot einfrieren — sonst kann ein
        # Editor sie zwischen mehreren frischen Reads toggeln und das LLM läuft
        # doppelt (einmal primär, einmal als Fallback).
        return _BossScanSnapshot(
            config=config, bosses=bosses, color_tolerance=config.color_tolerance,
            scan_region=config.scan_region,
            use_llm=config.use_llm, llm_fallback=config.llm_fallback,
            use_ocr=config.use_ocr, ocr_fallback=config.ocr_fallback,
        )


def _boss_detectors(state: AutoClickerState, snap: _BossScanSnapshot, img, debug: bool,
                    ocr_active: bool, llm_active: bool) -> list:
    """Die Erkenner in der Reihenfolge, in der sie gefragt werden.

    Primär eingestellte Zusatz-Erkenner vor den Vorlagen, Rückfall-Erkenner
    danach; bei gleicher Einstellung OCR vor LLM (lokal und schnell gegen bis
    zu `llm_timeout`). Keiner läuft doppelt: primär und Rückfall schliessen
    sich über dasselbe Flag aus.
    """
    def ocr():
        return _execute_ocr_boss_detection(state, snap.config, img, debug, snap.bosses)

    def llm():
        return _execute_llm_boss_detection(state, snap.config, img, debug, snap.bosses)

    def template():
        # Bosse der Reihe nach prüfen (Reihenfolge = Priorität)
        return next((boss for boss in snap.bosses
                     if _check_profile_match(boss, img, snap.color_tolerance, state, debug,
                                             "ERKANNT!")), None)

    extra = ((ocr, ocr_active, snap.ocr_fallback), (llm, llm_active, snap.llm_fallback))
    primary = [detect for detect, active, fallback in extra if active and not fallback]
    later = [detect for detect, active, fallback in extra if active and fallback]
    return primary + [template] + later


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
              "— im Boss-Editor anpassbar.", "yellow"))
    for i, (target, boss_name, source) in enumerate(pending, 1):
        print(f"  {i}. [{source}] '{boss_name}'  → {target}")
    print(col("=" * 55, "yellow"))


# =============================================================================
# OCR-ERKENNUNG
# =============================================================================

@dataclass
class _DetectionRun:
    """Was OCR und LLM über ihre Versuche hinweg brauchen."""
    state: AutoClickerState
    config: BossScanConfig
    debug: bool
    bosses: list
    max_attempts: int
    warm_tried: bool = False      # der Aufwärm-Versuch des LLM gilt einmal je Scan

    def image(self, first_img, attempt: int, what: str):
        """Das Bild für einen Versuch: beim ersten das schon aufgenommene, danach ein neues."""
        current = first_img if attempt == 1 else take_screenshot(self.config.scan_region)
        if current is None and self.debug:
            print(dbg(f"  → {what} Versuch {attempt}/{self.max_attempts}: Screenshot fehlgeschlagen"))
        return current

    def known(self, name: str) -> Optional[BossProfile]:
        return next((boss for boss in self.bosses if boss.name == name), None)


def _execute_ocr_boss_detection(state: AutoClickerState, config: BossScanConfig,
                                 img, debug: bool,
                                 bosses_snapshot: list[BossProfile]) -> BossProfile | None:
    """Versucht einen Boss per OCR-Texterkennung zu erkennen.

    Mindestens 80 % Konfidenz erforderlich. Liegt die Sicherheit darunter, wird
    sofort ein neuer Screenshot gemacht und der Scan wiederholt — bis zu
    state.config.ocr_retry_count Mal.
    """
    detect = _ocr_detector(debug)
    if detect is None:
        return None
    run = _DetectionRun(state, config, debug, bosses_snapshot,
                        max_attempts=1 + max(0, state.config.ocr_retry_count))
    for attempt in range(1, run.max_attempts + 1):
        current_img = run.image(img, attempt, "OCR")
        if current_img is None:
            break
        boss, done = _ocr_attempt(run, detect, current_img, attempt)
        if done:
            return boss
        if attempt < run.max_attempts and debug:
            print(dbg(f"  → OCR: Konfidenz zu niedrig — Versuch {attempt + 1}/{run.max_attempts}..."))
    return None


def _ocr_detector(debug: bool):
    """`detect_boss_name`, wenn ein OCR-Backend da ist — sonst None (im Debug gesagt)."""
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
    return detect_boss_name


def _ocr_attempt(run: _DetectionRun, detect, img, attempt: int) -> tuple[Optional[BossProfile], bool]:
    """Ein OCR-Versuch: `(Boss, fertig)` — fertig heisst: nicht weiter versuchen."""
    cfg = run.state.config
    # Mindestens _OCR_MIN_BOSS_CONFIDENCE erzwingen, auch wenn User-Config niedriger ist
    threshold = max(_OCR_MIN_BOSS_CONFIDENCE, cfg.ocr_min_confidence)
    if run.debug:
        attempt_info = f"Versuch {attempt}/{run.max_attempts}, " if run.max_attempts > 1 else ""
        print(dbg(f"  → OCR-Erkennung ({attempt_info}{cfg.ocr_backend or 'Auto'}, "
                  f"min. {threshold*100:.0f}%)..."))
    success, matched_name, raw_text, duration, new_candidate = detect(
        img=img,
        boss_names=[boss.name for boss in run.bosses],
        backend=cfg.ocr_backend,
        languages=[lang.strip() for lang in cfg.ocr_languages.split(",")],
        min_confidence=threshold,
        new_boss_min_confidence=_OCR_MIN_BOSS_CONFIDENCE,
    )
    if run.debug:
        print(dbg(f"  → OCR-Text: '{raw_text}' ({duration:.0f}ms)" if raw_text
                  else f"  → OCR: kein Text erkannt ({duration:.0f}ms)"))

    boss = run.known(matched_name) if success and matched_name is not None else None
    if boss is not None:
        if run.debug:
            print(dbg(f"  → OCR: {boss.name} ERKANNT! (Versuch {attempt})"))
        return boss, True
    if new_candidate:
        # Hohe Konfidenz aber unbekannter Name — sofort speichern, nicht weiter retry
        return _handle_new_boss(run.state, run.config, new_candidate, "OCR", run.debug), True
    return None, False


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
        from ..llm_vision import match_boss_name
    except ImportError:
        if debug:
            print(dbg("  → LLM: Import fehlgeschlagen"))
        return None

    run = _DetectionRun(state, config, debug, bosses_snapshot,
                        max_attempts=1 + max(0, state.config.llm_retry_count))
    for attempt in range(1, run.max_attempts + 1):
        current_img = run.image(img, attempt, "LLM")
        if current_img is None:
            break
        success, response, duration = _llm_answer(run, current_img, attempt)
        if not success:
            if debug:
                print(dbg(f"  → LLM-Fehler: {response} ({duration:.0f}ms)"))
            break
        if debug:
            print(dbg(f"  → LLM-Antwort: '{response}' ({duration:.0f}ms)"))

        matched_name, is_new = match_boss_name(response, [boss.name for boss in run.bosses])
        if matched_name is not None:
            return _llm_boss(run, matched_name, is_new, attempt)
        if debug:
            retry_msg = f" — Versuch {attempt + 1}/{run.max_attempts}..." if attempt < run.max_attempts else ""
            print(dbg(f"  → LLM: kein Boss erkannt{retry_msg}"))
    return None


def _llm_answer(run: _DetectionRun, img, attempt: int) -> tuple[bool, str, float]:
    """Eine Antwort des Modells — ein Timeout bekommt EINEN zweiten Versuch.

    **Ein Timeout ist kein Fehlschlag, sondern ein kaltes Modell.** Gemessen:
    die ersten Aufrufe an einen frisch gestarteten Server brauchen ueber
    120 s, die folgenden 3,5. Hier stand `break` — und damit fiel
    ausgerechnet der ERSTE Boss-Scan eines Laufs aus, waehrend
    `llm_retry_count` daneben stand und nur bei „kein Boss erkannt"
    wiederholte. Der zweite Versuch trifft ein warmes Modell und kostet fast
    nichts; er zaehlt bewusst NICHT gegen das Wiederholungs-Budget, denn er
    beantwortet eine andere Frage.
    """
    from ..llm_vision import analyze_image, is_timeout
    cfg = run.state.config
    if run.debug:
        attempt_info = f"Versuch {attempt}/{run.max_attempts}, " if run.max_attempts > 1 else ""
        print(dbg(f"  → LLM-Erkennung ({attempt_info}{cfg.llm_provider}, "
                  f"{cfg.llm_model or 'Standard'})..."))

    def ask(limit):
        return analyze_image(
            img=img,
            provider=cfg.llm_provider,
            endpoint=cfg.llm_endpoint,
            model=cfg.llm_model,
            prompt=cfg.llm_boss_prompt,
            boss_names=[boss.name for boss in run.bosses],
            timeout=limit,
            reasoning=cfg.llm_reasoning,
            max_tokens=cfg.llm_max_tokens,
        )

    success, response, duration = ask(cfg.llm_timeout)
    if success or not is_timeout(response) or run.warm_tried:
        return success, response, duration
    run.warm_tried = True
    if run.debug:
        print(dbg(f"  → LLM: Zeitüberschreitung nach {duration / 1000:.0f}s "
                  "— das Modell lädt gerade, zweiter Versuch …"))
    return ask(max(cfg.llm_timeout * 2, 120))


def _llm_boss(run: _DetectionRun, name: str, is_new: bool, attempt: int) -> Optional[BossProfile]:
    """Das Profil zu einem erkannten Namen — bekannt, neu angelegt oder schon vorgemerkt."""
    boss = None if is_new else run.known(name)
    if boss is not None:
        if run.debug:
            print(dbg(f"  → LLM: {boss.name} ERKANNT! (Versuch {attempt})"))
        return boss
    # Neuer Boss — über gemeinsamen Handler speichern und zur Bestätigung vormerken
    new_boss = _handle_new_boss(run.state, run.config, name, "LLM", run.debug)
    if new_boss is not None:
        return new_boss
    # Falls _handle_new_boss None zurückgab (Name schon bekannt oder vorgemerkt),
    # das Profil trotzdem liefern. Auch aus der globalen Bibliothek: mit
    # boss_learn_global landen neue Bosse dort und NICHT in config.bosses —
    # die Suche allein in config.bosses ging in dem Fall ins Leere und der
    # Scan meldete "kein Boss", obwohl er den Namen gerade erkannt hatte.
    with run.state.lock:
        candidates = list(run.config.bosses) + list(run.state.global_bosses)
    return next((boss for boss in candidates if boss.name == name), None)


# =============================================================================
# BOSS-AKTION (führt die im BossProfile hinterlegte Aktion aus)
# =============================================================================

@dataclass
class _ActionContext:
    """Was eine Erkennungs-Aktion zum Ausführen und Melden braucht."""
    state: AutoClickerState
    subject: str
    label: str
    step_num: int
    total_steps: int
    phase: str
    debug: bool
    x: int
    y: int
    key: Optional[str]
    scan: Optional[str]
    scan_mode: str

    def status(self, msg: str, dbg_msg: str = None) -> None:
        _step_status(self.debug, self.phase, self.step_num, self.total_steps, msg, dbg_msg)


def _execute_detection_action(state: AutoClickerState, *, subject: str, action: str,
                              label: str, step_num: int, total_steps: int, phase: str,
                              debug: bool, x: int = 0, y: int = 0,
                              key: Optional[str] = None, delay: float = 0,
                              point_id: Optional[int] = None,
                              scan: Optional[str] = None,
                              scan_mode: str = SCAN_MODE_ALL) -> bool:
    """Führt eine Erkennungs-Aktion aus (geteilt von Boss-Scan und Icon-Scan).

    `subject` ist der Betreff für Status-Meldungen (z.B. "Boss 'Drache'" oder
    "Icon 'Mission'"), `label` das Tag für safe_click/safe_key. Gibt False zurück
    wenn die Sequenz abgebrochen werden soll (skip_cycle/restart/Stop).
    """
    if action == BOSS_ACTION_CLICK:
        # Nur eine gültige Referenz erlaubt den Klick. (0, 0) selbst kann ein
        # gültiger Punkt sein und ist deshalb kein Kennzeichen für einen Fehler.
        target = _action_point(state, point_id)
        if target is None:
            print(err(f"{subject}: Klick entfällt — Zielpunkt fehlt."))
            return True
        x, y = target

    # Eine Zeile pro Erkennung — die Klick-Eintraege darunter sagen nur, WO geklickt
    # wurde, nicht WESHALB. Boss- und Icon-Scan laufen beide hier durch, also steht
    # die Zeile genau einmal statt an jeder Fundstelle.
    log_event(state, "detected", detail=subject, x=x, y=y,
              extra=f"aktion={action}")
    if delay > 0:
        if debug:
            print(dbg(f"{subject}: Aktion-Delay {delay}s"))
        if state.stop_event.wait(delay):
            return False

    handler = _DETECTION_ACTIONS.get(action)
    if handler is None:
        return True
    return handler(_ActionContext(state, subject, label, step_num, total_steps, phase,
                                  debug, x, y, key, scan, scan_mode))


def _action_point(state: AutoClickerState, point_id: Optional[int]) -> Optional[tuple[int, int]]:
    with state.lock:
        seq = state.active_sequence
        point = next((p for p in seq.points if p.id == point_id), None) if seq else None
        return (point.x, point.y) if point is not None else None


def _act_scan(ctx: _ActionContext) -> bool:
    if not ctx.scan:
        print(err(f"{ctx.subject}: Kein Item-Scan definiert!"))
        return True
    ctx.status(f"{ctx.subject} → Scan '{ctx.scan}'",
               f"{ctx.subject} → Starte Scan '{ctx.scan}' ({ctx.scan_mode})")
    scan_results = execute_item_scan(ctx.state, ctx.scan, ctx.scan_mode)
    if not scan_results:
        if ctx.debug:
            print(dbg("Scan: kein Item gefunden"))
        return True
    for pos, item, priority in scan_results:
        if ctx.state.stop_event.is_set():
            return False
        if not _click_scan_result(ctx.state, pos, item, priority, ctx.debug):
            return False
    if ctx.debug:
        print(dbg(f"Scan fertig: {len(scan_results)} Item(s) geklickt"))
    return True


def _act_click(ctx: _ActionContext) -> bool:
    ctx.status(f"{ctx.subject} → Klick ({ctx.x},{ctx.y})")
    if not safe_click(ctx.state, ctx.x, ctx.y, label=ctx.label):
        return False
    with ctx.state.lock:
        ctx.state.total_clicks += 1
    return True


def _act_key(ctx: _ActionContext) -> bool:
    ctx.status(f"{ctx.subject} → Taste '{ctx.key}'")
    if not ctx.key:
        return True
    if safe_key(ctx.state, ctx.key, label=ctx.label):
        with ctx.state.lock:
            ctx.state.key_presses += 1
        return True
    return not input_refused(ctx.state)   # verweigert — sonst bliebe ein Block-Skip haengen


def _act_skip(ctx: _ActionContext) -> bool:
    if ctx.debug:
        print(dbg(f"{ctx.subject} → Schritt überspringen"))
    return True


def _act_skip_cycle(ctx: _ActionContext) -> bool:
    ctx.status(f"{ctx.subject} → Zyklus überspringen")
    ctx.state.skip_cycle_event.set()
    return False


def _act_restart(ctx: _ActionContext) -> bool:
    ctx.status(f"{ctx.subject} → Neustart", f"{ctx.subject} → Sequenz neustarten")
    ctx.state.restart_event.set()
    return False


_DETECTION_ACTIONS = {
    BOSS_ACTION_SCAN: _act_scan,
    BOSS_ACTION_CLICK: _act_click,
    BOSS_ACTION_KEY: _act_key,
    BOSS_ACTION_SKIP: _act_skip,
    BOSS_ACTION_SKIP_CYCLE: _act_skip_cycle,
    BOSS_ACTION_RESTART: _act_restart,
}


def _execute_boss_action(state: AutoClickerState, boss: BossProfile,
                         step: SequenceStep, step_num: int, total_steps: int,
                         phase: str, debug: bool) -> bool:
    """Führt die einem Boss zugeordnete Aktion aus (dünner Adapter)."""
    return _execute_detection_action(
        state, subject=f"Boss '{boss.name}'", action=boss.action,
        label=f"boss:{boss.name}", step_num=step_num, total_steps=total_steps,
        phase=phase, debug=debug,
        x=boss.action_x, y=boss.action_y, key=boss.action_key,
        point_id=boss.action_point_id,
        delay=boss.action_delay, scan=boss.action_scan, scan_mode=boss.action_scan_mode,
    )


# =============================================================================
# ASYNC-PFAD (Boss-Detection läuft im Hintergrund, Sequenz läuft weiter)
# =============================================================================

def _async_gate(state: AutoClickerState, message: str) -> bool:
    """Darf der Hintergrund-Thread jetzt handeln? Nicht nach einem Stopp, nicht
    nach der Notbremse (die stoppt dann auch), und erst nach einer Pause.

    Der Async-Pfad muss dieselben Grenzen achten wie der Sync-Pfad — sonst
    erkennt der Watcher bei pausierter Sequenz weiter Bosse und feuert Aktionen.
    """
    if state.stop_event.is_set():
        return False
    if check_failsafe(state):
        state.stop_event.set()
        return False
    return wait_while_paused(state, message)


def _boss_async_thread(state: AutoClickerState, step: SequenceStep,
                       step_num: int, total_steps: int, phase: str) -> None:
    """Hintergrund-Thread: Boss-Detection + Aktion komplett asynchron.

    Sequenz-Worker läuft parallel weiter. Klick-Konflikte werden über
    state.input_lock in safe_click/safe_key garantiert: Worker und dieser Thread
    können nie gleichzeitig SetCursorPos+SendInput senden (echte Mutual-Exclusion).
    llm_action_event bleibt als Status-Marker erhalten.
    """
    debug = is_verbose_debug(state)
    try:
        if step.boss_scan:
            boss = _async_single_scan(state, step, step_num, total_steps, phase, debug)
        else:
            boss = _async_watch(state, step.boss_watcher, debug)
        if boss is None or not _async_gate(state, "Async-Boss-Aktion pausiert..."):
            return
        # Boss erkannt → Aktion ausführen, Event sichert exklusiven Zugriff auf Maus/Tastatur
        state.llm_action_event.set()
        try:
            _execute_boss_action(state, boss, step, step_num, total_steps, phase, debug)
        finally:
            state.llm_action_event.clear()

    except Exception as e:
        detail = f"{type(e).__name__}: {e}"
        logger.exception("Asynchrone Boss-Erkennung fehlgeschlagen")
        log_event(state, "boss_async_error", detail=detail,
                  extra=step.boss_scan or step.boss_watcher or "")
        print(err(f"  -> Asynchrone Boss-Erkennung fehlgeschlagen: {detail}"))
    finally:
        state.llm_action_event.clear()


def _async_single_scan(state: AutoClickerState, step: SequenceStep, step_num: int,
                       total_steps: int, phase: str, debug: bool) -> Optional[BossProfile]:
    """Ein Boss-Scan im Hintergrund; ohne Treffer greift das ELSE (nur click/key)."""
    if not _async_gate(state, f"Async-Scan '{step.boss_scan}' pausiert..."):
        return None
    found, boss = execute_boss_scan(state, step.boss_scan)
    if found and boss:
        return boss
    # Für else_config: skip/skip_cycle/restart greifen zu spät (Sequenz
    # läuft schon weiter), aber click/key sind harmlose Idempotenz-Aktionen.
    _maybe_execute_async_else(state, step, step_num, total_steps, phase, debug)
    return None


def _async_watch(state: AutoClickerState, watcher_name: str, debug: bool) -> Optional[BossProfile]:
    """Watcher-Schleife bis Boss erkannt oder Limit erreicht."""
    interval = state.config.llm_watcher_interval
    max_scans = state.config.llm_watcher_max_scans
    timeout = state.config.llm_watcher_timeout
    scan_count = 0
    start_time = time.time()
    while not state.stop_event.is_set():
        if not _async_gate(state, f"Async-Watcher '{watcher_name}' pausiert..."):
            return None
        scan_count += 1
        found, boss = execute_boss_scan(state, watcher_name)
        if found and boss:
            return boss
        elapsed = time.time() - start_time
        if max_scans > 0 and scan_count >= max_scans:
            if debug:
                print(dbg(f"  → Async-Watcher '{watcher_name}': max. Scans ({max_scans}) erreicht"))
            return None
        if timeout > 0 and elapsed >= timeout:
            if debug:
                print(dbg(f"  → Async-Watcher '{watcher_name}': Timeout ({timeout:.0f}s) erreicht"))
            return None
        state.stop_event.wait(interval)
    return None


def _maybe_execute_async_else(state: AutoClickerState, step: SequenceStep,
                              step_num: int, total_steps: int, phase: str,
                              debug: bool) -> None:
    """Führt die else_config-Aktion im Async-Pfad aus — nur click/key.

    skip/skip_cycle/restart werden bewusst verworfen, weil die Hauptsequenz
    schon weitergelaufen ist und ein verspäteter Zyklus-Reset Chaos stiften würde.
    """
    ec = step.else_config
    if ec is None or ec.action not in (ELSE_CLICK, ELSE_KEY):
        return
    if not _async_gate(state, "Async-Else-Aktion pausiert..."):
        return
    state.llm_action_event.set()
    try:
        if ec.delay > 0 and state.stop_event.wait(ec.delay):
            return
        if ec.action == ELSE_CLICK:
            safe_click(state, ec.x, ec.y, ec.name or "Async-Else-Klick")
            if debug:
                print(dbg(f"  → Async-Else: Klick ({ec.x},{ec.y})"))
        elif ec.key:
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
