"""Die Unter-Editoren des Slot-Editors, per Tastenfolge.

Geschrieben, BEVOR sie in Stufen zerlegt wurden: `slot_repair` (22),
`create_slot` (17), `slot_auto_detect` (13), `edit_slot` (12). Gestellt werden
Tastatur, Maus, Bildschirm, Platte und die Erkennung; geprüft wird, welcher
Slot herauskommt — und bei `repair`, dass erst nach Vorschau und Zustimmung
geschrieben wird.
"""
import contextlib as _cl
import io as _io
from pathlib import Path as _Path

from ._harness import check, section

section("Slot-Editor: neuer Slot, bearbeiten, automatisch finden, reparieren")

import autoclicker.editors.slot_editor as _SE
import autoclicker.editors.item_editor.autoscan as _AS
import autoclicker.editors.import_export_editor as _IEE
import autoclicker.import_export as _IE
from autoclicker.models import AutoClickerState as _ST, ItemSlot as _SLOT


class _Image:
    """Ein Screenshot: feste Grösse, eine Farbe, merkt sich Speicherorte."""

    def __init__(self, size=(4, 2), color=(10, 20, 30)):
        self.size, self.color, self.saved = size, color, []

    def load(self):
        return _Pixels(self.color)

    def save(self, path):
        self.saved.append(_Path(path))


class _Pixels:
    def __init__(self, color):
        self.color = color

    def __getitem__(self, _xy):
        return self.color


class _Run:
    def __init__(self, inputs=(), choices=(), answers=(), region=(100, 200, 160, 260),
                 shot=True, cursor=((5, 6),), pixel=(1, 2, 3), detected=(), opencv=True,
                 saves=True):
        self.inputs, self.choices, self.answers = list(inputs), list(choices), list(answers)
        self.region, self.cursor, self.pixel = region, list(cursor), pixel
        self.detected, self.opencv, self.saves = list(detected), opencv, saves
        self.image = _Image() if shot else None
        self.state = _ST()
        self.calls = []
        self.output = ""

    def stubs(self):
        return {
            "safe_input": lambda _p="": self.inputs.pop(0) if self.inputs else "cancel",
            "confirm": lambda _q, *a, **k: self.answers.pop(0) if self.answers else False,
            "interactive_select": lambda *a, **k: self.choices.pop(0) if self.choices else 5,
            "select_region": lambda: self.region,
            "take_screenshot": lambda region: self.image,
            "get_cursor_pos": lambda: self.cursor.pop(0) if self.cursor else (0, 0),
            "get_pixel_color": lambda x, y: self.pixel,
            "active_sequence_dir": lambda state: _Path("seq"),
            "detect_slots_in_image": lambda img, color, tol, verbose=False: (
                list(self.detected), _BGR()),
            "OPENCV_AVAILABLE": self.opencv,
            "NUMPY_AVAILABLE": self.opencv,
            "save_global_slots": lambda state: self.calls.append("gespeichert") or self.saves,
            "time": _Clock(),
        }

    def __call__(self, fn, *args):
        stubs = self.stubs()
        old = {name: getattr(_SE, name) for name in stubs}
        foreign = [
            (_AS, "item_autoscan_from_image",
             lambda state, slots, img, offset: self.calls.append(("lernen", len(slots), offset))),
            (_IE, "backup_before_calibration",
             lambda state: self.calls.append("sicherung") or "backups/x.zip"),
            (_IE, "calibration_preview", lambda state, t: [("Punkt 1", (1, 1), (11, 21))]),
            (_IE, "calibrate_inventory",
             lambda state, t, **kw: self.calls.append(("kalibriert", t, kw)) or {"Punkte": 1}),
            (_IEE, "_outside_all_monitors", lambda targets: 0),
        ]
        old_foreign = [(module, name, getattr(module, name)) for module, name, _v in foreign]
        for name, value in stubs.items():
            setattr(_SE, name, value)
        for module, name, value in foreign:
            setattr(module, name, value)
        buffer = _io.StringIO()
        try:
            with _cl.redirect_stdout(buffer):
                result = fn(self.state, *args)
        finally:
            for name, value in old.items():
                setattr(_SE, name, value)
            for module, name, value in old_foreign:
                setattr(module, name, value)
            self.output = buffer.getvalue()
        return result


