"""Das Paket `editors/item_editor/`, per Tastenfolge.

Geschrieben, BEVOR die neun Funktionen über der Komplexitätsgrenze zerlegt
wurden (`_learn_single` 26, `_dispatch_command` 23, `edit_item` 21,
`_run_autoscan` 18, `_capture_template_for_item` 16, `run_global_item_editor`
15, `llm_name_items` 13, `collect_marker_colors` 12, `create_item` 12).

Die Stellvertreter setzt `_stubs()` in JEDEM Modul des Pakets, das den Namen
kennt — dazu `_item_fields` (die echten `ask_priority`/`ask_confirm_click`
laufen mit und lesen dieselbe Tastenfolge) und `utils` (`edit_item` holt
`interactive_select` beim Aufruf). So darf der Umbau Code verschieben, ohne
dass die Tests es merken.
"""
import contextlib as _cl
import io as _io
from pathlib import Path as _Path

from ._harness import check, section

section("Item-Editor: Hauptschleife, Anlegen, Bearbeiten, Lernen, Autoscan, Vorlagen")

import autoclicker.editors._item_fields as _IF
import autoclicker.editors.item_editor.autoscan as _AU
import autoclicker.editors.item_editor.commands as _CO
import autoclicker.editors.item_editor.editor as _ED
import autoclicker.editors.item_editor.items as _IT
import autoclicker.editors.item_editor.learn as _LE
import autoclicker.editors.item_editor.markers as _MK
import autoclicker.imaging as _IMG
import autoclicker.llm_vision as _LLM
import autoclicker.utils as _UT
from autoclicker.models import (
    AutoClickerState as _ST, ItemProfile as _IP, ItemScanConfig as _ISC,
    ItemSlot as _SLOT, Sequence as _SEQ,
)

_MODULES = (_ED, _IT, _LE, _AU, _CO, _MK, _IF, _UT, _IMG, _LLM)
_RUNS = [0]


class _Img:
    """Ein Screenshot: Grösse, eine Farbe; `save` schreibt wirklich eine Datei."""

    def __init__(self, size=(4, 2), pixels=None):
        self.size = size
        self.pixels = pixels or {}
        self.saved = []

    def load(self):
        return self

    def __getitem__(self, xy):
        return self.pixels.get(xy, (10, 20, 30))

    def save(self, path):
        path = _Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"png")
        self.saved.append(path)


class _Run:
    def __init__(self, inputs=(), choices=(), answers=(), region=(0, 0, 4, 2), shot=True,
                 opencv=True, pillow=True, categories=(), saves=(), **stubs):
        self.inputs, self.choices = list(inputs), list(choices)
        self.answers, self.saves = list(answers), list(saves)
        self.region, self.opencv, self.pillow = region, opencv, pillow
        self.image = _Img() if shot is True else (shot or None)
        self.categories = list(categories)
        self.extra = stubs
        self.calls = []
        self.output = ""
        self.state = _ST()
        self.state.active_sequence = _SEQ("farm")
        # Jeder Lauf hat seinen eigenen Vorlagenordner: `free_template_file`
        # weicht sonst auf `_2` aus, weil ein früherer Fall die Datei anlegte.
        _RUNS[0] += 1
        self.tpl = _Path(f"tpl{_RUNS[0]}")

    def _save_items(self, state):
        self.calls.append(("gespeichert", list(state.global_items)))
        return self.saves.pop(0) if self.saves else True

    def stubs(self):
        stubs = {
            "safe_input": lambda _p="": self.inputs.pop(0) if self.inputs else "cancel",
            "confirm": lambda _q, *a, **k: self.answers.pop(0) if self.answers else False,
            "interactive_select": lambda *a, **k: self.choices.pop(0) if self.choices else 5,
            "select_region": lambda: self.region,
            "take_screenshot": lambda region: self.image,
            "active_templates_dir": lambda state: self.tpl,
            "OPENCV_AVAILABLE": self.opencv,
            "PILLOW_AVAILABLE": self.pillow,
            "get_existing_categories": lambda state: list(self.categories),
            "save_global_items": self._save_items,
            "save_item_preset": lambda state, name: self.calls.append(("save", name)),
            "load_item_preset": lambda state, name: self.calls.append(("load", name)),
            "delete_item_preset": lambda name: self.calls.append(("preset del", name)),
            "list_item_presets": lambda: [],
        }
        stubs.update(self.extra)
        return stubs

    def __call__(self, fn, *args, **kwargs):
        saved = []
        for module in _MODULES:
            for name, value in self.stubs().items():
                if hasattr(module, name):
                    saved.append((module, name, getattr(module, name)))
                    setattr(module, name, value)
        buffer = _io.StringIO()
        try:
            with _cl.redirect_stdout(buffer):
                result = fn(self.state, *args, **kwargs)
        finally:
            for module, name, value in reversed(saved):
                setattr(module, name, value)
            self.output = buffer.getvalue()
        return result


