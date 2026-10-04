"""Tests für den optionalen automatischen Studio-Start."""

import contextlib
import io
from types import SimpleNamespace
import unittest
from unittest.mock import patch, MagicMock

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
                          return_value=True) as open_mock:
            self.assertTrue(main_module._studio_opens_on_start(state))

        open_mock.assert_called_once_with(state, quit_with_window=True)

    def test_studio_start_can_be_disabled(self):
        state = SimpleNamespace(
            config=AppConfig(studio_open_on_start=False))

        with patch.object(main_module, "handle_sequence_studio") as open_mock:
            self.assertFalse(main_module._studio_opens_on_start(state))

        open_mock.assert_not_called()

    def test_start_option_selects_exactly_one_start_surface(self):
        studio = SimpleNamespace(config=AppConfig(studio_open_on_start=True))
        tui = SimpleNamespace(config=AppConfig(studio_open_on_start=False))

        self.assertFalse(main_module._tui_is_start_surface(studio))
        self.assertTrue(main_module._tui_is_start_surface(tui))

    def test_failed_studio_start_is_reported_to_the_caller(self):
        state = SimpleNamespace(config=AppConfig(studio_open_on_start=True))

        with patch.object(main_module, "handle_sequence_studio",
                          return_value=False):
            self.assertFalse(main_module._studio_opens_on_start(state))

    def test_normal_start_does_not_override_last_opened_sequence(self):
        state = SimpleNamespace(
            active_sequence=Sequence(name="AktivImHauptprozess"))

        with patch("subprocess.Popen") as start_now:
            self.assertTrue(handlers.handle_sequence_studio(
                state, quit_with_window=True))

        args = start_now.call_args.args[0]
        self.assertNotIn("AktivImHauptprozess", args)
        self.assertIn("--beenden-mit-fenster", args)


