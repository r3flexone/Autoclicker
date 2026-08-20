"""
Learn-Befehl für den Item-Editor (Bulk- und Single-Modus).

Bulk:    `learn 5-10 [template|simple]`   — mehrere Items aus Slot-Range
Single:  `learn <Nr>`                     — ein Item interaktiv aus einem Slot

Im Single-Modus wird Screenshot + Marker-Farben SOFORT aufgenommen, danach
die User-Eingaben — so kann das Item-Inventar sich zwischenzeitlich ändern
ohne die Daten zu verlieren.
"""

from pathlib import Path

from ...imaging import OPENCV_AVAILABLE, take_screenshot
from ...models import ItemProfile, AutoClickerState
from ...persistence import (
    get_point_by_id, shift_category_priorities, TEMPLATES_DIR,
)
from ...utils import (
    confirm, eindeutiger_name, is_cancel, naechster_freier_name, ok,
    parse_non_negative_float, safe_input, sanitize_filename,
)
from .items import select_category
from .markers import collect_marker_colors


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
        return _learn_bulk(state, slot_list, learn_arg)

    # Single-Learn
    return _learn_single(state, slot_list, user_input)


def _learn_bulk(state: AutoClickerState, slot_list: list, learn_arg: str) -> bool:
    """Bulk-Variante: legt Items für einen Slot-Bereich an."""
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
        confirm_point_id = None
        confirm_delay = state.config.scan_confirm_delay
        confirm_input = safe_input("  Bestätigungs-Punkt-ID für alle (Enter = keine): ").strip()
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
            except ValueError:
                pass

        created_count = 0
        for slot_idx in range(start_slot - 1, end_slot):
            slot = slot_list[slot_idx]
            with state.lock:
                item_name = eindeutiger_name(f"{slot.name} Item", state.global_items)

            priority = slot_idx - start_slot + 2

            item = ItemProfile(
                name=item_name,
                marker_colors=[],
                category=category,
                priority=priority,
                confirm_point_id=confirm_point_id,
                confirm_delay=confirm_delay,
                min_confidence=state.config.scan_min_confidence
            )

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


def _learn_single(state: AutoClickerState, slot_list: list, user_input: str) -> bool:
    """Single-Variante: ein Item aus einem Slot lernen.

    Wichtig: Screenshot + Marker-Farben werden SOFORT aufgenommen (vor User-Eingaben),
    damit sich das Item-Inventar während des Tippens ändern darf.
    """
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

    def _cleanup_cached_template() -> None:
        """Löscht das gecachte Template bei Abbruch."""
        if cached_template_path and cached_template_path.exists():
            try:
                cached_template_path.unlink()
            except OSError:
                pass

    # Item-Name abfragen. Nicht `len(...) + 1` — das schlaegt nach dem ersten Loeschen
    # einen bereits vergebenen Namen vor, und der Name ist hier die Referenz.
    with state.lock:
        vorschlag = naechster_freier_name("Item", state.global_items)
    item_name = safe_input(f"  Item-Name (Enter = '{vorschlag}'): ").strip()
    if is_cancel(item_name):
        _cleanup_cached_template()
        return True
    if not item_name:
        item_name = vorschlag

    with state.lock:
        name_exists = item_name in state.global_items
    if name_exists:
        if not confirm(f"  '{item_name}' existiert bereits. Überschreiben?"):
            print("  -> Abgebrochen")
            _cleanup_cached_template()
            return True
        print(f"  -> '{item_name}' wird überschrieben")

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
    confirm_point_id = None
    confirm_delay = state.config.scan_confirm_delay
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
                confirm_point_id = point_id
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

    item = ItemProfile(item_name, marker_colors, category, priority,
                       confirm_point_id=confirm_point_id, confirm_delay=confirm_delay)

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

    confirm_str = f" -> Punkt #{confirm_point_id} nach {confirm_delay}s" if confirm_point_id else ""
    template_str = " + Template" if item.template else ""
    print(f"  + Item '{item_name}' gelernt mit {len(marker_colors)} Marker-Farben!{confirm_str}{template_str}")
    return True
