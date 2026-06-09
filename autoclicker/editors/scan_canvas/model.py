"""
GUI-freier Modell-Layer fürs Scan-Studio.

Lädt/speichert Slots (und perspektivisch Items/Scans) direkt aus den JSON-Dateien
ohne AutoClickerState — der Subprocess hat keinen geteilten State. Format und
Serialisierung sind identisch zu den Konsolen-Editoren (slots/slots.json), damit
beide Wege dieselben Dateien lesen/schreiben.
"""

import json
from pathlib import Path

from ...models import ItemSlot
from ...utils import compact_json, atomic_write
from ...persistence.serialization import _slot_to_dict


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
