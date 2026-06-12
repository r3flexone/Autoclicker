"""
Boss-Scan-Konfigurationen (eine JSON pro Scan unter boss_scans/).
"""

import json
import logging
from pathlib import Path
from typing import Optional

from ..models import BossScanConfig, AutoClickerState, BOSS_ACTION_SKIP
from ..utils import compact_json, atomic_write, save_tag, load_tag, err, warn
from .paths import BOSS_SCANS_DIR
from .serialization import _boss_profile_to_dict, _boss_profile_from_dict
from ._scan_store import ensure_dir, write_scan, list_scan_files, load_all_scans

logger = logging.getLogger("autoclicker")


def ensure_boss_scans_dir() -> Path:
    """Stellt sicher, dass der Boss-Scans-Ordner existiert."""
    return ensure_dir(BOSS_SCANS_DIR)


def save_boss_scan(config: BossScanConfig) -> None:
    """Speichert eine Boss-Scan Konfiguration."""
    data = {
        "name": config.name,
        "scan_region": list(config.scan_region),
        "color_tolerance": config.color_tolerance,
        "default_action": config.default_action,
        "default_scan": config.default_scan,
        "bosses": [_boss_profile_to_dict(b) for b in config.bosses],
        "use_llm": config.use_llm,
        "llm_fallback": config.llm_fallback,
        "use_ocr": config.use_ocr,
        "ocr_fallback": config.ocr_fallback,
    }
    write_scan(BOSS_SCANS_DIR, config.name, data, "Boss-Scan")


def load_boss_scan_file(filepath: Path) -> Optional[BossScanConfig]:
    """Lädt eine Boss-Scan Konfiguration."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        bosses = [_boss_profile_from_dict(b) for b in data.get("bosses", [])]

        return BossScanConfig(
            name=data["name"],
            scan_region=tuple(data.get("scan_region", (0, 0, 100, 100))),
            color_tolerance=data.get("color_tolerance", 30),
            default_action=data.get("default_action", BOSS_ACTION_SKIP),
            default_scan=data.get("default_scan"),
            bosses=bosses,
            use_llm=data.get("use_llm", False),
            llm_fallback=data.get("llm_fallback", True),
            use_ocr=data.get("use_ocr", False),
            ocr_fallback=data.get("ocr_fallback", True),
        )

    except (json.JSONDecodeError, IOError, KeyError, TypeError) as e:
        logger.error(f"Konnte {filepath} nicht laden: {e}")
        return None


def _global_bosses_file() -> Path:
    # Unterordner statt boss_scans/*.json — sonst würde die Datei von
    # list_scan_files als (defekte) Scan-Konfiguration mitgelistet.
    return Path(BOSS_SCANS_DIR) / "global" / "bosses.json"


def save_global_bosses(state: AutoClickerState) -> None:
    """Speichert die globale Boss-Bibliothek (crash-sicher)."""
    with state.lock:
        data = [_boss_profile_to_dict(b) for b in state.global_bosses]
    filepath = _global_bosses_file()
    filepath.parent.mkdir(parents=True, exist_ok=True)
    try:
        atomic_write(filepath, compact_json(data))
        print(save_tag(f"Boss-Bibliothek gespeichert ({len(data)} Boss(e))"))
    except (IOError, OSError) as e:
        print(err(f"Boss-Bibliothek konnte nicht gespeichert werden: {e}"))


def load_global_bosses(state: AutoClickerState) -> None:
    """Lädt die globale Boss-Bibliothek (fehlende Datei = leere Bibliothek)."""
    filepath = _global_bosses_file()
    if not filepath.exists():
        return
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        with state.lock:
            state.global_bosses = [_boss_profile_from_dict(b) for b in data]
            count = len(state.global_bosses)
        print(load_tag(f"{count} globale(r) Boss(e) geladen"))
    except (json.JSONDecodeError, IOError, OSError, KeyError, TypeError, ValueError, UnicodeDecodeError) as e:
        print(warn(f"Boss-Bibliothek konnte nicht geladen werden: {e}"))
        logger.error(f"Konnte {filepath} nicht laden: {e}")


def list_available_boss_scans() -> list[tuple[str, Path]]:
    """Listet alle verfügbaren Boss-Scan Konfigurationen auf."""
    return list_scan_files(BOSS_SCANS_DIR)


def load_all_boss_scans(state: AutoClickerState) -> None:
    """Lädt alle Boss-Scan Konfigurationen."""
    load_all_scans(BOSS_SCANS_DIR, load_boss_scan_file, state.boss_scans, "Boss-Scan")
