"""Vertragstests für die Windows-/Linux-Plattformgrenze.

Die CI hat keinen X-Server. Sie prüft daher Auswahl, Delegation und Fehlerfälle;
echte globale Eingabe steht im manuellen LINUX_TESTPLAN.md.
"""

import contextlib
import io
import os
import sys
import unittest
from unittest.mock import patch

from PIL import Image

from autoclicker.platforms import load_backend
from autoclicker.platforms.base import BACKEND_FUNCTIONS
from autoclicker.platforms import linux_x11


class LinuxBackendTests(unittest.TestCase):
    def tearDown(self):
        linux_x11._hotkey_listener = None
        linux_x11.flush_hotkey_messages()

    def test_linux_backend_erfuellt_vertrag(self):
        fehlend = [name for name in BACKEND_FUNCTIONS
                   if not callable(getattr(linux_x11, name, None))]
        self.assertEqual([], fehlend)

    def test_selector_waehlt_linux_backend(self):
        with patch("autoclicker.platforms.sys.platform", "linux"):
            self.assertIs(load_backend(), linux_x11)

    def test_facade_exportiert_backend_und_gemeinsame_konstanten(self):
        if not sys.platform.startswith("linux"):
            self.skipTest("Fassade verwendet auf diesem Runner das Windows-Backend")
        from autoclicker import winapi
        self.assertIs(winapi.capture_screen, linux_x11.capture_screen)
        self.assertEqual("Autoclicker.SequenzStudio", winapi.APP_ID)

    def test_wayland_wird_nicht_als_x11_ausgegeben(self):
        umgebung = {
            "XDG_SESSION_TYPE": "wayland",
            "WAYLAND_DISPLAY": "wayland-0",
            "DISPLAY": ":0",
        }
        with patch.dict(os.environ, umgebung, clear=True):
            self.assertFalse(linux_x11._x11_ready())
            self.assertTrue(any("Wayland" in text
                                for text in linux_x11.environment_warnings()))

    def test_start_bricht_bei_nicht_nutzbarer_plattform_ab(self):
        import main as app
        ausgabe = io.StringIO()
        with patch.object(app, "environment_warnings",
                          return_value=["Wayland erkannt"]), \
                contextlib.redirect_stdout(ausgabe):
            self.assertFalse(app._plattform_bereit())
        self.assertIn("Start abgebrochen", ausgabe.getvalue())

        with patch.object(app, "print_banner"), patch.object(
                app, "_plattform_bereit", return_value=False):
            self.assertEqual(2, app.main())

    def test_headless_start_liefert_klare_warnung(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(linux_x11._x11_ready())
            self.assertTrue(any("DISPLAY" in text
                                for text in linux_x11.environment_warnings()))
            self.assertFalse(linux_x11.register_hotkeys())

    def test_hotkey_listener_stellt_ids_in_die_event_queue(self):
        erfasst = {}

        class Listener:
            def __init__(self, callbacks):
                erfasst.update(callbacks)

            def start(self):
                return None

        class Keyboard:
            GlobalHotKeys = Listener

        with patch.dict(os.environ,
                        {"XDG_SESSION_TYPE": "x11", "DISPLAY": ":99"},
                        clear=True), patch.object(
                            linux_x11, "_pynput", return_value=(Keyboard, object())):
            self.assertTrue(linux_x11.register_hotkeys())
            erfasst["<ctrl>+<alt>+a"]()
            self.assertEqual(1, linux_x11.poll_hotkey())

    def test_fensteraufloesung_bevorzugt_exakten_titel(self):
        fenster = [
            ("Idle Clans - Hilfe", (0, 0, 100, 100), 1),
            ("Idle Clans", (200, 100, 500, 400), 2),
        ]
        with patch.object(linux_x11, "liste_fenster", return_value=fenster):
            self.assertEqual(2, linux_x11.resolve_window("Idle Clans")[2])

    def test_linux_pixelmessung_nutzt_plattformaufnahme(self):
        from autoclicker import imaging
        bild = Image.new("RGB", (1, 1), (12, 34, 56))
        with patch.object(imaging, "_IS_WINDOWS", False), patch.object(
                imaging, "capture_screen", return_value=bild) as aufnahme:
            self.assertEqual((12, 34, 56), imaging.get_pixel_color(7, 9))
        aufnahme.assert_called_once_with((7, 9, 8, 10))


if __name__ == "__main__":
    unittest.main()
