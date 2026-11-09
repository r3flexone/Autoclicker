"""Tests für das Studio-Fenster: wo es aufgeht und was es beim Schliessen sichert."""

from types import SimpleNamespace
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch

from test_support import install_platform_stubs

install_platform_stubs()

from autoclicker.sequence_studio import _on_close, _save_scans_on_close
from autoclicker.models import Sequence, SequenceStep, ClickPoint, ItemScanConfig
from autoclicker.persistence.sequences import save_sequence_file, load_sequence_file
from autoclicker.editors.sequence_studio.bridge import StudioBridge


class StudioCloseTest(unittest.TestCase):
    def setUp(self):
        self._cwd = Path.cwd()
        self._temp = tempfile.TemporaryDirectory()
        os.chdir(self._temp.name)

    def tearDown(self):
        os.chdir(self._cwd)
        self._temp.cleanup()

    def _bridge(self):
        seq = Sequence("test", init_steps=[SequenceStep(point_id=7)],
                       points=[ClickPoint(10, 20, "Ziel", 7)])
        path = Path("sequences/test/sequence.json")
        self.assertTrue(save_sequence_file(seq, path))
        return StudioBridge(seq, path, "sequences")

    def test_rettung_ist_am_gemeldeten_pfad_vollstaendig_ladbar(self):
        bridge = self._bridge()
        original = bridge.filepath.read_bytes()
        bridge.points[0].x = 123
        bridge._dirty = True
        path = bridge.rescue_write()
        self.assertIsNotNone(path)
        self.assertTrue(path.is_file())
        seq = load_sequence_file(path)
        self.assertEqual([(p.id, p.x, p.y) for p in seq.points], [(7, 123, 20)])
        self.assertFalse(seq.init_steps[0].unresolved)
        self.assertEqual(seq.init_steps[0].x, 123)
        self.assertEqual(bridge.filepath.read_bytes(), original)

    def test_umbenennen_prueft_fremdaenderung_vor_dem_verschieben(self):
        bridge = self._bridge()
        data = json.loads(bridge.filepath.read_text(encoding="utf-8"))
        data["points"][0]["x"] = 999
        bridge.filepath.write_text(json.dumps(data), encoding="utf-8")
        os.utime(bridge.filepath, (2000000000, 2000000000))
        bridge.board.name = "neu"
        bridge._dirty = True
        answer = bridge.save()
        self.assertTrue(answer["question"])
        self.assertTrue(bridge.filepath.exists())
        self.assertFalse(Path("sequences/neu").exists())
        self.assertEqual(load_sequence_file(bridge.filepath).points[0].x, 999)

    def test_scan_schreibfehler_bleibt_ungespeichert_und_ist_wiederholbar(self):
        bridge = self._bridge()
        bridge._scan_load()
        bridge.scans["Inventar"] = ItemScanConfig(name="Inventar", owner_sequence="test")
        bridge._scan_dirty = True
        with patch("autoclicker.persistence._scan_store.atomic_write",
                   side_effect=OSError("Datenträger voll")):
            answer = bridge.scan_save()
        self.assertEqual(answer["status"]["kind"], "err")
        self.assertTrue(bridge._scan_dirty)
        self.assertFalse(Path("sequences/test/item_scans/inventar.json").exists())
        answer = bridge.scan_save()
        self.assertEqual(answer["status"]["kind"], "ok")
        self.assertFalse(bridge._scan_dirty)
        self.assertTrue(Path("sequences/test/item_scans/inventar.json").exists())

    def test_dirty_item_scans_are_saved(self):
        bridge = SimpleNamespace(
            _scan_dirty=True,
            scan_save=Mock(return_value={
                "status": {"kind": "ok", "text": "saved"},
            }),
        )

        self.assertTrue(_save_scans_on_close(bridge))

        bridge.scan_save.assert_called_once_with()

    def test_clean_item_scans_are_not_saved_again(self):
        bridge = SimpleNamespace(
            _scan_dirty=False,
            scan_save=Mock(),
        )

        self.assertFalse(_save_scans_on_close(bridge))

        bridge.scan_save.assert_not_called()

    def test_save_error_is_reported_as_failure(self):
        bridge = SimpleNamespace(
            _scan_dirty=True,
            scan_save=Mock(return_value={
                "status": {"kind": "err", "text": "Datenträger voll"},
            }),
        )

        self.assertFalse(_save_scans_on_close(bridge))

    def test_only_auto_started_window_closes_the_main_program(self):
        bridge = SimpleNamespace(
            _scan_dirty=False,
            reclick_on_close=Mock(),
            rescue_write=Mock(return_value=None),
        )
        with patch("autoclicker.mailbox.send_command") as send_command:
            _on_close(bridge, False)
            send_command.assert_not_called()
            _on_close(bridge, True)
            _on_close(bridge, True)
            send_command.assert_called_once_with("quit_program")

    def test_neue_sequenz_ueberschreibt_keine_vorhandene(self):
        # „Neu", Namen einer vorhandenen eintippen, Speichern: die Ordner-
        # pruefung stand nur im Zweig mit alter Datei, und die vorhandene
        # sequence.json wurde ueberschrieben (Schritte und Punkte weg).
        existing = self._bridge().filepath
        original = existing.read_bytes()
        bridge = StudioBridge(Sequence("andere"), Path("sequences/andere/sequence.json"),
                              "sequences")
        with patch("sys.stdout"):
            bridge.new({})
            bridge.sequence_set({"field": "name", "value": "test"})
            answer = bridge.save({})
        self.assertEqual(answer["status"]["kind"], "err")
        self.assertEqual(existing.read_bytes(), original)


