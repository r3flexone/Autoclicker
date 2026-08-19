"""Stabiles Protokoll zwischen Scan-Logik, Brücke und Weboberfläche."""

MODUS_WAHL = "wahl"
MODUS_SLOT = "slot"
MODUS_MESSEN = "messen"
MODUS_KLICK = "klick"
MODUS_BEREICH = "bereich"
MODUS_FINDEN = "finden"
MODI = (
    MODUS_WAHL,
    MODUS_FINDEN,
    MODUS_SLOT,
    MODUS_MESSEN,
    MODUS_KLICK,
    MODUS_BEREICH,
)

ART_SLOT = "slot"
ART_ITEM = "item"
ART_SCAN = "scan"

MIN_SLOT = 8
TREFFER_MIN = 14
UNDO_TIEFE = 30
