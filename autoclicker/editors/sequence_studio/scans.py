"""
Der Reiter „Scans": Slots, Items und Item-Scans auf einem Screenshot.

Hier lag bis zum Umbau ein eigenes Fenster in Dear PyGui
(`editors/scan_canvas/`). Es ist ersatzlos weg — die Arbeit ist dieselbe
geblieben, aber sie gehört in dasselbe Fenster wie die Sequenz, die die Scans
benutzt. Zwei Fenster mit zwei Bedienkonzepten für dieselben Dateien waren
eines zu viel.

**Was hier liegt und was nicht.** Die Logik — Auswahl, Modus, Rechteck aus zwei
Ecken, Farbe messen, Item lernen, Erkennung — steht in dieser Klasse und wird in
`tools/test_logic.py` gemessen. Die Ansicht zeichnet nur, was `scan_daten()`
sagt. Dieselbe Regel wie in `bridge.py`, und aus demselben Grund: eine
Oberfläche lässt sich hier nicht testen, eine Momentaufnahme schon.

**Der Screenshot bleibt in Python.** Die Seite bekommt ihn einmal als
verkleinertes Bild; gemessen wird nie darauf, sondern immer im Originalbild
(`_foto_farbe`). Ein Farbwert, den die Ansicht aus einem skalierten Bild abliest,
wäre interpoliert — und dieselbe Farbe soll später der Worker wiederfinden.

**Die Erkennung fragt die Laufzeit, nicht sich selbst.** `scan_erkennen()` ruft
`_check_profile_match()` aus `runtime/item_scan.py` — dieselbe Funktion, die im
Lauf entscheidet. Eine zweite Rechnung „nur für die Vorschau" wäre eine Vorschau,
die etwas anderes zeigt als das, was passiert.
"""

import base64
import copy
import io
from pathlib import Path
from typing import Optional

from ...models import ItemProfile, ItemScanConfig, ItemSlot
from ...persistence.paths import (
    ITEMS_FILE, SLOTS_FILE, TEMPLATES_DIR,
)
from ...utils import eindeutiger_name, sanitize_filename
from .model import hexfarbe, rgbwert
from .scan_capture import ScanCaptureMixin
from .scan_model import (
    existing_categories, load_items, load_slots, next_item_name,
    next_slot_name, normalize_region, save_items, save_slots, save_template,
)
from ..scan_services import detect_slots_in_image

# Die Modi des Zeigers auf dem Bild. Mehr als einer ist nötig, weil ein Klick
# auf dieselbe Stelle Verschiedenes bedeuten kann — und ein Klick, dessen
# Bedeutung man raten muss, ist schlimmer als ein Modus-Knopf.
MODUS_WAHL = "wahl"        # Slot unter dem Zeiger auswählen
MODUS_SLOT = "slot"        # zwei Ecken -> neuer Slot
MODUS_MESSEN = "messen"    # Farbe an der Stelle -> Slot-Hintergrund
MODUS_KLICK = "klick"      # Klickpunkt des gewählten Slots
MODUS_BEREICH = "bereich"  # zwei Ecken -> Bildbereich einschränken
MODUS_FINDEN = "finden"    # ein Klick auf den Hintergrund -> alle Slots
MODI = (MODUS_WAHL, MODUS_FINDEN, MODUS_SLOT, MODUS_MESSEN, MODUS_KLICK,
        MODUS_BEREICH)

ART_SLOT = "slot"
ART_ITEM = "item"
ART_SCAN = "scan"

# Kleiner als das ist kein Slot, sondern ein Verklicker: zwei Klicks fast auf
# dieselbe Stelle. Angelegt wurde so ein Gebilde bisher trotzdem — und war dann
# kaum wieder loszuwerden, weil man es im Bild nicht mehr traf.
MIN_SLOT = 8
# Wie gross ein Slot mindestens sein muss, um ihn ANKLICKEN zu können. Nicht
# dasselbe wie `MIN_SLOT`: kleine Slots gibt es weiterhin (aus einer alten
# Datei, aus getippten Zahlen), und gerade die will man auswählen können, um
# sie zu löschen. Die Trefferfläche wächst, der Slot bleibt, wie er ist.
TREFFER_MIN = 14

# Wie viele Schritte sich der Reiter merkt. Ein Schritt ist ein vollständiger
# Abzug von Slots, Items und Scans — bei einem echten Bestand (56 Slots, 24
# Items) sind das rund 30 KB, also kosten dreissig davon unter einem Megabyte.
# Weiter zurück braucht niemand: was älter ist, holt man sich über „Neu laden"
# vom letzten Speicherstand.
UNDO_TIEFE = 30

