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
        if modus not in MODI_ALLE:
            return self._scan_melde(f"Unbekannter Modus '{modus}'.", "err")
        # Region und Aktionspunkt gehören den Erkennungs-Scans und brauchen ein
        # Ziel; das setzt `region_modus()`. Hier landen sie nur, wenn jemand den
        # Buchstaben drückt, während gar kein Boss-/Icon-Scan offen ist.
        if modus in (MODUS_REGION, MODUS_AKTION) and not self._region_ziel:
            return self._scan_melde(
                "Erst einen Boss- bzw. Icon-Scan öffnen.", "warn")
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
        if self.scan_modus == MODUS_REGION:
            return self._klick_region(x, y)
        if self.scan_modus == MODUS_AKTION:
            return self._klick_aktion(x, y)
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
        self._region_ziel = None
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
