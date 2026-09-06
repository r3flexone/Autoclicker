"""Unittest-Discovery ohne doppelten Vertragslauf im gemeinsamen Runner."""

import argparse
from pathlib import Path
import unittest


def sammeln(wurzel: Path, ohne_vertrag: bool = False) -> unittest.TestSuite:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for datei in sorted(wurzel.glob("test_*.py")):
        if ohne_vertrag and datei.name == "test_regression.py":
            continue
        suite.addTests(loader.discover(str(wurzel), pattern=datei.name))
    return suite


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ohne-vertrag", action="store_true")
    args = parser.parse_args()
    suite = sammeln(Path(__file__).resolve().parents[1], args.ohne_vertrag)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
