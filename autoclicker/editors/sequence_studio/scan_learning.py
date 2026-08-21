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
        """Verwendet bei gleicher Schreibweise die bereits bekannte Kategorie.

        **Leerraum zaehlt nicht mit.** „Helme", „ Helme" und „Helme  Gross"
        gegen „Helme Gross" waeren sonst verschiedene Kategorien — und Items
        derselben Kategorie konkurrieren miteinander, eine getrennte verliert
        also still ihre Gruppe. Aehnlichkeit darueber hinaus wird NICHT geraten:
        ein getipptes Wort stillschweigend in ein anderes zu aendern ist
        schlimmer als der Tippfehler.
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


class _NurConfig:
    """Ein `state`-Stellvertreter mit nichts als der Config.

    `_check_profile_match()` will einen `AutoClickerState`, benutzt davon aber
    ausschliesslich `state.config`. Diesen Prozess einen echten State bauen zu
    lassen hiesse, den halben Hauptprozess mitzuziehen — für drei
    Config-Werte.
    """

    def __init__(self, config):
        self.config = config
