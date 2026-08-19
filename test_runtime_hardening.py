"""Regressionstests für Bilderkennung, OCR-Cache und asynchrone Fehler."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_support import install_platform_stubs

install_platform_stubs()

from autoclicker import imaging, ocr
from autoclicker.models import (
    AutoClickerState, ItemProfile, ItemScanConfig, ItemSlot, SequenceStep,
    SCAN_MODE_EVERY,
)
from autoclicker.runtime import boss_detection, item_scan


class RuntimeHardeningTest(unittest.TestCase):
    def test_template_path_stays_below_template_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "templates"
            root.mkdir()
            with patch.object(imaging, "TEMPLATES_DIR", str(root)):
                self.assertIsNone(imaging._template_path("../secret.png"))
                self.assertIsNone(imaging._template_path(str(Path(directory) / "x.png")))
                safe = imaging._template_path("nested/item.png")
            self.assertEqual(Path(safe), (root / "nested/item.png").resolve())

    def test_easyocr_cache_is_keyed_by_languages(self):
        created = []

        class FakeEasyOCR:
            @staticmethod
            def Reader(languages, **kwargs):
                reader = object()
                created.append((tuple(languages), reader))
                return reader

        with patch.object(ocr, "_easyocr_mod", FakeEasyOCR), \
                patch.object(ocr, "_cuda_available", return_value=False):
            ocr._easyocr_readers.clear()
            english_1 = ocr._get_easyocr_reader(["en"])
            english_2 = ocr._get_easyocr_reader(["en"])
            german = ocr._get_easyocr_reader(["de"])

        self.assertIs(english_1, english_2)
        self.assertIsNot(english_1, german)
        self.assertEqual([entry[0] for entry in created], [("en",), ("de",)])

    def test_item_scan_chooses_highest_quality_match(self):
        state = AutoClickerState()
        state.config.scan_slot_delay = 0
        slot = ItemSlot("Slot", (0, 0, 10, 10), (5, 5))
        low = ItemProfile(name="Niedrig", template="low.png")
        high = ItemProfile(name="Hoch", template="high.png")
        state.item_scans["Test"] = ItemScanConfig(
            name="Test", slots=[slot], items=[low, high])

        def score(profile, *args, return_score=False, **kwargs):
            value = 0.91 if profile.name == "Hoch" else 0.82
            return (True, value) if return_score else True

        with patch.object(item_scan, "take_screenshot", return_value=object()), \
                patch.object(item_scan, "_park_mouse_for_scan"), \
                patch.object(item_scan, "_check_profile_match", side_effect=score):
            result = item_scan.execute_item_scan(state, "Test", SCAN_MODE_EVERY)

        self.assertEqual(result[0][1].name, "Hoch")

    def test_async_boss_failure_is_always_logged(self):
        state = AutoClickerState()
        step = SequenceStep(boss_scan="Test")
        with patch.object(boss_detection, "execute_boss_scan",
                          side_effect=RuntimeError("kaputt")), \
                patch.object(boss_detection, "log_event") as log, \
                patch.object(boss_detection.logger, "exception") as exception:
            boss_detection._boss_async_thread(state, step, 1, 1, "LOOP")

        exception.assert_called_once()
        self.assertEqual(log.call_args.args[1], "boss_async_error")


if __name__ == "__main__":
    unittest.main()
