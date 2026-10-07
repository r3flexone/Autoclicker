"""
Die Verbindung zu Discord — HTTPS mit `urllib`, ohne Fremdpaket.

**Warum keine Bibliothek (`discord.py`).** Gebraucht werden sieben Anfragen:
wer bin ich, welcher Kanal, was ist neu, antworten, Antwort ändern, Reaktion
setzen, Reaktionen lesen. Eine Bibliothek brächte dafür asyncio, aiohttp und
eine Dauerverbindung mit — und vor allem fremden Code, der die Daten aus dem
Netz verarbeitet. Hier läuft dazwischen nur die Standardbibliothek. Dieselbe
Entscheidung wie in `llm_vision.py`.

**Warum Abfragen statt Dauerverbindung.** Ein Knopf-Klick (Interaktion) geht
nur an EINE Verbindung des Bots; teilen sich mehrere PCs einen Bot, erführen
die anderen nichts davon. Eine Nachricht im Kanal lesen dagegen alle — und nur
eine Nachricht trägt den Zeitstempel, aus dem alle dieselbe Startzeit rechnen.

Die Verbindung geht immer von hier aus, wie ein Browser: kein offener Port,
nichts, was sich von aussen zu diesem PC verbindet.
"""

import email.utils
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

API = "https://discord.com/api/v10"
# Discord verlangt diese Form; mit dem Standard-Agenten von urllib weist die
# vorgeschaltete Firewall die Anfrage ab, bevor sie Discord erreicht.
USER_AGENT = "DiscordBot (https://github.com/r3flexone/Autoclicker, 1.0)"
# Millisekunden seit 1970 am Beginn der Discord-Zeitrechnung (2015-01-01).
DISCORD_EPOCH_MS = 1420070400000
# Die Reaktion, die einen Lauf anhält. Ein einzelnes Zeichen ohne
# Variantenauswahl — bei ⏹ (mit U+FE0F) hängt am Zeichen, ob Discord es als
# dasselbe Emoji erkennt.
STOP_EMOJI = "\U0001F6D1"
# Wie lange eine Anfrage höchstens dauern darf. Der Bot läuft in einem eigenen
# Thread; ein Hänger hält dort nur das Abfragen auf, nie den Hauptprozess.
TIMEOUT = 10.0
# Eine Nachricht darf 2000 Zeichen haben; eine Antwort des Bots ist eine Zeile.
MAX_CONTENT = 1900


