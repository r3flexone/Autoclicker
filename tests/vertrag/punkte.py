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

Dazu die Frage eine Ebene darüber: **wem gehören die Punkte?** Der Sequenz, in
deren `sequence.json` sie stehen — und damit muss jeder Wechsel des Gegenstands
sie mitwechseln. Der Umzug auf sequenzlokale Punkte hat das an zwei Stellen
spiegelbildlich verfehlt: `neu()` im Studio liess die Punkte der VORIGEN Sequenz
stehen (und `speichern()` schrieb sie mit), `edit_sequence()` in der Konsole
liess sie ganz weg (und schrieb eine Sequenz ohne eine einzige Stelle). Gemessen
wird beides an der Datei, nicht an der Liste im Speicher.
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

    # ------------------------------------------------------------------
    section("Eine neue Sequenz faengt ohne Punkte an")

    # `laden()` ersetzt die Punkte, `neu()` liess sie stehen - und
    # `speichern()` schreibt `self.points` in die Datei. Eine frisch angelegte
    # Sequenz kam damit mit dem ganzen Punktebestand der vorher offenen auf die
    # Platte: ein Rest aus der Zeit der globalen `points.json`, in der genau das
    # richtig war. Seit die Punkte im Feld `points` IHRER `sequence.json`
    # stehen, sind es fremde Punkte.
    _b = _bruecke([_STEP(point_id=1), _STEP(point_id=2)],
                  [_CP(id=1, x=100, y=200, name="Bank"),
                   _CP(id=2, x=300, y=400, name="Truhe")])
    check("die Ausgangssequenz hat ihre zwei Punkte", len(_b.points) == 2)
    _b.neu()
    check("nach 'neu' ist die Punkteliste leer", _b.points == [])

    # Gemessen wird bis auf die PLATTE. Ein Test, der nur `self.points` prueft,
    # sieht die Wirkung nicht: geschrieben wird erst beim Speichern, und dort
    # steht die Punkteliste im selben Dict wie die Sequenz.
    _b.sequenz_setzen({"feld": "name", "wert": "Frisch"})
    _b.speichern()
    import json as _js
    _datei = _js.loads(
        Path("sequences/frisch/sequence.json").read_text(encoding="utf-8"))
    check("und die geschriebene Datei traegt keine fremden Punkte",
          _datei.get("points") in (None, []))
    check("die Ausgangssequenz behaelt ihre eigenen",
          len(_js.loads(Path("sequences/farm/sequence.json").read_text(
              encoding="utf-8")).get("points", [])) == 2)

    # ------------------------------------------------------------------
    section("Der Konsolen-Editor nimmt die Punkte mit")

    # **Derselbe Umbau, dieselbe Fehlerklasse, andere Richtung.** Seit die
    # Punkte in der `sequence.json` stehen, muessen sie beim Speichern DORT
    # landen — `edit_sequence()` baut aber ein frisches `Sequence(...)`, und
    # dessen Punkteliste faengt leer an. Geschrieben wurde die Sequenz damit
    # ohne einen einzigen Punkt, waehrend jeder Schritt weiter seine `point_id`
    # trug: die Schritte standen noch da, nur ohne Stelle.
    #
    # Gemessen wird an der Datei und ueber den echten Editor — er braucht nur
    # `safe_input`, laesst sich also mit einer Tastenfolge fuettern (dasselbe
    # Muster wie in `konsolen_editoren.py`). Der Durchlauf aendert NICHTS:
    # bestehende Sequenz oeffnen, jede Phase mit „done" verlassen, speichern.
    # Genau dabei verschwanden die Punkte.
    import contextlib as _cl
    import io as _io
    import autoclicker.editors.sequence_editor.editor as _ED
    import autoclicker.editors.sequence_editor.loops as _LOOPS
    import autoclicker.editors.sequence_editor.steps as _STEPS

    _folge = ["",        # Beschreibung behalten
              "done",    # INIT-Phase
              "done",    # Loop-Phasen
              "",        # Zyklen behalten
              "done"]    # END-Phase

    def _naechste(_prompt=""):
        return _folge.pop(0) if _folge else "done"

    _st = _ST()
    _seq = _SEQ(name="Konsole",
                loop_phases=[_PHASE(name="A", steps=[_STEP(point_id=1)])],
                points=[_CP(id=1, x=11, y=22, name="Bank")])
    _st.sequences["Konsole"] = _seq
    _st.active_sequence = _seq
    _st.points = _seq.points
    save_data(_st)

    _alt = (_ED.safe_input, _LOOPS.safe_input, _STEPS.safe_input)
    _ED.safe_input = _LOOPS.safe_input = _STEPS.safe_input = _naechste
    try:
        with _cl.redirect_stdout(_io.StringIO()):
            _ED.edit_sequence(_st, _seq)
    finally:
        _ED.safe_input, _LOOPS.safe_input, _STEPS.safe_input = _alt

    _nach = _js.loads(
        Path("sequences/konsole/sequence.json").read_text(encoding="utf-8"))
    check("die gespeicherte Sequenz hat ihren Punkt noch",
          [pt.get("id") for pt in _nach.get("points", [])] == [1])
    check("und der Schritt zeigt weiterhin darauf",
          _nach["loop_phases"][0]["steps"][0].get("point_id") == 1)
    # Der State ist die zweite Haelfte: er zeigt nach dem Speichern auf die
    # Punkte DIESER Sequenz, nicht auf eine leere Liste daneben.
    check("und der State haelt dieselbe Liste wie die Sequenz",
          _st.points is _st.active_sequence.points and len(_st.points) == 1)

    # ------------------------------------------------------------------
    section("Umbenennen zieht JEDE Referenz nach")

    # **Der Name IST die Referenz** - ein Scan wird per Namen aus dem Schritt
    # gerufen. Gemessen an einem echten Durchgang zog genau EINE von sechs
    # Referenzen nach: `step.item_scan`. Boss, Watcher, Icon und der
    # Fallback-Scan (`BossScanConfig.default_scan`, den `runtime/steps.py` bei
    # „kein Boss erkannt" wirklich ausfuehrt) blieben auf dem alten Namen
    # stehen - und weil `_erkennung_umbenennen` die alte Datei absichtlich
    # liegen liess, stand der Scan nach dem naechsten Oeffnen ZWEIMAL da.
    from autoclicker.models import (
        BossScanConfig as _BSC, IconScanConfig as _ISC, ItemScanConfig as _ISCAN,
    )
    import contextlib as _cl_ref
    import io as _io_ref

    _st_ref = _ST()
    _seq_ref = _SEQ(name="Ref", loop_phases=[_PHASE(name="A", steps=[
        _STEP(item_scan="beutel", name="Scan:beutel"),
        _STEP(boss_scan="wache", name="Boss:wache"),
        _STEP(boss_watcher="wache", name="Watcher:wache"),
        _STEP(icon_scan="lupe", name="Icon:lupe"),
        _STEP(boss_scan="wache", name="Mein eigener Name"),
    ])])
    _st_ref.sequences["Ref"] = _seq_ref
    _st_ref.active_sequence = _seq_ref
    save_data(_st_ref)
    _br = _SB(_seq_ref, dict(list_available_sequences())["Ref"], "sequences")
    with _cl_ref.redirect_stdout(_io_ref.StringIO()):
        _br._scan_laden()
        _br.scans["beutel"] = _ISCAN(name="beutel", owner_sequence="Ref")
        _br.boss_scans["wache"] = _BSC(name="wache", owner_sequence="Ref",
                                       default_scan="beutel")
        _br.icon_scans["lupe"] = _ISC(name="lupe", owner_sequence="Ref")
        _br.scan_offen, _br.boss_offen, _br.icon_offen = "beutel", "wache", "lupe"
        _br._erkennung_speichern()
        _br.scan_setzen({"name": "beutel", "feld": "name", "wert": "tasche"})
        _br.boss_scan_setzen({"name": "wache", "feld": "name", "wert": "drache"})
        _br.icon_setzen({"name": "lupe", "feld": "name", "wert": "brille"})

    _sr = _br.board.lanes[1].steps
    check("der Item-Scan-Block zeigt auf den neuen Namen",
          _sr[0].item_scan == "tasche")
    check("der Boss-Scan-Block ebenso", _sr[1].boss_scan == "drache")
    check("der Watcher ebenso - er zeigt auf dieselbe Datei",
          _sr[2].boss_watcher == "drache")
    check("der Icon-Scan-Block ebenso", _sr[3].icon_scan == "brille")
    check("und der Fallback-Scan eines Boss-Scans, den die Laufzeit ausfuehrt",
          _br.boss_scans["drache"].default_scan == "tasche")

    # Die Beschriftung zieht mit - aber NUR die abgeleitete.
    check("die abgeleitete Beschriftung zieht mit",
          [_sr[0].name, _sr[1].name, _sr[3].name]
          == ["Scan:tasche", "Boss:drache", "Icon:brille"])
    check("ein selbst getippter Blockname bleibt unangetastet",
          _sr[4].name == "Mein eigener Name" and _sr[4].boss_scan == "drache")

    # **Ein Umbenennen, das klont, ist keins.** `_scan_laden()` sieht den Ordner
    # durch; blieb die alte Datei liegen, stand der Scan nach dem naechsten
    # Oeffnen zweimal da - und der Block lief gegen die alte.
    with _cl_ref.redirect_stdout(_io_ref.StringIO()):
        _br._erkennung_speichern()
        _br2 = _SB(_SEQ(name="Ref"), _br.filepath, "sequences")
        _br2._scan_laden()
    check("die alte Boss-Datei bleibt nicht liegen",
          sorted(_br2.boss_scans) == ["drache"])
    check("und die alte Icon-Datei ebenso wenig",
          sorted(_br2.icon_scans) == ["brille"])
