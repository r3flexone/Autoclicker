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

    def sequenz_liste(self, daten: Optional[dict] = None) -> list[dict]:
        """Kennzahlen aller gespeicherten Sequenzen für die Übersicht.

        Keine Momentaufnahme — deshalb über `frage()` zu holen, sonst zerschösse die
        Antwort den Editor-Zustand. Über `load_sequence_file()`, damit Migration und
        Punkt-Auflösung mitlaufen. Nur Kennzahlen, keine Schritte.
        """
        raus: list[dict] = []
        wurzel = Path(self.sequences_dir)
        dateien = sorted(
            (ordner / "sequence.json" for ordner in wurzel.iterdir()
             if ordner.is_dir() and (ordner / "sequence.json").exists()),
            key=lambda pfad: pfad.parent.name,
        ) if wurzel.exists() else []
        for pfad in dateien:
            gespeicherter_name = pfad.parent.name
            try:
                geaendert = pfad.stat().st_mtime
            except OSError:
                geaendert = 0.0
            seq = load_sequence_file(pfad)
            if seq is None:
                raus.append({"name": gespeicherter_name, "datei": str(pfad), "defekt": True,
                             "geaendert": geaendert, "offen": pfad == self.filepath})
                continue
            raus.append({
                "name": seq.name,
                "datei": str(pfad),
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
                "offen": pfad == self.filepath,
                "warnungen": scan_warnungen(sequence_to_board(seq)),
            })
        return raus

    def lauf_status(self, daten: Optional[dict] = None) -> dict:
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

    # Was das Studio dem Hauptprozess sagen darf. Die Gegenstelle ist `BEFEHLE`
    # in handlers.py — ein Test hält beide Listen gegeneinander, denn laufen sie
    # auseinander, tut ein Knopf einfach nichts und niemand merkt es.
    LAUF_BEFEHLE = ("start", "start_manuell", "stop", "pause", "skip", "skip_step", "finish",
                    "manuell", "manuell_aktion", "zeitplan")
    # Alles, was das Studio dem Hauptprozess sagen darf. „zeigen" steuert keinen
    # Lauf, geht aber denselben Weg — der Test haelt DIESE Liste gegen `BEFEHLE`.
    # „nachklick" ist der Werkzeuge-Reiter: die Klick-Runde braucht einen
    # systemweiten Maus-Hook und muss deshalb drueben laufen.
    ALLE_BEFEHLE = LAUF_BEFEHLE + ("zeigen", "config", "daten", "aufnahme",
                                   "aufnahme_stop",
                                   "programm_beenden",
                                   "nachklick", "nachklick_stop", "block_test")

    def aufnahme_starten(self, daten: Optional[dict] = None) -> dict:
        """Startet eine neue Sequenz-Aufnahme im Hauptprozess.

        Das Studio kann den systemweiten Maus- und Tastatur-Hook nicht selbst
        installieren. Wie Start/Pause und die Klick-Runde legt es deshalb einen
        begrenzten Befehl in den gemeinsamen Briefkasten. Alle Angaben gehen mit,
        damit der Abschluss nicht unsichtbar in der Konsole auf Eingaben wartet.
        """
        from ...befehl import sende
        daten = daten or {}
        name = str(daten.get("name") or "").strip()
        if not name:
            return {"ok": False, "meldung": "Bitte zuerst einen Namen eingeben."}
        sicher = sanitize_filename(name)
        ziel = Path(self.sequences_dir) / sicher / "sequence.json"
        if ziel.exists():
            return {"ok": False, "meldung": f"'{sicher}' gibt es bereits."}
        try:
            zyklen = max(0, int(daten.get("zyklen") or 0))
        except (TypeError, ValueError):
            return {"ok": False, "meldung": "Zyklen müssen eine ganze Zahl sein."}
        # Die drei Zeilen der vorigen Aufnahme sollen beim neuen Start nicht
        # noch für einen Augenblick als neue Ereignisse aufblitzen.
        from ...config import RECORD_STATUS_FILE
        try:
            Path(RECORD_STATUS_FILE).unlink(missing_ok=True)
        except OSError:
            pass
        if not sende("aufnahme", name=sicher, zyklen=zyklen,
                     beschreibung=str(daten.get("beschreibung") or "").strip()):
            return {"ok": False, "meldung": "Aufnahme konnte nicht gestartet werden."}
        return {"ok": True, "name": sicher,
                "meldung": "Aufnahme startet — jetzt ins Spiel wechseln."}

    def aufnahme_stoppen(self, daten: Optional[dict] = None) -> dict:
        """Beendet die Aufnahme; der Hauptprozess baut und speichert die Blöcke."""
        from ...befehl import sende
        if not sende("aufnahme_stop"):
            return {"ok": False, "meldung": "Stopp konnte nicht gesendet werden."}
        return {"ok": True, "meldung": "Aufnahme wird beendet und gespeichert."}

    def aufnahme_status(self, daten: Optional[dict] = None) -> dict:
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

    def lauf_befehl(self, daten: dict) -> dict:
        """Start, Pause oder Stopp — als Auftrag an den Hauptprozess.

        Dieses Fenster sieht weder `AutoClickerState` noch `stop_event`; es legt einen
        Befehl ab, den der Hauptprozess in seiner Hotkey-Schleife abholt.

        Vor dem Start wird gespeichert — der Hauptprozess lädt die Datei, und ein
        Start-Knopf, der eine ältere Fassung startet als die angezeigte, wäre
        schlimmer als keiner.
        """
        from ...befehl import sende
        befehl = (daten or {}).get("befehl") or ""
        if befehl not in self.LAUF_BEFEHLE:
            return self._melde(f"Unbekannter Lauf-Befehl '{befehl}'.", "err")

        argumente: dict = {}
        if befehl in ("start", "start_manuell", "zeitplan"):
            if self._dirty:
                zustand = self.speichern()
                if zustand["status"]["art"] == "err":
                    return zustand      # Meldung steht schon drin, Start faellt aus
            if not self.filepath.exists():
                return self._melde("Erst speichern — die Datei gibt es noch nicht.", "warn")
            argumente = {"datei": str(self.filepath), "sequenz": self.board.name}
        if befehl == "zeitplan":
            zeit = str((daten or {}).get("zeit") or "").strip()
            if not zeit:
                return self._melde("Bitte eine Startzeit eingeben.", "warn")
            argumente["zeit"] = zeit
        if befehl == "manuell_aktion":
            aktion = str((daten or {}).get("aktion") or "")
            if aktion not in ("run", "skip", "continue", "stop"):
                return self._melde("Unbekannte manuelle Aktion.", "err")
            argumente["aktion"] = aktion

        if not sende(befehl, **argumente):
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
                "zeitplan": f"Start für '{self.board.name}' geplant."}[befehl]
        return self._melde(text)

    def punkt_zeigen(self, daten: Optional[dict] = None) -> dict:
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
        welche = (daten or {}).get("welche") or "klick"
        quelle = {
            "trigger": lambda: step.wait_condition,
            "verify": lambda: step.verify_condition,
            "else": lambda: step.else_config,
        }.get(welche)
        punkt = self._punkt(quelle().point_id if quelle and quelle() else step.point_id)
        if punkt is None:
            return self._melde("Diese Stelle hat keinen Punkt zum Zeigen.", "warn")

        from ...befehl import sende
        if not sende("zeigen", x=punkt.x, y=punkt.y, punkt=punkt.id,
                     name=punkt.name or "", farbe=list(punkt.color) if punkt.color else None):
            return self._melde("Befehl konnte nicht abgelegt werden.", "err")
        return self._melde(f"Maus zu #{punkt.id} ({punkt.x},{punkt.y}) — im Spiel nachsehen.")

    def block_testen(self, daten: Optional[dict] = None) -> dict:
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
        from ...befehl import sende
        if not sende("block_test", datei=str(self.filepath), phase=lane.kind,
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
        pfad = Path(CONFIG_FILE)
        try:
            roh = json.loads(pfad.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}, ""
        except (OSError, ValueError) as fehler:
            return {}, f"config.json ist nicht lesbar: {fehler}"
        if not isinstance(roh, dict):
            return {}, "config.json enthält kein Objekt."
        return roh, ""

    def config_lesen(self, daten: Optional[dict] = None) -> dict:
        """Werte, Standardwerte, Abschnitte und Beschreibungen in einem Rutsch.

        Der dritte `frage()`-Kanal. Der Pfad steht absolut dabei: `config.json` liegt
        relativ zum Arbeitsverzeichnis, und welche Datei gemeint ist, darf man nicht
        raten müssen.
        """
        from ...config import (
            AppConfig, CONFIG_FILE, config_abschnitte, optionale_felder,
        )
        from ...config_meta import META
        roh, fehler = self._config_datei()
        return {
            "pfad": str(Path(CONFIG_FILE).resolve()),
            "werte": AppConfig.from_dict(roh).to_dict(),
            "standard": AppConfig().to_dict(),
            "abschnitte": [{"titel": t, "keys": list(k)} for t, k in config_abschnitte()],
            "meta": {k: m.as_dict() for k, m in META.items()},
            # Wo ein leeres Eingabefeld `null` heisst und nicht 0.
            "optional": optionale_felder(),
            "fehler": fehler,
        }

    def config_schreiben(self, daten: Optional[dict] = None) -> dict:
        """Schreibt geänderte Werte in `config.json` — und meldet Korrekturen.

        Nur die geänderten Schlüssel, gemischt gegen die Datei wie sie JETZT aussieht:
        der Hauptprozess schreibt dieselbe Datei.

        `__post_init__` hebt ungültige Werte still auf den Standard; im Studio sähe
        das niemand, deshalb wird der geschriebene Stand gegen das Gesendete gehalten
        und die Abweichung zurückgemeldet.
        """
        from ...config import AppConfig, CONFIG, save_config, uebernehmen
        werte = (daten or {}).get("werte")
        if not isinstance(werte, dict) or not werte:
            return {"ok": False, "meldung": "Nichts zu speichern."}

        roh, fehler = self._config_datei()
        if fehler:
            # Kaputt ist nicht leer: draufschreiben würde den einzigen Rest
            # wegwerfen, den man noch von Hand reparieren kann.
            return {"ok": False, "meldung": fehler + " — nicht überschrieben."}

        neu = AppConfig.from_dict({**roh, **werte})
        fertig = neu.to_dict()
        korrekturen = [{"key": k, "gesendet": v, "wurde": fertig.get(k)}
                       for k, v in werte.items()
                       if k in fertig and not _gleicher_wert(v, fertig[k])]
        save_config(neu)
        # **Der Schreiber war der Einzige, der sich selbst nicht neu lud.** Der
        # Hauptprozess bekommt den Briefkasten-Befehl unten und ruft
        # `befehl_config()`; DIESER Prozess hat die Datei geschrieben und blieb
        # danach auf den Werten vom Programmstart sitzen — jeder Reiter, der
        # `CONFIG` liest, zeigte bis zum Neustart den alten Stand. Aufgefallen
        # ist es am Bericht-Reiter („session_log_enabled ist aus", direkt nachdem
        # man es eingeschaltet hatte); betroffen war der ganze Baum: die
        # OCR/LLM-Lampen und Marker-Schwellen im Scans-Reiter, die Toleranz beim
        # Farbvergleich im Werkzeuge-Reiter, der Fenstertitel im Teilen-Reiter.
        #
        # `uebernehmen()` statt einer Zuweisung: das Objekt darf nicht getauscht
        # werden, sonst sitzt jeder mit `from ...config import CONFIG` (imaging,
        # die Scan-Module) weiter auf dem alten. Genau dafuer gibt es die
        # Funktion — ihr Docstring nennt diese Stelle als dritten Aufrufer, nur
        # gerufen hat sie hier nie jemand.
        uebernehmen(CONFIG, neu)
        # Der Hauptprozess hält seinen eigenen Stand im Speicher und merkt von
        # der geschriebenen Datei nichts. Derselbe Briefkasten wie bei Start und
        # Stopp — läuft gerade keiner, verfällt der Befehl (befehl.MAX_ALTER).
        from ...befehl import sende
        sende("config")
        # Was ohne ELSE passiert, steht in derselben Datei — der gemerkte
        # Zeitstempel ist damit veraltet.
        self._cfg_stand = -1.0
        return {"ok": True, "werte": fertig, "korrekturen": korrekturen}

    def befehl_offen(self, daten: Optional[dict] = None) -> bool:
        """Liegt der letzte Befehl noch im Briefkasten?

        Die einzige Rückmeldung über den Hauptprozess: er leert den Kasten beim Lesen.
        Liegt der Befehl später noch da, hört niemand zu. Fragt nur, ändert nichts.
        """
        from ...befehl import BEFEHL_DATEI
        try:
            return BEFEHL_DATEI.exists()
        except OSError:
            return False

    def laden(self, daten: dict) -> dict:
        """Öffnet eine gespeicherte Sequenz. Fragt bei ungespeicherten Änderungen."""
        name = (daten or {}).get("name") or ""
        if not name:
            return self._melde("Keine Sequenz gewählt.", "warn")
        if self._dirty and not (daten or {}).get("verwerfen"):
            self._frage = {"art": "laden", "ziel": name,
                           "titel": "Ungespeicherte Änderungen",
                           "text": f"'{self.board.name}' hat ungespeicherte Änderungen. "
                                   "Vor dem Laden speichern?",
                           "weiter": "Verwerfen", "speichern": True}
            return self.snapshot()
        pfad = next((p for n, p in list_available_sequences() if n == name), None)
        seq = load_sequence_file(pfad) if pfad else None
        if seq is None:
            return self._melde(f"'{name}' konnte nicht geladen werden.", "err")
        self.board = sequence_to_board(seq)
        self.filepath = Path(pfad)
        # Punkte neu einlesen: zwischen zwei Sequenzen kann im Hauptprozess ein
        # Punkt dazugekommen sein.
        from .model import palette_from_sequence
        self.points = palette_from_sequence(seq)
        self._scan_init()
        self._scan_laden()
        self._auswahl_leeren()
        self._dirty = False
        self._stand_merken()
        from ...sequence_studio import merke_zuletzt_verwendet
        merke_zuletzt_verwendet(self.filepath)
        return self._melde(f"Geladen: {name}")

    def neu(self, daten: Optional[dict] = None) -> dict:
        """Legt eine leere Sequenz an (noch ohne Datei auf Platte)."""
        if self._dirty and not (daten or {}).get("verwerfen"):
            self._frage = {"art": "neu", "ziel": "",
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
        self._scan_init()
        self._auswahl_leeren()
        self._dirty = False
        self._stand_merken()
        return self._melde("Neue Sequenz — noch nicht gespeichert.", "warn")

    def sequenz_setzen(self, daten: dict) -> dict:
        """Name, Zyklen oder Beschreibung der Sequenz ändern."""
        feld, wert = (daten or {}).get("feld"), (daten or {}).get("wert")
        if feld == "name":
            self.board.name = str(wert or "")
        elif feld == "zyklen":
            self.board.total_cycles = max(0, int(wert or 0))
        elif feld == "beschreibung":
            self.board.description = str(wert or "")
        else:
            return self._melde(f"Unbekanntes Feld '{feld}'.", "err")
        return self._geaendert()

    def _scan_ohne_namen(self) -> Optional[str]:
        """Erster Scan-Block mit leerem Namen, als lesbare Stelle."""
        offen = scan_warnungen(self.board)
        return offen[0] if offen else None

    def speichern(self, daten: Optional[dict] = None) -> dict:
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

        alt = self.filepath
        neu = (Path(self.sequences_dir) / sanitize_filename(self.board.name)
               / "sequence.json")
        umbenannt = neu != alt

        # Der Ordner ist die Besitzeinheit. Beim Umbenennen wandern deshalb
        # Scans, Vorlagen und Bilder gemeinsam mit der Sequenz.
        alt_ordner = alt.parent
        neu_ordner = neu.parent
        verschoben = False
        if umbenannt and alt.exists():
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

        # Hat der Hauptprozess dieselbe Datei zwischenzeitlich geschrieben?
        # Beide Prozesse teilen sich den Ordner: eine Aufnahme legt Punkte an,
        # `save_data()` schreibt die Sequenz. Ohne diese Frage gewinnt einfach
        # der Zweite, und die Arbeit des Ersten ist weg — ohne ein Wort.
        fremd = self._fremd_geaendert(neu if not umbenannt else None)
        if fremd and not (daten or {}).get("erzwingen"):
            self._frage = {
                "art": "speichern",
                "titel": "Ausserhalb geändert",
                "text": f"{fremd} wurde geändert, seit diese Sequenz geöffnet ist — "
                        "vermutlich vom Hauptprozess. Speichern überschreibt das.",
                "weiter": "Trotzdem speichern",
                "speichern": False,
            }
            return self.snapshot()

        from .model import palette_to_points
        sequence = board_to_sequence(self.board)
        sequence.points = palette_to_points(self.points)
        if not save_sequence_file(sequence, neu):
            if verschoben:
                try:
                    neu_ordner.rename(alt_ordner)
                except OSError:
                    pass
            return self._melde("Speichern fehlgeschlagen!", "err")

        self.filepath = neu
        if verschoben:
            self._scan_init()
            self._scan_laden()
        self._gespeichert = True
        self._dirty = False
        self._stand_merken()
        from ...sequence_studio import merke_zuletzt_verwendet
        merke_zuletzt_verwendet(self.filepath)
        text = f"Gespeichert: {neu.name}"
        if verschoben:
            text = f"Umbenannt → {neu_ordner.name}/ (alle Scans mitgenommen)"

        leer = self._scan_ohne_namen()
        if leer:
            return self._melde(f"{text} — {leer} hat noch keine Konfiguration "
                               f"und wird übersprungen.", "warn")
        return self._melde(text)

    def _fremd_geaendert(self, ziel) -> str:
        """Welche Datei sich seit dem Laden von aussen geändert hat (leer = keine).

        `ziel` ist die Sequenzdatei, die gleich geschrieben wird — beim Umbenennen
        `None`, denn dann entsteht eine neue Datei und es gibt nichts zu
        überschreiben. `sequence.json` wird immer geprüft: die schreibt das Studio
        bei jedem Speichern mit, und der Hauptprozess legt dort während einer
        Aufnahme neue Punkte an.
        """
        if ziel is not None and _mtime(ziel) not in (None, self._stand_datei):
            return Path(ziel).name
        return ""

    def _stand_merken(self) -> None:
        """Nach dem Schreiben (oder Laden) den Stand der Dateien festhalten."""
        self._stand_datei = _mtime(self.filepath)
        self._stand_punkte = self._stand_datei

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
        from ...persistence.sweep import sicherungspfad
        # sicherungspfad() liefert "<name>.json.bak" — hier soll die Datei lesbar
        # heissen und eine echte .json-Endung tragen, damit man sie direkt
        # zurückkopieren kann.
        ziel = sicherungspfad(self.filepath).with_name(
            f"{self.filepath.stem}.ungespeichert.json")
        try:
            ziel.parent.mkdir(parents=True, exist_ok=True)
            if save_sequence_file(board_to_sequence(self.board), ziel):
                return ziel
        except (IOError, OSError):
            return None
        return None
