"""Der Schritt-Editor einer Phase (`sequence_editor/steps.py`), per Tastenfolge.

Geschrieben, BEVOR sechs Methoden von `_PhaseEditor` zerlegt wurden — der
Verteiler `_dispatch` (33), `_handle_edit_menu` (17), `_handle_link` (17),
`_parse_point_options` (15), `_handle_wait` (12), `_handle_show_detail` (12).
Gefahren wird jeder Befehl über `edit_phase()`, also durch den echten
Verteiler: ein Befehl, der dort im falschen Zweig landet, fällt hier auf.
Gestellt werden Tastatur, Maus, Farbabgriff, Speichern und der echte Lauf
(`execute_step`).
"""
import contextlib as _cl
import io as _io

from ._harness import check, section

section("Schritt-Editor einer Phase: Befehle per Tastenfolge")

import autoclicker.editors.sequence_editor.helpers as _HE
import autoclicker.editors.sequence_editor.steps as _PS
import autoclicker.runtime.steps as _RS
import autoclicker.winapi as _WIN
from autoclicker.models import (
    AutoClickerState as _ST, ClickPoint as _CP, SequenceStep as _STEP, WaitCondition as _WC,
)

_MODULES = (_PS, _HE, _RS, _WIN)


class _Run:
    def __init__(self, inputs, steps=None, answers=(), cursor=((50, 60),), pixel=(7, 8, (1, 2, 3)),
                 region=(0, 0, 40, 30), pillow=True, executed=None):
        self.inputs, self.answers, self.cursor = list(inputs), list(answers), list(cursor)
        self.pixel, self.region, self.pillow = pixel, region, pillow
        self.steps = steps if steps is not None else []
        self.executed = executed if executed is not None else []
        self.saved = 0
        self.output = ""
        self.state = _ST()
        self.state.points = [_CP(100, 200, "Knopf", 1, color=(10, 20, 30)),
                             _CP(300, 400, "Ohne Farbe", 2)]

    def _save_points(self, state):
        self.saved += 1
        return True

    def stubs(self):
        return {
            "safe_input": lambda _p="": self.inputs.pop(0) if self.inputs else "done",
            "confirm": lambda _q, *a, **k: self.answers.pop(0) if self.answers else False,
            "get_cursor_pos": lambda: self.cursor.pop(0) if self.cursor else (0, 0),
            "capture_pixel_color": lambda: self.pixel,
            "select_region": lambda: self.region,
            "save_points": self._save_points,
            "PILLOW_AVAILABLE": self.pillow,
            "execute_step": lambda state, step, n, total, phase: self.executed.append(step) or True,
            "get_screen_pixel": lambda x, y: (99, 99, 99),
        }

    def run(self):
        saved = []
        for module in _MODULES:
            for name, value in self.stubs().items():
                if hasattr(module, name):
                    saved.append((module, name, getattr(module, name)))
                    setattr(module, name, value)
        buffer = _io.StringIO()
        try:
            with _cl.redirect_stdout(buffer):
                self.result = _PS.edit_phase(self.state, self.steps, "LOOP")
        finally:
            for module, name, value in reversed(saved):
                setattr(module, name, value)
            self.output = buffer.getvalue()
        return self


def _one(*inputs, **kw):
    """Ein Befehl, dann done — gibt (Lauf, letzter Schritt) zurück."""
    run = _Run(list(inputs) + ["done"], **kw).run()
    return run, (run.steps[-1] if run.steps else None)


# ============================================================ Ende und Hilfe
_r = _Run(["done"]).run()
check("done gibt die Schritte zurück", _r.result is _r.steps)
_r = _Run(["cancel"]).run()
check("cancel gibt None", _r.result is None and "[ABBRUCH]" in _r.output)
_r = _Run(["", "quatsch", "done"]).run()
check("leer fragt weiter, Unbekanntes wird gesagt", "Unbekannter Befehl" in _r.output)
_r = _Run(["help", "?", "??", "help full", "done"]).run()
check("help kurz, ?/??/help full ausführlich",
      _r.output.count("Kurzübersicht") == 2 and _r.output.count("NACHPRUEFUNG") == 3)

