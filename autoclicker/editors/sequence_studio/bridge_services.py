"""Datei-, Lauf- und Konfigurationsdienste der Studio-Brücke."""

import time
from pathlib import Path
from typing import Optional

from ...models import LoopPhase, Sequence
from ...persistence import (
    list_available_sequences,
    load_sequence_file,
    save_sequence_file,
)
from ...utils import sanitize_filename
from .bridge_contract import (
    _same_value,
    _hex,
    _mtime,
    scan_warnings,
)
from .model import (
    BLOCK_COLORS,
    BLOCK_LABELS,
    board_to_sequence,
    sequence_to_board,
)


class BridgeServicesMixin:
    """Kapselt Persistenz, Laufsteuerung und Konfiguration."""

    def sequence_list(self, data: Optional[dict] = None) -> list[dict]:
        """Kennzahlen aller gespeicherten Sequenzen für die Übersicht.

        Keine Momentaufnahme — deshalb über `ask()` zu holen, sonst zerschösse die
        Antwort den Editor-Zustand. Über `load_sequence_file()`, damit Migration und
        Punkt-Auflösung mitlaufen. Nur Kennzahlen, keine Schritte.
        """
        out: list[dict] = []
        root_layer = Path(self.sequences_dir)
        files = sorted(
            (folder / "sequence.json" for folder in root_layer.iterdir()
             if folder.is_dir() and (folder / "sequence.json").exists()),
            key=lambda path: path.parent.name,
        ) if root_layer.exists() else []
        for path in files:
            saved_name = path.parent.name
            try:
                changed = path.stat().st_mtime
            except OSError:
                changed = 0.0
            seq = load_sequence_file(path)
            if seq is None:
                # Auch die defekte bekommt ihren Umfang: sie ist der haeufigste
                # Grund, ueberhaupt loeschen zu wollen — und dann will man
                # wissen, was am Ordner sonst noch haengt.
                out.append({"name": saved_name, "file": str(path), "broken": True,
                             "changed": changed, "open": path == self.filepath,
                             "scope": self._sequence_extent(path.parent)})
                continue
            out.append({
                "name": seq.name,
                "file": str(path),
                "broken": False,
                "description": seq.description,
                "cycles": seq.total_cycles,
                "init": len(seq.init_steps),
                "end": len(seq.end_steps),
                "phases": [{"name": lp.name, "steps": len(lp.steps),
                            "repeat": lp.repeat,
                            "start": lp.scheduled_start or ""}
                           for lp in seq.loop_phases],
                "steps": seq.total_steps(),
                "changed": changed,
                "open": path == self.filepath,
                "scope": self._sequence_extent(path.parent),
                "warnings": scan_warnings(sequence_to_board(seq)),
            })
        return out

    # Was in einem Sequenzordner ausser der sequence.json noch liegt. Reihenfolge
    # = Anzeige; der Schluessel ist der Unterordner.
    #
    # **Einzahl und Mehrzahl stehen beide da.** Die Ansicht haengte erst ein "n"
    # an, und das ergab "2x Item-Scann" und "3x gemerkter Bildschirmn" - bei drei
    # von fuenf Woertern falsch. Deutsche Mehrzahl ist keine Regel, die man in
    # einer Zeile JavaScript trifft; sie gehoert zu den Daten.
    _EXTENT = (("item_scans", "Item-Scan", "Item-Scans"),
               ("boss_scans", "Boss-Scan", "Boss-Scans"),
               ("icon_scans", "Icon-Scan", "Icon-Scans"),
               ("templates", "Vorlage", "Vorlagen"),
               ("bilder", "gemerkter Bildschirm", "gemerkte Bildschirme"))

    @classmethod
    def _sequence_extent(cls, folder: Path) -> list[dict]:
        """Was am Sequenzordner haengt — fuer die Rueckfrage vor dem Loeschen.

        Eine Sequenz ist eine **Besitzeinheit**: Scans, Vorlagen und gemerkte
        Bildschirme liegen in ihrem Ordner und gehen mit ihr. Wer das nicht
        vorher liest, loescht einen Nachmittag Arbeit an Item-Vorlagen mit, weil
        er „nur die Sequenz" wegraeumen wollte.
        """
        out = []
        for below, one_item, many in cls._EXTENT:
            try:
                n = sum(1 for p in (folder / below).iterdir() if p.is_file())
            except OSError:
                n = 0
            if n:
                out.append({"kind": below, "word": one_item if n == 1 else many,
                             "count": n})
        return out

    def _sequence_folder(self, name: str) -> Optional[Path]:
        """Ordner einer Sequenz zu ihrem ANGEZEIGTEN Namen — oder `None`.

        **Der Ordner heisst nicht wie die Sequenz.** `save_data()` legt ihn
        unter `sanitize_filename(name)` an: aus „Raid" wird `sequences/raid`,
        aus „Mein Lauf" wird `mein_lauf`. Wer den angezeigten Namen an den Pfad
        haengt, greift deshalb ins Leere — und im schlimmeren Fall daneben:
        liegt zufaellig ein Ordner `sequences/Raid`, wanderte der nach
        `backups/`, waehrend die echte Sequenz stehenblieb und das Loeschen
        „hat geklappt" meldete.

        Gesucht wird deshalb wie beim Laden ueber `list_available_sequences()`
        — der Name steht IN der Datei, nicht am Ordner. Eine defekte Datei
        steht dort nicht, und genau die will man am haeufigsten loeschen;
        `sequence_list()` meldet sie unter ihrem Ordnernamen, also ist der der
        zweite Weg.

        Nebenbei schliesst das den Pfad: `name` kommt aus dem Fenster, und ein
        `..` darin fuehrte beim blossen Zusammenhaengen aus `sequences/`
        heraus. Was hier nicht als Eintrag dasteht, gibt es nicht.
        """
        for entry, path in list_available_sequences():
            if entry == name:
                return Path(path).parent
        root_layer = Path(self.sequences_dir)
        if root_layer.is_dir():
            for folder in root_layer.iterdir():
                if folder.is_dir() and folder.name == name:
                    return folder
        return None

    def sequence_delete(self, data: Optional[dict] = None) -> dict:
        """Raeumt einen Sequenzordner weg — nach `backups/`, nicht ins Nichts.

        Geloescht wird der ganze Ordner, denn genau so ist eine Sequenz
        aufgebaut: Punkte stehen in ihrer `sequence.json`, Scans, Vorlagen und
        gemerkte Bildschirme daneben. Nur die JSON zu entfernen liesse einen
        Ordner voller Vorlagen zurueck, den nie wieder jemand ansieht.

        **Verschoben statt entfernt.** „Nie Daten verlieren" ist die Regel des
        Start-Durchgangs, und sie gilt hier erst recht: der Ordner landet unter
        `backups/sequences/<ordner>/` — gespiegelte Struktur, also unter dem
        ORDNERnamen — und laesst sich von Hand zurueckschieben. Ein
        vorhandener Stand dort wird nicht ueberschrieben, sondern bekommt einen
        Zeitstempel — die aelteste Sicherung bleibt die aelteste.

        Zwei Absagen, und beide haben denselben Grund: hinterher stimmte sonst
        etwas nicht mehr, das niemand mehr nachvollziehen kann.

        * **Die offene Sequenz nicht.** Der Editor haelt sie im Speicher; der
          naechste Druck auf Speichern legte den Ordner einfach wieder an, und
          das Loeschen sah aus, als haette es nicht gewirkt.
        * **Nicht waehrend eines Laufs.** Der Worker liest waehrenddessen
          Vorlagen und Scan-Dateien aus genau diesem Ordner.
        """
        import shutil
        from datetime import datetime
        from ...persistence.paths import BACKUPS_DIR

        name = str((data or {}).get("name") or "").strip()
        if not name:
            return {"ok": False, "message": "Keine Sequenz genannt."}
        folder = self._sequence_folder(name)
        if folder is None or not folder.is_dir():
            return {"ok": False, "message": f"'{name}' gibt es nicht (mehr)."}
        if folder.resolve() == self.filepath.parent.resolve():
            return {"ok": False, "message": (
                f"'{name}' ist gerade geöffnet. Erst eine andere laden — sonst "
                "legt der nächste Druck auf Speichern den Ordner wieder an.")}
        if self._running():
            return {"ok": False, "message": (
                "Eine Sequenz läuft — der Worker liest gerade aus diesen Ordnern.")}

        # Gespiegelte Struktur, wie bei `backup_path()` im Start-Durchgang:
        # `sequences/raid` -> `backups/sequences/raid`. Der ORDNERname, nicht
        # der angezeigte — sonst laege die Sicherung unter einem Pfad, den es so
        # nie gab, und Zurueckschieben waere kein blosses Verschieben mehr.
        target = Path(BACKUPS_DIR) / "sequences" / folder.name
        if target.exists():
            target = target.with_name(f"{folder.name}_{datetime.now():%Y%m%d_%H%M%S}")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(folder), str(target))
        except (OSError, shutil.Error) as error:
            return {"ok": False, "message": f"Konnte nicht wegräumen: {error}"}
        return {"ok": True, "message": f"'{name}' liegt jetzt unter {target}."}

    def run_status(self, data: Optional[dict] = None) -> dict:
        """Was gerade läuft — gelesen aus der Statusdatei des Hauptprozesses.

        Der zweite `ask()`-Kanal, und nie ein Fehler: dass nichts läuft, ist der
        Normalfall. Die Datei ist der gemeinsame Nenner zwischen beiden Prozessen.
        """
        import json
        from ...config import RUN_STATUS_FILE
        try:
            with open(RUN_STATUS_FILE, "r", encoding="utf-8") as f:
                state_value = json.load(f)
        except (OSError, ValueError):
            return {"active": False}
        if not isinstance(state_value, dict):
            return {"active": False}
        # Ein abgeschlossener Lauf (`end`) darf beliebig alt sein — er IST
        # Vergangenheit. Die Altersregel gilt nur für einen, der sich noch für
        # laufend hält.
        if not state_value.get("active"):
            return state_value if (state_value.get("end") or state_value.get("countdown")) else {"active": False}
        # Älter als 5 s heisst: der Schreiber lebt nicht mehr. Ein abgestürzter
        # Lauf soll nicht ewig als „läuft" in der Oberfläche stehen — der Worker
        # schreibt spätestens alle 200 ms, und selbst ein Schritt, der auf eine
        # Farbe wartet, geht durch `execute_step`.
        if time.time() - float(state_value.get("stamp") or 0) > 5:
            return {"active": False, "orphaned": True}
        # Typ → Farbe und Marke: die Laufzeit schreibt nur den Schlüssel, weil
        # `runtime/` die Ansicht nicht kennen darf. Übersetzt wird hier, damit
        # der laufende Block dieselbe Farbe trägt wie seine Karte im Board — die
        # Farbe ist die Legende, und sie muss in beiden Ansichten dieselbe sein.
        type_value = state_value.get("block_set_type")
        if type_value in BLOCK_COLORS:
            state_value["block_color"] = _hex(BLOCK_COLORS[type_value])
            state_value["block_badge"] = BLOCK_LABELS[type_value]
        return state_value

    # Was das Studio dem Hauptprozess sagen darf. Die Gegenstelle ist `COMMANDS`
    # in handlers.py — ein Test hält beide Listen gegeneinander, denn laufen sie
    # auseinander, tut ein Knopf einfach nichts und niemand merkt es.
    RUN_COMMANDS = ("start", "start_manual", "stop", "pause", "skip", "skip_step", "finish",
                    "manual", "manual_action", "schedule")
    # Alles, was das Studio dem Hauptprozess sagen darf. „zeigen" steuert keinen
    # Lauf, geht aber denselben Weg — der Test haelt DIESE Liste gegen `COMMANDS`.
    # „nachklick" ist der Werkzeuge-Reiter: die Klick-Runde braucht einen
    # systemweiten Maus-Hook und muss deshalb drueben laufen.
    ALL_COMMANDS = RUN_COMMANDS + ("show", "config", "data_reload", "recording",
                                   "recording_stop",
                                   "quit_program",
                                   "reclick", "reclick_stop", "block_test")

    def recording_start(self, data: Optional[dict] = None) -> dict:
        """Startet eine neue Sequenz-Aufnahme im Hauptprozess.

        Das Studio kann den systemweiten Maus- und Tastatur-Hook nicht selbst
        installieren. Wie Start/Pause und die Klick-Runde legt es deshalb einen
        begrenzten Befehl in den gemeinsamen Briefkasten. Alle Angaben gehen mit,
        damit der Abschluss nicht unsichtbar in der Konsole auf Eingaben wartet.
        """
        from ...mailbox import send_command
        data = data or {}
        name = str(data.get("name") or "").strip()
        if not name:
            return {"ok": False, "message": "Bitte zuerst einen Namen eingeben."}
        safe_name = sanitize_filename(name)
        target = Path(self.sequences_dir) / safe_name / "sequence.json"
        if target.exists():
            return {"ok": False, "message": f"'{safe_name}' gibt es bereits."}
        try:
            cycles = max(0, int(data.get("cycles") or 0))
        except (TypeError, ValueError):
            return {"ok": False, "message": "Zyklen müssen eine ganze Zahl sein."}
        # Die drei Zeilen der vorigen Aufnahme sollen beim neuen Start nicht
        # noch für einen Augenblick als neue Ereignisse aufblitzen.
        from ...config import RECORD_STATUS_FILE
        try:
            Path(RECORD_STATUS_FILE).unlink(missing_ok=True)
        except OSError:
            pass
        if not send_command("recording", name=safe_name, cycles=cycles,
                     description=str(data.get("description") or "").strip()):
            return {"ok": False, "message": "Aufnahme konnte nicht gestartet werden."}
        return {"ok": True, "name": safe_name,
                "message": "Aufnahme startet — jetzt ins Spiel wechseln."}

    def recording_stop(self, data: Optional[dict] = None) -> dict:
        """Beendet die Aufnahme; der Hauptprozess baut und speichert die Blöcke."""
        from ...mailbox import send_command
        if not send_command("recording_stop"):
            return {"ok": False, "message": "Stopp konnte nicht gesendet werden."}
        return {"ok": True, "message": "Aufnahme wird beendet und gespeichert."}

    def recording_status(self, data: Optional[dict] = None) -> dict:
        """Die rollende Live-Ausgabe der Aufnahme — höchstens drei Zeilen."""
        import json
        from ...config import RECORD_STATUS_FILE
        try:
            with open(RECORD_STATUS_FILE, "r", encoding="utf-8") as f:
                status = json.load(f)
        except (OSError, ValueError):
            return {"active": False, "paused": False, "count": 0,
                    "events": []}
        return status if isinstance(status, dict) else {
            "active": False, "paused": False, "count": 0, "events": []}

    def run_command(self, data: dict) -> dict:
        """Start, Pause oder Stopp — als Auftrag an den Hauptprozess.

        Dieses Fenster sieht weder `AutoClickerState` noch `stop_event`; es legt einen
        Befehl ab, den der Hauptprozess in seiner Hotkey-Schleife abholt.

        Vor dem Start wird gespeichert — der Hauptprozess lädt die Datei, und ein
        Start-Knopf, der eine ältere Fassung startet als die angezeigte, wäre
        schlimmer als keiner.
        """
        from ...mailbox import send_command
        command = (data or {}).get("command") or ""
        if command not in self.RUN_COMMANDS:
            return self._report(f"Unbekannter Lauf-Befehl '{command}'.", "err")

        arguments: dict = {}
        if command in ("start", "start_manual", "schedule"):
            if self._dirty:
                state_value = self.save()
                if state_value["status"]["kind"] == "err":
                    return state_value      # Meldung steht schon drin, Start faellt aus
            if not self.filepath.exists():
                return self._report("Erst speichern — die Datei gibt es noch nicht.", "warn")
            arguments = {"file": str(self.filepath), "sequence": self.board.name}
        if command == "schedule":
            time_value = str((data or {}).get("time") or "").strip()
            if not time_value:
                return self._report("Bitte eine Startzeit eingeben.", "warn")
            arguments["time"] = time_value
        if command == "manual_action":
            action = str((data or {}).get("action") or "")
            if action not in ("run", "skip", "continue", "stop"):
                return self._report("Unbekannte manuelle Aktion.", "err")
            arguments["action"] = action

        if not send_command(command, **arguments):
            return self._report("Befehl konnte nicht abgelegt werden.", "err")
        text = {"start": f"'{self.board.name}' gestartet.",
                "start_manual": f"'{self.board.name}' im Schrittmodus gestartet.",
                "stop": "Stopp geschickt.",
                "pause": "Pause umgeschaltet.",
                "skip": "Aktuelle Wartezeit wird übersprungen.",
                "skip_step": "Aktueller Block wird vollständig übersprungen.",
                "finish": "Zyklus wird sauber abgeschlossen.",
                "manual": "Manueller Modus umgeschaltet.",
                "manual_action": "Entscheidung geschickt.",
                "schedule": f"Start für '{self.board.name}' geplant."}[command]
        return self._report(text)

    def point_show(self, data: Optional[dict] = None) -> dict:
        """Setzt die Maus im Hauptprozess auf die Stelle des gewählten Blocks.

        „Sitzt der Punkt da, wo ich denke?" beantwortet ein Mauszeiger im Spiel, kein
        Zahlenpaar. Messen kann nur der Hauptprozess — die Auswertung steht deshalb
        in dessen Konsole.
        """
        lane, row, step = self._single()
        if step is None:
            return self.snapshot()
        # Ein Block hat bis zu drei Stellen, und die Frage „sitzt das noch?"
        # stellt sich bei allen dreien: der Klick, der Prüf-Pixel des Triggers
        # und der ELSE-Klick. Welche gemeint ist, sagt der Aufrufer.
        which = (data or {}).get("which") or "click"
        source = {
            "trigger": lambda: step.wait_condition,
            "verify": lambda: step.verify_condition,
            "else": lambda: step.else_config,
        }.get(which)
        point = self._point(source().point_id if source and source() else step.point_id)
        if point is None:
            return self._report("Diese Stelle hat keinen Punkt zum Zeigen.", "warn")

        from ...mailbox import send_command
        if not send_command("show", x=point.x, y=point.y, point=point.id,
                     name=point.name or "", color=list(point.color) if point.color else None):
            return self._report("Befehl konnte nicht abgelegt werden.", "err")
        return self._report(f"Maus zu #{point.id} ({point.x},{point.y}) — im Spiel nachsehen.")

    def block_test(self, data: Optional[dict] = None) -> dict:
        """Führt den gewählten Block einmal im Hauptprozess aus.

        Gesendet werden nur Datei und Position, nicht ein frei konstruierter
        Schritt. Der Hauptprozess lädt dadurch dieselbe gespeicherte Fassung,
        die auch ein echter Lauf verwenden würde.
        """
        lane, row, step = self._single()
        if step is None or lane is None or row is None:
            return self._report("Bitte genau einen Block wählen.", "warn")
        if self._dirty:
            state_value = self.save()
            if state_value["status"]["kind"] == "err":
                return state_value
        loop_index = ([ln for ln in self.board.lanes if ln.kind == "loop"].index(lane)
                      if lane.kind == "loop" else -1)
        from ...mailbox import send_command
        if not send_command("block_test", file=str(self.filepath), phase=lane.kind,
                     phase_index=loop_index, block=int(row)):
            return self._report("Block-Test konnte nicht gesendet werden.", "err")
        return self._report("Block-Test geschickt — echter Klick/Tastendruck möglich.", "warn")

    # ------------------------------------------------------------ Einstellungen

    def _config_file(self) -> tuple:
        """`config.json` als reine Werte — und was beim Lesen schiefging.

        Bewusst nicht `load_config()`: die schreibt die Datei, sobald ein Feld fehlt.
        `({}, "")` heisst „gibt es noch nicht", `({}, "…")` heisst „da liegt etwas
        Unlesbares" — und darauf wird nicht geschrieben.
        """
        import json
        from ...config import CONFIG_FILE
        path = Path(CONFIG_FILE)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}, ""
        except (OSError, ValueError) as error:
            return {}, f"config.json ist nicht lesbar: {error}"
        if not isinstance(raw, dict):
            return {}, "config.json enthält kein Objekt."
        return raw, ""

    def config_read(self, data: Optional[dict] = None) -> dict:
        """Werte, Standardwerte, Abschnitte und Beschreibungen in einem Rutsch.

        Der dritte `ask()`-Kanal. Der Pfad steht absolut dabei: `config.json` liegt
        relativ zum Arbeitsverzeichnis, und welche Datei gemeint ist, darf man nicht
        raten müssen.
        """
        from ...config import (
            AppConfig, CONFIG_FILE, config_sections, optional_fields,
        )
        from ...config_meta import META
        raw, error = self._config_file()
        return {
            "path": str(Path(CONFIG_FILE).resolve()),
            "values": AppConfig.from_dict(raw).to_dict(),
            "defaults": AppConfig().to_dict(),
            "sections": [{"title": t, "keys": list(k)} for t, k in config_sections()],
            "meta": {k: m.as_dict() for k, m in META.items()},
            # Wo ein leeres Eingabefeld `null` heisst und nicht 0.
            "optional": optional_fields(),
            # Was hinter einem Feld gerade WIRKLICH liegt — heute nur der
            # Katalog. Der Pfad allein sagt nicht, ob die Datei da ist und wie
            # alt sie ist, und genau das ist die Frage, die man an eine
            # geholte Liste hat.
            "states": self._config_states(),
            "error": error,
        }

    @staticmethod
    def _catalog_state(path: str) -> str:
        """Umfang und Alter der Katalog-Datei — als ein Satz fuer die Ansicht.

        Gelesen wird die Datei selbst und nicht `load_catalog()`: der Zeitpunkt
        steht als `_erzeugt` drin, und der `Catalog` traegt nur Items und
        Gegner. Ein Fehler ist hier kein Fehlerfall, sondern eine Auskunft —
        „Datei fehlt" ist genau das, was man wissen will, wenn der Knopf
        scheinbar nichts bewirkt hat.
        """
        import json
        from datetime import datetime, timezone
        if not path:
            return ""
        file = Path(path)
        if not file.exists():
            return "Datei fehlt — noch nicht geholt?"
        try:
            raw = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            return f"nicht lesbar ({e})"
        count = len(raw.get("items") or {})
        enemy = len(raw.get("gegner") or [])
        when = str(raw.get("_erzeugt") or "")
        parts = [f"{count} Items", f"{enemy} Gegner"]
        try:
            # `_erzeugt` steht in UTC (…Z). Angezeigt wird Ortszeit — ein
            # Zeitstempel, den man mit der eigenen Uhr vergleichen soll, darf
            # nicht in einer anderen Zone stehen.
            raw_time = datetime.strptime(when, "%Y-%m-%dT%H:%M:%SZ")
            local = raw_time.replace(tzinfo=timezone.utc).astimezone()
            parts.append("geholt am " + local.strftime("%d.%m.%Y um %H:%M"))
        except ValueError:
            if when:
                parts.append("geholt am " + when)
        return " · ".join(parts)

    def _config_states(self) -> dict:
        """Zusatzauskunft je Feld, wo der Wert allein zu wenig sagt."""
        from ...config import CONFIG
        stamp = self._catalog_state(str(CONFIG.scan_catalog_file or "").strip())
        return {"scan_catalog_file": stamp} if stamp else {}

    def config_write(self, data: Optional[dict] = None) -> dict:
        """Schreibt geänderte Werte in `config.json` — und meldet Korrekturen.

        Nur die geänderten Schlüssel, gemischt gegen die Datei wie sie JETZT aussieht:
        der Hauptprozess schreibt dieselbe Datei.

        `__post_init__` hebt ungültige Werte still auf den Standard; im Studio sähe
        das niemand, deshalb wird der geschriebene Stand gegen das Gesendete gehalten
        und die Abweichung zurückgemeldet.
        """
        from ...config import AppConfig, CONFIG, save_config, apply_config
        values = (data or {}).get("values")
        if not isinstance(values, dict) or not values:
            return {"ok": False, "message": "Nichts zu speichern."}

        raw, error = self._config_file()
        if error:
            # Kaputt ist nicht leer: draufschreiben würde den einzigen Rest
            # wegwerfen, den man noch von Hand reparieren kann.
            return {"ok": False, "message": error + " — nicht überschrieben."}

        new = AppConfig.from_dict({**raw, **values})
        done = new.to_dict()
        corrections = [{"key": k, "sent": v, "became": done.get(k)}
                       for k, v in values.items()
                       if k in done and not _same_value(v, done[k])]
        save_config(new)
        # **Der Schreiber war der Einzige, der sich selbst nicht neu lud.** Der
        # Hauptprozess bekommt den Briefkasten-Befehl unten und ruft
        # `command_config()`; DIESER Prozess hat die Datei geschrieben und blieb
        # danach auf den Werten vom Programmstart sitzen — jeder Reiter, der
        # `CONFIG` liest, zeigte bis zum Neustart den alten Stand. Aufgefallen
        # ist es am Bericht-Reiter („session_log_enabled ist aus", direkt nachdem
        # man es eingeschaltet hatte); betroffen war der ganze Baum: die
        # OCR/LLM-Lampen und Marker-Schwellen im Scans-Reiter, die Toleranz beim
        # Farbvergleich im Werkzeuge-Reiter, der Fenstertitel im Teilen-Reiter.
        #
        # `apply_config()` statt einer Zuweisung: das Objekt darf nicht getauscht
        # werden, sonst sitzt jeder mit `from ...config import CONFIG` (imaging,
        # die Scan-Module) weiter auf dem alten. Genau dafuer gibt es die
        # Funktion — ihr Docstring nennt diese Stelle als dritten Aufrufer, nur
        # gerufen hat sie hier nie jemand.
        apply_config(CONFIG, new)
        # Der Hauptprozess hält seinen eigenen Stand im Speicher und merkt von
        # der geschriebenen Datei nichts. Derselbe Briefkasten wie bei Start und
        # Stopp — läuft gerade keiner, verfällt der Befehl (mailbox.MAX_AGE).
        from ...mailbox import send_command
        send_command("config")
        # Was ohne ELSE passiert, steht in derselben Datei — der gemerkte
        # Zeitstempel ist damit veraltet.
        self._cfg_state = -1.0
        return {"ok": True, "values": done, "corrections": corrections}

    def catalog_fetch(self, data: Optional[dict] = None) -> dict:
        """Holt den Item-Katalog aus der Spiel-API und traegt den Pfad ein.

        **Bis hierhin ging das nur auf der Kommandozeile** — ausgerechnet die
        Datei, ohne die das LLM frei raet und die Kategorie leer bleibt, war
        die einzige, die man im Fenster nicht beschaffen konnte. Der
        Einstellungen-Reiter zeigt den Pfad, also gehoert der Knopf dorthin.

        Gerechnet wird in `tools/catalog.py`, mit denselben Funktionen, die die
        Kommandozeile benutzt — dieselbe Richtung wie beim Bericht-Reiter:
        **die Bruecke ruft das Werkzeug, nie umgekehrt.** Der Import steht
        deshalb hier drin und in einem `try`: `tools/` gehoert zum Repo, nicht
        zum Programm.

        Der Pfad wird nur gesetzt, wenn keiner dasteht: wer einen eigenen
        eingetragen hat, bekommt seine Datei aktualisiert und nicht seinen
        Eintrag ueberschrieben.
        """
        import sys
        from ...config import CONFIG

        root_layer = Path(__file__).resolve().parents[3]
        if str(root_layer) not in sys.path:
            sys.path.insert(0, str(root_layer))
        try:
            from tools.catalog import (build_catalog, fetch_game_data,
                                       _summary, STANDARD_ZIEL)
        except ImportError as e:
            return {"ok": False,
                    "message": f"tools/catalog.py nicht gefunden ({e})."}

        target = Path(str(CONFIG.scan_catalog_file or "").strip() or STANDARD_ZIEL)
        # Was das Werkzeug an der Antwort nicht kannte, gehoert in die
        # Statuszeile — auf stderr saehe es im Studio niemand, und ein neues
        # Konstrukt nach einem Spiel-Update ist ein Hinweis, kein Abbruch.
        hints: list = []
        try:
            catalog = build_catalog(fetch_game_data(hints=hints))
        except Exception as e:
            # Netz, DNS, ein geaendertes Antwortformat — alles derselbe Fall
            # fuer den Nutzer: er hat die Datei nicht. Der Grund steht dabei,
            # damit "geht nicht" nicht die ganze Auskunft ist.
            return {"ok": False, "message": f"Nicht erreichbar: {e}"}
        if not catalog.get("items"):
            return {"ok": False, "message": "Die API hat keine Items geliefert — "
                                            "nichts geschrieben."}
        try:
            from ...utils import atomic_write
            import json as _json
            target.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(target, _json.dumps(catalog, ensure_ascii=False, indent=1))
        except OSError as e:
            return {"ok": False, "message": f"Konnte '{target}' nicht schreiben: {e}"}

        message = _summary(catalog).splitlines()[0]
        kind = "ok"
        if hints:
            message += " — " + " ".join(hints)
            kind = "warn"
        if not str(CONFIG.scan_catalog_file or "").strip():
            res = self.config_write({"values": {"scan_catalog_file": str(target)}})
            if not res.get("ok"):
                return {"ok": False,
                        "message": f"{message} — geschrieben nach '{target}', aber der "
                                   f"Pfad liess sich nicht eintragen: "
                                   f"{res.get('message', '')}"}
            return {"ok": True, "kind": kind, "message": f"{message}. Eingetragen: {target}",
                    "path": str(target)}
        return {"ok": True, "kind": kind, "message": f"{message}. Aktualisiert: {target}",
                "path": str(target)}

    def command_pending(self, data: Optional[dict] = None) -> bool:
        """Liegt der letzte Befehl noch im Briefkasten?

        Die einzige Rückmeldung über den Hauptprozess: er leert den Kasten beim Lesen.
        Liegt der Befehl später noch da, hört niemand zu. Fragt nur, ändert nichts.
        """
        from ...mailbox import COMMAND_PATH
        try:
            return COMMAND_PATH.exists()
        except OSError:
            return False

    def load(self, data: dict) -> dict:
        """Öffnet eine gespeicherte Sequenz. Fragt bei ungespeicherten Änderungen."""
        name = (data or {}).get("name") or ""
        if not name:
            return self._report("Keine Sequenz gewählt.", "warn")
        if self._dirty and not (data or {}).get("discard"):
            self._ask = {"kind": "load", "target": name,
                           "title": "Ungespeicherte Änderungen",
                           "text": f"'{self.board.name}' hat ungespeicherte Änderungen. "
                                   "Vor dem Laden speichern?",
                           "proceed_label": "Verwerfen", "save": True}
            return self.snapshot()
        path = next((p for n, p in list_available_sequences() if n == name), None)
        seq = load_sequence_file(path) if path else None
        if seq is None:
            return self._report(f"'{name}' konnte nicht geladen werden.", "err")
        self.board = sequence_to_board(seq)
        self.filepath = Path(path)
        # Punkte neu einlesen: zwischen zwei Sequenzen kann im Hauptprozess ein
        # Punkt dazugekommen sein.
        from .model import palette_from_sequence
        self.points = palette_from_sequence(seq)
        self._scan_init()
        self._scan_load()
        self._selection_clear()
        self._dirty = False
        self._state_remember()
        from ...sequence_studio import remember_last_used
        remember_last_used(self.filepath)
        return self._report(f"Geladen: {name}")

    def new(self, data: Optional[dict] = None) -> dict:
        """Legt eine leere Sequenz an (noch ohne Datei auf Platte)."""
        if self._dirty and not (data or {}).get("discard"):
            self._ask = {"kind": "new", "target": "",
                           "title": "Ungespeicherte Änderungen",
                           "text": f"'{self.board.name}' hat ungespeicherte Änderungen. "
                                   "Vor dem Anlegen speichern?",
                           "proceed_label": "Verwerfen", "save": True}
            return self.snapshot()
        base_name = f"Sequenz_{int(time.time())}"
        # Mit einer Loop-Phase, nicht nur INIT und END: fast jede Sequenz braucht
        # sie, und wer sie nicht braucht, laesst sie leer — eine leere Phase kostet
        # zur Laufzeit nichts (der Worker geht durch null Schritte). Ohne sie war
        # der erste Griff nach dem Anlegen immer derselbe: „+ Loop-Phase".
        self.board = sequence_to_board(Sequence(
            name=base_name, loop_phases=[LoopPhase(name="Ablauf", repeat=1, steps=[])]))
        self.filepath = Path(self.sequences_dir) / sanitize_filename(base_name) / "sequence.json"
        # **Die Punkte gehoeren der Sequenz, nicht dem Fenster.** `load()` ersetzt
        # sie, `new()` liess sie stehen — und `save()` schreibt `self.points`
        # in die Datei: eine frisch angelegte Sequenz kam damit mit dem ganzen
        # Punktebestand der vorher offenen auf die Platte. Ein Rest aus der Zeit
        # der globalen `points.json`, in der genau das richtig war.
        self.points = []
        self._scan_init()
        self._selection_clear()
        self._dirty = False
        self._state_remember()
        return self._report("Neue Sequenz — noch nicht gespeichert.", "warn")

    def sequence_set(self, data: dict) -> dict:
        """Name, Zyklen oder Beschreibung der Sequenz ändern."""
        field, value = (data or {}).get("field"), (data or {}).get("value")
        if field == "name":
            self.board.name = str(value or "")
        elif field == "cycles":
            self.board.total_cycles = max(0, int(value or 0))
        elif field == "description":
            self.board.description = str(value or "")
        else:
            return self._report(f"Unbekanntes Feld '{field}'.", "err")
        return self._changed()

    def _scan_without_name(self) -> Optional[str]:
        """Erster Scan-Block mit leerem Namen, als lesbare Stelle."""
        remaining = scan_warnings(self.board)
        return remaining[0] if remaining else None

    def save(self, data: Optional[dict] = None) -> dict:
        """Schreibt Punkte und Sequenz. Die Datei folgt dem Sequenz-Namen.

        Ein Scan ohne Konfiguration hält das Speichern nicht auf: wer einen Block
        anlegt, um seine Stelle im Ablauf festzuhalten, soll ihn speichern können.
        Repariert ist der Fall dort, wo er kaputt war — `execute_step` überspringt so
        einen Block mit Ansage. Gemeldet wird er hier trotzdem.
        """
        if not (self.board.name or "").strip():
            # Der Name ist etwas anderes: er IST der Dateiname. Ohne ihn gibt es
            # kein Ziel, das Speichern ist nicht unvollstaendig, sondern unmoeglich.
            return self._report("Nicht gespeichert: Sequenz-Name fehlt.", "err")

        old = self.filepath
        new = (Path(self.sequences_dir) / sanitize_filename(self.board.name)
               / "sequence.json")
        renamed = new != old

        # Hat der Hauptprozess dieselbe Datei zwischenzeitlich geschrieben?
        # Beide Prozesse teilen sich den Ordner: eine Aufnahme legt Punkte an,
        # `save_data()` schreibt die Sequenz. Ohne diese Frage gewinnt einfach
        # der Zweite, und die Arbeit des Ersten ist weg — ohne ein Wort.
        foreign = self._changed_externally(old)
        if foreign and not (data or {}).get("force"):
            self._ask = {
                "kind": "save",
                "title": "Ausserhalb geändert",
                "text": f"{foreign} wurde geändert, seit diese Sequenz geöffnet ist — "
                        "vermutlich vom Hauptprozess. Speichern überschreibt das.",
                "proceed_label": "Trotzdem speichern",
                "save": False,
            }
            return self.snapshot()

        # Der Ordner ist die Besitzeinheit. Beim Umbenennen wandern deshalb
        # Scans, Vorlagen und Bilder gemeinsam mit der Sequenz.
        old_folder = old.parent
        new_folder = new.parent
        moved = False
        if renamed and old.exists():
            if new_folder.exists():
                return self._report(
                    f"Nicht gespeichert: Ordner '{new_folder.name}' existiert bereits.",
                    "err")
            try:
                old_folder.rename(new_folder)
                moved = True
            except OSError as error:
                return self._report(f"Sequenzordner konnte nicht umbenannt werden: {error}",
                                   "err")

        from .model import palette_to_points
        sequence = board_to_sequence(self.board)
        sequence.points = palette_to_points(self.points)
        if not save_sequence_file(sequence, new):
            if moved:
                try:
                    new_folder.rename(old_folder)
                except OSError:
                    pass
            return self._report("Speichern fehlgeschlagen!", "err")

        self.filepath = new
        if moved:
            self._scan_init()
            self._scan_load()
        self._saved = True
        self._dirty = False
        self._state_remember()
        from ...sequence_studio import remember_last_used
        remember_last_used(self.filepath)
        text = f"Gespeichert: {new.name}"
        if moved:
            text = f"Umbenannt → {new_folder.name}/ (alle Scans mitgenommen)"

        empty = self._scan_without_name()
        if empty:
            return self._report(f"{text} — {empty} hat noch keine Konfiguration "
                               f"und wird übersprungen.", "warn")
        return self._report(text)

    def _changed_externally(self, target) -> str:
        """Welche Datei sich seit dem Laden von aussen geändert hat (leer = keine).

        `target` ist die geladene Datei, auch vor dem Umbenennen: deren Inhalt
        wird beim anschliessenden Speichern ersetzt. `sequence.json` wird immer
        geprüft: die schreibt das Studio bei jedem Speichern mit, und der
        Hauptprozess legt dort während einer Aufnahme neue Punkte an.
        """
        if target is not None and _mtime(target) not in (None, self._state_file):
            return Path(target).name
        return ""

    def _state_remember(self) -> None:
        """Nach dem Schreiben (oder Laden) den Stand der Dateien festhalten."""
        # EIN Stand fuer beides: die Punkte stehen im Feld `points`
        # derselben Datei. Hier lag daneben ein `_stand_punkte`, das
        # dreimal gesetzt und nirgends gelesen wurde — ein Rest aus der
        # Zeit der eigenen `points.json`.
        self._state_file = _mtime(self.filepath)

    def rescue_write(self) -> Optional[Path]:
        """Sichert ungespeicherte Änderungen beim Schliessen des Fensters.

        Gefragt wird nicht: das Fenster ist zu diesem Zeitpunkt schon auf dem Weg
        nach draussen. Die Kopie landet unter `backups/`, nicht in `sequences/` —
        dort listet `list_available_sequences()` jede `*.json` als Sequenz auf,
        und eine halbfertige Rettungsdatei zwischen den echten wäre schlimmer als
        der Verlust.
        """
        if not self._dirty:
            return None
        from ...persistence.sweep import backup_path
        # backup_path() liefert "<name>.json.bak" — hier soll die Datei lesbar
        # heissen und eine echte .json-Endung tragen, damit man sie direkt
        # zurückkopieren kann.
        target = backup_path(self.filepath).with_name(
            f"{self.filepath.stem}.ungespeichert.json")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            from .model import palette_to_points
            sequence = board_to_sequence(self.board)
            sequence.points = palette_to_points(self.points)
            if save_sequence_file(sequence, target):
                return target
        except (IOError, OSError):
            return None
        return None
