"""Das Programm-Symbol: EINE Geometrie, aus der jede Grösse entsteht.

Es gibt keine `.ico` und keine `.png` im Repo, aus der das Fenstersymbol käme —
sondern eine Liste von Formen, aus der sich alles ableitet: das Symbol für
Titelleiste und Taskleiste (`winapi.setze_fenster_symbol`), die Bilddateien für
eine Verknüpfung (`tools/symbol.py`) und, von Hand nachgezogen, das SVG im Kopf
der Oberfläche. Eine Binärdatei im Repo wäre eine zweite Wahrheit, die still
veraltet — dasselbe Argument wie überall sonst im Projekt.

Aus einer Geometrie lässt sich **jede** Grösse sauber ableiten, und das braucht
es: die Titelleiste will 16 px, ALT+TAB und Taskleiste 32, eine Verknüpfung 256.
Vorher stand hier ein 16×16-Raster aus Nullen und Einsen, und es hatte alle
Fehler eines handgesetzten Rasters — scharfe Ecken, Treppen, Motiv bis an den
Rand.

**Zwei Fassungen, nicht eine skalierte.** Bei 16 px ist ein Umriss ein grauer
Fleck: die Fahne der grossen Fassung hat 0,6 Einheiten Strichstärke, das sind
bei 16 px vier Zehntel Pixel. Die kleine Fassung füllt die Fahne deshalb, lässt
die Punktkette weg (was im Kopf der Oberfläche bei 20 px trägt, ist hier
Rauschen) und macht die Striche breiter. Was bleibt, ist dasselbe Motiv:
Zeilen, eine Fahne davor.

Dieses Modul kennt **kein** Windows und **kein** Pillow — es rechnet nur, wie
viel Farbe auf einen Pixel fällt. Wer daraus Bytes macht, macht das bei sich:
`winapi` als ICO-Bits, `tools/symbol.py` als PNG.
"""

import math

# Die Farben des Studios. Amber ist der Grund, Dunkel das Motiv — dieselbe
# Aufteilung wie in der Oberfläche, wo Amber „gewählt/läuft" heisst.
AMBER = (0xF5, 0x9E, 0x0B)
DUNKEL = (0x0C, 0x0F, 0x14)

RASTER = 24.0        # Kantenlänge der Motivbeschreibung, wie das SVG-viewBox
RUNDUNG = 0.22       # Eckenradius des Grundes als Anteil der Kante (wie `.marke`)
PROBEN = 4           # Abtastungen je Pixel und Achse — das ist die Kantenglättung

# Bis zu dieser Kantenlänge wird die vereinfachte Fassung gezeichnet. 32 ist
# nicht geraten, sondern gemessen: bei 32 px ist die Punktkette der grossen
# Fassung körnig und der Fahnen-Umriss einen halben Pixel breit. Titelleiste
# (16) und ALT+TAB/Taskleiste (32) bekommen deshalb beide die kleine; die
# grosse fängt bei der Verknüpfungsgrösse an, wo sie auch trägt.
KLEIN_BIS = 32

# --------------------------------------------------------------------- Formen
#
# Vier Grundformen, alle im 24er-Raster:
#   ("rr",     x, y, b, h, r)          gefülltes Rechteck mit runden Ecken
#   ("kreis",  x, y, r)                gefüllter Kreis
#   ("strich", x1, y1, x2, y2, b)      Strecke mit runden Enden
#   ("zug",    ((x, y), …), b, zu)     Linienzug, rund verbunden
#
# Mehr braucht das Motiv nicht, und weniger ginge nicht: ein Umriss ist ein Zug,
# eine Fahnenstange ein Strich, eine Zeile ein Rechteck.

# Die grosse Fassung — das Motiv, wie es auch im Kopf der Oberfläche steht.
MOTIV = (
    # Drei Zeilen: Marke plus Balken. Die mittlere ist kürzer, sonst sähe der
    # Block aus wie ein Rechteck statt wie eine Liste.
    ("rr", 3.2, 7.9, 2.5, 2.5, 0.6),
    ("rr", 6.6, 7.9, 11.4, 2.5, 0.6),
    ("rr", 3.2, 11.4, 2.5, 2.5, 0.6),
    ("rr", 6.6, 11.4, 9.3, 2.5, 0.6),
    ("rr", 3.2, 14.9, 2.5, 2.5, 0.6),
    ("rr", 6.6, 14.9, 11.4, 2.5, 0.6),
    # Die Fahne: Stange mit Fuss, Tuch als Umriss. Sie steht VOR den Zeilen und
    # kreuzt sie — beide sind dunkel, also verschwindet die Stange in einer
    # Zeile und taucht in der Lücke wieder auf. Genau das macht sie zur Marke
    # in einem Ablauf statt zu einem Strich daneben.
    ("strich", 9.6, 2.6, 9.6, 19.4, 0.62),
    ("kreis", 9.6, 20.1, 0.85),
    ("zug", ((7.9, 2.6), (12.2, 5.2), (7.9, 7.5)), 0.62, True),
    # Die Punktkette rechts: der Ablauf geht weiter, als das Bild zeigt.
    ("kreis", 19.7, 6.5, 0.62),
    ("kreis", 19.7, 8.7, 0.38),
    ("kreis", 19.7, 10.4, 0.38),
    ("kreis", 19.7, 12.1, 0.38),
    ("kreis", 19.7, 13.8, 0.38),
    ("kreis", 19.7, 15.5, 0.38),
    ("kreis", 19.7, 17.2, 0.38),
    ("kreis", 19.7, 19.4, 0.62),
)

