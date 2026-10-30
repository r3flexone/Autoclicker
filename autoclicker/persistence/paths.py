"""
Verzeichnis-Konstanten und init_directories.

Alle Pfade an einer Stelle. Beim App-Start wird init_directories() einmal
aufgerufen damit die Ordnerstruktur garantiert existiert.
"""

import os

SEQUENCE_SCREENSHOTS_DIR: str = "screenshots"
SLOT_PRESETS_DIR: str = os.path.join("presets", "slots")
ITEM_PRESETS_DIR: str = os.path.join("presets", "items")
# Sicherungen des Start-Durchgangs. Der Ordner spiegelt die Datenstruktur darunter
# (backups/sequences/<name>.json.bak), sonst ueberschriebe die Sicherung von
# item_scans/foo.json die von boss_scans/foo.json - gleicher Dateiname, anderer Ordner.
# Bewusst NICHT in init_directories(): der Ordner soll erst entstehen, wenn es wirklich
# etwas zu sichern gab. Ein leeres backups/ bei jeder frischen Installation waere Rauschen.
BACKUPS_DIR: str = "backups"


def init_directories() -> None:
    """Erstellt alle benötigten Verzeichnisse."""
    # Lauf-Screenshots und wiederverwendbare Presets sind programmweit. Alle
    # eigentlichen Scan-Daten werden erst im jeweiligen Sequenzordner angelegt.
    for folder in [SEQUENCE_SCREENSHOTS_DIR, SLOT_PRESETS_DIR, ITEM_PRESETS_DIR]:
        os.makedirs(folder, exist_ok=True)
