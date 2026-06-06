#!/usr/bin/env python3
"""Standalone-Test für die LLM-Boss-Erkennung.

Nutzt die gleiche Code-Bahn (autoclicker.llm_vision.analyze_image) wie der
Worker im laufenden Autoclicker — damit driftet der Test nicht weg vom
Produktionscode (Reasoning-Strip, System-Prompt, Provider-Defaults).

Aufruf:
    python tools/test_llm.py                # Connection-Test + interaktiver Scan
    python tools/test_llm.py screenshot     # Einmaliger Boss-Scan über Region-Picker
    python tools/test_llm.py items          # Item-/Mengen-Erkennung mit Verify-2.-Scan
"""

import base64
import io
import json
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path

# Repo-Root in sys.path damit `autoclicker` importierbar ist, auch aus tools/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autoclicker.config import AppConfig
from autoclicker.llm_vision import analyze_image, match_boss_name, test_connection


# Prototyp-System-Prompt fürs Item-/Mengen-Ablesen. Erzwingt JSON statt Freitext,
# damit das Ergebnis nachgelagert in Aktionen übersetzbar wäre.
ITEM_SYSTEM_PROMPT = (
    "Du bist ein präziser OCR-Analyst für das Inventar im Spiel Idle Clans.\n"
    "Deine Aufgabe: lies JEDES sichtbare Item-Feld ab und gib Name + Menge zurück.\n"
    "DEINE REGELN:\n"
    "1. Antworte AUSSCHLIESSLICH mit gültigem JSON-Array, nichts davor/danach.\n"
    "2. Format: [{\"slot\": <nr von links-oben, 1-basiert>, \"item\": \"<name>\", "
    "\"menge\": <ganzzahl>}]\n"
    "3. Lies Zahlen exakt ab. Raten ist verboten — bei unleserlicher Menge: \"menge\": null.\n"
    "4. Leere Felder ignorieren. Wenn nichts erkennbar ist: []\n"
    "5. Keine Erklärungen, kein Markdown, keine Code-Fences."
)
ITEM_USER_PROMPT = "Lies alle Items und Mengen aus diesem Inventar-Ausschnitt ab."

# Default-Vision-Modell für den Item-Test. Unabhängig von config.json, damit ein
# veralteter llm_model-Eintrag (z.B. ein Nicht-Vision-Modell) hier nicht stört.
DEFAULT_ITEM_MODEL = "google/gemma-4-12b-qat"


def _print_header(title: str) -> None:
    print(f"\n\033[1m=== {title} ===\033[0m")


def run_connection_test(config: AppConfig) -> bool:
    """Pingt den konfigurierten LLM-Provider und listet verfügbare Modelle."""
    _print_header(f"VERBINDUNGSTEST: {config.llm_provider}")
    success, message = test_connection(
        provider=config.llm_provider,
        endpoint=config.llm_endpoint,
        model=config.llm_model,
    )
    color = "\033[92m" if success else "\033[91m"
    print(f"{color}{message}\033[0m")
    return success


def run_single_scan(config: AppConfig) -> None:
    """Einmaliger Scan: Region wählen, analysieren, Ergebnis."""
    from autoclicker.imaging import take_screenshot, select_region

    print("\nRegion auswählen...")
    region = select_region()
    if not region:
        print("Abgebrochen.")
        return

    img = take_screenshot(region)
    if img is None:
        print("\033[91mScreenshot fehlgeschlagen!\033[0m")
        return

    print(f"Sende an {config.llm_provider} ({config.llm_model})...")
    success, response, duration_ms = analyze_image(
        img=img,
        provider=config.llm_provider,
        endpoint=config.llm_endpoint,
        model=config.llm_model,
        prompt=config.llm_boss_prompt,
        boss_names=None,
        timeout=config.llm_timeout,
        reasoning=config.llm_reasoning,
        max_tokens=config.llm_max_tokens,
    )

    if not success:
        print(f"\033[91mFehler: {response}\033[0m  ({duration_ms:.0f}ms)")
        return

    matched, is_new = match_boss_name(response, boss_names=[])
    color = "\033[93m" if matched is None else ("\033[96m" if is_new else "\033[92m")
    print(f"\nRoh-Antwort:   '{response}'")
    print(f"Boss-Name:     {color}{matched or '— (kein Boss)'}\033[0m")
    print(f"Reasoning:     {'an' if config.llm_reasoning else 'aus'}")
    print(f"Zeitaufwand:   {duration_ms / 1000:.2f}s")


