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

from autoclicker.sequence_studio import _beim_schliessen, _scans_beim_schliessen_speichern
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
        pfad = Path("sequences/test/sequence.json")
        self.assertTrue(save_sequence_file(seq, pfad))
        return StudioBridge(seq, pfad, "sequences")

    def test_rettung_ist_am_gemeldeten_pfad_vollstaendig_ladbar(self):
        bridge = self._bruecke()
        original = bridge.filepath.read_bytes()
        bridge.points[0].x = 123
        bridge._dirty = True
        pfad = bridge.rettung_schreiben()
        self.assertIsNotNone(pfad)
        self.assertTrue(pfad.is_file())
        seq = load_sequence_file(pfad)
        self.assertEqual([(p.id, p.x, p.y) for p in seq.points], [(7, 123, 20)])
        self.assertFalse(seq.init_steps[0].unresolved)
        self.assertEqual(seq.init_steps[0].x, 123)
        self.assertEqual(bridge.filepath.read_bytes(), original)

    def test_umbenennen_prueft_fremdaenderung_vor_dem_verschieben(self):
        bridge = self._bruecke()
        daten = json.loads(bridge.filepath.read_text(encoding="utf-8"))
        daten["points"][0]["x"] = 999
        bridge.filepath.write_text(json.dumps(daten), encoding="utf-8")
        os.utime(bridge.filepath, (2000000000, 2000000000))
        bridge.board.name = "neu"
        bridge._dirty = True
        antwort = bridge.speichern()
        self.assertTrue(antwort["frage"])
        self.assertTrue(bridge.filepath.exists())
        self.assertFalse(Path("sequences/neu").exists())
        self.assertEqual(load_sequence_file(bridge.filepath).points[0].x, 999)

    def test_scan_schreibfehler_bleibt_ungespeichert_und_ist_wiederholbar(self):
        bridge = self._bruecke()
        bridge._scan_laden()
        bridge.scans["Inventar"] = ItemScanConfig(name="Inventar", owner_sequence="test")
        bridge._scan_dirty = True
        with patch("autoclicker.persistence._scan_store.atomic_write",
                   side_effect=OSError("Datenträger voll")):
            antwort = bridge.scan_speichern()
        self.assertEqual(antwort["status"]["art"], "err")
        self.assertTrue(bridge._scan_dirty)
        self.assertFalse(Path("sequences/test/item_scans/inventar.json").exists())
        antwort = bridge.scan_speichern()
        self.assertEqual(antwort["status"]["art"], "ok")
        self.assertFalse(bridge._scan_dirty)
        self.assertTrue(Path("sequences/test/item_scans/inventar.json").exists())

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

    def test_only_auto_started_window_closes_the_main_program(self):
        bridge = SimpleNamespace(
            _scan_dirty=False,
            nachklick_beim_schliessen=Mock(),
            rettung_schreiben=Mock(return_value=None),
        )
        with patch("autoclicker.befehl.sende") as sende:
            _beim_schliessen(bridge, False)
            sende.assert_not_called()
            _beim_schliessen(bridge, True)
            _beim_schliessen(bridge, True)
            sende.assert_called_once_with("programm_beenden")


if __name__ == "__main__":
    unittest.main()
