"""
Visuelles Scan-Studio (Dear PyGui) — Slots, Items und Scan-Configs auf einem
eingefrorenen Screenshot zusammenbauen.

Läuft als separater Subprocess (siehe autoclicker/scan_studio.py), liest/schreibt
dieselben JSON-Dateien wie die Konsolen-Editoren (slots/slots.json,
items/items.json, item_scans/<name>.json). Beide Wege bleiben gleichwertig
nutzbar — die GUI ersetzt nichts, sie ergänzt.

Modul-Aufteilung:
    texture.py     PIL-Image → Dear-PyGui-Textur + Koordinaten-Mapping
                   (Anzeige-Pixel ↔ Bildschirm-Pixel). Die kritische Komponente.
    model.py       GUI-freies Laden/Speichern von Slots (und später Items/Scans).
    canvas_dpg.py  Screenshot-Canvas: Rechtecke zeichnen → Slots, Eigenschaften.
"""
