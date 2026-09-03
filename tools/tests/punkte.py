"""Die Stelle eines Blocks gehört dem Block, Name und Farbe dem Punkt.

Punkte werden bewusst geteilt: klickt eine Sequenz zweimal denselben Knopf, ist
das EIN Punkt — sonst wandert beim Nachjustieren nur die Hälfte mit. Genau das
ist beim Bearbeiten eines einzelnen Blocks aber die falsche Regel: man korrigiert
eine Stelle und verstellt drei andere, ohne es zu sehen.

Deshalb zwei Wege mit zwei Bedeutungen, und beide werden hier gemessen:

* **Block-Inspektor** (`punkt_setzen`) — „dieser Block klickt woanders hin".
  Ist der Punkt geteilt, spaltet sich einer ab (copy-on-write).
* **Werkzeuge → Punkte verwalten** (`werkzeug_punkt_setzen`) — „der Knopf ist
  umgezogen". Der Punkt wandert, alle ziehen mit.

Liefe der zweite Weg auch über copy-on-write, wäre die Kalibrierung kaputt: sie
lebt davon, dass eine Korrektur ALLE Schritte erreicht.
"""
import os as _os
import tempfile
from pathlib import Path

from ._harness import check, section
from autoclicker.editors.sequence_studio.bridge import StudioBridge as _SB
from autoclicker.models import (
    AutoClickerState as _ST, ClickPoint as _CP, ElseConfig as _ELSE,
    LoopPhase as _PHASE, Sequence as _SEQ, SequenceStep as _STEP,
    WaitCondition as _WAIT,
)

section("Die Stelle eines Blocks aendert nur diesen Block")

