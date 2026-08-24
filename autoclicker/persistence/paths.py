"""
Verzeichnis-Konstanten und init_directories.

Alle Pfade an einer Stelle. Beim App-Start wird init_directories() einmal
aufgerufen damit die Ordnerstruktur garantiert existiert.
"""

import os

# Nur noch für das sichere Erkennen/Zurücksetzen alter, typweise getrennter
# Bestände. Aktuelle Scan-Daten liegen unter sequences/<name>/.
BOSS_SCANS_DIR: str = "boss_scans"
ICON_SCANS_DIR: str = "icon_scans"
ITEM_SCANS_DIR: str = "item_scans"
SLOTS_DIR: str = "slots"
ITEMS_DIR: str = "items"
SCREENSHOTS_DIR: str = os.path.join(SLOTS_DIR, "Screenshots")
# Je Item-Scan ein eingefrorener Bildschirm, auf dem seine Slots liegen. Ein
# Unterordner in item_scans/ und keine Datei daneben: `list_scan_files()` sieht
# nur `*.json` im Ordner selbst, ein PNG dort wäre trotzdem Rauschen zwischen
# den Konfigurationen. Der Ursprung des virtuellen Desktops steht IM PNG (siehe
# editors/sequence_studio/scans.py) — sonst wäre es eine zweite Datei, die mit
# der ersten synchron bleiben müsste.
SCAN_SHOTS_DIR: str = os.path.join(ITEM_SCANS_DIR, "bilder")
SEQUENCE_SCREENSHOTS_DIR: str = "screenshots"
TEMPLATES_DIR: str = os.path.join(ITEMS_DIR, "templates")
SLOTS_FILE: str = os.path.join(SLOTS_DIR, "slots.json")
ITEMS_FILE: str = os.path.join(ITEMS_DIR, "items.json")
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
