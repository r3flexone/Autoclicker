"""Der Runner darf fehlende Pflichtprüfungen nicht als Erfolg ausgeben."""

from contextlib import redirect_stdout
import io
from pathlib import Path
import unittest
from unittest.mock import patch

from tests import alle_tests, wurzeltests


class TestRunnerTest(unittest.TestCase):
    def test_exitcode_null_ohne_erfolgreichen_vertragsabschluss_reicht_nicht(self):
        for ausgabe in ("", "Start ohne Abschluss", "0 PASS / 0 FAIL",
                        "8 PASS / 1 FAIL", "8 PASS / 0 FAIL\n9 PASS / 1 FAIL"):
            with self.subTest(ausgabe=ausgabe), \
                    patch.object(alle_tests, "_lauf", return_value=(0, ausgabe)):
                self.assertFalse(alle_tests.vertrag().ok)
        with patch.object(alle_tests, "_lauf", return_value=(0, "=== 8 PASS / 0 FAIL ===")):
            self.assertTrue(alle_tests.vertrag().ok)

    def test_nicht_erkannter_mutant_macht_den_gesamtlauf_rot(self):
        with patch.object(alle_tests, "_lauf", side_effect=[(0, "OK"), (1, "LÜCKE")]), \
                redirect_stdout(io.StringIO()) as ausgabe:
            self.assertEqual(alle_tests.main(["runner", "--nur", "wurzel", "--mutationen"]), 1)
        self.assertIn("Gegenproben", ausgabe.getvalue())
        self.assertNotIn("alles grün", ausgabe.getvalue())

    def test_browser_lokal_optional_aber_als_pflicht_rot(self):
        for arguments, exitcode, message in (
                ([], 0, "ÜBERSPRUNGEN"), (["--rauch-pflicht"], 1, "FAIL")):
            with self.subTest(arguments=arguments), \
                    patch("tests.rauch._bruecke.playwright_da", return_value=(False, "Browser fehlt")), \
                    patch.object(alle_tests, "_lauf") as run, \
                    redirect_stdout(io.StringIO()) as ausgabe:
                self.assertEqual(alle_tests.main(["runner", "--nur", "rauch", *arguments]), exitcode)
                self.assertIn(message, ausgabe.getvalue())
                self.assertIn("Browser fehlt", ausgabe.getvalue())
                if exitcode:
                    self.assertNotIn("alles grün", ausgabe.getvalue())
                run.assert_not_called()

    def test_roter_browserlauf_bleibt_rot(self):
        with patch("tests.rauch._bruecke.playwright_da", return_value=(True, "")), \
                patch.object(alle_tests, "_lauf", return_value=(1, "AssertionError")), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(alle_tests.main([
                "runner", "--nur", "rauch", "--rauch-pflicht", "--rauchtest", "items"]), 1)

    def test_vertragsfehler_wird_nicht_durch_gruene_wurzeltests_verdeckt(self):
        for code in (0, 1):
            commands = []

            def run(command):
                commands.append(command)
                if "test_logic.py" in command[-1]:
                    return code, "1 PASS / 0 FAIL " if code == 0 else "0 PASS / 1 FAIL "
                return 0, "OK"

            with self.subTest(code=code), patch.object(alle_tests, "_lauf", side_effect=run), \
                    redirect_stdout(io.StringIO()):
                self.assertEqual(alle_tests.main(["runner", "--nur", "vertrag", "--nur", "wurzel"]), code)
            self.assertEqual(len(commands), 2)
            self.assertIn("--ohne-vertrag", commands[1])

    def test_wurzel_allein_behaelt_den_vertragswrapper(self):
        with patch.object(alle_tests, "_lauf", return_value=(0, "OK")) as run, \
                redirect_stdout(io.StringIO()):
            self.assertEqual(alle_tests.main(["runner", "--nur", "wurzel"]), 0)
        self.assertNotIn("--ohne-vertrag", run.call_args.args[0])

    def test_discovery_entfernt_nur_den_vertragswrapper(self):
        def ids(suite):
            for test in suite:
                if isinstance(test, unittest.TestSuite):
                    yield from ids(test)
                else:
                    yield test.id()

        root_dir = Path(__file__).resolve().parent
        full_value = set(ids(wurzeltests.sammeln(root_dir)))
        einzeln = set(ids(wurzeltests.sammeln(root_dir, ohne_vertrag=True)))
        self.assertEqual(full_value - einzeln, {"test_regression.RegressionSuiteTest.test_logic_regressions"})
        self.assertEqual(einzeln - full_value, set())
        self.assertTrue(einzeln)


if __name__ == "__main__":
    unittest.main()
