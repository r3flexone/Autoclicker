"""
Persistenz-Subpaket: Speichern und Laden aller JSON-Dateien.

Modul-Aufteilung:
    paths.py          Verzeichnis-Konstanten + init_directories
    serialization.py  Dataclass ↔ Dict — die eine Quelle fürs Dateiformat (Saver
                      und Start-Durchgang laufen alle durch sie)
    schema.py         Schema-Version: Stempel und Erkennung einer neueren Fassung
    sequences.py      Sequence-Dateien + Punkte
    item_scans.py     ItemScanConfig + Klick-Referenzen der Scans
    boss_scans.py     BossScanConfig + Boss-Bibliothek
    icon_scans.py     IconScanConfig
    _scan_store.py    geteiltes Skelett der drei Scan-Arten (+ LOAD_EXCEPTIONS)
    globals.py        Slot-/Item-Arbeitsansicht der TUI zurück in den Scan, Kategorien
    presets.py        Slot- und Item-Presets
    sweep.py          schickt beim Programmstart ALLE Dateien in einem Durchgang durch
                      Loader und Serializer (gleiche Logik nutzt tools/migrate.py)

Hier stehen nur die Namen, die andere Pakete über `from ..persistence import …`
holen; alles andere importiert man aus dem Untermodul.
"""

from .boss_scans import (
    save_boss_scan, load_boss_scan_file,
    list_available_boss_scans,
    save_global_bosses, load_global_bosses,
)
from .sweep import sweep_on_start
from .icon_scans import (
    save_icon_scan, load_icon_scan_file,
    list_available_icon_scans,
)
from .globals import (
    save_global_slots, save_global_items,
    get_existing_categories, shift_category_priorities,
)
from .item_scans import (
    save_item_scan, load_item_scan_file,
    list_available_item_scans, load_all_item_scans,
    resolve_click_references,
    bind_item_scan_context,
)
from .paths import SEQUENCE_SCREENSHOTS_DIR, init_directories
from .presets import (
    list_slot_presets, save_slot_preset, load_slot_preset, delete_slot_preset,
    list_item_presets, save_item_preset, load_item_preset, delete_item_preset,
)
from .sequences import (
    ensure_sequences_dir, save_sequence_file, load_sequence_file, locate_step, find_sequence_path,
    free_sequence_name, confirm_new_sequence_name,
    list_available_sequences, activate_sequence,
    save_points, get_next_point_id, get_point_by_id, print_points,
    sequence_dir, sequence_file, sequence_templates_dir,
    active_sequence_dir, active_templates_dir, free_template_file,
    point_for_position, resolve,
    resolve_point_references,
)

__all__ = [
    # paths
    'SEQUENCE_SCREENSHOTS_DIR', 'init_directories',
    # sequences
    'ensure_sequences_dir', 'save_sequence_file', 'load_sequence_file', 'locate_step', 'find_sequence_path',
    'free_sequence_name', 'confirm_new_sequence_name',
    'list_available_sequences', 'activate_sequence',
    'save_points', 'get_next_point_id', 'get_point_by_id', 'print_points',
    'sequence_dir', 'sequence_file', 'sequence_templates_dir',
    'active_sequence_dir', 'active_templates_dir', 'free_template_file',
    'point_for_position', 'resolve',
    'resolve_point_references',
    # item_scans
    'save_item_scan', 'load_item_scan_file',
    'list_available_item_scans', 'load_all_item_scans',
    'resolve_click_references',
    'bind_item_scan_context',
    # boss_scans
    'save_boss_scan', 'load_boss_scan_file',
    'list_available_boss_scans',
    'save_global_bosses', 'load_global_bosses',
    # icon_scans
    'save_icon_scan', 'load_icon_scan_file',
    'list_available_icon_scans',
    # globals
    'save_global_slots', 'save_global_items',
    'get_existing_categories', 'shift_category_priorities',
    # presets
    'list_slot_presets', 'save_slot_preset', 'load_slot_preset', 'delete_slot_preset',
    'list_item_presets', 'save_item_preset', 'load_item_preset', 'delete_item_preset',
    # sweep
    'sweep_on_start',
]