class ScanTeil(ScanCaptureMixin):
    """Slots, Items und Item-Scans — der Teil der Brücke, der am Bild hängt.

    Eine Mixin-Klasse und keine eigene Brücke: pywebview legt **ein** Objekt als
    `js_api` aus, also müssen alle Methoden an `StudioBridge` hängen. Getrennte
    Datei bleibt es trotzdem — `bridge.py` ist mit dem Sequenz-Editor voll.

    Alle Methoden geben `scan_daten()` zurück, nie `snapshot()`: der Reiter hat
    seinen eigenen Zustand, und eine Sequenz-Momentaufnahme wäre der falsche
    Gegenstand (s. die Regel zu `ruf()` und `frage()` in `bridge.py`).
    """

    # ------------------------------------------------------------------ Aufbau

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

    @staticmethod
    def _platte_stand() -> dict:
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

    def scan_modus_setzen(self, daten: dict) -> dict:
        """Was ein Klick auf dem Bild bedeutet.

        **Der Rückweg ist die markierte Kachel selbst**: nochmal darauf klicken
        (bzw. den Buchstaben nochmal drücken) führt zurück ins Auswählen —
        dieselbe Regel wie bei der ELSE-Aktion im Sequenz-Editor. Ein Modus, in
        den man nur hinein kommt, ist die Falltür, die es hier nicht geben darf;
        ESC allein zu haben reicht nicht, denn ESC sieht man einem Bild nicht an.

        `MODUS_WAHL` ist davon ausgenommen: er *ist* der Rückweg, ein Umschalten
        auf sich selbst wäre bedeutungslos.
        """
        modus = (daten or {}).get("modus") or MODUS_WAHL
        if modus not in MODI:
            return self._scan_melde(f"Unbekannter Modus '{modus}'.", "err")
        if "fixiert" in (daten or {}):
            self.scan_werkzeug_fixiert = bool((daten or {}).get("fixiert"))
        if (modus == self.scan_modus and modus != MODUS_WAHL
                and "fixiert" not in (daten or {})):
            self._ecke = None
            self._suchbereich = None
            self.scan_modus = MODUS_WAHL
            return self._scan_melde("Zurück zum Auswählen.", "info")
        self.scan_modus = modus
        self._ecke = None
        # Jeder Wechsel fängt die Suche von vorn an: ein Suchbereich von vorhin
        # gehört zu einer Absicht von vorhin.
        self._suchbereich = None
        texte = {
            MODUS_WAHL: "Auswählen: auf einen Slot klicken — daneben klicken "
                        "zieht ein Rechteck um mehrere.",
            MODUS_SLOT: "Neuer Slot: zwei Ecken anklicken.",
            MODUS_MESSEN: "Farbe messen: auf den Slot-Hintergrund klicken.",
            MODUS_KLICK: "Klickpunkt: die Stelle im Slot anklicken.",
            MODUS_BEREICH: "Bereich: zwei Ecken um den Teil, der zählt.",
            MODUS_FINDEN: "Slots finden: zwei Ecken um das Inventar, dann auf "
                          "einen leeren Slot-Hintergrund darin klicken.",
        }
        zurueck = "" if modus == MODUS_WAHL else "  ·  ESC oder nochmal die Kachel = zurück"
        return self._scan_melde(texte[modus] + zurueck, "info")

    def scan_waehlen(self, daten: dict) -> dict:
        """Wählt einen Slot, ein Item oder einen Scan aus."""
        art = (daten or {}).get("art") or ART_SLOT
        name = str((daten or {}).get("name") or "")
        if art not in (ART_SLOT, ART_ITEM, ART_SCAN):
            return self._scan_melde(f"Unbekannte Art '{art}'.", "err")
        self.scan_art, self.scan_name = art, name
        # Eine Zeile in der Liste anzuklicken ist eine EINZEL-Auswahl. Sonst
        # bliebe nach einem Rechteck die alte Menge stehen, und der nächste
        # Druck auf „löschen" nähme dreissig Slots statt des einen, den man
        # gerade angeklickt hat.
        self._auswahl = [name] if art == ART_SLOT and name in self.slots else []
        return self.scan_daten()

    def _gewaehlter_slot(self) -> Optional[ItemSlot]:
        return self.slots.get(self.scan_name) if self.scan_art == ART_SLOT else None

    def _auswahl_slots(self) -> list:
        """Worauf eine Sammel-Aktion wirkt: die Auswahl, sonst der eine Gewählte.

        **Eine Stelle, weil sonst jede Sammel-Aktion ihre eigene Antwort gäbe.**
        Die Regel stand ausgeschrieben in `scan_slot_loeschen` — und Löschen war
        lange die einzige Sammel-Aktion, die es gab. Sobald es mehrere sind,
        muss „was ist gewählt" überall dasselbe heissen; sonst nähme „löschen"
        dreissig Slots und „Grösse angleichen" nur einen.

        Die Reihenfolge des Rechtecks bleibt erhalten (`_auswahl`), damit
        Meldungen und Listen in derselben Folge stehen wie die Auswahl selbst.
        """
        namen = [n for n in self._auswahl if n in self.slots]
        if namen:
            return [self.slots[n] for n in namen]
        slot = self._gewaehlter_slot()
        return [slot] if slot is not None else []

    def scan_klick(self, daten: dict) -> dict:
        """Ein Klick auf dem Bild — was er tut, hängt am Modus.

        Die Koordinaten kommen in **Bildschirm**-Pixeln an; die Umrechnung aus
        der Anzeige macht die Seite, weil nur sie weiss, wie gross das Bild
        gerade dargestellt wird.
        """
        self._scan_laden()
        try:
            x, y = int((daten or {})["x"]), int((daten or {})["y"])
        except (KeyError, TypeError, ValueError):
            return self._scan_melde("Klick ohne Stelle — ignoriert.", "err")

        if self.scan_modus == MODUS_SLOT:
            return self._klick_slot(x, y)
        if self.scan_modus == MODUS_MESSEN:
            return self._klick_messen(x, y)
        if self.scan_modus == MODUS_KLICK:
            return self._klick_klickpunkt(x, y)
        if self.scan_modus == MODUS_BEREICH:
            return self._klick_bereich(x, y)
        if self.scan_modus == MODUS_FINDEN:
            return self._klick_finden(x, y)
        return self._klick_waehlen(x, y, bool((daten or {}).get("zusatz")))

    def _klick_slot(self, x: int, y: int) -> dict:
        """Zwei Ecken ergeben einen Slot — der Weg, den der Nutzer verlangt hat.

        Zwei Klicks statt Ziehen: beim Ziehen verrutscht die Ecke um ein paar
        Pixel, und bei einem Slot von 60 px Kantenlänge schneidet das schon das
        Symbol an. Zwischen den Klicks zeigt die Ansicht das entstehende
        Rechteck.
        """
        if self._ecke is None:
            self._ecke = (x, y)
            return self._scan_melde("Erste Ecke gesetzt — jetzt die zweite.", "info")
        x1, y1, x2, y2 = normalize_region(self._ecke[0], self._ecke[1], x, y)
        self._ecke = None
        # **Ein Slot von 2×2 px ist nie gewollt, sondern ein Doppelklick.** Er
        # entstand trotzdem — und war danach kaum wieder loszuwerden, weil man
        # ihn im Bild nicht mehr traf. Ihn gar nicht erst anzulegen ist die
        # Reparatur, die keine Bedienoberfläche kostet.
        if x2 - x1 < MIN_SLOT or y2 - y1 < MIN_SLOT:
            return self._scan_melde(
                f"Zu klein ({x2 - x1}×{y2 - y1} px, mindestens {MIN_SLOT}) — "
                "nochmal aufziehen.", "warn")

        self._merke("Slot angelegt")
        name = next_slot_name(self.slots)
        # Der Hintergrund wird an der INNEREN Ecke gemessen, nicht in der Mitte:
        # dort liegt das Item. Trifft die Messung daneben (Rahmen, Schatten),
        # korrigiert man sie mit dem Pipetten-Modus — deshalb steht sie in der
        # Meldung.
        farbe = self._foto_farbe(x1 + 2, y1 + 2)
        self.slots[name] = ItemSlot(
            name=name, scan_region=(x1, y1, x2, y2),
            click_pos=((x1 + x2) // 2, (y1 + y2) // 2),
            slot_color=farbe)
        self.scan_art, self.scan_name = ART_SLOT, name
        self._auswahl = [name]
        self._dazu(ART_SLOT, name)
        self._werkzeug_fertig()
        gemessen = f" · Hintergrund {hexfarbe(farbe)}" if farbe else ""
        return self._scan_geaendert(
            f"{name}: {x2 - x1}×{y2 - y1} px{gemessen}")

    def _klick_finden(self, x: int, y: int) -> dict:
        """Erst den Suchbereich aufziehen, dann den Hintergrund zeigen.

        Der Schritt, der im Studio fehlte: ein volles Inventar sind 45 Slots und
        damit 90 Klicks, wenn man jeden einzeln aufzieht. Die Erkennung dafür
        gibt es längst — `erkenne_slots_im_bild()` aus dem Konsolen-Slot-Editor,
        dieselbe Funktion, die auch `repair` benutzt. Zwei Erkennungen wären
        zwei Ergebnisse.

        **Gesucht wird in einem Bereich, nicht im ganzen Bild.** Eine Farbe ist
        kein Ort: liegt neben dem Inventar ein Menü in genau demselben Grau,
        wird es mitgefunden, und heraus kommen zwanzig Slots, von denen acht
        keine sind. Das fiel erst beim Erkennen auf, und dann hat man sie schon
        alle einzeln wegzuräumen. Der Bereich beantwortet dieselbe Frage vorher
        und mit zwei Klicks.

        Die beiden Ecken schränken deshalb nur die **Suche** ein — anders als
        `MODUS_BEREICH`, der das Bild zuschneidet und für jede weitere Aufnahme
        gilt. Das Bild bleibt, wie es ist; nur diese eine Erkennung sieht
        weniger davon.

        Angelegt wird, was nicht schon einen Slot hat: ein zweiter Durchgang
        ergänzt also, statt zu verdoppeln.
        """
        if self._foto is None or self._foto_info is None:
            return self._scan_melde("Erst ein Bild aufnehmen.", "warn")
        if self._suchbereich is None:
            return self._such_ecke(x, y)

        sx1, sy1, sx2, sy2 = self._suchbereich
        if not (sx1 <= x <= sx2 and sy1 <= y <= sy2):
            return self._scan_melde(
                "Die Stelle liegt neben dem Suchbereich — hinein klicken, oder "
                "mit ESC von vorn.", "warn")
        farbe = self._foto_farbe(x, y)
        if farbe is None:
            return self._scan_melde("Dort liegt kein Bild — erst aufnehmen.", "warn")
        if not self._hat_opencv():
            return self._scan_melde(
                "Das Finden braucht OpenCV: pip install opencv-python", "err")
        ausschnitt = self._foto_crop(self._suchbereich)
        if ausschnitt is None:
            return self._scan_melde("Der Suchbereich liegt nicht im Bild.", "warn")

        try:
            rechtecke = self._slots_suchen(ausschnitt, farbe)
        except Exception as fehler:                     # OpenCV/NumPy-Innenleben
            return self._scan_melde(f"Erkennung fehlgeschlagen: {fehler}", "err")
        if not rechtecke:
            return self._scan_melde(
                f"Nichts gefunden zu {hexfarbe(farbe)} — auf eine LEERE Stelle im "
                "Slot klicken, nicht auf ein Item.", "warn")

        self._merke("Slots gesucht")
        ziel = self._bestehende_slot_groesse()
        neu, dazu, schon = 0, 0, 0
        for rx, ry, rb, rh in rechtecke:
            region = self._mit_einzug(
                (sx1 + rx, sy1 + ry, sx1 + rx + rb, sy1 + ry + rh))
            if ziel is not None:
                zb, zh = ziel
                breite, hoehe = region[2] - region[0], region[3] - region[1]
                if abs(breite - zb) <= self._GROESSE_TOLERANZ \
                        and abs(hoehe - zh) <= self._GROESSE_TOLERANZ:
                    region = self._auf_groesse(region, ziel)
            vorhanden = self._slot_an_stelle(region)
            if vorhanden is not None:
                # **Gefunden ist gefunden, auch wenn der Slot schon existiert.**
                # Bei zwei Spielen liegen die Slots des einen längst im Bestand —
                # ein zweiter Scan über demselben Inventar legte deshalb nichts
                # an, nahm aber auch nichts auf, und weil die Listen nur
                # Mitglieder zeigen, blieb er leer: „45 gefunden, alle schon da"
                # und keine einzige Marke im Bild. Wer hier sucht, meint diesen
                # Scan — also gehören die Treffer hinein, angelegt oder nicht.
                if self._dazu(ART_SLOT, vorhanden):
                    dazu += 1
                else:
                    schon += 1
                continue
            name = next_slot_name(self.slots)
            self.slots[name] = ItemSlot(
                name=name, scan_region=region,
                click_pos=((region[0] + region[2]) // 2, (region[1] + region[3]) // 2),
                slot_color=farbe)
            self._dazu(ART_SLOT, name)
            neu += 1
        # Der Durchgang ist vorbei, ob er etwas angelegt hat oder nicht — also
        # endet er auch dann im Auswählen, wenn alles schon dastand. Nur bei
        # Erfolg zurückzuschalten hiesse: derselbe Klick lässt einen mal im
        # Modus stehen und mal nicht, je nach Ergebnis.
        self._suchbereich = None
        self.scan_modus = MODUS_WAHL
        if not neu and not dazu:
            return self._scan_melde(f"{schon} Slot(s) gefunden — alle schon da."
                                    f"{self._gleich_erkennen()}", "info")
        teile = []
        if neu:
            teile.append(f"{neu} Slot(s) angelegt")
        if dazu:
            teile.append(f"{dazu} schon vorhandene in den Scan aufgenommen")
        if schon:
            teile.append(f"{schon} war(en) schon dabei")
        return self._scan_geaendert(f"{', '.join(teile)} · Hintergrund {hexfarbe(farbe)}"
                                    f"{self._einzug_hinweis()}"
                                    f"{self._gleich_erkennen()}")

    def _gleich_erkennen(self) -> str:
        """Prüft die frisch gefundenen Slots sofort gegen den Item-Bestand.

        **Die Frage nach dem Finden ist nicht „habe ich Slots", sondern „was
        davon kenne ich schon".** Ohne diesen Durchgang stehen zwanzig gleich
        aussehende Rechtecke da, und der nächste Schritt — „Items lernen" —
        lernt stumpf alle zwanzig, auch die neunzehn, die längst im Bestand
        liegen. Grün markiert heisst: das hier ist erledigt, kümmere dich um den
        Rest. Stimmt ein Treffer nicht, ändert man ihn rechts oder lernt aus dem
        Slot ein zweites Item — die Markierung ist ein Vorschlag, keine
        Festlegung.

        Kostet an einem vollen Inventar rund 0,3 s (45 Slots gegen 45 Items,
        gemessen) und damit weniger als das Finden selbst. Ohne Items im Bestand
        ist es augenblicklich und sagt gar nichts — dann gibt es nichts zu
        erkennen, und eine Meldung darüber wäre nur Rauschen.
        """
        # Die Slot-Liste ist gerade eine andere geworden — was vorher an einem
        # Slot stand, gehört zu einem anderen Stand. Auch dann wegräumen, wenn
        # gar nicht gerechnet wird: Namen werden wiederverwendet
        # (`next_slot_name` füllt Lücken), ein alter Treffer klebte sonst am
        # neuen Slot.
        self._treffer = {}
        if not self.items:
            return ""
        try:
            gefunden, geprueft, _, fremd, gesamt = self._erkennen_lauf()
        except Exception:            # OpenCV/NumPy-Innenleben — nie den Fund verlieren
            return ""
        if not geprueft:
            return ""
        offen = gesamt - gefunden
        text = f" · davon {gefunden} mit bekanntem Item"
        if offen:
            text += f", {offen} noch unbekannt"
        if fremd:
            text += f" ({fremd} gehören noch nicht zu diesem Scan)"
        return text

    def _such_ecke(self, x: int, y: int) -> dict:
        """Die zwei Ecken um das Inventar — der erste Teil von `finden`."""
        if self._ecke is None:
            self._ecke = (x, y)
            return self._scan_melde(
                "Suchbereich: erste Ecke um das Inventar — jetzt die zweite.", "info")
        x1, y1, x2, y2 = normalize_region(self._ecke[0], self._ecke[1], x, y)
        self._ecke = None
        if x2 - x1 < 8 or y2 - y1 < 8:
            return self._scan_melde("Zu klein — nochmal aufziehen.", "warn")
        self._suchbereich = (x1, y1, x2, y2)
        return self._scan_melde(
            f"Suchbereich {x2 - x1}×{y2 - y1} px — jetzt auf einen LEEREN "
            "Slot-Hintergrund darin klicken.", "info")

    def _mit_einzug(self, region: tuple) -> tuple:
        """Zieht den Slot-Rand um `scan_slot_inset` ein.

        **Dieselbe Rechnung wie im Konsolen-Editor** (`slot_auto_detect` in
        `editors/slot_editor.py`), und sie fehlte hier: die Erkennung liefert
        das Rechteck der ganzen Zelle samt Rahmen und Schatten. Ohne Einzug
        lernt jedes Item den Rahmen als Merkmal mit, und beim Vergleich zählt
        er wie ein Teil des Symbols.

        Nie mehr abziehen, als übrig bleiben darf: bei einer 24-px-Zelle wären
        zweimal 10 px fast nichts mehr. Von Hand aufgezogene Slots bleiben
        unangetastet — dort ist das Rechteck genau das, was gemeint war.
        """
        from ...config import CONFIG
        breite, hoehe = region[2] - region[0], region[3] - region[1]
        einzug = min(max(0, int(CONFIG.scan_slot_inset)),
                     (min(breite, hoehe) - MIN_SLOT) // 2)
        if einzug <= 0:
            return region
        return (region[0] + einzug, region[1] + einzug,
                region[2] - einzug, region[3] - einzug)

    @staticmethod
    def _einzug_hinweis() -> str:
        """Sagt, dass eingezogen wurde — sonst wundert man sich über die Grösse."""
        from ...config import CONFIG
        einzug = max(0, int(CONFIG.scan_slot_inset))
        return f" · Einzug {einzug} px (Einstellungen: scan_slot_inset)" if einzug else ""

    # Enger werdende Bänder für Sättigung und Helligkeit. Der erste Wert ist der
    # des Konsolen-Editors; die engeren braucht es bei dunklen Oberflächen, wo
    # Slot und Panel sich nur um wenige Stufen unterscheiden.
    _SV_STUFEN = (50, 35, 25, 18, 12, 8)

    # Ab wie viel Pixel Abweichung ein neu gefundener Slot NICHT mehr an die
    # Grösse bestehender Slots angeglichen wird (s. `_bestehende_slot_groesse`).
    # Klein gehalten: das soll nur die paar Pixel Median-Drift zwischen zwei
    # Suchdurchgängen auffangen, nicht einen Slot anderer Grösse verbiegen, der
    # aus einem anderen Grund im Scan liegt (z.B. von Hand angelegt).
    _GROESSE_TOLERANZ = 6

    def _slots_suchen(self, bild, farbe: tuple) -> list:
        """Sucht die Slots mit mehreren Toleranzen und nimmt das beste Ergebnis.

        **Eine feste Toleranz reicht nicht.** Gemessen an einem dunklen Inventar:
        mit dem Standardband (±50 auf Sättigung und Helligkeit) verschmelzen
        Slots und Panel zu EINER Fläche, und heraus kommt ein einziges Rechteck
        über dem ganzen Inventar. Wie eng es sein muss, hängt am Kontrast der
        jeweiligen Oberfläche — bei vier gestellten Panel-Farben lag der Umschlag
        bei 35, 25, 18 und 8.

        Statt den Nutzer einen Regler suchen zu lassen, wird gemessen: der
        Durchgang mit den **meisten** Rechtecken gewinnt, und bei Gleichstand das
        weiteste Band (das ist das nachsichtigste). Ein Ergebnis, in dem ein
        Rechteck mehr als die halbe Fläche einnimmt, zählt nicht — das ist nie
        ein Slot, sondern das Panel.
        """
        from ...config import CONFIG
        flaeche = bild.width * bild.height
        bestes: list = []
        for sv in self._SV_STUFEN:
            rechtecke, _ = detect_slots_in_image(
                bild, farbe, CONFIG.scan_slot_hsv_tolerance, sv_tolerance=sv)
            rechtecke = [r for r in rechtecke if r[2] * r[3] * 2 <= flaeche]
            if len(rechtecke) > len(bestes):
                bestes = rechtecke
        return bestes

    def _bestehende_slot_groesse(self) -> Optional[tuple]:
        """Zielgrösse für neu gefundene Slots, wenn schon welche im Scan liegen.

        `erkenne_slots_im_bild()` normalisiert nur INNERHALB eines Suchdurchgangs
        auf den Median — ein zweiter `finden`-Lauf auf demselben Raster (z.B. weil
        beim ersten Mal Items im Weg standen) bekommt seinen eigenen Median und
        weicht dadurch ein paar Pixel vom ersten Durchgang ab, obwohl die Slots im
        Spiel exakt gleich gross sind. Genau diese Differenz liess Templates aus dem
        ersten Durchgang beim zweiten als „passt nicht zur Scan-Region" auffallen.
        Neu gefundene Slots übernehmen deshalb die Grösse, die im Scan schon
        feststeht, statt bei jedem Durchgang neu zu raten.

        **Gefragt wird nur der offene Scan, nie der ganze Bestand.** Zwei
        Bedienflächen desselben Spiels sind nicht gleich gross: an einem echten
        Bestand gemessen hat das Inventar-Raster 64 Hintergrund-Zeilen, die
        Ausrüstungsreihe 61 — dieselben 3 px, die als „Template 62×60, Slot
        62×57" auffielen, und sie sind **richtig**. Der Bestand als Bezug hätte
        die Reihe auf die Höhe des Rasters gezogen und damit ein Template
        erzeugt, das drei Pixel Fremdes mitlernt.

        Ist der offene Scan noch leer, gibt es keinen Bezug — dann bleibt der
        Fund, wie er gemessen wurde. Das kostet nichts: liegt der Slot schon im
        Bestand, wird er ohnehin übernommen statt neu angelegt (`_klick_finden`),
        und eine wirklich neue Fläche hat keinen Vorgänger, dem sie folgen könnte.
        """
        slots = self._scan_slots()
        groessen = [(s.scan_region[2] - s.scan_region[0], s.scan_region[3] - s.scan_region[1])
                    for s in slots if s.scan_region]
        if not groessen:
            return None
        breiten = sorted(g[0] for g in groessen)
        hoehen = sorted(g[1] for g in groessen)
        return breiten[len(breiten) // 2], hoehen[len(hoehen) // 2]

    @staticmethod
    def _auf_groesse(region: tuple, groesse: tuple) -> tuple:
        """Zentriert `region` auf `groesse`, ohne die Mitte zu verschieben."""
        zb, zh = groesse
        cx, cy = (region[0] + region[2]) // 2, (region[1] + region[3]) // 2
        return (cx - zb // 2, cy - zh // 2, cx - zb // 2 + zb, cy - zh // 2 + zh)

    def _slot_an_stelle(self, region: tuple) -> Optional[str]:
        """Der Name des Slots an dieser Stelle, sonst `None`. Mitte zählt.

        Nicht auf Gleichheit prüfen: die Erkennung normalisiert auf die
        Median-Grösse, ein von Hand aufgezogener Slot liegt also fast nie exakt
        gleich — und dann stünden zwei Slots übereinander.

        Gibt den **Namen** zurück und nicht bloss ja/nein: der Suchdurchgang
        nimmt einen schon vorhandenen Slot in den offenen Scan auf, und dafür
        muss er wissen, welcher es ist.
        """
        mx, my = (region[0] + region[2]) // 2, (region[1] + region[3]) // 2
        for s in self.slots.values():
            r = s.scan_region
            if r and r[0] <= mx <= r[2] and r[1] <= my <= r[3]:
                return s.name
        return None

    def _klick_messen(self, x: int, y: int) -> dict:
        slot = self._gewaehlter_slot()
        if slot is None:
            return self._scan_melde("Erst einen Slot wählen.", "warn")
        farbe = self._foto_farbe(x, y)
        if farbe is None:
            return self._scan_melde("Dort liegt kein Bild — erst aufnehmen.", "warn")
        self._merke("Hintergrundfarbe gemessen")
        slot.slot_color = farbe
        self._werkzeug_fertig()
        return self._scan_geaendert(f"{slot.name}: Hintergrund {hexfarbe(farbe)}")

    def _klick_klickpunkt(self, x: int, y: int) -> dict:
        slot = self._gewaehlter_slot()
        if slot is None:
            return self._scan_melde("Erst einen Slot wählen.", "warn")
        self._merke("Klickpunkt gesetzt")
        slot.click_pos = (x, y)
        self._werkzeug_fertig()
        return self._scan_geaendert(f"{slot.name}: Klickpunkt ({x}, {y})")

    def _klick_waehlen(self, x: int, y: int, zusatz: bool = False) -> dict:
        """Den kleinsten Slot unter der Stelle auswählen.

        **Nicht den obersten, sondern den kleinsten** — und das ist der
        Unterschied zwischen „auswählbar" und „für immer da". Ein winziger Slot,
        der versehentlich in einem grossen liegt, war sonst nicht zu treffen: der
        grosse fing jeden Klick ab, und gelöscht wird, was gewählt ist. Der
        kleinste ist ohnehin immer der, den man meint; der grosse bleibt überall
        sonst anklickbar.

        Dazu eine Trefferfläche von mindestens `TREFFER_MIN` px: was zwei Pixel
        gross ist, trifft man auch dann nicht, wenn nichts darüber liegt. Der
        Slot selbst wird davon nicht angefasst — nur, wo man ihn packen kann.

        Bei gleicher Grösse gewinnt weiterhin der zuletzt angelegte: das ist
        der, den man gerade vor sich hat.

        **Daneben klicken zieht ein Auswahl-Rechteck auf.** Ein einzelner Slot
        ist ein Klick; dreissig sind sonst dreissig Klicks und dreissig
        Bestätigungen. Zwei Ecken, alle darin liegenden sind gewählt, und die
        Sammel-Aktion arbeitet auf der Auswahl — dieselbe Regel wie im
        Sequenz-Editor. Mit `zusatz` (STRG) kommt ein einzelner Slot dazu oder
        fällt heraus.
        """
        if self._ecke is not None:
            return self._rahmen_auswahl(x, y)
        gewaehlt = self._slot_unter(x, y)
        if gewaehlt is None:
            # Nichts getroffen: das ist der Anfang eines Rechtecks, nicht
            # „nichts". Aufgehoben wird die Auswahl mit ESC oder mit einem
            # Rechteck, in dem nichts liegt.
            self._ecke = (x, y)
            return self._scan_melde(
                "Auswahl-Rechteck: zweite Ecke — oder ESC.", "info")
        if zusatz:
            return self._auswahl_umschalten(gewaehlt)
        self.scan_art = ART_SLOT
        self.scan_name = gewaehlt
        self._auswahl = [gewaehlt]
        return self.scan_daten()

    def _slot_unter(self, x: int, y: int) -> Optional[str]:
        """Der Name des Slots an dieser Stelle — der KLEINSTE, nicht der oberste.

        Steht als eigene Funktion da, seit es mehr als einen Anlass gibt, sie zu
        stellen: das Auswählen, der ALT-Klick (Farbe messen) und der Doppelklick
        (Klickpunkt). Dreimal ausgeschrieben wären es drei Regeln, die
        auseinanderlaufen — und dann träfe derselbe Zeiger je nach Handgriff
        einen anderen Slot.
        """
        gewaehlt, kleinste = None, None
        for slot in self.slots.values():
            x1, y1, x2, y2 = self._trefferflaeche(slot.scan_region)
            if not (x1 <= x <= x2 and y1 <= y <= y2):
                continue
            flaeche = ((slot.scan_region[2] - slot.scan_region[0]) *
                       (slot.scan_region[3] - slot.scan_region[1]))
            if kleinste is None or flaeche <= kleinste:
                gewaehlt, kleinste = slot.name, flaeche
        return gewaehlt

    def scan_direkt(self, daten: dict) -> dict:
        """Farbe messen bzw. Klickpunkt setzen, OHNE vorher den Modus zu wechseln.

        **Für einen Handgriff erst eine Kachel anzuklicken ist ein Handgriff zu
        viel.** Die Modi bleiben — sie beantworten „was tut ein Klick gerade",
        und beim Aufziehen von zwanzig Slots ist genau das die richtige Frage.
        Aber die beiden Korrekturen, die man *zwischendurch* macht, brauchen
        keinen Modus: sie gelten dem Slot unter dem Zeiger, und den sieht man.

        - `messen` (ALT-Klick): Hintergrundfarbe an genau dieser Stelle.
        - `klick` (Doppelklick): Klickpunkt auf genau diese Stelle.

        Beides wählt den Slot gleich mit aus: man hat ihn ja angefasst, und der
        Inspektor soll danach ihn zeigen und nicht den von vorhin. Trifft der
        Zeiger keinen Slot, passiert nichts — ohne Ziel gäbe es nichts zu setzen.
        """
        try:
            x, y = int((daten or {})["x"]), int((daten or {})["y"])
        except (KeyError, TypeError, ValueError):
            return self._scan_melde("Klick ohne Stelle — ignoriert.", "err")
        was = str((daten or {}).get("was") or "")
        name = self._slot_unter(x, y)
        if name is None:
            return self._scan_melde("Dort liegt kein Slot.", "info")
        self.scan_art, self.scan_name = ART_SLOT, name
        self._auswahl = [name]
        if was == "messen":
            return self._klick_messen(x, y)
        if was == "klick":
            return self._klick_klickpunkt(x, y)
        return self._scan_melde(f"Unbekannter Handgriff '{was}'.", "err")

    def _rahmen_auswahl(self, x: int, y: int) -> dict:
        """Zweite Ecke: alles, was ganz darin liegt, ist gewählt.

        **Ganz darin, nicht angeschnitten.** „Alle, die darin sind" heisst genau
        das; ein Slot, der halb aus dem Rechteck ragt, ist eine Ermessensfrage,
        und Ermessen ist bei einer Sammel-Löschung das Falsche. Wer mehr will,
        zieht grösser — das sieht man beim Ziehen ja.
        """
        x1, y1, x2, y2 = normalize_region(self._ecke[0], self._ecke[1], x, y)
        self._ecke = None
        drin = [s.name for s in self.slots.values()
                if s.scan_region and x1 <= s.scan_region[0] and s.scan_region[2] <= x2
                and y1 <= s.scan_region[1] and s.scan_region[3] <= y2]
        self._auswahl = drin
        self.scan_art = ART_SLOT
        self.scan_name = drin[0] if drin else ""
        if not drin:
            return self._scan_melde("Nichts im Rechteck — Auswahl aufgehoben.", "info")
        return self._scan_melde(f"{len(drin)} Slot(s) gewählt — „löschen“ "
                                "(oder Entf) nimmt alle.", "info")

    def _auswahl_umschalten(self, name: str) -> dict:
        """STRG-Klick: einen Slot zur Auswahl dazu oder heraus."""
        if name in self._auswahl:
            self._auswahl.remove(name)
            if self.scan_name == name:
                self.scan_name = self._auswahl[0] if self._auswahl else ""
        else:
            self._auswahl.append(name)
            self.scan_name = name
        self.scan_art = ART_SLOT
        return self.scan_daten()

    @staticmethod
    def _trefferflaeche(region: tuple) -> tuple:
        """Das Rechteck, mit dem ein Klick verglichen wird — nie unter TREFFER_MIN."""
        x1, y1, x2, y2 = region
        wx = max(0, (TREFFER_MIN - (x2 - x1)) // 2)
        wy = max(0, (TREFFER_MIN - (y2 - y1)) // 2)
        return (x1 - wx, y1 - wy, x2 + wx, y2 + wy)

    def scan_abbrechen(self, daten: Optional[dict] = None) -> dict:
        """ESC: halb gesetzte Ecke und Auswahl verwerfen, zurück ins Auswählen."""
        self._ecke = None
        self._suchbereich = None
        self._auswahl = []
        self._lern_review = []
        self.scan_modus = MODUS_WAHL
        return self.scan_daten()

    # ----------------------------------------------------------------- Slots

    def scan_slot_setzen(self, daten: dict) -> dict:
        """Ein Feld eines Slots setzen — Name, Region, Klickpunkt, Farbe."""
        name = str((daten or {}).get("name") or "")
        feld = str((daten or {}).get("feld") or "")
        wert = (daten or {}).get("wert")
        slot = self.slots.get(name)
        if slot is None:
            return self._scan_melde(f"Slot '{name}' gibt es nicht.", "err")

        # **Gemerkt wird pro Zweig, nicht oben am Eingang.** Ein Feld, das
        # abgelehnt wird oder denselben Wert noch einmal bekommt, legte sonst
        # einen Schritt auf den Stapel, der nichts zurückzunehmen hat — und
        # STRG+Z täte einmal scheinbar gar nichts. Ein Rückgängig, dem man nicht
        # trauen kann, ist kaum besser als keins.
        if feld == "name":
            return self._slot_umbenennen(slot, str(wert or "").strip())
        if feld == "farbe":
            self._merke(f"'{name}': Hintergrundfarbe")
            slot.slot_color = rgbwert(wert)
            return self._scan_geaendert(f"{slot.name}: Hintergrund {wert or 'entfernt'}")
        if feld in ("x1", "y1", "x2", "y2"):
            self._merke(f"'{name}': Fläche")
            werte = list(slot.scan_region)
            werte[("x1", "y1", "x2", "y2").index(feld)] = int(wert or 0)
            slot.scan_region = normalize_region(*werte)
            return self._scan_geaendert()
        if feld in ("kx", "ky"):
            self._merke(f"'{name}': Klickpunkt")
            kx, ky = slot.click_pos
            slot.click_pos = (int(wert or 0), ky) if feld == "kx" else (kx, int(wert or 0))
            return self._scan_geaendert()
        return self._scan_melde(f"Unbekanntes Feld '{feld}'.", "err")

    def _slot_umbenennen(self, slot: ItemSlot, neu: str) -> dict:
        """Umbenennen heisst hier: die Referenz in jedem Scan mitziehen.

        Ein Slot wird **per Name** referenziert — der Name IST die Referenz.
        Ohne das Nachziehen zeigte jeder Scan danach ins Leere, und zwar
        stillschweigend: er liefe mit einem Slot weniger weiter.
        """
        if not neu or neu == slot.name:
            return self.scan_daten()
        if neu in self.slots:
            return self._scan_melde(f"'{neu}' gibt es schon.", "warn")
        self._merke(f"'{slot.name}' umbenannt")
        alt = slot.name
        self.slots = {(neu if k == alt else k): v for k, v in self.slots.items()}
        slot.name = neu
        betroffen = 0
        for cfg in self.scans.values():
            if alt in cfg.slot_names:
                cfg.slot_names = [neu if n == alt else n for n in cfg.slot_names]
                betroffen += 1
        self._objekte_angleichen()
        self.scan_name = neu
        zusatz = f" · in {betroffen} Scan(s) nachgezogen" if betroffen else ""
        return self._scan_geaendert(f"'{alt}' heisst jetzt '{neu}'{zusatz}")

    def scan_slot_loeschen(self, daten: Optional[dict] = None) -> dict:
        """Löscht die gewählten Slots — einen oder die ganze Auswahl.

        **Die Sammel-Aktion arbeitet auf der Auswahl, nicht auf einem Slot** —
        dieselbe Regel wie im Sequenz-Editor. Ein Rechteck um dreissig Slots und
        ein Griff, statt dreissigmal auswählen und löschen.
        """
        namen = [s.name for s in self._auswahl_slots()]
        if not namen:
            return self._scan_melde("Kein Slot gewählt.", "warn")
        self._merke(f"{len(namen)} Slot(s) gelöscht" if len(namen) > 1
                    else f"'{namen[0]}' gelöscht")
        betroffen = set()
        for name in namen:
            del self.slots[name]
            self._treffer.pop(name, None)
            for cfg in self.scans.values():
                if name in cfg.slot_names:
                    betroffen.add(cfg.name)
                    cfg.slot_names = [n for n in cfg.slot_names if n != name]
        self._objekte_angleichen()
        self.scan_name = ""
        self._auswahl = []
        hinweis = f" · aus {len(betroffen)} Scan(s) entfernt" if betroffen else ""
        was = f"'{namen[0]}'" if len(namen) == 1 else f"{len(namen)} Slots"
        return self._scan_geaendert(f"{was} gelöscht{hinweis}", "warn")

    def scan_verschieben(self, daten: dict) -> dict:
        """Schiebt die gewählten Slots um `dx`/`dy` Pixel — Fläche und Klickpunkt.

        **Ein Slot, der drei Pixel daneben liegt, war nur über vier Zahlenfelder
        zu retten** — und bei dreissig Slots gar nicht. Dabei ist genau das der
        Normalfall: das Spielfenster ist umgezogen, die Erkennung sass eine Zeile
        zu hoch, der Rahmen wurde mitgelernt. Mit Pfeiltasten (SHIFT = zehn
        Pixel) und Ziehen im Bild ist es ein Handgriff.

        Der Klickpunkt geht **mit**, statt neu aus der Mitte gerechnet zu
        werden: er ist womöglich bewusst aus der Mitte gesetzt (ein Knopf in der
        Ecke des Slots), und ein Verschieben soll die Fläche verschieben, nicht
        die Einstellung wegwerfen.

        `zaehlt=False` unterdrückt den Rückgängig-Schritt — dafür gibt es genau
        einen Grund: das Ziehen im Bild schickt beim Loslassen EINEN Aufruf mit
        dem Gesamtversatz, aber die Pfeiltaste feuert bei gedrückt gehaltener
        Taste im Dutzend. Ohne das läge nach zwei Sekunden Halten der ganze
        Stapel voll mit Ein-Pixel-Schritten und der Schritt davor wäre draussen.
        """
        try:
            dx, dy = int((daten or {}).get("dx") or 0), int((daten or {}).get("dy") or 0)
        except (TypeError, ValueError):
            return self._scan_melde("Verschieben ohne Weite — ignoriert.", "err")
        if not dx and not dy:
            return self.scan_daten()
        slots = self._auswahl_slots()
        if not slots:
            return self._scan_melde("Kein Slot gewählt.", "warn")
        # Nur der erste Schritt einer Serie kommt auf den Stapel: STRG+Z soll
        # das ganze Verschieben zurücknehmen, nicht dessen letzten Pixel.
        if (daten or {}).get("zaehlt", True):
            self._merke(f"{len(slots)} Slot(s) verschoben" if len(slots) > 1
                        else f"'{slots[0].name}' verschoben")
        for slot in slots:
            x1, y1, x2, y2 = slot.scan_region
            slot.scan_region = (x1 + dx, y1 + dy, x2 + dx, y2 + dy)
            slot.click_pos = (slot.click_pos[0] + dx, slot.click_pos[1] + dy)
        # Die Treffer gehören zu den alten Stellen — an einer verschobenen
        # Fläche liegt womöglich etwas anderes.
        for slot in slots:
            self._treffer.pop(slot.name, None)
        was = f"{len(slots)} Slots" if len(slots) > 1 else f"'{slots[0].name}'"
        return self._scan_geaendert(f"{was} um ({dx:+d}, {dy:+d}) verschoben.")

    def scan_groesse_angleichen(self, daten: Optional[dict] = None) -> dict:
        """Zieht die gewählten Slots auf dieselbe Grösse, um ihre Mitte herum.

        Der Fall dafür ist der von Hand aufgezogene Slot: zwei Klicks treffen
        nie zweimal dieselbe Kantenlänge, und ein Template, das aus einer um
        drei Pixel abweichenden Fläche gelernt wurde, passt beim Vergleich
        nicht mehr sauber. Die Mitte bleibt stehen — sie ist das, was der
        Nutzer gemeint hat; die Kante ist die Ungenauigkeit.

        Bezug ist der **Median** der Auswahl, nicht der grösste oder kleinste:
        ein einzelner Verklicker soll nicht alle anderen verbiegen.
        """
        slots = self._auswahl_slots()
        if len(slots) < 2:
            return self._scan_melde(
                "Dafür braucht es mehrere Slots — im Bild ein Rechteck aufziehen.", "warn")
        breiten = sorted(s.scan_region[2] - s.scan_region[0] for s in slots)
        hoehen = sorted(s.scan_region[3] - s.scan_region[1] for s in slots)
        ziel = (breiten[len(breiten) // 2], hoehen[len(hoehen) // 2])
        self._merke(f"{len(slots)} Slot(s) angeglichen")
        geaendert = 0
        for slot in slots:
            alt = tuple(slot.scan_region)
            neu = self._auf_groesse(alt, ziel)
            if neu != alt:
                slot.scan_region = neu
                self._treffer.pop(slot.name, None)
                geaendert += 1
        return self._scan_geaendert(
            f"{geaendert} von {len(slots)} Slot(s) auf {ziel[0]}×{ziel[1]} px gezogen.")

    def scan_auswahl_farbe(self, daten: Optional[dict] = None) -> dict:
        """Misst den Hintergrund jedes gewählten Slots neu — jeden an sich selbst.

        **Nicht eine Farbe für alle.** Das wäre der naheliegende Griff und der
        falsche: Inventare sind selten gleichmässig ausgeleuchtet, und eine
        gemeinsame Farbe verschöbe die Maske beim Lernen an jedem Slot ein
        bisschen. Gemessen wird an derselben inneren Ecke wie beim Aufziehen
        (`_klick_slot`) — also dort, wo bei einem gefüllten Slot am ehesten
        Hintergrund liegt und nicht das Symbol.
        """
        slots = self._auswahl_slots()
        if not slots:
            return self._scan_melde("Kein Slot gewählt.", "warn")
        if self._foto is None:
            return self._scan_melde("Erst ein Bild aufnehmen.", "warn")
        self._merke(f"Hintergrund von {len(slots)} Slot(s) gemessen")
        gemessen, daneben = 0, 0
        for slot in slots:
            farbe = self._foto_farbe(slot.scan_region[0] + 2, slot.scan_region[1] + 2)
            if farbe is None:
                daneben += 1
                continue
            slot.slot_color = farbe
            gemessen += 1
        rest = f", {daneben} liegen ausserhalb des Bildes" if daneben else ""
        return self._scan_geaendert(f"{gemessen} Hintergrundfarbe(n) gemessen{rest}.")

    def scan_auswahl_lernen(self, daten: Optional[dict] = None) -> dict:
        """Lernt aus jedem gewählten Slot ein Item — wie `scan_items_lernen`,
        nur auf der Auswahl.

        Der Fall, für den es das gibt: nach dem Erkennen stehen fünf Slots
        orange da (nichts erkannt), der Rest grün. Genau die fünf will man
        lernen — „aus ALLEN Slots lernen" liefe stattdessen über alle
        fünfundvierzig und würde vierzig Doppelte prüfen.
        """
        slots = self._auswahl_slots()
        if not slots:
            return self._scan_melde("Kein Slot gewählt.", "warn")
        self._merke(f"aus {len(slots)} Slot(s) gelernt")
        neu, doppelt, leer = 0, 0, 0
        for slot in slots:
            ergebnis = self._lerne_aus_slot(slot, dedup=self._hat_opencv())
            if ergebnis is None:
                leer += 1
            elif ergebnis == "":
                doppelt += 1
            else:
                neu += 1
                self._dazu(ART_ITEM, ergebnis)
        teile = [f"{neu} neu"]
        if doppelt:
            teile.append(f"{doppelt} schon bekannt")
        if leer:
            teile.append(f"{leer} ohne Bild")
        return self._scan_geaendert("Aus der Auswahl gelernt: " + ", ".join(teile))

    def scan_auswahl_mitglied(self, daten: dict) -> dict:
        """Nimmt die gewählten Slots in den offenen Scan — oder heraus.

        Zwischen „einer" (Häkchen) und „alle" (Schieber im Kopf) lag nichts.
        Genau dazwischen liegt aber der Alltag: die Ausrüstungsreihe gehört
        dazu, die Taschenplätze darunter nicht.
        """
        cfg = self.scans.get(self.scan_offen)
        if cfg is None:
            return self._scan_melde("Kein Scan offen.", "warn")
        slots = self._auswahl_slots()
        if not slots:
            return self._scan_melde("Kein Slot gewählt.", "warn")
        dazu = bool((daten or {}).get("wert"))
        self._merke(f"{len(slots)} Slot(s) {'dazu' if dazu else 'raus'}")
        namen = [s.name for s in slots]
        if dazu:
            cfg.slot_names += [n for n in namen if n not in cfg.slot_names]
        else:
            cfg.slot_names = [n for n in cfg.slot_names if n not in namen]
        self._objekte_angleichen()
        return self._scan_geaendert(
            f"{len(namen)} Slot(s) {'in' if dazu else 'aus'} '{cfg.name}' "
            f"{'aufgenommen' if dazu else 'entfernt'} "
            f"— jetzt {len(cfg.slot_names)}.")

    def scan_slot_doppeln(self, daten: Optional[dict] = None) -> dict:
        """Ein Slot neben dem gewählten — der schnellste Weg zu einer Reihe.

        Versetzt um seine eigene Breite plus zwei Pixel: Inventare stehen im
        Raster, und die zweite Zelle liegt fast immer genau dort.
        """
        slot = self._gewaehlter_slot()
        if slot is None:
            return self._scan_melde("Kein Slot gewählt.", "warn")
        self._merke("Slot gedoppelt")
        x1, y1, x2, y2 = slot.scan_region
        versatz = (x2 - x1) + 2
        name = next_slot_name(self.slots)
        self.slots[name] = ItemSlot(
            name=name, scan_region=(x1 + versatz, y1, x2 + versatz, y2),
            click_pos=(slot.click_pos[0] + versatz, slot.click_pos[1]),
            slot_color=slot.slot_color)
        self.scan_name = name
        self._auswahl = [name]
        self._dazu(ART_SLOT, name)
        return self._scan_geaendert(f"{name} neben '{slot.name}' angelegt.")

    # ----------------------------------------------------------------- Items

    def scan_item_lernen(self, daten: Optional[dict] = None) -> dict:
        """Lernt ein Item aus der Region eines Slots: Template + Marker-Farben.

        Genau das, was `execute_item_scan()` beim Auto-Lernen tut — nur mit dem
        Unterschied, dass man hier sieht, was gelernt wurde, und es benennen
        kann.
        """
        name = str((daten or {}).get("slot") or "") or self.scan_name
        slot = self.slots.get(name)
        if slot is None:
            return self._scan_melde("Kein Slot gewählt.", "warn")
        self._merke("Item gelernt")
        gelernt = self._lerne_aus_slot(slot)
        if gelernt is None:
            return self._scan_melde("Kein Bild an dieser Stelle — erst aufnehmen.", "warn")
        self.scan_art, self.scan_name = ART_ITEM, gelernt
        self._dazu(ART_ITEM, gelernt)
        return self._scan_geaendert(f"'{gelernt}' aus '{slot.name}' gelernt.")

    def scan_items_lernen(self, daten: Optional[dict] = None) -> dict:
        """Aus jedem Slot ein Item — Doppelte werden übersprungen.

        Der Weg für ein volles Inventar: einmal drücken statt zwanzigmal. Die
        Doppel-Erkennung braucht OpenCV; ohne sie entstünde aus zwei gleichen
        Slots zweimal dasselbe Item.

        **„Alle" heisst die des offenen Scans** (`_scan_slots()`), nicht den
        ganzen Bestand: bei zwei Spielen lief der Durchgang sonst auch über die
        Slots des anderen. Die liegen ausserhalb des Bildes, es kam also nichts
        dabei heraus — nur eine Meldung, die von „11 ohne Bild" sprach und den
        Verdacht auf den Screenshot lenkte.
        """
        slots = self._scan_slots()
        if not slots:
            return self._scan_melde("Keine Slots vorhanden.", "warn")
        self._merke("Items gelernt")
        neu, doppelt, leer = 0, 0, 0
        for slot in slots:
            ergebnis = self._lerne_aus_slot(slot, dedup=self._hat_opencv())
            if ergebnis is None:
                leer += 1
            elif ergebnis == "":
                doppelt += 1
            else:
                neu += 1
                self._dazu(ART_ITEM, ergebnis)
        teile = [f"{neu} neu"]
        if doppelt:
            teile.append(f"{doppelt} schon bekannt")
        if leer:
            teile.append(f"{leer} ohne Bild")
        return self._scan_geaendert("Gelernt: " + ", ".join(teile))

    def _lerne_aus_slot(self, slot: ItemSlot, dedup: bool = False) -> Optional[str]:
        """Der Name des neuen Items, `""` bei einem Duplikat, `None` ohne Bild."""
        crop = self._foto_crop(slot.scan_region)
        if crop is None:
            return None
        from ..item_editor.markers import (
            _collect_markers_silent, _find_matching_existing_item,
        )
        from ...config import CONFIG
        if dedup and self.items:
            if _find_matching_existing_item(crop, list(self.items.items()),
                                            CONFIG.scan_min_confidence):
                return ""
        name = next_item_name(self.items)
        # Einmal maskieren, beides daraus: Template UND Marker sehen damit
        # genau dieselbe Flaeche als Item an.
        from ...imaging import mit_hintergrund_maske
        maskiert = mit_hintergrund_maske(crop, slot.slot_color)
        marker = _collect_markers_silent(maskiert, slot.slot_color)
        self.items[name] = ItemProfile(
            name=name,
            marker_colors=[tuple(c) for c in marker],
            category=None,
            # Hinter das bisher letzte, nicht `len + 1`: nach dem Löschen eines Items
            # vergäbe das eine Priorität, die es schon gibt — und die Reihenfolge, in
            # der der Scan klickt, wäre an dieser Stelle Zufall.
            priority=max((i.priority for i in self.items.values()), default=0) + 1,
            template=save_template(maskiert, name),
            min_confidence=CONFIG.scan_min_confidence,
        )
        return name

    def scan_lernvorschau(self, daten: Optional[dict] = None) -> dict:
        """Bereitet mehrere Items vor, ohne Bestand oder Templates zu veraendern."""
        scope = str((daten or {}).get("scope") or "alle")
        slots = self._auswahl_slots() if scope == "auswahl" else self._scan_slots()
        if not slots:
            return self._scan_melde("Keine Slots fuer die Lernvorschau.", "warn")
        if self._foto is None:
            return self._scan_melde("Erst einen Screenshot aufnehmen.", "warn")

        from ..item_editor.markers import (
            _find_matching_existing_item, _item_has_compatible_template,
        )
        from ...config import CONFIG
        from ...imaging import mit_hintergrund_maske

        review = []
        vergeben = set(self.items)
        offener_scan = self.scans.get(self.scan_offen)
        scan_items = set(offener_scan.item_names) if offener_scan else set()
        for slot in slots:
            crop = self._foto_crop(slot.scan_region)
            if crop is None:
                continue
            treffer = (_find_matching_existing_item(
                crop, list(self.items.items()), CONFIG.scan_min_confidence)
                if self._hat_opencv() else None)
            kompatibel = bool(
                treffer and _item_has_compatible_template(self.items[treffer], crop))
            variante = treffer if treffer and not kompatibel else ""
            # Ein sicher erkannter Treffer IST das vorhandene Item. Zuvor stand
            # bei einem kompatiblen Treffer oben „Bogen erkannt", im Namensfeld
            # aber „Item 1". Der Platzhalter war nur fuer einen moeglichen
            # manuellen Widerspruch gedacht und bereitete beim Ankreuzen sogar
            # ein Duplikat vor. Der vorhandene Datensatz ist deshalb immer der
            # sichtbare Standard; `neu_name` bleibt nur fuer die ausdrueckliche
            # UI-Aktion „Als anderes Item lernen" erhalten.
            neu_name = next_item_name({n: None for n in vergeben})
            vergeben.add(neu_name)
            if treffer:
                item = self.items[treffer]
                name = treffer
                kategorie = item.category or ""
                prioritaet = item.priority
            else:
                name = neu_name
                kategorie = ""
                prioritaet = 1
            im_scan = bool(treffer and treffer in scan_items)
            kann_hinzufuegen = bool(
                kompatibel and offener_scan is not None and not im_scan)
            maskiert = mit_hintergrund_maske(crop, slot.slot_color)
            review.append({
                "slot": slot.name, "name": name, "kategorie": kategorie,
                "prioritaet": prioritaet,
                "vorhanden": treffer or "", "neu_name": neu_name,
                "duplikat": treffer if kompatibel else "",
                "variante": variante,
                "im_scan": im_scan, "kann_hinzufuegen": kann_hinzufuegen,
                # Das Haekchen beschreibt die gewuenschte Scan-Mitgliedschaft:
                # erkannt = vorausgewaehlt. So kann man ein erkanntes Item
                # bewusst abwaehlen und damit aus genau diesem Scan entfernen.
                "ausgewaehlt": True,
                "bild": self._bild_url(maskiert), "crop": maskiert,
            })
        self._lern_review = review
        if not review:
            return self._scan_melde("Keiner der Slots liegt im Screenshot.", "warn")
        doppelt = sum(bool(z["duplikat"]) for z in review)
        varianten = sum(bool(z["variante"]) for z in review)
        teile = []
        if doppelt:
            teile.append(f"{doppelt} bereits gelernt")
        if varianten:
            teile.append(f"{varianten} neue Grössenvariante(n)")
        zusatz = " - " + ", ".join(teile) if teile else ""
        return self._scan_melde(
            f"{len(review)} Vorschlaege vorbereitet{zusatz}.", "info")

    @staticmethod
    def _bild_url(img) -> str:
        try:
            with io.BytesIO() as stream:
                img.save(stream, format="PNG")
                return "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode("ascii")
        except (OSError, ValueError):
            return ""

    def scan_lernvorschau_abbrechen(self, daten: Optional[dict] = None) -> dict:
        self._lern_review = []
        return self._scan_melde("Lernvorschau verworfen.", "info")

    def _kategorie_normalisieren(self, wert) -> Optional[str]:
        """Verwendet bei gleicher Schreibweise die bereits bekannte Kategorie."""
        neu = str(wert or "").strip()
        if not neu:
            return None
        schluessel = neu.casefold()
        for vorhanden in existing_categories(self.items):
            if vorhanden.casefold() == schluessel:
                return vorhanden
        return neu

    def _prioritaet_einordnen(self, kategorie: Optional[str], wert,
                              ausnehmen: Optional[ItemProfile] = None) -> tuple[int, int]:
        """Wertet die TUI-Sonderzahl 0 aus; liefert (Prioritaet, verschoben)."""
        try:
            prioritaet = int(wert)
        except (TypeError, ValueError):
            prioritaet = 1
        if prioritaet != 0:
            return max(1, prioritaet), 0
        if not kategorie:
            return 1, 0

        verschoben = 0
        for item in self.items.values():
            if item is not ausnehmen and item.category == kategorie:
                item.priority = max(1, int(item.priority)) + 1
                verschoben += 1
        return 1, verschoben

    def scan_lernvorschau_uebernehmen(self, daten: Optional[dict] = None) -> dict:
        """Uebernimmt Items und die gewuenschte Mitgliedschaft im offenen Scan."""
        eingaben = (daten or {}).get("zeilen") or []
        by_slot = {str(z.get("slot") or ""): z for z in eingaben if isinstance(z, dict)}

        def ist_ausgewaehlt(zeile: dict) -> bool:
            eingabe = by_slot.get(zeile["slot"], {})
            return bool(eingabe.get("ausgewaehlt", zeile["ausgewaehlt"]))

        # Ein vorhandenes Item kann in mehreren Slots erkannt werden. Diese
        # Zeilen meinen dieselbe Scan-Mitgliedschaft; sobald eine davon markiert
        # ist, bleibt das Item enthalten. Die Oberfläche hält die Häkchen
        # zusätzlich synchron, diese ODER-Regel schützt aber auch alte Clients.
        mitgliedschaft = {}
        for zeile in self._lern_review:
            eingabe = by_slot.get(zeile["slot"], {})
            vorhanden = str(zeile.get("vorhanden") or "")
            if vorhanden and not bool(eingabe.get("als_anders", False)):
                mitgliedschaft[vorhanden] = (
                    mitgliedschaft.get(vorhanden, False) or ist_ausgewaehlt(zeile))

        cfg = self.scans.get(self.scan_offen)
        zu_entfernen = [
            name for name, behalten in mitgliedschaft.items()
            if not behalten and cfg is not None and name in cfg.item_names
        ]
        ausgewaehlt = [
            zeile for zeile in self._lern_review if ist_ausgewaehlt(zeile)
        ]
        if not ausgewaehlt and not zu_entfernen:
            self._lern_review = []
            return self._scan_melde(
                "Keine Items ausgewählt; am Scan wurde nichts geändert.", "info")

        from ..item_editor.markers import _collect_markers_silent
        from ...config import CONFIG
        self._merke("Item-Auswahl der Lernvorschau uebernommen")
        neu = []
        varianten = []
        unveraendert = set()
        hinzugefuegt = []
        entfernt = []
        bearbeitet = []
        metadaten_gesetzt = set()

        # Zuerst wird der Zustand der erkannten Items angewendet. Abwählen
        # löscht nicht das globale Item oder seine Vorlagen, sondern nur dessen
        # Namen aus dem aktuell geöffneten Scan.
        if cfg is not None:
            for name, behalten in mitgliedschaft.items():
                if behalten:
                    if self._dazu(ART_ITEM, name):
                        hinzugefuegt.append(name)
                elif name in cfg.item_names:
                    cfg.item_names = [n for n in cfg.item_names if n != name]
                    entfernt.append(name)
            if entfernt:
                self._objekte_angleichen()

        vergeben = set(self.items)
        for zeile in ausgewaehlt:
            eingabe = by_slot.get(zeile["slot"], {})
            als_anders = bool(eingabe.get("als_anders", False))
            erkannter_name = str(zeile.get("vorhanden") or "")
            if erkannter_name and not als_anders:
                # Der Name ist die Identität des erkannten Items. Geändert wird
                # er nur über die ausdrückliche Aktion „Als anderes Item lernen“.
                basis = erkannter_name
            else:
                basis = (str(eingabe.get("name") or zeile["name"]).strip()
                         or zeile["name"])
            slot = self.slots.get(zeile["slot"])
            if slot is None:
                continue
            crop = zeile["crop"]
            # Ein bereits vorhandener Name bedeutet bewusst: dieses Bild ist
            # dasselbe Item in einem anderen Slot-Typ. Seine sichtbaren Daten
            # können bearbeitet werden; bei Bedarf kommt eine Bildvariante hinzu.
            vorhanden = self.items.get(basis)
            if vorhanden is not None:
                # Bei einem regulär erkannten Treffer stammen die sichtbaren
                # Werte aus genau diesem Profil und dürfen direkt bearbeitet
                # werden. Bei „anderes Item“ kann ein fremder vorhandener Name
                # gewählt werden; dessen Metadaten werden nicht mit den leeren
                # Standardfeldern überschrieben.
                if erkannter_name and not als_anders and basis not in metadaten_gesetzt:
                    vorher = (vorhanden.category, vorhanden.priority)
                    kategorie = self._kategorie_normalisieren(
                        eingabe.get("kategorie", zeile["kategorie"]))
                    prioritaet, verschoben = self._prioritaet_einordnen(
                        kategorie,
                        eingabe.get("prioritaet", zeile["prioritaet"]),
                        ausnehmen=vorhanden,
                    )
                    vorhanden.category = kategorie
                    vorhanden.priority = prioritaet
                    metadaten_gesetzt.add(basis)
                    if vorher != (kategorie, prioritaet) or verschoben:
                        bearbeitet.append(basis)

                from ..item_editor.markers import _item_has_compatible_template
                if _item_has_compatible_template(vorhanden, crop):
                    if self._dazu(ART_ITEM, basis) and basis not in hinzugefuegt:
                        hinzugefuegt.append(basis)
                    elif basis not in hinzugefuegt and basis not in bearbeitet:
                        unveraendert.add(basis)
                    continue
                datei = save_template(crop, basis)
                if datei:
                    if vorhanden.template:
                        vorhanden.template_variants.append(datei)
                    else:
                        vorhanden.template = datei
                    if basis not in varianten:
                        varianten.append(basis)
                    if self._dazu(ART_ITEM, basis) and basis not in hinzugefuegt:
                        hinzugefuegt.append(basis)
                continue

            name = eindeutiger_name(basis, vergeben)
            vergeben.add(name)
            marker = _collect_markers_silent(crop, slot.slot_color)
            kategorie = self._kategorie_normalisieren(eingabe.get("kategorie"))
            prioritaet, _ = self._prioritaet_einordnen(
                kategorie, eingabe.get("prioritaet", zeile["prioritaet"]))
            self.items[name] = ItemProfile(
                name=name, marker_colors=[tuple(c) for c in marker],
                category=kategorie, priority=prioritaet,
                template=save_template(crop, name),
                min_confidence=CONFIG.scan_min_confidence,
            )
            self._dazu(ART_ITEM, name)
            neu.append(name)
        self._lern_review = []
        gewaehlt = neu + varianten + hinzugefuegt
        if gewaehlt:
            self.scan_art, self.scan_name = ART_ITEM, gewaehlt[0]
        teile = []
        if neu:
            teile.append(f"{len(neu)} neue Item(s)")
        if varianten:
            teile.append(f"{len(varianten)} Grössenvariante(n) ergänzt")
        if hinzugefuegt:
            teile.append(f"{len(hinzugefuegt)} bestehende Item(s) zum Scan hinzugefügt")
        if entfernt:
            teile.append(f"{len(entfernt)} Item(s) aus dem Scan entfernt")
        if bearbeitet:
            teile.append(f"{len(bearbeitet)} bestehende Item(s) bearbeitet")
        if unveraendert:
            teile.append(f"{len(unveraendert)} bereits vollständig eingerichtet")
        text = ", ".join(teile) + "." if teile else "Keine Änderungen."
        return self._scan_geaendert(text)

    def scan_item_setzen(self, daten: dict) -> dict:
        """Ein Feld eines Items — Name, Kategorie, Priorität, Konfidenz."""
        name = str((daten or {}).get("name") or "")
        feld = str((daten or {}).get("feld") or "")
        wert = (daten or {}).get("wert")
        item = self.items.get(name)
        if item is None:
            return self._scan_melde(f"Item '{name}' gibt es nicht.", "err")

        if feld == "name":
            return self._item_umbenennen(item, str(wert or "").strip())
        if feld == "kategorie":
            self._merke(f"'{name}': Kategorie")
            item.category = self._kategorie_normalisieren(wert)
            return self._scan_geaendert()
        if feld == "prioritaet":
            self._merke(f"'{name}': Priorität")
            item.priority, verschoben = self._prioritaet_einordnen(
                item.category, wert, ausnehmen=item)
            try:
                nach_vorn = int(wert) == 0
            except (TypeError, ValueError):
                nach_vorn = False
            if nach_vorn and not item.category:
                return self._scan_geaendert(
                    f"{name}: Priorität 1. Für 'ganz nach vorn' erst eine Kategorie wählen.",
                    "warn")
            zusatz = (f"; {verschoben} andere Item(s) in '{item.category}' nach hinten gerückt"
                      if verschoben else "")
            return self._scan_geaendert(f"{name}: Priorität {item.priority}{zusatz}.")
        if feld == "konfidenz":
            self._merke(f"'{name}': Konfidenz")
            item.min_confidence = max(0.0, min(1.0, float(wert or 0)))
            return self._scan_geaendert()
        return self._scan_melde(f"Unbekanntes Feld '{feld}'.", "err")

    def _item_umbenennen(self, item: ItemProfile, neu: str) -> dict:
        """Wie beim Slot: der Name ist die Referenz, also ziehen die Scans mit."""
        if not neu or neu == item.name:
            return self.scan_daten()
        if neu in self.items:
            return self._scan_melde(f"'{neu}' gibt es schon.", "warn")
        self._merke(f"'{item.name}' umbenannt")
        alt = item.name
        self.items = {(neu if k == alt else k): v for k, v in self.items.items()}
        item.name = neu
        betroffen = 0
        for cfg in self.scans.values():
            if alt in cfg.item_names:
                cfg.item_names = [neu if n == alt else n for n in cfg.item_names]
                betroffen += 1
        self._objekte_angleichen()
        self.scan_name = neu
        zusatz = f" · in {betroffen} Scan(s) nachgezogen" if betroffen else ""
        return self._scan_geaendert(f"'{alt}' heisst jetzt '{neu}'{zusatz}")

    def scan_item_loeschen(self, daten: Optional[dict] = None) -> dict:
        name = self.scan_name if self.scan_art == ART_ITEM else ""
        item = self.items.get(name)
        if item is None:
            return self._scan_melde("Kein Item gewählt.", "warn")
        self._merke(f"'{name}' gelöscht")
        del self.items[name]
        for cfg in self.scans.values():
            cfg.item_names = [n for n in cfg.item_names if n != name]
        self._objekte_angleichen()
        self.scan_name = ""
        # Das Template bleibt liegen: es kann zu einem Boss gehören (beide
        # teilen sich items/templates/), und eine Datei zu löschen, die einem
        # anderen gehört, ist der stille Datenverlust, den es hier nicht gibt.
        return self._scan_geaendert(f"'{name}' gelöscht.", "warn")

    # ------------------------------------------------------------- Erkennung

    def scan_erkennen(self, daten: Optional[dict] = None) -> dict:
        """Was steckt gerade in welchem Slot? — mit der Rechnung der Laufzeit.

        Der Punkt der ganzen Ansicht: statt einen Scan zu starten und am
        Ergebnis zu raten, steht an jedem Slot, welches Item dort erkannt wurde
        und woran es lag. Gerechnet wird auf dem eingefrorenen Screenshot,
        gefragt wird `_check_profile_match()` — dieselbe Funktion, die im Lauf
        entscheidet.
        """
        self._scan_laden()
        if self._foto is None:
            return self._scan_melde("Erst einen Screenshot aufnehmen.", "warn")
        if not self._scan_slots():
            return self._scan_melde("Keine Slots vorhanden.", "warn")
        gefunden, geprueft, toleranz, _, gesamt = self._erkennen_lauf()
        return self._scan_melde(
            f"{gefunden} von {gesamt} Slot(s) erkannt "
            f"(Toleranz {toleranz}, {geprueft} Item(s) geprüft).")

    def scan_treffer_uebernehmen(self, daten: Optional[dict] = None) -> dict:
        """Nimmt alle erkannten, aber scan-fremden Items gesammelt auf."""
        cfg = self.scans.get(self.scan_offen)
        if cfg is None:
            return self._scan_melde("Erst einen Item-Scan oeffnen.", "warn")
        namen = []
        for treffer in self._treffer.values():
            name = treffer.get("name")
            if name and treffer.get("fremd") and name not in namen:
                namen.append(name)
        if not namen:
            return self._scan_melde("Keine sicheren fremden Treffer vorhanden.", "info")
        self._merke(f"{len(namen)} erkannte Items aufgenommen")
        for name in namen:
            self._dazu(ART_ITEM, name)
        for treffer in self._treffer.values():
            if treffer.get("name") in namen:
                treffer["fremd"] = False
        return self._scan_geaendert(f"{len(namen)} erkannte Item(s) hinzugefuegt.")

    def _erkennen_lauf(self) -> tuple:
        """Füllt `_treffer`; liefert `(gefunden, geprüft, Toleranz, fremd, gesamt)`.

        Getrennt von `scan_erkennen()`, weil es zwei Anlässe gibt und nur einer
        davon eine eigene Meldung schreibt: der Knopf sagt das Ergebnis, das
        Finden hängt es an seine eigene Meldung an. Die **Rechnung** darf es
        deshalb nur einmal geben — zwei Erkennungen wären zwei Ergebnisse, und
        genau das vermeidet der Reiter an jeder anderen Stelle auch.

        `fremd` zählt Treffer, die nicht zum offenen Scan gehören. Das kann nur
        bei einem Scan **ohne** Items passieren (dann prüft `_kandidaten()` den
        ganzen Bestand) — und dort ist es die nützlichste Auskunft überhaupt:
        das Item kennst du schon aus einem anderen Spiel, es fehlt nur das
        Häkchen.

        `gesamt` ist die Zahl der geprüften **Slots** — die des offenen Scans,
        nicht die des Bestands. Vorher stand als Nenner die Bestandsgrösse da
        („13 von 56 erkannt"), obwohl elf davon zu einem anderen Spiel gehören
        und gar nicht im Bild liegen.
        """
        # Erst hier importiert: `runtime/__init__` zieht den Worker samt
        # `winapi` nach, und den braucht der Rest des Fensters nicht.
        from ...runtime.item_scan import _check_profile_match
        from ...config import CONFIG

        toleranz = self._toleranz()
        kandidaten = self._kandidaten()
        stellvertreter = _NurConfig(CONFIG)
        cfg = self.scans.get(self.scan_offen)
        dabei = set(cfg.item_names) if cfg else set()
        self._treffer = {}
        gefunden, fremd = 0, 0
        slots = self._scan_slots()
        for slot in slots:
            crop = self._foto_crop(slot.scan_region)
            if crop is None:
                self._treffer[slot.name] = {"name": None, "grund": "ausserhalb des Bildes"}
                continue
            treffer = None
            for item in kandidaten:
                if _check_profile_match(item, crop, toleranz, stellvertreter, False):
                    treffer = item
                    break
            if treffer is None:
                self._treffer[slot.name] = {"name": None, "grund": "nichts erkannt"}
            else:
                gefunden += 1
                if cfg is not None and treffer.name not in dabei:
                    fremd += 1
                self._treffer[slot.name] = {
                    "name": treffer.name,
                    "farbe": hexfarbe(treffer.marker_colors[0]) if treffer.marker_colors else None,
                    "fremd": cfg is not None and treffer.name not in dabei,
                }
        return gefunden, len(kandidaten), toleranz, fremd, len(slots)

    def _kandidaten(self) -> list:
        """Welche Items geprüft werden — die des gewählten Scans, sonst alle.

        Ist ein Scan offen, ist genau seine Liste die interessante: sie
        beantwortet die Frage „findet DIESER Scan, was er finden soll?". Ohne
        Scan wird alles geprüft, sonst sähe man bei leerer Auswahl nichts.
        """
        cfg = self.scans.get(self.scan_offen)
        if cfg is not None and cfg.item_names:
            gewaehlt = [self.items[n] for n in cfg.item_names if n in self.items]
            if gewaehlt:
                return sorted(gewaehlt, key=lambda i: i.priority)
        return sorted(self.items.values(), key=lambda i: i.priority)

    def _toleranz(self) -> int:
        cfg = self.scans.get(self.scan_offen)
        if cfg is not None:
            return cfg.color_tolerance
        return ItemScanConfig(name="").color_tolerance

    # -------------------------------------------------------- Scan-Konfigs

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


class _NurConfig:
    """Ein `state`-Stellvertreter mit nichts als der Config.

    `_check_profile_match()` will einen `AutoClickerState`, benutzt davon aber
    ausschliesslich `state.config`. Diesen Prozess einen echten State bauen zu
    lassen hiesse, den halben Hauptprozess mitzuziehen — für drei
    Config-Werte.
    """

    def __init__(self, config):
        self.config = config
