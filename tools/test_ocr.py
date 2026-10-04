#!/usr/bin/env python3
"""
Schnelltest für OCR-Texterkennung.
Testet ob EasyOCR/Tesseract installiert ist und erkennt Text auf Screenshots.

Nutzung:
    python tools/test_ocr.py                         Region per Maus auswählen
    python tools/test_ocr.py test                    Nur Backend-Status prüfen
    python tools/test_ocr.py bild.png                Bild-Datei analysieren
    python tools/test_ocr.py --region x1,y1,x2,y2   Region direkt angeben
    python tools/test_ocr.py --bosses "Boss1,Boss2"  Gegen bekannte Namen matchen
"""

import sys
import os

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _PROJECT_ROOT)

from autoclicker.ocr import (
    is_available, available_backends, get_status,
    read_text, detect_boss_name,
)


def color(text, c):
    colors = {"green": "\033[92m", "red": "\033[91m", "yellow": "\033[93m",
              "cyan": "\033[96m", "bold": "\033[1m", "reset": "\033[0m"}
    return f"{colors.get(c, '')}{text}{colors['reset']}"


def parse_args():
    options = {"backend": None, "action": "screenshot", "boss_names": [],
               "region": None, "languages": ["en"]}
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in _VALUE_OPTIONS and i + 1 < len(args):
            field, convert = _VALUE_OPTIONS[arg]
            options[field] = convert(args[i + 1])
            i += 2
            continue
        # `--help`/`-h`, `test`, `screenshot` — alles andere ist eine Bild-Datei.
        options["action"] = _ACTIONS.get(arg, arg)
        i += 1

    return (options["backend"], options["action"], options["boss_names"],
            options["region"], options["languages"])


def _split(value: str) -> list[str]:
    return [part.strip() for part in value.split(",")]


def _parse_region(value: str) -> tuple:
    """`x1,y1,x2,y2` als Rechteck mit links-oben zuerst; Unlesbares beendet das Werkzeug."""
    try:
        parts = [int(p) for p in _split(value)]
        if len(parts) != 4:
            raise ValueError(f"Erwarte 4 Werte (x1,y1,x2,y2), bekam {len(parts)}")
    except ValueError as e:
        print(f"{color('Ungültige --region:', 'red')} {e}")
        sys.exit(1)
    x1, y1, x2, y2 = parts
    return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


# Option mit Wert → (Feld, Umwandlung). Steht der Wert nicht mehr da, zählt
# die Option wie jedes andere Wort als Aktion.
_VALUE_OPTIONS = {
    "--backend": ("backend", lambda value: value),
    "--bosses": ("boss_names", _split),
    "--languages": ("languages", _split),
    "--region": ("region", _parse_region),
}
_ACTIONS = {"--help": "help", "-h": "help", "test": "test", "screenshot": "screenshot"}


def print_help():
    print(f"""
{color('OCR Test-Script', 'bold')}

{color('Nutzung:', 'cyan')}
    python tools/test_ocr.py                          Region per Maus auswählen
    python tools/test_ocr.py test                     Nur Backend-Status prüfen
    python tools/test_ocr.py bild.png                 Bild-Datei analysieren

{color('Optionen:', 'cyan')}
    --backend easyocr|tesseract                       Backend (Standard: Auto)
    --bosses "Boss1,Boss2,Boss3"                      Bekannte Boss-Namen
    --region x1,y1,x2,y2                              Region direkt angeben
    --languages "en,de"                               Sprach-Codes (Standard: en)

{color('Beispiele:', 'cyan')}
    python tools/test_ocr.py                          Region per Maus → OCR
    python tools/test_ocr.py --bosses "Dragon,Goblin"
    python tools/test_ocr.py --region 100,200,800,600
    python tools/test_ocr.py boss.png --bosses "Dragon,Goblin,Skeleton"
    python tools/test_ocr.py test                     Nur Status prüfen
""")


