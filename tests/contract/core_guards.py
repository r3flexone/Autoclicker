"""Sicherungen in Persistenz und Modell, die bis zum Umbau keine Prüfung hatten.

Aufgefallen bei der Gegenprobe nach dem Zerlegen von `resolve()`,
`_parse_steps()` & Co.: an diesen Stellen konnte man die Sicherung entfernen,
und die ganze Suite blieb grün. Jede Prüfung hier wird auf der entschärften
Fassung rot.
"""
import contextlib as _cl
import io as _io

from ._harness import check, section

from autoclicker.models import (
    ClickPoint as _CP, LoopPhase as _LP, Sequence as _SEQ, SequenceStep as _STEP,
)
from autoclicker.persistence.sequences import resolve as _resolve
from autoclicker.persistence.serialization import _parse_steps

# =============================================================================
section("Auflösen: gemeldet wird ein Umzug, nicht das erste Füllen")
# =============================================================================
# Ein frisch geladener Schritt steht auf (0, 0), bis der Punkt ihn füllt. Das
# als „folgt Punkt #1: (0, 0) -> …" zu melden, hiesse bei jedem Laden eine
# Zeile je Klick — und die echten Umzüge gingen darin unter.
_step = _STEP(x=0, y=0, point_id=1)
_seq = _SEQ(name="Farm", loop_phases=[_LP("Loop 1", [_step])])
_points = {1: _CP(10, 20, "Knopf", 1)}
check("das erste Füllen bleibt still", _resolve(_points, _seq) == []
      and (_step.x, _step.y) == (10, 20))
_points[1] = _CP(30, 40, "Knopf", 1)
_said = _resolve(_points, _seq)
check("ein Umzug des Punkts wird gemeldet",
      len(_said) == 1 and "folgt Punkt #1: (10, 20) -> (30, 40)" in _said[0])
_points[1] = _CP(50, 60, "Knopf", 1)
check("ausser auf Wunsch still", _resolve(_points, _seq, quiet=True) == []
      and (_step.x, _step.y) == (50, 60))
check("und ohne Änderung nichts", _resolve(_points, _seq) == [])

# =============================================================================
section("Laden: ein Screenshot-Bereich braucht vier Werte")
# =============================================================================
_out = _io.StringIO()
with _cl.redirect_stdout(_out):
    _three, _four = _parse_steps([
        {"screenshot_only": True, "screenshot_region": [1, 2, 3]},
        {"screenshot_only": True, "screenshot_region": ["1", 2, 3.0, 4]},
    ])
check("drei Werte: kein Bereich, also Vollbild", _three.screenshot_region is None)
check("und es wird gesagt", "Ungültige screenshot_region" in _out.getvalue())
check("vier Werte werden ganze Zahlen", _four.screenshot_region == (1, 2, 3, 4))

# =============================================================================
section("Config: Spannen und Meldungen der Korrektur")
# =============================================================================
from autoclicker.config import AppConfig as _AC                    # noqa: E402

_out = _io.StringIO()
with _cl.redirect_stdout(_out):
    _cfg = _AC(humanize_micro_delay_min=-3, humanize_micro_delay_max=-5,
               humanize_break_interval_min=-1,
               humanize_break_duration_min=40, humanize_break_duration_max=10)
check("ein negatives Minimum wird 0, ein Maximum darunter zieht nach",
      (_cfg.humanize_micro_delay_min, _cfg.humanize_micro_delay_max) == (0, 0))
check("ein Pausen-Abstand unter 0 wird 0", _cfg.humanize_break_interval_min == 0)
check("eine Pausendauer mit max < min wird auf min gehoben",
      (_cfg.humanize_break_duration_min, _cfg.humanize_break_duration_max) == (40, 40))
check("still — die Spannen werden nicht gemeldet", _out.getvalue() == "")

_out = _io.StringIO()
with _cl.redirect_stdout(_out):
    _cfg = _AC(ocr_backend="paddle", pixel_check_interval=0)
check("ein unbekanntes OCR-Backend wird 'automatisch'", _cfg.ocr_backend is None)
check("und die Meldung nennt es so",
      "ocr_backend='paddle' → None (Auto)" in _out.getvalue()
      and "pixel_check_interval=0 → 0.1" in _out.getvalue())

# =============================================================================
section("Katalog: eine neu geschriebene Datei wird neu gelesen")
# =============================================================================
import json as _json                                                # noqa: E402
import tempfile as _tmp                                             # noqa: E402
from pathlib import Path as _P                                      # noqa: E402
from autoclicker.catalog import load_catalog as _load_catalog       # noqa: E402

_file = _P(_tmp.mkdtemp(prefix="katalog_stand_")) / "katalog.json"
_file.write_text(_json.dumps({"items": {"Bogen": {"kategorie": "Bogen", "wert": 1}}}),
                 encoding="utf-8")
_first = _load_catalog(str(_file))
_file.write_text(_json.dumps({"items": {"Godlike Bow": {"kategorie": "Bow", "wert": 99}}}),
                 encoding="utf-8")
_second = _load_catalog(str(_file))
check("nach dem Neuschreiben gilt der neue Inhalt, nicht der zwischengespeicherte",
      _second is not _first and _second.category("Godlike Bow") == "Bow")

# =============================================================================
section("Diagnose: auch ein Boss-Watcher zeigt auf einen Scan")
# =============================================================================
from autoclicker.diagnostics import _dead_references                # noqa: E402

_seq = _SEQ(name="Nirgends", loop_phases=[_LP("Loop 1", [
    _STEP(boss_watcher="Wächter"), _STEP(boss_scan="Drache"), _STEP(point_id=7)])])
_refs, _scans = _dead_references(_seq)
check("ein Watcher auf einen fehlenden Boss-Scan wird gemeldet",
      any("boss_watcher 'Wächter'" in text for text, _target in _scans))
check("ebenso der Boss-Scan selbst", any("boss_scan 'Drache'" in text for text, _t in _scans))
check("und der tote Punkt", [text for text, _t in _refs] == ["Loop 1[3] → Punkt #7"])
