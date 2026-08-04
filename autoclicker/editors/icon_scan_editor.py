"""
Icon-Scan-Editor für den Autoclicker.

Ein Icon-Scan erkennt ein einzelnes Symbol/Icon (z.B. ein rotes "!" das eine
nicht machbare Mission markiert) per Template oder Farb-Marker in einer Region
und führt bei Fund eine Aktion aus (Klick / Taste / Zyklus überspringen / ...).
Bewusst schlank — kein Item-Sammeln, kein LLM.
"""

import time
from pathlib import Path
from typing import Optional

from ..models import (
    IconScanConfig, AutoClickerState,
    ICON_ACTION_CLICK, ICON_ACTION_KEY, ICON_ACTION_SKIP,
    ICON_ACTION_SKIP_CYCLE, ICON_ACTION_RESTART,
)
from ..utils import (
    safe_input, sanitize_filename, is_cancel, interactive_select,
    col, ok, err, warn, header, breadcrumb, parse_non_negative_float,
)
from ..winapi import get_cursor_pos
from ..imaging import (
    PILLOW_AVAILABLE, OPENCV_AVAILABLE, take_screenshot,
)
from ..persistence import (
    save_icon_scan, list_available_icon_scans, load_icon_scan_file,
    punkt_fuer_stelle, TEMPLATES_DIR,
)
from ._detection_capture import capture_markers, select_scan_region, prompt_key


def run_icon_scan_editor(state: AutoClickerState) -> None:
    """Hauptmenü für Icon-Scan Konfiguration."""
    print(header("ICON-SCAN EDITOR"))
    print(f"  {breadcrumb('Hauptmenü', 'Item-Scan', 'Icon-Scans')}")

    if not PILLOW_AVAILABLE:
        print(f"\n{err('Pillow nicht installiert!')}")
        print("         Installieren mit: pip install pillow")
        return

    available_scans = list_available_icon_scans()
    loaded_scans = []
    menu_options = ["Neuen Icon-Scan erstellen"]
    for name, path in available_scans:
        config = load_icon_scan_file(path)
        if config:
            loaded_scans.append(config)
            menu_options.append(str(config))
        else:
            print(warn(f"Icon-Scan '{name}' ({path.name}) konnte nicht geladen werden — fehlt im Menü!"))

    choice = interactive_select(menu_options, title="\nWas möchtest du tun?")

    if choice == -1:
        print(f"{col('[ABBRUCH]', 'yellow')} Editor beendet.")
        return
    elif choice == 0:
        edit_icon_scan(state, None)
    elif 1 <= choice < len(menu_options):
        edit_icon_scan(state, loaded_scans[choice - 1])


def _select_icon_action(state: AutoClickerState,
                        existing: Optional[IconScanConfig] = None) -> Optional[dict]:
    """Fragt die Aktion ab, die bei erkanntem Icon ausgeführt wird."""
    action_options = [
        "Punkt klicken (z.B. Ablehnen-Button)",
        "Taste drücken",
        "Schritt überspringen (nur erkennen)",
        "Zyklus überspringen",
        "Sequenz neustarten",
    ]
    action_map = [
        ICON_ACTION_CLICK, ICON_ACTION_KEY, ICON_ACTION_SKIP,
        ICON_ACTION_SKIP_CYCLE, ICON_ACTION_RESTART,
    ]

    default_idx = 0
    if existing:
        try:
            default_idx = action_map.index(existing.action)
        except ValueError:
            pass

    choice = interactive_select(action_options, title="\nAktion wenn das Icon erkannt wird:",
                                default=default_idx)
    if choice == -1:
        return None

    action = action_map[choice]
    result = {
        "action": action,
        "action_point_id": None,
        "action_key": None,
        "action_delay": 0,
    }

    if action == ICON_ACTION_CLICK:
        print("\n  Bewege die Maus zum Klick-Punkt und drücke Enter...")
        try:
            safe_input()
            x, y = get_cursor_pos()
            # Die Stelle wird ein Punkt, gespeichert wird nur seine ID. Sonst haette
            # dieser Klick eine Koordinate, die weder eine Reparatur im Punkte-Menue
            # noch eine Kalibrierung ueber die Punkte je erreicht.
            with state.lock:
                pid = punkt_fuer_stelle(state, x, y, None, "Icon-Scan Klick",
                                        source="Icon-Scan-Editor")
            result["action_point_id"] = pid
            print(f"  → Klick-Position: ({x}, {y})  [Punkt #{pid}]")
        except (KeyboardInterrupt, EOFError):
            return None

    elif action == ICON_ACTION_KEY:
        key = prompt_key()
        if key is None:
            return None
        result["action_key"] = key

    # Delay vor Aktion (nicht bei reinem Skip/Cycle/Restart sinnvoll, aber harmlos)
    if action in (ICON_ACTION_CLICK, ICON_ACTION_KEY):
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


