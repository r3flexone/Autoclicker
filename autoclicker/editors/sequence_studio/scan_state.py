"""Zustand, Darstellung und Undo-Verlauf des Scan-Editors."""

import base64
import copy
import re as _re
from typing import Optional

from ...models import ItemProfile, ItemScanConfig, ItemSlot
from .model import hexfarbe
from .scan_contract import (
    ARTEN,
    ART_SCAN,
    ART_SLOT,
    MIN_SLOT,
    MODUS_FINDEN,
    MODUS_WAHL,
    UNDO_TIEFE,
)
from .scan_model import existing_categories


def _natuerlich(name: str) -> list:
    """Sortierschlüssel, der Zahlen als Zahlen liest: "Slot 2" vor "Slot 10"."""
    return [int(teil) if teil.isdigit() else teil.casefold()
            for teil in _re.split(r"(\d+)", name or "")]


class ScanStateMixin:
    """Verwaltet Scan-Zustand und erzeugt JSON-fähige Momentaufnahmen."""

    def _scan_init(self) -> None:
        """Wird aus `StudioBridge.__init__` gerufen."""
        self.slots: dict = {}
        self.items: dict = {}
        self.scans: dict = {}
        self._scan_stand: dict = {}            # Scan-Name -> mtime seiner Datei
        self._scan_geladen = False
        self._foto = None                      # PIL-Bild in Originalgrösse
        self._foto_bild: str = ""              # data:-URL, verkleinert
        self._foto_info: Optional[dict] = None
        self._ecke: Optional[tuple] = None     # erste Ecke beim Aufziehen
        # Worin die Slot-Erkennung sucht. Nur für den einen Durchgang, deshalb
        # nicht neben `scan_bereich`: der schränkt das BILD ein und gilt für
        # jede weitere Aufnahme, dieser hier schränkt eine SUCHE ein und ist
        # danach wieder weg.
        self._suchbereich: Optional[tuple] = None
        # Welcher Teil des Bildschirms aufgenommen wird. None = alles. Nicht in
        # der Scan-Datei, sondern IM gemerkten Bild: dessen Ursprung und Grösse
        # SIND der Bereich, und zwei Stellen für dieselbe Angabe liefen
        # auseinander.
        self.scan_bereich: Optional[tuple] = None
        # Das gewaehlte Fenster. Damit wird es DIREKT abgebildet, also auch
        # dann, wenn etwas davor liegt — allen voran dieses Studio. Nur fuer
        # die Sitzung: ein Fenster-Handle ueberlebt keinen Neustart, und ein
        # gespeichertes zeigte beim naechsten Mal irgendwohin.
        self.scan_fenster_id: int = 0
        self.scan_modus: str = MODUS_WAHL
        # Werkzeuge sind standardmaessig einmalig. Fuer Serien kann die Ansicht
        # sie anheften; dann bleibt der Modus nach einer erfolgreichen Aktion an.
        self.scan_werkzeug_fixiert: bool = False
        self.scan_art: str = ART_SLOT
        self.scan_name: str = ""
        # Die Slot-Auswahl. `scan_name` bleibt der EINE, an dem der Inspektor
        # arbeitet (Farbe messen, Klickpunkt, lernen); `_auswahl` ist die Menge,
        # auf der Sammel-Aktionen laufen. Dieselbe Trennung wie im
        # Sequenz-Editor, wo `sel_rows` neben dem angezeigten Block steht.
        self._auswahl: list = []
        # Der offene Item-Scan ist der ZUSAMMENHANG, nicht die Auswahl: wer
        # einen Slot anklickt, um ihn zu bearbeiten, arbeitet weiter an
        # demselben Scan. Vorher hing beides an `scan_art`/`scan_name`, und ein
        # Klick auf einen Slot verlor den Zusammenhang.
        self.scan_offen: str = ""
        # Welche der drei Ansichten den gemeinsamen Aufnahmebereich gerade
        # benutzt. Die Weboberfläche schickt die Art bei jedem Handgriff mit;
        # der Wert ist der Rückhalt für den anschliessenden Klick ins Bild.
        self.scan_aufnahme_art: str = "item"
        # Zeigen die Listen nur, was zum offenen Scan gehört? Mit mehreren
        # Spielen liegen sonst alle Items aller Spiele untereinander.
        self.nur_dabei: bool = True
        self._treffer: dict = {}               # Slot-Name -> Erkennungsergebnis
        # Mehrfach-Lernen wird erst als Vorschau aufgebaut und danach bestaetigt.
        # PIL-Crops bleiben im Python-Prozess; die Seite erhaelt nur data:-Bilder.
        self._lern_review: list = []
        # Der Rückgängig-Stapel: `(Beschreibung, Abzug)` je Schritt, jüngster
        # zuletzt. Siehe `_merke()` — hier gab es bis dahin gar nichts, und ein
        # Rechteck über dreissig Slots plus Entf war endgültig.
        self._undo: list = []
        self._scan_dirty = False
        self._scan_status = ("", "info")
        self._vorschau: dict = {}              # Template-Datei -> (mtime, data-URL)
        # Wie die Dateien aussahen, als wir sie gelesen haben. Der Hauptprozess
        # schreibt dieselben — daran erkennt der Reiter, dass er veraltet ist.
        self._platte: dict = {}
        # Boss- und Icon-Scans liegen im selben Reiter, auf derselben Aufnahme
        # und mit demselben Rückgängig-Stapel. Ihr Zustand lebt in
        # `scan_detect.py`; von hier aus wird er nur mitgeführt.
        self._erkennung_init()

    def _scan_laden(self) -> None:
        """Slots, Items und Scan-Konfigurationen von Platte — einmal je Sitzung.

        Nicht im Konstruktor: wer das Studio für eine Sequenz aufmacht, soll nicht
        auf Dateien warten, die er vielleicht nie ansieht. `_platte_stand()` merkt
        sich dabei, wie sie aussahen — der Hauptprozess schreibt dieselben.
        """
        if self._scan_geladen:
            return
        self._scan_geladen = True
        self.scans = self._scans_laden()
        self._erkennung_laden()
        # Der zuletzt bearbeitete Scan ist offen — dieselbe Regel wie bei den
        # Sequenzen (`zuletzt_bearbeitet()` in `sequence_studio.py`) und aus
        # demselben Grund: ein echtes „zuletzt geöffnet" müsste jemand
        # mitschreiben, und das Dateisystem weiss es schon.
        #
        # Vorher öffnete sich nur bei GENAU EINEM Scan etwas. Wer einen zweiten
        # anlegte, sah beim nächsten Öffnen eine leere Mitte und musste erst
        # merken, dass oben links eine Auswahl steht.
        if self._scan_stand:
            neuster = max(self._scan_stand, key=lambda n: self._scan_stand[n])
            self.scan_offen = neuster
            self._scan_arbeitsbestand(neuster)
            self._foto_laden(neuster)
        self._platte = self._platte_stand()

    def _scan_hat_konfiguration(self, art: str) -> bool:
        """Ist für die gewünschte Aufnahmeart wirklich ein Scan geöffnet?"""
        if art == "boss":
            return self.boss_offen in self.boss_scans
        if art == "icon":
            return self.icon_offen in self.icon_scans
        return self.scan_offen in self.scans

    def _scan_voraussetzung(self, daten: Optional[dict] = None) -> Optional[dict]:
        """Sperrt Aufnahme und Bildwerkzeuge ohne eindeutiges Speicherziel.

        Ein Bild oder Slot ohne Scan lebte vorher nur im Arbeitsspeicher. Beim
        Speichern gab es keine Konfiguration, der man ihn hätte zuordnen können;
        nach dem Schliessen war er weg. Darum gilt die Reihenfolge zentral in der
        Brücke und nicht nur als deaktivierter Knopf in der Seite.
        """
        self._scan_laden()
        art = str((daten or {}).get("art") or self.scan_aufnahme_art or "item")
        if art not in ARTEN:
            art = "item"
        self.scan_aufnahme_art = art
        if self._scan_hat_konfiguration(art):
            return None
        name = {"item": "Item-Scan", "boss": "Boss-Scan", "icon": "Icon-Scan"}[art]
        return self._scan_melde(
            f"Zuerst einen {name} anlegen oder öffnen — erst danach können Bild "
            "und Bereiche dazu erfasst werden.", "warn")

    def _platte_stand(self) -> dict:
        """Pfad -> Änderungszeit für alles, was der Reiter von Platte liest.

        Der Ordner der Scans kommt als Ganzes mit: eine gelöschte oder neu
        dazugekommene Datei ändert seinen eigenen Zeitstempel, und genau das
        soll auffallen.
        """
        stand = {}
        scan_ordner = self.filepath.parent / "item_scans"
        pfade = [scan_ordner]
        pfade += sorted(scan_ordner.glob("*.json")) if scan_ordner.is_dir() else []
        # Boss- und Icon-Scans gehören dazu, seit der Reiter sie bearbeitet:
        # der Konsolen-Editor bleibt als zweiter Weg bestehen, und ein per LLM
        # entdeckter Boss landet im Lauf in der Bibliothek. Ohne diese Pfade
        # meldete „auf Platte hat sich etwas geändert" ausgerechnet das nicht,
        # woran man gerade arbeitet.
        pfade += self._erkennung_pfade()
        for p in pfade:
            try:
                stand[str(p)] = p.stat().st_mtime
            except OSError:
                stand[str(p)] = 0.0
        return stand

    def _platte_nachziehen(self, *pfade) -> None:
        """Der eigene Schreibvorgang zählt nicht als Fremdänderung.

        Das gemerkte Bild liegt unter `item_scans/bilder/`, und das Anlegen des
        Unterordners dreht die Änderungszeit des Elternordners weiter — sonst meldete
        der Reiter direkt nach der eigenen Aufnahme eine Fremdänderung.

        Ohne Argumente der ganze Stand (nach dem Speichern), mit Argumenten nur die
        genannten Pfade — sonst verschluckt es eine fremde Änderung anderswo.
        """
        stand = self._platte_stand()
        if not pfade:
            self._platte = stand
            return
        for pfad in pfade:
            if str(pfad) in stand:
                self._platte[str(pfad)] = stand[str(pfad)]

    def _platte_fremd(self) -> bool:
        """Hat jemand anders die Dateien angefasst, seit wir sie gelesen haben?

        „Jemand anders" ist im Alltag der eigene Hauptprozess: Auto-Lernen im
        Lauf schreibt `items.json`, der Konsolen-Editor schreibt Scans. Eigene
        Speicherungen zählen nicht mit — `scan_speichern()` zieht den Stand nach.
        """
        return bool(self._scan_geladen) and self._platte_stand() != self._platte

    def scan_neu_laden(self, daten: Optional[dict] = None) -> dict:
        """Liest Slots, Items und Scans neu von Platte.

        **Ungespeichertes wird nicht kommentarlos verworfen.** Der erste Druck
        meldet nur, der zweite (mit `verwerfen`) lädt — dieselbe Zwei-Schritt-
        Regel wie überall, wo hier etwas verloren gehen kann.
        """
        if self._scan_dirty and not (daten or {}).get("verwerfen"):
            return self._scan_melde(
                "Es gibt ungespeicherte Änderungen. Nochmal „Neu laden“ verwirft sie "
                "— „Speichern“ behält sie.", "warn")
        offen = self.scan_offen
        self._scan_geladen = False
        self._ecke = self._suchbereich = None
        self._auswahl, self._treffer = [], {}
        self.scan_name, self.scan_offen = "", ""
        self._vorschau = {}
        # Der Stapel beschreibt Stände, die es nach dem Neulesen nicht mehr
        # gibt. Ein Rückgängig darüber hinweg holte den Speicherstand von vorhin
        # zurück und überschriebe damit genau das, was gerade von Platte kam.
        self._undo = []
        self._scan_dirty = False
        self._boss_test = self._icon_test = None
        self._boss_tests = {}
        self._region_ziel = None
        self._scan_laden()
        # Der vorher offene Scan bleibt offen, wenn es ihn noch gibt — sonst
        # steht man nach dem Nachladen woanders als vorher.
        if offen and offen in self.scans:
            self.scan_offen = offen
            self.scan_art, self.scan_name = ART_SCAN, offen
            self._foto_laden(offen)
        return self._scan_melde(
            f"Neu geladen: {len(self.slots)} Slot(s), {len(self.items)} Item(s), "
            f"{len(self.scans)} Scan(s).")

    def _naechste_slot_id(self) -> int:
        """Die nächste freie Slot-ID — dieselbe Rechnung wie bei Punkten."""
        return max((s.id for s in self.slots.values()), default=0) + 1

    def _slot_ids_vergeben(self) -> None:
        """Backfill für Altbestand ohne Slot-ID.

        Neue Slots bekommen ihre ID bei der Entstehung (`scan_interaction.py`);
        ältere Dateien kennen das Feld noch nicht und laden mit `id=0`. Vergeben
        wird in stabiler Reihenfolge, sonst hinge die Zuteilung von der
        zufälligen Dict-Reihenfolge ab. Das ist ein Schreibzugriff wert — die ID
        soll ab jetzt feststehen, nicht bei jedem Start neu gewürfelt werden.

        **Stabil heisst hier natürlich sortiert, nicht Zeichen für Zeichen.**
        Ein reiner String-Vergleich stellt "Slot 10" zwischen "Slot 1" und
        "Slot 2"; bei sechzig durchnummerierten Slots bekam "Slot 2" damit die
        ID 12 und "Slot 3" die 23. Die IDs waren stabil und trotzdem
        unbrauchbar, weil sie in Sprüngen dastanden.
        """
        ohne = sorted((s for s in self.slots.values() if not s.id),
                      key=lambda s: _natuerlich(s.name))
        if not ohne:
            return
        naechste = self._naechste_slot_id()
        for slot in ohne:
            slot.id = naechste
            naechste += 1
        self._scan_dirty = True

    def _scans_laden(self) -> dict:
        """Alle Item-Scan-Konfigurationen als Name -> Config.

        Nebenbei wird der Änderungszeitpunkt jeder Datei gemerkt: daran hängt,
        welcher Scan beim Öffnen vorne steht.
        """
        from ...persistence import load_item_scan_file
        gefunden = {}
        self._scan_stand = {}
        ordner = self.filepath.parent / "item_scans"
        for pfad in sorted(ordner.glob("*.json")) if ordner.is_dir() else []:
            cfg = load_item_scan_file(pfad, self.board.name)
            if cfg is None:
                continue
            schluessel = cfg.name or pfad.stem
            gefunden[schluessel] = cfg
            try:
                self._scan_stand[schluessel] = pfad.stat().st_mtime
            except OSError:
                self._scan_stand[schluessel] = 0.0
        return gefunden

    def _scan_arbeitsbestand(self, name: str) -> None:
        """Bindet Listen und Werkzeuge an den Besitz des geöffneten Scans."""
        cfg = self.scans.get(name)
        self.slots = {slot.name: slot for slot in cfg.slots} if cfg else {}
        self.items = {item.name: item for item in cfg.items} if cfg else {}
        self._slot_ids_vergeben()

    def _objekte_angleichen(self) -> None:
        """Schreibt den Arbeitsbestand in den geöffneten Scan zurück."""
        cfg = self.scans.get(self.scan_offen)
        if cfg is not None:
            cfg.slots = list(self.slots.values())
            cfg.items = list(self.items.values())

    def _dazu(self, art: str, name: str) -> bool:
        """Nimmt einen frisch angelegten Slot bzw. ein Item in den offenen Scan.

        Wer in einem offenen Scan etwas anlegt, legt es für ihn an — sonst wäre es
        sofort wieder weg (die Listen zeigen nur die Mitglieder). Ohne offenen Scan
        passiert nichts. Gibt zurück, ob es eine Änderung war.
        """
        cfg = self.scans.get(self.scan_offen)
        if cfg is None:
            return False
        bestand = self.slots if art == ART_SLOT else self.items
        if name not in bestand:
            return False
        self._objekte_angleichen()
        return True

    def _scan_melde(self, text: str, art: str = "ok") -> dict:
        self._scan_status = (text, art)
        return self.scan_daten()

    def _scan_geaendert(self, text: str = "", art: str = "ok") -> dict:
        self._scan_dirty = True
        return self._scan_melde(text, art) if text else self.scan_daten()

    def _werkzeug_fertig(self) -> None:
        """Einmal-Werkzeuge fallen nach erfolgreicher Aktion ins Auswaehlen zurueck."""
        if not self.scan_werkzeug_fixiert:
            self.scan_modus = MODUS_WAHL
            self._ecke = None
            self._suchbereich = None
            # Das Ziel gehoerte zu genau diesem Durchgang. Bliebe es stehen,
            # wirkte der naechste Buchstabendruck auf einen Scan, den man
            # inzwischen gar nicht mehr offen hat.
            self._region_ziel = None

    # ----------------------------------------------------------- Rückgängig

    def _zustand(self) -> dict:
        """Ein vollständiger Abzug dessen, was dieser Reiter bearbeitet."""
        return {
            "slots": copy.deepcopy(self.slots),
            "items": copy.deepcopy(self.items),
            "scans": copy.deepcopy(self.scans),
            "art": self.scan_art,
            "name": self.scan_name,
            "auswahl": list(self._auswahl),
            "offen": self.scan_offen,
            "dirty": self._scan_dirty,
            "bereich": copy.deepcopy(self.scan_bereich),
            "fenster_id": self.scan_fenster_id,
            # Der Abzug ist vollständig oder er ist keiner: ein Rückgängig, das
            # die Slots zurückdreht und den Boss-Scan stehen lässt, wäre ein
            # halbes Zurück — und das ist schlimmer als gar keins.
            "erkennung": self._erkennung_zustand(),
        }

    def _merke(self, was: str) -> None:
        """Legt den Stand VOR einer Änderung auf den Rückgängig-Stapel.

        Ein vollständiger Abzug statt einzelner Rückwärts-Schritte: eine Aktion rührt
        hier fast immer an mehrere Stellen (ein gelöschter Slot verschwindet aus
        jedem Scan), und ein vergessener Rückwärts-Schritt drehte die Daten halb
        zurück. Aufgerufen von der Methode, die ändert — nicht von der Oberfläche.
        """
        self._undo.append((was, self._zustand()))
        del self._undo[:-UNDO_TIEFE]

    def scan_rueckgaengig(self, daten: Optional[dict] = None) -> dict:
        """Nimmt den letzten Schritt zurück (STRG+Z).

        Was auf Platte passiert ist, holt das nicht zurück: ein gelöschter Scan kommt
        als Konfiguration wieder, sein gemerkter Screenshot ist weg. Das steht in der
        Meldung, statt ein vollständiges Zurück zu versprechen.
        """
        if not self._undo:
            return self._scan_melde("Nichts zum Rückgängigmachen.", "info")
        was, stand = self._undo.pop()
        self.slots = stand["slots"]
        self.items = stand["items"]
        self.scans = stand["scans"]
        self.scan_art, self.scan_name = stand["art"], stand["name"]
        self._auswahl = [n for n in stand["auswahl"] if n in self.slots]
        self.scan_offen = stand["offen"]
        self._scan_dirty = stand["dirty"]
        self.scan_bereich = stand.get("bereich")
        self.scan_fenster_id = stand.get("fenster_id", 0)
        self._erkennung_zurueck(stand.get("erkennung") or {})
        # Die Scan-Konfigurationen tragen abgeleitete Objektlisten; nach dem
        # Abzug zeigen sie auf Kopien statt auf die Slots in `self.slots`.
        self._objekte_angleichen()
        # Ein Treffer gehört zu dem Slot-Stand, in dem er gemessen wurde. Was es
        # nicht mehr gibt, fliegt raus — der Rest bleibt gültig, denn das Bild
        # hat sich nicht geändert.
        self._treffer = {n: t for n, t in self._treffer.items() if n in self.slots}
        return self._scan_melde(
            f"Rückgängig: {was}. ({len(self._undo)} weitere Schritte)"
            if self._undo else f"Rückgängig: {was}.", "warn")

    def _schritte(self) -> list:
        """Die drei Schritte zu einem neuen Scan, mit ihrem Stand.

        Zwischen Schritt 2 und 3 liegt das Spiel: Slots nimmt man oft am leeren
        Inventar auf, „Items lernen" auf dem alten Bild lernt leere Slots.

        Der Stand wird abgeleitet, nicht mitgeschrieben — erledigt heisst: es ist da.
        """
        cfg = self.scans.get(self.scan_offen)
        hat_slots = (any(s.enabled for s in cfg.slots) if cfg
                     else any(s.enabled for s in self.slots.values()))
        hat_items = (any(i.enabled for i in cfg.items) if cfg
                     else any(i.enabled for i in self.items.values()))
        roh = [
            (1, "Bild", "Aufnehmen — Vollbild, oder vorher rechts ein Fenster "
                "wählen.", self._foto is not None,
             "scan_foto", "Screenshot aufnehmen"),
            (2, "Slots", "Bereich um das Inventar aufziehen, dann auf einen "
                "LEEREN Slot-Hintergrund klicken.", hat_slots,
             "modus:" + MODUS_FINDEN, "Slots finden"),
            (3, "Items", "Inventar im Spiel füllen, NEU aufnehmen, dann lernen.",
             hat_items, "scan_lernvorschau", "Items prüfen & lernen"),
        ]
        offen = [nr for nr, _, _, fertig, _, _ in roh if not fertig]
        aktuell = offen[0] if offen else 0
        return [{"nr": nr, "titel": titel, "was": was, "fertig": fertig,
                 "aktuell": nr == aktuell, "befehl": befehl, "knopf": knopf}
                for nr, titel, was, fertig, befehl, knopf in roh]

    def _flaeche(self) -> Optional[dict]:
        """Die Arbeitsfläche: das Bild, sonst das Rechteck um die Slots.

        Ein älterer Scan bringt Slots mit, aber kein gemerktes Bild; ohne die
        Ersatzfläche stünde die Mitte leer, obwohl die Slots da sind. Alle
        Umrechnungen laufen über `links`/`oben`/`skala` und stimmen genauso.
        `bild` sagt, was von beidem dasteht.
        """
        if self._foto_info:
            return dict(self._foto_info, bild=True)
        regionen = [s.scan_region for s in self._scan_slots() if s.scan_region]
        if not regionen:
            return None
        rand = 40
        links = min(r[0] for r in regionen) - rand
        oben = min(r[1] for r in regionen) - rand
        rechts = max(r[2] for r in regionen) + rand
        unten = max(r[3] for r in regionen) + rand
        return {"links": links, "oben": oben, "bild": False, "skala": 1.0,
                "breite": max(1, rechts - links), "hoehe": max(1, unten - oben),
                "stand": 0.0}

    def _scan_slots(self) -> list:
        """Die Slots des offenen Scans.

        `self.slots` ist bereits die gebundene Arbeitsansicht genau dieses
        Scans. Eine zweite Mitgliedsliste würde denselben Besitz nochmals und
        potenziell widersprüchlich ausdrücken.
        """
        return list(self.slots.values())

    # -------------------------------------------------------- Momentaufnahme

    def scan_daten(self, daten: Optional[dict] = None) -> dict:
        """Alles, was der Reiter zum Zeichnen braucht — ohne das Bild selbst."""
        # Lokal wie in `_katalog_pruefen()`: `scan_state` soll `config` nicht
        # schon beim Import nachziehen. `CONFIG` und nicht `load_config()` —
        # es gibt EIN Config-Objekt pro Prozess, und der Einstellungen-Reiter
        # haelt es aktuell.
        from ...config import CONFIG
        self._scan_laden()
        text, art = self._scan_status
        cfg = self.scans.get(self.scan_offen)
        dabei_slots = set(cfg.slot_names) if cfg else set()
        dabei_items = set(cfg.item_names) if cfg else set()
        # Einmal gerechnet: die Arbeitsfläche steht in der Aufnahme UND
        # entscheidet, welche fremden Slots gerade zu sehen sind.
        flaeche = self._flaeche()
        # **Die Nummer eines Slots ist seine Stelle im Scan**, nicht eine
        # erfundene ID: `ItemSlot` hat keine, der Name IST der Schlüssel — und
        # genau diese Reihenfolge läuft `execute_item_scan()` ab. „#7" heisst
        # also „wird als siebter angesehen", und das ist die Frage, die man an
        # eine Nummer hat.
        aktive_slots = [s for s in cfg.slots if s.enabled] if cfg else []
        nummern = {s.name: i + 1 for i, s in enumerate(aktive_slots)}
        erkannt = self._erkannte_items()
        return {
            # Scan, Slots, Items und Vorlagen liegen im Ordner dieser Sequenz.
            # Der Bezug muss in der Ansicht vor der Aufnahme sichtbar sein;
            # nur aus dem aktuell offenen Editor darauf zu schliessen ist bei
            # mehreren Sequenzen zu fehleranfaellig.
            "sequenz": self.board.name,
            "aufnahme_bereit": {
                art: self._scan_hat_konfiguration(art) for art in ARTEN
            },
            "modus": self.scan_modus,
            "werkzeug_fixiert": self.scan_werkzeug_fixiert,
            "ecke": list(self._ecke) if self._ecke else None,
            # Der Suchbereich muss zu SEHEN sein, solange man noch die Farbe
            # zeigen soll — sonst klickt man den Hintergrund an und weiss nicht,
            # worin gesucht wird.
            "suchbereich": list(self._suchbereich) if self._suchbereich else None,
            "foto": flaeche,
            "slots": [self._slot_json(s, s.name in dabei_slots,
                                      nummern.get(s.name), len(aktive_slots),
                                      bool(cfg.reverse) if cfg else False)
                      for s in self.slots.values()],
            "items": [self._item_json(i, i.name in dabei_items, erkannt.get(i.name))
                      for i in self.items.values()],
            "scans": [self._scan_json(c) for c in self.scans.values()],
            "kategorien": existing_categories(self.items),
            # Ob der OFFENE Scan den Katalog benutzt UND eine Datei da ist. Die
            # Ansicht rechnet das nicht selbst nach: sie sieht `config.json`
            # nicht, und zwei Antworten auf dieselbe Frage liefen auseinander.
            "katalog_an": bool(self._katalog()),
            # Ob die Sammel-Benennung ueberhaupt etwas tun kann. Die Ansicht
            # sieht `config.json` nicht — ein Knopf, der jedes Mal nur „ist
            # nicht aktiviert" meldet, ist schlechter als keiner.
            "llm_an": bool(CONFIG.llm_enabled),
            # Laeuft gerade ein Benenn-Durchgang, und wie weit ist er?
            "autoname": self._autoname_stand(),
            "bereich": list(self.scan_bereich) if self.scan_bereich else None,
            "fenster_id": self.scan_fenster_id,
            # Der Titel ist die dauerhafte Quelle, das HWND nur ihr aktueller
            # Sitzungswert. So bleibt in der Oberfläche auch bei geschlossenem
            # Spiel sichtbar, welches Fenster dieser Scan erwartet.
            "fenster_titel": cfg.capture_window_title if cfg else None,
            "fenster_verfuegbar": bool(self.scan_fenster_id),
            "fenster_referenz": (list(cfg.capture_window_rect)
                                  if cfg and cfg.capture_window_rect else None),
            "schritte": self._schritte(),
            "offen": self.scan_offen,
            "nur_dabei": self.nur_dabei,
            "wahl": {"art": self.scan_art, "name": self.scan_name},
            # Die Menge, auf der Sammel-Aktionen laufen. `wahl` bleibt der EINE,
            # den der Inspektor bearbeitet — zwei Dinge, zwei Felder.
            "auswahl": [n for n in self._auswahl if n in self.slots],
            # Was STRG+Z zurücknehmen würde. Der Knopf nennt es beim Namen: ein
            # „Rückgängig" ohne Angabe, WAS es rückgängig macht, drückt man
            # entweder gar nicht oder einmal zu oft.
            "undo": {"tiefe": len(self._undo),
                     "was": self._undo[-1][0] if self._undo else ""},
            "dirty": self._scan_dirty,
            # Hat der Hauptprozess die Dateien angefasst? Ein Lauf mit
            # Auto-Lernen tut das, und ohne diesen Hinweis sucht man die
            # gelernten Items im Reiter vergeblich.
            "fremd": self._platte_fremd(),
            "status": {"text": text, "art": art},
            "ergebnis": self._ergebnis_json(),
            "review": self._review_json(),
            # Beide sind optional und der Reiter sagt es, statt Knöpfe
            # anzubieten, die nichts tun: ohne Pillow gibt es kein Bild, ohne
            # OpenCV kein Template-Matching (also keine Erkennung und kein
            # Erkennen von Doppelten beim Lernen).
            "opencv": self._hat_opencv(),
            "pillow": self._hat_pillow(),
            # Boss- und Icon-Scans liegen in derselben Momentaufnahme: sie
            # teilen sich Bühne, Zoom, Rückgängig und Speichern-Knopf. Zwei
            # Aufnahmen hiessen zwei Wahrheiten über dasselbe Bild.
            **self._erkennung_json(),
        }

    def _ergebnis_json(self) -> Optional[dict]:
        """Kompakte Auswertung des letzten Testscans fuer die Ergebnisleiste."""
        if not self._treffer:
            return None
        slots = self._scan_slots()
        slot_namen = {s.name for s in slots}
        treffer = {n: t for n, t in self._treffer.items() if n in slot_namen}
        erkannt = [n for n, t in treffer.items() if t.get("name") and not t.get("fremd")]
        fremd = [n for n, t in treffer.items() if t.get("name") and t.get("fremd")]
        unbekannt = [n for n, t in treffer.items() if not t.get("name")]
        return {
            "gesamt": len(slots), "erkannt": len(erkannt), "fremd": len(fremd),
            "unbekannt": len(unbekannt), "erkannt_slots": erkannt,
            "fremd_slots": fremd, "unbekannt_slots": unbekannt,
        }

    def _review_json(self) -> Optional[dict]:
        if not self._lern_review:
            return None
        return {
            "zeilen": [
                {k: v for k, v in zeile.items() if k != "crop"}
                for zeile in self._lern_review
            ],
            # Name ist zugleich die Item-Identitaet. Die Vorschlaege machen es
            # moeglich, eine weitere Slot-Groesse an ein bestehendes Item zu
            # haengen, statt aus Versehen ein zweites Item anzulegen.
            "itemnamen": sorted(self.items, key=str.casefold),
        }

    @staticmethod
    def _hat_opencv() -> bool:
        try:
            from ...imaging import OPENCV_AVAILABLE
            return bool(OPENCV_AVAILABLE)
        except ImportError:
            return False

    @staticmethod
    def _hat_pillow() -> bool:
        try:
            from ...imaging import PILLOW_AVAILABLE
            return bool(PILLOW_AVAILABLE)
        except ImportError:
            return False

    def _slot_json(self, slot: ItemSlot, dabei: bool = False,
                   nummer: Optional[int] = None, gesamt: int = 0,
                   rueckwaerts: bool = False) -> dict:
        treffer = self._treffer.get(slot.name)
        breite = slot.scan_region[2] - slot.scan_region[0]
        hoehe = slot.scan_region[3] - slot.scan_region[1]
        return {
            "dabei": dabei,
            "aktiv": bool(slot.enabled),
            "name": slot.name,
            "region": list(slot.scan_region),
            "klick": list(slot.click_pos),
            "farbe": hexfarbe(slot.slot_color),
            "breite": breite,
            "hoehe": hoehe,
            # Zu klein, um je etwas zu erkennen — und im Bild kaum zu treffen.
            # Neu entstehen kann so einer nicht mehr; wer noch einen hat, soll
            # ihn in der LISTE finden, denn dort ist er so gross wie jeder
            # andere. Das ist der zweite Weg zum Löschen.
            "winzig": breite < MIN_SLOT or hoehe < MIN_SLOT,
            "treffer": treffer,
            # **Stabile Identität.** Bleibt beim Aus- und Wiedereinschalten
            # gleich; die laufende Nummer gehört dagegen nur aktiven Slots.
            "id": slot.id,
            # Die Stelle im offenen Scan (1-basiert) und die Stelle im LAUF —
            # die beiden gehen auseinander, sobald „Slots rückwärts" an ist.
            # Nur für den Tooltip und die Vorsortierung; angezeigt wird die ID.
            "nummer": nummer,
            "lauf": (gesamt - nummer + 1) if (nummer and rueckwaerts) else nummer,
            "gesamt": gesamt,
        }

    def _erkannte_items(self) -> dict:
        """Item-Name -> die Slots, in denen es gerade erkannt wird.

        Ein erkanntes Item steht deshalb im Scan-Inspektor, bevor jemand es ein
        zweites Mal lernt. Der Slot-Name kommt mit: „erkannt" ohne Beleg ist eine
        Behauptung, und in der Item-Liste sah man vom Erkennen sonst gar nichts.
        """
        gefunden: dict = {}
        for slot, eintrag in self._treffer.items():
            name = eintrag.get("name")
            if name:
                gefunden.setdefault(name, []).append(slot)
        return gefunden

    def _item_json(self, item: ItemProfile, dabei: bool = False,
                   erkannt_in=None) -> dict:
        from ...imaging import template_size
        vorlagen = item.template_names()
        groessen = []
        for name in vorlagen:
            groesse = template_size(name, self.filepath.parent / "templates")
            if groesse and list(groesse) not in groessen:
                groessen.append(list(groesse))
        scan_groessen = []
        cfg = self.scans.get(self.scan_offen)
        if cfg is not None:
            for slot_name in cfg.slot_names:
                slot = self.slots.get(slot_name)
                if slot is None:
                    continue
                region = slot.scan_region
                groesse = [region[2] - region[0], region[3] - region[1]]
                if groesse not in scan_groessen:
                    scan_groessen.append(groesse)
        fehlende_groessen = ([g for g in scan_groessen if g not in groessen]
                             if vorlagen else [])
        return {
            "dabei": dabei,
            "aktiv": bool(item.enabled),
            # Gehört (noch) nicht dazu, wird aber gerade gesehen. Die Ansicht
            # zeigt genau diese beiden Sorten, alles Weitere auf Knopfdruck: ein
            # neuer Scan soll leer anfangen und nicht mit dem Bestand eines
            # fremden Spiels.
            "erkannt": bool(erkannt_in),
            # In WELCHEN Slots — sonst ist „erkannt" eine Behauptung ohne Beleg,
            # und bei einem Fehlgriff (zwei Items sehen sich ähnlich) fehlt
            # genau die Angabe, an der man ihn bemerkt.
            "erkannt_in": list(erkannt_in or []),
            "name": item.name,
            "kategorie": item.category,
            "prioritaet": item.priority,
            "konfidenz": item.min_confidence,
            "template": vorlagen[0] if vorlagen else None,
            "vorlagen": vorlagen,
            "vorlagengroessen": groessen,
            "fehlende_scan_groessen": fehlende_groessen,
            "marker": [hexfarbe(c) for c in item.marker_colors],
            # **Der Klick danach.** Manche Spiele fragen nach („wirklich
            # verkaufen?"), und ohne die Bestätigung bleibt das Popup stehen —
            # der nächste Slot wird dann gar nicht mehr erreicht. Das Feld gab
            # es im Modell und in den Konsolen-Editoren seit jeher; im Studio
            # war es die einzige Item-Eigenschaft ohne Bedienelement.
            "bestaetigung": self._bestaetigung_json(item),
            "bestaetigung_verzoegerung": item.confirm_delay,
            # Ein Profil ohne Template UND ohne Marker wird nie erkannt — das
            # sagt die Selbstdiagnose auch, nur eben erst beim Start.
            "stumm": not vorlagen and not item.marker_colors,
        }

    def _bestaetigung_json(self, item: ItemProfile) -> Optional[dict]:
        """Der Bestätigungsklick eines Items — als Punkt, nie als Zahlenpaar.

        Die Koordinate steht in der Punktliste der `sequence.json`, sonst nirgends; `confirm_point`
        ist der abgeleitete Arbeitswert. Zeigt die Referenz ins Leere, wird das
        gesagt statt verschwiegen — ein Klick auf (0, 0) wäre schlimmer.
        """
        if item.confirm_point_id is None:
            return None
        punkt = next((p for p in self.points if p.id == item.confirm_point_id), None)
        if punkt is None:
            return {"punkt_id": item.confirm_point_id, "fehlt": True,
                    "text": f"Punkt #{item.confirm_point_id} fehlt"}
        return {"punkt_id": punkt.id, "fehlt": False,
                "text": (punkt.name or f"Punkt {punkt.id}")
                        + f" ({punkt.x}, {punkt.y})"}

    def _scan_json(self, cfg: ItemScanConfig) -> dict:
        return {
            "name": cfg.name,
            "slots": list(cfg.slot_names),
            "items": list(cfg.item_names),
            "toleranz": cfg.color_tolerance,
            "lernen": bool(cfg.learn_unknown),
            "reverse": bool(cfg.reverse),
            "use_catalog": bool(cfg.use_catalog),
            "fenster": ({
                "titel": cfg.capture_window_title,
                "instanz": cfg.capture_window_index,
                "referenz": (list(cfg.capture_window_rect)
                              if cfg.capture_window_rect else None),
            } if cfg.capture_window_title else None),
            # Namen, die es global nicht mehr gibt: der Scan läuft mit dem Rest
            # weiter, aber man soll es sehen, bevor er es meldet.
            "fehlend": ([n for n in cfg.slot_names if n not in self.slots] +
                        [n for n in cfg.item_names if n not in self.items]),
        }

    def scan_vorschau(self, daten: Optional[dict] = None) -> dict:
        """Template-Bilder als data:-URLs — nur die angefragten Namen.

        Getrennt von `scan_daten()` aus demselben Grund wie der Screenshot: bei
        fünfzig Items wären das 200 KB, die sonst bei jedem Klick mitliefen. Die
        Seite merkt sie sich und fragt nur nach, was sie noch nicht hat.
        """
        self._scan_laden()
        namen = (daten or {}).get("namen") or []
        ergebnis = {}
        for name in namen:
            item = self.items.get(name)
            if item is None or not item.template_names():
                continue
            url = self._template_url(item.template_names()[0])
            if url:
                ergebnis[name] = url
        return ergebnis

    def _template_url(self, dateiname: str) -> str:
        """Ein Template als data:-URL, gemerkt an mtime + Name."""
        pfad = self.filepath.parent / "templates" / dateiname
        try:
            stand = pfad.stat().st_mtime
        except OSError:
            return ""
        gemerkt = self._vorschau.get(dateiname)
        if gemerkt and gemerkt[0] == stand:
            return gemerkt[1]
        try:
            roh = pfad.read_bytes()
        except OSError:
            return ""
        url = "data:image/png;base64," + base64.b64encode(roh).decode("ascii")
        self._vorschau[dateiname] = (stand, url)
        return url

    # ------------------------------------------------------ Auswahl und Modus
