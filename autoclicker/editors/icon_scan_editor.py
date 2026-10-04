"""
Icon-Scan-Editor für den Autoclicker.

Ein Icon-Scan erkennt ein einzelnes Symbol/Icon (z.B. ein rotes "!" das eine
nicht machbare Mission markiert) per Template oder Farb-Marker in einer Region
und führt bei Fund eine Aktion aus (Klick / Taste / Zyklus überspringen / ...).
Bewusst schlank — kein Item-Sammeln, kein LLM.

Der Assistent läuft in Stufen (`_icon_draft` → `_step_region` →
`_step_detection` → `_select_icon_action` → `_save_icon_scan`); jede gibt bei
einem Abbruch None bzw. False zurück. Was er mit dem Boss-Editor teilt
(Erkennung, Aktion, Klickpunkt, Konfidenz, Toleranz), steht in
`_detection_capture.py`.
"""

import time
from dataclasses import dataclass, field
from typing import Optional

from ..models import (
    IconScanConfig, AutoClickerState,
    ICON_ACTION_CLICK, ICON_ACTION_KEY, ICON_ACTION_SKIP,
    ICON_ACTION_SKIP_CYCLE, ICON_ACTION_RESTART,
)
from ..utils import (
    safe_input, is_cancel, interactive_select,
    col, ok, err, warn, header, breadcrumb,
)
from ..imaging import PILLOW_AVAILABLE, take_screenshot
from ..persistence import save_icon_scan, list_available_icon_scans, load_icon_scan_file
from ._detection_capture import (
    DETECT_MARKERS, DETECT_TEMPLATE, ask_action_details, ask_min_confidence,
    ask_tolerance, capture_markers, choose_detection, select_action,
    select_scan_region, store_template,
)

_ICON_ACTIONS = [
    ("Punkt klicken (z.B. Ablehnen-Button)", ICON_ACTION_CLICK),
    ("Taste drücken", ICON_ACTION_KEY),
    ("Schritt überspringen (nur erkennen)", ICON_ACTION_SKIP),
    ("Zyklus überspringen", ICON_ACTION_SKIP_CYCLE),
    ("Sequenz neustarten", ICON_ACTION_RESTART),
]


def run_icon_scan_editor(state: AutoClickerState) -> None:
    """Hauptmenü für Icon-Scan Konfiguration."""
    print(header("ICON-SCAN EDITOR"))
    print(f"  {breadcrumb('Hauptmenü', 'Item-Scan', 'Icon-Scans')}")

    if not PILLOW_AVAILABLE:
        print(f"\n{err('Pillow nicht installiert!')}")
        print("         Installieren mit: pip install pillow")
        return

    owner = state.active_sequence.name if state.active_sequence else ""
    available_scans = list_available_icon_scans(owner)
    loaded_scans = []
    menu_options = ["Neuen Icon-Scan erstellen"]
    for name, path in available_scans:
        config = load_icon_scan_file(path, owner)
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
    action = select_action(_ICON_ACTIONS, "\nAktion wenn das Icon erkannt wird:",
                           existing.action if existing else None)
    if action is None:
        return None
    result = {
        "action": action,
        "action_point_id": None,
        "action_key": None,
        "action_delay": 0,
    }
    # Eine Verzögerung gibt es nur vor etwas, das selbst eine Wirkung hat.
    if not ask_action_details(state, action, result, "Icon-Scan Klick", "Icon-Scan-Editor",
                              with_delay=action in (ICON_ACTION_CLICK, ICON_ACTION_KEY)):
        return None
    return result


@dataclass
class _IconDraft:
    """Was der Assistent bis zum Speichern zusammenträgt."""
    name: str
    region: tuple
    template: Optional[str]
    min_confidence: float
    marker_colors: list = field(default_factory=list)
    tolerance: int = IconScanConfig.color_tolerance


