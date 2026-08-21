"""Screenshot-, Fenster- und Aufnahmezustand des Scan-Studios."""

import base64
import io
import time
from pathlib import Path
from typing import Optional

from ...persistence.paths import SCAN_SHOTS_DIR
from ...utils import sanitize_filename
from .scan_model import crop_region, normalize_region

FOTO_MAX_BREITE = 2400


def _als_datenurl(bild, format_: str = "PNG") -> str:
    """PIL-Bild -> data:-URL. Leerer String, wenn es nicht geht."""
    try:
        puffer = io.BytesIO()
        bild.save(puffer, format=format_)
    except (OSError, ValueError):
        return ""
    art = "png" if format_.upper() == "PNG" else "jpeg"
    return f"data:image/{art};base64," + base64.b64encode(puffer.getvalue()).decode("ascii")


class ScanCaptureMixin:
    # --------------------------------------------------------------- Das Bild

    def scan_foto(self, daten: Optional[dict] = None) -> dict:
        """Nimmt einen Screenshot auf und legt ihn unter das Raster.

        Der eingefrorene Bildschirm ist die Arbeitsfläche: Slots zieht man dort auf,
        wo sie im Spiel liegen. Vollbild ist die Voreinstellung (der ganze virtuelle
        Desktop); `bereich` schränkt ein, und ohne Angabe gilt der zuletzt gesetzte
        Bereich des Scans — der steht im gemerkten Bild und überlebt das Schliessen.
        """
        self._scan_laden()
        try:
            from ...imaging import PILLOW_AVAILABLE, take_screenshot
            from ...winapi import get_virtual_origin, resolve_window
        except ImportError:
            return self._scan_melde("Bildmodule fehlen — kein Screenshot möglich.", "err")
        if not PILLOW_AVAILABLE:
            return self._scan_melde("Ohne Pillow gibt es kein Bild: pip install pillow", "err")

        bereich = self._bereich_aus(daten) if daten else None
        if bereich is None:
            bereich = self.scan_bereich

        # Eine gespeicherte Quelle wird bei JEDER Aufnahme neu aufgelöst: HWNDs
        # überleben keinen Neustart. Editor und Runtime rufen danach exakt
        # denselben Aufnahmehelfer auf.
        cfg = self.scans.get(self.scan_offen)
        bild, hinweis, fenster_genutzt, ausrichtung_warnung = None, "", False, False
        if cfg is not None and cfg.capture_window_title:
            fenster = resolve_window(
                cfg.capture_window_title, cfg.capture_window_index,
                cfg.capture_window_rect)
            if fenster is None:
                self.scan_fenster_id = 0
                return self._scan_melde(
                    f"Fenster '{cfg.capture_window_title}' nicht gefunden. Spiel "
                    "öffnen oder rechts eine andere Aufnahmequelle wählen.", "err")
            self.scan_fenster_id = int(fenster[2])
            bild, bereich, hinweis = self._fensterbild()
            if bild is None:
                return self._scan_melde(
                    f"Fenster '{cfg.capture_window_title}' konnte nicht aufgenommen "
                    "werden.", "err")
            fenster_genutzt = True
            ausrichtung, ausrichtung_warnung = self._slots_an_fenster(cfg, bereich)
            hinweis += ausrichtung
        elif self.scan_fenster_id:
            bild, bereich, hinweis = self._fensterbild()
            if bild is None:
                return self._scan_melde("Gewähltes Fenster konnte nicht aufgenommen werden.",
                                        "err")
            fenster_genutzt = True

        if bild is None:
            bild = take_screenshot(bereich) if bereich else take_screenshot()
        if bild is None:
            return self._scan_melde("Screenshot fehlgeschlagen.", "err")

        links, oben = (bereich[0], bereich[1]) if bereich else get_virtual_origin()
        self.scan_bereich = bereich
        self._foto = bild
        self._foto_merken(bild, links, oben)
        self._anzeigebild(links, oben, time.time())
        # Ein alter Treffer gehört zu einem alten Bild, ein alter Suchbereich
        # auch: er stand in Bildschirm-Koordinaten um ein Inventar, das jetzt
        # woanders liegen kann.
        self._treffer = {}
        self._suchbereich = None
        wo = "Fenster" if fenster_genutzt else ("Bereich" if bereich else "Vollbild")
        # **Die Uhrzeit steht dabei, damit man SIEHT, dass aufgenommen wurde.**
        # Zwei Aufnahmen desselben Spielstands sehen gleich aus, und wenn auch
        # die Meldung Wort für Wort dieselbe ist, wirkt der Knopf kaputt — genau
        # der Eindruck, wegen dem hier vorher „passiert nichts" gemeldet wurde.
        return self._scan_melde(f"{wo} aufgenommen um {time.strftime('%H:%M:%S')}: "
                                f"{bild.width}×{bild.height} px "
                                f"ab ({links}, {oben}).{hinweis}"
                                f"{self._draussen_hinweis()}",
                                "warn" if hinweis.startswith(" Direkte")
                                or ausrichtung_warnung else "ok")

    def _fensterbild(self):
        """Bildet das gewählte Fenster ab. `(bild, bereich, hinweis)`.

        Der Grund, ein Fenster zu wählen statt nur einen Ausschnitt: ein
        Desktop-Ausschnitt zeigt auch das Studio, das davor liegt. Kann sich ein Spiel
        über PrintWindow nicht zeichnen, fällt der gemeinsame Helfer auf den
        sichtbaren Ausschnitt zurück — denselben Weg nimmt der Live-Scan.
        """
        try:
            from ...imaging import take_consistent_window_screenshot
        except ImportError:
            return None, None, ""
        ergebnis = take_consistent_window_screenshot(self.scan_fenster_id)
        if ergebnis is None:
            return None, None, ""
        return ergebnis

    def _slots_an_fenster(self, cfg, rechteck: tuple) -> tuple[str, bool]:
        """Zieht Slots auf die aktuelle Fensterlage und merkt die neue Referenz.

        Die Slots bleiben aus Kompatibilitätsgründen global in Bildschirm-
        Koordinaten gespeichert. Das Referenzrechteck sagt, zu welcher Lage sie
        gehören. Beim neuen Foto werden beide gemeinsam verschoben bzw. skaliert.
        """
        from ..scan_services import map_point_between_rects, map_region_between_rects

        neu = tuple(int(v) for v in rechteck)
        alt = tuple(cfg.capture_window_rect) if cfg.capture_window_rect else None
        if alt == neu:
            return "", False

        slots = [self.slots[name] for name in cfg.slot_names if name in self.slots]
        if alt is None:
            self._merke("Fensterquelle verankert")
            cfg.capture_window_rect = neu
            self._scan_dirty = True
            return " Slots sind jetzt relativ zu diesem Fenster verankert.", False

        try:
            verschoben = [(
                slot,
                map_region_between_rects(slot.scan_region, alt, neu),
                map_point_between_rects(slot.click_pos, alt, neu),
            ) for slot in slots]
        except (TypeError, ValueError):
            self._merke("Fensterquelle neu verankert")
            cfg.capture_window_rect = neu
            self._scan_dirty = True
            return (" Alte Fenstergeometrie war ungültig; Quelle neu verankert, "
                    "Slots unverändert.", True)

        self._merke("Slots ans Fenster angepasst")
        for slot, region, klick in verschoben:
            slot.scan_region = region
            slot.click_pos = klick
        cfg.capture_window_rect = neu
        self._objekte_angleichen()
        self._scan_dirty = True
        if not slots:
            return " Fensterreferenz aktualisiert.", False
        gleiche_groesse = (alt[2] - alt[0], alt[3] - alt[1]) == (
            neu[2] - neu[0], neu[3] - neu[1])
        if gleiche_groesse:
            return (f" {len(slots)} Slot(s) folgen dem verschobenen Fenster "
                    "automatisch.", False)
        return (f" Fenstergrösse geändert: {len(slots)} Slot(s) angepasst. "
                "Items für neue Slotgrössen einmal ergänzend lernen.", True)

    def _fensterquelle_wiederherstellen(self, cfg) -> bool:
        """Stellt die sitzungsabhängige HWND aus der gespeicherten Quelle her."""
        self.scan_fenster_id = 0
        if cfg is None or not cfg.capture_window_title:
            return False
        if self.scan_bereich is None and cfg.capture_window_rect:
            self.scan_bereich = tuple(cfg.capture_window_rect)
        try:
            from ...winapi import resolve_window
            fenster = resolve_window(
                cfg.capture_window_title, cfg.capture_window_index,
                cfg.capture_window_rect)
        except ImportError:
            fenster = None
        if fenster is None:
            return False
        self.scan_fenster_id = int(fenster[2])
        return True

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
        draussen = [s for s in self._scan_slots() if s.scan_region
                    and not (rand[0] <= s.scan_region[0] and s.scan_region[2] <= rand[2]
                             and rand[1] <= s.scan_region[1] and s.scan_region[3] <= rand[3])]
        return f" {len(draussen)} Slot(s) liegen ausserhalb." if draussen else ""

    def scan_bereich_setzen(self, daten: Optional[dict] = None) -> dict:
        """Setzt, WAS aufgenommen wird — aufgenommen wird erst auf Knopfdruck.

        Ohne `bereich` heisst es Vollbild: der Rückweg, ohne den ein eingeschränkter
        Scan nie wieder das Ganze sähe.

        Wählen und Aufnehmen sind zwei Dinge, also zwei Klicks. Vorher nahm die
        Methode gleich mit auf — dann hatte man plötzlich ein Bild, ohne etwas
        ausgelöst zu haben, und der Knopf daneben schien nichts mehr zu tun.

        `_klick_bereich` (zwei Ecken im Bild) bleibt die Ausnahme und schneidet
        sofort zu: dort ist der Zuschnitt das Ergebnis, nicht die Vorbereitung.
        """
        self._scan_laden()
        neuer_bereich = self._bereich_aus(daten or {})
        try:
            fenster_id = int((daten or {}).get("fenster") or 0)
        except (TypeError, ValueError):
            fenster_id = 0

        cfg = self.scans.get(self.scan_offen)
        if fenster_id:
            try:
                from ...winapi import liste_fenster
                fenster = liste_fenster()
            except ImportError:
                fenster = []
            gewaehlt = next((e for e in fenster if int(e[2]) == fenster_id), None)
            if gewaehlt is None:
                return self._scan_melde(
                    "Das gewählte Fenster ist nicht mehr offen. Liste neu wählen.", "err")
            titel, rechteck, _kennung = gewaehlt
            gleich = [e for e in fenster if e[0].casefold() == titel.casefold()]
            index = next((i for i, e in enumerate(gleich)
                          if int(e[2]) == fenster_id), 0)
            if cfg is not None:
                aenderung = (cfg.capture_window_title != titel
                              or cfg.capture_window_index != index
                              or cfg.capture_window_rect is None)
                if aenderung:
                    self._merke("Fensterquelle gewählt")
                    cfg.capture_window_title = titel
                    cfg.capture_window_index = index
                    # Beim ersten Verankern gelten vorhandene Slots für die
                    # aktuelle Lage. Danach bleibt die alte Referenz bis zur
                    # Aufnahme stehen, damit die Slots mitwandern können.
                    if cfg.capture_window_rect is None:
                        cfg.capture_window_rect = tuple(rechteck)
                    self._scan_dirty = True
            self.scan_fenster_id = fenster_id
            self.scan_bereich = tuple(rechteck)
        else:
            if cfg is not None and (cfg.capture_window_title
                                    or cfg.capture_window_rect is not None):
                self._merke("Fensterquelle entfernt")
                cfg.capture_window_title = None
                cfg.capture_window_index = 0
                cfg.capture_window_rect = None
                self._scan_dirty = True
            self.scan_fenster_id = 0
            self.scan_bereich = neuer_bereich
        if not self.scan_bereich:
            return self._scan_melde("Vollbild gewählt — jetzt „Screenshot aufnehmen“.",
                                    "info")
        x1, y1, x2, y2 = self.scan_bereich
        wo = "Fenster" if self.scan_fenster_id else "Bereich"
        return self._scan_melde(
            f"{wo} gewählt: {x2 - x1}×{y2 - y1} px ab ({x1}, {y1}) — "
            f"jetzt „{wo} aufnehmen“."
            + (" Slots folgen diesem Fenster danach automatisch."
               if self.scan_fenster_id else ""), "info")

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
        return [{"titel": titel, "bereich": list(rechteck), "id": kennung}
                for titel, rechteck, kennung in liste_fenster()]

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
        # Ein von Hand gesetzter Ausschnitt ist kleiner als das Fenster — ab
        # jetzt gilt er, nicht mehr das Fenster. Sonst holte die naechste
        # Aufnahme wieder das ganze Fenster und der Zuschnitt waere weg.
        cfg = self.scans.get(self.scan_offen)
        if cfg is not None and (cfg.capture_window_title
                                or cfg.capture_window_rect is not None):
            self._merke("Eigener Bildausschnitt gewählt")
            cfg.capture_window_title = None
            cfg.capture_window_index = 0
            cfg.capture_window_rect = None
            self._scan_dirty = True
        self.scan_fenster_id = 0
        self.scan_bereich = (x1, y1, x2, y2)
        self._foto = ausschnitt
        self._foto_merken(ausschnitt, x1, y1)
        self._anzeigebild(x1, y1, time.time())
        self._treffer = {}
        self._werkzeug_fertig()
        return self._scan_melde(f"Bereich: {x2 - x1}×{y2 - y1} px ab ({x1}, {y1})."
                                f"{self._draussen_hinweis()}")

    @staticmethod
    def _foto_pfad(scan: str) -> Path:
        return Path(SCAN_SHOTS_DIR) / f"{sanitize_filename(scan)}.png"

    def _foto_merken(self, bild, links: int, oben: int) -> None:
        """Legt den Screenshot beim offenen Scan ab — für das nächste Öffnen.

        Der Ursprung des virtuellen Desktops steht IM PNG (Text-Chunk), nicht in
        einer Datei daneben: zwei Dateien, die zusammengehören, laufen irgendwann
        auseinander, und dann sind alle Koordinaten um einen Monitor verschoben.

        Ohne offenen Scan wird nichts abgelegt — welches Spiel gemeint ist, sagt der Scan.
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
            # Das Bild liegt UNTER `item_scans/` — und der Unterordner entsteht
            # gerade eben, was die Änderungszeit des Elternordners weiterdreht.
            # Ohne dieses Nachziehen meldete der Reiter direkt nach der eigenen
            # Aufnahme „auf Platte hat sich etwas geändert".
            from ...persistence.paths import ITEM_SCANS_DIR
            self._platte_nachziehen(Path(ITEM_SCANS_DIR))
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
            self._fensterquelle_wiederherstellen(self.scans.get(scan))
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
        self._fensterquelle_wiederherstellen(self.scans.get(scan))
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

