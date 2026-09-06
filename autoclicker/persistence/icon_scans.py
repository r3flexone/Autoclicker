"""
Icon-Scan-Konfigurationen (eine JSON pro Scan unter icon_scans/).

Ein Icon-Scan erkennt ein einzelnes Symbol/Icon (z.B. ein rotes "!") per
Template oder Farb-Marker in einer Region und führt bei Fund eine Aktion aus.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from ..models import (
    DEFAULT_MIN_CONFIDENCE, IconScanConfig, AutoClickerState, ICON_ACTION_CLICK,
)
from .migration import KIND_ICON_SCAN, migrate
from .sequences import sequence_dir
from ._scan_store import ensure_dir, write_scan, list_scan_files, load_all_scans, LOAD_EXCEPTIONS
from .serialization import _icon_scan_to_dict, _klick_referenz

logger = logging.getLogger("autoclicker")


def _icon_scans_dir(owner: str) -> Path:
    return sequence_dir(owner) / "icon_scans"


def ensure_icon_scans_dir(owner: str = "") -> Path:
    """Stellt sicher, dass der Icon-Scans-Ordner existiert."""
    return ensure_dir(_icon_scans_dir(owner)) if owner else Path("sequences")


def save_icon_scan(config: IconScanConfig) -> bool:
    """Speichert eine Icon-Scan Konfiguration."""
    if not config.owner_sequence:
        raise ValueError("Icon-Scan hat keine Besitzer-Sequenz")
    return write_scan(str(_icon_scans_dir(config.owner_sequence)), config.name,
               _icon_scan_to_dict(config), "Icon-Scan")


def load_icon_scan_file(filepath: Path, owner: str = "") -> Optional[IconScanConfig]:
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
            action_point_id=_klick_referenz(
                data, f"Icon-Scan '{data['name']}'",
                "Klick-Punkt im Icon-Scan-Editor neu setzen"),
            action_key=data.get("action_key"),
            action_delay=data.get("action_delay", 0),
            owner_sequence=owner or filepath.parent.parent.name,
        )

    except LOAD_EXCEPTIONS as e:
        logger.error(f"Konnte {filepath} nicht laden: {e}")
        return None


def list_available_icon_scans(owner: str = "") -> list[tuple[str, Path]]:
    """Listet alle verfügbaren Icon-Scan Konfigurationen auf."""
    return list_scan_files(str(_icon_scans_dir(owner))) if owner else []


def load_all_icon_scans(state: AutoClickerState) -> None:
    """Lädt alle Icon-Scan Konfigurationen."""
    owner = state.active_sequence.name if state.active_sequence else ""
    if not owner:
        state.icon_scans.clear()
        return
    ordner = str(_icon_scans_dir(owner))
    load_all_scans(ordner, lambda pfad: load_icon_scan_file(pfad, owner),
                   state.icon_scans, "Icon-Scan")