def edit_icon_scan(state: AutoClickerState, existing: Optional[IconScanConfig]) -> None:
    """Erstellt oder bearbeitet eine Icon-Scan Konfiguration."""
    if existing:
        print(f"\n--- Bearbeite Icon-Scan: {existing.name} ---")
        scan_name = existing.name
        scan_region = existing.scan_region
        template = existing.template
        min_confidence = existing.min_confidence
        marker_colors = list(existing.marker_colors)
        tolerance = existing.color_tolerance
    else:
        print("\n--- Neuen Icon-Scan erstellen ---")
        scan_name = safe_input("Name des Icon-Scans: ").strip()
        if is_cancel(scan_name):
            return
        if not scan_name:
            scan_name = f"IconScan_{int(time.time())}"
        scan_region = (0, 0, 100, 100)
        template = None
        min_confidence = state.config.scan_min_confidence
        marker_colors = []
        tolerance = IconScanConfig.color_tolerance

    # === SCHRITT 1: Scan-Region ===
    print(header("SCHRITT 1: SCAN-REGION (wo erscheint das Icon?)"))
    print("  Tipp: Region eng um das Icon legen — robuster fürs Template-Matching.")
    if existing:
        r = scan_region
        print(f"  Aktuelle Region: ({r[0]},{r[1]}) → ({r[2]},{r[3]})")

    new_region = select_scan_region(scan_region if existing else None)
    if new_region is None:
        if not existing:
            return  # Neu-Erstellung abgebrochen
        # Beim Bearbeiten: alte Region behalten
    else:
        scan_region = new_region

    # === SCHRITT 2: Erkennung (Template oder Marker) ===
    print(header("SCHRITT 2: ERKENNUNG"))
    detect_options = []
    if OPENCV_AVAILABLE:
        detect_options.append("Template-Bild aufnehmen")
    detect_options.append("Farb-Marker setzen")
    if existing and (existing.template or existing.marker_colors):
        detect_options.append("Bestehende Erkennung beibehalten")

    has_keep = "Bestehende Erkennung beibehalten" in detect_options
    detect_choice = interactive_select(detect_options, title="\nWie soll das Icon erkannt werden?",
                                       default=len(detect_options) - 1 if has_keep else 0)
    if detect_choice == -1:
        print(f"  {col('[ABBRUCH]', 'yellow')} Icon-Scan nicht gespeichert.")
        return

    chosen_label = detect_options[detect_choice]

    if chosen_label == "Template-Bild aufnehmen":
        img = take_screenshot(scan_region)
        if not img:
            print(f"  {err('Screenshot fehlgeschlagen!')}")
            return
        safe_name = sanitize_filename(f"icon_{scan_name}")
        template_file = f"{safe_name}.png"
        template_path = Path(TEMPLATES_DIR) / template_file
        template_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(template_path)
        template = template_file
        marker_colors = []
        print(f"  → Template gespeichert: {template_file}")
        try:
            conf_input = safe_input(f"  Min. Konfidenz % (Enter={int(min_confidence * 100)}): ").strip()
            if conf_input:
                min_confidence = max(0.1, min(1.0, float(conf_input) / 100))
        except ValueError:
            pass

    elif chosen_label == "Farb-Marker setzen":
        captured = capture_markers()
        if captured is None:
            return
        marker_colors = captured
        template = None

        try:
            tol_input = safe_input(f"  Farbtoleranz (Enter={tolerance}): ").strip()
            if tol_input:
                tolerance = max(1, min(100, int(tol_input)))
        except ValueError:
            pass

    # === SCHRITT 3: Aktion bei Fund ===
    print(header("SCHRITT 3: AKTION BEI ERKANNTEM ICON"))
    action_result = _select_icon_action(state, existing)
    if action_result is None:
        return

    config = IconScanConfig(
        name=scan_name,
        scan_region=scan_region,
        template=template,
        min_confidence=min_confidence,
        marker_colors=marker_colors,
        color_tolerance=tolerance,
        **action_result,
    )

    with state.lock:
        state.icon_scans[scan_name] = config

    save_icon_scan(config)

    save_msg = ok(f"Icon-Scan '{scan_name}' gespeichert!")
    print(f"\n{save_msg}")
    print(f"         Nutze im Sequenz-Editor: 'icon {scan_name}'")
