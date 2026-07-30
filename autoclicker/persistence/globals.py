"""
Globale Slots, Items und Kategorie-Operationen.

Slots und Items werden in slots/slots.json bzw. items/items.json gespeichert
(eine Datei pro Datentyp, nicht eine pro Eintrag wie bei den Scans).
"""

import json
import logging
from pathlib import Path

from ..models import ItemSlot, AutoClickerState
from ..utils import compact_json, save_tag, load_tag, err, atomic_write
from .migration import KIND_ITEMS, KIND_SLOTS, migrate
from .paths import ITEMS_FILE, SLOTS_FILE
from .serialization import _item_to_dict, _slot_to_dict, _item_from_dict, _slot_from_dict

logger = logging.getLogger("autoclicker")


# =============================================================================
# SLOTS
# =============================================================================

def save_global_slots(state: AutoClickerState) -> None:
    """Speichert alle globalen Slots."""
    with state.lock:
        data = {name: _slot_to_dict(slot) for name, slot in state.global_slots.items()}
    try:
        atomic_write(SLOTS_FILE, compact_json(data))
        print(save_tag(f"{len(data)} Slot(s) gespeichert"))
    except (IOError, OSError) as e:
        print(err(f"Slots konnten nicht gespeichert werden: {e}"))


def load_global_slots(state: AutoClickerState) -> None:
    """Lädt alle globalen Slots."""
    if not Path(SLOTS_FILE).exists():
        return
    try:
        with open(SLOTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        data, _meldungen = migrate(data, KIND_SLOTS)
        # Per-Eintrag absichern — ein einzelner kaputter Slot soll nicht das
        # Laden aller restlichen verhindern.
        for name, s in data.items():
            try:
                state.global_slots[name] = _slot_from_dict(name, s)
            except (KeyError, TypeError, ValueError) as e:
                logger.warning(f"Slot '{name}' übersprungen (ungültig): {e}")
        if state.global_slots:
            print(load_tag(f"{len(state.global_slots)} Slot(s) geladen"))
    except (json.JSONDecodeError, IOError, OSError, KeyError, TypeError, ValueError, UnicodeDecodeError) as e:
        logger.error(f"Slots laden fehlgeschlagen: {e}")


# =============================================================================
# ITEMS
# =============================================================================

def save_global_items(state: AutoClickerState) -> None:
    """Speichert alle globalen Items, sortiert nach Kategorie und Priorität."""
    with state.lock:
        sorted_items = sorted(state.global_items.items(),
                              key=lambda kv: (kv[1].category is None, kv[1].category or "", kv[1].priority))
        data = {name: _item_to_dict(item) for name, item in sorted_items}
    try:
        atomic_write(ITEMS_FILE, compact_json(data))
        print(save_tag(f"{len(data)} Item(s) gespeichert"))
    except (IOError, OSError) as e:
        print(err(f"Items konnten nicht gespeichert werden: {e}"))


def load_global_items(state: AutoClickerState) -> None:
    """Lädt alle globalen Items."""
    if not Path(ITEMS_FILE).exists():
        return
    try:
        with open(ITEMS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        data, _meldungen = migrate(data, KIND_ITEMS)
        # Per-Eintrag absichern — ein einzelnes kaputtes Item soll nicht das
        # Laden aller restlichen verhindern.
        for name, i in data.items():
            try:
                state.global_items[name] = _item_from_dict(i, name)
            except (KeyError, TypeError, ValueError) as e:
                logger.warning(f"Item '{name}' übersprungen (ungültig): {e}")
        if state.global_items:
            print(load_tag(f"{len(state.global_items)} Item(s) geladen"))
    except (json.JSONDecodeError, IOError, OSError, KeyError, TypeError, ValueError, UnicodeDecodeError) as e:
        logger.error(f"Items laden fehlgeschlagen: {e}")


# =============================================================================
# KATEGORIE-OPERATIONEN
# =============================================================================

def get_existing_categories(state: AutoClickerState) -> list[str]:
    """Sammelt alle existierenden Kategorien aus den Items."""
    categories = set()
    for item in state.global_items.values():
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
        for item in state.global_items.values():
            if item.category == category:
                item.priority += 1
                shifted += 1

    if shifted > 0:
        save_global_items(state)
        print(f"  → {shifted} Item(s) in Kategorie '{category}' nach hinten verschoben")

    return shifted
