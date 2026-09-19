"""
Kompatible Fassade für den Scan-Teil des Sequenz-Studios.

Die Implementierung ist nach Verantwortlichkeiten getrennt; `ScanPart` und die
bisher öffentlich importierten Konstanten bleiben an derselben Stelle verfügbar.
"""

from .scan_capture import ScanCaptureMixin
from .scan_contract import (
    KIND_LIBRARY,
    KIND_BOSS,
    KIND_BOSS_SCAN,
    KIND_ICON_SCAN,
    KIND_ITEM,
    KIND_SCAN,
    KIND_SLOT,
    SCAN_KINDS,
    MIN_REGION,
    MIN_SLOT,
    MODES,
    MODES_ALL,
    MODES_DETECTION,
    MODE_ACTION,
    MODE_AREA,
    MODE_FIND,
    MODE_CLICK,
    MODE_MEASURE,
    MODE_REGION,
    MODE_SLOT,
    MODE_CHOICE,
    HIT_MIN,
    UNDO_DEPTH,
)
from .scan_detect import ScanDetectMixin
from .scan_interaction import ScanInteractionMixin
from .scan_learning import ScanLearningMixin, _ConfigOnly
from .scan_library import ScanLibraryMixin
from .scan_state import ScanStateMixin

__all__ = [
    "KIND_LIBRARY",
    "KIND_BOSS",
    "KIND_BOSS_SCAN",
    "KIND_ICON_SCAN",
    "KIND_ITEM",
    "KIND_SCAN",
    "KIND_SLOT",
    "SCAN_KINDS",
    "MIN_REGION",
    "MIN_SLOT",
    "MODES",
    "MODES_ALL",
    "MODES_DETECTION",
    "MODE_ACTION",
    "MODE_AREA",
    "MODE_FIND",
    "MODE_CLICK",
    "MODE_MEASURE",
    "MODE_REGION",
    "MODE_SLOT",
    "MODE_CHOICE",
    "ScanPart",
    "HIT_MIN",
    "UNDO_DEPTH",
    "_ConfigOnly",
]


class ScanPart(
    ScanLibraryMixin,
    ScanLearningMixin,
    ScanDetectMixin,
    ScanInteractionMixin,
    ScanStateMixin,
    ScanCaptureMixin,
):
    """Alle drei Scan-Arten als gemeinsamer Teil der Studio-Brücke.

    Item-, Boss- und Icon-Scans teilen sich die Aufnahme, den Zoom, den
    Rückgängig-Stapel und den Speichern-Knopf — sie unterscheiden sich in dem,
    was auf dem Bild markiert wird, nicht im Werkzeugkasten darum herum.
    """
