#!/usr/bin/env python3
"""
Slot-Tester: Debug-Tool fuer Slot-Erkennung und Farb-Analyse.

Testet die Slot-Erkennung mit:
- Screenshot der Slots
- Farberkennung mit Hintergrund-Maske (slot_color Ausschluss)
- Template Matching
- Debug-Bilder in tools/debug/ speichern

Benoetigt: pip install pillow numpy opencv-python
"""

# DPI-Awareness MUSS vor allem anderen stehen (Multi-Monitor)!
import ctypes
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import json
import sys
from pathlib import Path
from datetime import datetime

# Pfade
SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DEBUG_DIR = SCRIPT_DIR / "debug"
SLOTS_FILE = PROJECT_DIR / "slots" / "slots.json"
TEMPLATES_DIR = PROJECT_DIR / "items" / "templates"

# Debug-Ordner erstellen
DEBUG_DIR.mkdir(exist_ok=True)

# Abhaengigkeiten pruefen
try:
    from PIL import Image, ImageGrab
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

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

if not PILLOW_AVAILABLE:
    print("[FEHLER] Pillow nicht installiert!")
    print("         pip install pillow")
    sys.exit(1)

if not NUMPY_AVAILABLE:
    print("[WARNUNG] NumPy nicht installiert - eingeschraenkte Funktionen")
    print("          pip install numpy")


def take_screenshot(region: tuple = None) -> Image.Image:
    """Screenshot mit Multi-Monitor Support."""
    try:
        if region:
            full = ImageGrab.grab(all_screens=True)
            SM_XVIRTUALSCREEN = 76
            SM_YVIRTUALSCREEN = 77
            x_offset = ctypes.windll.user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
            y_offset = ctypes.windll.user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
            adjusted = (
                region[0] - x_offset,
                region[1] - y_offset,
                region[2] - x_offset,
                region[3] - y_offset
            )
            return full.crop(adjusted)
        else:
            return ImageGrab.grab(all_screens=True)
    except Exception as e:
        print(f"[FEHLER] Screenshot: {e}")
        return None


def take_screenshot_bitblt(region: tuple = None) -> Image.Image:
    """Screenshot mit BitBlt (fuer Spiele)."""
    try:
        if region:
            left, top, right, bottom = region
            width = right - left
            height = bottom - top
        else:
            left, top = 0, 0
            width = ctypes.windll.user32.GetSystemMetrics(0)
            height = ctypes.windll.user32.GetSystemMetrics(1)

        hwnd = ctypes.windll.user32.GetDesktopWindow()
        hwndDC = ctypes.windll.user32.GetWindowDC(hwnd)
        memDC = ctypes.windll.gdi32.CreateCompatibleDC(hwndDC)
        bmp = ctypes.windll.gdi32.CreateCompatibleBitmap(hwndDC, width, height)
        old_bmp = ctypes.windll.gdi32.SelectObject(memDC, bmp)

        ctypes.windll.gdi32.BitBlt(memDC, 0, 0, width, height, hwndDC, left, top, 0x00CC0020)

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ('biSize', ctypes.c_uint32), ('biWidth', ctypes.c_int32),
                ('biHeight', ctypes.c_int32), ('biPlanes', ctypes.c_uint16),
                ('biBitCount', ctypes.c_uint16), ('biCompression', ctypes.c_uint32),
                ('biSizeImage', ctypes.c_uint32), ('biXPelsPerMeter', ctypes.c_int32),
                ('biYPelsPerMeter', ctypes.c_int32), ('biClrUsed', ctypes.c_uint32),
                ('biClrImportant', ctypes.c_uint32),
            ]

        bi = BITMAPINFOHEADER()
        bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bi.biWidth = width
        bi.biHeight = -height
        bi.biPlanes = 1
        bi.biBitCount = 32
        bi.biCompression = 0

        buffer = (ctypes.c_char * (width * height * 4))()
        ctypes.windll.gdi32.GetDIBits(memDC, bmp, 0, height, buffer, ctypes.byref(bi), 0)

        ctypes.windll.gdi32.SelectObject(memDC, old_bmp)
        ctypes.windll.gdi32.DeleteObject(bmp)
        ctypes.windll.gdi32.DeleteDC(memDC)
        ctypes.windll.user32.ReleaseDC(hwnd, hwndDC)

        if not NUMPY_AVAILABLE:
            return None
        img_array = np.frombuffer(buffer, dtype=np.uint8).reshape((height, width, 4))
        img_rgb = img_array[:, :, [2, 1, 0]]
        return Image.fromarray(img_rgb)
    except Exception as e:
        print(f"[FEHLER] BitBlt: {e}")
        return None


def color_distance(c1: tuple, c2: tuple) -> float:
    """Euklidische Distanz zwischen RGB-Farben."""
    return ((c1[0]-c2[0])**2 + (c1[1]-c2[1])**2 + (c1[2]-c2[2])**2) ** 0.5


