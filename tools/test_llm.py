#!/usr/bin/env python3
"""Standalone-Test für die LLM-Boss-Erkennung.

Nutzt die gleiche Code-Bahn (autoclicker.llm_vision.analyze_image) wie der
Worker im laufenden Autoclicker — damit driftet der Test nicht weg vom
Produktionscode (Reasoning-Strip, System-Prompt, Provider-Defaults).

Aufruf:
    python tools/test_llm.py                # Connection-Test + interaktiver Scan
    python tools/test_llm.py screenshot     # Einmaliger Scan über Region-Picker
"""

import sys
from pathlib import Path

# Repo-Root in sys.path damit `autoclicker` importierbar ist, auch aus tools/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autoclicker.config import AppConfig
from autoclicker.llm_vision import analyze_image, match_boss_name, test_connection


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

    # Interaktive Schleife
    while True:
        choice = input("\nEnter = Scan | q = Quit: ").strip().lower()
        if choice == "q":
            return 0
        run_single_scan(config)


if __name__ == "__main__":
    raise SystemExit(main())
