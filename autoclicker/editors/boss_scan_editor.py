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
    VALID_BOSS_ACTIONS, SCAN_MODE_ALL, VALID_SCAN_MODES,
)
from ..config import CONFIG, DEFAULT_MIN_CONFIDENCE
from ..utils import (
    safe_input, sanitize_filename, is_cancel, confirm, interactive_select,
    col, ok, err, info, hint, header, breadcrumb, suggest_command,
    cancel_hint, parse_non_negative_float,
)
from ..winapi import get_cursor_pos
from ..imaging import (
    PILLOW_AVAILABLE, OPENCV_AVAILABLE, take_screenshot, select_region,
)
from ..persistence import (
    save_boss_scan, list_available_boss_scans, load_boss_scan_file,
    list_available_item_scans, BOSS_SCANS_DIR, TEMPLATES_DIR,
)


def run_boss_scan_editor(state: AutoClickerState) -> None:
    """Hauptmenü für Boss-Scan Konfiguration."""
    print(header("BOSS-SCAN EDITOR"))
    print(f"  {breadcrumb('Hauptmenü', 'Item-Scan', 'Boss-Scans')}")

    if not PILLOW_AVAILABLE:
        print(f"\n{err('Pillow nicht installiert!')}")
        print("         Installieren mit: pip install pillow")
        return

    # Bestehende Boss-Scans laden
    available_scans = list_available_boss_scans()
    loaded_scans = []
    menu_options = ["Neuen Boss-Scan erstellen"]
    for name, path in available_scans:
        config = load_boss_scan_file(path)
        if config:
            loaded_scans.append(config)
            menu_options.append(str(config))

    choice = interactive_select(menu_options, title="\nWas möchtest du tun?")

    if choice == -1:
        print(f"{col('[CANCEL]', 'yellow')} Editor beendet.")
        return
    elif choice == 0:
        edit_boss_scan(state, None)
    elif 1 <= choice < len(menu_options):
        edit_boss_scan(state, loaded_scans[choice - 1])


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

    choice = interactive_select(action_options, title="\nAktion wenn dieser Boss erkannt wird:")
    if choice == -1:
        return None

    action = action_map[choice]
    result = {
        "action": action,
        "action_scan": None,
        "action_scan_mode": SCAN_MODE_ALL,
        "action_x": 0,
        "action_y": 0,
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
            result["action_x"] = x
            result["action_y"] = y
            print(f"  → Klick-Position: ({x}, {y})")
        except (KeyboardInterrupt, EOFError):
            return None

    elif action == BOSS_ACTION_KEY:
        key = safe_input("  Taste (z.B. 'enter', 'space', '1'): ").strip()
        if not key:
            print("  → Keine Taste angegeben!")
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

    detect_choice = interactive_select(detect_options, title="\nWie soll der Boss erkannt werden?")
    if detect_choice == -1:
        return None

    template = existing.template if existing else None
    min_confidence = existing.min_confidence if existing else DEFAULT_MIN_CONFIDENCE
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
        marker_colors = []
        print("\n  Farb-Marker aufnehmen (Maus auf Farbpunkt bewegen, Enter drücken)")
        print("  'done' oder 'd' wenn fertig, 'cancel' zum Abbrechen")
        while True:
            try:
                inp = safe_input(f"  Marker {len(marker_colors)+1}: ").strip().lower()
                if inp in ("done", "d"):
                    break
                if is_cancel(inp):
                    return None
                if inp == "" or inp == "enter":
                    # Farbwert von aktueller Mausposition lesen
                    x, y = get_cursor_pos()
                    from ..imaging import get_pixel_color
                    color = get_pixel_color(x, y)
                    if color:
                        marker_colors.append(color)
                        print(f"    → RGB{color} bei ({x},{y})")
                    else:
                        print(f"    → Konnte Farbe nicht lesen!")
            except (KeyboardInterrupt, EOFError):
                return None

        if not marker_colors:
            print(f"  {err('Mindestens 1 Marker benötigt!')}")
            return None

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
        tolerance = 30
        default_action = BOSS_ACTION_SKIP
        default_scan = None

    # === SCHRITT 1: Scan-Region ===
    print(header("SCHRITT 1: SCAN-REGION (wo erscheint der Boss?)"))
    if existing:
        r = scan_region
        print(f"  Aktuelle Region: ({r[0]},{r[1]}) → ({r[2]},{r[3]})")

    region_options = [
        "Per Maus auswählen (2 Ecken)",
        "Koordinaten manuell eingeben",
    ]
    if existing:
        region_options.append("Bestehende Region beibehalten")

    region_choice = interactive_select(region_options)
    if region_choice == -1:
        return

    if region_options[region_choice] == "Per Maus auswählen (2 Ecken)":
        result = select_region()
        if result:
            scan_region = result
            print(f"  → Region: ({scan_region[0]},{scan_region[1]}) → ({scan_region[2]},{scan_region[3]})")
        else:
            print(f"  {err('Region-Auswahl fehlgeschlagen!')}")
            if not existing:
                return

    elif region_options[region_choice] == "Koordinaten manuell eingeben":
        try:
            inp = safe_input("  Region (x1,y1,x2,y2): ").strip()
            parts = [int(x.strip()) for x in inp.split(",")]
            if len(parts) == 4:
                scan_region = tuple(parts)
                print(f"  → Region: ({scan_region[0]},{scan_region[1]}) → ({scan_region[2]},{scan_region[3]})")
            else:
                print(f"  {err('Format: x1,y1,x2,y2')}")
                if not existing:
                    return
        except (ValueError, KeyboardInterrupt, EOFError):
            if not existing:
                return

    # === SCHRITT 2: Bosse definieren ===
    print(header("SCHRITT 2: BOSSE DEFINIEREN"))
    if bosses:
        print("\nAktuelle Bosse:")
        for i, boss in enumerate(bosses):
            print(f"  [{i+1}] {boss}")

    print("\nBefehle: 'add' (Boss hinzufügen), 'edit <Nr>', 'del <Nr>', 'done / d', 'cancel'")

    while True:
        try:
            inp = safe_input("[Bosse] > ").strip().lower()

            if inp in ("done", "d"):
                break
            elif is_cancel(inp):
                return
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
                _known = ["add", "edit", "del", "done", "cancel", "show"]
                suggestion = suggest_command(inp, _known)
                print(f"  → Unbekannter Befehl.{suggestion}")

        except (KeyboardInterrupt, EOFError):
            return

    if not bosses:
        print(f"\n{err('Mindestens 1 Boss erforderlich!')}")
        return

    # === SCHRITT 3: Default-Aktion ===
    print(header("SCHRITT 3: DEFAULT-AKTION (wenn kein Boss erkannt)"))
    default_options = [
        "Schritt überspringen (skip)",
        "Zyklus überspringen (skip_cycle)",
        "Sequenz neustarten (restart)",
        "Default Item-Scan ausführen",
    ]
    default_map = [BOSS_ACTION_SKIP, BOSS_ACTION_SKIP_CYCLE, BOSS_ACTION_RESTART, BOSS_ACTION_SCAN]

    default_choice = interactive_select(default_options)
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

    # === Speichern ===
    config = BossScanConfig(
        name=scan_name,
        scan_region=scan_region,
        bosses=bosses,
        color_tolerance=tolerance,
        default_action=default_action,
        default_scan=default_scan,
    )

    with state.lock:
        state.boss_scans[scan_name] = config

    save_boss_scan(config)

    save_msg = ok(f"Boss-Scan '{scan_name}' gespeichert!")
    print(f"\n{save_msg}")
    print(f"         {len(bosses)} Boss(e), Region ({scan_region[0]},{scan_region[1]})-({scan_region[2]},{scan_region[3]})")
    print(f"         Nutze im Sequenz-Editor: 'boss {scan_name}'")