def _item(name, **kw):
    return _IP(name=name, **kw)


def _slots(count):
    return [_SLOT(f"S{i}", (i * 10, 0, i * 10 + 4, 2), (i * 10 + 2, 1), slot_color=(9, 9, 9))
            for i in range(count)]


# ============================================================ Hauptschleife

def _editor(inputs, items=("A", "B"), **kw):
    run = _Run(inputs=inputs, **kw)
    config = _ISC("Inv", owner_sequence="farm", items=[_item(n) for n in items])
    run.state.item_scans["Inv"] = config
    run.state.active_item_scan = "Inv"
    run.state.global_items = {it.name: it for it in config.items}
    run(_ED.run_global_item_editor)
    return run


_r = _Run(inputs=["done"], pillow=False)
_r(_ED.run_global_item_editor)
check("Hauptschleife: ohne Pillow öffnet der Editor nicht", "Pillow nicht installiert" in _r.output)
_r = _Run(inputs=["done"])
_r(_ED.run_global_item_editor)
check("Hauptschleife: ohne gewählten Scan wird es gesagt", "nicht vorbereitet" in _r.output)
_r = _editor(["done"])
check("Hauptschleife: 'done' speichert und beendet",
      _r.calls == [("gespeichert", ["A", "B"])] and "beendet" in _r.output)
_r = _editor(["done", "done"], saves=[False, True])
check("Hauptschleife: scheitert das Speichern, bleibt sie offen",
      "bleibt offen" in _r.output and len(_r.calls) == 2)
_r = _editor(["del 1", "cancel"])
check("Hauptschleife: 'cancel' stellt die Items vom Start wieder her",
      list(_r.state.global_items) == ["A", "B"] and "[ABBRUCH]" in _r.output)
_r = _editor(["", "quatsch", "save", "done"])
check("Hauptschleife: leer fragt weiter, Unbekanntes wird gesagt",
      _r.output.count("Unbekannter Befehl") == 2)
_r = _editor(["help", "??", "?", "help full", "done"])
check("Hauptschleife: 'help' kurz, '?'/'??'/'help full' vollständig",
      _r.output.count("Kurzübersicht (?") == 2 and _r.output.count("preset del <N>") == 3)

_routes = []
_r = _editor(["autoscan nocolor", "learn 3", "rename 2", "autoname", "templates", "template 1",
              "Save Mein Set", "LOAD Altes", "preset del Weg", "done"],
             item_autoscan_command=lambda st, cmd: _routes.append(("autoscan", cmd)),
             item_learn_command=lambda st, cmd: _routes.append(("learn", cmd)),
             handle_rename_command=lambda st, cmd: _routes.append(("rename", cmd)),
             handle_autoname_command=lambda st: _routes.append(("autoname",)),
             handle_templates_command=lambda st: _routes.append(("templates",)),
             handle_template_command=lambda st, cmd: _routes.append(("template", cmd)))
check("Hauptschleife: jeder Befehl landet bei seinem Handler",
      _routes == [("autoscan", "autoscan nocolor"), ("learn", "learn 3"), ("rename", "rename 2"),
                  ("autoname",), ("templates",), ("template", "template 1")])
check("Hauptschleife: Preset-Namen behalten ihre Schreibweise",
      [c for c in _r.calls if c[0] in ("save", "load", "preset del")]
      == [("save", "Mein Set"), ("load", "Altes"), ("preset del", "Weg")])

_r = _editor(["add", "add", "done"], create_item=lambda st: _item("Neu"))
check("Hauptschleife: add übernimmt das neue Item", list(_r.state.global_items)[-1] == "Neu")
_r = _editor(["add", "done"], create_item=lambda st: None)
check("Hauptschleife: ein abgebrochenes add ändert nichts", list(_r.state.global_items) == ["A", "B"])
_r = _editor(["edit 2", "done"], edit_item=lambda st, it: _item("B2"))
check("Hauptschleife: edit mit neuem Namen ersetzt den Eintrag",
      list(_r.state.global_items) == ["A", "B2"])
