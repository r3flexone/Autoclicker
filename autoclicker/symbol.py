"""Rastert das Sequenz-Studio-Logo für Windows und Verknüpfungen.

Die SVG-Datei neben der Weboberfläche ist die einzige Quelle für das Motiv. Der
Browser lädt sie direkt; `winapi.setze_fenster_symbol` und `tools/symbol.py`
holen über :func:`punkte` dieselben Formen als RGBA-Pixel. Damit bleiben
Kopfzeile, Titelleiste, Taskleiste und exportierte Symbole identisch.

Absichtlich gibt es keine SVG- oder Pillow-Laufzeitabhängigkeit. Das neue Logo
braucht aus SVG nur gefüllte Pfade mit M/L/C/Z sowie eine Rotation. Diese kleine
Teilmenge wird hier mit der Standardbibliothek gelesen und zeilenweise mit
Kantenglättung gerastert. Die transparenten Aussparungen bleiben dabei echte
Transparenz statt dunkler Ersatzfarbe.
"""

from functools import lru_cache
import math
from pathlib import Path
import re
from xml.etree import ElementTree


LOGO_PFAD = (Path(__file__).parent / "editors" / "sequence_studio" / "web"
             / "sequenz-studio-logo.svg")
PROBEN = 4
KURVEN_SCHRITTE = 12

