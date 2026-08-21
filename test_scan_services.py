"""Tests für die GUI-unabhängigen Scan-Dienste."""

import unittest

# Pillow ist optional, wie ueberall im Baum. Der Import stand hier oben und ohne
# Pillow starb das Modul beim LADEN - womit `python -m unittest test_*.py` gar
# nicht erst sammelte und es zwei Testkommandos brauchte. Uebersprungen wird
# jetzt, was Bilder braucht; der Rest laeuft.
try:
    from PIL import Image
    PILLOW = True
except ImportError:                                              # pragma: no cover
    Image = None
    PILLOW = False

braucht_pillow = unittest.skipUnless(PILLOW, "Pillow nicht installiert")

from autoclicker.editors.scan_services import (
    _hue_intervals,
    detect_slots_in_image,
)


class HueIntervalsTest(unittest.TestCase):
    def test_regular_interval(self):
        self.assertEqual(_hue_intervals(90, 3), [(87, 93)])

    def test_wraps_below_zero(self):
        self.assertEqual(_hue_intervals(1, 3), [(0, 4), (178, 179)])

    def test_wraps_above_opencv_range(self):
        self.assertEqual(_hue_intervals(179, 3), [(176, 179), (0, 2)])

    def test_tolerance_is_bounded(self):
        self.assertEqual(_hue_intervals(20, 999), [(0, 179)])


@braucht_pillow
class SlotDetectionTest(unittest.TestCase):
    def test_red_hue_wrap_detects_slot(self):
        try:
            import cv2  # noqa: F401
            import numpy  # noqa: F401
        except ImportError:
            self.skipTest("OpenCV/NumPy nicht installiert")

        image = Image.new("RGB", (80, 80), (0, 0, 0))
        image.paste((255, 8, 0), (10, 10, 60, 60))

        slots, _ = detect_slots_in_image(
            image,
            slot_color_rgb=(255, 0, 8),
            hsv_tolerance=3,
            sv_tolerance=20,
        )

        self.assertEqual(slots, [(10, 10, 50, 50)])


if __name__ == "__main__":
    unittest.main()
