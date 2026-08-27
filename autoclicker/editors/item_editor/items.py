"""
Item-CRUD: einzelnes Item erstellen, bearbeiten, Kategorie auswählen.

Wird sowohl vom interaktiven Editor (editor.py) als auch von autoscan.py
und learn.py genutzt.
"""

from typing import Optional

from ...config import CONFIG
from ...imaging import (
    OPENCV_AVAILABLE, take_screenshot, select_region,
)
from ...models import ItemProfile, AutoClickerState
from ...persistence import (
    get_existing_categories, get_point_by_id, shift_category_priorities,
    active_templates_dir,
)
from ...utils import (
    confirm, info, is_cancel, naechster_freier_name, parse_non_negative_float,
    safe_input, sanitize_filename,
)


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
    # Nicht `len(...) + 1`: nach dem ersten Loeschen schlaegt das einen Namen vor, den
    # es schon gibt - und weil der Name die Referenz IST, folgt darauf die Rueckfrage
    # nach dem Ueberschreiben. `naechster_freier_name()` fuellt Luecken.
    with state.lock:
        vorschlag = naechster_freier_name("Item", state.global_items)

    item_name = safe_input(f"  Item-Name (Enter = '{vorschlag}', 'cancel'): ").strip()
    if is_cancel(item_name):
        print("  -> Item-Erstellung abgebrochen")
        return None
    if not item_name:
        item_name = vorschlag

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
    min_confidence = state.config.scan_min_confidence

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
                    template_path = active_templates_dir(state) / template_file
                    template_path.parent.mkdir(parents=True, exist_ok=True)
                    img.save(template_path)
                    print(f"  -> Template gespeichert: {template_path}")

                    try:
                        conf_input = safe_input(f"  Min. Konfidenz % (Enter={int(min_confidence * 100)}): ").strip()
                        if conf_input:
                            min_confidence = max(0.1, min(1.0, float(conf_input) / 100))
                    except ValueError:
                        pass
    else:
        print(f"\n  {info('OpenCV nicht installiert - kein Template-Matching möglich')}")
        print("         Installieren mit: pip install opencv-python")

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
    confirm_point_id = None
    confirm_delay = CONFIG.scan_confirm_delay
    print("\n  Bestätigungs-Punkt? (z.B. für Popup-Bestätigung)")
    confirm_input = safe_input("  Punkt-ID (Enter=Nein): ").strip()
    if confirm_input:
        try:
            point_id = int(confirm_input)
            with state.lock:
                found_point = get_point_by_id(state, point_id)
                if found_point:
                    confirm_point_id = point_id
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
        confirm_point_id=confirm_point_id,
        confirm_delay=confirm_delay,
        template=template_file,
        min_confidence=min_confidence
    )


def edit_item(state: AutoClickerState, item: ItemProfile) -> Optional[ItemProfile]:
    """Bearbeitet ein bestehendes Item."""
    from ...utils import interactive_select

    print(f"\n  Bearbeite Item: {item.name}")
    print(f"    Kategorie: {item.category or '(keine)'}")
    print(f"    Priorität: {item.priority}")
    if item.template_names():
        print(f"    Vorlagen: {', '.join(item.template_names())} "
              f"({item.min_confidence:.0%})")
    if item.confirm_point_id:
        print(f"    Bestätigung: Punkt #{item.confirm_point_id} nach {item.confirm_delay}s")

    new_name = item.name
    new_category = item.category
    new_priority = item.priority
    new_template = item.template
    new_confidence = item.min_confidence
    new_confirm_id = item.confirm_point_id
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
                        template_path = active_templates_dir(state) / new_template
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
                            new_confirm_id = point_id
                            delay_input = safe_input(f"  Wartezeit (Enter={new_confirm_delay}s): ").strip()
                            if delay_input:
                                delay_val, delay_err = parse_non_negative_float(delay_input, "Wartezeit")
                                if delay_err:
                                    print(f"  -> {delay_err}, behalte {new_confirm_delay}s")
                                else:
                                    new_confirm_delay = delay_val
                            print("  -> Bestätigung gesetzt")
                        else:
                            print(f"  -> Punkt #{point_id} existiert nicht")
                except ValueError:
                    print("  -> Ungültige Eingabe")
            else:
                new_confirm_id = None
                print("  -> Bestätigung entfernt")

    return ItemProfile(
        name=new_name,
        marker_colors=item.marker_colors,
        category=new_category,
        priority=new_priority,
        confirm_point_id=new_confirm_id,
        confirm_delay=new_confirm_delay,
        template=new_template,
        min_confidence=new_confidence,
        template_variants=list(item.template_variants),
    )
