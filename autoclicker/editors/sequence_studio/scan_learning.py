"""Item-Lernen, Vorschau und Erkennung im Scan-Editor."""

import base64
import io
from dataclasses import dataclass, field
from typing import Optional

from ...models import ItemProfile, ItemScanConfig, ItemSlot
from ...utils import unique_name
from .model import hex_color
from .scan_contract import KIND_ITEM
from .scan_model import existing_categories, next_item_name, save_template


@dataclass
class _LearnResult:
    """Was das Übernehmen der Lernvorschau bewirkt hat — für die Meldung."""
    assigned: set
    new: list = field(default_factory=list)
    variants: list = field(default_factory=list)
    edited: list = field(default_factory=list)
    unchanged: set = field(default_factory=set)
    metadata_set: set = field(default_factory=set)

    def text(self) -> str:
        parts = []
        if self.new:
            parts.append(f"{len(self.new)} neue Item(s)")
        if self.variants:
            parts.append(f"{len(self.variants)} Grössenvariante(n) ergänzt")
        if self.edited:
            parts.append(f"{len(self.edited)} bestehende Item(s) bearbeitet")
        if self.unchanged:
            parts.append(f"{len(self.unchanged)} bereits vollständig eingerichtet")
        return ", ".join(parts) + "." if parts else "Keine Änderungen."


_ITEM_SETTERS = {
    "name": "_item_set_name",
    "active": "_item_set_active",
    "category": "_item_set_category",
    "priority": "_item_set_priority",
    "confidence": "_item_set_confidence",
    "confirmation": "_item_set_confirmation",
    "confirmation_delay": "_item_set_confirmation_delay",
}


