"""
Der Bot: liest den Kanal, antwortet und legt Aufträge für den Hauptprozess ab.

**Ein Thread im Hauptprozess, kein eigener Prozess.** Er stirbt mit dem
Programm — ein Bot, der ein beendetes Programm überlebt, würde im Kanal
weiter „bereit“ melden. Blockieren kann er den Hauptprozess nicht: jede
Anfrage hat ein Zeitlimit, und gewartet wird nur hier.

**Er führt nichts selbst aus.** Ein `!start` wird zu einem `Order` in
`self.orders`; abgeholt wird im Main-Thread, in derselben Schleife wie die
Hotkeys (`_check_remote` in `main.py`), und ausgeführt von der kleinen
Tabelle `REMOTE_COMMANDS` in `handlers.py` — zwei Einträge, `start` und
`stop`. Der Briefkasten des Studios (`mailbox.py`) bleibt aussen vor: was
dort ankommt, kann Einstellungen schreiben und Werkzeuge starten, und
nichts davon soll aus einem Chat erreichbar sein.

**Er schreibt genau eine Datei**, seinen Zustand für das Studio
(`STATUS_FILE`). Die Freigaben liest er nur; ein Test hält beides fest.

Drei Regeln für das, was aus dem Kanal kommt:

- **Nur, wer auf der Liste steht.** Die ID entscheidet, nie der Name; wer
  nicht freigegeben ist, bekommt keine Antwort (und erfährt so nichts).
- **Nie nachfeuern.** Beim Verbinden gilt die neueste Nachricht als
  gelesen; ein Start, dessen Startzeit vorbei ist, startet nicht, und ein
  `!stop` oder `!status` von vor einer Minute meint etwas anderes als jetzt.
- **Echo nur in bereinigter Form.** Ein Wort aus dem Kanal steht in der
  Antwort nur, wenn es `clean_word()` übersteht; angepingt wird niemand.
"""

import json
import logging
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..utils import atomic_write, compact_json
from .discord import DiscordClient, DiscordError, snowflake_time
from .settings import (
    LEAD_SECONDS, SETTINGS_FILE, STATUS_FILE, RemoteSettings,
    clean_word, load_settings, sequence_for, user_allowed,
)

logger = logging.getLogger("autoclicker")

# Wie oft der Kanal gelesen wird. Bei 20 s Vorlauf bleiben selbst im
# ungünstigsten Fall 15 s — und mehrere PCs teilen sich einen Bot und damit
# dessen Anfrage-Kontingent.
POLL_INTERVAL = 5.0
# Wie oft der Thread aufwacht, um Antworten des Hauptprozesses abzuschicken.
TICK = 0.5
# Wie oft der Zustand für das Studio geschrieben wird, wenn sich nichts ändert —
# der Stempel sagt dem Reiter, dass der Thread lebt.
STATUS_INTERVAL = 5.0
# Ein `!stop`/`!status`, das älter ist, wird nicht mehr beantwortet.
MAX_AGE = 60.0
# So viel muss bis zum Start noch bleiben, sonst ist es „zu spät“.
MIN_REMAINING = 1.0
# Nach einem Fehler: warten, verdoppeln, höchstens so lange.
BACKOFF_FIRST = 5.0
BACKOFF_MAX = 60.0
# Ein falscher Token wird nicht im Sekundentakt wiederholt.
AUTH_RETRY = 300.0
# Ein laufender Lauf ohne frischen Stempel ist verwaist (wie im Live-Run).
STALE = 15.0
# Nach der Startzeit so lange auf einen Laufstatus warten.
GRACE = 20.0
SEEN_LIMIT = 20
LOG_LIMIT = 15

ORDER_START = "start"
ORDER_STOP = "stop"


@dataclass
class Order:
    """Ein Auftrag an den Hauptprozess. Mehr als diese Felder gibt es nicht."""
    command: str
    arguments: dict
    message_id: str = ""
    sender: str = ""


@dataclass
class Track:
    """Ein angenommener Start, dessen Antwortzeile mitwandert."""
    message_id: str
    reply_id: str
    sequence: str
    target: float
    phase: str = "countdown"
    text: str = ""
    stop_sent: bool = False