finally:
    _os.chdir(_cwd)
    import shutil as _sh
    _sh.rmtree(_sand, ignore_errors=True)

# ----------------------------------------------------------------------
section("Die Farbe des Punkts steht auf jeder Karte, die einen hat")

# Sie stand nur an der Farb-Bedingung („wartet bis RGB(…) da"). Ein reiner
# Klick zeigte Koordinaten - und beim Ueberfliegen von 50 Karten unterscheidet
# niemand vierstellige Koordinaten, die Farbe des Knopfs schon. Das ist, was
# man zum Umsortieren braucht: „der gruene, dann der rote".
from ._harness import studio_web_source as _web_src
_seq_pf = _SEQ(name="Farben", loop_phases=[_PHASE(name="A", steps=[
    _STEP(x=1, y=2, delay_before=0, point_id=1),                      # Klick, Farbe
    _STEP(x=3, y=4, delay_before=0, point_id=2),                      # Klick, ohne Farbe
    _STEP(delay_before=0, key_press="a"),                             # Taste
    _STEP(x=1, y=2, delay_before=0, point_id=1,
          wait_condition=_WAIT(point_id=1)),                          # FARBE+KLICK
])], points=[_CP(1, 2, "gruen", 1, color=(32, 135, 111)),
             _CP(3, 4, "blind", 2)])
