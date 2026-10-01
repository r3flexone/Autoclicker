"""
Item-CRUD: einzelnes Item erstellen, bearbeiten, Kategorie auswählen.

Wird sowohl vom interaktiven Editor (editor.py) als auch von autoscan.py
und learn.py genutzt.

Was Anlegen, Bearbeiten und Lernen teilen, steht hier an einer Stelle:
der Name eines neuen Items (`ask_new_item_name`) und die Aufnahme einer
Vorlage aus einer Region (`_capture_item_template`). Die Konfidenz fragt
dieselbe Funktion wie im Boss- und Icon-Editor ab (`ask_min_confidence`).
"""

from typing import Optional

from ...config import CONFIG
from ...imaging import (
    OPENCV_AVAILABLE, take_screenshot, select_region,
)
from ...models import ItemProfile, AutoClickerState
from ...persistence import (
    get_existing_categories, active_templates_dir, free_template_file,
)
from ...utils import (
    confirm, info, interactive_select, is_cancel, next_free_name, safe_input,
)
from .._detection_capture import ask_min_confidence
from .._item_fields import ask_confirm_click, ask_priority


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


def ask_new_item_name(state: AutoClickerState, prompt_extra: str = "",
                      cancel_message: Optional[str] = None) -> Optional[str]:
    """Der Name eines neuen Items — oder None (abgebrochen bzw. nicht überschreiben).

    Nicht `len(...) + 1`: nach dem ersten Loeschen schlaegt das einen Namen
    vor, den es schon gibt - und weil der Name die Referenz IST, folgt darauf
    die Rueckfrage nach dem Ueberschreiben. `next_free_name()` fuellt Luecken.
    """
    with state.lock:
        proposal = next_free_name("Item", state.global_items)
    item_name = safe_input(f"  Item-Name (Enter = '{proposal}'{prompt_extra}): ").strip()
    if is_cancel(item_name):
        if cancel_message:
            print(cancel_message)
        return None
    item_name = item_name or proposal

    with state.lock:
        name_exists = item_name in state.global_items
    if name_exists:
        if not confirm(f"  '{item_name}' existiert bereits. Überschreiben?"):
            print("  -> Abgebrochen")
            return None
        print(f"  -> '{item_name}' wird überschrieben")
    return item_name


def _capture_item_template(state: AutoClickerState, item_name: str, min_confidence: float,
                           intro: str) -> Optional[tuple[str, float]]:
    """Region wählen, Screenshot als Vorlage ablegen, Konfidenz fragen.

    Gibt `(Dateiname, Konfidenz)` zurück, None ohne Region oder Bild.
    """
    print(intro)
    region = select_region()
    if not region:
        return None
    img = take_screenshot(region)
    if not img:
        return None
    template_file = free_template_file(active_templates_dir(state), item_name)
    template_path = active_templates_dir(state) / template_file
    template_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(template_path)
    print(f"  -> Template gespeichert: {template_path}")
    return template_file, ask_min_confidence(min_confidence)


def create_item(state: AutoClickerState) -> Optional[ItemProfile]:
    """Erstellt ein neues Item interaktiv."""
    item_name = ask_new_item_name(state, ", 'cancel'", "  -> Item-Erstellung abgebrochen")
    if item_name is None:
        return None

    template_file = None
    min_confidence = state.config.scan_min_confidence
    if OPENCV_AVAILABLE:
        print("\n  Template erstellen?")
        print("  (Screenshot einer Region, die das Item zeigt)")
        print("  Enter = Ja, 'skip' = Nein")
        if safe_input().strip().lower() != "skip":
            captured = _capture_item_template(state, item_name, min_confidence,
                                              "\n  Region für Template auswählen...")
            if captured:
                template_file, min_confidence = captured
    else:
        print(f"\n  {info('OpenCV nicht installiert - kein Template-Matching möglich')}")
        print("         Installieren mit: pip install opencv-python")

    category = select_category(state)
    priority = ask_priority(state, category)

    print("\n  Bestätigungs-Punkt? (z.B. für Popup-Bestätigung)")
    confirm_point_id, confirm_delay = ask_confirm_click(
        state, CONFIG.scan_confirm_delay, prompt="  Punkt-ID (Enter = keiner): ")

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


