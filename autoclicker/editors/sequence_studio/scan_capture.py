"""Screenshot-, Fenster- und Aufnahmezustand des Scan-Studios."""

import base64
import io
import time
from pathlib import Path
from typing import Optional

from ...utils import sanitize_filename
from .scan_model import crop_region, normalize_region

PHOTO_MAX_WIDTH = 2400


def _as_data_url(image, format_: str = "PNG") -> str:
    """PIL-Bild -> data:-URL. Leerer String, wenn es nicht geht."""
    try:
        buffer = io.BytesIO()
        image.save(buffer, format=format_)
    except (OSError, ValueError):
        return ""
    kind = "png" if format_.upper() == "PNG" else "jpeg"
    return f"data:image/{kind};base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


class ScanCaptureMixin:
    # --------------------------------------------------------------- Das Bild

    def scan_screenshot(self, data: Optional[dict] = None) -> dict:
        """Nimmt einen Screenshot auf und legt ihn unter das Raster.

        Der eingefrorene Bildschirm ist die Arbeitsfläche: Slots zieht man dort auf,
        wo sie im Spiel liegen. Vollbild ist die Voreinstellung (der ganze virtuelle
        Desktop); `area` schränkt ein, und ohne Angabe gilt der zuletzt gesetzte
        Bereich des Scans — der steht im gemerkten Bild und überlebt das Schliessen.
        """
        locked = self._scan_requirement(data)
        if locked is not None:
            return locked
        try:
            from ...imaging import PILLOW_AVAILABLE, take_screenshot
            from ...winapi import get_virtual_origin, resolve_window
        except ImportError:
            return self._scan_report("Bildmodule fehlen — kein Screenshot möglich.", "err")
        if not PILLOW_AVAILABLE:
            return self._scan_report("Ohne Pillow gibt es kein Bild: pip install pillow", "err")

        area = self._area_from(data) if data else None
        if area is None:
            area = self.scan_area

        # Eine gespeicherte Quelle wird bei JEDER Aufnahme neu aufgelöst: HWNDs
        # überleben keinen Neustart. Editor und Runtime rufen danach exakt
        # denselben Aufnahmehelfer auf.
        cfg = self.scans.get(self.open_scan)
        image, hint, window_used, alignment_warning = None, "", False, False
        if cfg is not None and cfg.capture_window_title:
            window = resolve_window(
                cfg.capture_window_title, cfg.capture_window_index,
                cfg.capture_window_rect)
            if window is None:
                self.scan_window_id = 0
                return self._scan_report(
                    f"Fenster '{cfg.capture_window_title}' nicht gefunden. Spiel "
                    "öffnen oder rechts eine andere Aufnahmequelle wählen.", "err")
            self.scan_window_id = int(window[2])
            image, area, hint = self._window_image()
            if image is None:
                return self._scan_report(
                    f"Fenster '{cfg.capture_window_title}' konnte nicht aufgenommen "
                    "werden.", "err")
            window_used = True
            alignment, alignment_warning = self._slots_to_window(cfg, area)
            hint += alignment
        elif self.scan_window_id:
            image, area, hint = self._window_image()
            if image is None:
                return self._scan_report("Gewähltes Fenster konnte nicht aufgenommen werden.",
                                        "err")
            window_used = True

        if image is None:
            image = take_screenshot(area) if area else take_screenshot()
        if image is None:
            return self._scan_report("Screenshot fehlgeschlagen.", "err")

        left, top = (area[0], area[1]) if area else get_virtual_origin()
        self.scan_area = area
        self._photo = image
        self._photo_remember(image, left, top)
        self._display_image(left, top, time.time())
        # Ein alter Treffer gehört zu einem alten Bild, ein alter Suchbereich
        # auch: er stand in Bildschirm-Koordinaten um ein Inventar, das jetzt
        # woanders liegen kann.
        self._matches = {}
        self._search_area = None
        wo = "Fenster" if window_used else ("Bereich" if area else "Vollbild")
        # **Die Uhrzeit steht dabei, damit man SIEHT, dass aufgenommen wurde.**
        # Zwei Aufnahmen desselben Spielstands sehen gleich aus, und wenn auch
        # die Meldung Wort für Wort dieselbe ist, wirkt der Knopf kaputt — genau
        # der Eindruck, wegen dem hier vorher „passiert nichts" gemeldet wurde.
        return self._scan_report(f"{wo} aufgenommen um {time.strftime('%H:%M:%S')}: "
                                f"{image.width}×{image.height} px "
                                f"ab ({left}, {top}).{hint}"
                                f"{self._outside_hint()}",
                                "warn" if hint.startswith(" Direkte")
                                or alignment_warning else "ok")

    def _window_image(self):
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
        result = take_consistent_window_screenshot(self.scan_window_id)
        if result is None:
            return None, None, ""
        return result

    def _slots_to_window(self, cfg, rect_value: tuple) -> tuple[str, bool]:
        """Zieht Slots auf die aktuelle Fensterlage und merkt die neue Referenz.

        Die Slots bleiben aus Kompatibilitätsgründen global in Bildschirm-
        Koordinaten gespeichert. Das Referenzrechteck sagt, zu welcher Lage sie
        gehören. Beim neuen Foto werden beide gemeinsam verschoben bzw. skaliert.
        """
        from ..scan_services import map_point_between_rects, map_region_between_rects

        new = tuple(int(v) for v in rect_value)
        old = tuple(cfg.capture_window_rect) if cfg.capture_window_rect else None
        if old == new:
            return "", False

        slots = [self.slots[name] for name in cfg.slot_names if name in self.slots]
        if old is None:
            self._remember("Fensterquelle verankert")
            cfg.capture_window_rect = new
            self._scan_dirty = True
            return " Slots sind jetzt relativ zu diesem Fenster verankert.", False

        try:
            moved = [(
                slot,
                map_region_between_rects(slot.scan_region, old, new),
                map_point_between_rects(slot.click_pos, old, new),
            ) for slot in slots]
        except (TypeError, ValueError):
            self._remember("Fensterquelle neu verankert")
            cfg.capture_window_rect = new
            self._scan_dirty = True
            return (" Alte Fenstergeometrie war ungültig; Quelle neu verankert, "
                    "Slots unverändert.", True)

        self._remember("Slots ans Fenster angepasst")
        for slot, region, click_value in moved:
            slot.scan_region = region
            slot.click_pos = click_value
        cfg.capture_window_rect = new
        self._sync_objects()
        self._scan_dirty = True
        if not slots:
            return " Fensterreferenz aktualisiert.", False
        same_size = (old[2] - old[0], old[3] - old[1]) == (
            new[2] - new[0], new[3] - new[1])
        if same_size:
            return (f" {len(slots)} Slot(s) folgen dem verschobenen Fenster "
                    "automatisch.", False)
        return (f" Fenstergrösse geändert: {len(slots)} Slot(s) angepasst. "
                "Items für neue Slotgrössen einmal ergänzend lernen.", True)

    def _window_source_restore(self, cfg) -> bool:
        """Stellt die sitzungsabhängige HWND aus der gespeicherten Quelle her."""
        self.scan_window_id = 0
        if cfg is None or not cfg.capture_window_title:
            return False
        if self.scan_area is None and cfg.capture_window_rect:
            self.scan_area = tuple(cfg.capture_window_rect)
        try:
            from ...winapi import resolve_window
            window = resolve_window(
                cfg.capture_window_title, cfg.capture_window_index,
                cfg.capture_window_rect)
        except ImportError:
            window = None
        if window is None:
            return False
        self.scan_window_id = int(window[2])
        return True

    @staticmethod
    def _area_from(data: dict) -> Optional[tuple]:
        """Liest `area` aus einer Anfrage — vier Zahlen oder nichts."""
        raw = (data or {}).get("area")
        if not raw or len(raw) != 4:
            return None
        try:
            x1, y1, x2, y2 = (int(w) for w in raw)
        except (TypeError, ValueError):
            return None
        x1, y1, x2, y2 = normalize_region(x1, y1, x2, y2)
        return (x1, y1, x2, y2) if x2 - x1 >= 8 and y2 - y1 >= 8 else None

    def _outside_hint(self) -> str:
        """Sagt, wie viele Slots des offenen Scans neben dem Bild liegen.

        Ohne das ist ein zu eng gesetzter Bereich still: die Slots stehen weiter
        in der Liste, sind aber im Bild nicht zu sehen, und man sucht den Fehler
        bei der Erkennung statt beim Ausschnitt.
        """
        if self._photo_info is None:
            return ""
        f = self._photo_info
        margin = (f["left"], f["top"],
                f["left"] + round(f["width"] / f["scale"]),
                f["top"] + round(f["height"] / f["scale"]))
        outside = [s for s in self._scan_slots() if s.scan_region
                    and not (margin[0] <= s.scan_region[0] and s.scan_region[2] <= margin[2]
                             and margin[1] <= s.scan_region[1] and s.scan_region[3] <= margin[3])]
        return f" {len(outside)} Slot(s) liegen ausserhalb." if outside else ""

    def scan_area_set(self, data: Optional[dict] = None) -> dict:
        """Setzt, WAS aufgenommen wird — aufgenommen wird erst auf Knopfdruck.

        Ohne `area` heisst es Vollbild: der Rückweg, ohne den ein eingeschränkter
        Scan nie wieder das Ganze sähe.

        Wählen und Aufnehmen sind zwei Dinge, also zwei Klicks. Vorher nahm die
        Methode gleich mit auf — dann hatte man plötzlich ein Bild, ohne etwas
        ausgelöst zu haben, und der Knopf daneben schien nichts mehr zu tun.

        `_click_area` (zwei Ecken im Bild) bleibt die Ausnahme und schneidet
        sofort zu: dort ist der Zuschnitt das Ergebnis, nicht die Vorbereitung.
        """
        locked = self._scan_requirement(data)
        if locked is not None:
            return locked
        new_area = self._area_from(data or {})
        try:
            window_id = int((data or {}).get("window") or 0)
        except (TypeError, ValueError):
            window_id = 0

        cfg = self.scans.get(self.open_scan)
        if window_id:
            try:
                from ...winapi import list_windows
                window = list_windows()
            except ImportError:
                window = []
            selected = next((e for e in window if int(e[2]) == window_id), None)
            if selected is None:
                return self._scan_report(
                    "Das gewählte Fenster ist nicht mehr offen. Liste neu wählen.", "err")
            title, rect_value, _identity = selected
            same = [e for e in window if e[0].casefold() == title.casefold()]
            index = next((i for i, e in enumerate(same)
                          if int(e[2]) == window_id), 0)
            if cfg is not None:
                change = (cfg.capture_window_title != title
                              or cfg.capture_window_index != index
                              or cfg.capture_window_rect is None)
                if change:
                    self._remember("Fensterquelle gewählt")
                    cfg.capture_window_title = title
                    cfg.capture_window_index = index
                    # Beim ersten Verankern gelten vorhandene Slots für die
                    # aktuelle Lage. Danach bleibt die alte Referenz bis zur
                    # Aufnahme stehen, damit die Slots mitwandern können.
                    if cfg.capture_window_rect is None:
                        cfg.capture_window_rect = tuple(rect_value)
                    self._scan_dirty = True
            self.scan_window_id = window_id
            self.scan_area = tuple(rect_value)
        else:
            if cfg is not None and (cfg.capture_window_title
                                    or cfg.capture_window_rect is not None):
                self._remember("Fensterquelle entfernt")
                cfg.capture_window_title = None
                cfg.capture_window_index = 0
                cfg.capture_window_rect = None
                self._scan_dirty = True
            self.scan_window_id = 0
            self.scan_area = new_area
        if not self.scan_area:
            return self._scan_report("Vollbild gewählt — jetzt „Screenshot aufnehmen“.",
                                    "info")
        x1, y1, x2, y2 = self.scan_area
        wo = "Fenster" if self.scan_window_id else "Bereich"
        return self._scan_report(
            f"{wo} gewählt: {x2 - x1}×{y2 - y1} px ab ({x1}, {y1}) — "
            f"jetzt „{wo} aufnehmen“."
            + (" Slots folgen diesem Fenster danach automatisch."
               if self.scan_window_id else ""), "info")

    def scan_windows(self, data: Optional[dict] = None) -> list:
        """Die offenen Fenster mit ihrer Lage — zur Auswahl des Bereichs.

        Der Fall, für den es das gibt: dasselbe Programm mehrmals offen. Der
        Titel ist dann dreimal derselbe, unterscheidbar sind sie nur an der
        Lage — die steht deshalb mit dabei und die Liste ist danach sortiert.

        `ask()` und nicht `call()`: es ändert nichts, es beantwortet nur etwas.
        """
        try:
            from ...winapi import list_windows
        except ImportError:
            return []
        return [{"title": title, "area": list(rect_value), "id": identity}
                for title, rect_value, identity in list_windows()]

    def _click_area(self, x: int, y: int) -> dict:
        """Zwei Ecken schränken das Bild ein — zugeschnitten, nicht neu geholt.

        Neu aufzunehmen wäre das Naheliegende und wäre falsch: zwischen den
        beiden Klicks vergeht Zeit, und was man zugeschnitten hat, soll man auch
        bekommen. Der Bereich wird gemerkt, die nächste Aufnahme holt genau ihn.
        """
        if self._photo is None or self._photo_info is None:
            return self._scan_report("Erst ein Bild aufnehmen.", "warn")
        if self._corner is None:
            self._corner = (x, y)
            return self._scan_report("Erste Ecke des Bereichs — jetzt die zweite.", "info")
        x1, y1, x2, y2 = normalize_region(self._corner[0], self._corner[1], x, y)
        self._corner = None
        if x2 - x1 < 8 or y2 - y1 < 8:
            return self._scan_report("Zu klein — nochmal aufziehen.", "warn")

        crop_value = crop_region(self._photo, (x1, y1, x2, y2),
                                 int(self._photo_info["left"]), int(self._photo_info["top"]))
        if crop_value is None:
            return self._scan_report("Der Bereich liegt nicht im Bild.", "warn")
        # Ein von Hand gesetzter Ausschnitt ist kleiner als das Fenster — ab
        # jetzt gilt er, nicht mehr das Fenster. Sonst holte die naechste
        # Aufnahme wieder das ganze Fenster und der Zuschnitt waere weg.
        cfg = self.scans.get(self.open_scan)
        if cfg is not None and (cfg.capture_window_title
                                or cfg.capture_window_rect is not None):
            self._remember("Eigener Bildausschnitt gewählt")
            cfg.capture_window_title = None
            cfg.capture_window_index = 0
            cfg.capture_window_rect = None
            self._scan_dirty = True
        self.scan_window_id = 0
        self.scan_area = (x1, y1, x2, y2)
        self._photo = crop_value
        self._photo_remember(crop_value, x1, y1)
        self._display_image(x1, y1, time.time())
        self._matches = {}
        self._tool_done()
        return self._scan_report(f"Bereich: {x2 - x1}×{y2 - y1} px ab ({x1}, {y1})."
                                f"{self._outside_hint()}")

    def _photo_path(self, scan: str) -> Path:
        return (self.filepath.parent / "bilder"
                / f"{sanitize_filename(scan)}.png")

    def _photo_remember(self, image, left: int, top: int) -> None:
        """Legt den Screenshot beim offenen Scan ab — für das nächste Öffnen.

        Der Ursprung des virtuellen Desktops steht IM PNG (Text-Chunk), nicht in
        einer Datei daneben: zwei Dateien, die zusammengehören, laufen irgendwann
        auseinander, und dann sind alle Koordinaten um einen Monitor verschoben.

        Ohne offenen Scan wird nichts abgelegt — welches Spiel gemeint ist, sagt der Scan.
        """
        if not self.open_scan:
            return
        try:
            from PIL import PngImagePlugin
            info = PngImagePlugin.PngInfo()
            info.add_text("left", str(int(left)))
            info.add_text("top", str(int(top)))
            path = self._photo_path(self.open_scan)
            path.parent.mkdir(parents=True, exist_ok=True)
            image.save(path, "PNG", pnginfo=info)
            # Das Bild liegt UNTER `item_scans/` — und der Unterordner entsteht
            # gerade eben, was die Änderungszeit des Elternordners weiterdreht.
            # Ohne dieses Nachziehen meldete der Reiter direkt nach der eigenen
            # Aufnahme „auf Platte hat sich etwas geändert".
            self._disk_track(self.filepath.parent)
        except (ImportError, OSError, ValueError):
            pass      # ein fehlendes Erinnerungsbild ist kein Grund, den Reiter zu stören

    def _photo_load(self, scan: str) -> bool:
        """Holt den zuletzt abgelegten Screenshot dieses Scans zurück."""
        path = self._photo_path(scan)
        try:
            from PIL import Image
            image = Image.open(path)
            image.load()
        except (ImportError, OSError, ValueError):
            self._photo = None
            self._photo_image = ""
            self._photo_info = None
            self.scan_area = None
            self._window_source_restore(self.scans.get(scan))
            return False
        text = getattr(image, "text", {}) or {}
        try:
            left, top = int(text.get("left", 0)), int(text.get("top", 0))
        except (TypeError, ValueError):
            left, top = 0, 0
        self._photo = image.convert("RGB")
        # Ursprung und Grösse des gemerkten Bildes SIND der Bereich — deshalb
        # steht er nirgends sonst. Deckt er den ganzen Desktop ab, ist es kein
        # Bereich, sondern Vollbild; sonst sagte die Anzeige „Bereich" für etwas,
        # das keine Einschränkung ist.
        self.scan_area = self._area_or_fullscreen(
            (left, top, left + image.width, top + image.height))
        self._window_source_restore(self.scans.get(scan))
        self._display_image(left, top, path.stat().st_mtime)
        self._matches = {}
        return True

    @staticmethod
    def _area_or_fullscreen(rect_value: tuple) -> Optional[tuple]:
        """None, wenn das Rechteck der ganze virtuelle Desktop ist."""
        try:
            from ...winapi import get_virtual_desktop
        except ImportError:
            return rect_value
        screen = get_virtual_desktop()
        return None if screen and tuple(screen) == tuple(rect_value) else rect_value

    def _display_image(self, left: int, top: int, stamp: float) -> None:
        """Verkleinert das Original für die Übertragung und merkt die Geometrie."""
        image = self._photo
        scale = min(1.0, PHOTO_MAX_WIDTH / image.width) if image.width else 1.0
        display = image if scale >= 1.0 else image.resize(
            (max(1, int(image.width * scale)), max(1, int(image.height * scale))))
        self._photo_image = _as_data_url(display, "PNG")
        self._photo_info = {
            "left": left, "top": top,
            "width": display.width, "height": display.height,
            "scale": round(display.width / image.width, 6) if image.width else 1.0,
            "stamp": stamp,
        }

    def scan_image(self, data: Optional[dict] = None) -> str:
        """Das Bild als data:-URL — getrennt geholt, weil es gross ist.

        Stünde es in `scan_data()`, ginge es bei jedem Klick erneut durch die
        Brücke. Die Seite holt es einmal je Aufnahme (`photo.stand` ändert sich).
        """
        return self._photo_image

    def _photo_color(self, x: int, y: int) -> Optional[tuple]:
        """Die Farbe an einer Bildschirmstelle — aus dem Originalbild."""
        if self._photo is None or self._photo_info is None:
            return None
        px = int(x) - int(self._photo_info["left"])
        py = int(y) - int(self._photo_info["top"])
        if not (0 <= px < self._photo.width and 0 <= py < self._photo.height):
            return None
        try:
            value = self._photo.convert("RGB").getpixel((px, py))
        except (OSError, ValueError):
            return None
        return tuple(int(v) for v in value[:3])

    def _photo_crop(self, region):
        """Der Ausschnitt einer Slot-Region aus dem Screenshot, oder None."""
        if self._photo is None or self._photo_info is None or not region:
            return None
        return crop_region(self._photo, tuple(region),
                           int(self._photo_info["left"]), int(self._photo_info["top"]))

