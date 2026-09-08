"""
LLM Vision-Erkennung für den Autoclicker.
Nutzt lokale LLMs (Ollama / LM Studio) für Bild-basierte Boss-Erkennung.
"""

import base64
import io
import json
import logging
import re
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

# Standard-Endpunkte je Anbieter. An EINER Stelle, weil sie sonst dreifach dastehen:
# hier fuer den Chat, hier fuer den Verbindungstest, und nochmal im Boss-Scan-Editor.
DEFAULT_CHAT_ENDPOINT = {
    PROVIDER_OLLAMA: "http://localhost:11434/api/chat",
    PROVIDER_LMSTUDIO: "http://localhost:1234/v1/chat/completions",
}
DEFAULT_TEST_ENDPOINT = {
    PROVIDER_OLLAMA: "http://localhost:11434/api/tags",
    PROVIDER_LMSTUDIO: "http://localhost:1234/v1/models",
}


def chat_endpoint(provider: str) -> str:
    """Chat-Endpunkt des Anbieters (LM Studio als Rueckfall)."""
    return DEFAULT_CHAT_ENDPOINT.get(provider, DEFAULT_CHAT_ENDPOINT[PROVIDER_LMSTUDIO])


def test_endpoint_for(provider: str) -> str:
    """Endpunkt fuer den Verbindungstest (Modell-Liste statt Chat)."""
    return DEFAULT_TEST_ENDPOINT.get(provider, DEFAULT_TEST_ENDPOINT[PROVIDER_LMSTUDIO])
VALID_PROVIDERS = {PROVIDER_OLLAMA, PROVIDER_LMSTUDIO}


def _image_to_base64(img: 'Image.Image') -> str:
    """Konvertiert ein PIL Image zu Base64-String (PNG-Format)."""
    with io.BytesIO() as buffer:
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")


def _build_ollama_request(model: str, image_b64: str, prompt: str,
                          boss_names: list[str] = None,
                          reasoning: bool = False,
                          max_tokens: int = 0,
                          system_prompt: str = None) -> dict:
    """Erstellt den Request-Body für die Ollama API.

    max_tokens > 0 überschreibt den Auto-Default (128 ohne, 2048 mit Reasoning).
    system_prompt überschreibt den Default-Boss-OCR-Prompt (z.B. für Item-Scan).
    """
    system_prompt = system_prompt or _build_system_prompt(boss_names)

    # Bei Reasoning-Modellen braucht es deutlich mehr Tokens — sonst wird das Thinking
    # abgeschnitten und der Boss-Name kommt nie als Antwort raus. Ollama-Default: 128.
    if max_tokens > 0:
        num_predict = max_tokens
    else:
        num_predict = 2048 if reasoning else 128
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
            "num_predict": num_predict,
        }
    }
    if reasoning:
        # Bool funktioniert für qwen3/deepseek-r1/gemma3. gpt-oss erwartet "low"/"medium"/"high"
        # und ignoriert bool — das ist ein bekannter Edge-Case.
        body["think"] = True
    return body


def _build_lmstudio_request(model: str, image_b64: str, prompt: str,
                             boss_names: list[str] = None,
                             reasoning: bool = False,
                             max_tokens: int = 0,
                             system_prompt: str = None) -> dict:
    """Erstellt den Request-Body für die LM Studio API (OpenAI-kompatibel).

    max_tokens > 0 überschreibt den Auto-Default (50 ohne, 2048 mit Reasoning).
    system_prompt überschreibt den Default-Boss-OCR-Prompt (z.B. für Item-Scan).
    """
    system_prompt = system_prompt or _build_system_prompt(boss_names)

    # Reasoning-Modelle (DeepSeek-R1, QwQ) packen <think>...</think> oft direkt in den content.
    # Mit nur 50 Tokens wird das Thinking abgeschnitten bevor der eigentliche Boss-Name kommt.
    if max_tokens <= 0:
        max_tokens = 2048 if reasoning else 50
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
        "max_tokens": max_tokens,
    }
    if reasoning:
        # OpenAI-Konvention für /v1/chat/completions — wird von gpt-oss in LM Studio genutzt.
        # Andere Modelle ignorieren den Parameter, machen Reasoning aber ggf. trotzdem via <think>-Tags.
        body["reasoning_effort"] = "high"
    else:
        # Explizit deaktivieren — ohne diesen Parameter denken Reasoning-Modelle
        # (z.B. Gemma-4-12b-qat) trotzdem und verbrauchen alle Tokens im Reasoning,
        # sodass content leer bleibt.
        body["reasoning_effort"] = "none"
    return body


