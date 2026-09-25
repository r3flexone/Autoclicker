"""
Bildverarbeitung und Farberkennung für den Autoclicker.
Screenshots, Farbanalyse, Template-Matching.
"""

import logging
import os
from pathlib import Path
# 'Image.Image' in den Annotationen ist ein String und wird nie ausgewertet - der Name
# kommt aus dem optionalen Pillow-Import weiter unten. Ein zusaetzlicher TYPE_CHECKING-
# Import waere nur eine zweite Definition desselben Namens.
from typing import Optional

from .config import CONFIG
from .models import DEFAULT_MIN_CONFIDENCE
from .utils import safe_input, interactive_select, err
from .winapi import (
    capture_screen, capture_window, get_client_rect_by_handle, get_cursor_pos,
    get_screen_pixel,
)

# Logger
logger = logging.getLogger("autoclicker")

# Verzeichnisse (importiert aus persistence um Duplizierung zu vermeiden)
from .persistence import SEQUENCE_SCREENSHOTS_DIR

# Vorlagenordner, wenn ein Aufrufer keinen mitgibt. Bewusst `None`: Vorlagen
# liegen je Sequenz unter `sequences/<name>/templates/`, einen programmweiten
# Ordner gibt es seit dem Umzug auf Besitzeinheiten nicht mehr. Hier stand als
# Rueckfall `items/templates/` — ein Pfad, der absichtlich ins Leere zeigte,
# „damit es auffaellt"; aufgefallen ist er als „Template nicht gefunden" im
# Rauschen. Ohne Ordner gibt es jetzt keinen Pfad und eine Zeile, die das sagt.
# Wer Vorlagen sucht, nimmt `active_templates_dir(state)` bzw.
# `sequence_templates_dir(name)`; Tests setzen die Variable fuer einen Sandkasten.
TEMPLATES_DIR: str | None = None
_missing_root_reported = False


def _template_path(template_name: str, template_root=None) -> str | None:
    """Löst einen Template-Namen sicher innerhalb des Vorlagenordners auf.

    Scan-Dateien sind normale JSON-Dateien und können auch von Hand verändert
    werden. Absolute Pfade und ``..`` dürfen den Template-Ordner deshalb niemals
    verlassen. Ohne Ordner (weder Argument noch `TEMPLATES_DIR`) gibt es keinen
    Pfad — und einmal je Prozess eine Zeile, die den fehlenden Ordner nennt.
    """
    global _missing_root_reported
    if not isinstance(template_name, str) or not template_name.strip():
        return None
    relative = Path(template_name)
    if relative.is_absolute():
        return None
    base = template_root or TEMPLATES_DIR
    if not base:
        if not _missing_root_reported:
            _missing_root_reported = True
            logger.warning("Vorlage '%s' ohne Vorlagenordner angefragt — der Aufrufer "
                           "muss `template_root` mitgeben (sequence_templates_dir).",
                           template_name)
        return None
    root = Path(base).resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    if candidate == root:
        return None
    return str(candidate)

# Optionale Imports
try:
    from PIL import Image
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    logger.warning("Pillow nicht installiert. Bilderkennung deaktiviert.")
    logger.warning("Installieren mit: pip install pillow")

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    logger.warning("OpenCV nicht installiert. Template Matching deaktiviert.")
    logger.warning("Installieren mit: pip install opencv-python")



def get_pixel_color(x: int, y: int) -> tuple[int, int, int] | None:
    """Liest die Farbe eines einzelnen Pixels an der angegebenen Position."""
    if not PILLOW_AVAILABLE:
        return None
    return get_screen_pixel(int(x), int(y))


# Wie weit um einen aufgenommenen Klick die Fläche gemessen wird (in jede
# Richtung). Gemessen an einer echten Aufnahme: sechs Klicks auf denselben
# breiten Knopf lagen bis 55 px auseinander — ein Radius von 8 px legte dafür
# fünf Punkte an. 64 reicht für den Knopf und kostet einen BitBlt über 129×129
# Pixel (rund 12 ms, im Maus-Hook unbedenklich).
SURFACE_RADIUS = 64