# ============================================================ Punkt-Klick (Standardbefehl)
_r, _s = _one("1")
check("Punkt-Klick: Punkt-ID, keine Wartezeit, Farbe des Punkts",
      (_s.point_id, _s.delay_before, _s.recorded_color, _s.wait_condition) == (1, 0, (10, 20, 30), None))
_r, _s = _one("2")
check("Punkt-Klick: ohne Punktfarbe wird live gelesen", _s.recorded_color == (99, 99, 99))
_r, _s = _one("1 5")
check("Punkt-Klick: mit Wartezeit", _s.delay_before == 5)
_r, _s = _one("1 2-4")
check("Punkt-Klick: mit Zufallsbereich", (_s.delay_before, _s.delay_max) == (2, 4))
_r, _s = _one("1 color")
check("Punkt-Klick: color wartet auf die Punktfarbe am Punkt",
      _s.wait_condition and (_s.wait_condition.point_id, _s.wait_condition.color,
                             _s.wait_condition.until_gone) == (1, (10, 20, 30), False))
_r, _s = _one("1 colorgone")
check("Punkt-Klick: colorgone", _s.wait_condition.until_gone is True)
_r, _s = _one("1 checkcolor")
check("Punkt-Klick: checkcolor prüft nur einmal",
      _s.wait_condition.check_only is True and _s.wait_condition.until_gone is False)
_r, _s = _one("1 5 color")
check("Punkt-Klick: Zeit und dann Farbe", (_s.delay_before, _s.wait_condition.until_gone) == (5, False))
_r, _s = _one("1 5 checkgone")
check("Punkt-Klick: Zeit und einmalige Prüfung auf WEG",
      _s.wait_condition.check_only and _s.wait_condition.until_gone)
_r, _s = _one("2 color")
check("Punkt-Klick: ohne Punktfarbe wird an der Maus abgegriffen, als eigener Punkt",
      _s.wait_condition.pixel == (7, 8) and _s.wait_condition.point_id not in (None, 2))
_r, _s = _one("2 color", pixel=(None, None, None))
check("Punkt-Klick: keine Farbe lesbar legt keinen Schritt an",
      _s is None and "Keine Farbe lesbar" in _r.output)
_r, _s = _one("2 5 checkcolor", pixel=(None, None, None))
check("Punkt-Klick: auch nicht mit Zeit davor", _s is None)
_r, _s = _one("1 x")
check("Punkt-Klick: eine unlesbare Zeit wird gesagt", _s is None and "Format: <Nr> <Zeit>" in _r.output)
_r, _s = _one("1 5-x")
check("Punkt-Klick: ein unlesbarer Bereich wird gesagt", _s is None and "<Min>-<Max>" in _r.output)
_r, _s = _one("9")
check("Punkt-Klick: ein unbekannter Punkt", _s is None and "nicht gefunden" in _r.output)
# Das Farbwort stand nur hinter einer festen Zeit; hinter einem Bereich fiel es
# still weg, und ein Tippfehler darin ergab einen Klick ohne Bedingung.
_r, _s = _one("1 2-4 color")
check("Punkt-Klick: Bereich und dann Farbe",
      (_s.delay_before, _s.delay_max) == (2, 4) and _s.wait_condition is not None
      and _s.wait_condition.until_gone is False)
_r, _s = _one("1 2-4 checkgone")
check("Punkt-Klick: Bereich und einmalige Prüfung",
      _s.wait_condition.check_only and _s.wait_condition.until_gone)
_r, _s = _one("1 5 colr")
check("Punkt-Klick: ein unbekanntes Farbwort legt keinen Schritt an und wird gesagt",
      _s is None and "Nicht verstanden: 'colr'" in _r.output)
