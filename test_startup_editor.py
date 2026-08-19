"""Tests für den optionalen automatischen Studio-Start."""

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_support import install_platform_stubs

install_platform_stubs()

import main as main_module
from autoclicker.config import AppConfig


class StartupEditorTest(unittest.TestCase):
    def test_studio_opens_by_default(self):
        state = SimpleNamespace(config=AppConfig())

        with patch.object(main_module, "handle_sequence_studio") as oeffnen:
            self.assertTrue(main_module._studio_beim_start_oeffnen(state))

        oeffnen.assert_called_once_with(state)

    def test_studio_start_can_be_disabled(self):
        state = SimpleNamespace(
            config=AppConfig(studio_open_on_start=False))

        with patch.object(main_module, "handle_sequence_studio") as oeffnen:
            self.assertFalse(main_module._studio_beim_start_oeffnen(state))

        oeffnen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
