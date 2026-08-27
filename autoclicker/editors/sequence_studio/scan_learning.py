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

    def scan_items_autoname(self, daten: Optional[dict] = None) -> dict:
        """Benennt ausgewählte Auto-Items per konfigurierter LLM-Vision."""
        from ...config import load_config
        config = load_config()
        if not config.llm_enabled:
            return self._scan_melde("LLM-Vision ist in den Einstellungen nicht aktiviert.", "err")
        namen = [str(n) for n in ((daten or {}).get("namen") or [])]
        kandidaten = [i for i in self.items.values()
                      if (not namen or i.name in namen)
                      and i.category == "Auto" and i.template_names()]
        if not kandidaten:
            return self._scan_melde("Keine passenden Auto-Items mit Vorlage gefunden.", "warn")
        try:
            from PIL import Image
            from ...llm_vision import suggest_item_name
            from ...utils import sanitize_filename
        except ImportError:
            return self._scan_melde("Pillow oder LLM-Vision ist nicht verfügbar.", "err")
        umbenannt = 0
        for item in list(kandidaten):
            pfad = self.filepath.parent / "templates" / item.template_names()[0]
            try:
                with Image.open(pfad) as bild:
                    vorschlag = suggest_item_name(
                        bild.copy(), provider=config.llm_provider,
                        endpoint=config.llm_endpoint, model=config.llm_model,
                        timeout=config.llm_timeout)
            except (OSError, ValueError):
                continue
            basis = sanitize_filename(vorschlag).strip() if vorschlag else ""
            if not basis:
                continue
            neu, nr = basis, 1
            while neu in self.items and neu != item.name:
                nr += 1
                neu = f"{basis} {nr}"
            if neu != item.name:
                self._item_umbenennen(item, neu)
                umbenannt += 1
        return self._scan_geaendert(f"{umbenannt} Auto-Item(s) per LLM benannt.")

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


class _NurConfig:
    """Ein `state`-Stellvertreter mit nichts als der Config.

    `_check_profile_match()` will einen `AutoClickerState`, benutzt davon aber
    ausschliesslich `state.config`. Diesen Prozess einen echten State bauen zu
    lassen hiesse, den halben Hauptprozess mitzuziehen — für drei
    Config-Werte.
    """

    def __init__(self, config):
        self.config = config
