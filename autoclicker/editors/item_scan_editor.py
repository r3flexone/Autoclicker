"""
Item-Scan-Editor für den Autoclicker.
Ermöglicht das Erstellen und Bearbeiten von Item-Scan-Konfigurationen.
"""

import time
from pathlib import Path
from typing import Optional

from ..models import ClickPoint, ItemSlot, ItemProfile, ItemScanConfig, AutoClickerState
from ..config import CONFIG, DEFAULT_MIN_CONFIDENCE
from ..utils import safe_input, sanitize_filename, is_cancel, confirm, interactive_select, col, ok, err, info, hint, header, breadcrumb, suggest_command, cancel_hint, parse_non_negative_float
from ..winapi import get_cursor_pos
from ..imaging import (
    PILLOW_AVAILABLE, OPENCV_AVAILABLE, take_screenshot, get_pixel_color,
    select_region, get_color_name
)
from ..persistence import (
    save_item_scan, list_available_item_scans, load_item_scan_file,
    list_slot_presets, load_slot_preset, list_item_presets, load_item_preset,
    save_global_items, get_existing_categories, shift_category_priorities,
    get_point_by_id, TEMPLATES_DIR
)
from .slot_editor import run_global_slot_editor
from .item_editor import run_global_item_editor, select_category
from .boss_scan_editor import run_boss_scan_editor



def run_item_scan_menu(state: AutoClickerState) -> None:
    """Hauptmenü für Item-Scan Konfiguration (Slots, Items, Scans)."""
    print(header("ITEM-SCAN MENÜ"))
    print(f"  {breadcrumb('Hauptmenü', 'Item-Scan')}")

    with state.lock:
        slot_count = len(state.global_slots)
        item_count = len(state.global_items)
        scan_count = len(state.item_scans)
        boss_count = len(state.boss_scans)

    menu_options = [
        f"Slots bearbeiten     ({slot_count} vorhanden)",
        f"Items bearbeiten     ({item_count} vorhanden)",
        f"Scans bearbeiten     ({scan_count} vorhanden)",
        f"Boss-Scans bearbeiten ({boss_count} vorhanden)",
    ]

    choice = interactive_select(menu_options)

    if choice == 0:
        run_global_slot_editor(state)
    elif choice == 1:
        run_global_item_editor(state)
    elif choice == 2:
        run_item_scan_editor(state)
    elif choice == 3:
        run_boss_scan_editor(state)


def run_item_scan_editor(state: AutoClickerState) -> None:
    """Interaktiver Editor für Item-Scan Konfigurationen (verknüpft Slots + Items)."""
    print(header("SCAN-EDITOR (Slots + Items verknüpfen)"))
    print(f"  {breadcrumb('Hauptmenü', 'Item-Scan', 'Scans')}")

    if not PILLOW_AVAILABLE:
        print(f"\n{err('Pillow nicht installiert!')}")
        print("         Installieren mit: pip install pillow")
        return

    # Bestehende Item-Scans einmal laden und cachen
    available_scans = list_available_item_scans()
    loaded_scans = []
    menu_options = ["Neuen Item-Scan erstellen"]
    for name, path in available_scans:
        config = load_item_scan_file(path)
        if config:
            loaded_scans.append(config)
            menu_options.append(str(config))

    if available_scans:
        print("  (Tipp: 'del <Nr>' im Textmodus zum Löschen)")

    choice = interactive_select(menu_options, title="\nWas möchtest du tun?")

    if choice == -1:
        print(f"{col('[CANCEL]', 'yellow')} Editor beendet.")
        return
    elif choice == 0:
        edit_item_scan(state, None)
    elif 1 <= choice < len(menu_options):
        edit_item_scan(state, loaded_scans[choice - 1])


