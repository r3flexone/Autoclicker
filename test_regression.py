"""Standard-Discovery-Wrapper für den projektspezifischen Regressionstest."""

import os
from pathlib import Path
import subprocess
import sys
import unittest


class RegressionSuiteTest(unittest.TestCase):
    def test_logic_regressions(self):
        root = Path(__file__).resolve().parent
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        result = subprocess.run(
            [sys.executable, str(root / "tools" / "test_logic.py")],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"Regressionstest fehlgeschlagen.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
        )
        self.assertIn(" PASS / 0 FAIL ", result.stdout)


if __name__ == "__main__":
    unittest.main()
