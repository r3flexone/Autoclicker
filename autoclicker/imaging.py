"""
Bildverarbeitung und Farberkennung für den Autoclicker.
Screenshots, Farbanalyse, Template-Matching.
"""

import ctypes
import ctypes.wintypes as wintypes
import logging
import os
from typing import Optional, TYPE_CHECKING

from .config import CONFIG, DEFAULT_MIN_CONFIDENCE
from .utils import safe_input, interactive_select, err
from .winapi import get_cursor_pos

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

if TYPE_CHECKING:
    from PIL import Image

# Logger
logger = logging.getLogger("autoclicker")

# Verzeichnisse (importiert aus persistence um Duplizierung zu vermeiden)
from .persistence import ITEMS_DIR, TEMPLATES_DIR

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


def find_color_in_image(img: 'Image.Image', target_color: tuple, tolerance: float, pixel_step: int = 2) -> bool:
    """
    Prüft ob eine Farbe im Bild vorhanden ist (optimiert mit NumPy wenn verfügbar).

    Args:
        img: PIL Image
        target_color: RGB-Tuple (r, g, b)
        tolerance: Maximale Farbdistanz
        pixel_step: Schrittweite beim Scannen (1=genau, 2=schneller)

    Returns:
        True wenn Farbe gefunden, sonst False
    """
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
            return bool(np.any(sq_distances <= tolerance * tolerance))
        return False
    else:
        # Fallback: Langsame PIL-Version
        pixels = img.load()
        width, height = img.size
        for x in range(0, width, pixel_step):
            for y in range(0, height, pixel_step):
                pixel = pixels[x, y][:3]
                if color_distance(pixel, target_color) <= tolerance:
                    return True
        return False


def match_template_in_image(img: 'Image.Image', template_name: str, min_confidence: float = DEFAULT_MIN_CONFIDENCE) -> tuple:
    """
    Sucht ein Template-Bild im gegebenen Bild mittels OpenCV Template Matching.

    Args:
        img: PIL Image (Suchbereich)
        template_name: Dateiname des Templates (in items/templates/)
        min_confidence: Mindest-Konfidenz für Match (0.0-1.0)

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

    # Template-Pfad erstellen
    template_path = os.path.join(TEMPLATES_DIR, template_name)
    if not os.path.exists(template_path):
        logger.error(f"Template nicht gefunden: {template_path}")
        return (False, 0.0, None)

    try:
        # PIL-Bild zu OpenCV-Format konvertieren (RGB -> BGR)
        img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

        # Template laden (mit Unicode-Pfad-Unterstützung für Windows)
        # cv2.imread hat Probleme mit Umlauten (ü, ä, ö) - daher imdecode verwenden
        template_cv = cv2.imdecode(np.fromfile(template_path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if template_cv is None:
            logger.error(f"Konnte Template nicht laden: {template_path}")
            return (False, 0.0, None)

        # Größenvergleich: Template muss zum Scan-Bild passen
        th, tw = template_cv.shape[:2]
        ih, iw = img_cv.shape[:2]

        if tw != iw or th != ih:
            # Größen-Diskrepanz! Template an Scan-Bildgröße anpassen
            # Passiert wenn Slot-Regionen nach Template-Erstellung geändert wurden
            # (z.B. neue Auto-Erkennung, Monitor-Wechsel, DPI-Änderung)
            if tw > 0 and th > 0:
                logger.debug(f"Template '{template_name}' Größe {tw}x{th} != Scan {iw}x{ih} - resize")
                template_cv = cv2.resize(template_cv, (iw, ih), interpolation=cv2.INTER_AREA)

        # Debug: Scan-Bild und Template speichern zum Vergleich
        if CONFIG.debug_save_templates:
            debug_dir = os.path.join(ITEMS_DIR, "debug")
            os.makedirs(debug_dir, exist_ok=True)
            # Basis-Name aus Template (ohne .png)
            base_name = os.path.splitext(template_name)[0]
            # Aktuelles Scan-Bild (was im Slot ist)
            img.save(os.path.join(debug_dir, f"{base_name}_scan.png"))
            # Template/Maske (was cv2 zum Vergleich verwendet)
            cv2.imwrite(os.path.join(debug_dir, f"{base_name}_template.png"), template_cv)

        # Template Matching mit TM_CCOEFF_NORMED (beste Methode für farbige Bilder)
        result = cv2.matchTemplate(img_cv, template_cv, cv2.TM_CCOEFF_NORMED)

        # Bestes Match finden
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        # max_val ist die Konfidenz (0.0 - 1.0)
        if max_val >= min_confidence:
            # Position ist obere linke Ecke des Matches
            return (True, max_val, max_loc)
        else:
            # Bei sehr niedrigen Werten: Größen-Mismatch als mögliche Ursache loggen
            if max_val < 0.3 and (tw != iw or th != ih):
                logger.debug(
                    f"Template '{template_name}': {max_val:.1%} - "
                    f"Größen-Mismatch (Template {tw}x{th}, Scan {iw}x{ih}) könnte Ursache sein. "
                    f"Templates neu erstellen empfohlen."
                )
            return (False, max_val, None)

    except (ValueError, TypeError, AttributeError) as e:
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
            return "Weiß"

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
            SM_XVIRTUALSCREEN = 76
            SM_YVIRTUALSCREEN = 77
            x_offset = ctypes.windll.user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
            y_offset = ctypes.windll.user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
            adjusted_region = (
                region[0] - x_offset,
                region[1] - y_offset,
                region[2] - x_offset,
                region[3] - y_offset
            )
            # Bounds-Check: Region muss positive Größe haben
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
        # Virtual Screen Metriken für Multi-Monitor-Support
        SM_XVIRTUALSCREEN = 76   # Linke Kante des virtuellen Desktops
        SM_YVIRTUALSCREEN = 77   # Obere Kante des virtuellen Desktops
        SM_CXVIRTUALSCREEN = 78  # Breite des virtuellen Desktops
        SM_CYVIRTUALSCREEN = 79  # Höhe des virtuellen Desktops

        virtual_left = _user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        virtual_top = _user32.GetSystemMetrics(SM_YVIRTUALSCREEN)

        if region:
            left, top, right, bottom = region
            width = right - left
            height = bottom - top
            if width <= 0 or height <= 0:
                return None
        else:
            # Vollbild: gesamter virtueller Desktop (alle Monitore)
            left = virtual_left
            top = virtual_top
            width = _user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
            height = _user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)

        # Device Contexts - GetWindowDC(GetDesktopWindow()) liefert DC für gesamten virtuellen Desktop
        hwnd = _user32.GetDesktopWindow()
        hwndDC = _user32.GetWindowDC(hwnd)
        memDC = _gdi32.CreateCompatibleDC(hwndDC)
        bmp = _gdi32.CreateCompatibleBitmap(hwndDC, width, height)
        old_bmp = _gdi32.SelectObject(memDC, bmp)

        # BitBlt - Koordinaten funktionieren auch negativ (linker Monitor)
        _gdi32.BitBlt(memDC, 0, 0, width, height, hwndDC, left, top, 0x00CC0020)

        # Bitmap-Daten auslesen
        bi = BITMAPINFOHEADER()
        bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bi.biWidth = width
        bi.biHeight = -height
        bi.biPlanes = 1
        bi.biBitCount = 32
        bi.biCompression = 0

        buffer = (ctypes.c_char * (width * height * 4))()
        _gdi32.GetDIBits(memDC, bmp, 0, height, buffer, ctypes.byref(bi), 0)

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
