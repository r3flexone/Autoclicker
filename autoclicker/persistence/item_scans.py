"""
Item-Scan-Konfigurationen (eine JSON pro Scan unter item_scans/).

update_item_in_scans lebt hier weil es die Scan-JSONs auf der Platte anfasst,
auch wenn der Anlass (Item umbenannt) konzeptuell zur Item-Verwaltung gehört.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from ..models import ItemScanConfig, AutoClickerState
from ..utils import compact_json, warn, atomic_write
from .migration import KIND_ITEM_SCAN, migrate
from .paths import ITEM_SCANS_DIR
from .serialization import _item_scan_to_dict
from ._scan_store import ensure_dir, write_scan, list_scan_files, load_all_scans, LOAD_EXCEPTIONS

logger = logging.getLogger("autoclicker")


def ensure_item_scans_dir() -> Path:
    """Stellt sicher, dass der Item-Scans-Ordner existiert."""
    return ensure_dir(ITEM_SCANS_DIR)


def save_item_scan(config: ItemScanConfig) -> None:
    """Speichert eine Item-Scan Konfiguration."""
    write_scan(ITEM_SCANS_DIR, config.name, _item_scan_to_dict(config), "Item-Scan")


def load_item_scan_file(filepath: Path) -> Optional[ItemScanConfig]:
    """Lädt eine Item-Scan Konfiguration.

    Slots und Items bleiben hier LEER - in der Datei stehen nur Namen. Gefüllt werden sie
    von `resolve_scan_references(state)`, weil dafür die globalen Slots/Items gebraucht
    werden und die hängen am State.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        data, _meldungen = migrate(data, KIND_ITEM_SCAN)

        return ItemScanConfig(
            name=data["name"],
            slot_names=[str(n) for n in data.get("slot_names", [])],
            item_names=[str(n) for n in data.get("item_names", [])],
            color_tolerance=data.get("color_tolerance", 40),
            learn_unknown=data.get("learn_unknown", False)
        )

    except LOAD_EXCEPTIONS as e:
        logger.error(f"Konnte {filepath} nicht laden: {e}")
        return None


def list_available_item_scans() -> list[tuple[str, Path]]:
    """Listet alle verfügbaren Item-Scan Konfigurationen auf."""
    return list_scan_files(ITEM_SCANS_DIR)


def load_all_item_scans(state: AutoClickerState) -> None:
    """Lädt alle Item-Scan Konfigurationen und löst ihre Referenzen auf."""
    load_all_scans(ITEM_SCANS_DIR, load_item_scan_file, state.item_scans, "Item-Scan")
    for meldung in resolve_scan_references(state):
        print(warn(meldung))


def resolve_scan_references(state: AutoClickerState) -> list[str]:
    """Füllt `slots`/`items` jedes Item-Scans aus den globalen Slots/Items.

    Der globale Eintrag ist die Wahrheit: ändert man Marker-Farben, Template oder
    Priorität eines Items, wirkt das ab sofort in jedem Scan, der es benutzt. Vorher lag
    im Scan eine Kopie, die nichts davon mitbekam.

    Gibt Klartext-Meldungen zu Namen zurück, die es global nicht (mehr) gibt. Der Scan
    läuft dann mit dem Rest weiter - lieber ein Slot weniger als ein toter Scan.
    """
    meldungen = []
    with state.lock:
        globale_slots = dict(state.global_slots)
        globale_items = dict(state.global_items)
        scans = list(state.item_scans.values())

    for config in scans:
        slots, fehlende_slots = [], []
        for name in config.slot_names:
            if name in globale_slots:
                slots.append(globale_slots[name])
            else:
                fehlende_slots.append(name)

        items, fehlende_items = [], []
        for name in config.item_names:
            if name in globale_items:
                items.append(globale_items[name])
            else:
                fehlende_items.append(name)

        with state.lock:
            config.slots = slots
            config.items = items

        if fehlende_slots:
            meldungen.append(f"Scan '{config.name}': Slot(s) fehlen in slots.json - "
                             f"{', '.join(fehlende_slots)}")
        if fehlende_items:
            meldungen.append(f"Scan '{config.name}': Item(s) fehlen in items.json - "
                             f"{', '.join(fehlende_items)}")
    return meldungen


def update_item_in_scans(old_name: str, new_name: str,
                          new_template: Optional[str] = None) -> tuple[int, int]:
    """Zieht einen umbenannten Item-Namen in allen Scan-Dateien nach.

    Der Name IST die Referenz - beim Umbenennen zeigt sie sonst ins Leere. Alles andere
    (Marker, Template, Priorität) braucht kein Nachziehen mehr, seit der Scan nur noch
    verweist statt zu kopieren; `new_template` bleibt nur der Signatur-Kompatibilität
    wegen erhalten und wird nicht mehr gebraucht.

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

            # Auch dieser Weg schreibt die Datei - also durch die gleiche Schleuse wie
            # der Loader. Sonst waere Umbenennen der einzige Save, der Altformat
            # unveraendert zurueckschreibt.
            data, meldungen = migrate(data, KIND_ITEM_SCAN)
            modified = bool(meldungen)
            namen = data.get("item_names") or []
            if old_name in namen:
                data["item_names"] = [new_name if n == old_name else n for n in namen]
                modified = True

            if modified:
                atomic_write(scan_file, compact_json(data))
                updated_scans += 1

        except (json.JSONDecodeError, IOError, KeyError, TypeError) as e:
            failed_scans += 1
            print(f"  {warn(f'Konnte {scan_file.name} nicht aktualisieren: {e}')}")

    return updated_scans, failed_scans