class _Clock:
    def sleep(self, _seconds):
        pass

    def strftime(self, _fmt):
        return "20261001_120000"


class _BGR:
    """Steht für das BGR-Bild der Erkennung; die Vorschau-Grafik zeichnet darauf."""

    def copy(self):
        return self


def _slot(name, region=(0, 0, 10, 10), color=(1, 2, 3)):
    return _SLOT(name, region, ((region[0] + region[2]) // 2, (region[1] + region[3]) // 2),
                 slot_color=color)


# ============================================================ create_slot
_r = _Run(inputs=["", "", ""], cursor=[(7, 8), (130, 230)])
_new = _r(_SE.create_slot)
check("neuer Slot: der erste freie Name wird vorgeschlagen", _new.name == "Slot 1")
check("neuer Slot: Region aus der Auswahl, Farbe unter der Maus, Klick an der Maus",
      (_new.scan_region, _new.slot_color, _new.click_pos)
      == ((100, 200, 160, 260), (1, 2, 3), (130, 230)))
check("neuer Slot: die Farben der Region werden gezeigt", "Top" in _r.output)
check("neuer Slot: der Screenshot liegt unter bilder/",
      _r.image.saved == [_Path("seq/bilder/slot_1.png")])
_r = _Run(inputs=["Beutel", "skip", "center"])
_new = _r(_SE.create_slot)
check("neuer Slot: getippter Name, 'skip' ohne Farbe, 'center' = Mitte",
      (_new.name, _new.slot_color, _new.click_pos) == ("Beutel", None, (130, 230)))
_r = _Run(inputs=["cancel"])
check("neuer Slot: 'cancel' beim Namen", _r(_SE.create_slot) is None)
_r = _Run(inputs=["A"], answers=[False])
_r.state.global_slots = {"A": _slot("A")}
check("neuer Slot: ein vergebener Name ohne Zustimmung bricht ab", _r(_SE.create_slot) is None)
_r = _Run(inputs=["A", "", ""], answers=[True])
_r.state.global_slots = {"A": _slot("A")}
check("neuer Slot: mit Zustimmung geht es weiter", _r(_SE.create_slot).name == "A")
_r = _Run(inputs=[""], region=None)
check("neuer Slot: ohne Region kein Slot", _r(_SE.create_slot) is None)
_r = _Run(inputs=["", "cancel"])
check("neuer Slot: 'cancel' bei der Farbe", _r(_SE.create_slot) is None)
_r = _Run(inputs=["", "", "center"], pixel=None)
_new = _r(_SE.create_slot)
check("neuer Slot: unlesbare Farbe wird übersprungen und gesagt",
      _new.slot_color is None and "überspringe" in _r.output)
_r = _Run(inputs=["", "skip", "center"], shot=False)
_new = _r(_SE.create_slot)
check("neuer Slot: ohne Screenshot trotzdem ein Slot", _new is not None and "Top" not in _r.output)

# ============================================================ edit_slot
_old = _SLOT("Alt", (0, 0, 10, 10), (5, 5), slot_color=(9, 9, 9), id=4)
_r = _Run(inputs=["Neu", "", ""], choices=[0, 1, 2, 3, 4, 5], cursor=[(77, 88), (1, 1)],
          pixel=(4, 4, 4))
_new = _r(_SE.edit_slot, _old)
check("Slot bearbeiten: jedes Feld lässt sich ändern",
      (_new.name, _new.scan_region, _new.click_pos, _new.slot_color, _new.enabled)
      == ("Neu", (100, 200, 160, 260), (77, 88), (4, 4, 4), False))
check("Slot bearbeiten: die ID bleibt", _new.id == 4)
_r = _Run(inputs=[""], choices=[0, 1, 5], region=None)
_new = _r(_SE.edit_slot, _old)
check("Slot bearbeiten: Enter und eine abgebrochene Region ändern nichts",
      (_new.name, _new.scan_region) == ("Alt", (0, 0, 10, 10)))
_r = _Run(inputs=[""], choices=[3, 5], pixel=None)
check("Slot bearbeiten: unlesbare Farbe lässt die alte stehen",
      _r(_SE.edit_slot, _old).slot_color == (9, 9, 9))
_r = _Run(choices=[4, 4, 5])
check("Slot bearbeiten: zweimal umschalten ist wieder an", _r(_SE.edit_slot, _old).enabled is True)
check("Slot bearbeiten: der alte Slot bleibt unangetastet",
      (_old.name, _old.enabled) == ("Alt", True))

# ============================================================ slot_auto_detect
_r = _Run(opencv=False)
check("automatisch: ohne OpenCV nichts", _r(_SE.slot_auto_detect) is False
      and "OpenCV" in _r.output)
_r = _Run(region=None)
check("automatisch: ohne Region nichts", _r(_SE.slot_auto_detect) is False)
_r = _Run(shot=False)
check("automatisch: ohne Screenshot nichts", _r(_SE.slot_auto_detect) is False)
_r = _Run(inputs=[""], pixel=None)
check("automatisch: ohne Farbe nichts", _r(_SE.slot_auto_detect) is False)
_r = _Run(inputs=[""], detected=[])
check("automatisch: nichts erkannt wird gesagt",
      _r(_SE.slot_auto_detect) is False and "Keine Slots erkannt" in _r.output)

try:
    import cv2 as _cv2  # noqa: F401
    import numpy as _np
except ImportError:
    _np = None
if _np is None:
    print("  ÜBERSPRUNGEN: Slot-Erkennung mit Vorschau braucht OpenCV und NumPy")
else:
    class _BGRArray(_BGR):
        def copy(self):
            return _np.zeros((100, 200, 3), dtype=_np.uint8)

    _r = _Run(inputs=[""], detected=[(0, 0, 20, 20), (30, 0, 20, 20)], answers=[True])
    _r.state.config.scan_slot_inset = 2
    _r.state.global_slots = {"Slot 1": _slot("Slot 1")}
    _orig_detect = _Run.stubs

    def _stubs_with_array(self):
        stubs = _orig_detect(self)
        stubs["detect_slots_in_image"] = lambda img, c, t, verbose=False: (
            list(self.detected), _BGRArray())
        return stubs

    _Run.stubs = _stubs_with_array
    try:
        _ok = _r(_SE.slot_auto_detect)
    finally:
        _Run.stubs = _orig_detect
    check("automatisch: erkannte Slots kommen mit freien Namen dazu",
          _ok is True and list(_r.state.global_slots) == ["Slot 1", "Slot 2", "Slot 3"])
    check("automatisch: Region um den Einzug verkleinert, Klick in der Mitte",
          (_r.state.global_slots["Slot 2"].scan_region,
           _r.state.global_slots["Slot 2"].click_pos) == ((102, 202, 118, 218), (110, 210)))
    check("automatisch: die Farbe unter der Maus wird die Slot-Farbe",
          _r.state.global_slots["Slot 3"].slot_color == (1, 2, 3))
    check("automatisch: auf Wunsch werden Items aus demselben Bild gelernt",
          ("lernen", 2, (100, 200)) in _r.calls)
    check("automatisch: Screenshot und Vorschau landen unter bilder/",
          _r.image.saved == [_Path("seq/bilder/screenshot_20261001_120000.png")]
          and _Path("seq/bilder/preview_20261001_120000.png").exists())

# ============================================================ slot_repair
def _repair_run(old_regions, detected, answers=(), **kw):
    run = _Run(inputs=[""], detected=detected, answers=list(answers), **kw)
    run.state.config.scan_slot_inset = 0
    run.state.global_slots = {f"S{i}": _slot(f"S{i}", reg) for i, reg in enumerate(old_regions)}
    return run


_r = _Run(opencv=False)
check("repair: ohne OpenCV nichts", _r(_SE.slot_repair) is False)
_r = _Run()
check("repair: ohne Slots nichts", _r(_SE.slot_repair) is False
      and "nichts zu reparieren" in _r.output)
_r = _repair_run([(100, 200, 110, 210)], [], region=None)
check("repair: ohne Region nichts", _r(_SE.slot_repair) is False)
# Gespeichert bei (100,200); erkannt im Bereich ab (100,200) bei (5,5) → Versatz +5/+5.
_old = [(100, 200, 110, 210), (120, 200, 130, 210)]
_found = [(5, 5, 10, 10), (25, 5, 10, 10)]
_r = _repair_run(_old, _found, answers=[False])
check("repair: ohne Zustimmung wird nichts geändert",
      _r(_SE.slot_repair) is False and _r.state.global_slots["S0"].scan_region == _old[0]
      and "VORSCHAU" in _r.output and "+5 X, +5 Y" in _r.output)
_r = _repair_run(_old, _found, answers=[True, False])
check("repair: mit Zustimmung neu vermessen, gesichert und gespeichert",
      _r(_SE.slot_repair) is True
      and _r.state.global_slots["S0"].scan_region == (105, 205, 115, 215)
      and _r.state.global_slots["S1"].click_pos == (130, 210)
      and _r.calls[:2] == ["sicherung", "gespeichert"])
_r = _repair_run(_old, _found, answers=[True, True, True])
_r(_SE.slot_repair)
_cal = [c for c in _r.calls if isinstance(c, tuple) and c[0] == "kalibriert"]
check("repair: der Versatz geht auf Wunsch an den Rest — ohne die Slots",
      _cal and _cal[0][2] == {"with_scans": True, "with_sequences": True, "with_slots": False})
_r = _repair_run(_old, _found, answers=[True, True, False])
check("repair: ohne zweite Zustimmung nur die Slots",
      _r(_SE.slot_repair) is True and not any(isinstance(c, tuple) for c in _r.calls)
      and "Nur die Slots" in _r.output)
_r = _repair_run(_old, [(5, 5, 10, 10)])
check("repair: eine andere Anzahl wird nicht geraten",
      _r(_SE.slot_repair) is False and "Nichts geaendert" in _r.output)
_r = _repair_run(_old, [(0, 0, 10, 10), (20, 0, 10, 10)])
check("repair: ohne Versatz ist nichts zu tun",
      _r(_SE.slot_repair) is False and "schon richtig" in _r.output)
_r = _repair_run(_old, _found, answers=[True, False], saves=False)
check("repair: scheitert das Speichern, wird es gesagt",
      _r(_SE.slot_repair) is True and "NICHT gespeichert" in _r.output)
_r = _Run(inputs=[""], detected=_found, answers=[False], pixel=(7, 7, 7))
_r.state.config.scan_slot_inset = 0
_r.state.global_slots = {f"S{i}": _slot(f"S{i}", reg, color=None) for i, reg in enumerate(_old)}
_r(_SE.slot_repair)
check("repair: ohne gespeicherte Farbe wird einmal gepickt",
      "bitte einmalig picken" in _r.output and "VORSCHAU" in _r.output)
_r = _Run(inputs=[""], detected=_found, pixel=None)
_r.state.global_slots = {f"S{i}": _slot(f"S{i}", reg, color=None) for i, reg in enumerate(_old)}
check("repair: unlesbare Farbe bricht ab", _r(_SE.slot_repair) is False)