def parse_command(content) -> Optional[tuple]:
    """`!start raid` → ("start", "raid"); `!stop` → ("stop", ""); sonst None."""
    parts = str(content or "").strip().split()
    if not parts or not parts[0].startswith("!"):
        return None
    name = parts[0][1:].casefold()
    if name == "start":
        return ("start", parts[1] if len(parts) > 1 else "")
    if name in ("stop", "status"):
        return (name, "")
    return None


def discord_time(stamp: float) -> str:
    """Eine Uhrzeit, die Discord jedem Leser in SEINER Zeitzone zeigt."""
    return f"<t:{int(stamp)}:T>"


def _author_name(author: dict) -> str:
    return str(author.get("global_name") or author.get("username") or "?")[:40]


# Nachrichtenarten, die ein Mensch tippt: normal (0) und als Antwort (19).
# Alles andere (jemand ist beigetreten, eine Nachricht wurde angeheftet …)
# trägt keinen Text und ist kein Befehl.
_TYPED = (0, 19)


def looks_stripped(message: dict) -> bool:
    """Leer, obwohl ein Mensch geschrieben hat — fehlt der Inhalts-Schalter?

    Ohne „Message Content Intent“ liefert Discord Text, Anhänge und Einbettungen
    leer aus. Eine Nachricht, an der gar nichts dran ist, gibt es sonst nicht.
    """
    return not any(message.get(k) for k in
                   ("content", "attachments", "embeds", "sticker_items", "components"))


def describe_run(track: Track, status: Optional[dict], now: float) -> tuple:
    """(Phase, Antwortzeile) eines angenommenen Starts, aus dem Laufstatus.

    Geändert wird die Zeile nur beim Phasenwechsel — Klickzahlen im
    Fünf-Sekunden-Takt nachzutragen hiesse, Discords Grenze für Änderungen
    mit Rauschen zu verbrauchen.
    """
    seq = track.sequence
    mine = isinstance(status, dict) and status.get("sequence") == seq
    if mine and status.get("countdown"):
        return "countdown", f"⏳ `{seq}` startet um {discord_time(track.target)}"
    if mine and status.get("active"):
        if now - float(status.get("stamp") or 0) > STALE:
            return "lost", f"⚠️ `{seq}` meldet sich nicht mehr"
        return "running", f"▶️ `{seq}` läuft seit {discord_time(track.target)}"
    if mine and float(status.get("end") or 0) >= track.target - 2:
        counters = status.get("counters") or {}
        reason = str(status.get("reason") or "")
        return "done", (f"✅ `{seq}` fertig — {status.get('elapsed_cycles', 0)} Zyklen, "
                        f"{counters.get('clicks', 0)} Klicks" + (f" ({reason})" if reason else ""))
    if now < track.target - 0.5:
        return "aborted", f"⏹️ `{seq}` abgebrochen, bevor es losging"
    if now - track.target > GRACE:
        return "lost", f"⚠️ `{seq}` — kein Laufstatus"
    return track.phase, track.text


def status_line(settings: RemoteSettings, status: Optional[dict], now: float) -> str:
    """Die Antwort auf `!status`: was läuft, und welche Wörter hier gelten."""
    words = ", ".join(f"`{w.word}`" for w in settings.words) or "keine"
    status = status if isinstance(status, dict) else {}
    seq = str(status.get("sequence") or "")
    if status.get("countdown"):
        what = f"⏳ `{seq}` startet um {discord_time(float(status.get('target_time') or 0))}"
    elif status.get("active") and now - float(status.get("stamp") or 0) <= STALE:
        clicks = (status.get("counters") or {}).get("clicks", 0)
        what = f"▶️ `{seq}` läuft — {clicks} Klicks"
    else:
        what = "💤 bereit"
    return f"{what} · Wörter: {words}"


