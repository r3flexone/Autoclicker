"""Konsolen-Editoren für Boss- und Icon-Scans, per Tastenfolge.

Geschrieben, BEVOR die beiden Editoren in Stufen zerlegt wurden:
`edit_boss_scan()` hatte Komplexität 36, `_edit_boss_list()` 24,
`edit_icon_scan()` 22 — und beide trugen dieselbe Aktionswahl, denselben
Klickpunkt, dieselbe Verzögerung und dieselbe Wahl der Erkennung als Kopie.

Gestellt wird alles, was eine Tastatur, einen Bildschirm oder die Platte
braucht. Die Stellvertreter setzt `_stubs()` in JEDEM der drei Module, das den
Namen kennt (Boss-Editor, Icon-Editor, `_detection_capture`): so bleiben die
Tests gültig, wenn der Umbau Code zwischen ihnen verschiebt — gemessen wird
das Verhalten, nicht wo es wohnt.
"""
import contextlib as _cl
import io as _io
from pathlib import Path as _Path

from ._harness import check, section

section("Icon- und Boss-Scan-Editor: Tastenfolgen")

import autoclicker.editors._detection_capture as _DC
import autoclicker.editors.boss_scan_editor as _BO
import autoclicker.editors.icon_scan_editor as _IC
import autoclicker.ocr as _OCR
from autoclicker.models import (
    AutoClickerState as _ST, BossProfile as _BP, BossScanConfig as _BSC,
    IconScanConfig as _ISC, Sequence as _SEQ,
    BOSS_ACTION_CLICK, BOSS_ACTION_KEY, BOSS_ACTION_RESTART, BOSS_ACTION_SCAN,
    BOSS_ACTION_SKIP, BOSS_ACTION_SKIP_CYCLE,
    ICON_ACTION_CLICK, ICON_ACTION_KEY, ICON_ACTION_SKIP,
)

_MODULES = (_BO, _IC, _DC)


class _Shot:
    """Ein Screenshot, der sich merkt, wohin er gespeichert wurde."""

    def __init__(self, region):
        self.region = region
        self.saved = []

    def save(self, path):
        self.saved.append(_Path(path))


class _Run:
    """Eine gestellte Sitzung: Eingaben hinein, Aufrufe und Ausgabe heraus."""

    def __init__(self, inputs=(), choices=(), answers=(), region=(10, 20, 30, 40),
                 markers=((1, 2, 3),), key="space", cursor=((50, 60),), opencv=True,
                 shot=True, saved=True, item_scans=(), ocr=False):
        self.inputs, self.choices = list(inputs), list(choices)
        self.answers, self.cursor = list(answers), list(cursor)
        self.region, self.markers, self.key = region, markers, key
        self.opencv, self.shot, self.saved_ok = opencv, shot, saved
        self.item_scans, self.ocr = list(item_scans), ocr
        self.selects = []          # (Titel, Optionen, Vorauswahl)
        self.saved = []            # gespeicherte Configs
        self.points = []           # (x, y, Name, Quelle)
        self.shots = []
        self.output = ""
        self.state = _ST()
        self.state.active_sequence = _SEQ("farm")

    def _select(self, options, title="", default=0, **_k):
        self.selects.append((title, list(options), default))
        return self.choices.pop(0) if self.choices else -1

    def _point(self, state, x, y, color, name, source=""):
        self.points.append((x, y, name, source))
        return 7

    def _screenshot(self, region):
        if not self.shot:
            return None
        shot = _Shot(region)
        self.shots.append(shot)
        return shot

    def _save(self, config):
        self.saved.append(config)
        return self.saved_ok

    def stubs(self):
        return {
            "safe_input": lambda _p="": self.inputs.pop(0) if self.inputs else "cancel",
            "interactive_select": self._select,
            "confirm": lambda _q, *a, **k: self.answers.pop(0) if self.answers else False,
            "select_scan_region": lambda current=None: self.region,
            "capture_markers": lambda *a, **k: (list(self.markers)
                                                if self.markers is not None else None),
            "prompt_key": lambda *a, **k: self.key,
            "get_cursor_pos": lambda: self.cursor.pop(0) if self.cursor else (0, 0),
            "point_for_position": self._point,
            "take_screenshot": self._screenshot,
            "active_templates_dir": lambda state: _Path("vorlagen"),
            "OPENCV_AVAILABLE": self.opencv,
            "save_icon_scan": self._save,
            "save_boss_scan": self._save,
            "save_global_bosses": lambda state: self.saved.append("bibliothek"),
            "list_available_item_scans": lambda owner: [(n, None) for n in self.item_scans],
            "_test_llm_connection": lambda state: None,
        }

    def __call__(self, fn, *args):
        saved = []
        for module in _MODULES:
            for name, value in self.stubs().items():
                if hasattr(module, name):
                    saved.append((module, name, getattr(module, name)))
                    setattr(module, name, value)
        ocr_old = (_OCR.is_available, _OCR.get_status)
        _OCR.is_available = lambda: self.ocr
        _OCR.get_status = lambda: "OCR fehlt"
        buffer = _io.StringIO()
        try:
            with _cl.redirect_stdout(buffer):
                result = fn(self.state, *args)
        finally:
            for module, name, value in reversed(saved):
                setattr(module, name, value)
            _OCR.is_available, _OCR.get_status = ocr_old
            self.output = buffer.getvalue()
        return result


