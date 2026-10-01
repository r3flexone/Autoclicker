"""
Auto-Scan-Befehl: scannt automatisch ALLE Slots und legt Items mit
Templates + Marker-Farben an. Nur Kategorie und Bestätigungs-Punkt werden
einmal abgefragt — alles andere passiert automatisch. Namen können danach
mit dem rename-Befehl angepasst werden.
"""


from collections import Counter

from ...config import CONFIG
from ...imaging import OPENCV_AVAILABLE, take_screenshot
from ...models import ItemProfile, AutoClickerState
from ...persistence import save_global_items, active_templates_dir, free_template_file
from ...utils import (
    col, confirm, err, header, hint, safe_input, unique_name,
)
from .._item_fields import ask_confirm_click
from ..scan_services import crop_screen_region
from .items import select_category
from .markers import (
    _collect_markers_silent, _find_matching_existing_item,
    _item_has_compatible_template,
)


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
    confirm_point_id, confirm_delay = ask_confirm_click(
        state, CONFIG.scan_confirm_delay,
        prompt="\n  Bestätigungs-Punkt-ID für alle Items (Enter = keiner): ")

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
    return crop_screen_region(source_img, slot.scan_region, region_origin)


def _run_autoscan(state: AutoClickerState, slot_list: list, settings: dict,
                  source_img=None, region_origin: tuple = None) -> None:
    """Führt den eigentlichen Auto-Scan-Loop aus.

    Wenn source_img + region_origin gesetzt sind, werden die Templates aus diesem
    Bild geschnitten (gleicher Screenshot wie die Slot-Erkennung); sonst wird pro
    Slot ein frischer Screenshot gemacht.
    """
    print(f"\n  === SCANNE {len(slot_list)} SLOTS ===\n")

    # Bestehende Items mit Templates sammeln (für Duplikat-Erkennung)
    with state.lock:
        existing_templates = [
            (name, item) for name, item in state.global_items.items()
            if item.template_names()
        ]
    if existing_templates:
        print(f"  ({len(existing_templates)} bestehende Items werden zum Vergleich genutzt)\n")

    counts = Counter()
    created_names: list[str] = []  # für optionale LLM-Benennung am Schluss
    for idx, slot in enumerate(slot_list):
        print(f"  [{idx + 1}/{len(slot_list)}] {slot.name}...", end=" ", flush=True)
        template_img = _slot_image(slot, source_img, region_origin)
        if template_img is None:
            print("FEHLER (Screenshot)")
            counts["failed"] += 1
            continue
        known = _known_slot(state, template_img, existing_templates, settings["min_confidence"])
        if known:
            counts[known] += 1
            continue
        item = _new_autoscan_item(state, slot, template_img, idx + 1, settings)
        existing_templates.append((item.name, item))
        created_names.append(item.name)

    if created_names or counts["variant"]:
        save_global_items(state)
    _print_autoscan_summary(len(created_names), counts)
    _offer_llm_names(state, created_names)

    print("\n  Tipp: 'rename <Nr>' zum Umbenennen, 'autoname' für LLM-Benennung, 'show' zum Anzeigen")
    print("        'save <Name>' zum Speichern als Preset")


def _slot_image(slot, source_img, region_origin):
    """Der Slot als Bild: aus dem gemeinsamen Screenshot geschnitten oder neu aufgenommen."""
    if source_img is not None and region_origin is not None:
        try:
            return _crop_slot_template(slot, source_img, region_origin)
        except (ValueError, OSError):
            return None
    return take_screenshot(slot.scan_region)


def _store_template(state: AutoClickerState, img, base_name: str) -> str:
    """Legt `img` unter einem freien Dateinamen im Vorlagenordner ab."""
    template_file = free_template_file(active_templates_dir(state), base_name)
    template_path = active_templates_dir(state) / template_file
    template_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(template_path)
    return template_file


def _known_slot(state: AutoClickerState, img, existing: list, min_confidence: float):
    """Kennt der Bestand den Slot-Inhalt schon? "duplicate", "variant" oder None.

    Der Vorlagenordner MUSS mitgegeben werden — in BEIDE Prüfungen: ohne ihn
    faellt `_template_path()` auf den globalen `items/templates/` zurueck, den
    es seit dem Umzug auf Besitzeinheiten nicht mehr gibt. Bei der Suche selbst
    fehlte er: sie fand nie ein Duplikat, und ein zweiter `autoscan` legte jedes
    Item ein zweites Mal an.
    """
    folder = active_templates_dir(state)
    matched = _find_matching_existing_item(img, existing, min_confidence, folder)
    if not matched:
        return None
    with state.lock:
        item = state.global_items.get(matched)
    if item is None or _item_has_compatible_template(item, img, folder):
        print(f"BEREITS VORHANDEN -> '{matched}' (übersprungen)")
        return "duplicate"
    width, height = img.size
    template_file = _store_template(state, img, f"{matched}_{width}x{height}")
    with state.lock:
        item.template_variants.append(template_file)
    print(f"VARIANTE -> '{matched}' kann jetzt auch {width}x{height}-Slots")
    return "variant"


def _new_autoscan_item(state: AutoClickerState, slot, img, slot_num: int,
                       settings: dict) -> ItemProfile:
    """Legt für einen unbekannten Slot-Inhalt ein Item samt Vorlage an."""
    priority = slot_num if settings["auto_priority"] else 1
    with state.lock:
        item_name = unique_name(f"{slot.name} Item", state.global_items)
    template_file = _store_template(state, img, item_name)
    marker_colors = (_collect_markers_silent(img, slot.slot_color)
                     if settings["use_markers"] else [])
    item = ItemProfile(
        name=item_name,
        marker_colors=marker_colors,
        category=settings["category"],
        priority=priority,
        confirm_point_id=settings["confirm_point_id"],
        confirm_delay=settings["confirm_delay"],
        template=template_file,
        min_confidence=settings["min_confidence"],
    )
    with state.lock:
        state.global_items[item_name] = item
    marker_str = f" + {len(marker_colors)} Marker" if marker_colors else ""
    print(f"NEU -> '{item_name}' (P{priority}){marker_str}")
    return item


def _print_autoscan_summary(created: int, counts: Counter) -> None:
    parts = [f"{created} neu erstellt"]
    for key, label in (("duplicate", "Duplikat(e) übersprungen"),
                       ("variant", "Grössenvariante(n) ergänzt"),
                       ("failed", "fehlgeschlagen")):
        if counts[key]:
            parts.append(f"{counts[key]} {label}")
    print(f"\n  === FERTIG: {', '.join(parts)} ===")


def _offer_llm_names(state: AutoClickerState, created_names: list) -> None:
    """Optionale LLM-Benennung der neuen Items.

    Hier (Setup, kein Zeitdruck) ist das ok, im laufenden Scan dagegen nicht —
    es würde den Worker je Item bis `llm_timeout` blockieren.
    """
    if not created_names or not state.config.llm_enabled:
        return
    print(f"\n  {len(created_names)} neue Item(s) könnten per LLM benannt werden "
          f"{hint('(kann je Item ein paar Sekunden dauern)')}.")
    if not confirm("  Jetzt per LLM benennen?", default=True):
        return
    from .commands import llm_name_items
    with state.lock:
        targets = [(n, state.global_items[n].template) for n in created_names
                   if n in state.global_items and state.global_items[n].template]
    renamed = llm_name_items(state, targets)
    if renamed:
        save_global_items(state)
    print(f"  -> {renamed} Item(s) benannt.")
