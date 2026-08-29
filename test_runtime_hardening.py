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
from autoclicker.runtime import actions, boss_detection, item_scan, steps


class RuntimeHardeningTest(unittest.TestCase):
    def test_block_skip_during_delay_prevents_the_action(self):
        """Ein Live-Block-Skip darf nach der Wartezeit nicht doch noch klicken."""
        state = AutoClickerState()
        step = SequenceStep(x=10, y=20, delay_before=0.5, name="letzter Klick")

        def skip_waehrend_warten(*_args, **_kwargs):
            state.skip_step_event.set()
            return True

        with patch.object(steps, "check_failsafe", return_value=False), \
                patch.object(steps, "print_step_detail"), \
                patch.object(steps, "wait_with_pause_skip",
                             side_effect=skip_waehrend_warten), \
                patch.object(steps, "_execute_click") as klicken:
            self.assertTrue(steps.execute_step(state, step, 1, 1, "Ablauf"))

        klicken.assert_not_called()
        self.assertFalse(state.skip_step_event.is_set())

    @unittest.skipUnless(imaging.PILLOW_AVAILABLE, "Pillow fehlt")
    def test_sparse_color_markers_between_sampled_pixels_are_found(self):
        """Das schnelle 2er-Raster darf seltene Marker nicht verschlucken."""
        from PIL import Image

        bild = Image.new("RGB", (5, 5), (0, 0, 0))
        marker = (105, 130, 80)
        # Beide Treffer liegen ausserhalb von [::2, ::2]. Genau diese Lage trat
        # bei zwei gelernten Markern von Item 7 auf.
        bild.putpixel((1, 1), marker)
        bild.putpixel((3, 3), marker)

        self.assertTrue(imaging.find_color_in_image(
            bild, marker, 0, pixel_step=2, min_pixels=2))
        with patch.object(imaging, "NUMPY_AVAILABLE", False):
            self.assertTrue(imaging.find_color_in_image(
                bild, marker, 0, pixel_step=2, min_pixels=2))

    def test_failed_input_is_not_logged_as_success(self):
        state = AutoClickerState()
        common = (
            patch.object(actions, "_wait_for_target_window", return_value=True),
            patch.object(actions, "_humanize_check_break"),
            patch.object(actions, "_humanize_delay"),
            patch.object(actions, "_humanize_jitter", side_effect=lambda x, y, _s: (x, y)),
        )

        with common[0], common[1], common[2], common[3], \
                patch.object(actions, "send_click", return_value=False), \
                patch.object(actions, "log_event") as log:
            self.assertFalse(actions.safe_click(state, 10, 20, "test"))
            log.assert_not_called()

        with patch.object(actions, "_wait_for_target_window", return_value=True), \
                patch.object(actions, "_humanize_check_break"), \
                patch.object(actions, "_humanize_delay"), \
                patch.object(actions, "send_scroll", return_value=False), \
                patch.object(actions, "log_event") as log:
            self.assertFalse(actions.safe_scroll(state, 1, label="test"))
            log.assert_not_called()

        with patch.object(actions, "_wait_for_target_window", return_value=True), \
                patch.object(actions, "_humanize_check_break"), \
                patch.object(actions, "_humanize_delay"), \
                patch.object(actions, "send_key", return_value=False), \
                patch.object(actions, "log_event") as log:
            self.assertFalse(actions.safe_key(state, "a", "test"))
            log.assert_not_called()

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

    def test_auto_learn_publishes_only_complete_item(self):
        state = AutoClickerState()
        slot = ItemSlot("Slot", (0, 0, 10, 10), (5, 5))

        class LearningImage:
            size = (10, 10)

            def save(self, _path):
                with state.lock:
                    published = list(state.global_items.values())
                    self.assert_complete = bool(
                        published and published[0].template)

        image = LearningImage()
        image.assert_complete = False
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(imaging, "OPENCV_AVAILABLE", True), \
                patch("autoclicker.editors.item_editor.markers._prepare_learning_image",
                      return_value=(image, [], False)), \
                patch("autoclicker.editors.item_editor.markers._find_matching_existing_item",
                      return_value=None), \
                patch("autoclicker.persistence.active_templates_dir",
                      return_value=Path(directory)), \
                patch("autoclicker.persistence.save_global_items"):
            item_scan._learn_unknown_slot_item(state, slot, object(), False)

        self.assertTrue(image.assert_complete)
        self.assertEqual(state.global_items["Auto Slot"].template, "auto_slot.png")

    def test_async_boss_failure_is_always_logged(self):
        state = AutoClickerState()
        step = SequenceStep(boss_scan="Test")
        with patch.object(boss_detection, "execute_boss_scan",
                          side_effect=RuntimeError("kaputt")), \
                patch.object(boss_detection, "check_failsafe", return_value=False), \
                patch.object(boss_detection, "wait_while_paused", return_value=True), \
                patch.object(boss_detection, "log_event") as log, \
                patch.object(boss_detection.logger, "exception") as exception:
            boss_detection._boss_async_thread(state, step, 1, 1, "LOOP")

        exception.assert_called_once()
        self.assertEqual(log.call_args.args[1], "boss_async_error")


if __name__ == "__main__":
    unittest.main()