def capture_surface(x: int, y: int) -> Optional[tuple]:
    """`(links, oben, Bild)` um eine Stelle — oder `None` (kein Pillow, kein Bild).

    Aufgenommen wird im Maus-Hook, also bevor das Spiel den Klick überhaupt
    sieht: der Knopf steht noch so da, wie ihn der Klick getroffen hat.
    """
    left, top = int(x) - SURFACE_RADIUS, int(y) - SURFACE_RADIUS
    try:
        image = capture_screen((left, top, int(x) + SURFACE_RADIUS + 1,
                                int(y) + SURFACE_RADIUS + 1))
    except (OSError, ValueError, TypeError, AttributeError):
        return None
    if image is None:
        return None
    return left, top, image


def click_surface(patch, x: int, y: int, color, tolerance: int) -> Optional[frozenset]:
    """Die zusammenhängende Farbfläche um `(x, y)` — in Bildschirm-Koordinaten.

    „Derselbe Knopf" ist keine Frage des Abstands, sondern der Fläche: zwei
    Klicks auf einen breiten Knopf liegen weit auseinander, zwei gleichfarbige
    Knöpfe übereinander dicht beieinander — aber zwischen ihnen liegt ein Rand
    in anderer Farbe. Gefüllt wird deshalb vom Klick aus (4er-Nachbarschaft),
    solange jede Farbe höchstens `tolerance` je Kanal von der Klickfarbe
    abweicht. Beschriftung auf dem Knopf sind Löcher, um die herum gefüllt wird.

    Verglichen wird mit der KLICKfarbe, nicht mit dem Nachbarpixel: sonst liefe
    die Füllung über einen weichen Verlauf in die nächste Fläche hinein.
    """
    if patch is None or not color:
        return None
    left, top, image = patch
    try:
        width, height = image.size
        data = image.convert("RGB").tobytes()
    except (OSError, ValueError, AttributeError):
        return None
    cx, cy = int(x) - left, int(y) - top
    if not (0 <= cx < width and 0 <= cy < height):
        return None
    r0, g0, b0 = (int(v) for v in color[:3])

    def fits(index: int) -> bool:
        o = index * 3
        return (abs(data[o] - r0) <= tolerance and abs(data[o + 1] - g0) <= tolerance
                and abs(data[o + 2] - b0) <= tolerance)

    start = cy * width + cx
    if not fits(start):
        return None
    seen = bytearray(width * height)
    seen[start] = 1
    stack = [start]
    area = []
    while stack:
        index = stack.pop()
        area.append(index)
        px, py = index % width, index // width
        for neighbor, inside in ((index - 1, px > 0), (index + 1, px < width - 1),
                                 (index - width, py > 0), (index + width, py < height - 1)):
            if inside and not seen[neighbor]:
                seen[neighbor] = 1
                if fits(neighbor):
                    stack.append(neighbor)
    return frozenset((left + i % width, top + i // width) for i in area)


def color_distance(c1: tuple, c2: tuple) -> float:
    """Berechnet die Distanz zwischen zwei RGB-Farben."""
    return ((c1[0]-c2[0])**2 + (c1[1]-c2[1])**2 + (c1[2]-c2[2])**2) ** 0.5


def find_color_in_image(img: 'Image.Image', target_color: tuple, tolerance: float,
                        pixel_step: int = 2, min_pixels: int = 1) -> bool:
    """Prüft ob eine Farbe im Bild vorhanden ist (mit NumPy wenn verfügbar).

    `pixel_step` ist die Schrittweite des schnellen ersten Abtastens,
    `min_pixels` die nötige Anzahl passender Pixel (> 1 macht die Erkennung
    robuster gegen einzelne Rausch-Pixel). Verfehlt das Raster eine seltene
    Farbe, wird vollständig geprüft: die Beschleunigung darf nicht davon
    abhängen, ob ein Marker zufällig auf geraden Pixelkoordinaten liegt.
    """
    min_pixels = max(1, min_pixels)
    pixel_step = max(1, int(pixel_step))
    if NUMPY_AVAILABLE:
        # Schnelle NumPy-Version (ca. 100x schneller)
        # asarray vermeidet Kopie wenn PIL-Daten bereits im richtigen Format
        img_array = np.asarray(img)
        if len(img_array.shape) == 3 and img_array.shape[2] >= 3:
            target = np.array(target_color, dtype=np.float32)

            def enough(rgb) -> bool:
                # Quadrierte Distanz vergleichen (vermeidet teure sqrt-Berechnung)
                values = rgb.astype(np.float32)
                distances = np.sum((values - target) ** 2, axis=2)
                return int(np.count_nonzero(
                    distances <= tolerance * tolerance)) >= min_pixels

            # In fast allen Fällen trifft schon das kleine Raster. Nur beim
            # Fehlschlag folgt die vollständige Gegenprobe — genau dort lag
            # Item 7: zwei gültige Marker standen ausschliesslich dazwischen.
            if enough(img_array[::pixel_step, ::pixel_step, :3]):
                return True
            return pixel_step > 1 and enough(img_array[:, :, :3])
        return False
    else:
        # Fallback: Langsame PIL-Version
        pixels = img.load()
        width, height = img.size

        def enough(step: int) -> bool:
            matches = 0
            for x in range(0, width, step):
                for y in range(0, height, step):
                    pixel = pixels[x, y][:3]
                    if color_distance(pixel, target_color) <= tolerance:
                        matches += 1
                        if matches >= min_pixels:
                            return True
            return False

        if enough(pixel_step):
            return True
        if pixel_step > 1:
            return enough(1)
        return False


# TEMPLATE-CACHE
# Haelt das dekodierte Bild und die auf eine Slot-Groesse angepasste Variante;
# sonst laege jedes Template pro Item x Slot x Zyklus neu von Platte. Schluessel
# ist (mtime, size) der Datei - neu Gelerntes faellt von selbst raus. Ohne Lock:
# Dict-Zugriffe sind unter dem GIL atomar, schlimmstenfalls dekodieren zwei
# Threads dasselbe Bild doppelt.
_template_cache: dict = {}
_TEMPLATE_CACHE_MAX = 256

# Schon gemeldete Groessen-Konflikte. Der Schluessel ist die GROESSENPAARUNG
# (Template gegen Slot), nicht das einzelne Template - sonst steht die Meldung
# einmal pro Item da, und das sind bei zwei Inventaren im Bestand zwei Dutzend
# Zeilen mit derselben Aussage. Genau der Fall, gegen den die Sperre gedacht war:
# eine Konsole voll gleichlautender Warnungen liest niemand mehr.
_reported_sizes: set = set()


def _load_template(template_path: str):
    """Lädt ein Template-Bild (BGR) aus dem Cache oder von Platte. None wenn nicht da.

    Unicode-Pfade: cv2.imread scheitert an Umlauten, deshalb fromfile + imdecode.
    """
    if not OPENCV_AVAILABLE or not NUMPY_AVAILABLE:
        return None
    try:
        st = os.stat(template_path)
    except OSError:
        logger.error(f"Template nicht gefunden: {template_path}")
        return None

    stamp = (st.st_mtime, st.st_size)
    entry = _template_cache.get(template_path)
    if entry is not None and entry["stamp"] == stamp:
        return entry["image"]

    # UNCHANGED statt COLOR: ein Template mit Alpha-Kanal traegt darin seine
    # Maske. Ohne das faellt sie beim Laden weg und niemand merkt es.
    image = cv2.imdecode(np.fromfile(template_path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if image is not None and image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if image is None:
        logger.error(f"Konnte Template nicht laden: {template_path}")
        return None

    if len(_template_cache) >= _TEMPLATE_CACHE_MAX:
        _template_cache.clear()
    _template_cache[template_path] = {"stamp": stamp, "image": image, "scaled": {}}
    return image


def with_background_mask(img: 'Image.Image', background) -> 'Image.Image':
    """Legt einen Alpha-Kanal an: Hintergrund durchsichtig, Item deckend.

    Ein Slot besteht zu 60–90 % aus immer gleicher Slot-Fläche; ein Vergleich
    über das ganze Rechteck stimmt also hauptsächlich über den Hintergrund ab.
    Die Maske merkt sich Stellen, nicht Farben — deshalb trägt sie auch vor
    einem anders gefärbten Menü. Sie steckt IM Template-PNG, nicht in einer
    Datei daneben.
    """
    if img is None or not background:
        return img
    limit = CONFIG.scan_slot_color_distance
    rgb = img.convert("RGB")
    width, height = rgb.size
    pixel = rgb.load()
    mask = Image.new("L", (width, height))
    mp = mask.load()
    hr, hg, hb = background[:3]
    for y in range(height):
        for x in range(width):
            r, g, b = pixel[x, y]
            if ((r - hr) ** 2 + (g - hg) ** 2 + (b - hb) ** 2) ** 0.5 <= limit:
                mp[x, y] = 0
            else:
                mp[x, y] = 255
    result = rgb.convert("RGBA")
    result.putalpha(mask)
    return result


def _masked_confidence(image, template, mask) -> float:
    """TM_CCOEFF_NORMED, aber nur über die Pixel, die das Item ausmachen.

    Von Hand statt `cv2.matchTemplate(..., mask=)`: mit Maske kann OpenCV nur
    `TM_SQDIFF`/`TM_CCORR_NORMED`, deren Zahlen etwas anderes bedeuten — jede
    gespeicherte `min_confidence` verschöbe sich still. Template und Ausschnitt
    sind hier immer gleich gross, also genau eine Korrelation und keine Suche.
    """
    choice = mask > 127
    if int(choice.sum()) < 16:
        # Fast alles wegmaskiert — dann sagt die Rechnung nichts mehr aus.
        return 0.0
    a = template[choice].astype(np.float64).ravel()
    b = image[choice].astype(np.float64).ravel()
    a -= a.mean()
    b -= b.mean()
    denominator = float(np.sqrt(float((a * a).sum()) * float((b * b).sum())))
    return float((a * b).sum() / denominator) if denominator > 0 else 0.0


def _template_at_size(template_path: str, image, width: int, height: int):
    """Gibt das Template in der gewünschten Grösse zurück (skaliert + gemerkt).

    Die Grössen-Anpassung greift, wenn eine Slot-Region nach dem Erstellen des Templates
    geändert wurde. Sie ist pro Slot-Grösse immer dieselbe Rechnung — also einmal.
    """
    if image.shape[1] == width and image.shape[0] == height:
        return image
    entry = _template_cache.get(template_path)
    key_name = (width, height)
    if entry is not None:
        done = entry["scaled"].get(key_name)
        if done is not None:
            return done
    scaled = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
    if entry is not None:
        entry["scaled"][key_name] = scaled
    return scaled


def template_size(template_name: str, template_root=None) -> tuple[int, int] | None:
    """Pixelgroesse einer gespeicherten Vorlage, oder ``None`` wenn unlesbar."""
    template_path = _template_path(template_name, template_root)
    if template_path is None:
        return None
    template_cv = _load_template(template_path)
    if template_cv is None:
        return None
    return (int(template_cv.shape[1]), int(template_cv.shape[0]))


def _size_hint(template_name: str, tw: int, th: int,
                      iw: int, ih: int, value: float) -> str:
    """Der Text für den Fall „Template und Slot sind verschieden gross".

    Meist harmlos: verschiedene Flächen desselben Spiels haben verschiedene
    Slot-Höhen, und jedes Item wird auch gegen die Slots der anderen gehalten.
    Deshalb nennt der Text die Frage, die beide Fälle trennt (findet der Scan
    seine übrigen Items noch?), statt „Template neu aufnehmen" zu empfehlen —
    und keinen negativen Prozentwert, denn CCOEFF läuft von -1 bis +1.
    """
    similar = "keine Ähnlichkeit" if value <= 0 else f"nur {value:.0%} Ähnlichkeit"
    return (
        f"'{template_name}' wurde in einem Slot von {tw}x{th} gelernt, geprüft "
        f"wurde gegen {iw}x{ih} — {similar}.\n"
        "         Meist ist das normal: verschiedene Flächen desselben Spiels haben "
        "verschiedene Slot-Höhen (Ausrüstungsreihe vs. Inventar-Raster), und dieses "
        "Item gehört dann schlicht zur anderen.\n"
        "         Findet der Scan seine übrigen Items weiterhin? Dann ist alles in "
        "Ordnung. Findet er gar nichts mehr, hat sich die Slot-Region verschoben — "
        "dann Slots neu vermessen und die Templates neu lernen.\n"
        f"         (Weitere Templates mit {tw}x{th} gegen {iw}x{ih} werden nicht "
        "mehr gemeldet.)"
    )


def match_template_in_image(img: 'Image.Image', template_name: str,
                            min_confidence: float = DEFAULT_MIN_CONFIDENCE,
                            *, resize_template: bool = True,
                            report_size_mismatch: bool = True,
                            template_root=None) -> tuple:
    """Sucht ein Template-Bild im gegebenen Bild mittels OpenCV Template Matching.

    `resize_template` passt die Vorlage an eine abweichende Bildgrösse an;
    Item-Scans setzen das aus und nehmen eine passende Variante.
    `report_size_mismatch` schaltet die Diagnose ab (für bewusste Varianten-
    und Duplikatprüfungen).

    Gibt `(gefunden, konfidenz, (x, y) relativ zum Suchbereich | None)` zurück.
    """
    if not OPENCV_AVAILABLE:
        logger.warning("OpenCV nicht verfügbar für Template Matching")
        return (False, 0.0, None)

    if not NUMPY_AVAILABLE:
        logger.warning("NumPy nicht verfügbar für Template Matching")
        return (False, 0.0, None)

    template_path = _template_path(template_name, template_root)
    if template_path is None:
        logger.error("Unsicherer Template-Pfad abgewiesen: %r", template_name)
        return (False, 0.0, None)

    try:
        # PIL-Bild zu OpenCV-Format konvertieren (RGB -> BGR)
        img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

        template_cv = _load_template(template_path)
        if template_cv is None:
            return (False, 0.0, None)

        # Grössenvergleich: Template muss zum Scan-Bild passen
        th, tw = template_cv.shape[:2]
        ih, iw = img_cv.shape[:2]

        if (tw != iw or th != ih) and not resize_template:
            return (False, 0.0, None)

        if (tw != iw or th != ih) and tw > 0 and th > 0:
            # Grössen-Diskrepanz! Template an Scan-Bildgrösse anpassen
            # Passiert wenn Slot-Regionen nach Template-Erstellung geändert wurden
            # (z.B. neue Auto-Erkennung, Monitor-Wechsel, DPI-Änderung)
            logger.debug(f"Template '{template_name}' Grösse {tw}x{th} != Scan {iw}x{ih} - resize")
            template_cv = _template_at_size(template_path, template_cv, iw, ih)

        # Debug: Scan-Bild und Template speichern zum Vergleich. Unter den
        # Lauf-Screenshots, nicht unter `items/` — den Ordner gibt es seit dem
        # Umzug auf Besitzeinheiten nur noch als Altbestand fuer den Reset.
        if CONFIG.debug_save_templates:
            debug_dir = os.path.join(SEQUENCE_SCREENSHOTS_DIR, "debug")
            os.makedirs(debug_dir, exist_ok=True)
            # Nur der echte Dateistamm — niemals Verzeichnisteile aus der Config.
            base_name = Path(template_path).stem
            # Aktuelles Scan-Bild (was im Slot ist)
            img.save(os.path.join(debug_dir, f"{base_name}_scan.png"))
            # Template/Maske (was cv2 zum Vergleich verwendet)
            cv2.imwrite(os.path.join(debug_dir, f"{base_name}_template.png"), template_cv)

        # Traegt das Template eine Maske, wird nur ueber das Item verglichen -
        # der Hintergrund macht sonst neun Zehntel der Uebereinstimmung aus.
        mask = None
        if template_cv.ndim == 3 and template_cv.shape[2] == 4:
            mask = template_cv[:, :, 3]
            template_cv = np.ascontiguousarray(template_cv[:, :, :3])

        if mask is not None and template_cv.shape[:2] == img_cv.shape[:2]:
            max_val = _masked_confidence(img_cv, template_cv, mask)
            max_loc = (0, 0)
        else:
            # Template Matching mit TM_CCOEFF_NORMED (beste Methode für farbige Bilder)
            result = cv2.matchTemplate(img_cv, template_cv, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        # max_val ist die Konfidenz (0.0 - 1.0)
        if max_val >= min_confidence:
            # Position ist obere linke Ecke des Matches
            return (True, max_val, max_loc)
        else:
            # Bei sehr niedrigen Werten: Groessen-Mismatch als moegliche Ursache
            # melden - siehe _size_hint(), nur eine der Ursachen ist ein Fehler.
            if (report_size_mismatch and max_val < 0.3
                    and (tw != iw or th != ih)):
                key_name = (tw, th, iw, ih)
                if key_name not in _reported_sizes:
                    _reported_sizes.add(key_name)
                    logger.warning(_size_hint(template_name, tw, th, iw, ih,
                                                     max_val))
            return (False, max_val, None)

    except (ValueError, TypeError, AttributeError, cv2.error) as e:
        # cv2.error explizit fangen (z.B. Grössen-Mismatch nach Resize, leere Matrix) —
        # sonst propagiert es in den Worker und reisst die Sequenz ab. cv2 ist hier
        # garantiert verfügbar, da die Funktion oben bei not OPENCV_AVAILABLE früh
        # zurückkehrt (OPENCV_AVAILABLE-Muster).
        logger.error(f"Template Matching Fehler: {e}")
        return (False, 0.0, None)


def get_color_name(rgb: tuple) -> str:
    """Gibt einen ungefähren Farbnamen für RGB zurück."""
    r, g, b = rgb

    # Graustufen
    if abs(r - g) < 30 and abs(g - b) < 30 and abs(r - b) < 30:
        if r < 50:
            return "Schwarz"
        elif r < 120:
            return "Dunkelgrau"
        elif r < 200:
            return "Grau"
        else:
            return "Weiss"

    # Dominante Farbe bestimmen
    if r > g and r > b:
        if g > b + 50:
            return "Orange" if r > 200 else "Braun"
        elif b > g + 30:
            return "Pink/Magenta"
        else:
            return "Rot"
    elif g > r and g > b:
        if r > b + 30:
            return "Gelb/Lime"
        elif b > r + 30:
            return "Türkis/Cyan"
        else:
            return "Grün"
    elif b > r and b > g:
        if r > g + 30:
            return "Lila/Violett"
        elif g > r + 30:
            return "Türkis/Cyan"
        else:
            return "Blau"
    elif r > 200 and g > 200 and b < 100:
        return "Gelb"
    elif r > 200 and g < 100 and b > 200:
        return "Magenta"
    elif r < 100 and g > 200 and b > 200:
        return "Cyan"
    else:
        return "Gemischt"


def take_screenshot(region: tuple = None) -> Optional['Image.Image']:
    """Nimmt über das aktive Plattform-Backend einen Screenshot auf."""
    return capture_screen(region)


def take_window_screenshot(hwnd: int) -> Optional[tuple]:
    """Bildet EIN Fenster ab — auch wenn etwas davor liegt.

    Gibt `(bild, (l, t, r, b))` zurück: den Client-Bereich und dessen Lage in
    Bildschirm-Koordinaten, damit alles Weitere rechnet wie bei einem
    Desktop-Ausschnitt. `None`, wenn es nicht geht.

    BitBlt vom Desktop kopiert, was auf dem Schirm steht — also auch das
    Studio-Fenster davor. `PrintWindow` mit `PW_RENDERFULLCONTENT` lässt das
    Fenster sich selbst zeichnen; eine Garantie ist es nicht, deshalb prüft der
    Aufrufer das Ergebnis mit `is_blank()`.
    """
    return capture_window(hwnd)


def is_blank(image) -> bool:
    """Ist das Bild einfarbig? Dann hat sich das Fenster nicht gezeichnet.

    Manche Fenster liefern trotz `PW_RENDERFULLCONTENT` eine schwarze Fläche.
    Die sieht aus wie ein Ergebnis, und alles Weitere arbeitete auf Nichts.
    """
    if image is None:
        return True
    try:
        corners = image.convert("RGB").getcolors(maxcolors=4)
    except (OSError, ValueError):
        return False
    return bool(corners) and len(corners) <= 1


def take_consistent_window_screenshot(hwnd: int) -> Optional[tuple]:
    """Gemeinsame Fensteraufnahme für Editor UND laufenden Item-Scan.

    Gibt `(bild, client_rechteck, hinweis)` zurück. Zuerst PrintWindow; kann
    sich ein Spiel dort nicht zeichnen, nehmen beide Aufrufer denselben
    Desktop-Ausschnitt — dann ist der Hinweis nicht leer, weil dabei nichts vor
    dem Spielfenster liegen darf.
    """
    if not hwnd:
        return None
    direct = take_window_screenshot(hwnd)
    if direct is not None and not is_blank(direct[0]):
        return direct[0], tuple(direct[1]), ""

    rect_value = get_client_rect_by_handle(hwnd)
    if rect_value is None:
        return None
    image = take_screenshot(rect_value)
    if image is None:
        return None
    return (image, tuple(rect_value),
            " Direkte Fensteraufnahme nicht verfügbar — sichtbaren "
            "Fensterbereich verwendet; es darf nichts davor liegen.")


def analyze_screen_colors(region: tuple = None, pixel_step: int = 2) -> dict:
    """
    Analysiert die häufigsten Farben in einem Screenshot.
    Nützlich um die richtigen Farben für die Erkennung zu finden.
    """
    if not PILLOW_AVAILABLE:
        logger.error("Pillow nicht installiert!")
        return {}

    img = take_screenshot(region)
    if img is None:
        return {}

    # Farben zählen (mit Rundung auf 10er-Schritte für Gruppierung)
    color_counts = {}
    pixels = img.load()
    width, height = img.size

    for x in range(0, width, pixel_step):
        for y in range(0, height, pixel_step):
            pixel = pixels[x, y][:3]
            # Runde auf 5er-Schritte für Gruppierung
            rounded = (pixel[0] // 5 * 5, pixel[1] // 5 * 5, pixel[2] // 5 * 5)
            color_counts[rounded] = color_counts.get(rounded, 0) + 1

    return color_counts


def select_region() -> Optional[tuple]:
    """
    Lässt den Benutzer eine Region per Maus auswählen.
    Returns (x1, y1, x2, y2) oder None bei Abbruch.
    """
    print("\n  Bewege die Maus zur OBEREN LINKEN Ecke des Bereichs")
    print("  und drücke Enter...")
    try:
        safe_input()
        x1, y1 = get_cursor_pos()
        print(f"  → Obere linke Ecke: ({x1}, {y1})")

        print("\n  Bewege die Maus zur UNTEREN RECHTEN Ecke des Bereichs")
        print("  und drücke Enter...")
        safe_input()
        x2, y2 = get_cursor_pos()
        print(f"  → Untere rechte Ecke: ({x2}, {y2})")

        # Koordinaten sortieren (falls falsche Reihenfolge)
        if x1 > x2:
            x1, x2 = x2, x1
        if y1 > y2:
            y1, y2 = y2, y1

        width = x2 - x1
        height = y2 - y1

        if width < 2 or height < 2:
            print(f"\n  {err('Region zu klein!')} {width}x{height} Pixel (mindestens 2x2 nötig)")
            return None

        print(f"\n  Region: {width}x{height} Pixel ({x1},{y1}) → ({x2},{y2})")

        region = (x1, y1, x2, y2)
        return region

    except (KeyboardInterrupt, EOFError):
        print("\n  [ABBRUCH] Keine Region ausgewählt.")
        return None


def run_color_analyzer() -> None:
    """Interaktive Farbanalyse für die aktuelle Mausposition oder Region."""
    print("\n" + "=" * 60)
    print("  FARB-ANALYSATOR")
    print("=" * 60)

    if not PILLOW_AVAILABLE:
        print(f"\n{err('Pillow nicht installiert!')}")
        print("         Installieren mit: pip install pillow")
        return

    menu_options = ["Farbe unter Mauszeiger", "Region (Bereich auswählen)", "Vollbild"]
    choice = interactive_select(menu_options, title="\nWas möchtest du analysieren?")

    if choice == -1:
        return

    if choice == 0:
        # Farbe unter Mauszeiger
        print("\nBewege die Maus zur gewünschten Position und drücke Enter...")
        safe_input()
        x, y = get_cursor_pos()

        img = take_screenshot((x, y, x+1, y+1))
        if img:
            pixel = img.getpixel((0, 0))[:3]
            color_name = get_color_name(pixel)
            print(f"\n[FARBE] Position ({x}, {y})")
            print(f"        RGB: {pixel}")
            print(f"        Hex: #{pixel[0]:02x}{pixel[1]:02x}{pixel[2]:02x}")
            print(f"        Name: {color_name}")

    elif choice == 1:
        # Region analysieren
        region = select_region()
        if region:
            analyze_and_print_colors(region)

    elif choice == 2:
        # Vollbild analysieren
        analyze_and_print_colors(None)


def analyze_and_print_colors(region: tuple = None) -> None:
    """Analysiert und zeigt die häufigsten Farben."""
    print("\n[ANALYSE] Analysiere Farben...")

    color_counts = analyze_screen_colors(region)
    if not color_counts:
        print(err("Keine Farben gefunden!"))
        return

    # Top 20 häufigste Farben
    sorted_colors = sorted(color_counts.items(), key=lambda x: x[1], reverse=True)[:20]

    print("\nTop 20 häufigste Farben:")
    print("-" * 50)
    for i, (color, count) in enumerate(sorted_colors, 1):
        # Prüfen ob grün/türkis
        is_green = (color[1] > color[0] and color[1] > color[2] and color[1] > 100)
        is_teal = (color[1] > 100 and color[2] > 100 and abs(color[1] - color[2]) < 80 and color[0] < 100)

        marker = ""
        if is_green:
            marker = " ← GRÜN"
        elif is_teal:
            marker = " ← TÜRKIS"

        print(f"  {i:2}. RGB({color[0]:3}, {color[1]:3}, {color[2]:3}) - {count:5} Pixel{marker}")

    print("-" * 50)