def edit_item_scan(state: AutoClickerState, existing: Optional[ItemScanConfig]) -> None:
    """Bearbeitet eine Item-Scan Konfiguration (verknüpft globale Slots + Items)."""

    # === SCHRITT 0: Presets auswählen (nur wenn welche existieren) ===
    slot_presets = list_slot_presets()
    item_presets = list_item_presets()

    if slot_presets or item_presets:
        print(header("PRESETS AUSWÄHLEN"))

        with state.lock:
            cur_slots = len(state.global_slots)
            cur_items = len(state.global_items)

        # Slot-Presets (nur anzeigen wenn welche existieren)
        if slot_presets:
            print("\nSlot-Presets:")
            for i, (name, path, count) in enumerate(slot_presets):
                print(f"  [{i+1}] {name} ({count} Slots)")
            print(f"  [0] Aktuelle Slots verwenden ({cur_slots} geladen)")

            while True:
                try:
                    slot_choice = safe_input("\nSlot-Preset wählen (Enter=0, 'cancel'): ").strip()
                    if is_cancel(slot_choice):
                        print("  -> Abgebrochen")
                        return
                    if not slot_choice or slot_choice == "0":
                        break
                    slot_num = int(slot_choice)
                    if 1 <= slot_num <= len(slot_presets):
                        preset_name, _, _ = slot_presets[slot_num - 1]
                        load_slot_preset(state, preset_name)
                        break
                    else:
                        print(f"  -> Ungültig! 0-{len(slot_presets)}")
                except ValueError:
                    print("  -> Bitte eine Nummer eingeben!")
                except (KeyboardInterrupt, EOFError):
                    return

        # Item-Presets (nur anzeigen wenn welche existieren)
        if item_presets:
            print("\nItem-Presets:")
            for i, (name, path, count) in enumerate(item_presets):
                print(f"  [{i+1}] {name} ({count} Items)")
            print(f"  [0] Aktuelle Items verwenden ({cur_items} geladen)")

            while True:
                try:
                    item_choice = safe_input("\nItem-Preset wählen (Enter=0, 'cancel'): ").strip()
                    if is_cancel(item_choice):
                        print("  -> Abgebrochen")
                        return
                    if not item_choice or item_choice == "0":
                        break
                    item_num = int(item_choice)
                    if 1 <= item_num <= len(item_presets):
                        preset_name, _, _ = item_presets[item_num - 1]
                        load_item_preset(state, preset_name)
                        break
                    else:
                        print(f"  -> Ungültig! 0-{len(item_presets)}")
                except ValueError:
                    print("  -> Bitte eine Nummer eingeben!")
                except (KeyboardInterrupt, EOFError):
                    return

    # Prüfe ob globale Slots vorhanden sind
    with state.lock:
        available_slots = dict(state.global_slots)
        available_items = dict(state.global_items)

    if not available_slots:
        print(f"\n{err('Keine Slots im gewählten Preset!')}")
        print("         Erstelle zuerst Slots im Slot-Editor (Option 1)")
        return

    # Items sind optional - können im Scan-Editor erstellt werden
    if not available_items:
        print(f"\n{info('Keine Items im gewählten Preset.')}")
        print("       Du kannst sie gleich per Template erstellen!")

    if existing:
        print(f"\n--- Bearbeite Scan: {existing.name} ---")
        scan_name = existing.name
        selected_slot_names = [s.name for s in existing.slots]
        selected_item_names = [i.name for i in existing.items]
        tolerance = existing.color_tolerance
    else:
        print("\n--- Neuen Scan erstellen ---")
        scan_name = safe_input("Name des Scans: ").strip()
        if not scan_name:
            scan_name = f"Scan_{int(time.time())}"
        selected_slot_names = []
        selected_item_names = []
        tolerance = 40

    # Schritt 1: Slots auswählen
    print(header("SCHRITT 1: SLOTS AUSWÄHLEN"))
    print("\nVerfügbare Slots:")
    slot_list = list(available_slots.keys())
    for i, name in enumerate(slot_list):
        selected = "X" if name in selected_slot_names else " "
        print(f"  [{selected}] {i+1}. {available_slots[name]}")

    print(f"\nBefehle: '<Nr>', '<Von>-<Bis>' (z.B. 1-5), 'all', 'clear', 'show / s', 'done / d', 'cancel / {cancel_hint()}")
    while True:
        try:
            inp = safe_input("[Slots] > ").strip().lower()
            if inp in ("done", "d"):
                break
            elif is_cancel(inp):
                return
            elif inp == "all":
                selected_slot_names = list(slot_list)
                print(f"  + Alle {len(slot_list)} Slots ausgewählt")
            elif inp == "clear":
                selected_slot_names = []
                print("  + Auswahl gelöscht")
            elif inp in ("show", "s"):
                print(f"\nSlots ({len(selected_slot_names)}/{len(slot_list)} ausgewählt):")
                for i, name in enumerate(slot_list):
                    marker = "X" if name in selected_slot_names else " "
                    print(f"  [{marker}] {i+1}. {available_slots[name]}")
            elif "-" in inp:
                # Bereich: 1-5
                try:
                    parts = inp.split("-")
                    start = int(parts[0])
                    end = int(parts[1])
                    if 1 <= start <= len(slot_list) and 1 <= end <= len(slot_list):
                        for num in range(min(start, end), max(start, end) + 1):
                            name = slot_list[num - 1]
                            if name not in selected_slot_names:
                                selected_slot_names.append(name)
                        print(f"  + Slots {start}-{end} hinzugefügt")
                    else:
                        print(f"  -> Ungültig! 1-{len(slot_list)}")
                except (ValueError, IndexError):
                    print("  -> Format: <Von>-<Bis> (z.B. 1-5)")
            else:
                try:
                    num = int(inp)
                    if 1 <= num <= len(slot_list):
                        name = slot_list[num - 1]
                        if name in selected_slot_names:
                            selected_slot_names.remove(name)
                            print(f"  - {name} entfernt")
                        else:
                            selected_slot_names.append(name)
                            print(f"  + {name} hinzugefügt")
                    else:
                        print(f"  -> Ungültig! 1-{len(slot_list)}")
                except ValueError:
                    _known = ["done", "cancel", "all", "clear", "show"]
                    suggestion = suggest_command(inp, _known)
                    print(f"  -> Unbekannter Befehl.{suggestion}")
        except (KeyboardInterrupt, EOFError):
            return

    if not selected_slot_names:
        print(f"\n{err('Mindestens 1 Slot erforderlich!')}")
        return

    # Schritt 2: Items auswählen oder erstellen
    print(header("SCHRITT 2: ITEMS AUSWÄHLEN / ERSTELLEN"))

    # Zeige verfügbare Templates
    templates_dir = Path(TEMPLATES_DIR)
    templates = list(templates_dir.glob("*.png")) if templates_dir.exists() else []
    if templates:
        print(f"\nVerfügbare Templates ({len(templates)}):")
        for t in sorted(templates)[:10]:  # Max 10 anzeigen
            print(f"    {t.name}")
        if len(templates) > 10:
            print(f"    ... und {len(templates) - 10} weitere")

    # Aktualisiere available_items
    with state.lock:
        available_items = dict(state.global_items)

    print("\nVerfügbare Items:")
    item_list = list(available_items.keys())
    if item_list:
        for i, name in enumerate(item_list):
            selected = "X" if name in selected_item_names else " "
            print(f"  [{selected}] {i+1}. {available_items[name]}")
    else:
        print("  (Keine Items - erstelle welche mit 'new')")

    print("\n" + "-" * 40)
    print("Befehle:")
    print("  <Nr>              - Item auswählen/abwählen")
    print("  <Von>-<Bis>       - Bereich auswählen (z.B. 1-5)")
    print("  all | clear       - Alle auswählen / Auswahl löschen")
    print("  new <Slot-Nr>     - Neues Item per Template von Slot erstellen")
    print(f"  show / s | done / d | cancel / {cancel_hint()}")
    print("-" * 40)

    while True:
        try:
            inp = safe_input("[Items] > ").strip()
            inp_lower = inp.lower()

            if inp_lower in ("done", "d"):
                break
            elif is_cancel(inp_lower):
                return
            elif inp_lower == "all":
                selected_item_names = list(item_list)
                print(f"  + Alle {len(item_list)} Items ausgewählt")
            elif inp_lower == "clear":
                selected_item_names = []
                print("  + Auswahl gelöscht")
            elif inp_lower in ("show", "s"):
                print(f"\nItems ({len(selected_item_names)}/{len(item_list)} ausgewählt):")
                if item_list:
                    for i, name in enumerate(item_list):
                        marker = "X" if name in selected_item_names else " "
                        print(f"  [{marker}] {i+1}. {available_items[name]}")
                else:
                    print("  (Keine Items vorhanden)")

            elif inp_lower.startswith("new"):
                # Neues Item per Template erstellen
                if not OPENCV_AVAILABLE:
                    print("  -> OpenCV nicht installiert! (pip install opencv-python)")
                    continue

                # Slot-Nummer parsen
                slot_num = None
                if inp_lower.startswith("new "):
                    try:
                        slot_num = int(inp[4:])
                    except ValueError:
                        pass

                if slot_num is None:
                    print(f"\n  Von welchem Slot Screenshot machen? (1-{len(slot_list)})")
                    try:
                        slot_num = int(safe_input("  Slot-Nr: ").strip())
                    except ValueError:
                        print("  -> Ungültige Eingabe!")
                        continue

                if slot_num < 1 or slot_num > len(slot_list):
                    print(f"  -> Ungültiger Slot! Verfügbar: 1-{len(slot_list)}")
                    continue

                # Screenshot vom Slot machen
                slot_name = slot_list[slot_num - 1]
                slot = available_slots[slot_name]
                print(f"\n  Mache Screenshot von {slot_name}...")

                template_img = take_screenshot(slot.scan_region)
                if not template_img:
                    print("  -> Screenshot fehlgeschlagen!")
                    continue

                # Item-Name abfragen
                item_name = safe_input("  Item-Name: ").strip()
                if not item_name:
                    item_name = f"Item_{len(item_list) + 1}"

                # Prüfen ob Name schon existiert
                if item_name in available_items:
                    if not confirm(f"  '{item_name}' existiert bereits. Überschreiben?"):
                        print("  -> Abgebrochen")
                        continue
                    print(f"  -> '{item_name}' wird überschrieben")

                # Template speichern
                safe_name = sanitize_filename(item_name)
                template_file = f"{safe_name}.png"
                template_path = Path(TEMPLATES_DIR) / template_file
                template_path.parent.mkdir(parents=True, exist_ok=True)
                template_img.save(template_path)

                # Kategorie zuerst (für Prioritäts-Verschiebung)
                category = select_category(state)

                # Priorität
                priority = 1
                try:
                    prio_input = safe_input(f"  Priorität (1=beste, 0=beste+verschieben, Enter={priority}): ").strip()
                    if prio_input:
                        prio_val = int(prio_input)
                        if prio_val == 0:
                            if category:
                                shift_category_priorities(state, category)
                                priority = 1
                            else:
                                print("  -> Priorität 0 nur mit Kategorie möglich!")
                                priority = 1
                        else:
                            priority = max(1, prio_val)
                except ValueError:
                    pass

                # Konfidenz
                min_confidence = DEFAULT_MIN_CONFIDENCE
                try:
                    conf_input = safe_input(f"  Min. Konfidenz % (Enter={int(DEFAULT_MIN_CONFIDENCE * 100)}): ").strip()
                    if conf_input:
                        min_confidence = max(0.1, min(1.0, float(conf_input) / 100))
                except ValueError:
                    pass

                # Bestätigungs-Klick?
                confirm_point = None
                confirm_delay = CONFIG.default_confirm_delay
                confirm_input = safe_input("  Bestätigungs-Punkt ID (Enter=Nein): ").strip()
                if confirm_input:
                    try:
                        point_id = int(confirm_input)
                        with state.lock:
                            found_point = get_point_by_id(state, point_id)
                            if found_point:
                                confirm_point = ClickPoint(found_point.x, found_point.y)
                                delay_input = safe_input("  Wartezeit vor Bestätigung (Enter=0.5s): ").strip()
                                if delay_input:
                                    delay_val, delay_err = parse_non_negative_float(delay_input, "Wartezeit")
                                    if delay_err:
                                        print(f"  -> {delay_err}, behalte {confirm_delay}s")
                                    else:
                                        confirm_delay = delay_val
                            else:
                                print(f"  -> Punkt #{point_id} existiert nicht")
                    except ValueError:
                        pass

                # Item erstellen
                new_item = ItemProfile(
                    name=item_name,
                    marker_colors=[],
                    category=category,
                    priority=priority,
                    confirm_point=confirm_point,
                    confirm_delay=confirm_delay,
                    template=template_file,
                    min_confidence=min_confidence
                )

                # Global speichern
                with state.lock:
                    state.global_items[item_name] = new_item
                save_global_items(state)

                # Listen aktualisieren
                available_items[item_name] = new_item
                item_list.append(item_name)
                selected_item_names.append(item_name)

                cat_str = f" [{category}]" if category else ""
                print(f"  + Item '{item_name}'{cat_str} erstellt mit Template '{template_file}' ({min_confidence:.0%})")
                print(f"  + Automatisch zum Scan hinzugefügt")

            elif "-" in inp_lower and not inp_lower.startswith("new"):
                # Bereich: 1-5
                try:
                    parts = inp_lower.split("-")
                    start = int(parts[0])
                    end = int(parts[1])
                    if 1 <= start <= len(item_list) and 1 <= end <= len(item_list):
                        for num in range(min(start, end), max(start, end) + 1):
                            name = item_list[num - 1]
                            if name not in selected_item_names:
                                selected_item_names.append(name)
                        print(f"  + Items {start}-{end} hinzugefügt")
                    else:
                        print(f"  -> Ungültig! 1-{len(item_list)}")
                except (ValueError, IndexError):
                    print("  -> Format: <Von>-<Bis> (z.B. 1-5)")
            else:
                try:
                    num = int(inp)
                    if 1 <= num <= len(item_list):
                        name = item_list[num - 1]
                        if name in selected_item_names:
                            selected_item_names.remove(name)
                            print(f"  - {name} entfernt")
                        else:
                            selected_item_names.append(name)
                            print(f"  + {name} hinzugefügt")
                    else:
                        print(f"  -> Ungültig! 1-{len(item_list)}")
                except ValueError:
                    _known = ["done", "cancel", "all", "clear", "show", "new"]
                    suggestion = suggest_command(inp, _known)
                    print(f"  -> Unbekannter Befehl.{suggestion}")
        except (KeyboardInterrupt, EOFError):
            return

    if not selected_item_names:
        print(f"\n{info('Keine Items ausgewählt.')}")
        if not confirm("Trotzdem speichern?"):
            print(f"{col('[CANCEL]', 'yellow')} Scan nicht gespeichert.")
            return

    # Schritt 3: Toleranz
    print(header("SCHRITT 3: FARBTOLERANZ"))
    print(f"\nAktuelle Toleranz: {tolerance}")
    print("(Höher = mehr Farben werden als 'gleich' erkannt)")
    try:
        tol_input = safe_input(f"Neue Toleranz (Enter = {tolerance}): ").strip()
        if tol_input:
            tolerance = max(1, min(100, int(tol_input)))
    except ValueError:
        pass

    # Slots und Items aus globalen Definitionen holen
    with state.lock:
        slots = [state.global_slots[n] for n in selected_slot_names if n in state.global_slots]
        items = [state.global_items[n] for n in selected_item_names if n in state.global_items]

    # Speichern
    config = ItemScanConfig(
        name=scan_name,
        slots=slots,
        items=items,
        color_tolerance=tolerance
    )

    with state.lock:
        state.item_scans[scan_name] = config

    save_item_scan(config)

    save_msg = ok(f"Scan '{scan_name}' gespeichert!")
    print(f"\n{save_msg}")
    print(f"         {len(slots)} Slots, {len(items)} Items")
    print(f"         Nutze im Sequenz-Editor: 'scan {scan_name}'")
