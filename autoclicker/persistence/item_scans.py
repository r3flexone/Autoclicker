"""
Item-Scan-Konfigurationen (eine JSON pro Scan unter item_scans/).

update_item_in_scans lebt hier weil es die Scan-JSONs auf der Platte anfasst,
auch wenn der Anlass (Item umbenannt) konzeptuell zur Item-Verwaltung gehört.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from ..models import ItemScanConfig, ItemSlot, AutoClickerState
from ..utils import compact_json, warn, atomic_write
from .paths import ITEM_SCANS_DIR
from .serialization import _item_to_dict, _slot_to_dict, _item_from_dict
from ._scan_store import ensure_dir, write_scan, list_scan_files, load_all_scans

logger = logging.getLogger("autoclicker")


def ensure_item_scans_dir() -> Path:
    """Stellt sicher, dass der Item-Scans-Ordner existiert."""
    return ensure_dir(ITEM_SCANS_DIR)


def save_item_scan(config: ItemScanConfig) -> None:
    """Speichert eine Item-Scan Konfiguration."""
    data = {
        "name": config.name,
        "color_tolerance": config.color_tolerance,
        "slots": [_slot_to_dict(slot) for slot in config.slots],
        "items": [_item_to_dict(item) for item in config.items]
    }
    write_scan(ITEM_SCANS_DIR, config.name, data, "Item-Scan")


def load_item_scan_file(filepath: Path) -> Optional[ItemScanConfig]:
    """Lädt eine Item-Scan Konfiguration."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        slots = []
        for s in data.get("slots", []):
            slot_color = s.get("slot_color")
            if slot_color:
                slot_color = tuple(slot_color)
            slot = ItemSlot(
                name=s["name"],
                scan_region=tuple(s["scan_region"]),
                click_pos=tuple(s["click_pos"]),
                slot_color=slot_color
            )
            slots.append(slot)

        items = [_item_from_dict(i) for i in data.get("items", [])]

        return ItemScanConfig(
            name=data["name"],
            slots=slots,
            items=items,
            color_tolerance=data.get("color_tolerance", 40)
        )

    except (json.JSONDecodeError, IOError, KeyError, TypeError) as e:
        logger.error(f"Konnte {filepath} nicht laden: {e}")
        return None


def list_available_item_scans() -> list[tuple[str, Path]]:
    """Listet alle verfügbaren Item-Scan Konfigurationen auf."""
    return list_scan_files(ITEM_SCANS_DIR)


def load_all_item_scans(state: AutoClickerState) -> None:
    """Lädt alle Item-Scan Konfigurationen."""
    load_all_scans(ITEM_SCANS_DIR, load_item_scan_file, state.item_scans, "Item-Scan")


def update_item_in_scans(old_name: str, new_name: str,
                          new_template: Optional[str] = None) -> tuple[int, int]:
    """Aktualisiert ein Item in allen Scan-Konfigurationen (beim Rename).

    Returns:
        (updated_count, failed_count) - Anzahl aktualisierter und fehlgeschlagener Scans.
    """
    updated_scans = 0
    failed_scans = 0
    scan_dir = Path(ITEM_SCANS_DIR)

    if not scan_dir.exists():
        return 0, 0

    for scan_file in scan_dir.glob("*.json"):
        try:
            with open(scan_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            modified = False
            for item in data.get("items", []):
                if item.get("name") == old_name:
                    item["name"] = new_name
                    if new_template:
                        item["template"] = new_template
                    modified = True

            if modified:
                atomic_write(scan_file, compact_json(data))
                updated_scans += 1

        except (json.JSONDecodeError, IOError, KeyError, TypeError) as e:
            failed_scans += 1
            print(f"  {warn(f'Konnte {scan_file.name} nicht aktualisieren: {e}')}")

    return updated_scans, failed_scans
