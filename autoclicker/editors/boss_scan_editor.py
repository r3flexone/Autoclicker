"""
Boss-Scan-Editor für den Autoclicker.
Ermöglicht das Erstellen und Bearbeiten von Boss-Scan-Konfigurationen.
Ein Boss-Scan erkennt welcher Boss in einer Region ist und führt
je nach Boss eine andere Aktion aus (Item-Scan, Klick, Taste, etc.).

Der Assistent läuft in Stufen (Region → Bosse → Default-Aktion → Toleranz →
LLM → OCR → speichern); jede, die abbrechen kann, gibt False zurück. Die
Boss-Liste ist eine Befehlsschleife wie der Loop-Phasen-Editor: ein Befehl,
eine Funktion. Was der Editor mit dem Icon-Editor teilt (Erkennung, Aktion,
Klickpunkt, Konfidenz, Toleranz), steht in `_detection_capture.py`.
"""

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from ..models import (
    BossProfile, BossScanConfig, AutoClickerState,
    BOSS_ACTION_SCAN, BOSS_ACTION_CLICK, BOSS_ACTION_KEY,
    BOSS_ACTION_SKIP, BOSS_ACTION_SKIP_CYCLE, BOSS_ACTION_RESTART,
    SCAN_MODE_ALL,
)
from ..config import save_config
from ..utils import (
    safe_input, is_cancel, confirm, interactive_select,
    col, ok, err, info, header, breadcrumb, suggest_command, warn, hint,
)
from ..winapi import get_cursor_pos
from ..imaging import PILLOW_AVAILABLE, take_screenshot
from ..persistence import (
    save_boss_scan, list_available_boss_scans, load_boss_scan_file,
    list_available_item_scans, save_global_bosses,
)
from ._detection_capture import (
    DETECT_MARKERS, DETECT_TEMPLATE, ask_action_details, ask_min_confidence,
    ask_tolerance, capture_markers, choose_detection, select_action,
    select_scan_region, store_template,
)
from ..persistence.boss_scans import boss_scan_name_allowed

_BOSS_ACTIONS = [
    ("Item-Scan ausführen", BOSS_ACTION_SCAN),
    ("Punkt klicken", BOSS_ACTION_CLICK),
    ("Taste drücken", BOSS_ACTION_KEY),
    ("Schritt überspringen", BOSS_ACTION_SKIP),
    ("Zyklus überspringen", BOSS_ACTION_SKIP_CYCLE),
    ("Sequenz neustarten", BOSS_ACTION_RESTART),
]
# Ohne erkannten Boss gibt es weder Punkt noch Taste (VALID_BOSS_DEFAULT_ACTIONS).
_DEFAULT_ACTIONS = [
    ("Schritt überspringen (skip)", BOSS_ACTION_SKIP),
    ("Zyklus überspringen (skip_cycle)", BOSS_ACTION_SKIP_CYCLE),
    ("Sequenz neustarten (restart)", BOSS_ACTION_RESTART),
    ("Default Item-Scan ausführen", BOSS_ACTION_SCAN),
]
_SCAN_MODES = [
    ("Bestes pro Kategorie (all)", "all"),
    ("Nur 1 bestes Item (best)", "best"),
    ("Alle Treffer (every)", "every"),
]
_LLM_OPTIONS = [
    "Kein LLM verwenden",
    "LLM als Fallback (wenn Template/Marker nichts finden)",
    "LLM als primäre Erkennung (immer zuerst LLM fragen)",
    "LLM-Verbindung testen",
]
_OCR_OPTIONS = [
    "Kein OCR verwenden",
    "OCR als Fallback (wenn Template/Marker nichts finden)",
    "OCR als primäre Erkennung (immer zuerst OCR)",
]
_BOSS_HELP = ("\nBefehle: 'add' (Boss hinzufügen), 'edit <Nr>', 'del <Nr>', "
              "'show / s', 'help / ?', 'done / d', 'cancel'")
