"""Rastert das Sequenz-Studio-Logo für Windows und Verknüpfungen.

Die SVG-Dateien neben der Weboberfläche sind die einzige Quelle für das Motiv.
Der Browser lädt sie direkt; `winapi.set_window_icon` und `tools/symbol.py`
holen über :func:`pixel_rows` dieselben Formen als RGBA-Pixel. Damit bleiben
Kopfzeile, Titelleiste, Taskleiste und exportierte Symbole identisch.

**Zwei Dateien, weil es zwei Grössen sind, nicht zwei Motive.** Das grosse
Motiv hat neun Knoten und 10er-Linien — bei 16 px sind das Linien unter einem
Pixel, und heraus kam graues Rauschen genau dort, wo man das Symbol am
häufigsten sieht (Titelleiste, Browser-Tab). Das kleine ist dieselbe Kette mit
vier Knoten, jede Kante auf dem 16er-Raster. Bis `SMALL_UP_TO` Pixel gilt das
kleine, darüber das grosse — es ist das eigentliche Logo.

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


_WEB = Path(__file__).parent / "editors" / "sequence_studio" / "web"
LOGO_PATH = _WEB / "sequenz-studio-logo.svg"
LOGO_SMALL_PATH = _WEB / "sequenz-studio-logo-small.svg"
# Bis zu dieser Kantenlänge das kleine Motiv. Nur 16 px: ab 32 ist das grosse
# lesbar genug, und es ist das eigentliche Logo — das kleine springt nur dort
# ein, wo vom grossen nichts übrig bleibt.
SMALL_UP_TO = 24
SAMPLES = 4
CURVE_STEPS = 12

_TOKEN = re.compile(r"[A-Za-z]|[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
_ROTATION = re.compile(
    r"\s*rotate\(\s*([-+\d.]+)(?:[\s,]+([-+\d.]+)[\s,]+([-+\d.]+))?\s*\)\s*")


def _path_polygons(data: str) -> tuple[tuple[tuple[float, float], ...], ...]:
    """Flacht einen SVG-Pfad aus M/L/C/Z zu geschlossenen Polygonen ab."""
    reader = _PathReader(data)
    command = None
    while not reader.done():
        token = reader.peek()
        if token.isalpha():
            reader.skip()
            command = token
            if command in "Zz":
                reader.close_path()
                command = None
                continue
            if command not in _PATH_COMMANDS:
                raise ValueError(f"SVG-Befehl {command!r} wird im Studio-Logo nicht unterstützt")
        if command is None:
            raise ValueError("Koordinate ohne SVG-Befehl im Studio-Logo")
        getattr(reader, _PATH_COMMANDS[command])()
        # Weitere Paare nach M sind laut SVG normale Linien.
        if command == "M":
            command = "L"

    reader.finish_polygon()
    if not reader.polygons:
        raise ValueError("Das Studio-Logo enthält einen leeren SVG-Pfad")
    return tuple(reader.polygons)


# Befehl → Methode von `_PathReader`. Z steht nicht darin: es liest keine Zahlen.
_PATH_COMMANDS = {"M": "move", "L": "line", "C": "curve"}


class _PathReader:
    """Die Zahlen eines Pfads und das Polygon, das gerade entsteht."""

    def __init__(self, data: str) -> None:
        self._parts = _TOKEN.findall(data)
        self._i = 0
        self.polygons: list[tuple[tuple[float, float], ...]] = []
        self._polygon: list[tuple[float, float]] = []
        self._position = (0.0, 0.0)
        self._start = (0.0, 0.0)

    def done(self) -> bool:
        return self._i >= len(self._parts)

    def peek(self) -> str:
        return self._parts[self._i]

    def skip(self) -> None:
        self._i += 1

    def number(self) -> float:
        if self.done() or self.peek().isalpha():
            raise ValueError("Unvollständiger SVG-Pfad im Studio-Logo")
        value = float(self.peek())
        self.skip()
        return value

    def finish_polygon(self) -> None:
        """Legt das laufende Polygon ab — mit weniger als drei Punkten ist es keins."""
        if len(self._polygon) >= 3:
            self.polygons.append(tuple(self._polygon))
        self._polygon = []

    def close_path(self) -> None:
        """Z: Polygon ab, weiter geht es am Anfang des Teilpfads."""
        self.finish_polygon()
        self._position = self._start

    def move(self) -> None:
        self.finish_polygon()
        self._position = (self.number(), self.number())
        self._start = self._position
        self._polygon = [self._position]

    def line(self) -> None:
        self._position = (self.number(), self.number())
        self._polygon.append(self._position)

    def curve(self) -> None:
        """C: kubische Bézier-Kurve, in CURVE_STEPS Geradenstücke zerlegt."""
        x0, y0 = self._position
        x1, y1, x2, y2, x3, y3 = (self.number() for _ in range(6))
        for step in range(1, CURVE_STEPS + 1):
            t = step / CURVE_STEPS
            u = 1.0 - t
            self._polygon.append((
                u ** 3 * x0 + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t ** 3 * x3,
                u ** 3 * y0 + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t ** 3 * y3,
            ))
        self._position = (x3, y3)


def _rotator(transform: str):
    """Liefert die Punktabbildung für die im Logo verwendete SVG-Rotation."""
    if not transform:
        return lambda point: point
    match = _ROTATION.fullmatch(transform)
    if not match:
        raise ValueError(f"Unbekannte SVG-Transformation im Studio-Logo: {transform!r}")
    angle = math.radians(float(match.group(1)))
    cx = float(match.group(2) or 0.0)
    cy = float(match.group(3) or 0.0)
    cos_value, sin_value = math.cos(angle), math.sin(angle)

    def rotate(point):
        x, y = point[0] - cx, point[1] - cy
        return (cx + x * cos_value - y * sin_value,
                cy + x * sin_value + y * cos_value)

    return rotate


def _tag(element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def logo_path(edge: int) -> Path:
    """Welche Datei für diese Kantenlänge gilt."""
    return LOGO_SMALL_PATH if edge <= SMALL_UP_TO else LOGO_PATH


@lru_cache(maxsize=2)
def _logo_geometry(path: Path = LOGO_PATH):
    """Liest Farbe, ViewBox, sichtbaren Grund und Aussparungen aus dem SVG."""
    root_layer = ElementTree.parse(path).getroot()
    viewbox = tuple(float(w) for w in root_layer.attrib["viewBox"].split())
    if len(viewbox) != 4 or viewbox[2] <= 0 or viewbox[3] <= 0:
        raise ValueError("Ungültige viewBox im Studio-Logo")

    color_rect = next((e for e in root_layer if _tag(e) == "rect" and "mask" in e.attrib), None)
    if color_rect is None:
        raise ValueError("Farbfläche im Studio-Logo fehlt")
    color_text = color_rect.attrib.get("fill", "").lstrip("#")
    if len(color_text) != 6:
        raise ValueError("Das Studio-Logo braucht eine sechsstellige Hex-Farbe")
    color = tuple(int(color_text[i:i + 2], 16) for i in (0, 2, 4))

    mask = next((e for e in root_layer.iter() if _tag(e) == "mask"), None)
    group = (next((e for e in mask.iter() if _tag(e) == "g"), None)
               if mask is not None else None)
    if group is None:
        raise ValueError("Pfadgruppe in der Maske des Studio-Logos fehlt")
    rotate = _rotator(group.attrib.get("transform", ""))

    reason = []
    cutouts = []
    for path in (e for e in group.iter() if _tag(e) == "path"):
        target = reason if path.attrib.get("fill", "").lower() in {"white", "#fff", "#ffffff"} \
            else cutouts
        for polygon in _path_polygons(path.attrib.get("d", "")):
            target.append(tuple(rotate(point) for point in polygon))
    if not reason or not cutouts:
        raise ValueError("Grund oder transparente Aussparung im Studio-Logo fehlt")
    return color, viewbox, tuple(reason), tuple(cutouts)


def _intervals(polygons, y: float):
    """Gibt die nach Even/Odd-Regel gefüllten X-Intervalle einer Zeile zurück."""
    for polygon in polygons:
        cuts = []
        before = polygon[-1]
        for point in polygon:
            x1, y1 = before
            x2, y2 = point
            if (y1 > y) != (y2 > y):
                cuts.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
            before = point
        cuts.sort()
        for i in range(0, len(cuts) - 1, 2):
            yield cuts[i], cuts[i + 1]


def _paint(line: bytearray, intervals, value: int,
          left: float, step: float) -> None:
    """Setzt Subpixel, deren Mittelpunkt in einem der Intervalle liegt."""
    width = len(line)
    fill = bytes((value,))
    for beginning, end in intervals:
        from_index = max(0, math.ceil((beginning - left) / step - 0.5))
        until = min(width, math.ceil((end - left) / step - 0.5))
        if until > from_index:
            line[from_index:until] = fill * (until - from_index)


def pixel_rows(edge: int, samples: int = SAMPLES):
    """Liefert das Logo von oben nach unten als Zeilen mit RGBA-Pixeln.

    Kleine Windows-Symbole erhalten vier Subpixel je Achse. Bei großen Exporten
    reichen weniger Proben, weil ein Bildpixel dort bereits deutlich kleiner als
    die Kurven des 256er-SVGs ist.
    """
    if edge <= 0 or samples <= 0:
        raise ValueError("Kantenlänge und Probenzahl müssen positiv sein")
    if edge >= 512:
        samples = min(samples, 1)
    elif edge >= 128:
        samples = min(samples, 2)

    color, (left, top, width, height), reason, cutouts = _logo_geometry(logo_path(edge))
    sub_width = edge * samples
    x_step = width / sub_width
    y_step = height / (edge * samples)
    total = samples * samples

    for zy in range(edge):
        coverage = [0] * edge
        for py in range(samples):
            y = top + (zy * samples + py + 0.5) * y_step
            subpixel = bytearray(sub_width)
            _paint(subpixel, _intervals(reason, y), 1, left, x_step)
            _paint(subpixel, _intervals(cutouts, y), 0, left, x_step)
            for zx in range(edge):
                from_index = zx * samples
                coverage[zx] += sum(subpixel[from_index:from_index + samples])
        yield [color + (round(255 * fraction / total),) for fraction in coverage]
