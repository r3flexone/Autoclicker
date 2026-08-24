"""Öffnen, Pflegen und Speichern von Item-Scan-Konfigurationen."""

from typing import Optional

from ...models import ItemScanConfig
from ...utils import eindeutiger_name, sanitize_filename
from .scan_contract import ART_ITEM, ART_SCAN, ART_SLOT


class ScanLibraryMixin:
    """Verwaltet die Scan-Bibliothek und ihre Beziehungen zu Slots und Items."""

    def scan_oeffnen(self, daten: Optional[dict] = None) -> dict:
        """Wählt den Item-Scan, in dessen Zusammenhang gearbeitet wird.

        Der Scan ist hier das Übergeordnete: mit mehreren Spielen liegen sonst
        alle Slots und Items aller Spiele in einer Liste, und keine davon gehört
        sichtbar irgendwohin. Ist einer offen, zeigen die Listen standardmässig
        nur seine Mitglieder, und sein Bild kommt gleich mit.

        Ein leerer Name macht ihn wieder zu — dann sieht man den ganzen Bestand.
        """
        name = str((daten or {}).get("name") or "")
        self._scan_laden()
        if name and name not in self.scans:
            return self._scan_melde(f"Scan '{name}' gibt es nicht.", "err")
        self.scan_offen = name
        self._scan_arbeitsbestand(name)
        self._treffer = {}
        if name:
            self.scan_art, self.scan_name = ART_SCAN, name
            if not self._foto_laden(name):
                # Ein älterer Scan bringt Slots mit, aber kein gemerktes Bild.
                # Dass seine Slots trotzdem dastehen, ist die halbe Antwort auf
                # „warum ist die Mitte leer" — die andere Hälfte ist der Knopf.
                quelle = self.scans[name].capture_window_title
                quelltext = (f" Fenster '{quelle}' ist momentan nicht offen."
                             if quelle and not self.scan_fenster_id else "")
                if self._flaeche():
                    return self._scan_melde(
                        f"'{name}' geöffnet — kein Bild gemerkt, die Slots stehen "
                        "trotzdem. „Screenshot aufnehmen“ legt das Spiel dahinter."
                        + quelltext,
                        "info")
                return self._scan_melde(
                    f"'{name}' geöffnet — noch kein Bild dazu. Screenshot aufnehmen."
                    + quelltext,
                    "info")
            quelle = self.scans[name].capture_window_title
            if quelle and not self.scan_fenster_id:
                return self._scan_melde(
                    f"'{name}' geöffnet, Bild von zuletzt. Fenster '{quelle}' ist "
                    "momentan nicht offen.", "warn")
            return self._scan_melde(f"'{name}' geöffnet, Bild von zuletzt.")
        self._foto = None
        self._foto_bild = ""
        self._foto_info = None
        self.scan_bereich = None
        self.scan_fenster_id = 0
        return self._scan_melde("Kein Scan offen — der ganze Bestand steht da.", "info")

    def scan_filter(self, daten: Optional[dict] = None) -> dict:
        """Nur die Mitglieder des offenen Scans zeigen — oder alles.

        „Alles" braucht man zum Hinzufügen, „nur Mitglieder" zum Arbeiten. Ein
        Schalter statt zweier Listen, weil es dieselben Dinge sind.
        """
        self.nur_dabei = bool((daten or {}).get("wert"))
        return self.scan_daten()

    def scan_neu(self, daten: Optional[dict] = None) -> dict:
        """Eine neue Item-Scan-Konfiguration — leer, aber mit eindeutigem Namen.

        **Erst laden, dann anlegen.** `_scan_laden()` ersetzt `self.scans`
        komplett durch das, was auf Platte steht — passiert es NACH dem Anlegen,
        ist der frische Scan wieder weg. In der Oberfläche fällt das nicht auf
        (der Reiter zeichnet beim Öffnen und lädt dabei), über die Brücke
        aufgerufen aber sehr wohl.
        """
        self._scan_laden()
        name = eindeutiger_name(str((daten or {}).get("name") or "Neuer Scan"), self.scans)
        self._merke("Scan angelegt")
        self.scans[name] = ItemScanConfig(name=name)
        self.scans[name].owner_sequence = self.board.name
        self.scan_art, self.scan_name = ART_SCAN, name
        # Ein frisch angelegter Scan ist der, an dem man arbeitet — sonst müsste
        # man ihn direkt danach noch einmal auswählen.
        self.scan_offen = name
        self._scan_arbeitsbestand(name)
        # Eine Aufnahme ohne Scan hatte früher kein Speicherziel. Falls aus
        # einer bereits offenen Sitzung noch so ein verwaistes Bild da ist,
        # darf ein anschliessend angelegter Scan es nicht still übernehmen.
        self._foto = None
        self._foto_bild = ""
        self._foto_info = None
        self.scan_bereich = None
        self.scan_fenster_id = 0
        return self._scan_geaendert(f"Scan '{name}' angelegt und geöffnet.")

    def scan_setzen(self, daten: dict) -> dict:
        """Ein Feld einer Scan-Konfiguration."""
        name = str((daten or {}).get("name") or "")
        feld = str((daten or {}).get("feld") or "")
        wert = (daten or {}).get("wert")
        cfg = self.scans.get(name)
        if cfg is None:
            return self._scan_melde(f"Scan '{name}' gibt es nicht.", "err")

        if feld == "name":
            neu = sanitize_filename(str(wert or "").strip())
            if not neu or neu == cfg.name:
                return self.scan_daten()
            if neu in self.scans:
                return self._scan_melde(f"'{neu}' gibt es schon.", "warn")
            self._merke(f"Scan '{cfg.name}' umbenannt")
            alt = cfg.name
            self.scans = {(neu if k == alt else k): v for k, v in self.scans.items()}
            cfg.name = neu
            self.scan_name = neu
            if self.scan_offen == alt:
                self.scan_offen = neu
            for lane in self.board.lanes:
                for step in lane.steps:
                    if step.item_scan == alt:
                        step.item_scan = neu
            # Das Erinnerungsbild gehört zum Scan, nicht zum Dateinamen.
            try:
                self._foto_pfad(alt).replace(self._foto_pfad(neu))
            except OSError:
                pass
            alt_pfad = self.filepath.parent / "item_scans" / f"{sanitize_filename(alt)}.json"
            try:
                alt_pfad.unlink(missing_ok=True)
            except OSError:
                return self._scan_melde(
                    f"'{alt}' wurde umbenannt, die alte Datei blieb liegen.", "warn")
            return self._scan_geaendert(
                f"'{alt}' heisst jetzt '{neu}'.")
        if feld == "toleranz":
            try:
                toleranz = int(wert)
            except (TypeError, ValueError):
                return self._scan_melde(
                    "Die Farb-Toleranz muss eine ganze Zahl sein.", "err")
            self._merke(f"'{name}': Farb-Toleranz")
            cfg.color_tolerance = max(0, toleranz)
            return self._scan_geaendert()
        if feld == "lernen":
            self._merke(f"'{name}': Unbekanntes lernen")
            cfg.learn_unknown = bool(wert)
            return self._scan_geaendert()
        if feld == "reverse":
            self._merke(f"'{name}': Laufrichtung")
            cfg.reverse = bool(wert)
            return self._scan_geaendert(
                f"'{cfg.name}': Slots laufen "
                f"{'rückwärts' if cfg.reverse else 'vorwärts'}")
        return self._scan_melde(f"Unbekanntes Feld '{feld}'.", "err")

    def scan_alle_loeschen(self, daten: dict) -> dict:
        """Löscht alle Slots bzw. alle Items dieses Scans auf einen Schlag.

        Einzeln durchzuklicken war bei fünfzig Stück der Grund, warum man diesen
        Knopf sucht.

        Der Bezug ist derselbe wie überall: der offene Scan, sonst der ganze
        Bestand (`_scan_slots()` / `_kandidaten()`) — dieselbe Regel wie bei
        „N Items prüfen & lernen".

        Kein Bestätigungsdialog, aus demselben Grund wie beim einzelnen
        Löschen: STRG+Z holt den ganzen Stand zurück, auch diesen.
        """
        art = str((daten or {}).get("art") or "")
        if art == ART_SLOT:
            namen = [s.name for s in self._scan_slots()]
            if not namen:
                return self._scan_melde("Keine Slots zum Löschen.", "warn")
            self._auswahl = namen
            return self.scan_slot_loeschen()
        if art == ART_ITEM:
            namen = [i.name for i in self._kandidaten()]
            if not namen:
                return self._scan_melde("Keine Items zum Löschen.", "warn")
            self._merke(f"{len(namen)} Item(s) gelöscht" if len(namen) > 1
                        else f"'{namen[0]}' gelöscht")
            for name in namen:
                del self.items[name]
            self._objekte_angleichen()
            self.scan_name = ""
            was = f"'{namen[0]}'" if len(namen) == 1 else f"{len(namen)} Items"
            return self._scan_geaendert(f"{was} gelöscht.", "warn")
        return self._scan_melde(f"Unbekannte Art '{art}'.", "err")

    def scan_loeschen(self, daten: Optional[dict] = None) -> dict:
        """Löscht die offene Scan-Konfiguration samt Datei."""
        # Die Scan-Maske kennt ihren Namen selbst und schickt ihn mit. Der
        # globale Auswahlzustand kann inzwischen schon wieder auf einem Slot
        # oder Item stehen; davon darf der Löschknopf seiner sichtbaren Maske
        # nicht abhängen. Ohne Namen bleibt der offene Scan der sinnvolle
        # Rückfall für ältere Aufrufer.
        name = str((daten or {}).get("name") or self.scan_offen)
        if name not in self.scans:
            return self._scan_melde("Kein Scan gewählt.", "warn")
        # STRG+Z holt die Konfiguration zurück, nicht die Dateien: die JSON
        # schreibt das nächste Speichern neu, der gemerkte Screenshot ist weg.
        self._merke(f"Scan '{name}' gelöscht (Bild bleibt weg)")
        del self.scans[name]
        self.scan_name = ""
        if self.scan_offen == name:
            self.scan_offen = ""
        try:
            self._foto_pfad(name).unlink(missing_ok=True)
        except OSError:
            pass
        pfad = self.filepath.parent / "item_scans" / f"{sanitize_filename(name)}.json"
        try:
            pfad.unlink(missing_ok=True)
        except OSError:
            return self._scan_melde(f"'{name}' entfernt, die Datei blieb liegen.", "warn")
        # Auch Löschen ist ein eigener Schreibvorgang: es dreht die
        # Änderungszeit des Ordners weiter.
        self._platte_nachziehen(self.filepath.parent / "item_scans")
        return self._scan_melde(f"Scan '{name}' gelöscht.", "warn")

    # --------------------------------------------------------------- Sichern

    def scan_speichern(self, daten: Optional[dict] = None) -> dict:
        """Schreibt Slots, Items und alle Scan-Konfigurationen.

        Ein Knopf für alle Dateiarten des Reiters, weil sie zusammen entstehen:
        wer einen Slot anlegt, lernt daraus ein Item und hängt beides in einen
        Scan; wer eine Boss-Region aufzieht, nimmt gleich die Vorlage auf.
        Getrennte Knöpfe hiessen, sich diese Reihenfolge merken zu müssen.

        **Die Punkte gehen mit.** Ein Klickpunkt einer Boss- oder Icon-Aktion
        ist ein Punkt in `sequence.json` — die Koordinate steht dort und sonst
        nirgends. Bliebe er ungeschrieben, zeigte die gespeicherte Aktion beim
        nächsten Start ins Leere.

        Danach erfährt der Hauptprozess davon (Briefkasten-Befehl `daten`) —
        sonst arbeitete er bis zum nächsten `CTRL+ALT+L` mit dem alten Stand.
        """
        from ...persistence import save_item_scan

        # Scan-Aktionen können neue Sequenzpunkte anlegen, ohne einen Ablaufblock
        # zu verändern. Darum muss derselbe Knopf zuerst auch `sequence.json`
        # schreiben. Beim Umbenennen lädt `speichern()` den verschobenen Ordner
        # neu; die noch ungespeicherten Scan-Objekte halten wir über diesen
        # kurzen Schritt fest und schreiben sie danach in den neuen Ordner.
        arbeitsbestand = (
            self.slots, self.items, self.scans, self.boss_scans,
            self.icon_scans, self.global_bosses, self.scan_offen,
        )
        sequenz_antwort = self.speichern(daten)
        if sequenz_antwort.get("frage"):
            return self._scan_melde(
                "Sequenz wurde ausserhalb geändert — zuerst im Sequenz-Reiter entscheiden.",
                "warn")
        sequenz_status = sequenz_antwort.get("status") or {}
        if sequenz_status.get("art") == "err":
            return self._scan_melde(
                sequenz_status.get("text") or "Sequenz konnte nicht gespeichert werden.",
                "err")
        (self.slots, self.items, self.scans, self.boss_scans,
         self.icon_scans, self.global_bosses, self.scan_offen) = arbeitsbestand

        fehler = []
        self._objekte_angleichen()
        for cfg in self.scans.values():
            try:
                cfg.owner_sequence = self.board.name
                save_item_scan(cfg)
            except (OSError, ValueError):
                fehler.append(f"{cfg.name}.json")
        fehler += self._erkennung_speichern()
        if fehler:
            return self._scan_melde("Nicht geschrieben: " + ", ".join(fehler), "err")

        self._scan_dirty = False
        # Der eigene Schreibvorgang darf sich nicht selbst als Fremdaenderung
        # melden - sonst stuende der Hinweis nach jedem Speichern da.
        self._platte_nachziehen()
        from ...befehl import sende
        sende("daten")
        return self._scan_melde(
            f"{len(self.slots)} Slot(s), {len(self.items)} Item(s), "
            f"{len(self.scans)} Item-Scan(s), {len(self.boss_scans)} Boss-Scan(s), "
            f"{len(self.icon_scans)} Icon-Scan(s) gespeichert.")
