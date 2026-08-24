"""Regressionstests fuer den gefuehrten Itemscan-Editor."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_support import install_platform_stubs

install_platform_stubs()

# Pillow ist optional (s. test_scan_services.py): der Import stand hier oben und
# ohne Pillow starb das Modul beim LADEN.
try:
    from PIL import Image
    PILLOW = True
except ImportError:                                              # pragma: no cover
    Image = None
    PILLOW = False

braucht_pillow = unittest.skipUnless(PILLOW, "Pillow nicht installiert")

from autoclicker.editors.sequence_studio.bridge import StudioBridge
from autoclicker.editors.sequence_studio.scans import MODUS_SLOT, MODUS_WAHL
from autoclicker.models import (
    AutoClickerState, ItemProfile, ItemScanConfig, ItemSlot, Sequence,
)


@braucht_pillow
class ItemscanEditorUxTest(unittest.TestCase):
    def setUp(self):
        self.old_cwd = os.getcwd()
        self.temp = tempfile.TemporaryDirectory()
        os.chdir(self.temp.name)
        Path("sequences").mkdir()
        self.bridge = StudioBridge(
            Sequence(name="Test"), Path("sequences/test/sequence.json"), "sequences")
        self.bridge._scan_geladen = True
        self.bridge._foto = Image.new("RGB", (120, 80), (40, 44, 52))
        for x in range(20, 50):
            for y in range(20, 50):
                self.bridge._foto.putpixel((x, y), (190, 50, 60))
        self.bridge._foto_info = {
            "links": 0, "oben": 0, "breite": 120, "hoehe": 80,
            "skala": 1.0, "stand": 1.0,
        }
        slot = ItemSlot(
            name="Slot 1", scan_region=(10, 10, 60, 60),
            click_pos=(35, 35), slot_color=(40, 44, 52))
        self.bridge.slots = {slot.name: slot}
        scan = ItemScanConfig(
            name="Inventar", slots=[slot], owner_sequence="Test")
        self.bridge.scans = {scan.name: scan}
        self.bridge.scan_offen = scan.name

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.temp.cleanup()

    def test_membership_api_is_removed(self):
        self.assertFalse(hasattr(self.bridge, "scan_mitglied"))
        self.assertFalse(hasattr(self.bridge, "scan_alle"))
        self.assertFalse(hasattr(self.bridge, "scan_auswahl_mitglied"))

    def test_invalid_tolerance_is_reported_without_mutation(self):
        cfg = self.bridge.scans["Inventar"]
        vorher = cfg.color_tolerance

        state = self.bridge.scan_setzen({
            "name": "Inventar", "feld": "toleranz", "wert": "keine Zahl",
        })

        self.assertEqual(cfg.color_tolerance, vorher)
        self.assertEqual(state["status"]["art"], "err")
        self.assertIn("ganze Zahl", state["status"]["text"])

    def test_one_shot_tool_and_pin(self):
        self.bridge.scan_modus_setzen({"modus": MODUS_SLOT})
        self.bridge.scan_klick({"x": 65, "y": 10})
        state = self.bridge.scan_klick({"x": 115, "y": 60})
        self.assertEqual(state["modus"], MODUS_WAHL)

        self.bridge.scan_modus_setzen({"modus": MODUS_SLOT, "fixiert": True})
        self.bridge.scan_klick({"x": 65, "y": 15})
        state = self.bridge.scan_klick({"x": 115, "y": 65})
        self.assertEqual(state["modus"], MODUS_SLOT)
        self.assertTrue(state["werkzeug_fixiert"])

    def test_learning_review_does_not_mutate_until_confirmed(self):
        state = self.bridge.scan_lernvorschau({"scope": "alle"})
        self.assertEqual(self.bridge.items, {})
        self.assertIsNotNone(state["review"])
        self.assertFalse(Path("sequences/test/templates").exists())

        row = state["review"]["zeilen"][0]
        state = self.bridge.scan_lernvorschau_uebernehmen({"zeilen": [{
            "slot": row["slot"], "ausgewaehlt": True,
            "name": "Roter Helm", "kategorie": "Helme",
        }]})
        self.assertIn("Roter Helm", self.bridge.items)
        self.assertEqual(self.bridge.items["Roter Helm"].category, "Helme")
        self.assertIn("Roter Helm", self.bridge.scans["Inventar"].item_names)
        self.assertIsNone(state["review"])
        self.assertTrue(Path("sequences/test/templates/roter_helm.png").exists())

    def test_recognized_item_shows_its_data_and_is_added_without_duplicate(self):
        self.bridge.items["Bogen"] = ItemProfile(
            name="Bogen", category="Waffen", priority=4)

        matcher = patch(
            "autoclicker.editors.item_editor.markers._find_matching_existing_item",
            return_value="Bogen")
        compatible = patch(
            "autoclicker.editors.item_editor.markers._item_has_compatible_template",
            return_value=True)
        with matcher, compatible:
            state = self.bridge.scan_lernvorschau({"scope": "alle"})
            row = state["review"]["zeilen"][0]
            self.assertEqual(
                (row["name"], row["kategorie"], row["prioritaet"]),
                ("Bogen", "Waffen", 4))
            self.assertEqual(row["vorhanden"], "Bogen")
            self.assertEqual(row["neu_name"], "Item 1")
            self.assertFalse(row["kann_hinzufuegen"])
            self.assertTrue(row["ausgewaehlt"])
            self.assertTrue(row["im_scan"])

            state = self.bridge.scan_lernvorschau_uebernehmen({"zeilen": [{
                "slot": row["slot"], "ausgewaehlt": True,
                "name": row["name"], "kategorie": "Fernkampf",
                "prioritaet": 2,
            }]})

        self.assertEqual(list(self.bridge.items), ["Bogen"])
        self.assertEqual(self.bridge.scans["Inventar"].item_names, ["Bogen"])
        self.assertEqual(self.bridge.items["Bogen"].category, "Fernkampf")
        self.assertEqual(self.bridge.items["Bogen"].priority, 2)
        self.assertEqual(state["wahl"], {"art": "item", "name": "Bogen"})
        self.assertIn("bearbeitet", state["status"]["text"])

        with matcher, compatible:
            state = self.bridge.scan_lernvorschau({"scope": "alle"})
            row = state["review"]["zeilen"][0]
            self.assertEqual(row["name"], "Bogen")
            self.assertEqual((row["kategorie"], row["prioritaet"]), ("Fernkampf", 2))
            self.assertTrue(row["im_scan"])
            self.assertNotIn("gesperrt", row)
            self.assertTrue(row["ausgewaehlt"])

            state = self.bridge.scan_lernvorschau_uebernehmen({"zeilen": [{
                "slot": row["slot"], "ausgewaehlt": False,
                "vorhanden": "Bogen", "als_anders": False,
                "name": "Bogen", "kategorie": "Fernkampf", "prioritaet": 2,
            }]})

        self.assertIn("Bogen", self.bridge.items)
        self.assertEqual(self.bridge.scans["Inventar"].item_names, ["Bogen"])
        self.assertIn("nichts gelernt", state["status"]["text"])

    def test_review_offers_an_explicit_override_for_a_wrong_match(self):
        js = (Path(self.old_cwd) /
              "autoclicker/editors/sequence_studio/web/app.js").read_text(
                  encoding="utf-8")
        self.assertIn("Als anderes Item lernen", js)
        self.assertIn("bereits in diesem Scan eingerichtet", js)
        self.assertIn("wird nicht gelernt oder geändert", js)
        self.assertNotIn("wird aus diesem Scan entfernt", js)
        self.assertIn("als_anders: n.dataset.alsAnderes", js)
        self.assertIn("kat.sperren(bestehend && !normalerTreffer)", js)
        self.assertIn('name.value = z.neu_name || "Item"', js)

    def test_repeated_recognized_item_has_one_shared_scan_membership(self):
        slot = ItemSlot(
            name="Slot 2", scan_region=(60, 10, 110, 60),
            click_pos=(85, 35), slot_color=(40, 44, 52))
        self.bridge.slots[slot.name] = slot
        cfg = self.bridge.scans["Inventar"]
        cfg.slots.append(slot)
        for x in range(70, 100):
            for y in range(20, 50):
                self.bridge._foto.putpixel((x, y), (50, 120, 210))
        self.bridge.items["Bogen"] = ItemProfile(
            name="Bogen", category="Waffen", priority=1)
        cfg.items.append(self.bridge.items["Bogen"])
        self.bridge._objekte_angleichen()

        matcher = patch(
            "autoclicker.editors.item_editor.markers._find_matching_existing_item",
            return_value="Bogen")
        compatible = patch(
            "autoclicker.editors.item_editor.markers._item_has_compatible_template",
            return_value=True)
        with matcher, compatible:
            state = self.bridge.scan_lernvorschau({"scope": "alle"})
            rows = state["review"]["zeilen"]
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(row["ausgewaehlt"] for row in rows))

            # Eine abgewählte Zeile bedeutet nur „nicht lernen“, nicht löschen.
            self.bridge.scan_lernvorschau_uebernehmen({"zeilen": [
                {"slot": rows[0]["slot"], "ausgewaehlt": False},
                {"slot": rows[1]["slot"], "ausgewaehlt": True},
            ]})
            self.assertIn("Bogen", cfg.item_names)

            state = self.bridge.scan_lernvorschau({"scope": "alle"})
            rows = state["review"]["zeilen"]
            state = self.bridge.scan_lernvorschau_uebernehmen({"zeilen": [
                {"slot": row["slot"], "ausgewaehlt": False} for row in rows
            ]})

        self.assertIn("Bogen", cfg.item_names)
        self.assertIn("nichts gelernt", state["status"]["text"])

    def test_result_summary_has_no_foreign_membership(self):
        self.bridge.items["Bekannt"] = ItemProfile(name="Bekannt")
        self.bridge._objekte_angleichen()
        self.bridge._treffer = {
            "Slot 1": {"name": "Bekannt", "fremd": False},
        }
        result = self.bridge.scan_daten()["ergebnis"]
        self.assertEqual(result["fremd"], 0)
        self.assertEqual(result["gesamt"], 1)
        self.assertIn("Bekannt", self.bridge.scans["Inventar"].item_names)

    def test_category_reuses_existing_spelling_and_allows_new_names(self):
        self.bridge.items = {
            "Helm": ItemProfile(name="Helm", category="Helme"),
            "Ruestung": ItemProfile(name="Ruestung", category="Ruestungen"),
        }

        self.bridge.scan_item_setzen({
            "name": "Ruestung", "feld": "kategorie", "wert": "helme",
        })
        self.assertEqual(self.bridge.items["Ruestung"].category, "Helme")

        state = self.bridge.scan_item_setzen({
            "name": "Ruestung", "feld": "kategorie", "wert": "Traenke",
        })
        self.assertEqual(self.bridge.items["Ruestung"].category, "Traenke")
        self.assertEqual(state["kategorien"], ["Helme", "Traenke"])

        # Leerraum zählt nicht mit: „ Helme " und „Helme  Gross" gegen
        # „Helme Gross" wären sonst eigene Kategorien — und Items derselben
        # Kategorie konkurrieren miteinander, eine getrennte verliert still
        # ihre Gruppe.
        self.bridge.scan_item_setzen({
            "name": "Ruestung", "feld": "kategorie", "wert": "  helme  ",
        })
        self.assertEqual(self.bridge.items["Ruestung"].category, "Helme")
        self.bridge.scan_item_setzen({
            "name": "Ruestung", "feld": "kategorie", "wert": "Schwere   Helme",
        })
        self.assertEqual(self.bridge.items["Ruestung"].category, "Schwere Helme")
        # Weiter wird NICHT geraten: ein getipptes Wort stillschweigend in ein
        # anderes zu ändern ist schlimmer als der Tippfehler selbst.
        self.bridge.scan_item_setzen({
            "name": "Ruestung", "feld": "kategorie", "wert": "Helmr",
        })
        self.assertEqual(self.bridge.items["Ruestung"].category, "Helmr")

    def test_category_fields_offer_existing_and_free_text(self):
        """Kategorie: vorhandene vorschlagen, neue trotzdem tippbar.

        Geprüft wird die EIGENSCHAFT, nicht der Name einer Hilfsfunktion: ein
        `<input>` mit `list=` schlägt vor, ohne die Eingabe einzuschränken —
        ein `<select>` täte das Gegenteil. Vorher stand hier der Aufruf
        `kategoriefeld("Kategorie"`; seit die Kategorie in der Item-Maske
        steht, gibt es diese Funktion nicht mehr, und der Test fiel um, obwohl
        die Eigenschaft unverändert galt.
        """
        js = (Path(self.old_cwd) /
              "autoclicker/editors/sequence_studio/web/app.js").read_text(
                  encoding="utf-8")
        # EIN Bedienelement für beide Stellen, an denen eine Kategorie entsteht:
        # die Maske in der Item-Liste und die Lern-Vorschau. Vorher war es
        # zweimal ein freies Textfeld mit einer `<datalist>` daneben — ein
        # Angebot, das man kennen musste, und tippen war der einzige Weg.
        self.assertIn("function kategorieWahl(", js)
        self.assertEqual(js.count("kategorieWahl("), 4)   # Definition + 3 Aufrufe
        # Vorhandene stehen zur Wahl …
        self.assertIn("kategorienWerte(", js)
        self.assertIn('el("option", {value: k}, k)', js)
        # … eine neue lässt sich trotzdem anlegen …
        self.assertIn("＋ neue Kategorie", js)
        self.assertIn("KATEGORIE_NEU", js)
        # … und ist danach überall wählbar, ohne sie ein zweites Mal zu tippen.
        self.assertIn("function kategorieOptionenAktualisieren", js)
        # Getippt wird nur, wenn es nichts zu wählen gibt — sonst wäre das
        # Auswählen wieder das Angebot, das man kennen muss.
        self.assertIn("tausche(!vorhandene.length", js)

    def test_priority_zero_shifts_only_the_same_category(self):
        self.bridge.items = {
            "Goldhelm": ItemProfile(name="Goldhelm", category="Helme", priority=1),
            "Eisenhelm": ItemProfile(name="Eisenhelm", category="Helme", priority=4),
            "Apfel": ItemProfile(name="Apfel", category="Nahrung", priority=1),
        }

        state = self.bridge.scan_item_setzen({
            "name": "Eisenhelm", "feld": "prioritaet", "wert": 0,
        })

        self.assertEqual(self.bridge.items["Eisenhelm"].priority, 1)
        self.assertEqual(self.bridge.items["Goldhelm"].priority, 2)
        self.assertEqual(self.bridge.items["Apfel"].priority, 1)
        self.assertIn("1 andere", state["status"]["text"])

    def test_learning_review_accepts_priority_zero(self):
        self.bridge.items["Goldhelm"] = ItemProfile(
            name="Goldhelm", category="Helme", priority=1)
        state = self.bridge.scan_lernvorschau({"scope": "alle"})
        row = state["review"]["zeilen"][0]

        self.bridge.scan_lernvorschau_uebernehmen({"zeilen": [{
            "slot": row["slot"], "ausgewaehlt": True,
            "name": "Eisenhelm", "kategorie": "Helme", "prioritaet": 0,
        }]})

        self.assertEqual(self.bridge.items["Eisenhelm"].priority, 1)
        self.assertEqual(self.bridge.items["Goldhelm"].priority, 2)

    def test_learning_review_defaults_every_item_to_priority_one(self):
        slot = ItemSlot(
            name="Slot 2", scan_region=(60, 10, 110, 60),
            click_pos=(85, 35), slot_color=(40, 44, 52))
        self.bridge.slots[slot.name] = slot
        self.bridge.scans["Inventar"].slots.append(slot)
        for x in range(70, 100):
            for y in range(20, 50):
                self.bridge._foto.putpixel((x, y), (50, 120, 210))

        state = self.bridge.scan_lernvorschau({"scope": "alle"})

        self.assertEqual(len(state["review"]["zeilen"]), 2)
        self.assertEqual(
            [row["prioritaet"] for row in state["review"]["zeilen"]], [1, 1])

    def test_completely_empty_slot_is_not_offered_or_learned(self):
        self.bridge._foto = Image.new("RGB", (120, 80), (40, 44, 52))

        state = self.bridge.scan_lernvorschau({"scope": "alle"})

        self.assertIsNone(state["review"])
        self.assertEqual(self.bridge.items, {})
        self.assertIn("leere", state["status"]["text"])

        state = self.bridge.scan_item_lernen({"slot": "Slot 1"})

        self.assertEqual(self.bridge.items, {})
        self.assertIn("Kein Item", state["status"]["text"])
        self.assertFalse(Path("sequences/test/templates").exists())

    def test_existing_item_name_adds_a_slot_size_variant(self):
        templates = Path("sequences/test/templates")
        templates.mkdir(parents=True)
        primary = Image.new("RGB", (62, 57), (20, 80, 160))
        for x in range(0, 62, 4):
            primary.paste((220, 180, 20), (x, 0, min(x + 2, 62), 57))
        primary.save(templates / "roter_helm.png")
        self.bridge.items["Roter Helm"] = ItemProfile(
            name="Roter Helm", category="Helme", priority=3,
            template="roter_helm.png")

        # Auch wenn die automatische Zuordnung einmal nicht sicher genug ist,
        # kann der vorhandene Name bewusst ausgewaehlt werden.
        with patch(
                "autoclicker.editors.item_editor.markers._find_matching_existing_item",
                return_value=None):
            state = self.bridge.scan_lernvorschau({"scope": "alle"})
        row = state["review"]["zeilen"][0]
        self.assertIn("Roter Helm", state["review"]["itemnamen"])

        self.bridge.scan_lernvorschau_uebernehmen({"zeilen": [{
            "slot": row["slot"], "ausgewaehlt": True,
            "name": "Roter Helm", "kategorie": "Falsche Kategorie",
            "prioritaet": 99,
        }]})

        self.assertEqual(list(self.bridge.items), ["Roter Helm"])
        item = self.bridge.items["Roter Helm"]
        self.assertEqual((item.category, item.priority), ("Helme", 3))
        self.assertEqual(len(item.template_variants), 1)
        variant = templates / item.template_variants[0]
        self.assertTrue(variant.exists())
        with Image.open(variant) as learned:
            self.assertEqual(learned.size, (50, 50))
        self.assertIn("Roter Helm", self.bridge.scans["Inventar"].item_names)

    def test_item_matching_uses_only_the_exact_slot_size(self):
        from autoclicker.imaging import OPENCV_AVAILABLE
        if not OPENCV_AVAILABLE:
            self.skipTest("OpenCV nicht installiert")
        from autoclicker.runtime.item_scan import _check_profile_match

        templates = Path("sequences/test/templates")
        templates.mkdir(parents=True, exist_ok=True)

        def pattern(size, offset):
            bild = Image.new("RGB", size, (18, 22, 28))
            for x in range(4 + offset, size[0] - 4, 7):
                bild.paste((210, 40 + offset, 75),
                           (x, 5, min(x + 3, size[0]), size[1] - 5))
            return bild

        pattern((62, 57), 0).save(templates / "robe.png")
        passend = pattern((50, 50), 1)
        passend.save(templates / "robe_50x50.png")
        item = ItemProfile(
            name="Robe", template="robe.png",
            template_variants=["robe_50x50.png"], min_confidence=0.8)
        state = AutoClickerState()

        self.assertTrue(_check_profile_match(
            item, passend, 40, state, False, template_root=templates))
        with self.assertNoLogs("autoclicker", level="WARNING"):
            self.assertFalse(_check_profile_match(
                item, pattern((51, 50), 1), 40, state, False,
                template_root=templates))

        data = self.bridge._item_json(item)
        self.assertEqual(data["vorlagengroessen"], [[62, 57], [50, 50]])

        from autoclicker.persistence.serialization import _item_from_dict, _item_to_dict
        gespeicherte_daten = _item_to_dict(item)
        self.assertEqual(gespeicherte_daten["template_variants"], ["robe_50x50.png"])
        geladen = _item_from_dict(gespeicherte_daten, "Robe")
        self.assertEqual(geladen.template_names(), ["robe.png", "robe_50x50.png"])

    def test_priority_is_visible_with_category_context(self):
        js = (Path(self.old_cwd) /
              "autoclicker/editors/sequence_studio/web/app.js").read_text(
                  encoding="utf-8")
        self.assertIn("function prioritaetsUebersicht", js)
        self.assertIn("Bereits gesetzte Prioritäten", js)
        self.assertIn("Ganz nach vorn", js)
        self.assertIn('"P" + i.prioritaet', js)
        # Gelesen wird über Klassen, nicht über Positionen: `inputs[3]` verschob
        # sich still, sobald ein Feld dazwischen kam oder ein <input> zu einem
        # <select> wurde. Ein Import, der die Priorität als Kategorie liest,
        # fällt niemandem auf.
        self.assertIn('n.querySelector(".scan-review-prio").value', js)
        self.assertIn('n.querySelector(".scan-review-name").value', js)
        self.assertIn('n.querySelector(".scan-review-kategorie").wert()', js)
        self.assertNotIn("inputs[3].value", js)
        self.assertIn("function scanReviewKategorienAktualisieren", js)
        self.assertIn("Auf ausgewählte anwenden", js)
        self.assertIn("neue Vorlage für", js)
        self.assertIn("Gelernte Slot-Größen", js)

    def test_guided_mode_keeps_screenshot_source_controls_visible(self):
        html = (Path(self.old_cwd) /
                "autoclicker/editors/sequence_studio/web/index.html").read_text(
                    encoding="utf-8")
        self.assertNotIn(".scans.gefuehrt.hat-bild #ab-bild{display:none}", html)
        self.assertIn("SCAN EINRICHTEN", html)
        # Die Erklaerung dazu steht weiterhin da, aber im ⓘ statt als Absatz:
        # sie gilt immer und aendert sich nie, also stand sie bei jedem Blick
        # auf den Schritt im Weg. Was im HTML bleibt, ist der STAND.
        js = (Path(self.old_cwd) /
              "autoclicker/editors/sequence_studio/web/app.js").read_text(
                  encoding="utf-8")
        self.assertIn("derselben Aufnahmemethode neu aufgenommen", js)
        self.assertIn("folgen seiner Position automatisch", js)
        self.assertIn('$("scan-foto-info")', js)
        self.assertIn('id="scan-foto-info"', html)
        self.assertIn('id="scan-groesse"', html)
        self.assertNotIn('id="scan-bar-foto"', html)
        self.assertNotIn('id="scan-bar-lernen"', html)

    def test_window_source_moves_editor_slots_with_the_game(self):
        old_rect = (0, 0, 120, 80)
        new_rect = (200, 100, 320, 180)
        with patch("autoclicker.winapi.liste_fenster", return_value=[
                ("Mein Spiel", old_rect, 77)]):
            state = self.bridge.scan_bereich_setzen({
                "bereich": list(old_rect), "fenster": 77,
            })

        cfg = self.bridge.scans["Inventar"]
        self.assertEqual(cfg.capture_window_title, "Mein Spiel")
        self.assertEqual(cfg.capture_window_rect, old_rect)
        self.assertEqual(state["fenster_titel"], "Mein Spiel")

        bild = Image.new("RGB", (120, 80), (25, 35, 45))
        bild.putpixel((20, 20), (200, 50, 60))
        with patch("autoclicker.winapi.resolve_window",
                   return_value=("Mein Spiel", new_rect, 88)), patch(
                "autoclicker.imaging.take_consistent_window_screenshot",
                return_value=(bild, new_rect, "")):
            state = self.bridge.scan_foto()

        slot = self.bridge.slots["Slot 1"]
        self.assertEqual(slot.scan_region, (210, 110, 260, 160))
        self.assertEqual(slot.click_pos, (235, 135))
        self.assertEqual(cfg.capture_window_rect, new_rect)
        self.assertIn("folgen dem verschobenen Fenster", state["status"]["text"])
        self.assertTrue(state["dirty"])

    def test_window_source_roundtrip_and_legacy_default(self):
        from autoclicker.persistence.item_scans import load_item_scan_file
        from autoclicker.persistence.serialization import _item_scan_to_dict
        from autoclicker.utils import compact_json

        cfg = ItemScanConfig(
            name="Fensterinventar", capture_window_title="Mein Spiel",
            capture_window_index=2,
            capture_window_rect=(100, 200, 900, 700),
        )
        path = Path("fenster_scan.json")
        path.write_text(compact_json(_item_scan_to_dict(cfg)), encoding="utf-8")
        loaded = load_item_scan_file(path)
        self.assertEqual(loaded.capture_window_title, "Mein Spiel")
        self.assertEqual(loaded.capture_window_index, 2)
        self.assertEqual(loaded.capture_window_rect, (100, 200, 900, 700))

        legacy = Path("alter_scan.json")
        legacy.write_text('{"name":"Alt"}', encoding="utf-8")
        loaded_legacy = load_item_scan_file(legacy)
        self.assertIsNone(loaded_legacy.capture_window_title)
        self.assertIsNone(loaded_legacy.capture_window_rect)

    def test_window_geometry_maps_move_and_resize(self):
        from autoclicker.editors.scan_services import (
            map_point_between_rects, map_region_between_rects,
        )

        source = (100, 100, 1100, 700)
        moved = (300, 200, 1300, 800)
        self.assertEqual(
            map_region_between_rects((150, 160, 250, 260), source, moved),
            (350, 260, 450, 360))
        self.assertEqual(
            map_point_between_rects((200, 210), source, moved), (400, 310))

        resized = (0, 0, 2000, 1200)
        self.assertEqual(
            map_region_between_rects((100, 100, 200, 200), source, resized),
            (0, 0, 200, 200))

    def test_live_window_scan_uses_one_shared_capture_and_relative_click(self):
        import autoclicker.runtime.item_scan as runtime

        old_rect = (100, 100, 300, 300)
        new_rect = (300, 200, 500, 400)
        slot = ItemSlot(
            name="Fensterslot", scan_region=(110, 120, 130, 140),
            click_pos=(120, 130), slot_color=(10, 20, 30))
        item = ItemProfile(name="Treffer", marker_colors=[(200, 50, 60)])
        cfg = ItemScanConfig(
            name="Live", slots=[slot], items=[item],
            capture_window_title="Mein Spiel", capture_window_index=0,
            capture_window_rect=old_rect,
        )
        state = AutoClickerState()
        state.item_scans = {"Live": cfg}
        full = Image.new("RGB", (200, 200), (10, 20, 30))
        full.paste((200, 50, 60), (10, 20, 30, 40))
        seen_sizes = []

        def match(_item, image, *_args, **_kwargs):
            seen_sizes.append(image.size)
            return True, 1.0

        with patch.object(runtime, "resolve_window",
                          return_value=("Mein Spiel", new_rect, 99)), patch.object(
                runtime, "take_consistent_window_screenshot",
                return_value=(full, new_rect, "")) as capture, patch.object(
                runtime, "take_screenshot",
                side_effect=AssertionError("Legacy-Aufnahme darf nicht laufen")), patch.object(
                runtime, "_check_profile_match", side_effect=match), patch.object(
                runtime, "_park_mouse_for_scan"):
            result = runtime.execute_item_scan(state, "Live")

        capture.assert_called_once_with(99)
        self.assertEqual(seen_sizes, [(20, 20)])
        self.assertEqual(result[0][0], (320, 230))
        # Die global gespeicherten Slots bleiben unangetastet; die Anpassung gilt
        # in der Runtime nur für diesen Lauf.
        self.assertEqual(slot.click_pos, (120, 130))

    def test_disabled_slot_is_kept_but_not_scanned(self):
        import autoclicker.runtime.item_scan as runtime

        active = ItemSlot(
            name="Aktiv", scan_region=(0, 0, 20, 20), click_pos=(10, 10))
        parked = ItemSlot(
            name="Geparkt", scan_region=(20, 0, 40, 20), click_pos=(30, 10),
            enabled=False)
        item = ItemProfile(name="Treffer", marker_colors=[(200, 50, 60)])
        state = AutoClickerState()
        state.config.scan_slot_delay = 0
        state.item_scans = {
            "Inventar": ItemScanConfig(
                name="Inventar", slots=[active, parked], items=[item])}
        bild = Image.new("RGB", (20, 20), (200, 50, 60))

        with patch.object(runtime, "take_screenshot", return_value=bild) as capture, \
                patch.object(runtime, "_check_profile_match", return_value=(True, 1.0)), \
                patch.object(runtime, "_park_mouse_for_scan"):
            result = runtime.execute_item_scan(state, "Inventar")

        self.assertEqual([slot.name for slot in state.item_scans["Inventar"].slots],
                         ["Aktiv", "Geparkt"])
        self.assertEqual(capture.call_count, 1)
        self.assertEqual([treffer[0] for treffer in result], [(10, 10)])
        self.assertEqual([treffer[1].name for treffer in result], ["Treffer"])


if __name__ == "__main__":
    unittest.main()
