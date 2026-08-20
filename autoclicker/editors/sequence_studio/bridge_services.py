"""Datei-, Lauf- und Konfigurationsdienste der Studio-Brücke."""

import os
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
    _punkte_pfad,
    scan_warnungen,
)
from .model import (
    BLOCK_COLORS,
    BLOCK_LABELS,
    board_to_sequence,
    load_palette_points,
    save_palette_points,
    sequence_to_board,
)


class BridgeServicesMixin:
    """Kapselt Persistenz, Laufsteuerung und Konfiguration."""

    def sequenz_liste(self, daten: Optional[dict] = None) -> list[dict]:
        """Kennzahlen aller gespeicherten Sequenzen für die Übersicht.

        **Die eine Methode, die keine Momentaufnahme zurückgibt** (mit
        `lauf_status()`). Deshalb ruft die Oberfläche sie über `frage()` statt
        über `ruf()`: `ruf()` ersetzt `S` mit der Antwort, und eine Liste an
        dieser Stelle hiesse Editor-Zustand weg, sobald man die Übersicht
        aufmacht. Wer hier etwas ergänzt, prüft zuerst, welcher der beiden
        Kanäle gemeint ist.

        Bewusst über `load_sequence_file()` und nicht über einen eigenen
        JSON-Leser: so laufen Migration und Punkt-Auflösung mit, und die Zahlen
        hier sind dieselben, die der Editor beim Öffnen zeigt.

        Nur Kennzahlen, keine Schritte — die Liste soll auch bei 40 Sequenzen
        sofort stehen, und gelesen wird sie bei jedem Öffnen des Reiters neu
        (im Hauptprozess kann zwischendurch eine dazugekommen sein).

        **Der Ordner wird selbst durchgesehen, nicht `list_available_sequences()`
        gefragt.** Die überspringt unlesbare Dateien stillschweigend — richtig für
        ein Menü (laden liesse sie sich ohnehin nicht), falsch für eine Übersicht:
        genau dann sucht man die Datei im Explorer, weil sie nirgends auftaucht.
        Hier steht sie mit dem Vermerk, dass sie kaputt ist.
        """
        raus: list[dict] = []
        ordner = Path(self.sequences_dir)
        try:
            dateien = sorted(p for p in ordner.glob("*.json") if p.name != "points.json")
        except OSError:
            return []
        for pfad in dateien:
            try:
                geaendert = pfad.stat().st_mtime
            except OSError:
                geaendert = 0.0
            seq = load_sequence_file(pfad)
            if seq is None:
                raus.append({"name": pfad.stem, "datei": pfad.name, "defekt": True,
                             "geaendert": geaendert, "offen": pfad == self.filepath})
                continue
            raus.append({
                "name": seq.name,
                "datei": pfad.name,
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

        Der zweite Kanal neben `sequenz_liste()`: keine Momentaufnahme, deshalb
        über `frage()` abzuholen. Und **nie ein Fehler** — dass nichts läuft ist
        der Normalfall, nicht der Ausnahmefall.

        Der Hauptprozess und dieses Fenster teilen keinen Speicher; die Datei
        ist der gemeinsame Nenner, so wie überall sonst zwischen den beiden.
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
            return zustand if zustand.get("ende") else {"aktiv": False}
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
    LAUF_BEFEHLE = ("start", "stop", "pause")
    # Alles, was das Studio dem Hauptprozess sagen darf. „zeigen" steuert keinen
    # Lauf, geht aber denselben Weg — der Test haelt DIESE Liste gegen `BEFEHLE`.
    ALLE_BEFEHLE = LAUF_BEFEHLE + ("zeigen", "config", "daten")

    def lauf_befehl(self, daten: dict) -> dict:
        """Start, Pause oder Stopp — als Auftrag an den Hauptprozess.

        Dieses Fenster kann die Sequenz nicht selbst ausführen: es ist ein eigener
        Prozess und sieht weder `AutoClickerState` noch `stop_event`. Es legt
        deshalb einen Befehl ab (`befehl.py`), den der Hauptprozess in derselben
        Schleife abholt, in der auch seine Hotkeys ankommen — ein Studio-Knopf ist
        damit genau so viel wert wie ein Tastendruck, nicht mehr und nicht weniger.

        **Vor dem Start wird gespeichert.** Der Hauptprozess lädt die Datei; was
        nur hier im Speicher steht, liefe nicht mit. Ein Start-Knopf, der eine
        ältere Fassung startet als die angezeigte, wäre schlimmer als keiner.
        """
        from ...befehl import sende
        befehl = (daten or {}).get("befehl") or ""
        if befehl not in self.LAUF_BEFEHLE:
            return self._melde(f"Unbekannter Lauf-Befehl '{befehl}'.", "err")

        argumente: dict = {}
        if befehl == "start":
            if self._dirty:
                zustand = self.speichern()
                if zustand["status"]["art"] == "err":
                    return zustand      # Meldung steht schon drin, Start faellt aus
            if not self.filepath.exists():
                return self._melde("Erst speichern — die Datei gibt es noch nicht.", "warn")
            argumente = {"datei": str(self.filepath), "sequenz": self.board.name}

        if not sende(befehl, **argumente):
            return self._melde("Befehl konnte nicht abgelegt werden.", "err")
        text = {"start": f"'{self.board.name}' gestartet.",
                "stop": "Stopp geschickt.",
                "pause": "Pause umgeschaltet."}[befehl]
        return self._melde(text)

    def punkt_zeigen(self, daten: Optional[dict] = None) -> dict:
        """Setzt die Maus im Hauptprozess auf die Stelle des gewählten Blocks.

        Der kürzeste Weg zu der Frage, die man beim Bauen einer Sequenz am
        häufigsten hat: **sitzt der Punkt da, wo ich denke?** Ein Blick auf
        „(4402,561)" beantwortet sie nicht, ein Mauszeiger im Spiel schon.

        Messen kann nur der Hauptprozess (dieses Fenster sieht den Bildschirm
        nicht), deshalb steht die Auswertung — gespeicherte gegen aktuelle Farbe —
        in dessen Konsole. Hier bleibt die Rückmeldung, dass der Auftrag raus ist.
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

    # ------------------------------------------------------------ Einstellungen

    def _config_datei(self) -> tuple:
        """`config.json` als reine Werte — und was beim Lesen schiefging.

        Bewusst nicht `load_config()`: die **schreibt** die Datei, sobald ein
        Feld fehlt, und gibt bei jedem Aufruf eine Zeile in der Konsole des
        Hauptprozesses aus. Ein Leser tut weder das eine noch das andere.

        Drei Ergebnisse, und der Unterschied zwischen den letzten beiden ist der
        wichtige: `({}, "")` heisst „gibt es noch nicht" (dann legt das
        Speichern sie an), `({}, "…")` heisst „da liegt etwas, das ich nicht
        verstehe" — und darauf wird nicht geschrieben.
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

        Der dritte `frage()`-Kanal: keine Momentaufnahme, sondern ein eigener
        Gegenstand — über `ruf()` geholt zerschösse die Antwort den
        Editor-Zustand.

        Der Pfad steht absolut dabei, weil `config.json` relativ zum
        Arbeitsverzeichnis liegt: wer die App aus einem anderen Ordner startet,
        bearbeitet eine andere Datei, und das darf man nicht raten müssen.
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

        **Nur die geänderten Schlüssel**, nicht die ganze Config: der
        Hauptprozess schreibt dieselbe Datei (Debug-Stufen, Factory Reset,
        Import), und ein Fenster, das seit einer Stunde offensteht, soll dessen
        Änderungen nicht mit seinem alten Stand überbügeln. Gemischt wird
        deshalb gegen die Datei, wie sie **jetzt** aussieht.

        `AppConfig.__post_init__` korrigiert ungültige Werte still (Konfidenz
        über 1, max unter min, unbekannte Aktion). Im Hauptprozess sieht man das
        an einer Konsolenzeile — hier sähe sie niemand, deshalb wird der
        korrigierte Stand gegen das Gesendete gehalten und die Abweichung
        zurückgemeldet. Die Datei enthält dann etwas anderes als eingegeben, und
        das darf nicht stillschweigend passieren.
        """
        from ...config import AppConfig, save_config
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

        Die einzige Rückmeldung, die dieses Fenster über den Hauptprozess bekommt:
        er leert den Kasten beim Lesen. Liegt der Befehl Sekunden später immer
        noch da, hört niemand zu — das Programm ist zu, oder es hängt. Ohne diese
        Frage meldete der Knopf „gestartet" und es passierte nichts, was von
        aussen wie ein kaputter Knopf aussieht.

        Fragt nur, ändert nichts: gehört zu `frage()`, nicht zu `ruf()`.
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
        self.points = load_palette_points(self.sequences_dir)
        self._auswahl_leeren()
        self._dirty = False
        self._stand_merken()
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
            name=basis, loop_phases=[LoopPhase(name="Loop", repeat=1, steps=[])]))
        self.filepath = Path(self.sequences_dir) / f"{sanitize_filename(basis)}.json"
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

        **Ein Scan ohne Konfiguration hält das Speichern nicht auf.** Das tat es
        einmal, und die Begründung war richtig, aber an der falschen Stelle: ein
        leerer Scan-Name fiel im Executor durch den Truthiness-Dispatch bis zum
        Klick durch und wurde zu einem Klick auf (0, 0). Nur hat das den Editor
        nichts anzugehen — wer einen Block anlegt, um seine Stelle im Ablauf
        festzuhalten, und die Konfiguration erst danach baut (die entsteht in
        einem anderen Prozess, mit CTRL+ALT+N), soll das speichern koennen.
        Repariert ist es jetzt dort, wo es kaputt war: `execute_step` ueberspringt
        so einen Block mit Ansage.

        Gemeldet wird er trotzdem — still soll er nicht bleiben.
        """
        if not (self.board.name or "").strip():
            # Der Name ist etwas anderes: er IST der Dateiname. Ohne ihn gibt es
            # kein Ziel, das Speichern ist nicht unvollstaendig, sondern unmoeglich.
            return self._melde("Nicht gespeichert: Sequenz-Name fehlt.", "err")

        alt = self.filepath
        neu = Path(self.sequences_dir) / f"{sanitize_filename(self.board.name)}.json"
        umbenannt = neu != alt

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

        # Punkte ZUERST: die Sequenz verweist nur noch auf sie. Schlägt das fehl,
        # zeigten frisch angelegte Referenzen ins Leere — dann lieber gar nicht
        # speichern, als eine Sequenz mit toten Verweisen zu hinterlassen.
        if not save_palette_points(self.sequences_dir, self.points):
            return self._melde("points.json nicht schreibbar — nichts gespeichert.", "err")
        if not save_sequence_file(board_to_sequence(self.board), neu):
            return self._melde("Speichern fehlgeschlagen!", "err")

        self.filepath = neu
        self._gespeichert = True
        self._dirty = False
        self._stand_merken()
        text = f"Gespeichert: {neu.name}"
        if umbenannt and alt.exists():
            try:
                os.remove(alt)
                text = f"Umbenannt → {neu.name} (alte Datei entfernt)"
            except OSError:
                text = f"Gespeichert: {neu.name} (alte Datei {alt.name} blieb)"

        leer = self._scan_ohne_namen()
        if leer:
            return self._melde(f"{text} — {leer} hat noch keine Konfiguration "
                               f"und wird übersprungen.", "warn")
        return self._melde(text)

    def _fremd_geaendert(self, ziel) -> str:
        """Welche Datei sich seit dem Laden von aussen geändert hat (leer = keine).

        `ziel` ist die Sequenzdatei, die gleich geschrieben wird — beim Umbenennen
        `None`, denn dann entsteht eine neue Datei und es gibt nichts zu
        überschreiben. `points.json` wird immer geprüft: die schreibt das Studio
        bei jedem Speichern mit, und der Hauptprozess legt dort während einer
        Aufnahme neue Punkte an.
        """
        if ziel is not None and _mtime(ziel) not in (None, self._stand_datei):
            return Path(ziel).name
        punkte = _punkte_pfad(self.sequences_dir)
        if _mtime(punkte) not in (None, self._stand_punkte):
            return "points.json"
        return ""

    def _stand_merken(self) -> None:
        """Nach dem Schreiben (oder Laden) den Stand der Dateien festhalten."""
        self._stand_datei = _mtime(self.filepath)
        self._stand_punkte = _mtime(_punkte_pfad(self.sequences_dir))

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
