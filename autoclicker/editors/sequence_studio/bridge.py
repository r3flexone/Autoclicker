"""
Kompatible Fassade der Web-Brücke des Sequenz-Studios.

Die öffentliche Klasse bleibt stabil. Darstellung, Dienste und Editor-Kommandos
sind intern nach Verantwortlichkeiten getrennt.
"""

from pathlib import Path
from typing import Optional

from ...models import Sequence
from .bridge_contract import (
    ELSE_ACTIONS,
    SCAN_FIELD,
    SCAN_MODES,
    TRIGGER_PRESENT,
    TRIGGER_NONE,
    TRIGGER_GONE,
    TYPE_ORDER,
    _ELSE_SCANS,
    _FIELDS,
    _blocks,
    _same_value,
    _hex,
    _mtime,
    _rgb,
    _position,
    _wait_text,
    else_applies,
    scan_warnings,
    trigger_name,
)
from .bridge_bericht import BridgeReportMixin
from .bridge_editing import BridgeEditingMixin
from .bridge_services import BridgeServicesMixin
from .bridge_teilen import BridgeShareMixin
from .bridge_view import BridgeViewMixin
from .bridge_werkzeuge import BridgeToolsMixin
from .model import Lane, PalettePoint, SequenceBoard, palette_from_sequence, sequence_to_board
from .scans import ScanTeil

__all__ = [
    "ELSE_ACTIONS",
    "SCAN_FIELD",
    "SCAN_MODES",
    "StudioBridge",
    "TRIGGER_PRESENT",
    "TRIGGER_NONE",
    "TRIGGER_GONE",
    "TYPE_ORDER",
    "_ELSE_SCANS",
    "_FIELDS",
    "_blocks",
    "_same_value",
    "_hex",
    "_mtime",
    "_rgb",
    "_position",
    "_wait_text",
    "else_applies",
    "scan_warnings",
    "trigger_name",
]


class StudioBridge(
    BridgeReportMixin,
    BridgeEditingMixin,
    BridgeServicesMixin,
    BridgeShareMixin,
    BridgeViewMixin,
    BridgeToolsMixin,
    ScanTeil,
):
    """Gemeinsame pywebview-API für Sequenz-Editor und Scan-Werkzeuge."""

    def __init__(self, seq: Sequence, filepath, sequences_dir: str):
        self.board: SequenceBoard = sequence_to_board(seq)
        self.filepath = Path(filepath)
        self.sequences_dir = sequences_dir
        self.points: list[PalettePoint] = palette_from_sequence(seq)
        # Was ohne ELSE passiert, steht in der config.json — gemerkt am
        # Zeitstempel, damit nicht jede Momentaufnahme die Datei liest.
        self._cfg_state: float = -1.0
        self._cfg_info: dict = {}
        # Stand der Dateien beim Laden. Der Hauptprozess schreibt dieselben
        # Dateien (Aufnahme legt Punkte an, `save_data` schreibt die Sequenz) —
        # ohne diesen Vergleich überschreibt das Studio das kommentarlos.
        self._state_file: Optional[float] = _mtime(self.filepath)
        # Die Auswahl lebt in GENAU EINER Phase. Eine Auswahl quer über INIT und
        # END hätte bei "eine Position hoch" keine Bedeutung, und die
        # Sammelaktionen wären nicht mehr eindeutig.
        self.sel_lane: Optional[Lane] = None
        self.sel_rows: set[int] = set()
        # Fester Ausgangspunkt für Umschalt+Klick. Ohne eigenen Anker wurde der
        # Bereich aus min/max der ganzen Auswahl berechnet und liess sich mit
        # demselben Umschalt-Klick nicht wieder abwählen.
        self.sel_anchor: Optional[int] = None
        self._dirty = False
        # Wurde in dieser Sitzung mindestens einmal geschrieben? Nur dafür da,
        # dass die Schlussmeldung ans Neuladen im Hauptprozess erinnern kann.
        self._saved = False
        self._status = ("", "info")
        self._ask: Optional[dict] = None
        # Welcher Reiter beim Start offen ist. Reiner Oberflächenzustand, aber
        # er kommt von aussen: CTRL+ALT+V startet denselben Prozess wie
        # CTRL+ALT+B, nur mit "scans".
        self.start_view: str = "editor"
        self._scan_init()
        self._report_init()
        self._share_init()
        self._tools_init()
