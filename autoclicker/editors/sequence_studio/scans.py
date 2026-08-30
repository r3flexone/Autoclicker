"""
Kompatible Fassade für den Scan-Teil des Sequenz-Studios.

Die Implementierung ist nach Verantwortlichkeiten getrennt; `ScanTeil` und die
bisher öffentlich importierten Konstanten bleiben an derselben Stelle verfügbar.
"""

from .scan_capture import ScanCaptureMixin
from .scan_contract import (
    ART_BIBLIOTHEK,
    ART_BOSS,
    ART_BOSS_SCAN,
    ART_ICON_SCAN,
    ART_ITEM,
    ART_SCAN,
    ART_SLOT,
    ARTEN,
    MIN_REGION,
    MIN_SLOT,
    MODI,
    MODI_ALLE,
    MODI_ERKENNUNG,
    MODUS_AKTION,
    MODUS_BEREICH,
    MODUS_FINDEN,
    MODUS_KLICK,
    MODUS_MESSEN,
    MODUS_REGION,
    MODUS_SLOT,
    MODUS_WAHL,
    TREFFER_MIN,
    UNDO_TIEFE,
)
from .scan_detect import ScanDetectMixin
from .scan_interaction import ScanInteractionMixin
from .scan_learning import ScanLearningMixin, _NurConfig
from .scan_library import ScanLibraryMixin
from .scan_state import ScanStateMixin

__all__ = [
    "ART_BIBLIOTHEK",
    "ART_BOSS",
    "ART_BOSS_SCAN",
    "ART_ICON_SCAN",
    "ART_ITEM",
    "ART_SCAN",
    "ART_SLOT",
    "ARTEN",
    "MIN_REGION",
    "MIN_SLOT",
    "MODI",
    "MODI_ALLE",
    "MODI_ERKENNUNG",
    "MODUS_AKTION",
    "MODUS_BEREICH",
    "MODUS_FINDEN",
    "MODUS_KLICK",
    "MODUS_MESSEN",
    "MODUS_REGION",
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