_ITEM_EDIT_OPTIONS = ["Name", "Kategorie", "Priorität", "Template", "Bestätigungs-Punkt",
                      "Fertig"]
_ITEM_EDIT_DONE = 5


def edit_item(state: AutoClickerState, item: ItemProfile) -> Optional[ItemProfile]:
    """Bearbeitet ein bestehendes Item — Feld für Feld, bis 'Fertig'.

    Gearbeitet wird auf einem Entwurf; das übergebene Item bleibt unangetastet.
    Marker, Varianten (als Kopie) und der Schalter gehen unverändert mit.
    """
    print(f"\n  Bearbeite Item: {item.name}")
    print(f"    Kategorie: {item.category or '(keine)'}")
    print(f"    Priorität: {item.priority}")
    if item.template_names():
        print(f"    Vorlagen: {', '.join(item.template_names())} "
              f"({item.min_confidence:.0%})")
    if item.confirm_point_id:
        print(f"    Bestätigung: Punkt #{item.confirm_point_id} nach {item.confirm_delay}s")

    draft = ItemProfile(
        name=item.name,
        marker_colors=item.marker_colors,
        category=item.category,
        priority=item.priority,
        confirm_point_id=item.confirm_point_id,
        confirm_delay=item.confirm_delay,
        template=item.template,
        min_confidence=item.min_confidence,
        template_variants=list(item.template_variants),
        enabled=item.enabled,
    )
    while True:
        choice = interactive_select(_ITEM_EDIT_OPTIONS, title="\n  Was ändern?",
                                    allow_cancel=False)
        if choice == _ITEM_EDIT_DONE:
            return draft
        handler = _ITEM_EDIT_FIELDS.get(choice)
        if handler is not None:
            handler(state, item, draft)


def _edit_item_name(state: AutoClickerState, item: ItemProfile, draft: ItemProfile) -> None:
    name_input = safe_input(f"  Neuer Name (Enter = '{draft.name}'): ").strip()
    if not name_input:
        return
    with state.lock:
        collision = name_input != item.name and name_input in state.global_items
    if collision:
        print("  -> Name bereits vergeben. Bitte einen anderen Namen wählen.")
        return
    draft.name = name_input
    print(f"  -> Name geändert zu '{draft.name}'")


def _edit_item_category(state: AutoClickerState, item: ItemProfile, draft: ItemProfile) -> None:
    draft.category = select_category(state)
    print(f"  -> Kategorie geändert zu '{draft.category or '(keine)'}'")


def _edit_item_priority(state: AutoClickerState, item: ItemProfile, draft: ItemProfile) -> None:
    prio_input = safe_input(f"  Neue Priorität (Enter = {draft.priority}): ").strip()
    if not prio_input:
        return
    try:
        draft.priority = max(1, int(prio_input))
    except ValueError:
        print("  -> Ungültige Eingabe")
        return
    print(f"  -> Priorität geändert zu {draft.priority}")


def _edit_item_template(state: AutoClickerState, item: ItemProfile, draft: ItemProfile) -> None:
    if not OPENCV_AVAILABLE:
        print("  -> OpenCV nicht installiert!")
        return
    captured = _capture_item_template(state, draft.name, draft.min_confidence,
                                      "\n  Neues Template erstellen...")
    if captured:
        draft.template, draft.min_confidence = captured


def _edit_item_confirmation(state: AutoClickerState, item: ItemProfile,
                            draft: ItemProfile) -> None:
    print("  Neuer Bestätigungs-Punkt?")
    draft.confirm_point_id, draft.confirm_delay = ask_confirm_click(
        state, draft.confirm_delay, prompt="  Punkt-ID (Enter = entfernen): ")
    print("  -> Bestätigung gesetzt" if draft.confirm_point_id is not None
          else "  -> Bestätigung entfernt")


_ITEM_EDIT_FIELDS = {
    0: _edit_item_name,
    1: _edit_item_category,
    2: _edit_item_priority,
    3: _edit_item_template,
    4: _edit_item_confirmation,
}
