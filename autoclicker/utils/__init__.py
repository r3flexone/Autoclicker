"""
Utils-Subpaket: Konsole, I/O, Parsing.

Modul-Aufteilung:
    console.py   ANSI-Farben, Status-Tags, Konsolen-Detection, Layout-Helper
    io.py        safe_input, interactive_select, read_key, read_command, wait_while_paused
    parsing.py   parse_time_input, parse_non_negative_*, format_duration, sanitize_filename, compact_json

Re-exportiert die komplette bisherige API damit `from .utils import ...`
und `from autoclicker.utils import ...` aus anderen Modulen unverändert
weiterfunktionieren.
"""

from .console import (
    col, ok, err, warn, info, hint, dbg, describe_color,
    save_tag, load_tag, delete_tag,
    header, cmd_hint, breadcrumb,
    suggest_command, coord_context,
    clear_line, init_logging,
)
from .io import (
    is_cancel, cancel_hint,
    flush_input_buffer, safe_input, confirm,
    read_key, read_command, interactive_select,
    wait_while_paused,
)
from .parsing import (
    parse_time_input, parse_non_negative_float, parse_non_negative_range,
    format_duration, sanitize_filename, eindeutiger_name, compact_json, atomic_write,
)

__all__ = [
    # console
    'col', 'ok', 'err', 'warn', 'info', 'hint', 'dbg', 'describe_color',
    'save_tag', 'load_tag', 'delete_tag',
    'header', 'cmd_hint', 'breadcrumb',
    'suggest_command', 'coord_context',
    'clear_line', 'init_logging',
    # io
    'is_cancel', 'cancel_hint',
    'flush_input_buffer', 'safe_input', 'confirm',
    'read_key', 'read_command', 'interactive_select',
    'wait_while_paused',
    # parsing
    'parse_time_input', 'parse_non_negative_float', 'parse_non_negative_range',
    'format_duration', 'sanitize_filename', 'eindeutiger_name',
    'compact_json', 'atomic_write',
]