def get_color_name(rgb: tuple) -> str:
    """Gibt einen Farbnamen fuer RGB zurueck."""
    r, g, b = rgb
    if abs(r - g) < 30 and abs(g - b) < 30 and abs(r - b) < 30:
        if r < 50:
            return "Schwarz"
        elif r < 120:
            return "Dunkelgrau"
        elif r < 200:
            return "Grau"
        else:
            return "Weiss"
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
            return "Tuerkis/Cyan"
        else:
            return "Gruen"
    elif b > r and b > g:
        if r > g + 30:
            return "Lila/Violett"
        elif g > r + 30:
            return "Tuerkis/Cyan"
        else:
            return "Blau"
    return "Gemischt"


def load_slots() -> dict:
    """Laedt Slots aus slots.json."""
    if not SLOTS_FILE.exists():
        print(f"[FEHLER] {SLOTS_FILE} nicht gefunden!")
        return {}

    try:
        with open(SLOTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[FEHLER] Slots laden: {e}")
        return {}


def analyze_slot_colors(img: Image.Image, slot_color: tuple = None,
                        color_distance_threshold: int = 25) -> dict:
    """
    Analysiert Farben in einem Slot-Bild mit Hintergrund-Ausschluss.

    Returns:
        dict mit: all_colors, filtered_colors, excluded_count, mask_image
    """
    pixels = img.load()
    width, height = img.size

    # Alle Farben zaehlen (gerundet auf 5er)
    color_counts = {}
    for x in range(width):
        for y in range(height):
            pixel = pixels[x, y][:3]
            rounded = (pixel[0] // 5 * 5, pixel[1] // 5 * 5, pixel[2] // 5 * 5)
            color_counts[rounded] = color_counts.get(rounded, 0) + 1

    all_colors = sorted(color_counts.items(), key=lambda x: x[1], reverse=True)

    # Maske erstellen (wo Hintergrund ausgeschlossen wird)
    mask_img = Image.new("RGB", (width, height), (255, 255, 255))
    mask_pixels = mask_img.load()

    excluded_count = 0
    filtered_counts = dict(color_counts)

    if slot_color:
        slot_rounded = (slot_color[0] // 5 * 5, slot_color[1] // 5 * 5, slot_color[2] // 5 * 5)

        # Farben zum Ausschliessen finden
        colors_to_remove = []
        for color in color_counts.keys():
            if color_distance(color, slot_rounded) <= color_distance_threshold:
                colors_to_remove.append(color)

        # Aus filtered entfernen
        for color in colors_to_remove:
            excluded_count += filtered_counts.pop(color, 0)

        # Maske erstellen: ausgeschlossene Pixel = rot
        for x in range(width):
            for y in range(height):
                pixel = pixels[x, y][:3]
                rounded = (pixel[0] // 5 * 5, pixel[1] // 5 * 5, pixel[2] // 5 * 5)
                if rounded in colors_to_remove:
                    mask_pixels[x, y] = (255, 0, 0)  # Rot = ausgeschlossen
                else:
                    mask_pixels[x, y] = pixel  # Original behalten

    filtered_colors = sorted(filtered_counts.items(), key=lambda x: x[1], reverse=True)

    return {
        "all_colors": all_colors,
        "filtered_colors": filtered_colors,
        "excluded_count": excluded_count,
        "mask_image": mask_img
    }


def match_template(img: Image.Image, template_name: str,
                   min_confidence: float = 0.8) -> tuple:
    """Template Matching mit OpenCV."""
    if not OPENCV_AVAILABLE or not NUMPY_AVAILABLE:
        return (False, 0.0, None)

    template_path = TEMPLATES_DIR / template_name
    if not template_path.exists():
        return (False, 0.0, f"Template nicht gefunden: {template_path}")

    try:
        img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        template_cv = cv2.imdecode(
            np.fromfile(str(template_path), dtype=np.uint8),
            cv2.IMREAD_COLOR
        )

        if template_cv is None:
            return (False, 0.0, "Template konnte nicht geladen werden")

        result = cv2.matchTemplate(img_cv, template_cv, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        if max_val >= min_confidence:
            return (True, max_val, max_loc)
        else:
            return (False, max_val, None)
    except Exception as e:
        return (False, 0.0, str(e))


def test_single_slot(slot_name: str, slot_data: dict, use_bitblt: bool = False):
    """Testet einen einzelnen Slot und speichert Debug-Bilder."""
    print(f"\n{'='*50}")
    print(f"  SLOT: {slot_name}")
    print(f"{'='*50}")

    region = slot_data.get("scan_region")
    slot_color = slot_data.get("slot_color")
    if slot_color:
        slot_color = tuple(slot_color)

    print(f"  Region: {region}")
    print(f"  Slot-Farbe: {slot_color} ({get_color_name(slot_color) if slot_color else 'keine'})")

    # Screenshot
    print("\n  Screenshot...")
    if use_bitblt:
        img = take_screenshot_bitblt(tuple(region))
    else:
        img = take_screenshot(tuple(region))

    if img is None:
        print("  [FEHLER] Screenshot fehlgeschlagen!")
        return

    print(f"  -> Groesse: {img.size[0]}x{img.size[1]}")

    # Timestamp fuer Dateinamen
    ts = datetime.now().strftime("%H%M%S")
    safe_name = slot_name.replace(" ", "_").replace("/", "_")

    # Original speichern
    orig_path = DEBUG_DIR / f"{safe_name}_{ts}_original.png"
    img.save(orig_path)
    print(f"  -> Gespeichert: {orig_path.name}")

    # Farb-Analyse
    print("\n  Farb-Analyse...")
    result = analyze_slot_colors(img, slot_color)

    print(f"\n  Alle Farben (Top 10):")
    for i, (color, count) in enumerate(result["all_colors"][:10]):
        name = get_color_name(color)
        print(f"    {i+1}. RGB{color} - {name} ({count} Pixel)")

    if slot_color:
        print(f"\n  Nach Hintergrund-Ausschluss ({result['excluded_count']} Pixel entfernt):")
        for i, (color, count) in enumerate(result["filtered_colors"][:10]):
            name = get_color_name(color)
            marker = " *" if i < 5 else ""
            print(f"    {i+1}. RGB{color} - {name} ({count} Pixel){marker}")

        # Maske speichern
        mask_path = DEBUG_DIR / f"{safe_name}_{ts}_mask.png"
        result["mask_image"].save(mask_path)
        print(f"\n  -> Maske gespeichert: {mask_path.name}")
        print(f"     (Rot = ausgeschlossener Hintergrund)")


def test_all_slots(use_bitblt: bool = False):
    """Testet alle Slots."""
    slots = load_slots()
    if not slots:
        return

    print(f"\n{len(slots)} Slots gefunden.\n")

    for name, data in slots.items():
        test_single_slot(name, data, use_bitblt)

    print(f"\n{'='*50}")
    print(f"  Debug-Bilder in: {DEBUG_DIR}")
    print(f"{'='*50}")


def test_template_matching():
    """Testet Template Matching auf allen Slots."""
    if not OPENCV_AVAILABLE:
        print("[FEHLER] OpenCV nicht installiert!")
        return

    slots = load_slots()
    if not slots:
        return

    # Verfuegbare Templates auflisten
    templates = list(TEMPLATES_DIR.glob("*.png"))
    if not templates:
        print(f"[FEHLER] Keine Templates in {TEMPLATES_DIR}")
        return

    print(f"\nVerfuegbare Templates ({len(templates)}):")
    for i, t in enumerate(templates):
        print(f"  {i+1}. {t.name}")

    try:
        choice = input("\nTemplate-Nummer (oder Name): ").strip()
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(templates):
                template_name = templates[idx].name
            else:
                print("Ungueltige Nummer!")
                return
        else:
            template_name = choice if choice.endswith(".png") else f"{choice}.png"
    except ValueError:
        return

    print(f"\nTeste Template '{template_name}' auf allen Slots...")

    for name, data in slots.items():
        region = data.get("scan_region")
        img = take_screenshot(tuple(region))
        if img is None:
            continue

        found, conf, pos = match_template(img, template_name)
        status = "GEFUNDEN" if found else "nicht gefunden"
        print(f"  {name}: {status} (Konfidenz: {conf:.2%})")


def main():
    print("\n" + "=" * 60)
    print("  SLOT-TESTER - Debug-Tool")
    print("=" * 60)
    print(f"\n  Projekt: {PROJECT_DIR}")
    print(f"  Debug-Ordner: {DEBUG_DIR}")
    print(f"  Slots-Datei: {SLOTS_FILE}")

    slots = load_slots()
    print(f"  Geladene Slots: {len(slots)}")

    if not slots:
        print("\n[FEHLER] Keine Slots geladen!")
        return

    print("\nOptionen:")
    print("  [1] Alle Slots testen (ImageGrab)")
    print("  [2] Alle Slots testen (BitBlt - fuer Spiele)")
    print("  [3] Einzelnen Slot testen")
    print("  [4] Template Matching testen")
    print("  [0] Beenden")

    try:
        choice = input("\n> ").strip()

        if choice == "1":
            test_all_slots(use_bitblt=False)
        elif choice == "2":
            test_all_slots(use_bitblt=True)
        elif choice == "3":
            print("\nVerfuegbare Slots:")
            slot_names = list(slots.keys())
            for i, name in enumerate(slot_names):
                print(f"  {i+1}. {name}")

            idx = int(input("\nSlot-Nummer: ").strip()) - 1
            if 0 <= idx < len(slot_names):
                name = slot_names[idx]
                use_bb = input("BitBlt verwenden? (j/n): ").strip().lower() == "j"
                test_single_slot(name, slots[name], use_bb)
        elif choice == "4":
            test_template_matching()
        elif choice == "0":
            return
        else:
            print("Ungueltige Option!")

    except (KeyboardInterrupt, EOFError):
        print("\n[ABBRUCH]")
    except Exception as e:
        print(f"\n[FEHLER] {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[ABBRUCH]")

    input("\nENTER zum Beenden...")