_r, _s = _one("1 color 5")
check("Punkt-Klick: ein Wort hinter dem Farbwort wird gesagt",
      _s is None and "Nicht verstanden: '5'" in _r.output)
_r, _s = _one("1 5 color colorgone")
check("Punkt-Klick: zwei Farbwörter sind eins zu viel", _s is None and "Nicht verstanden" in _r.output)
_r, _s = _one("1 color else skip")
check("Punkt-Klick: mit Bedingung und else", _s.else_config is not None and _s.else_config.action == "skip")
_r, _s = _one("1 5 else skip")
check("Punkt-Klick: ohne Bedingung wirkt else nicht und wird gesagt",
      _s.else_config is None and "keine Wirkung" in _r.output)

# ============================================================ wait
_r, _s = _one("wait 5")
check("wait: nur warten", (_s.wait_only, _s.delay_before, _s.name) == (True, 5, "Wait:5s"))
_r, _s = _one("wait 1-3")
check("wait: Zufallsbereich", (_s.delay_before, _s.delay_max, _s.name) == (1, 3, "Wait:1-3s"))
_r, _s = _one("wait x")
check("wait: unlesbar", _s is None and "wait <Zeit>" in _r.output)
_r, _s = _one("wait 1-x")
check("wait: unlesbarer Bereich", _s is None and "wait <Min>-<Max>" in _r.output)
_r, _s = _one("wait 1 color")
check("wait <Punkt> color: wartet auf die Punktfarbe, ohne Klick",
      _s.wait_only and _s.wait_condition and _s.wait_condition.until_gone is False
      and _s.name == "Wait:Pixel Knopf")
_r, _s = _one("wait 1 colorgone")
check("wait <Punkt> colorgone", _s.wait_condition.until_gone and _s.name == "Wait:Gone Knopf")
_r, _s = _one("wait 9 color")
check("wait <Punkt>: unbekannter Punkt", _s is None and "nicht gefunden" in _r.output)
_r, _s = _one("wait x color")
check("wait <Punkt>: keine Nummer", _s is None and "wait <Punkt-Nr> color" in _r.output)
_r, _s = _one("wait pixel")
check("wait pixel: Farbe an der Maus", _s.wait_condition.pixel == (7, 8) and _s.name == "Wait:Pixel")
_r, _s = _one("wait pixelgone")
check("wait pixelgone", _s.wait_condition.until_gone and _s.name == "Wait:Gone")
_r, _s = _one("wait pixel", pixel=(None, None, None))
check("wait pixel: ohne Farbe kein Schritt", _s is None)
_r, _s = _one("wait 1 color else restart")
check("wait <Punkt>: mit else", _s.else_config.action == "restart")
_r, _s = _one("wait pixel else skip")
check("wait pixel: mit else", _s.else_config.action == "skip")

# ============================================================ key, Scans, Screenshot
_r, _s = _one("key enter")
check("key: Taste sofort", (_s.key_press, _s.delay_before) == ("enter", 0))
_r, _s = _one("key 5 space")
check("key: mit Wartezeit", (_s.key_press, _s.delay_before) == ("space", 5))
_r, _s = _one("key 2-4 a")
check("key: mit Bereich", (_s.delay_before, _s.delay_max) == (2, 4))
_r, _s = _one("key x enter")
check("key: unlesbare Zeit", _s is None)
_r, _s = _one("key gibtsnicht")
check("key: unbekannte Taste", _s is None and "Unbekannte Taste" in _r.output)
_r, _s = _one("scan Beute every else skip")
check("scan: Name, Modus, else",
      (_s.item_scan, _s.item_scan_mode, _s.else_config.action) == ("Beute", "every", "skip"))
