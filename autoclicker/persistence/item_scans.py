"""
Item-Scan-Konfigurationen (eine JSON pro Scan unter item_scans/).

update_item_in_scans lebt hier weil es die Scan-JSONs auf der Platte anfasst,
auch wenn der Anlass (Item umbenannt) konzeptuell zur Item-Verwaltung gehört.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from ..models import ClickPoint, ItemScanConfig, AutoClickerState
from .migration import KIND_ITEM_SCAN, migrate
from .sequences import sequence_dir
from .serialization import _item_scan_from_dict, _item_scan_to_dict
from ._scan_store import ensure_dir, write_scan, list_scan_files, load_all_scans, LOAD_EXCEPTIONS

logger = logging.getLogger("autoclicker")


def _item_scans_dir(owner: str) -> Path:
    return sequence_dir(owner) / "item_scans"


def ensure_item_scans_dir(owner: str = "") -> Path:
    """Stellt sicher, dass der Item-Scans-Ordner existiert."""
    if not owner:
        return Path("sequences")
    return ensure_dir(_item_scans_dir(owner))


def save_item_scan(config: ItemScanConfig) -> bool:
    """Speichert eine Item-Scan Konfiguration."""
    if not config.owner_sequence:
        raise ValueError("Item-Scan hat keine Besitzer-Sequenz")
    return write_scan(str(_item_scans_dir(config.owner_sequence)), config.name,
               _item_scan_to_dict(config), "Item-Scan")


def load_item_scan_file(filepath: Path, owner: str = "") -> Optional[ItemScanConfig]:
    """Lädt eine Item-Scan Konfiguration.

    Slots und Items werden vollständig aus derselben Scan-Datei geladen; der Scan
    ist damit unabhängig von allen anderen Scans.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        data, _meldungen = migrate(data, KIND_ITEM_SCAN)

        config = _item_scan_from_dict(data)
        config.owner_sequence = owner or filepath.parent.parent.name
        return config

    except LOAD_EXCEPTIONS as e:
        logger.error(f"Konnte {filepath} nicht laden: {e}")
        return None


def list_available_item_scans(owner: str = "") -> list[tuple[str, Path]]:
    """Listet alle verfügbaren Item-Scan Konfigurationen auf."""
    if not owner:
        return []
    return list_scan_files(str(_item_scans_dir(owner)))


def load_all_item_scans(state: AutoClickerState) -> None:
    """Lädt alle eigenständigen Item-Scan-Konfigurationen."""
    with state.lock:
        owner = state.active_sequence.name if state.active_sequence else ""
    if not owner:
        state.item_scans.clear()
        return
    ordner = str(_item_scans_dir(owner))
    load_all_scans(ordner, lambda pfad: load_item_scan_file(pfad, owner),
                   state.item_scans, "Item-Scan")
    with state.lock:
        if state.active_item_scan not in state.item_scans:
            state.active_item_scan = next(iter(state.item_scans), "")
    bind_item_scan_context(state, state.active_item_scan)


def bind_item_scan_context(state: AutoClickerState, name: str) -> bool:
    """Bindet die TUI-Arbeitsdicts an genau einen eigenständigen Scan."""
    with state.lock:
        cfg = state.item_scans.get(name)
        state.active_item_scan = name if cfg else ""
        state.global_slots = ({slot.name: slot for slot in cfg.slots} if cfg else {})
        state.global_items = ({item.name: item for item in cfg.items} if cfg else {})
    return cfg is not None


def flush_item_scan_context(state: AutoClickerState) -> Optional[ItemScanConfig]:
    """Schreibt die TUI-Arbeitsdicts in ihren Besitzer zurück."""
    with state.lock:
        cfg = state.item_scans.get(state.active_item_scan)
        if cfg is None:
            return None
        cfg.slots = list(state.global_slots.values())
        cfg.items = list(state.global_items.values())
        return cfg


def resolve_scan_references(state: AutoClickerState, sequence=None) -> list[str]:
    """Löst nur Punkt-IDs der Scans gegen die verwendende Sequenz auf."""
    return resolve_klick_referenzen(state, sequence)


def resolve_klick_referenzen(state: AutoClickerState, sequence=None) -> list[str]:
    """Fuellt die Klick-Ziele, die per Punkt-ID gespeichert sind.

    | wer | Feld | fuellt |
    |---|---|---|
    | `ItemProfile` | `confirm_point_id` | `confirm_point` |
    | `BossProfile` | `action_point_id` | `action_x`, `action_y` |
    | `IconScanConfig` | `action_point_id` | `action_x`, `action_y` |

    Gleiches Muster wie `aufloesen()`. Eine tote Referenz wird gemeldet und das
    Klick-Ziel bleibt leer — die Aktion tut dann nichts, statt auf (0, 0) zu klicken.
    """
    meldungen = []
    with state.lock:
        seq = sequence or state.active_sequence
        punkte = {p.id: p for p in (seq.points if seq else [])}
        items = [item for cfg in state.item_scans.values() for item in cfg.items]
        bosse = list(state.global_bosses)
        for cfg in state.boss_scans.values():
            bosse += list(cfg.bosses)
        icons = list(state.icon_scans.values())

    def hol(pid, wo):
        punkt = punkte.get(pid)
        if punkt is None:
            meldungen.append(f"{wo} zeigt auf Punkt #{pid}, den es nicht mehr gibt "
                             f"- Klick entfaellt")
        return punkt

    with state.lock:
        for item in items:
            if item.confirm_point_id is None:
                item.confirm_point = None
                continue
            punkt = hol(item.confirm_point_id, f"Item '{item.name}' (Bestaetigung)")
            item.confirm_point = ClickPoint(punkt.x, punkt.y, punkt.name,
                                            punkt.id) if punkt else None

        for traeger, wo in ([(b, f"Boss '{b.name}'") for b in bosse]
                            + [(i, f"Icon-Scan '{i.name}'") for i in icons]):
            if traeger.action_point_id is None:
                continue
            punkt = hol(traeger.action_point_id, wo)
            if punkt is not None:
                traeger.action_x, traeger.action_y = punkt.x, punkt.y
            else:
                # Kein Rueckfall auf (0, 0): die Aktion wird uebersprungen.
                traeger.action_x = traeger.action_y = 0
    return meldungen


def update_item_in_scans(old_name: str, new_name: str) -> tuple[int, int]:
    """Kompatibilitäts-Helfer ohne globale Wirkung.

    Ein Item gehört genau einem Scan. Dessen Objekt wird vom Editor direkt
    umbenannt und anschliessend als kompletter Scan gespeichert; gleichnamige
    Items anderer Scans dürfen ausdrücklich nicht mitgezogen werden.
    """
    return 0, 0
