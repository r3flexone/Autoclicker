"""
Boss-Scan-Konfigurationen (eine JSON pro Scan unter boss_scans/).
"""

import json
import logging
from pathlib import Path
from typing import Optional

from ..models import BossScanConfig, AutoClickerState, BOSS_ACTION_SKIP
from ..utils import compact_json, sanitize_filename, save_tag, load_tag, err
from .paths import BOSS_SCANS_DIR
from .serialization import _boss_profile_to_dict, _boss_profile_from_dict

logger = logging.getLogger("autoclicker")


def ensure_boss_scans_dir() -> Path:
    """Stellt sicher, dass der Boss-Scans-Ordner existiert."""
    path = Path(BOSS_SCANS_DIR)
    path.mkdir(exist_ok=True)
    return path


def save_boss_scan(config: BossScanConfig) -> None:
    """Speichert eine Boss-Scan Konfiguration."""
    ensure_boss_scans_dir()

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

    filename = f"{sanitize_filename(config.name)}.json"
    try:
        with open(Path(BOSS_SCANS_DIR) / filename, "w", encoding="utf-8") as f:
            f.write(compact_json(data))
        print(save_tag(f"Boss-Scan '{config.name}' gespeichert in '{BOSS_SCANS_DIR}/'"))
    except (IOError, OSError) as e:
        print(err(f"Boss-Scan konnte nicht gespeichert werden: {e}"))


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


def list_available_boss_scans() -> list[tuple[str, Path]]:
    """Listet alle verfügbaren Boss-Scan Konfigurationen auf."""
    scan_dir = Path(BOSS_SCANS_DIR)
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


def load_all_boss_scans(state: AutoClickerState) -> None:
    """Lädt alle Boss-Scan Konfigurationen."""
    for name, path in list_available_boss_scans():
        config = load_boss_scan_file(path)
        if config:
            state.boss_scans[config.name] = config
    if state.boss_scans:
        print(load_tag(f"{len(state.boss_scans)} Boss-Scan(s) geladen"))