_BOSS_KNOWN = ["add", "edit", "del", "done", "cancel", "show", "help"]


def run_boss_scan_editor(state: AutoClickerState) -> None:
    """Hauptmenü für Boss-Scan Konfiguration."""
    print(header("BOSS-SCAN EDITOR"))
    print(f"  {breadcrumb('Hauptmenü', 'Item-Scan', 'Boss-Scans')}")

    if not PILLOW_AVAILABLE:
        print(f"\n{err('Pillow nicht installiert!')}")
        print("         Installieren mit: pip install pillow")
        return

    # Menü-Loop: nach jeder Aktion zurück ins Menü, ESC/cancel beendet
    while True:
        owner = state.active_sequence.name if state.active_sequence else ""
        available_scans = list_available_boss_scans(owner)
        loaded_scans = []
        with state.lock:
            num_global = len(state.global_bosses)
        learn_target = "Bibliothek (global)" if state.config.boss_learn_global else "jeweiliger Scan"
        menu_options = [
            "Neuen Boss-Scan erstellen",
            f"Boss-Bibliothek verwalten ({num_global} globale Bosse)",
            f"Auto-Lernen neuer Bosse → {learn_target} [umschalten]",
        ]
        num_fixed = len(menu_options)
        for name, path in available_scans:
            config = load_boss_scan_file(path, owner)
            if config:
                loaded_scans.append(config)
                menu_options.append(str(config))
            else:
                print(warn(f"Boss-Scan '{name}' ({path.name}) konnte nicht geladen werden — fehlt im Menü!"))

        choice = interactive_select(menu_options, title="\nWas möchtest du tun?")

        if choice == -1:
            print(f"{col('[ABBRUCH]', 'yellow')} Editor beendet.")
            return
        elif choice == 0:
            edit_boss_scan(state, None)
        elif choice == 1:
            edit_global_bosses(state)
        elif choice == 2:
            _toggle_learn_target(state)
        elif num_fixed <= choice < len(menu_options):
            edit_boss_scan(state, loaded_scans[choice - num_fixed])


def _toggle_learn_target(state: AutoClickerState) -> None:
    """Wohin neu entdeckte Bosse (LLM/OCR) gelernt werden: Bibliothek oder Scan."""
    state.config.boss_learn_global = not state.config.boss_learn_global
    saved = save_config(state.config)
    if state.config.boss_learn_global:
        print(ok("Neu entdeckte Bosse (LLM/OCR) landen jetzt in der globalen Bibliothek."))
    else:
        print(ok("Neu entdeckte Bosse (LLM/OCR) landen jetzt im jeweiligen Scan."))
    if not saved:
        print(warn("Nicht in config.json geschrieben — gilt nur bis zum Neustart."))


# =============================================================================
# EIN BOSS
# =============================================================================

def _select_boss_action(state: AutoClickerState, existing_boss: Optional[BossProfile] = None) -> Optional[dict]:
    """Fragt den Benutzer nach der Aktion für einen Boss.

    Returns:
        Dict mit action-Feldern oder None bei Abbruch.
    """
    action = select_action(_BOSS_ACTIONS, "\nAktion wenn dieser Boss erkannt wird:",
                           existing_boss.action if existing_boss else None)
    if action is None:
        return None
    result = {
        "action": action,
        "action_scan": None,
        "action_scan_mode": SCAN_MODE_ALL,
        "action_point_id": None,
        "action_key": None,
        "action_delay": 0,
    }
    if action == BOSS_ACTION_SCAN and not _ask_action_scan(state, result):
        return None
    if not ask_action_details(
            state, action, result, "Boss-Klick", "Boss-Scan-Editor",
            with_delay=action in (BOSS_ACTION_SCAN, BOSS_ACTION_CLICK, BOSS_ACTION_KEY)):
        return None
    return result