def _build_system_prompt(boss_names: list[str] = None) -> str:
    """Erstellt den System-Prompt für Boss-Erkennung."""
    base = (
        "Du bist ein präziser OCR-Analyst für das Spiel Idle Clans. "
        "Deine Aufgabe: lies den Eigennamen des Bosses/Gegners vom Bild ab.\n"
        "DEINE REGELN:\n"
        "1. Antworte in GENAU EINER Zeile mit AUSSCHLIESSLICH dem Eigennamen — "
        "keine Präfixe wie 'Der Boss ist', keine Anführungszeichen, keine Interpunktion, "
        "keine Erklärungen, kein Smalltalk.\n"
        "2. Ignoriere ALLES andere auf dem Bild (UI-Texte, 'Art', Level, Zahlen, Beschreibungen).\n"
        "3. Wenn kein Boss-Name lesbar ist, antworte mit GENAU diesem Wort: KEIN_BOSS\n"
        "4. Gib den Namen exakt so wieder, wie er auf dem Bild steht — rate nicht "
        "und verändere die Schreibweise nicht.\n"
        "\n"
        "Beispiele:\n"
        "Bild zeigt 'Skeleton King' → Skeleton King\n"
        "Bild zeigt nur Inventar/Menü → KEIN_BOSS"
    )

    if boss_names:
        names_str = ", ".join(boss_names)
        base += (
            f"\n\nBereits bekannte Bosse (mögliche Referenz, NICHT abschliessend): {names_str}\n"
            "Wenn der abgelesene Name exakt einem davon entspricht, verwende genau diese Schreibweise. "
            "Wenn du einen anderen oder unsicheren Namen liest, gib ihn trotzdem wörtlich wieder — "
            "ordne ihn NICHT gewaltsam einem bekannten Boss zu."
        )

    return base


# =============================================================================
# MITSCHRIFT (config.llm_debug)
# =============================================================================
#
# **Eine leere Antwort hat vier Ursachen, und von aussen sehen sie gleich aus:**
# das Modell kann keine Bilder, der Modellname stimmt nicht, ein
# Reasoning-Modell hat alle Tokens verdacht, oder das Bild war schwarz. Ohne
# die rohe Antwort raet man zwischen ihnen — genau dafuer gab es
# `_raw_lmstudio_debug()` in `tools/test_llm.py`, also einen zweiten
# HTTP-Aufruf neben dem echten mit einer anderen Frage. Hier haengt die
# Mitschrift AM echten Aufruf: was dasteht, ist das, was der Aufrufer bekommen
# hat, und nicht das, was ein Nachbau bekommen haette.
#
# Gelesen wird `CONFIG` und nicht ein eigener Modulschalter — es gibt EIN
# Config-Objekt pro Prozess, und der Einstellungen-Reiter haelt es aktuell.
# Beide Importe stehen IN den Funktionen: `llm_vision` zieht sonst `config`
# und `utils` schon beim blossen Import nach, und die Vertragssuite importiert
# es einzeln.

# Der Grund, den `suggest_item_name_grund()` fuer eine Zeitueberschreitung
# meldet. Als Konstante, damit der Aufrufer ihn nicht am Text erkennen muss.
TIMEOUT = "timeout"


def ist_timeout(antwort: str) -> bool:
    """War dieser Fehlschlag eine Zeitueberschreitung?

    **Der Unterschied entscheidet, ob sich ein zweiter Versuch lohnt.** Ein
    Timeout heisst fast immer: der Server laedt das Modell gerade (gemessen —
    die ersten Aufrufe ueber 120 s, die folgenden 3,5), und der naechste
    Versuch trifft ein warmes Modell. Ein Verbindungsfehler heisst: da ist
    niemand, und Wiederholen ist nur Warten.

    Die Regel steht hier und nicht bei den Aufrufern: sie haengt am Text, den
    `analyze_image()` erzeugt, und der gehoert diesem Modul.
    """
    return str(antwort or "").startswith("Timeout")

