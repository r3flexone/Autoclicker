"""
Auto-Scan-Befehl: scannt automatisch ALLE Slots und legt Items mit
Templates + Marker-Farben an. Nur Kategorie und Bestätigungs-Punkt werden
einmal abgefragt — alles andere passiert automatisch. Namen können danach
mit dem rename-Befehl angepasst werden.
"""

from pathlib import Path

from ...config import CONFIG
from ...imaging import OPENCV_AVAILABLE, take_screenshot
from ...models import ItemProfile, AutoClickerState
from ...persistence import (
    get_point_by_id, save_global_items, TEMPLATES_DIR,
)
from ...utils import (
    col, confirm, err, header, hint, parse_non_negative_float, safe_input,
    sanitize_filename,
)
from .items import select_category
from .markers import _collect_markers_silent, _find_matching_existing_item


def item_autoscan_command(state: AutoClickerState, user_input: str) -> bool:
    """Scannt automatisch ALLE Slots und erstellt Items mit Templates + Marker-Farben.

    Unterstützte Modi:
        autoscan          - Mit Templates + Marker-Farben (empfohlen)
        autoscan nocolor  - Nur Templates, keine Marker-Farben
    """
    with state.lock:
        slot_list = list(state.global_slots.values())

    if not slot_list:
        print(f"  -> {err('Keine Slots vorhanden!')} Erst Slots mit 'auto' im Slot-Editor erstellen.")
        return True

    if not OPENCV_AVAILABLE:
        print(f"  -> {err('OpenCV nicht installiert!')} (pip install opencv-python)")
        print("       OpenCV wird für Template-Matching benötigt.")
        return True

    # Modus parsen
    args = user_input[8:].strip().lower()  # nach "autoscan"
    use_markers = args != "nocolor"
    mode_str = "Templates + Marker" if use_markers else "nur Templates"

    print(header(f"AUTO-SCAN: {len(slot_list)} Slots ({mode_str})"))
    print(f"\n  Scannt automatisch alle {len(slot_list)} Slots und erstellt Items.")
    print("  Namen können danach mit 'rename <Nr>' angepasst werden.\n")

    settings = _collect_autoscan_settings(state, slot_list, use_markers)
    if settings is None:
        return True

    _run_autoscan(state, slot_list, settings)
    return True


def _collect_autoscan_settings(state: AutoClickerState, slot_list: list,
                                use_markers: bool) -> dict | None:
    """Fragt die einmaligen Einstellungen für den Auto-Scan ab.

    Returns None wenn der User abbricht, sonst ein Dict mit den Settings.
    """
    # Kategorie
    print("  Kategorie für ALLE Items (Enter = keine):")
    category = select_category(state, show_explanation=False)

    # Prioritäts-Modus
    print("\n  Prioritäts-Vergabe:")
    print("    [1] Automatisch (Slot-Reihenfolge: P1, P2, P3, ... - frühere Slots bevorzugt)")
    print("    [2] Alle gleich (P1 - erstgefundenes Item je Kategorie gewinnt)")
    print(f"       {col('Hinweis:', 'yellow')} Bei gleicher Priorität + gleicher Kategorie entscheidet die Scan-Reihenfolge.")
    prio_choice = safe_input("  Wahl (Enter = 1): ").strip()
    auto_priority = prio_choice != "2"

    # Bestätigungs-Punkt
    confirm_point_id = None
    confirm_delay = CONFIG.scan_confirm_delay
    confirm_input = safe_input("\n  Bestätigungs-Punkt-ID für alle Items (Enter = keiner): ").strip()
    if confirm_input:
        try:
            point_id = int(confirm_input)
            found_point = get_point_by_id(state, point_id)
            if found_point:
                confirm_point_id = point_id
                delay_input = safe_input(f"  Wartezeit vor Bestätigung (Enter = {confirm_delay}s): ").strip()
                if delay_input:
                    delay_val, delay_err = parse_non_negative_float(delay_input, "Wartezeit")
                    if delay_err:
                        print(f"  -> {delay_err}, behalte {confirm_delay}s")
                    else:
                        confirm_delay = delay_val
            else:
                print(f"  -> Punkt #{point_id} existiert nicht, überspringe")
        except ValueError:
            pass

    # Konfidenz
    min_confidence = state.config.scan_min_confidence
    try:
        conf_input = safe_input(f"\n  Min. Konfidenz % für alle (Enter = {int(min_confidence * 100)}): ").strip()
        if conf_input:
            min_confidence = max(0.1, min(1.0, float(conf_input) / 100))
    except ValueError:
        pass

    # Bestätigung
    print("\n  --- Zusammenfassung ---")
    print(f"  Slots:       {len(slot_list)}")
    print(f"  Kategorie:   {category or '(keine)'}")
    print(f"  Priorität:   {'automatisch (1,2,3,...)' if auto_priority else 'alle gleich (1)'}")
    print(f"  Konfidenz:   {min_confidence:.0%}")
    if confirm_point_id:
        print(f"  Bestätigung: Punkt #{confirm_point_id} nach {confirm_delay}s")
    else:
        print("  Bestätigung: keine")
    print(f"  Marker:      {'Ja' if use_markers else 'Nein'}")

    if not confirm("\n  Starten?"):
        print("  -> Abgebrochen")
        return None

    return {
        "category": category,
        "auto_priority": auto_priority,
        "confirm_point_id": confirm_point_id,
        "confirm_delay": confirm_delay,
        "min_confidence": min_confidence,
        "use_markers": use_markers,
    }


