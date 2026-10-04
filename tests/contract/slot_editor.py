"""Konsolen-Slot-Editor (`run_global_slot_editor`), per Tastenfolge.

Geschrieben, BEVOR der Editor in Stufen zerlegt wurde: 203 Zeilen und
Komplexität 44 — nach dem Loop-Phasen-Editor die verzweigteste Funktion des
Repos, und in keinem Test. Er ist transaktional (Snapshot am Start, `cancel`
stellt ihn wieder her), und genau das ist der Teil, der beim Zerlegen am
leichtesten verloren geht: `repair` schreibt sofort und zieht den Snapshot
nach, damit `cancel` keine halbe Reparatur zurückdreht.

Gestellt werden Eingabe, Rückfrage, Speichern und die Unter-Editoren
(`create_slot`, `edit_slot`, `slot_auto_detect`, `slot_repair`, Presets).
"""
import contextlib as _cl
import io as _io

from ._harness import check, section

section("Slot-Editor: Befehle per Tastenfolge")

import autoclicker.editors.slot_editor as _SE
from autoclicker.models import AutoClickerState as _ST, ItemSlot as _SLOT


def _slot(name, x=0):
    return _SLOT(name, (x, 0, x + 8, 8), (x + 4, 4))


class _Run:
    def __init__(self, inputs, slots=(), answers=(), saves=(), created=None,
                 edited=None, repaired=False, pillow=True, interrupt_after=None):
        self.inputs, self.answers = list(inputs), list(answers)
        self.saves = list(saves)            # Rückgabewerte von save_global_slots, der Reihe nach
        self.created, self.edited, self.repaired = created, edited, repaired
        self.pillow, self.interrupt_after = pillow, interrupt_after
        self.saved_states = []              # Namen der Slots bei jedem Speichern
        self.calls = []
        self.state = _ST()
        self.state.global_slots = {s.name: s for s in slots}
        self.output = ""

    def _input(self, _prompt=""):
        if self.interrupt_after is not None and not self.inputs:
            raise KeyboardInterrupt
        return self.inputs.pop(0) if self.inputs else "cancel"

    def _save(self, state):
        self.saved_states.append(list(state.global_slots))
        return self.saves.pop(0) if self.saves else True

    def _repair(self, state):
        self.calls.append("repair")
        if self.repaired:
            state.global_slots["Repariert"] = _slot("Repariert", 90)
        return self.repaired

    def run(self):
        stubs = {
            "safe_input": self._input,
            "confirm": lambda _q, *a, **k: self.answers.pop(0) if self.answers else False,
            "save_global_slots": self._save,
            "PILLOW_AVAILABLE": self.pillow,
            "list_slot_presets": lambda: [],
            "create_slot": lambda state: self.created,
            "edit_slot": lambda state, slot: (self.edited(slot) if callable(self.edited)
                                              else self.edited),
            "slot_auto_detect": lambda state: self.calls.append("auto"),
            "slot_repair": self._repair,
            "save_slot_preset": lambda state, name: self.calls.append(("save", name)),
            "load_slot_preset": lambda state, name: self.calls.append(("load", name)),
            "delete_slot_preset": lambda name: self.calls.append(("preset del", name)),
        }
        old = {name: getattr(_SE, name) for name in stubs}
        for name, value in stubs.items():
            setattr(_SE, name, value)
        buffer = _io.StringIO()
        try:
            with _cl.redirect_stdout(buffer):
                _SE.run_global_slot_editor(self.state)
        finally:
            for name, value in old.items():
                setattr(_SE, name, value)
            self.output = buffer.getvalue()
        return self

    @property
    def names(self):
        return list(self.state.global_slots)


# --- Ohne Pillow ---
_r = _Run(["done"], pillow=False).run()
check("ohne Pillow öffnet der Editor nicht", "Pillow nicht installiert" in _r.output
      and _r.saved_states == [])

# --- done / cancel / Strg+C ---
_r = _Run(["done"], slots=[_slot("A")]).run()
check("'done' speichert und beendet", _r.saved_states == [["A"]] and "beendet" in _r.output)
_r = _Run(["DONE"], slots=[_slot("A")]).run()
check("Grossschreibung stört nicht", _r.saved_states == [["A"]])
_r = _Run(["done", "done"], slots=[_slot("A")], saves=[False, True]).run()
check("scheitert das Speichern, bleibt der Editor offen",
      "bleibt offen" in _r.output and len(_r.saved_states) == 2)
_r = _Run(["add", "cancel"], slots=[_slot("A")], created=_slot("B", 20)).run()
check("'cancel' stellt den Stand vom Start wieder her und schreibt ihn",
      _r.names == ["A"] and _r.saved_states == [["A"]] and "[ABBRUCH]" in _r.output)
