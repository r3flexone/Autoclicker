"""Der Reiter „Fernstart“: welche Wörter aus Discord hier was starten dürfen.

**Nur hier wird `remote.json` geschrieben** — also nur von dem, der vor dem
Rechner sitzt. Der Bot im Hauptprozess liest die Datei bei jeder Änderung neu
(am Zeitstempel); ein Briefkasten-Befehl ist dafür nicht nötig, und der
Hauptprozess prüft jeden Auftrag ohnehin noch einmal gegen die Datei.

**Der Token verlässt diese Brücke nie in Richtung Seite.** `remote_data()`
sagt nur, OB einer eingetragen ist. Ein Feld, das den Token zurückbekäme,
stünde im Fenster, im Rauchtest-Screenshot und in jedem Bildschirmfoto, das
jemand von seinem Studio teilt.

Alles läuft über `ask()`: geändert wird `remote.json`, nicht die Sequenz —
dieselbe Begründung wie bei `config_write()`.
"""

import json
import time
from pathlib import Path
from typing import Optional


def _remote():
    """Die Module des Fernstarts — erst beim ersten Aufruf geladen."""
    from ...remote import settings
    return settings


class BridgeRemoteMixin:
    """Der Reiter „Fernstart“: Freigaben lesen, ändern, Verbindung prüfen."""

    # ------------------------------------------------------------ Momentaufnahme

    def remote_data(self, data: Optional[dict] = None) -> dict:
        """Alles, was der Reiter zeichnet — ohne den Token."""
        rs = _remote()
        settings = rs.load_settings()
        sequences = self._remote_sequences()
        return {
            "settings": {
                "enabled": settings.enabled,
                "channel_id": settings.channel_id,
                "pc_name": settings.pc_name,
                "pc_default": rs.default_pc_name(),
                "token_set": bool(settings.token),
                "users": [{"id": u.id, "name": u.name} for u in settings.users],
                "words": [{"word": w.word, "sequence": w.sequence,
                           "exists": w.sequence in sequences} for w in settings.words],
            },
            "error": settings.error,
            "sequences": sequences,
            "focus_check": self._remote_focus_check(),
            "lead": rs.LEAD_SECONDS,
            "status": self._remote_status(settings),
            "path": str(Path(rs.SETTINGS_FILE).resolve()),
        }

    @staticmethod
    def _remote_sequences() -> list:
        from ...persistence import list_available_sequences
        return [name for name, _path in list_available_sequences()]

    @staticmethod
    def _remote_focus_check() -> bool:
        """Steht die Fensterfokus-Prüfung an — in der DATEI, nicht im Speicher.

        Der Hauptprozess entscheidet nach der Datei (er lädt sie nach jedem
        Schreiben neu); ein Fenster, das seit einer Stunde offen ist, hätte
        im Speicher womöglich den Stand von damals.
        """
        from ...config import CONFIG, CONFIG_FILE
        try:
            data = json.loads(Path(CONFIG_FILE).read_text(encoding="utf-8"))
            return bool(data.get("window_focus_check"))
        except (OSError, ValueError, AttributeError):
            return bool(CONFIG.window_focus_check)

    @staticmethod
    def _remote_status(settings) -> dict:
        """Was der Bot zuletzt gemeldet hat — und ob er überhaupt noch lebt."""
        rs = _remote()
        try:
            status = json.loads(Path(rs.STATUS_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            status = None
        if not isinstance(status, dict):
            return {"alive": False}
        allowed = {u.id for u in settings.users}
        status["seen"] = [dict(s, allowed=s.get("id") in allowed)
                          for s in status.get("seen") or [] if isinstance(s, dict)]
        # Der Bot schreibt alle fünf Sekunden; nach zwanzig ohne Stempel läuft
        # der Hauptprozess nicht mehr — dann gilt auch „verbunden“ nicht.
        status["alive"] = time.time() - float(status.get("stamp") or 0) < 20
        return status

    # ------------------------------------------------------------ Ändern

    def _remote_change(self, change, done: str) -> dict:
        """Liest, ändert, schreibt — und meldet, was passiert ist.

        Eine unlesbare Datei wird nicht überschrieben: darin steht ein Token,
        und „kaputt“ ist nicht „leer“.
        """
        rs = _remote()
        settings = rs.load_settings()
        if settings.error:
            return dict(self.remote_data(), message=settings.error, kind="err")
        problem = change(settings)
        if problem:
            return dict(self.remote_data(), message=problem, kind="warn")
        if not rs.save_settings(settings):
            return dict(self.remote_data(), message="remote.json nicht gespeichert.",
                        kind="err")
        return dict(self.remote_data(), message=done, kind="ok")

    def remote_set(self, data: Optional[dict] = None) -> dict:
        """Ein einzelnes Feld: Schalter, Kanal oder Name dieses PCs."""
        rs = _remote()
        data = data or {}
        field_name = str(data.get("field") or "")
        value = data.get("value")

        def change(settings):
            if field_name == "enabled":
                settings.enabled = value is True
            elif field_name == "channel_id":
                channel = rs.clean_snowflake(value)
                if value and not channel:
                    return "Eine Kanal-ID ist eine lange Zahl (Rechtsklick auf den Kanal → ID kopieren)."
                settings.channel_id = channel
            elif field_name == "pc_name":
                settings.pc_name = " ".join(str(value or "").split())[:32]
            else:
                return f"Unbekanntes Feld '{field_name}'."
            return ""

        texts = {"enabled": "Fernstart an." if value is True else "Fernstart aus.",
                 "channel_id": "Kanal gespeichert.", "pc_name": "Name gespeichert."}
        return self._remote_change(change, texts.get(field_name, "Gespeichert."))

    def remote_token(self, data: Optional[dict] = None) -> dict:
        """Trägt den Bot-Token ein — oder entfernt ihn (leer)."""
        rs = _remote()
        raw = str((data or {}).get("token") or "").strip()
        token = rs.clean_token(raw)

        def change(settings):
            if raw and not token:
                return ("Das sieht nicht nach einem Bot-Token aus — im Developer-Portal "
                        "unter „Bot“ → „Reset Token“ kopieren.")
            settings.token = token
            return ""

        return self._remote_change(change, "Token gespeichert." if token else "Token entfernt.")

    def remote_word(self, data: Optional[dict] = None) -> dict:
        """Ein Wort freigeben, umhängen oder entfernen."""
        rs = _remote()
        data = data or {}
        action = str(data.get("action") or "")
        word = rs.clean_word(data.get("word"))
        sequence = str(data.get("sequence") or "")

        def change(settings):
            if not word:
                return "Ein Wort: Buchstaben, Ziffern, - und _, höchstens 24 Zeichen, ohne Leerzeichen."
            if action == "remove":
                settings.words = [w for w in settings.words if w.word != word]
                return ""
            if sequence not in self._remote_sequences():
                return "Bitte eine vorhandene Sequenz wählen."
            existing = next((w for w in settings.words if w.word == word), None)
            if existing is None:
                settings.words.append(rs.RemoteWord(word, sequence))
            else:
                existing.sequence = sequence
            return ""

        done = (f"`{word}` entfernt." if action == "remove"
                else f"`{word}` startet hier „{sequence}“.")
        return self._remote_change(change, done)

    def remote_user(self, data: Optional[dict] = None) -> dict:
        """Eine Person freigeben oder wieder entfernen — per Discord-ID."""
        rs = _remote()
        data = data or {}
        action = str(data.get("action") or "")
        user_id = rs.clean_snowflake(data.get("id"))
        name = " ".join(str(data.get("name") or "").split())[:64]

        def change(settings):
            if not user_id:
                return ("Eine Discord-ID ist eine lange Zahl (Entwicklermodus an, "
                        "Rechtsklick auf die Person → ID kopieren).")
            settings.users = [u for u in settings.users if u.id != user_id]
            if action != "remove":
                settings.users.append(rs.RemoteUser(user_id, name))
            return ""

        label = name or user_id
        done = f"{label} entfernt." if action == "remove" else f"{label} darf jetzt starten."
        return self._remote_change(change, done)

    # ------------------------------------------------------------ Prüfen

    def remote_check(self, data: Optional[dict] = None) -> dict:
        """Fragt Discord, ob Token und Kanal stimmen — mit dem, was gespeichert ist."""
        from ...remote.discord import DiscordClient, DiscordError
        settings = _remote().load_settings()
        if settings.error:
            return {"ok": False, "kind": "err", "message": settings.error}
        if not settings.token:
            return {"ok": False, "kind": "warn", "message": "Erst den Bot-Token eintragen."}
        client = DiscordClient(settings.token)
        try:
            me = client.me()
            if not settings.channel_id:
                return {"ok": True, "kind": "warn",
                        "message": f"Token stimmt (Bot „{me.get('username')}“) — "
                                   f"jetzt die Kanal-ID eintragen."}
            channel = client.channel(settings.channel_id)
            messages = client.messages(settings.channel_id, limit=10)
        except DiscordError as e:
            return {"ok": False, "kind": "err", "message": self._remote_error_text(e)}
        return self._remote_check_result(me, channel, messages, client.clock_offset)

    @staticmethod
    def _remote_error_text(error) -> str:
        if error.status == 401:
            return "Der Token wird nicht angenommen."
        if error.status in (403, 404):
            return ("Kanal nicht erreichbar — ist der Bot im Server, und darf er "
                    "den Kanal sehen und den Verlauf lesen?")
        return f"Discord nicht erreichbar: {error.message}"

    @staticmethod
    def _remote_check_result(me: dict, channel: dict, messages: list, offset) -> dict:
        from ...remote.bot import looks_stripped
        human = [m for m in messages if not (m.get("author") or {}).get("bot")]
        text = f"Verbunden: Bot „{me.get('username')}“ liest #{channel.get('name')}."
        if human and all(looks_stripped(m) for m in human):
            return {"ok": True, "kind": "warn",
                    "message": text + " Aber die Nachrichten kommen leer an — im "
                               "Developer-Portal „Message Content Intent“ einschalten."}
        if offset is not None and abs(offset) > 2:
            return {"ok": True, "kind": "warn",
                    "message": text + f" Die Uhr dieses PCs weicht um {offset:+.0f} s ab — "
                               f"Windows-Zeit synchronisieren, sonst startet er versetzt."}
        return {"ok": True, "kind": "ok", "message": text}
