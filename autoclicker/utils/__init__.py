"""
Utils-Subpaket: Konsole, I/O, Parsing.

Modul-Aufteilung:
    console.py   ANSI-Farben, Status-Tags, Konsolen-Detection, Layout-Helper
    io.py        safe_input, interactive_select, read_key, read_command
    parsing.py   parse_time_input, parse_non_negative_*, format_duration, sanitize_filename, clean_item_name, compact_json

Hier stehen die Namen, die andere Module als `from .utils import ...` holen.
Was nur ein Modul des Pakets braucht (etwa `flush_input_buffer` und `read_key`
aus `io.py`), wird dort geholt — `from .utils.io import ...`.
"""

from .console import (
    col, ok, err, warn, info, hint, dbg, describe_color,
    save_tag, load_tag, delete_tag,
    header, cmd_hint, breadcrumb,
    suggest_command, coord_context,
    clear_line, status_line, init_logging,
)
from .io import (
    is_cancel, cancel_hint,
    safe_input, confirm,
    read_command, interactive_select,
)
from .parsing import (
    parse_time_input, parse_non_negative_float, parse_non_negative_range,
    format_duration, sanitize_filename, clean_item_name, without_counter,
    unique_name, next_free_name,
    compact_json, atomic_write,
)

__all__ = [
    # console
    'col', 'ok', 'err', 'warn', 'info', 'hint', 'dbg', 'describe_color',
    'save_tag', 'load_tag', 'delete_tag',
    'header', 'cmd_hint', 'breadcrumb',
    'suggest_command', 'coord_context',
    'clear_line', 'status_line', 'init_logging',
    # io
    'is_cancel', 'cancel_hint',
    'safe_input', 'confirm',
    'read_command', 'interactive_select',
    # parsing
    'parse_time_input', 'parse_non_negative_float', 'parse_non_negative_range',
    'format_duration', 'sanitize_filename', 'clean_item_name', 'without_counter', 'unique_name', 'next_free_name',
    'compact_json', 'atomic_write',
]