def item_autoscan_from_image(state: AutoClickerState, slot_list: list,
                             source_img, region_origin: tuple) -> None:
    """Lernt Items für die gegebenen Slots aus EINEM bereits aufgenommenen Bild.

    Wird vom Slot-Editor genutzt, damit Slots UND Items aus demselben Screenshot
    gelernt werden können. Die Template-Bilder werden aus source_img geschnitten
    (statt pro Slot neu zu screenshotten), region_origin = (offset_x, offset_y)
    ist der Bild-Ursprung in absoluten Bildschirm-Koordinaten.
    """
    if not slot_list:
        print(f"  -> {err('Keine Slots zum Lernen!')}")
        return
    if not OPENCV_AVAILABLE:
        print(f"  -> {err('OpenCV nicht installiert!')} (pip install opencv-python)")
        return

    print(header(f"ITEMS LERNEN: {len(slot_list)} Slots (aus demselben Screenshot)"))
    settings = _collect_autoscan_settings(state, slot_list, use_markers=True)
    if settings is None:
        return
    _run_autoscan(state, slot_list, settings, source_img=source_img,
                  region_origin=region_origin)


def _crop_slot_template(slot, source_img, region_origin):
    """Schneidet die Slot-Region aus dem Quellbild (lokale Koordinaten)."""
    ox, oy = region_origin
    x1, y1, x2, y2 = slot.scan_region
    return source_img.crop((x1 - ox, y1 - oy, x2 - ox, y2 - oy))


