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
import io
import time
from pathlib import Path
from typing import Optional

from ...models import ItemProfile, ItemScanConfig, ItemSlot
from ...persistence.paths import (
    ITEMS_FILE, SCAN_SHOTS_DIR, SLOTS_FILE, TEMPLATES_DIR,
)
from ...utils import eindeutiger_name, sanitize_filename
from .model import hexfarbe, rgbwert
from .scan_model import (
    crop_region, existing_categories, load_items, load_slots, next_item_name,
    next_slot_name, normalize_region, save_items, save_slots, save_template,
)

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

# Breiter als das wird das Bild für die Anzeige nicht geschickt. Ein virtueller
# Desktop aus drei Monitoren ist schnell 5760 px breit; als PNG sind das
# mehrere MB, die durch die JS-Brücke müssten. Gemessen wird ohnehin im
# Originalbild, die Verkleinerung kostet also keine Genauigkeit.
FOTO_MAX_BREITE = 2400


class ScanTeil:
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
        # Welcher Teil des Bildschirms aufgenommen wird. None = alles. Nicht in
        # der Scan-Datei, sondern IM gemerkten Bild: dessen Ursprung und Grösse
        # SIND der Bereich, und zwei Stellen für dieselbe Angabe liefen
        # auseinander.
        self.scan_bereich: Optional[tuple] = None
        self.scan_modus: str = MODUS_WAHL
        self.scan_art: str = ART_SLOT
        self.scan_name: str = ""
        # Der offene Item-Scan ist der ZUSAMMENHANG, nicht die Auswahl: wer
        # einen Slot anklickt, um ihn zu bearbeiten, arbeitet weiter an
        # demselben Scan. Vorher hing beides an `scan_art`/`scan_name`, und ein
        # Klick auf einen Slot verlor den Zusammenhang.
        self.scan_offen: str = ""
        # Zeigen die Listen nur, was zum offenen Scan gehört? Mit mehreren
        # Spielen liegen sonst alle Items aller Spiele untereinander.
        self.nur_dabei: bool = True
        self._treffer: dict = {}               # Slot-Name -> Erkennungsergebnis
        self._scan_dirty = False
        self._scan_status = ("", "info")
        self._vorschau: dict = {}              # Template-Datei -> (mtime, data-URL)

    def _scan_laden(self) -> None:
        """Slots, Items und Scan-Konfigurationen von Platte — einmal je Sitzung.

        Nicht im Konstruktor: wer das Studio für eine Sequenz aufmacht, soll
        nicht auf das Lesen von Dateien warten, die er vielleicht nie ansieht.
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

    def _dazu(self, art: str, name: str) -> None:
        """Nimmt einen frisch angelegten Slot bzw. ein Item in den offenen Scan.

        **Wer in einem offenen Scan etwas anlegt, legt es FÜR ihn an.** Ohne das
        war der neue Slot sofort wieder weg: die Listen zeigen standardmässig nur
        die Mitglieder, und ein gerade aufgezogener Slot war keines. Man musste
        den Filter ausschalten, ihn suchen und ein Häkchen setzen — für etwas,
        das man erkennbar gerade für diesen Scan gemacht hat.

        Ohne offenen Scan passiert nichts; dann arbeitet man am Bestand.
        """
        cfg = self.scans.get(self.scan_offen)
        if cfg is None:
            return
        namen = cfg.slot_names if art == ART_SLOT else cfg.item_names
        if name not in namen:
            namen.append(name)
            self._objekte_angleichen()

    def _scan_melde(self, text: str, art: str = "ok") -> dict:
        self._scan_status = (text, art)
        return self.scan_daten()

    def _scan_geaendert(self, text: str = "", art: str = "ok") -> dict:
        self._scan_dirty = True
        return self._scan_melde(text, art) if text else self.scan_daten()

    # --------------------------------------------------------------- Das Bild

    def scan_foto(self, daten: Optional[dict] = None) -> dict:
        """Nimmt einen Screenshot auf und legt ihn unter das Raster.

        Der eingefrorene Bildschirm ist die Arbeitsfläche: Slots zieht man dort
        auf, wo sie im Spiel liegen, statt Koordinaten zu tippen.

        **Vollbild ist die Voreinstellung, nicht die einzige Möglichkeit.**
        Aufgenommen wird der ganze virtuelle Desktop, damit auch ein Fenster auf
        dem zweiten Monitor dazugehört — aber wer dasselbe Spiel dreimal offen
        hat, arbeitet auf einem Bild, in dem drei Viertel stören. `bereich`
        schränkt die Aufnahme ein; ohne Angabe gilt der zuletzt gesetzte Bereich
        des Scans, und der überlebt das Schliessen (er steht im gemerkten Bild).
        """
        self._scan_laden()
        try:
            from ...imaging import PILLOW_AVAILABLE, take_screenshot
            from ...winapi import get_virtual_origin
        except ImportError:
            return self._scan_melde("Bildmodule fehlen — kein Screenshot möglich.", "err")
        if not PILLOW_AVAILABLE:
            return self._scan_melde("Ohne Pillow gibt es kein Bild: pip install pillow", "err")

        bereich = self._bereich_aus(daten) if daten else None
        if bereich is None:
            bereich = self.scan_bereich

        bild = take_screenshot(bereich) if bereich else take_screenshot()
        if bild is None:
            return self._scan_melde("Screenshot fehlgeschlagen.", "err")

        links, oben = (bereich[0], bereich[1]) if bereich else get_virtual_origin()
        self.scan_bereich = bereich
        self._foto = bild
        self._foto_merken(bild, links, oben)
        self._anzeigebild(links, oben, time.time())
        # Ein alter Treffer gehört zu einem alten Bild.
        self._treffer = {}
        wo = "Bereich" if bereich else "Vollbild"
        return self._scan_melde(f"{wo}: {bild.width}×{bild.height} px "
                                f"ab ({links}, {oben}).{self._draussen_hinweis()}")

    @staticmethod
    def _bereich_aus(daten: dict) -> Optional[tuple]:
        """Liest `bereich` aus einer Anfrage — vier Zahlen oder nichts."""
        roh = (daten or {}).get("bereich")
        if not roh or len(roh) != 4:
            return None
        try:
            x1, y1, x2, y2 = (int(w) for w in roh)
        except (TypeError, ValueError):
            return None
        x1, y1, x2, y2 = normalize_region(x1, y1, x2, y2)
        return (x1, y1, x2, y2) if x2 - x1 >= 8 and y2 - y1 >= 8 else None

    def _draussen_hinweis(self) -> str:
        """Sagt, wie viele Slots des offenen Scans neben dem Bild liegen.

        Ohne das ist ein zu eng gesetzter Bereich still: die Slots stehen weiter
        in der Liste, sind aber im Bild nicht zu sehen, und man sucht den Fehler
        bei der Erkennung statt beim Ausschnitt.
        """
        if self._foto_info is None:
            return ""
        f = self._foto_info
        rand = (f["links"], f["oben"],
                f["links"] + round(f["breite"] / f["skala"]),
                f["oben"] + round(f["hoehe"] / f["skala"]))
        draussen = [s for s in self._flaechen_slots() if s.scan_region
                    and not (rand[0] <= s.scan_region[0] and s.scan_region[2] <= rand[2]
                             and rand[1] <= s.scan_region[1] and s.scan_region[3] <= rand[3])]
        return f" {len(draussen)} Slot(s) liegen ausserhalb." if draussen else ""

    def scan_bereich_setzen(self, daten: Optional[dict] = None) -> dict:
        """Setzt den Aufnahmebereich und nimmt ihn gleich auf.

        Ohne `bereich` heisst es Vollbild — der Rückweg, ohne den ein einmal
        eingeschränkter Scan nie wieder das Ganze sähe.
        """
        self._scan_laden()
        self.scan_bereich = self._bereich_aus(daten or {})
        return self.scan_foto()

    def scan_fenster(self, daten: Optional[dict] = None) -> list:
        """Die offenen Fenster mit ihrer Lage — zur Auswahl des Bereichs.

        Der Fall, für den es das gibt: dasselbe Programm mehrmals offen. Der
        Titel ist dann dreimal derselbe, unterscheidbar sind sie nur an der
        Lage — die steht deshalb mit dabei und die Liste ist danach sortiert.

        `frage()` und nicht `ruf()`: es ändert nichts, es beantwortet nur etwas.
        """
        try:
            from ...winapi import liste_fenster
        except ImportError:
            return []
        return [{"titel": titel, "bereich": list(rechteck)}
                for titel, rechteck in liste_fenster()]

    def _klick_bereich(self, x: int, y: int) -> dict:
        """Zwei Ecken schränken das Bild ein — zugeschnitten, nicht neu geholt.

        Neu aufzunehmen wäre das Naheliegende und wäre falsch: zwischen den
        beiden Klicks vergeht Zeit, und was man zugeschnitten hat, soll man auch
        bekommen. Der Bereich wird gemerkt, die nächste Aufnahme holt genau ihn.
        """
        if self._foto is None or self._foto_info is None:
            return self._scan_melde("Erst ein Bild aufnehmen.", "warn")
        if self._ecke is None:
            self._ecke = (x, y)
            return self._scan_melde("Erste Ecke des Bereichs — jetzt die zweite.", "info")
        x1, y1, x2, y2 = normalize_region(self._ecke[0], self._ecke[1], x, y)
        self._ecke = None
        if x2 - x1 < 8 or y2 - y1 < 8:
            return self._scan_melde("Zu klein — nochmal aufziehen.", "warn")

        ausschnitt = crop_region(self._foto, (x1, y1, x2, y2),
                                 int(self._foto_info["links"]), int(self._foto_info["oben"]))
        if ausschnitt is None:
            return self._scan_melde("Der Bereich liegt nicht im Bild.", "warn")
        self.scan_bereich = (x1, y1, x2, y2)
        self._foto = ausschnitt
        self._foto_merken(ausschnitt, x1, y1)
        self._anzeigebild(x1, y1, time.time())
        self._treffer = {}
        return self._scan_melde(f"Bereich: {x2 - x1}×{y2 - y1} px ab ({x1}, {y1})."
                                f"{self._draussen_hinweis()}")

    @staticmethod
    def _foto_pfad(scan: str) -> Path:
        return Path(SCAN_SHOTS_DIR) / f"{sanitize_filename(scan)}.png"

    def _foto_merken(self, bild, links: int, oben: int) -> None:
        """Legt den Screenshot beim offenen Scan ab — für das nächste Öffnen.

        **Der Ursprung des virtuellen Desktops steht IM PNG** (Text-Chunk), nicht
        in einer Datei daneben. Zwei Dateien, die zusammengehören, laufen
        irgendwann auseinander: eine gelöschte, eine überschriebene, und die
        Koordinaten sind still um einen Monitor verschoben. Im Bild selbst kann
        das nicht passieren.

        Ohne offenen Scan wird nichts abgelegt: das Bild gehört zu einem Spiel,
        und welches gemeint ist, sagt der Scan.
        """
        if not self.scan_offen:
            return
        try:
            from PIL import PngImagePlugin
            info = PngImagePlugin.PngInfo()
            info.add_text("links", str(int(links)))
            info.add_text("oben", str(int(oben)))
            pfad = self._foto_pfad(self.scan_offen)
            pfad.parent.mkdir(parents=True, exist_ok=True)
            bild.save(pfad, "PNG", pnginfo=info)
        except (ImportError, OSError, ValueError):
            pass      # ein fehlendes Erinnerungsbild ist kein Grund, den Reiter zu stören

    def _foto_laden(self, scan: str) -> bool:
        """Holt den zuletzt abgelegten Screenshot dieses Scans zurück."""
        pfad = self._foto_pfad(scan)
        try:
            from PIL import Image
            bild = Image.open(pfad)
            bild.load()
        except (ImportError, OSError, ValueError):
            self._foto = None
            self._foto_bild = ""
            self._foto_info = None
            self.scan_bereich = None
            return False
        text = getattr(bild, "text", {}) or {}
        try:
            links, oben = int(text.get("links", 0)), int(text.get("oben", 0))
        except (TypeError, ValueError):
            links, oben = 0, 0
        self._foto = bild.convert("RGB")
        # Ursprung und Grösse des gemerkten Bildes SIND der Bereich — deshalb
        # steht er nirgends sonst. Deckt er den ganzen Desktop ab, ist es kein
        # Bereich, sondern Vollbild; sonst sagte die Anzeige „Bereich" für etwas,
        # das keine Einschränkung ist.
        self.scan_bereich = self._bereich_oder_vollbild(
            (links, oben, links + bild.width, oben + bild.height))
        self._anzeigebild(links, oben, pfad.stat().st_mtime)
        self._treffer = {}
        return True

    @staticmethod
    def _bereich_oder_vollbild(rechteck: tuple) -> Optional[tuple]:
        """None, wenn das Rechteck der ganze virtuelle Desktop ist."""
        try:
            from ...winapi import get_virtual_desktop
        except ImportError:
            return rechteck
        schirm = get_virtual_desktop()
        return None if schirm and tuple(schirm) == tuple(rechteck) else rechteck

    def _anzeigebild(self, links: int, oben: int, stand: float) -> None:
        """Verkleinert das Original für die Übertragung und merkt die Geometrie."""
        bild = self._foto
        skala = min(1.0, FOTO_MAX_BREITE / bild.width) if bild.width else 1.0
        anzeige = bild if skala >= 1.0 else bild.resize(
            (max(1, int(bild.width * skala)), max(1, int(bild.height * skala))))
        self._foto_bild = _als_datenurl(anzeige, "PNG")
        self._foto_info = {
            "links": links, "oben": oben,
            "breite": anzeige.width, "hoehe": anzeige.height,
            "skala": round(anzeige.width / bild.width, 6) if bild.width else 1.0,
            "stand": stand,
        }

    def scan_bild(self, daten: Optional[dict] = None) -> str:
        """Das Bild als data:-URL — getrennt geholt, weil es gross ist.

        Stünde es in `scan_daten()`, ginge es bei jedem Klick erneut durch die
        Brücke. Die Seite holt es einmal je Aufnahme (`foto.stand` ändert sich).
        """
        return self._foto_bild

    def _foto_farbe(self, x: int, y: int) -> Optional[tuple]:
        """Die Farbe an einer Bildschirmstelle — aus dem Originalbild."""
        if self._foto is None or self._foto_info is None:
            return None
        px = int(x) - int(self._foto_info["links"])
        py = int(y) - int(self._foto_info["oben"])
        if not (0 <= px < self._foto.width and 0 <= py < self._foto.height):
            return None
        try:
            wert = self._foto.convert("RGB").getpixel((px, py))
        except (OSError, ValueError):
            return None
        return tuple(int(v) for v in wert[:3])

    def _foto_crop(self, region):
        """Der Ausschnitt einer Slot-Region aus dem Screenshot, oder None."""
        if self._foto is None or self._foto_info is None or not region:
            return None
        return crop_region(self._foto, tuple(region),
                           int(self._foto_info["links"]), int(self._foto_info["oben"]))

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
            (1, "Bereich", "Fenster wählen oder Ausschnitt aufziehen — dann "
                "Screenshot.", self._foto is not None,
             "scan_foto", "Screenshot aufnehmen"),
            (2, "Slots", "Auf einen LEEREN Slot-Hintergrund klicken — das legt "
                "alle auf einmal an.", hat_slots,
             "modus:" + MODUS_FINDEN, "Slots finden"),
            (3, "Items", "Inventar im Spiel füllen, NEU aufnehmen, dann lernen.",
             hat_items, "scan_items_lernen", "aus allen Slots lernen"),
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
        regionen = [s.scan_region for s in self._flaechen_slots() if s.scan_region]
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

    def _flaechen_slots(self) -> list:
        """Die Slots, um die sich die Ersatzfläche legt: die des offenen Scans."""
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
        return {
            "modus": self.scan_modus,
            "ecke": list(self._ecke) if self._ecke else None,
            "foto": self._flaeche(),
            "slots": [self._slot_json(s, s.name in dabei_slots) for s in self.slots.values()],
            "items": [self._item_json(i, i.name in dabei_items) for i in self.items.values()],
            "scans": [self._scan_json(c) for c in self.scans.values()],
            "kategorien": existing_categories(self.items),
            "bereich": list(self.scan_bereich) if self.scan_bereich else None,
            "schritte": self._schritte(),
            "offen": self.scan_offen,
            "nur_dabei": self.nur_dabei,
            "wahl": {"art": self.scan_art, "name": self.scan_name},
            "dirty": self._scan_dirty,
            "status": {"text": text, "art": art},
            # Beide sind optional und der Reiter sagt es, statt Knöpfe
            # anzubieten, die nichts tun: ohne Pillow gibt es kein Bild, ohne
            # OpenCV kein Template-Matching (also keine Erkennung und kein
            # Erkennen von Doppelten beim Lernen).
            "opencv": self._hat_opencv(),
            "pillow": self._hat_pillow(),
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
        return {
            "dabei": dabei,
            "name": slot.name,
            "region": list(slot.scan_region),
            "klick": list(slot.click_pos),
            "farbe": hexfarbe(slot.slot_color),
            "breite": slot.scan_region[2] - slot.scan_region[0],
            "hoehe": slot.scan_region[3] - slot.scan_region[1],
            "treffer": treffer,
        }

    def _item_json(self, item: ItemProfile, dabei: bool = False) -> dict:
        return {
            "dabei": dabei,
            "name": item.name,
            "kategorie": item.category,
            "prioritaet": item.priority,
            "konfidenz": item.min_confidence,
            "template": item.template,
            "marker": [hexfarbe(c) for c in item.marker_colors],
            # Ein Profil ohne Template UND ohne Marker wird nie erkannt — das
            # sagt die Selbstdiagnose auch, nur eben erst beim Start.
            "stumm": not item.template and not item.marker_colors,
        }

    def _scan_json(self, cfg: ItemScanConfig) -> dict:
        return {
            "name": cfg.name,
            "slots": list(cfg.slot_names),
            "items": list(cfg.item_names),
            "toleranz": cfg.color_tolerance,
            "lernen": bool(cfg.learn_unknown),
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
            if item is None or not item.template:
                continue
            url = self._template_url(item.template)
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
        """Was ein Klick auf dem Bild bedeutet."""
        modus = (daten or {}).get("modus") or MODUS_WAHL
        if modus not in MODI:
            return self._scan_melde(f"Unbekannter Modus '{modus}'.", "err")
        self.scan_modus = modus
        self._ecke = None
        texte = {
            MODUS_WAHL: "Auswählen: auf einen Slot klicken.",
            MODUS_SLOT: "Neuer Slot: zwei Ecken anklicken.",
            MODUS_MESSEN: "Farbe messen: auf den Slot-Hintergrund klicken.",
            MODUS_KLICK: "Klickpunkt: die Stelle im Slot anklicken.",
            MODUS_BEREICH: "Bereich: zwei Ecken um den Teil, der zählt.",
            MODUS_FINDEN: "Slots finden: auf einen leeren Slot-Hintergrund klicken.",
        }
        return self._scan_melde(texte[modus], "info")

    def scan_waehlen(self, daten: dict) -> dict:
        """Wählt einen Slot, ein Item oder einen Scan aus."""
        art = (daten or {}).get("art") or ART_SLOT
        name = str((daten or {}).get("name") or "")
        if art not in (ART_SLOT, ART_ITEM, ART_SCAN):
            return self._scan_melde(f"Unbekannte Art '{art}'.", "err")
        self.scan_art, self.scan_name = art, name
        return self.scan_daten()

    def _gewaehlter_slot(self) -> Optional[ItemSlot]:
        return self.slots.get(self.scan_name) if self.scan_art == ART_SLOT else None

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
        return self._klick_waehlen(x, y)

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
        if x2 - x1 < 2 or y2 - y1 < 2:
            return self._scan_melde("Zu klein — nochmal aufziehen.", "warn")

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
        self._dazu(ART_SLOT, name)
        gemessen = f" · Hintergrund {hexfarbe(farbe)}" if farbe else ""
        return self._scan_geaendert(
            f"{name}: {x2 - x1}×{y2 - y1} px{gemessen}")

    def _klick_finden(self, x: int, y: int) -> dict:
        """Ein Klick auf einen leeren Slot-Hintergrund legt ALLE Slots an.

        Der Schritt, der im Studio fehlte: ein volles Inventar sind 45 Slots und
        damit 90 Klicks, wenn man jeden einzeln aufzieht. Die Erkennung dafür
        gibt es längst — `erkenne_slots_im_bild()` aus dem Konsolen-Slot-Editor,
        dieselbe Funktion, die auch `repair` benutzt. Zwei Erkennungen wären
        zwei Ergebnisse.

        Gebraucht wird nur eine Farbe, und die zeigt man statt sie zu tippen.
        Angelegt wird, was nicht schon einen Slot hat: ein zweiter Durchgang
        ergänzt also, statt zu verdoppeln.
        """
        if self._foto is None or self._foto_info is None:
            return self._scan_melde("Erst ein Bild aufnehmen.", "warn")
        farbe = self._foto_farbe(x, y)
        if farbe is None:
            return self._scan_melde("Dort liegt kein Bild — erst aufnehmen.", "warn")
        if not self._hat_opencv():
            return self._scan_melde(
                "Das Finden braucht OpenCV: pip install opencv-python", "err")

        try:
            rechtecke = self._slots_suchen(farbe)
        except Exception as fehler:                     # OpenCV/NumPy-Innenleben
            return self._scan_melde(f"Erkennung fehlgeschlagen: {fehler}", "err")
        if not rechtecke:
            return self._scan_melde(
                f"Nichts gefunden zu {hexfarbe(farbe)} — auf eine LEERE Stelle im "
                "Slot klicken, nicht auf ein Item.", "warn")

        links, oben = int(self._foto_info["links"]), int(self._foto_info["oben"])
        neu, schon = 0, 0
        for rx, ry, rb, rh in rechtecke:
            region = (links + rx, oben + ry, links + rx + rb, oben + ry + rh)
            if self._slot_an_stelle(region):
                schon += 1
                continue
            name = next_slot_name(self.slots)
            self.slots[name] = ItemSlot(
                name=name, scan_region=region,
                click_pos=((region[0] + region[2]) // 2, (region[1] + region[3]) // 2),
                slot_color=farbe)
            self._dazu(ART_SLOT, name)
            neu += 1
        if not neu:
            return self._scan_melde(f"{schon} Slot(s) gefunden — alle schon da.", "info")
        self.scan_modus = MODUS_WAHL
        teile = f"{neu} Slot(s) angelegt"
        if schon:
            teile += f", {schon} schon vorhanden"
        return self._scan_geaendert(f"{teile} · Hintergrund {hexfarbe(farbe)}")

    # Enger werdende Bänder für Sättigung und Helligkeit. Der erste Wert ist der
    # des Konsolen-Editors; die engeren braucht es bei dunklen Oberflächen, wo
    # Slot und Panel sich nur um wenige Stufen unterscheiden.
    _SV_STUFEN = (50, 35, 25, 18, 12, 8)

    def _slots_suchen(self, farbe: tuple) -> list:
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
        from ..slot_editor import erkenne_slots_im_bild
        from ...config import CONFIG
        flaeche = self._foto.width * self._foto.height
        bestes: list = []
        for sv in self._SV_STUFEN:
            rechtecke, _ = erkenne_slots_im_bild(
                self._foto, farbe, CONFIG.scan_slot_hsv_tolerance, sv_toleranz=sv)
            rechtecke = [r for r in rechtecke if r[2] * r[3] * 2 <= flaeche]
            if len(rechtecke) > len(bestes):
                bestes = rechtecke
        return bestes

    def _slot_an_stelle(self, region: tuple) -> bool:
        """Liegt an dieser Stelle schon ein Slot? Mitte im Rechteck zählt.

        Nicht auf Gleichheit prüfen: die Erkennung normalisiert auf die
        Median-Grösse, ein von Hand aufgezogener Slot liegt also fast nie exakt
        gleich — und dann stünden zwei Slots übereinander.
        """
        mx, my = (region[0] + region[2]) // 2, (region[1] + region[3]) // 2
        for s in self.slots.values():
            r = s.scan_region
            if r and r[0] <= mx <= r[2] and r[1] <= my <= r[3]:
                return True
        return False

    def _klick_messen(self, x: int, y: int) -> dict:
        slot = self._gewaehlter_slot()
        if slot is None:
            return self._scan_melde("Erst einen Slot wählen.", "warn")
        farbe = self._foto_farbe(x, y)
        if farbe is None:
            return self._scan_melde("Dort liegt kein Bild — erst aufnehmen.", "warn")
        slot.slot_color = farbe
        return self._scan_geaendert(f"{slot.name}: Hintergrund {hexfarbe(farbe)}")

    def _klick_klickpunkt(self, x: int, y: int) -> dict:
        slot = self._gewaehlter_slot()
        if slot is None:
            return self._scan_melde("Erst einen Slot wählen.", "warn")
        slot.click_pos = (x, y)
        return self._scan_geaendert(f"{slot.name}: Klickpunkt ({x}, {y})")

    def _klick_waehlen(self, x: int, y: int) -> dict:
        """Den obersten Slot unter der Stelle auswählen.

        Rückwärts durch die Liste, damit bei überlappenden Slots der zuletzt
        angelegte gewinnt — das ist der, den man gerade vor sich hat.
        """
        for slot in reversed(list(self.slots.values())):
            x1, y1, x2, y2 = slot.scan_region
            if x1 <= x <= x2 and y1 <= y <= y2:
                self.scan_art, self.scan_name = ART_SLOT, slot.name
                return self.scan_daten()
        self.scan_name = ""
        return self.scan_daten()

    def scan_abbrechen(self, daten: Optional[dict] = None) -> dict:
        """ESC: eine halb gesetzte Ecke verwerfen, zurück ins Auswählen."""
        self._ecke = None
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

        if feld == "name":
            return self._slot_umbenennen(slot, str(wert or "").strip())
        if feld == "farbe":
            slot.slot_color = rgbwert(wert)
            return self._scan_geaendert(f"{slot.name}: Hintergrund {wert or 'entfernt'}")
        if feld in ("x1", "y1", "x2", "y2"):
            werte = list(slot.scan_region)
            werte[("x1", "y1", "x2", "y2").index(feld)] = int(wert or 0)
            slot.scan_region = normalize_region(*werte)
            return self._scan_geaendert()
        if feld in ("kx", "ky"):
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
        slot = self._gewaehlter_slot()
        if slot is None:
            return self._scan_melde("Kein Slot gewählt.", "warn")
        del self.slots[slot.name]
        self._treffer.pop(slot.name, None)
        benutzt = [c.name for c in self.scans.values() if slot.name in c.slot_names]
        for cfg in self.scans.values():
            cfg.slot_names = [n for n in cfg.slot_names if n != slot.name]
        self._objekte_angleichen()
        self.scan_name = ""
        hinweis = f" · aus {len(benutzt)} Scan(s) entfernt" if benutzt else ""
        return self._scan_geaendert(f"'{slot.name}' gelöscht{hinweis}", "warn")

    def scan_slot_doppeln(self, daten: Optional[dict] = None) -> dict:
        """Ein Slot neben dem gewählten — der schnellste Weg zu einer Reihe.

        Versetzt um seine eigene Breite plus zwei Pixel: Inventare stehen im
        Raster, und die zweite Zelle liegt fast immer genau dort.
        """
        slot = self._gewaehlter_slot()
        if slot is None:
            return self._scan_melde("Kein Slot gewählt.", "warn")
        x1, y1, x2, y2 = slot.scan_region
        versatz = (x2 - x1) + 2
        name = next_slot_name(self.slots)
        self.slots[name] = ItemSlot(
            name=name, scan_region=(x1 + versatz, y1, x2 + versatz, y2),
            click_pos=(slot.click_pos[0] + versatz, slot.click_pos[1]),
            slot_color=slot.slot_color)
        self.scan_name = name
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
        """
        if not self.slots:
            return self._scan_melde("Keine Slots vorhanden.", "warn")
        neu, doppelt, leer = 0, 0, 0
        for slot in list(self.slots.values()):
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
        marker = _collect_markers_silent(crop, slot.slot_color)
        self.items[name] = ItemProfile(
            name=name,
            marker_colors=[tuple(c) for c in marker],
            category=None,
            priority=len(self.items) + 1,
            template=save_template(crop, name),
            min_confidence=CONFIG.scan_min_confidence,
        )
        return name

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
            item.category = str(wert or "").strip() or None
            return self._scan_geaendert()
        if feld == "prioritaet":
            item.priority = max(1, int(wert or 1))
            return self._scan_geaendert()
        if feld == "konfidenz":
            item.min_confidence = max(0.0, min(1.0, float(wert or 0)))
            return self._scan_geaendert()
        return self._scan_melde(f"Unbekanntes Feld '{feld}'.", "err")

    def _item_umbenennen(self, item: ItemProfile, neu: str) -> dict:
        """Wie beim Slot: der Name ist die Referenz, also ziehen die Scans mit."""
        if not neu or neu == item.name:
            return self.scan_daten()
        if neu in self.items:
            return self._scan_melde(f"'{neu}' gibt es schon.", "warn")
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
        if not self.slots:
            return self._scan_melde("Keine Slots vorhanden.", "warn")

        # Erst hier importiert: `runtime/__init__` zieht den Worker samt
        # `winapi` nach, und den braucht der Rest des Fensters nicht.
        from ...runtime.item_scan import _check_profile_match
        from ...config import CONFIG

        toleranz = self._toleranz()
        kandidaten = self._kandidaten()
        stellvertreter = _NurConfig(CONFIG)
        self._treffer = {}
        gefunden = 0
        for slot in self.slots.values():
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
                self._treffer[slot.name] = {
                    "name": treffer.name,
                    "farbe": hexfarbe(treffer.marker_colors[0]) if treffer.marker_colors else None,
                }
        return self._scan_melde(
            f"{gefunden} von {len(self.slots)} Slot(s) erkannt "
            f"(Toleranz {toleranz}, {len(kandidaten)} Item(s) geprüft).")

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
                if self._flaeche():
                    return self._scan_melde(
                        f"'{name}' geöffnet — kein Bild gemerkt, die Slots stehen "
                        "trotzdem. „Screenshot aufnehmen“ legt das Spiel dahinter.",
                        "info")
                return self._scan_melde(
                    f"'{name}' geöffnet — noch kein Bild dazu. Screenshot aufnehmen.",
                    "info")
            return self._scan_melde(f"'{name}' geöffnet, Bild von zuletzt.")
        self._foto = None
        self._foto_bild = ""
        self._foto_info = None
        self.scan_bereich = None
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
        self.scans[name] = ItemScanConfig(name=name)
        self.scan_art, self.scan_name = ART_SCAN, name
        # Ein frisch angelegter Scan ist der, an dem man arbeitet — sonst müsste
        # man ihn direkt danach noch einmal auswählen.
        self.scan_offen = name
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
            cfg.color_tolerance = max(0, int(wert or 0))
            return self._scan_geaendert()
        if feld == "lernen":
            cfg.learn_unknown = bool(wert)
            return self._scan_geaendert()
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
        name = str((daten or {}).get("name") or "")
        liste = cfg.slot_names if art == ART_SLOT else cfg.item_names
        if name in liste:
            liste.remove(name)
        else:
            liste.append(name)
        self._objekte_angleichen()
        return self._scan_geaendert()

    def scan_loeschen(self, daten: Optional[dict] = None) -> dict:
        """Löscht die offene Scan-Konfiguration samt Datei."""
        name = self.scan_name if self.scan_art == ART_SCAN else ""
        if name not in self.scans:
            return self._scan_melde("Kein Scan gewählt.", "warn")
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


def _als_datenurl(bild, format_: str = "PNG") -> str:
    """PIL-Bild -> `data:`-URL. Leerer String, wenn es nicht geht."""
    try:
        puffer = io.BytesIO()
        bild.save(puffer, format=format_)
    except (OSError, ValueError):
        return ""
    art = "png" if format_.upper() == "PNG" else "jpeg"
    return f"data:image/{art};base64," + base64.b64encode(puffer.getvalue()).decode("ascii")
