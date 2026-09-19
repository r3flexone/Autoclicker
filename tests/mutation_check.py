"""Gezielte Gegenproben: python tests/mutation_check.py [--case NAME].

Jeder Fall läuft zuerst unverändert, danach mit einer entfernten Sicherung in
einem frischen Prozess. Nur Assertion-Fehler erkennen einen Mutanten; Import-
fehler, übersprungene Tests und Timeouts sind keine erfolgreiche Gegenprobe.
Geändert wird ausschliesslich Funktionscode im Arbeitsspeicher, keine Datei.
Dies ist eine gezielte Regressionsprüfung, keine vollständige Mutationsanalyse.
"""

import argparse
import importlib
import inspect
import io
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = "test_runtime_hardening.RuntimeHardeningTest."
STUDIO = "test_studio_close.StudioCloseTest."
CASES = {
    "browser-required": (
        "tests.all_tests", "smoke", "e.ok = False", "e.ok = True",
        "test_test_runner.TestRunnerTest.test_browser_lokal_optional_aber_als_pflicht_rot"),
    "double-contract-run": (
        "tests.root_tests", "collect", "continue", "pass",
        "test_test_runner.TestRunnerTest.test_discovery_entfernt_nur_den_vertragswrapper"),
    "pause-after-focus": (
        "autoclicker.runtime.actions", "_input_allowed",
        "if not state.pause_event.is_set():", "if True:",
        "test_input_synchronisation.InputSynchronisationTest"),
    **{f"stop-after-delay-{kind}": (
        "autoclicker.runtime.actions", f"safe_{kind}",
        "_humanize_delay(state)\n        if not _input_allowed(state, label):\n            return False",
        "_humanize_delay(state)",
        RUNTIME + "test_stopp_im_mikrodelay_verhindert_jede_eingabe")
       for kind in ("click", "key", "scroll")},
    "worker-run-status": (
        "autoclicker.runtime.worker", "sequence_worker",
        "state.is_running = False", "state.is_running = True",
        RUNTIME + "test_worker_fehler_raeumt_lauf_und_log_auf"),
    "rescue-points": (
        "autoclicker.editors.sequence_studio.bridge_services",
        "BridgeServicesMixin.rescue_write",
        "sequence.points = palette_to_points(self.points)", "sequence.points = []",
        STUDIO + "test_rettung_ist_am_gemeldeten_pfad_vollstaendig_ladbar"),
    "scan-write-error": (
        "autoclicker.persistence._scan_store", "write_scan",
        "return False", "return True",
        STUDIO + "test_scan_schreibfehler_bleibt_ungespeichert_und_ist_wiederholbar"),
    "import-rollback": (
        "autoclicker.import_export", "_ImportTransaction.rollback",
        "from .config import apply_config", "return\n    from .config import apply_config",
        "test_import_export_security.ImportExportSecurityTest.test_failed_import_rolls_back_state_and_files"),
}


def run_check(name: str, mutated: bool) -> int:
    # Zwei Orte: das Repo-Wurzelverzeichnis fuer `autoclicker` und `tests`, und
    # `tests/root` fuer die Testmodule, die `CASES` beim Namen nennt.
    for _path in (ROOT, ROOT / "tests" / "root"):
        if str(_path) not in sys.path:
            sys.path.insert(0, str(_path))
    module_name, path, old, new, test = CASES[name]
    suite = unittest.defaultTestLoader.loadTestsFromName(test)
    function_obj = importlib.import_module(module_name)
    for part in path.split("."):
        function_obj = getattr(function_obj, part)
    original = function_obj.__code__
    try:
        if mutated:
            source = textwrap.dedent(inspect.getsource(function_obj))
            if source.count(old) != 1:
                raise ValueError(f"Mutationsstelle nicht mehr eindeutig: {name}")
            namespace = dict(function_obj.__globals__)
            exec(compile(source.replace(old, new), f"<Gegenprobe {name}>", "exec"), namespace)
            # Auch zuvor importierte Funktionsreferenzen sehen den Mutanten.
            function_obj.__code__ = namespace[function_obj.__name__].__code__
        output = io.StringIO()
        result = unittest.TextTestRunner(stream=output).run(suite)
    finally:
        function_obj.__code__ = original
    if not result.testsRun or result.errors or result.skipped:
        print(output.getvalue())
        return 2
    if mutated:
        if result.failures:
            return 0
        print("LÜCKE: Der eingeschleuste Fehler bleibt grün.")
        return 1
    if not result.wasSuccessful():
        print(output.getvalue())
        return 2
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", choices=CASES, action="append")
    parser.add_argument("--kind", choices=("basis", "mutiert"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.kind:
        return run_check(args.case[0], args.kind == "mutiert")
    error = 0
    environment = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    for name in args.case or CASES:
        for mode in ("basis", "mutiert"):
            try:
                run = subprocess.run(
                    [sys.executable, str(Path(__file__).resolve()), "--case", name, "--kind", mode],
                    cwd=ROOT, env=environment, capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=60)
            except subprocess.TimeoutExpired:
                print(f"FEHLER {name}: Zeitlimit ({mode})", flush=True)
                error += 1
                break
            if run.returncode:
                print(f"FEHLER {name} ({mode})\n{run.stdout}\n{run.stderr}", flush=True)
                error += 1
                break
        else:
            print(f"ERKANNT {name}: Basis grün, Mutant durch Assertion rot", flush=True)
    return 1 if error else 0


if __name__ == "__main__":
    raise SystemExit(main())
