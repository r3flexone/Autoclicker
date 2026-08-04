"""
Boss-Scan-Editor für den Autoclicker.
Ermöglicht das Erstellen und Bearbeiten von Boss-Scan-Konfigurationen.
Ein Boss-Scan erkennt welcher Boss in einer Region ist und führt
je nach Boss eine andere Aktion aus (Item-Scan, Klick, Taste, etc.).
"""

import time
from pathlib import Path
from typing import Optional

from ..models import (
    BossProfile, BossScanConfig, AutoClickerState,
    BOSS_ACTION_SCAN, BOSS_ACTION_CLICK, BOSS_ACTION_KEY,
    BOSS_ACTION_SKIP, BOSS_ACTION_SKIP_CYCLE, BOSS_ACTION_RESTART,
    SCAN_MODE_ALL,
)
from ..config import save_config
from ..utils import (
    safe_input, sanitize_filename, is_cancel, confirm, interactive_select,
    col, ok, err, info, header, breadcrumb, suggest_command,
    parse_non_negative_float, warn, hint,
)
from ..winapi import get_cursor_pos
from ..imaging import (
    PILLOW_AVAILABLE, OPENCV_AVAILABLE, take_screenshot,
)
from ..persistence import (
    save_boss_scan, list_available_boss_scans, load_boss_scan_file,
    list_available_item_scans, punkt_fuer_stelle, TEMPLATES_DIR, save_global_bosses,
)
from ._detection_capture import capture_markers, select_scan_region, prompt_key


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
        available_scans = list_available_boss_scans()
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
            config = load_boss_scan_file(path)
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
            state.config.boss_learn_global = not state.config.boss_learn_global
            save_config(state.config)
            if state.config.boss_learn_global:
                print(ok("Neu entdeckte Bosse (LLM/OCR) landen jetzt in der globalen Bibliothek."))
            else:
                print(ok("Neu entdeckte Bosse (LLM/OCR) landen jetzt im jeweiligen Scan."))
        elif num_fixed <= choice < len(menu_options):
            edit_boss_scan(state, loaded_scans[choice - num_fixed])


