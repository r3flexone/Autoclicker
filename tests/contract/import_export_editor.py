"""Konsolen-Editor für Export, Import und Kalibrierung, per Tastenfolge.

Geschrieben, BEVOR `_run_import` (39), `run_calibration` (21) und
`_run_export` (15) zerlegt wurden. Gestellt werden Tastatur, Maus, Fenster
und die Bündel-Funktionen aus `import_export`; die reinen Rechnungen
(`compute_transform`, `transform_from_offset`, `is_identity`) laufen echt mit.
Die Stellvertreter setzt `_Run` in jedem Modul, das den Namen kennt — die
Editor-Funktionen holen viele davon erst im Rumpf.
"""
import contextlib as _cl
import io as _io
from pathlib import Path as _Path

from ._harness import check, section

section("Import/Export-Editor: Export, Import, Kalibrierung per Tastenfolge")

import autoclicker.editors.import_export_editor as _IEE
import autoclicker.import_export as _IE
import autoclicker.persistence as _PERS
import autoclicker.winapi as _WIN
from autoclicker.models import AutoClickerState as _ST, ClickPoint as _CP, ItemSlot as _SLOT

_MODULES = (_IEE, _IE, _PERS, _WIN)


class _Run:
    def __init__(self, inputs=(), choices=(), answers=(), cursor=(), window=None,
                 desktop=None, **stubs):
        self.inputs, self.choices, self.answers = list(inputs), list(choices), list(answers)
        self.cursor = list(cursor)
        self.window, self.desktop = window, desktop
        self.extra = stubs
        self.calls = []
        self.output = ""
        self.state = _ST()

    def stubs(self):
        stubs = {
            "safe_input": lambda _p="": self.inputs.pop(0) if self.inputs else "cancel",
            "confirm": lambda _q, *a, **k: self.answers.pop(0) if self.answers else False,
            "interactive_select": lambda *a, **k: self.choices.pop(0) if self.choices else -1,
            "get_cursor_pos": lambda: self.cursor.pop(0) if self.cursor else (0, 0),
            "set_cursor_pos": lambda x, y: self.calls.append(("maus", x, y)),
            "get_client_rect_by_title": lambda title: self.window,
            "get_virtual_desktop": lambda: self.desktop,
        }
        stubs.update(self.extra)
        return stubs

    def __call__(self, fn, *args):
        saved = []
        for module in _MODULES:
            for name, value in self.stubs().items():
                if hasattr(module, name):
                    saved.append((module, name, getattr(module, name)))
                    setattr(module, name, value)
        buffer = _io.StringIO()
        try:
            with _cl.redirect_stdout(buffer):
                result = fn(self.state, *args)
        finally:
            for module, name, value in reversed(saved):
                setattr(module, name, value)
            self.output = buffer.getvalue()
        return result


# ============================================================ Export
def _export(inputs=(), select=False, ok=True, window=None, title="Spiel", **kw):
    exported = []

    def export(state, path, ref1, ref2, **flags):
        _Path(path).parent.mkdir(parents=True, exist_ok=True)
        _Path(path).write_bytes(b"x" * 2048)
        exported.append((path, ref1, ref2, flags))
        return (True, path) if ok else (False, "Platte voll")

    run = _Run(inputs=inputs, window=window, export_bundle=export,
               list_available_sequences=lambda *a: [("A", None), ("B", None)], **kw)
    run.state.config.window_focus_title = title
    run(_IEE._run_export, select)
    run.exported = exported
    return run


_r = _export(inputs=[""], window=(100, 50, 900, 650))
_path, _ref1, _ref2, _flags = _r.exported[0]
check("Export: mit Spielfenster kommen die Referenzpunkte aus dessen Ecken",
      (_ref1, _ref2, _flags["source_window"]) == ((100, 50), (900, 650), (100, 50, 900, 650)))
check("Export: der Standardname liegt unter exports/",
      _path.startswith("exports") and _path.endswith(".zip") and "autoclicker_export_" in _path)
check("Export: Sequenzen und Config sind dabei",
      _flags["include_sequences"] is True and _flags["include_config"] is True)
check("Export: zählt die Sequenzen und erklärt den Empfang",
      "Sequenzordner: 2" in _r.output and "ANLEITUNG" in _r.output and "2.0 KB" in _r.output)
_r = _export(inputs=["", "", "mein"], cursor=[(1, 2), (300, 400)])
_path, _ref1, _ref2, _flags = _r.exported[0]
check("Export: ohne Fenster zwei Punkte von Hand, '.zip' wird ergänzt",
      (_ref1, _ref2, _flags["source_window"]) == ((1, 2), (300, 400), None)
      and _path.endswith("mein.zip") and "nicht gefunden" in _r.output)
