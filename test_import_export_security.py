"""Regressionstests für den Sicherheitsrand des Setup-Imports/-Exports."""

import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile

from test_support import install_platform_stubs

install_platform_stubs()

from autoclicker.import_export import export_bundle, import_bundle, kalibriere_bestand
from autoclicker.models import (
    AutoClickerState, ClickPoint, ItemProfile, ItemScanConfig, ItemSlot, Sequence,
)


def _manifest(version=1):
    return {
        "version": version,
        "reference_points": {"point1": [0, 0], "point2": [10, 10]},
        "contents": {},
    }


class ImportExportSecurityTest(unittest.TestCase):
    def setUp(self):
        self._old_cwd = os.getcwd()
        self._temp = tempfile.TemporaryDirectory()
        os.chdir(self._temp.name)

    def tearDown(self):
        os.chdir(self._old_cwd)
        self._temp.cleanup()

    def test_export_does_not_read_template_outside_template_directory(self):
        Path("items/templates").mkdir(parents=True)
        Path("secret.png").write_bytes(b"private")
        state = AutoClickerState()
        state.global_items["X"] = ItemProfile(name="X", template="../../secret.png")

        ok, _ = export_bundle(
            state, "bundle.zip", (0, 0), (10, 10),
            include_points=False, include_sequences=False, include_slots=False,
            include_item_scans=False, include_boss_scans=False,
            include_icon_scans=False, include_config=False,
        )

        self.assertTrue(ok)
        with zipfile.ZipFile("bundle.zip") as zf:
            self.assertFalse(any(name.startswith("templates/") for name in zf.namelist()))

    def test_sanitized_name_collisions_get_unique_archive_entries(self):
        state = AutoClickerState()
        state.sequences = {"Test?": Sequence(name="Test?"), "Test*": Sequence(name="Test*")}
        ok, _ = export_bundle(
            state, "bundle.zip", (0, 0), (10, 10), include_points=False,
            include_slots=False, include_items=False, include_item_scans=False,
            include_boss_scans=False, include_icon_scans=False, include_config=False,
        )

        self.assertTrue(ok)
        with zipfile.ZipFile("bundle.zip") as zf:
            entries = [name for name in zf.namelist() if name.startswith("sequences/")]
        self.assertEqual(len(entries), 2)
        self.assertEqual(len(set(entries)), 2)

    def test_export_includes_all_item_template_sizes(self):
        Path("items/templates").mkdir(parents=True)
        Path("items/templates/robe.png").write_bytes(b"primary")
        Path("items/templates/robe_62x57.png").write_bytes(b"variant")
        state = AutoClickerState()
        state.global_items["Robe"] = ItemProfile(
            name="Robe", template="robe.png",
            template_variants=["robe_62x57.png"])

        ok, _ = export_bundle(
            state, "bundle.zip", (0, 0), (10, 10),
            include_points=False, include_sequences=False, include_slots=False,
            include_item_scans=False, include_boss_scans=False,
            include_icon_scans=False, include_config=False,
        )

        self.assertTrue(ok)
        with zipfile.ZipFile("bundle.zip") as zf:
            self.assertIn("templates/robe.png", zf.namelist())
            self.assertIn("templates/robe_62x57.png", zf.namelist())
            items = json.loads(zf.read("items.json"))
        self.assertEqual(items["Robe"]["template_variants"], ["robe_62x57.png"])

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
        sequence = {
            "name": "neu", "schema_version": 2, "init_steps": [], "end_steps": [],
            "loop_phases": [],
        }
        with zipfile.ZipFile("bundle.zip", "w") as zf:
            zf.writestr("manifest.json", json.dumps(_manifest()))
            zf.writestr("sequences/neu.json", json.dumps(sequence))
            zf.writestr("slots.json", json.dumps({"Defekt": {}}))
        state = AutoClickerState()
        state.points = [ClickPoint(5, 5, "Alt", 1)]

        ok, _ = import_bundle(state, "bundle.zip", import_config=False)

        self.assertFalse(ok)
        self.assertEqual([(p.id, p.name) for p in state.points], [(1, "Alt")])
        self.assertEqual(state.sequences, {})
        self.assertFalse(Path("sequences").exists())
        self.assertFalse(Path("slots").exists())

    def test_import_keeps_window_scan_anchor_aligned_with_remapped_slots(self):
        manifest = _manifest()
        slot = {
            "scan_region": [110, 120, 130, 140],
            "click_pos": [120, 130],
        }
        scan = {
            "name": "Live", "slot_names": ["Slot 1"], "item_names": [],
            "reverse": True, "capture_window_title": "Mein Spiel",
            "capture_window_index": 2,
            "capture_window_rect": [100, 100, 300, 300],
        }
        with zipfile.ZipFile("bundle.zip", "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("slots.json", json.dumps({"Slot 1": slot}))
            zf.writestr("item_scans/live.json", json.dumps(scan))

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
        imported_slot = state.global_slots["Slot 1"]
        imported_scan = state.item_scans["Live"]
        self.assertEqual(imported_slot.scan_region, (225, 247, 265, 287))
        self.assertEqual(imported_scan.capture_window_rect, (205, 207, 605, 607))
        self.assertEqual(imported_scan.capture_window_title, "Mein Spiel")
        self.assertEqual(imported_scan.capture_window_index, 2)
        self.assertTrue(imported_scan.reverse)

    def test_calibration_moves_slot_and_its_window_anchor_together(self):
        state = AutoClickerState()
        slot = ItemSlot("Slot 1", (10, 20, 30, 40), (20, 30))
        state.global_slots[slot.name] = slot
        state.item_scans["Live"] = ItemScanConfig(
            name="Live", slots=[slot], capture_window_title="Mein Spiel",
            capture_window_rect=(0, 0, 100, 100),
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
