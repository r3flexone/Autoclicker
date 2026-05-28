"""
Icon-Scan-Konfigurationen (eine JSON pro Scan unter icon_scans/).

Ein Icon-Scan erkennt ein einzelnes Symbol/Icon (z.B. ein rotes "!") per
Template oder Farb-Marker in einer Region und führt bei Fund eine Aktion aus.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from ..models import IconScanConfig, AutoClickerState, ICON_ACTION_CLICK
from ..utils import compact_json, sanitize_filename, save_tag, load_tag, err
from .paths import ICON_SCANS_DIR

logger = logging.getLogger("autoclicker")


def ensure_icon_scans_dir() -> Path:
    """Stellt sicher, dass der Icon-Scans-Ordner existiert."""
    path = Path(ICON_SCANS_DIR)
    path.mkdir(exist_ok=True)
    return path


def save_icon_scan(config: IconScanConfig) -> None:
    """Speichert eine Icon-Scan Konfiguration."""
    ensure_icon_scans_dir()

    data = {
        "name": config.name,
        "scan_region": list(config.scan_region),
        "template": config.template,
        "min_confidence": config.min_confidence,
        "marker_colors": [list(c) for c in config.marker_colors],
        "color_tolerance": config.color_tolerance,
        "action": config.action,
        "action_x": config.action_x,
        "action_y": config.action_y,
        "action_key": config.action_key,
        "action_delay": config.action_delay,
    }

    filename = f"{sanitize_filename(config.name)}.json"
    try:
        with open(Path(ICON_SCANS_DIR) / filename, "w", encoding="utf-8") as f:
            f.write(compact_json(data))
        print(save_tag(f"Icon-Scan '{config.name}' gespeichert in '{ICON_SCANS_DIR}/'"))
    except (IOError, OSError) as e:
        print(err(f"Icon-Scan konnte nicht gespeichert werden: {e}"))


def load_icon_scan_file(filepath: Path) -> Optional[IconScanConfig]:
    """Lädt eine Icon-Scan Konfiguration."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        return IconScanConfig(
            name=data["name"],
            scan_region=tuple(data.get("scan_region", (0, 0, 100, 100))),
            template=data.get("template"),
            min_confidence=data.get("min_confidence", 0.8),
            marker_colors=[tuple(c) for c in data.get("marker_colors", [])],
            color_tolerance=data.get("color_tolerance", 30),
            action=data.get("action", ICON_ACTION_CLICK),
            action_x=data.get("action_x", 0),
            action_y=data.get("action_y", 0),
            action_key=data.get("action_key"),
            action_delay=data.get("action_delay", 0),
        )

    except (json.JSONDecodeError, IOError, KeyError, TypeError) as e:
        logger.error(f"Konnte {filepath} nicht laden: {e}")
        return None


def list_available_icon_scans() -> list[tuple[str, Path]]:
    """Listet alle verfügbaren Icon-Scan Konfigurationen auf."""
    scan_dir = Path(ICON_SCANS_DIR)
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
            pass
    return scans


def load_all_icon_scans(state: AutoClickerState) -> None:
    """Lädt alle Icon-Scan Konfigurationen."""
    for name, path in list_available_icon_scans():
        config = load_icon_scan_file(path)
        if config:
            state.icon_scans[config.name] = config
    if state.icon_scans:
        print(load_tag(f"{len(state.icon_scans)} Icon-Scan(s) geladen"))
