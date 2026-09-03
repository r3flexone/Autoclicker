"""Duplizieren legt eigene Punkte an — Verschieben ändert weiterhin den Punkt.

Zwei Regeln, die sich nur scheinbar widersprechen:

* **X und Y verschieben den PUNKT**, und jeder Schritt darauf zieht mit. Das ist
  richtig und soll so bleiben: klicken zwei Blöcke denselben Knopf und der Knopf
  zieht um, sollen beide mit — sonst wäre jede Kalibrierung eine halbe.
* **Ein Duplikat bekommt eigene Punkte.** Man dupliziert einen Block, um ihn zu
  ändern; zeigten beide auf denselben Punkt, verstellte jede Korrektur an der
  Kopie auch das Original. Der Zusammenhang wäre schon beim Anlegen falsch.

Hier lag der Fehler, und er sah aus wie einer beim Ändern: Block duplizieren,
Kopie verschieben — und das Original wanderte mit.
"""
import os as _os
import tempfile
from pathlib import Path

from ._harness import check, section
from autoclicker.models import (
    AutoClickerState as _ST, ClickPoint as _CP, ElseConfig as _ELSE,
    LoopPhase as _PHASE, Sequence as _SEQ, SequenceStep as _STEP,
    WaitCondition as _WAIT,
)
from autoclicker.editors.sequence_studio.bridge import StudioBridge as _SB

section("Duplizieren: die Kopie bekommt eigene Punkte")