# =========================================================== Icon-Scan

# Neu, Farb-Marker, Aktion "überspringen": der kürzeste vollständige Weg.
_r = _Run(inputs=["Warnung", "35"], choices=[1, 2])
_r(_IC.edit_icon_scan, None)
_cfg = _r.saved[0] if _r.saved else None
check("Icon: neuer Scan wird gespeichert", isinstance(_cfg, _ISC))
check("Icon: mit Name, Region, Markern und Toleranz",
      (_cfg.name, _cfg.scan_region, _cfg.marker_colors, _cfg.color_tolerance)
      == ("Warnung", (10, 20, 30, 40), [(1, 2, 3)], 35))
check("Icon: ohne Template, Aktion überspringen",
      _cfg.template is None and _cfg.action == ICON_ACTION_SKIP)
check("Icon: gehört der aktiven Sequenz", _cfg.owner_sequence == "farm")
check("Icon: steht auch im Arbeitsspeicher", _r.state.icon_scans.get("Warnung") is _cfg)
check("Icon: und sagt, wie man ihn benutzt", "icon Warnung" in _r.output)

_r = _Run(inputs=["cancel"])
_r(_IC.edit_icon_scan, None)
check("Icon: 'cancel' beim Namen legt nichts an", _r.saved == [] and not _r.state.icon_scans)

_r = _Run(inputs=["", ""], choices=[1, 2])
_r(_IC.edit_icon_scan, None)
check("Icon: ohne Namen gibt es einen erfundenen",
      _r.saved and _r.saved[0].name.startswith("IconScan_"))

_r = _Run(inputs=["X"], region=None)
_r(_IC.edit_icon_scan, None)
check("Icon: keine Region beim Anlegen legt nichts an", _r.saved == [])

_r = _Run(inputs=["X"], choices=[-1])
_r(_IC.edit_icon_scan, None)
check("Icon: Abbruch bei der Erkennung legt nichts an",
      _r.saved == [] and "[ABBRUCH]" in _r.output)

_r = _Run(inputs=["X"], choices=[1], markers=None)
_r(_IC.edit_icon_scan, None)
check("Icon: Abbruch bei den Markern legt nichts an", _r.saved == [])

_r = _Run(inputs=["X", ""], choices=[1, -1])
_r(_IC.edit_icon_scan, None)
check("Icon: Abbruch bei der Aktion legt nichts an", _r.saved == [])

# Template: aus der Region, Konfidenz in Prozent, Marker fallen weg.
_r = _Run(inputs=["Ausruf!", "90"], choices=[0, 2])
_r(_IC.edit_icon_scan, None)
_cfg = _r.saved[0]
check("Icon: das Template kommt aus der Scan-Region",
      _r.shots and _r.shots[0].region == (10, 20, 30, 40))
check("Icon: und liegt als icon_<Name>.png im Vorlagenordner",
      _cfg.template == "icon_ausruf.png"
      and _r.shots[0].saved == [_Path("vorlagen") / "icon_ausruf.png"])
