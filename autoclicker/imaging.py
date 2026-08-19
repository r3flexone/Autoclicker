"""
Bildverarbeitung und Farberkennung für den Autoclicker.
Screenshots, Farbanalyse, Template-Matching.
"""

import ctypes
import ctypes.wintypes as wintypes
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
    get_client_rect_by_handle, get_cursor_pos, get_virtual_desktop,
    get_virtual_origin,
)

# GDI32 Funktions-Deklarationen (restype nötig um Handle-Trunkierung auf 64-bit zu vermeiden)
_gdi32 = ctypes.windll.gdi32
_user32 = ctypes.windll.user32

_user32.GetDesktopWindow.restype = wintypes.HWND
_user32.GetWindowDC.argtypes = [wintypes.HWND]
_user32.GetWindowDC.restype = wintypes.HDC
_user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
_user32.ReleaseDC.restype = ctypes.c_int

_gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
_gdi32.CreateCompatibleDC.restype = wintypes.HDC
_gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
_gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
_gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
_gdi32.SelectObject.restype = wintypes.HGDIOBJ
_gdi32.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                           wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD]
_gdi32.BitBlt.restype = wintypes.BOOL
_gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                              ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
_gdi32.GetDIBits.restype = ctypes.c_int
_gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
_gdi32.DeleteObject.restype = wintypes.BOOL
_gdi32.DeleteDC.argtypes = [wintypes.HDC]
_gdi32.DeleteDC.restype = wintypes.BOOL

_user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
_user32.PrintWindow.restype = wintypes.BOOL
_user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.GetWindowRect.restype = wintypes.BOOL
_user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.GetClientRect.restype = wintypes.BOOL
_user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
_user32.ClientToScreen.restype = wintypes.BOOL

# BitBlt-Rasteroperation: Quelle 1:1 kopieren (Windows GDI SRCCOPY).
SRCCOPY = 0x00CC0020

# PrintWindow: das ganze Fenster zeichnen lassen, samt GPU-beschleunigtem
# Inhalt. Ohne dieses Flag (ab Windows 8.1) bleiben Browser und viele Spiele
# leer — dann waere die ganze Funktion nutzlos für den Fall, für den es sie gibt.
PW_RENDERFULLCONTENT = 0x00000002

# BITMAPINFOHEADER für Screenshots (einmal definiert, wiederverwendbar)
class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ('biSize', ctypes.c_uint32), ('biWidth', ctypes.c_int32),
        ('biHeight', ctypes.c_int32), ('biPlanes', ctypes.c_uint16),
        ('biBitCount', ctypes.c_uint16), ('biCompression', ctypes.c_uint32),
        ('biSizeImage', ctypes.c_uint32), ('biXPelsPerMeter', ctypes.c_int32),
        ('biYPelsPerMeter', ctypes.c_int32), ('biClrUsed', ctypes.c_uint32),
        ('biClrImportant', ctypes.c_uint32),
    ]

# Logger
logger = logging.getLogger("autoclicker")

# Verzeichnisse (importiert aus persistence um Duplizierung zu vermeiden)
from .persistence import ITEMS_DIR, TEMPLATES_DIR


def _template_path(template_name: str) -> str | None:
    """Löst einen Template-Namen sicher innerhalb von ``TEMPLATES_DIR`` auf.

    Scan-Dateien sind normale JSON-Dateien und können auch von Hand verändert
    werden. Absolute Pfade und ``..`` dürfen den Template-Ordner deshalb niemals
    verlassen.
    """
    if not isinstance(template_name, str) or not template_name.strip():
        return None
    relative = Path(template_name)
    if relative.is_absolute():
        return None
    root = Path(TEMPLATES_DIR).resolve()
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
    from PIL import Image, ImageGrab
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
    try:
        img = ImageGrab.grab(bbox=(x, y, x + 1, y + 1), all_screens=True)
        if img:
            return img.getpixel((0, 0))[:3]
    except (OSError, ValueError):
        pass  # Screenshot fehlgeschlagen
    return None


def color_distance(c1: tuple, c2: tuple) -> float:
    """Berechnet die Distanz zwischen zwei RGB-Farben."""
    return ((c1[0]-c2[0])**2 + (c1[1]-c2[1])**2 + (c1[2]-c2[2])**2) ** 0.5


