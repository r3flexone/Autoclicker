"""Auswahl, Mauswerkzeuge und Slot-Bearbeitung des Scan-Editors."""

from typing import Optional

from ...models import ItemSlot
from .model import hexfarbe, rgbwert
from .scan_contract import (
    ART_ITEM,
    ART_SCAN,
    ART_SLOT,
    MIN_SLOT,
    MODI_ALLE,
    MODUS_AKTION,
    MODUS_BEREICH,
    MODUS_FINDEN,
    MODUS_KLICK,
    MODUS_MESSEN,
    MODUS_REGION,
    MODUS_SLOT,
    MODUS_WAHL,
    TREFFER_MIN,
)
from .scan_model import next_slot_name, normalize_region
from ..scan_services import detect_slots_in_image


class ScanInteractionMixin:
    """Übersetzt Benutzeraktionen in Auswahl- und Slot-Änderungen."""

    def scan_mode_set(self, data: dict) -> dict:
        """Was ein Klick auf dem Bild bedeutet.

        Nochmal auf denselben Modus führt zurück ins Auswählen — ein Modus, in den
        man nur hinein kommt, wäre eine Falltür.
        """
        modus = (data or {}).get("modus") or MODUS_WAHL
        if modus not in MODI_ALLE:
            return self._scan_report(f"Unbekannter Modus '{modus}'.", "err")
        if modus != MODUS_WAHL:
            gesperrt = self._scan_requirement(data)
            if gesperrt is not None:
                return gesperrt
        # Region und Aktionspunkt gehören den Erkennungs-Scans und brauchen ein
        # Ziel; das setzt `region_mode()`. Hier landen sie nur, wenn jemand den
        # Buchstaben drückt, während gar kein Boss-/Icon-Scan offen ist.
        if modus in (MODUS_REGION, MODUS_AKTION) and not self._region_ziel:
            return self._scan_report(
                "Erst einen Boss- bzw. Icon-Scan öffnen.", "warn")
        if "fixiert" in (data or {}):
            self.scan_werkzeug_fixiert = bool((data or {}).get("fixiert"))
        if (modus == self.scan_modus and modus != MODUS_WAHL
                and "fixiert" not in (data or {})):
            self._ecke = None
            self._suchbereich = None
            self.scan_modus = MODUS_WAHL
            return self._scan_report("Zurück zum Auswählen.", "info")
        self.scan_modus = modus
        self._ecke = None
        # Jeder Wechsel fängt die Suche von vorn an: ein Suchbereich von vorhin
        # gehört zu einer Absicht von vorhin.
        self._suchbereich = None
        if modus not in (MODUS_REGION, MODUS_AKTION):
            self._region_ziel = None
        texte = {
            MODUS_WAHL: "Auswählen: auf einen Slot klicken — daneben klicken "
                        "zieht ein Rechteck um mehrere.",
            MODUS_SLOT: "Neuer Slot: zwei Ecken anklicken.",
            MODUS_MESSEN: "Farbe messen: auf den Slot-Hintergrund klicken.",
            MODUS_KLICK: "Klickpunkt: die Stelle im Slot anklicken.",
            MODUS_BEREICH: "Bereich: zwei Ecken um den Teil, der zählt.",
            MODUS_FINDEN: "Slots finden: zwei Ecken um das Inventar, dann auf "
                          "einen leeren Slot-Hintergrund darin klicken.",
            MODUS_REGION: "Region: zwei Ecken um das, was erkannt werden soll.",
            MODUS_AKTION: "Klickpunkt: die Stelle anklicken, die bei einem "
                          "Treffer geklickt wird.",
        }
        zurueck = "" if modus == MODUS_WAHL else "  ·  ESC oder nochmal die Kachel = zurück"
        return self._scan_report(texte[modus] + zurueck, "info")

    def scan_select(self, data: dict) -> dict:
        """Wählt einen Slot, ein Item oder einen Scan aus."""
        kind = (data or {}).get("kind") or ART_SLOT
        name = str((data or {}).get("name") or "")
        if kind not in (ART_SLOT, ART_ITEM, ART_SCAN):
            return self._scan_report(f"Unbekannte Art '{kind}'.", "err")
        self.scan_art, self.scan_name = kind, name
        # Eine Zeile in der Liste anzuklicken ist eine EINZEL-Auswahl. Sonst
        # bliebe nach einem Rechteck die alte Menge stehen, und der nächste
        # Druck auf „löschen" nähme dreissig Slots statt des einen, den man
        # gerade angeklickt hat.
        self._auswahl = [name] if kind == ART_SLOT and name in self.slots else []
        return self.scan_data()

    def _selected_slot(self) -> Optional[ItemSlot]:
        return self.slots.get(self.scan_name) if self.scan_art == ART_SLOT else None

    def _selection_slots(self) -> list:
        """Worauf eine Sammel-Aktion wirkt: die Auswahl, sonst der eine Gewählte.

        Eine Stelle für alle, sonst nähme „löschen" dreissig Slots und „Grösse
        angleichen" einen.
        """
        names = [n for n in self._auswahl if n in self.slots]
        if names:
            return [self.slots[n] for n in names]
        slot = self._selected_slot()
        return [slot] if slot is not None else []

    def scan_click(self, data: dict) -> dict:
        """Ein Klick auf dem Bild — was er tut, hängt am Modus.

        Die Koordinaten kommen in **Bildschirm**-Pixeln an; die Umrechnung aus
        der Anzeige macht die Seite, weil nur sie weiss, wie gross das Bild
        gerade dargestellt wird.
        """
        self._scan_load()
        if self.scan_modus != MODUS_WAHL:
            gesperrt = self._scan_requirement(data)
            if gesperrt is not None:
                return gesperrt
        try:
            x, y = int((data or {})["x"]), int((data or {})["y"])
        except (KeyError, TypeError, ValueError):
            return self._scan_report("Klick ohne Stelle — ignoriert.", "err")

        if self.scan_modus == MODUS_SLOT:
            return self._click_slot(x, y)
        if self.scan_modus == MODUS_MESSEN:
            return self._click_measure(x, y)
        if self.scan_modus == MODUS_KLICK:
            return self._click_clickpoint(x, y)
        if self.scan_modus == MODUS_BEREICH:
            return self._click_area(x, y)
        if self.scan_modus == MODUS_FINDEN:
            return self._click_find(x, y)
        if self.scan_modus == MODUS_REGION:
            return self._click_region(x, y)
        if self.scan_modus == MODUS_AKTION:
            return self._click_action(x, y)
        return self._click_select(x, y, bool((data or {}).get("zusatz")))

    def _click_slot(self, x: int, y: int) -> dict:
        """Zwei Ecken ergeben einen Slot — der Weg, den der Nutzer verlangt hat.

        Zwei Klicks statt Ziehen: beim Ziehen verrutscht die Ecke um ein paar
        Pixel, und bei einem Slot von 60 px Kantenlänge schneidet das schon das
        Symbol an. Zwischen den Klicks zeigt die Ansicht das entstehende
        Rechteck.
        """
        if self._ecke is None:
            self._ecke = (x, y)
            return self._scan_report("Erste Ecke gesetzt — jetzt die zweite.", "info")
        x1, y1, x2, y2 = normalize_region(self._ecke[0], self._ecke[1], x, y)
        self._ecke = None
        # **Ein Slot von 2×2 px ist nie gewollt, sondern ein Doppelklick.** Er
        # entstand trotzdem — und war danach kaum wieder loszuwerden, weil man
        # ihn im Bild nicht mehr traf. Ihn gar nicht erst anzulegen ist die
        # Reparatur, die keine Bedienoberfläche kostet.
        if x2 - x1 < MIN_SLOT or y2 - y1 < MIN_SLOT:
            return self._scan_report(
                f"Zu klein ({x2 - x1}×{y2 - y1} px, mindestens {MIN_SLOT}) — "
                "nochmal aufziehen.", "warn")

        self._remember("Slot angelegt")
        name = next_slot_name(self.slots)
        # Der Hintergrund wird an der INNEREN Ecke gemessen, nicht in der Mitte:
        # dort liegt das Item. Trifft die Messung daneben (Rahmen, Schatten),
        # korrigiert man sie mit dem Pipetten-Modus — deshalb steht sie in der
        # Meldung.
        color = self._photo_color(x1 + 2, y1 + 2)
        self.slots[name] = ItemSlot(
            name=name, scan_region=(x1, y1, x2, y2),
            click_pos=((x1 + x2) // 2, (y1 + y2) // 2),
            slot_color=color, id=self._next_slot_id())
        self.scan_art, self.scan_name = ART_SLOT, name
        self._auswahl = [name]
        self._add_to_scan(ART_SLOT, name)
        self._tool_done()
        gemessen = f" · Hintergrund {hexfarbe(color)}" if color else ""
        return self._scan_changed(
            f"{name}: {x2 - x1}×{y2 - y1} px{gemessen}")

    def _click_find(self, x: int, y: int) -> dict:
        """Erst den Suchbereich aufziehen, dann den Hintergrund zeigen.

        Gesucht wird nur im Bereich, nicht im ganzen Bild: eine Farbe ist kein Ort,
        und ein Menü im selben Grau käme sonst als Slot mit. Anders als
        `MODUS_BEREICH` schneidet er das Bild nicht zu und gilt nur für diesen
        Durchgang. Angelegt wird, was nicht schon einen Slot hat.
        """
        if self._foto is None or self._foto_info is None:
            return self._scan_report("Erst ein Bild aufnehmen.", "warn")
        if self._suchbereich is None:
            return self._search_corner(x, y)

        sx1, sy1, sx2, sy2 = self._suchbereich
        if not (sx1 <= x <= sx2 and sy1 <= y <= sy2):
            return self._scan_report(
                "Die Stelle liegt neben dem Suchbereich — hinein klicken, oder "
                "mit ESC von vorn.", "warn")
        color = self._photo_color(x, y)
        if color is None:
            return self._scan_report("Dort liegt kein Bild — erst aufnehmen.", "warn")
        if not self._has_opencv():
            return self._scan_report(
                "Das Finden braucht OpenCV: pip install opencv-python", "err")
        ausschnitt = self._photo_crop(self._suchbereich)
        if ausschnitt is None:
            return self._scan_report("Der Suchbereich liegt nicht im Bild.", "warn")

        try:
            rechtecke = self._slots_search(ausschnitt, color)
        except Exception as fehler:                     # OpenCV/NumPy-Innenleben
            return self._scan_report(f"Erkennung fehlgeschlagen: {fehler}", "err")
        if not rechtecke:
            return self._scan_report(
                f"Nichts gefunden zu {hexfarbe(color)} — auf eine LEERE Stelle im "
                "Slot klicken, nicht auf ein Item.", "warn")

        self._remember("Slots gesucht")
        target = self._existing_slot_size()
        new, dazu, schon = 0, 0, 0
        for rx, ry, rb, rh in rechtecke:
            region = self._with_inset(
                (sx1 + rx, sy1 + ry, sx1 + rx + rb, sy1 + ry + rh))
            if target is not None:
                zb, zh = target
                width, height = region[2] - region[0], region[3] - region[1]
                if abs(width - zb) <= self._GROESSE_TOLERANZ \
                        and abs(height - zh) <= self._GROESSE_TOLERANZ:
                    region = self._to_size(region, target)
            existing = self._slot_at_position(region)
            if existing is not None:
                # **Gefunden ist gefunden, auch wenn der Slot schon existiert.**
                # Bei zwei Spielen liegen die Slots des einen längst im Bestand —
                # ein zweiter Scan über demselben Inventar legte deshalb nichts
                # an, nahm aber auch nichts auf, und weil die Listen nur
                # Mitglieder zeigen, blieb er leer: „45 gefunden, alle schon da"
                # und keine einzige Marke im Bild. Wer hier sucht, meint diesen
                # Scan — also gehören die Treffer hinein, angelegt oder nicht.
                if self._add_to_scan(ART_SLOT, existing):
                    dazu += 1
                else:
                    schon += 1
                continue
            name = next_slot_name(self.slots)
            self.slots[name] = ItemSlot(
                name=name, scan_region=region,
                click_pos=((region[0] + region[2]) // 2, (region[1] + region[3]) // 2),
                slot_color=color, id=self._next_slot_id())
            self._add_to_scan(ART_SLOT, name)
            new += 1
        # Der Durchgang ist vorbei, ob er etwas angelegt hat oder nicht — also
        # endet er auch dann im Auswählen, wenn alles schon dastand. Nur bei
        # Erfolg zurückzuschalten hiesse: derselbe Klick lässt einen mal im
        # Modus stehen und mal nicht, je nach Ergebnis.
        self._suchbereich = None
        self.scan_modus = MODUS_WAHL
        if not new and not dazu:
            return self._scan_report(f"{schon} Slot(s) gefunden — alle schon da."
                                    f"{self._detect_immediately()}", "info")
        parts = []
        if new:
            parts.append(f"{new} Slot(s) angelegt")
        if dazu:
            parts.append(f"{dazu} schon vorhandene in den Scan aufgenommen")
        if schon:
            parts.append(f"{schon} war(en) schon dabei")
        return self._scan_changed(f"{', '.join(parts)} · Hintergrund {hexfarbe(color)}"
                                    f"{self._inset_hint()}"
                                    f"{self._detect_immediately()}")

    def _detect_immediately(self) -> str:
        """Prüft die frisch gefundenen Slots sofort gegen den Item-Bestand.

        Die Frage nach dem Finden ist „was davon kenne ich schon" — sonst lernt der
        nächste Schritt auch die neunzehn, die längst im Bestand liegen. Der Treffer
        ist ein Vorschlag, keine Festlegung.
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
            found, checked, _, foreign, total = self._detect_run()
        except Exception:            # OpenCV/NumPy-Innenleben — nie den Fund verlieren
            return ""
        if not checked:
            return ""
        remaining = total - found
        text = f" · davon {found} mit bekanntem Item"
        if remaining:
            text += f", {remaining} noch unbekannt"
        if foreign:
            text += f" ({foreign} gehören noch nicht zu diesem Scan)"
        return text

    def _search_corner(self, x: int, y: int) -> dict:
        """Die zwei Ecken um das Inventar — der erste Teil von `finden`."""
        if self._ecke is None:
            self._ecke = (x, y)
            return self._scan_report(
                "Suchbereich: erste Ecke um das Inventar — jetzt die zweite.", "info")
        x1, y1, x2, y2 = normalize_region(self._ecke[0], self._ecke[1], x, y)
        self._ecke = None
        if x2 - x1 < 8 or y2 - y1 < 8:
            return self._scan_report("Zu klein — nochmal aufziehen.", "warn")
        self._suchbereich = (x1, y1, x2, y2)
        return self._scan_report(
            f"Suchbereich {x2 - x1}×{y2 - y1} px — jetzt auf einen LEEREN "
            "Slot-Hintergrund darin klicken.", "info")

    def _with_inset(self, region: tuple) -> tuple:
        """Zieht den Slot-Rand um `scan_slot_inset` ein.

        Die Erkennung liefert die ganze Zelle samt Rahmen; ohne Einzug lernt jedes
        Item den Rahmen mit. Nie mehr abziehen, als übrig bleiben darf. Von Hand
        aufgezogene Slots bleiben unangetastet.
        """
        from ...config import CONFIG
        width, height = region[2] - region[0], region[3] - region[1]
        einzug = min(max(0, int(CONFIG.scan_slot_inset)),
                     (min(width, height) - MIN_SLOT) // 2)
        if einzug <= 0:
            return region
        return (region[0] + einzug, region[1] + einzug,
                region[2] - einzug, region[3] - einzug)

    @staticmethod
    def _inset_hint() -> str:
        """Sagt, dass eingezogen wurde — sonst wundert man sich über die Grösse."""
        from ...config import CONFIG
        einzug = max(0, int(CONFIG.scan_slot_inset))
        return f" · Einzug {einzug} px (Einstellungen: scan_slot_inset)" if einzug else ""

    # Enger werdende Bänder für Sättigung und Helligkeit. Der erste Wert ist der
    # des Konsolen-Editors; die engeren braucht es bei dunklen Oberflächen, wo
    # Slot und Panel sich nur um wenige Stufen unterscheiden.
    _SV_STUFEN = (50, 35, 25, 18, 12, 8)

    # Ab wie viel Pixel Abweichung ein neu gefundener Slot NICHT mehr an die
    # Grösse bestehender Slots angeglichen wird (s. `_existing_slot_size`).
    # Klein gehalten: das soll nur die paar Pixel Median-Drift zwischen zwei
    # Suchdurchgängen auffangen, nicht einen Slot anderer Grösse verbiegen, der
    # aus einem anderen Grund im Scan liegt (z.B. von Hand angelegt).
    _GROESSE_TOLERANZ = 6

    def _slots_search(self, image, color: tuple) -> list:
        """Sucht die Slots mit mehreren Toleranzen und nimmt das beste Ergebnis.

        Eine feste Toleranz reicht nicht: bei dunklen Oberflächen verschmelzen Slots
        und Panel zu einer Fläche. Es gewinnt der Durchgang mit den meisten
        Rechtecken; ein Rechteck über mehr als der halben Fläche zählt nie mit — das
        ist das Panel.
        """
        from ...config import CONFIG
        flaeche = image.width * image.height
        bestes: list = []
        for sv in self._SV_STUFEN:
            rechtecke, _ = detect_slots_in_image(
                image, color, CONFIG.scan_slot_hsv_tolerance, sv_tolerance=sv)
            rechtecke = [r for r in rechtecke if r[2] * r[3] * 2 <= flaeche]
            if len(rechtecke) > len(bestes):
                bestes = rechtecke
        return bestes

    def _existing_slot_size(self) -> Optional[tuple]:
        """Zielgrösse für neu gefundene Slots, wenn schon welche im Scan liegen.

        `detect_slots_in_image()` normalisiert je Durchgang auf den Median — ein
        zweiter Lauf weicht deshalb ein paar Pixel ab, obwohl die Slots gleich gross
        sind. Bezug ist der offene Scan, nie der Bestand: zwei Bedienflächen
        desselben Spiels sind wirklich verschieden hoch. Leerer Scan = kein Bezug.
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
    def _to_size(region: tuple, size: tuple) -> tuple:
        """Zentriert `region` auf `size`, ohne die Mitte zu verschieben."""
        zb, zh = size
        cx, cy = (region[0] + region[2]) // 2, (region[1] + region[3]) // 2
        return (cx - zb // 2, cy - zh // 2, cx - zb // 2 + zb, cy - zh // 2 + zh)

    def _slot_at_position(self, region: tuple) -> Optional[str]:
        """Der Name des Slots an dieser Stelle, sonst `None`. Mitte zählt.

        Nicht auf Gleichheit prüfen — die Erkennung normalisiert auf den Median. Den
        Namen, weil der Suchdurchgang einen vorhandenen Slot in den Scan aufnimmt.
        """
        mx, my = (region[0] + region[2]) // 2, (region[1] + region[3]) // 2
        for s in self.slots.values():
            r = s.scan_region
            if r and r[0] <= mx <= r[2] and r[1] <= my <= r[3]:
                return s.name
        return None

    def _click_measure(self, x: int, y: int) -> dict:
        slot = self._selected_slot()
        if slot is None:
            return self._scan_report("Erst einen Slot wählen.", "warn")
        color = self._photo_color(x, y)
        if color is None:
            return self._scan_report("Dort liegt kein Bild — erst aufnehmen.", "warn")
        self._remember("Hintergrundfarbe gemessen")
        slot.slot_color = color
        self._tool_done()
        return self._scan_changed(f"{slot.name}: Hintergrund {hexfarbe(color)}")

    def _click_clickpoint(self, x: int, y: int) -> dict:
        slot = self._selected_slot()
        if slot is None:
            return self._scan_report("Erst einen Slot wählen.", "warn")
        self._remember("Klickpunkt gesetzt")
        slot.click_pos = (x, y)
        self._tool_done()
        return self._scan_changed(f"{slot.name}: Klickpunkt ({x}, {y})")

    def _click_select(self, x: int, y: int, zusatz: bool = False) -> dict:
        """Den kleinsten Slot unter der Stelle auswählen.

        Den kleinsten, nicht den obersten: ein Winzling in einem grossen Slot wäre
        sonst nie zu treffen und damit nie zu löschen. Trefferfläche mindestens
        `TREFFER_MIN` px — der Slot selbst bleibt, wie er ist.

        Daneben klicken zieht ein Auswahl-Rechteck auf; `zusatz` (STRG) nimmt einen
        einzelnen dazu oder heraus.
        """
        if self._ecke is not None:
            return self._frame_selection(x, y)
        selected = self._slot_under(x, y)
        if selected is None:
            # Nichts getroffen: das ist der Anfang eines Rechtecks, nicht
            # „nichts". Aufgehoben wird die Auswahl mit ESC oder mit einem
            # Rechteck, in dem nichts liegt.
            self._ecke = (x, y)
            return self._scan_report(
                "Auswahl-Rechteck: zweite Ecke — oder ESC.", "info")
        if zusatz:
            return self._selection_toggle(selected)
        self.scan_art = ART_SLOT
        self.scan_name = selected
        self._auswahl = [selected]
        return self.scan_data()

    def _slot_under(self, x: int, y: int) -> Optional[str]:
        """Der Name des Slots an dieser Stelle — der KLEINSTE, nicht der oberste.

        Steht als eigene Funktion da, seit es mehr als einen Anlass gibt, sie zu
        stellen: das Auswählen, der ALT-Klick (Farbe messen) und der Doppelklick
        (Klickpunkt). Dreimal ausgeschrieben wären es drei Regeln, die
        auseinanderlaufen — und dann träfe derselbe Zeiger je nach Handgriff
        einen anderen Slot.
        """
        selected, kleinste = None, None
        for slot in self.slots.values():
            x1, y1, x2, y2 = self._hit_area(slot.scan_region)
            if not (x1 <= x <= x2 and y1 <= y <= y2):
                continue
            flaeche = ((slot.scan_region[2] - slot.scan_region[0]) *
                       (slot.scan_region[3] - slot.scan_region[1]))
            if kleinste is None or flaeche <= kleinste:
                selected, kleinste = slot.name, flaeche
        return selected

    def scan_direct(self, data: dict) -> dict:
        """Farbe messen bzw. Klickpunkt setzen, OHNE vorher den Modus zu wechseln.

        Ein Modus lohnt sich, solange man dasselbe zwanzigmal tut; eine einzelne
        Korrektur am Slot unter dem Zeiger ist das Gegenteil davon.
        `messen` = ALT-Klick, `klick` = Doppelklick. Beides wählt den Slot mit aus.
        """
        gesperrt = self._scan_requirement({"kind": "item"})
        if gesperrt is not None:
            return gesperrt
        try:
            x, y = int((data or {})["x"]), int((data or {})["y"])
        except (KeyError, TypeError, ValueError):
            return self._scan_report("Klick ohne Stelle — ignoriert.", "err")
        was = str((data or {}).get("was") or "")
        name = self._slot_under(x, y)
        if name is None:
            return self._scan_report("Dort liegt kein Slot.", "info")
        self.scan_art, self.scan_name = ART_SLOT, name
        self._auswahl = [name]
        if was == "messen":
            return self._click_measure(x, y)
        if was == "klick":
            return self._click_clickpoint(x, y)
        return self._scan_report(f"Unbekannter Handgriff '{was}'.", "err")

    def _frame_selection(self, x: int, y: int) -> dict:
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
            return self._scan_report("Nichts im Rechteck — Auswahl aufgehoben.", "info")
        return self._scan_report(f"{len(drin)} Slot(s) gewählt — „löschen“ "
                                "(oder Entf) nimmt alle.", "info")

    def _selection_toggle(self, name: str) -> dict:
        """STRG-Klick: einen Slot zur Auswahl dazu oder heraus."""
        if name in self._auswahl:
            self._auswahl.remove(name)
            if self.scan_name == name:
                self.scan_name = self._auswahl[0] if self._auswahl else ""
        else:
            self._auswahl.append(name)
            self.scan_name = name
        self.scan_art = ART_SLOT
        return self.scan_data()

    @staticmethod
    def _hit_area(region: tuple) -> tuple:
        """Das Rechteck, mit dem ein Klick verglichen wird — nie unter TREFFER_MIN."""
        x1, y1, x2, y2 = region
        wx = max(0, (TREFFER_MIN - (x2 - x1)) // 2)
        wy = max(0, (TREFFER_MIN - (y2 - y1)) // 2)
        return (x1 - wx, y1 - wy, x2 + wx, y2 + wy)

    def scan_cancel(self, data: Optional[dict] = None) -> dict:
        """ESC: halb gesetzte Ecke und Auswahl verwerfen, zurück ins Auswählen."""
        self._ecke = None
        self._suchbereich = None
        self._auswahl = []
        self._lern_review = []
        self._region_ziel = None
        self.scan_modus = MODUS_WAHL
        return self.scan_data()

    # ----------------------------------------------------------------- Slots

    def scan_slot_set(self, data: dict) -> dict:
        """Ein Feld eines Slots setzen — Aktiv, Name, Region, Klickpunkt, Farbe."""
        name = str((data or {}).get("name") or "")
        feld = str((data or {}).get("feld") or "")
        value = (data or {}).get("value")
        slot = self.slots.get(name)
        if slot is None:
            return self._scan_report(f"Slot '{name}' gibt es nicht.", "err")

        # **Gemerkt wird pro Zweig, nicht oben am Eingang.** Ein Feld, das
        # abgelehnt wird oder denselben Wert noch einmal bekommt, legte sonst
        # einen Schritt auf den Stapel, der nichts zurückzunehmen hat — und
        # STRG+Z täte einmal scheinbar gar nichts. Ein Rückgängig, dem man nicht
        # trauen kann, ist kaum besser als keins.
        if feld == "name":
            return self._slot_rename(slot, str(value or "").strip())
        if feld == "active":
            new = bool(value)
            if slot.enabled == new:
                return self.scan_data()
            self._remember(f"'{name}': {'ein' if new else 'aus'}")
            slot.enabled = new
            return self._scan_changed(
                f"{slot.name} ist {'eingeschaltet' if new else 'ausgeschaltet'}.")
        if feld == "color":
            self._remember(f"'{name}': Hintergrundfarbe")
            slot.slot_color = rgbwert(value)
            return self._scan_changed(f"{slot.name}: Hintergrund {value or 'entfernt'}")
        if feld in ("x1", "y1", "x2", "y2"):
            self._remember(f"'{name}': Fläche")
            values = list(slot.scan_region)
            values[("x1", "y1", "x2", "y2").index(feld)] = int(value or 0)
            slot.scan_region = normalize_region(*values)
            return self._scan_changed()
        if feld in ("kx", "ky"):
            self._remember(f"'{name}': Klickpunkt")
            kx, ky = slot.click_pos
            slot.click_pos = (int(value or 0), ky) if feld == "kx" else (kx, int(value or 0))
            return self._scan_changed()
        return self._scan_report(f"Unbekanntes Feld '{feld}'.", "err")

    def _slot_rename(self, slot: ItemSlot, new: str) -> dict:
        """Umbenennen heisst hier: die Referenz in jedem Scan mitziehen.

        Ein Slot wird **per Name** referenziert — der Name IST die Referenz.
        Ohne das Nachziehen zeigte jeder Scan danach ins Leere, und zwar
        stillschweigend: er liefe mit einem Slot weniger weiter.
        """
        if not new or new == slot.name:
            return self.scan_data()
        if new in self.slots:
            return self._scan_report(f"'{new}' gibt es schon.", "warn")
        self._remember(f"'{slot.name}' umbenannt")
        old = slot.name
        self.slots = {(new if k == old else k): v for k, v in self.slots.items()}
        slot.name = new
        self._sync_objects()
        self.scan_name = new
        return self._scan_changed(f"'{old}' heisst jetzt '{new}'")

    def scan_slot_delete(self, data: Optional[dict] = None) -> dict:
        """Löscht die gewählten Slots — einen oder die ganze Auswahl.

        **Die Sammel-Aktion arbeitet auf der Auswahl, nicht auf einem Slot** —
        dieselbe Regel wie im Sequenz-Editor. Ein Rechteck um dreissig Slots und
        ein Griff, statt dreissigmal auswählen und löschen.
        """
        names = [s.name for s in self._selection_slots()]
        if not names:
            return self._scan_report("Kein Slot gewählt.", "warn")
        self._remember(f"{len(names)} Slot(s) gelöscht" if len(names) > 1
                    else f"'{names[0]}' gelöscht")
        for name in names:
            del self.slots[name]
            self._treffer.pop(name, None)
        self._sync_objects()
        self.scan_name = ""
        self._auswahl = []
        was = f"'{names[0]}'" if len(names) == 1 else f"{len(names)} Slots"
        return self._scan_changed(f"{was} gelöscht", "warn")

    def scan_move(self, data: dict) -> dict:
        """Schiebt die gewählten Slots um `dx`/`dy` Pixel — Fläche und Klickpunkt.

        Der Klickpunkt geht mit, statt neu aus der Mitte gerechnet zu werden: er ist
        womöglich bewusst aus der Mitte gesetzt.

        `zaehlt=False` unterdrückt den Rückgängig-Schritt — eine gehaltene Pfeiltaste
        ist EIN Verschieben, nicht dreissig.
        """
        try:
            dx, dy = int((data or {}).get("dx") or 0), int((data or {}).get("dy") or 0)
        except (TypeError, ValueError):
            return self._scan_report("Verschieben ohne Weite — ignoriert.", "err")
        if not dx and not dy:
            return self.scan_data()
        slots = self._selection_slots()
        if not slots:
            return self._scan_report("Kein Slot gewählt.", "warn")
        # Nur der erste Schritt einer Serie kommt auf den Stapel: STRG+Z soll
        # das ganze Verschieben zurücknehmen, nicht dessen letzten Pixel.
        if (data or {}).get("counts", True):
            self._remember(f"{len(slots)} Slot(s) verschoben" if len(slots) > 1
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
        return self._scan_changed(f"{was} um ({dx:+d}, {dy:+d}) verschoben.")

    def scan_align_size(self, data: Optional[dict] = None) -> dict:
        """Zieht die gewählten Slots auf dieselbe Grösse, um ihre Mitte herum.

        Bezug ist der Median der Auswahl, nicht der grösste oder kleinste: ein
        einzelner Verklicker soll nicht alle anderen verbiegen.
        """
        slots = self._selection_slots()
        if len(slots) < 2:
            return self._scan_report(
                "Dafür braucht es mehrere Slots — im Bild ein Rechteck aufziehen.", "warn")
        breiten = sorted(s.scan_region[2] - s.scan_region[0] for s in slots)
        hoehen = sorted(s.scan_region[3] - s.scan_region[1] for s in slots)
        target = (breiten[len(breiten) // 2], hoehen[len(hoehen) // 2])
        self._remember(f"{len(slots)} Slot(s) angeglichen")
        changed = 0
        for slot in slots:
            old = tuple(slot.scan_region)
            new = self._to_size(old, target)
            if new != old:
                slot.scan_region = new
                self._treffer.pop(slot.name, None)
                changed += 1
        return self._scan_changed(
            f"{changed} von {len(slots)} Slot(s) auf {target[0]}×{target[1]} px gezogen.")

    def scan_selection_color(self, data: Optional[dict] = None) -> dict:
        """Misst den Hintergrund jedes gewählten Slots neu — jeden an sich selbst.

        Nicht eine Farbe für alle: Inventare sind selten gleichmässig ausgeleuchtet,
        und eine gemeinsame Farbe verschöbe die Lernmaske an jedem Slot ein bisschen.
        """
        slots = self._selection_slots()
        if not slots:
            return self._scan_report("Kein Slot gewählt.", "warn")
        if self._foto is None:
            return self._scan_report("Erst ein Bild aufnehmen.", "warn")
        self._remember(f"Hintergrund von {len(slots)} Slot(s) gemessen")
        gemessen, daneben = 0, 0
        for slot in slots:
            color = self._photo_color(slot.scan_region[0] + 2, slot.scan_region[1] + 2)
            if color is None:
                daneben += 1
                continue
            slot.slot_color = color
            gemessen += 1
        remainder = f", {daneben} liegen ausserhalb des Bildes" if daneben else ""
        return self._scan_changed(f"{gemessen} Hintergrundfarbe(n) gemessen{remainder}.")

