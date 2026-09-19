"""Rastert das Sequenz-Studio-Logo für Windows und Verknüpfungen.

Die SVG-Datei neben der Weboberfläche ist die einzige Quelle für das Motiv. Der
Browser lädt sie direkt; `winapi.set_window_icon` und `tools/symbol.py`
holen über :func:`pixel_rows` dieselben Formen als RGBA-Pixel. Damit bleiben
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


LOGO_PATH = (Path(__file__).parent / "editors" / "sequence_studio" / "web"
             / "sequenz-studio-logo.svg")
SAMPLES = 4
CURVE_STEPS = 12

_TOKEN = re.compile(r"[A-Za-z]|[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
_ROTATION = re.compile(
    r"\s*rotate\(\s*([-+\d.]+)(?:[\s,]+([-+\d.]+)[\s,]+([-+\d.]+))?\s*\)\s*")


def _path_polygons(data: str) -> tuple[tuple[tuple[float, float], ...], ...]:
    """Flacht einen SVG-Pfad aus M/L/C/Z zu geschlossenen Polygonen ab."""
    parts = _TOKEN.findall(data)
    polygone: list[tuple[tuple[float, float], ...]] = []
    polygon: list[tuple[float, float]] = []
    command = None
    position = (0.0, 0.0)
    start = (0.0, 0.0)
    i = 0

    def number() -> float:
        nonlocal i
        if i >= len(parts) or parts[i].isalpha():
            raise ValueError("Unvollständiger SVG-Pfad im Studio-Logo")
        value = float(parts[i])
        i += 1
        return value

    while i < len(parts):
        if parts[i].isalpha():
            command = parts[i]
            i += 1
            if command in "Zz":
                if len(polygon) >= 3:
                    polygone.append(tuple(polygon))
                polygon = []
                position = start
                command = None
                continue
            if command not in {"M", "L", "C"}:
                raise ValueError(f"SVG-Befehl {command!r} wird im Studio-Logo nicht unterstützt")
        if command is None:
            raise ValueError("Koordinate ohne SVG-Befehl im Studio-Logo")

        if command == "M":
            if len(polygon) >= 3:
                polygone.append(tuple(polygon))
            position = (number(), number())
            start = position
            polygon = [position]
            # Weitere Paare nach M sind laut SVG normale Linien.
            command = "L"
        elif command == "L":
            position = (number(), number())
            polygon.append(position)
        else:  # C: kubische Bézier-Kurve
            x0, y0 = position
            x1, y1, x2, y2, x3, y3 = (number() for _ in range(6))
            for step in range(1, CURVE_STEPS + 1):
                t = step / CURVE_STEPS
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


def _rotator(transform: str):
    """Liefert die Punktabbildung für die im Logo verwendete SVG-Rotation."""
    if not transform:
        return lambda point: point
    match = _ROTATION.fullmatch(transform)
    if not match:
        raise ValueError(f"Unbekannte SVG-Transformation im Studio-Logo: {transform!r}")
    winkel = math.radians(float(match.group(1)))
    cx = float(match.group(2) or 0.0)
    cy = float(match.group(3) or 0.0)
    cosinus, sinus = math.cos(winkel), math.sin(winkel)

    def rotate(point):
        x, y = point[0] - cx, point[1] - cy
        return (cx + x * cosinus - y * sinus,
                cy + x * sinus + y * cosinus)

    return rotate


def _tag(element) -> str:
    return element.tag.rsplit("}", 1)[-1]


@lru_cache(maxsize=1)
def _logo_geometry():
    """Liest Farbe, ViewBox, sichtbaren Grund und Aussparungen aus dem SVG."""
    wurzel = ElementTree.parse(LOGO_PATH).getroot()
    viewbox = tuple(float(w) for w in wurzel.attrib["viewBox"].split())
    if len(viewbox) != 4 or viewbox[2] <= 0 or viewbox[3] <= 0:
        raise ValueError("Ungültige viewBox im Studio-Logo")

    farb_rect = next((e for e in wurzel if _tag(e) == "rect" and "mask" in e.attrib), None)
    if farb_rect is None:
        raise ValueError("Farbfläche im Studio-Logo fehlt")
    color_text = farb_rect.attrib.get("fill", "").lstrip("#")
    if len(color_text) != 6:
        raise ValueError("Das Studio-Logo braucht eine sechsstellige Hex-Farbe")
    color = tuple(int(color_text[i:i + 2], 16) for i in (0, 2, 4))

    maske = next((e for e in wurzel.iter() if _tag(e) == "mask"), None)
    group = (next((e for e in maske.iter() if _tag(e) == "g"), None)
               if maske is not None else None)
    if group is None:
        raise ValueError("Pfadgruppe in der Maske des Studio-Logos fehlt")
    rotate = _rotator(group.attrib.get("transform", ""))

    reason = []
    aussparungen = []
    for path in (e for e in group.iter() if _tag(e) == "path"):
        target = reason if path.attrib.get("fill", "").lower() in {"white", "#fff", "#ffffff"} \
            else aussparungen
        for polygon in _path_polygons(path.attrib.get("d", "")):
            target.append(tuple(rotate(point) for point in polygon))
    if not reason or not aussparungen:
        raise ValueError("Grund oder transparente Aussparung im Studio-Logo fehlt")
    return color, viewbox, tuple(reason), tuple(aussparungen)


def _intervals(polygone, y: float):
    """Gibt die nach Even/Odd-Regel gefüllten X-Intervalle einer Zeile zurück."""
    for polygon in polygone:
        schnitte = []
        before = polygon[-1]
        for point in polygon:
            x1, y1 = before
            x2, y2 = point
            if (y1 > y) != (y2 > y):
                schnitte.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
            before = point
        schnitte.sort()
        for i in range(0, len(schnitte) - 1, 2):
            yield schnitte[i], schnitte[i + 1]


def _paint(line: bytearray, intervalle, value: int,
          left: float, step: float) -> None:
    """Setzt Subpixel, deren Mittelpunkt in einem der Intervalle liegt."""
    width = len(line)
    fuellung = bytes((value,))
    for anfang, end in intervalle:
        from_index = max(0, math.ceil((anfang - left) / step - 0.5))
        until = min(width, math.ceil((end - left) / step - 0.5))
        if until > from_index:
            line[from_index:until] = fuellung * (until - from_index)


def pixel_rows(edge: int, proben: int = SAMPLES):
    """Liefert das Logo von oben nach unten als Zeilen mit RGBA-Pixeln.

    Kleine Windows-Symbole erhalten vier Subpixel je Achse. Bei großen Exporten
    reichen weniger Proben, weil ein Bildpixel dort bereits deutlich kleiner als
    die Kurven des 256er-SVGs ist.
    """
    if edge <= 0 or proben <= 0:
        raise ValueError("Kantenlänge und Probenzahl müssen positiv sein")
    if edge >= 512:
        proben = min(proben, 1)
    elif edge >= 128:
        proben = min(proben, 2)

    color, (left, top, width, height), reason, aussparungen = _logo_geometry()
    sub_breite = edge * proben
    x_schritt = width / sub_breite
    y_schritt = height / (edge * proben)
    total = proben * proben

    for zy in range(edge):
        deckung = [0] * edge
        for py in range(proben):
            y = top + (zy * proben + py + 0.5) * y_schritt
            subpixel = bytearray(sub_breite)
            _paint(subpixel, _intervals(reason, y), 1, left, x_schritt)
            _paint(subpixel, _intervals(aussparungen, y), 0, left, x_schritt)
            for zx in range(edge):
                from_index = zx * proben
                deckung[zx] += sum(subpixel[from_index:from_index + proben])
        yield [color + (round(255 * anteil / total),) for anteil in deckung]