def _ask_action_scan(state: AutoClickerState, result: dict) -> bool:
    """Welcher Item-Scan in welchem Modus läuft, wenn der Boss erkannt wird."""
    owner = state.active_sequence.name if state.active_sequence else ""
    available = list_available_item_scans(owner)
    if not available:
        print(f"\n{err('Keine Item-Scans vorhanden!')}")
        print("         Erstelle zuerst einen Item-Scan.")
        return False
    scan_choice = interactive_select([name for name, _ in available],
                                     title="\nWelchen Item-Scan ausführen?")
    if scan_choice == -1:
        return False
    result["action_scan"] = available[scan_choice][0]
    mode_choice = interactive_select([label for label, _mode in _SCAN_MODES],
                                     title="Scan-Modus:")
    if mode_choice >= 0:
        result["action_scan_mode"] = _SCAN_MODES[mode_choice][1]
    return True


def _add_or_edit_boss(state: AutoClickerState, existing: Optional[BossProfile] = None) -> Optional[BossProfile]:
    """Erstellt oder bearbeitet ein BossProfile.

    Returns:
        BossProfile oder None bei Abbruch.
    """
    name = _ask_boss_name(existing)
    if name is None:
        return None
    detection = choose_detection(
        "\nWie soll der Boss erkannt werden?",
        bool(existing and (existing.template or existing.marker_colors)))
    if detection is None:
        return None

    template = existing.template if existing else None
    min_confidence = (existing.min_confidence if existing
                      else state.config.scan_min_confidence)
    marker_colors = list(existing.marker_colors) if existing else []
    if detection == DETECT_TEMPLATE:
        captured = _capture_boss_template(state, name, min_confidence)
        if captured is None:
            return None
        template, min_confidence = captured
    elif detection == DETECT_MARKERS:
        captured = capture_markers()
        if captured is None:
            return None
        marker_colors = captured

    action_result = _select_boss_action(state, existing)
    if action_result is None:
        return None
    return BossProfile(
        name=name,
        marker_colors=marker_colors,
        template=template,
        min_confidence=min_confidence,
        **action_result,
    )


def _ask_boss_name(existing: Optional[BossProfile]) -> Optional[str]:
    """Beim Bearbeiten behält Enter den Namen; beim Anlegen ist ohne Namen Schluss."""
    if existing:
        print(f"\n--- Boss bearbeiten: {existing.name} ---")
        return safe_input(f"  Name (Enter={existing.name}): ").strip() or existing.name
    print("\n--- Neuen Boss hinzufügen ---")
    name = safe_input("  Boss-Name: ").strip()
    if not name:
        print("  → Kein Name angegeben!")
        return None
    return name


def _capture_boss_template(state: AutoClickerState, name: str,
                           min_confidence: float) -> Optional[tuple[str, float]]:
    """Zwei Ecken, Screenshot, Template ablegen, Konfidenz — oder None."""
    print("\n  Bewege die Maus zur OBEREN LINKEN Ecke des Boss-Bereichs")
    print("  und drücke Enter...")
    try:
        safe_input()
        x1, y1 = get_cursor_pos()
        print(f"  → Obere linke Ecke: ({x1}, {y1})")

        print("  Bewege die Maus zur UNTEREN RECHTEN Ecke und drücke Enter...")
        safe_input()
        x2, y2 = get_cursor_pos()
        print(f"  → Untere rechte Ecke: ({x2}, {y2})")

        if x2 <= x1 or y2 <= y1:
            print(f"  {err('Ungültiger Bereich!')}")
            return None
        img = take_screenshot((x1, y1, x2, y2))
        if not img:
            print(f"  {err('Screenshot fehlgeschlagen!')}")
            return None
        template = store_template(state, img, f"boss_{name}")
        return template, ask_min_confidence(min_confidence)
    except (KeyboardInterrupt, EOFError):
        return None


# =============================================================================
# DIE BOSS-LISTE (Befehlsschleife)
# =============================================================================