_TOKEN = re.compile(r"[A-Za-z]|[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
_ROTATION = re.compile(
    r"\s*rotate\(\s*([-+\d.]+)(?:[\s,]+([-+\d.]+)[\s,]+([-+\d.]+))?\s*\)\s*")


def _pfad_polygone(daten: str) -> tuple[tuple[tuple[float, float], ...], ...]:
    """Flacht einen SVG-Pfad aus M/L/C/Z zu geschlossenen Polygonen ab."""
    teile = _TOKEN.findall(daten)
    polygone: list[tuple[tuple[float, float], ...]] = []
    polygon: list[tuple[float, float]] = []
    befehl = None
    position = (0.0, 0.0)
    start = (0.0, 0.0)
    i = 0

    def zahl() -> float:
        nonlocal i
        if i >= len(teile) or teile[i].isalpha():
            raise ValueError("Unvollständiger SVG-Pfad im Studio-Logo")
        wert = float(teile[i])
        i += 1
        return wert

    while i < len(teile):
        if teile[i].isalpha():
            befehl = teile[i]
            i += 1
            if befehl in "Zz":
                if len(polygon) >= 3:
                    polygone.append(tuple(polygon))
                polygon = []
                position = start
                befehl = None
                continue
            if befehl not in {"M", "L", "C"}:
                raise ValueError(f"SVG-Befehl {befehl!r} wird im Studio-Logo nicht unterstützt")
        if befehl is None:
            raise ValueError("Koordinate ohne SVG-Befehl im Studio-Logo")

        if befehl == "M":
            if len(polygon) >= 3:
                polygone.append(tuple(polygon))
            position = (zahl(), zahl())
            start = position
            polygon = [position]
            # Weitere Paare nach M sind laut SVG normale Linien.
            befehl = "L"
        elif befehl == "L":
            position = (zahl(), zahl())
            polygon.append(position)
        else:  # C: kubische Bézier-Kurve
            x0, y0 = position
            x1, y1, x2, y2, x3, y3 = (zahl() for _ in range(6))
            for schritt in range(1, KURVEN_SCHRITTE + 1):
                t = schritt / KURVEN_SCHRITTE
                u = 1.0 - t
                polygon.append((
                    u ** 3 * x0 + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t ** 3 * x3,
                    u ** 3 * y0 + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t ** 3 * y3,
                ))
            position = (x3, y3)

    if len(polygon) >= 3:
        polygone.append(tuple(polygon))
    if not polygone:
        raise ValueError("Das Studio-Logo enthält einen leeren SVG-Pfad")
    return tuple(polygone)


def _dreher(transform: str):
    """Liefert die Punktabbildung für die im Logo verwendete SVG-Rotation."""
    if not transform:
        return lambda punkt: punkt
    treffer = _ROTATION.fullmatch(transform)
    if not treffer:
        raise ValueError(f"Unbekannte SVG-Transformation im Studio-Logo: {transform!r}")
    winkel = math.radians(float(treffer.group(1)))
    cx = float(treffer.group(2) or 0.0)
    cy = float(treffer.group(3) or 0.0)
    cosinus, sinus = math.cos(winkel), math.sin(winkel)

    def drehen(punkt):
        x, y = punkt[0] - cx, punkt[1] - cy
        return (cx + x * cosinus - y * sinus,
                cy + x * sinus + y * cosinus)

    return drehen


def _tag(element) -> str:
    return element.tag.rsplit("}", 1)[-1]


@lru_cache(maxsize=1)
def _logo_geometrie():
    """Liest Farbe, ViewBox, sichtbaren Grund und Aussparungen aus dem SVG."""
    wurzel = ElementTree.parse(LOGO_PFAD).getroot()
    viewbox = tuple(float(w) for w in wurzel.attrib["viewBox"].split())
    if len(viewbox) != 4 or viewbox[2] <= 0 or viewbox[3] <= 0:
        raise ValueError("Ungültige viewBox im Studio-Logo")

    farb_rect = next((e for e in wurzel if _tag(e) == "rect" and "mask" in e.attrib), None)
    if farb_rect is None:
        raise ValueError("Farbfläche im Studio-Logo fehlt")
    farbtext = farb_rect.attrib.get("fill", "").lstrip("#")
    if len(farbtext) != 6:
        raise ValueError("Das Studio-Logo braucht eine sechsstellige Hex-Farbe")
    farbe = tuple(int(farbtext[i:i + 2], 16) for i in (0, 2, 4))

    maske = next((e for e in wurzel.iter() if _tag(e) == "mask"), None)
    gruppe = (next((e for e in maske.iter() if _tag(e) == "g"), None)
               if maske is not None else None)
    if gruppe is None:
        raise ValueError("Pfadgruppe in der Maske des Studio-Logos fehlt")
    drehen = _dreher(gruppe.attrib.get("transform", ""))

    grund = []
    aussparungen = []
    for pfad in (e for e in gruppe.iter() if _tag(e) == "path"):
        ziel = grund if pfad.attrib.get("fill", "").lower() in {"white", "#fff", "#ffffff"} \
            else aussparungen
        for polygon in _pfad_polygone(pfad.attrib.get("d", "")):
            ziel.append(tuple(drehen(punkt) for punkt in polygon))
    if not grund or not aussparungen:
        raise ValueError("Grund oder transparente Aussparung im Studio-Logo fehlt")
    return farbe, viewbox, tuple(grund), tuple(aussparungen)


def _intervalle(polygone, y: float):
    """Gibt die nach Even/Odd-Regel gefüllten X-Intervalle einer Zeile zurück."""
    for polygon in polygone:
        schnitte = []
        vorher = polygon[-1]
        for punkt in polygon:
            x1, y1 = vorher
            x2, y2 = punkt
            if (y1 > y) != (y2 > y):
                schnitte.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
            vorher = punkt
        schnitte.sort()
        for i in range(0, len(schnitte) - 1, 2):
            yield schnitte[i], schnitte[i + 1]


def _male(zeile: bytearray, intervalle, wert: int,
          links: float, schritt: float) -> None:
    """Setzt Subpixel, deren Mittelpunkt in einem der Intervalle liegt."""
    breite = len(zeile)
    fuellung = bytes((wert,))
    for anfang, ende in intervalle:
        von = max(0, math.ceil((anfang - links) / schritt - 0.5))
        bis = min(breite, math.ceil((ende - links) / schritt - 0.5))
        if bis > von:
            zeile[von:bis] = fuellung * (bis - von)


def punkte(kante: int, proben: int = PROBEN):
    """Liefert das Logo von oben nach unten als Zeilen mit RGBA-Pixeln.

    Kleine Windows-Symbole erhalten vier Subpixel je Achse. Bei großen Exporten
    reichen weniger Proben, weil ein Bildpixel dort bereits deutlich kleiner als
    die Kurven des 256er-SVGs ist.
    """
    if kante <= 0 or proben <= 0:
        raise ValueError("Kantenlänge und Probenzahl müssen positiv sein")
    if kante >= 512:
        proben = min(proben, 1)
    elif kante >= 128:
        proben = min(proben, 2)

    farbe, (links, oben, breite, hoehe), grund, aussparungen = _logo_geometrie()
    sub_breite = kante * proben
    x_schritt = breite / sub_breite
    y_schritt = hoehe / (kante * proben)
    gesamt = proben * proben

    for zy in range(kante):
        deckung = [0] * kante
        for py in range(proben):
            y = oben + (zy * proben + py + 0.5) * y_schritt
            subpixel = bytearray(sub_breite)
            _male(subpixel, _intervalle(grund, y), 1, links, x_schritt)
            _male(subpixel, _intervalle(aussparungen, y), 0, links, x_schritt)
            for zx in range(kante):
                von = zx * proben
                deckung[zx] += sum(subpixel[von:von + proben])
        yield [farbe + (round(255 * anteil / gesamt),) for anteil in deckung]
