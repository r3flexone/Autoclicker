"""
Item-Editor für den Autoclicker.
Ermöglicht das Erstellen und Bearbeiten von Item-Definitionen für Item-Scans.
"""

import copy
from pathlib import Path
from typing import Optional

from ..models import ClickPoint, ItemProfile, AutoClickerState
from ..config import CONFIG, DEFAULT_MIN_CONFIDENCE
from ..utils import safe_input, sanitize_filename, is_cancel, confirm, interactive_select, col, ok, err, info, hint, header, cmd_hint, breadcrumb, suggest_command, cancel_hint, parse_non_negative_float
from ..winapi import get_cursor_pos
from ..imaging import (
    PILLOW_AVAILABLE, OPENCV_AVAILABLE, take_screenshot, get_pixel_color,
    select_region, get_color_name, color_distance
)
from ..persistence import (
    save_global_items, list_item_presets, save_item_preset,
    load_item_preset, delete_item_preset, get_existing_categories,
    shift_category_priorities, get_point_by_id, update_item_in_scans,
    TEMPLATES_DIR
)



def run_global_item_editor(state: AutoClickerState) -> None:
    """Interaktiver Editor für globale Item-Definitionen."""
    print(header("ITEM-EDITOR (Globale Item-Definitionen)"))
    print(f"  {breadcrumb('Hauptmenü', 'Item-Scan', 'Items')}")

    if not PILLOW_AVAILABLE:
        print(f"\n{err('Pillow nicht installiert!')}")
        print("         Installieren mit: pip install pillow")
        return

    # Backup für cancel
    with state.lock:
        _items_backup = copy.deepcopy(state.global_items)

    # Aktuelle Items anzeigen
    with state.lock:
        current_items = list(state.global_items.items())

    if current_items:
        print(f"\nAktuelle Items ({len(current_items)}):")
        for i, (name, item) in enumerate(current_items):
            print(f"  {i+1}. {item}")
    else:
        print("\n  (Keine Items vorhanden)")

    # Verfügbare Slots anzeigen
    with state.lock:
        slots = dict(state.global_slots)
    if slots:
        print(f"\nVerfügbare Slots für Item-Lernen ({len(slots)}):")
        for i, (name, slot) in enumerate(slots.items()):
            print(f"  {i+1}. {slot.name}")

    # Presets anzeigen
    presets = list_item_presets()
    if presets:
        print(f"\nVerfügbare Presets ({len(presets)}):")
        for name, path, count in presets:
            print(f"  - {name} ({count} Items)")

    def _print_item_help(full=False):
        if not full:
            print("\n  Kurzübersicht (? / ?? = vollständige Hilfe):")
            print("    learn <Nr>       Item aus Slot lernen")
            print("    add              Neues Item manuell")
            print("    edit <Nr>        Item bearbeiten")
            print("    del <Nr>         Item löschen")
            print("    show / s         Alle Items anzeigen")
            print(f"    done / d | cancel / {cancel_hint()}  Fertig / Abbrechen")
        else:
            print("\n" + "-" * 60)
            print("Befehle:")
            print(cmd_hint("learn <Nr>", "Item aus Slot lernen (automatisch!)"))
            print(cmd_hint("learn <Nr>-<Nr>", "Bulk: Items für Slot-Bereich (mit Template)"))
            print(cmd_hint("learn <Nr>-<Nr> simple", "Bulk: ohne Template"))
            print(cmd_hint("add", "Neues Item manuell hinzufügen"))
            print(cmd_hint("edit <Nr>", "Item bearbeiten"))
            print(cmd_hint("rename <Nr>", "Item umbenennen (inkl. Template)"))
            print(cmd_hint("del <Nr>", "Item löschen"))
            print(cmd_hint("del all", "Alle Items löschen"))
            print(cmd_hint("show / s", "Alle Items anzeigen"))
            print(cmd_hint("template <Nr>", "Template für Item setzen/entfernen"))
            print(cmd_hint("templates", "Verfügbare Templates anzeigen"))
            print(cmd_hint("save <Name>", "Als Preset speichern"))
            print(cmd_hint("load <Name>", "Preset laden"))
            print(cmd_hint("preset del <N>", "Preset löschen"))
            print(cmd_hint("help", "Kurzübersicht"))
            print(cmd_hint("? / help full / ??", "Vollständige Hilfe"))
            print(cmd_hint("done / d", "Fertig"))
            print(cmd_hint(f"cancel / {cancel_hint()}", "Abbrechen"))
            print("-" * 60)

    _print_item_help()

    while True:
        try:
            with state.lock:
                item_count = len(state.global_items)
            prompt = f"[ITEMS: {item_count}]"
            user_input = safe_input(f"{prompt} > ").strip()
            cmd = user_input.lower()

            if cmd in ("done", "d"):
                save_global_items(state)
                print(ok("Item-Editor beendet."))
                return
            elif is_cancel(cmd):
                with state.lock:
                    state.global_items = _items_backup
                print(col("[ABBRUCH]", "yellow") + " Änderungen verworfen.")
                return
            elif cmd == "":
                continue
            elif cmd == "help":
                _print_item_help()
                continue
            elif cmd in ("?", "help full", "??"):
                _print_item_help(full=True)
                continue
            elif cmd in ("show", "s"):
                with state.lock:
                    if state.global_items:
                        print(f"\nItems ({len(state.global_items)}):")
                        sorted_items = sorted(state.global_items.values(), key=lambda x: x.priority)
                        for i, item in enumerate(sorted_items):
                            print(f"  {i+1}. {item}")
                    else:
                        print("  (Keine Items)")
                continue

            elif cmd.startswith("learn"):
                item_learn_command(state, cmd)
                continue

            elif cmd == "add":
                item = create_item(state)
                if item:
                    with state.lock:
                        state.global_items[item.name] = item
                    print(f"  + Item '{item.name}' hinzugefügt")
                continue

            elif cmd.startswith("edit "):
                try:
                    edit_num = int(cmd[5:])
                    with state.lock:
                        item_list = list(state.global_items.items())
                        if 1 <= edit_num <= len(item_list):
                            name, item = item_list[edit_num - 1]
                            new_item = edit_item(state, item)
                            if new_item:
                                # Falls Name geändert wurde
                                if new_item.name != name:
                                    del state.global_items[name]
                                state.global_items[new_item.name] = new_item
                                print(f"  + Item '{new_item.name}' aktualisiert")
                        else:
                            print(f"  -> Ungültig! Verfügbar: 1-{len(item_list)}")
                except ValueError:
                    print("  -> Format: edit <Nr>")
                continue

            elif cmd == "del all":
                with state.lock:
                    if not state.global_items:
                        print("  -> Keine Items vorhanden!")
                        continue
                    count = len(state.global_items)
                if confirm(f"  {count} Item(s) wirklich löschen?"):
                    with state.lock:
                        state.global_items.clear()
                    print(f"  + {count} Item(s) gelöscht!")
                else:
                    print("  -> Abgebrochen")
                continue

            elif cmd.startswith("del "):
                try:
                    del_num = int(cmd[4:])
                    with state.lock:
                        item_list = list(state.global_items.keys())
                        if 1 <= del_num <= len(item_list):
                            name = item_list[del_num - 1]
                            del state.global_items[name]
                            print(f"  + Item '{name}' gelöscht")
                        else:
                            print(f"  -> Ungültig! Verfügbar: 1-{len(item_list)}")
                except ValueError:
                    print("  -> Format: del <Nr>")
                continue

            elif cmd.startswith("rename "):
                handle_rename_command(state, cmd)
                continue

            elif cmd == "templates":
                handle_templates_command()
                continue

            elif cmd.startswith("template "):
                handle_template_command(state, cmd)
                continue

            elif cmd.startswith("save "):
                preset_name = user_input[5:].strip()
                if preset_name:
                    save_item_preset(state, preset_name)
                else:
                    print("  -> Format: save <Name>")
                continue

            elif cmd.startswith("load "):
                preset_name = user_input[5:].strip()
                if preset_name:
                    load_item_preset(state, preset_name)
                else:
                    print("  -> Format: load <Name>")
                continue

            elif cmd.startswith("preset del "):
                preset_name = user_input[11:].strip()
                if preset_name:
                    delete_item_preset(preset_name)
                else:
                    print("  -> Format: preset del <Name>")
                continue

            else:
                _known = ["learn", "add", "edit", "rename", "del", "show", "template", "templates", "save", "load", "preset", "help", "done", "cancel"]
                suggestion = suggest_command(cmd, _known)
                print(f"  -> Unbekannter Befehl.{suggestion} {hint('(? = Hilfe)')}")

        except (KeyboardInterrupt, EOFError):
            with state.lock:
                state.global_items = _items_backup
            print("\n" + col("[ABBRUCH]", "yellow") + " Änderungen verworfen.")
            return


