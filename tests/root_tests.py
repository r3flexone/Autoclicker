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
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# `discover()` legt das Startverzeichnis selbst in `sys.path` — deshalb findet
# ein Wurzelmodul sein `test_support` als schlichten Nachbarn, ohne Paketpfad.
MODULE = Path(__file__).resolve().parent / "root"


def collect(root_layer: Path, without_contract: bool = False) -> unittest.TestSuite:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for file in sorted(root_layer.glob("test_*.py")):
        if without_contract and file.name == "test_regression.py":
            continue
        suite.addTests(loader.discover(str(root_layer), pattern=file.name))
    return suite


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--without-contract", action="store_true")
    args = parser.parse_args()
    suite = collect(MODULE, args.without_contract)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
