"""Ein gestelltes Spielbild — statt eines echten Screenshots.

Die Rauchtests laufen ohne Bildschirm; `take_screenshot` wird deshalb auf ein
gemaltes Bild umgebogen. Das ist kein Nachbau der Bilderkennung: gerechnet wird
weiter mit den echten Funktionen, sie bekommen nur ihre Pixel von hier.
"""

from __future__ import annotations


def stelle_bildschirm(bild) -> None:
    """Biegt Aufnahme und Ursprung auf ein festes Bild um."""
    import autoclicker.imaging as img
    import autoclicker.winapi as win
    img.take_screenshot = lambda region=None: (
        bild.copy() if not region else bild.crop(tuple(region)))
    win.get_virtual_origin = lambda: (0, 0)


def inventar(spalten: int = 3, zeilen: int = 2):
    """Ein Raster aus verschiedenfarbigen Items. Gibt `(bild, slot_ecken)`."""
    from PIL import Image
    bild = Image.new("RGB", (800, 600), (18, 21, 27))
    farben = [(200, 60, 60), (60, 200, 90), (70, 110, 230),
              (230, 190, 60), (180, 80, 210), (60, 200, 210)]
    ecken = []
    for i in range(spalten * zeilen):
        sx, sy = 60 + (i % spalten) * 90, 80 + (i // spalten) * 90
        for x in range(sx, sx + 62):
            for y in range(sy, sy + 60):
                bild.putpixel((x, y), (48, 54, 68))     # Slot-Hintergrund
        for x in range(sx + 14, sx + 48):
            for y in range(sy + 12, sy + 48):
                bild.putpixel((x, y), farben[i % len(farben)])
        ecken.append((sx, sy))
    return bild, ecken


def flaeche_mit_marke():
    """Ein dunkles Bild mit einem roten Fleck — reicht Boss- und Icon-Scans."""
    from PIL import Image
    bild = Image.new("RGB", (800, 600), (24, 28, 36))
    for x in range(300, 340):
        for y in range(200, 240):
            bild.putpixel((x, y), (220, 50, 60))
    return bild, (300, 200, 340, 240)