def select_category(state: AutoClickerState, show_explanation: bool = True) -> Optional[str]:
    """Lässt den Benutzer eine Kategorie auswählen oder erstellen."""
    existing = get_existing_categories(state)

    if show_explanation:
        print("\n  Kategorie (z.B. 'Hosen', 'Jacken', 'Juwelen')")
        print("  Items derselben Kategorie konkurrieren - nur das beste wird geklickt.")

    if existing:
        print("  Vorhandene Kategorien:")
        for i, cat in enumerate(existing):
            print(f"    {i+1}. {cat}")
        print("  (Nummer wählen oder neuen Namen eingeben)")

    user_input = safe_input("  Kategorie (Enter = keine): ").strip()

    if not user_input:
        return None

    try:
        num = int(user_input)
        if 1 <= num <= len(existing):
            return existing[num - 1]
        else:
            return user_input
    except ValueError:
        return user_input


def create_item(state: AutoClickerState) -> Optional[ItemProfile]:
    """Erstellt ein neues Item interaktiv."""
    with state.lock:
        item_num = len(state.global_items) + 1

    item_name = safe_input(f"  Item-Name (Enter = 'Item {item_num}', 'cancel'): ").strip()
    if is_cancel(item_name):
        print("  -> Item-Erstellung abgebrochen")
        return None
    if not item_name:
        item_name = f"Item {item_num}"

    # Prüfen ob Name schon existiert
    with state.lock:
        name_exists = item_name in state.global_items
    if name_exists:
        if not confirm(f"  '{item_name}' existiert bereits. Überschreiben?"):
            print("  -> Abgebrochen")
            return None
        print(f"  -> '{item_name}' wird überschrieben")

    # Template erstellen (Screenshot von Slot)
    template_file = None
    min_confidence = DEFAULT_MIN_CONFIDENCE

    if OPENCV_AVAILABLE:
        print("\n  Template erstellen?")
        print("  (Screenshot einer Region, die das Item zeigt)")
        print("  Enter = Ja, 'skip' = Nein")
        if safe_input().strip().lower() != "skip":
            print("\n  Region für Template auswählen...")
            region = select_region()
            if region:
                img = take_screenshot(region)
                if img:
                    safe_name = sanitize_filename(item_name)
                    template_file = f"{safe_name}.png"
                    template_path = Path(TEMPLATES_DIR) / template_file
                    template_path.parent.mkdir(parents=True, exist_ok=True)
                    img.save(template_path)
                    print(f"  -> Template gespeichert: {template_path}")

                    # Konfidenz abfragen
                    try:
                        conf_input = safe_input(f"  Min. Konfidenz % (Enter={int(DEFAULT_MIN_CONFIDENCE * 100)}): ").strip()
                        if conf_input:
                            min_confidence = max(0.1, min(1.0, float(conf_input) / 100))
                    except ValueError:
                        pass
    else:
        print(f"\n  {info('OpenCV nicht installiert - kein Template-Matching möglich')}")
        print("         Installieren mit: pip install opencv-python")

    # Kategorie
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

    # Bestätigungs-Klick
    confirm_point = None
    confirm_delay = CONFIG.default_confirm_delay
    print("\n  Bestätigungs-Punkt? (z.B. für Popup-Bestätigung)")
    confirm_input = safe_input("  Punkt-ID (Enter=Nein): ").strip()
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

    return ItemProfile(
        name=item_name,
        marker_colors=[],
        category=category,
        priority=priority,
        confirm_point=confirm_point,
        confirm_delay=confirm_delay,
        template=template_file,
        min_confidence=min_confidence
    )


