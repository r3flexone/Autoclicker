"""Gezielte Gegenproben: python tests/mutationspruefung.py [--case NAME].

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

WURZEL = Path(__file__).resolve().parents[1]
RUNTIME = "test_runtime_hardening.RuntimeHardeningTest."
STUDIO = "test_studio_close.StudioCloseTest."
FAELLE = {
    "browser-pflicht": (
        "tests.all_tests", "smoke", "e.ok = False", "e.ok = True",
        "test_test_runner.TestRunnerTest.test_browser_lokal_optional_aber_als_pflicht_rot"),
    "doppelter-vertragslauf": (
        "tests.root_tests", "sammeln", "continue", "pass",
        "test_test_runner.TestRunnerTest.test_discovery_entfernt_nur_den_vertragswrapper"),
    "pause-nach-fokus": (
        "autoclicker.runtime.actions", "_input_allowed",
        "if not state.pause_event.is_set():", "if True:",
        "test_input_synchronisation.EingabeSynchronisationTest"),
    **{f"stopp-nach-delay-{kind}": (
        "autoclicker.runtime.actions", f"safe_{kind}",
        "_humanize_delay(state)\n        if not _input_allowed(state, label):\n            return False",
        "_humanize_delay(state)",
        RUNTIME + "test_stopp_im_mikrodelay_verhindert_jede_eingabe")
       for kind in ("click", "key", "scroll")},
    "worker-laufstatus": (
        "autoclicker.runtime.worker", "sequence_worker",
        "state.is_running = False", "state.is_running = True",
        RUNTIME + "test_worker_fehler_raeumt_lauf_und_log_auf"),
    "rettung-punkte": (
        "autoclicker.editors.sequence_studio.bridge_services",
        "BridgeServicesMixin.rescue_write",
        "sequence.points = palette_to_points(self.points)", "sequence.points = []",
        STUDIO + "test_rettung_ist_am_gemeldeten_pfad_vollstaendig_ladbar"),
    "scan-schreibfehler": (
        "autoclicker.persistence._scan_store", "write_scan",
        "return False", "return True",
        STUDIO + "test_scan_schreibfehler_bleibt_ungespeichert_und_ist_wiederholbar"),
    "import-rollback": (
        "autoclicker.import_export", "_ImportTransaction.rollback",
        "from .config import apply_config", "return\n    from .config import apply_config",
        "test_import_export_security.ImportExportSecurityTest.test_failed_import_rolls_back_state_and_files"),
}


def pruefen(name: str, mutiert: bool) -> int:
    # Zwei Orte: das Repo-Wurzelverzeichnis fuer `autoclicker` und `tests`, und
    # `tests/wurzel` fuer die Testmodule, die `FAELLE` beim Namen nennt.
    for _path in (WURZEL, WURZEL / "tests" / "root"):
        if str(_path) not in sys.path:
            sys.path.insert(0, str(_path))
    module_name, path, old, new, test = FAELLE[name]
    suite = unittest.defaultTestLoader.loadTestsFromName(test)
    funktion = importlib.import_module(module_name)
    for part in path.split("."):
        funktion = getattr(funktion, part)
    original = funktion.__code__
    try:
        if mutiert:
            source = textwrap.dedent(inspect.getsource(funktion))
            if source.count(old) != 1:
                raise ValueError(f"Mutationsstelle nicht mehr eindeutig: {name}")
            namensraum = dict(funktion.__globals__)
            exec(compile(source.replace(old, new), f"<Gegenprobe {name}>", "exec"), namensraum)
            # Auch zuvor importierte Funktionsreferenzen sehen den Mutanten.
            funktion.__code__ = namensraum[funktion.__name__].__code__
        ausgabe = io.StringIO()
        result = unittest.TextTestRunner(stream=ausgabe).run(suite)
    finally:
        funktion.__code__ = original
    if not result.testsRun or result.errors or result.skipped:
        print(ausgabe.getvalue())
        return 2
    if mutiert:
        if result.failures:
            return 0
        print("LÜCKE: Der eingeschleuste Fehler bleibt grün.")
        return 1
    if not result.wasSuccessful():
        print(ausgabe.getvalue())
        return 2
    return 0


def main() -> int:
    for strom in (sys.stdout, sys.stderr):
        if hasattr(strom, "reconfigure"):
            strom.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", choices=FAELLE, action="append")
    parser.add_argument("--kind", choices=("basis", "mutiert"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.kind:
        return pruefen(args.case[0], args.kind == "mutiert")
    error = 0
    umgebung = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    for name in args.case or FAELLE:
        for mode in ("basis", "mutiert"):
            try:
                run = subprocess.run(
                    [sys.executable, str(Path(__file__).resolve()), "--case", name, "--kind", mode],
                    cwd=WURZEL, env=umgebung, capture_output=True, text=True,
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