class RemoteBot:
    """Ein Durchgang ist `step()`; `run()` wiederholt ihn, bis `stop()`."""

    def __init__(self, run_status_path, settings_path=None, status_path=None,
                 client_factory=DiscordClient, clock=time.time):
        self.orders: "queue.Queue[Order]" = queue.Queue()
        self.answers: queue.Queue = queue.Queue()
        self._run_path = Path(run_status_path)
        self._settings_path = Path(settings_path or SETTINGS_FILE)
        self._status_path = Path(status_path or STATUS_FILE)
        self._client_factory = client_factory
        self._clock = clock
        self._halt = threading.Event()
        self.settings = RemoteSettings()
        self._settings_stamp = None
        self._connection = None
        self.client: Optional[DiscordClient] = None
        self.me_id = ""
        self.me_name = ""
        self.channel_name = ""
        self.after: Optional[str] = None
        self.error = ""
        self.retry_at = 0.0
        self.backoff = 0.0
        self.next_poll = 0.0
        self.last_poll = 0.0
        self.content_missing = False
        self.seen: list = []
        self.log: list = []
        self.track: Optional[Track] = None
        self._status_written = 0.0

    # ------------------------------------------------------------ Hauptprozess

    def fetch_order(self) -> Optional[Order]:
        """Für den Main-Thread: der nächste Auftrag, oder None."""
        try:
            return self.orders.get_nowait()
        except queue.Empty:
            return None

    def answer(self, order: Order, ok: bool, text: str, sequence: str = "") -> None:
        """Für den Main-Thread: was aus dem Auftrag wurde — der Bot sagt es im Kanal."""
        self.answers.put((order, bool(ok), str(text), str(sequence)))

    def fetch_answer(self) -> Optional[tuple]:
        try:
            return self.answers.get_nowait()
        except queue.Empty:
            return None

    # ------------------------------------------------------------ Schleife

    def run(self) -> None:
        while not self._halt.is_set():
            try:
                wait = self.step()
            except Exception as e:                               # noqa: BLE001
                # Ein Fehler hier darf den Thread nicht still beenden — dann
                # stünde der Fernstart im Studio als „verbunden“ und täte nichts.
                logger.exception("Fernstart: Durchgang fehlgeschlagen")
                self.error = f"interner Fehler: {type(e).__name__}: {e}"
                self._disconnect()
                wait = BACKOFF_MAX
            self._halt.wait(wait)

    def stop(self) -> None:
        self._halt.set()

    def step(self) -> float:
        """Ein Durchgang. Gibt zurück, wie lange bis zum nächsten gewartet wird."""
        self._reload_settings()
        now = self._clock()
        if not self.settings.ready():
            self._disconnect()
            self.track = None
            # Was der Hauptprozess inzwischen beantwortet hat, ginge an einen
            # Kanal, den es nicht mehr gibt — und später nachgereicht wäre es
            # eine Antwort auf eine Frage von gestern.
            while self.fetch_answer() is not None:
                pass
            self._write_status()
            return 2.0
        if now >= self.retry_at:
            try:
                self._exchange(now)
                self.error = ""
                self.backoff = 0.0
            except DiscordError as e:
                self._failed(e, now)
        self._write_status()
        return TICK

    def _exchange(self, now: float) -> None:
        if self.client is None:
            self._connect()
        self._drain_answers()
        if now >= self.next_poll:
            self.next_poll = now + POLL_INTERVAL
            self._poll()
            self._watch(now)
            self.last_poll = now

    def _failed(self, error: DiscordError, now: float) -> None:
        if error.status == 401:
            self.error = "Der Token wird nicht angenommen — im Studio neu eintragen."
            self.retry_at = now + AUTH_RETRY
        elif error.status in (403, 404):
            # 403 kommt auch beim Antworten, wenn der Bot lesen, aber nicht
            # schreiben darf — der Satz nennt deshalb beide Rechte.
            self.error = (f"Kanal nicht erreichbar oder Rechte fehlen ({error.message}) — "
                          f"ist der Bot im Server, und darf er den Kanal lesen, darin "
                          f"schreiben und reagieren?")
            self.retry_at = now + BACKOFF_MAX
        else:
            self.backoff = min(BACKOFF_MAX, (self.backoff * 2) or BACKOFF_FIRST)
            self.error = f"{error.message} — neuer Versuch in {self.backoff:g} s"
            self.retry_at = now + self.backoff
        self._disconnect()

    # ------------------------------------------------------------ Einstellungen

    def _reload_settings(self) -> None:
        try:
            stamp = self._settings_path.stat().st_mtime_ns
        except OSError:
            stamp = None
        if stamp == self._settings_stamp:
            return
        self._settings_stamp = stamp
        self.settings = load_settings(self._settings_path)
        # Neuer Token oder anderer Kanal: neu verbinden, und ein alter Fehler
        # („Token wird nicht angenommen“) gilt nicht mehr.
        if (self.settings.token, self.settings.channel_id) != self._connection:
            self._disconnect()
            self.track = None
            self.retry_at = 0.0
            self.error = ""

    # ------------------------------------------------------------ Verbindung

    def _connect(self) -> None:
        client = self._client_factory(self.settings.token)
        me = client.me()
        channel = client.channel(self.settings.channel_id)
        recent = client.messages(self.settings.channel_id, limit=50)
        self.me_id = str(me.get("id") or "")
        self.me_name = str(me.get("username") or "")
        self.channel_name = str(channel.get("name") or "")
        # **Was schon im Kanal steht, ist gelesen.** Nur die Absender merken —
        # damit das Studio sie zum Freigeben anbieten kann —, nichts ausführen.
        ids = [str(m.get("id")) for m in recent if str(m.get("id") or "").isdigit()]
        self.after = max(ids, key=int) if ids else None
        for message in reversed(recent):
            self._remember((message.get("author") or {}), message.get("id"))
        self.client = client
        self._connection = (self.settings.token, self.settings.channel_id)
        self.next_poll = 0.0

    def _disconnect(self) -> None:
        # Ein angenommener Start bleibt verfolgt: eine kurze Netzstörung
        # ändert nichts daran, dass der Lauf läuft und seine Zeile fertig
        # werden soll. Weg ist er erst, wenn sich die Verbindung selbst ändert.
        self.client = None
        self._connection = None

    # ------------------------------------------------------------ Lesen

    def _poll(self) -> None:
        messages = self.client.messages(self.settings.channel_id, after=self.after)
        for message in sorted(messages, key=lambda m: int(m.get("id") or 0)):
            self.after = str(message.get("id"))
            self._handle(message)

    def _handle(self, message: dict) -> None:
        author = message.get("author") or {}
        if author.get("bot") or str(author.get("id") or "") == self.me_id:
            return
        if message.get("type", 0) not in _TYPED:
            return
        self._remember(author, message.get("id"))
        if looks_stripped(message):
            self.content_missing = True
            return
        self.content_missing = False
        parsed = parse_command(message.get("content"))
        if parsed is None:
            return
        kind, word = parsed
        if not user_allowed(self.settings, str(author.get("id") or "")):
            self._note(_author_name(author), f"!{kind} ignoriert — nicht freigegeben", False)
            return
        {"start": self._on_start, "stop": self._on_stop,
         "status": self._on_status}[kind](message, author, word)

    def _age(self, message: dict) -> float:
        return self._clock() - snowflake_time(message.get("id"))

    def _order(self, command: str, message_id, author: dict, **arguments) -> None:
        """Legt einen Auftrag ab — Absender als Name UND als ID: der
        Hauptprozess prüft die Freigabe selbst noch einmal."""
        name = _author_name(author)
        arguments.update(sender=name, sender_id=str(author.get("id") or ""))
        self.orders.put(Order(command, arguments, message_id=str(message_id), sender=name))

    def _on_start(self, message: dict, author: dict, raw_word: str) -> None:
        name = _author_name(author)
        word = clean_word(raw_word)
        if not word:
            self._reply(message.get("id"), "❓ Welches Wort? `!start <wort>`")
            return
        target = snowflake_time(message.get("id")) + LEAD_SECONDS
        if sequence_for(self.settings, word) is None:
            self._note(name, f"!start {word} — hier nicht freigegeben", False)
            self._reply(message.get("id"), f"❌ `{word}` ist hier nicht freigegeben")
            return
        if target - self._clock() < MIN_REMAINING:
            self._note(name, f"!start {word} — zu spät gesehen", False)
            self._reply(message.get("id"), f"⏰ `{word}` zu spät gesehen — nicht gestartet")
            return
        self._note(name, f"!start {word} — an den Hauptprozess", True)
        self._order(ORDER_START, message.get("id"), author, word=word, target=target)

    def _on_stop(self, message: dict, author: dict, _word: str) -> None:
        if self._age(message) > MAX_AGE:
            return
        self._note(_author_name(author), "!stop — an den Hauptprozess", True)
        self._order(ORDER_STOP, message.get("id"), author)

    def _on_status(self, message: dict, _author: dict, _word: str) -> None:
        if self._age(message) > MAX_AGE:
            return
        self._reply(message.get("id"),
                    status_line(self.settings, self._run_status(), self._clock()))

    # ------------------------------------------------------------ Antworten

    def _reply(self, message_id, text: str) -> dict:
        content = f"**{self.settings.display_name()}**: {text}"
        return self.client.send(self.settings.channel_id, content, reply_to=message_id)

    def _drain_answers(self) -> None:
        while True:
            item = self.fetch_answer()
            if item is None:
                return
            order, ok, text, sequence = item
            self._note(order.sender, text, ok)
            reply = self._reply(order.message_id, text)
            if ok and order.command == ORDER_START and sequence:
                self._track(order, reply, sequence, text)

    def _track(self, order: Order, reply: dict, sequence: str, text: str) -> None:
        self.track = Track(message_id=order.message_id, reply_id=str(reply.get("id") or ""),
                           sequence=sequence, target=float(order.arguments.get("target") or 0),
                           text=text)
        try:
            self.client.react(self.settings.channel_id, order.message_id)
        except DiscordError:
            # Ohne Reaktion bleibt `!stop` — kein Grund, den Start zu verwerfen.
            pass

    # ------------------------------------------------------------ Mitlaufen

    def _run_status(self) -> Optional[dict]:
        try:
            data = json.loads(self._run_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def _watch(self, now: float) -> None:
        track = self.track
        if track is None:
            return
        phase, text = describe_run(track, self._run_status(), now)
        if text != track.text and track.reply_id:
            self.client.edit(self.settings.channel_id, track.reply_id,
                             f"**{self.settings.display_name()}**: {text}")
        track.phase, track.text = phase, text
        if phase in ("done", "aborted", "lost"):
            self.track = None
            return
        self._check_stop_reaction(track)

    def _check_stop_reaction(self, track: Track) -> None:
        """🛑 unter dem Start — von jemandem auf der Liste — hält den Lauf an."""
        if track.stop_sent:
            return
        for user in self.client.reactions(self.settings.channel_id, track.message_id):
            if user.get("bot") or not user_allowed(self.settings, str(user.get("id") or "")):
                continue
            self._note(_author_name(user), "🛑 — an den Hauptprozess", True)
            self._order(ORDER_STOP, track.message_id, user)
            track.stop_sent = True
            return

    # ------------------------------------------------------------ Zustand fürs Studio

    def _remember(self, author: dict, message_id) -> None:
        user_id = str(author.get("id") or "")
        if not user_id or author.get("bot") or user_id == self.me_id:
            return
        try:
            at = snowflake_time(message_id)
        except (TypeError, ValueError):
            at = self._clock()
        self.seen = [s for s in self.seen if s["id"] != user_id]
        self.seen.insert(0, {"id": user_id, "name": _author_name(author), "at": at})
        del self.seen[SEEN_LIMIT:]

    def _note(self, who: str, text: str, ok: bool) -> None:
        self.log.insert(0, {"at": self._clock(), "who": who, "text": text, "ok": ok})
        del self.log[LOG_LIMIT:]
        self._status_written = 0.0

    def snapshot(self) -> dict:
        offset = self.client.clock_offset if self.client is not None else None
        return {
            "enabled": self.settings.enabled,
            "ready": self.settings.ready(),
            "connected": self.client is not None,
            "bot_name": self.me_name,
            "channel_name": self.channel_name,
            "error": self.settings.error or self.error,
            "last_poll": self.last_poll,
            "clock_offset": offset,
            "content_missing": self.content_missing,
            "seen": self.seen,
            "log": self.log,
            "stamp": self._clock(),
        }

    def _write_status(self) -> None:
        now = self._clock()
        if now - self._status_written < STATUS_INTERVAL:
            return
        self._status_written = now
        try:
            atomic_write(self._status_path, compact_json(self.snapshot()))
        except (OSError, TypeError, ValueError):
            pass


def start_bot(run_status_path) -> RemoteBot:
    """Startet den Bot als Hintergrund-Thread. Ohne Freigaben schläft er nur."""
    bot = RemoteBot(run_status_path)
    threading.Thread(target=bot.run, daemon=True, name="remote-bot").start()
    return bot