def test_backends():
    print(f"\n{color('=== OCR STATUS ===', 'bold')}")
    backends = available_backends()

    if not backends:
        print(f"  Status: {color('Kein Backend verfügbar', 'red')}")
        print()
        print(f"  {color('Installation:', 'yellow')}")
        print("  pip install easyocr        (empfohlen, GPU-Unterstützung)")
        print("  pip install pytesseract     (+ Tesseract installieren)")
        return False

    for b in backends:
        print(f"  {color(b, 'green')} — verfügbar")

    print(f"\n  {color('Bereit!', 'green')} {get_status()}")
    return True


def analyze(backend, img, boss_names, languages):
    import time

    print(f"\n{color('=== OCR-ANALYSE ===', 'bold')}")
    w, h = img.size
    print(f"  Bild:      {w}x{h} Pixel")
    print(f"  Backend:   {color(backend or 'Auto', 'cyan')}")
    print(f"  Sprachen:  {color(', '.join(languages), 'cyan')}")
    if boss_names:
        print(f"  Bosse:     {color(', '.join(boss_names), 'cyan')}")
    print()
    print("  Lese Text...", end=" ", flush=True)

    start = time.time()
    texts = read_text(img, backend=backend, languages=languages)
    duration = (time.time() - start) * 1000

    print(f"{color('OK', 'green')} ({duration:.0f}ms)")
    print()

    if not texts:
        print(f"  {color('Kein Text erkannt', 'yellow')}")
        return

    print(f"  {color('Erkannter Text:', 'bold')}")
    for text, conf in texts:
        conf_color = "green" if conf >= 0.7 else ("yellow" if conf >= 0.4 else "red")
        print(f"    {color(f'{conf:.0%}', conf_color)} {text}")

    if boss_names:
        print()
        success, matched, raw, dur = detect_boss_name(
            img, boss_names, backend=backend, languages=languages
        )
        if success and matched:
            print(f"  {color('Boss erkannt:', 'bold')} {color(matched, 'green')}")
        else:
            print(f"  {color('Kein Boss-Name zugeordnet', 'yellow')}")
            print(f"  Erkannter Text: '{raw}'")
    else:
        print(f"\n  {color('Hinweis:', 'yellow')} Nutze --bosses um gegen bekannte Namen abzugleichen")


def main():
    backend, action, boss_names, region, languages = parse_args()

    if action == "help":
        print_help()
        return

    if action == "test":
        test_backends()
        return

    if not is_available():
        print(f"\n{color('Kein OCR-Backend installiert!', 'red')}")
        print("  pip install easyocr        (empfohlen)")
        print("  pip install pytesseract     (Alternative)")
        return

    try:
        from PIL import Image
    except ImportError:
        print(f"\n{color('Pillow nicht installiert!', 'red')} pip install pillow")
        return

    if action == "screenshot":
        img = _screenshot(region)
    else:
        img = _open_image(Image, action)
    if img is _STOP:
        return
    if img is None:
        print(f"\n{color('Kein Bild verfügbar!', 'red')}")
        return

    analyze(backend, img, boss_names, languages)
    print()


# Ein Bild-Weg hat schon gesagt, warum es kein Bild gibt — `main` hört still auf.
_STOP = object()


def _screenshot(region):
    """Ein Screenshot der Region oder eines mit der Maus gewählten Bereichs."""
    print(f"\n{color('=== SCREENSHOT ===', 'bold')}")
    try:
        from autoclicker.imaging import take_screenshot, select_region

        if region is not None:
            img = take_screenshot(region)
            print(f"  Screenshot: Region {region}")
            return img
        sel_region = select_region()
        if not sel_region:
            print("  -> Abgebrochen")
            return _STOP
        return take_screenshot(sel_region)
    except Exception as e:
        print(f"  Screenshot fehlgeschlagen: {e}")
        return _STOP


def _open_image(image_module, filepath: str):
    """Die Bild-Datei aus der Kommandozeile."""
    if not os.path.exists(filepath):
        print(f"\n{color(f'Datei nicht gefunden: {filepath}', 'red')}")
        return _STOP
    try:
        img = image_module.open(filepath)
        print(f"\n  Bild geladen: {filepath}")
        return img
    except Exception as e:
        print(f"\n{color(f'Bild konnte nicht geladen werden: {e}', 'red')}")
        return _STOP


if __name__ == "__main__":
    main()