_r = _editor(["edit 2", "done"], answers=[False], edit_item=lambda st, it: _item("A"))
check("Hauptschleife: edit auf einen vergebenen Namen fragt — ohne Zustimmung bleibt alles",
      list(_r.state.global_items) == ["A", "B"] and "unverändert" in _r.output)
_r = _editor(["edit 2", "done"], answers=[True], edit_item=lambda st, it: _item("A", priority=7))
check("Hauptschleife: mit Zustimmung wird überschrieben",
      list(_r.state.global_items) == ["A"] and _r.state.global_items["A"].priority == 7)
_r = _editor(["edit 9", "edit x", "done"])
check("Hauptschleife: edit ausserhalb bzw. mit Buchstaben",
      "Ungültig! Verfügbar: 1-2" in _r.output and "Format: edit <Nr>" in _r.output)
_r = _editor(["del 1", "del 9", "del x", "done"])
check("Hauptschleife: del", list(_r.state.global_items) == ["B"]
      and "Ungültig! Verfügbar: 1-1" in _r.output and "Format: del <Nr>" in _r.output)
_r = _editor(["del all", "done"], answers=[True])
check("Hauptschleife: del all nach Rückfrage", _r.state.global_items == {})
_r = _editor(["del all", "done"], answers=[False])
check("Hauptschleife: del all ohne Zustimmung", len(_r.state.global_items) == 2)
_r = _editor(["del all", "done"], items=())
check("Hauptschleife: del all ohne Items", "Keine Items vorhanden" in _r.output)
_r = _editor(["show", "done"])
check("Hauptschleife: show", "Items (2)" in _r.output)


def _raise_os(*_a):
    raise OSError("Platte voll")


_r = _editor(["templates", "done"], handle_templates_command=_raise_os)
check("Hauptschleife: ein Dateifehler wird gesagt, der Editor bleibt offen",
      "Platte voll" in _r.output and "beendet" in _r.output)


def _interrupt(*_a):
    raise KeyboardInterrupt


_r = _editor(["del 1", "templates"], handle_templates_command=_interrupt)
check("Hauptschleife: Strg+C verwirft", list(_r.state.global_items) == ["A", "B"]
      and "[ABBRUCH]" in _r.output)

# ============================================================ create_item
_r = _Run(inputs=["", "", "90", "", "", ""])
_new = _r(_IT.create_item)
check("anlegen: erster freier Name, Template aus der Region, Konfidenz",
      (_new.name, _new.template, round(_new.min_confidence, 2)) == ("Item 1", "item_1.png", 0.9)
      and _r.image.saved == [_r.tpl / "item_1.png"])
check("anlegen: ohne Kategorie, Priorität 1, ohne Bestätigung",
      (_new.category, _new.priority, _new.confirm_point_id) == (None, 1, None))
_r = _Run(inputs=["Bogen", "skip", "2", "4", ""], categories=["Helme", "Waffen"])
_new = _r(_IT.create_item)
check("anlegen: 'skip' ohne Template, Kategorie per Nummer, Priorität",
      (_new.name, _new.template, _new.category, _new.priority) == ("Bogen", None, "Waffen", 4))
_r = _Run(inputs=["X", "", "Neu", "", ""], region=None)
_new = _r(_IT.create_item)
check("anlegen: ohne Region kein Template, neue Kategorie per Name",
      _new.template is None and _new.category == "Neu")
_r = _Run(inputs=["X", "", "", ""], opencv=False)
_new = _r(_IT.create_item)
check("anlegen: ohne OpenCV kein Template und gesagt",
      _new.template is None and "OpenCV nicht installiert" in _r.output)
_r = _Run(inputs=["cancel"])
check("anlegen: 'cancel' beim Namen", _r(_IT.create_item) is None)
_r = _Run(inputs=["A"], answers=[False])
_r.state.global_items = {"A": _item("A")}
check("anlegen: vergebener Name ohne Zustimmung", _r(_IT.create_item) is None)
_r = _Run(inputs=["A", "skip", "", "", ""], answers=[True])
_r.state.global_items = {"A": _item("A")}
check("anlegen: mit Zustimmung wird überschrieben",
      _r(_IT.create_item).name == "A" and "überschrieben" in _r.output)
