"""Der Item-Scan der Laufzeit, Stufe für Stufe.

Geschrieben, BEVOR `execute_item_scan()` in Stufen zerlegt wurde: die Funktion
hatte 175 Zeilen und eine Komplexität von 37, und abgedeckt war nur ein Teil
dessen, was sie entscheidet (Fensteraufnahme mit Session, bester Treffer,
geparkte Items, Block-Skip). Was hier steht, hält das übrige Verhalten fest —
Reihenfolge, Abbruch, die drei Fehlerfälle des Fenster-Modus, der Live-Bericht —,
damit der Umbau gegen etwas laufen kann und nicht nur gegen die Hoffnung.
"""

import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from test_support import install_platform_stubs

install_platform_stubs()

from autoclicker.models import (
    AutoClickerState, ItemProfile, ItemScanConfig, ItemSlot, SCAN_MODE_EVERY,
)
from autoclicker.runtime import item_scan


def _slots(count: int) -> list:
    return [ItemSlot(f"S{i}", (i * 10, 0, i * 10 + 8, 8), (100 + i, 0))
            for i in range(count)]


def _item(name: str = "Kohle") -> ItemProfile:
    return ItemProfile(name=name, marker_colors=[(1, 2, 3)])


def _no_match(profile, img, *args, return_score=False, **kwargs):
    return (False, 0.0) if return_score else False


class _Report:
    def __init__(self) -> None:
        self.seen = []
        self.frame = None


class ItemScanRunTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state = AutoClickerState()
        self.state.config.scan_slot_delay = 0
        self.scanned = []          # Regionen, in der Reihenfolge der Aufnahmen
        self.output = ""

    def _shot(self, region):
        self.scanned.append(tuple(region))
        return Mock(size=(region[2] - region[0], region[3] - region[1]), region=tuple(region))

    def _scan(self, config, matcher=_no_match, shot=None, **kwargs):
        self.state.item_scans[config.name] = config
        buffer = io.StringIO()
        with patch.object(item_scan, "take_screenshot", side_effect=shot or self._shot), \
                patch.object(item_scan, "_park_mouse_for_scan"), \
                patch.object(item_scan, "_check_profile_match", side_effect=matcher), \
                redirect_stdout(buffer):
            result = item_scan.execute_item_scan(
                self.state, config.name, kwargs.pop("mode", SCAN_MODE_EVERY), **kwargs)
        self.output = buffer.getvalue()
        return result

    # ------------------------------------------------------------ Reihenfolge

    def test_rueckwaerts_scannt_die_slots_von_hinten(self):
        slots = _slots(3)
        self._scan(ItemScanConfig("inv", slots=slots, items=[_item()], reverse=True))
        self.assertEqual(self.scanned, [s.scan_region for s in reversed(slots)])

    def test_vorwaerts_ist_die_voreinstellung(self):
        slots = _slots(3)
        self._scan(ItemScanConfig("inv", slots=slots, items=[_item()]))
        self.assertEqual(self.scanned, [s.scan_region for s in slots])

    def test_slots_override_gilt_wie_uebergeben_und_ohne_ausgeschaltete(self):
        slots = _slots(3)
        slots[1].enabled = False
        self._scan(ItemScanConfig("inv", slots=_slots(3), items=[_item()], reverse=True),
                   slots_override=[slots[2], slots[1], slots[0]])
        self.assertEqual(self.scanned, [slots[2].scan_region, slots[0].scan_region])

    def test_ausgeschaltete_slots_werden_nicht_gescannt(self):
        slots = _slots(3)
        slots[0].enabled = False
        self._scan(ItemScanConfig("inv", slots=slots, items=[_item()]))
        self.assertEqual(self.scanned, [slots[1].scan_region, slots[2].scan_region])

    # ------------------------------------------------------------ Treffer

    def test_gleichstand_gewinnt_das_fruehere_item(self):
        first, second = _item("Erstes"), _item("Zweites")

        def equal(profile, img, *args, return_score=False, **kwargs):
            return (True, 0.9) if return_score else True

        result = self._scan(ItemScanConfig("inv", slots=_slots(1), items=[first, second]),
                            matcher=equal)
        self.assertEqual([entry[1].name for entry in result], ["Erstes"])

    def test_treffer_liefert_klickstelle_item_und_prioritaet(self):
        slots = _slots(2)
        item = ItemProfile(name="Kohle", marker_colors=[(1, 2, 3)], priority=3)

        def second_slot(profile, img, *args, return_score=False, **kwargs):
            fits = img.region == slots[1].scan_region
            return (fits, 1.0 if fits else 0.0) if return_score else fits

        result = self._scan(ItemScanConfig("inv", slots=slots, items=[item]),
                            matcher=second_slot)
        self.assertEqual(result, [(slots[1].click_pos, item, 3)])

    def test_fehlendes_bild_ueberspringt_nur_diesen_slot(self):
        slots = _slots(3)
        report = _Report()

        def shot(region):
            if tuple(region) == slots[1].scan_region:
                return None
            return self._shot(region)

        self._scan(ItemScanConfig("inv", slots=slots, items=[_item()]), shot=shot,
                   report=report)
        self.assertEqual([entry[0].name for entry in report.seen], ["S0", "S2"])

    def test_auto_lernen_nur_fuer_slots_ohne_treffer(self):
        slots = _slots(2)

        def first_slot(profile, img, *args, return_score=False, **kwargs):
            fits = img.region == slots[0].scan_region
            return (fits, 1.0 if fits else 0.0) if return_score else fits

        config = ItemScanConfig("inv", slots=slots, items=[_item()], learn_unknown=True)
        with patch.object(item_scan, "_learn_unknown_slot_item") as learn:
            self._scan(config, matcher=first_slot)
        learn.assert_called_once()
        self.assertEqual(learn.call_args.args[1].name, "S1")
        self.assertIs(learn.call_args.args[4], config)

    def test_ohne_auto_lernen_wird_nichts_gelernt(self):
        with patch.object(item_scan, "_learn_unknown_slot_item") as learn:
            self._scan(ItemScanConfig("inv", slots=_slots(2), items=[_item()]))
        learn.assert_not_called()

    # ------------------------------------------------------------ Abbruch

    def test_unbekannter_scan_scannt_nichts(self):
        self.assertEqual(self._scan_name_only("fehlt"), [])
        self.assertEqual(self.scanned, [])
        self.assertIn("nicht gefunden", self.output)

    def _scan_name_only(self, name):
        buffer = io.StringIO()
        with patch.object(item_scan, "take_screenshot", side_effect=self._shot), \
                redirect_stdout(buffer):
            result = item_scan.execute_item_scan(self.state, name, SCAN_MODE_EVERY)
        self.output = buffer.getvalue()
        return result

    def test_stopp_scannt_nichts_mehr(self):
        self.state.stop_event.set()
        self._scan(ItemScanConfig("inv", slots=_slots(2), items=[_item()]))
        self.assertEqual(self.scanned, [])
        self.assertTrue(self.state.stop_event.is_set())

    def test_ein_skip_endet_den_scan_und_wird_verbraucht(self):
        self.state.skip_event.set()
        self._scan(ItemScanConfig("inv", slots=_slots(2), items=[_item()]))
        self.assertEqual(self.scanned, [])
        self.assertFalse(self.state.skip_event.is_set(),
                         "sonst überspringt ein Skip zwei Dinge")

    def test_der_block_skip_bleibt_fuer_den_dispatcher_stehen(self):
        self.state.skip_step_event.set()
        self._scan(ItemScanConfig("inv", slots=_slots(2), items=[_item()]))
        self.assertEqual(self.scanned, [])
        self.assertTrue(self.state.skip_step_event.is_set())

    def test_ein_stopp_in_der_pause_endet_den_scan(self):
        with patch.object(item_scan, "wait_while_paused", return_value=False):
            self._scan(ItemScanConfig("inv", slots=_slots(2), items=[_item()]))
        self.assertEqual(self.scanned, [])

    def test_die_slot_pause_liegt_nur_zwischen_den_slots(self):
        self.state.config.scan_slot_delay = 0.5
        self.state.stop_event = Mock()
        self.state.stop_event.is_set.return_value = False
        self.state.stop_event.wait.return_value = False
        with patch.object(item_scan, "wait_while_paused", return_value=True):
            self._scan(ItemScanConfig("inv", slots=_slots(3), items=[_item()]))
        self.assertEqual(self.state.stop_event.wait.call_count, 2)
        self.assertEqual(len(self.scanned), 3)

    def test_ein_stopp_in_der_slot_pause_endet_den_scan(self):
        self.state.config.scan_slot_delay = 0.5
        self.state.stop_event = Mock()
        self.state.stop_event.is_set.return_value = False
        self.state.stop_event.wait.return_value = True
        with patch.object(item_scan, "wait_while_paused", return_value=True):
            self._scan(ItemScanConfig("inv", slots=_slots(3), items=[_item()]))
        self.assertEqual(len(self.scanned), 1)

    # ------------------------------------------------------------ Fenster-Modus

    def _window_config(self, reference=(100, 100, 400, 400)):
        return ItemScanConfig("inv", slots=_slots(2), items=[_item()],
                              capture_window_title="Spiel",
                              capture_window_rect=reference)

    def test_fenster_fehlt_scannt_nichts_und_sagt_es(self):
        with patch.object(item_scan, "resolve_window", return_value=None):
            result = self._scan(self._window_config())
        self.assertEqual(result, [])
        self.assertIn("nicht gefunden", self.output)

    def test_fenster_nicht_aufnehmbar_scannt_nichts_und_sagt_es(self):
        with patch.object(item_scan, "resolve_window", return_value=("Spiel", (0, 0, 9, 9), 7)), \
                patch.object(item_scan, "take_consistent_window_screenshot", return_value=None):
            result = self._scan(self._window_config())
        self.assertEqual(result, [])
        self.assertIn("nicht aufgenommen", self.output)

    def test_kaputte_fenstergeometrie_scannt_nichts_und_sagt_es(self):
        rect = (200, 100, 500, 400)
        with patch.object(item_scan, "resolve_window", return_value=("Spiel", rect, 7)), \
                patch.object(item_scan, "take_consistent_window_screenshot",
                             return_value=(Mock(size=(300, 300)), rect, "")):
            result = self._scan(self._window_config(reference=(5, 5, 5, 5)))
        self.assertEqual(result, [])
        self.assertIn("Fenstergeometrie", self.output)

    def test_fenster_modus_rechnet_slots_auf_die_heutige_lage_um(self):
        moved = (200, 100, 500, 400)        # 100 px nach rechts gewandert
        crops = []

        def crop(_image, region, origin):
            crops.append((tuple(region), tuple(origin)))
            return Mock(size=(8, 8), region=tuple(region))

        def any_slot(profile, img, *args, return_score=False, **kwargs):
            return (True, 1.0) if return_score else True

        with patch.object(item_scan, "resolve_window", return_value=("Spiel", moved, 7)), \
                patch.object(item_scan, "take_consistent_window_screenshot",
                             return_value=(Mock(size=(300, 300)), moved, "")), \
                patch.object(item_scan, "crop_screen_region", side_effect=crop):
            result = self._scan(self._window_config(), matcher=any_slot)
        self.assertEqual(crops, [((100, 0, 108, 8), (200, 100)),
                                 ((110, 0, 118, 8), (200, 100))])
        self.assertEqual([entry[0] for entry in result], [(200, 0), (201, 0)])
        self.assertEqual(self.scanned, [], "im Fenster-Modus kein Desktop-Ausschnitt je Slot")

    def test_fenster_hinweis_steht_einmal_je_scan_und_hinweis(self):
        rect = (100, 100, 400, 400)
        item_scan._window_capture_warnings.discard(("inv", " Hinweis"))
        with patch.object(item_scan, "resolve_window", return_value=("Spiel", rect, 7)), \
                patch.object(item_scan, "take_consistent_window_screenshot",
                             return_value=(Mock(size=(300, 300)), rect, " Hinweis")), \
                patch.object(item_scan, "crop_screen_region", return_value=Mock(size=(8, 8))):
            self._scan(self._window_config())
            first = self.output
            self._scan(self._window_config())
        self.assertIn("Hinweis", first)
        self.assertNotIn("Hinweis", self.output)

    # ------------------------------------------------------------ Live-Bericht

    def test_bericht_sieht_jeden_slot_auch_ohne_treffer(self):
        slots = _slots(2)
        item = _item()

        def first_slot(profile, img, *args, return_score=False, **kwargs):
            fits = img.region == slots[0].scan_region
            return (fits, 1.0 if fits else 0.0) if return_score else fits

        report = _Report()
        self._scan(ItemScanConfig("inv", slots=slots, items=[item]), matcher=first_slot,
                   report=report)
        self.assertEqual([(entry[0].name, entry[1]) for entry in report.seen],
                         [("S0", item), ("S1", None)])

    def test_bericht_nimmt_den_bereich_einmal_und_vor_dem_ersten_slot_auf(self):
        slots = _slots(2)
        report = _Report()
        config = ItemScanConfig("inv", slots=slots, items=[_item()])
        self._scan(config, report=report)
        margin = item_scan.FRAME_MARGIN
        frame_region = (0 - margin, 0 - margin, 18 + margin, 8 + margin)
        self.assertEqual(report.frame[1], frame_region)
        self.assertEqual(self.scanned[0], frame_region, "zuerst der Bereich, dann die Slots")

        self.scanned.clear()
        self._scan(config, report=report)
        self.assertNotIn(frame_region, self.scanned, "einmal je Block, nicht je Aufruf")

    def test_debug_nennt_den_besten_von_mehreren_treffern_auch_ohne_bericht(self):
        self.state.config.debug_log = True

        def both(profile, img, *args, return_score=False, **kwargs):
            value = 0.9 if profile.name == "B" else 0.8
            return (True, value) if return_score else True

        self._scan(ItemScanConfig("inv", slots=_slots(1), items=[_item("A"), _item("B")]),
                   matcher=both)
        self.assertIn("bester von 2 Treffern", self.output)


if __name__ == "__main__":
    unittest.main()
