#!/usr/bin/env python3
"""
Schnelltest für LLM Vision (Ollama / LM Studio).
Testet Verbindung und Bilderkennung ohne den Autoclicker starten zu müssen.

Nutzung:
    python test_llm.py                              # Verbindungstest
    python test_llm.py screenshot                   # Screenshot machen + analysieren
    python test_llm.py screenshot --region x1,y1,x2,y2  # Direkter Region-Screenshot
    python test_llm.py bild.png                     # Vorhandenes Bild analysieren
    python test_llm.py --provider lmstudio          # LM Studio statt Ollama
    python test_llm.py --model moondream            # Anderes Modell
"""

import sys
import os
import time

# Projekt-Root zum Path hinzufügen
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from autoclicker.llm_vision import (
    test_connection, analyze_image, match_boss_name,
    PROVIDER_OLLAMA, PROVIDER_LMSTUDIO,
)


def color(text, c):
    colors = {"green": "\033[92m", "red": "\033[91m", "yellow": "\033[93m",
              "cyan": "\033[96m", "bold": "\033[1m", "reset": "\033[0m"}
    return f"{colors.get(c, '')}{text}{colors['reset']}"


def parse_args():
    provider = PROVIDER_OLLAMA
    model = None
    action = "test"  # "test", "screenshot", oder Dateipfad
    prompt = None
    boss_names = []
    region = None  # (x1, y1, x2, y2) oder None

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--provider" and i + 1 < len(args):
            provider = args[i + 1]
            i += 2
        elif arg == "--model" and i + 1 < len(args):
            model = args[i + 1]
            i += 2
        elif arg == "--prompt" and i + 1 < len(args):
            prompt = args[i + 1]
            i += 2
        elif arg == "--bosses" and i + 1 < len(args):
            boss_names = [b.strip() for b in args[i + 1].split(",")]
            i += 2
        elif arg == "--region" and i + 1 < len(args):
            try:
                parts = [int(p.strip()) for p in args[i + 1].split(",")]
                if len(parts) != 4:
                    raise ValueError(f"Erwarte 4 Werte (x1,y1,x2,y2), bekam {len(parts)}")
                x1, y1, x2, y2 = parts
                if x1 > x2:
                    x1, x2 = x2, x1
                if y1 > y2:
                    y1, y2 = y2, y1
                region = (x1, y1, x2, y2)
            except ValueError as e:
                print(f"{color('Ungültige --region:', 'red')} {e}")
                print("  Format: --region x1,y1,x2,y2 (z.B. --region 100,200,800,600)")
                sys.exit(1)
            i += 2
        elif arg == "screenshot":
            action = "screenshot"
            i += 1
        elif arg in ("--help", "-h"):
            action = "help"
            i += 1
        else:
            action = arg  # Dateipfad
            i += 1

    return provider, model, action, prompt, boss_names, region


def print_help():
    print(f"""
{color('LLM Vision Test-Script', 'bold')}

{color('Nutzung:', 'cyan')}
    python test_llm.py                          Verbindungstest
    python test_llm.py screenshot               Screenshot + Analyse
    python test_llm.py bild.png                 Bild-Datei analysieren

{color('Optionen:', 'cyan')}
    --provider ollama|lmstudio                  Provider (Standard: ollama)
    --model <name>                              Modell (Standard: llava)
    --prompt "Was siehst du?"                   Custom Prompt
    --bosses "Boss1,Boss2,Boss3"                Bekannte Boss-Namen
    --region x1,y1,x2,y2                        Region direkt angeben (statt interaktiv)

{color('Beispiele:', 'cyan')}
    python test_llm.py                          Nur Verbindung testen
    python test_llm.py screenshot               Screenshot vom Bildschirm
    python test_llm.py screenshot --model moondream
    python test_llm.py screenshot --region 100,200,800,600
    python test_llm.py boss.png --bosses "Dragon,Goblin,Skeleton"
    python test_llm.py screenshot --prompt "Beschreibe was du siehst"
    python test_llm.py --provider lmstudio screenshot
""")


def test_conn(provider, model):
    print(f"\n{color('=== VERBINDUNGSTEST ===', 'bold')}")
    print(f"  Provider: {color(provider, 'cyan')}")

    success, message = test_connection(provider)

    if success:
        print(f"  Status:   {color('OK', 'green')}")
        print(f"  {message}")
    else:
        print(f"  Status:   {color('FEHLER', 'red')}")
        print(f"  {message}")
        print()
        if provider == PROVIDER_OLLAMA:
            print(f"  {color('Lösung:', 'yellow')}")
            print(f"  1. Ollama installieren: https://ollama.com")
            print(f"  2. Vision-Modell laden: ollama pull llava")
            print(f"  3. Prüfen ob es läuft:  ollama list")
        else:
            print(f"  {color('Lösung:', 'yellow')}")
            print(f"  1. LM Studio starten")
            print(f"  2. Vision-Modell laden (z.B. LLaVA)")
    return success


