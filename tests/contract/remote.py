"""Fernstart über Discord: wer was auf diesem PC starten darf — und was nicht.

Gemessen wird ohne Netz: der Bot läuft gegen einen nachgebauten Kanal
(`_Channel`), die Verbindung gegen einen nachgebauten Server (`_opener`). So
lassen sich genau die Fälle stellen, um die es geht — der fremde Absender,
das nicht freigegebene Wort, der zu spät gesehene Start, der alte `!stop`.

Dazu die Grenze, an der die Sicherheit hängt, von beiden Seiten: der Bot
erreicht keine Speicherfunktion und keinen Briefkasten-Befehl, und der
Hauptprozess glaubt ihm nicht, sondern prüft die Freigabe selbst noch einmal.
"""
from ._harness import check, section, studio_web_source, REPO

import ast as _ast
import contextlib as _cl
import io as _io
import json as _json
import os as _os
import tempfile as _tmp
import time as _time
import urllib.error as _ue
import zipfile as _zip
from pathlib import Path

from autoclicker.remote import settings as _rs
from autoclicker.remote import bot as _bot
from autoclicker.remote.discord import (
    DiscordClient as _DC, DiscordError as _DE, STOP_EMOJI as _STOP, snowflake_time as _snow_t,
)

_OWNER = "111111111111111111"
_FRIEND = "222222222222222222"
_STRANGER = "333333333333333333"
_ME = "900000000000000001"
_CHANNEL = "444444444444444444"
_TOKEN = "MTIz" + "a" * 20 + ".Gh1234." + "b" * 30


def _quiet(fn, *args):
    with _cl.redirect_stdout(_io.StringIO()):
        return fn(*args)


_counter = [0]


def _snowflake(stamp: float) -> str:
    """Eine Discord-ID zu einem Zeitpunkt — eindeutig auch bei gleicher Zeit."""
    _counter[0] += 1
    return str(((int(stamp * 1000) - 1420070400000) << 22) + _counter[0])


def _settings(**changes) -> _rs.RemoteSettings:
    base = dict(enabled=True, token=_TOKEN, channel_id=_CHANNEL, pc_name="Alex",
                users=[_rs.RemoteUser(_OWNER, "Alex"), _rs.RemoteUser(_FRIEND, "Ben")],
                words=[_rs.RemoteWord("raid", "Raid")])
    base.update(changes)
    return _rs.RemoteSettings(**base)


