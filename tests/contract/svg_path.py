"""Der SVG-Pfadleser des Programm-Symbols, vor dem Zerlegen festgehalten.

Die Logo-Tests in `test_logic.py` prüfen das Ergebnis am echten Logo — welche
Regeln der Leser dabei einhält (implizite Linie nach M, Z springt zum Anfang,
zu kurze Polygone fallen weg, jeder Fehler hat seinen Text), sieht man dort nicht.
"""
from ._harness import check, section

import autoclicker.symbol as _SYM


def _polygons(data):
    """Die Polygone — oder der Fehlertext, damit ein Fehler rot wird statt abzustürzen."""
    try:
        return _SYM._path_polygons(data)
    except ValueError as e:
        return str(e)


def _error(data):
    try:
        _SYM._path_polygons(data)
    except ValueError as e:
        return str(e)
    return None


# =============================================================================
section("Symbol: SVG-Pfade lesen")
# =============================================================================
check("ein Dreieck mit M, L und Z",
      _polygons("M0 0 L10 0 L10 10 Z") == (((0.0, 0.0), (10.0, 0.0), (10.0, 10.0)),))
check("Paare nach M sind Linien",
      _polygons("M0 0 10 0 10 10 Z") == (((0.0, 0.0), (10.0, 0.0), (10.0, 10.0)),))
check("ein neues M schliesst das alte Polygon, das Ende das letzte",
      len(_polygons("M0 0 L10 0 L10 10 M20 20 L30 20 L30 30")) == 2)
check("ein Polygon mit weniger als drei Punkten fällt weg",
      len(_polygons("M0 0 L1 0 Z M0 0 L10 0 L10 10 Z")) == 1)

_curve = _polygons("M0 0 C0 10 10 10 10 0 Z")[0]
check("eine Kurve wird in CURVE_STEPS Stücke zerlegt",
      len(_curve) == 1 + _SYM.CURVE_STEPS and _curve[-1] == (10.0, 0.0))
check("und liegt auf der Bézier-Kurve (Mitte bei t = 0,5)",
      _curve[_SYM.CURVE_STEPS // 2] == (5.0, 7.5))
# Nach Z geht es am Anfang des Teilpfads weiter, nicht am letzten Punkt.
_after_z = _polygons("M0 0 L10 0 L10 10 Z C0 0 0 0 0 0 Z")
check("Z springt zurück an den Anfang des Teilpfads",
      len(_after_z) == 2 and set(_after_z[1]) == {(0.0, 0.0)})

# =============================================================================
section("Symbol: was der Leser ablehnt")
# =============================================================================
check("unbekannter Befehl", _error("M0 0 A1 1 0 0 0 5 5 Z")
      == "SVG-Befehl 'A' wird im Studio-Logo nicht unterstützt")
check("Koordinate ohne Befehl", _error("5 5") == "Koordinate ohne SVG-Befehl im Studio-Logo")
check("auch nach Z braucht es einen neuen Befehl",
      _error("M0 0 L10 0 L10 10 Z 5 5") == "Koordinate ohne SVG-Befehl im Studio-Logo")
check("abgeschnittener Pfad", _error("M0") == "Unvollständiger SVG-Pfad im Studio-Logo")
check("ein Befehl, wo eine Zahl stehen muss",
      _error("M0 L1 1") == "Unvollständiger SVG-Pfad im Studio-Logo")
check("leerer Pfad", _error("") == "Das Studio-Logo enthält einen leeren SVG-Pfad")
check("nur zu kurze Polygone zählen als leer",
      _error("M0 0 L1 1 Z") == "Das Studio-Logo enthält einen leeren SVG-Pfad")
