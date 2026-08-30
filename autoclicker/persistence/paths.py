"""
Verzeichnis-Konstanten und init_directories.

Alle Pfade an einer Stelle. Beim App-Start wird init_directories() einmal
aufgerufen damit die Ordnerstruktur garantiert existiert.
"""

import os

# Ordner aus der Zeit vor den Besitzeinheiten. Sie werden NICHT mehr beschrieben —
# aktuelle Daten liegen unter sequences/<name>/. Stehen bleiben sie fuer genau
# einen Zweck: der Factory-Reset (handlers.py) soll einen solchen Altbestand
# sicher wegraeumen koennen, falls er auf einer Platte noch herumliegt.
# `SLOTS_FILE`, `ITEMS_FILE` und `SCREENSHOTS_DIR` (slots/Screenshots) sind mit
# dem globalen Bestand ersatzlos entfallen; niemand las sie mehr.
BOSS_SCANS_DIR: str = "boss_scans"
ICON_SCANS_DIR: str = "icon_scans"
ITEM_SCANS_DIR: str = "item_scans"
SLOTS_DIR: str = "slots"
ITEMS_DIR: str = "items"

SEQUENCE_SCREENSHOTS_DIR: str = "screenshots"
# Rueckfall von `_template_path()`, wenn ein Aufrufer keinen Ordner mitgibt. Der
# Ordner existiert im heutigen Layout NICHT — der Rueckfall findet also nichts,
# und das ist Absicht: er soll auffallen, nicht stillschweigend woandershin
# greifen. Wer Vorlagen sucht, nimmt `active_templates_dir(state)` bzw.
# `sequence_templates_dir(name)`.
TEMPLATES_DIR: str = os.path.join(ITEMS_DIR, "templates")
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