_r = _export(inputs=["", ""], cursor=[(5, 5), (5, 5)], title="")
check("Export: gleiche Punkte werden abgelehnt",
      not _r.exported and "identisch" in _r.output and "nicht gefunden" not in _r.output)
_r = _export(inputs=["cancel"])
check("Export: Abbruch beim ersten Punkt", not _r.exported and "Abgebrochen" in _r.output)
_r = _export(inputs=["", "cancel"])
check("Export: Abbruch beim zweiten Punkt", not _r.exported)
_r = _export(inputs=["cancel"], window=(0, 0, 10, 10))
check("Export: Abbruch beim Dateinamen", not _r.exported and "Abgebrochen" in _r.output)
_r = _export(inputs=["n", "n"], select=True)
check("Export mit Auswahl: nichts gewählt", not _r.exported and "Nichts zum Exportieren" in _r.output)
_r = _export(inputs=["n", "", "x.zip"], select=True, window=(0, 0, 10, 10))
check("Export mit Auswahl: nur die Config",
      _r.exported[0][3]["include_sequences"] is False and _r.exported[0][3]["include_config"] is True)
_r = _export(inputs=[""], window=(0, 0, 10, 10), ok=False)
check("Export: ein Fehlschlag wird gesagt", "Export fehlgeschlagen: Platte voll" in _r.output)


# ============================================================ Import
_MANIFEST = {"contents": {"sequences": ["Raid"], "config": True, "templates": 3},
             "reference_points": {"point1": [0, 0], "point2": [1000, 500]},
             "sequence_descriptions": {"Raid": "Tagesrunde"},
             "source_window": [0, 0, 1000, 500]}


def _import(inputs=(), choices=(0,), answers=(True,), manifest=None, ok=True, window=None,
            zips=("a.zip",), outside=(), cursor=()):
    imported = []
    folder = _Path("exports")
    folder.mkdir(exist_ok=True)
    for old in folder.glob("*.zip"):
        old.unlink()
    for name in zips:
        (folder / name).write_bytes(b"zip")
    manifest = _MANIFEST if manifest is None else manifest

    def import_bundle(state, path, transform=None, merge=True, **flags):
        imported.append((path, transform, merge, flags))
        return (True, "1 Sequenz") if ok else (False, "kaputt")

    run = _Run(inputs=inputs, choices=choices, answers=answers, window=window, cursor=cursor,
               read_manifest=lambda path: (True, manifest) if manifest else (False, "kein Manifest"),
               import_bundle=import_bundle,
               clicks_outside_window=lambda state, win: list(outside))
    run.state.config.window_focus_title = "Spiel"
    run(_IEE._run_import)
    run.imported = imported
    return run


_r = _import(inputs=["", "", "", ""], window=(0, 0, 2000, 1000))
_path, _t, _merge, _flags = _r.imported[0]
check("Import: die gewählte Datei aus exports/", _path.endswith("a.zip"))
check("Import: mit beiden Fenstern automatisch aus der Fenstergrösse",
      (_t["scale_x"], _t["scale_y"]) == (2.0, 2.0) and "Skalierung: 200.00%" in _r.output)
check("Import: was im Bündel steht, wird gefragt und übernommen; Merge ist Vorgabe",
      _flags == {"import_sequences": True, "import_config": True} and _merge is True)
check("Import: Inhalt samt Beschreibung wird gezeigt",
      "Tagesrunde" in _r.output and "Templates:   3" in _r.output and "Config:      ja" in _r.output)
check("Import: eine Umrechnung wird zum Prüfen empfohlen", "debug_detail" in _r.output)
_r = _import(inputs=["3", "", "n", "2"], window=(0, 0, 1000, 500))
check("Import: 1:1, Config abgewählt, Ersetzen",
      _r.imported[0][1] is None and _r.imported[0][3]["import_config"] is False
      and _r.imported[0][2] is False and "debug_detail" not in _r.output)
_r = _import(inputs=["2", "", "", "", "", ""], window=(0, 0, 1000, 500),
             cursor=[(10, 20), (510, 270)])
check("Import: von Hand zwei Punkte, daraus die Umrechnung",
      round(_r.imported[0][1]["scale_x"], 3) == 0.5 and _r.imported[0][1]["offset_x"] == 10)
_r = _import(inputs=["", "", "", "", "", ""], cursor=[(0, 0), (1000, 500)])
check("Import: ohne Spielfenster jetzt wird von Hand gesetzt",
      "Spielfenster nicht gefunden" in _r.output and _r.imported[0][1]["scale_x"] == 1.0)
