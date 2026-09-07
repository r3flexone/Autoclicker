"""Unittest-Discovery ohne doppelten Vertragslauf im gemeinsamen Runner."""

import argparse
from pathlib import Path
import sys
import unittest

# Die Wurzelmodule liegen in `tests/wurzel/`, importieren aber `autoclicker`,
# `main` und `market_analysis` — die stehen im Repo-Wurzelverzeichnis. Beim
# Aufruf als `python -m tests.wurzeltests` liegt das ohnehin in `sys.path`;
# ausgeschrieben (`python tests/wurzeltests.py`) nicht. Eine Zeile, und beide
# Wege funktionieren.
WURZEL = Path(__file__).resolve().parents[1]
if str(WURZEL) not in sys.path:
    sys.path.insert(0, str(WURZEL))

# `discover()` legt das Startverzeichnis selbst in `sys.path` — deshalb findet
# ein Wurzelmodul sein `test_support` als schlichten Nachbarn, ohne Paketpfad.
MODULE = Path(__file__).resolve().parent / "wurzel"


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
    suite = sammeln(MODULE, args.ohne_vertrag)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
