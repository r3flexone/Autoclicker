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
    _gleicher_wert,
    _hex,
    _mtime,
    scan_warnungen,
)
from .model import (
    BLOCK_COLORS,
    BLOCK_LABELS,
    board_to_sequence,
    sequence_to_board,
)


class BridgeServicesMixin:
    """Kapselt Persistenz, Laufsteuerung und Konfiguration."""

    def sequenz_liste(self, data: Optional[dict] = None) -> list[dict]:
        """Kennzahlen aller gespeicherten Sequenzen für die Übersicht.

        Keine Momentaufnahme — deshalb über `frage()` zu holen, sonst zerschösse die
        Antwort den Editor-Zustand. Über `load_sequence_file()`, damit Migration und
        Punkt-Auflösung mitlaufen. Nur Kennzahlen, keine Schritte.
        """
        raus: list[dict] = []
        wurzel = Path(self.sequences_dir)
        dateien = sorted(
            (folder / "sequence.json" for folder in wurzel.iterdir()
             if folder.is_dir() and (folder / "sequence.json").exists()),
            key=lambda path: path.parent.name,
        ) if wurzel.exists() else []
        for path in dateien:
            gespeicherter_name = path.parent.name
            try:
                geaendert = path.stat().st_mtime
            except OSError:
                geaendert = 0.0
            seq = load_sequence_file(path)
            if seq is None:
                # Auch die defekte bekommt ihren Umfang: sie ist der haeufigste
                # Grund, ueberhaupt loeschen zu wollen — und dann will man
                # wissen, was am Ordner sonst noch haengt.
                raus.append({"name": gespeicherter_name, "datei": str(path), "defekt": True,
                             "geaendert": geaendert, "offen": path == self.filepath,
                             "umfang": self._sequenz_umfang(path.parent)})
                continue
            raus.append({
                "name": seq.name,
                "datei": str(path),
                "defekt": False,
                "beschreibung": seq.description,
                "zyklen": seq.total_cycles,
                "init": len(seq.init_steps),
                "end": len(seq.end_steps),
                "phasen": [{"name": lp.name, "schritte": len(lp.steps),
                            "wiederholungen": lp.repeat,
                            "start": lp.scheduled_start or ""}
                           for lp in seq.loop_phases],
                "schritte": seq.total_steps(),
                "geaendert": geaendert,
                "offen": path == self.filepath,
                "umfang": self._sequenz_umfang(path.parent),
                "warnungen": scan_warnungen(sequence_to_board(seq)),
            })
        return raus

    # Was in einem Sequenzordner ausser der sequence.json noch liegt. Reihenfolge
    # = Anzeige; der Schluessel ist der Unterordner.
    #
    # **Einzahl und Mehrzahl stehen beide da.** Die Ansicht haengte erst ein "n"
    # an, und das ergab "2x Item-Scann" und "3x gemerkter Bildschirmn" - bei drei
    # von fuenf Woertern falsch. Deutsche Mehrzahl ist keine Regel, die man in
    # einer Zeile JavaScript trifft; sie gehoert zu den Daten.
    _UMFANG = (("item_scans", "Item-Scan", "Item-Scans"),
               ("boss_scans", "Boss-Scan", "Boss-Scans"),
               ("icon_scans", "Icon-Scan", "Icon-Scans"),
               ("templates", "Vorlage", "Vorlagen"),
               ("bilder", "gemerkter Bildschirm", "gemerkte Bildschirme"))

    @classmethod
    def _sequenz_umfang(cls, folder: Path) -> list[dict]:
        """Was am Sequenzordner haengt — fuer die Rueckfrage vor dem Loeschen.

        Eine Sequenz ist eine **Besitzeinheit**: Scans, Vorlagen und gemerkte
        Bildschirme liegen in ihrem Ordner und gehen mit ihr. Wer das nicht
        vorher liest, loescht einen Nachmittag Arbeit an Item-Vorlagen mit, weil
        er „nur die Sequenz" wegraeumen wollte.
        """
        raus = []
        for unter, eins, viele in cls._UMFANG:
            try:
                n = sum(1 for p in (folder / unter).iterdir() if p.is_file())
            except OSError:
                n = 0
            if n:
                raus.append({"art": unter, "wort": eins if n == 1 else viele,
                             "anzahl": n})
        return raus

    def _sequenz_ordner(self, name: str) -> Optional[Path]:
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
        `sequenz_liste()` meldet sie unter ihrem Ordnernamen, also ist der der
        zweite Weg.

        Nebenbei schliesst das den Pfad: `name` kommt aus dem Fenster, und ein
        `..` darin fuehrte beim blossen Zusammenhaengen aus `sequences/`
        heraus. Was hier nicht als Eintrag dasteht, gibt es nicht.
        """
        for entry, path in list_available_sequences():
            if entry == name:
                return Path(path).parent
        wurzel = Path(self.sequences_dir)
        if wurzel.is_dir():
            for folder in wurzel.iterdir():
                if folder.is_dir() and folder.name == name:
                    return folder
        return None

    def sequenz_loeschen(self, data: Optional[dict] = None) -> dict:
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
            return {"ok": False, "meldung": "Keine Sequenz genannt."}
        folder = self._sequenz_ordner(name)
        if folder is None or not folder.is_dir():
            return {"ok": False, "meldung": f"'{name}' gibt es nicht (mehr)."}
        if folder.resolve() == self.filepath.parent.resolve():
            return {"ok": False, "meldung": (
                f"'{name}' ist gerade geöffnet. Erst eine andere laden — sonst "
                "legt der nächste Druck auf Speichern den Ordner wieder an.")}
        if self._laeuft():
            return {"ok": False, "meldung": (
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
        except (OSError, shutil.Error) as fehler:
            return {"ok": False, "meldung": f"Konnte nicht wegräumen: {fehler}"}
        return {"ok": True, "meldung": f"'{name}' liegt jetzt unter {target}."}

    def lauf_status(self, data: Optional[dict] = None) -> dict:
        """Was gerade läuft — gelesen aus der Statusdatei des Hauptprozesses.

        Der zweite `frage()`-Kanal, und nie ein Fehler: dass nichts läuft, ist der
        Normalfall. Die Datei ist der gemeinsame Nenner zwischen beiden Prozessen.
        """
        import json
        from ...config import RUN_STATUS_FILE
        try:
            with open(RUN_STATUS_FILE, "r", encoding="utf-8") as f:
                zustand = json.load(f)
        except (OSError, ValueError):
            return {"aktiv": False}
        if not isinstance(zustand, dict):
            return {"aktiv": False}
        # Ein abgeschlossener Lauf (`ende`) darf beliebig alt sein — er IST
        # Vergangenheit. Die Altersregel gilt nur für einen, der sich noch für
        # laufend hält.
        if not zustand.get("aktiv"):
            return zustand if (zustand.get("ende") or zustand.get("countdown")) else {"aktiv": False}
        # Älter als 5 s heisst: der Schreiber lebt nicht mehr. Ein abgestürzter
        # Lauf soll nicht ewig als „läuft" in der Oberfläche stehen — der Worker
        # schreibt spätestens alle 200 ms, und selbst ein Schritt, der auf eine
        # Farbe wartet, geht durch `execute_step`.
        if time.time() - float(zustand.get("stand") or 0) > 5:
            return {"aktiv": False, "verwaist": True}
        # Typ → Farbe und Marke: die Laufzeit schreibt nur den Schlüssel, weil
        # `runtime/` die Ansicht nicht kennen darf. Übersetzt wird hier, damit
        # der laufende Block dieselbe Farbe trägt wie seine Karte im Board — die
        # Farbe ist die Legende, und sie muss in beiden Ansichten dieselbe sein.
        typ = zustand.get("block_typ")
        if typ in BLOCK_COLORS:
            zustand["block_farbe"] = _hex(BLOCK_COLORS[typ])
            zustand["block_marke"] = BLOCK_LABELS[typ]
        return zustand

    # Was das Studio dem Hauptprozess sagen darf. Die Gegenstelle ist `COMMANDS`
    # in handlers.py — ein Test hält beide Listen gegeneinander, denn laufen sie
    # auseinander, tut ein Knopf einfach nichts und niemand merkt es.
    LAUF_BEFEHLE = ("start", "start_manuell", "stop", "pause", "skip", "skip_step", "finish",
                    "manuell", "manuell_aktion", "zeitplan")
    # Alles, was das Studio dem Hauptprozess sagen darf. „zeigen" steuert keinen
    # Lauf, geht aber denselben Weg — der Test haelt DIESE Liste gegen `COMMANDS`.
    # „nachklick" ist der Werkzeuge-Reiter: die Klick-Runde braucht einen
    # systemweiten Maus-Hook und muss deshalb drueben laufen.
    ALLE_BEFEHLE = LAUF_BEFEHLE + ("zeigen", "config", "daten", "aufnahme",
                                   "aufnahme_stop",
                                   "programm_beenden",
                                   "nachklick", "nachklick_stop", "block_test")

    def aufnahme_starten(self, data: Optional[dict] = None) -> dict:
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
            return {"ok": False, "meldung": "Bitte zuerst einen Namen eingeben."}
        sicher = sanitize_filename(name)
        target = Path(self.sequences_dir) / sicher / "sequence.json"
        if target.exists():
            return {"ok": False, "meldung": f"'{sicher}' gibt es bereits."}
        try:
            cycles = max(0, int(data.get("zyklen") or 0))
        except (TypeError, ValueError):
            return {"ok": False, "meldung": "Zyklen müssen eine ganze Zahl sein."}
        # Die drei Zeilen der vorigen Aufnahme sollen beim neuen Start nicht
        # noch für einen Augenblick als neue Ereignisse aufblitzen.
        from ...config import RECORD_STATUS_FILE
        try:
            Path(RECORD_STATUS_FILE).unlink(missing_ok=True)
        except OSError:
            pass
        if not send_command("aufnahme", name=sicher, cycles=cycles,
                     description=str(data.get("beschreibung") or "").strip()):
            return {"ok": False, "meldung": "Aufnahme konnte nicht gestartet werden."}
        return {"ok": True, "name": sicher,
                "meldung": "Aufnahme startet — jetzt ins Spiel wechseln."}

    def aufnahme_stoppen(self, data: Optional[dict] = None) -> dict:
        """Beendet die Aufnahme; der Hauptprozess baut und speichert die Blöcke."""
        from ...mailbox import send_command
        if not send_command("aufnahme_stop"):
            return {"ok": False, "meldung": "Stopp konnte nicht gesendet werden."}
        return {"ok": True, "meldung": "Aufnahme wird beendet und gespeichert."}

    def aufnahme_status(self, data: Optional[dict] = None) -> dict:
        """Die rollende Live-Ausgabe der Aufnahme — höchstens drei Zeilen."""
        import json
        from ...config import RECORD_STATUS_FILE
        try:
            with open(RECORD_STATUS_FILE, "r", encoding="utf-8") as f:
                status = json.load(f)
        except (OSError, ValueError):
            return {"aktiv": False, "pausiert": False, "anzahl": 0,
                    "ereignisse": []}
        return status if isinstance(status, dict) else {
            "aktiv": False, "pausiert": False, "anzahl": 0, "ereignisse": []}

    def lauf_befehl(self, data: dict) -> dict:
        """Start, Pause oder Stopp — als Auftrag an den Hauptprozess.

        Dieses Fenster sieht weder `AutoClickerState` noch `stop_event`; es legt einen
        Befehl ab, den der Hauptprozess in seiner Hotkey-Schleife abholt.

        Vor dem Start wird gespeichert — der Hauptprozess lädt die Datei, und ein
        Start-Knopf, der eine ältere Fassung startet als die angezeigte, wäre
        schlimmer als keiner.
        """
        from ...mailbox import send_command
        command = (data or {}).get("befehl") or ""
        if command not in self.LAUF_BEFEHLE:
            return self._melde(f"Unbekannter Lauf-Befehl '{command}'.", "err")

        arguments: dict = {}
        if command in ("start", "start_manuell", "zeitplan"):
            if self._dirty:
                zustand = self.speichern()
                if zustand["status"]["art"] == "err":
                    return zustand      # Meldung steht schon drin, Start faellt aus
            if not self.filepath.exists():
                return self._melde("Erst speichern — die Datei gibt es noch nicht.", "warn")
            arguments = {"file": str(self.filepath), "sequence": self.board.name}
        if command == "zeitplan":
            zeit = str((data or {}).get("zeit") or "").strip()
            if not zeit:
                return self._melde("Bitte eine Startzeit eingeben.", "warn")
            arguments["time"] = zeit
        if command == "manuell_aktion":
            aktion = str((data or {}).get("aktion") or "")
            if aktion not in ("run", "skip", "continue", "stop"):
                return self._melde("Unbekannte manuelle Aktion.", "err")
            arguments["action"] = aktion

        if not send_command(command, **arguments):
            return self._melde("Befehl konnte nicht abgelegt werden.", "err")
        text = {"start": f"'{self.board.name}' gestartet.",
                "start_manuell": f"'{self.board.name}' im Schrittmodus gestartet.",
                "stop": "Stopp geschickt.",
                "pause": "Pause umgeschaltet.",
                "skip": "Aktuelle Wartezeit wird übersprungen.",
                "skip_step": "Aktueller Block wird vollständig übersprungen.",
                "finish": "Zyklus wird sauber abgeschlossen.",
                "manuell": "Manueller Modus umgeschaltet.",
                "manuell_aktion": "Entscheidung geschickt.",
                "zeitplan": f"Start für '{self.board.name}' geplant."}[command]
        return self._melde(text)

    def punkt_zeigen(self, data: Optional[dict] = None) -> dict:
        """Setzt die Maus im Hauptprozess auf die Stelle des gewählten Blocks.

        „Sitzt der Punkt da, wo ich denke?" beantwortet ein Mauszeiger im Spiel, kein
        Zahlenpaar. Messen kann nur der Hauptprozess — die Auswertung steht deshalb
        in dessen Konsole.
        """
        lane, row, step = self._einzelner()
        if step is None:
            return self.snapshot()
        # Ein Block hat bis zu drei Stellen, und die Frage „sitzt das noch?"
        # stellt sich bei allen dreien: der Klick, der Prüf-Pixel des Triggers
        # und der ELSE-Klick. Welche gemeint ist, sagt der Aufrufer.
        welche = (data or {}).get("welche") or "klick"
        source = {
            "trigger": lambda: step.wait_condition,
            "verify": lambda: step.verify_condition,
            "else": lambda: step.else_config,
        }.get(welche)
        point = self._punkt(source().point_id if source and source() else step.point_id)
        if point is None:
            return self._melde("Diese Stelle hat keinen Punkt zum Zeigen.", "warn")

        from ...mailbox import send_command
        if not send_command("zeigen", x=point.x, y=point.y, point=point.id,
                     name=point.name or "", color=list(point.color) if point.color else None):
            return self._melde("Befehl konnte nicht abgelegt werden.", "err")
        return self._melde(f"Maus zu #{point.id} ({point.x},{point.y}) — im Spiel nachsehen.")

    def block_testen(self, data: Optional[dict] = None) -> dict:
        """Führt den gewählten Block einmal im Hauptprozess aus.

        Gesendet werden nur Datei und Position, nicht ein frei konstruierter
        Schritt. Der Hauptprozess lädt dadurch dieselbe gespeicherte Fassung,
        die auch ein echter Lauf verwenden würde.
        """
        lane, row, step = self._einzelner()
        if step is None or lane is None or row is None:
            return self._melde("Bitte genau einen Block wählen.", "warn")
        if self._dirty:
            zustand = self.speichern()
            if zustand["status"]["art"] == "err":
                return zustand
        loop_index = ([ln for ln in self.board.lanes if ln.kind == "loop"].index(lane)
                      if lane.kind == "loop" else -1)
        from ...mailbox import send_command
        if not send_command("block_test", file=str(self.filepath), phase=lane.kind,
                     phase_index=loop_index, block=int(row)):
            return self._melde("Block-Test konnte nicht gesendet werden.", "err")
        return self._melde("Block-Test geschickt — echter Klick/Tastendruck möglich.", "warn")

    # ------------------------------------------------------------ Einstellungen

    def _config_datei(self) -> tuple:
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
        except (OSError, ValueError) as fehler:
            return {}, f"config.json ist nicht lesbar: {fehler}"
        if not isinstance(raw, dict):
            return {}, "config.json enthält kein Objekt."
        return raw, ""

    def config_lesen(self, data: Optional[dict] = None) -> dict:
        """Werte, Standardwerte, Abschnitte und Beschreibungen in einem Rutsch.

        Der dritte `frage()`-Kanal. Der Pfad steht absolut dabei: `config.json` liegt
        relativ zum Arbeitsverzeichnis, und welche Datei gemeint ist, darf man nicht
        raten müssen.
        """
        from ...config import (
            AppConfig, CONFIG_FILE, config_sections, optional_fields,
        )
        from ...config_meta import META
        raw, fehler = self._config_datei()
        return {
            "pfad": str(Path(CONFIG_FILE).resolve()),
            "werte": AppConfig.from_dict(raw).to_dict(),
            "standard": AppConfig().to_dict(),
            "abschnitte": [{"titel": t, "keys": list(k)} for t, k in config_sections()],
            "meta": {k: m.as_dict() for k, m in META.items()},
            # Wo ein leeres Eingabefeld `null` heisst und nicht 0.
            "optional": optional_fields(),
            # Was hinter einem Feld gerade WIRKLICH liegt — heute nur der
            # Katalog. Der Pfad allein sagt nicht, ob die Datei da ist und wie
            # alt sie ist, und genau das ist die Frage, die man an eine
            # geholte Liste hat.
            "staende": self._config_staende(),
            "fehler": fehler,
        }

    @staticmethod
    def _katalog_stand(path: str) -> str:
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
        gegner = len(raw.get("gegner") or [])
        wann = str(raw.get("_erzeugt") or "")
        parts = [f"{count} Items", f"{gegner} Gegner"]
        try:
            # `_erzeugt` steht in UTC (…Z). Angezeigt wird Ortszeit — ein
            # Zeitstempel, den man mit der eigenen Uhr vergleichen soll, darf
            # nicht in einer anderen Zone stehen.
            roh_zeit = datetime.strptime(wann, "%Y-%m-%dT%H:%M:%SZ")
            lokal = roh_zeit.replace(tzinfo=timezone.utc).astimezone()
            parts.append("geholt am " + lokal.strftime("%d.%m.%Y um %H:%M"))
        except ValueError:
            if wann:
                parts.append("geholt am " + wann)
        return " · ".join(parts)

    def _config_staende(self) -> dict:
        """Zusatzauskunft je Feld, wo der Wert allein zu wenig sagt."""
        from ...config import CONFIG
        stand = self._katalog_stand(str(CONFIG.scan_catalog_file or "").strip())
        return {"scan_catalog_file": stand} if stand else {}

    def config_schreiben(self, data: Optional[dict] = None) -> dict:
        """Schreibt geänderte Werte in `config.json` — und meldet Korrekturen.

        Nur die geänderten Schlüssel, gemischt gegen die Datei wie sie JETZT aussieht:
        der Hauptprozess schreibt dieselbe Datei.

        `__post_init__` hebt ungültige Werte still auf den Standard; im Studio sähe
        das niemand, deshalb wird der geschriebene Stand gegen das Gesendete gehalten
        und die Abweichung zurückgemeldet.
        """
        from ...config import AppConfig, CONFIG, save_config, apply_config
        values = (data or {}).get("werte")
        if not isinstance(values, dict) or not values:
            return {"ok": False, "meldung": "Nichts zu speichern."}

        raw, fehler = self._config_datei()
        if fehler:
            # Kaputt ist nicht leer: draufschreiben würde den einzigen Rest
            # wegwerfen, den man noch von Hand reparieren kann.
            return {"ok": False, "meldung": fehler + " — nicht überschrieben."}

        new = AppConfig.from_dict({**raw, **values})
        fertig = new.to_dict()
        korrekturen = [{"key": k, "gesendet": v, "wurde": fertig.get(k)}
                       for k, v in values.items()
                       if k in fertig and not _gleicher_wert(v, fertig[k])]
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
        self._cfg_stand = -1.0
        return {"ok": True, "werte": fertig, "korrekturen": korrekturen}

    def katalog_holen(self, data: Optional[dict] = None) -> dict:
        """Holt den Item-Katalog aus der Spiel-API und traegt den Pfad ein.

        **Bis hierhin ging das nur auf der Kommandozeile** — ausgerechnet die
        Datei, ohne die das LLM frei raet und die Kategorie leer bleibt, war
        die einzige, die man im Fenster nicht beschaffen konnte. Der
        Einstellungen-Reiter zeigt den Pfad, also gehoert der Knopf dorthin.

        Gerechnet wird in `tools/katalog.py`, mit denselben Funktionen, die die
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

        wurzel = Path(__file__).resolve().parents[3]
        if str(wurzel) not in sys.path:
            sys.path.insert(0, str(wurzel))
        try:
            from tools.katalog import (baue_katalog, hole_spieldaten,
                                       _zusammenfassung, STANDARD_ZIEL)
        except ImportError as e:
            return {"ok": False,
                    "meldung": f"tools/katalog.py nicht gefunden ({e})."}

        target = Path(str(CONFIG.scan_catalog_file or "").strip() or STANDARD_ZIEL)
        # Was das Werkzeug an der Antwort nicht kannte, gehoert in die
        # Statuszeile — auf stderr saehe es im Studio niemand, und ein neues
        # Konstrukt nach einem Spiel-Update ist ein Hinweis, kein Abbruch.
        hinweise: list = []
        try:
            katalog = baue_katalog(hole_spieldaten(hinweise=hinweise))
        except Exception as e:
            # Netz, DNS, ein geaendertes Antwortformat — alles derselbe Fall
            # fuer den Nutzer: er hat die Datei nicht. Der Grund steht dabei,
            # damit "geht nicht" nicht die ganze Auskunft ist.
            return {"ok": False, "meldung": f"Nicht erreichbar: {e}"}
        if not katalog.get("items"):
            return {"ok": False, "meldung": "Die API hat keine Items geliefert — "
                                            "nichts geschrieben."}
        try:
            from ...utils import atomic_write
            import json as _json
            target.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(target, _json.dumps(katalog, ensure_ascii=False, indent=1))
        except OSError as e:
            return {"ok": False, "meldung": f"Konnte '{target}' nicht schreiben: {e}"}

        message = _zusammenfassung(katalog).splitlines()[0]
        kind = "ok"
        if hinweise:
            message += " — " + " ".join(hinweise)
            kind = "warn"
        if not str(CONFIG.scan_catalog_file or "").strip():
            erg = self.config_schreiben({"werte": {"scan_catalog_file": str(target)}})
            if not erg.get("ok"):
                return {"ok": False,
                        "meldung": f"{message} — geschrieben nach '{target}', aber der "
                                   f"Pfad liess sich nicht eintragen: "
                                   f"{erg.get('meldung', '')}"}
            return {"ok": True, "art": kind, "meldung": f"{message}. Eingetragen: {target}",
                    "pfad": str(target)}
        return {"ok": True, "art": kind, "meldung": f"{message}. Aktualisiert: {target}",
                "pfad": str(target)}

    def befehl_offen(self, data: Optional[dict] = None) -> bool:
        """Liegt der letzte Befehl noch im Briefkasten?

        Die einzige Rückmeldung über den Hauptprozess: er leert den Kasten beim Lesen.
        Liegt der Befehl später noch da, hört niemand zu. Fragt nur, ändert nichts.
        """
        from ...mailbox import COMMAND_PATH
        try:
            return COMMAND_PATH.exists()
        except OSError:
            return False

    def laden(self, data: dict) -> dict:
        """Öffnet eine gespeicherte Sequenz. Fragt bei ungespeicherten Änderungen."""
        name = (data or {}).get("name") or ""
        if not name:
            return self._melde("Keine Sequenz gewählt.", "warn")
        if self._dirty and not (data or {}).get("verwerfen"):
            self._ask = {"art": "laden", "ziel": name,
                           "titel": "Ungespeicherte Änderungen",
                           "text": f"'{self.board.name}' hat ungespeicherte Änderungen. "
                                   "Vor dem Laden speichern?",
                           "weiter": "Verwerfen", "speichern": True}
            return self.snapshot()
        path = next((p for n, p in list_available_sequences() if n == name), None)
        seq = load_sequence_file(path) if path else None
        if seq is None:
            return self._melde(f"'{name}' konnte nicht geladen werden.", "err")
        self.board = sequence_to_board(seq)
        self.filepath = Path(path)
        # Punkte neu einlesen: zwischen zwei Sequenzen kann im Hauptprozess ein
        # Punkt dazugekommen sein.
        from .model import palette_from_sequence
        self.points = palette_from_sequence(seq)
        self._scan_init()
        self._scan_laden()
        self._auswahl_leeren()
        self._dirty = False
        self._stand_merken()
        from ...sequence_studio import remember_last_used
        remember_last_used(self.filepath)
        return self._melde(f"Geladen: {name}")

    def new(self, data: Optional[dict] = None) -> dict:
        """Legt eine leere Sequenz an (noch ohne Datei auf Platte)."""
        if self._dirty and not (data or {}).get("verwerfen"):
            self._ask = {"art": "neu", "ziel": "",
                           "titel": "Ungespeicherte Änderungen",
                           "text": f"'{self.board.name}' hat ungespeicherte Änderungen. "
                                   "Vor dem Anlegen speichern?",
                           "weiter": "Verwerfen", "speichern": True}
            return self.snapshot()
        basis = f"Sequenz_{int(time.time())}"
        # Mit einer Loop-Phase, nicht nur INIT und END: fast jede Sequenz braucht
        # sie, und wer sie nicht braucht, laesst sie leer — eine leere Phase kostet
        # zur Laufzeit nichts (der Worker geht durch null Schritte). Ohne sie war
        # der erste Griff nach dem Anlegen immer derselbe: „+ Loop-Phase".
        self.board = sequence_to_board(Sequence(
            name=basis, loop_phases=[LoopPhase(name="Ablauf", repeat=1, steps=[])]))
        self.filepath = Path(self.sequences_dir) / sanitize_filename(basis) / "sequence.json"
        # **Die Punkte gehoeren der Sequenz, nicht dem Fenster.** `laden()` ersetzt
        # sie, `new()` liess sie stehen — und `speichern()` schreibt `self.points`
        # in die Datei: eine frisch angelegte Sequenz kam damit mit dem ganzen
        # Punktebestand der vorher offenen auf die Platte. Ein Rest aus der Zeit
        # der globalen `points.json`, in der genau das richtig war.
        self.points = []
        self._scan_init()
        self._auswahl_leeren()
        self._dirty = False
        self._stand_merken()
        return self._melde("Neue Sequenz — noch nicht gespeichert.", "warn")

    def sequenz_setzen(self, data: dict) -> dict:
        """Name, Zyklen oder Beschreibung der Sequenz ändern."""
        feld, value = (data or {}).get("feld"), (data or {}).get("wert")
        if feld == "name":
            self.board.name = str(value or "")
        elif feld == "zyklen":
            self.board.total_cycles = max(0, int(value or 0))
        elif feld == "beschreibung":
            self.board.description = str(value or "")
        else:
            return self._melde(f"Unbekanntes Feld '{feld}'.", "err")
        return self._geaendert()

    def _scan_without_name(self) -> Optional[str]:
        """Erster Scan-Block mit leerem Namen, als lesbare Stelle."""
        offen = scan_warnungen(self.board)
        return offen[0] if offen else None

    def speichern(self, data: Optional[dict] = None) -> dict:
        """Schreibt Punkte und Sequenz. Die Datei folgt dem Sequenz-Namen.

        Ein Scan ohne Konfiguration hält das Speichern nicht auf: wer einen Block
        anlegt, um seine Stelle im Ablauf festzuhalten, soll ihn speichern können.
        Repariert ist der Fall dort, wo er kaputt war — `execute_step` überspringt so
        einen Block mit Ansage. Gemeldet wird er hier trotzdem.
        """
        if not (self.board.name or "").strip():
            # Der Name ist etwas anderes: er IST der Dateiname. Ohne ihn gibt es
            # kein Ziel, das Speichern ist nicht unvollstaendig, sondern unmoeglich.
            return self._melde("Nicht gespeichert: Sequenz-Name fehlt.", "err")

        old = self.filepath
        new = (Path(self.sequences_dir) / sanitize_filename(self.board.name)
               / "sequence.json")
        umbenannt = new != old

        # Hat der Hauptprozess dieselbe Datei zwischenzeitlich geschrieben?
        # Beide Prozesse teilen sich den Ordner: eine Aufnahme legt Punkte an,
        # `save_data()` schreibt die Sequenz. Ohne diese Frage gewinnt einfach
        # der Zweite, und die Arbeit des Ersten ist weg — ohne ein Wort.
        fremd = self._fremd_geaendert(old)
        if fremd and not (data or {}).get("erzwingen"):
            self._ask = {
                "art": "speichern",
                "titel": "Ausserhalb geändert",
                "text": f"{fremd} wurde geändert, seit diese Sequenz geöffnet ist — "
                        "vermutlich vom Hauptprozess. Speichern überschreibt das.",
                "weiter": "Trotzdem speichern",
                "speichern": False,
            }
            return self.snapshot()

        # Der Ordner ist die Besitzeinheit. Beim Umbenennen wandern deshalb
        # Scans, Vorlagen und Bilder gemeinsam mit der Sequenz.
        alt_ordner = old.parent
        neu_ordner = new.parent
        verschoben = False
        if umbenannt and old.exists():
            if neu_ordner.exists():
                return self._melde(
                    f"Nicht gespeichert: Ordner '{neu_ordner.name}' existiert bereits.",
                    "err")
            try:
                alt_ordner.rename(neu_ordner)
                verschoben = True
            except OSError as fehler:
                return self._melde(f"Sequenzordner konnte nicht umbenannt werden: {fehler}",
                                   "err")

        from .model import palette_to_points
        sequence = board_to_sequence(self.board)
        sequence.points = palette_to_points(self.points)
        if not save_sequence_file(sequence, new):
            if verschoben:
                try:
                    neu_ordner.rename(alt_ordner)
                except OSError:
                    pass
            return self._melde("Speichern fehlgeschlagen!", "err")

        self.filepath = new
        if verschoben:
            self._scan_init()
            self._scan_laden()
        self._gespeichert = True
        self._dirty = False
        self._stand_merken()
        from ...sequence_studio import remember_last_used
        remember_last_used(self.filepath)
        text = f"Gespeichert: {new.name}"
        if verschoben:
            text = f"Umbenannt → {neu_ordner.name}/ (alle Scans mitgenommen)"

        leer = self._scan_without_name()
        if leer:
            return self._melde(f"{text} — {leer} hat noch keine Konfiguration "
                               f"und wird übersprungen.", "warn")
        return self._melde(text)

    def _fremd_geaendert(self, target) -> str:
        """Welche Datei sich seit dem Laden von aussen geändert hat (leer = keine).

        `target` ist die geladene Datei, auch vor dem Umbenennen: deren Inhalt
        wird beim anschliessenden Speichern ersetzt. `sequence.json` wird immer
        geprüft: die schreibt das Studio bei jedem Speichern mit, und der
        Hauptprozess legt dort während einer Aufnahme neue Punkte an.
        """
        if target is not None and _mtime(target) not in (None, self._stand_datei):
            return Path(target).name
        return ""

    def _stand_merken(self) -> None:
        """Nach dem Schreiben (oder Laden) den Stand der Dateien festhalten."""
        # EIN Stand fuer beides: die Punkte stehen im Feld `points`
        # derselben Datei. Hier lag daneben ein `_stand_punkte`, das
        # dreimal gesetzt und nirgends gelesen wurde — ein Rest aus der
        # Zeit der eigenen `points.json`.
        self._stand_datei = _mtime(self.filepath)

    def rettung_schreiben(self) -> Optional[Path]:
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
