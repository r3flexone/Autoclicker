"""
GUI-freier Modell-Layer für Slots, Items und Templates.

Lädt/speichert direkt aus den JSON-Dateien ohne `AutoClickerState` — der
Studio-Subprozess hat keinen geteilten State. Format und Serialisierung sind
identisch zu den Konsolen-Editoren (`slots/slots.json`, `items/items.json`),
damit beide Wege dieselben Dateien lesen und schreiben.

Lag bis zum Umbau unter `editors/scan_canvas/` neben dem Dear-PyGui-Fenster.
Das Fenster ist weg — der Modell-Layer nicht: er war von Anfang an ohne GUI
geschrieben und wird jetzt vom Scans-Reiter des Sequenz-Studios benutzt
(`scans.py`).
"""

import json
from pathlib import Path

from ...models import ItemSlot, ItemProfile
from ...utils import (compact_json, atomic_write, sanitize_filename,
                      naechster_freier_name)
from ...persistence.serialization import (
    _slot_to_dict, _item_to_dict, _item_from_dict, _slot_from_dict)
from ...persistence.paths import TEMPLATES_DIR
from ..scan_services import crop_screen_region


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
    if not isinstance(data, dict):
        print(f"WARNUNG: {path} ist kein JSON-Objekt (Top-Level-Liste?) - ignoriert.")
        return {}
    slots: dict[str, ItemSlot] = {}
    for name, s in data.items():
        try:
            slots[name] = _slot_from_dict(name, s)
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
    return naechster_freier_name("Slot", slots)


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
    if not isinstance(data, dict):
        print(f"WARNUNG: {path} ist kein JSON-Objekt (Top-Level-Liste?) - ignoriert.")
        return {}
    items: dict[str, ItemProfile] = {}
    for name, i in data.items():
        try:
            items[name] = _item_from_dict(i, name)
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
    return naechster_freier_name("Item", items)


def existing_categories(items: dict[str, ItemProfile]) -> list[str]:
    """Alle vorkommenden Kategorien (sortiert, ohne None)."""
    return sorted({i.category for i in items.values() if i.category})


def crop_region(full_img, region: tuple[int, int, int, int],
                virtual_left: int, virtual_top: int):
    """Schneidet die Slot-Region (Bildschirm-Koordinaten) aus dem Vollbild-Screenshot."""
    return crop_screen_region(full_img, region, (virtual_left, virtual_top))


def save_template(img, name: str, hintergrund=None) -> str | None:
    """Speichert ein Bild als Template-PNG in items/templates/. Gibt den Dateinamen zurück.

    Items und Bosse teilen sich den Ordner items/templates/. Existiert die
    Zieldatei bereits (z.B. Boss 'X' nach Item 'X'), wird ein nummeriertes
    Suffix (_2, _3, ...) gewaehlt, statt das fremde Template zu ueberschreiben.
    Der tatsaechlich verwendete Dateiname wird zurueckgegeben, damit die Config
    konsistent darauf verweist.
    """
    if img is None:
        return None
    # Mit bekanntem Hintergrund traegt das Template seine Maske selbst: der
    # Vergleich stimmt sonst zu neun Zehnteln ueber die Slot-Flaeche ab.
    if hintergrund:
        try:
            from ...imaging import mit_hintergrund_maske
            img = mit_hintergrund_maske(img, hintergrund)
        except ImportError:
            pass
    Path(TEMPLATES_DIR).mkdir(parents=True, exist_ok=True)
    base = sanitize_filename(name)
    filename = f"{base}.png"
    n = 2
    while (Path(TEMPLATES_DIR) / filename).exists():
        filename = f"{base}_{n}.png"
        n += 1
    try:
        img.save(Path(TEMPLATES_DIR) / filename)
        return filename
    except (IOError, OSError, ValueError):
        return None