check("Icon: Konfidenz in Prozent", abs(_cfg.min_confidence - 0.9) < 1e-9)
check("Icon: ein Template ersetzt die Marker", _cfg.marker_colors == [])
_r = _Run(inputs=["X", "abc"], choices=[0, 2])
_r(_IC.edit_icon_scan, None)
check("Icon: eine unlesbare Konfidenz lässt den Vorschlag stehen",
      _r.saved[0].min_confidence == _r.state.config.scan_min_confidence)
_r = _Run(inputs=["X"], choices=[0], shot=False)
_r(_IC.edit_icon_scan, None)
check("Icon: ein gescheiterter Screenshot legt nichts an",
      _r.saved == [] and "Screenshot fehlgeschlagen" in _r.output)
_r = _Run(inputs=["X", ""], choices=[0, 2], opencv=False)
_r(_IC.edit_icon_scan, None)
check("Icon: ohne OpenCV gibt es kein Template",
      _r.selects[0][1] == ["Farb-Marker setzen"])

# Toleranz wird eingegrenzt; ein Tippfehler lässt sie stehen.
for _typed, _expected in (("500", 100), ("0", 1), ("abc", _ISC.color_tolerance)):
    _r = _Run(inputs=["X", _typed], choices=[1, 2])
    _r(_IC.edit_icon_scan, None)
    check(f"Icon: Toleranz '{_typed}' wird {_expected}", _r.saved[0].color_tolerance == _expected)

# Bearbeiten: Region bleibt, "beibehalten" ist vorgewählt, die Aktion auch.
_old = _ISC("Alt", scan_region=(1, 1, 9, 9), marker_colors=[(4, 5, 6)],
            color_tolerance=12, action=ICON_ACTION_KEY, action_key="enter")
_r = _Run(inputs=[""], choices=[2, 1], region=None, key="f")
_r(_IC.edit_icon_scan, _old)
_cfg = _r.saved[0]
check("Icon bearbeiten: ohne neue Region bleibt die alte", _cfg.scan_region == (1, 1, 9, 9))
check("Icon bearbeiten: 'beibehalten' ist vorgewählt",
      _r.selects[0][1][-1] == "Bestehende Erkennung beibehalten"
      and _r.selects[0][2] == len(_r.selects[0][1]) - 1)
check("Icon bearbeiten: beibehalten lässt Marker und Toleranz stehen",
      (_cfg.marker_colors, _cfg.color_tolerance) == ([(4, 5, 6)], 12))
check("Icon bearbeiten: die Aktion ist vorgewählt", _r.selects[1][2] == 1)
check("Icon bearbeiten: Taste aus der Abfrage", (_cfg.action, _cfg.action_key) == (ICON_ACTION_KEY, "f"))

# Klick: die Stelle wird ein Punkt, gespeichert wird seine ID; dazu die Verzögerung.
_r = _Run(inputs=["X", "", "", "1.5"], choices=[1, 0], cursor=[(321, 654)])
_r(_IC.edit_icon_scan, None)
_cfg = _r.saved[0]
check("Icon: Klick wird ein Punkt", _r.points == [(321, 654, "Icon-Scan Klick", "Icon-Scan-Editor")])
check("Icon: gespeichert wird die Punkt-ID", (_cfg.action, _cfg.action_point_id) == (ICON_ACTION_CLICK, 7))
check("Icon: mit Verzögerung", _cfg.action_delay == 1.5)
_r = _Run(inputs=["X", "", "", "-2"], choices=[1, 0])
_r(_IC.edit_icon_scan, None)
check("Icon: eine ungültige Verzögerung wird 0 und gesagt",
      _r.saved[0].action_delay == 0 and "verwende 0s" in _r.output)
_r = _Run(inputs=["X", ""], choices=[1, 1], key=None)
_r(_IC.edit_icon_scan, None)
check("Icon: Abbruch bei der Taste legt nichts an", _r.saved == [])

_r = _Run(inputs=["X", ""], choices=[1, 2], saved=False)
_r(_IC.edit_icon_scan, None)
check("Icon: scheitert das Speichern, steht kein 'gespeichert' da",
      "nicht gespeichert" in _r.output and "gespeichert!" not in _r.output)


# =========================================================== Boss-Scan

def _boss_new(*inputs, choices, **kw):
    """Neuer Boss-Scan, ein Boss 'Hydra' per Markern, Aktion überspringen."""
    return _Run(inputs=list(inputs), choices=choices, **kw)