def find_color_in_image(img: 'Image.Image', target_color: tuple, tolerance: float,
                        pixel_step: int = 2, min_pixels: int = 1) -> bool:
    """
    Prüft ob eine Farbe im Bild vorhanden ist (optimiert mit NumPy wenn verfügbar).

    Args:
        img: PIL Image
        target_color: RGB-Tuple (r, g, b)
        tolerance: Maximale Farbdistanz
        pixel_step: Schrittweite beim Scannen (1=genau, 2=schneller)
        min_pixels: Mindestanzahl passender (abgetasteter) Pixel, damit als
            gefunden gilt. 1 = altes Verhalten (ein Pixel reicht). Werte > 1
            machen die Erkennung robuster gegen einzelne Rausch-Pixel — der
            Schwellwert bezieht sich auf das durch pixel_step abgetastete Raster.

    Returns:
        True wenn mindestens min_pixels passende Pixel gefunden, sonst False
    """
    min_pixels = max(1, min_pixels)
    if NUMPY_AVAILABLE:
        # Schnelle NumPy-Version (ca. 100x schneller)
        # asarray vermeidet Kopie wenn PIL-Daten bereits im richtigen Format
        img_array = np.asarray(img)
        if len(img_array.shape) == 3 and img_array.shape[2] >= 3:
            # Nur RGB-Kanäle verwenden, mit pixel_step für Performance
            rgb = img_array[::pixel_step, ::pixel_step, :3].astype(np.float32)
            target = np.array(target_color, dtype=np.float32)
            # Quadrierte Distanz vergleichen (vermeidet teure sqrt-Berechnung)
            sq_distances = np.sum((rgb - target) ** 2, axis=2)
            matches = int(np.count_nonzero(sq_distances <= tolerance * tolerance))
            return matches >= min_pixels
        return False
    else:
        # Fallback: Langsame PIL-Version
        pixels = img.load()
        width, height = img.size
        matches = 0
        for x in range(0, width, pixel_step):
            for y in range(0, height, pixel_step):
                pixel = pixels[x, y][:3]
                if color_distance(pixel, target_color) <= tolerance:
                    matches += 1
                    if matches >= min_pixels:
                        return True
        return False


# =============================================================================
# TEMPLATE-CACHE
# =============================================================================
# Ein Template wurde bisher bei JEDEM Vergleich neu von Platte gelesen und dekodiert -
# also pro Item x pro Slot x pro Scan-Schritt, in jedem Zyklus, fuer Bytes die sich nie
# aendern. Bei 20 Items und 5 Slots sind das 100 Dateizugriffe je Scan.
#
# Der Cache haelt das dekodierte Bild und die auf eine Slot-Groesse angepasste Variante.
# Schluessel ist (mtime, size) der Datei: wird ein Template neu gelernt oder ueberschrieben,
# faellt der Eintrag von selbst raus - kein manuelles Invalidieren, kein Neustart noetig.
#
# Ohne Lock: Dict-Zugriffe sind unter dem GIL atomar. Schlimmstenfalls dekodieren zwei
# Threads (Worker + Async-Boss) dasselbe Bild doppelt - das kostet nichts und geht nicht
# kaputt. Ein Lock waere hier teurer als der Schaden.
_template_cache: dict = {}
_TEMPLATE_CACHE_MAX = 256

# Schon gemeldete Groessen-Konflikte. Der Schluessel ist die GROESSENPAARUNG
# (Template gegen Slot), nicht das einzelne Template - sonst steht die Meldung
# einmal pro Item da, und das sind bei zwei Inventaren im Bestand zwei Dutzend
# Zeilen mit derselben Aussage. Genau der Fall, gegen den die Sperre gedacht war:
# eine Konsole voll gleichlautender Warnungen liest niemand mehr.
_gemeldete_groessen: set = set()


