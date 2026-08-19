"""
Kompatible Fassade für den Scan-Teil des Sequenz-Studios.

Die Implementierung ist nach Verantwortlichkeiten getrennt; `ScanTeil` und die
bisher öffentlich importierten Konstanten bleiben an derselben Stelle verfügbar.
"""

from .scan_capture import ScanCaptureMixin
from .scan_contract import (
    ART_ITEM,
    ART_SCAN,
    ART_SLOT,
    MIN_SLOT,
    MODI,
    MODUS_BEREICH,
    MODUS_FINDEN,
    MODUS_KLICK,
    MODUS_MESSEN,
    MODUS_SLOT,
    MODUS_WAHL,
    TREFFER_MIN,
    UNDO_TIEFE,
)
from .scan_interaction import ScanInteractionMixin
from .scan_learning import ScanLearningMixin, _NurConfig
from .scan_library import ScanLibraryMixin
from .scan_state import ScanStateMixin

__all__ = [
    "ART_ITEM",
    "ART_SCAN",
    "ART_SLOT",
    "MIN_SLOT",
    "MODI",
    "MODUS_BEREICH",
    "MODUS_FINDEN",
    "MODUS_KLICK",
    "MODUS_MESSEN",
    "MODUS_SLOT",
    "MODUS_WAHL",
    "ScanTeil",
    "TREFFER_MIN",
    "UNDO_TIEFE",
    "_NurConfig",
]


class ScanTeil(
    ScanLibraryMixin,
    ScanLearningMixin,
    ScanInteractionMixin,
    ScanStateMixin,
    ScanCaptureMixin,
):
    """Slots, Items und Item-Scans als gemeinsamer Teil der Studio-Brücke."""
