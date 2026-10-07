"""
Die Freigaben des Fernstarts — `remote.json`, eine Datei nur für diesen PC.

**Warum nicht in der `config.json`.** Hier steht der Bot-Token, und hier steht,
wer auf diesem Rechner etwas starten darf. Die `config.json` wandert mit jedem
Export-Bündel zum Mitspieler und wird beim Import überschrieben; eine
Freigabe, die so mitreist, brächte ein fremdes Bündel gleich „freigegeben“
mit. Eine eigene Datei, die weder Export noch Import kennen, macht diese
Grenze messbar statt zu einer Liste von Ausnahmen. Dieselbe Überlegung trennt
sie von den Sequenzen: eine Freigabe in der `sequence.json` reiste mit.

**Geschrieben wird sie nur aus dem Studio** (`bridge_remote.py`), also von
dem, der vor dem Rechner sitzt. Der Bot liest sie nur — ein Test hält fest,
dass `bot.py` `save_settings` nicht einmal erwähnt.

Die Datei ist `.gitignore`d. Eine unlesbare Datei wird gemeldet und nicht
überschrieben (`error`): kaputt ist nicht leer, und darin steht ein Token.
"""

import getpass
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..utils import atomic_write, compact_json

SETTINGS_FILE = "remote.json"
# Was der Bot gerade tut, für den Reiter „Fernstart“ im Studio. Transient wie
# `.run.json`, und aus demselben Grund im Wurzelordner statt in `sequences/`.
STATUS_FILE = ".remote-status.json"

# **Wie lange nach der Nachricht gestartet wird.** Keine Einstellung, sondern
# Protokoll: stünde sie in der Datei, könnten zwei PCs verschiedene Werte
# tragen und starteten genau dann versetzt, wenn es darauf ankommt. Zwanzig
# Sekunden reichen für das Abfrage-Intervall und eine langsame Antwort.
LEAD_SECONDS = 20.0

# Was ein Wort sein darf. Es wird in Discord getippt und mit der Freigabe
# verglichen — Leerzeichen, Satzzeichen und Formatierung haben darin nichts zu
# suchen, und ein kurzes Wort ist eines, das man auf dem Handy richtig tippt.
_WORD = re.compile(r"[a-z0-9äöüß_-]{1,24}")
# Discord-IDs („Snowflakes“) sind Ziffernfolgen, heute 17–20 Stellen.
_SNOWFLAKE = re.compile(r"\d{15,21}")
# Ein Bot-Token: drei Teile aus Base64-Zeichen, durch Punkte getrennt.
_TOKEN = re.compile(r"[A-Za-z0-9_\-.]{50,120}")


@dataclass
class RemoteUser:
    """Wer starten darf — die ID ist der Schlüssel, der Name nur Anzeige.

    Der Name kann sich in Discord jederzeit ändern und ist nicht eindeutig;
    verglichen wird deshalb nie mit ihm.
    """
    id: str
    name: str = ""


@dataclass
class RemoteWord:
    """Ein Wort in Discord und die Sequenz, die es auf DIESEM PC startet."""
    word: str
    sequence: str


@dataclass
class RemoteSettings:
    enabled: bool = False
    token: str = ""
    channel_id: str = ""
    # So steht der PC in den Antworten im Kanal. Leer heisst: Benutzername.
    pc_name: str = ""
    users: list = field(default_factory=list)
    words: list = field(default_factory=list)
    # Nicht in der Datei: warum sie nicht gelesen werden konnte.
    error: str = ""

    def display_name(self) -> str:
        return self.pc_name.strip() or default_pc_name()

    def ready(self) -> bool:
        """Kann der Bot überhaupt loslegen?"""
        return bool(self.enabled and self.token and self.channel_id and not self.error)


def default_pc_name() -> str:
    try:
        return getpass.getuser() or "PC"
    except (OSError, KeyError, ImportError):
        return "PC"