def analyze(provider, model, img, prompt, boss_names):
    print(f"\n{color('=== BILD-ANALYSE ===', 'bold')}")
    print(f"  Provider: {color(provider, 'cyan')}")
    print(f"  Modell:   {color(model or '(Standard)', 'cyan')}")
    if boss_names:
        print(f"  Bosse:    {color(', '.join(boss_names), 'cyan')}")

    w, h = img.size
    print(f"  Bild:     {w}x{h} Pixel")

    if not prompt:
        prompt = "Welcher Boss ist auf diesem Screenshot zu sehen? Antworte nur mit dem Boss-Namen."

    print(f"  Prompt:   {prompt}")
    if not boss_names:
        print(f"  {color('Hinweis:', 'yellow')} Keine Boss-Namen angegeben (--bosses \"Name1,Name2\")")
        print(f"            Ohne Namen kann das LLM nicht zuordnen!")
    print()
    print(f"  Sende an LLM...", end=" ", flush=True)

    success, response, duration = analyze_image(
        img=img,
        provider=provider,
        model=model,
        prompt=prompt,
        boss_names=boss_names if boss_names else None,
        timeout=60,
    )

    if success:
        print(f"{color('OK', 'green')} ({duration:.0f}ms)")
        print()
        print(f"  {color('Antwort:', 'bold')}")
        print(f"  {color(response, 'green')}")

        from autoclicker.llm_vision import is_no_boss, clean_boss_name
        print()
        if is_no_boss(response):
            print(f"  {color('Ergebnis:', 'bold')} {color('Kein Boss erkannt', 'yellow')}")
        else:
            cleaned = clean_boss_name(response)
            if boss_names:
                matched, is_new = match_boss_name(response, boss_names)
                if matched and not is_new:
                    print(f"  {color('Boss erkannt:', 'bold')} {color(matched, 'green')} (bekannt)")
                elif matched and is_new:
                    print(f"  {color('Neuer Boss:', 'bold')} {color(matched, 'cyan')} (würde gespeichert werden)")
                else:
                    print(f"  {color('Kein Boss zugeordnet', 'yellow')}")
            else:
                print(f"  {color('Boss-Name:', 'bold')} {color(cleaned, 'cyan')}")
                print(f"  (Nutze --bosses um gegen bekannte Namen abzugleichen)")
    else:
        print(f"{color('FEHLER', 'red')} ({duration:.0f}ms)")
        print(f"  {response}")


def main():
    provider, model, action, prompt, boss_names, region = parse_args()

    if action == "help":
        print_help()
        return

    # Immer zuerst Verbindung testen
    if not test_conn(provider, model):
        return

    if action == "test":
        print(f"\n{color('Verbindung OK!', 'green')} Nutze 'python test_llm.py screenshot' für einen Bildtest.")
        return

    # Bild laden
    try:
        from PIL import Image
    except ImportError:
        print(f"\n{color('Pillow nicht installiert!', 'red')} pip install pillow")
        return

    img = None

    if action == "screenshot":
        print(f"\n{color('=== SCREENSHOT ===', 'bold')}")

        try:
            from autoclicker.imaging import take_screenshot, select_region

            if region is not None:
                # Region per CLI-Argument vorgegeben
                img = take_screenshot(region)
                print(f"  Screenshot: Region {region}")
            else:
                print("  [1] Vollbild")
                print("  [2] Region auswählen (2 Ecken)")
                print("  [3] Region eintippen (x1,y1,x2,y2)")
                choice = input("  Wahl (Enter=1): ").strip()

                if choice == "2":
                    print("\n  Region auswählen...")
                    sel_region = select_region()
                    if sel_region:
                        img = take_screenshot(sel_region)
                        print(f"  Screenshot: {sel_region}")
                    else:
                        print("  -> Abgebrochen")
                        return
                elif choice == "3":
                    raw = input("  Koordinaten (x1,y1,x2,y2): ").strip()
                    try:
                        parts = [int(p.strip()) for p in raw.split(",")]
                        if len(parts) != 4:
                            raise ValueError(f"Erwarte 4 Werte, bekam {len(parts)}")
                        x1, y1, x2, y2 = parts
                        if x1 > x2:
                            x1, x2 = x2, x1
                        if y1 > y2:
                            y1, y2 = y2, y1
                        typed_region = (x1, y1, x2, y2)
                        img = take_screenshot(typed_region)
                        print(f"  Screenshot: {typed_region}")
                    except ValueError as e:
                        print(f"  {color('Ungültige Eingabe:', 'red')} {e}")
                        return
                else:
                    img = take_screenshot()
                    print("  Screenshot: Vollbild")
        except Exception as e:
            print(f"  Screenshot fehlgeschlagen: {e}")
            print("  Tipp: Auf Windows muss das Script mit Bildschirmzugriff laufen")
            return

    else:
        # Datei laden
        filepath = action
        if not os.path.exists(filepath):
            print(f"\n{color(f'Datei nicht gefunden: {filepath}', 'red')}")
            return
        try:
            img = Image.open(filepath)
            print(f"\n  Bild geladen: {filepath}")
        except Exception as e:
            print(f"\n{color(f'Bild konnte nicht geladen werden: {e}', 'red')}")
            return

    if img is None:
        print(f"\n{color('Kein Bild verfügbar!', 'red')}")
        return

    analyze(provider, model, img, prompt, boss_names)
    print()


if __name__ == "__main__":
    main()