# Die kleine Fassung (16 px): weniger Teile, dickere Striche, gefüllte Fahne.
MOTIV_KLEIN = (
    ("rr", 3.4, 7.6, 2.8, 2.8, 0.7),
    ("rr", 7.4, 7.6, 12.6, 2.8, 0.7),
    ("rr", 3.4, 12.0, 2.8, 2.8, 0.7),
    ("rr", 7.4, 12.0, 9.6, 2.8, 0.7),
    ("rr", 3.4, 16.4, 2.8, 2.8, 0.7),
    ("rr", 7.4, 16.4, 12.6, 2.8, 0.7),
    ("strich", 9.2, 2.6, 9.2, 20.4, 1.3),
    ("kreis", 9.2, 20.8, 1.7),
    ("zug", ((9.2, 2.6), (15.2, 5.6), (9.2, 8.6)), 0.0, True),
)


def motiv_fuer(kante: int) -> tuple:
    """Welche Fassung bei dieser Kantenlänge gezeichnet wird."""
    return MOTIV_KLEIN if kante <= KLEIN_BIS else MOTIV


# ------------------------------------------------------------------- Rechnung


def _im_rr(x: float, y: float, form: tuple) -> bool:
    _, rx, ry, b, h, r = form
    r = min(r, b / 2, h / 2)
    dx = abs(x - (rx + b / 2)) - (b / 2 - r)
    dy = abs(y - (ry + h / 2)) - (h / 2 - r)
    if dx > r or dy > r:
        return False
    if dx <= 0 or dy <= 0:      # in einem der beiden Balken, nicht in der Ecke
        return True
    return dx * dx + dy * dy <= r * r


def _abstand_strecke(x: float, y: float, x1: float, y1: float,
                     x2: float, y2: float) -> float:
    dx, dy = x2 - x1, y2 - y1
    laenge = dx * dx + dy * dy
    t = 0.0 if laenge == 0 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / laenge))
    return math.hypot(x - (x1 + t * dx), y - (y1 + t * dy))


def _im_polygon(x: float, y: float, ecken) -> bool:
    """Strahlenschnitt: liegt der Punkt innerhalb des Polygons?"""
    drin = False
    for i in range(len(ecken)):
        x1, y1 = ecken[i]
        x2, y2 = ecken[i - 1]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) / (y2 - y1) * (x2 - x1):
            drin = not drin
    return drin


def _in_form(x: float, y: float, form: tuple) -> bool:
    art = form[0]
    if art == "rr":
        return _im_rr(x, y, form)
    if art == "kreis":
        _, cx, cy, r = form
        return (x - cx) ** 2 + (y - cy) ** 2 <= r * r
    if art == "strich":
        _, x1, y1, x2, y2, b = form
        return _abstand_strecke(x, y, x1, y1, x2, y2) <= b / 2
    if art == "zug":
        _, ecken, b, zu = form
        # Breite 0 heisst gefüllt statt umrandet — der Weg, wie die kleine
        # Fassung aus demselben Umriss ein Tuch macht.
        if b <= 0:
            return _im_polygon(x, y, ecken)
        paare = list(zip(ecken, ecken[1:]))
        if zu:
            paare.append((ecken[-1], ecken[0]))
        return any(_abstand_strecke(x, y, a[0], a[1], e[0], e[1]) <= b / 2
                   for a, e in paare)
    raise ValueError(f"unbekannte Form: {art}")


_GRUND = ("rr", 0.0, 0.0, RASTER, RASTER, RASTER * RUNDUNG)


def punkte(kante: int, proben: int = PROBEN):
    """Liefert das Bild zeilenweise von OBEN nach unten als (r, g, b, a).

    Je Pixel werden `proben`² Punkte geprüft: daraus die Deckung am Rand (Alpha)
    und die Mischung Amber↔Motiv. Das kostet bei 32×32 rund 16 000 Punktproben —
    einmalig — und ist der Unterschied zwischen runden Ecken und einer Treppe.
    """
    formen = motiv_fuer(kante)
    gesamt = proben * proben
    schritt = RASTER / kante
    for zy in range(kante):
        zeile = []
        for zx in range(kante):
            innen = motiv = 0
            for py in range(proben):
                y = (zy + (py + 0.5) / proben) * schritt
                for px in range(proben):
                    x = (zx + (px + 0.5) / proben) * schritt
                    if not _in_form(x, y, _GRUND):
                        continue
                    innen += 1
                    if any(_in_form(x, y, f) for f in formen):
                        motiv += 1
            anteil = motiv / innen if innen else 0.0
            zeile.append(tuple(round(a + (d - a) * anteil)
                               for a, d in zip(AMBER, DUNKEL))
                         + (round(255 * innen / gesamt),))
        yield zeile