# Name → Region → Boss (add, Name, Marker, Aktion skip) → done → Default
# skip_cycle → Toleranz → LLM aus → (OCR fehlt).
_r = _boss_new("bibliothek", "Drache", "add", "Hydra", "done", "20",
               choices=[1, 3, 1, 0])
_r(_BO.edit_boss_scan, None)
_cfg = _r.saved[0] if _r.saved else None
check("Boss: 'bibliothek' ist reserviert und wird erneut gefragt",
      "reserviert" in _r.output and _cfg is not None and _cfg.name == "Drache")
check("Boss: der Boss steht im Scan",
      [b.name for b in _cfg.bosses] == ["Hydra"]
      and _cfg.bosses[0].marker_colors == [(1, 2, 3)]
      and _cfg.bosses[0].action == BOSS_ACTION_SKIP)
check("Boss: Default-Aktion, Toleranz, Region",
      (_cfg.default_action, _cfg.color_tolerance, _cfg.scan_region)
      == (BOSS_ACTION_SKIP_CYCLE, 20, (10, 20, 30, 40)))
check("Boss: ohne LLM und OCR", (_cfg.use_llm, _cfg.use_ocr) == (False, False))
check("Boss: steht im Arbeitsspeicher und sagt, wie man ihn benutzt",
      _r.state.boss_scans.get("Drache") is _cfg and "boss Drache" in _r.output)
check("Boss: ohne OCR wird es gesagt", "OCR fehlt" in _r.output)

_r = _Run(inputs=["cancel"])
_r(_BO.edit_boss_scan, None)
check("Boss: 'cancel' beim Namen legt nichts an",
      _r.saved == [] and "nicht angelegt" in _r.output)
_r = _boss_new("", "add", "H", "done", "", choices=[1, 3, 0, 0])
_r(_BO.edit_boss_scan, None)
check("Boss: ohne Namen gibt es einen erfundenen",
      _r.saved and _r.saved[0].name.startswith("BossScan_"))
_r = _Run(inputs=["X"], region=None)
_r(_BO.edit_boss_scan, None)
check("Boss: keine Region beim Anlegen legt nichts an und sagt es",
      _r.saved == [] and "[ABBRUCH]" in _r.output)

# Die Boss-Liste.
_r = _boss_new("X", "done", "cancel", choices=[])
_r(_BO.edit_boss_scan, None)
check("Boss-Liste: 'done' ohne Boss wird abgelehnt",
      "Mindestens 1 Boss" in _r.output and _r.saved == [])
_r = _boss_new("X", "done", "", choices=[0, 0])
_r.state.global_bosses = [_BP("Global")]
_r(_BO.edit_boss_scan, None)
check("Boss-Liste: mit globalen Bossen darf sie leer bleiben",
      _r.saved and _r.saved[0].bosses == [] and "globalen" in _r.output)
_r = _boss_new("X", "add", "A", "add", "B", "add", "C", "del 2", "edit 9", "edit x",
               "del 9", "del x", "show", "quatsch", "done", "",
               choices=[1, 3, 1, 3, 1, 3, 0, 0])
_r(_BO.edit_boss_scan, None)
check("Boss-Liste: add, del", [b.name for b in _r.saved[0].bosses] == ["A", "C"])
check("Boss-Liste: ungültige Nummern werden gesagt",
      _r.output.count("Ungültig! 1-2") == 2)
check("Boss-Liste: und Buchstaben nennen das Format",
      "Format: edit <Nr>" in _r.output and "Format: del <Nr>" in _r.output)
check("Boss-Liste: show und unbekannte Befehle",
      "Bosse (2)" in _r.output and "Unbekannter Befehl" in _r.output)
_r = _boss_new("X", "add", "A", "edit 1", "", "done", "",
               choices=[1, 3, 2, 4, 0, 0])
_r(_BO.edit_boss_scan, None)
_b = _r.saved[0].bosses[0]
check("Boss-Liste: edit mit Enter behält den Namen", _b.name == "A")
check("Boss-Liste: edit bietet 'beibehalten' an und übernimmt die neue Aktion",
      _r.selects[2][1][-1] == "Bestehende Erkennung beibehalten"
      and _b.action == BOSS_ACTION_SKIP_CYCLE and _b.marker_colors == [(1, 2, 3)])