class StudioStartGeometryTest(unittest.TestCase):
    """Das Fenster geht mittig auf dem Hauptmonitor auf und passt darauf.

    Ohne ausdrückliche Lage ging es bei (312, 312) auf — die Kaskaden-Ecke von
    Windows; pywebviews „mittig“ greift erst, wenn das Fenster schon steht.
    """

    def test_mittig_auf_dem_hauptmonitor(self):
        from autoclicker.sequence_studio import window_geometry
        self.assertEqual(window_geometry((3440, 1440), 1.0),
                         {"x": 920, "y": 220, "width": 1600, "height": 1000})

    def test_skalierter_bildschirm_bleibt_mittig_und_passt(self):
        # 150 %: pywebview multipliziert Lage und Grösse selbst mit dem Faktor.
        # Ohne die Umrechnung stünde das Fenster rechts über den Rand hinaus.
        from autoclicker.sequence_studio import window_geometry
        g = window_geometry((2560, 1440), 1.5)
        left = g["x"] * 1.5
        right = 2560 - (g["x"] + g["width"]) * 1.5
        bottom = 1440 - (g["y"] + g["height"]) * 1.5
        self.assertGreaterEqual(right, 0)
        self.assertGreaterEqual(bottom, 0)
        self.assertLessEqual(abs(left - right), 3)

    def test_kleiner_bildschirm_bekommt_ein_kleineres_fenster(self):
        from autoclicker.sequence_studio import window_geometry
        g = window_geometry((1366, 768), 1.0)
        self.assertLess(g["width"], 1366)
        self.assertLess(g["height"], 768)
        self.assertEqual(g["x"], (1366 - g["width"]) // 2)
        self.assertEqual(g["y"], (768 - g["height"]) // 2)

    def test_ohne_bildschirm_nur_die_groesse(self):
        from autoclicker.sequence_studio import window_geometry
        for screen, scale in ((None, 1.0), ((0, 0), 1.0), ((1920, 1080), 0)):
            self.assertEqual(window_geometry(screen, scale),
                             {"width": 1600, "height": 1000}, (screen, scale))

    def test_start_uebergibt_die_lage_an_pywebview(self):
        import sys
        import types
        from autoclicker import winapi
        from autoclicker.sequence_studio import main

        created = {}

        def create_window(title, **kwargs):
            created.update(kwargs)
            # MagicMock, weil `closing += …` ein `__iadd__` braucht.
            return SimpleNamespace(events=SimpleNamespace(closing=MagicMock()))

        fake = types.ModuleType("webview")
        fake.create_window = create_window
        fake.start = lambda *args, **kwargs: None
        with tempfile.TemporaryDirectory() as folder:
            cwd = os.getcwd()
            os.chdir(folder)
            try:
                save_sequence_file(Sequence("test"), Path("sequences/test/sequence.json"))
                with patch.dict(sys.modules, {"webview": fake}), \
                        patch.object(winapi, "get_screen_size", return_value=(3440, 1440)), \
                        patch.object(winapi, "get_screen_scale", return_value=1.0), \
                        patch.object(winapi, "set_app_id", return_value=True), \
                        patch("sys.stdout"):
                    self.assertEqual(main(["studio", "test"]), 0)
            finally:
                os.chdir(cwd)
        self.assertEqual((created.get("x"), created.get("y")), (920, 220))
        self.assertEqual((created["width"], created["height"]), (1600, 1000))


if __name__ == "__main__":
    unittest.main()