_r = _Run(inputs=["X", "skip", "7", "", ""], categories=["Helme"])
check("anlegen: eine Nummer ausserhalb ist ein Kategoriename", _r(_IT.create_item).category == "7")

# ============================================================ edit_item
_old = _item("Alt", category="Helme", priority=3, template="alt.png", marker_colors=[(1, 1, 1)],
             template_variants=["alt_62x57.png"], enabled=False, min_confidence=0.8)
_r = _Run(inputs=["Neu", "Waffen", "5", "70", ""], choices=[0, 1, 2, 3, 4, 5])
_new = _r(_IT.edit_item, _old)
check("bearbeiten: Name, Kategorie, Priorität, Template, Bestätigung",
      (_new.name, _new.category, _new.priority, _new.template, round(_new.min_confidence, 2))
      == ("Neu", "Waffen", 5, "neu.png", 0.7))
check("bearbeiten: Marker, Varianten und Schalter bleiben",
      (_new.marker_colors, _new.template_variants, _new.enabled)
      == ([(1, 1, 1)], ["alt_62x57.png"], False))
check("bearbeiten: die Varianten-Liste ist eine Kopie",
      _new.template_variants is not _old.template_variants)
_r = _Run(inputs=["B", "x", "0"], choices=[0, 2, 2, 5])
_r.state.global_items = {"Alt": _old, "B": _item("B")}
_new = _r(_IT.edit_item, _old)
check("bearbeiten: ein vergebener Name wird abgelehnt",
      _new.name == "Alt" and "bereits vergeben" in _r.output)
check("bearbeiten: ungültige Priorität gesagt, 0 wird 1",
      "Ungültige Eingabe" in _r.output and _new.priority == 1)
_r = _Run(choices=[3, 5], opencv=False)
check("bearbeiten: Template ohne OpenCV",
      _r(_IT.edit_item, _old).template == "alt.png" and "OpenCV nicht installiert" in _r.output)
_r = _Run(choices=[3, 5], region=None)
check("bearbeiten: Template ohne Region bleibt", _r(_IT.edit_item, _old).template == "alt.png")

# ============================================================ learn
def _learn(cmd, inputs=(), slots=3, markers=((1, 2, 3),), **kw):
    run = _Run(inputs=inputs, collect_marker_colors=lambda region, color: list(markers), **kw)
    run.state.global_slots = {s.name: s for s in _slots(slots)}
    run(_LE.item_learn_command, cmd)
    return run


_r = _learn("learn 1", slots=0)
check("lernen: ohne Slots wird es gesagt", "Keine Slots vorhanden" in _r.output)
_r = _learn("learn 2", inputs=["", "", "", ""])
_new = _r.state.global_items.get("Item 1")
check("lernen: ein Item aus Slot 2 mit Markern und Template",
      _new is not None and _new.marker_colors == [(1, 2, 3)] and _new.template == "item_1.png")
check("lernen: die vorläufige Vorlage ist umbenannt",
      (_r.tpl / "item_1.png").exists() and not (_r.tpl / "_learn_temp_2.png").exists())
_r = _learn("learn", inputs=["2", "Kiste", "", "", ""])
check("lernen: ohne Nummer wird nach dem Slot gefragt", "Kiste" in _r.state.global_items)
_r = _learn("learn", inputs=["x"])
check("lernen: eine falsche Slot-Eingabe wird gesagt", "Ungültige Eingabe" in _r.output)
_r = _learn("learn 9")
check("lernen: ein Slot ausserhalb wird gesagt", "Ungültiger Slot" in _r.output)
_r = _learn("learn 1", markers=())
check("lernen: ohne Farben kein Item", "Keine Farben" in _r.output and not _r.state.global_items)
for _label, _seq in (("Name", ["cancel"]), ("Priorität", ["", "", "cancel"]),
                     ("Bestätigung", ["", "", "", "cancel"])):
    _r = _learn("learn 1", inputs=_seq)
    check(f"lernen: Abbruch bei {_label} räumt die vorläufige Vorlage weg",
          not _r.state.global_items and not (_r.tpl / "_learn_temp_1.png").exists())
