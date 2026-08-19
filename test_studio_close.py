"""Tests für die Sicherung des Studios beim Schliessen."""

from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from test_support import install_platform_stubs

install_platform_stubs()

from autoclicker.sequence_studio import _scans_beim_schliessen_speichern


class StudioCloseTest(unittest.TestCase):
    def test_dirty_item_scans_are_saved(self):
        bridge = SimpleNamespace(
            _scan_dirty=True,
            scan_speichern=Mock(return_value={
                "status": {"art": "ok", "text": "gespeichert"},
            }),
        )

        self.assertTrue(_scans_beim_schliessen_speichern(bridge))

        bridge.scan_speichern.assert_called_once_with()

    def test_clean_item_scans_are_not_saved_again(self):
        bridge = SimpleNamespace(
            _scan_dirty=False,
            scan_speichern=Mock(),
        )

        self.assertFalse(_scans_beim_schliessen_speichern(bridge))

        bridge.scan_speichern.assert_not_called()

    def test_save_error_is_reported_as_failure(self):
        bridge = SimpleNamespace(
            _scan_dirty=True,
            scan_speichern=Mock(return_value={
                "status": {"art": "err", "text": "Datenträger voll"},
            }),
        )

        self.assertFalse(_scans_beim_schliessen_speichern(bridge))


if __name__ == "__main__":
    unittest.main()