def edit_item(state: AutoClickerState, item: ItemProfile) -> Optional[ItemProfile]:
    """Bearbeitet ein bestehendes Item."""
    print(f"\n  Bearbeite Item: {item.name}")
    print(f"    Kategorie: {item.category or '(keine)'}")
    print(f"    Priorität: {item.priority}")
    if item.template:
        print(f"    Template: {item.template} ({item.min_confidence:.0%})")
    if item.confirm_point:
        print(f"    Bestätigung: ({item.confirm_point.x}, {item.confirm_point.y}) nach {item.confirm_delay}s")

    new_name = item.name
    new_category = item.category
    new_priority = item.priority
    new_template = item.template
    new_confidence = item.min_confidence
    new_confirm = item.confirm_point
    new_confirm_delay = item.confirm_delay

    while True:
        edit_options = ["Name", "Kategorie", "Priorität", "Template", "Bestätigungs-Punkt", "Fertig"]
        choice = interactive_select(edit_options, title="\n  Was ändern?", allow_cancel=False)

        if choice == 5:  # Fertig
            break
        elif choice == 0:  # Name
            name_input = safe_input(f"  Neuer Name (Enter = '{new_name}'): ").strip()
            if name_input:
                new_name = name_input
                print(f"  -> Name geändert zu '{new_name}'")
        elif choice == 1:  # Kategorie
            new_category = select_category(state)
            print(f"  -> Kategorie geändert zu '{new_category or '(keine)'}'")
        elif choice == 2:  # Priorität
            try:
                prio_input = safe_input(f"  Neue Priorität (Enter = {new_priority}): ").strip()
                if prio_input:
                    new_priority = max(1, int(prio_input))
                    print(f"  -> Priorität geändert zu {new_priority}")
            except ValueError:
                print("  -> Ungültige Eingabe")
        elif choice == 3:  # Template
            if OPENCV_AVAILABLE:
                print("\n  Neues Template erstellen...")
                region = select_region()
                if region:
                    img = take_screenshot(region)
                    if img:
                        safe_name = sanitize_filename(new_name)
                        new_template = f"{safe_name}.png"
                        template_path = Path(TEMPLATES_DIR) / new_template
                        template_path.parent.mkdir(parents=True, exist_ok=True)
                        img.save(template_path)
                        print(f"  -> Template gespeichert: {template_path}")

                        try:
                            conf_input = safe_input(f"  Min. Konfidenz % (Enter={int(new_confidence * 100)}): ").strip()
                            if conf_input:
                                new_confidence = max(0.1, min(1.0, float(conf_input) / 100))
                        except ValueError:
                            pass
            else:
                print("  -> OpenCV nicht installiert!")
        elif choice == 4:  # Bestätigungs-Punkt
            print("  Neuer Bestätigungs-Punkt?")
            confirm_input = safe_input("  Punkt-ID (Enter=entfernen): ").strip()
            if confirm_input:
                try:
                    point_id = int(confirm_input)
                    with state.lock:
                        found_point = get_point_by_id(state, point_id)
                        if found_point:
                            new_confirm = ClickPoint(found_point.x, found_point.y)
                            delay_input = safe_input(f"  Wartezeit (Enter={new_confirm_delay}s): ").strip()
                            if delay_input:
                                delay_val, delay_err = parse_non_negative_float(delay_input, "Wartezeit")
                                if delay_err:
                                    print(f"  -> {delay_err}, behalte {new_confirm_delay}s")
                                else:
                                    new_confirm_delay = delay_val
                            print(f"  -> Bestätigung gesetzt")
                        else:
                            print(f"  -> Punkt #{point_id} existiert nicht")
                except ValueError:
                    print("  -> Ungültige Eingabe")
            else:
                new_confirm = None
                print("  -> Bestätigung entfernt")

    return ItemProfile(
        name=new_name,
        marker_colors=item.marker_colors,
        category=new_category,
        priority=new_priority,
        confirm_point=new_confirm,
        confirm_delay=new_confirm_delay,
        template=new_template,
        min_confidence=new_confidence
    )


