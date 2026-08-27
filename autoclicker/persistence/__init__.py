"""
Persistenz-Subpaket: Speichern und Laden aller JSON-Dateien.

Modul-Aufteilung:
    paths.py          Verzeichnis-Konstanten + init_directories
    serialization.py  Dataclass ↔ Dict (intern + import_export.py)
    sequences.py      Sequence-Dateien + Punkte
    item_scans.py     ItemScanConfig + update_item_in_scans
    boss_scans.py     BossScanConfig
    globals.py        global_slots, global_items, Kategorien
    presets.py        Slot- und Item-Presets
    migration.py      Schema-Versionierung + Normalisierer (die EINE Schleuse fuer
                      Altformate - Loader lesen nur das aktuelle Format)
    sweep.py          hebt beim Programmstart ALLE Dateien in einem Durchgang
                      (gleiche Logik nutzt tools/migrate.py)

Re-exportiert die komplette bisherige API damit `from .persistence import ...`
in main.py, handlers.py, import_export.py, imaging.py, runtime/, editors/
weiterhin unverändert funktioniert.
"""

from .boss_scans import (
    ensure_boss_scans_dir, save_boss_scan, load_boss_scan_file,
    list_available_boss_scans, load_all_boss_scans,
    save_global_bosses, load_global_bosses,
)
from .migration import (
    ALL_KINDS, KIND_BOSS_SCAN, KIND_GLOBAL_BOSSES, KIND_ICON_SCAN, KIND_ITEMS,
    KIND_ITEM_SCAN, KIND_POINTS, KIND_SEQUENCE, KIND_SLOTS, SCHEMA_VERSION,
    file_version, migrate, needs_migration, stamp,
)
from .sweep import sweep, sweep_beim_start, SweepErgebnis
from .icon_scans import (
    ensure_icon_scans_dir, save_icon_scan, load_icon_scan_file,
    list_available_icon_scans, load_all_icon_scans,
)
from .globals import (
    save_global_slots, load_global_slots,
    save_global_items, load_global_items,
    get_existing_categories, shift_category_priorities,
)
from .item_scans import (
    ensure_item_scans_dir, save_item_scan, load_item_scan_file,
    list_available_item_scans, load_all_item_scans,
    update_item_in_scans, resolve_scan_references, resolve_klick_referenzen,
    bind_item_scan_context, flush_item_scan_context,
)
from .paths import (
    BOSS_SCANS_DIR, ICON_SCANS_DIR, ITEM_SCANS_DIR, SLOTS_DIR, ITEMS_DIR,
    SCREENSHOTS_DIR, SEQUENCE_SCREENSHOTS_DIR, TEMPLATES_DIR,
    SLOTS_FILE, ITEMS_FILE,
    SLOT_PRESETS_DIR, ITEM_PRESETS_DIR,
    init_directories,
)
from .presets import (
    list_slot_presets, save_slot_preset, load_slot_preset, delete_slot_preset,
    list_item_presets, save_item_preset, load_item_preset, delete_item_preset,
)
from .sequences import (
    ensure_sequences_dir, save_sequence_file, load_sequence_file,
    list_available_sequences, save_data,
    load_points, save_points, get_next_point_id, get_point_by_id, print_points,
    sequence_dir, sequence_file, sequence_templates_dir,
    active_sequence_dir, active_templates_dir,
    punkt_fuer_stelle, punkte_nachladen, aufloesen,
    resolve_point_references,
)
from .serialization import (
    _item_to_dict, _slot_to_dict, _item_from_dict, _slot_from_dict,
    _step_to_dict, _sequence_to_dict,
    _boss_profile_to_dict, _boss_profile_from_dict,
    _point_to_dict, _item_scan_from_dict, _item_scan_to_dict,
    _boss_scan_to_dict, _icon_scan_to_dict,
)

__all__ = [
    # paths
    'BOSS_SCANS_DIR', 'ICON_SCANS_DIR', 'ITEM_SCANS_DIR', 'SLOTS_DIR', 'ITEMS_DIR',
    'SCREENSHOTS_DIR', 'SEQUENCE_SCREENSHOTS_DIR', 'TEMPLATES_DIR',
    'SLOTS_FILE', 'ITEMS_FILE', 'SLOT_PRESETS_DIR', 'ITEM_PRESETS_DIR',
    'init_directories',
    # serialization
    '_item_to_dict', '_slot_to_dict', '_item_from_dict', '_slot_from_dict',
    '_step_to_dict', '_sequence_to_dict',
    '_boss_profile_to_dict', '_boss_profile_from_dict',
    '_point_to_dict', '_item_scan_from_dict', '_item_scan_to_dict',
    '_boss_scan_to_dict', '_icon_scan_to_dict',
    # sequences
    'ensure_sequences_dir', 'save_sequence_file', 'load_sequence_file',
    'list_available_sequences', 'save_data',
    'load_points', 'save_points', 'get_next_point_id', 'get_point_by_id', 'print_points',
    'sequence_dir', 'sequence_file', 'sequence_templates_dir',
    'active_sequence_dir', 'active_templates_dir',
    'punkt_fuer_stelle', 'punkte_nachladen', 'aufloesen',
    'resolve_point_references',
    # item_scans
    'ensure_item_scans_dir', 'save_item_scan', 'load_item_scan_file',
    'list_available_item_scans', 'load_all_item_scans', 'update_item_in_scans',
    'resolve_scan_references', 'resolve_klick_referenzen',
    'bind_item_scan_context', 'flush_item_scan_context',
    # boss_scans
    'ensure_boss_scans_dir', 'save_boss_scan', 'load_boss_scan_file',
    'list_available_boss_scans', 'load_all_boss_scans',
    'save_global_bosses', 'load_global_bosses',
    # icon_scans
    'ensure_icon_scans_dir', 'save_icon_scan', 'load_icon_scan_file',
    'list_available_icon_scans', 'load_all_icon_scans',
    # globals
    'save_global_slots', 'load_global_slots',
    'save_global_items', 'load_global_items',
    'get_existing_categories', 'shift_category_priorities',
    # presets
    'list_slot_presets', 'save_slot_preset', 'load_slot_preset', 'delete_slot_preset',
    'list_item_presets', 'save_item_preset', 'load_item_preset', 'delete_item_preset',
    # migration
    'ALL_KINDS', 'KIND_BOSS_SCAN', 'KIND_GLOBAL_BOSSES', 'KIND_ICON_SCAN',
    'KIND_ITEMS', 'KIND_ITEM_SCAN', 'KIND_POINTS', 'KIND_SEQUENCE', 'KIND_SLOTS',
    'SCHEMA_VERSION',
    'file_version', 'migrate', 'needs_migration', 'stamp',
    # sweep
    'sweep', 'sweep_beim_start', 'SweepErgebnis',
]
