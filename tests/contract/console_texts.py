"""Farbnamen und Lageangaben der Konsole (`utils/console.py`), festgehalten.

Geschrieben, BEVOR `_color_name` und `coord_context` (je 12) als Tabellen
neu geschrieben wurden — beide standen in keinem Test. Die Erwartungen sind
die Antworten der alten Fassung für eine Auswahl, die jeden Zweig trifft.
"""
from ._harness import check, section

import autoclicker.utils.console as _CON
import autoclicker.winapi as _WIN

section("Farbnamen: jeder Bereich")
for _rgb, _name in (((10, 10, 10), "Schwarz"), ((80, 80, 90), "Dunkelgrau"),
                    ((150, 150, 160), "Grau"), ((230, 230, 230), "Weiss"),
                    ((200, 20, 20), "Rot"), ((100, 10, 10), "Dunkelrot"),
                    ((200, 10, 40), "Rot"), ((100, 5, 20), "Dunkelrot"),
                    ((139, 69, 19), "Braun"), ((240, 140, 20), "Orange"),
                    ((220, 220, 30), "Gelb"), ((110, 110, 10), "Oliv"),
                    ((30, 200, 40), "Grün"), ((10, 100, 20), "Dunkelgrün"),
                    ((30, 200, 200), "Türkis"), ((20, 40, 220), "Blau"),
                    ((10, 20, 100), "Dunkelblau"), ((150, 60, 220), "Lila"),
                    ((230, 60, 180), "Pink"), ((250, 20, 120), "Pink"),
                    ((100, 10, 50), "Pink")):
    check(f"{_rgb} heisst {_name}", _CON._color_name(*_rgb) == _name)

section("Lageangaben: neun Felder und kein Bildschirm")
_saved = _WIN.get_screen_size
_WIN.get_screen_size = lambda: (1000, 1000)
try:
    for (_x, _y), _where in (((10, 10), "oben links"), ((500, 10), "oben"),
                             ((990, 10), "oben rechts"), ((10, 500), "links"),
                             ((500, 500), "Mitte"), ((990, 500), "rechts"),
                             ((10, 990), "unten links"), ((500, 990), "unten"),
                             ((990, 990), "unten rechts")):
        _text = _CON.coord_context(_x, _y)
        check(f"({_x}, {_y}) liegt {_where}",
              _text.startswith(f"({_x}, {_y}) ") and f"= {_where} (" in _text
              and f"({_x * 100 // 1000}%, {_y * 100 // 1000}%)" in _text)
    _WIN.get_screen_size = lambda: None
    check("ohne Bildschirmgrösse nur die Zahlen", _CON.coord_context(5, 6) == "(5, 6)")
    _WIN.get_screen_size = lambda: (0, 0)
    check("bei Grösse 0 ebenso", _CON.coord_context(5, 6) == "(5, 6)")
finally:
    _WIN.get_screen_size = _saved

# Der zweite Farbnamen-Rechner (nach dominantem Kanal, für Werkzeuge und
# Laufstatus). Dass es zwei mit verschiedenen Antworten gibt, ist eine eigene
# Frage — hier wird nur festgehalten, was dieser heute sagt.
section("Farbnamen (imaging): jeder Zweig")
from autoclicker.imaging import get_color_name as _gcn
for _rgb, _name in (((10, 10, 10), "Schwarz"), ((80, 80, 80), "Dunkelgrau"),
                    ((150, 150, 150), "Grau"), ((230, 230, 230), "Weiss"),
                    ((250, 180, 20), "Orange"), ((150, 110, 20), "Braun"),
                    ((200, 20, 100), "Pink/Magenta"), ((200, 50, 40), "Rot"),
                    ((150, 200, 20), "Gelb/Lime"), ((20, 200, 150), "Türkis/Cyan"),
                    ((50, 200, 60), "Grün"), ((150, 20, 200), "Lila/Violett"),
                    ((20, 150, 200), "Türkis/Cyan"), ((40, 50, 200), "Blau"),
                    ((250, 250, 50), "Gelb"), ((250, 50, 250), "Magenta"),
                    ((50, 250, 250), "Cyan"), ((150, 150, 50), "Gemischt")):
    check(f"{_rgb} heisst {_name}", _gcn(_rgb) == _name)