_br_pf = _SB(_seq_pf, Path("sequences/farben.json"), "sequences")
_br_pf._punkte_anwenden()      # wie nach dem Laden: `load_sequence_file` loest auf
_karten = _br_pf.snapshot()["phasen"][1]["bloecke"]
check("ein Klick-Block traegt die Farbe seines Punkts",
      _karten[0]["punkt_farbe"] == "#20876F")
check("und die Stelle steht in seiner ersten Zeile",
      _karten[0]["zeilen"][0].startswith("#1 "))
check("ohne gemessene Farbe kein Feldchen", _karten[1]["punkt_farbe"] is None)
check("ein Block ohne Punkt hat keins", _karten[2]["punkt_farbe"] is None)
check("FARBE+KLICK traegt beides: Punktfarbe und Bedingung",
      _karten[3]["punkt_farbe"] == "#20876F" and _karten[3]["farbfeld"] == "#20876F"
      and _karten[3]["farbtext"].startswith("wartet bis"))
_web_pf = _web_src()
check("die Ansicht haengt das Feldchen an die erste Zeile",
      "block.punkt_farbe" in _web_pf and "karte-zeile mit-farbe" in _web_pf)
check("und zeichnet es wie das an der Bedingung",
      ".karte-zeile .feldchen,\n.karte-farbe .feldchen{" in _web_pf)

# ----------------------------------------------------------------------
section("Ein geteilter Punkt sagt, dass er geteilt ist")