_r = _import(inputs=["2", "", ""])
check("Import: ohne Fenster kann man auch 1:1 wählen", _r.imported[0][1] is None)
_r = _import(inputs=["", "", ""], cursor=[(3, 3), (3, 3)])
check("Import: gleiche Punkte werden abgelehnt", not _r.imported and "identisch" in _r.output)
_r = _import(inputs=["", "cancel"])
check("Import: Abbruch beim Punkt importiert nichts", not _r.imported)
_r = _import(inputs=["3", "", "", ""], window=(0, 0, 10, 10), answers=(False,))
check("Import: ohne Zustimmung nichts", not _r.imported and "Abgebrochen" in _r.output)
_r = _import(choices=(-1,))
check("Import: Abbruch bei der Dateiwahl", not _r.imported)
_r = _import(manifest={})
check("Import: ein unlesbares Bündel wird gesagt", "kein Manifest" in _r.output and not _r.imported)
_r = _import(inputs=["3", "", "", ""], window=(0, 0, 10, 10), ok=False)
check("Import: ein Fehlschlag wird gesagt", "Import fehlgeschlagen: kaputt" in _r.output)
_r = _import(inputs=["3", "", "", ""], window=(0, 0, 10, 10),
             outside=[(f"Punkt {i}", 9999, 9999) for i in range(10)])
check("Import: Klicks ausserhalb des Fensters werden gezeigt (höchstens acht)",
      "10 Klick-Position(en) liegen AUSSERHALB" in _r.output and "2 weitere" in _r.output)
_r = _import(zips=(), inputs=["fehlt.zip"])
check("Import: ohne ZIP wird ein Pfad erfragt, ein fehlender gesagt",
      "Keine ZIP-Dateien" in _r.output and "nicht gefunden: fehlt.zip" in _r.output)
_Path("hier.zip").write_bytes(b"zip")
try:
    _r = _import(choices=(1,), inputs=['"hier.zip"', "3", "", "", ""], window=(0, 0, 10, 10))
finally:
    _Path("hier.zip").unlink()
check("Import: 'Anderen Pfad' nimmt einen Pfad (Anführungszeichen stören nicht)",
      _r.imported and _r.imported[0][0] == "hier.zip")
_r = _import(zips=(), inputs=["cancel"])
check("Import: Abbruch beim Pfad", not _r.imported and "Abgebrochen" in _r.output)


# ============================================================ Kalibrierung
def _calibrate(inputs=(), choices=(0, 0), answers=(False, True), points=2, slots=0,
               cursor=((110, 205),), desktop=None, preview=None):
    calibrated = []

    def calibrate(state, t, **flags):
        calibrated.append((t, flags))
        return {"points": 2, "sequences": 1, "slots": 0}

    run = _Run(inputs=inputs, choices=choices, answers=answers, cursor=cursor, desktop=desktop,
               calibration_preview=lambda state, t: preview or [("Punkt 1", (100, 200), (110, 205))],
               calibrate_inventory=calibrate,
               backup_before_calibration=lambda state: "backups/kal.zip")
    run.state.points = [_CP(id=i + 1, x=100 * (i + 1), y=200 * (i + 1), name=f"P{i + 1}")
                        for i in range(points)]
    run.state.global_slots = {f"S{i}": _SLOT(f"S{i}", (0, 0, 8, 8), (4, 4)) for i in range(slots)}
    run(_IEE.run_calibration)
    run.calibrated = calibrated
    return run


_r = _calibrate(points=0)
check("Kalibrierung: ohne Punkte nichts", "nichts zu kalibrieren" in _r.output)
_r = _calibrate(inputs=["", "", ""])
_t, _flags = _r.calibrated[0]
check("Kalibrierung: ein Punkt neu gesetzt ergibt den Versatz",
      (_t["offset_x"], _t["offset_y"], _t["scale_x"]) == (10, 5, 1.0)
      and ("maus", 100, 200) in _r.calls)
check("Kalibrierung: Vorgabe ist alles ausser Slots, mit Sicherung",
      _flags == {"with_scans": True, "with_sequences": True, "with_slots": False}
      and "kal.zip" in _r.output and "2  Punkte" in _r.output)
_r = _calibrate(inputs=["", "0", ""])
check("Kalibrierung: eine Achse von Hand auf 0", _r.calibrated[0][0]["offset_x"] == 0
      and "von Hand gesetzt" in _r.output)
_r = _calibrate(inputs=["", "abc", "3", ""])
check("Kalibrierung: eine Fehleingabe fragt erneut", _r.calibrated[0][0]["offset_x"] == 3
      and "ganze Zahl" in _r.output)
