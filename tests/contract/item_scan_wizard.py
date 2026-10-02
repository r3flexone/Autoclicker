"""Der Item-Scan-Assistent (`edit_item_scan`), per Tastenfolge.

Geschrieben, BEVOR `edit_item_scan` (Komplexität 18), `_new_item_from_template`
(16) und `multi_select` (26) zerlegt wurden. Die Mehrfachauswahl selbst hat
ihre Prüfungen in `tests/test_logic.py`; hier stehen der Ablauf darum herum
und die Ränder, die dort fehlten. Gestellt sind Eingabe, Rückfragen,
Screenshot, Kategorie/Priorität/Bestätigungsklick (eigene Tests in
`item_editor`) und das Speichern.
"""
import contextlib as _cl
import io as _io
import os as _os
import tempfile as _tmp

from ._harness import check, section

import autoclicker.editors.item_scan_editor as _ISE
from autoclicker.models import (
    AutoClickerState as _ST, ItemProfile as _IP, ItemScanConfig as _ISC, ItemSlot as _SLOT,
    Sequence as _SEQ,
)
from autoclicker.persistence import activate_sequence, active_templates_dir


class _FakeImage:
    def save(self, path):
        with open(path, "wb") as handle:
            handle.write(b"png")


def _slots():
    return {name: _SLOT(name, (i * 10, 0, i * 10 + 8, 8), (i * 10 + 4, 4))
            for i, name in enumerate(("S1", "S2", "S3"))}


class _Wizard:
    """Ein Durchgang durch `edit_item_scan`."""

    def __init__(self, inputs, confirms=(), existing=None, slots=True, items=True,
                 opencv=True, screenshot=True, save_ok=True, presets=((), ())):
        self.inputs, self.confirms = list(inputs), list(confirms)
        self.existing, self.opencv, self.screenshot, self.save_ok = existing, opencv, screenshot, save_ok
        self.slot_presets, self.item_presets = presets
        self.saved, self.preset_loads = [], []
        self.state = _ST()
        with _cl.redirect_stdout(_io.StringIO()):
            activate_sequence(self.state, _SEQ("Scan", points=[]))
        if slots:
            self.state.global_slots = _slots()
        if items:
            self.state.global_items = {"A": _IP("A", []), "B": _IP("B", [])}
        self.output = ""

    def _input(self, _prompt=""):
        value = self.inputs.pop(0) if self.inputs else "cancel"
        if isinstance(value, BaseException):
            raise value
        return value

    def _confirm(self, *a, **k):
        return self.confirms.pop(0) if self.confirms else k.get("default", False)

    def _save(self, config):
        self.saved.append(config)
        return self.save_ok

    def run(self):
        stubs = [
            (_ISE, "safe_input", self._input),
            (_ISE, "confirm", self._confirm),
            (_ISE, "OPENCV_AVAILABLE", self.opencv),
            (_ISE, "take_screenshot", lambda region: _FakeImage() if self.screenshot else None),
            (_ISE, "select_category", lambda state: "Waffen"),
            (_ISE, "ask_priority", lambda state, category: 2),
            (_ISE, "ask_confirm_click", lambda state, delay, prompt="": (None, 0.5)),
            (_ISE, "save_global_items", lambda state: True),
            (_ISE, "save_item_scan", self._save),
            (_ISE, "list_slot_presets", lambda: list(self.slot_presets)),
            (_ISE, "list_item_presets", lambda: list(self.item_presets)),
            (_ISE, "load_slot_preset", lambda state, name: self.preset_loads.append(("slot", name))),
            (_ISE, "load_item_preset", lambda state, name: self.preset_loads.append(("item", name))),
        ]
        saved = [(m, n, getattr(m, n)) for m, n, _ in stubs]
        for module, name, value in stubs:
            setattr(module, name, value)
        buffer = _io.StringIO()
        try:
            with _cl.redirect_stdout(buffer):
                _ISE.edit_item_scan(self.state, self.existing)
        finally:
            for module, name, value in reversed(saved):
                setattr(module, name, value)
            self.output = buffer.getvalue()
        return self

    def config(self):
        return self.saved[-1] if self.saved else None


def _selection(inputs, entries=None, **kw):
    """multi_select mit einer Tastenfolge — für die Ränder, die test_logic nicht prüft."""
    entries = list(entries if entries is not None else ["A", "B", "C"])
    queue = list(inputs)

    def _input(_prompt=""):
        value = queue.pop(0) if queue else "cancel"
        if isinstance(value, BaseException):
            raise value
        return value

    original = _ISE.safe_input
    _ISE.safe_input = _input
    buffer = _io.StringIO()
    try:
        with _cl.redirect_stdout(buffer):
            result = _ISE.multi_select("> ", entries, [], lambda i, n, on: f"{i} {n} {on}", **kw)
    finally:
        _ISE.safe_input = original
    return result, buffer.getvalue(), entries


