"""
Item-Editor-Subpaket.

Modul-Aufteilung:
    editor.py     run_global_item_editor + Befehls-Dispatch + Hilfe-Text
    items.py      create_item, edit_item, select_category
    markers.py    Marker-Farben-Sammlung + Duplikat-Erkennung
    autoscan.py   item_autoscan_command (ALLE Slots automatisch)
    learn.py      item_learn_command (Bulk + Single)
    commands.py   rename/template/templates-Befehle

Externe Konsumenten: editors/__init__.py + editors/item_scan_editor.py
brauchen run_global_item_editor, select_category, item_autoscan_command.
"""

from .autoscan import item_autoscan_command
from .editor import run_global_item_editor
from .items import select_category

__all__ = [
    'run_global_item_editor',
    'select_category',
    'item_autoscan_command',
]