def _edit_boss_list(state: AutoClickerState, bosses: list, allow_empty: bool) -> bool:
    """Interaktiver add/edit/del-Loop für eine BossProfile-Liste (mutiert in-place).

    allow_empty: 'done' mit leerer Liste zulassen (Bibliothek / Scan mit
    globalen Bossen) oder nicht.

    Returns:
        True bei 'done', False bei Abbruch (cancel/ESC/Strg+C).
    """
    if bosses:
        print("\nAktuelle Bosse:")
        _print_bosses(bosses)
    print(_BOSS_HELP)

    while True:
        try:
            finished = _boss_list_step(state, bosses, allow_empty)
        except (KeyboardInterrupt, EOFError):
            return False
        if finished is not None:
            return finished


def _boss_list_step(state: AutoClickerState, bosses: list, allow_empty: bool) -> Optional[bool]:
    """Eine Eingabe der Boss-Liste: True = fertig, False = abgebrochen, None = weiter."""
    inp = safe_input("[Bosse] > ").strip().lower()
    if inp in ("done", "d"):
        if bosses or allow_empty:
            return True
        print("  " + err("Mindestens 1 Boss erforderlich!") + " "
              + hint("('add' = Boss hinzufügen, 'cancel' = Editor verlassen)"))
        return None
    if is_cancel(inp):
        return False
    found = _boss_command(inp)
    if found is None:
        print(f"  → Unbekannter Befehl.{suggest_command(inp, _BOSS_KNOWN)}")
        return None
    handler, argument = found
    handler(state, bosses, argument)
    return None


def _boss_command(inp: str) -> Optional[tuple[Callable, str]]:
    """Wer für eine Eingabe zuständig ist, samt dem Rest der Eingabe — oder None."""
    if inp in ("help", "?"):
        return _boss_help, ""
    if inp == "add":
        return _boss_add, ""
    if inp.startswith("edit "):
        return _boss_edit, inp[5:]
    if inp.startswith("del "):
        return _boss_delete, inp[4:]
    if inp in ("show", "s"):
        return _boss_show, ""
    return None


def _print_bosses(bosses: list) -> None:
    for i, boss in enumerate(bosses):
        print(f"  [{i+1}] {boss}")


def _boss_index(argument: str, bosses: list, usage: str) -> Optional[int]:
    """Die Nummer als Listenindex — oder None, und gesagt wird, warum."""
    try:
        number = int(argument)
    except ValueError:
        print(f"  → Format: {usage}")
        return None
    if not 1 <= number <= len(bosses):
        print(f"  → Ungültig! 1-{len(bosses)}")
        return None
    return number - 1


def _boss_help(state, bosses, argument) -> None:
    print(_BOSS_HELP)


def _boss_add(state, bosses, argument) -> None:
    boss = _add_or_edit_boss(state)
    if boss:
        bosses.append(boss)
        print(f"  + Boss '{boss.name}' hinzugefügt")
        print(f"    {boss}")


def _boss_edit(state, bosses, argument) -> None:
    index = _boss_index(argument, bosses, "edit <Nr>")
    if index is None:
        return
    boss = _add_or_edit_boss(state, bosses[index])
    if boss:
        bosses[index] = boss
        print(f"  ~ Boss '{boss.name}' aktualisiert")


def _boss_delete(state, bosses, argument) -> None:
    index = _boss_index(argument, bosses, "del <Nr>")
    if index is None:
        return
    removed = bosses.pop(index)
    print(f"  - Boss '{removed.name}' entfernt")


def _boss_show(state, bosses, argument) -> None:
    if not bosses:
        print("  (Keine Bosse definiert)")
        return
    print(f"\nBosse ({len(bosses)}):")
    _print_bosses(bosses)


