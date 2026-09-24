"""Regressionstests für Bilderkennung, OCR-Cache und asynchrone Fehler."""

import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from test_support import install_platform_stubs

install_platform_stubs()

from autoclicker import imaging, ocr
from autoclicker.models import (
    AutoClickerState, ItemProfile, ItemScanConfig, ItemSlot, SequenceStep,
    SCAN_MODE_EVERY, Sequence, ClickPoint, BossProfile, BossScanConfig,
    IconScanConfig,
)
from autoclicker.runtime import actions, boss_detection, item_scan, steps, worker


class RuntimeHardeningTest(unittest.TestCase):
    def test_neustart_gibt_einen_alten_llm_aufruf_nicht_wieder_frei(self):
        from autoclicker import handlers
        state = AutoClickerState()
        state.active_sequence = Sequence("Test", init_steps=[SequenceStep(wait_only=True)])
        state.stop_event.set()
        state.llm_thread = Mock()
        state.llm_thread.is_alive.return_value = True
        with patch.object(handlers.threading, "Thread") as thread:
            handlers.handle_toggle(state)
        thread.assert_not_called()
        self.assertFalse(state.is_running)
        self.assertTrue(state.stop_event.is_set())

    def test_auto_lernen_verwendet_den_sequenzordner_fuer_beide_pruefungen(self):
        state = AutoClickerState()
        state.active_sequence = Sequence("farm")
        item = ItemProfile(name="Bogen", template="bogen.png")
        config = ItemScanConfig(name="Beutel", items=[item], owner_sequence="farm")
        image = Mock(size=(10, 10))
        slot = ItemSlot("Slot", (0, 0, 10, 10), (5, 5))
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "sequences/farm/templates"
            with patch.object(imaging, "OPENCV_AVAILABLE", True), \
                    patch("autoclicker.persistence.active_templates_dir", return_value=folder), \
                    patch("autoclicker.editors.item_editor.markers._prepare_learning_image",
                          return_value=(image, [], False)), \
                    patch("autoclicker.editors.item_editor.markers._find_matching_existing_item",
                          return_value="Bogen") as search, \
                    patch("autoclicker.editors.item_editor.markers._item_has_compatible_template",
                          return_value=True) as size:
                item_scan._learn_unknown_slot_item(state, slot, image, False, config)
            search.assert_called_once_with(image, [("Bogen", item)],
                                          state.config.scan_min_confidence, folder)
            size.assert_called_once_with(item, image, folder)
            image.save.assert_not_called()
            self.assertEqual([it.name for it in config.items], ["Bogen"])

    def test_neuer_befehl_bleibt_waehrend_des_lesens_erhalten(self):
        from autoclicker import mailbox
        with tempfile.TemporaryDirectory() as temp, \
                patch.object(mailbox, "COMMAND_PATH", Path(temp) / "briefkasten.json"):
            mailbox.send_command("start")
            read_fn = Path.read_text

            def with_new_command(path, *args, **kwargs):
                text = read_fn(path, *args, **kwargs)
                mailbox.send_command("stop")
                return text

            with patch.object(Path, "read_text", with_new_command):
                self.assertEqual(mailbox.fetch_command()["command"], "start")
            self.assertEqual(mailbox.fetch_command()["command"], "stop")
            self.assertIsNone(mailbox.fetch_command())

    def test_loader_lehnt_falsche_json_strukturen_kontrolliert_ab(self):
        import json
        from autoclicker.persistence import load_sequence_file
        for data in ([1], {"name": "Defekt", "loop_phases": [None]},
                      {"name": "Defekt", "init_steps": [None]},
                      {"name": "Defekt", "loop_phases": {}},
                      {"name": "Defekt", "end_steps": "kein Array"}):
            with self.subTest(data=data), tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "sequence.json"
                path.write_text(json.dumps(data), encoding="utf-8")
                self.assertIsNone(load_sequence_file(path))

    def test_stopp_im_mikrodelay_verhindert_jede_eingabe(self):
        for kind, arguments in (("click", (10, 20)), ("key", ("a",))):
            with self.subTest(kind=kind):
                state = AutoClickerState()
                with patch.object(actions, "_humanize_delay",
                                  side_effect=lambda s: s.stop_event.set()), \
                        patch.object(actions, "_humanize_check_break"), \
                        patch.object(actions, "_wait_for_target_window", return_value=True), \
                        patch.object(actions, "send_" + kind, return_value=True) as send_fn:
                    self.assertFalse(getattr(actions, "safe_" + kind)(state, *arguments))
                send_fn.assert_not_called()

    def test_pause_sperrt_auch_einen_klick_ohne_wartezeit(self):
        state = AutoClickerState()
        state.pause_event.set()
        arrived = threading.Event()
        original = actions.wait_while_paused

        def waiting(s, text):
            arrived.set()
            return original(s, text)

        with patch.object(steps, "check_failsafe", return_value=False), \
                patch.object(steps, "print_step_detail"), \
                patch.object(steps.status, "write_status"), \
                patch.object(actions, "wait_while_paused", side_effect=waiting), \
                patch.object(actions, "send_click", return_value=True) as send_fn:
            t = threading.Thread(target=steps.execute_step, args=(
                state, SequenceStep(point_id=1, delay_before=0), 1, 1, "INIT"))
            t.start()
            try:
                self.assertTrue(arrived.wait(1), "Keine Pausenprüfung vor der Eingabe")
                send_fn.assert_not_called()
            finally:
                state.pause_event.clear()
                t.join(2)
            self.assertFalse(t.is_alive())
            send_fn.assert_called_once()

    def test_fokus_wird_nach_humanize_pause_erneut_geprueft(self):
        state = AutoClickerState()
        state.config.window_focus_check = True
        state.config.window_focus_title = "Spiel"
        state.config.window_focus_action = "stop"
        focus = {"active": True}
        with patch.object(actions, "is_target_window_active",
                          side_effect=lambda _title: focus["active"]), \
                patch.object(actions, "get_foreground_window_title", return_value="Editor"), \
                patch.object(actions, "_humanize_check_break",
                             side_effect=lambda _s: focus.update(active=False)), \
                patch.object(actions, "send_click", return_value=True) as send_fn:
            self.assertFalse(actions.safe_click(state, 10, 20))
        send_fn.assert_not_called()

    def test_boss_und_icon_klicken_nur_einen_existierenden_punkt(self):
        from autoclicker.persistence import resolve_click_references
        for kind in ("boss", "icon"):
            with self.subTest(kind=kind):
                state = AutoClickerState()
                state.active_sequence = Sequence("Test")
                boss = BossProfile(name="Boss", action="click", action_point_id=7)
                icon = IconScanConfig(name="Icon", action="click", action_point_id=7)
                state.boss_scans["B"] = BossScanConfig(name="B", bosses=[boss])
                state.icon_scans["I"] = icon

                def execute():
                    if kind == "boss":
                        return boss_detection._execute_boss_action(
                            state, boss, SequenceStep(boss_scan="B"), 1, 1, "INIT", False)
                    return steps._execute_icon_scan_step(
                        state, SequenceStep(icon_scan="I"), 1, 1, "INIT")

                with patch.object(steps, "execute_icon_scan", return_value=True), \
                        patch.object(boss_detection, "safe_click", return_value=True) as click_fn:
                    resolve_click_references(state)
                    execute()
                    click_fn.assert_not_called()
                    # Auch (0, 0) kann ein gültiger Punkt sein: die ID entscheidet.
                    state.active_sequence.points = [ClickPoint(0, 0, "Ziel", 7)]
                    resolve_click_references(state)
                    execute()
                    self.assertEqual(click_fn.call_args.args[1:3], (0, 0))
                    self.assertEqual(click_fn.call_count, 1)

    def test_worker_fehler_raeumt_lauf_und_log_auf(self):
        state = AutoClickerState()
        state.is_running = True
        protokoll = Mock()
        seq = Sequence("Test", init_steps=[SequenceStep(wait_only=True)])
        with patch.object(worker, "_prepare_worker_state", return_value=seq), \
                patch("autoclicker.session_log.start_session_log", return_value=protokoll), \
                patch.object(worker, "_run_main_loop", side_effect=RuntimeError("Schritt kaputt")), \
                patch.object(worker, "set_console_title"), \
                patch.object(worker.status, "write_status"), \
                patch.object(worker.status, "finish_run") as end:
            try:
                worker.sequence_worker(state)
            except RuntimeError:
                pass
        self.assertFalse(state.is_running)
        self.assertTrue(state.stop_event.is_set())
        self.assertIsNone(state.session_log)
        protokoll.close.assert_called_once()
        self.assertIn("Fehler", end.call_args.args[1])

    def test_zyklen_vor_einem_neustart_zaehlen_in_der_zusammenfassung_mit(self):
        """Neustart faengt bei Zyklus 1 an — die Statistik vergisst die davor nicht.

        `_run_main_loop` setzte `cycle_count` bei jedem Anlauf auf 0 und gab am
        Ende nur den letzten Stand zurueck: nach einem Neustart im zweiten
        Zyklus stand in der Zusammenfassung „Zyklen: 2", gelaufen waren vier.
        Die Grenze `total_cycles` gilt weiter je Anlauf (das ist der Neustart).
        """
        from autoclicker.models import LoopPhase
        state = AutoClickerState()
        seq = Sequence("Test", loop_phases=[LoopPhase(name="A", steps=[
            SequenceStep(wait_only=True, delay_before=0)])], total_cycles=2)
        calls = []

        def step_fn(st, step, num, total, phase):
            calls.append(phase)
            if len(calls) == 2:          # im zweiten Zyklus: Neustart
                st.restart_event.set()
                return False
            return True

        with patch.object(worker, "execute_step", step_fn), \
                patch.object(worker, "set_console_title"), \
                patch.object(worker.status, "write_status"):
            cycles = worker._run_main_loop(state, seq, {}, threading.Lock(), False)

        # Anlauf 1: Zyklus 1 ok, Zyklus 2 -> Neustart. Anlauf 2: Zyklus 1 und 2.
        self.assertEqual(len(calls), 4)
        self.assertEqual(state.restarts, 1)
        self.assertEqual(cycles, 4, "beide Anlaeufe zaehlen")

    def test_block_skip_during_delay_prevents_the_action(self):
        """Ein Live-Block-Skip darf nach der Wartezeit nicht doch noch klicken."""
        state = AutoClickerState()
        step = SequenceStep(x=10, y=20, delay_before=0.5, name="letzter Klick")

        def skip_while_waiting(*_args, **_kwargs):
            state.skip_step_event.set()
            return True

        with patch.object(steps, "check_failsafe", return_value=False), \
                patch.object(steps, "print_step_detail"), \
                patch.object(steps, "wait_with_pause_skip",
                             side_effect=skip_while_waiting), \
                patch.object(steps, "_execute_click") as click_fn:
            self.assertTrue(steps.execute_step(state, step, 1, 1, "Ablauf"))

        click_fn.assert_not_called()
        self.assertFalse(state.skip_step_event.is_set())

    @unittest.skipUnless(imaging.PILLOW_AVAILABLE, "Pillow fehlt")
    def test_sparse_color_markers_between_sampled_pixels_are_found(self):
        """Das schnelle 2er-Raster darf seltene Marker nicht verschlucken."""
        from PIL import Image

        image = Image.new("RGB", (5, 5), (0, 0, 0))
        marker = (105, 130, 80)
        # Beide Treffer liegen ausserhalb von [::2, ::2]. Genau diese Lage trat
        # bei zwei gelernten Markern von Item 7 auf.
        image.putpixel((1, 1), marker)
        image.putpixel((3, 3), marker)

        self.assertTrue(imaging.find_color_in_image(
            image, marker, 0, pixel_step=2, min_pixels=2))
        with patch.object(imaging, "NUMPY_AVAILABLE", False):
            self.assertTrue(imaging.find_color_in_image(
                image, marker, 0, pixel_step=2, min_pixels=2))

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

    def test_immediate_modus_nimmt_das_fenster_nur_nach_einem_klick_neu_auf(self):
        """Ein Durchgang, viele Slots, EINE Aufnahme — bis geklickt wird.

        Der Immediate-Modus ruft `execute_item_scan` je Slot; ohne die Session
        hiess das bei 45 Slots 45 `PrintWindow`-Aufnahmen und 45-mal Maus parken.
        Frisch sein muss das Bild nur NACH einem Klick (das Spiel rueckt auf,
        die Maus steht auf dem Item) — davor sind es dieselben Pixel.
        """
        state = AutoClickerState()
        state.config.scan_click_immediate = True
        state.config.scan_slot_delay = 0
        state.config.scan_park_mouse = True
        rect = (100, 100, 400, 400)
        slots = [ItemSlot(f"S{i}", (110 + i * 10, 110, 118 + i * 10, 118), (5, 5))
                 for i in range(1, 5)]
        item = ItemProfile(name="Kohle", marker_colors=[(1, 2, 3)])
        state.item_scans["inv"] = ItemScanConfig(
            name="inv", slots=slots, items=[item], capture_window_title="Spiel",
            capture_window_rect=rect, owner_sequence="farm")
        captures, parked, clicked = [], [], []

        def capture(_hwnd):
            captures.append(1)
            return Mock(size=(300, 300)), rect, ""

        def crop(_image, region, _origin):
            return {"region": region}

        def match(profile, img, *args, return_score=False, **kwargs):
            # Slot 2 traegt das Item — die anderen sind leer.
            fits = img["region"][0] == slots[1].scan_region[0]
            return (fits, 1.0 if fits else 0.0) if return_score else fits

        step = SequenceStep(x=0, y=0, delay_before=0, name="S", item_scan="inv")
        with patch.object(item_scan, "resolve_window", return_value=("Spiel", rect, 42)), \
                patch.object(item_scan, "take_consistent_window_screenshot", capture), \
                patch.object(item_scan, "crop_screen_region", crop), \
                patch.object(item_scan, "_park_mouse_for_scan",
                             lambda pos: parked.append(pos)), \
                patch.object(item_scan, "_check_profile_match", match), \
                patch.object(steps, "check_failsafe", return_value=False), \
                patch.object(steps, "_click_scan_result",
                             lambda st, pos, it, prio, dbg: clicked.append(it.name) or True):
            self.assertTrue(steps.execute_step(state, step, 1, 1, "T"))

        self.assertEqual(clicked, ["Kohle"])
        # Slot 1 und 2 auf der ersten Aufnahme, nach dem Klick eine zweite fuer 3 und 4.
        self.assertEqual(len(captures), 2, "einmal vor dem Klick, einmal danach")
        self.assertEqual(len(parked), 2, "geparkt wird beim Start und nach dem Klick")

    def test_ohne_session_nimmt_jeder_aufruf_selbst_auf(self):
        """Der normale Pfad (ein Aufruf fuer alle Slots) bleibt, wie er war."""
        state = AutoClickerState()
        state.config.scan_slot_delay = 0
        rect = (100, 100, 400, 400)
        slots = [ItemSlot(f"S{i}", (110, 110, 118, 118), (5, 5)) for i in range(3)]
        state.item_scans["inv"] = ItemScanConfig(
            name="inv", slots=slots, items=[ItemProfile(name="K", marker_colors=[(1, 2, 3)])],
            capture_window_title="Spiel", capture_window_rect=rect, owner_sequence="farm")
        captures = []

        def capture(_hwnd):
            captures.append(1)
            return Mock(size=(300, 300)), rect, ""

        with patch.object(item_scan, "resolve_window", return_value=("Spiel", rect, 42)), \
                patch.object(item_scan, "take_consistent_window_screenshot", capture), \
                patch.object(item_scan, "crop_screen_region", return_value=object()), \
                patch.object(item_scan, "_park_mouse_for_scan"), \
                patch.object(item_scan, "_check_profile_match", return_value=(False, 0.0)):
            item_scan.execute_item_scan(state, "inv", SCAN_MODE_EVERY)
            item_scan.execute_item_scan(state, "inv", SCAN_MODE_EVERY)
        self.assertEqual(len(captures), 2, "je Aufruf eine Aufnahme, drei Slots teilen sie")

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
        config = ItemScanConfig(name="Beutel", owner_sequence="farm")

        class LearningImage:
            size = (10, 10)

            def save(self, _path):
                with state.lock:
                    published = list(config.items)
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
                patch("autoclicker.persistence.save_item_scan"):
            item_scan._learn_unknown_slot_item(state, slot, object(), False, config)

        self.assertTrue(image.assert_complete)
        self.assertEqual(config.items[0].name, "Auto Slot")
        self.assertEqual(config.items[0].template, "auto_slot.png")

    def test_auto_lernen_schreibt_in_den_laufenden_scan_nicht_in_die_arbeitsansicht(self):
        """Zwei Item-Scans in einer Sequenz: gelernt wird in dem, der LAEUFT.

        `state.global_items` ist nur die Konsolen-Ansicht auf `active_item_scan`
        (hier: Scan A). Laeuft Scan B mit `learn_unknown`, landete das Item vorher
        in A — und wurde gegen die Items von A dedupliziert. Dazu gehoert: das
        gelernte Item ist GEPARKT (enabled=False), also wird es im naechsten
        Zyklus nicht geklickt, und gespeichert wird der laufende Scan.
        """
        from autoclicker.persistence.item_scans import bind_item_scan_context
        state = AutoClickerState()
        state.active_sequence = Sequence("farm")
        scan_a = ItemScanConfig(name="A", items=[ItemProfile(name="Bogen", template="b.png")],
                                owner_sequence="farm")
        scan_b = ItemScanConfig(name="B", owner_sequence="farm")
        state.item_scans = {"A": scan_a, "B": scan_b}
        bind_item_scan_context(state, "A")
        slot = ItemSlot("Slot 3", (0, 0, 10, 10), (5, 5))
        image = Mock(size=(10, 10))
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(imaging, "OPENCV_AVAILABLE", True), \
                patch("autoclicker.editors.item_editor.markers._prepare_learning_image",
                      return_value=(image, [(1, 2, 3)], False)), \
                patch("autoclicker.editors.item_editor.markers._find_matching_existing_item",
                      return_value=None) as search, \
                patch("autoclicker.persistence.active_templates_dir",
                      return_value=Path(directory)), \
                patch("autoclicker.persistence.save_item_scan") as save:
            item_scan._learn_unknown_slot_item(state, slot, image, False, scan_b)

        # Dedup gegen die Items des LAUFENDEN Scans (B ist leer), nicht gegen A.
        self.assertEqual(search.call_args[0][1], [])
        self.assertEqual([it.name for it in scan_a.items], ["Bogen"])
        self.assertEqual([it.name for it in scan_b.items], ["Auto Slot 3"])
        self.assertFalse(scan_b.items[0].enabled, "gelernt heisst geparkt, nicht geklickt")
        self.assertEqual(scan_b.items[0].category, "Auto")
        save.assert_called_once_with(scan_b)
        # Die Konsolen-Ansicht zeigt weiter auf A und bleibt unberuehrt.
        self.assertEqual(list(state.global_items), ["Bogen"])

    def test_auto_lernen_haelt_die_arbeitsansicht_desselben_scans_aktuell(self):
        """Zeigt die Konsolen-Ansicht auf den laufenden Scan, sieht sie das Item.

        Sonst schriebe ihr naechstes `done` (flush_item_scan_context ersetzt
        cfg.items durch die Ansicht) die Liste OHNE das gelernte Item zurueck.
        """
        from autoclicker.persistence.item_scans import (
            bind_item_scan_context, flush_item_scan_context)
        state = AutoClickerState()
        state.active_sequence = Sequence("farm")
        scan = ItemScanConfig(name="A", owner_sequence="farm")
        state.item_scans = {"A": scan}
        bind_item_scan_context(state, "A")
        slot = ItemSlot("Slot 1", (0, 0, 10, 10), (5, 5))
        image = Mock(size=(10, 10))
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(imaging, "OPENCV_AVAILABLE", True), \
                patch("autoclicker.editors.item_editor.markers._prepare_learning_image",
                      return_value=(image, [], False)), \
                patch("autoclicker.editors.item_editor.markers._find_matching_existing_item",
                      return_value=None), \
                patch("autoclicker.persistence.active_templates_dir",
                      return_value=Path(directory)), \
                patch("autoclicker.persistence.save_item_scan"):
            item_scan._learn_unknown_slot_item(state, slot, image, False, scan)

        self.assertIn("Auto Slot 1", state.global_items)
        flush_item_scan_context(state)
        self.assertEqual([it.name for it in scan.items], ["Auto Slot 1"])

    def test_geparkte_items_werden_im_scan_nicht_geklickt_aber_dedupliziert(self):
        """Der Scan sieht nur eingeschaltete Items; die Dedup-Liste alle."""
        state = AutoClickerState()
        state.config.scan_slot_delay = 0
        slot = ItemSlot("Slot", (0, 0, 10, 10), (5, 5))
        parked = ItemProfile(name="Auto Slot", template="auto_slot.png", enabled=False)
        config = ItemScanConfig(name="Test", slots=[slot], items=[parked],
                                learn_unknown=True, owner_sequence="farm")
        state.item_scans["Test"] = config
        seen = []
        with patch.object(item_scan, "take_screenshot", return_value=object()), \
                patch.object(item_scan, "_park_mouse_for_scan"), \
                patch.object(item_scan, "_check_profile_match",
                             side_effect=lambda profile, *a, **k: seen.append(profile.name) or (False, 0.0)), \
                patch.object(item_scan, "_learn_unknown_slot_item") as learn:
            result = item_scan.execute_item_scan(state, "Test", SCAN_MODE_EVERY)
        self.assertEqual(result, [])
        self.assertEqual(seen, [], "ein geparktes Item wird nicht verglichen")
        learn.assert_called_once()
        self.assertIs(learn.call_args[0][4], config, "gelernt wird in den laufenden Scan")

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

    def _in_sandbox(self):
        """Temp-Ordner als Arbeitsverzeichnis — Sequenzen und `.run.json` landen dort."""
        cwd = Path.cwd()
        temp = tempfile.TemporaryDirectory()
        os.chdir(temp.name)
        self.addCleanup(temp.cleanup)
        self.addCleanup(os.chdir, cwd)

    def test_konsolen_loader_laedt_die_scans_der_sequenz(self):
        # CTRL+ALT+L (und S/T ohne geladene Sequenz) setzte Sequenz und Punkte
        # von Hand: der Lauf hatte danach GAR keine Scans.
        from autoclicker.editors.sequence_editor import loader
        from autoclicker.persistence import save_item_scan, save_sequence_file, sequence_file
        self._in_sandbox()
        path = sequence_file("A")
        path.parent.mkdir(parents=True)
        save_sequence_file(Sequence("A", init_steps=[SequenceStep(item_scan="inv")]), path)
        state = AutoClickerState()
        with patch("sys.stdout"):
            save_item_scan(ItemScanConfig(name="inv", owner_sequence="A"))
            with patch.object(loader, "interactive_select", return_value=0):
                loader.run_sequence_loader(state)
        self.assertEqual(state.active_sequence.name, "A")
        self.assertEqual(list(state.item_scans), ["inv"])

    def test_block_skip_im_immediate_scan_gilt_dem_ganzen_block(self):
        # `execute_item_scan` verbrauchte den Skip selbst — im Immediate-Modus
        # fiel dadurch nur EIN Slot weg, der Rest wurde weiter geklickt.
        self._in_sandbox()
        state = AutoClickerState()
        state.is_running = True
        state.config.scan_click_immediate = True
        state.config.scan_item_click_delay = 0
        state.item_scans["inv"] = ItemScanConfig("inv", slots=[
            ItemSlot(f"S{i}", (i * 10, 0, i * 10 + 8, 8), (100 + i, 0)) for i in range(4)],
            items=[ItemProfile("Bogen", marker_colors=[(1, 2, 3)])])
        parks, clicks = [], []

        def park(*_args):
            parks.append(1)
            if len(parks) == 2:
                state.skip_step_event.set()      # beim Scan des zweiten Slots

        with patch.object(item_scan, "take_screenshot", return_value=Mock(size=(8, 8))), \
                patch.object(item_scan, "_park_mouse_for_scan", side_effect=park), \
                patch.object(item_scan, "_check_profile_match", return_value=(True, 1.0)), \
                patch.object(actions, "send_click",
                             side_effect=lambda x, y, *a: clicks.append((x, y)) or True), \
                patch.object(steps, "check_failsafe", return_value=False), \
                patch("sys.stdout"):
            result = steps.execute_step(
                state, SequenceStep(item_scan="inv", item_scan_mode=SCAN_MODE_EVERY),
                1, 1, "Loop")
        self.assertTrue(result)
        self.assertEqual(clicks, [(100, 0)])
        self.assertFalse(state.skip_step_event.is_set())


if __name__ == "__main__":
    unittest.main()
