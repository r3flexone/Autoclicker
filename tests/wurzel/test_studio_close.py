"""Tests für die Sicherung des Studios beim Schliessen."""

from types import SimpleNamespace
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

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

    def _bruecke(self):
        seq = Sequence("test", init_steps=[SequenceStep(point_id=7)],
                       points=[ClickPoint(10, 20, "Ziel", 7)])
        path = Path("sequences/test/sequence.json")
        self.assertTrue(save_sequence_file(seq, path))
        return StudioBridge(seq, path, "sequences")

    def test_rettung_ist_am_gemeldeten_pfad_vollstaendig_ladbar(self):
        bridge = self._bruecke()
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
        bridge = self._bruecke()
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
        bridge = self._bruecke()
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


if __name__ == "__main__":
    unittest.main()