_r = _Run(inputs=["A"], answers=[False], collect_marker_colors=lambda r, c: [(1, 2, 3)])
_r.state.global_slots = {s.name: s for s in _slots(1)}
_r.state.global_items = {"A": _item("A")}
_r(_LE.item_learn_command, "learn 1")
check("lernen: vergebener Name ohne Zustimmung räumt auf",
      not (_r.tpl / "_learn_temp_1.png").exists() and "Abgebrochen" in _r.output)
_r = _learn("learn 1-2", inputs=["Helme", ""])
check("lernen in Serie: je Slot ein Item mit Template und steigender Priorität",
      [(n, it.priority, it.template, it.category) for n, it in _r.state.global_items.items()]
      == [("S0 Item", 1, "s0_item.png", "Helme"), ("S1 Item", 2, "s1_item.png", "Helme")])
_r = _learn("learn 2-3 simple", inputs=["", ""])
check("lernen in Serie: 'simple' ohne Template, Priorität ab 1",
      [(n, it.priority, it.template) for n, it in _r.state.global_items.items()]
      == [("S1 Item", 1, None), ("S2 Item", 2, None)])
_r = _learn("learn 2-9")
check("lernen in Serie: ein Bereich ausserhalb", "Ungültiger Bereich" in _r.output)
_r = _learn("learn a-b")
check("lernen in Serie: Buchstaben nennen das Format", "Format: learn <von>-<bis>" in _r.output)

# ============================================================ autoscan
def _autoscan(cmd="autoscan", inputs=("", "", "", ""), answers=(True,), slots=3,
              shots=None, match=None, compatible=True, items=(), **kw):
    found = []

    def find(img, existing, conf, template_root=None):
        found.append(template_root)
        return match(img) if match else None

    pictures = list(shots) if shots is not None else None
    run = _Run(inputs=list(inputs), answers=list(answers),
               _find_matching_existing_item=find,
               _item_has_compatible_template=lambda item, img, root=None: compatible,
               _collect_markers_silent=lambda img, color: [(7, 7, 7)], **kw)
    if pictures is not None:
        run.image = None
        run.extra["take_screenshot"] = lambda region: pictures.pop(0) if pictures else None
    run.state.global_slots = {s.name: s for s in _slots(slots)}
    run.state.global_items = {it.name: it for it in items}
    run(_AU.item_autoscan_command, cmd)
    run.found_roots = found
    return run


_r = _autoscan(slots=0)
check("autoscan: ohne Slots wird es gesagt", "Keine Slots" in _r.output)
_r = _autoscan(opencv=False)
check("autoscan: ohne OpenCV wird es gesagt", "OpenCV nicht installiert" in _r.output)
_r = _autoscan(answers=(False,))
check("autoscan: ohne Zustimmung nichts", not _r.state.global_items and "Abgebrochen" in _r.output)
_r = _autoscan(inputs=("Erze", "2", "", "80"))
check("autoscan: je Slot ein Item, alle P1 bei Wahl 2, mit Markern",
      [(n, it.priority, it.category, it.marker_colors, round(it.min_confidence, 2))
       for n, it in _r.state.global_items.items()]
      == [(f"S{i} Item", 1, "Erze", [(7, 7, 7)], 0.8) for i in range(3)])
check("autoscan: gespeichert wird einmal am Ende", [c[0] for c in _r.calls] == ["gespeichert"])
_r = _autoscan(cmd="autoscan nocolor")
check("autoscan nocolor: ohne Marker, Priorität nach Slot",
      [(it.priority, it.marker_colors) for it in _r.state.global_items.values()]
      == [(1, []), (2, []), (3, [])])
_r = _autoscan(items=[_item("S0 Item")], slots=1)
check("autoscan: ein vergebener Name bekommt einen Zähler",
      list(_r.state.global_items) == ["S0 Item", "S0 Item 2"])
_old_item = _item("Alt", template="alt.png")
_r = _autoscan(shots=[None, _Img(), _Img((6, 6))], items=[_old_item],
               match=lambda img: "Alt", compatible=True)
check("autoscan: Fehlschlag und Duplikat werden gezählt, nichts neu",
      list(_r.state.global_items) == ["Alt"]
      and "0 neu erstellt, 2 Duplikat(e) übersprungen, 1 fehlgeschlagen" in _r.output
      and _r.calls == [])
_r = _autoscan(slots=1, items=[_item("Alt", template="alt.png")],
               match=lambda img: "Alt", compatible=False)
