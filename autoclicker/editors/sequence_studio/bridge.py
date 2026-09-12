"""
Kompatible Fassade der Web-Brücke des Sequenz-Studios.

Die öffentliche Klasse bleibt stabil. Darstellung, Dienste und Editor-Kommandos
sind intern nach Verantwortlichkeiten getrennt.
"""

from pathlib import Path
from typing import Optional

from ...models import Sequence
from .bridge_contract import (
    ELSE_AKTIONEN,
    SCAN_FELD,
    SCAN_MODI,
    TRIGGER_DA,
    TRIGGER_KEIN,
    TRIGGER_WEG,
    TYP_REIHENFOLGE,
    _ELSE_SCANS,
    _FELDER,
    _bloecke,
    _gleicher_wert,
    _hex,
    _mtime,
    _rgb,
    _stelle,
    _wartetext,
    else_greift,
    scan_warnungen,
    trigger_name,
)
from .bridge_bericht import BridgeBerichtMixin
from .bridge_editing import BridgeEditingMixin
from .bridge_services import BridgeServicesMixin
from .bridge_teilen import BridgeTeilenMixin
from .bridge_view import BridgeViewMixin
from .bridge_werkzeuge import BridgeWerkzeugeMixin
from .model import Lane, PalettePoint, SequenceBoard, palette_from_sequence, sequence_to_board
from .scans import ScanTeil

__all__ = [
    "ELSE_AKTIONEN",
    "SCAN_FELD",
    "SCAN_MODI",
    "StudioBridge",
    "TRIGGER_DA",
    "TRIGGER_KEIN",
    "TRIGGER_WEG",
    "TYP_REIHENFOLGE",
    "_ELSE_SCANS",
    "_FELDER",
    "_bloecke",
    "_gleicher_wert",
    "_hex",
    "_mtime",
    "_rgb",
    "_stelle",
    "_wartetext",
    "else_greift",
    "scan_warnungen",
    "trigger_name",
]


class StudioBridge(
    BridgeBerichtMixin,
    BridgeEditingMixin,
    BridgeServicesMixin,
    BridgeTeilenMixin,
    BridgeViewMixin,
    BridgeWerkzeugeMixin,
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
        self._cfg_stand: float = -1.0
        self._cfg_info: dict = {}
        # Stand der Dateien beim Laden. Der Hauptprozess schreibt dieselben
        # Dateien (Aufnahme legt Punkte an, `save_data` schreibt die Sequenz) —
        # ohne diesen Vergleich überschreibt das Studio das kommentarlos.
        self._stand_datei: Optional[float] = _mtime(self.filepath)
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
        self._gespeichert = False
        self._status = ("", "info")
        self._frage: Optional[dict] = None
        # Welcher Reiter beim Start offen ist. Reiner Oberflächenzustand, aber
        # er kommt von aussen: CTRL+ALT+V startet denselben Prozess wie
        # CTRL+ALT+B, nur mit "scans".
        self.start_ansicht: str = "editor"
        self._scan_init()
        self._bericht_init()
        self._teilen_init()
        self._werkzeuge_init()