_sandbox = _tmp.mkdtemp(prefix="fernstart_")
_cwd = _os.getcwd()
_os.chdir(_sandbox)
try:
    # -----------------------------------------------------------------------
    section("Fernstart: die Freigaben in remote.json")

    _loaded = _rs.load_settings()
    check("ohne Datei ist der Fernstart aus — und das ist kein Fehler",
          _loaded.enabled is False and _loaded.error == "" and not _loaded.ready())

    _rs.save_settings(_rs.RemoteSettings(
        enabled=True, token="Bot " + _TOKEN, channel_id=_CHANNEL,
        users=[_rs.RemoteUser(_OWNER, "Alex"), _rs.RemoteUser(_OWNER, "doppelt")],
        words=[_rs.RemoteWord("raid", "Raid")]))
    _raw = _json.loads(Path(_rs.SETTINGS_FILE).read_text(encoding="utf-8"))
    _raw["words"].append({"word": "Raid", "sequence": "Zweite"})
    _raw["words"].append({"word": "zwei worte", "sequence": "X"})
    _raw["users"].append({"id": "kein-id", "name": "x"})
    Path(_rs.SETTINGS_FILE).write_text(_json.dumps(_raw), encoding="utf-8")
    _loaded = _rs.load_settings()
    check("ein Token mit „Bot “ davor wird bereinigt, nicht abgelehnt",
          _loaded.token == _TOKEN)
    check("ein Wort gilt nur einmal, ohne Rücksicht auf Gross/Klein",
          [(w.word, w.sequence) for w in _loaded.words] == [("raid", "Raid")])
    check("kaputte Einträge fallen einzeln heraus, eine ID gilt einmal",
          [u.id for u in _loaded.users] == [_OWNER])
    check("startbereit erst mit Schalter, Token und Kanal", _loaded.ready())

    check("ein Wort ist kurz und ohne Leerzeichen",
          _rs.clean_word(" Raid ") == "raid" and _rs.clean_word("ra id") == ""
          and _rs.clean_word("x" * 25) == "" and _rs.clean_word("`raid`") == "")
    check("die Freigabe sucht das Wort ohne Gross/Klein",
          _rs.sequence_for(_loaded, "RAID") == "Raid" and _rs.sequence_for(_loaded, "farm") is None)
    check("entscheidend ist die ID, nie der Name",
          _rs.user_allowed(_loaded, _OWNER) and not _rs.user_allowed(_loaded, "Alex")
          and not _rs.user_allowed(_loaded, ""))
    check("ein Token-Fetzen ist kein Token", _rs.clean_token("abc") == "")

    Path(_rs.SETTINGS_FILE).write_text("{kaputt", encoding="utf-8")
    _broken = _rs.load_settings()
    check("eine unlesbare Datei wird gemeldet, nicht als leer gelesen",
          _broken.error != "" and not _broken.ready())
    check("und nicht überschrieben — darin steht ein Token",
          _rs.save_settings(_broken) is False
          and Path(_rs.SETTINGS_FILE).read_text(encoding="utf-8") == "{kaputt")
    Path(_rs.SETTINGS_FILE).unlink()

    # -----------------------------------------------------------------------
    section("Fernstart: was aus einer Nachricht wird")

    check("!start mit Wort", _bot.parse_command("!start raid") == ("start", "raid"))
    check("Gross/Klein am Befehl egal", _bot.parse_command("!START Raid") == ("start", "Raid"))
    check("!start ohne Wort wird gefragt, nicht ignoriert",
          _bot.parse_command("!start") == ("start", ""))
    check("!stop und !status", _bot.parse_command(" !stop ") == ("stop", "")
          and _bot.parse_command("!status") == ("status", ""))
    check("alles andere ist kein Befehl",
          _bot.parse_command("start raid") is None and _bot.parse_command("!quit") is None
          and _bot.parse_command("") is None and _bot.parse_command(None) is None)
    # Das Beispiel aus Discords eigener Dokumentation.
    check("der Zeitstempel steckt in der ID (auf die Millisekunde)",
          abs(_snow_t("175928847299117063") - 1462015105.796) < 0.001)

    # -----------------------------------------------------------------------
    section("Fernstart: der Bot gegen einen nachgebauten Kanal")

    class _Channel:
        """Ein Kanal samt Bot-Konto — ohne Netz, mit Protokoll."""

        def __init__(self):
            self.msgs = []
            self.sent, self.edits, self.reacts = [], [], []
            self.reaction_users = []
            self.calls = 0
            self.clock_offset = None
            self.fail = None

        def _maybe_fail(self):
            self.calls += 1
            if self.fail is not None:
                raise self.fail

        def me(self):
            self._maybe_fail()
            return {"id": _ME, "username": "Clicker"}

        def channel(self, channel_id):
            self._maybe_fail()
            return {"id": channel_id, "name": "start"}

        def messages(self, channel_id, after=None, limit=50):
            self._maybe_fail()
            out = [m for m in self.msgs if after is None or int(m["id"]) > int(after)]
            return sorted(out, key=lambda m: -int(m["id"]))[:limit]

        def send(self, channel_id, content, reply_to=None):
            self._maybe_fail()
            self.sent.append((content, reply_to))
            return {"id": _snowflake(_now[0])}

        def edit(self, channel_id, message_id, content):
            self._maybe_fail()
            self.edits.append((message_id, content))
            return {}

        def react(self, channel_id, message_id, emoji=_STOP):
            self._maybe_fail()
            self.reacts.append((message_id, emoji))

        def reactions(self, channel_id, message_id, emoji=_STOP):
            self._maybe_fail()
            return list(self.reaction_users)

        def post(self, author_id, content, **extra):
            message = {"id": _snowflake(_now[0]), "type": 0, "content": content,
                       "author": {"id": author_id, "username": f"u{author_id[:3]}"}}
            message["author"].update(extra.pop("author", {}))
            message.update(extra)
            self.msgs.append(message)
            return message

    _now = [1_800_000_000.0]
    _channel = _Channel()
    _factory_tokens = []

    def _factory(token):
        _factory_tokens.append(token)
        return _channel

    _rs.save_settings(_settings())
    _b = _bot.RemoteBot("run.json", client_factory=_factory, clock=lambda: _now[0])

    def _step(seconds: float = _bot.POLL_INTERVAL):
        _now[0] += seconds
        _b.step()

    def _orders():
        out = []
        while True:
            order = _b.fetch_order()
            if order is None:
                return out
            out.append(order)

    _channel.post(_OWNER, "!start raid")             # stand schon vor dem Start da
    _step(1)
    check("beim Verbinden gilt alles Vorhandene als gelesen — nichts feuert nach",
          _orders() == [] and _channel.sent == [])
    check("die Absender von vorher stehen trotzdem zum Freigeben bereit",
          [s["id"] for s in _b.seen] == [_OWNER])

    _start_msg = _channel.post(_OWNER, "!start RAID")
    _step()
    _got = _orders()
    check("ein !start von der Liste wird zum Auftrag", len(_got) == 1 and _got[0].command == "start")
    _start = _got[0] if _got else None
    check("mit der Startzeit aus dem Zeitstempel der Nachricht plus Vorlauf",
          _start is not None and abs(_start.arguments["target"]
                                     - (_snow_t(_start_msg["id"]) + _rs.LEAD_SECONDS)) < 0.001)
    check("mit Absender als Name UND als ID — der Hauptprozess prüft selbst",
          _start is not None and _start.arguments["sender_id"] == _OWNER
          and _start.arguments["word"] == "raid")

    _channel.post(_STRANGER, "!start raid")
    _channel.post(_STRANGER, "!stop")
    _step()
    check("ein Fremder startet nichts und stoppt nichts",
          _orders() == [] and _channel.sent == [])
    check("und bekommt keine Antwort — er erfährt nichts",
          all(_STRANGER not in str(s) for s in _channel.sent))
    check("aber er steht unter „zuletzt im Kanal“ (zum Freigeben)",
          _b.seen[0]["id"] == _STRANGER)

    _channel.post(_OWNER, "!start farm")
    _step()
    check("ein nicht freigegebenes Wort startet nichts", _orders() == [])
    check("und das wird gesagt", len(_channel.sent) == 1
          and "nicht freigegeben" in _channel.sent[-1][0]
          and _channel.sent[-1][0].startswith("**Alex**:"))

    _channel.post(_OWNER, "!start raid")
    _step(_rs.LEAD_SECONDS + 5)                         # erst viel später gesehen
    check("ein zu spät gesehener Start startet nicht", _orders() == [])
    check("und sagt es", "zu spät" in _channel.sent[-1][0])

    _channel.post(_OWNER, "!start <@123> @everyone")
    _step()
    check("ein Wort, das keins ist, wird nicht ins Echo übernommen",
          _orders() == [] and "@everyone" not in _channel.sent[-1][0]
          and "<@123>" not in _channel.sent[-1][0])

    _channel.post(_ME, "!start raid")
    _channel.post(_FRIEND, "!start raid", author={"bot": True})
    _sent_before = len(_channel.sent)
    _step()
    check("eigene Nachrichten und andere Bots zählen nicht",
          _orders() == [] and len(_channel.sent) == _sent_before)

    _channel.post(_FRIEND, "!stop")
    _step()
    _got = _orders()
    check("!stop von der Liste wird zum Auftrag",
          [o.command for o in _got] == ["stop"] and _got[0].arguments["sender_id"] == _FRIEND)

    _channel.post(_FRIEND, "!stop")
    _channel.post(_FRIEND, "!status")
    _sent_before = len(_channel.sent)
    _step(_bot.MAX_AGE + 10)
    check("ein !stop oder !status von vor über einer Minute meint nicht jetzt",
          _orders() == [] and len(_channel.sent) == _sent_before)

    _channel.post(_OWNER, "", attachments=[], embeds=[])
    _step()
    check("eine leere Nachricht eines Menschen heisst: Inhalts-Schalter fehlt",
          _b.content_missing is True)
    _channel.post(_OWNER, "hallo")
    _step()
    check("und die nächste mit Text nimmt die Warnung zurück", _b.content_missing is False)

    _channel.post(_OWNER, "", type=7)                   # „ist beigetreten“
    _step()
    check("eine Systemnachricht ist keine leere Nachricht", _b.content_missing is False)

    # --- Die Antwort des Hauptprozesses und das Mitlaufen ---
    _target = _now[0] + 15
    _order = _bot.Order("start", {"word": "raid", "target": _target, "sender": "Alex",
                                  "sender_id": _OWNER}, message_id=_start_msg["id"], sender="Alex")
    _text = f"⏳ `Raid` startet um {_bot.discord_time(_target)}"
    _b.answer(_order, True, _text, "Raid")
    _step(0.5)
    check("die Antwort steht im Kanal, als Antwort auf den Befehl",
          _channel.sent[-1] == (f"**Alex**: {_text}", _start_msg["id"]))
    check("und unter dem Befehl liegt 🛑 zum Anhalten",
          _channel.reacts == [(_start_msg["id"], _STOP)])
    check("der Start wird verfolgt", _b.track is not None and _b.track.sequence == "Raid")

    Path("run.json").write_text(_json.dumps({"countdown": True, "sequence": "Raid",
                                             "target_time": _target}), encoding="utf-8")
    _step()
    check("solange der Countdown läuft, ändert sich die Zeile nicht", _channel.edits == [])

    _channel.reaction_users = [{"id": _STRANGER, "username": "x"},
                               {"id": _ME, "username": "Clicker", "bot": True}]
    _step()
    check("🛑 von einem Fremden (oder vom Bot selbst) hält nichts an", _orders() == [])
    _channel.reaction_users.append({"id": _FRIEND, "username": "Ben"})
    _step()
    _got = _orders()
    check("🛑 von jemandem auf der Liste hält an",
          [(o.command, o.arguments["sender_id"]) for o in _got] == [("stop", _FRIEND)])
    _step()
    check("und nur einmal, nicht bei jeder Abfrage", _orders() == [])

    # Die Uhr steht schon hinter der Startzeit (die Reaktions-Runden oben);
    # zurückgedreht wird sie nicht. Die nächste Abfrage kommt sofort.
    _now[0] = max(_now[0], _target + 1)
    Path("run.json").write_text(_json.dumps({"active": True, "sequence": "Raid",
                                             "stamp": _now[0]}), encoding="utf-8")
    _b.next_poll = 0.0
    _step(0.1)
    check("läuft der Lauf, wird die Zeile einmal geändert",
          len(_channel.edits) == 1 and "läuft" in _channel.edits[-1][1])
    Path("run.json").write_text(_json.dumps({
        "active": False, "sequence": "Raid", "end": _now[0] + 30, "reason": "von Hand gestoppt",
        "elapsed_cycles": 3, "counters": {"clicks": 42}, "stamp": _now[0] + 30}),
        encoding="utf-8")
    _step()
    check("am Ende steht, was der Lauf geschafft hat",
          "fertig" in _channel.edits[-1][1] and "42 Klicks" in _channel.edits[-1][1]
          and "von Hand gestoppt" in _channel.edits[-1][1])
    check("danach wird nichts mehr verfolgt", _b.track is None)

    # Countdown abgebrochen: die Anzeige verschwindet vor der Startzeit. Der
    # Hauptprozess schreibt den Countdown, BEVOR er antwortet (`schedule_run`).
    _target2 = _now[0] + 15
    _order2 = _bot.Order("start", dict(_order.arguments, target=_target2),
                         message_id=_start_msg["id"], sender="Alex")
    Path("run.json").write_text(_json.dumps({"countdown": True, "sequence": "Raid",
                                             "target_time": _target2}), encoding="utf-8")
    _b.answer(_order2, True, f"⏳ `Raid` startet um {_bot.discord_time(_target2)}", "Raid")
    _step(0.5)
    Path("run.json").unlink()
    _step()
    check("ein abgebrochener Countdown wird als abgebrochen gemeldet",
          "abgebrochen" in _channel.edits[-1][1] and _b.track is None)

    _b.answer(_order, False, "❌ hier läuft schon etwas", "")
    _step(0.5)
    check("eine Absage steht im Kanal und wird nicht verfolgt",
          "läuft schon" in _channel.sent[-1][0] and _b.track is None)

    # --- !status ---
    Path("run.json").write_text(_json.dumps({"active": True, "sequence": "Raid",
                                             "counters": {"clicks": 7}, "stamp": _now[0]}),
                                encoding="utf-8")
    _channel.post(_FRIEND, "!status")
    _step()
    check("!status sagt, was läuft und welche Wörter hier gelten",
          "läuft" in _channel.sent[-1][0] and "`raid`" in _channel.sent[-1][0])
    Path("run.json").unlink()

    # --- Zustand für das Studio ---
    _b._status_written = 0.0
    _step(0.1)
    _status_raw = Path(_rs.STATUS_FILE).read_text(encoding="utf-8")
    _status = _json.loads(_status_raw)
    check("der Bot schreibt seinen Zustand fürs Studio",
          _status["connected"] and _status["bot_name"] == "Clicker"
          and _status["channel_name"] == "start" and _status["log"])
    check("ohne den Token", _TOKEN not in _status_raw)

    # --- Aus, Fehler, neuer Token ---
    _rs.save_settings(_settings(enabled=False))
    _os.utime(_rs.SETTINGS_FILE, ns=(1, _time.time_ns() + 10_000_000))
    _calls = _channel.calls
    _b.answer(_order, True, _text, "Raid")
    _step()
    _step()
    check("ausgeschaltet fragt der Bot Discord gar nicht erst", _channel.calls == _calls)
    check("und eine liegengebliebene Antwort geht nicht später noch hinaus",
          _b.fetch_answer() is None)

    _rs.save_settings(_settings())
    _os.utime(_rs.SETTINGS_FILE, ns=(1, _time.time_ns() + 20_000_000))
    _channel.fail = _DE(401, "HTTP 401: Unauthorized")
    _step()
    check("ein abgelehnter Token wird gemeldet", "Token" in _b.error and _b.client is None)
    _calls = _channel.calls
    _step()
    _step()
    check("und nicht im Sekundentakt wiederholt", _channel.calls == _calls)

    # Lesen ja, schreiben nein: Discord antwortet beim Senden mit 403.
    _channel.fail = _DE(403, "HTTP 403: Missing Permissions")
    _now[0] = _b.retry_at
    _step(0)
    check("fehlende Rechte nennen Lesen UND Schreiben",
          "schreiben" in _b.error and "lesen" in _b.error)

    _channel.fail = None
    _rs.save_settings(_settings(token=_TOKEN[:-1] + "c"))
    _os.utime(_rs.SETTINGS_FILE, ns=(1, _time.time_ns() + 30_000_000))
    _step()
    check("ein neuer Token verbindet sofort neu",
          _factory_tokens[-1].endswith("c") and _b.client is not None and _b.error == "")

    _channel.fail = _DE(0, "keine Verbindung")
    _step()
    _first = _b.retry_at - _now[0]
    _now[0] = _b.retry_at
    _step(0)
    check("ohne Netz wird mit wachsendem Abstand neu versucht",
          _b.retry_at - _now[0] > _first and "keine Verbindung" in _b.error)
    _channel.fail = None

    # -----------------------------------------------------------------------
    section("Fernstart: die Verbindung zu Discord")

    class _Answer:
        def __init__(self, body: bytes, date: str = ""):
            self._body = body
            self.headers = {"Date": date} if date else {}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return self._body

    _requests = []
    _replies = []

    def _opener(request, timeout=None):
        _requests.append(request)
        reply = _replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    _sleeps = []
    _client = _DC(_TOKEN, opener=_opener, sleep=_sleeps.append, clock=lambda: 1_800_000_000.0)

    _replies.append(_Answer(b'{"id": "1", "username": "Clicker"}',
                            "Fri, 15 Jan 2027 08:00:05 GMT"))
    _client.me()
    _req = _requests[-1]
    check("der Token geht als „Bot …“ mit, nie in der Adresse",
          _req.get_header("Authorization") == f"Bot {_TOKEN}" and _TOKEN not in _req.full_url)
    check("mit dem Agenten, den Discord verlangt",
          _req.get_header("User-agent", "").startswith("DiscordBot ("))
    check("die eigene Uhr wird gegen Discord gemessen",
          _client.clock_offset is not None)

    _replies.append(_Answer(b'{"id": "5"}'))
    _client.send(_CHANNEL, "x" * 5000, reply_to="77")
    _body = _json.loads(_requests[-1].data)
    check("eine Antwort pingt niemanden an", _body.get("allowed_mentions") == {"parse": []})
    check("und bleibt unter Discords Grenze", len(_body["content"]) <= 2000)
    check("und hängt am Befehl, auf den sie antwortet",
          _body["message_reference"]["message_id"] == "77")

    _replies.append(_Answer(b""))
    _client.react(_CHANNEL, "77")
    check("eine Reaktion ohne Körper trägt trotzdem eine Länge",
          _requests[-1].get_method() == "PUT" and _requests[-1].data == b"")

    def _http(code, body=b"{}"):
        return _ue.HTTPError("https://discord.com", code, "x", {}, _io.BytesIO(body))

    _replies.extend([_http(429, b'{"retry_after": 1.5}'), _Answer(b"[]")])
    check("bei „zu viele Anfragen“ wird gewartet und wiederholt",
          _client.messages(_CHANNEL) == [] and _sleeps[-1] == 1.5)

    _replies.append(_http(401, b'{"message": "401: Unauthorized"}'))
    try:
        _client.me()
        _status_401 = None
    except _DE as e:
        _status_401 = e.status
    check("ein abgelehnter Token kommt als Fehler mit Status 401", _status_401 == 401)

    try:
        _client.messages("../../users/@me")
        _injected = True
    except _DE:
        _injected = False
    check("in die Adresse kommen nur Ziffern als ID", not _injected)

    # -----------------------------------------------------------------------
    section("Fernstart: der Hauptprozess prüft selbst")

    from autoclicker.handlers import REMOTE_COMMANDS as _RC, remote_start as _start_cmd
    from autoclicker.models import AutoClickerState as _ST, LoopPhase as _PHASE, \
        Sequence as _SEQ, SequenceStep as _STEP
    from autoclicker.persistence import save_sequence_file, sequence_file

    check("aus dem Chat sind genau Start und Stopp erreichbar",
          sorted(_RC) == ["start", "stop"])

    _seq = _SEQ("Raid", loop_phases=[_PHASE("L", steps=[_STEP(key_press="a")])])
    sequence_file("Raid").parent.mkdir(parents=True, exist_ok=True)
    save_sequence_file(_seq, sequence_file("Raid"))
    _rs.save_settings(_settings())
    _st = _ST()
    _st.config.window_focus_check = True

    def _args(**changes):
        base = {"word": "raid", "target": _time.time() + 10, "sender": "Ben",
                "sender_id": _FRIEND}
        base.update(changes)
        return base

    def _refused(arguments, words):
        ok, text, _seq_name = _quiet(_start_cmd, _st, arguments)
        return ok is False and words in text and not _st.countdown_active

    check("ein Absender, der nicht auf der Liste steht, startet nichts",
          _refused(_args(sender_id=_STRANGER), "nicht freigegeben"))
    check("ein Wort, das hier nicht freigegeben ist, startet nichts",
          _refused(_args(word="farm"), "nicht freigegeben"))
    check("eine vergangene Startzeit startet nichts",
          _refused(_args(target=_time.time() - 1), "vorbei"))
    check("eine Startzeit weit in der Zukunft auch nicht",
          _refused(_args(target=_time.time() + 600), "Zukunft"))
    _st.config.window_focus_check = False
    check("ohne Fensterfokus-Prüfung startet aus der Ferne nichts",
          _refused(_args(), "Fensterfokus"))
    _st.config.window_focus_check = True
    _rs.save_settings(_settings(enabled=False))
    check("ist der Fernstart aus, gilt auch ein Auftrag nicht, der schon unterwegs war",
          _refused(_args(), "aus"))
    _rs.save_settings(_settings(words=[_rs.RemoteWord("raid", "Gibtsnicht")]))
    check("eine freigegebene Sequenz, die fehlt, startet nichts",
          _refused(_args(), "fehlt"))
    _rs.save_settings(_settings())

    # Ein im Studio angefangener Schrittmodus darf den Fernstart nicht anhalten.
    _st.step_mode = True
    _st.step_via_studio = True
    _ok, _text, _name = _quiet(_start_cmd, _st, _args())
    check("ein Schrittmodus aus dem Studio gilt für den Fernstart nicht",
          _st.step_mode is False and _st.step_via_studio is False)
    check("ein gültiger Auftrag stellt den Countdown",
          _ok is True and _st.countdown_active and _name == "Raid"
          and _st.active_sequence is not None and _st.active_sequence.name == "Raid")
    check("und die Antwortzeile ist die, die der Bot beim Mitlaufen erwartet",
          _text.startswith("⏳ `Raid` startet um <t:"))
    _ok2, _text2, _name2 = _quiet(_start_cmd, _st, _args())
    check("ein zweiter Start während des Countdowns wird abgelehnt",
          _ok2 is False and "läuft schon" in _text2 and _st.countdown_active)
    # Der Countdown-Thread meldet seinen Abbruch selbst — mitgefangen, solange gewartet wird.
    with _cl.redirect_stdout(_io.StringIO()):
        _ok, _text, _name = _RC["stop"](_st, {"sender": "Ben", "sender_id": _FRIEND})
        _end = _time.time() + 3
        while _st.countdown_active and _time.time() < _end:
            _time.sleep(0.02)
        _time.sleep(0.1)
    check("!stop bricht den Countdown ab", _ok is True and not _st.countdown_active)
    _ok, _text, _name = _quiet(_RC["stop"], _st, {"sender": "Ben", "sender_id": _FRIEND})
    check("und sagt, wenn nichts lief", _ok is False and "nichts" in _text)
    _ok, _text, _name = _quiet(_RC["stop"], _st, {"sender": "x", "sender_id": _STRANGER})
    check("auch Stoppen nur von der Liste", _ok is False and "nicht freigegeben" in _text)

    # -----------------------------------------------------------------------
    section("Fernstart: aus dem Chat führt kein Weg zu einer Speicherfunktion")

    def _tree(relative: str):
        return _ast.parse((REPO / relative).read_text(encoding="utf-8"))

    def _imports(tree) -> set:
        found = set()
        for node in _ast.walk(tree):
            if isinstance(node, _ast.ImportFrom):
                found.add("." * node.level + (node.module or ""))
            elif isinstance(node, _ast.Import):
                found.update(a.name for a in node.names)
        return found

    def _names(tree) -> set:
        found = set()
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Name):
                found.add(node.id)
            elif isinstance(node, _ast.Attribute):
                found.add(node.attr)
            elif isinstance(node, _ast.ImportFrom):
                found.update(a.name for a in node.names)
        return found

    _bot_tree = _tree("autoclicker/remote/bot.py")
    _own = {m for m in _imports(_bot_tree) if m.startswith(".") or m.startswith("autoclicker")}
    check("der Bot holt sich aus dem Programm nur Hilfen, Verbindung und Freigaben",
          _own <= {"..utils", ".discord", ".settings"})
    if not _own <= {"..utils", ".discord", ".settings"}:
        print("        zusätzlich: " + ", ".join(sorted(_own - {"..utils", ".discord", ".settings"})))
    _forbidden = {"save_settings", "send_command", "COMMANDS", "mailbox", "save_config",
                  "save_sequence_file", "activate_sequence"} & _names(_bot_tree)
    check("und erwähnt keine Speicherfunktion und keinen Briefkasten", _forbidden == set())
    _dc_own = {m for m in _imports(_tree("autoclicker/remote/discord.py"))
               if m.startswith(".") or m.startswith("autoclicker")}
    check("die Verbindung kennt das Programm gar nicht", _dc_own == set())

    _writes = [node for node in _ast.walk(_bot_tree) if isinstance(node, _ast.Call)
               and getattr(node.func, "id", "") == "atomic_write"]
    check("geschrieben wird nur der eigene Zustand fürs Studio",
          _writes and all(_ast.unparse(n.args[0]) == "self._status_path" for n in _writes))
    check("und keine Datei auf anderem Weg",
          not {"write_text", "write_bytes", "unlink", "rename", "replace"} & _names(_bot_tree))

    _main_tree = _tree("main.py")
    _check_remote = next(n for n in _ast.walk(_main_tree)
                         if isinstance(n, _ast.FunctionDef) and n.name == "_check_remote")
    check("der Hauptprozess führt Aufträge nur aus REMOTE_COMMANDS aus",
          "REMOTE_COMMANDS" in _names(_check_remote) and "COMMANDS" not in _names(_check_remote))

    # -----------------------------------------------------------------------
    section("Fernstart: remote.json reist nicht mit")

    _ignored = (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()
    check("Freigaben und Zustand stehen in .gitignore",
          "remote.json" in _ignored and ".remote-status.json" in _ignored)

    from autoclicker.import_export import export_bundle as _export
    from autoclicker.persistence import activate_sequence
    _st2 = _ST()
    activate_sequence(_st2, _seq)
    Path("config.json").write_text("{}", encoding="utf-8")
    _ok, _msg = _quiet(_export, _st2, "buendel.zip", (0, 0), (100, 100))
    with _zip.ZipFile("buendel.zip") as _zf:
        _names_zip = _zf.namelist()
        _all = b"".join(_zf.read(n) for n in _names_zip)
    check("ein Export-Bündel enthält keine remote.json",
          _ok and not any(n.endswith("remote.json") for n in _names_zip))
    check("und nirgends den Token", _TOKEN.encode() not in _all)

    # -----------------------------------------------------------------------
    section("Fernstart: der Reiter im Studio")

    from autoclicker.editors.sequence_studio.bridge import StudioBridge as _SB
    from autoclicker.persistence import find_sequence_path

    _rs.save_settings(_settings())
    _bridge = _SB(_seq, find_sequence_path("Raid"), "sequences")
    _data = _bridge.remote_data()
    check("der Reiter bekommt alles, was er zeichnet",
          _data["settings"]["words"] == [{"word": "raid", "sequence": "Raid", "exists": True}]
          and _data["settings"]["token_set"] is True and "Raid" in _data["sequences"])
    check("aber nie den Token", _TOKEN not in _json.dumps(_data))

    _r = _bridge.remote_token({"token": "geheim"})
    check("ein Fetzen wird nicht als Token gespeichert",
          _r["kind"] == "warn" and _rs.load_settings().token == _TOKEN)
    _r = _bridge.remote_token({"token": ""})
    check("leer entfernt den Token", _r["kind"] == "ok" and _rs.load_settings().token == "")
    _r = _bridge.remote_token({"token": _TOKEN})
    check("und ein echter wird gespeichert, ohne zurückzukommen",
          _rs.load_settings().token == _TOKEN and _TOKEN not in _json.dumps(_r))

    _r = _bridge.remote_word({"action": "set", "word": "Farm", "sequence": "Gibtsnicht"})
    check("ein Wort lässt sich nur einer vorhandenen Sequenz zuordnen",
          _r["kind"] == "warn" and _rs.sequence_for(_rs.load_settings(), "farm") is None)
    _r = _bridge.remote_word({"action": "set", "word": "Farm", "sequence": "Raid"})
    check("und wird klein gespeichert", _rs.sequence_for(_rs.load_settings(), "farm") == "Raid")
    _r = _bridge.remote_word({"action": "set", "word": "zwei worte", "sequence": "Raid"})
    check("ein Wort mit Leerzeichen wird abgelehnt", _r["kind"] == "warn")
    _r = _bridge.remote_word({"action": "remove", "word": "farm"})
    check("und eines entfernt", _rs.sequence_for(_rs.load_settings(), "farm") is None)

    _r = _bridge.remote_user({"action": "add", "id": "Alex", "name": "Alex"})
    check("eine Person ohne gültige ID wird nicht eingetragen", _r["kind"] == "warn")
    _r = _bridge.remote_user({"action": "add", "id": _STRANGER, "name": "Neu"})
    check("eine mit ID schon", _rs.user_allowed(_rs.load_settings(), _STRANGER))
    _r = _bridge.remote_user({"action": "remove", "id": _STRANGER})
    check("und wieder entfernt", not _rs.user_allowed(_rs.load_settings(), _STRANGER))

    _r = _bridge.remote_set({"field": "channel_id", "value": "#start"})
    check("ein Kanalname ist keine Kanal-ID",
          _r["kind"] == "warn" and _rs.load_settings().channel_id == _CHANNEL)
    _r = _bridge.remote_set({"field": "enabled", "value": False})
    check("der Schalter schaltet", _rs.load_settings().enabled is False)
    _r = _bridge.remote_set({"field": "token", "value": "x"})
    check("ein Feld, das es nicht gibt, ändert nichts", _r["kind"] == "warn")

    Path(_rs.SETTINGS_FILE).write_text("{kaputt", encoding="utf-8")
    _r = _bridge.remote_set({"field": "enabled", "value": True})
    check("eine unlesbare remote.json wird gemeldet und nicht überschrieben",
          _r["kind"] == "err" and "JSON" in _r["message"]
          and Path(_rs.SETTINGS_FILE).read_text(encoding="utf-8") == "{kaputt")
    Path(_rs.SETTINGS_FILE).unlink()
    check("Prüfen ohne Token fragt gar nicht erst im Netz",
          _bridge.remote_check()["kind"] == "warn")

    _web = studio_web_source()
    check("die Seite hat einen Reiter dafür",
          'data-view="remote"' in _web and 'id="view-remote"' in _web)
    _hidden = _web[_web.index('n.hidden = ["settings"'):]
    check("und blendet dort die Sequenz-Knöpfe aus",
          '"remote"' in _hidden[:_hidden.index("].includes(next)")])
finally:
    _os.chdir(_cwd)
