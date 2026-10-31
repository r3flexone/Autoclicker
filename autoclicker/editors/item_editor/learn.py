"""
Learn-Befehl für den Item-Editor (Bulk- und Single-Modus).

Bulk:    `learn 5-10 [template|simple]`   — mehrere Items aus Slot-Range
Single:  `learn <Nr>`                     — ein Item interaktiv aus einem Slot

Im Single-Modus wird Screenshot + Marker-Farben SOFORT aufgenommen, danach
die User-Eingaben — so kann das Item-Inventar sich zwischenzeitlich ändern
ohne die Daten zu verlieren.
"""


from typing import Optional

from ...imaging import OPENCV_AVAILABLE, take_screenshot
from ...models import ItemProfile, AutoClickerState
from ...persistence import active_templates_dir, free_template_file
from ...utils import unique_name, is_cancel, ok, safe_input
from .._item_fields import (
    CANCELLED, ask_confirm_click, ask_priority,
)
from ..scan_services import save_template
from .items import ask_new_item_name, select_category
from .markers import collect_marker_colors


def item_learn_command(state: AutoClickerState, user_input: str) -> None:
    """Verarbeitet den learn-Befehl (Bulk und Single)."""
    with state.lock:
        slot_list = list(state.scan_slots.values())

    if not slot_list:
        print("  -> Keine Slots vorhanden! Erst Slots mit 'auto' im Slot-Editor erstellen.")
        return

    # Bulk-Learn: learn 5-10 [template|simple]
    learn_arg = user_input[5:].strip() if user_input.startswith("learn ") else ""
    if "-" in learn_arg:
        _learn_bulk(state, slot_list, learn_arg)
        return

    # Single-Learn
    _learn_single(state, slot_list, user_input)


def _learn_bulk(state: AutoClickerState, slot_list: list, learn_arg: str) -> None:
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
            return

        use_template = mode_part.lower() in ("template", "t")
        mode_str = "MIT Template" if use_template else "OHNE Template"

        print(f"\n  === BULK LEARN: Slots {start_slot}-{end_slot} ({mode_str}) ===")

        # Kategorie einmal für alle abfragen
        print("  Kategorie für alle Items (Enter = keine):")
        category = select_category(state, show_explanation=False)

        # Bestätigungs-Punkt einmal für alle abfragen
        confirm_point_id, confirm_delay = ask_confirm_click(
            state, state.config.scan_confirm_delay,
            prompt="  Bestätigungs-Punkt-ID für alle (Enter = keiner): ")

        created_count = 0
        for slot_idx in range(start_slot - 1, end_slot):
            slot = slot_list[slot_idx]
            with state.lock:
                item_name = unique_name(f"{slot.name} Item", state.scan_items)

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
                    template_file = free_template_file(active_templates_dir(state),
                                                       item_name)
                    save_template(state, template_img, template_file)
                    item.template = template_file

            with state.lock:
                state.scan_items[item_name] = item
            created_count += 1

            template_str = f" + {item.template}" if item.template else ""
            print(f"    + {item_name} (P{priority}){template_str}")

        print(f"\n  === {created_count} Items erstellt! ===")

    except (ValueError, IndexError):
        print("  -> Format: learn <von>-<bis> [template|simple]")
        print("    Beispiel: learn 1-5 template  (mit Screenshot)")
        print("    Beispiel: learn 1-5 simple    (ohne Screenshot)")