# =============================================================================
# MARKER-FARBEN SAMMLUNG
# =============================================================================

def collect_marker_colors(region: tuple = None, exclude_color: tuple = None) -> list[tuple]:
    """Sammelt Marker-Farben für ein Item-Profil durch Region-Scan."""

    # Wenn keine Region übergeben, manuell auswählen
    if not region:
        print("\n  Wähle einen Bereich auf dem Item aus:")
        print("  (Die 5 häufigsten Farben werden automatisch genommen)")
        region = select_region()
        if not region:
            return []

    # Screenshot der Region
    print(f"\n  Scanne Region ({region[0]},{region[1]}) - ({region[2]},{region[3]})...")
    img = take_screenshot(region)
    if img is None:
        print("  -> Fehler beim Screenshot!")
        return []

    # Farben zählen (mit Rundung für Gruppierung)
    color_counts = {}
    pixels = img.load()
    width, height = img.size

    for x in range(width):
        for y in range(height):
            pixel = pixels[x, y][:3]
            # Runde auf 5er-Schritte für Gruppierung ähnlicher Farben
            rounded = (pixel[0] // 5 * 5, pixel[1] // 5 * 5, pixel[2] // 5 * 5)
            color_counts[rounded] = color_counts.get(rounded, 0) + 1

    # Slot-Hintergrundfarbe ausschließen (falls vorhanden)
    if exclude_color:
        exclude_rounded = (exclude_color[0] // 5 * 5, exclude_color[1] // 5 * 5, exclude_color[2] // 5 * 5)

        slot_color_dist = CONFIG.slot_color_distance
        colors_to_remove = []
        for color in color_counts.keys():
            if color_distance(color, exclude_rounded) <= slot_color_dist:
                colors_to_remove.append(color)

        total_excluded = 0
        for color in colors_to_remove:
            total_excluded += color_counts.pop(color)

        if total_excluded > 0:
            color_name = get_color_name(exclude_color)
            print(f"  -> Slot-Hintergrund ~RGB{exclude_color} ({color_name}) ausgeschlossen ({total_excluded} Pixel, {len(colors_to_remove)} Farbtöne)")

    # Top N häufigste Farben (aus Config)
    marker_count = CONFIG.marker_count
    sorted_colors = sorted(color_counts.items(), key=lambda x: x[1], reverse=True)[:marker_count]
    colors = [color for color, count in sorted_colors]

    print(f"\n  Top {marker_count} Farben gefunden:")
    for i, (color, count) in enumerate(sorted_colors):
        color_name = get_color_name(color)
        print(f"    {i+1}. RGB{color} - {color_name} ({count} Pixel)")

    return colors


# =============================================================================
# LEARN-BEFEHL (Bulk und Single)
# =============================================================================

def item_learn_command(state: AutoClickerState, user_input: str) -> bool:
    """Verarbeitet den learn-Befehl (Bulk und Single). Gibt True zurück wenn verarbeitet."""
    with state.lock:
        slot_list = list(state.global_slots.values())

    if not slot_list:
        print("  -> Keine Slots vorhanden! Erst Slots mit 'auto' im Slot-Editor erstellen.")
        return True

    # Bulk-Learn: learn 5-10 [template|simple]
    learn_arg = user_input[5:].strip() if user_input.startswith("learn ") else ""
    if "-" in learn_arg:
        parts = learn_arg.split()
        range_part = parts[0]
        mode_part = parts[1] if len(parts) > 1 else "template"

        try:
            range_parts = range_part.split("-")
            start_slot = int(range_parts[0])
            end_slot = int(range_parts[1])

            if start_slot < 1 or end_slot > len(slot_list) or start_slot > end_slot:
                print(f"  -> Ungültiger Bereich! Verfügbar: 1-{len(slot_list)}")
                return True

            use_template = mode_part.lower() in ("template", "t")
            mode_str = "MIT Template" if use_template else "OHNE Template"

            print(f"\n  === BULK LEARN: Slots {start_slot}-{end_slot} ({mode_str}) ===")

            # Kategorie einmal für alle abfragen
            print("  Kategorie für alle Items (Enter = keine):")
            category = select_category(state, show_explanation=False)

            # Bestätigungs-Punkt einmal für alle abfragen
            confirm_point = None
            confirm_delay = state.config.default_confirm_delay
            confirm_input = safe_input("  Bestätigungs-Punkt-ID für alle (Enter = keine): ").strip()
            if confirm_input:
                try:
                    point_id = int(confirm_input)
                    found_point = get_point_by_id(state, point_id)
                    if found_point:
                        confirm_point = ClickPoint(found_point.x, found_point.y)
                        delay_input = safe_input(f"  Wartezeit vor Bestätigung (Enter = {confirm_delay}s): ").strip()
                        if delay_input:
                            delay_val, delay_err = parse_non_negative_float(delay_input, "Wartezeit")
                            if delay_err:
                                print(f"  -> {delay_err}, behalte {confirm_delay}s")
                            else:
                                confirm_delay = delay_val
                except ValueError:
                    pass

            created_count = 0
            for slot_idx in range(start_slot - 1, end_slot):
                slot = slot_list[slot_idx]
                item_name = f"{slot.name} Item"

                # Eindeutigen Namen sicherstellen
                base_name = item_name
                counter = 1
                while item_name in state.global_items:
                    counter += 1
                    item_name = f"{base_name} {counter}"

                priority = slot_idx - start_slot + 2

                # Item erstellen
                item = ItemProfile(
                    name=item_name,
                    marker_colors=[],
                    category=category,
                    priority=priority,
                    confirm_point=confirm_point,
                    confirm_delay=confirm_delay,
                    min_confidence=DEFAULT_MIN_CONFIDENCE
                )

                # Template speichern wenn gewünscht
                if use_template and OPENCV_AVAILABLE:
                    template_img = take_screenshot(slot.scan_region)
                    if template_img:
                        safe_name = sanitize_filename(item_name)
                        template_file = f"{safe_name}.png"
                        template_path = Path(TEMPLATES_DIR) / template_file
                        template_path.parent.mkdir(parents=True, exist_ok=True)
                        template_img.save(template_path)
                        item.template = template_file

                with state.lock:
                    state.global_items[item_name] = item
                created_count += 1

                template_str = f" + {item.template}" if item.template else ""
                print(f"    + {item_name} (P{priority}){template_str}")

            print(f"\n  === {created_count} Items erstellt! ===")
            return True

        except (ValueError, IndexError):
            print("  -> Format: learn <von>-<bis> [template|simple]")
            print("    Beispiel: learn 1-5 template  (mit Screenshot)")
            print("    Beispiel: learn 1-5 simple    (ohne Screenshot)")
            return True

    # Single-Learn: Slot-Nummer aus Befehl oder nachfragen
    slot_num = None
    if user_input.startswith("learn "):
        try:
            slot_num = int(user_input[6:])
        except ValueError:
            pass

    if slot_num is None:
        print(f"\n  Verfügbare Slots (1-{len(slot_list)}):")
        for i, slot in enumerate(slot_list):
            print(f"    {i+1}. {slot.name}")
        try:
            slot_input = safe_input("  Slot-Nr wo das Item liegt: ").strip()
            if is_cancel(slot_input):
                return True
            slot_num = int(slot_input)
        except ValueError:
            print("  -> Ungültige Eingabe!")
            return True

    if slot_num < 1 or slot_num > len(slot_list):
        print(f"  -> Ungültiger Slot! Verfügbar: 1-{len(slot_list)}")
        return True

    selected_slot = slot_list[slot_num - 1]

    # === SOFORT: Screenshot + Farben + Template aufnehmen ===
    print(f"\n  Scanne Slot '{selected_slot.name}' SOFORT...")
    marker_colors = collect_marker_colors(selected_slot.scan_region, selected_slot.slot_color)

    if not marker_colors:
        print("  -> Keine Farben gefunden!")
        return True

    # Template sofort aufnehmen (wenn OpenCV verfügbar)
    cached_template_path = None
    if OPENCV_AVAILABLE:
        template_img = take_screenshot(selected_slot.scan_region)
        if template_img:
            # Temporär unter generischem Namen speichern, wird später umbenannt
            temp_name = f"_learn_temp_{slot_num}.png"
            cached_template_path = Path(TEMPLATES_DIR) / temp_name
            cached_template_path.parent.mkdir(parents=True, exist_ok=True)
            template_img.save(cached_template_path)
            print(ok("Screenshot + Farben aufgenommen! Jetzt hast du Zeit für die Eingaben."))
    else:
        print(ok("Farben aufgenommen! Jetzt hast du Zeit für die Eingaben."))

    # === Ab hier: Benutzereingaben (Item kann sich inzwischen ändern, Daten sind gecacht) ===

    def _cleanup_cached_template():
        """Löscht das gecachte Template bei Abbruch."""
        if cached_template_path and cached_template_path.exists():
            try:
                cached_template_path.unlink()
            except OSError:
                pass

    # Item-Name abfragen
    item_num = len(state.global_items) + 1
    item_name = safe_input(f"  Item-Name (Enter = 'Item {item_num}'): ").strip()
    if is_cancel(item_name):
        _cleanup_cached_template()
        return True
    if not item_name:
        item_name = f"Item {item_num}"

    # Prüfen ob Name schon existiert
    with state.lock:
        name_exists = item_name in state.global_items
    if name_exists:
        if not confirm(f"  '{item_name}' existiert bereits. Überschreiben?"):
            print("  -> Abgebrochen")
            _cleanup_cached_template()
            return True
        print(f"  -> '{item_name}' wird überschrieben")

    # Kategorie zuerst (für Prioritäts-Verschiebung)
    category = select_category(state)

    # Priorität
    priority = 1
    try:
        prio_input = safe_input(f"  Priorität (1=beste, 0=beste+verschieben, Enter={priority}): ").strip()
        if is_cancel(prio_input):
            print("  -> Abgebrochen")
            _cleanup_cached_template()
            return True
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

    # Bestätigungs-Klick abfragen
    confirm_point = None
    confirm_delay = state.config.default_confirm_delay
    print("\n  Soll nach dem Item-Klick noch ein Bestätigungs-Klick erfolgen?")
    print("  (z.B. auf einen 'Accept' oder 'Craft' Button)")
    confirm_input = safe_input("  Punkt-ID für Bestätigung (Enter = Nein): ").strip()
    if is_cancel(confirm_input):
        print("  -> Abgebrochen")
        _cleanup_cached_template()
        return True
    if confirm_input:
        try:
            point_id = int(confirm_input)
            found_point = get_point_by_id(state, point_id)
            if found_point:
                confirm_point = ClickPoint(found_point.x, found_point.y)
                delay_input = safe_input(f"  Wartezeit vor Bestätigung in Sek (Enter = {confirm_delay}): ").strip()
                if delay_input:
                    delay_val, delay_err = parse_non_negative_float(delay_input, "Wartezeit")
                    if delay_err:
                        print(f"  -> {delay_err}, behalte {confirm_delay}s")
                    else:
                        confirm_delay = delay_val
            else:
                print(f"  -> Punkt #{point_id} existiert nicht")
        except ValueError:
            print("  -> Keine gültige Zahl, keine Bestätigung")

    # Item erstellen
    item = ItemProfile(item_name, marker_colors, category, priority, confirm_point, confirm_delay)

    # Gecachtes Template dem Item zuweisen und umbenennen
    if cached_template_path and cached_template_path.exists():
        safe_name = sanitize_filename(item_name)
        template_file = f"{safe_name}.png"
        final_path = Path(TEMPLATES_DIR) / template_file
        try:
            cached_template_path.rename(final_path)
            item.template = template_file
            print(f"  + Template gespeichert: {template_file}")
        except OSError as e:
            print(f"  -> Template-Fehler: {e}")
            _cleanup_cached_template()

    with state.lock:
        state.global_items[item_name] = item

    confirm_str = f" -> ({confirm_point.x},{confirm_point.y}) nach {confirm_delay}s" if confirm_point else ""
    template_str = f" + Template" if item.template else ""
    print(f"  + Item '{item_name}' gelernt mit {len(marker_colors)} Marker-Farben!{confirm_str}{template_str}")
    return True


# =============================================================================
# RENAME-BEFEHL
# =============================================================================

def handle_rename_command(state: AutoClickerState, cmd: str) -> None:
    """Verarbeitet den rename-Befehl im Item-Editor."""
    try:
        rename_num = int(cmd[7:])

        # Daten unter Lock lesen, dann Lock freigeben für User-Input
        with state.lock:
            item_names = list(state.global_items.keys())
            if rename_num < 1 or rename_num > len(item_names):
                print(f"  -> Ungültiges Item! Verfügbar: 1-{len(item_names)}")
                return
            old_name = item_names[rename_num - 1]
            old_template = state.global_items[old_name].template

        # User-Input OHNE Lock (blockiert nicht andere Threads)
        print(f"\n  Aktueller Name: '{old_name}'")
        if old_template:
            print(f"  Template: {old_template}")

        new_name = safe_input("  Neuer Name (Enter = abbrechen): ").strip()
        if not new_name or is_cancel(new_name):
            print("  -> Abgebrochen")
            return

        if new_name == old_name:
            print("  -> Name ist identisch, nichts geändert")
            return

        # Duplikat-Check und Bestätigung OHNE Lock
        with state.lock:
            name_exists = new_name in state.global_items
        if name_exists:
            if not confirm(f"  '{new_name}' existiert bereits. Überschreiben?"):
                print("  -> Abgebrochen")
                return

        # Template umbenennen (File-I/O, kein Lock nötig)
        new_template = None
        if old_template:
            old_template_path = Path(TEMPLATES_DIR) / old_template
            safe_name = sanitize_filename(new_name)
            new_template = f"{safe_name}.png"
            new_template_path = Path(TEMPLATES_DIR) / new_template

            if old_template_path.exists():
                try:
                    old_template_path.rename(new_template_path)
                    print(f"  + Template umbenannt: {old_template} -> {new_template}")
                except (OSError, IOError) as e:
                    print(f"  -> Template-Datei Umbenennung fehlgeschlagen: {e}")
                    print(f"    Template-Pfad aktualisiert: {new_template}")
            else:
                print(f"  -> Template-Datei nicht gefunden: {old_template}")
                print(f"    Template-Pfad aktualisiert: {new_template}")

        # Mutation unter Lock
        with state.lock:
            if old_name not in state.global_items:
                print(f"  -> Item '{old_name}' nicht mehr vorhanden!")
                return
            item = state.global_items[old_name]
            if new_name in state.global_items and new_name != old_name:
                del state.global_items[new_name]
                print(f"  -> '{new_name}' wird überschrieben")
            item.name = new_name
            if new_template is not None:
                item.template = new_template
            del state.global_items[old_name]
            state.global_items[new_name] = item

        # Auch in allen Scan-Konfigurationen aktualisieren
        updated_scans, failed_scans = update_item_in_scans(old_name, new_name, item.template)
        if updated_scans > 0:
            print(f"  + {updated_scans} Scan-Konfiguration(en) aktualisiert")
        if failed_scans > 0:
            print(f"  {warn(f'{failed_scans} Scan-Datei(en) konnten nicht aktualisiert werden!')}")

        print(f"  + Item umbenannt: '{old_name}' -> '{new_name}' (gespeichert)")
    except ValueError:
        print("  -> Format: rename <Nr>")


# =============================================================================
# TEMPLATE-BEFEHLE
# =============================================================================

def handle_templates_command() -> None:
    """Zeigt verfügbare Templates an."""
    if not Path(TEMPLATES_DIR).exists():
        print("  -> Keine Templates vorhanden")
        return
    templates = list(Path(TEMPLATES_DIR).glob("*.png"))
    if not templates:
        print("  -> Keine Templates vorhanden")
        print(f"    (Ordner: {TEMPLATES_DIR})")
    else:
        print(f"\n  Verfügbare Templates ({len(templates)}):")
        for t in sorted(templates):
            print(f"    - {t.name}")


def handle_template_command(state: AutoClickerState, cmd: str) -> None:
    """Verarbeitet den template-Befehl im Item-Editor."""
    try:
        item_num = int(cmd[9:])
        with state.lock:
            item_names = list(state.global_items.keys())
            if 1 <= item_num <= len(item_names):
                name = item_names[item_num - 1]
                item = state.global_items[name]

                # Verfügbare Templates anzeigen
                templates = list(Path(TEMPLATES_DIR).glob("*.png")) if Path(TEMPLATES_DIR).exists() else []
                if templates:
                    print(f"\n  Verfügbare Templates:")
                    for i, t in enumerate(sorted(templates)):
                        print(f"    {i+1}. {t.name}")

                current = item.template if item.template else "Keins"
                print(f"\n  Item: {item.name}")
                print(f"  Aktuelles Template: {current}")
                print(f"  Aktuelle Konfidenz: {item.min_confidence:.0%}")

                print("\n  Optionen:")
                print("    <Dateiname.png> - Template setzen")
                print("    <Nr>            - Template aus Liste wählen")
                print("    capture         - Screenshot als Template speichern")
                print("    remove          - Template entfernen")
                print("    Enter           - Abbrechen")

                template_input = safe_input("  Template: ").strip()
                if not template_input:
                    return

                if template_input.lower() == "remove":
                    item.template = None
                    print("  + Template entfernt!")
                elif template_input.lower() == "capture":
                    # Screenshot-Region abfragen
                    with state.lock:
                        slot_list = list(state.global_slots.values())
                    if slot_list:
                        print(f"\n  Screenshot von:")
                        print("    0. Freie Region wählen")
                        for i, slot in enumerate(slot_list):
                            print(f"    {i+1}. {slot.name}")
                        try:
                            slot_choice = safe_input("  Auswahl: ").strip()
                            if slot_choice == "0":
                                region = select_region()
                            else:
                                slot_idx = int(slot_choice) - 1
                                if 0 <= slot_idx < len(slot_list):
                                    region = slot_list[slot_idx].scan_region
                                else:
                                    print("  -> Ungültiger Slot!")
                                    return
                        except ValueError:
                            region = select_region()
                    else:
                        region = select_region()

                    if region:
                        img = take_screenshot(region)
                        if img:
                            safe_name = sanitize_filename(item.name)
                            template_file = f"{safe_name}.png"
                            template_path = Path(TEMPLATES_DIR) / template_file
                            template_path.parent.mkdir(parents=True, exist_ok=True)
                            img.save(template_path)
                            item.template = template_file

                            conf_input = safe_input(f"  Min. Konfidenz (Enter={item.min_confidence:.0%}): ").strip()
                            if conf_input:
                                try:
                                    conf = float(conf_input.replace("%", "")) / 100
                                    item.min_confidence = max(0.1, min(1.0, conf))
                                except ValueError:
                                    pass

                            print(f"  + Template gespeichert: {template_file}")
                        else:
                            print("  -> Screenshot fehlgeschlagen!")
                else:
                    # Dateiname oder Nummer
                    try:
                        template_num = int(template_input)
                        if 1 <= template_num <= len(templates):
                            item.template = sorted(templates)[template_num - 1].name
                        else:
                            print("  -> Ungültige Nummer!")
                            return
                    except ValueError:
                        if not template_input.endswith(".png"):
                            template_input += ".png"
                        item.template = template_input

                    # Konfidenz abfragen
                    conf_input = safe_input(f"  Min. Konfidenz (aktuell {item.min_confidence:.0%}, Enter=behalten): ").strip()
                    if conf_input:
                        try:
                            conf = float(conf_input.replace("%", "")) / 100
                            item.min_confidence = max(0.1, min(1.0, conf))
                        except ValueError:
                            pass

                    print(f"  + Template gesetzt: {item.template} (>={item.min_confidence:.0%})")
            else:
                print(f"  -> Ungültiges Item!")
    except ValueError:
        print("  -> Format: template <Nr>")