# **Der Fall aus einer echten Aufnahme.** `punkt_an_stelle()` legt den Klick auf
# denselben Knopf in Loop 1 und Loop 4 auf EINEN Punkt - richtig so. Wer dann
# Loop 1 eine andere Stelle gibt („Stelle mit der Maus setzen"), verschiebt den
# Punkt, und Loop 4 zieht mit: der Block dort klickt ploetzlich woanders hin,
# und man sucht den Fehler in der Aufnahme („der Punkt war im Loop 4 an einer
# voellig falschen Stelle"). Dass der Punkt geteilt ist, stand nirgends - nur
# die Regel dazu im ⓘ. Drei Dinge dagegen: der Inspektor nennt die anderen
# Verwendungen, das Verschieben sagt, wer mitzieht, und ein Block kann sich
# einen eigenen Punkt abtrennen.
_seq_gp = _SEQ(name="Geteilt", loop_phases=[
    _PHASE(name="Loop", steps=[
        _STEP(x=10, y=10, delay_before=0, point_id=1,
              wait_condition=_WAIT(point_id=1)),                # FARBE+KLICK auf #1
    ]),
    _PHASE(name="Loop 4", steps=[
        _STEP(x=99, y=99, delay_before=0, point_id=2),
        _STEP(x=10, y=10, delay_before=0, point_id=1),          # derselbe Knopf
    ]),
], points=[_CP(10, 10, "knopf", 1, color=(32, 135, 111)),
           _CP(99, 99, "anderer", 2, color=(1, 2, 3))])
_br_gp = _SB(_seq_gp, Path("sequences/geteilt.json"), "sequences")
_br_gp._punkte_anwenden()
_br_gp.waehlen({"phase": 1, "zeile": 0})
_insp = _br_gp.snapshot()["block"]
check("der Inspektor nennt die anderen Verwendungen des Punkts",
      _insp["punkt_andere"] == ["Loop 4 · Block 2 · Stelle"])
check("den eigenen Pruef-Pixel zaehlt er dabei nicht mit",
      all("Loop · Block 1" not in v for v in _insp["punkt_andere"]))
_br_gp.waehlen({"phase": 2, "zeile": 0})
check("ein Block mit eigenem Punkt hat keine",
      _br_gp.snapshot()["block"]["punkt_andere"] == [])

_br_gp.waehlen({"phase": 1, "zeile": 0})
_z_gp = _br_gp.punkt_setzen({"punkt": 1, "feld": "x", "wert": 20})
check("das Verschieben sagt, wer mitzieht",
      "zieht 1 weitere" in _z_gp["status"]["text"]
      and "Loop 4 · Block 2" in _z_gp["status"]["text"])
check("und Loop 4 ist wirklich mitgezogen - das ist die Regel, nicht der Fehler",
      _br_gp.board.lanes[2].steps[1].x == 20)
_br_gp.waehlen({"phase": 2, "zeile": 0})
_z_gp2 = _br_gp.punkt_setzen({"punkt": 2, "feld": "x", "wert": 98})
check("ein ungeteilter Punkt bekommt keinen Nachsatz",
      "zieht" not in _z_gp2["status"]["text"])
_br_gp.waehlen({"phase": 1, "zeile": 0})

# Abtrennen: Loop 1 bekommt einen eigenen Punkt, Loop 4 behaelt #1 - und beim
# FARBE+KLICK wandern Klick UND Pruef-Pixel gemeinsam (wie beim Duplizieren).
_z_ab = _br_gp.punkt_abtrennen()
_s1 = _br_gp.board.lanes[1].steps[0]
check("Abtrennen gibt dem Block einen eigenen Punkt",
      _s1.point_id not in (1, 2) and _s1.wait_condition.point_id == _s1.point_id)
check("der neue Punkt liegt erst einmal auf derselben Stelle",
      (_s1.x, _s1.y) == (20, 10))
check("Loop 4 behaelt den alten Punkt",
      _br_gp.board.lanes[2].steps[1].point_id == 1)
check("und die Meldung sagt beides",
      f"#{_s1.point_id}" in _z_ab["status"]["text"] and "#1 bleibt bei" in _z_ab["status"]["text"])
_br_gp.punkt_setzen({"punkt": _s1.point_id, "feld": "x", "wert": 30})
check("danach verschiebt sich nur noch dieser Block",
      _s1.x == 30 and _br_gp.board.lanes[2].steps[1].x == 20)
check("ein zweites Abtrennen tut nichts und sagt es",
      "nichts abzutrennen" in _br_gp.punkt_abtrennen()["status"]["text"]
      and _br_gp.board.lanes[1].steps[0].point_id == _s1.point_id)
_web_gp = _web_src()
check("die Ansicht zeigt die Verwendungen und den Abtrennen-Knopf",
      "b.punkt_andere" in _web_gp and 'ruf("punkt_abtrennen")' in _web_gp)
