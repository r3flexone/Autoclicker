"""Zustand, Darstellung und Undo-Verlauf des Scan-Editors."""

import base64
import copy
from pathlib import Path
from typing import Optional

from ...models import ItemProfile, ItemScanConfig, ItemSlot
from ...persistence.paths import ITEMS_FILE, SLOTS_FILE, TEMPLATES_DIR
from .model import hexfarbe
from .scan_contract import (
    ART_SCAN,
    ART_SLOT,
    MIN_SLOT,
    MODUS_FINDEN,
    MODUS_WAHL,
    UNDO_TIEFE,
)
from .scan_model import (
    existing_categories,
    load_items,
    load_slots,
)


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

        Nicht im Konstruktor: wer das Studio für eine Sequenz aufmacht, soll
        nicht auf das Lesen von Dateien warten, die er vielleicht nie ansieht.

        **„Einmal je Sitzung" war zu wenig.** Der Hauptprozess schreibt dieselben
        Dateien, während das Fenster offensteht: ein Lauf mit `learn_unknown`
        legt neue Items an und speichert sie. Die Konsole meldete „gelernt", das
        Studio zeigte sie nie — es hatte `items.json` beim Öffnen gelesen und
        danach nie wieder. Deshalb merkt sich `_platte_stand()`, wie die Dateien
        beim Laden aussahen, und `scan_daten()` sagt, wenn sich das geändert hat.
        """
        if self._scan_geladen:
            return
        self._scan_geladen = True
        self.slots = load_slots(SLOTS_FILE)
        self.items = load_items(ITEMS_FILE)
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
            self._foto_laden(neuster)
        self._platte = self._platte_stand()

    def _platte_stand(self) -> dict:
        """Pfad -> Änderungszeit für alles, was der Reiter von Platte liest.

        Der Ordner der Scans kommt als Ganzes mit: eine gelöschte oder neu
        dazugekommene Datei ändert seinen eigenen Zeitstempel, und genau das
        soll auffallen.
        """
        from ...persistence.paths import ITEM_SCANS_DIR
        stand = {}
        pfade = [Path(SLOTS_FILE), Path(ITEMS_FILE), Path(ITEM_SCANS_DIR)]
        pfade += sorted(Path(ITEM_SCANS_DIR).glob("*.json")) \
            if Path(ITEM_SCANS_DIR).is_dir() else []
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

    def _scans_laden(self) -> dict:
        """Alle Item-Scan-Konfigurationen als Name -> Config.

        Nebenbei wird der Änderungszeitpunkt jeder Datei gemerkt: daran hängt,
        welcher Scan beim Öffnen vorne steht.
        """
        from ...persistence import list_available_item_scans, load_item_scan_file
        gefunden = {}
        self._scan_stand = {}
        for name, pfad in list_available_item_scans():
            cfg = load_item_scan_file(pfad)
            if cfg is None:
                continue
            schluessel = cfg.name or name
            gefunden[schluessel] = cfg
            try:
                self._scan_stand[schluessel] = pfad.stat().st_mtime
            except OSError:
                self._scan_stand[schluessel] = 0.0
        return gefunden

    def _objekte_angleichen(self) -> None:
        """Zieht die abgeleiteten Objektlisten der Scans an ihren Namen nach.

        **Ohne das kommt Gelöschtes zurück.** `ItemScanConfig.sync_names()` füllt
        eine leere Namensliste aus den Objekten — genau dafür ist sie da (der
        Editor baut die Config aus Objekten). Wer also nur `item_names` leert und
        `items` stehen lässt, hat beim nächsten Speichern wieder alles drin.

        Muss deshalb nach **jeder** Änderung an den Namen laufen: Häkchen,
        Umbenennen, Löschen.
        """
        for cfg in self.scans.values():
            cfg.slots = [self.slots[n] for n in cfg.slot_names if n in self.slots]
            cfg.items = [self.items[n] for n in cfg.item_names if n in self.items]

    def _dazu(self, art: str, name: str) -> bool:
        """Nimmt einen frisch angelegten Slot bzw. ein Item in den offenen Scan.

        **Wer in einem offenen Scan etwas anlegt, legt es FÜR ihn an.** Ohne das
        war der neue Slot sofort wieder weg: die Listen zeigen standardmässig nur
        die Mitglieder, und ein gerade aufgezogener Slot war keines. Man musste
        den Filter ausschalten, ihn suchen und ein Häkchen setzen — für etwas,
        das man erkennbar gerade für diesen Scan gemacht hat.

        Ohne offenen Scan passiert nichts; dann arbeitet man am Bestand.

        Gibt zurück, ob es eine Änderung war — „war schon dabei" ist etwas
        anderes als „gerade aufgenommen", und der Suchdurchgang zählt beides
        getrennt.
        """
        cfg = self.scans.get(self.scan_offen)
        if cfg is None:
            return False
        namen = cfg.slot_names if art == ART_SLOT else cfg.item_names
        if name in namen:
            return False
        namen.append(name)
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

        **Es gab hier kein Rückgängig, und das war die grösste Lücke des
        Reiters.** Ein Auswahl-Rechteck über dreissig Slots und ein Druck auf
        Entf waren endgültig; der einzige Ausweg hiess „Neu laden" — und der
        wirft *alles* seit dem letzten Speichern weg, also auch die halbe Stunde
        Arbeit davor. Zwischen „ich habe mich um einen Slot vertan" und „ich
        werfe den Nachmittag weg" lag nichts.

        Der ganze Abzug statt einzelner Rückwärts-Schritte: eine Aktion hier
        rührt fast immer an mehrere Stellen gleichzeitig (ein gelöschter Slot
        verschwindet aus jedem Scan, ein umbenanntes Item wird in jedem Scan
        nachgezogen). Rückwärts-Schritte müssten jede dieser Nebenwirkungen
        einzeln kennen — und ein vergessener wäre ein Rückgängig, das die Daten
        halb zurückdreht. Das ist schlimmer als keins. Ein Abzug kostet bei
        einem echten Bestand rund 30 KB und ist damit billiger als der Fehler,
        den er verhindert.

        Aufgerufen wird es **vor** der Änderung und von der Methode, die sie
        macht — nicht von der Oberfläche: sonst hinge das Rückgängig daran, dass
        jeder Knopf daran denkt.
        """
        self._undo.append((was, self._zustand()))
        del self._undo[:-UNDO_TIEFE]

    def scan_rueckgaengig(self, daten: Optional[dict] = None) -> dict:
        """Nimmt den letzten Schritt zurück (STRG+Z).

        **Was auf Platte passiert ist, holt das nicht zurück.** Ein gelöschter
        Scan kommt als Konfiguration wieder und wird beim nächsten Speichern neu
        geschrieben — sein gemerkter Screenshot ist aber weg, und gelernte
        Templates bleiben liegen (die gehören womöglich schon einem anderen
        Item). Das steht in der Meldung, statt ein vollständiges Zurück zu
        versprechen, das es nicht gibt.
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

        **Die Reihenfolge stand nirgends.** Der Reiter zeigte alle Bedienelemente
        gleichzeitig, und wer zum ersten Mal einen Scan anlegt, sieht eine Wand
        aus Knöpfen statt eines Weges. Die drei Schritte sind immer dieselben:
        Bereich, Slots, Items.

        **Zwischen Schritt 2 und 3 liegt das Spiel.** Slots nimmt man oft an
        einem LEEREN Inventar auf — dann gibt es noch nichts zu lernen. Man füllt
        es, nimmt neu auf und lernt erst dann. Genau das sagt Schritt 3, weil es
        sonst niemand ahnt: ein „Items lernen" auf dem alten Bild lernt drei
        leere Slots.

        Der Stand wird **abgeleitet, nicht mitgeschrieben** — sonst gäbe es einen
        Fortschritt, der nicht zu den Daten passt. Erledigt heisst schlicht: es
        ist da.
        """
        cfg = self.scans.get(self.scan_offen)
        hat_slots = bool(cfg.slot_names) if cfg else bool(self.slots)
        hat_items = bool(cfg.item_names) if cfg else bool(self.items)
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

        **Ein Scan ohne Bild ist nicht dasselbe wie ein Scan ohne Inhalt.** Ein
        älterer Scan bringt seine Slots mit, aber kein gemerktes Bild — das gibt
        es erst, seit der Reiter es ablegt. Bis hierher stand die Mitte deshalb
        leer, obwohl die Slots längst da waren: man sah nicht, was man hat, und
        konnte nichts davon anfassen.

        Ohne Bild wird die Fläche aus dem umschliessenden Rechteck der Slots
        gerechnet (mit etwas Rand). Alle Umrechnungen laufen über `links`/`oben`
        und `skala` — die stimmen dann genauso, nur ist der Hintergrund leer.
        Ein späterer Screenshot legt sich dahinter, ohne dass sich etwas
        verschiebt.

        `bild` sagt, was von beidem es ist. Ohne das würde die Seite ein Bild
        nachfordern, das es nicht gibt.
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
        """Die Slots, um die es geht: die des offenen Scans, sonst der Bestand.

        **Der offene Scan ist der Bezug, nicht der Bestand.** Wer zwei Spiele
        betreibt, hat die Slots beider in einer Datei — und alles, was „alle
        Slots" sagt, meinte bis hierher wirklich alle. Das war an drei Stellen
        falsch, und zwei davon fielen nur als seltsame Zahl auf:

        - „aus ALLEN Slots lernen" lief über den ganzen Bestand. Die Slots des
          anderen Spiels liegen ausserhalb des Bildes, also kam nichts dabei
          heraus — gemeldet wurde es aber als „11 ohne Bild", und man sucht den
          Fehler beim Screenshot.
        - „X von 56 Slot(s) erkannt" nannte den Bestand als Nenner, obwohl der
          Scan 45 hat. Elf davon konnten gar nicht erkannt werden.
        - Die Ersatzfläche (kein Bild gemerkt) legte sich um beide Spiele und
          war damit doppelt so gross wie nötig.

        Ohne offenen Scan ist der Bestand die richtige Antwort: dann gibt es
        keine engere Menge.
        """
        cfg = self.scans.get(self.scan_offen)
        if cfg is None:
            return list(self.slots.values())
        return [self.slots[n] for n in cfg.slot_names if n in self.slots]

    # -------------------------------------------------------- Momentaufnahme

    def scan_daten(self, daten: Optional[dict] = None) -> dict:
        """Alles, was der Reiter zum Zeichnen braucht — ohne das Bild selbst."""
        self._scan_laden()
        text, art = self._scan_status
        cfg = self.scans.get(self.scan_offen)
        dabei_slots = set(cfg.slot_names) if cfg else set()
        dabei_items = set(cfg.item_names) if cfg else set()
        erkannt = self._erkannte_items()
        return {
            "modus": self.scan_modus,
            "werkzeug_fixiert": self.scan_werkzeug_fixiert,
            "ecke": list(self._ecke) if self._ecke else None,
            # Der Suchbereich muss zu SEHEN sein, solange man noch die Farbe
            # zeigen soll — sonst klickt man den Hintergrund an und weiss nicht,
            # worin gesucht wird.
            "suchbereich": list(self._suchbereich) if self._suchbereich else None,
            "foto": self._flaeche(),
            "slots": [self._slot_json(s, s.name in dabei_slots) for s in self.slots.values()],
            "items": [self._item_json(i, i.name in dabei_items, i.name in erkannt)
                      for i in self.items.values()],
            "scans": [self._scan_json(c) for c in self.scans.values()],
            "kategorien": existing_categories(self.items),
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

    def _slot_json(self, slot: ItemSlot, dabei: bool = False) -> dict:
        treffer = self._treffer.get(slot.name)
        breite = slot.scan_region[2] - slot.scan_region[0]
        hoehe = slot.scan_region[3] - slot.scan_region[1]
        return {
            "dabei": dabei,
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
        }

    def _erkannte_items(self) -> set:
        """Welche Items gerade in irgendeinem Slot erkannt werden.

        **Das ist der Grund, warum die Item-Liste eines Scans nicht leer bleibt.**
        Dasselbe Item kann in mehreren Spielen vorkommen; es ein zweites Mal zu
        lernen ist genau das, was man vermeiden will. Wird es erkannt, steht es
        im Scan-Inspektor — bevor jemand auf die Idee kommt, es neu zu lernen.
        Ein Haken genügt dann.
        """
        return {e["name"] for e in self._treffer.values() if e.get("name")}

    def _item_json(self, item: ItemProfile, dabei: bool = False,
                   erkannt: bool = False) -> dict:
        from ...imaging import template_size
        vorlagen = item.template_names()
        groessen = []
        for name in vorlagen:
            groesse = template_size(name)
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
            # Gehört (noch) nicht dazu, wird aber gerade gesehen. Die Ansicht
            # zeigt genau diese beiden Sorten, alles Weitere auf Knopfdruck: ein
            # neuer Scan soll leer anfangen und nicht mit dem Bestand eines
            # fremden Spiels.
            "erkannt": erkannt,
            "name": item.name,
            "kategorie": item.category,
            "prioritaet": item.priority,
            "konfidenz": item.min_confidence,
            "template": vorlagen[0] if vorlagen else None,
            "vorlagen": vorlagen,
            "vorlagengroessen": groessen,
            "fehlende_scan_groessen": fehlende_groessen,
            "marker": [hexfarbe(c) for c in item.marker_colors],
            # Ein Profil ohne Template UND ohne Marker wird nie erkannt — das
            # sagt die Selbstdiagnose auch, nur eben erst beim Start.
            "stumm": not vorlagen and not item.marker_colors,
        }

    def _scan_json(self, cfg: ItemScanConfig) -> dict:
        return {
            "name": cfg.name,
            "slots": list(cfg.slot_names),
            "items": list(cfg.item_names),
            "toleranz": cfg.color_tolerance,
            "lernen": bool(cfg.learn_unknown),
            "reverse": bool(cfg.reverse),
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
        pfad = Path(TEMPLATES_DIR) / dateiname
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