check("Boss-Liste: die alte Aktion ist vorgewählt", _r.selects[3][2] == 3)
_r = _boss_new("X", "add", "", "cancel", choices=[])
_r(_BO.edit_boss_scan, None)
check("Boss-Liste: ein Boss ohne Namen wird nicht angelegt, cancel speichert nichts",
      "Kein Name" in _r.output and _r.saved == [])

# Ein Boss mit Template: zwei Ecken, Screenshot, Konfidenz.
_r = _boss_new("X", "add", "Ork", "", "", "75", "done", "",
               choices=[0, 3, 0, 0], cursor=[(5, 6), (55, 66)])
_r(_BO.edit_boss_scan, None)
_b = _r.saved[0].bosses[0]
check("Boss-Template: aus den beiden Ecken",
      _r.shots[0].region == (5, 6, 55, 66) and _b.template == "boss_ork.png")
check("Boss-Template: Konfidenz in Prozent", abs(_b.min_confidence - 0.75) < 1e-9)
_r = _boss_new("X", "add", "Ork", "", "", "cancel", choices=[0], cursor=[(50, 6), (5, 66)])
_r(_BO.edit_boss_scan, None)
check("Boss-Template: verdrehte Ecken werden abgelehnt",
      "Ungültiger Bereich" in _r.output and not _r.shots)
_r = _boss_new("X", "add", "Ork", "", "", "cancel", choices=[0],
               cursor=[(5, 6), (55, 66)], shot=False)
_r(_BO.edit_boss_scan, None)
check("Boss-Template: ein gescheiterter Screenshot legt keinen Boss an",
      "Screenshot fehlgeschlagen" in _r.output and _r.saved == [])

# Boss-Aktionen.
_r = _boss_new("X", "add", "A", "", "done", "", choices=[1, 0, 1, 2, 0, 0],
               item_scans=["Beute", "Inventar"])
_r(_BO.edit_boss_scan, None)
_b = _r.saved[0].bosses[0]
check("Boss-Aktion Item-Scan: Scan und Modus werden gewählt",
      (_b.action, _b.action_scan, _b.action_scan_mode) == (BOSS_ACTION_SCAN, "Inventar", "every"))
_r = _boss_new("X", "add", "A", "cancel", choices=[1, 0])
_r(_BO.edit_boss_scan, None)
check("Boss-Aktion Item-Scan ohne Scans: der Boss entsteht nicht",
      "Keine Item-Scans" in _r.output and _r.saved == [])
_r = _boss_new("X", "add", "A", "", "2", "done", "", choices=[1, 1, 0, 0], cursor=[(9, 8)])
_r(_BO.edit_boss_scan, None)
_b = _r.saved[0].bosses[0]
check("Boss-Aktion Klick: ein Punkt, seine ID, die Verzögerung",
      (_b.action, _b.action_point_id, _b.action_delay) == (BOSS_ACTION_CLICK, 7, 2.0)
      and _r.points == [(9, 8, "Boss-Klick", "Boss-Scan-Editor")])
_r = _boss_new("X", "add", "A", "", "done", "", choices=[1, 2, 0, 0], key="f5")
_r(_BO.edit_boss_scan, None)
check("Boss-Aktion Taste", (_r.saved[0].bosses[0].action, _r.saved[0].bosses[0].action_key)
      == (BOSS_ACTION_KEY, "f5"))

# Default-Aktion "Item-Scan".
_r = _boss_new("X", "add", "A", "done", "", choices=[1, 3, 3, 1, 0], item_scans=["Beute", "Rest"])
_r(_BO.edit_boss_scan, None)
check("Boss-Default Item-Scan: der Scan wird gewählt",
      (_r.saved[0].default_action, _r.saved[0].default_scan) == (BOSS_ACTION_SCAN, "Rest"))
_r = _boss_new("X", "add", "A", "done", "", choices=[1, 3, 3, 0])
_r(_BO.edit_boss_scan, None)
check("Boss-Default Item-Scan ohne Scans fällt auf skip zurück",
      _r.saved[0].default_action == BOSS_ACTION_SKIP and "Keine Item-Scans" in _r.output)
