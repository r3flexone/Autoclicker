"""
Preset-Verwaltung für Slots und Items.

Generische Helper (_list/_save/_delete_preset) werden von den typ-spezifischen
list/save/load/delete-Funktionen wiederverwendet.
"""

import json
from pathlib import Path

from ..models import AutoClickerState
from ..utils import compact_json, sanitize_filename, save_tag, load_tag, delete_tag, err, atomic_write
from .globals import save_global_items, save_global_slots
from .migration import KIND_ITEMS, KIND_SLOTS, migrate
from .paths import ITEM_PRESETS_DIR, SLOT_PRESETS_DIR
from .serialization import _item_to_dict, _slot_to_dict, _item_from_dict, _slot_from_dict


# =============================================================================
# GENERISCHE PRESET-HELFER
# =============================================================================

def _list_presets(presets_dir: str) -> list[tuple[str, Path, int]]:
    """Listet alle verfügbaren Presets in einem Verzeichnis auf."""
    preset_dir = Path(presets_dir)
    if not preset_dir.exists():
        return []
    presets = []
    for f in sorted(preset_dir.glob("*.json")):
        try:
            with open(f, "r", encoding="utf-8") as file:
                data = json.load(file)
                presets.append((f.stem, f, len(data)))
        except (json.JSONDecodeError, IOError, OSError, KeyError, TypeError, ValueError, UnicodeDecodeError):
            pass
    return presets


def _save_preset(data: dict, preset_name: str, presets_dir: str, label: str) -> bool:
    """Speichert Daten als Preset-Datei."""
    safe_name = sanitize_filename(preset_name)
    filepath = Path(presets_dir) / f"{safe_name}.json"
    try:
        atomic_write(filepath, compact_json(data))
        print(save_tag(f"{label}-Preset '{preset_name}' gespeichert ({len(data)} {label}s)"))
        return True
    except (IOError, OSError) as e:
        print(err(f"{label}-Preset konnte nicht gespeichert werden: {e}"))
        return False


def _delete_preset(preset_name: str, presets_dir: str, label: str) -> bool:
    """Löscht eine Preset-Datei."""
    safe_name = sanitize_filename(preset_name)
    filepath = Path(presets_dir) / f"{safe_name}.json"
    if not filepath.exists():
        print(err(f"Preset '{preset_name}' nicht gefunden!"))
        return False
    try:
        filepath.unlink()
        print(delete_tag(f"{label}-Preset '{preset_name}' gelöscht"))
        return True
    except OSError as e:
        print(err(f"Preset konnte nicht gelöscht werden: {e}"))
        return False


# =============================================================================
# SLOT-PRESETS
# =============================================================================

def list_slot_presets() -> list[tuple[str, Path, int]]:
    """Listet alle verfügbaren Slot-Presets auf."""
    return _list_presets(SLOT_PRESETS_DIR)


def save_slot_preset(state: AutoClickerState, preset_name: str) -> bool:
    """Speichert aktuelle Slots als Preset."""
    with state.lock:
        data = {name: _slot_to_dict(slot) for name, slot in state.global_slots.items()}
    if not data:
        print(err("Keine Slots vorhanden zum Speichern!"))
        return False
    return _save_preset(data, preset_name, SLOT_PRESETS_DIR, "Slot")


def load_slot_preset(state: AutoClickerState, preset_name: str) -> bool:
    """Lädt ein Slot-Preset."""
    safe_name = sanitize_filename(preset_name)
    filepath = Path(SLOT_PRESETS_DIR) / f"{safe_name}.json"
    if not filepath.exists():
        print(err(f"Preset '{preset_name}' nicht gefunden!"))
        return False
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        data, _meldungen = migrate(data, KIND_SLOTS)
        if not isinstance(data, dict):
            raise TypeError("Slot-Preset muss ein JSON-Objekt sein")
        geladen = {name: _slot_from_dict(name, s) for name, s in data.items()}
        with state.lock:
            state.global_slots = geladen
            hat_scan = state.active_item_scan in state.item_scans
        # Der Assistent lädt Presets auch vor dem Anlegen seines ersten Scans.
        if hat_scan and not save_global_slots(state):
            return False
        print(load_tag(f"Slot-Preset '{preset_name}' geladen ({len(geladen)} Slots)"))
        return True
    except (json.JSONDecodeError, IOError, OSError, KeyError, TypeError, ValueError, UnicodeDecodeError) as e:
        print(err(f"Preset laden fehlgeschlagen: {e}"))
        return False


def delete_slot_preset(preset_name: str) -> bool:
    """Löscht ein Slot-Preset."""
    return _delete_preset(preset_name, SLOT_PRESETS_DIR, "Slot")


# =============================================================================
# ITEM-PRESETS
# =============================================================================

def list_item_presets() -> list[tuple[str, Path, int]]:
    """Listet alle verfügbaren Item-Presets auf."""
    return _list_presets(ITEM_PRESETS_DIR)


def save_item_preset(state: AutoClickerState, preset_name: str) -> bool:
    """Speichert aktuelle Items als Preset."""
    with state.lock:
        sorted_items = sorted(state.global_items.items(),
                              key=lambda kv: (kv[1].category is None, kv[1].category or "", kv[1].priority))
        data = {name: _item_to_dict(item) for name, item in sorted_items}
    if not data:
        print(err("Keine Items vorhanden zum Speichern!"))
        return False
    return _save_preset(data, preset_name, ITEM_PRESETS_DIR, "Item")


def load_item_preset(state: AutoClickerState, preset_name: str) -> bool:
    """Lädt ein Item-Preset."""
    safe_name = sanitize_filename(preset_name)
    filepath = Path(ITEM_PRESETS_DIR) / f"{safe_name}.json"
    if not filepath.exists():
        print(err(f"Preset '{preset_name}' nicht gefunden!"))
        return False
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        data, _meldungen = migrate(data, KIND_ITEMS)
        if not isinstance(data, dict):
            raise TypeError("Item-Preset muss ein JSON-Objekt sein")
        geladen = {name: _item_from_dict(i, name) for name, i in data.items()}
        with state.lock:
            state.global_items = geladen
            hat_scan = state.active_item_scan in state.item_scans
        if hat_scan and not save_global_items(state):
            return False
        print(load_tag(f"Item-Preset '{preset_name}' geladen ({len(geladen)} Items)"))
        return True
    except (json.JSONDecodeError, IOError, OSError, KeyError, TypeError, ValueError, UnicodeDecodeError) as e:
        print(err(f"Preset laden fehlgeschlagen: {e}"))
        return False


def delete_item_preset(preset_name: str) -> bool:
    """Löscht ein Item-Preset."""
    return _delete_preset(preset_name, ITEM_PRESETS_DIR, "Item")