class DiscordError(Exception):
    """Eine Anfrage ist gescheitert. `status` 0 heisst: gar keine Antwort."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def snowflake_time(snowflake) -> float:
    """Wann eine Discord-ID entstand, in Sekunden seit 1970.

    Die oberen Bits jeder ID sind der Zeitstempel in Millisekunden — genauer
    als das ISO-Feld `timestamp` und ohne Datumsformat, das man parsen müsste.
    """
    return ((int(snowflake) >> 22) + DISCORD_EPOCH_MS) / 1000.0


def _snowflake(value) -> str:
    """Eine ID, die in einen Pfad darf — nur Ziffern, sonst ein Fehler."""
    text = str(value or "")
    if not text.isdigit():
        raise DiscordError(0, f"ungültige ID {text!r}")
    return text


def _error_text(error: urllib.error.HTTPError) -> str:
    try:
        data = json.loads(error.read() or b"{}")
    except (ValueError, OSError):
        data = {}
    message = data.get("message") if isinstance(data, dict) else None
    return f"HTTP {error.code}: {message or error.reason}"


def _retry_after(error: urllib.error.HTTPError) -> float:
    """Wie lange Discord nach 429 warten lässt — gedeckelt, damit nichts hängt."""
    try:
        data = json.loads(error.read() or b"{}")
        wait = float(data.get("retry_after", 1.0))
    except (ValueError, OSError, TypeError, AttributeError):
        wait = 1.0
    return min(max(wait, 0.5), 30.0)


class DiscordClient:
    """Die sieben Anfragen, die der Fernstart braucht.

    `opener` und `sleep` sind austauschbar, damit die Suite ohne Netz prüfen
    kann, was gesendet wird.
    """

    def __init__(self, token: str, opener=None, sleep=time.sleep, clock=time.time):
        self.token = token
        self._open = opener or urllib.request.urlopen
        self._sleep = sleep
        self._clock = clock
        # Discord-Uhr minus eigene Uhr, aus dem `Date`-Kopf der letzten Antwort.
        # Auf die Sekunde genau, mehr gibt der Kopf nicht her — genug, um eine
        # falsch gehende Uhr zu bemerken, nicht genug, um sie zu korrigieren.
        self.clock_offset: Optional[float] = None

    # ------------------------------------------------------------ Anfragen

    def _build(self, method: str, path: str, body) -> urllib.request.Request:
        headers = {"Authorization": f"Bot {self.token}", "User-Agent": USER_AGENT}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif method in ("PUT", "POST", "PATCH"):
            # Ohne Körper verlangt Discord trotzdem eine Länge (0).
            data = b""
        return urllib.request.Request(API + path, data=data, headers=headers, method=method)

    def _note_clock(self, headers) -> None:
        try:
            stamp = email.utils.parsedate_to_datetime(headers.get("Date")).timestamp()
        except (TypeError, ValueError, AttributeError):
            return
        # Der Kopf ist auf die Sekunde abgeschnitten — die Mitte ist der beste Schätzer.
        self.clock_offset = stamp + 0.5 - self._clock()

    def request(self, method: str, path: str, body=None):
        """Eine Anfrage; bei 429 wird gewartet und bis zu zweimal wiederholt."""
        for _attempt in range(3):
            try:
                with self._open(self._build(method, path, body), timeout=TIMEOUT) as answer:
                    self._note_clock(answer.headers)
                    raw = answer.read()
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    self._sleep(_retry_after(e))
                    continue
                raise DiscordError(e.code, _error_text(e)) from None
            except (urllib.error.URLError, OSError) as e:
                raise DiscordError(0, f"keine Verbindung: {getattr(e, 'reason', e)}") from None
            try:
                return json.loads(raw) if raw else None
            except ValueError:
                raise DiscordError(0, "Antwort ist kein JSON") from None
        raise DiscordError(429, "zu viele Anfragen — Discord bremst")

    # ------------------------------------------------------------ Gegenstände

    def me(self) -> dict:
        return self.request("GET", "/users/@me") or {}

    def channel(self, channel_id) -> dict:
        return self.request("GET", f"/channels/{_snowflake(channel_id)}") or {}

    def messages(self, channel_id, after=None, limit: int = 50) -> list:
        query = {"limit": max(1, min(int(limit), 100))}
        if after:
            query["after"] = _snowflake(after)
        path = f"/channels/{_snowflake(channel_id)}/messages?{urllib.parse.urlencode(query)}"
        answer = self.request("GET", path)
        return answer if isinstance(answer, list) else []

    def send(self, channel_id, content: str, reply_to=None) -> dict:
        body = {"content": str(content)[:MAX_CONTENT],
                # Niemand wird angepingt — auch nicht, wenn ein Name aus dem
                # Kanal in der Antwort steht.
                "allowed_mentions": {"parse": []}}
        if reply_to:
            body["message_reference"] = {"message_id": _snowflake(reply_to),
                                         "fail_if_not_exists": False}
        return self.request("POST", f"/channels/{_snowflake(channel_id)}/messages", body) or {}

    def edit(self, channel_id, message_id, content: str) -> dict:
        body = {"content": str(content)[:MAX_CONTENT], "allowed_mentions": {"parse": []}}
        path = f"/channels/{_snowflake(channel_id)}/messages/{_snowflake(message_id)}"
        return self.request("PATCH", path, body) or {}

    def _reaction_path(self, channel_id, message_id, emoji: str) -> str:
        return (f"/channels/{_snowflake(channel_id)}/messages/{_snowflake(message_id)}"
                f"/reactions/{urllib.parse.quote(emoji)}")

    def react(self, channel_id, message_id, emoji: str = STOP_EMOJI) -> None:
        self.request("PUT", self._reaction_path(channel_id, message_id, emoji) + "/@me")

    def reactions(self, channel_id, message_id, emoji: str = STOP_EMOJI) -> list:
        answer = self.request("GET", self._reaction_path(channel_id, message_id, emoji)
                              + "?limit=100")
        return answer if isinstance(answer, list) else []