def _raw_lmstudio_debug(img, model: str, endpoint: str = "http://localhost:1234/v1/chat/completions") -> None:
    """Sendet Bild direkt an LM Studio und druckt die vollständige Raw-Antwort.

    Umgeht analyze_image() komplett — so sieht man exakt was LM Studio zurückgibt,
    inkl. reasoning_content, ob content leer ist, etc.
    """
    _print_header("RAW LM-STUDIO DEBUG")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    body = {
        "model": model,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "Was siehst du auf diesem Bild? Beschreibe kurz die sichtbaren Zahlen."},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ]}],
        "temperature": 0.0,
        "max_tokens": 200,
    }
    try:
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        print("Vollständige Antwort von LM Studio:")
        print(json.dumps(raw, indent=2, ensure_ascii=False))
        choices = raw.get("choices", [])
        if choices:
            msg = choices[0].get("message", {})
            print(f"\ncontent:          '{msg.get('content', '')}'")
            print(f"reasoning_content: '{str(msg.get('reasoning_content', ''))[:200]}'")
    except Exception as e:
        print(f"\033[91mFehler: {e}\033[0m")


def _flush_stdin() -> None:
    """Verwirft gepufferte Tastatureingaben vor einem Prompt.

    Tippt man während eines langen Scans ungeduldig (z.B. 'i'), werden die Tasten
    gepuffert und landen sonst im nächsten input() — so wurde schon mal 'i' als
    Modellname interpretiert. Best-effort: msvcrt (Windows) / termios (POSIX)."""
    try:
        import msvcrt
        while msvcrt.kbhit():
            msvcrt.getch()
        return
    except ImportError:
        pass
    try:
        import termios
        termios.tcflush(sys.stdin, termios.TCIFLUSH)
    except (ImportError, OSError):
        pass


def _parse_item_json(response: str):
    """Extrahiert das JSON-Array aus der LLM-Antwort (tolerant ggü. Code-Fences/Text).

    Returns: (parsed_list_or_None, fehler_text_or_None)
    """
    if not response:
        return None, "leere Antwort"
    # Häufigster Müll: ```json ... ``` Fences oder erklärender Text drumherum.
    # Wir greifen das erste '[' bis zum letzten ']' heraus.
    start = response.find("[")
    end = response.rfind("]")
    if start == -1 or end == -1 or end < start:
        return None, "kein JSON-Array gefunden"
    snippet = response[start:end + 1]
    try:
        data = json.loads(snippet)
    except json.JSONDecodeError as e:
        return None, f"JSON ungültig: {e}"
    if not isinstance(data, list):
        return None, "JSON ist kein Array"
    return data, None


def _items_to_key(items) -> dict:
    """Normalisiert eine Item-Liste auf {item_name: menge} für den Verify-Vergleich."""
    result = {}
    for entry in items or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("item", "")).strip().lower()
        if name:
            result[name] = entry.get("menge")
    return result


def _scan_items_once(config: AppConfig, img, label: str, model: str):
    """Ein LLM-Durchlauf fürs Item-Ablesen. Gibt geparste Liste zurück (oder None)."""
    success, response, duration_ms = analyze_image(
        img=img,
        provider=config.llm_provider,
        endpoint=config.llm_endpoint,
        model=model,
        prompt=ITEM_USER_PROMPT,
        reasoning=config.llm_reasoning,
        max_tokens=max(config.llm_max_tokens, 512),  # JSON braucht mehr Tokens als ein Boss-Name
        # 12B-Vision-Modelle brauchen ~20s — der Config-Timeout (oft 30s) ist zu knapp.
        timeout=max(config.llm_timeout, 120),
        system_prompt=ITEM_SYSTEM_PROMPT,
    )
    print(f"\n[{label}] {duration_ms / 1000:.2f}s")
    if not success:
        print(f"\033[91mFehler: {response}\033[0m")
        return None
    print(f"Roh-Antwort: '{response}'")
    if not response or not response.strip():
        print("\033[91mLeere Antwort.\033[0m \033[90mMögliche Ursachen: Modell ist nicht "
              "Vision-fähig (kann das Bild nicht sehen), falscher Modellname, oder der "
              "Screenshot war leer/schwarz (siehe gespeichertes Debug-Bild).\033[0m")
        return None
    items, parse_err = _parse_item_json(response)
    if parse_err:
        print(f"\033[91mParse-Fehler: {parse_err}\033[0m")
        return None
    for entry in items:
        if isinstance(entry, dict):
            print(f"  Slot {entry.get('slot', '?')}: "
                  f"{entry.get('item', '?')} × {entry.get('menge', '?')}")
    print(f"\033[92m{len(items)} Item(s) gelesen.\033[0m")
    return items