def edit_global_bosses(state: AutoClickerState) -> None:
    """Verwaltet die globale Boss-Bibliothek (gilt zusätzlich in jedem Boss-Scan)."""
    print(header("BOSS-BIBLIOTHEK (globale Bosse)"))
    print("  Diese Bosse gelten automatisch in JEDEM Boss-Scan.")
    print(f"  {col('Hinweis:', 'cyan')} Lokale Bosse eines Scans haben bei gleichem Namen Vorrang.")

    with state.lock:
        bosses = list(state.global_bosses)

    if _edit_boss_list(state, bosses, allow_empty=True):
        with state.lock:
            state.global_bosses = bosses
        save_global_bosses(state)
    else:
        print(f"  {col('[ABBRUCH]', 'yellow')} Änderungen verworfen.")


# =============================================================================
# DER BOSS-SCAN (Assistent in Stufen)
# =============================================================================

@dataclass
class _BossDraft:
    """Was der Assistent bis zum Speichern zusammenträgt."""
    name: str
    region: tuple = (0, 0, 100, 100)
    bosses: list = field(default_factory=list)
    tolerance: int = BossScanConfig.color_tolerance
    default_action: str = BOSS_ACTION_SKIP
    default_scan: Optional[str] = None
    use_llm: bool = False
    llm_fallback: bool = True
    use_ocr: bool = False
    ocr_fallback: bool = True


def edit_boss_scan(state: AutoClickerState, existing: Optional[BossScanConfig]) -> None:
    """Erstellt oder bearbeitet eine Boss-Scan Konfiguration."""
    draft = _boss_draft(existing)
    if draft is None or not _boss_step_region(draft, existing):
        return
    if not _boss_step_bosses(state, draft):
        return
    _boss_step_default(state, draft)
    _boss_step_tolerance(draft)
    _boss_step_llm(state, draft)
    _boss_step_ocr(draft)
    _save_boss_config(state, draft)


def _boss_draft(existing: Optional[BossScanConfig]) -> Optional[_BossDraft]:
    """Der Ausgangsstand: der bestehende Scan (mit KOPIE der Boss-Liste) oder ein neuer."""
    if existing:
        print(f"\n--- Bearbeite Boss-Scan: {existing.name} ---")
        return _BossDraft(existing.name, existing.scan_region, list(existing.bosses),
                          existing.color_tolerance, existing.default_action,
                          existing.default_scan, existing.use_llm, existing.llm_fallback,
                          existing.use_ocr, existing.ocr_fallback)
    print("\n--- Neuen Boss-Scan erstellen ---")
    while True:
        name = safe_input("Name des Boss-Scans: ").strip()
        if is_cancel(name):
            print(warn("[ABBRUCH] Boss-Scan nicht angelegt."))
            return None
        if boss_scan_name_allowed(name):
            return _BossDraft(name or f"BossScan_{int(time.time())}")
        print(err("'bibliothek' ist reserviert. Bitte einen anderen Namen wählen."))


def _boss_step_region(draft: _BossDraft, existing: Optional[BossScanConfig]) -> bool:
    """SCHRITT 1. Ohne neue Region bleibt beim Bearbeiten die alte; beim Anlegen = Abbruch."""
    print(header("SCHRITT 1: SCAN-REGION (wo erscheint der Boss?)"))
    if existing:
        r = draft.region
        print(f"  Aktuelle Region: ({r[0]},{r[1]}) → ({r[2]},{r[3]})")
    new_region = select_scan_region(draft.region if existing else None)
    if new_region is not None:
        draft.region = new_region
        return True
    if existing is None:
        print(f"  {col('[ABBRUCH]', 'yellow')} Boss-Scan nicht gespeichert.")
        return False
    return True