check("autoscan: ein Treffer in anderer Grösse wird eine Variante",
      _r.state.global_items["Alt"].template_variants == ["alt_4x2.png"]
      and "1 Grössenvariante(n) ergänzt" in _r.output and _r.calls)
_r = _autoscan(slots=2)
check("autoscan: die Duplikatprüfung sieht den Vorlagenordner der Sequenz",
      _r.found_roots == [_r.tpl, _r.tpl])
_named = []
_r = _Run(inputs=["", "", "", ""], answers=[True, True],
          _find_matching_existing_item=lambda *a, **k: None,
          _collect_markers_silent=lambda img, color: [],
          llm_name_items=lambda st, targets: _named.append(targets) or 1)
_r.state.config.llm_enabled = True
_r.state.global_slots = {s.name: s for s in _slots(1)}
_r(_AU.item_autoscan_command, "autoscan")
check("autoscan: mit LLM werden die neuen Items zum Benennen angeboten",
      _named == [[("S0 Item", "s0_item.png")]] and len(_r.calls) == 2)
_r = _Run(inputs=["", "", "", ""], answers=[True],
          _find_matching_existing_item=lambda *a, **k: None,
          _collect_markers_silent=lambda img, color: [],
          crop_screen_region=lambda img, region, origin: _Img())
_r(_AU.item_autoscan_from_image, _slots(2), object(), (100, 200))
check("autoscan aus einem Bild: geschnitten statt neu aufgenommen",
      list(_r.state.global_items) == ["S0 Item", "S1 Item"])

# ============================================================ Vorlagen
def _template(cmd, inputs, item=None, slots=2, sizes=None, **kw):
    item = item or _item("Bogen")
    run = _Run(inputs=list(inputs),
               template_size=lambda name, root=None: (sizes or {}).get(name), **kw)
    run.state.global_slots = {s.name: s for s in _slots(slots)}
    run.state.global_items = {"Bogen": item}
    run(_CO.handle_template_command, cmd)
    run.item = item
    return run


_r = _template("template x", [])
check("Vorlage: Buchstaben nennen das Format", "Format: template <Nr>" in _r.output)
_r = _template("template 5", [])
check("Vorlage: ein Item ausserhalb wird gesagt", "Ungültiges Item" in _r.output)
_r = _template("template 1", [""])
check("Vorlage: Enter ändert nichts", _r.item.template is None)
_r = _template("template 1", ["remove"],
               item=_item("Bogen", template="a.png", template_variants=["b.png"]))
check("Vorlage: remove entfernt alle", (_r.item.template, _r.item.template_variants) == (None, []))
_r = _template("template 1", ["bogen", "85%"])
check("Vorlage: ein Dateiname bekommt .png, Konfidenz mit Prozentzeichen",
      (_r.item.template, round(_r.item.min_confidence, 2)) == ("bogen.png", 0.85))
_r = _template("template 1", ["capture", "2", ""])
check("Vorlage aufnehmen: aus Slot 2, erste Vorlage heisst wie das Item",
      _r.item.template == "bogen.png" and _r.image.saved == [_r.tpl / "bogen.png"])
_r = _template("template 1", ["capture", "0", ""])
check("Vorlage aufnehmen: 0 = freie Region", _r.item.template == "bogen.png")
_r = _template("template 1", ["capture", "9"])
check("Vorlage aufnehmen: ein Slot ausserhalb wird gesagt",
      "Ungültiger Slot" in _r.output and _r.item.template is None)
_r = _template("template 1", ["capture", "x", "50"])
check("Vorlage aufnehmen: Buchstaben = freie Region",
      _r.item.template == "bogen.png" and round(_r.item.min_confidence, 2) == 0.5)
_r = _template("template 1", ["capture", ""], slots=0)
check("Vorlage aufnehmen: ohne Slots direkt die Region", _r.item.template == "bogen.png")
_r = _template("template 1", ["capture", "1", ""],
               item=_item("Bogen", template="bogen.png"), sizes={"bogen.png": (4, 2)})
check("Vorlage aufnehmen: dieselbe Grösse ersetzt die Datei",
      (_r.item.template, _r.item.template_variants) == ("bogen.png", []))
_r = _template("template 1", ["capture", "1", ""],
               item=_item("Bogen", template="bogen.png"), sizes={"bogen.png": (9, 9)})