class ScanLearningMixin:
    """Lernt Item-Profile und prüft sie mit derselben Logik wie die Laufzeit."""

    def scan_item_learn(self, data: Optional[dict] = None) -> dict:
        """Lernt ein Item aus der Region eines Slots: Template + Marker-Farben.

        Genau das, was `execute_item_scan()` beim Auto-Lernen tut — nur mit dem
        Unterschied, dass man hier sieht, was gelernt wurde, und es benennen
        kann.
        """
        name = str((data or {}).get("slot") or "") or self.scan_name
        slot = self.slots.get(name)
        if slot is None:
            return self._scan_report("Kein Slot gewählt.", "warn")
        self._remember("Item gelernt")
        learned = self._learn_from_slot(slot)
        if learned is None:
            return self._scan_report(
                "Kein Item in diesem Slot — leer oder ohne Bild.", "info")
        self.scan_kind, self.scan_name = KIND_ITEM, learned
        self._add_to_scan(KIND_ITEM, learned)
        return self._scan_changed(f"'{learned}' aus '{slot.name}' gelernt.")

    def _learn_from_slot(self, slot: ItemSlot) -> Optional[str]:
        """Der Name des neuen Items, `None` ohne Bild."""
        crop = self._photo_crop(slot.scan_region)
        if crop is None:
            return None
        from ..item_editor.markers import _prepare_learning_image
        from ...config import CONFIG
        masked, marker, is_blank = _prepare_learning_image(crop, slot.slot_color)
        if is_blank:
            return None
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
            template=save_template(masked, name,
                                   template_dir=self.filepath.parent / "templates"),
            min_confidence=CONFIG.scan_min_confidence,
        )
        return name

    def scan_learn_preview(self, data: Optional[dict] = None) -> dict:
        """Bereitet mehrere Items vor, ohne Bestand oder Templates zu veraendern."""
        scope = str((data or {}).get("scope") or "all")
        slots = self._selection_slots() if scope == "selection" else self._scan_slots()
        if not slots:
            return self._scan_report("Keine Slots fuer die Lernvorschau.", "warn")
        if self._photo is None:
            return self._scan_report("Erst einen Screenshot aufnehmen.", "warn")

        review = []
        empty_slots = 0
        assigned = set(self.items)
        for slot in slots:
            row = self._learn_row(slot, assigned)
            if row == "empty":
                empty_slots += 1
            elif row is not None:
                review.append(row)
        self._learn_review = review
        return self._learn_preview_report(review, empty_slots)

    def _learn_row(self, slot, assigned: set):
        """Eine Zeile der Lernvorschau — "empty" für einen leeren Slot, None ohne Bild."""
        from ..item_editor.markers import (
            _find_matching_existing_item, _item_has_compatible_template,
            _prepare_learning_image,
        )
        from ...config import CONFIG
        crop = self._photo_crop(slot.scan_region)
        if crop is None:
            return None
        masked, _marker, is_blank = _prepare_learning_image(crop, slot.slot_color)
        if is_blank:
            return "empty"
        templates = self.filepath.parent / "templates"
        match = (_find_matching_existing_item(
            crop, list(self.items.items()), CONFIG.scan_min_confidence, templates)
            if self._has_opencv() else None)
        compatible = bool(match and _item_has_compatible_template(self.items[match], crop, templates))
        # Ein sicher erkannter Treffer IST das vorhandene Item. Zuvor stand
        # bei einem kompatiblen Treffer oben „Bogen erkannt", im Namensfeld
        # aber „Item 1". Der Platzhalter war nur fuer einen moeglichen
        # manuellen Widerspruch gedacht und bereitete beim Ankreuzen sogar
        # ein Duplikat vor. Der vorhandene Datensatz ist deshalb immer der
        # sichtbare Standard; `new_name` bleibt nur fuer die ausdrueckliche
        # UI-Aktion „Als anderes Item lernen" erhalten.
        new_name = next_item_name({n: None for n in assigned})
        assigned.add(new_name)
        item = self.items[match] if match else None
        return {
            "slot": slot.name,
            "name": match or new_name,
            "category": (item.category or "") if item else "",
            "priority": item.priority if item else 1,
            "existing": match or "", "new_name": new_name,
            "duplicate": match if compatible else "",
            "variant": match if match and not compatible else "",
            # Der Arbeitsbestand gehört bereits vollständig zum offenen Scan.
            # Es gibt keine zweite Mitgliedschaft mehr.
            "in_scan": bool(match), "can_add": False,
            # Das Haekchen beschreibt die gewuenschte Scan-Mitgliedschaft:
            # erkannt = vorausgewaehlt. So kann man ein erkanntes Item
            # bewusst abwaehlen und damit aus genau diesem Scan entfernen.
            "ticked": True,
            "image": self._image_url(masked), "crop": masked,
        }

    def _learn_preview_report(self, review: list, empty_slots: int) -> dict:
        if not review:
            if empty_slots:
                return self._scan_report(
                    f"{empty_slots} leere Slot(s) übersprungen — nichts zu lernen.", "info")
            return self._scan_report("Keiner der Slots liegt im Screenshot.", "warn")
        duplicate = sum(bool(z["duplicate"]) for z in review)
        variants = sum(bool(z["variant"]) for z in review)
        parts = []
        if duplicate:
            parts.append(f"{duplicate} bereits gelernt")
        if variants:
            parts.append(f"{variants} neue Grössenvariante(n)")
        if empty_slots:
            parts.append(f"{empty_slots} leere übersprungen")
        extra = " - " + ", ".join(parts) if parts else ""
        return self._scan_report(f"{len(review)} Vorschlaege vorbereitet{extra}.", "info")

    @staticmethod
    def _image_url(img) -> str:
        try:
            with io.BytesIO() as stream:
                img.save(stream, format="PNG")
                return "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode("ascii")
        except (OSError, ValueError):
            return ""

    def scan_learn_preview_cancel(self, data: Optional[dict] = None) -> dict:
        self._learn_review = []
        return self._scan_report("Lernvorschau verworfen.", "info")

    def _category_normalize(self, value) -> Optional[str]:
        """Verwendet bei gleicher Schreibweise die bereits bekannte Kategorie.

        Leerraum zaehlt nicht mit; darueber hinaus wird NICHTS geraten. Ein getipptes
        Wort stillschweigend in ein aehnliches zu aendern ist schlimmer als der
        Tippfehler — Items derselben Kategorie konkurrieren miteinander, eine
        getrennte verliert still ihre Gruppe.
        """
        new = " ".join(str(value or "").split())
        if not new:
            return None
        key_name = new.casefold()
        for existing in existing_categories(self.items):
            if existing.casefold() == key_name:
                return existing
        return new

    def _priority_place(self, category: Optional[str], value,
                              exclude: Optional[ItemProfile] = None) -> tuple[int, int]:
        """Wertet die TUI-Sonderzahl 0 aus; liefert (Prioritaet, verschoben)."""
        try:
            priority = int(value)
        except (TypeError, ValueError):
            priority = 1
        if priority != 0:
            return max(1, priority), 0
        if not category:
            return 1, 0

        moved = 0
        for item in self.items.values():
            if item is not exclude and item.category == category:
                item.priority = max(1, int(item.priority)) + 1
                moved += 1
        return 1, moved

    def scan_learn_preview_apply(self, data: Optional[dict] = None) -> dict:
        """Uebernimmt Items und die gewuenschte Mitgliedschaft im offenen Scan."""
        inputs = (data or {}).get("rows") or []
        by_slot = {str(z.get("slot") or ""): z for z in inputs if isinstance(z, dict)}
        ticked = [line for line in self._learn_review
                  if bool(by_slot.get(line["slot"], {}).get("ticked", line["ticked"]))]
        if not ticked:
            self._learn_review = []
            return self._scan_report(
                "Keine Items ausgewählt; nichts gelernt oder geändert.", "info")

        self._remember("Item-Auswahl der Lernvorschau uebernommen")
        result = _LearnResult(assigned=set(self.items))
        for line in ticked:
            user_input = by_slot.get(line["slot"], {})
            slot = self.slots.get(line["slot"])
            if slot is None:
                continue
            as_other = bool(user_input.get("as_other", False))
            detected_name = str(line.get("existing") or "")
            if detected_name and not as_other:
                # Der Name ist die Identität des erkannten Items. Geändert wird
                # er nur über die ausdrückliche Aktion „Als anderes Item lernen“.
                base_name = detected_name
            else:
                base_name = (str(user_input.get("name") or line["name"]).strip()
                             or line["name"])
            # Ein bereits vorhandener Name bedeutet bewusst: dieses Bild ist
            # dasselbe Item in einem anderen Slot-Typ. Seine sichtbaren Daten
            # können bearbeitet werden; bei Bedarf kommt eine Bildvariante hinzu.
            existing = self.items.get(base_name)
            if existing is not None:
                own = bool(detected_name) and not as_other
                self._learn_into_existing(existing, base_name, line, user_input, own, result)
            else:
                self._learn_new_item(base_name, slot, line, user_input, result)
        self._learn_review = []
        selected = result.new + result.variants + result.edited
        if selected:
            self.scan_kind, self.scan_name = KIND_ITEM, selected[0]
        return self._scan_changed(result.text())

    def _learn_into_existing(self, existing: ItemProfile, base_name: str, line: dict,
                             user_input: dict, own: bool, result: "_LearnResult") -> None:
        """Ein Vorlagenbild für ein vorhandenes Item: Daten bearbeiten, Variante anhängen.

        Bei einem regulär erkannten Treffer (`own`) stammen die sichtbaren Werte
        aus genau diesem Profil und dürfen direkt bearbeitet werden. Bei „anderes
        Item“ kann ein fremder vorhandener Name gewählt werden; dessen Metadaten
        werden nicht mit den leeren Standardfeldern überschrieben.
        """
        from ..item_editor.markers import _item_has_compatible_template
        if own and base_name not in result.metadata_set:
            before = (existing.category, existing.priority)
            category = self._category_normalize(user_input.get("category", line["category"]))
            priority, moved = self._priority_place(
                category, user_input.get("priority", line["priority"]), exclude=existing)
            existing.category = category
            existing.priority = priority
            result.metadata_set.add(base_name)
            if before != (category, priority) or moved:
                result.edited.append(base_name)

        templates = self.filepath.parent / "templates"
        if _item_has_compatible_template(existing, line["crop"], templates):
            self._sync_objects()
            if base_name not in result.edited:
                result.unchanged.add(base_name)
            return
        file = save_template(line["crop"], base_name, template_dir=templates)
        if not file:
            return
        if existing.template:
            existing.template_variants.append(file)
        else:
            existing.template = file
        if base_name not in result.variants:
            result.variants.append(base_name)
        self._sync_objects()

    def _learn_new_item(self, base_name: str, slot, line: dict, user_input: dict,
                        result: "_LearnResult") -> None:
        """Ein neues Item aus dem Vorlagenbild, unter einem freien Namen."""
        from ..item_editor.markers import _collect_markers_silent
        from ...config import CONFIG
        name = unique_name(base_name, result.assigned)
        result.assigned.add(name)
        marker = _collect_markers_silent(line["crop"], slot.slot_color)
        category = self._category_normalize(user_input.get("category"))
        priority, _ = self._priority_place(category, user_input.get("priority", line["priority"]))
        self.items[name] = ItemProfile(
            name=name, marker_colors=[tuple(c) for c in marker],
            category=category, priority=priority,
            template=save_template(line["crop"], name,
                                   template_dir=self.filepath.parent / "templates"),
            min_confidence=CONFIG.scan_min_confidence,
        )
        self._add_to_scan(KIND_ITEM, name)
        result.new.append(name)

    def scan_item_set(self, data: dict) -> dict:
        """Ein Feld eines Items — Aktiv, Name, Kategorie, Priorität, Konfidenz.

        Je Feld eine Methode (`_ITEM_SETTERS`); jede legt ihren Rückgängig-Stand
        selbst ab, und zwar erst, wenn sich wirklich etwas ändert.
        """
        name = str((data or {}).get("name") or "")
        field = str((data or {}).get("field") or "")
        value = (data or {}).get("value")
        item = self.items.get(name)
        if item is None:
            return self._scan_report(f"Item '{name}' gibt es nicht.", "err")
        setter = _ITEM_SETTERS.get(field)
        if setter is None:
            return self._scan_report(f"Unbekanntes Feld '{field}'.", "err")
        return getattr(self, setter)(item, name, value)

    def _item_set_name(self, item, name: str, value) -> dict:
        return self._item_rename(item, str(value or "").strip())

    def _item_set_active(self, item, name: str, value) -> dict:
        new = bool(value)
        if item.enabled == new:
            return self.scan_data()
        self._remember(f"'{name}': {'ein' if new else 'aus'}")
        item.enabled = new
        return self._scan_changed(
            f"{item.name} ist {'eingeschaltet' if new else 'ausgeschaltet'}.")

    def _item_set_category(self, item, name: str, value) -> dict:
        self._remember(f"'{name}': Kategorie")
        item.category = self._category_normalize(value)
        # **Ein Rang, den es schon gibt, ist kein Rang.** Items derselben
        # Kategorie konkurrieren miteinander; bei gleicher Zahl entscheidet
        # die Scan-Reihenfolge, also der Zufall. Wer ein Item in eine
        # Kategorie schiebt, hat über seine Priorität nichts gesagt — dann
        # ist der nächste freie Platz die einzige Antwort, die nicht rät.
        # Eine ausdrücklich getippte Zahl bleibt dagegen stehen
        # (`_item_set_priority` fasst sie nicht an).
        free = self._free_priority(item)
        if free is None:
            return self._scan_changed()
        old = item.priority
        item.priority = free
        return self._scan_changed(
            f"{name}: P{old} war in '{item.category}' vergeben — jetzt P{free}.")

    def _item_set_priority(self, item, name: str, value) -> dict:
        self._remember(f"'{name}': Priorität")
        item.priority, moved = self._priority_place(item.category, value, exclude=item)
        try:
            to_front = int(value) == 0
        except (TypeError, ValueError):
            to_front = False
        if to_front and not item.category:
            return self._scan_changed(
                f"{name}: Priorität 1. Für 'ganz nach vorn' erst eine Kategorie wählen.",
                "warn")
        extra = (f"; {moved} andere Item(s) in '{item.category}' nach hinten gerückt"
                  if moved else "")
        return self._scan_changed(f"{name}: Priorität {item.priority}{extra}.")

    def _item_set_confidence(self, item, name: str, value) -> dict:
        self._remember(f"'{name}': Konfidenz")
        item.min_confidence = max(0.0, min(1.0, float(value or 0)))
        return self._scan_changed()

    def _item_set_confirmation(self, item, name: str, value) -> dict:
        # Leer heisst „keine Bestätigung" — und das ist etwas anderes als
        # Punkt 0. Ein Punkt, den es nicht gibt, wird abgelehnt statt still
        # gesetzt: sonst klickte der Lauf auf (0, 0).
        if value in (None, "", "0", 0):
            self._remember(f"'{name}': Bestätigungsklick")
            item.confirm_point_id = None
            item.confirm_point = None
            return self._scan_changed(f"{name}: kein Bestätigungsklick mehr.")
        try:
            point_id = int(value)
        except (TypeError, ValueError):
            return self._scan_report("Der Bestätigungsklick braucht einen Punkt.", "err")
        if not any(p.id == point_id for p in self.points):
            return self._scan_report(f"Punkt #{point_id} gibt es nicht.", "err")
        self._remember(f"'{name}': Bestätigungsklick")
        item.confirm_point_id = point_id
        self._confirmation_apply(item)
        return self._scan_changed(f"{name}: bestätigt über Punkt #{point_id}.")

    def _item_set_confirmation_delay(self, item, name: str, value) -> dict:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return self._scan_report("Die Wartezeit muss eine Zahl sein.", "err")
        if number < 0:
            return self._scan_report("Die Wartezeit kann nicht negativ sein.", "err")
        self._remember(f"'{name}': Wartezeit vor der Bestätigung")
        item.confirm_delay = number
        return self._scan_changed()

    def _confirmation_apply(self, item) -> None:
        """Zieht `confirm_point` an der Referenz nach — abgeleiteter Arbeitswert.

        Dieselbe Rolle wie `_action_point_apply()` bei Boss und Icon: die
        Koordinate steht in der Punktliste der `sequence.json`, der Serializer schreibt sie hier
        nicht, und gefüllt wird sie nur, damit die Anzeige etwas zu zeigen hat.
        """
        from ...models import ClickPoint
        point = next((p for p in self.points if p.id == item.confirm_point_id), None)
        item.confirm_point = (ClickPoint(x=point.x, y=point.y, name=point.name or "")
                              if point else None)

    def _free_priority(self, item: ItemProfile) -> Optional[int]:
        """Der nächste freie Rang der Kategorie — oder None, wenn keiner nötig.

        Nur bei einer echten Kollision: sitzt das Item allein auf seiner Zahl,
        wird nichts verschoben. Ohne Kategorie gibt es keine Konkurrenz.
        """
        if not item.category:
            return None
        assigned = {int(i.priority) for i in self.items.values()
                    if i is not item and i.category == item.category}
        if int(item.priority) not in assigned:
            return None
        rank = 1
        while rank in assigned:
            rank += 1
        return rank

    def _item_rename(self, item: ItemProfile, new: str, remember: bool = True) -> dict:
        """Wie beim Slot: der Name ist die Referenz, also ziehen die Scans mit.

        `merken=False` ist fuer Sammel-Aktionen da: wer sechsundfuenfzig Items
        in einem Durchgang benennt, legt EINEN Stand vorher ab statt
        sechsundfuenfzig einzelne — der Stapel ist dreissig tief, und der
        Zustand vor dem Durchgang waere sonst als Erstes herausgefallen. Genau
        der Stand, auf den man ihn zurueckdrehen will.
        """
        if not new or new == item.name:
            return self.scan_data()
        if new in self.items:
            return self._scan_report(f"'{new}' gibt es schon.", "warn")
        if remember:
            self._remember(f"'{item.name}' umbenannt")
        old = item.name
        self.items = {(new if k == old else k): v for k, v in self.items.items()}
        item.name = new
        failed = self._templates_follow_name(item, old, new)
        self._sync_objects()
        self.scan_name = new
        if failed:
            return self._scan_changed(
                f"'{old}' heisst jetzt '{new}' — {failed} Vorlage(n) konnten nicht "
                "umbenannt werden und behalten ihren alten Dateinamen.", "warn")
        return self._scan_changed(f"'{old}' heisst jetzt '{new}'")

    def _templates_follow_name(self, item: ItemProfile, old: str, new: str) -> int:
        """Die Vorlagen eines umbenannten Items bekommen seinen neuen Namen.

        **Sonst gehört ein Dateiname danach zu einem fremden Namen.** Aus
        „Auto Slot 19 2" wurde „Überlegener Edelstein", die Vorlage hiess weiter
        `auto_slot_19_2.png` — und das nächste Auto-Lernen in Slot 19 nahm den
        wieder freien Namen und schrieb eine Truhe in genau diese Datei. Das
        Überschreiben verhindert inzwischen `free_template_file()`; hier geht es
        darum, dass Name und Datei gar nicht erst auseinanderlaufen.

        **Kopiert, nicht verschoben.** Rückgängig (`_remember`) und „Verwerfen &
        neu laden" drehen nur den Speicher bzw. die JSON zurück, nie die Platte:
        nach einem Verschieben zeigte das zurückgeholte Item auf eine Datei, die
        es nicht mehr gibt. Die alte Datei bleibt deshalb liegen — dieselbe
        Haltung wie beim Löschen einer Vorlage („bleibt als Sicherung").
        Ein Grössen-Anhang (`_62x57`) wandert mit. Gibt `Anzahl Fehlschläge`
        zurück; eine Vorlage, die sich nicht kopieren lässt, behält ihren Namen.
        """
        import shutil
        from pathlib import Path
        from ...persistence import free_template_file
        from ...utils import sanitize_filename
        folder = Path(self.filepath).parent / "templates"
        old_stem, new_stem = sanitize_filename(old), sanitize_filename(new)
        renamed: dict[str, str] = {}
        failed = 0
        for file_name in item.template_names():
            stem = Path(file_name).stem
            target = (new_stem + stem[len(old_stem):] if stem.startswith(old_stem)
                      else new_stem)
            if target == stem or not (folder / file_name).is_file():
                continue
            new_file = free_template_file(folder, target)
            try:
                shutil.copy2(folder / file_name, folder / new_file)
            except OSError:
                failed += 1
                continue
            renamed[file_name] = new_file
            if file_name in self._preview:
                self._preview[new_file] = self._preview[file_name]
        if renamed:
            if item.template in renamed:
                item.template = renamed[item.template]
            item.template_variants = [renamed.get(v, v) for v in item.template_variants]
        return failed

    def scan_item_delete(self, data: Optional[dict] = None) -> dict:
        name = self.scan_name if self.scan_kind == KIND_ITEM else ""
        item = self.items.get(name)
        if item is None:
            return self._scan_report("Kein Item gewählt.", "warn")
        self._remember(f"'{name}' gelöscht")
        del self.items[name]
        self._sync_objects()
        self.scan_name = ""
        # Das Template bleibt liegen: es kann zu einem Boss gehören (beide
        # teilen sich den lokalen Template-Ordner), und eine Datei zu löschen, die einem
        # anderen gehört, ist der stille Datenverlust, den es hier nicht gibt.
        return self._scan_changed(f"'{name}' gelöscht.", "warn")

    def scan_item_remove_template(self, data: Optional[dict] = None) -> dict:
        """Löst eine fehlerhafte Vorlage vom Item, ohne fremde Dateien zu löschen."""
        data = data or {}
        name = str(data.get("name") or self.scan_name)
        file = str(data.get("file") or "")
        item = self.items.get(name)
        if item is None or file not in item.template_names():
            return self._scan_report("Vorlage nicht gefunden.", "err")
        self._remember(f"'{name}': Vorlage entfernt")
        if item.template == file:
            variants = [v for v in item.template_variants if v != file]
            item.template = variants.pop(0) if variants else None
            item.template_variants = variants
        else:
            item.template_variants = [v for v in item.template_variants if v != file]
        self._preview.pop(file, None)
        return self._scan_changed(
            f"Vorlage '{file}' von '{name}' entfernt. Die Bilddatei bleibt als Sicherung bestehen.",
            "warn")

    def _catalog(self):
        """Der Katalog DIESES Scans — leer, wenn er ihn nicht benutzt.

        Zwei Schalter, und sie beantworten verschiedene Fragen: `scan_catalog_file`
        sagt, WO der Katalog liegt (eine Datei je Spiel, also programmweit),
        `ItemScanConfig.use_catalog` sagt, OB dieser Scan ihn benutzt. Wer zwei
        Spiele betreibt, hat einen Katalog, der nur fuer eines von beiden gilt —
        dieselbe Ueberlegung wie bei der Laufrichtung.

        Die Config wird frisch gelesen und nicht gemerkt: der Pfad steht im
        Einstellungen-Reiter desselben Fensters, und ein Katalog, der erst nach
        einem Neustart greift, ist der Fall, in dem man den Knopf fuer kaputt
        haelt. `load_catalog` haengt seinen Cache ohnehin am Dateistand.
        """
        from ...catalog import EMPTY
        catalog, _reason = self._catalog_check()
        return catalog if catalog is not None else EMPTY

    def _catalog_check(self):
        """(Katalog, Grund) — genau einer von beiden ist gesetzt.

        Drei Gruende, und sie auseinanderzuhalten ist der ganze Zweck: bei
        "Schalter aus" sucht man sonst die Datei, und bei "keine Datei" den
        Schalter.
        """
        # `CONFIG` statt `load_config()`: diese Pruefung laeuft bei JEDER
        # Momentaufnahme, also nach jedem Klick — ein Dateizugriff pro Klick
        # waere zu teuer. Das Objekt haelt der Einstellungen-Reiter aktuell
        # (`config_write` ruft `apply_config(CONFIG, …)` auf dem eigenen
        # Prozess), und `load_catalog` haengt seinen Cache am Dateistand.
        from ...config import CONFIG
        from ...catalog import load_catalog

        cfg = self.scans.get(self.open_scan)
        if cfg is None:
            return None, ("Erst einen Item-Scan öffnen — der Katalog wird je Scan "
                          "ein- und ausgeschaltet.")
        if not cfg.use_catalog:
            return None, (f"'{cfg.name}' benutzt den Katalog nicht. Der Schalter steht "
                          "in den Scan-Einstellungen (Scan-Maske aufklappen).")
        path = CONFIG.scan_catalog_file
        if not path:
            return None, ("Keine Katalog-Datei eingetragen — Einstellungen → "
                          "SCAN-EINSTELLUNGEN → 'Item-Katalog', dort holt der "
                          "Knopf 'Katalog aus der Spiel-API holen' sie und "
                          "trägt den Pfad gleich ein.")
        catalog = load_catalog(path)
        if not catalog:
            return None, f"Katalog '{path}' ist leer oder nicht lesbar."
        return catalog, None

    def _catalog_target(self, data: Optional[dict]) -> list:
        """Worauf eine Katalog-Aktion wirkt: die Auswahl, sonst der offene Scan.

        Dieselbe Bezugsregel wie bei jeder Sammel-Aktion des Reiters
        (`_scan_slots()`/`_candidates()`) — eine ausdrueckliche Auswahl gewinnt,
        sonst gilt der offene Scan und ohne Scan der Bestand.
        """
        names = [str(n) for n in ((data or {}).get("names") or [])]
        if names:
            return [self.items[n] for n in names if n in self.items]
        return list(self._candidates())

    @staticmethod
    def _catalog_name(name: str, catalog) -> str:
        """Unter welchem Namen dieses Item im Katalog steht — oder "".

        Zwei Anlaeufe, und die Reihenfolge ist die Regel: der volle Name
        gewinnt, der ohne Eindeutigkeits-Zaehler ist der Rueckfall.
        """
        from ...utils import without_counter
        if catalog.match(name):
            return name
        base_name = without_counter(name)
        return base_name if base_name != name and catalog.match(base_name) else ""

    def _catalog_plan(self, items: list, catalog) -> tuple:
        """Was sich aendern WUERDE — `(Aenderungen, bekannte Items)`.

        Getrennt vom Anwenden, damit `_remember()` nur bei einer echten Aenderung
        laeuft. Ein zweiter Klick auf denselben Knopf aendert nichts, und ein
        Rueckgaengig-Stand, der nichts zurueckdreht, ist ein STRG+Z, das
        scheinbar wirkungslos ist — danach traut man dem Stapel nicht mehr.

        `Aenderungen` ist eine Liste `(Item, Kategorie, Prioritaet)`.
        """
        from ...catalog import ranks
        # **Ein angehaengter Zaehler macht den Namen fuer den Katalog
        # unbekannt.** "Godlike Bow 2" steht dort nicht, und das Item blieb
        # deshalb ohne Kategorie neben seinem eingeordneten Zwilling stehen.
        # Erst der volle Name, dann der ohne Zaehler: was im Katalog steht,
        # gewinnt — "Slot 1" bleibt "Slot 1".
        known = []
        for i in items:
            search = self._catalog_name(i.name, catalog)
            if search:
                known.append((i, catalog.category(search), catalog.value(search)))
        rank = ranks([(i.name, category, value) for i, category, value in known])

        changes = []
        for item, category, _value in known:
            new_prio = rank.get(item.name, item.priority)
            if item.category != category or item.priority != new_prio:
                changes.append((item, category, new_prio))
        return changes, len(known)

    @staticmethod
    def _catalog_apply(changes: list) -> set:
        """Traegt den Plan ein und liefert die benutzten Kategorien."""
        categories = set()
        for item, category, priority in changes:
            item.category = category
            item.priority = priority
            if category:
                categories.add(category)
        return categories

    def scan_category_rename(self, data: Optional[dict] = None) -> dict:
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
        old = self._category_normalize((data or {}).get("old")) or None
        new = self._category_normalize((data or {}).get("new")) or None
        if old == new:
            return self.scan_data()
        affected = [i for i in self.items.values() if (i.category or None) == old]
        if not affected:
            return self._scan_report(
                f"Keine Items in '{old or 'ohne Kategorie'}'.", "warn")

        # Das ist der Tooltip von „↶ Zurück", also Sprache, kein Schlüssel:
        # hier stand 'without' — ein Rest des Englisch-Umbaus.
        self._remember(f"Kategorie '{old or 'ohne Kategorie'}' → "
                       f"'{new or 'ohne Kategorie'}'")
        for item in affected:
            item.category = new
        # **Zusammengelegt heisst doppelte Ränge.** Zwei Items mit P1 in
        # derselben Kategorie sind eine Rangfolge, die der Zufall entscheidet —
        # in Modus `all` gewinnt eines und das andere wird nie geklickt.
        # Dicht gemacht wird in der bisherigen Reihenfolge: die Werte des
        # Katalogs holt man sich mit „Aus Katalog einordnen", falls man sie
        # will. Ungefragt danach umzusortieren würde handgesetzte Ränge
        # überschreiben.
        reassigned = self._ranks_dense(new, pulled_in=affected)
        extra = f", {reassigned} Rang/Ränge neu vergeben" if reassigned else ""
        return self._scan_changed(
            f"{len(affected)} Item(s): '{old or 'ohne Kategorie'}' → "
            f"'{new or 'ohne Kategorie'}'{extra}.")

    def _ranks_dense(self, category, pulled_in: list = None) -> int:
        """Prioritäten einer Kategorie auf 1..n ziehen — wie viele sich ändern.

        **Wer dazukommt, kommt hinten an.** Nach Priorität und Name über die
        ganze Gruppe zu sortieren wäre die naheliegende Fassung und die
        falsche: ein zugezogenes Item mit P1 schöbe sich zwischen die
        bestehenden und verschöbe deren handgesetzte Ränge. Wer eine Gruppe in
        eine andere schiebt, sagt damit nichts über die Rangfolge der
        Zielgruppe.
        """
        newly_included = {id(i) for i in (pulled_in or [])}
        group = [i for i in self.items.values()
                  if (i.category or None) == (category or None)]
        ordered = sorted(group,
                          key=lambda i: (id(i) in newly_included, i.priority, i.name))
        changed = 0
        for nr, item in enumerate(ordered, 1):
            if item.priority != nr:
                item.priority = nr
                changed += 1
        return changed

    def scan_catalog_apply(self, data: Optional[dict] = None) -> dict:
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
        catalog, reason = self._catalog_check()
        if catalog is None:
            return self._scan_report(reason, "err")

        target = self._catalog_target(data)
        if not target:
            return self._scan_report("Keine Items ausgewählt.", "warn")

        changes, known = self._catalog_plan(target, catalog)
        if not known:
            return self._scan_report(
                f"Keiner der {len(target)} Namen steht im Katalog. Erst benennen — "
                "von Hand oder mit „Aus Katalog benennen“.", "warn")
        if not changes:
            return self._scan_report(
                f"{known} Item(s) im Katalog gefunden — alle stehen schon richtig.",
                "info")

        self._remember("Aus Katalog eingeordnet")
        categories = self._catalog_apply(changes)
        remainder = len(target) - known
        extra = f"; {remainder} nicht im Katalog (unverändert)" if remainder else ""
        return self._scan_changed(
            f"{len(changes)} Item(s) in {len(categories)} Kategorie(n) "
            f"eingeordnet{extra}.")

    @staticmethod
    def _autoname_remaining(without: int, selection, timeouts: int = 0) -> str:
        """Der Nachsatz der Schlussmeldung: was NICHT geklappt hat.

        Zwei Dinge, und das zweite ist das wichtigere: ohne Katalog raet das
        Modell frei und antwortet auf die deutsche Frage auch deutsch — heraus
        kommt die Art ("Bogen") statt des Gegenstands ("Godlike Bow"). Das
        sieht in der Liste wie ein Ergebnis aus, ist aber keins, das sich
        einordnen liesse. Wer es nicht dazusagt, laesst den Nutzer
        sechsundfuenfzig geratene Namen fuer echte halten.
        """
        parts = []
        if without:
            parts.append(f"{without} ohne Vorschlag")
        if timeouts:
            # Der Hinweis gehoert an die Zahl: eine Zeitueberschreitung sieht in
            # der Liste aus wie ein nicht erkanntes Item, hat aber eine ganz
            # andere Abhilfe.
            parts.append(f"{timeouts}× Zeitüberschreitung (auch beim zweiten "
                         "Versuch) — llm_timeout in den Einstellungen erhöhen")
        if not selection:
            parts.append("ohne Katalog frei geraten — Einstellungen → "
                         "'Item-Katalog', anlegen mit python tools/catalog.py")
        return ("; " + "; ".join(parts) + ".") if parts else "."

    def _autoname_target(self, data: Optional[dict]) -> tuple:
        """Worauf ein Benenn-Durchgang wirkt — `(Items, Grund wenn leer)`.

        Drei Bezuege, und der mittlere ist der Grund fuer den Knopf im Kopf:
        eine ausdrueckliche Auswahl gewinnt (wer Items markiert, meint genau
        die), `all_of` nimmt jedes Item des offenen Scans, und ohne beides bleibt
        es beim vorsichtigen Standard — sonst benennt ein Fehlgriff den ganzen
        von Hand gepflegten Bestand um.

        `all_of` gibt es, weil der Normalfall nicht "ein Item" ist: nach dem
        Lernen heissen sie alle „Item 1“ … „Item 56“, und einzeln benannt
        waeren das sechsundfuenfzig Masken zum Aufklappen. Der Bezug ist
        `_candidates()` — der offene Scan, sonst der Bestand —, dieselbe Regel
        wie bei jeder anderen Sammel-Aktion des Reiters.
        """
        names = [str(n) for n in ((data or {}).get("names") or [])]
        if names:
            return ([i for i in self.items.values()
                     if i.name in names and i.template_names()],
                    "Keines der gewählten Items hat eine Vorlage.")
        if (data or {}).get("all_items"):
            return ([i for i in self._candidates() if i.template_names()],
                    "Kein Item mit Vorlage gefunden — erst Items lernen, "
                    "dann benennen.")
        return ([i for i in self.items.values()
                 if i.category == "Auto" and i.template_names()],
                "Keine auto-gelernten Items mit Vorlage gefunden. "
                "Für andere Items erst welche auswählen.")

    def _autoname_state(self) -> Optional[dict]:
        """Der Fortschritt fuer die Ansicht, oder `None` ohne Durchgang.

        Er steht in der MOMENTAUFNAHME und nicht nur in der Antwort des
        Schritts: die Seite baut sich nach jeder Bruecken-Antwort neu auf, und
        ein Fortschritt, den nur der Schritt selbst kennt, waere nach dem
        naechsten Neuzeichnen weg.
        """
        run = getattr(self, "_autoname", None)
        if not run:
            return None
        return {"total": run["total"], "open": len(run["open"]),
                "done": run["total"] - len(run["open"]),
                "renamed": run["renamed"], "variants": run["variants"]}

    def scan_autoname_start(self, data: Optional[dict] = None) -> dict:
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
            return self._scan_report(
                "LLM-Vision ist in den Einstellungen nicht aktiviert.", "err")
        try:
            from PIL import Image      # noqa: F401  (nur die Verfuegbarkeit)
            from ...llm_vision import suggest_item_name    # noqa: F401
        except ImportError:
            return self._scan_report("Pillow oder LLM-Vision ist nicht verfügbar.", "err")

        candidates, empty_text = self._autoname_target(data)
        if not candidates:
            return self._scan_report(empty_text, "warn")

        # Mit Katalog darf das Modell nur noch AUSWAEHLEN. Frei geraten nennt
        # es die Art ("Bogen"), aus der Liste den Gegenstand ("Godlike Bow") —
        # und nur der zweite laesst sich hinterher einordnen. Einmal geholt und
        # fuer den Durchgang festgehalten: die Liste darf sich zwischen zwei
        # Schritten nicht aendern, sonst waehlt Item 30 aus einer anderen Menge
        # als Item 1.
        catalog = self._catalog()
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
            "open": [i.name for i in candidates],
            "total": len(candidates),
            "selection": catalog.names() or None,
            "named": [],
            "renamed": 0,
            "variants": 0,
            "without": 0,
            "timeouts": 0,
            "remembered": False,
        }
        return self._scan_report(f"Benennt {len(candidates)} Item(s) …", "info")

    def scan_autoname_step(self, data: Optional[dict] = None) -> dict:
        """Ein Item des laufenden Durchgangs — fragt das Modell, benennt um."""
        from ...llm_vision import TIMEOUT
        from ...utils import clean_item_name

        run = getattr(self, "_autoname", None)
        if not run:
            return self._scan_report("Es läuft kein Benenn-Durchgang.", "warn")
        if not run["open"]:
            return self.scan_data()

        item = self.items.get(run["open"].pop(0))
        template_value = self._autoname_template(item)
        if template_value is None:
            # Zwischen Start und Schritt kann gelöscht worden sein — oder die
            # Vorlage ist nicht lesbar.
            run["without"] += 1
            return self.scan_data()

        proposal, reason = _autoname_ask(run, template_value)
        base_name = clean_item_name(proposal) if proposal else ""
        if not base_name:
            # Ein Timeout wird getrennt gezaehlt: "ohne Vorschlag" hiesse, das
            # Modell habe hingesehen und nichts erkannt.
            run["timeouts" if reason == TIMEOUT else "without"] += 1
            return self.scan_data()
        if base_name == item.name:
            return self.scan_data()

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
        inventory = self.items.get(base_name)
        if inventory is not None:
            return self._autoname_variant(inventory, item, run)

        # **Ein Stand fuer den ganzen Durchgang, und erst beim ersten Treffer.**
        # Vorher abgelegt waere er ein STRG+Z, das nichts zurueckdreht, wenn das
        # Modell nichts erkennt; je Item abgelegt waere der Stand von VOR dem
        # Durchgang nach dreissig Items aus dem Stapel gefallen — also genau
        # der, auf den man zurueck will.
        if not run["remembered"]:
            self._remember(str(run["total"]) + " Item(s) per LLM benannt")
            run["remembered"] = True
        self._item_rename(item, base_name, remember=False)
        run["renamed"] += 1
        run["named"].append(item)
        return self._scan_changed()

    def _autoname_template(self, item):
        """Die erste Vorlage des Items als Bild — None, wenn es fehlt oder unlesbar ist."""
        from PIL import Image
        if item is None or not item.template_names():
            return None
        path = self.filepath.parent / "templates" / item.template_names()[0]
        try:
            with Image.open(path) as image:
                return image.copy()
        except (OSError, ValueError):
            return None

    def _autoname_variant(self, inventory, item, run: dict) -> dict:
        """Die Vorlage des Doppels an das bekannte Item haengen, das Doppel weg.

        Der Rueckgaengig-Stand entsteht hier genauso wie beim Umbenennen: EINER
        fuer den ganzen Durchgang, und erst wenn wirklich etwas passiert.
        """
        new = [n for n in item.template_names() if n not in inventory.template_names()]
        if not new and item.name not in self.items:
            return self.scan_data()
        if not run["remembered"]:
            self._remember(str(run["total"]) + " Item(s) per LLM benannt")
            run["remembered"] = True
        inventory.template_variants = list(inventory.template_variants) + new
        self.items.pop(item.name, None)
        # Gespeichert wird `cfg.items`, nicht der Arbeitsbestand des Reiters:
        # ohne das Angleichen stuende das geloeschte Item beim naechsten
        # Speichern noch im Scan.
        self._sync_objects()
        run["variants"] += 1
        return self._scan_changed()

    def scan_autoname_end(self, data: Optional[dict] = None) -> dict:
        """Schliesst den Durchgang ab — auch den abgebrochenen.

        **Einordnen gehoert zum Benennen, nicht in einen zweiten Knopf.** Nach
        dem Benennen ist die Frage nicht "habe ich Namen", sondern "stehen sie
        richtig" — dieselbe Ueberlegung wie bei `_detect_immediately()` nach dem
        Slot-Finden. Es kostet nichts (kein Netz, kein Modell), und die Namen
        kommen ja gerade aus diesem Katalog.

        Ein Abbruch laeuft ueber denselben Weg: was bis dahin benannt wurde,
        wird eingeordnet und bleibt stehen. Es wegzuwerfen hiesse, zwanzig
        Modell-Antworten zu verbrennen, weil man die einundzwanzigste nicht
        mehr abwarten wollte — und STRG+Z holt ohnehin den ganzen Durchgang
        auf einmal zurueck.
        """
        run = getattr(self, "_autoname", None)
        if not run:
            return self._scan_report("Es läuft kein Benenn-Durchgang.", "warn")
        self._autoname = None
        cancelled = bool((data or {}).get("cancelled"))
        remaining = len(run["open"])
        checked = run["total"] - remaining
        head = (str(run["renamed"]) + " von " + str(checked)
                + " Item(s) per LLM benannt")
        # **Eine zusammengelegte Vorlage wird gesagt.** Sonst zaehlt der Nutzer
        # hinterher weniger Items als Slots und sucht den Fehler beim Lernen.
        if run["variants"]:
            head += (", " + str(run["variants"])
                     + " Vorlage(n) an ein bekanntes Item angehängt")
        if cancelled:
            head += " — abgebrochen, " + str(remaining) + " nicht angesehen"

        catalog = self._catalog()
        if catalog and run["named"]:
            changes, _known = self._catalog_plan(run["named"], catalog)
            if changes:
                categories = self._catalog_apply(changes)
                return self._scan_changed(
                    head + ", " + str(len(changes)) + " davon in "
                    + str(len(categories)) + " Kategorie(n) eingeordnet"
                    + self._autoname_remaining(run["without"], run["selection"], run["timeouts"]))
        return self._scan_changed(
            head + self._autoname_remaining(run["without"], run["selection"], run["timeouts"]))

    # ------------------------------------------------------------- Erkennung

    def scan_recognize(self, data: Optional[dict] = None) -> dict:
        """Was steckt gerade in welchem Slot? — mit der Rechnung der Laufzeit.

        Der Punkt der ganzen Ansicht: statt einen Scan zu starten und am
        Ergebnis zu raten, steht an jedem Slot, welches Item dort erkannt wurde
        und woran es lag. Gerechnet wird auf dem eingefrorenen Screenshot,
        gefragt wird `_check_profile_match()` — dieselbe Funktion, die im Lauf
        entscheidet.
        """
        self._scan_load()
        if self._photo is None:
            return self._scan_report("Erst einen Screenshot aufnehmen.", "warn")
        if not any(slot.enabled for slot in self._scan_slots()):
            return self._scan_report("Keine aktiven Slots vorhanden.", "warn")
        found, checked, tolerance, total = self._detect_run()
        return self._scan_report(
            f"{found} von {total} Slot(s) erkannt "
            f"(Toleranz {tolerance}, {checked} Item(s) geprüft).")

    def _detect_run(self) -> tuple:
        """Füllt `_matches`; liefert `(gefunden, geprüft, Toleranz, gesamt)`.

        Getrennt von `scan_recognize()`, weil es zwei Anlässe gibt und nur einer eine
        eigene Meldung schreibt — die Rechnung darf es trotzdem nur einmal geben.

        `total` ist die Zahl der Slots des offenen Scans, nicht die des Bestands.
        """
        # Erst hier importiert: `runtime/__init__` zieht den Worker samt
        # `winapi` nach, und den braucht der Rest des Fensters nicht.
        from ...runtime.item_scan import _check_profile_match
        from ...config import CONFIG

        tolerance = self._tolerance()
        candidates = self._candidates()
        stand_in = _ConfigOnly(CONFIG)
        self._matches = {}
        found = 0
        slots = [slot for slot in self._scan_slots() if slot.enabled]
        for slot in slots:
            crop = self._photo_crop(slot.scan_region)
            if crop is None:
                self._matches[slot.name] = {"name": None, "reason": "ausserhalb des Bildes"}
                continue
            match = None
            for item in candidates:
                if _check_profile_match(
                        item, crop, tolerance, stand_in, False,
                        template_root=self.filepath.parent / "templates"):
                    match = item
                    break
            if match is None:
                self._matches[slot.name] = {"name": None, "reason": "nichts erkannt"}
            else:
                found += 1
                self._matches[slot.name] = {
                    "name": match.name,
                    "color": hex_color(match.marker_colors[0]) if match.marker_colors else None,
                }
        return found, len(candidates), tolerance, len(slots)

    def _candidates(self) -> list:
        """Welche Items geprüft werden — die des gewählten Scans, sonst alle.

        Ist ein Scan offen, ist genau seine Liste die interessante: sie
        beantwortet die Frage „findet DIESER Scan, was er finden soll?". Ohne
        Scan wird alles geprüft, sonst sähe man bei leerer Auswahl nichts.
        """
        cfg = self.scans.get(self.open_scan)
        if cfg is not None:
            selected = [self.items[n] for n in cfg.item_names
                        if n in self.items and self.items[n].enabled]
            return sorted(selected, key=lambda i: i.priority)
        return sorted((i for i in self.items.values() if i.enabled),
                      key=lambda i: i.priority)

    def _tolerance(self) -> int:
        cfg = self.scans.get(self.open_scan)
        if cfg is not None:
            return cfg.color_tolerance
        return ItemScanConfig(name="").color_tolerance

    # -------------------------------------------------------- Scan-Konfigs


