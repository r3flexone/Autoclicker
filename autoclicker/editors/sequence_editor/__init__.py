"""
Sequenz-Editor-Subpaket.

Modul-Aufteilung:
    editor.py    run_sequence_editor + edit_sequence (Top-Level)
    loader.py    run_sequence_loader + Coordinate-Remap
    loops.py     edit_loop_phases
    steps.py     edit_phase (Hauptarbeit) + Phase-Help
    helpers.py   apply_else_to_step, capture_pixel_color, parse_else_condition,
                  parse_uhrzeit

Externe Konsumenten: editors/__init__.py braucht run_sequence_editor und
run_sequence_loader. Beides hier re-exportiert.
"""

from .editor import run_sequence_editor
from .loader import run_sequence_loader

__all__ = ['run_sequence_editor', 'run_sequence_loader']
