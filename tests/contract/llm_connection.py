"""LLM-Aufruf und Verbindungsprüfung, vor dem Zerlegen festgehalten.

`analyze_image` trug vier Fehlerzweige mit je eigener Meldung, und
`test_connection` hatte gar keinen Test: die Lampe im Studio lebt davon, dass
genau diese Texte und Wahrheitswerte herauskommen. Das HTTP ist gestubbt, das
Bild auch — es geht um die Entscheidungen, nicht um Pillow.
"""
from ._harness import check, section

import contextlib as _cl
import json as _json
import socket as _socket

import autoclicker.llm_vision as _LV
from autoclicker.config import CONFIG as _CFG


class _Answer:
    def __init__(self, payload):
        self._raw = (payload if isinstance(payload, bytes)
                     else _json.dumps(payload).encode("utf-8"))

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@_cl.contextmanager
def _server(answer):
    """`answer` ist eine Antwort (dict/bytes) oder eine Ausnahme; die Anfragen landen in `sent`."""
    sent = []

    def urlopen(req, timeout=None):
        sent.append((req, timeout))
        if isinstance(answer, BaseException):
            raise answer
        return _Answer(answer)

    saved = (_LV.urllib.request.urlopen, _LV._image_to_base64, _CFG.llm_debug)
    _LV.urllib.request.urlopen = urlopen
    _LV._image_to_base64 = lambda img: "QUJD"
    _CFG.llm_debug = False
    try:
        yield sent
    finally:
        _LV.urllib.request.urlopen, _LV._image_to_base64, _CFG.llm_debug = saved


_CHOICE = {"choices": [{"message": {"content": "  Kraken  "}}]}

# =============================================================================
section("LLM-Aufruf: Vorgaben je Anbieter")
# =============================================================================
with _server(_CHOICE) as _sent:
    _ok = _LV.analyze_image(object(), provider="lmstudio", timeout=9)
_req, _timeout = _sent[0]
_body = _json.loads(_req.data.decode("utf-8"))
check("LM Studio: Antwort getrimmt, Erfolg", _ok[0] is True and _ok[1] == "Kraken")
check("ohne Endpunkt der Chat-Endpunkt des Anbieters",
      _req.full_url == _LV.chat_endpoint("lmstudio"))
check("ohne Modell das Standardmodell von LM Studio",
      _body["model"] == "google/gemma-4-12b-qat")
check("die Zeitgrenze geht an den Aufruf", _timeout == 9)
check("ohne Prompt die Boss-Frage", "Welcher Boss" in _req.data.decode("utf-8"))

with _server({"message": {"content": "Hydra"}}) as _sent:
    _ok = _LV.analyze_image(object(), provider="ollama", endpoint="http://x/api/chat")
_body = _json.loads(_sent[0][0].data.decode("utf-8"))
check("Ollama: eigenes Standardmodell und eigener Endpunkt",
      _body["model"] == "gemma3n:e4b" and _sent[0][0].full_url == "http://x/api/chat")
check("und die Ollama-Antwort wird gelesen", _ok[:2] == (True, "Hydra"))

_ok = _LV.analyze_image(object(), provider="openai")
check("ein unbekannter Anbieter wird abgelehnt, ohne Aufruf",
      _ok[0] is False and _ok[1].startswith("Unbekannter Provider: openai") and _ok[2] == 0.0)

# =============================================================================
section("LLM-Aufruf: jeder Fehler hat seinen Text")
# =============================================================================
with _server(_socket.timeout()):
    _ok = _LV.analyze_image(object(), provider="lmstudio", timeout=7)
check("Zeitüberschreitung: 'Timeout nach 7s', als Timeout erkannt",
      _ok[0] is False and _ok[1] == "Timeout nach 7s" and _LV.is_timeout(_ok[1]))
with _server(_LV.urllib.error.URLError("kein Server")):
    _ok = _LV.analyze_image(object(), provider="lmstudio")