def _autoname_ask(run: dict, template_value) -> tuple:
    """Fragt das Modell nach einem Namen — `(Vorschlag, Grund)`.

    `llm_reasoning` und `llm_max_tokens` galten nur fuer den Boss-Scan — wer
    sie einschaltete, weil die BENENNUNG besser werden soll, aenderte nichts.
    Ein Schalter, der an der Stelle wirkungslos ist, an der man ihn sucht, ist
    schlimmer als keiner.

    **Beim ersten Aufruf laedt der Server das Modell.** Gemessen an einem
    echten Bestand: die ersten vier Anfragen ueber 120 s, die folgenden 3,5 s.
    Der zweite Versuch trifft also ein warmes Modell und kostet fast nichts —
    ihn wegzulassen hiesse, den Anfang jedes Durchgangs zu verschenken. Mehr
    als einer waere Warten ohne Aussicht: antwortet es auch dann nicht, liegt
    es nicht am Aufwaermen.
    """
    from ...llm_vision import TIMEOUT, suggest_item_name_with_reason
    config = run["config"]

    def ask_for(limit):
        return suggest_item_name_with_reason(
            template_value, provider=config.llm_provider,
            endpoint=config.llm_endpoint, model=config.llm_model,
            timeout=limit, candidates=run["selection"],
            reasoning=config.llm_reasoning,
            max_tokens=config.llm_max_tokens)

    proposal, reason = ask_for(config.llm_timeout)
    if reason == TIMEOUT:
        proposal, reason = ask_for(max(config.llm_timeout * 2, 120))
    return proposal, reason


class _ConfigOnly:
    """Ein `state`-Stellvertreter mit nichts als der Config.

    `_check_profile_match()` will einen `AutoClickerState`, benutzt davon aber
    ausschliesslich `state.config`. Diesen Prozess einen echten State bauen zu
    lassen hiesse, den halben Hauptprozess mitzuziehen — für drei
    Config-Werte.
    """

    def __init__(self, config):
        self.config = config