def _select_boss_action(state: AutoClickerState, existing_boss: Optional[BossProfile] = None) -> Optional[dict]:
    """Fragt den Benutzer nach der Aktion für einen Boss.

    Returns:
        Dict mit action-Feldern oder None bei Abbruch.
    """
    action_options = [
        "Item-Scan ausführen",
        "Punkt klicken",
        "Taste drücken",
        "Schritt überspringen",
        "Zyklus überspringen",
        "Sequenz neustarten",
    ]
    action_map = [
        BOSS_ACTION_SCAN, BOSS_ACTION_CLICK, BOSS_ACTION_KEY,
        BOSS_ACTION_SKIP, BOSS_ACTION_SKIP_CYCLE, BOSS_ACTION_RESTART,
    ]

    # Default-Auswahl basierend auf existierendem Boss
    default_idx = 0
    if existing_boss:
        try:
            default_idx = action_map.index(existing_boss.action)
        except ValueError:
            pass

    choice = interactive_select(action_options, title="\nAktion wenn dieser Boss erkannt wird:",
                                default=default_idx)
    if choice == -1:
        return None

    action = action_map[choice]
    result = {
        "action": action,
        "action_scan": None,
        "action_scan_mode": SCAN_MODE_ALL,
        "action_point_id": None,
        "action_key": None,
        "action_delay": 0,
    }

    if action == BOSS_ACTION_SCAN:
        # Item-Scan auswählen
        available = list_available_item_scans()
        if not available:
            print(f"\n{err('Keine Item-Scans vorhanden!')}")
            print("         Erstelle zuerst einen Item-Scan.")
            return None

        scan_options = [f"{name}" for name, _ in available]
        scan_choice = interactive_select(scan_options, title="\nWelchen Item-Scan ausführen?")
        if scan_choice == -1:
            return None

        result["action_scan"] = available[scan_choice][0]

        # Scan-Modus
        mode_options = ["Bestes pro Kategorie (all)", "Nur 1 bestes Item (best)", "Alle Treffer (every)"]
        mode_map = ["all", "best", "every"]
        mode_choice = interactive_select(mode_options, title="Scan-Modus:")
        if mode_choice >= 0:
            result["action_scan_mode"] = mode_map[mode_choice]

    elif action == BOSS_ACTION_CLICK:
        print("\n  Bewege die Maus zum Klick-Punkt und drücke Enter...")
        try:
            safe_input()
            x, y = get_cursor_pos()
            # Die Stelle wird ein Punkt, gespeichert wird nur seine ID. Sonst haette
            # dieser Klick eine Koordinate, die weder eine Reparatur im Punkte-Menue
            # noch eine Kalibrierung ueber die Punkte je erreicht.
            with state.lock:
                pid = punkt_fuer_stelle(state, x, y, None, "Boss-Klick",
                                        source="Boss-Scan-Editor")
            result["action_point_id"] = pid
            print(f"  → Klick-Position: ({x}, {y})  [Punkt #{pid}]")
        except (KeyboardInterrupt, EOFError):
            return None

    elif action == BOSS_ACTION_KEY:
        key = prompt_key()
        if key is None:
            return None
        result["action_key"] = key

    # Delay vor Aktion
    if action in (BOSS_ACTION_SCAN, BOSS_ACTION_CLICK, BOSS_ACTION_KEY):
        try:
            delay_input = safe_input("  Verzögerung vor Aktion in Sekunden (Enter=0): ").strip()
            if delay_input:
                val, delay_err = parse_non_negative_float(delay_input, "Verzögerung")
                if delay_err:
                    print(f"  → {delay_err}, verwende 0s")
                else:
                    result["action_delay"] = val
        except (KeyboardInterrupt, EOFError):
            pass

    return result


def _add_or_edit_boss(state: AutoClickerState, existing: Optional[BossProfile] = None) -> Optional[BossProfile]:
    """Erstellt oder bearbeitet ein BossProfile.

    Returns:
        BossProfile oder None bei Abbruch.
    """
    # Name
    if existing:
        print(f"\n--- Boss bearbeiten: {existing.name} ---")
        name = safe_input(f"  Name (Enter={existing.name}): ").strip()
        if not name:
            name = existing.name
    else:
        print("\n--- Neuen Boss hinzufügen ---")
        name = safe_input("  Boss-Name: ").strip()
        if not name:
            print("  → Kein Name angegeben!")
            return None

    # Erkennungsmethode
    detect_options = []
    if OPENCV_AVAILABLE:
        detect_options.append("Template-Bild aufnehmen")
    detect_options.append("Farb-Marker setzen")
    if existing and (existing.template or existing.marker_colors):
        detect_options.append("Bestehende Erkennung beibehalten")

    has_keep = "Bestehende Erkennung beibehalten" in detect_options
    detect_choice = interactive_select(detect_options, title="\nWie soll der Boss erkannt werden?",
                                       default=len(detect_options) - 1 if has_keep else 0)
    if detect_choice == -1:
        return None

    template = existing.template if existing else None
    min_confidence = (existing.min_confidence if existing
                      else state.config.scan_min_confidence)
    marker_colors = list(existing.marker_colors) if existing else []

    chosen_label = detect_options[detect_choice]

    if chosen_label == "Template-Bild aufnehmen":
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

            safe_name = sanitize_filename(f"boss_{name}")
            template_file = f"{safe_name}.png"
            template_path = Path(TEMPLATES_DIR) / template_file
            template_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(template_path)
            template = template_file
            print(f"  → Template gespeichert: {template_file}")

            # Konfidenz
            try:
                conf_input = safe_input(f"  Min. Konfidenz % (Enter={int(min_confidence * 100)}): ").strip()
                if conf_input:
                    min_confidence = max(0.1, min(1.0, float(conf_input) / 100))
            except ValueError:
                pass

        except (KeyboardInterrupt, EOFError):
            return None

    elif chosen_label == "Farb-Marker setzen":
        captured = capture_markers()
        if captured is None:
            return None
        marker_colors = captured

    # Aktion auswählen
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