_DEBUG_ROH_MAX = 4000       # Zeichen der rohen JSON-Antwort; ein Base64-Echo sprengt sonst die Konsole


def _debug_an() -> bool:
    """Schreibt die Config gerade jede LLM-Antwort mit?"""
    try:
        from .config import CONFIG
        return bool(CONFIG.llm_debug)
    except Exception:
        return False


def _debug_ausgabe(zeilen: list) -> None:
    """Ein Block, EIN Schreibvorgang — dieselbe Regel wie bei `status_line()`.

    Je Zeile einzeln geschrieben stand vor jeder ein `clear_line()`, und das
    sind achtzig Leerzeichen: dreissig Zeilen roher JSON kamen mit einer
    achtzig Spalten breiten Treppe davor heraus. Geloescht werden muss die
    Status-Zeile trotzdem — sie steht ohne Zeilenumbruch da, sonst klebt die
    erste Mitschrift-Zeile hinten an ihr.
    """
    try:
        from .utils import clear_line, dbg
        clear_line()
        marke = dbg("[LLM]")
    except Exception:
        marke = "[LLM]"
    print("\n".join(f"{marke} {z}" for z in zeilen), flush=True)


def _debug_anfrage(provider: str, model: str, endpoint: str, prompt: str,
                   system_prompt: Optional[str], img) -> None:
    """Was rausgeht: Modell, Endpunkt, Bildmass und beide Prompts.

    Der System-Prompt gehoert dazu und nicht nur die Frage: bei der
    Item-Benennung entscheidet er ueber die Sprache und darueber, ob das
    Modell frei raet oder aus dem Katalog auswaehlt — genau die Stelle, an der
    man sich fragt, warum eine Antwort deutsch ist.
    """
    groesse = getattr(img, "size", None)
    zeilen = [f"-> {provider} · {model} · {endpoint}",
              f"   Bild: {groesse[0]}×{groesse[1]}" if groesse else "   Bild: (unbekannt)"]
    if system_prompt:
        zeilen.append(f"   System: {system_prompt!r}")
    zeilen.append(f"   Prompt: {prompt!r}")
    _debug_ausgabe(zeilen)


def _debug_antwort(result: dict, text: str, duration_ms: float) -> None:
    """Was zurueckkam — roh und daneben das, was der Code daraus liest.

    Die rohe Antwort steht MIT dem Denk-Feld da (`reasoning_content`), das
    `_extract_response_text` verwirft: ein Modell, das alle Tokens ins Denken
    steckt, liefert einen leeren `content` und sieht sonst aus wie ein
    kaputter Aufruf.
    """
    from .utils import warn
    roh = json.dumps(result, ensure_ascii=False, indent=2)
    rest = max(0, len(roh) - _DEBUG_ROH_MAX)
    zeilen = [f"<- {duration_ms:.0f} ms, roh:"]
    zeilen += ["   " + z for z in roh[:_DEBUG_ROH_MAX].splitlines()]
    if rest:
        zeilen.append(f"   … ({rest} weitere Zeichen abgeschnitten)")
    if text.strip():
        zeilen.append(f"   gelesen: {text!r}")
    else:
        zeilen.append("   gelesen: (leer) " + warn(
            "Modell ohne Bild-Faehigkeit, falscher Modellname, leeres Bild "
            "oder alle Tokens im Reasoning verbraucht"))
    _debug_ausgabe(zeilen)


def _debug_fehler(text: str, duration_ms: float) -> None:
    """Auch ein Fehlschlag wird mitgeschrieben — sonst fehlt in der Mitschrift
    ausgerechnet der Aufruf, der nicht funktioniert hat."""
    from .utils import err
    _debug_ausgabe([err(f"<- nach {duration_ms:.0f} ms: {text}")])


