"""Regressionstests für den Sicherheitsrand des Setup-Imports/-Exports."""

import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from test_support import install_platform_stubs

install_platform_stubs()

from autoclicker.import_export import export_bundle, import_bundle, kalibriere_bestand
from autoclicker.models import (
    AutoClickerState, ClickPoint, ItemScanConfig, ItemSlot, Sequence,
)
from autoclicker.persistence import load_item_scan_file
from autoclicker.persistence.sequences import sequence_dir


def _manifest(version=1):
    return {
        "version": version,
        "reference_points": {"point1": [0, 0], "point2": [10, 10]},
        "contents": {},
    }


def _sequence_data(name):
    return {
        "name": name, "schema_version": 4, "points": [],
        "init_steps": [], "loop_phases": [], "end_steps": [],
    }


def _write_sequence(name):
    root = Path("sequences") / name
    root.mkdir(parents=True, exist_ok=True)
    (root / "sequence.json").write_text(
        json.dumps(_sequence_data(name)), encoding="utf-8")
    return root


class ImportExportSecurityTest(unittest.TestCase):
    def setUp(self):
        self._old_cwd = os.getcwd()
        self._temp = tempfile.TemporaryDirectory()
        os.chdir(self._temp.name)

    def tearDown(self):
        os.chdir(self._old_cwd)
        self._temp.cleanup()

    def test_export_does_not_read_template_outside_template_directory(self):
        root = _write_sequence("Sicher")
        (root / "item_scans").mkdir()
        (root / "item_scans/scan.json").write_text(json.dumps({
            "name": "Scan", "slots": {},
            "items": {"X": {"name": "X", "template": "../../secret.png"}},
        }), encoding="utf-8")
        Path("secret.png").write_bytes(b"private")
        state = AutoClickerState()

        ok, _ = export_bundle(
            state, "bundle.zip", (0, 0), (10, 10),
            include_points=False, include_sequences=False, include_slots=False,
            include_item_scans=False, include_boss_scans=False,
            include_icon_scans=False, include_config=False,
        )

        self.assertTrue(ok)
        with zipfile.ZipFile("bundle.zip") as zf:
            self.assertFalse(any(name.endswith("secret.png") for name in zf.namelist()))

    def test_distinct_sequence_folders_stay_distinct_in_archive(self):
        _write_sequence("Alpha")
        _write_sequence("Beta")
        state = AutoClickerState()
        ok, _ = export_bundle(
            state, "bundle.zip", (0, 0), (10, 10), include_points=False,
            include_slots=False, include_items=False, include_item_scans=False,
            include_boss_scans=False, include_icon_scans=False, include_config=False,
        )

        self.assertTrue(ok)
        with zipfile.ZipFile("bundle.zip") as zf:
            entries = [name for name in zf.namelist() if name.endswith("/sequence.json")]
        self.assertEqual(len(entries), 2)
        self.assertEqual(len(set(entries)), 2)

    def test_export_includes_all_item_template_sizes(self):
        root = _write_sequence("Farm")
        (root / "templates").mkdir()
        (root / "templates/robe.png").write_bytes(b"primary")
        (root / "templates/robe_62x57.png").write_bytes(b"variant")
        (root / "item_scans").mkdir()
        (root / "item_scans/inventar.json").write_text(json.dumps({
            "name": "Inventar", "slots": {},
            "items": {"Robe": {
                "name": "Robe", "template": "robe.png",
                "template_variants": ["robe_62x57.png"],
            }},
        }), encoding="utf-8")
        state = AutoClickerState()

        ok, _ = export_bundle(
            state, "bundle.zip", (0, 0), (10, 10),
            include_points=False, include_sequences=False, include_slots=False,
            include_item_scans=False, include_boss_scans=False,
            include_icon_scans=False, include_config=False,
        )

        self.assertTrue(ok)
        with zipfile.ZipFile("bundle.zip") as zf:
            self.assertIn("sequences/Farm/templates/robe.png", zf.namelist())
            self.assertIn("sequences/Farm/templates/robe_62x57.png", zf.namelist())
            scan = json.loads(zf.read("sequences/Farm/item_scans/inventar.json"))
        self.assertEqual(
            scan["items"]["Robe"]["template_variants"], ["robe_62x57.png"])

    def test_import_rejects_wrong_manifest_version_before_writing(self):
        with zipfile.ZipFile("bundle.zip", "w") as zf:
            zf.writestr("manifest.json", json.dumps(_manifest(version=999)))
            zf.writestr("points.json", json.dumps([{"id": 2, "x": 1, "y": 1}]))
        state = AutoClickerState()
        state.points = [ClickPoint(5, 5, "Alt", 1)]

        ok, _ = import_bundle(state, "bundle.zip", import_config=False)

        self.assertFalse(ok)
        self.assertEqual([(p.id, p.name) for p in state.points], [(1, "Alt")])
        self.assertFalse(Path("points.json").exists())

    def test_failed_import_rolls_back_state_and_files(self):
        from autoclicker import import_export as modul
        original = _write_sequence("bestand")
        vorher = (original / "sequence.json").read_bytes()
        manifest = _manifest()
        manifest["layout"] = "sequence-folders"
        with zipfile.ZipFile("bundle.zip", "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("sequences/A/sequence.json", json.dumps(_sequence_data("bestand")))
            zf.writestr("sequences/A/templates/neu.png", b"neues Bild")
            zf.writestr("sequences/Z/sequence.json", json.dumps(_sequence_data("defekt")))
        state = AutoClickerState()
        state.points = [ClickPoint(5, 5, "Alt", 1)]
        echtes_copytree = modul.shutil.copytree
        mutiert = []

        def kopieren(quelle, ziel, *args, **kwargs):
            if Path(ziel).name == "defekt":
                mutiert.append((original / "templates/neu.png").read_bytes())
                raise OSError("Fehler nach dem ersten ersetzten Ordner")
            return echtes_copytree(quelle, ziel, *args, **kwargs)

        with patch.object(modul.shutil, "copytree", side_effect=kopieren):
            ok, _ = import_bundle(state, "bundle.zip", import_config=False, merge=False)

        self.assertFalse(ok)
        self.assertEqual(mutiert, [b"neues Bild"])
        self.assertEqual([(p.id, p.name) for p in state.points], [(1, "Alt")])
        self.assertEqual(state.sequences, {})
        self.assertEqual((original / "sequence.json").read_bytes(), vorher)
        self.assertFalse((original / "templates/neu.png").exists())
        self.assertFalse(Path("sequences/defekt").exists())

    def test_windows_archivpfade_werden_vor_dem_schreiben_abgelehnt(self):
        from autoclicker.import_export import _sicherer_bundle_pfad
        for name in ("sequences/farm/..\\..\\fremd.txt",
                     "sequences/farm/C:\\fremd.txt", "sequences/farm/bild.png:strom",
                     "sequences/farm/../../fremd.txt"):
            with self.subTest(name=name):
                self.assertIsNone(_sicherer_bundle_pfad(name))

    def test_boss_bibliothek_ueberlebt_einen_transformierten_import(self):
        manifest = _manifest()
        manifest["layout"] = "sequence-folders"
        bibliothek = [{"name": "Drache", "action": "click", "action_point_id": 7}]
        seq = _sequence_data("farm")
        seq["points"] = [{"id": 7, "x": 10, "y": 20}]
        with zipfile.ZipFile("bundle.zip", "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("sequences/farm/sequence.json", json.dumps(seq))
            zf.writestr("sequences/farm/boss_scans/bibliothek.json", json.dumps(bibliothek))
        ok, meldung = import_bundle(AutoClickerState(), "bundle.zip", import_config=False,
                                   transform={"scale_x": 1, "scale_y": 1,
                                              "offset_x": 30, "offset_y": 40})
        self.assertTrue(ok, meldung)
        self.assertEqual(json.loads(Path("sequences/farm/boss_scans/bibliothek.json")
                                    .read_text(encoding="utf-8")), bibliothek)
        self.assertEqual(json.loads(Path("sequences/farm/sequence.json")
                                    .read_text(encoding="utf-8"))["points"][0]["x"], 40)

    def test_failed_folder_import_rolls_back_nested_sequences(self):
        original = _write_sequence("Bestand")
        marker = original / "item_scans" / "scan.json"
        marker.parent.mkdir()
        marker.write_text('{"name": "Alt"}', encoding="utf-8")
        template = original / "templates" / "item.png"
        template.parent.mkdir()
        template.write_bytes(b"altes bild")
        manifest = _manifest()
        manifest["layout"] = "sequence-folders"
        manifest["contents"]["sequences"] = ["ABestand", "ZDefekt"]
        with zipfile.ZipFile("bundle.zip", "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr(
                "sequences/ABestand/sequence.json",
                json.dumps(_sequence_data("Bestand")))
            zf.writestr("sequences/ABestand/templates/item.png", b"neues bild")
            # Ein gültiger Eintrag erzeugt den zweiten Ordner, aber ohne dessen
            # Pflichtdatei sequence.json. Der Fehler tritt dadurch erst auf,
            # nachdem "Bestand" bereits ersetzt wurde.
            zf.writestr("sequences/ZDefekt/templates/item.png", b"beliebig")
        state = AutoClickerState()
        bestand = Sequence(name="Bestand")
        state.sequences[bestand.name] = bestand

        ok, _ = import_bundle(state, "bundle.zip", import_config=False)

        self.assertFalse(ok)
        self.assertEqual(list(state.sequences), ["Bestand"])
        self.assertEqual(marker.read_text(encoding="utf-8"), '{"name": "Alt"}')
        self.assertEqual(template.read_bytes(), b"altes bild")

    def test_import_keeps_window_scan_anchor_aligned_with_remapped_slots(self):
        manifest = _manifest()
        manifest["layout"] = "sequence-folders"
        manifest["contents"]["sequences"] = ["Farm"]
        slot = {
            "scan_region": [110, 120, 130, 140],
            "click_pos": [120, 130],
        }
        scan = {
            "name": "Live", "slots": {"Slot 1": slot}, "items": {},
            "reverse": True, "capture_window_title": "Mein Spiel",
            "capture_window_index": 2,
            "capture_window_rect": [100, 100, 300, 300],
        }
        with zipfile.ZipFile("bundle.zip", "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("sequences/Farm/sequence.json", json.dumps(_sequence_data("Farm")))
            zf.writestr("sequences/Farm/item_scans/live.json", json.dumps(scan))

        transform = {"scale_x": 2.0, "scale_y": 2.0,
                     "offset_x": 5, "offset_y": 7}
        state = AutoClickerState()
        ok, _ = import_bundle(
            state, "bundle.zip", transform=transform,
            import_points=False, import_sequences=False, import_items=False,
            import_boss_scans=False, import_icon_scans=False,
            import_config=False,
        )

        self.assertTrue(ok)
        # Der Besitzordner heisst, was `sanitize_filename()` daraus macht
        # (klein geschrieben) — nicht, wie der Pfad im Buendel lautete.
        imported_scan = load_item_scan_file(
            sequence_dir("Farm") / "item_scans" / "live.json", "Farm")
        self.assertIsNotNone(imported_scan)
        imported_slot = imported_scan.slots[0]
        self.assertEqual(imported_slot.scan_region, (225, 247, 265, 287))
        self.assertEqual(imported_scan.capture_window_rect, (205, 207, 605, 607))
        self.assertEqual(imported_scan.capture_window_title, "Mein Spiel")
        self.assertEqual(imported_scan.capture_window_index, 2)
        self.assertTrue(imported_scan.reverse)

    def test_calibration_moves_slot_and_its_window_anchor_together(self):
        state = AutoClickerState()
        sequence = Sequence(name="Farm")
        state.sequences[sequence.name] = sequence
        state.active_sequence = sequence
        slot = ItemSlot("Slot 1", (10, 20, 30, 40), (20, 30))
        state.global_slots[slot.name] = slot
        state.item_scans["Live"] = ItemScanConfig(
            name="Live", slots=[slot], capture_window_title="Mein Spiel",
            capture_window_rect=(0, 0, 100, 100), owner_sequence="Farm",
        )
        transform = {"scale_x": 1.0, "scale_y": 1.0,
                     "offset_x": 50, "offset_y": -10}

        counts = kalibriere_bestand(
            state, transform, mit_scans=True, mit_sequenzen=False,
            mit_slots=True)

        self.assertEqual(slot.scan_region, (60, 10, 80, 30))
        self.assertEqual(
            state.item_scans["Live"].capture_window_rect, (50, -10, 150, 90))
        self.assertEqual(counts["item_scans"], 1)


if __name__ == "__main__":
    unittest.main()
