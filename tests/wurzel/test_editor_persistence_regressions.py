"""Gegenproben für Sequenzbesitz, Editor-Abbruch und Speicherfehler."""

import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from test_support import install_platform_stubs

install_platform_stubs()

from autoclicker.models import (
    AutoClickerState, BossProfile, BossScanConfig, IconScanConfig,
    ItemProfile, ItemScanConfig, Sequence,
)
from autoclicker.persistence import boss_scans, icon_scans, item_scans, presets
from autoclicker.persistence import globals as bestand
from autoclicker.persistence.sequences import active_templates_dir
from autoclicker.editors.item_editor import editor, commands
from autoclicker.editors.sequence_studio.bridge import StudioBridge
from autoclicker.handlers import _sequenz_daten_laden


class EditorPersistenzTest(unittest.TestCase):
    def setUp(self):
        self.cwd = os.getcwd()
        self.temp = tempfile.TemporaryDirectory()
        os.chdir(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(os.chdir, self.cwd)
        self.ausgabe = io.StringIO()
        self.umleitung = redirect_stdout(self.ausgabe)
        self.umleitung.__enter__()
        self.addCleanup(self.umleitung.__exit__, None, None, None)
        self.state = AutoClickerState()
        self.state.active_sequence = Sequence(name="Alt")
        self.scan = ItemScanConfig("Inventar", items=[
            ItemProfile("A", priority=9), ItemProfile("B", priority=1),
        ], owner_sequence="Alt")
        self.state.item_scans = {self.scan.name: self.scan}
        item_scans.bind_item_scan_context(self.state, self.scan.name)

    def test_sequenzwechsel_entfernt_fremden_bestand(self):
        self.state.icon_scans = {"Icon": IconScanConfig("Icon", owner_sequence="Alt")}
        self.state.global_bosses = [BossProfile("Drache")]
        self.state.active_sequence = Sequence(name="Neu")
        _sequenz_daten_laden(self.state)
        self.assertEqual(self.state.item_scans, {})
        self.assertEqual(self.state.icon_scans, {})
        self.assertEqual(self.state.global_bosses, [])
        self.assertEqual(self.state.global_items, {})
        self.assertEqual(self.state.active_item_scan, "")

    def test_neuladen_entfernt_geloeschte_scans(self):
        item_scans.save_item_scan(self.scan)
        self.state.item_scans["Veraltet"] = ItemScanConfig("Veraltet", owner_sequence="Alt")
        item_scans.load_all_item_scans(self.state)
        self.assertEqual(list(self.state.item_scans), ["Inventar"])

    def test_sequenzwechsel_laedt_neuen_bestand_ohne_alte_eintraege(self):
        neu = ItemScanConfig("Neu", items=[ItemProfile("NeuItem")], owner_sequence="Neu")
        item_scans.save_item_scan(neu)
        self.state.active_sequence = Sequence(name="Neu")
        _sequenz_daten_laden(self.state)
        self.assertEqual(list(self.state.item_scans), ["Neu"])
        self.assertEqual(list(self.state.global_items), ["NeuItem"])
        self.assertIs(self.state.global_items["NeuItem"], self.state.item_scans["Neu"].items[0])

    def test_anzeige_und_loeschen_verwenden_dieselbe_nummer(self):
        editor._dispatch_command(self.state, "show", "show")
        erste = next(z for z in self.ausgabe.getvalue().splitlines() if z.strip().startswith("1."))
        angezeigt = "A" if " A:" in erste else "B"
        editor._handle_delete_single(self.state, "del 1")
        self.assertNotIn(angezeigt, self.state.global_items)

    def test_edit_fragt_vor_namenskollision(self):
        with patch.object(editor, "edit_item", return_value=ItemProfile("B")), \
                patch.object(editor, "confirm", return_value=False) as frage:
            editor._handle_edit(self.state, "edit 1")
        frage.assert_called_once()
        self.assertEqual(list(self.state.global_items), ["A", "B"])
        self.assertEqual(self.state.global_items["B"].priority, 1)

    def test_cancel_stellt_scan_und_vorlagen_wieder_her(self):
        self.scan.items = [ItemProfile("Alt", template="alt.png")]
        item_scans.bind_item_scan_context(self.state, self.scan.name)
        ordner = active_templates_dir(self.state)
        ordner.mkdir(parents=True)
        (ordner / "alt.png").write_bytes(b"Original")
        item_scans.save_item_scan(self.scan)
        datei = Path("sequences/alt/item_scans/inventar.json")
        vorher = datei.read_bytes()
        with patch.object(editor, "PILLOW_AVAILABLE", True), \
                patch.object(editor, "safe_input", side_effect=["rename 1", "cancel"]), \
                patch.object(commands, "safe_input", return_value="Neu"):
            editor.run_global_item_editor(self.state)
        self.assertEqual(list(self.state.global_items), ["Alt"])
        self.assertEqual([i.name for i in self.state.item_scans["Inventar"].items], ["Alt"])
        self.assertEqual((ordner / "alt.png").read_bytes(), b"Original")
        self.assertFalse((ordner / "neu.png").exists())
        self.assertEqual(datei.read_bytes(), vorher)

    def test_cancel_nach_preset_laden_stellt_datei_wieder_her(self):
        item_scans.save_item_scan(self.scan)
        datei = Path("sequences/alt/item_scans/inventar.json")
        vorher = datei.read_bytes()
        preset = Path("presets/items/fremd.json")
        preset.parent.mkdir(parents=True)
        preset.write_text(json.dumps({"Fremd": {}}), encoding="utf-8")
        with patch.object(editor, "PILLOW_AVAILABLE", True), \
                patch.object(editor, "safe_input", side_effect=["load fremd", "cancel"]):
            editor.run_global_item_editor(self.state)
        self.assertEqual(datei.read_bytes(), vorher)
        self.assertEqual(self.state.item_scans["Inventar"].item_names, ["A", "B"])

    def test_rename_dateifehler_laesst_referenz_unveraendert(self):
        self.state.global_items["A"].template = "a.png"
        ordner = active_templates_dir(self.state)
        ordner.mkdir(parents=True)
        (ordner / "a.png").write_bytes(b"Original")
        with patch.object(Path, "rename", side_effect=PermissionError("gesperrt")):
            self.assertFalse(commands._apply_item_rename(self.state, "A", "Neu"))
        self.assertEqual(self.state.global_items["A"].template, "a.png")
        self.assertEqual((ordner / "a.png").read_bytes(), b"Original")

    def test_rename_erhaelt_vorlage_eines_anderen_scans(self):
        self.state.global_items["A"].template = "a.png"
        fremd = ItemScanConfig("Zweiter", items=[ItemProfile("A", template="a.png")],
                              owner_sequence="Alt")
        self.state.item_scans[fremd.name] = fremd
        item_scans.save_item_scan(fremd)
        ordner = active_templates_dir(self.state)
        ordner.mkdir(parents=True)
        (ordner / "a.png").write_bytes(b"Original")
        self.assertTrue(commands._apply_item_rename(self.state, "A", "Neu"))
        self.assertTrue(bestand.save_global_items(self.state))
        for name in ("inventar", "zweiter"):
            geladen = item_scans.load_item_scan_file(Path(f"sequences/alt/item_scans/{name}.json"))
            item = next(i for i in geladen.items if i.name == ("Neu" if name == "inventar" else "A"))
            self.assertEqual((ordner / item.template).read_bytes(), b"Original")
        self.assertEqual(fremd.items[0].name, "A")

    def test_speicherfehler_wird_bis_zum_aufrufer_gemeldet(self):
        for speichern in (bestand.save_global_items, bestand.save_global_slots):
            with self.subTest(speichern=speichern.__name__), \
                    patch.object(item_scans, "save_item_scan", return_value=False):
                self.ausgabe.seek(0)
                self.ausgabe.truncate()
                self.assertIs(speichern(self.state), False)
                self.assertNotIn("[SAVE]", self.ausgabe.getvalue())

    def test_done_bleibt_bei_speicherfehler_offen(self):
        with patch.object(editor, "PILLOW_AVAILABLE", True), \
                patch.object(editor, "save_global_items", side_effect=[False, True]) as speichern, \
                patch.object(editor, "safe_input", side_effect=["done", "done"]):
            editor.run_global_item_editor(self.state)
        self.assertEqual(speichern.call_count, 2)

    def test_done_speichert_und_abbruch_durch_tastatur_verwirft(self):
        for ende in ("done", KeyboardInterrupt(), EOFError()):
            with self.subTest(ende=type(ende).__name__):
                self.scan.items = [ItemProfile("A"), ItemProfile("B")]
                item_scans.bind_item_scan_context(self.state, self.scan.name)
                item_scans.save_item_scan(self.scan)
                with patch.object(editor, "PILLOW_AVAILABLE", True), \
                        patch.object(editor, "safe_input", side_effect=["del 1", ende]):
                    editor.run_global_item_editor(self.state)
                erwartet = ["B"] if ende == "done" else ["A", "B"]
                geladen = item_scans.load_item_scan_file(Path("sequences/alt/item_scans/inventar.json"))
                self.assertEqual(geladen.item_names, erwartet)
                self.assertEqual(list(self.state.global_items), erwartet)

    def test_studio_lehnt_reservierten_bossnamen_auch_beim_umbenennen_ab(self):
        bridge = StudioBridge(Sequence(name="Alt"), Path("sequences/alt/sequence.json"), "sequences")
        bridge._scan_geladen = True
        bridge.boss_scan_neu({"name": "Bibliothek"})
        self.assertEqual(bridge.boss_scans, {})
        bridge.boss_scan_neu({"name": "Erlaubt"})
        bridge.boss_scan_setzen({"feld": "name", "wert": "bibliothek!"})
        self.assertEqual(list(bridge.boss_scans), ["Erlaubt"])

    def test_reservierter_bossname_ueberschreibt_keine_bibliothek(self):
        self.state.global_bosses = [BossProfile("Drache")]
        boss_scans.save_global_bosses(self.state)
        datei = Path("sequences/alt/boss_scans/bibliothek.json")
        vorher = datei.read_bytes()
        for name in ("bibliothek", "Bibliothek", "bibliothek!"):
            with self.subTest(name=name):
                self.assertFalse(boss_scans.save_boss_scan(BossScanConfig(name, owner_sequence="Alt")))
                self.assertEqual(datei.read_bytes(), vorher)

    def test_scan_loader_fangen_falsche_json_strukturen_ab(self):
        faelle = [(item_scans.load_item_scan_file, x) for x in (
            [], None, 3, {"name": "Scan", "items": {"A": []}},
            {"name": "Scan", "slots": {"S": None}},
            {"name": "Scan", "slots": []}, {"name": "Scan", "items": None},
        )]
        faelle += [(boss_scans.load_boss_scan_file, []), (icon_scans.load_icon_scan_file, [])]
        datei = Path("scan.json")
        for loader, daten in faelle:
            with self.subTest(loader=loader.__name__, daten=daten):
                datei.write_text(json.dumps(daten), encoding="utf-8")
                self.assertIsNone(loader(datei))

    def test_defektes_preset_laesst_bestand_und_datei_unveraendert(self):
        item_scans.save_item_scan(self.scan)
        scan_datei = Path("sequences/alt/item_scans/inventar.json")
        vorher = scan_datei.read_bytes()
        for art, laden, attribut in (
                ("items", presets.load_item_preset, "global_items"),
                ("slots", presets.load_slot_preset, "global_slots")):
            datei = Path("presets") / art / "defekt.json"
            datei.parent.mkdir(parents=True, exist_ok=True)
            bestand_vorher = dict(getattr(self.state, attribut))
            gueltig = {"scan_region": [0, 0, 10, 10], "click_pos": [5, 5]} if art == "slots" else {}
            for daten in ([], {"Gueltig": gueltig, "Defekt": None}):
                with self.subTest(art=art, daten=daten):
                    datei.write_text(json.dumps(daten), encoding="utf-8")
                    self.assertFalse(laden(self.state, "defekt"))
                    self.assertEqual(getattr(self.state, attribut), bestand_vorher)
                    self.assertEqual(scan_datei.read_bytes(), vorher)

    def test_preset_meldet_speicherfehler(self):
        for art, laden, speichern in (
                ("items", presets.load_item_preset, "save_global_items"),
                ("slots", presets.load_slot_preset, "save_global_slots")):
            with self.subTest(art=art):
                datei = Path("presets") / art / "neu.json"
                datei.parent.mkdir(parents=True, exist_ok=True)
                eintrag = {"scan_region": [0, 0, 10, 10], "click_pos": [5, 5]} if art == "slots" else {}
                datei.write_text(json.dumps({"Neu": eintrag}), encoding="utf-8")
                with patch.object(presets, speichern, return_value=False) as speichern_mock:
                    self.assertFalse(laden(self.state, "neu"))
                speichern_mock.assert_called_once()

    def test_scan_speichern_faengt_fehler_beim_ordner_anlegen_ab(self):
        for speichern, cfg in (
                (item_scans.save_item_scan, self.scan),
                (boss_scans.save_boss_scan, BossScanConfig("Boss", owner_sequence="Alt")),
                (icon_scans.save_icon_scan, IconScanConfig("Icon", owner_sequence="Alt"))):
            with self.subTest(speichern=speichern.__name__), \
                    patch.object(Path, "mkdir", side_effect=PermissionError("gesperrt")):
                self.assertFalse(speichern(cfg))


if __name__ == "__main__":
    unittest.main()
