"""
Gemeinsame Bausteine für die datei-basierten Scan-Konfigurationen
(item_scans / boss_scans / icon_scans).

Diese Module folgen alle demselben Muster: ein Ordner mit einer JSON pro
Konfiguration. Das mechanische Skelett (Ordner anlegen, Datei schreiben,
Verzeichnis auflisten, alle laden) liegt hier zentral — die typ-spezifische
Serialisierung (Config ↔ dict) bleibt im jeweiligen Modul.
"""

import json
import logging
from pathlib import Path
from typing import Callable

from ..utils import compact_json, sanitize_filename, save_tag, load_tag, err, atomic_write

logger = logging.getLogger("autoclicker")


def ensure_dir(directory: str) -> Path:
    """Stellt sicher, dass der Scan-Ordner existiert."""
    path = Path(directory)
    path.mkdir(exist_ok=True)
    return path


def write_scan(directory: str, name: str, data: dict, type_label: str) -> None:
    """Schreibt eine Scan-Konfiguration als JSON-Datei (<dir>/<name>.json)."""
    ensure_dir(directory)
    filename = f"{sanitize_filename(name)}.json"
    try:
        atomic_write(Path(directory) / filename, compact_json(data))
        print(save_tag(f"{type_label} '{name}' gespeichert in '{directory}/'"))
    except (IOError, OSError) as e:
        print(err(f"{type_label} konnte nicht gespeichert werden: {e}"))


def list_scan_files(directory: str) -> list[tuple[str, Path]]:
    """Listet alle (name, pfad) der *.json im Scan-Ordner. Korrupte werden übersprungen."""
    scan_dir = Path(directory)
    if not scan_dir.exists():
        return []

    scans = []
    for f in scan_dir.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as file:
                data = json.load(file)
                scans.append((data.get("name", f.stem), f))
        except (json.JSONDecodeError, IOError, KeyError, TypeError):
            pass  # Ungültige/korrupte Datei überspringen
    return scans


def load_all_scans(directory: str, loader: Callable, target: dict, type_label: str) -> None:
    """Lädt alle Konfigurationen aus dem Ordner in das target-Dict (Key = config.name)."""
    for name, path in list_scan_files(directory):
        config = loader(path)
        if config:
            target[config.name] = config
    if target:
        print(load_tag(f"{len(target)} {type_label}(s) geladen"))