def clean_word(text) -> str:
    """Das Wort, wie es verglichen wird — oder "" für eines, das keins ist."""
    word = str(text or "").strip().casefold()
    return word if _WORD.fullmatch(word) else ""


def clean_snowflake(text) -> str:
    raw = str(text or "").strip()
    return raw if _SNOWFLAKE.fullmatch(raw) else ""


def clean_token(text) -> str:
    """Ein eingefügter Token, bereinigt — oder "" für etwas, das keiner ist.

    Das Portal zeigt den Token ohne Präfix; wer ihn aus einer Anleitung mit
    `Bot ` davor kopiert, soll trotzdem nicht scheitern.
    """
    raw = str(text or "").strip()
    if raw.lower().startswith("bot "):
        raw = raw[4:].strip()
    return raw if _TOKEN.fullmatch(raw) else ""


def sequence_for(settings: RemoteSettings, word) -> Optional[str]:
    """Die Sequenz hinter einem Wort — oder `None`, wenn es nicht freigegeben ist."""
    wanted = clean_word(word)
    if not wanted:
        return None
    for entry in settings.words:
        if entry.word == wanted and entry.sequence:
            return entry.sequence
    return None


def user_allowed(settings: RemoteSettings, user_id) -> bool:
    wanted = str(user_id or "")
    return bool(wanted) and any(u.id == wanted for u in settings.users)


# ----------------------------------------------------------------- Datei

def _users_from(raw) -> list:
    users = []
    for entry in raw if isinstance(raw, list) else []:
        if not isinstance(entry, dict):
            continue
        user_id = clean_snowflake(entry.get("id"))
        if user_id and all(u.id != user_id for u in users):
            users.append(RemoteUser(user_id, str(entry.get("name") or "")[:64]))
    return users


def _words_from(raw) -> list:
    words = []
    for entry in raw if isinstance(raw, list) else []:
        if not isinstance(entry, dict):
            continue
        word = clean_word(entry.get("word"))
        if word and all(w.word != word for w in words):
            words.append(RemoteWord(word, str(entry.get("sequence") or "")))
    return words


def settings_from_dict(data: dict) -> RemoteSettings:
    """Liest, was brauchbar ist — ein kaputter Eintrag fällt einzeln heraus."""
    return RemoteSettings(
        enabled=data.get("enabled") is True,
        token=clean_token(data.get("token")),
        channel_id=clean_snowflake(data.get("channel_id")),
        pc_name=str(data.get("pc_name") or "")[:32],
        users=_users_from(data.get("users")),
        words=_words_from(data.get("words")),
    )


def settings_to_dict(settings: RemoteSettings) -> dict:
    return {
        "enabled": bool(settings.enabled),
        "token": settings.token,
        "channel_id": settings.channel_id,
        "pc_name": settings.pc_name,
        "users": [{"id": u.id, "name": u.name} for u in settings.users],
        "words": [{"word": w.word, "sequence": w.sequence} for w in settings.words],
    }


def load_settings(path=None) -> RemoteSettings:
    """Die Freigaben von Platte. Wirft nie: ohne Datei ist der Fernstart aus."""
    target = Path(path or SETTINGS_FILE)
    try:
        raw = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return RemoteSettings()
    except (OSError, UnicodeError) as e:
        return RemoteSettings(error=f"{target.name} nicht lesbar: {e}")
    try:
        data = json.loads(raw)
    except ValueError as e:
        return RemoteSettings(error=f"{target.name} ist kein gültiges JSON: {e}")
    if not isinstance(data, dict):
        return RemoteSettings(error=f"{target.name} ist kein Objekt")
    return settings_from_dict(data)


def save_settings(settings: RemoteSettings, path=None) -> bool:
    """Schreibt die Freigaben. Sagt, ob es geklappt hat — wie jeder Saver."""
    if settings.error:
        return False
    try:
        atomic_write(Path(path or SETTINGS_FILE), compact_json(settings_to_dict(settings)))
        return True
    except (OSError, TypeError, ValueError):
        return False