class MainStartTest(unittest.TestCase):
    """`main()` von aussen: welche Oberfläche erscheint, was die Schleife tut.

    Alles, was das System anfasst, ist ersetzt; `poll_hotkey` liefert eine
    feste Folge von Tastendrücken und endet mit CTRL+ALT+Q.
    """

    def run_main(self, hotkeys=(), *, studio=True, studio_opens=True, first=False,
                 migrate=True, hotkeys_ok=True, llm=None, ocr=None):
        """Führt `main()` aus und gibt `(Rückgabe, Aufrufliste, Ausgabe)` zurück."""
        calls = []
        keys = list(hotkeys) + [main_module.HOTKEY_QUIT]

        def recorded(name, result=None):
            def fn(*args, **kwargs):
                calls.append((name, args))
                return result
            return fn

        def poll():
            key = keys.pop(0)
            if isinstance(key, BaseException):
                raise key
            return key

        names = {
            "print_banner": None, "print_help": None, "_tui_show_ready": None,
            "ensure_sequences_dir": None, "init_directories": None,
            "sweep_on_start": None, "check_on_start": None, "discard_command": None,
            "handle_quit": None, "unregister_hotkeys": None,
            "flush_hotkey_messages": None, "_check_commands": None,
            "handle_pause": None, "init_logging": None,
        }
        with contextlib.ExitStack() as stack:
            for name, result in names.items():
                stack.enter_context(patch.object(main_module, name, recorded(name, result)))
            stack.enter_context(patch.object(main_module, "_platform_ready", return_value=True))
            stack.enter_context(patch.object(main_module, "get_current_thread_id", return_value=77))
            stack.enter_context(patch.object(main_module, "_first_start", return_value=first))
            stack.enter_context(patch.object(main_module, "register_hotkeys", return_value=hotkeys_ok))
            stack.enter_context(patch.object(main_module, "poll_hotkey", poll))
            stack.enter_context(patch.object(main_module, "_studio_opens_on_start",
                                             recorded("studio", studio_opens)))
            stack.enter_context(patch.object(main_module.time, "sleep"))
            config = main_module.CONFIG
            for field, value in (("studio_open_on_start", studio), ("migrate_on_start", migrate),
                                 ("llm_enabled", llm is not None), ("ocr_enabled", ocr is not None),
                                 ("llm_provider", "lmstudio")):
                stack.enter_context(patch.object(config, field, value))
            if llm is not None:
                stack.enter_context(patch("autoclicker.llm_vision.test_connection", llm))
            if ocr is not None:
                stack.enter_context(patch("autoclicker.ocr.is_available", return_value=ocr))
                stack.enter_context(patch("autoclicker.ocr.get_status", return_value="EasyOCR bereit"))
            output = io.StringIO()
            # stderr: der Logger meldet einen Handler-Fehler samt Stack dorthin.
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
                result = main_module.main()
        return result, calls, output.getvalue()

    @staticmethod
    def names(calls):
        return [name for name, _args in calls]

    def test_studio_start_zeigt_keine_konsolenoberflaeche(self):
        result, calls, _out = self.run_main(studio=True, studio_opens=True, first=True)
        self.assertEqual(0, result)
        for hidden in ("print_banner", "print_help", "_tui_show_ready"):
            self.assertNotIn(hidden, self.names(calls))

    def test_briefkasten_wird_vor_dem_studio_geleert(self):
        _result, calls, _out = self.run_main()
        order = self.names(calls)
        self.assertLess(order.index("discard_command"), order.index("studio"))

    def test_konsolenstart_beim_ersten_mal_mit_anleitung(self):
        _result, calls, _out = self.run_main(studio=False, first=True)
        order = self.names(calls)
        self.assertEqual(["print_banner", "print_help", "_tui_show_ready"],
                         [n for n in order if n in ("print_banner", "print_help", "_tui_show_ready")])
        self.assertNotIn("studio", order[:order.index("_tui_show_ready")])

    def test_konsolenstart_danach_ohne_anleitung(self):
        _result, calls, _out = self.run_main(studio=False, first=False)
        self.assertNotIn("print_help", self.names(calls))
        self.assertIn("_tui_show_ready", self.names(calls))

    def test_gescheitertes_studio_faellt_sichtbar_auf_die_konsole(self):
        _result, calls, out = self.run_main(studio=True, studio_opens=False, first=True)
        self.assertIn("Studio konnte nicht geöffnet werden", out)
        order = self.names(calls)
        self.assertEqual(["print_banner", "print_help", "_tui_show_ready"],
                         [n for n in order if n in ("print_banner", "print_help", "_tui_show_ready")])
        self.assertLess(order.index("studio"), order.index("print_banner"))

    def test_start_durchgang_nur_wenn_eingeschaltet(self):
        _r, calls, _o = self.run_main(migrate=True)
        self.assertIn("sweep_on_start", self.names(calls))
        _r, calls, _o = self.run_main(migrate=False)
        self.assertNotIn("sweep_on_start", self.names(calls))

    def test_fehlende_hotkeys_werden_gemeldet(self):
        _r, _c, out = self.run_main(hotkeys_ok=False)
        self.assertIn("Nicht alle Hotkeys", out)
        _r, _c, out = self.run_main(hotkeys_ok=True)
        self.assertNotIn("Nicht alle Hotkeys", out)

    def test_schleife_verteilt_hotkeys_und_fragt_im_leerlauf_den_briefkasten(self):
        unknown = 987654
        result, calls, _out = self.run_main(
            [None, main_module.HOTKEY_PAUSE, unknown, None])
        self.assertEqual(0, result)
        order = self.names(calls)
        loop = order[order.index("studio") + 1:]
        self.assertEqual(["_check_commands", "handle_pause", "flush_hotkey_messages",
                          "_check_commands", "handle_quit", "unregister_hotkeys"], loop)
        quit_args = dict(calls)["handle_quit"]
        self.assertEqual(77, quit_args[1])

    def test_ein_fehler_im_handler_beendet_die_schleife_nicht(self):
        broken = MagicMock(side_effect=RuntimeError("kaputt"))
        with patch.object(main_module, "handle_switch", broken):
            result, calls, out = self.run_main([main_module.HOTKEY_SWITCH, None])
        self.assertEqual(0, result)
        self.assertIn("kaputt", out)
        self.assertIn("handle_quit", self.names(calls))

    def test_strg_c_beendet_geordnet(self):
        captured = {}
        real_state = main_module.AutoClickerState

        def remember():
            captured["state"] = real_state()
            return captured["state"]

        with patch.object(main_module, "AutoClickerState", remember):
            result, calls, out = self.run_main([KeyboardInterrupt()])
        self.assertEqual(0, result)
        self.assertIn("Programm wird beendet", out)
        self.assertTrue(captured["state"].stop_event.is_set())
        self.assertTrue(captured["state"].quit_event.is_set())
        self.assertIn("unregister_hotkeys", self.names(calls))
        self.assertNotIn("handle_quit", self.names(calls))

    def test_llm_verbindung_wird_beim_start_gemeldet(self):
        _r, _c, out = self.run_main(llm=lambda provider: (True, "Verbunden! 'm' ist geladen."))
        self.assertIn("[LLM] lmstudio verbunden: Verbunden! 'm' ist geladen.", out)
        _r, _c, out = self.run_main(llm=lambda provider: (False, "Nicht erreichbar: x"))
        self.assertIn("[LLM] LM Studio nicht erreichbar! Nicht erreichbar: x", out)
        self.assertIn("Bitte LM Studio starten", out)

        def broken(provider):
            raise RuntimeError("weg")
        result, _c, out = self.run_main(llm=broken)
        self.assertEqual(0, result)
        self.assertNotIn("[LLM]", out)

    def test_ocr_status_wird_beim_start_gemeldet(self):
        _r, _c, out = self.run_main(ocr=True)
        self.assertIn("[OCR] EasyOCR bereit", out)
        _r, _c, out = self.run_main(ocr=False)
        self.assertIn("[OCR] EasyOCR bereit", out)
        _r, _c, out = self.run_main()
        self.assertNotIn("[OCR]", out)


if __name__ == "__main__":
    unittest.main()
