"""Der Runner darf fehlende Pflichtprüfungen nicht als Erfolg ausgeben."""

from contextlib import redirect_stdout
import io
from pathlib import Path
import unittest
from unittest.mock import patch

from tools import alle_tests, wurzeltests


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
        for argumente, exitcode, meldung in (
                ([], 0, "ÜBERSPRUNGEN"), (["--rauch-pflicht"], 1, "FAIL")):
            with self.subTest(argumente=argumente), \
                    patch("tools.rauchtests._bruecke.playwright_da", return_value=(False, "Browser fehlt")), \
                    patch.object(alle_tests, "_lauf") as lauf, \
                    redirect_stdout(io.StringIO()) as ausgabe:
                self.assertEqual(alle_tests.main(["runner", "--nur", "rauch", *argumente]), exitcode)
                self.assertIn(meldung, ausgabe.getvalue())
                self.assertIn("Browser fehlt", ausgabe.getvalue())
                if exitcode:
                    self.assertNotIn("alles grün", ausgabe.getvalue())
                lauf.assert_not_called()

    def test_roter_browserlauf_bleibt_rot(self):
        with patch("tools.rauchtests._bruecke.playwright_da", return_value=(True, "")), \
                patch.object(alle_tests, "_lauf", return_value=(1, "AssertionError")), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(alle_tests.main([
                "runner", "--nur", "rauch", "--rauch-pflicht", "--rauchtest", "items"]), 1)

    def test_vertragsfehler_wird_nicht_durch_gruene_wurzeltests_verdeckt(self):
        for code in (0, 1):
            befehle = []

            def lauf(befehl):
                befehle.append(befehl)
                if "test_logic.py" in befehl[-1]:
                    return code, "1 PASS / 0 FAIL " if code == 0 else "0 PASS / 1 FAIL "
                return 0, "OK"

            with self.subTest(code=code), patch.object(alle_tests, "_lauf", side_effect=lauf), \
                    redirect_stdout(io.StringIO()):
                self.assertEqual(alle_tests.main(["runner", "--nur", "vertrag", "--nur", "wurzel"]), code)
            self.assertEqual(len(befehle), 2)
            self.assertIn("--ohne-vertrag", befehle[1])

    def test_wurzel_allein_behaelt_den_vertragswrapper(self):
        with patch.object(alle_tests, "_lauf", return_value=(0, "OK")) as lauf, \
                redirect_stdout(io.StringIO()):
            self.assertEqual(alle_tests.main(["runner", "--nur", "wurzel"]), 0)
        self.assertNotIn("--ohne-vertrag", lauf.call_args.args[0])

    def test_discovery_entfernt_nur_den_vertragswrapper(self):
        def ids(suite):
            for test in suite:
                if isinstance(test, unittest.TestSuite):
                    yield from ids(test)
                else:
                    yield test.id()

        wurzel = Path(__file__).resolve().parent
        voll = set(ids(wurzeltests.sammeln(wurzel)))
        einzeln = set(ids(wurzeltests.sammeln(wurzel, ohne_vertrag=True)))
        self.assertEqual(voll - einzeln, {"test_regression.RegressionSuiteTest.test_logic_regressions"})
        self.assertEqual(einzeln - voll, set())
        self.assertTrue(einzeln)


if __name__ == "__main__":
    unittest.main()