_r = _Run(["add"], slots=[_slot("A")], created=_slot("B", 20), interrupt_after=0).run()
check("Strg+C verwirft ebenso", _r.names == ["A"] and _r.saved_states == [["A"]]
      and "[ABBRUCH]" in _r.output)
_r = _Run(["", "quatsch", "save", "done"]).run()
check("leere Eingabe fragt weiter, Unbekanntes wird gesagt",
      _r.output.count("Unbekannter Befehl") == 2)

# --- add / edit ---
_r = _Run(["add", "done"], slots=[_slot("A")], created=_slot("B", 20)).run()
check("add übernimmt den neuen Slot", _r.names == ["A", "B"])
_r = _Run(["add", "done"], slots=[_slot("A")], created=None).run()
check("ein abgebrochenes add ändert nichts", _r.names == ["A"])
_r = _Run(["edit 2", "done"], slots=[_slot("A"), _slot("B", 20)],
          edited=lambda s: _SLOT("B2", s.scan_region, s.click_pos)).run()
check("edit mit neuem Namen ersetzt den alten Eintrag", _r.names == ["A", "B2"])
_r = _Run(["edit 1", "done"], slots=[_slot("A")],
          edited=lambda s: _SLOT("A", (1, 1, 9, 9), s.click_pos)).run()
check("edit mit gleichem Namen ändert den Slot",
      _r.state.global_slots["A"].scan_region == (1, 1, 9, 9))
_r = _Run(["edit 1", "done"], slots=[_slot("A")], edited=None).run()
check("ein abgebrochenes edit ändert nichts", _r.state.global_slots["A"].scan_region == (0, 0, 8, 8))
_r = _Run(["edit 3", "edit x", "done"], slots=[_slot("A")]).run()
check("edit ausserhalb bzw. mit Buchstaben wird gesagt",
      "Ungültig! Verfügbar: 1-1" in _r.output and "Format: edit <Nr>" in _r.output)

# --- del ---
_r = _Run(["del 1", "done"], slots=[_slot("A"), _slot("B", 20)]).run()
check("del <Nr> löscht genau diesen Slot (ohne Rückfrage)", _r.names == ["B"])
_r = _Run(["del 5", "del x", "done"], slots=[_slot("A")]).run()
check("del ausserhalb bzw. mit Buchstaben wird gesagt",
      "Ungültig! Verfügbar: 1-1" in _r.output and "Format: del <Nr>" in _r.output
      and _r.names == ["A"])
_r = _Run(["del all", "done"], slots=[_slot("A"), _slot("B", 20)], answers=[True]).run()
check("del all leert nach Rückfrage", _r.names == [] and "2 Slot(s) gelöscht" in _r.output)
_r = _Run(["del all", "done"], slots=[_slot("A")], answers=[False]).run()
check("ohne Zustimmung bleibt alles", _r.names == ["A"])
_r = _Run(["del all", "done"]).run()
check("del all ohne Slots sagt es", "Keine Slots vorhanden" in _r.output)

# --- show / help ---
_r = _Run(["show", "done"], slots=[_slot("Erster")]).run()
check("show nennt die Slots", "Slots (1)" in _r.output and "Erster" in _r.output)
_r = _Run(["s", "done"]).run()
check("ohne Slots sagt show das", "(Keine Slots)" in _r.output)
_r = _Run(["?", "done"]).run()
check("? zeigt die Befehle noch einmal", _r.output.count("preset del <N>") == 2)

# --- auto / repair ---
_r = _Run(["auto", "done"]).run()
check("auto ruft die automatische Erkennung", _r.calls == ["auto"])
_r = _Run(["repair", "cancel"], slots=[_slot("A")], repaired=True).run()
check("nach einem repair nimmt cancel die Reparatur NICHT zurück",
      _r.names == ["A", "Repariert"] and "cancel nimmt das nicht" in _r.output)
_r = _Run(["fix", "add", "cancel"], slots=[_slot("A")], repaired=True,
          created=_slot("Neu", 40)).run()
check("aber alles danach", _r.names == ["A", "Repariert"])
_r = _Run(["reparieren", "cancel"], slots=[_slot("A")], repaired=False).run()
check("ein repair ohne Ergebnis lässt den Snapshot stehen",
      _r.calls == ["repair"] and _r.names == ["A"])

# --- Presets: der Name behält seine Schreibweise ---
_r = _Run(["save Mein Raster", "LOAD Altes", "preset del Weg Damit", "done"]).run()
check("save/load/preset del geben den Namen wie getippt weiter",
      _r.calls == [("save", "Mein Raster"), ("load", "Altes"), ("preset del", "Weg Damit")])