_r = _calibrate(inputs=["", "cancel"])
check("Kalibrierung: Abbruch beim Nachjustieren", not _r.calibrated and "[ABBRUCH]" in _r.output)
_r = _calibrate(inputs=["", "0", "0"])
check("Kalibrierung: ein Versatz von null tut nichts",
      not _r.calibrated and "nichts zu tun" in _r.output)
_r = _calibrate(inputs=["cancel"])
check("Kalibrierung: Abbruch beim Referenzpunkt", not _r.calibrated)
_r = _calibrate(choices=(-1,))
check("Kalibrierung: Abbruch bei der Punktwahl", not _r.calibrated and "[ABBRUCH]" in _r.output)
_r = _calibrate(inputs=["", "", ""], choices=(0, -1))
check("Kalibrierung: Abbruch beim Umfang", not _r.calibrated)
_r = _calibrate(inputs=["", "", ""], answers=(False, False))
check("Kalibrierung: ohne Zustimmung nichts", not _r.calibrated)
_r = _calibrate(inputs=["", "", ""], choices=(0, 1), slots=3)
check("Kalibrierung: mit Slots wird gewarnt, und sie lassen sich mitnehmen",
      _r.calibrated[0][1]["with_slots"] is True and "Naeherung" in _r.output
      and "nur VERSCHOBEN" in _r.output)
_r = _calibrate(inputs=["", "", ""], choices=(0, 2))
check("Kalibrierung: nur die Punkte",
      _r.calibrated[0][1] == {"with_scans": False, "with_sequences": False, "with_slots": False})
_r = _calibrate(inputs=["", "", ""], desktop=(0, 0, 100, 100))
check("Kalibrierung: Ziele ausserhalb aller Monitore werden gewarnt",
      "ausserhalb aller Monitore" in _r.output)
# Zwei Punkte: der zweite skaliert. P1 (100,200) -> (110,205), P2 (200,400) -> (310,605).
_r = _calibrate(inputs=["", ""], choices=(0, 0, 0), answers=(True, True),
                cursor=[(110, 205), (310, 605)])
_t = _r.calibrated[0][0]
check("Kalibrierung: ein zweiter Punkt bringt die Skalierung",
      (round(_t["scale_x"], 3), round(_t["scale_y"], 3)) == (2.0, 2.0)
      and "Skalierung:" in _r.output and "Versatz nachjustieren" not in _r.output)
_r = _calibrate(inputs=["", "cancel", "", ""], choices=(0, 0, 0), answers=(True, True))
check("Kalibrierung: ohne zweiten Punkt wird nur verschoben",
      "nur verschoben" in _r.output and _r.calibrated[0][0]["scale_x"] == 1.0)
_r = _calibrate(inputs=["", "", ""], points=1, answers=(True,))
check("Kalibrierung: mit nur einem Punkt keine Skalierung",
      _r.calibrated and "Zweiten Referenzpunkt" not in _r.output)


# ============================================================ ein Schalter für die Sequenzen
# `export_bundle` hatte sieben Schalter (Punkte, Sequenzen, Slots, Items, drei
# Scan-Arten), die es intern zu einem ODER zusammenfasste — jeder stand auf
# True, und ein vergessener schaltete den Export wieder ein. Jetzt ist es einer,
# und er trennt wirklich.
import zipfile as _zipfile
from autoclicker.persistence import save_sequence_file as _save_seq, sequence_file as _seq_file
from autoclicker.models import Sequence as _SEQ

_seq_path = _seq_file("Bündeltest")
_seq_path.parent.mkdir(parents=True, exist_ok=True)
with _cl.redirect_stdout(_io.StringIO()):
    _save_seq(_SEQ("Bündeltest"), _seq_path)
    _ok_without, _ = _IE.export_bundle(_ST(), "ohne.zip", (0, 0), (10, 10),
                                       include_sequences=False, include_config=True)
    _ok_with, _ = _IE.export_bundle(_ST(), "mit.zip", (0, 0), (10, 10), include_config=False)
with _zipfile.ZipFile("ohne.zip") as _zf:
    _names_without = _zf.namelist()
with _zipfile.ZipFile("mit.zip") as _zf:
    _names_with = _zf.namelist()
check("export_bundle: ohne Sequenzen steht kein Sequenzordner im Bündel",
      _ok_without and not any(n.startswith("sequences/") for n in _names_without))
check("export_bundle: mit Sequenzen steht er drin",
      _ok_with and any(n.endswith("/sequence.json") for n in _names_with))