_sand = Path(tempfile.mkdtemp(prefix="punkte_"))
_cwd = _os.getcwd()
_os.chdir(_sand)
try:
    Path("sequences").mkdir(exist_ok=True)
    from autoclicker.persistence import list_available_sequences, save_data

    def _bruecke(steps, punkte):
        """Frisches Studio auf einer Sequenz mit genau diesen Schritten."""
        st = _ST()
        seq = _SEQ(name="Farm", loop_phases=[_PHASE(name="A", steps=steps)],
                   points=punkte)
        st.sequences["Farm"] = seq
        st.active_sequence = seq
        st.points = seq.points
        save_data(st)
        b = _SB(seq, dict(list_available_sequences())["Farm"], "sequences")
        return b

    def _waehle(b, row):
        b.sel_lane = b.board.lanes[1]          # INIT ist Lane 0, die Loop-Phase 1
        b.sel_rows = {row}
        return b.sel_lane.steps[row]

    # --- geteilter Punkt: es entsteht ein neuer -----------------------------
    _b = _bruecke([_STEP(point_id=1), _STEP(point_id=1)],
                  [_CP(id=1, x=100, y=200, name="Bank", color=(10, 20, 30))])
    _vorher = len(_b.points)
    _s0 = _waehle(_b, 0)
    _z = _b.punkt_setzen({"punkt": 1, "feld": "x", "wert": 555})
    _neu_id = _b.board.lanes[1].steps[0].point_id
    check("ein geteilter Punkt wird abgespalten", len(_b.points) == _vorher + 1)
    check("der Block zeigt auf den neuen", _neu_id != 1)
    check("und der neue steht an der neuen Stelle",
          _b._punkt(_neu_id).x == 555 and _b._punkt(_neu_id).y == 200)
    check("der alte bleibt, wo er war", _b._punkt(1).x == 100)
    check("und der zweite Block bleibt auf ihm",
          _b.board.lanes[1].steps[1].point_id == 1)
    check("Name und Farbe kommen mit",
          _b._punkt(_neu_id).name == "Bank" and _b._punkt(_neu_id).color == (10, 20, 30))
    check("und es wird gesagt", "angelegt" in _z["status"]["text"])

    # Die zweite Achse trifft schon den neuen Punkt — kein zweites Abspalten.
    _zahl = len(_b.points)
    _b.punkt_setzen({"punkt": _neu_id, "feld": "y", "wert": 666})
    check("die zweite Achse legt keinen weiteren an", len(_b.points) == _zahl)
    check("und landet am selben Punkt", _b._punkt(_neu_id).y == 666)

    # --- Punkt nur bei diesem Block: an Ort und Stelle ----------------------
    _b = _bruecke([_STEP(point_id=1), _STEP(point_id=2)],
                  [_CP(id=1, x=100, y=200), _CP(id=2, x=300, y=400)])
    _vorher = len(_b.points)
    _waehle(_b, 0)
    _b.punkt_setzen({"punkt": 1, "feld": "x", "wert": 555})
    check("ein Punkt ohne fremde Nutzer wird verschoben, nicht kopiert",
          len(_b.points) == _vorher and _b._punkt(1).x == 555)
    check("und der Block bleibt an ihm", _b.board.lanes[1].steps[0].point_id == 1)

    # --- FARBE+KLICK: Klick und Pruef-Pixel bleiben derselbe Punkt ----------
    _b = _bruecke([_STEP(point_id=1, wait_condition=_WAIT(point_id=1)),
                   _STEP(point_id=1)],
                  [_CP(id=1, x=100, y=200)])
    _s0 = _waehle(_b, 0)
    _b.punkt_setzen({"punkt": 1, "feld": "x", "wert": 555})
    _s0 = _b.board.lanes[1].steps[0]
    check("bei FARBE+KLICK zieht der Pruef-Pixel mit",
          _s0.point_id == _s0.wait_condition.point_id and _s0.point_id != 1)
    check("der andere Block bleibt trotzdem auf dem alten",
          _b.board.lanes[1].steps[1].point_id == 1)

    # Nachpruefung und ELSE desselben Blocks ebenso.
    _b = _bruecke([_STEP(point_id=1, verify_condition=_WAIT(point_id=1),
                         else_config=_ELSE(action="click", point_id=1)),
                   _STEP(point_id=1)],
                  [_CP(id=1, x=100, y=200)])
    _waehle(_b, 0)
    _b.punkt_setzen({"punkt": 1, "feld": "y", "wert": 999})
    _s0 = _b.board.lanes[1].steps[0]
    check("Nachpruefung und ELSE desselben Blocks ziehen mit",
          _s0.verify_condition.point_id == _s0.point_id
          and _s0.else_config.point_id == _s0.point_id)

    # --- Name und Farbe gehoeren dem Punkt und spalten NICHT ab -------------
    _b = _bruecke([_STEP(point_id=1), _STEP(point_id=1)],
                  [_CP(id=1, x=100, y=200, name="Bank")])
    _vorher = len(_b.points)
    _waehle(_b, 0)
    _b.punkt_setzen({"punkt": 1, "feld": "name", "wert": "Truhe"})
    _b.punkt_setzen({"punkt": 1, "feld": "farbe", "wert": "#0A141E"})
    check("Umbenennen legt keinen neuen Punkt an", len(_b.points) == _vorher)
    check("und gilt fuer beide Bloecke",
          _b._punkt(1).name == "Truhe"
          and _b.board.lanes[1].steps[1].point_id == 1)
    check("die Farbe ebenso", _b._punkt(1).color == (10, 20, 30))

    # --- Ohne eindeutigen Block bleibt alles beim Alten ---------------------
    _b = _bruecke([_STEP(point_id=1), _STEP(point_id=1)],
                  [_CP(id=1, x=100, y=200)])
    _vorher = len(_b.points)
    _b.sel_lane, _b.sel_rows = None, set()
    _b.punkt_setzen({"punkt": 1, "feld": "x", "wert": 555})
    check("ohne gewaehlten Block wird nichts abgespalten",
          len(_b.points) == _vorher and _b._punkt(1).x == 555)

    # --- Gegenprobe: der Werkzeuge-Weg zieht weiterhin ALLE mit -------------
    # Das ist keine Inkonsequenz, sondern der Grund, warum es zwei Methoden
    # gibt: „der Knopf ist umgezogen" muss jeden Schritt erreichen, sonst waere
    # jede Kalibrierung eine halbe.
    _b = _bruecke([_STEP(point_id=1), _STEP(point_id=1)],
                  [_CP(id=1, x=100, y=200)])
    _vorher = len(_b.points)
    _waehle(_b, 0)
    _z = _b.werkzeug_punkt_setzen({"punkt_id": 1, "feld": "x", "wert": 555})
    check("Werkzeuge > Punkte verwalten verschiebt weiterhin den Punkt",
          _z["ok"] and len(_b.points) == _vorher and _b._punkt(1).x == 555)
    check("und beide Bloecke ziehen mit",
          [s.point_id for s in _b.board.lanes[1].steps] == [1, 1])

    # --- „Stelle mit der Maus setzen" erbt dasselbe Verhalten ---------------
    # Zweiter Eingang in dieselbe Regel. Ohne diesen Test koennte er still
    # danebenlaufen — er ruft `punkt_setzen` zwar auf, aber ueber zwei
    # Einzelaufrufe, und der zweite darf nicht nochmal abspalten.
    import autoclicker.utils.io as _io
    import autoclicker.winapi as _win
    _alt = (_io.warte_auf_taste, _win.get_cursor_pos, _win.get_screen_pixel)
    _io.warte_auf_taste = lambda *a, **k: "enter"
    _win.get_cursor_pos = lambda: (777, 888)
    _win.get_screen_pixel = lambda x, y: (1, 2, 3)
    try:
        _b = _bruecke([_STEP(point_id=1), _STEP(point_id=1)],
                      [_CP(id=1, x=100, y=200)])
        _vorher = len(_b.points)
        _waehle(_b, 0)
        _b.punkt_aufnehmen()
        _neu = _b.board.lanes[1].steps[0].point_id
        check("die Maus-Aufnahme spaltet genau EINEN Punkt ab",
              len(_b.points) == _vorher + 1 and _neu != 1)
        check("er liegt an der Mausposition",
              (_b._punkt(_neu).x, _b._punkt(_neu).y) == (777, 888))
        check("die gemessene Farbe landet am neuen Punkt",
              _b._punkt(_neu).color == (1, 2, 3))
        check("und der alte Punkt bleibt unberuehrt",
              (_b._punkt(1).x, _b._punkt(1).y) == (100, 200)
              and _b.board.lanes[1].steps[1].point_id == 1)
    finally:
        _io.warte_auf_taste, _win.get_cursor_pos, _win.get_screen_pixel = _alt
finally:
    _os.chdir(_cwd)
    import shutil as _sh
    _sh.rmtree(_sand, ignore_errors=True)
