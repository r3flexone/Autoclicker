"""Der Runner darf fehlende Pflichtprüfungen nicht als Erfolg ausgeben."""

from contextlib import redirect_stdout
import io
from pathlib import Path
import unittest
from unittest.mock import patch

from tests import all_tests, root_tests


class TestRunnerTest(unittest.TestCase):
    def test_exitcode_null_ohne_erfolgreichen_vertragsabschluss_reicht_nicht(self):
        for ausgabe in ("", "Start ohne Abschluss", "0 PASS / 0 FAIL",
                        "8 PASS / 1 FAIL", "8 PASS / 0 FAIL\n9 PASS / 1 FAIL"):
            with self.subTest(ausgabe=ausgabe), \
                    patch.object(all_tests, "_run", return_value=(0, ausgabe)):
                self.assertFalse(all_tests.contract().ok)
        with patch.object(all_tests, "_run", return_value=(0, "=== 8 PASS / 0 FAIL ===")):
            self.assertTrue(all_tests.contract().ok)

    def test_nicht_erkannter_mutant_macht_den_gesamtlauf_rot(self):
        with patch.object(all_tests, "_run", side_effect=[(0, "OK"), (1, "LÜCKE")]), \
                redirect_stdout(io.StringIO()) as ausgabe:
            self.assertEqual(all_tests.main(["runner", "--only", "root", "--mutations"]), 1)
        self.assertIn("Gegenproben", ausgabe.getvalue())
        self.assertNotIn("alles grün", ausgabe.getvalue())

    def test_browser_lokal_optional_aber_als_pflicht_rot(self):
        for arguments, exitcode, message in (
                ([], 0, "ÜBERSPRUNGEN"), (["--smoke-required"], 1, "FAIL")):
            with self.subTest(arguments=arguments), \
                    patch("tests.smoke._bridge.playwright_available", return_value=(False, "Browser fehlt")), \
                    patch.object(all_tests, "_run") as run, \
                    redirect_stdout(io.StringIO()) as ausgabe:
                self.assertEqual(all_tests.main(["runner", "--only", "smoke", *arguments]), exitcode)
                self.assertIn(message, ausgabe.getvalue())
                self.assertIn("Browser fehlt", ausgabe.getvalue())
                if exitcode:
                    self.assertNotIn("alles grün", ausgabe.getvalue())
                run.assert_not_called()

    def test_roter_browserlauf_bleibt_rot(self):
        with patch("tests.smoke._bridge.playwright_available", return_value=(True, "")), \
                patch.object(all_tests, "_run", return_value=(1, "AssertionError")), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(all_tests.main([
                "runner", "--only", "smoke", "--smoke-required", "--smoke-test", "items"]), 1)

    def test_vertragsfehler_wird_nicht_durch_gruene_wurzeltests_verdeckt(self):
        for code in (0, 1):
            commands = []

            def run(command):
                commands.append(command)
                if "test_logic.py" in command[-1]:
                    return code, "1 PASS / 0 FAIL " if code == 0 else "0 PASS / 1 FAIL "
                return 0, "OK"

            with self.subTest(code=code), patch.object(all_tests, "_run", side_effect=run), \
                    redirect_stdout(io.StringIO()):
                self.assertEqual(all_tests.main(["runner", "--only", "contract", "--only", "root"]), code)
            self.assertEqual(len(commands), 2)
            self.assertIn("--without-contract", commands[1])

    def test_wurzel_allein_behaelt_den_vertragswrapper(self):
        with patch.object(all_tests, "_run", return_value=(0, "OK")) as run, \
                redirect_stdout(io.StringIO()):
            self.assertEqual(all_tests.main(["runner", "--only", "root"]), 0)
        self.assertNotIn("--without-contract", run.call_args.args[0])

    def test_discovery_entfernt_nur_den_vertragswrapper(self):
        def ids(suite):
            for test in suite:
                if isinstance(test, unittest.TestSuite):
                    yield from ids(test)
                else:
                    yield test.id()

        root_layer = Path(__file__).resolve().parent
        full_value = set(ids(root_tests.collect(root_layer)))
        single = set(ids(root_tests.collect(root_layer, without_contract=True)))
        self.assertEqual(full_value - single, {"test_regression.RegressionSuiteTest.test_logic_regressions"})
        self.assertEqual(single - full_value, set())
        self.assertTrue(single)


if __name__ == "__main__":
    unittest.main()