def _boss_step_bosses(state: AutoClickerState, draft: _BossDraft) -> bool:
    """SCHRITT 2: die Boss-Liste. Leer erlaubt, wenn die Bibliothek Bosse hat."""
    print(header("SCHRITT 2: BOSSE DEFINIEREN"))
    with state.lock:
        num_global = len(state.global_bosses)
    if num_global:
        print(f"\n  {info(f'{num_global} globale(r) Boss(e) aus der Bibliothek gelten zusätzlich.')}")
    if not _edit_boss_list(state, draft.bosses, allow_empty=num_global > 0):
        return False
    if not draft.bosses and num_global:
        print(f"  {info(f'Keine lokalen Bosse — der Scan nutzt die {num_global} globalen.')}")
    return True


def _boss_step_default(state: AutoClickerState, draft: _BossDraft) -> None:
    """SCHRITT 3: was passiert, wenn kein Boss erkannt wird. Ohne Auswahl bleibt es."""
    print(header("SCHRITT 3: DEFAULT-AKTION (wenn kein Boss erkannt)"))
    actions = [action for _label, action in _DEFAULT_ACTIONS]
    preselect = actions.index(draft.default_action) if draft.default_action in actions else 0
    choice = interactive_select([label for label, _action in _DEFAULT_ACTIONS],
                                default=preselect)
    if choice < 0:
        return
    draft.default_action = actions[choice]
    if draft.default_action != BOSS_ACTION_SCAN:
        return
    owner = state.active_sequence.name if state.active_sequence else ""
    available = list_available_item_scans(owner)
    if not available:
        print(f"  {info('Keine Item-Scans vorhanden.')}")
        draft.default_action = BOSS_ACTION_SKIP
        return
    scan_choice = interactive_select([name for name, _ in available],
                                     title="Welchen Default-Scan?")
    if scan_choice >= 0:
        draft.default_scan = available[scan_choice][0]


def _boss_step_tolerance(draft: _BossDraft) -> None:
    """SCHRITT 4: Farbtoleranz; leer, unlesbar oder abgebrochen = unverändert."""
    print(header("SCHRITT 4: FARBTOLERANZ"))
    print(f"\nAktuelle Toleranz: {draft.tolerance}")
    try:
        draft.tolerance = ask_tolerance(f"Neue Toleranz (Enter={draft.tolerance}): ",
                                        draft.tolerance)
    except (KeyboardInterrupt, EOFError):
        pass


def _boss_step_llm(state: AutoClickerState, draft: _BossDraft) -> None:
    """SCHRITT 5: LLM aus, als Fallback oder primär — oder erst die Verbindung testen."""
    print(header("SCHRITT 5: LLM VISION (optional)"))
    print("\n  LLM-basierte Boss-Erkennung nutzt ein lokales KI-Modell (Ollama/LM Studio)")
    print("  um Bosse per Bilderkennung zu identifizieren.")

    preselect = 0 if not draft.use_llm else (1 if draft.llm_fallback else 2)
    choice = interactive_select(_LLM_OPTIONS, title="\nLLM-Erkennung:", default=preselect)
    if choice == 0:
        draft.use_llm = False
    elif choice == 1:
        draft.use_llm, draft.llm_fallback = True, True
        print(f"  {ok('LLM als Fallback aktiviert')}")
        print("       Stelle sicher, dass in config.json 'llm_enabled: true' gesetzt ist")
        print("       und Ollama/LM Studio läuft (Einstellungen in config.json)")
    elif choice == 2:
        draft.use_llm, draft.llm_fallback = True, False
        print(f"  {ok('LLM als primäre Erkennung aktiviert')}")
    elif choice == 3:
        _test_llm_connection(state)
        # Nach dem Test nochmal fragen
        if confirm("  LLM aktivieren?"):
            draft.use_llm = True
            draft.llm_fallback = confirm("  Als Fallback? (Nein = primär)")
        else:
            draft.use_llm = False