def analyze_image(
    img: 'Image.Image',
    provider: str = PROVIDER_LMSTUDIO,
    endpoint: str = None,
    model: str = None,
    prompt: str = None,
    boss_names: list[str] = None,
    timeout: int = 60,
    reasoning: bool = False,
    max_tokens: int = 0,
    system_prompt: str = None,
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
        system_prompt: Überschreibt den Default-Boss-OCR-System-Prompt
            (z.B. für Item-/Mengen-Erkennung). None = Boss-Erkennung.

    Returns:
        (success: bool, response_text: str, duration_ms: float)
    """
    if not HTTP_AVAILABLE:
        return False, "HTTP-Bibliothek nicht verfügbar", 0.0

    # Defaults
    if provider not in VALID_PROVIDERS:
        return False, f"Unbekannter Provider: {provider}. Erlaubt: {VALID_PROVIDERS}", 0.0

    if endpoint is None:
        endpoint = chat_endpoint(provider)

    if model is None:
        if provider == PROVIDER_OLLAMA:
            model = "gemma3n:e4b"
        else:
            model = "google/gemma-4-12b-qat"

    if prompt is None:
        # Knappe Aufgaben-Frage; die Formatregeln stehen im System-Prompt
        # (nicht erneut wiederholen).
        prompt = "Welcher Boss ist auf diesem Bild zu sehen?"

    # Bild zu Base64 konvertieren
    image_b64 = _image_to_base64(img)

    # Request erstellen
    if provider == PROVIDER_OLLAMA:
        request_body = _build_ollama_request(model, image_b64, prompt, boss_names, reasoning, max_tokens, system_prompt)
    else:
        request_body = _build_lmstudio_request(model, image_b64, prompt, boss_names, reasoning, max_tokens, system_prompt)

    mitschrift = _debug_an()
    if mitschrift:
        _debug_anfrage(provider, model, endpoint, prompt, system_prompt, img)

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
            if mitschrift:
                _debug_antwort(result, text, duration_ms)
            return True, text.strip(), duration_ms

    except socket.timeout:
        duration_ms = (time.time() - start_time) * 1000
        logger.error(f"LLM Timeout ({provider}) nach {timeout}s")
        if mitschrift:
            _debug_fehler(f"Timeout nach {timeout}s", duration_ms)
        return False, f"Timeout nach {timeout}s", duration_ms

    except urllib.error.URLError as e:
        duration_ms = (time.time() - start_time) * 1000
        reason = str(getattr(e, 'reason', e))
        logger.error(f"LLM API-Fehler ({provider}): {reason}")
        if mitschrift:
            _debug_fehler(f"Verbindungsfehler: {reason}", duration_ms)
        return False, f"Verbindungsfehler: {reason}", duration_ms

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error(f"LLM Antwort-Fehler ({provider}): {e}")
        if mitschrift:
            _debug_fehler(f"Antwort-Fehler: {e}", duration_ms)
        return False, f"Antwort-Fehler: {e}", duration_ms

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error(f"LLM unerwarteter Fehler ({provider}): {e}")
        if mitschrift:
            _debug_fehler(f"Fehler: {e}", duration_ms)
        return False, f"Fehler: {e}", duration_ms


# Reasoning-Tags die manche Modelle inline in den content packen (DeepSeek-R1, QwQ u.a.)
# statt sie in ein separates Feld auszulagern. Wir strippen sie hier raus.
_THINK_TAG_PATTERN = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _strip_reasoning_tags(text: str) -> str:
    """Entfernt <think>...</think>-Blöcke und ähnliche Reasoning-Marker aus dem Content."""
    if not text:
        return text
    # Vollständige <think>...</think>-Blöcke entfernen
    cleaned = _THINK_TAG_PATTERN.sub("", text)
    # Unvollständiger Block am Anfang (kein schliessendes Tag, weil truncated): alles bis </think>
    if "</think>" in cleaned:
        cleaned = cleaned.split("</think>", 1)[1]
    # Falls nur ein offenes <think> ohne Schluss übrig ist → alles davor behalten, danach verwerfen
    if "<think>" in cleaned:
        cleaned = cleaned.split("<think>", 1)[0]
    return cleaned.strip()


def _extract_response_text(result: dict, provider: str) -> str:
    """Extrahiert den Antworttext aus der API-Antwort (Reasoning-Inhalt wird ignoriert)."""
    if provider == PROVIDER_OLLAMA:
        # Ollama: {"message": {"content": "...", "thinking": "..."}}
        # Bei think:true ist thinking separat — sonst können <think>-Tags im content stecken.
        content = result.get("message", {}).get("content", "")
    else:
        # LM Studio (OpenAI): {"choices": [{"message": {"content": "...", "reasoning_content": "..."}}]}
        choices = result.get("choices", [])
        if not choices:
            return ""
        msg = choices[0].get("message", {})
        # reasoning_content ignorieren, nur content verwenden
        content = msg.get("content", "")
    return _strip_reasoning_tags(content)


def is_no_boss(response: str) -> bool:
    """Prüft ob die LLM-Antwort 'kein Boss' bedeutet."""
    if not response:
        return True
    response_lower = response.lower().strip()
    negative_keywords = ["kein_boss", "kein boss", "no boss", "none", "nichts",
                         "nicht erkannt", "no enemy", "not found", "i don't see",
                         "i cannot", "i can't", "there is no"]
    # Wortgrenzen statt reinem Substring — sonst matcht z.B. "none" innerhalb
    # eines echten Boss-Namens wie "Stonekeeper" und unterdrückt die Erkennung.
    return any(re.search(r"\b" + re.escape(neg) + r"\b", response_lower)
               for neg in negative_keywords)


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

        # LLM-Antwort enthält einen Boss-Namen → spezifischsten (längsten)
        # Treffer wählen, nicht den ersten in der Liste (z.B. "Orkhäuptling"
        # statt "Ork").
        contained = [name for name in boss_names if name.lower() in cleaned_lower]
        if contained:
            return max(contained, key=len), False

        # Boss-Name enthält die LLM-Antwort — nur bei hinreichend langer Antwort,
        # sonst matcht ein Kürzel wie "a" jeden Namen, der diesen Buchstaben enthält.
        if len(cleaned_lower) >= 3:
            partial = [name for name in boss_names if cleaned_lower in name.lower()]
            if partial:
                return min(partial, key=len), False

    # Neuer Boss - nicht in der Liste!
    return cleaned, True


_ITEM_NAME_SYSTEM_PROMPT = (
    "Du benennst Gegenstände aus einem Inventar-Spiel. Antworte mit einem "
    "kurzen, treffenden Namen (1-3 Wörter) für den Gegenstand auf dem Bild. "
    "Nur der Name, keine Erklärung, keine Anführungszeichen. Wenn nichts "
    "Eindeutiges erkennbar ist, antworte mit 'Unbekannt'."
)


def _build_item_candidate_prompt(candidates: list[str]) -> str:
    """System-Prompt für die Auswahl aus einer geschlossenen Namensliste.

    Die Anweisung steht auf Englisch, und das ist gemessen, nicht Geschmack: mit
    dem deutschen Prompt antwortet das Modell deutsch ("Bogen", "Schwert") —
    also in einer Sprache, in der die Liste gar nicht steht, und der Abgleich
    findet nichts. Es nennt dann ausserdem nur die Art des Gegenstands, nicht
    den Gegenstand: aus derselben Vorlage wird "Bogen" statt "Godlike Bow".
    """
    return (
        "You identify items from the game Idle Clans by their inventory icon.\n"
        "You MUST answer with exactly one name copied verbatim from the "
        "CANDIDATES list below. No explanation, no markdown, just the name.\n"
        "If truly none of them fits, answer UNKNOWN.\n\n"
        "CANDIDATES:\n" + "\n".join(candidates)
    )


def _closest_candidate(name: str, candidates: list[str]) -> Optional[str]:
    """Naechster Katalogname zu einer knapp danebenliegenden Antwort.

    Auch mit geschlossener Liste erfindet ein Modell gelegentlich einen
    plausiblen Namen, den es so nicht gibt ("Pickaxe" statt "Godlike Pickaxe").
    Gemessen an 56 echten Vorlagen betraf das 3 — zu viele, um sie wegzuwerfen,
    zu wenige, um der freien Antwort zu trauen. Die Schwelle ist bewusst hoch:
    lieber kein Name als ein falscher, denn ein falscher wird gespeichert und
    zieht Kategorie und Prioritaet mit sich.
    """
    import difflib
    treffer = difflib.get_close_matches(name, candidates, n=1, cutoff=0.85)
    return treffer[0] if treffer else None


def _namens_tokens(gewuenscht: int, reasoning: bool, mit_liste: bool) -> int:
    """Wie viele Antwort-Tokens die Benennung bekommt.

    Drei Regeln, und die mittlere ist die, an der man sonst stolpert:

    * Ein ausdruecklich gesetzter Wert (`llm_max_tokens`) gewinnt — dafuer
      steht er in der Config.
    * **Mit Reasoning niemals kuerzen.** Ein Reasoning-Modell verbraucht die
      Tokens erst fuers Denken; mit 32 ist die Antwort zu Ende, bevor der Name
      kommt, und `content` bleibt leer. Genau dieser Fall steht auch in
      `_build_lmstudio_request` — dort ist er der Grund fuer den 2048er-Default.
    * Sonst reichen mit Liste 32: ein Katalogname ist ein paar Tokens lang.
      Abgeschnitten waere er nicht mehr woertlich und faende seinen eigenen
      Eintrag nicht wieder — deshalb nicht weniger.
    """
    if gewuenscht > 0:
        return gewuenscht
    if reasoning:
        return 0            # 0 = Auto, und Auto heisst mit Reasoning 2048
    return 32 if mit_liste else 0


def suggest_item_name(
    img: 'Image.Image',
    provider: str = PROVIDER_LMSTUDIO,
    endpoint: str = None,
    model: str = None,
    timeout: int = 60,
    candidates: list[str] = None,
    reasoning: bool = False,
    max_tokens: int = 0,
) -> Optional[str]:
    """Nur der Name — fuer Aufrufer, die den Grund nicht brauchen."""
    return suggest_item_name_grund(img, provider, endpoint, model, timeout,
                                   candidates, reasoning, max_tokens)[0]


def suggest_item_name_grund(
    img: 'Image.Image',
    provider: str = PROVIDER_LMSTUDIO,
    endpoint: str = None,
    model: str = None,
    timeout: int = 60,
    candidates: list[str] = None,
    reasoning: bool = False,
    max_tokens: int = 0,
) -> tuple:
    """Fragt das LLM nach einem Namen für den Gegenstand auf dem Bild.

    Mit `candidates` (den echten Item-Namen aus `katalog.py`) darf das Modell
    nur noch AUSWAEHLEN statt zu erfinden — aus "Bogen" wird "Godlike Bow".
    Zurueck kommt dann garantiert ein Name aus der Liste oder None; eine
    Antwort daneben wird einmal auf den naechsten Kandidaten gezogen und sonst
    verworfen.

    Ohne `candidates` bleibt alles wie bisher (freier Vorschlag).

    Returns:
        `(Name oder None, Grund)`. Der Grund ist "" bei einer Antwort — auch
        bei einer, die nichts erkannt hat —, sonst `TIMEOUT` oder der
        Fehlertext.

        **Ein Timeout ist nicht dasselbe wie "nicht erkannt", und beides als
        `None` zu melden war der Fehler**: an einem echten Bestand brauchten
        die ERSTEN vier Aufrufe je ueber 120 Sekunden (LM Studio laedt das
        Modell), die folgenden 3,5. Mit `llm_timeout` auf 60 fielen genau die
        ersten Items stumm durch und standen als "ohne Vorschlag" da — als
        haette das Modell sie angesehen und nichts erkannt.
    """
    if candidates:
        prompt, system_prompt = "Which item is this?", _build_item_candidate_prompt(candidates)
    else:
        prompt, system_prompt = "Wie heisst dieser Gegenstand?", _ITEM_NAME_SYSTEM_PROMPT

    success, response, _duration = analyze_image(
        img=img,
        provider=provider,
        endpoint=endpoint,
        model=model,
        prompt=prompt,
        timeout=timeout,
        system_prompt=system_prompt,
        reasoning=reasoning,
        max_tokens=_namens_tokens(max_tokens, reasoning, bool(candidates)),
    )
    if not success:
        grund = TIMEOUT if ist_timeout(response) else str(response)
        return None, grund
    name = clean_boss_name(_strip_reasoning_tags(response))
    if not name or name.lower() in ("unbekannt", "unknown", "none", "n/a"):
        return None, ""
    if candidates:
        # Woertlich aus der Liste? Sonst einmal heranziehen, sonst nichts.
        genau = {k.casefold(): k for k in candidates}.get(name.casefold())
        return (genau or _closest_candidate(name, candidates)), ""
    # Auf eine sinnvolle Länge kürzen (Modelle plappern manchmal doch)
    return name[:40].strip(), ""


def _modell_bekannt(modell: str, modelle: list) -> bool:
    """Kennt der Server dieses Modell?

    Ollama haengt an seine Namen ein Tag (`gemma3n:e4b` gegen `gemma3n`), und
    wer nur den Stamm eintraegt, meint dasselbe Modell. Verglichen wird
    deshalb der Stamm — aber nur in DIESE Richtung: ein eingetragenes
    `gemma3n:e4b` passt nicht auf ein geladenes `gemma3n:e2b`, das sind zwei.
    """
    if not modell:
        return True
    ziel = modell.casefold()
    for vorhanden in modelle:
        da = str(vorhanden or "").casefold()
        if da == ziel or da.split(":", 1)[0] == ziel:
            return True
    return False


def test_connection(provider: str = PROVIDER_LMSTUDIO,
                    endpoint: str = None, model: str = None) -> tuple[bool, str]:
    """Erreicht der Server — und kennt er das eingestellte Modell?

    **Die zweite Haelfte fehlte, und das war die wichtigere.** `model` wurde
    entgegengenommen und nie benutzt: die Lampe meldete gruen, solange
    ueberhaupt jemand antwortete, auch wenn `llm_model` gar nicht geladen war.
    Danach scheiterte jeder Aufruf, und die Auskunft darueber stand nirgends —
    man sucht den Fehler beim Bild oder beim Prompt.

    Ein erreichbarer Server ohne das eingestellte Modell ist deshalb **kein
    Erfolg**: die Frage hinter dieser Pruefung ist nicht „antwortet da wer",
    sondern „kann ich das LLM jetzt benutzen".

    Returns:
        (success: bool, message: str)
    """
    if not HTTP_AVAILABLE:
        return False, "HTTP-Bibliothek nicht verfügbar"

    if endpoint is None:
        endpoint = test_endpoint_for(provider)

    try:
        req = urllib.request.Request(endpoint, method="GET")
        with urllib.request.urlopen(req, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))

        if provider == PROVIDER_OLLAMA:
            modelle = [m.get("name", "?") for m in result.get("models", [])]
        else:
            modelle = [m.get("id", "?") for m in result.get("data", [])]

        if not modelle:
            return True, "Verbunden! Kein Modell geladen."
        if not _modell_bekannt(model, modelle):
            return False, (f"Verbunden — aber '{model}' ist nicht geladen. "
                           f"Verfügbar: {', '.join(modelle[:5])}"
                           + (" …" if len(modelle) > 5 else ""))
        if model:
            return True, f"Verbunden! '{model}' ist geladen."

        # Ohne eingestelltes Modell bleibt nur die Liste — und bei Ollama der
        # Hinweis, ob ueberhaupt eines davon Bilder lesen kann.
        if provider == PROVIDER_OLLAMA:
            sehend = [m for m in modelle if any(v in m.lower() for v in
                      ["gemma", "llava", "bakllava", "moondream", "vision", "minicpm"])]
            if sehend:
                return True, f"Verbunden! Vision-Modelle: {', '.join(sehend)}"
            return True, (f"Verbunden! Modelle: {', '.join(modelle[:5])} "
                          "(kein Vision-Modell erkannt)")
        return True, f"Verbunden! Modelle: {', '.join(modelle[:5])}"

    except urllib.error.URLError as e:
        reason = str(getattr(e, 'reason', e))
        return False, f"Nicht erreichbar: {reason}"
    except Exception as e:
        return False, f"Fehler: {e}"