_cwd = _os.getcwd()
_os.chdir(_tmp.mkdtemp(prefix="scan_assistent_"))
try:
    # =========================================================================
    section("Mehrfachauswahl: die übrigen Ränder")
    # =========================================================================
    _res, _out, _ = _selection(["1-9", "d"])
    check("ein Bereich ausserhalb wird mit Format gesagt", _res == [] and "Format: <Von>-<Bis>" in _out)
    _res, _out, _ = _selection(["s", "2", "d"])
    check("'s' zeigt, 'd' übernimmt", _res == ["B"] and "0/3 ausgewählt" in _out)
    check("STRG+C bricht ab", _selection([KeyboardInterrupt()])[0] is None)
    check("EOF bricht ab", _selection([EOFError()])[0] is None)
    _res, _out, _entries = _selection(["new 1", "d"], extra_prefix="new", extra_fn=lambda raw: "A")
    check("'new' mit einem vorhandenen Namen: kein zweiter Eintrag, aber gewählt",
          _res == ["A"] and _entries.count("A") == 1)
    _res, _out, _ = _selection(["quatsh", "d"])
    check("Tippfehler bekommt einen Vorschlag", "Unbekannter Befehl" in _out)

    # =========================================================================
    section("Item-Scan-Assistent: neuer Scan")
    # =========================================================================
    _r = _Wizard(["Neu"], slots=False).run()
    check("ohne Slots geht es nicht", "Keine Slots" in _r.output and not _r.saved)
    _r = _Wizard(["Inventar", "1-2", "done", "1", "done", "30"], confirms=[True, True, False]).run()
    _c = _r.config()
    check("Name, Slots, Items und die vier Einstellungen landen im Scan",
          _c is not None and _c.name == "Inventar" and [s.name for s in _c.slots] == ["S1", "S2", "S3"]
          and [s.enabled for s in _c.slots] == [True, True, False] and _c.item_names == ["A"]
          and _c.color_tolerance == 30 and _c.learn_unknown and _c.reverse and not _c.use_catalog)
    check("der Scan gehört der aktiven Sequenz und ist danach der aktive",
          _c.owner_sequence == "Scan" and _r.state.active_item_scan == "Inventar"
          and "Inventar" in _r.state.item_scans)
    check("die Meldung nennt aktive Slots und Items",
          "Scan 'Inventar' gespeichert" in _r.output and "2/3 Slots aktiv, 1 Items" in _r.output)
    _r = _Wizard(["", "1", "done", "1", "done", ""], confirms=[False, False, False]).run()
    check("ohne Namen: Scan_<Zeit>", _r.config().name.startswith("Scan_"))
    check("Enter bei der Toleranz behält den Standard",
          _r.config().color_tolerance == _ISC.color_tolerance)
    _r = _Wizard(["X", "done", "1", "done", "1", "done", ""], confirms=[False, False, False]).run()
    check("ohne Slot wird 'done' abgelehnt", "Mindestens 1 Slot" in _r.output and _r.config() is not None)
    _r = _Wizard(["X", "cancel"]).run()
    check("Abbruch bei den Slots speichert nichts", not _r.saved)
    _r = _Wizard(["X", "1", "done", "cancel"]).run()
    check("Abbruch bei den Items speichert nichts", not _r.saved)
    _r = _Wizard(["X", "1", "done", "done"], confirms=[False]).run()
    check("ohne Items und ohne 'trotzdem': nicht gespeichert",
          not _r.saved and "Scan nicht gespeichert" in _r.output)
    _r = _Wizard(["X", "1", "done", "done", ""], confirms=[True, False, False, False]).run()
    check("ohne Items, aber 'trotzdem': gespeichert", _r.config() is not None and _r.config().items == [])
    _r = _Wizard(["X", "1", "done", "1", "done", "x"], confirms=[False, False, False]).run()
    check("unlesbare Toleranz behält den Wert", "ungültig — behalte" in _r.output)
    _r = _Wizard(["X", "1", "done", "1", "done", "500"], confirms=[False, False, False]).run()
    check("Toleranz wird auf 100 begrenzt", _r.config().color_tolerance == 100)
    _r = _Wizard(["X", "1", "done", "1", "done", ""], confirms=[False, False, False], save_ok=False).run()
    check("scheitert das Speichern, wird es gesagt",
          "Scan nicht gespeichert; Änderungen bleiben im Arbeitsspeicher" in _r.output
          and "gespeichert!" not in _r.output)

    # =========================================================================
    section("Item-Scan-Assistent: bestehender Scan")
    # =========================================================================
    _old = _ISC("Alt", slots=list(_slots().values()), items=[_IP("B", [])],
                color_tolerance=17, learn_unknown=True, reverse=True, use_catalog=True,
                capture_window_title="Spiel", capture_window_index=2,
                capture_window_rect=(1, 2, 3, 4), owner_sequence="Scan")
    _old.slots[2].enabled = False
    _r = _Wizard(["done", "done", ""], existing=_old).run()
    _c = _r.config()
    check("bestehend: Auswahl und Einstellungen sind vorausgewählt",
          _c.name == "Alt" and [s.enabled for s in _c.slots] == [True, True, False]
          and _c.item_names == ["B"] and _c.color_tolerance == 17
          and _c.learn_unknown and _c.reverse and _c.use_catalog)
    check("und das Fenster-Ziel geht nicht verloren",
          (_c.capture_window_title, _c.capture_window_index, _c.capture_window_rect)
          == ("Spiel", 2, (1, 2, 3, 4)))

    # =========================================================================
    section("Item-Scan-Assistent: Presets")
    # =========================================================================
    _r = _Wizard(["9", "1", "Neu", "cancel"], presets=([("P1", None, 3)], ())).run()
    check("ein Slot-Preset wird geladen, eine falsche Nummer gesagt",
          _r.preset_loads == [("slot", "P1")] and "Ungültig! 0-1" in _r.output)
    _r = _Wizard(["x", "", "", "Neu", "cancel"],
                 presets=([("P1", None, 3)], [("I1", None, 2)])).run()
    check("Enter nimmt die aktuellen, Unsinn wird gesagt",
          _r.preset_loads == [] and "Bitte eine Nummer" in _r.output)
    _r = _Wizard(["cancel"], presets=([("P1", None, 3)], ())).run()
    check("Abbruch bei den Presets beendet den Assistenten",
          "Abgebrochen" in _r.output and not _r.saved and "SCHRITT 1" not in _r.output)

    # =========================================================================
    section("Item-Scan-Assistent: Item aus einem Slot anlegen")
    # =========================================================================
    _r = _Wizard(["X", "1", "done", "new 2", "Schwert", "80", "done", ""],
                 confirms=[False, False, False]).run()
    _new = _r.state.global_items.get("Schwert")
    check("new <Slot>: Item mit Vorlage, Kategorie, Priorität und Konfidenz",
          _new is not None and _new.category == "Waffen" and _new.priority == 2
          and abs(_new.min_confidence - 0.8) < 1e-9 and _new.confirm_delay == 0.5
          and (active_templates_dir(_r.state) / _new.template).exists())
    check("und gleich im Scan", "Schwert" in _r.config().item_names)
    _r = _Wizard(["X", "1", "done", "new", "3", "", "", "done", ""], confirms=[False, False, False]).run()
    check("new ohne Nummer fragt nach dem Slot; ohne Namen: Item <n>",
          "Item 1" in _r.state.global_items and "Von welchem Slot" in _r.output)
    _r = _Wizard(["X", "1", "done", "new 9", "new x", "abc", "done", ""], confirms=[False, False, False]).run()
    check("new: falscher Slot und unlesbare Nummer",
          "Ungültiger Slot" in _r.output and "Ungültige Eingabe" in _r.output
          and set(_r.state.global_items) == {"A", "B"})
    _r = _Wizard(["X", "1", "done", "new 1", "done", ""], confirms=[False, False, False], opencv=False).run()
    check("new ohne OpenCV", "OpenCV nicht installiert" in _r.output)
    _r = _Wizard(["X", "1", "done", "new 1", "done", ""], confirms=[False, False, False],
                 screenshot=False).run()
    check("new: Screenshot scheitert", "Screenshot fehlgeschlagen" in _r.output)
    _r = _Wizard(["X", "1", "done", "new 1", "A", "done", ""], confirms=[False, False, False, False]).run()
    check("new mit vergebenem Namen, Überschreiben verneint: nichts angelegt",
          "Abgebrochen" in _r.output and _r.state.global_items["A"].category is None)
    _r = _Wizard(["X", "1", "done", "new 1", "Dolch", "x", "done", ""],
                 confirms=[False, False, False]).run()
    check("new: unlesbare Konfidenz behält den Standard",
          "ungültig — behalte" in _r.output and "Dolch" in _r.state.global_items)
finally:
    _os.chdir(_cwd)