def _load_template(template_path: str):
    """Lädt ein Template-Bild (BGR) aus dem Cache oder von Platte. None wenn nicht da.

    Unicode-Pfade: cv2.imread scheitert an Umlauten, deshalb fromfile + imdecode.
    """
    try:
        st = os.stat(template_path)
    except OSError:
        logger.error(f"Template nicht gefunden: {template_path}")
        return None

    stand = (st.st_mtime, st.st_size)
    eintrag = _template_cache.get(template_path)
    if eintrag is not None and eintrag["stand"] == stand:
        return eintrag["bild"]

    # UNCHANGED statt COLOR: ein Template mit Alpha-Kanal traegt darin seine
    # Maske. Ohne das faellt sie beim Laden weg und niemand merkt es.
    bild = cv2.imdecode(np.fromfile(template_path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if bild is not None and bild.ndim == 2:
        bild = cv2.cvtColor(bild, cv2.COLOR_GRAY2BGR)
    if bild is None:
        logger.error(f"Konnte Template nicht laden: {template_path}")
        return None

    if len(_template_cache) >= _TEMPLATE_CACHE_MAX:
        _template_cache.clear()
    _template_cache[template_path] = {"stand": stand, "bild": bild, "skaliert": {}}
    return bild


def mit_hintergrund_maske(img: 'Image.Image', hintergrund) -> 'Image.Image':
    """Legt einen Alpha-Kanal an: Hintergrund durchsichtig, Item deckend.

    **Das Template besteht sonst zu neun Zehnteln aus Hintergrund.** Gemessen an
    einem echten Bestand: von 62×60 Pixeln eines Slots sind 10–40 % das Item, der
    Rest ist die immer gleiche Slot-Fläche. Ein Bildvergleich über das ganze
    Rechteck stimmt damit hauptsächlich darüber ab, dass beide denselben
    Hintergrund haben — und nur zu einem Zehntel darüber, ob es dasselbe Item ist.

    **Die Maske merkt sich Stellen, nicht Farben.** Das ist der Grund, warum sie
    auch dann trägt, wenn dasselbe Item später vor einem anders gefärbten Menü
    steht: verglichen werden nur die Pixel, an denen beim Lernen das Item sass.
    Welche Farbe der Hintergrund dort *heute* hat, geht in die Rechnung gar nicht
    mehr ein.

    Sie steckt IM Template-PNG (Alpha-Kanal), nicht in einer Datei daneben — zwei
    Dateien, die zusammengehören, laufen irgendwann auseinander. Dieselbe
    Entscheidung wie beim Ursprung im Screenshot-PNG.
    """
    if img is None or not hintergrund:
        return img
    grenze = CONFIG.scan_slot_color_distance
    rgb = img.convert("RGB")
    breite, hoehe = rgb.size
    pixel = rgb.load()
    maske = Image.new("L", (breite, hoehe))
    mp = maske.load()
    hr, hg, hb = hintergrund[:3]
    for y in range(hoehe):
        for x in range(breite):
            r, g, b = pixel[x, y]
            if ((r - hr) ** 2 + (g - hg) ** 2 + (b - hb) ** 2) ** 0.5 <= grenze:
                mp[x, y] = 0
            else:
                mp[x, y] = 255
    ergebnis = rgb.convert("RGBA")
    ergebnis.putalpha(maske)
    return ergebnis


def _konfidenz_maskiert(bild, template, maske) -> float:
    """TM_CCOEFF_NORMED, aber nur über die Pixel, die das Item ausmachen.

    **Warum von Hand und nicht `cv2.matchTemplate(..., mask=)`:** mit Maske kann
    OpenCV nur `TM_SQDIFF` und `TM_CCORR_NORMED`, und deren Zahlen bedeuten etwas
    anderes als die bisherige. `min_confidence` steht an jedem Item auf einem
    Wert, der für CCOEFF gedacht ist — ein Methodenwechsel würde jede gespeicherte
    Schwelle still verschieben, und niemand wüsste, warum plötzlich alles oder
    nichts passt.

    Template und Ausschnitt sind hier immer gleich gross (`_template_in_groesse`
    sorgt dafür), also ist das Ganze genau eine Korrelation und keine Suche.
    """
    wahl = maske > 127
    if int(wahl.sum()) < 16:
        # Fast alles wegmaskiert — dann sagt die Rechnung nichts mehr aus.
        return 0.0
    a = template[wahl].astype(np.float64).ravel()
    b = bild[wahl].astype(np.float64).ravel()
    a -= a.mean()
    b -= b.mean()
    nenner = float(np.sqrt(float((a * a).sum()) * float((b * b).sum())))
    return float((a * b).sum() / nenner) if nenner > 0 else 0.0


def _template_in_groesse(template_path: str, bild, breite: int, hoehe: int):
    """Gibt das Template in der gewünschten Grösse zurück (skaliert + gemerkt).

    Die Grössen-Anpassung greift, wenn eine Slot-Region nach dem Erstellen des Templates
    geändert wurde. Sie ist pro Slot-Grösse immer dieselbe Rechnung — also einmal.
    """
    if bild.shape[1] == breite and bild.shape[0] == hoehe:
        return bild
    eintrag = _template_cache.get(template_path)
    schluessel = (breite, hoehe)
    if eintrag is not None:
        fertig = eintrag["skaliert"].get(schluessel)
        if fertig is not None:
            return fertig
    skaliert = cv2.resize(bild, (breite, hoehe), interpolation=cv2.INTER_AREA)
    if eintrag is not None:
        eintrag["skaliert"][schluessel] = skaliert
    return skaliert


def template_size(template_name: str) -> tuple[int, int] | None:
    """Pixelgroesse einer gespeicherten Vorlage, oder ``None`` wenn unlesbar."""
    template_path = _template_path(template_name)
    if template_path is None:
        return None
    template_cv = _load_template(template_path)
    if template_cv is None:
        return None
    return (int(template_cv.shape[1]), int(template_cv.shape[0]))


def match_template_in_image(img: 'Image.Image', template_name: str,
                            min_confidence: float = DEFAULT_MIN_CONFIDENCE,
                            *, resize_template: bool = True,
                            report_size_mismatch: bool = True) -> tuple:
    """
    Sucht ein Template-Bild im gegebenen Bild mittels OpenCV Template Matching.

    Args:
        img: PIL Image (Suchbereich)
        template_name: Dateiname des Templates (in items/templates/)
        min_confidence: Mindest-Konfidenz für Match (0.0-1.0)
        resize_template: Vorlage an eine abweichende Bildgroesse anpassen. Item-
            Scans setzen dies aus und verwenden stattdessen eine passende Variante.
        report_size_mismatch: Diagnose fuer alte Aufrufer ausgeben. Bewusste
            Varianten-/Duplikatpruefungen setzen dies aus.

    Returns:
        (match_found: bool, confidence: float, position: tuple or None)
        position ist (x, y) relativ zum Suchbereich
    """
    if not OPENCV_AVAILABLE:
        logger.warning("OpenCV nicht verfügbar für Template Matching")
        return (False, 0.0, None)

    if not NUMPY_AVAILABLE:
        logger.warning("NumPy nicht verfügbar für Template Matching")
        return (False, 0.0, None)

    template_path = _template_path(template_name)
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
            template_cv = _template_in_groesse(template_path, template_cv, iw, ih)

        # Debug: Scan-Bild und Template speichern zum Vergleich
        if CONFIG.debug_save_templates:
            debug_dir = os.path.join(ITEMS_DIR, "debug")
            os.makedirs(debug_dir, exist_ok=True)
            # Nur der echte Dateistamm — niemals Verzeichnisteile aus der Config.
            base_name = Path(template_path).stem
            # Aktuelles Scan-Bild (was im Slot ist)
            img.save(os.path.join(debug_dir, f"{base_name}_scan.png"))
            # Template/Maske (was cv2 zum Vergleich verwendet)
            cv2.imwrite(os.path.join(debug_dir, f"{base_name}_template.png"), template_cv)

        # Traegt das Template eine Maske, wird nur ueber das Item verglichen -
        # der Hintergrund macht sonst neun Zehntel der Uebereinstimmung aus.
        maske = None
        if template_cv.ndim == 3 and template_cv.shape[2] == 4:
            maske = template_cv[:, :, 3]
            template_cv = np.ascontiguousarray(template_cv[:, :, :3])

        if maske is not None and template_cv.shape[:2] == img_cv.shape[:2]:
            max_val = _konfidenz_maskiert(img_cv, template_cv, maske)
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
            # Bei sehr niedrigen Werten: Grössen-Mismatch als mögliche Ursache loggen.
            # **Zwei Ursachen, und nur eine ist ein Fehler.** Entweder gehört das
            # Item zu einem anderen Inventar (dessen Slots eine andere Grösse haben)
            # — dann ist der Fehlschlag genau richtig, und ein neu aufgenommenes
            # Template würde nichts verbessern. Oder die Slot-Region hat sich
            # wirklich verschoben. Die Meldung nannte nur die zweite und schickte
            # den Leser damit auf die falsche Fährte.
            if (report_size_mismatch and max_val < 0.3
                    and (tw != iw or th != ih)):
                schluessel = (tw, th, iw, ih)
                if schluessel not in _gemeldete_groessen:
                    _gemeldete_groessen.add(schluessel)
                    logger.warning(
                        f"Template '{template_name}' passt nicht zur Scan-Region: "
                        f"Template {tw}x{th}, Slot {iw}x{ih} — nur {max_val:.0%} Übereinstimmung. "
                        "Gehört das Item zu einem anderen Inventar, ist das in Ordnung; "
                        "sonst hat sich die Slot-Region geändert (Template neu aufnehmen). "
                        "Weitere Templates dieser Grössenpaarung werden nicht mehr gemeldet."
                    )
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
    """
    Nimmt einen Screenshot auf. region=(x1, y1, x2, y2) oder None für Vollbild.
    Verwendet BitBlt (schneller, besser für Spiele) mit ImageGrab-Fallback.
    Unterstützt mehrere Monitore (auch negative Koordinaten für linke Monitore).
    """
    # Versuche BitBlt (schneller, besser für DirectX-Spiele)
    img = take_screenshot_bitblt(region)
    if img is not None:
        return img

    # Fallback auf ImageGrab (falls BitBlt fehlschlägt, z.B. kein NumPy)
    if not PILLOW_AVAILABLE:
        return None
    try:
        if region:
            # Bei Region: Erst alle Screens erfassen, dann zuschneiden
            full_screenshot = ImageGrab.grab(all_screens=True)
            x_offset, y_offset = get_virtual_origin()
            adjusted_region = (
                region[0] - x_offset,
                region[1] - y_offset,
                region[2] - x_offset,
                region[3] - y_offset
            )
            # Bounds-Check: Region muss positive Grösse haben
            if adjusted_region[2] <= adjusted_region[0] or adjusted_region[3] <= adjusted_region[1]:
                logger.error(f"Ungültige Region nach Offset-Anpassung: {adjusted_region}")
                return None
            return full_screenshot.crop(adjusted_region)
        else:
            return ImageGrab.grab(all_screens=True)
    except (OSError, ValueError) as e:
        logger.error(f"Screenshot fehlgeschlagen: {e}")
        return None


def take_screenshot_bitblt(region: tuple = None) -> Optional['Image.Image']:
    """
    Screenshot mit BitBlt (Windows API) - funktioniert besser mit Spielen!
    Unterstützt Multi-Monitor (auch negative Koordinaten für linke Monitore).
    Returns: PIL Image oder None
    """
    if not PILLOW_AVAILABLE or not NUMPY_AVAILABLE:
        return None

    hwnd = None
    hwndDC = None
    memDC = None
    bmp = None
    old_bmp = None
    try:
        # Multi-Monitor: Ursprung des virtuellen Desktops (kann negativ sein)
        virtual_left, virtual_top = get_virtual_origin()

        if region:
            left, top, right, bottom = region
            width = right - left
            height = bottom - top
            if width <= 0 or height <= 0:
                return None
        else:
            # Vollbild: gesamter virtueller Desktop (alle Monitore)
            rect = get_virtual_desktop()
            if rect is None:
                return None
            left, top = rect[0], rect[1]
            width, height = rect[2] - rect[0], rect[3] - rect[1]

        # Device Contexts - GetWindowDC(GetDesktopWindow()) liefert DC für gesamten virtuellen Desktop
        hwnd = _user32.GetDesktopWindow()
        hwndDC = _user32.GetWindowDC(hwnd)
        memDC = _gdi32.CreateCompatibleDC(hwndDC)
        bmp = _gdi32.CreateCompatibleBitmap(hwndDC, width, height)
        old_bmp = _gdi32.SelectObject(memDC, bmp)

        # BitBlt - Koordinaten funktionieren auch negativ (linker Monitor).
        # Rückgabe prüfen: bei gesperrtem Desktop / Secure-Screen schlägt BitBlt fehl.
        # Dann None zurückgeben, damit der ImageGrab-Fallback greift (statt einem
        # schwarzen Bild, das die Erkennung still verfälscht).
        if not _gdi32.BitBlt(memDC, 0, 0, width, height, hwndDC, left, top, SRCCOPY):
            logger.error("BitBlt fehlgeschlagen (Desktop gesperrt?) - Fallback auf ImageGrab")
            return None

        # Bitmap-Daten auslesen
        bi = BITMAPINFOHEADER()
        bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bi.biWidth = width
        bi.biHeight = -height
        bi.biPlanes = 1
        bi.biBitCount = 32
        bi.biCompression = 0

        buffer = (ctypes.c_char * (width * height * 4))()
        # GetDIBits gibt die Anzahl kopierter Scanlines zurück (0 = Fehler).
        if _gdi32.GetDIBits(memDC, bmp, 0, height, buffer, ctypes.byref(bi), 0) == 0:
            logger.error("GetDIBits fehlgeschlagen - Fallback auf ImageGrab")
            return None

        # In PIL Image konvertieren
        img_array = np.frombuffer(buffer, dtype=np.uint8).reshape((height, width, 4))
        # BGRA -> RGB
        img_rgb = img_array[:, :, [2, 1, 0]]
        return Image.fromarray(img_rgb)
    except (OSError, ValueError, AttributeError) as e:
        logger.error(f"BitBlt Screenshot fehlgeschlagen: {e}")
        return None
    finally:
        # GDI-Resourcen IMMER freigeben (jeder Schritt einzeln abgesichert)
        try:
            if old_bmp and memDC:
                _gdi32.SelectObject(memDC, old_bmp)
        except OSError:
            pass
        try:
            if bmp:
                _gdi32.DeleteObject(bmp)
        except OSError:
            pass
        try:
            if memDC:
                _gdi32.DeleteDC(memDC)
        except OSError:
            pass
        try:
            if hwndDC and hwnd:
                _user32.ReleaseDC(hwnd, hwndDC)
        except OSError:
            pass


def take_window_screenshot(hwnd: int) -> Optional[tuple]:
    """Bildet EIN Fenster ab — auch wenn etwas davor liegt.

    Gibt `(bild, (l, t, r, b))` zurück: den **Client-Bereich** (Inhalt ohne
    Titelleiste und Rahmen) und dessen Lage in Bildschirm-Koordinaten, damit
    alles Weitere rechnet wie bei einem Ausschnitt vom Desktop. `None`, wenn es
    nicht geht.

    **Warum nicht BitBlt vom Desktop:** das kopiert, was auf dem Schirm zu sehen
    ist — also auch das Studio-Fenster, das davor liegt. Genau der Fall, den man
    hier nicht will. `PrintWindow` fordert das Fenster stattdessen auf, sich
    selbst zu zeichnen; ob es dabei sichtbar ist, spielt keine Rolle.

    `PW_RENDERFULLCONTENT` (0x2, ab Windows 8.1) ist der Teil, auf den es
    ankommt: ohne dieses Flag liefern Fenster mit GPU-beschleunigtem Inhalt
    (Browser, viele Spiele) ein leeres Rechteck. Eine Garantie ist es trotzdem
    nicht — manche Vollbild-Spiele geben weiterhin Schwarz zurück. Deshalb prüft
    der Aufrufer das Ergebnis und fällt notfalls auf den Desktop zurück; ein
    schwarzes Bild wäre schlimmer als ein verdecktes, weil es aussieht, als
    hätte es geklappt.
    """
    if not PILLOW_AVAILABLE or not NUMPY_AVAILABLE or not hwnd:
        return None

    hwndDC = None
    memDC = None
    bmp = None
    old_bmp = None
    try:
        fenster = wintypes.RECT()
        client = wintypes.RECT()
        if not _user32.GetWindowRect(hwnd, ctypes.byref(fenster)):
            return None
        if not _user32.GetClientRect(hwnd, ctypes.byref(client)):
            return None
        ecke = wintypes.POINT(0, 0)
        if not _user32.ClientToScreen(hwnd, ctypes.byref(ecke)):
            return None
        breite = fenster.right - fenster.left
        hoehe = fenster.bottom - fenster.top
        cb = client.right - client.left
        ch = client.bottom - client.top
        if breite <= 0 or hoehe <= 0 or cb <= 0 or ch <= 0:
            return None

        hwndDC = _user32.GetWindowDC(hwnd)
        memDC = _gdi32.CreateCompatibleDC(hwndDC)
        bmp = _gdi32.CreateCompatibleBitmap(hwndDC, breite, hoehe)
        old_bmp = _gdi32.SelectObject(memDC, bmp)

        if not _user32.PrintWindow(hwnd, memDC, PW_RENDERFULLCONTENT):
            logger.error("PrintWindow fehlgeschlagen")
            return None

        bi = BITMAPINFOHEADER()
        bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bi.biWidth = breite
        bi.biHeight = -hoehe
        bi.biPlanes = 1
        bi.biBitCount = 32
        bi.biCompression = 0
        puffer = (ctypes.c_char * (breite * hoehe * 4))()
        if _gdi32.GetDIBits(memDC, bmp, 0, hoehe, puffer, ctypes.byref(bi), 0) == 0:
            logger.error("GetDIBits fehlgeschlagen (Fensterbild)")
            return None

        roh = np.frombuffer(puffer, dtype=np.uint8).reshape((hoehe, breite, 4))
        bild = Image.fromarray(roh[:, :, [2, 1, 0]])
        # Aus dem GANZEN Fenster den Client-Bereich schneiden: PrintWindow malt
        # Rahmen und Titelleiste mit, und die gehören nicht zum Spielfeld.
        dx = ecke.x - fenster.left
        dy = ecke.y - fenster.top
        bild = bild.crop((dx, dy, dx + cb, dy + ch))
        return bild, (ecke.x, ecke.y, ecke.x + cb, ecke.y + ch)
    except (OSError, ValueError, AttributeError) as e:
        logger.error(f"Fenster-Screenshot fehlgeschlagen: {e}")
        return None
    finally:
        try:
            if old_bmp and memDC:
                _gdi32.SelectObject(memDC, old_bmp)
        except OSError:
            pass
        try:
            if bmp:
                _gdi32.DeleteObject(bmp)
        except OSError:
            pass
        try:
            if memDC:
                _gdi32.DeleteDC(memDC)
        except OSError:
            pass
        try:
            if hwndDC:
                _user32.ReleaseDC(hwnd, hwndDC)
        except OSError:
            pass


def ist_leer(bild) -> bool:
    """Ist das Bild einfarbig? Dann hat sich das Fenster nicht gezeichnet.

    Der Prüfstein hinter `take_window_screenshot`: manche Fenster liefern trotz
    `PW_RENDERFULLCONTENT` eine schwarze Fläche. Die sieht aus wie ein Ergebnis,
    ist aber keines — und alles Weitere (Slots finden, Farbe messen) arbeitete
    dann auf Nichts, ohne dass es jemand merkt.
    """
    if bild is None:
        return True
    try:
        ecken = bild.convert("RGB").getcolors(maxcolors=4)
    except (OSError, ValueError):
        return False
    return bool(ecken) and len(ecken) <= 1


def take_consistent_window_screenshot(hwnd: int) -> Optional[tuple]:
    """Gemeinsame Fensteraufnahme für Editor UND laufenden Item-Scan.

    Ergebnis: ``(bild, client_rechteck, hinweis)``. Zuerst wird das Fenster
    direkt über PrintWindow aufgenommen. Kann sich ein Spiel dort nicht
    zeichnen, verwenden beide Aufrufer denselben sichtbaren Desktop-Ausschnitt.
    Der Hinweis ist dann nicht leer, weil bei diesem Fallback nichts vor dem
    Spielfenster liegen darf.
    """
    if not hwnd:
        return None
    direkt = take_window_screenshot(hwnd)
    if direkt is not None and not ist_leer(direkt[0]):
        return direkt[0], tuple(direkt[1]), ""

    rechteck = get_client_rect_by_handle(hwnd)
    if rechteck is None:
        return None
    bild = take_screenshot(rechteck)
    if bild is None:
        return None
    return (bild, tuple(rechteck),
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
