"""Öffnen, Pflegen und Speichern von Item-Scan-Konfigurationen."""

from pathlib import Path
from typing import Optional

from ...models import ItemScanConfig
from ...persistence.paths import ITEMS_FILE, SLOTS_FILE
from ...utils import eindeutiger_name, sanitize_filename
from .scan_contract import ART_ITEM, ART_SCAN, ART_SLOT
from .scan_model import save_items, save_slots


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
        """Eine neue Item-Scan-Konfiguration — leer, aber mit eindeutigem Namen."""
        name = eindeutiger_name(str((daten or {}).get("name") or "Neuer Scan"), self.scans)
        self._merke("Scan angelegt")
        self.scans[name] = ItemScanConfig(name=name)
        self.scan_art, self.scan_name = ART_SCAN, name
        # Ein frisch angelegter Scan ist der, an dem man arbeitet — sonst müsste
        # man ihn direkt danach noch einmal auswählen.
        self.scan_offen = name
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
            # Die alte Datei bleibt liegen: umbenennen hiesse hier löschen, und
            # eine Sequenz, die noch auf den alten Namen zeigt, verlöre ihren
            # Scan. Wer aufräumen will, löscht die Datei bewusst.
            alt = cfg.name
            self.scans = {(neu if k == alt else k): v for k, v in self.scans.items()}
            cfg.name = neu
            self.scan_name = neu
            if self.scan_offen == alt:
                self.scan_offen = neu
            # Das Erinnerungsbild gehört zum Scan, nicht zum Dateinamen.
            try:
                self._foto_pfad(alt).replace(self._foto_pfad(neu))
            except OSError:
                pass
            return self._scan_geaendert(
                f"'{alt}' heisst jetzt '{neu}' — die alte Datei bleibt liegen.", "warn")
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

    def scan_mitglied(self, daten: dict) -> dict:
        """Einen Slot oder ein Item zum offenen Scan dazu oder weg.

        Umschalten statt zweier Befehle: die Ansicht zeigt Häkchen, und ein
        Häkchen kennt nur einen Klick.
        """
        cfg = self.scans.get(str((daten or {}).get("scan") or self.scan_offen))
        if cfg is None:
            return self._scan_melde("Kein Scan gewählt.", "warn")
        art = str((daten or {}).get("art") or "")
        if art not in (ART_SLOT, ART_ITEM):
            return self._scan_melde(f"Unbekannte Art '{art}'.", "err")
        name = str((daten or {}).get("name") or "")
        bestand = self.slots if art == ART_SLOT else self.items
        if name not in bestand:
            return self._scan_melde(
                f"{'Slot' if art == ART_SLOT else 'Item'} '{name}' gibt es nicht.",
                "err")
        self._merke(f"'{name}' im Scan '{cfg.name}'")
        liste = cfg.slot_names if art == ART_SLOT else cfg.item_names
        if name in liste:
            liste.remove(name)
        else:
            liste.append(name)
        self._objekte_angleichen()
        self._treffer_mitgliedschaft()
        return self._scan_geaendert()

    def _treffer_mitgliedschaft(self) -> None:
        """Zieht das `fremd`-Merkmal der Treffer an der Mitgliedschaft nach.

        Ein Häkchen ändert nicht, WAS erkannt wurde — nur, ob der Scan es
        ansieht. Dafür noch einmal zu rechnen wäre Verschwendung; es stehen zu
        lassen wäre eine Anzeige, die nach dem eigenen Klick noch das Alte
        behauptet.
        """
        cfg = self.scans.get(self.scan_offen)
        dabei = set(cfg.item_names) if cfg else set()
        for eintrag in self._treffer.values():
            if eintrag.get("name"):
                eintrag["fremd"] = cfg is not None and eintrag["name"] not in dabei

    def scan_alle(self, daten: dict) -> dict:
        """Nimmt alle Slots bzw. alle Items in den offenen Scan — oder raus.

        Der Weg dorthin waren 56 Häkchen. Ein Scan umfasst fast immer *alles*,
        was zu seinem Spiel gehört; die Ausnahme klickt man danach einzeln weg.
        """
        # Wie `scan_mitglied`: der Inspektor arbeitet am GEWÄHLTEN Scan, der nicht
        # derselbe sein muss wie der offene. Ohne den Parameter träfe „alle" den
        # falschen.
        cfg = self.scans.get(str((daten or {}).get("scan") or self.scan_offen))
        if cfg is None:
            return self._scan_melde("Kein Scan gewählt.", "warn")
        art = str((daten or {}).get("art") or "")
        if art not in (ART_SLOT, ART_ITEM):
            return self._scan_melde(f"Unbekannte Art '{art}'.", "err")
        dazu = bool((daten or {}).get("wert"))
        self._merke(f"alle {'Slots' if art == ART_SLOT else 'Items'} "
                    f"{'dazu' if dazu else 'raus'}")
        bestand = self.slots if art == ART_SLOT else self.items
        vorher = len(cfg.slot_names if art == ART_SLOT else cfg.item_names)
        namen = list(bestand) if dazu else []
        if art == ART_SLOT:
            cfg.slot_names = namen
        else:
            cfg.item_names = namen
        self._objekte_angleichen()
        self._treffer_mitgliedschaft()
        wort = "Slot" if art == ART_SLOT else "Item"
        return self._scan_geaendert(
            f"{len(namen)} {wort}(s) im Scan '{cfg.name}' (vorher {vorher}).")

    def scan_loeschen(self, daten: Optional[dict] = None) -> dict:
        """Löscht die offene Scan-Konfiguration samt Datei."""
        name = self.scan_name if self.scan_art == ART_SCAN else ""
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
        from ...persistence.paths import ITEM_SCANS_DIR
        pfad = Path(ITEM_SCANS_DIR) / f"{sanitize_filename(name)}.json"
        try:
            pfad.unlink(missing_ok=True)
        except OSError:
            return self._scan_melde(f"'{name}' entfernt, die Datei blieb liegen.", "warn")
        return self._scan_melde(f"Scan '{name}' gelöscht.", "warn")

    # --------------------------------------------------------------- Sichern

    def scan_speichern(self, daten: Optional[dict] = None) -> dict:
        """Schreibt Slots, Items und alle Scan-Konfigurationen.

        Ein Knopf für drei Dateiarten, weil sie zusammen entstehen: wer einen
        Slot anlegt, lernt daraus ein Item und hängt beides in einen Scan.
        Getrennte Knöpfe hiessen, sich diese Reihenfolge merken zu müssen.

        Danach erfährt der Hauptprozess davon (Briefkasten-Befehl `daten`) —
        sonst arbeitete er bis zum nächsten `CTRL+ALT+L` mit dem alten Stand.
        """
        from ...persistence import save_item_scan
        fehler = []
        if not save_slots(self.slots, SLOTS_FILE):
            fehler.append("slots.json")
        if not save_items(self.items, ITEMS_FILE):
            fehler.append("items.json")
        for cfg in self.scans.values():
            try:
                save_item_scan(cfg)
            except OSError:
                fehler.append(f"{cfg.name}.json")
        if fehler:
            return self._scan_melde("Nicht geschrieben: " + ", ".join(fehler), "err")

        self._scan_dirty = False
        # Der eigene Schreibvorgang darf sich nicht selbst als Fremdaenderung
        # melden - sonst stuende der Hinweis nach jedem Speichern da.
        self._platte = self._platte_stand()
        from ...befehl import sende
        sende("daten")
        return self._scan_melde(
            f"{len(self.slots)} Slot(s), {len(self.items)} Item(s), "
            f"{len(self.scans)} Scan(s) gespeichert.")
