"""
Boss-Scan-Konfigurationen (eine JSON pro Scan unter boss_scans/).
"""

import json
import logging
from pathlib import Path
from typing import Optional

from ..models import BossScanConfig, AutoClickerState, BOSS_ACTION_SKIP
from ..utils import compact_json, atomic_write, save_tag, load_tag, err, warn, sanitize_filename
from .migration import KIND_BOSS_SCAN, KIND_GLOBAL_BOSSES, migrate
from .sequences import sequence_dir
from .serialization import _boss_profile_to_dict, _boss_profile_from_dict, _boss_scan_to_dict
from ._scan_store import ensure_dir, write_scan, list_scan_files, LOAD_EXCEPTIONS

logger = logging.getLogger("autoclicker")


def _boss_scans_dir(owner: str) -> Path:
    return sequence_dir(owner) / "boss_scans"


def ensure_boss_scans_dir(owner: str = "") -> Path:
    """Stellt sicher, dass der Boss-Scans-Ordner existiert."""
    return ensure_dir(_boss_scans_dir(owner)) if owner else Path("sequences")


def boss_scan_name_erlaubt(name: str) -> bool:
    """Die Bibliothek und ein Scan dürfen niemals dieselbe Datei belegen."""
    return sanitize_filename(name) != "bibliothek"


def save_boss_scan(config: BossScanConfig) -> bool:
    """Speichert eine Boss-Scan Konfiguration."""
    if not config.owner_sequence:
        raise ValueError("Boss-Scan hat keine Besitzer-Sequenz")
    if not boss_scan_name_erlaubt(config.name):
        print(err("Der Scan-Name 'bibliothek' ist für die Boss-Bibliothek reserviert."))
        return False
    try:
        return write_scan(str(_boss_scans_dir(config.owner_sequence)), config.name,
                          _boss_scan_to_dict(config), "Boss-Scan")
    except OSError as e:
        print(err(f"Boss-Scan konnte nicht gespeichert werden: {e}"))
        return False


def load_boss_scan_file(filepath: Path, owner: str = "") -> Optional[BossScanConfig]:
    """Lädt eine Boss-Scan Konfiguration."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        data, _meldungen = migrate(data, KIND_BOSS_SCAN)
        if not isinstance(data, dict):
            raise TypeError("Boss-Scan muss ein JSON-Objekt sein")

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
            owner_sequence=owner or filepath.parent.parent.name,
        )

    except LOAD_EXCEPTIONS as e:
        logger.error(f"Konnte {filepath} nicht laden: {e}")
        return None


def _global_bosses_file(owner: str) -> Path:
    # Reservierter Dateiname; die Scan-Auswahl schliesst ihn aus.
    return _boss_scans_dir(owner) / "bibliothek.json"


def save_global_bosses(state: AutoClickerState, owner: str = "") -> bool:
    """Speichert die globale Boss-Bibliothek (crash-sicher)."""
    with state.lock:
        data = [_boss_profile_to_dict(b) for b in state.global_bosses]
    owner = owner or (state.active_sequence.name if state.active_sequence else "")
    if not owner:
        return False
    filepath = _global_bosses_file(owner)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    try:
        atomic_write(filepath, compact_json(data))
        print(save_tag(f"Boss-Bibliothek gespeichert ({len(data)} Boss(e))"))
        return True
    except (IOError, OSError) as e:
        print(err(f"Boss-Bibliothek konnte nicht gespeichert werden: {e}"))
        return False


def load_global_bosses(state: AutoClickerState, owner: str = "") -> None:
    """Lädt die globale Boss-Bibliothek (fehlende Datei = leere Bibliothek)."""
    with state.lock:
        owner = owner or (state.active_sequence.name if getattr(state, "active_sequence", None) else "")
        state.global_bosses = []
    if not owner:
        return
    filepath = _global_bosses_file(owner)
    if not filepath.exists():
        return
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        data, _meldungen = migrate(data, KIND_GLOBAL_BOSSES)
        if not isinstance(data, list):
            raise TypeError("Boss-Bibliothek muss eine JSON-Liste sein")
        geladen = [_boss_profile_from_dict(b) for b in data]
        with state.lock:
            state.global_bosses = geladen
            count = len(state.global_bosses)
        print(load_tag(f"{count} globale(r) Boss(e) geladen"))
    except (json.JSONDecodeError, IOError, OSError, KeyError, TypeError, ValueError, UnicodeDecodeError) as e:
        print(warn(f"Boss-Bibliothek konnte nicht geladen werden: {e}"))
        logger.error(f"Konnte {filepath} nicht laden: {e}")


def list_available_boss_scans(owner: str = "") -> list[tuple[str, Path]]:
    """Listet alle verfügbaren Boss-Scan Konfigurationen auf."""
    if not owner:
        return []
    return [(name, pfad) for name, pfad in
            list_scan_files(str(_boss_scans_dir(owner)))
            if pfad.name != "bibliothek.json"]


def load_all_boss_scans(state: AutoClickerState) -> None:
    """Lädt alle Boss-Scan Konfigurationen."""
    owner = state.active_sequence.name if state.active_sequence else ""
    if not owner:
        state.boss_scans.clear()
        return
    geladen = {}
    for _name, pfad in list_available_boss_scans(owner):
        config = load_boss_scan_file(pfad, owner)
        if config is not None:
            geladen[config.name] = config
    with state.lock:
        state.boss_scans = geladen
    if geladen:
        print(load_tag(f"{len(geladen)} Boss-Scan(s) geladen"))
