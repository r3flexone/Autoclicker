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
from ...persistence.paths import ITEMS_FILE, SLOTS_FILE, TEMPLATES_DIR
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
MODI = (MODUS_WAHL, MODUS_SLOT, MODUS_MESSEN, MODUS_KLICK)

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
        self._scan_geladen = False
        self._foto = None                      # PIL-Bild in Originalgrösse
        self._foto_bild: str = ""              # data:-URL, verkleinert
        self._foto_info: Optional[dict] = None
        self._ecke: Optional[tuple] = None     # erste Ecke beim Aufziehen
        self.scan_modus: str = MODUS_WAHL
        self.scan_art: str = ART_SLOT
        self.scan_name: str = ""
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

    @staticmethod
    def _scans_laden() -> dict:
        """Alle Item-Scan-Konfigurationen als Name -> Config."""
        from ...persistence import list_available_item_scans, load_item_scan_file
        gefunden = {}
        for name, pfad in list_available_item_scans():
            cfg = load_item_scan_file(pfad)
            if cfg is not None:
                gefunden[cfg.name or name] = cfg
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
        auf, wo sie im Spiel liegen, statt Koordinaten zu tippen. Aufgenommen
        wird der **ganze virtuelle Desktop**, damit auch ein Fenster auf dem
        zweiten Monitor dazugehört.
        """
        self._scan_laden()
        try:
            from ...imaging import PILLOW_AVAILABLE, take_screenshot
            from ...winapi import get_virtual_origin
        except ImportError:
            return self._scan_melde("Bildmodule fehlen — kein Screenshot möglich.", "err")
        if not PILLOW_AVAILABLE:
            return self._scan_melde("Ohne Pillow gibt es kein Bild: pip install pillow", "err")

        bild = take_screenshot()
        if bild is None:
            return self._scan_melde("Screenshot fehlgeschlagen.", "err")

        links, oben = get_virtual_origin()
        self._foto = bild
        skala = min(1.0, FOTO_MAX_BREITE / bild.width) if bild.width else 1.0
        anzeige = bild if skala >= 1.0 else bild.resize(
            (max(1, int(bild.width * skala)), max(1, int(bild.height * skala))))
        self._foto_bild = _als_datenurl(anzeige, "PNG")
        self._foto_info = {
            "links": links, "oben": oben,
            "breite": anzeige.width, "hoehe": anzeige.height,
            "skala": round(anzeige.width / bild.width, 6) if bild.width else 1.0,
            "stand": time.time(),
        }
        # Ein alter Treffer gehört zu einem alten Bild.
        self._treffer = {}
        return self._scan_melde(f"Screenshot: {bild.width}×{bild.height} px "
                                f"ab ({links}, {oben}).")

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

    # -------------------------------------------------------- Momentaufnahme

    def scan_daten(self, daten: Optional[dict] = None) -> dict:
        """Alles, was der Reiter zum Zeichnen braucht — ohne das Bild selbst."""
        self._scan_laden()
        text, art = self._scan_status
        return {
            "modus": self.scan_modus,
            "ecke": list(self._ecke) if self._ecke else None,
            "foto": dict(self._foto_info) if self._foto_info else None,
            "slots": [self._slot_json(s) for s in self.slots.values()],
            "items": [self._item_json(i) for i in self.items.values()],
            "scans": [self._scan_json(c) for c in self.scans.values()],
            "kategorien": existing_categories(self.items),
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

    def _slot_json(self, slot: ItemSlot) -> dict:
        treffer = self._treffer.get(slot.name)
        return {
            "name": slot.name,
            "region": list(slot.scan_region),
            "klick": list(slot.click_pos),
            "farbe": hexfarbe(slot.slot_color),
            "breite": slot.scan_region[2] - slot.scan_region[0],
            "hoehe": slot.scan_region[3] - slot.scan_region[1],
            "treffer": treffer,
        }

    def _item_json(self, item: ItemProfile) -> dict:
        return {
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
        gemessen = f" · Hintergrund {hexfarbe(farbe)}" if farbe else ""
        return self._scan_geaendert(
            f"{name}: {x2 - x1}×{y2 - y1} px{gemessen}")

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
        cfg = self.scans.get(self.scan_name) if self.scan_art == ART_SCAN else None
        if cfg is not None and cfg.item_names:
            gewaehlt = [self.items[n] for n in cfg.item_names if n in self.items]
            if gewaehlt:
                return sorted(gewaehlt, key=lambda i: i.priority)
        return sorted(self.items.values(), key=lambda i: i.priority)

    def _toleranz(self) -> int:
        cfg = self.scans.get(self.scan_name) if self.scan_art == ART_SCAN else None
        if cfg is not None:
            return cfg.color_tolerance
        return ItemScanConfig(name="").color_tolerance

    # -------------------------------------------------------- Scan-Konfigs

    def scan_neu(self, daten: Optional[dict] = None) -> dict:
        """Eine neue Item-Scan-Konfiguration — leer, aber mit eindeutigem Namen."""
        name = eindeutiger_name(str((daten or {}).get("name") or "Neuer Scan"), self.scans)
        self.scans[name] = ItemScanConfig(name=name)
        self.scan_art, self.scan_name = ART_SCAN, name
        return self._scan_geaendert(f"Scan '{name}' angelegt.")

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
        cfg = self.scans.get(str((daten or {}).get("scan") or ""))
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