check("kein Server: Verbindungsfehler mit Grund",
      _ok[:2] == (False, "Verbindungsfehler: kein Server") and not _LV.is_timeout(_ok[1]))
with _server(b"kein json"):
    _ok = _LV.analyze_image(object(), provider="lmstudio")
check("kaputte Antwort: Antwort-Fehler", _ok[0] is False and _ok[1].startswith("Antwort-Fehler: "))
with _server({"choices": []}):
    _ok = _LV.analyze_image(object(), provider="lmstudio")
# Kein Fehler, sondern eine leere Antwort: was sie bedeutet, entscheidet der
# Aufrufer (die Mitschrift nennt dann die möglichen Ursachen).
check("Antwort ohne Auswahl: Erfolg mit leerem Text", _ok[:2] == (True, ""))
with _server(RuntimeError("kaputt")):
    _ok = _LV.analyze_image(object(), provider="lmstudio")
check("alles andere: 'Fehler: …'", _ok[:2] == (False, "Fehler: kaputt"))
check("auch ein Fehlschlag misst seine Dauer", isinstance(_ok[2], float) and _ok[2] >= 0)

# =============================================================================
section("Verbindungsprüfung: Server UND Modell")
# =============================================================================


def _connect(answer, provider="ollama", model=None):
    with _server(answer) as sent:
        result = _LV.test_connection(provider, model=model)
    return result, sent


_res, _sent = _connect({"models": []})
check("ohne geladenes Modell: verbunden, mit Hinweis",
      _res == (True, "Verbunden! Kein Modell geladen."))
check("geprüft wird am Test-Endpunkt des Anbieters",
      _sent[0][0].full_url == _LV.test_endpoint_for("ollama") and _sent[0][1] == 5)

_OLLAMA = {"models": [{"name": n} for n in ("llama3:8b", "gemma3n:e4b", "qwen", "phi", "mistral", "tiny")]}
_res, _ = _connect(_OLLAMA, model="gemma3n")
check("der Stamm genügt bei Ollama", _res == (True, "Verbunden! 'gemma3n' ist geladen."))
_res, _ = _connect(_OLLAMA, model="llava")
check("ein fehlendes Modell ist KEIN Erfolg",
      _res[0] is False and "'llava' ist nicht geladen" in _res[1])
check("die Liste nennt fünf und deutet den Rest an",
      _res[1].endswith("llama3:8b, gemma3n:e4b, qwen, phi, mistral …"))
_res, _ = _connect({"models": [{"name": "a"}, {"name": "b"}]}, model="c")
check("bei höchstens fünf ohne Auslassung", _res[1].endswith("Verfügbar: a, b"))

_res, _ = _connect(_OLLAMA)
check("ohne Modell bei Ollama: die Bild-fähigen werden genannt",
      _res == (True, "Verbunden! Vision-Modelle: gemma3n:e4b"))
_res, _ = _connect({"models": [{"name": "llama3"}, {"name": "phi"}]})
check("und gesagt, wenn keines Bilder liest",
      _res == (True, "Verbunden! Modelle: llama3, phi (kein Vision-Modell erkannt)"))
_res, _ = _connect({"data": [{"id": "m1"}, {"id": "m2"}]}, provider="lmstudio")
check("LM Studio liest `data[].id` und nennt die Liste",
      _res == (True, "Verbunden! Modelle: m1, m2"))
_res, _ = _connect({"data": [{"id": "m1"}]}, provider="lmstudio", model="m1")
check("LM Studio mit Modell", _res == (True, "Verbunden! 'm1' ist geladen."))

_res, _ = _connect(_LV.urllib.error.URLError("verweigert"))
check("kein Server: nicht erreichbar", _res == (False, "Nicht erreichbar: verweigert"))
_res, _ = _connect(b"<html>")
check("eine fremde Antwort: Fehler statt Absturz", _res[0] is False and _res[1].startswith("Fehler: "))