_r, _s = _one("scan Beute")
check("scan: Modus all als Vorgabe", _s.item_scan_mode == "all")
_r, _s = _one("boss Drache")
check("boss", (_s.boss_scan, _s.name) == ("Drache", "Boss:Drache"))
_r, _s = _one("watcher Drache")
check("watcher", _s.boss_watcher == "Drache")
_r, _s = _one("icon Warnung")
check("icon", _s.icon_scan == "Warnung")
_r, _s = _one("ss full")
check("Screenshot Vollbild", _s.screenshot_only and _s.screenshot_region is None)
_r, _s = _one("screenshot 0 0 10 20")
check("Screenshot feste Region", _s.screenshot_region == (0, 0, 10, 20))
_r, _s = _one("ss")
check("Screenshot interaktiv", _s.screenshot_region == (0, 0, 40, 30))
_r, _s = _one("ss", pillow=False)
check("Screenshot ohne Pillow", _s is None and "Pillow" in _r.output)


# ============================================================ Liste bearbeiten
def _three():
    return [_STEP(x=1, y=1, delay_before=1, name="A", point_id=1),
            _STEP(x=2, y=2, delay_before=2, name="B", point_id=1),
            _STEP(x=3, y=3, delay_before=3, name="C", point_id=1)]


def _names(run):
    return [s.name for s in run.steps]


_r = _Run(["del 2", "done"], steps=_three()).run()
check("del <Nr>", _names(_r) == ["A", "C"])
_r = _Run(["del 1-2", "done"], steps=_three()).run()
check("del <Von>-<Bis>", _names(_r) == ["C"])
_r = _Run(["del all", "done"], steps=_three()).run()
check("del all", _r.steps == [])
_r = _Run(["del 9", "del 3-1", "del x", "done"], steps=_three()).run()
check("del ausserhalb, verdreht, unlesbar",
      len(_r.steps) == 3 and "Ungültiger Schritt" in _r.output and "Ungültiger Bereich" in _r.output)
_r = _Run(["ins 1", "boss X", "done"], steps=_three()).run()
check("ins: der nächste neue Schritt kommt an die Stelle", _names(_r)[0] == "Boss:X")
_r = _Run(["ins 2", "ins 0", "boss X", "done"], steps=_three()).run()
check("ins 0 beendet den Einfügemodus", _names(_r)[-1] == "Boss:X")
_r = _Run(["ins 9", "ins 0", "ins x", "done"], steps=_three()).run()
check("ins: zu gross, nicht aktiv, unlesbar",
      "zu gross" in _r.output and "nicht aktiv" in _r.output and "Format: ins <Nr>" in _r.output)
_r = _Run(["points", "p", "done"]).run()
check("points zeigt die Punkte", _r.output.count("Knopf") >= 2)
_r = _Run(["learn Neu", "", "done"], cursor=[(5, 6)]).run()
check("learn <Name>: ein neuer Punkt an der Maus, gespeichert",
      _r.state.points[-1].name == "Neu" and (_r.state.points[-1].x, _r.state.points[-1].y) == (5, 6)
      and _r.saved == 1)
_r = _Run(["learn", "cancel", "done"]).run()
check("learn ohne Namen, abgebrochen", len(_r.state.points) == 2 and "Abgebrochen" in _r.output)

# Umbauen per Kurzbefehl
_r = _Run(["color 1", "done"], steps=_three()).run()
check("color <Nr>: Farb-Trigger und Klick", _r.steps[0].wait_condition is not None)
_r = _Run(["noclick 1", "click 2", "done"], steps=_three()).run()
check("noclick / click", _r.steps[0].wait_only is True and _r.steps[1].wait_only is False)
_r = _Run(["time 1 7", "time 2 1-2", "done"], steps=_three()).run()
check("time", (_r.steps[0].delay_before, _r.steps[1].delay_max) == (7, 2))
_r = _Run(["copy 1", "done"], steps=_three()).run()
check("copy: die Kopie steht dahinter", _names(_r) == ["A", "A", "B", "C"])
_r = _Run(["move 3 1", "done"], steps=_three()).run()
check("move", _names(_r) == ["C", "A", "B"])
_r = _Run(["scale 2", "done"], steps=_three()).run()
check("scale", [s.delay_before for s in _r.steps] == [2, 4, 6])
_r = _Run(["test 2", "done"], steps=_three()).run()
check("test führt eine Kopie ohne Wartezeit aus",
      len(_r.executed) == 1 and _r.executed[0].delay_before == 0 and _r.steps[1].delay_before == 2)
