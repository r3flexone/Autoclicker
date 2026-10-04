"""Unittest-Discovery ohne doppelten Vertragslauf im gemeinsamen Runner."""

import argparse
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

# Die Wurzelmodule liegen in `tests/root/`, importieren aber `autoclicker`,
# `main` und `market_analysis` — die stehen im Repo-Wurzelverzeichnis. Beim
# Aufruf als `python -m tests.root_tests` liegt das ohnehin in `sys.path`;
# ausgeschrieben (`python tests/root_tests.py`) nicht. Eine Zeile, und beide
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--without-contract", action="store_true")
    args = parser.parse_args(argv)
    # **Gelaufen wird in einem eigenen Ordner, nie im Repo** — dieselbe Regel
    # und derselbe Grund wie beim Arbeitsordner der Vertragssuite
    # (`tests/contract/_harness.py`): die Pfade der App sind CWD-relativ, und
    # jeder Test ohne eigene Sandbox schrieb in die echten Daten (zuletzt
    # `.run.json` aus einem Item-Scan-Test). Hier statt in jedem Testfall: ein
    # Schutz, an den jeder Testfall denken muss, ist einer, den einer vergisst.
    previous = os.getcwd()
    previous_temp = tempfile.tempdir
    sandbox = tempfile.mkdtemp(prefix="wurzelmodule_")
    os.chdir(sandbox)
    # Auch die Temp-Ordner der Testfälle entstehen darin und gehen mit weg —
    # dieselbe Regel wie in `tests/contract/_harness.py`.
    tempfile.tempdir = sandbox
    try:
        suite = collect(MODULE, args.without_contract)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    finally:
        tempfile.tempdir = previous_temp
        os.chdir(previous)
        shutil.rmtree(sandbox, ignore_errors=True)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