def _boss_step_ocr(draft: _BossDraft) -> None:
    """SCHRITT 6: OCR aus, als Fallback oder primär — gefragt nur, wenn es OCR gibt."""
    print(header("SCHRITT 6: OCR TEXTERKENNUNG (optional)"))
    print("\n  OCR liest den Boss-Namen direkt als Text vom Screenshot.")
    print("  Schneller als LLM, braucht aber sichtbaren Text im Bild.")

    try:
        from autoclicker.ocr import is_available, get_status
    except ImportError:
        print(f"\n  {warn('OCR-Modul nicht verfügbar')}")
        return
    if not is_available():
        print(f"\n  {warn(get_status())}")
        return

    preselect = 0 if not draft.use_ocr else (1 if draft.ocr_fallback else 2)
    choice = interactive_select(_OCR_OPTIONS, title="\nOCR-Erkennung:", default=preselect)
    if choice == 0:
        draft.use_ocr = False
    elif choice == 1:
        draft.use_ocr, draft.ocr_fallback = True, True
        print(f"  {ok('OCR als Fallback aktiviert')}")
        print("       Stelle sicher, dass in config.json 'ocr_enabled: true' gesetzt ist")
    elif choice == 2:
        draft.use_ocr, draft.ocr_fallback = True, False
        print(f"  {ok('OCR als primäre Erkennung aktiviert')}")


def _save_boss_config(state: AutoClickerState, draft: _BossDraft) -> None:
    config = BossScanConfig(
        name=draft.name,
        scan_region=draft.region,
        bosses=draft.bosses,
        color_tolerance=draft.tolerance,
        default_action=draft.default_action,
        default_scan=draft.default_scan,
        use_llm=draft.use_llm,
        llm_fallback=draft.llm_fallback,
        use_ocr=draft.use_ocr,
        ocr_fallback=draft.ocr_fallback,
        owner_sequence=state.active_sequence.name if state.active_sequence else "",
    )
    with state.lock:
        state.boss_scans[draft.name] = config

    if not save_boss_scan(config):
        print(err("Boss-Scan nicht gespeichert; Änderungen bleiben im Arbeitsspeicher."))
        return

    save_msg = ok(f"Boss-Scan '{draft.name}' gespeichert!")
    print(f"\n{save_msg}")
    tags = [tag for tag, used in (("LLM", draft.use_llm), ("OCR", draft.use_ocr)) if used]
    tag_str = f" [{'+'.join(tags)}]" if tags else ""
    r = draft.region
    print(f"         {len(draft.bosses)} Boss(e), Region ({r[0]},{r[1]})-({r[2]},{r[3]}){tag_str}")
    print(f"         Nutze im Sequenz-Editor: 'boss {draft.name}'")


def _test_llm_connection(state: AutoClickerState) -> None:
    """Testet die Verbindung zum LLM-Provider."""
    try:
        from ..llm_vision import test_connection, test_endpoint_for, PROVIDER_OLLAMA
    except ImportError:
        print(f"\n  {err('LLM Vision Modul konnte nicht geladen werden!')}")
        return

    provider = state.config.llm_provider
    endpoint = state.config.llm_endpoint

    print(f"\n  Teste Verbindung zu {provider}...")

    # Teste den richtigen Endpoint (Tags/Models statt Chat)
    if endpoint is None:
        test_endpoint = test_endpoint_for(provider)
    else:
        # Leite den Test-Endpoint vom Chat-Endpoint ab
        test_endpoint = endpoint

    # Mit Modell: ein erreichbarer Server ohne das eingestellte Modell ist
    # kein Erfolg — danach scheitert jeder Aufruf.
    success, message = test_connection(provider, test_endpoint,
                                       state.config.llm_model)

    if success:
        print(f"  {ok(message)}")
    else:
        print(f"  {err(message)}")
        print(f"\n  Stelle sicher, dass {'Ollama' if provider == PROVIDER_OLLAMA else 'LM Studio'} läuft!")
        if provider == PROVIDER_OLLAMA:
            print("  Vision-Modell installieren: ollama pull llava")
        else:
            print("  Lade ein Vision-Modell in LM Studio (z.B. LLaVA, MiniCPM-V)")