def _edit_boss_list(state: AutoClickerState, bosses: list, allow_empty: bool) -> bool:
    """Interaktiver add/edit/del-Loop für eine BossProfile-Liste (mutiert in-place).

    allow_empty: 'done' mit leerer Liste zulassen (Bibliothek / Scan mit
    globalen Bossen) oder nicht.

    Returns:
        True bei 'done', False bei Abbruch (cancel/ESC/Strg+C).
    """
    if bosses:
        print("\nAktuelle Bosse:")
        for i, boss in enumerate(bosses):
            print(f"  [{i+1}] {boss}")

    boss_help = ("\nBefehle: 'add' (Boss hinzufügen), 'edit <Nr>', 'del <Nr>', "
                 "'show / s', 'help / ?', 'done / d', 'cancel'")
    print(boss_help)

    while True:
        try:
            inp = safe_input("[Bosse] > ").strip().lower()

            if inp in ("done", "d"):
                if not bosses and not allow_empty:
                    print("  " + err("Mindestens 1 Boss erforderlich!") + " "
                          + hint("('add' = Boss hinzufügen, 'cancel' = Editor verlassen)"))
                    continue
                return True
            elif is_cancel(inp):
                return False
            elif inp in ("help", "?"):
                print(boss_help)
            elif inp == "add":
                boss = _add_or_edit_boss(state)
                if boss:
                    bosses.append(boss)
                    print(f"  + Boss '{boss.name}' hinzugefügt")
                    print(f"    {boss}")
            elif inp.startswith("edit "):
                try:
                    num = int(inp[5:])
                    if 1 <= num <= len(bosses):
                        boss = _add_or_edit_boss(state, bosses[num - 1])
                        if boss:
                            bosses[num - 1] = boss
                            print(f"  ~ Boss '{boss.name}' aktualisiert")
                    else:
                        print(f"  → Ungültig! 1-{len(bosses)}")
                except ValueError:
                    print("  → Format: edit <Nr>")
            elif inp.startswith("del "):
                try:
                    num = int(inp[4:])
                    if 1 <= num <= len(bosses):
                        removed = bosses.pop(num - 1)
                        print(f"  - Boss '{removed.name}' entfernt")
                    else:
                        print(f"  → Ungültig! 1-{len(bosses)}")
                except ValueError:
                    print("  → Format: del <Nr>")
            elif inp in ("show", "s"):
                if bosses:
                    print(f"\nBosse ({len(bosses)}):")
                    for i, boss in enumerate(bosses):
                        print(f"  [{i+1}] {boss}")
                else:
                    print("  (Keine Bosse definiert)")
            else:
                _known = ["add", "edit", "del", "done", "cancel", "show", "help"]
                suggestion = suggest_command(inp, _known)
                print(f"  → Unbekannter Befehl.{suggestion}")

        except (KeyboardInterrupt, EOFError):
            return False


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


