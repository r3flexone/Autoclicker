"""
LLM Vision-Erkennung für den Autoclicker.
Nutzt lokale LLMs (Ollama / LM Studio) für Bild-basierte Boss-Erkennung.
"""

import base64
import io
import json
import logging
import socket
import time
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image

# Logger
logger = logging.getLogger("autoclicker")

# HTTP-Bibliothek (eingebaut in Python)
try:
    import urllib.request
    import urllib.error
    HTTP_AVAILABLE = True
except ImportError:
    HTTP_AVAILABLE = False


# =============================================================================
# PROVIDER-KONFIGURATIONEN
# =============================================================================

# Ollama API: POST http://localhost:11434/api/chat
# LM Studio API: POST http://localhost:1234/v1/chat/completions (OpenAI-kompatibel)

PROVIDER_OLLAMA = "ollama"
PROVIDER_LMSTUDIO = "lmstudio"
VALID_PROVIDERS = {PROVIDER_OLLAMA, PROVIDER_LMSTUDIO}


def _image_to_base64(img: 'Image.Image') -> str:
    """Konvertiert ein PIL Image zu Base64-String (PNG-Format)."""
    with io.BytesIO() as buffer:
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")


def _build_ollama_request(model: str, image_b64: str, prompt: str,
                          boss_names: list[str] = None,
                          reasoning: bool = False) -> dict:
    """Erstellt den Request-Body für die Ollama API."""
    system_prompt = _build_system_prompt(boss_names)

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": prompt,
                "images": [image_b64]
            }
        ],
        "stream": False,
        "options": {
            "temperature": 0.0,
        }
    }
    if reasoning:
        body["think"] = True
    return body


def _build_lmstudio_request(model: str, image_b64: str, prompt: str,
                             boss_names: list[str] = None,
                             reasoning: bool = False) -> dict:
    """Erstellt den Request-Body für die LM Studio API (OpenAI-kompatibel)."""
    system_prompt = _build_system_prompt(boss_names)

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_b64}"
                        }
                    }
                ]
            }
        ],
        "temperature": 0.0,
        "max_tokens": 50,
    }
    if reasoning:
        # Hinweis für Reasoning-fähige Modelle (z.B. QwQ, DeepSeek-R1); wird ignoriert wenn nicht unterstützt
        body["reasoning_effort"] = "high"
    return body


def _build_system_prompt(boss_names: list[str] = None) -> str:
    """Erstellt den System-Prompt für Boss-Erkennung."""
    base = (
        "Du bist ein präziser OCR-Analyst für das Spiel Idle Clans. "
        "DEINE REGELN:\n"
        "1. Antworte NUR mit dem Eigennamen des Bosses/Gegners.\n"
        "2. Ignoriere ALLES andere auf dem Bild (UI-Texte, 'Art', Level, Zahlen, Beschreibungen).\n"
        "3. Wenn kein Name erkennbar ist, antworte NUR: KEIN_BOSS.\n"
        "4. Keine Interpunktion, keine Erklärungen, kein Smalltalk."
    )

    if boss_names:
        names_str = ", ".join(boss_names)
        base += f"\n\nBekannte Bosse: {names_str}"
        base += "\nWenn du einen dieser Bosse erkennst, verwende exakt diesen Namen."
        base += "\nWenn du einen ANDEREN Boss erkennst, antworte mit dessen Namen."

    return base


def analyze_image(
    img: 'Image.Image',
    provider: str = PROVIDER_LMSTUDIO,
    endpoint: str = None,
    model: str = None,
    prompt: str = None,
    boss_names: list[str] = None,
    timeout: int = 60,
    reasoning: bool = False,
) -> tuple[bool, str, float]:
    """Analysiert ein Bild mit einem lokalen LLM.

    Args:
        img: PIL Image zum Analysieren
        provider: "ollama" oder "lmstudio"
        endpoint: API-Endpoint URL (None = Standard)
        model: Modell-Name (None = Standard je nach Provider)
        prompt: Benutzer-Prompt (None = Standard Boss-Erkennung)
        boss_names: Liste bekannter Boss-Namen für den System-Prompt
        timeout: Timeout in Sekunden für die API-Anfrage

    Returns:
        (success: bool, response_text: str, duration_ms: float)
    """
    if not HTTP_AVAILABLE:
        return False, "HTTP-Bibliothek nicht verfügbar", 0.0

    # Defaults
    if provider not in VALID_PROVIDERS:
        return False, f"Unbekannter Provider: {provider}. Erlaubt: {VALID_PROVIDERS}", 0.0

    if endpoint is None:
        if provider == PROVIDER_OLLAMA:
            endpoint = "http://localhost:11434/api/chat"
        else:
            endpoint = "http://localhost:1234/v1/chat/completions"

    if model is None:
        if provider == PROVIDER_OLLAMA:
            model = "gemma4:e4b"
        else:
            model = "google/gemma-4-e2b"

    if prompt is None:
        prompt = "Extrahiere nur den Boss-Namen:"

    # Bild zu Base64 konvertieren
    image_b64 = _image_to_base64(img)

    # Request erstellen
    if provider == PROVIDER_OLLAMA:
        request_body = _build_ollama_request(model, image_b64, prompt, boss_names, reasoning)
    else:
        request_body = _build_lmstudio_request(model, image_b64, prompt, boss_names, reasoning)

    # API-Anfrage
    start_time = time.time()
    try:
        json_data = json.dumps(request_body).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=json_data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
            duration_ms = (time.time() - start_time) * 1000

            # Antwort extrahieren
            text = _extract_response_text(result, provider)
            return True, text.strip(), duration_ms

    except socket.timeout as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error(f"LLM Timeout ({provider}) nach {timeout}s")
        return False, f"Timeout nach {timeout}s", duration_ms

    except urllib.error.URLError as e:
        duration_ms = (time.time() - start_time) * 1000
        reason = str(getattr(e, 'reason', e))
        logger.error(f"LLM API-Fehler ({provider}): {reason}")
        return False, f"Verbindungsfehler: {reason}", duration_ms

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error(f"LLM Antwort-Fehler ({provider}): {e}")
        return False, f"Antwort-Fehler: {e}", duration_ms

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error(f"LLM unerwarteter Fehler ({provider}): {e}")
        return False, f"Fehler: {e}", duration_ms


