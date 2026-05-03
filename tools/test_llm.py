#!/usr/bin/env python3

import os
import base64
import requests
import time
from io import BytesIO

# --- KONFIGURATION ---
URL = "http://localhost:1234/v1/chat/completions"
MODEL = "google/gemma-4-e2b"


def start_visual_chat(img):
    # Bildvorbereitung
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    img_str = base64.b64encode(buffer.getvalue()).decode()

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Du bist ein präziser OCR-Analyst für Videospiele. "
                    "DEINE REGELN:\n"
                    "1. Antworte NUR mit dem Eigennamen des Bosses/Gegners.\n"
                    "2. Ignoriere ALLES andere auf dem Bild (UI-Texte, 'Art', Level, Zahlen, Beschreibungen).\n"
                    "3. Wenn kein Name erkennbar ist, antworte NUR: Kein_Boss.\n"
                    "4. Keine Interpunktion, keine Erklärungen, kein Smalltalk."
                )
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Extrahiere nur den Boss-Namen:"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_str}"}}
                ]
            }
        ],
        "temperature": 0.0,  # Verhindert Halluzinationen und Zusätze
    }

    start_time = time.time()
    try:
        response = requests.post(URL, json=payload, timeout=60)
        duration = time.time() - start_time

        if response.status_code == 200:
            result = response.json()
            content = result["choices"][0]["message"]["content"].strip()
            return content, duration
        else:
            return f"Fehler: {response.status_code}", duration
    except Exception as e:
        return str(e), time.time() - start_time


def main():
    from autoclicker.imaging import take_screenshot, select_region

    print("\033[1m=== BOSS-SCANNER (STRICT AI MODE) ===\033[0m")

    while True:
        print("\nBereit...")
        user_input = input("Enter = Scan | q = Quit: ").lower()

        if user_input == 'q':
            break

        region = select_region()
        if not region:
            continue

        img = take_screenshot(region)
        print("KI arbeitet...")

        antwort, dauer = start_visual_chat(img)

        # Visuelle Aufbereitung
        color = "\033[92m" if antwort != "Kein_Boss" else "\033[93m"
        print(f"\nIdentifiziert: {color}{antwort}\033[0m")
        print(f"Zeitaufwand:   {dauer:.2f} s")
        print("-" * 35)


if __name__ == "__main__":
    main()