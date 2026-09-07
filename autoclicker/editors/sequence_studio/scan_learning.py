"""Item-Lernen, Vorschau und Erkennung im Scan-Editor."""

import base64
import io
from typing import Optional

from ...models import ItemProfile, ItemScanConfig, ItemSlot
from ...utils import eindeutiger_name
from .model import hexfarbe
from .scan_contract import ART_ITEM
from .scan_model import existing_categories, next_item_name, save_template


class ScanLearningMixin:
    """Lernt Item-Profile und prüft sie mit derselben Logik wie die Laufzeit."""

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
            return self._scan_melde(
                "Kein Item in diesem Slot — leer oder ohne Bild.", "info")
        self.scan_art, self.scan_name = ART_ITEM, gelernt
        self._dazu(ART_ITEM, gelernt)
        return self._scan_geaendert(f"'{gelernt}' aus '{slot.name}' gelernt.")

    def scan_items_lernen(self, daten: Optional[dict] = None) -> dict:
        """Aus jedem Slot ein Item — Doppelte werden übersprungen.

        Der Weg für ein volles Inventar: einmal drücken statt zwanzigmal. Die
        Doppel-Erkennung braucht OpenCV.

        „Alle" heisst die Slots des offenen Scans (`_scan_slots()`), nicht den ganzen
        Bestand — sonst liefe der Durchgang bei zwei Spielen auch über die Slots des
        anderen, die ausserhalb des Bildes liegen.
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
            teile.append(f"{leer} leer oder ohne Bild")
        return self._scan_geaendert("Gelernt: " + ", ".join(teile))

    def _lerne_aus_slot(self, slot: ItemSlot, dedup: bool = False) -> Optional[str]:
        """Der Name des neuen Items, `""` bei einem Duplikat, `None` ohne Bild."""
        crop = self._foto_crop(slot.scan_region)
        if crop is None:
            return None
        from ..item_editor.markers import (
            _find_matching_existing_item, _prepare_learning_image,
        )
        from ...config import CONFIG
        maskiert, marker, ist_leer = _prepare_learning_image(crop, slot.slot_color)
        if ist_leer:
            return None
        if dedup and self.items:
            if _find_matching_existing_item(crop, list(self.items.items()),
                                            CONFIG.scan_min_confidence,
                                            self.filepath.parent / "templates"):
                return ""
        name = next_item_name(self.items)
        # Template UND Marker sehen dieselbe maskierte Flaeche als Item an.
        self.items[name] = ItemProfile(
            name=name,
            marker_colors=[tuple(c) for c in marker],
            category=None,
            # Hinter das bisher letzte, nicht `len + 1`: nach dem Löschen eines Items
            # vergäbe das eine Priorität, die es schon gibt — und die Reihenfolge, in
            # der der Scan klickt, wäre an dieser Stelle Zufall.
            priority=max((i.priority for i in self.items.values()), default=0) + 1,
            template=save_template(maskiert, name,
                                   template_dir=self.filepath.parent / "templates"),
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
            _prepare_learning_image,
        )
        from ...config import CONFIG

        review = []
        leere_slots = 0
        vergeben = set(self.items)
        for slot in slots:
            crop = self._foto_crop(slot.scan_region)
            if crop is None:
                continue
            maskiert, _marker, ist_leer = _prepare_learning_image(
                crop, slot.slot_color)
            if ist_leer:
                leere_slots += 1
                continue
            treffer = (_find_matching_existing_item(
                crop, list(self.items.items()), CONFIG.scan_min_confidence,
                self.filepath.parent / "templates")
                if self._hat_opencv() else None)
            kompatibel = bool(
                treffer and _item_has_compatible_template(
                    self.items[treffer], crop, self.filepath.parent / "templates"))
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
            # Der Arbeitsbestand gehört bereits vollständig zum offenen Scan.
            # Es gibt keine zweite Mitgliedschaft mehr.
            im_scan = bool(treffer)
            kann_hinzufuegen = False
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
            if leere_slots:
                return self._scan_melde(
                    f"{leere_slots} leere Slot(s) übersprungen — nichts zu lernen.",
                    "info")
            return self._scan_melde("Keiner der Slots liegt im Screenshot.", "warn")
        doppelt = sum(bool(z["duplikat"]) for z in review)
        varianten = sum(bool(z["variante"]) for z in review)
        teile = []
        if doppelt:
            teile.append(f"{doppelt} bereits gelernt")
        if varianten:
            teile.append(f"{varianten} neue Grössenvariante(n)")
        if leere_slots:
            teile.append(f"{leere_slots} leere übersprungen")
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
        """Verwendet bei gleicher Schreibweise die bereits bekannte Kategorie.

        Leerraum zaehlt nicht mit; darueber hinaus wird NICHTS geraten. Ein getipptes
        Wort stillschweigend in ein aehnliches zu aendern ist schlimmer als der
        Tippfehler — Items derselben Kategorie konkurrieren miteinander, eine
        getrennte verliert still ihre Gruppe.
        """
        neu = " ".join(str(wert or "").split())
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

        ausgewaehlt = [
            zeile for zeile in self._lern_review if ist_ausgewaehlt(zeile)
        ]
        if not ausgewaehlt:
            self._lern_review = []
            return self._scan_melde(
                "Keine Items ausgewählt; nichts gelernt oder geändert.", "info")

        from ..item_editor.markers import _collect_markers_silent
        from ...config import CONFIG
        self._merke("Item-Auswahl der Lernvorschau uebernommen")
        neu = []
        varianten = []
        unveraendert = set()
        bearbeitet = []
        metadaten_gesetzt = set()

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
                if _item_has_compatible_template(
                        vorhanden, crop, self.filepath.parent / "templates"):
                    self._objekte_angleichen()
                    if basis not in bearbeitet:
                        unveraendert.add(basis)
                    continue
                datei = save_template(crop, basis,
                                      template_dir=self.filepath.parent / "templates")
                if datei:
                    if vorhanden.template:
                        vorhanden.template_variants.append(datei)
                    else:
                        vorhanden.template = datei
                    if basis not in varianten:
                        varianten.append(basis)
                    self._objekte_angleichen()
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
                template=save_template(crop, name,
                                       template_dir=self.filepath.parent / "templates"),
                min_confidence=CONFIG.scan_min_confidence,
            )
            self._dazu(ART_ITEM, name)
            neu.append(name)
        self._lern_review = []
        gewaehlt = neu + varianten + bearbeitet
        if gewaehlt:
            self.scan_art, self.scan_name = ART_ITEM, gewaehlt[0]
        teile = []
        if neu:
            teile.append(f"{len(neu)} neue Item(s)")
        if varianten:
            teile.append(f"{len(varianten)} Grössenvariante(n) ergänzt")
        if bearbeitet:
            teile.append(f"{len(bearbeitet)} bestehende Item(s) bearbeitet")
        if unveraendert:
            teile.append(f"{len(unveraendert)} bereits vollständig eingerichtet")
        text = ", ".join(teile) + "." if teile else "Keine Änderungen."
        return self._scan_geaendert(text)

    def scan_item_setzen(self, daten: dict) -> dict:
        """Ein Feld eines Items — Aktiv, Name, Kategorie, Priorität, Konfidenz."""
        name = str((daten or {}).get("name") or "")
        feld = str((daten or {}).get("feld") or "")
        wert = (daten or {}).get("wert")
        item = self.items.get(name)
        if item is None:
            return self._scan_melde(f"Item '{name}' gibt es nicht.", "err")

        if feld == "name":
            return self._item_umbenennen(item, str(wert or "").strip())
        if feld == "aktiv":
            neu = bool(wert)
            if item.enabled == neu:
                return self.scan_daten()
            self._merke(f"'{name}': {'ein' if neu else 'aus'}")
            item.enabled = neu
            return self._scan_geaendert(
                f"{item.name} ist {'eingeschaltet' if neu else 'ausgeschaltet'}.")
        if feld == "kategorie":
            self._merke(f"'{name}': Kategorie")
            item.category = self._kategorie_normalisieren(wert)
            # **Ein Rang, den es schon gibt, ist kein Rang.** Items derselben
            # Kategorie konkurrieren miteinander; bei gleicher Zahl entscheidet
            # die Scan-Reihenfolge, also der Zufall. Wer ein Item in eine
            # Kategorie schiebt, hat über seine Priorität nichts gesagt — dann
            # ist der nächste freie Platz die einzige Antwort, die nicht rät.
            # Eine ausdrücklich getippte Zahl bleibt dagegen stehen (der Zweig
            # 'prioritaet' unten fasst sie nicht an).
            frei = self._freie_prioritaet(item)
            if frei is None:
                return self._scan_geaendert()
            alt = item.priority
            item.priority = frei
            return self._scan_geaendert(
                f"{name}: P{alt} war in '{item.category}' vergeben — jetzt P{frei}.")
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
        if feld == "bestaetigung":
            # Leer heisst „keine Bestätigung" — und das ist etwas anderes als
            # Punkt 0. Ein Punkt, den es nicht gibt, wird abgelehnt statt still
            # gesetzt: sonst klickte der Lauf auf (0, 0).
            if wert in (None, "", "0", 0):
                self._merke(f"'{name}': Bestätigungsklick")
                item.confirm_point_id = None
                item.confirm_point = None
                return self._scan_geaendert(f"{name}: kein Bestätigungsklick mehr.")
            try:
                punkt_id = int(wert)
            except (TypeError, ValueError):
                return self._scan_melde("Der Bestätigungsklick braucht einen Punkt.",
                                        "err")
            if not any(p.id == punkt_id for p in self.points):
                return self._scan_melde(f"Punkt #{punkt_id} gibt es nicht.", "err")
            self._merke(f"'{name}': Bestätigungsklick")
            item.confirm_point_id = punkt_id
            self._bestaetigung_anwenden(item)
            return self._scan_geaendert(f"{name}: bestätigt über Punkt #{punkt_id}.")
        if feld == "bestaetigung_verzoegerung":
            try:
                zahl = float(wert)
            except (TypeError, ValueError):
                return self._scan_melde("Die Wartezeit muss eine Zahl sein.", "err")
            if zahl < 0:
                return self._scan_melde("Die Wartezeit kann nicht negativ sein.", "err")
            self._merke(f"'{name}': Wartezeit vor der Bestätigung")
            item.confirm_delay = zahl
            return self._scan_geaendert()
        return self._scan_melde(f"Unbekanntes Feld '{feld}'.", "err")

    def _bestaetigung_anwenden(self, item) -> None:
        """Zieht `confirm_point` an der Referenz nach — abgeleiteter Arbeitswert.

        Dieselbe Rolle wie `_aktion_punkt_anwenden()` bei Boss und Icon: die
        Koordinate steht in der Punktliste der `sequence.json`, der Serializer schreibt sie hier
        nicht, und gefüllt wird sie nur, damit die Anzeige etwas zu zeigen hat.
        """
        from ...models import ClickPoint
        punkt = next((p for p in self.points if p.id == item.confirm_point_id), None)
        item.confirm_point = (ClickPoint(x=punkt.x, y=punkt.y, name=punkt.name or "")
                              if punkt else None)

    def _freie_prioritaet(self, item: ItemProfile) -> Optional[int]:
        """Der nächste freie Rang der Kategorie — oder None, wenn keiner nötig.

        Nur bei einer echten Kollision: sitzt das Item allein auf seiner Zahl,
        wird nichts verschoben. Ohne Kategorie gibt es keine Konkurrenz.
        """
        if not item.category:
            return None
        vergeben = {int(i.priority) for i in self.items.values()
                    if i is not item and i.category == item.category}
        if int(item.priority) not in vergeben:
            return None
        rang = 1
        while rang in vergeben:
            rang += 1
        return rang

    def _item_umbenennen(self, item: ItemProfile, neu: str, merken: bool = True) -> dict:
        """Wie beim Slot: der Name ist die Referenz, also ziehen die Scans mit.

        `merken=False` ist fuer Sammel-Aktionen da: wer sechsundfuenfzig Items
        in einem Durchgang benennt, legt EINEN Stand vorher ab statt
        sechsundfuenfzig einzelne — der Stapel ist dreissig tief, und der
        Zustand vor dem Durchgang waere sonst als Erstes herausgefallen. Genau
        der Stand, auf den man ihn zurueckdrehen will.
        """
        if not neu or neu == item.name:
            return self.scan_daten()
        if neu in self.items:
            return self._scan_melde(f"'{neu}' gibt es schon.", "warn")
        if merken:
            self._merke(f"'{item.name}' umbenannt")
        alt = item.name
        self.items = {(neu if k == alt else k): v for k, v in self.items.items()}
        item.name = neu
        self._objekte_angleichen()
        self.scan_name = neu
        return self._scan_geaendert(f"'{alt}' heisst jetzt '{neu}'")

    def scan_item_loeschen(self, daten: Optional[dict] = None) -> dict:
        name = self.scan_name if self.scan_art == ART_ITEM else ""
        item = self.items.get(name)
        if item is None:
            return self._scan_melde("Kein Item gewählt.", "warn")
        self._merke(f"'{name}' gelöscht")
        del self.items[name]
        self._objekte_angleichen()
        self.scan_name = ""
        # Das Template bleibt liegen: es kann zu einem Boss gehören (beide
        # teilen sich den lokalen Template-Ordner), und eine Datei zu löschen, die einem
        # anderen gehört, ist der stille Datenverlust, den es hier nicht gibt.
        return self._scan_geaendert(f"'{name}' gelöscht.", "warn")

    def scan_item_vorlage_entfernen(self, daten: Optional[dict] = None) -> dict:
        """Löst eine fehlerhafte Vorlage vom Item, ohne fremde Dateien zu löschen."""
        daten = daten or {}
        name = str(daten.get("name") or self.scan_name)
        datei = str(daten.get("datei") or "")
        item = self.items.get(name)
        if item is None or datei not in item.template_names():
            return self._scan_melde("Vorlage nicht gefunden.", "err")
        self._merke(f"'{name}': Vorlage entfernt")
        if item.template == datei:
            varianten = [v for v in item.template_variants if v != datei]
            item.template = varianten.pop(0) if varianten else None
            item.template_variants = varianten
        else:
            item.template_variants = [v for v in item.template_variants if v != datei]
        self._vorschau.pop(datei, None)
        return self._scan_geaendert(
            f"Vorlage '{datei}' von '{name}' entfernt. Die Bilddatei bleibt als Sicherung bestehen.",
            "warn")

    def _katalog(self):
        """Der Katalog DIESES Scans — leer, wenn er ihn nicht benutzt.

        Zwei Schalter, und sie beantworten verschiedene Fragen: `scan_catalog_file`
        sagt, WO der Katalog liegt (eine Datei je Spiel, also programmweit),
        `ItemScanConfig.use_catalog` sagt, OB dieser Scan ihn benutzt. Wer zwei
        Spiele betreibt, hat einen Katalog, der nur fuer eines von beiden gilt —
        dieselbe Ueberlegung wie bei der Laufrichtung.

        Die Config wird frisch gelesen und nicht gemerkt: der Pfad steht im
        Einstellungen-Reiter desselben Fensters, und ein Katalog, der erst nach
        einem Neustart greift, ist der Fall, in dem man den Knopf fuer kaputt
        haelt. `lade_katalog` haengt seinen Cache ohnehin am Dateistand.
        """
        from ...katalog import LEER
        katalog, _grund = self._katalog_pruefen()
        return katalog if katalog is not None else LEER

    def _katalog_pruefen(self):
        """(Katalog, Grund) — genau einer von beiden ist gesetzt.

        Drei Gruende, und sie auseinanderzuhalten ist der ganze Zweck: bei
        "Schalter aus" sucht man sonst die Datei, und bei "keine Datei" den
        Schalter.
        """
        # `CONFIG` statt `load_config()`: diese Pruefung laeuft bei JEDER
        # Momentaufnahme, also nach jedem Klick — ein Dateizugriff pro Klick
        # waere zu teuer. Das Objekt haelt der Einstellungen-Reiter aktuell
        # (`config_schreiben` ruft `uebernehmen(CONFIG, …)` auf dem eigenen
        # Prozess), und `lade_katalog` haengt seinen Cache am Dateistand.
        from ...config import CONFIG
        from ...katalog import lade_katalog

        cfg = self.scans.get(self.scan_offen)
        if cfg is None:
            return None, ("Erst einen Item-Scan öffnen — der Katalog wird je Scan "
                          "ein- und ausgeschaltet.")
        if not cfg.use_catalog:
            return None, (f"'{cfg.name}' benutzt den Katalog nicht. Der Schalter steht "
                          "in den Scan-Einstellungen (Scan-Maske aufklappen).")
        pfad = CONFIG.scan_catalog_file
        if not pfad:
            return None, ("Keine Katalog-Datei eingetragen — Einstellungen → "
                          "SCAN-EINSTELLUNGEN → 'Item-Katalog', dort holt der "
                          "Knopf 'Katalog aus der Spiel-API holen' sie und "
                          "trägt den Pfad gleich ein.")
        katalog = lade_katalog(pfad)
        if not katalog:
            return None, f"Katalog '{pfad}' ist leer oder nicht lesbar."
        return katalog, None

    def _katalog_ziel(self, daten: Optional[dict]) -> list:
        """Worauf eine Katalog-Aktion wirkt: die Auswahl, sonst der offene Scan.

        Dieselbe Bezugsregel wie bei jeder Sammel-Aktion des Reiters
        (`_scan_slots()`/`_kandidaten()`) — eine ausdrueckliche Auswahl gewinnt,
        sonst gilt der offene Scan und ohne Scan der Bestand.
        """
        namen = [str(n) for n in ((daten or {}).get("namen") or [])]
        if namen:
            return [self.items[n] for n in namen if n in self.items]
        return list(self._kandidaten())

    @staticmethod
    def _katalog_name(name: str, katalog) -> str:
        """Unter welchem Namen dieses Item im Katalog steht — oder "".

        Zwei Anlaeufe, und die Reihenfolge ist die Regel: der volle Name
        gewinnt, der ohne Eindeutigkeits-Zaehler ist der Rueckfall.
        """
        from ...utils import ohne_zaehler
        if katalog.treffer(name):
            return name
        basis = ohne_zaehler(name)
        return basis if basis != name and katalog.treffer(basis) else ""

    def _katalog_plan(self, items: list, katalog) -> tuple:
        """Was sich aendern WUERDE — `(Aenderungen, bekannte Items)`.

        Getrennt vom Anwenden, damit `_merke()` nur bei einer echten Aenderung
        laeuft. Ein zweiter Klick auf denselben Knopf aendert nichts, und ein
        Rueckgaengig-Stand, der nichts zurueckdreht, ist ein STRG+Z, das
        scheinbar wirkungslos ist — danach traut man dem Stapel nicht mehr.

        `Aenderungen` ist eine Liste `(Item, Kategorie, Prioritaet)`.
        """
        from ...katalog import raenge
        # **Ein angehaengter Zaehler macht den Namen fuer den Katalog
        # unbekannt.** "Godlike Bow 2" steht dort nicht, und das Item blieb
        # deshalb ohne Kategorie neben seinem eingeordneten Zwilling stehen.
        # Erst der volle Name, dann der ohne Zaehler: was im Katalog steht,
        # gewinnt — "Slot 1" bleibt "Slot 1".
        bekannt = []
        for i in items:
            such = self._katalog_name(i.name, katalog)
            if such:
                bekannt.append((i, katalog.kategorie(such), katalog.wert(such)))
        rang = raenge([(i.name, kategorie, wert) for i, kategorie, wert in bekannt])

        aenderungen = []
        for item, kategorie, _wert in bekannt:
            neu_prio = rang.get(item.name, item.priority)
            if item.category != kategorie or item.priority != neu_prio:
                aenderungen.append((item, kategorie, neu_prio))
        return aenderungen, len(bekannt)

    @staticmethod
    def _katalog_uebernehmen(aenderungen: list) -> set:
        """Traegt den Plan ein und liefert die benutzten Kategorien."""
        kategorien = set()
        for item, kategorie, prioritaet in aenderungen:
            item.category = kategorie
            item.priority = prioritaet
            if kategorie:
                kategorien.add(kategorie)
        return kategorien

    def scan_kategorie_umbenennen(self, daten: Optional[dict] = None) -> dict:
        """Benennt eine Kategorie um — und damit JEDES Item, das sie trägt.

        **Bis hierhin ging das nur Item für Item.** Die Kategorie ist kein
        eigenes Objekt, sondern ein Feld an jedem Item; wer zwei Gruppen
        zusammenlegen wollte, musste jede Maske einzeln anfassen. Bei
        dreiundzwanzig Kategorien auf sechsundfünfzig Items ist das kein Weg —
        und Zusammenlegen ist der Normalfall, weil der Katalog bewusst ENG
        einordnet (dreizehn dieser Kategorien haben genau ein Item).

        Ein leerer Zielname nimmt die Kategorie weg; ein leerer Quellname
        meint die Gruppe „ohne Kategorie". Beides ist dieselbe Bewegung.
        """
        alt = self._kategorie_normalisieren((daten or {}).get("alt")) or None
        neu = self._kategorie_normalisieren((daten or {}).get("neu")) or None
        if alt == neu:
            return self.scan_daten()
        betroffen = [i for i in self.items.values() if (i.category or None) == alt]
        if not betroffen:
            return self._scan_melde(
                f"Keine Items in '{alt or 'ohne Kategorie'}'.", "warn")

        self._merke(f"Kategorie '{alt or 'ohne'}' → '{neu or 'ohne'}'")
        for item in betroffen:
            item.category = neu
        # **Zusammengelegt heisst doppelte Ränge.** Zwei Items mit P1 in
        # derselben Kategorie sind eine Rangfolge, die der Zufall entscheidet —
        # in Modus `all` gewinnt eines und das andere wird nie geklickt.
        # Dicht gemacht wird in der bisherigen Reihenfolge: die Werte des
        # Katalogs holt man sich mit „Aus Katalog einordnen", falls man sie
        # will. Ungefragt danach umzusortieren würde handgesetzte Ränge
        # überschreiben.
        neu_vergeben = self._raenge_dicht(neu, zugezogen=betroffen)
        zusatz = f", {neu_vergeben} Rang/Ränge neu vergeben" if neu_vergeben else ""
        return self._scan_geaendert(
            f"{len(betroffen)} Item(s): '{alt or 'ohne Kategorie'}' → "
            f"'{neu or 'ohne Kategorie'}'{zusatz}.")

    def _raenge_dicht(self, kategorie, zugezogen: list = None) -> int:
        """Prioritäten einer Kategorie auf 1..n ziehen — wie viele sich ändern.

        **Wer dazukommt, kommt hinten an.** Nach Priorität und Name über die
        ganze Gruppe zu sortieren wäre die naheliegende Fassung und die
        falsche: ein zugezogenes Item mit P1 schöbe sich zwischen die
        bestehenden und verschöbe deren handgesetzte Ränge. Wer eine Gruppe in
        eine andere schiebt, sagt damit nichts über die Rangfolge der
        Zielgruppe.
        """
        neu_dabei = {id(i) for i in (zugezogen or [])}
        gruppe = [i for i in self.items.values()
                  if (i.category or None) == (kategorie or None)]
        geordnet = sorted(gruppe,
                          key=lambda i: (id(i) in neu_dabei, i.priority, i.name))
        geaendert = 0
        for nr, item in enumerate(geordnet, 1):
            if item.priority != nr:
                item.priority = nr
                geaendert += 1
        return geaendert

    def scan_katalog_anwenden(self, daten: Optional[dict] = None) -> dict:
        """Setzt Kategorie und Prioritaet aus dem Katalog — ohne LLM.

        Die Kategorie haengt am NAMEN, nicht am Modell: heisst ein Item
        "Citadel Helmet", steht im Katalog "Helm", und ob den Namen ein Mensch
        getippt oder `scan_items_autoname` vorgeschlagen hat, ist gleichgueltig.
        Deshalb steht dieser Knopf auch ohne `llm_enabled` zur Verfuegung.

        Die Prioritaet wird DICHT innerhalb der bearbeiteten Menge vergeben
        (teuerstes Item einer Kategorie bekommt P1). Ein Rang aus dem Katalog
        waere global und damit unbrauchbar — der beste Bogen eines Bestands
        bekaeme P49, weil 48 teurere im Katalog stehen, die man nicht besitzt.

        Angefasst wird nur, was der Katalog wirklich kennt. Ein Item mit einem
        selbst vergebenen Namen ("item_12") behaelt, was es hat, statt in eine
        geratene Kategorie zu rutschen.
        """
        katalog, grund = self._katalog_pruefen()
        if katalog is None:
            return self._scan_melde(grund, "err")

        ziel = self._katalog_ziel(daten)
        if not ziel:
            return self._scan_melde("Keine Items ausgewählt.", "warn")

        aenderungen, bekannt = self._katalog_plan(ziel, katalog)
        if not bekannt:
            return self._scan_melde(
                f"Keiner der {len(ziel)} Namen steht im Katalog. Erst benennen — "
                "von Hand oder mit „Aus Katalog benennen“.", "warn")
        if not aenderungen:
            return self._scan_melde(
                f"{bekannt} Item(s) im Katalog gefunden — alle stehen schon richtig.",
                "info")

        self._merke("Aus Katalog eingeordnet")
        kategorien = self._katalog_uebernehmen(aenderungen)
        rest = len(ziel) - bekannt
        zusatz = f"; {rest} nicht im Katalog (unverändert)" if rest else ""
        return self._scan_geaendert(
            f"{len(aenderungen)} Item(s) in {len(kategorien)} Kategorie(n) "
            f"eingeordnet{zusatz}.")

    @staticmethod
    def _autoname_rest(ohne: int, auswahl, timeouts: int = 0) -> str:
        """Der Nachsatz der Schlussmeldung: was NICHT geklappt hat.

        Zwei Dinge, und das zweite ist das wichtigere: ohne Katalog raet das
        Modell frei und antwortet auf die deutsche Frage auch deutsch — heraus
        kommt die Art ("Bogen") statt des Gegenstands ("Godlike Bow"). Das
        sieht in der Liste wie ein Ergebnis aus, ist aber keins, das sich
        einordnen liesse. Wer es nicht dazusagt, laesst den Nutzer
        sechsundfuenfzig geratene Namen fuer echte halten.
        """
        teile = []
        if ohne:
            teile.append(f"{ohne} ohne Vorschlag")
        if timeouts:
            # Der Hinweis gehoert an die Zahl: eine Zeitueberschreitung sieht in
            # der Liste aus wie ein nicht erkanntes Item, hat aber eine ganz
            # andere Abhilfe.
            teile.append(f"{timeouts}× Zeitüberschreitung (auch beim zweiten "
                         "Versuch) — llm_timeout in den Einstellungen erhöhen")
        if not auswahl:
            teile.append("ohne Katalog frei geraten — Einstellungen → "
                         "'Item-Katalog', anlegen mit python tools/katalog.py")
        return ("; " + "; ".join(teile) + ".") if teile else "."

    def _autoname_ziel(self, daten: Optional[dict]) -> tuple:
        """Worauf ein Benenn-Durchgang wirkt — `(Items, Grund wenn leer)`.

        Drei Bezuege, und der mittlere ist der Grund fuer den Knopf im Kopf:
        eine ausdrueckliche Auswahl gewinnt (wer Items markiert, meint genau
        die), `alle` nimmt jedes Item des offenen Scans, und ohne beides bleibt
        es beim vorsichtigen Standard — sonst benennt ein Fehlgriff den ganzen
        von Hand gepflegten Bestand um.

        `alle` gibt es, weil der Normalfall nicht "ein Item" ist: nach dem
        Lernen heissen sie alle „Item 1“ … „Item 56“, und einzeln benannt
        waeren das sechsundfuenfzig Masken zum Aufklappen. Der Bezug ist
        `_kandidaten()` — der offene Scan, sonst der Bestand —, dieselbe Regel
        wie bei jeder anderen Sammel-Aktion des Reiters.
        """
        namen = [str(n) for n in ((daten or {}).get("namen") or [])]
        if namen:
            return ([i for i in self.items.values()
                     if i.name in namen and i.template_names()],
                    "Keines der gewählten Items hat eine Vorlage.")
        if (daten or {}).get("alle"):
            return ([i for i in self._kandidaten() if i.template_names()],
                    "Kein Item mit Vorlage gefunden — erst Items lernen, "
                    "dann benennen.")
        return ([i for i in self.items.values()
                 if i.category == "Auto" and i.template_names()],
                "Keine auto-gelernten Items mit Vorlage gefunden. "
                "Für andere Items erst welche auswählen.")

    def _autoname_stand(self) -> Optional[dict]:
        """Der Fortschritt fuer die Ansicht, oder `None` ohne Durchgang.

        Er steht in der MOMENTAUFNAHME und nicht nur in der Antwort des
        Schritts: die Seite baut sich nach jeder Bruecken-Antwort neu auf, und
        ein Fortschritt, den nur der Schritt selbst kennt, waere nach dem
        naechsten Neuzeichnen weg.
        """
        lauf = getattr(self, "_autoname", None)
        if not lauf:
            return None
        return {"gesamt": lauf["gesamt"], "offen": len(lauf["offen"]),
                "fertig": lauf["gesamt"] - len(lauf["offen"]),
                "umbenannt": lauf["umbenannt"], "varianten": lauf["varianten"]}

    def scan_autoname_start(self, daten: Optional[dict] = None) -> dict:
        """Beginnt einen Benenn-Durchgang — **die Seite treibt ihn, Item fuer Item.**

        Der ganze Durchgang war einmal EIN Bruecken-Aufruf, und damit gab es
        kein Abbrechen: sechsundfuenfzig Modell-Aufrufe sind bei drei Sekunden
        je Vorlage knapp drei Minuten, in denen das Fenster nur zusehen konnte.
        Ein Abbruch-Flag haette einen zweiten Aufruf NEBEN dem laufenden
        gebraucht — der kommt in pywebview durch, im Rauchtest-Pruefstand aber
        nicht, und ein Abbruch, der nur im Fenster funktioniert, ist keiner.

        Also andersherum: der Zustand liegt hier, die Seite fragt nach dem
        naechsten Schritt. Das kostet einen Aufruf je Item (lokal, billig) und
        bringt dreierlei — Abbruch jederzeit, sichtbaren Fortschritt, und einen
        Durchgang, den die Vertragssuite Schritt fuer Schritt durchspielen kann.
        """
        from ...config import load_config
        config = load_config()
        if not config.llm_enabled:
            return self._scan_melde(
                "LLM-Vision ist in den Einstellungen nicht aktiviert.", "err")
        try:
            from PIL import Image      # noqa: F401  (nur die Verfuegbarkeit)
            from ...llm_vision import suggest_item_name    # noqa: F401
        except ImportError:
            return self._scan_melde("Pillow oder LLM-Vision ist nicht verfügbar.", "err")

        kandidaten, leer_text = self._autoname_ziel(daten)
        if not kandidaten:
            return self._scan_melde(leer_text, "warn")

        # Mit Katalog darf das Modell nur noch AUSWAEHLEN. Frei geraten nennt
        # es die Art ("Bogen"), aus der Liste den Gegenstand ("Godlike Bow") —
        # und nur der zweite laesst sich hinterher einordnen. Einmal geholt und
        # fuer den Durchgang festgehalten: die Liste darf sich zwischen zwei
        # Schritten nicht aendern, sonst waehlt Item 30 aus einer anderen Menge
        # als Item 1.
        katalog = self._katalog()
        self._autoname = {
            # **Die Config wird einmal geholt und festgehalten**, nicht je
            # Schritt: `load_config()` liest die Datei und schreibt eine Zeile
            # in die Konsole — bei sechsundfuenfzig Vorlagen also
            # sechsundfuenfzig Dateizugriffe und ebenso viele "[CONFIG]
            # geladen"-Zeilen mitten in der Mitschrift. Dieselbe Ueberlegung
            # wie beim Boss-Scan, der alle Flags in einem Lock-Snapshot
            # einfriert: was einen Durchgang steuert, darf sich waehrenddessen
            # nicht aendern.
            "config": config,
            "offen": [i.name for i in kandidaten],
            "gesamt": len(kandidaten),
            "auswahl": katalog.namen() or None,
            "benannt": [],
            "umbenannt": 0,
            "varianten": 0,
            "ohne": 0,
            "timeouts": 0,
            "gemerkt": False,
        }
        return self._scan_melde(f"Benennt {len(kandidaten)} Item(s) …", "info")

    def scan_autoname_schritt(self, daten: Optional[dict] = None) -> dict:
        """Ein Item des laufenden Durchgangs — fragt das Modell, benennt um."""
        lauf = getattr(self, "_autoname", None)
        if not lauf:
            return self._scan_melde("Es läuft kein Benenn-Durchgang.", "warn")
        if not lauf["offen"]:
            return self.scan_daten()

        from PIL import Image
        from ...llm_vision import TIMEOUT, suggest_item_name_grund
        from ...utils import bereinige_itemname

        config = lauf["config"]
        item = self.items.get(lauf["offen"].pop(0))
        if item is None or not item.template_names():
            # Zwischen Start und Schritt kann gelöscht worden sein.
            lauf["ohne"] += 1
            return self.scan_daten()

        pfad = self.filepath.parent / "templates" / item.template_names()[0]
        try:
            with Image.open(pfad) as bild:
                vorlage = bild.copy()
        except (OSError, ValueError):
            lauf["ohne"] += 1
            return self.scan_daten()

        def frag(grenze):
            return suggest_item_name_grund(
                vorlage, provider=config.llm_provider,
                endpoint=config.llm_endpoint, model=config.llm_model,
                timeout=grenze, candidates=lauf["auswahl"])

        vorschlag, grund = frag(config.llm_timeout)
        # **Beim ersten Aufruf laedt der Server das Modell.** Gemessen an einem
        # echten Bestand: die ersten vier Anfragen ueber 120 s, die folgenden
        # 3,5 s. Der zweite Versuch trifft also ein warmes Modell und kostet
        # fast nichts — ihn wegzulassen hiesse, den Anfang jedes Durchgangs zu
        # verschenken. Mehr als einer waere Warten ohne Aussicht: antwortet es
        # auch dann nicht, liegt es nicht am Aufwaermen.
        if grund == TIMEOUT:
            vorschlag, grund = frag(max(config.llm_timeout * 2, 120))

        basis = bereinige_itemname(vorschlag) if vorschlag else ""
        if not basis:
            # Ein Timeout wird getrennt gezaehlt: "ohne Vorschlag" hiesse, das
            # Modell habe hingesehen und nichts erkannt.
            lauf["timeouts" if grund == TIMEOUT else "ohne"] += 1
            return self.scan_daten()

        if basis == item.name:
            return self.scan_daten()

        # **Zwei Slots mit demselben Gegenstand sind EIN Item, kein zweites.**
        # Hier stand `"{basis} {nr}"`, und ein Inventar mit zwei Boegen ergab
        # "Godlike Bow" und "Godlike Bow 2" — mit drei Folgen: der Zaehler-Name
        # steht nicht im Katalog (das Item blieb ohne Kategorie), beide landeten
        # in derselben Kategorie mit derselben Prioritaet (in Modus `all` gewinnt
        # eines, das andere wird nie geklickt), und die zweite Vorlage gehoerte
        # ohnehin zum selben Gegenstand. Genau dafuer gibt es
        # `template_variants`: EIN Item, das in beiden Slots erkannt wird.
        #
        # Irrt sich das Modell und benennt zwei verschiedene Dinge gleich, haengt
        # eine fremde Vorlage am Item — sichtbar in dessen Vorlagenliste, dort
        # einzeln loesbar, und STRG+Z holt den ganzen Durchgang zurueck.
        bestand = self.items.get(basis)
        if bestand is not None:
            return self._autoname_variante(bestand, item, lauf)
        neu = basis

        # **Ein Stand fuer den ganzen Durchgang, und erst beim ersten Treffer.**
        # Vorher abgelegt waere er ein STRG+Z, das nichts zurueckdreht, wenn das
        # Modell nichts erkennt; je Item abgelegt waere der Stand von VOR dem
        # Durchgang nach dreissig Items aus dem Stapel gefallen — also genau
        # der, auf den man zurueck will.
        if not lauf["gemerkt"]:
            self._merke(str(lauf["gesamt"]) + " Item(s) per LLM benannt")
            lauf["gemerkt"] = True
        self._item_umbenennen(item, neu, merken=False)
        lauf["umbenannt"] += 1
        lauf["benannt"].append(item)
        return self._scan_geaendert()

    def _autoname_variante(self, bestand, item, lauf: dict) -> dict:
        """Die Vorlage des Doppels an das bekannte Item haengen, das Doppel weg.

        Der Rueckgaengig-Stand entsteht hier genauso wie beim Umbenennen: EINER
        fuer den ganzen Durchgang, und erst wenn wirklich etwas passiert.
        """
        neu = [n for n in item.template_names() if n not in bestand.template_names()]
        if not neu and item.name not in self.items:
            return self.scan_daten()
        if not lauf["gemerkt"]:
            self._merke(str(lauf["gesamt"]) + " Item(s) per LLM benannt")
            lauf["gemerkt"] = True
        bestand.template_variants = list(bestand.template_variants) + neu
        self.items.pop(item.name, None)
        # Der Name IST die Referenz: ohne das Angleichen kaeme das geloeschte
        # Item beim naechsten Speichern ueber `sync_names()` zurueck.
        self._objekte_angleichen()
        lauf["varianten"] += 1
        return self._scan_geaendert()

    def scan_autoname_ende(self, daten: Optional[dict] = None) -> dict:
        """Schliesst den Durchgang ab — auch den abgebrochenen.

        **Einordnen gehoert zum Benennen, nicht in einen zweiten Knopf.** Nach
        dem Benennen ist die Frage nicht "habe ich Namen", sondern "stehen sie
        richtig" — dieselbe Ueberlegung wie bei `_gleich_erkennen()` nach dem
        Slot-Finden. Es kostet nichts (kein Netz, kein Modell), und die Namen
        kommen ja gerade aus diesem Katalog.

        Ein Abbruch laeuft ueber denselben Weg: was bis dahin benannt wurde,
        wird eingeordnet und bleibt stehen. Es wegzuwerfen hiesse, zwanzig
        Modell-Antworten zu verbrennen, weil man die einundzwanzigste nicht
        mehr abwarten wollte — und STRG+Z holt ohnehin den ganzen Durchgang
        auf einmal zurueck.
        """
        lauf = getattr(self, "_autoname", None)
        if not lauf:
            return self._scan_melde("Es läuft kein Benenn-Durchgang.", "warn")
        self._autoname = None
        abgebrochen = bool((daten or {}).get("abgebrochen"))
        offen = len(lauf["offen"])
        geprueft = lauf["gesamt"] - offen
        kopf = (str(lauf["umbenannt"]) + " von " + str(geprueft)
                + " Item(s) per LLM benannt")
        # **Eine zusammengelegte Vorlage wird gesagt.** Sonst zaehlt der Nutzer
        # hinterher weniger Items als Slots und sucht den Fehler beim Lernen.
        if lauf["varianten"]:
            kopf += (", " + str(lauf["varianten"])
                     + " Vorlage(n) an ein bekanntes Item angehängt")
        if abgebrochen:
            kopf += " — abgebrochen, " + str(offen) + " nicht angesehen"

        katalog = self._katalog()
        if katalog and lauf["benannt"]:
            aenderungen, _bekannt = self._katalog_plan(lauf["benannt"], katalog)
            if aenderungen:
                kategorien = self._katalog_uebernehmen(aenderungen)
                return self._scan_geaendert(
                    kopf + ", " + str(len(aenderungen)) + " davon in "
                    + str(len(kategorien)) + " Kategorie(n) eingeordnet"
                    + self._autoname_rest(lauf["ohne"], lauf["auswahl"], lauf["timeouts"]))
        return self._scan_geaendert(
            kopf + self._autoname_rest(lauf["ohne"], lauf["auswahl"], lauf["timeouts"]))

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
        if not any(slot.enabled for slot in self._scan_slots()):
            return self._scan_melde("Keine aktiven Slots vorhanden.", "warn")
        gefunden, geprueft, toleranz, _, gesamt = self._erkennen_lauf()
        return self._scan_melde(
            f"{gefunden} von {gesamt} Slot(s) erkannt "
            f"(Toleranz {toleranz}, {geprueft} Item(s) geprüft).")

    def _erkennen_lauf(self) -> tuple:
        """Füllt `_treffer`; liefert `(gefunden, geprüft, Toleranz, fremd, gesamt)`.

        Getrennt von `scan_erkennen()`, weil es zwei Anlässe gibt und nur einer eine
        eigene Meldung schreibt — die Rechnung darf es trotzdem nur einmal geben.

        `gesamt` ist die Zahl der Slots des offenen Scans, nicht die des Bestands.
        """
        # Erst hier importiert: `runtime/__init__` zieht den Worker samt
        # `winapi` nach, und den braucht der Rest des Fensters nicht.
        from ...runtime.item_scan import _check_profile_match
        from ...config import CONFIG

        toleranz = self._toleranz()
        kandidaten = self._kandidaten()
        stellvertreter = _NurConfig(CONFIG)
        self._treffer = {}
        gefunden = 0
        slots = [slot for slot in self._scan_slots() if slot.enabled]
        for slot in slots:
            crop = self._foto_crop(slot.scan_region)
            if crop is None:
                self._treffer[slot.name] = {"name": None, "grund": "ausserhalb des Bildes"}
                continue
            treffer = None
            for item in kandidaten:
                if _check_profile_match(
                        item, crop, toleranz, stellvertreter, False,
                        template_root=self.filepath.parent / "templates"):
                    treffer = item
                    break
            if treffer is None:
                self._treffer[slot.name] = {"name": None, "grund": "nichts erkannt"}
            else:
                gefunden += 1
                self._treffer[slot.name] = {
                    "name": treffer.name,
                    "farbe": hexfarbe(treffer.marker_colors[0]) if treffer.marker_colors else None,
                    "fremd": False,
                }
        return gefunden, len(kandidaten), toleranz, 0, len(slots)

    def _kandidaten(self) -> list:
        """Welche Items geprüft werden — die des gewählten Scans, sonst alle.

        Ist ein Scan offen, ist genau seine Liste die interessante: sie
        beantwortet die Frage „findet DIESER Scan, was er finden soll?". Ohne
        Scan wird alles geprüft, sonst sähe man bei leerer Auswahl nichts.
        """
        cfg = self.scans.get(self.scan_offen)
        if cfg is not None:
            gewaehlt = [self.items[n] for n in cfg.item_names
                        if n in self.items and self.items[n].enabled]
            return sorted(gewaehlt, key=lambda i: i.priority)
        return sorted((i for i in self.items.values() if i.enabled),
                      key=lambda i: i.priority)

    def _toleranz(self) -> int:
        cfg = self.scans.get(self.scan_offen)
        if cfg is not None:
            return cfg.color_tolerance
        return ItemScanConfig(name="").color_tolerance

    # -------------------------------------------------------- Scan-Konfigs


class _NurConfig:
    """Ein `state`-Stellvertreter mit nichts als der Config.

    `_check_profile_match()` will einen `AutoClickerState`, benutzt davon aber
    ausschliesslich `state.config`. Diesen Prozess einen echten State bauen zu
    lassen hiesse, den halben Hauptprozess mitzuziehen — für drei
    Config-Werte.
    """

    def __init__(self, config):
        self.config = config
