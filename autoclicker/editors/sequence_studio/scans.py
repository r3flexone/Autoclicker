"""
Der Scan-Teil der Studio-Brücke: `ScanPart` fügt die Mixins zusammen.

Die Konstanten des Scan-Protokolls stehen in `scan_contract.py`.
"""

from .scan_capture import ScanCaptureMixin
from .scan_detect import ScanDetectMixin
from .scan_interaction import ScanInteractionMixin
from .scan_learning import ScanLearningMixin
from .scan_library import ScanLibraryMixin
from .scan_state import ScanStateMixin


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