_r = _Run(["break 1", "done"], steps=_three()).run()
check("break", _r.steps[0].breakpoint is True)
_r = _Run(["verify 1 1", "done"], steps=_three()).run()
check("verify <Nr> <Punkt>", _r.steps[0].verify_condition and _r.steps[0].verify_condition.point_id == 1)
_steps = _three()
_steps[0].wait_condition = _WC(point_id=1, pixel=(1, 1), color=(0, 0, 0))
_r = _Run(["recolor 1", "done"], steps=_steps).run()
check("recolor", _r.steps[0].wait_condition.color == (1, 2, 3))

# show <Nr>
_steps = _three()
_steps[0].delay_max = 3
_steps[0].recorded_color = (4, 5, 6)
_steps[0].wait_condition = _WC(point_id=1, pixel=(1, 1), color=(0, 0, 0), until_gone=True)
_r = _Run(["show 1", "show", "s", "done"], steps=_steps).run()
check("show <Nr>: alle Felder",
      "Wartezeit:       1-3s (zufällig)" in _r.output and "bis Farbe WEG" in _r.output
      and "Aufgen. Farbe:   RGB(4, 5, 6)" in _r.output)
_scan = [_STEP(x=0, y=0, delay_before=0, name="S", item_scan="Beute", key_press=None)]
_r = _Run(["show 1", "done"], steps=_scan).run()
check("show <Nr>: ein Scan-Schritt", "Item-Scan:       Beute (all)" in _r.output
      and "Farb-Trigger:    (keiner)" in _r.output)
_r = _Run(["show 9", "done"], steps=_three()).run()
check("show <Nr>: ausserhalb", "Ungültiger Schritt" in _r.output)

# ============================================================ edit-Menü
_r = _Run(["edit 1", "1", "9", "0", "done"], steps=_three()).run()
check("edit: Wartezeit", _r.steps[0].delay_before == 9)
_r = _Run(["e 1", "2", "2", "0", "done"], steps=_three()).run()
check("edit (e): Trigger auf Farbe DA", _r.steps[0].wait_condition is not None
      and not _r.steps[0].wait_condition.until_gone)
_r = _Run(["edit 1", "2", "1", "0", "done"], steps=_three()).run()
check("edit: Trigger entfernen", _r.steps[0].wait_condition is None)
_r = _Run(["edit 1", "2", "7", "0", "done"], steps=_three()).run()
check("edit: falsche Trigger-Wahl wird gesagt", "Bitte 1-3" in _r.output)
_r = _Run(["edit 1", "3", "0", "done"], steps=_three()).run()
check("edit: Klick an/aus", _r.steps[0].wait_only is True)
_r = _Run(["edit 1", "5", "x", "back", "done"], steps=_three()).run()
check("edit: Details und eine falsche Wahl", "Details" in _r.output and "Bitte 0-9" in _r.output)
_r = _Run(["edit 1", "6", "done"], steps=_three()).run()
check("edit: duplizieren schliesst das Menü", _names(_r) == ["A", "A", "B", "C"])
_r = _Run(["edit 1", "7", "3", "done"], steps=_three()).run()
check("edit: verschieben", _names(_r) == ["B", "C", "A"])
_r = _Run(["edit 2", "8", "0", "done"], steps=_three()).run()
check("edit: testen", len(_r.executed) == 1)
_r = _Run(["edit 2", "9", "done"], steps=_three(), answers=[True]).run()
check("edit: löschen nach Rückfrage", _names(_r) == ["A", "C"])
_r = _Run(["edit 2", "9", "0", "done"], steps=_three(), answers=[False]).run()
check("edit: ohne Zustimmung bleibt er", len(_r.steps) == 3)
_steps = _three()
_steps[0].wait_condition = _WC(point_id=1, pixel=(1, 1), color=(0, 0, 0))
_r = _Run(["edit 1", "4", "", "done"], steps=_steps).run()
check("edit: Farbe neu abgreifen", _r.steps[0].wait_condition.color == (1, 2, 3))
_r = _Run(["edit 9", "done"], steps=_three()).run()
check("edit: ausserhalb", "Ungültiger Schritt" in _r.output)