def _learn_single(state: AutoClickerState, slot_list: list, user_input: str) -> None:
    """Single-Variante: ein Item aus einem Slot lernen.

    Wichtig: Screenshot + Marker-Farben werden SOFORT aufgenommen (vor User-Eingaben),
    damit sich das Item-Inventar während des Tippens ändern darf. Die Vorlage
    liegt bis dahin unter einem vorläufigen Namen (`_PendingTemplate`); jeder
    Abbruch räumt sie weg.
    """
    slot_num = _ask_slot_number(slot_list, user_input)
    if slot_num is None:
        return
    selected_slot = slot_list[slot_num - 1]

    print(f"\n  Scanne Slot '{selected_slot.name}' SOFORT...")
    marker_colors = collect_marker_colors(selected_slot.scan_region, selected_slot.slot_color)
    if not marker_colors:
        print("  -> Keine Farben gefunden!")
        return
    pending = _PendingTemplate.capture(state, selected_slot, slot_num)

    details = _ask_learning_details(state)
    if details is None:
        pending.discard()
        return
    item_name, category, priority, (confirm_point_id, confirm_delay) = details

    item = ItemProfile(item_name, marker_colors, category, priority,
                       confirm_point_id=confirm_point_id, confirm_delay=confirm_delay)
    item.template = pending.adopt(state, item_name)
    with state.lock:
        state.scan_items[item_name] = item

    confirm_str = f" -> Punkt #{confirm_point_id} nach {confirm_delay}s" if confirm_point_id else ""
    template_str = " + Template" if item.template else ""
    print(f"  + Item '{item_name}' gelernt mit {len(marker_colors)} Marker-Farben!{confirm_str}{template_str}")


def _ask_slot_number(slot_list: list, user_input: str) -> Optional[int]:
    """Die Slot-Nummer aus `learn <Nr>` oder erfragt — None bei Abbruch/Fehleingabe (gesagt)."""
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
        slot_input = safe_input("  Slot-Nr wo das Item liegt: ").strip()
        if is_cancel(slot_input):
            return None
        try:
            slot_num = int(slot_input)
        except ValueError:
            print("  -> Ungültige Eingabe!")
            return None

    if not 1 <= slot_num <= len(slot_list):
        print(f"  -> Ungültiger Slot! Verfügbar: 1-{len(slot_list)}")
        return None
    return slot_num


class _PendingTemplate:
    """Die Vorlage, die SOFORT aufgenommen wird — vorläufig benannt, bis das Item steht."""

    def __init__(self, path=None) -> None:
        self.path = path

    @classmethod
    def capture(cls, state: AutoClickerState, slot, slot_num: int) -> '_PendingTemplate':
        if not OPENCV_AVAILABLE:
            print(ok("Farben aufgenommen! Jetzt hast du Zeit für die Eingaben."))
            return cls()
        template_img = take_screenshot(slot.scan_region)
        if not template_img:
            return cls()
        path = save_template(state, template_img, f"_learn_temp_{slot_num}.png")
        print(ok("Screenshot + Farben aufgenommen! Jetzt hast du Zeit für die Eingaben."))
        return cls(path)

    def discard(self) -> None:
        """Bei Abbruch: die vorläufige Datei weg."""
        if self.path and self.path.exists():
            try:
                self.path.unlink()
            except OSError:
                pass

    def adopt(self, state: AutoClickerState, item_name: str) -> Optional[str]:
        """Unter dem Namen des Items ablegen; gibt den Dateinamen zurück oder None."""
        if not (self.path and self.path.exists()):
            return None
        template_file = free_template_file(active_templates_dir(state), item_name)
        try:
            self.path.rename(active_templates_dir(state) / template_file)
        except OSError as e:
            print(f"  -> Template-Fehler: {e}")
            self.discard()
            return None
        print(f"  + Template gespeichert: {template_file}")
        return template_file


def _ask_learning_details(state: AutoClickerState):
    """Name, Kategorie, Priorität, Bestätigung — oder None bei Abbruch."""
    item_name = ask_new_item_name(state)
    if item_name is None:
        return None
    category = select_category(state)
    priority = ask_priority(state, category, cancellable=True)
    if priority is CANCELLED:
        print("  -> Abgebrochen")
        return None

    print("\n  Soll nach dem Item-Klick noch ein Bestätigungs-Klick erfolgen?")
    print("  (z.B. auf einen 'Accept' oder 'Craft' Button)")
    confirmation = ask_confirm_click(
        state, state.config.scan_confirm_delay,
        prompt="  Punkt-ID für Bestätigung (Enter = keiner): ", cancellable=True)
    if confirmation is CANCELLED:
        print("  -> Abgebrochen")
        return None
    return item_name, category, priority, confirmation