def edit_icon_scan(state: AutoClickerState, existing: Optional[IconScanConfig]) -> None:
    """Erstellt oder bearbeitet eine Icon-Scan Konfiguration."""
    draft = _icon_draft(state, existing)
    if draft is None or not _step_region(draft, existing):
        return
    if not _step_detection(state, draft, existing):
        return
    print(header("SCHRITT 3: AKTION BEI ERKANNTEM ICON"))
    action_result = _select_icon_action(state, existing)
    if action_result is None:
        return
    _save_icon_scan(state, draft, action_result)


def _icon_draft(state: AutoClickerState,
                existing: Optional[IconScanConfig]) -> Optional[_IconDraft]:
    """Der Ausgangsstand: der bestehende Scan oder ein neuer mit Namen. None = Abbruch."""
    if existing:
        print(f"\n--- Bearbeite Icon-Scan: {existing.name} ---")
        return _IconDraft(existing.name, existing.scan_region, existing.template,
                          existing.min_confidence, list(existing.marker_colors),
                          existing.color_tolerance)
    print("\n--- Neuen Icon-Scan erstellen ---")
    name = safe_input("Name des Icon-Scans: ").strip()
    if is_cancel(name):
        return None
    return _IconDraft(name or f"IconScan_{int(time.time())}", (0, 0, 100, 100), None,
                      state.config.scan_min_confidence)


def _step_region(draft: _IconDraft, existing: Optional[IconScanConfig]) -> bool:
    """SCHRITT 1. Ohne neue Region bleibt beim Bearbeiten die alte; beim Anlegen = Abbruch."""
    print(header("SCHRITT 1: SCAN-REGION (wo erscheint das Icon?)"))
    print("  Tipp: Region eng um das Icon legen — robuster fürs Template-Matching.")
    if existing:
        r = draft.region
        print(f"  Aktuelle Region: ({r[0]},{r[1]}) → ({r[2]},{r[3]})")
    new_region = select_scan_region(draft.region if existing else None)
    if new_region is not None:
        draft.region = new_region
        return True
    return existing is not None


def _step_detection(state: AutoClickerState, draft: _IconDraft,
                    existing: Optional[IconScanConfig]) -> bool:
    """SCHRITT 2: Template aus der Region oder Farb-Marker. False = Abbruch."""
    print(header("SCHRITT 2: ERKENNUNG"))
    detection = choose_detection(
        "\nWie soll das Icon erkannt werden?",
        bool(existing and (existing.template or existing.marker_colors)))
    if detection is None:
        print(f"  {col('[ABBRUCH]', 'yellow')} Icon-Scan nicht gespeichert.")
        return False

    if detection == DETECT_TEMPLATE:
        img = take_screenshot(draft.region)
        if not img:
            print(f"  {err('Screenshot fehlgeschlagen!')}")
            return False
        draft.template = store_template(state, img, f"icon_{draft.name}")
        draft.marker_colors = []
        draft.min_confidence = ask_min_confidence(draft.min_confidence)
    elif detection == DETECT_MARKERS:
        captured = capture_markers()
        if captured is None:
            return False
        draft.marker_colors, draft.template = captured, None
        draft.tolerance = ask_tolerance(f"  Farbtoleranz (Enter={draft.tolerance}): ",
                                        draft.tolerance)
    return True


def _save_icon_scan(state: AutoClickerState, draft: _IconDraft, action_result: dict) -> None:
    config = IconScanConfig(
        name=draft.name,
        scan_region=draft.region,
        template=draft.template,
        min_confidence=draft.min_confidence,
        marker_colors=draft.marker_colors,
        color_tolerance=draft.tolerance,
        owner_sequence=state.active_sequence.name if state.active_sequence else "",
        **action_result,
    )
    with state.lock:
        state.icon_scans[draft.name] = config

    # Dieselbe Regel wie im Boss-Editor: der Saver meldet den Fehler, und darunter
    # darf kein „gespeichert!" stehen.
    if not save_icon_scan(config):
        print(err("Icon-Scan nicht gespeichert; Änderungen bleiben im Arbeitsspeicher."))
        return
    save_msg = ok(f"Icon-Scan '{draft.name}' gespeichert!")
    print(f"\n{save_msg}")
    print(f"         Nutze im Sequenz-Editor: 'icon {draft.name}'")