def edit_boss_scan(state: AutoClickerState, existing: Optional[BossScanConfig]) -> None:
    """Erstellt oder bearbeitet eine Boss-Scan Konfiguration."""

    if existing:
        print(f"\n--- Bearbeite Boss-Scan: {existing.name} ---")
        scan_name = existing.name
        scan_region = existing.scan_region
        bosses = list(existing.bosses)
        tolerance = existing.color_tolerance
        default_action = existing.default_action
        default_scan = existing.default_scan
    else:
        print("\n--- Neuen Boss-Scan erstellen ---")
        scan_name = safe_input("Name des Boss-Scans: ").strip()
        if not scan_name:
            scan_name = f"BossScan_{int(time.time())}"
        scan_region = (0, 0, 100, 100)
        bosses = []
        tolerance = BossScanConfig.color_tolerance
        default_action = BOSS_ACTION_SKIP
        default_scan = None

    # === SCHRITT 1: Scan-Region ===
    print(header("SCHRITT 1: SCAN-REGION (wo erscheint der Boss?)"))
    if existing:
        r = scan_region
        print(f"  Aktuelle Region: ({r[0]},{r[1]}) → ({r[2]},{r[3]})")

    new_region = select_scan_region(scan_region if existing else None)
    if new_region is None:
        if not existing:
            print(f"  {col('[ABBRUCH]', 'yellow')} Boss-Scan nicht gespeichert.")
            return  # Neu-Erstellung abgebrochen
        # Beim Bearbeiten: alte Region behalten
    else:
        scan_region = new_region

    # === SCHRITT 2: Bosse definieren ===
    print(header("SCHRITT 2: BOSSE DEFINIEREN"))
    with state.lock:
        num_global = len(state.global_bosses)
    if num_global:
        print(f"\n  {info(f'{num_global} globale(r) Boss(e) aus der Bibliothek gelten zusätzlich.')}")

    if not _edit_boss_list(state, bosses, allow_empty=num_global > 0):
        return
    if not bosses and num_global:
        print(f"  {info(f'Keine lokalen Bosse — der Scan nutzt die {num_global} globalen.')}")

    # === SCHRITT 3: Default-Aktion ===
    print(header("SCHRITT 3: DEFAULT-AKTION (wenn kein Boss erkannt)"))
    default_options = [
        "Schritt überspringen (skip)",
        "Zyklus überspringen (skip_cycle)",
        "Sequenz neustarten (restart)",
        "Default Item-Scan ausführen",
    ]
    default_map = [BOSS_ACTION_SKIP, BOSS_ACTION_SKIP_CYCLE, BOSS_ACTION_RESTART, BOSS_ACTION_SCAN]

    try:
        preselect = default_map.index(default_action)
    except ValueError:
        preselect = 0
    default_choice = interactive_select(default_options, default=preselect)
    if default_choice >= 0:
        default_action = default_map[default_choice]

        if default_action == BOSS_ACTION_SCAN:
            available = list_available_item_scans()
            if available:
                scan_options = [name for name, _ in available]
                scan_choice = interactive_select(scan_options, title="Welchen Default-Scan?")
                if scan_choice >= 0:
                    default_scan = available[scan_choice][0]
            else:
                print(f"  {info('Keine Item-Scans vorhanden.')}")
                default_action = BOSS_ACTION_SKIP

    # === SCHRITT 4: Farbtoleranz ===
    print(header("SCHRITT 4: FARBTOLERANZ"))
    print(f"\nAktuelle Toleranz: {tolerance}")
    try:
        tol_input = safe_input(f"Neue Toleranz (Enter={tolerance}): ").strip()
        if tol_input:
            tolerance = max(1, min(100, int(tol_input)))
    except (ValueError, KeyboardInterrupt, EOFError):
        pass

    # === SCHRITT 5: LLM Vision ===
    use_llm = existing.use_llm if existing else False
    llm_fallback = existing.llm_fallback if existing else True

    print(header("SCHRITT 5: LLM VISION (optional)"))
    print("\n  LLM-basierte Boss-Erkennung nutzt ein lokales KI-Modell (Ollama/LM Studio)")
    print("  um Bosse per Bilderkennung zu identifizieren.")

    llm_options = [
        "Kein LLM verwenden",
        "LLM als Fallback (wenn Template/Marker nichts finden)",
        "LLM als primäre Erkennung (immer zuerst LLM fragen)",
        "LLM-Verbindung testen",
    ]

    llm_preselect = 0 if not use_llm else (1 if llm_fallback else 2)
    llm_choice = interactive_select(llm_options, title="\nLLM-Erkennung:", default=llm_preselect)
    if llm_choice == 0:
        use_llm = False
    elif llm_choice == 1:
        use_llm = True
        llm_fallback = True
        print(f"  {ok('LLM als Fallback aktiviert')}")
        print("       Stelle sicher, dass in config.json 'llm_enabled: true' gesetzt ist")
        print("       und Ollama/LM Studio läuft (Einstellungen in config.json)")
    elif llm_choice == 2:
        use_llm = True
        llm_fallback = False
        print(f"  {ok('LLM als primäre Erkennung aktiviert')}")
    elif llm_choice == 3:
        _test_llm_connection(state)
        # Nochmal fragen
        if confirm("  LLM aktivieren?"):
            use_llm = True
            llm_fallback = confirm("  Als Fallback? (Nein = primär)")
        else:
            use_llm = False

    # === SCHRITT 6: OCR Texterkennung ===
    use_ocr = existing.use_ocr if existing else False
    ocr_fallback = existing.ocr_fallback if existing else True

    print(header("SCHRITT 6: OCR TEXTERKENNUNG (optional)"))
    print("\n  OCR liest den Boss-Namen direkt als Text vom Screenshot.")
    print("  Schneller als LLM, braucht aber sichtbaren Text im Bild.")

    ocr_available = False
    try:
        from autoclicker.ocr import is_available, get_status
        ocr_available = is_available()
        if not ocr_available:
            print(f"\n  {warn(get_status())}")
    except ImportError:
        print(f"\n  {warn('OCR-Modul nicht verfügbar')}")

    if ocr_available:
        ocr_options = [
            "Kein OCR verwenden",
            "OCR als Fallback (wenn Template/Marker nichts finden)",
            "OCR als primäre Erkennung (immer zuerst OCR)",
        ]

        ocr_preselect = 0 if not use_ocr else (1 if ocr_fallback else 2)
        ocr_choice = interactive_select(ocr_options, title="\nOCR-Erkennung:", default=ocr_preselect)
        if ocr_choice == 0:
            use_ocr = False
        elif ocr_choice == 1:
            use_ocr = True
            ocr_fallback = True
            print(f"  {ok('OCR als Fallback aktiviert')}")
            print("       Stelle sicher, dass in config.json 'ocr_enabled: true' gesetzt ist")
        elif ocr_choice == 2:
            use_ocr = True
            ocr_fallback = False
            print(f"  {ok('OCR als primäre Erkennung aktiviert')}")

    # === Speichern ===
    config = BossScanConfig(
        name=scan_name,
        scan_region=scan_region,
        bosses=bosses,
        color_tolerance=tolerance,
        default_action=default_action,
        default_scan=default_scan,
        use_llm=use_llm,
        llm_fallback=llm_fallback,
        use_ocr=use_ocr,
        ocr_fallback=ocr_fallback,
    )

    with state.lock:
        state.boss_scans[scan_name] = config

    save_boss_scan(config)

    save_msg = ok(f"Boss-Scan '{scan_name}' gespeichert!")
    print(f"\n{save_msg}")
    tags = []
    if use_llm:
        tags.append("LLM")
    if use_ocr:
        tags.append("OCR")
    tag_str = f" [{'+'.join(tags)}]" if tags else ""
    print(f"         {len(bosses)} Boss(e), Region ({scan_region[0]},{scan_region[1]})-({scan_region[2]},{scan_region[3]}){tag_str}")
    print(f"         Nutze im Sequenz-Editor: 'boss {scan_name}'")


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

    success, message = test_connection(provider, test_endpoint)

    if success:
        print(f"  {ok(message)}")
    else:
        print(f"  {err(message)}")
        print(f"\n  Stelle sicher, dass {'Ollama' if provider == PROVIDER_OLLAMA else 'LM Studio'} läuft!")
        if provider == PROVIDER_OLLAMA:
            print("  Vision-Modell installieren: ollama pull llava")
        else:
            print("  Lade ein Vision-Modell in LM Studio (z.B. LLaVA, MiniCPM-V)")