_sand = Path(tempfile.mkdtemp(prefix="punkte_"))
_cwd = _os.getcwd()
_os.chdir(_sand)
try:
    Path("sequences").mkdir(exist_ok=True)
    from autoclicker.persistence import list_available_sequences, save_data

    def _bruecke(steps, punkte):
        st = _ST()
        seq = _SEQ(name="Farm", loop_phases=[_PHASE(name="A", steps=steps)],
                   points=punkte)
        st.sequences["Farm"] = seq
        st.active_sequence = seq
        st.points = seq.points
        save_data(st)
        return _SB(seq, dict(list_available_sequences())["Farm"], "sequences")

    def _waehle(b, *rows):
        b.sel_lane = b.board.lanes[1]      # INIT ist Lane 0, die Loop-Phase 1
        b.sel_rows = set(rows)
        b.sel_anchor = min(rows)
        return b.sel_lane.steps

    def _schritte(b):
        return b.board.lanes[1].steps

    # --- der Fall, der es ausgeloest hat -----------------------------------
    _b = _bruecke([_STEP(point_id=1)],
                  [_CP(id=1, x=100, y=200, name="Bank", color=(10, 20, 30))])
    _waehle(_b, 0)
    _z = _b.auswahl_duplizieren()
    _orig, _kopie = _schritte(_b)
    check("das Duplikat steht dahinter", len(_schritte(_b)) == 2)
    check("und bekommt einen eigenen Punkt", _kopie.point_id != _orig.point_id)
    check("der auf derselben Stelle liegt",
          (_b._punkt(_kopie.point_id).x, _b._punkt(_kopie.point_id).y) == (100, 200))
    check("Name und Farbe kommen mit",
          _b._punkt(_kopie.point_id).name == "Bank"
          and _b._punkt(_kopie.point_id).color == (10, 20, 30))
    check("und es wird gesagt", "Punkt" in _z["status"]["text"])

    # Und jetzt das, was vorher schiefging: die Kopie verschieben.
    _b.sel_rows = {1}
    _b.punkt_setzen({"punkt": _kopie.point_id, "feld": "x", "wert": 555})
    check("die Kopie laesst sich verschieben", _b._punkt(_kopie.point_id).x == 555)
    check("und das Original bleibt, wo es war", _b._punkt(_orig.point_id).x == 100)

    # --- Gegenprobe: der Punkt selbst zieht weiterhin ALLE mit -------------
    # Das ist keine Ausnahme, sondern der Normalfall. Zwei Bloecke auf einem
    # Knopf muessen zusammen umziehen, sonst waere jede Kalibrierung eine halbe.
    _b = _bruecke([_STEP(point_id=1), _STEP(point_id=1)],
                  [_CP(id=1, x=100, y=200)])
    _waehle(_b, 0)
    _b.punkt_setzen({"punkt": 1, "feld": "x", "wert": 777})
    check("ein geteilter Punkt wird verschoben, nicht gespalten",
          len(_b.points) == 1 and _b._punkt(1).x == 777)
    check("und beide Bloecke ziehen mit",
          all(s.x == 777 for s in _schritte(_b)))

    # --- FARBE+KLICK: die Kopie wartet auf DIE Stelle, die sie klickt -------
    _b = _bruecke([_STEP(point_id=1, wait_condition=_WAIT(point_id=1))],
                  [_CP(id=1, x=100, y=200)])
    _waehle(_b, 0)
    _b.auswahl_duplizieren()
    _kopie = _schritte(_b)[1]
    check("Klick und Pruef-Pixel der Kopie sind DERSELBE neue Punkt",
          _kopie.point_id == _kopie.wait_condition.point_id and _kopie.point_id != 1)
    check("es entsteht dafuer nur EIN Punkt", len(_b.points) == 2)

    # Nachpruefung und ELSE ebenso — vier Stellen, eine Abbildung.
    _b = _bruecke([_STEP(point_id=1, verify_condition=_WAIT(point_id=2),
                         else_config=_ELSE(action="click", point_id=1))],
                  [_CP(id=1, x=10, y=20), _CP(id=2, x=30, y=40)])
    _waehle(_b, 0)
    _b.auswahl_duplizieren()
    _kopie = _schritte(_b)[1]
    check("zwei verschiedene Vorlagen ergeben zwei neue Punkte", len(_b.points) == 4)
    check("der ELSE-Klick teilt den Punkt des Klicks, wie im Original",
          _kopie.else_config.point_id == _kopie.point_id)
    check("die Nachpruefung behaelt ihren eigenen",
          _kopie.verify_condition.point_id not in (1, 2, _kopie.point_id))

    # --- Mehrfachauswahl: die Beziehung UNTEREINANDER bleibt --------------
    # Zwei Gewaehlte auf einem Knopf ergeben zwei Kopien auf EINEM neuen Knopf,
    # nicht auf zweien - sonst laegen drei Punkte auf derselben Stelle.
    _b = _bruecke([_STEP(point_id=1), _STEP(point_id=1)],
                  [_CP(id=1, x=100, y=200)])
    _waehle(_b, 0, 1)
    _b.auswahl_duplizieren()
    _a, _bb, _ka, _kb = _schritte(_b)
    check("beide Kopien teilen sich EINEN neuen Punkt",
          _ka.point_id == _kb.point_id and _ka.point_id != 1)
    check("und es kommt genau ein Punkt dazu", len(_b.points) == 2)
    check("die Originale bleiben unberuehrt",
          _a.point_id == 1 and _bb.point_id == 1)

    # --- Bloecke ohne Punkt legen keinen an -------------------------------
    _b = _bruecke([_STEP(key_press="a"), _STEP(item_scan="Inventar")], [])
    _waehle(_b, 0, 1)
    _b.auswahl_duplizieren()
    check("ein Tasten- oder Scan-Block bekommt keinen Punkt geschenkt",
          len(_b.points) == 0 and len(_schritte(_b)) == 4)

    # --- Eine tote Referenz wird nicht wiederbelebt ------------------------
    # Zeigt ein Schritt ins Leere, ist das ein Fehler, den man sehen soll —
    # eine erfundene Kopie machte daraus stillschweigend einen Klick auf (0,0).
    _b = _bruecke([_STEP(point_id=99)], [_CP(id=1, x=10, y=20)])
    _waehle(_b, 0)
    _b.auswahl_duplizieren()
    check("eine Referenz ins Leere bleibt eine Referenz ins Leere",
          _schritte(_b)[1].point_id == 99 and len(_b.points) == 1)
finally:
    _os.chdir(_cwd)
    import shutil as _sh
    _sh.rmtree(_sand, ignore_errors=True)