def run_item_scan(config: AppConfig) -> None:
    """Liest Items+Mengen per LLM, macht einen 2. Scan und vergleicht (Verify-Konzept).

    Der Modellname wird hier direkt abgefragt (nicht aus config.json), damit ein
    veralteter/falscher llm_model-Eintrag den Test nicht sabotiert."""
    from autoclicker.imaging import take_screenshot, select_region

    _flush_stdin()  # gepufferte Tastendrücke aus einem vorherigen Scan verwerfen
    model = input(f"\nModellname (Enter = {DEFAULT_ITEM_MODEL}): ").strip() or DEFAULT_ITEM_MODEL
    # Schutz vor verirrtem Müll (z.B. ein einzelnes 'i' aus dem Menü): zu kurze
    # Namen sind nie echte LM-Studio-Identifier → auf Default zurückfallen.
    if len(model) < 3:
        print(f"\033[93mModellname '{model}' wirkt ungültig — nutze {DEFAULT_ITEM_MODEL}.\033[0m")
        model = DEFAULT_ITEM_MODEL

    print("\nInventar-Region auswählen...")
    region = select_region()
    if not region:
        print("Abgebrochen.")
        return

    img1 = take_screenshot(region)
    if img1 is None:
        print("\033[91mScreenshot fehlgeschlagen!\033[0m")
        return

    # Screenshot zur Kontrolle speichern — so siehst du, ob die Region (z.B. bei
    # negativen Multi-Monitor-Koordinaten) überhaupt korrekt erfasst wurde.
    debug_path = Path("item_scan_debug.png")
    try:
        img1.save(debug_path)
        print(f"\033[90mDebug-Screenshot gespeichert: {debug_path.resolve()}\033[0m")
    except OSError as e:
        print(f"\033[90mDebug-Screenshot konnte nicht gespeichert werden: {e}\033[0m")

    # Raw-Debug zuerst: einfache Frage ohne JSON-Zwang, zeigt die echte LM-Studio-Antwort.
    _raw_lmstudio_debug(img1, model)

    print(f"\nSende an {config.llm_provider} ({model}) mit Item-Prompt...")
    items1 = _scan_items_once(config, img1, "Scan 1", model)
    if items1 is None:
        return

    # Verify: 2. Screenshot derselben Region, erneut lesen, Ergebnisse vergleichen.
    img2 = take_screenshot(region)
    items2 = _scan_items_once(config, img2, "Scan 2 (Verify)", model) if img2 is not None else None
    if items2 is None:
        return

    key1, key2 = _items_to_key(items1), _items_to_key(items2)
    _print_header("VERIFY-VERGLEICH")
    if key1 == key2:
        print("\033[92m✓ Beide Scans identisch — Ergebnis konsistent.\033[0m")
    else:
        print("\033[93m⚠ Scans unterscheiden sich:\033[0m")
        for name in sorted(set(key1) | set(key2)):
            v1, v2 = key1.get(name, "—"), key2.get(name, "—")
            mark = " " if v1 == v2 else "\033[93m≠\033[0m"
            print(f"  {mark} {name}: {v1}  vs  {v2}")
        print("\n\033[90mHinweis: Abweichung = Modell liest nicht-deterministisch. "
              "Für Produktion bräuchte es eine unabhängige Verifikation (z.B. Tesseract).\033[0m")


def main() -> int:
    config = AppConfig()

    # Versuche eine vorhandene config.json zu nutzen — sonst bleiben die Defaults
    try:
        from autoclicker.config import load_config
        loaded = load_config()
        if loaded is not None:
            config = loaded
    except Exception:
        pass

    _print_header("BOSS-SCANNER LLM-TEST")
    print(f"Provider: {config.llm_provider}")
    print(f"Modell:   {config.llm_model}")
    print(f"Endpoint: {config.llm_endpoint or '(Standard)'}")
    print(f"Reasoning: {'an' if config.llm_reasoning else 'aus'}")

    if not run_connection_test(config):
        return 1

    mode = sys.argv[1] if len(sys.argv) > 1 else None
    if mode == "screenshot":
        run_single_scan(config)
        return 0
    if mode == "items":
        run_item_scan(config)
        return 0

    # Interaktive Schleife
    while True:
        choice = input("\nEnter = Boss-Scan | i = Item-Scan | q = Quit: ").strip().lower()
        if choice == "q":
            return 0
        if choice == "i":
            run_item_scan(config)
        else:
            run_single_scan(config)


if __name__ == "__main__":
    raise SystemExit(main())
