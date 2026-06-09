"""
GUI-freier Modell-Layer fürs Scan-Studio.

Lädt/speichert Slots (und perspektivisch Items/Scans) direkt aus den JSON-Dateien
ohne AutoClickerState — der Subprocess hat keinen geteilten State. Format und
Serialisierung sind identisch zu den Konsolen-Editoren (slots/slots.json), damit
beide Wege dieselben Dateien lesen/schreiben.
"""

import json
from pathlib import Path

from ...models import ItemSlot, ItemProfile
from ...utils import compact_json, atomic_write, sanitize_filename
from ...persistence.serialization import _slot_to_dict, _item_to_dict, _item_from_dict
from ...persistence.paths import TEMPLATES_DIR


def load_slots(slots_file: str) -> dict[str, ItemSlot]:
    """Lädt alle Slots aus slots/slots.json (read-only, ohne State)."""
    path = Path(slots_file)
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError, OSError):
        return {}
    slots: dict[str, ItemSlot] = {}
    for name, s in data.items():
        try:
            slot_color = tuple(s["slot_color"]) if s.get("slot_color") else None
            slots[name] = ItemSlot(
                name=s["name"],
                scan_region=tuple(s["scan_region"]),
                click_pos=tuple(s["click_pos"]),
                slot_color=slot_color,
            )
        except (KeyError, TypeError):
            continue  # defekten Eintrag überspringen
    return slots


def save_slots(slots: dict[str, ItemSlot], slots_file: str) -> bool:
    """Speichert alle Slots nach slots/slots.json (crash-sicher via atomic_write)."""
    path = Path(slots_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = {name: _slot_to_dict(slot) for name, slot in slots.items()}
        atomic_write(path, compact_json(data))
        return True
    except (IOError, OSError):
        return False


def next_slot_name(slots: dict[str, ItemSlot]) -> str:
    """Liefert einen freien Standard-Slotnamen ('Slot 1', 'Slot 2', ...)."""
    n = 1
    while f"Slot {n}" in slots:
        n += 1
    return f"Slot {n}"


def normalize_region(x1: int, y1: int, x2: int, y2: int) -> tuple[int, int, int, int]:
    """Sortiert die Ecken, sodass (links, oben, rechts, unten) gilt."""
    return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


# =============================================================================
# ITEMS
# =============================================================================

def load_items(items_file: str) -> dict[str, ItemProfile]:
    """Lädt alle Items aus items/items.json (read-only, ohne State)."""
    path = Path(items_file)
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError, OSError):
        return {}
    items: dict[str, ItemProfile] = {}
    for name, i in data.items():
        try:
            items[name] = _item_from_dict(i)
        except (KeyError, TypeError):
            continue
    return items


def save_items(items: dict[str, ItemProfile], items_file: str) -> bool:
    """Speichert alle Items nach items/items.json (sortiert wie der Konsolen-Editor)."""
    path = Path(items_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        sorted_items = sorted(
            items.items(),
            key=lambda kv: (kv[1].category is None, kv[1].category or "", kv[1].priority),
        )
        data = {name: _item_to_dict(item) for name, item in sorted_items}
        atomic_write(path, compact_json(data))
        return True
    except (IOError, OSError):
        return False


def next_item_name(items: dict[str, ItemProfile]) -> str:
    """Liefert einen freien Standard-Itemnamen ('Item 1', 'Item 2', ...)."""
    n = 1
    while f"Item {n}" in items:
        n += 1
    return f"Item {n}"


def existing_categories(items: dict[str, ItemProfile]) -> list[str]:
    """Alle vorkommenden Kategorien (sortiert, ohne None)."""
    return sorted({i.category for i in items.values() if i.category})


def crop_region(full_img, region: tuple[int, int, int, int],
                virtual_left: int, virtual_top: int):
    """Schneidet die Slot-Region (Bildschirm-Koordinaten) aus dem Vollbild-Screenshot."""
    x1 = max(0, region[0] - virtual_left)
    y1 = max(0, region[1] - virtual_top)
    x2 = min(full_img.width, region[2] - virtual_left)
    y2 = min(full_img.height, region[3] - virtual_top)
    if x2 <= x1 or y2 <= y1:
        return None
    return full_img.crop((x1, y1, x2, y2))


def save_template(img, name: str) -> str | None:
    """Speichert ein Bild als Template-PNG in items/templates/. Gibt den Dateinamen zurück."""
    if img is None:
        return None
    Path(TEMPLATES_DIR).mkdir(parents=True, exist_ok=True)
    filename = f"{sanitize_filename(name)}.png"
    try:
        img.save(Path(TEMPLATES_DIR) / filename)
        return filename
    except (IOError, OSError, ValueError):
        return None
