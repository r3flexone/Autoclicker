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
import tempfile
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
       for kind in ("click", "key")},
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
    "loader-scans": (
        "autoclicker.editors.sequence_editor.loader", "run_sequence_loader",
        "activate_sequence(state, seq)",
        "state.active_sequence = seq; state.points = seq.points",
        RUNTIME + "test_konsolen_loader_laedt_die_scans_der_sequenz"),
    "new-sequence-collision": (
        "autoclicker.editors.sequence_studio.bridge_services",
        "BridgeServicesMixin._save_move_folder",
        "if new_folder.exists():",
        "if old.exists() and new_folder.exists():",
        STUDIO + "test_neue_sequenz_ueberschreibt_keine_vorhandene"),
    "scan-block-skip": (
        "autoclicker.runtime.item_scan", "_scan_interrupted",
        "Rest des Blocks lief weiter.\n        return True",
        "Rest des Blocks lief weiter.\n        state.skip_step_event.clear()\n        return True",
        RUNTIME + "test_block_skip_im_immediate_scan_gilt_dem_ganzen_block"),
    "orderbook-outlier": (
        "market_analysis.orderbook", "_levels",
        'and plausible_price(entry["key"], reference)]', "]",
        "test_market_analysis.OutlierTest.test_ausreisser_im_buch_zaehlen_nicht"),
    "outlier-top": (
        "market_analysis.orderbook", "implausible_top",
        "and not plausible_price(entry[side], avg)", "and False",
        "test_market_analysis.OutlierTest.test_unplausibles_gebot_wird_durch_die_naechste_stufe_ersetzt"),
    "auto-cook-tax-per-hour": (
        "market_analysis.pricing", "_fishing_with_auto_cook",
        "effective_sell_price(other_id, market_map, item_info_map, other_per_hour)",
        "effective_sell_price(other_id, market_map, item_info_map, other_amount)",
        "test_market_analysis.ChainTest.test_rohrest_versteuert_je_stunde_nicht_je_stueck"),
    "raw-fish-auto-cook": (
        "market_analysis.pricing", "resolve_chain",
        "if cooked_id is not None and cooked_id not in visited and AUTO_COOK_CHANCE > 0:",
        "if False:",
        "test_market_analysis.ChainTest.test_roher_fisch_kommt_mit_auto_cook_nur_teilweise_roh"),
    "auto-learn-active-variant": (
        "autoclicker.runtime.item_scan", "_learn_against_known",
        "    if known_active:", "    if False:",
        RUNTIME + "test_auto_lernen_haengt_keine_variante_an_ein_eingeschaltetes_item"),
}


def run_check(name: str, mutated: bool) -> int:
    # Zwei Orte: das Repo-Wurzelverzeichnis fuer `autoclicker` und `tests`, und
    # `tests/root` fuer die Testmodule, die `CASES` beim Namen nennt.
    for _path in (ROOT, ROOT / "tests" / "root"):
        if str(_path) not in sys.path:
            sys.path.insert(0, str(_path))
    module_name, path, old, new, test = CASES[name]
    # Der Aufrufer startet jeden Lauf in einem eigenen Ordner, der danach
    # weggeräumt wird; Temp-Ordner der Testfälle entstehen darin mit.
    tempfile.tempdir = os.getcwd()
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
            # Jeder Lauf in einem eigenen, leeren Ordner — nie im Repo. Die
            # Pfade der App sind CWD-relativ, und die Testfaelle hier werden
            # beim Namen geladen, also ohne den Arbeitsordner von
            # `root_tests.main()`: ein Item-Scan-Fall schrieb so bei jeder
            # Gegenprobe `.run.json` in die echten Daten. `run_check` legt das
            # Repo selbst in `sys.path`.
            with tempfile.TemporaryDirectory(prefix="gegenprobe_",
                                             ignore_cleanup_errors=True) as workdir:
                try:
                    run = subprocess.run(
                        [sys.executable, str(Path(__file__).resolve()),
                         "--case", name, "--kind", mode],
                        cwd=workdir, env=environment, capture_output=True, text=True,
                        encoding="utf-8", errors="replace", timeout=60)
                except subprocess.TimeoutExpired:
                    run = None
            if run is None:
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