_r = _boss_new("X", "add", "A", "done", "", choices=[1, 3, -1, 0])
_r(_BO.edit_boss_scan, None)
check("Boss-Default: ohne Auswahl bleibt skip", _r.saved[0].default_action == BOSS_ACTION_SKIP)

# Toleranz.
for _typed, _expected in (("500", 100), ("0", 1), ("abc", _BSC.color_tolerance)):
    _r = _boss_new("X", "add", "A", "done", _typed, choices=[1, 3, 0, 0])
    _r(_BO.edit_boss_scan, None)
    check(f"Boss: Toleranz '{_typed}' wird {_expected}", _r.saved[0].color_tolerance == _expected)

# LLM und OCR.
for _choice, _answers, _expected in ((1, [], (True, True)), (2, [], (True, False)),
                                     (3, [True, False], (True, False)),
                                     (3, [True, True], (True, True)),
                                     (3, [False], (False, True))):
    _r = _boss_new("X", "add", "A", "done", "", choices=[1, 3, 0, _choice], answers=_answers)
    _r(_BO.edit_boss_scan, None)
    check(f"Boss-LLM: Wahl {_choice} {_answers} ergibt {_expected}",
          (_r.saved[0].use_llm, _r.saved[0].llm_fallback) == _expected)
for _choice, _expected in ((0, (False, True)), (1, (True, True)), (2, (True, False))):
    _r = _boss_new("X", "add", "A", "done", "", choices=[1, 3, 0, 0, _choice], ocr=True)
    _r(_BO.edit_boss_scan, None)
    check(f"Boss-OCR: Wahl {_choice} ergibt {_expected}",
          (_r.saved[0].use_ocr, _r.saved[0].ocr_fallback) == _expected)

# Bearbeiten: alles Bisherige ist vorgewählt.
_old = _BSC("Alt", scan_region=(1, 1, 9, 9), bosses=[_BP("A", action=BOSS_ACTION_SKIP)],
            color_tolerance=11, default_action=BOSS_ACTION_RESTART, use_llm=True,
            llm_fallback=False, use_ocr=True, ocr_fallback=False)
_r = _Run(inputs=["done", ""], choices=[-1, -1, -1], region=None, ocr=True)
_r(_BO.edit_boss_scan, _old)
_cfg = _r.saved[0]
check("Boss bearbeiten: Region, Bosse, Toleranz bleiben",
      (_cfg.scan_region, [b.name for b in _cfg.bosses], _cfg.color_tolerance)
      == ((1, 1, 9, 9), ["A"], 11))
check("Boss bearbeiten: Default, LLM und OCR sind vorgewählt",
      [s[2] for s in _r.selects] == [2, 2, 2])
check("Boss bearbeiten: und bleiben ohne Auswahl, wie sie waren",
      (_cfg.default_action, _cfg.use_llm, _cfg.llm_fallback, _cfg.use_ocr, _cfg.ocr_fallback)
      == (BOSS_ACTION_RESTART, True, False, True, False))
check("Boss bearbeiten: die Liste des alten Scans wird nicht verändert",
      _cfg.bosses is not _old.bosses)

_r = _Run(inputs=["X"], saved=False)
_r.inputs = ["X", "add", "A", "done", ""]
_r.choices = [1, 3, 0, 0]
_r(_BO.edit_boss_scan, None)
check("Boss: scheitert das Speichern, steht kein 'gespeichert' da",
      "nicht gespeichert" in _r.output and "gespeichert!" not in _r.output)

# Die Boss-Bibliothek.
_r = _Run(inputs=["add", "Golem", "done"], choices=[1, 3])
_r.state.global_bosses = [_BP("Alt")]
_r(_BO.edit_global_bosses)
check("Bibliothek: 'done' übernimmt und speichert",
      [b.name for b in _r.state.global_bosses] == ["Alt", "Golem"] and _r.saved == ["bibliothek"])
_r = _Run(inputs=["del 1", "cancel"])
_r.state.global_bosses = [_BP("Alt")]
_r(_BO.edit_global_bosses)
check("Bibliothek: 'cancel' verwirft",
      [b.name for b in _r.state.global_bosses] == ["Alt"] and _r.saved == []
      and "verworfen" in _r.output)