check("Vorlage aufnehmen: eine andere Grösse wird eine Variante",
      _r.item.template_variants == ["bogen_4x2.png"])
_r = _template("template 1", ["capture", "1"], shot=None)
check("Vorlage aufnehmen: ein gescheiterter Screenshot wird gesagt",
      "Screenshot fehlgeschlagen" in _r.output)

# ============================================================ LLM-Benennung
try:
    from PIL import Image as _PILImage
except ImportError:
    _PILImage = None
if _PILImage is None:
    print("  ÜBERSPRUNGEN: LLM-Benennung braucht Pillow zum Öffnen der Vorlagen")
else:
    # Erkannt wird die Vorlage an ihrer Grösse: das Bild, das beim LLM ankommt,
    # ist eine Kopie ohne Dateinamen (s. u., warum).
    _answers = {(4, 4): "Godlike Bow", (5, 5): "Godlike Bow", (6, 6): None}

    def _suggest(img, **kw):
        return _answers[img.size]

    _r = _Run(suggest_item_name=_suggest)
    _r.tpl.mkdir(exist_ok=True)
    for _name, _size in (("a.png", (4, 4)), ("b.png", (5, 5)), ("c.png", (6, 6))):
        _PILImage.new("RGB", _size).save(_r.tpl / _name)
    (_r.tpl / "kaputt.png").write_bytes(b"kein bild")
    # **Die Vorlage darf nicht offen bleiben.** `Image.open()` liest träge und
    # hält die Datei, bis das Bild geschlossen wird — unter Windows scheiterte
    # das Umbenennen danach mit WinError 32, und `autoname` benannte dort kein
    # einziges Item mit Vorlage um. Unter Linux fällt es nicht auf; deshalb
    # steht der Fall hier und läuft in der Windows-Matrix der CI mit.
    _r.state.global_items = {n: _item(n, template=t) for n, t in
                             (("Auto 1", "a.png"), ("Auto 2", "b.png"), ("Auto 3", "c.png"),
                              ("Auto 4", "fehlt.png"), ("Auto 5", "kaputt.png"))}
    _count = _r(_CO.llm_name_items, [(n, it.template) for n, it in _r.state.global_items.items()])
    check("LLM-Benennung: benannt, der zweite gleiche Name bekommt einen Zähler",
          _count == 2 and list(_r.state.global_items)[-2:] == ["Godlike Bow", "Godlike Bow 2"])
    check("LLM-Benennung: ohne Vorschlag, fehlende und kaputte Vorlage bleiben",
          {"Auto 3", "Auto 4", "Auto 5"} <= set(_r.state.global_items)
          and "kein Name vom LLM" in _r.output and "Template fehlt" in _r.output
          and "nicht lesbar" in _r.output)

_r = _Run()
_r(_CO.handle_autoname_command)
check("autoname: ohne LLM wird es gesagt", "nicht aktiviert" in _r.output)
_r = _Run()
_r.state.config.llm_enabled = True
_r(_CO.handle_autoname_command)
check("autoname: ohne Auto-Items wird es gesagt", "Keine auto-gelernten" in _r.output)

# ============================================================ Marker sammeln
_r = _Run(region=None)
check("Marker: ohne Region keine", _r(lambda st: _MK.collect_marker_colors()) == [])
_r = _Run(shot=None)
check("Marker: ohne Screenshot keine", _r(lambda st: _MK.collect_marker_colors((0, 0, 4, 2))) == [])
_pixels = {(0, 0): (200, 0, 0), (1, 0): (200, 0, 0), (2, 0): (0, 200, 0), (3, 0): (0, 0, 200),
           (0, 1): (12, 22, 32), (1, 1): (11, 21, 31), (2, 1): (10, 20, 30), (3, 1): (200, 0, 0)}
_r = _Run(shot=_Img((4, 2), _pixels))
_r.state.config.scan_marker_count = 2
_old_count = _MK.CONFIG.scan_marker_count
_MK.CONFIG.scan_marker_count = 2
try:
    _colors = _r(lambda st: _MK.collect_marker_colors((0, 0, 4, 2), (10, 20, 30)))
finally:
    _MK.CONFIG.scan_marker_count = _old_count
check("Marker: der Hintergrund fällt weg, die häufigsten bleiben",
      _colors[0] == (200, 0, 0) and len(_colors) == 2 and "ausgeschlossen" in _r.output)