def _run_autoscan(state: AutoClickerState, slot_list: list, settings: dict,
                  source_img=None, region_origin: tuple = None) -> None:
    """Führt den eigentlichen Auto-Scan-Loop aus.

    Wenn source_img + region_origin gesetzt sind, werden die Templates aus diesem
    Bild geschnitten (gleicher Screenshot wie die Slot-Erkennung); sonst wird pro
    Slot ein frischer Screenshot gemacht.
    """
    use_markers = settings["use_markers"]
    category = settings["category"]
    auto_priority = settings["auto_priority"]
    confirm_point_id = settings["confirm_point_id"]
    confirm_delay = settings["confirm_delay"]
    min_confidence = settings["min_confidence"]

    print(f"\n  === SCANNE {len(slot_list)} SLOTS ===\n")

    # Bestehende Items mit Templates sammeln (für Duplikat-Erkennung)
    with state.lock:
        existing_templates = [
            (name, item) for name, item in state.global_items.items()
            if item.template
        ]

    if existing_templates:
        print(f"  ({len(existing_templates)} bestehende Items werden zum Vergleich genutzt)\n")

    created_count = 0
    skipped_count = 0
    duplicate_count = 0
    created_names: list[str] = []  # für optionale LLM-Benennung am Schluss

    for idx, slot in enumerate(slot_list):
        slot_num = idx + 1
        priority = slot_num if auto_priority else 1

        print(f"  [{slot_num}/{len(slot_list)}] {slot.name}...", end=" ", flush=True)

        if source_img is not None and region_origin is not None:
            try:
                template_img = _crop_slot_template(slot, source_img, region_origin)
            except (ValueError, OSError):
                template_img = None
        else:
            template_img = take_screenshot(slot.scan_region)
        if template_img is None:
            print("FEHLER (Screenshot)")
            skipped_count += 1
            continue

        # Gegen bestehende Item-Templates vergleichen (Duplikat-Prüfung)
        matched_item = _find_matching_existing_item(template_img, existing_templates, min_confidence)
        if matched_item:
            print(f"BEREITS VORHANDEN -> '{matched_item}' (übersprungen)")
            duplicate_count += 1
            continue

        # Neuen Item-Namen vergeben (eindeutig)
        item_name = f"{slot.name} Item"
        base_name = item_name
        counter = 1
        with state.lock:
            while item_name in state.global_items:
                counter += 1
                item_name = f"{base_name} {counter}"

        # Template speichern
        safe_name = sanitize_filename(item_name)
        template_file = f"{safe_name}.png"
        template_path = Path(TEMPLATES_DIR) / template_file
        template_path.parent.mkdir(parents=True, exist_ok=True)
        template_img.save(template_path)

        # Marker-Farben sammeln (optional, leise)
        marker_colors = []
        if use_markers:
            marker_colors = _collect_markers_silent(template_img, slot.slot_color)

        item = ItemProfile(
            name=item_name,
            marker_colors=marker_colors,
            category=category,
            priority=priority,
            confirm_point_id=confirm_point_id,
            confirm_delay=confirm_delay,
            template=template_file,
            min_confidence=min_confidence
        )

        with state.lock:
            state.global_items[item_name] = item
        created_count += 1
        created_names.append(item_name)

        existing_templates.append((item_name, item))

        marker_str = f" + {len(marker_colors)} Marker" if marker_colors else ""
        print(f"NEU -> '{item_name}' (P{priority}){marker_str}")

    if created_count > 0:
        save_global_items(state)

    print(f"\n  === FERTIG: {created_count} neu erstellt", end="")
    if duplicate_count > 0:
        print(f", {duplicate_count} Duplikat(e) übersprungen", end="")
    if skipped_count > 0:
        print(f", {skipped_count} fehlgeschlagen", end="")
    print(" ===")

    # Optionale LLM-Benennung — hier (Setup, kein Zeitdruck) ist das ok, im
    # laufenden Scan dagegen nicht (würde den Worker blockieren).
    if created_names and state.config.llm_enabled:
        print(f"\n  {len(created_names)} neue Item(s) könnten per LLM benannt werden "
              f"{hint('(kann je Item ein paar Sekunden dauern)')}.")
        if confirm("  Jetzt per LLM benennen?", default=True):
            from .commands import llm_name_items
            with state.lock:
                targets = [(n, state.global_items[n].template) for n in created_names
                           if n in state.global_items and state.global_items[n].template]
            renamed = llm_name_items(state, targets)
            if renamed:
                save_global_items(state)
            print(f"  -> {renamed} Item(s) benannt.")

    print("\n  Tipp: 'rename <Nr>' zum Umbenennen, 'autoname' für LLM-Benennung, 'show' zum Anzeigen")
    print("        'save <Name>' zum Speichern als Preset")
