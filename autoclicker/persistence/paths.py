"""
Verzeichnis-Konstanten und init_directories.

Alle Pfade an einer Stelle. Beim App-Start wird init_directories() einmal
aufgerufen damit die Ordnerstruktur garantiert existiert.
"""

import os

# Daten-Verzeichnisse (relativ zum Arbeitsverzeichnis)
BOSS_SCANS_DIR: str = "boss_scans"
ITEM_SCANS_DIR: str = "item_scans"
SLOTS_DIR: str = "slots"
ITEMS_DIR: str = "items"
SCREENSHOTS_DIR: str = os.path.join(SLOTS_DIR, "Screenshots")
SEQUENCE_SCREENSHOTS_DIR: str = "screenshots"
TEMPLATES_DIR: str = os.path.join(ITEMS_DIR, "templates")
SLOTS_FILE: str = os.path.join(SLOTS_DIR, "slots.json")
ITEMS_FILE: str = os.path.join(ITEMS_DIR, "items.json")
SLOT_PRESETS_DIR: str = os.path.join(SLOTS_DIR, "presets")
ITEM_PRESETS_DIR: str = os.path.join(ITEMS_DIR, "presets")


def init_directories() -> None:
    """Erstellt alle benötigten Verzeichnisse."""
    for folder in [ITEM_SCANS_DIR, BOSS_SCANS_DIR, SLOTS_DIR, ITEMS_DIR, SCREENSHOTS_DIR,
                   SEQUENCE_SCREENSHOTS_DIR, TEMPLATES_DIR, SLOT_PRESETS_DIR, ITEM_PRESETS_DIR]:
        os.makedirs(folder, exist_ok=True)