# ============================================================ link
_steps = [_STEP(x=100, y=200, delay_before=0, name="genau"),          # passt zu Punkt 1
          _STEP(x=5, y=5, delay_before=0, name="nirgends"),
          _STEP(x=100, y=200, delay_before=0, name="schon", point_id=1),
          _STEP(x=0, y=0, delay_before=0, name="taste", key_press="enter"),
          _STEP(x=300, y=400, delay_before=0, name="doppelt")]
_r = _Run(["link", "done"], steps=_steps)
_r.state.points.append(_CP(300, 400, "Zwilling", 3))
_r.run()
check("link: ein eindeutiger Punkt wird verknüpft", _r.steps[0].point_id == 1)
check("link: mehrdeutig und ohne Punkt bleiben, Tasten werden übergangen",
      _r.steps[4].point_id is None and _r.steps[1].point_id is None and _r.steps[3].point_id is None
      and "1 mehrdeutig" in _r.output and "1 ohne passenden Punkt" in _r.output
      and "1 Schritt(e) waren schon verknüpft" in _r.output)
_r = _Run(["link all", "done"], steps=[_STEP(x=0, y=0, delay_before=0, name="t", key_press="a")]).run()
check("link: nichts zu tun", "Nichts zu tun" in _r.output)
_r = _Run(["link", "done"], steps=_three())
_r.state.points = []
_r.run()
check("link: ohne Punkte", "Keine Punkte" in _r.output)

# ============================================================ else-Formen
section("ELSE-Bedingung: jede Form")
_else_state = _ST()
_else_state.points = [_CP(100, 200, "Knopf", 1), _CP(300, 400, "", 2)]


def _else(text):
    buffer = _io.StringIO()
    with _cl.redirect_stdout(buffer):
        result = _HE.parse_else_condition(text.split(), _else_state)
    return result, buffer.getvalue()


check("leer", _else("")[0] == {})
for _word in ("skip", "skip_cycle", "restart", "SKIP"):
    check(f"else {_word}", _else(_word)[0] == {"else_action": _word.lower()})
check("else key <Taste>", _else("key Enter")[0] == {"else_action": "key", "else_key": "enter"})
_res, _out = _else("key gibtsnicht")
check("else key mit unbekannter Taste", _res == {} and "Unbekannte Taste" in _out)
_res, _out = _else("key")
check("else key ohne Taste ist ein unbekanntes Format", _res == {} and "Unbekanntes ELSE-Format" in _out)
check("else <Nr>: Punkt mit Namen",
      _else("1")[0] == {"else_action": "click", "else_point_id": 1, "else_x": 100, "else_y": 200,
                        "else_name": "Knopf"})
check("else <Nr> ohne Punktnamen", _else("2")[0]["else_name"] == "Punkt #2")
check("else <Nr> <Sek>", _else("1 2.5")[0]["else_delay"] == 2.5)
check("else <Nr> mit unlesbarer Zeit: ohne Verzögerung", "else_delay" not in _else("1 x")[0])
_res, _out = _else("9")
check("else <Nr>: unbekannter Punkt", _res == {} and "Punkt #9 nicht gefunden" in _out)
_res, _out = _else("quatsch")
check("else <Unsinn>", _res == {} and "Unbekanntes ELSE-Format" in _out)
