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
from ..utils import compact_json, sanitize_filename, save_tag, load_tag, err, warn
from .paths import ITEM_SCANS_DIR
from .serialization import _item_to_dict, _slot_to_dict, _item_from_dict

logger = logging.getLogger("autoclicker")


def ensure_item_scans_dir() -> Path:
    """Stellt sicher, dass der Item-Scans-Ordner existiert."""
    path = Path(ITEM_SCANS_DIR)
    path.mkdir(exist_ok=True)
    return path


def save_item_scan(config: ItemScanConfig) -> None:
    """Speichert eine Item-Scan Konfiguration."""
    ensure_item_scans_dir()

    data = {
        "name": config.name,
        "color_tolerance": config.color_tolerance,
        "slots": [_slot_to_dict(slot) for slot in config.slots],
        "items": [_item_to_dict(item) for item in config.items]
    }

    filename = f"{sanitize_filename(config.name)}.json"
    try:
        with open(Path(ITEM_SCANS_DIR) / filename, "w", encoding="utf-8") as f:
            f.write(compact_json(data))
        print(save_tag(f"Item-Scan '{config.name}' gespeichert in '{ITEM_SCANS_DIR}/'"))
    except (IOError, OSError) as e:
        print(err(f"Item-Scan konnte nicht gespeichert werden: {e}"))


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
    scan_dir = Path(ITEM_SCANS_DIR)
    if not scan_dir.exists():
        return []

    scans = []
    for f in scan_dir.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as file:
                data = json.load(file)
                name = data.get("name", f.stem)
                scans.append((name, f))
        except (json.JSONDecodeError, IOError, KeyError, TypeError):
            pass  # Ungültige/korrupte Datei überspringen
    return scans


def load_all_item_scans(state: AutoClickerState) -> None:
    """Lädt alle Item-Scan Konfigurationen."""
    for name, path in list_available_item_scans():
        config = load_item_scan_file(path)
        if config:
            state.item_scans[config.name] = config
    if state.item_scans:
        print(load_tag(f"{len(state.item_scans)} Item-Scan(s) geladen"))


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
                with open(scan_file, "w", encoding="utf-8") as f:
                    f.write(compact_json(data))
                updated_scans += 1

        except (json.JSONDecodeError, IOError, KeyError, TypeError) as e:
            failed_scans += 1
            print(f"  {warn(f'Konnte {scan_file.name} nicht aktualisieren: {e}')}")

    return updated_scans, failed_scans
