"""
TUI-Arbeitsansichten für Slots, Items und Kategorie-Operationen.

`state.scan_slots`/`state.scan_items` sind Ansichten auf die Slots und Items des
gewählten Item-Scans (`state.active_item_scan`) — der Scan besitzt sie, es gibt
keinen Bestand daneben. Gespeichert werden sie, indem die Ansichten in den Scan
zurückgeschrieben werden.
"""

from ..models import AutoClickerState
from ..utils import save_tag, err


# =============================================================================
# SLOTS
# =============================================================================

def save_scan_slots(state: AutoClickerState) -> bool:
    """Speichert die Slot-Arbeitsansicht in ihrem Item-Scan."""
    from .item_scans import flush_item_scan_context, save_item_scan
    cfg = flush_item_scan_context(state)
    if cfg is None:
        print(err("Kein Item-Scan zum Speichern gewählt."))
        return False
    try:
        if not save_item_scan(cfg):
            return False
        print(save_tag(f"{len(cfg.slots)} Slot(s) in '{cfg.name}' gespeichert"))
        return True
    except (IOError, OSError, ValueError) as e:
        print(err(f"Slots konnten nicht gespeichert werden: {e}"))
        return False


# =============================================================================
# ITEMS
# =============================================================================

def save_scan_items(state: AutoClickerState) -> bool:
    """Speichert die Item-Arbeitsansicht in ihrem Item-Scan."""
    from .item_scans import flush_item_scan_context, save_item_scan
    cfg = flush_item_scan_context(state)
    if cfg is None:
        print(err("Kein Item-Scan zum Speichern gewählt."))
        return False
    try:
        if not save_item_scan(cfg):
            return False
        print(save_tag(f"{len(cfg.items)} Item(s) in '{cfg.name}' gespeichert"))
        return True
    except (IOError, OSError, ValueError) as e:
        print(err(f"Items konnten nicht gespeichert werden: {e}"))
        return False


# =============================================================================
# KATEGORIE-OPERATIONEN
# =============================================================================

def get_existing_categories(state: AutoClickerState) -> list[str]:
    """Sammelt alle existierenden Kategorien aus den Items."""
    categories = set()
    for item in state.scan_items.values():
        if item.category:
            categories.add(item.category)
    return sorted(categories)


def shift_category_priorities(state: AutoClickerState, category: str) -> int:
    """Verschiebt alle Items einer Kategorie um +1 in der Priorität.

    Wird genutzt wenn ein neues Item mit Priorität 0 angelegt wird und damit
    "beste" werden soll — alle anderen Items der Kategorie rutschen einen Platz
    nach hinten.
    """
    if not category:
        return 0

    shifted = 0
    with state.lock:
        for item in state.scan_items.values():
            if item.category == category:
                item.priority += 1
                shifted += 1

    if shifted > 0:
        save_scan_items(state)
        print(f"  → {shifted} Item(s) in Kategorie '{category}' nach hinten verschoben")

    return shifted
