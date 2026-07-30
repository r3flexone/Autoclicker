"""
Icon-Scan-Konfigurationen (eine JSON pro Scan unter icon_scans/).

Ein Icon-Scan erkennt ein einzelnes Symbol/Icon (z.B. ein rotes "!") per
Template oder Farb-Marker in einer Region und führt bei Fund eine Aktion aus.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from ..config import DEFAULT_MIN_CONFIDENCE
from ..models import IconScanConfig, AutoClickerState, ICON_ACTION_CLICK
from .migration import KIND_ICON_SCAN, migrate
from .paths import ICON_SCANS_DIR
from ._scan_store import ensure_dir, write_scan, list_scan_files, load_all_scans, LOAD_EXCEPTIONS
from .serialization import _icon_scan_to_dict

logger = logging.getLogger("autoclicker")


def ensure_icon_scans_dir() -> Path:
    """Stellt sicher, dass der Icon-Scans-Ordner existiert."""
    return ensure_dir(ICON_SCANS_DIR)


def save_icon_scan(config: IconScanConfig) -> None:
    """Speichert eine Icon-Scan Konfiguration."""
    write_scan(ICON_SCANS_DIR, config.name, _icon_scan_to_dict(config), "Icon-Scan")


def load_icon_scan_file(filepath: Path) -> Optional[IconScanConfig]:
    """Lädt eine Icon-Scan Konfiguration."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        data, _meldungen = migrate(data, KIND_ICON_SCAN)

        return IconScanConfig(
            name=data["name"],
            scan_region=tuple(data.get("scan_region", (0, 0, 100, 100))),
            template=data.get("template"),
            min_confidence=data.get("min_confidence", DEFAULT_MIN_CONFIDENCE),
            marker_colors=[tuple(c) for c in data.get("marker_colors", [])],
            color_tolerance=data.get("color_tolerance", 30),
            action=data.get("action", ICON_ACTION_CLICK),
            action_x=data.get("action_x", 0),
            action_y=data.get("action_y", 0),
            action_key=data.get("action_key"),
            action_delay=data.get("action_delay", 0),
        )

    except LOAD_EXCEPTIONS as e:
        logger.error(f"Konnte {filepath} nicht laden: {e}")
        return None


def list_available_icon_scans() -> list[tuple[str, Path]]:
    """Listet alle verfügbaren Icon-Scan Konfigurationen auf."""
    return list_scan_files(ICON_SCANS_DIR)


def load_all_icon_scans(state: AutoClickerState) -> None:
    """Lädt alle Icon-Scan Konfigurationen."""
    load_all_scans(ICON_SCANS_DIR, load_icon_scan_file, state.icon_scans, "Icon-Scan")