def _extract_response_text(result: dict, provider: str) -> str:
    """Extrahiert den Antworttext aus der API-Antwort (Reasoning-Inhalt wird ignoriert)."""
    if provider == PROVIDER_OLLAMA:
        # Ollama: {"message": {"content": "...", "thinking": "..."}}
        # Bei Reasoning-Modellen ist thinking separat — wir wollen nur content
        return result.get("message", {}).get("content", "")
    else:
        # LM Studio (OpenAI): {"choices": [{"message": {"content": "...", "reasoning_content": "..."}}]}
        choices = result.get("choices", [])
        if choices:
            msg = choices[0].get("message", {})
            # reasoning_content ignorieren, nur content verwenden
            return msg.get("content", "")
        return ""


def is_no_boss(response: str) -> bool:
    """Prüft ob die LLM-Antwort 'kein Boss' bedeutet."""
    if not response:
        return True
    response_lower = response.lower().strip()
    negative_keywords = ["kein_boss", "kein boss", "no boss", "none", "nichts",
                         "nicht erkannt", "no enemy", "not found", "i don't see",
                         "i cannot", "i can't", "there is no"]
    return any(neg in response_lower for neg in negative_keywords)


def clean_boss_name(response: str) -> str:
    """Bereinigt den LLM-Antworttext zu einem sauberen Boss-Namen."""
    name = response.strip().strip('"').strip("'").strip(".")
    # Mehrzeilige Antworten: nur erste Zeile
    if "\n" in name:
        name = name.split("\n")[0].strip()
    # Präfixe entfernen die manche LLMs hinzufügen
    prefixes = ["the boss is ", "boss: ", "boss name: ", "it's ", "this is ",
                "der boss ist ", "boss-name: ", "das ist "]
    name_lower = name.lower()
    for prefix in prefixes:
        if name_lower.startswith(prefix):
            name = name[len(prefix):].strip()
            break
    return name


def match_boss_name(response: str, boss_names: list[str]) -> tuple[Optional[str], bool]:
    """Versucht den LLM-Antworttext einem bekannten Boss-Namen zuzuordnen.

    Args:
        response: Antwort vom LLM
        boss_names: Liste bekannter Boss-Namen

    Returns:
        (boss_name, is_new) - Boss-Name + ob es ein neuer unbekannter Boss ist.
        (None, False) wenn kein Boss erkannt wurde.
    """
    if not response:
        return None, False

    # Kein Boss erkannt?
    if is_no_boss(response):
        return None, False

    # Bereinigten Namen extrahieren
    cleaned = clean_boss_name(response)
    if not cleaned:
        return None, False

    # Gegen bekannte Bosse matchen
    if boss_names:
        cleaned_lower = cleaned.lower()

        # Exakter Match
        for name in boss_names:
            if name.lower() == cleaned_lower:
                return name, False

        # Enthaltener Match (LLM-Antwort enthält Boss-Namen)
        for name in boss_names:
            if name.lower() in cleaned_lower:
                return name, False

        # Boss-Name in LLM-Antwort enthalten
        for name in boss_names:
            if cleaned_lower in name.lower():
                return name, False

    # Neuer Boss - nicht in der Liste!
    return cleaned, True


def test_connection(provider: str = PROVIDER_LMSTUDIO,
                    endpoint: str = None, model: str = None) -> tuple[bool, str]:
    """Testet die Verbindung zum LLM-Provider.

    Returns:
        (success: bool, message: str)
    """
    if not HTTP_AVAILABLE:
        return False, "HTTP-Bibliothek nicht verfügbar"

    if endpoint is None:
        if provider == PROVIDER_OLLAMA:
            endpoint = "http://localhost:11434/api/tags"
        else:
            endpoint = "http://localhost:1234/v1/models"

    try:
        req = urllib.request.Request(endpoint, method="GET")
        with urllib.request.urlopen(req, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))

            if provider == PROVIDER_OLLAMA:
                models = [m.get("name", "?") for m in result.get("models", [])]
                vision_models = [m for m in models if any(v in m.lower() for v in
                                ["gemma", "llava", "bakllava", "moondream", "vision", "minicpm"])]
                if vision_models:
                    return True, f"Verbunden! Vision-Modelle: {', '.join(vision_models)}"
                elif models:
                    return True, f"Verbunden! Modelle: {', '.join(models[:5])} (kein Vision-Modell erkannt)"
                else:
                    return True, "Verbunden! Keine Modelle installiert."
            else:
                models = [m.get("id", "?") for m in result.get("data", [])]
                if models:
                    return True, f"Verbunden! Modelle: {', '.join(models[:5])}"
                else:
                    return True, "Verbunden! Kein Modell geladen."

    except urllib.error.URLError as e:
        reason = str(getattr(e, 'reason', e))
        return False, f"Nicht erreichbar: {reason}"
    except Exception as e:
        return False, f"Fehler: {e}"
