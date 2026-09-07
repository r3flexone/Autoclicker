"""Deterministische Übergänge zwischen Fokusverlust, Pause und Eingabe."""

from contextlib import ExitStack
import threading
import unittest
from unittest.mock import patch

from test_support import install_platform_stubs

install_platform_stubs()

from autoclicker.models import AutoClickerState
from autoclicker.runtime import actions


class EingabeSynchronisationTest(unittest.TestCase):
    def test_pause_waehrend_fokusverlust_sperrt_bis_zur_freigabe(self):
        self._fokus_pause(stoppen=False)

    def test_stopp_waehrend_fokuspause_verhindert_die_eingabe(self):
        self._fokus_pause(stoppen=True)

    def _fokus_pause(self, stoppen):
        for art, argumente in (("click", (10, 20)), ("key", ("a",)), ("scroll", (1,))):
            with self.subTest(art=art), ExitStack() as mocks:
                state = AutoClickerState()
                state.config.humanize_enabled = False
                state.config.window_focus_check = True
                state.config.window_focus_title = "Spiel"
                state.config.window_focus_action = "pause"
                verloren = threading.Event()
                wieder_da = threading.Event()
                entschieden = threading.Event()
                ergebnisse, fehler = [], []
                aufrufe = 0
                original_pause = actions.wait_while_paused

                def fokus(_titel):
                    nonlocal aufrufe
                    aufrufe += 1
                    if aufrufe == 1:
                        return True
                    if aufrufe == 2:
                        verloren.set()
                        return False
                    if not wieder_da.wait(3):
                        raise RuntimeError("Test hat Fokus nicht freigegeben")
                    return True

                def pause(s, text):
                    if s.pause_event.is_set():
                        entschieden.set()
                    return original_pause(s, text)

                def gesendet(*_args):
                    entschieden.set()
                    return True

                sender = [mocks.enter_context(patch.object(actions, "send_" + name,
                                                          side_effect=gesendet))
                          for name in ("click", "key", "scroll")]
                mocks.enter_context(patch.object(actions, "is_target_window_active", side_effect=fokus))
                mocks.enter_context(patch.object(actions, "get_foreground_window_title", return_value="Editor"))
                mocks.enter_context(patch.object(actions, "wait_while_paused", side_effect=pause))

                def ausfuehren():
                    try:
                        ergebnisse.append(getattr(actions, "safe_" + art)(state, *argumente))
                    except BaseException as exc:
                        fehler.append(exc)
                        entschieden.set()

                thread = threading.Thread(target=ausfuehren, daemon=True)
                thread.start()
                try:
                    self.assertTrue(verloren.wait(3), "Fokus-Wartephase nicht erreicht")
                    state.pause_event.set()
                    wieder_da.set()
                    self.assertTrue(entschieden.wait(3), "Keine Reaktion auf Fokusrückkehr")
                    self.assertEqual(fehler, [])
                    for senden in sender:
                        senden.assert_not_called()
                    if stoppen:
                        state.stop_event.set()
                    else:
                        state.pause_event.clear()
                    thread.join(3)
                    self.assertFalse(thread.is_alive(), "Eingabe-Thread hängt")
                    self.assertEqual(fehler, [])
                    self.assertEqual(ergebnisse, [not stoppen])
                    self.assertEqual(sum(s.call_count for s in sender), 0 if stoppen else 1)
                finally:
                    state.stop_event.set()
                    state.pause_event.clear()
                    wieder_da.set()
                    thread.join(3)


if __name__ == "__main__":
    unittest.main()
