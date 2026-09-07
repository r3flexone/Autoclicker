"""Tests für den optionalen automatischen Studio-Start."""

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_support import install_platform_stubs

install_platform_stubs()

import main as main_module
from autoclicker import handlers
from autoclicker.config import AppConfig
from autoclicker.models import Sequence


class StartupEditorTest(unittest.TestCase):
    def test_studio_opens_by_default(self):
        state = SimpleNamespace(config=AppConfig())

        with patch.object(main_module, "handle_sequence_studio",
                          return_value=True) as oeffnen:
            self.assertTrue(main_module._studio_beim_start_oeffnen(state))

        oeffnen.assert_called_once_with(state, beenden_mit_fenster=True)

    def test_studio_start_can_be_disabled(self):
        state = SimpleNamespace(
            config=AppConfig(studio_open_on_start=False))

        with patch.object(main_module, "handle_sequence_studio") as oeffnen:
            self.assertFalse(main_module._studio_beim_start_oeffnen(state))

        oeffnen.assert_not_called()

    def test_start_option_selects_exactly_one_start_surface(self):
        studio = SimpleNamespace(config=AppConfig(studio_open_on_start=True))
        tui = SimpleNamespace(config=AppConfig(studio_open_on_start=False))

        self.assertFalse(main_module._tui_ist_startoberflaeche(studio))
        self.assertTrue(main_module._tui_ist_startoberflaeche(tui))

    def test_failed_studio_start_is_reported_to_the_caller(self):
        state = SimpleNamespace(config=AppConfig(studio_open_on_start=True))

        with patch.object(main_module, "handle_sequence_studio",
                          return_value=False):
            self.assertFalse(main_module._studio_beim_start_oeffnen(state))

    def test_normal_start_does_not_override_last_opened_sequence(self):
        state = SimpleNamespace(
            active_sequence=Sequence(name="AktivImHauptprozess"))

        with patch("subprocess.Popen") as starten:
            self.assertTrue(handlers.handle_sequence_studio(
                state, beenden_mit_fenster=True))

        args = starten.call_args.args[0]
        self.assertNotIn("AktivImHauptprozess", args)
        self.assertIn("--beenden-mit-fenster", args)


if __name__ == "__main__":
    unittest.main()
