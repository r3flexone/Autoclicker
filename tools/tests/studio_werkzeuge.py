"""Reiter „Werkzeuge": prüfen, kalibrieren, Klick-Runde starten."""

from ._harness import check, section

import json as _js
import os as _os
import tempfile as _tf
from pathlib import Path as _P

from autoclicker.editors.sequence_studio.bridge import StudioBridge as _SB
from autoclicker.editors.sequence_studio.bridge_werkzeuge import KALIB_UMFANG
from autoclicker.models import (
    AutoClickerState as _ST, ClickPoint as _CP, ItemProfile as _IP,
    ItemScanConfig as _ISC, ItemSlot as _IS, LoopPhase as _LP, Sequence as _SEQ,
    SequenceStep as _SS,
)
from autoclicker.persistence import (
    list_available_sequences, save_data, save_global_items, save_global_slots,
    save_item_scan, save_points,
)
import autoclicker.befehl as _bf


def _sandkasten():
    """Ein vollständiger kleiner Bestand auf Platte, plus die Brücke darauf."""
    sand = _tf.mkdtemp(prefix="wz_")
    _os.chdir(sand)
    for d in ("sequences", "item_scans", "boss_scans", "icon_scans", "slots"):
        _P(d).mkdir()
    _P("items/templates").mkdir(parents=True)

    st = _ST()
    st.points = [_CP(id=1, x=100, y=100, name="Sammeln"),
                 _CP(id=2, x=900, y=600, name="Bestaetigen"),
                 _CP(id=3, x=400, y=300, name="Menue")]
    save_points(st)
    st.global_slots = {"Slot 1": _IS(name="Slot 1", scan_region=(10, 20, 70, 80),
                                     click_pos=(40, 50))}
    save_global_slots(st)
    seq = _SEQ(name="Farm", loop_phases=[_LP(name="A", steps=[
        _SS(point_id=1, delay_before=3.0), _SS(point_id=2)])])
    st.sequences["Farm"] = seq
    save_data(st)
    # Den Pfad NICHT von Hand bauen: `save_data` bereinigt den Namen (klein, ohne
    # Sonderzeichen), und die App holt ihn ueber `list_available_sequences()`. Ein
    # getippter Pfad geht daran vorbei - und genau der Unterschied entscheidet,
    # ob die Klick-Runde ihre Datei findet.
    bruecke = _SB(seq, _P(dict(list_available_sequences())["Farm"]), "sequences")
    # Die Maus gibt es im Test nicht: die Stelle kommt aus dem Stub, alles
    # andere laeuft wie im Fenster.
    bruecke._stelle_abwarten = lambda: (140, 130, "")
    return sand, bruecke


_cwd = _os.getcwd()

# --------------------------------------------------------------------- Prüfen

section("Studio-Werkzeuge: pruefen findet, was der Konsolen-`check` findet")
try:
    _sand, _b = _sandkasten()
    _d = _b.werkzeug_daten()
    check("die Punkte stehen zur Auswahl", [p["id"] for p in _d["punkte"]] == [1, 2, 3])
    # Die Kopfleiste blendet ihre Sequenz-Bedienelemente in diesem Reiter aus.
    # Ohne diese Angabe stuende nirgends, welche Sequenz die Klick-Runde meint.
    # Der NAME behaelt seine Schreibweise, der Dateiname wird entschaerft. Beide
    # stehen da, weil beide vorkommen: den Namen sucht man im Fenster, den
    # Dateinamen im Ordner.
    check("und der Reiter weiss, welche Sequenz offen ist", _d["sequenz"] == "Farm")
    check("samt Dateinamen, wie er auf Platte heisst",
          _d["datei"] == _b.filepath.name and _P("sequences", _d["datei"]).exists())
    check("samt der Frage, ob sie ungespeichert ist", _d["offen"] is False)
    _b._dirty = True
    check("und die Antwort aendert sich mit", _b.werkzeug_daten()["offen"] is True)
    _b._dirty = False
    check("und der Umfang kommt aus der Tabelle",
          [u["schluessel"] for u in _d["umfang"]] == [k for k, _, _ in KALIB_UMFANG])
    # Die Ansicht zeigt dieselben Schalter; laufen sie auseinander, schaltet ein
    # Haken etwas anderes als beschriftet.
    check("Slots sind standardmaessig AUS",
          {u["schluessel"]: u["vorgabe"] for u in _d["umfang"]}["mit_slots"] is False)

    _sauber = _b.werkzeug_pruefen()
    check("ein sauberer Bestand meldet nichts", _sauber["ok"] and not _sauber["befunde"])
    check("und sagt trotzdem, was geprueft wurde", len(_sauber["geprueft"]) > 0)

    # Jetzt absichtlich kaputt: ein Scan, der auf nicht vorhandene Namen zeigt.
    save_global_items(_ST(global_items={"Geist": _IP(name="Geist")}))
    save_item_scan(_ISC(name="Inventar", slot_names=["Gibt es nicht"],
                        item_names=["Geist", "Auch weg"]))
    _kaputt = _b.werkzeug_pruefen()
    _texte = " | ".join(f"{x['bereich']} {x['text']}" for x in _kaputt["befunde"])
    check("ein toter Slot-Verweis wird gemeldet", "Gibt es nicht" in _texte)
    check("ein totes Item ebenso", "Auch weg" in _texte)
    check("Fehler und Hinweise werden getrennt gezaehlt",
          _kaputt["fehler"] >= 2 and _kaputt["hinweise"] >= 1)
    # Gelesen wird von PLATTE, nicht aus dem, was die Reiter offen haben - sonst
    # meldete die Pruefung "sauber", weil sie die halben Daten gar nicht kennt.
    check("gelesen wird vom gespeicherten Stand", _kaputt["ok"])
finally:
    _os.chdir(_cwd)


# ---------------------------------------------------------------- Kalibrieren

section("Studio-Werkzeuge: kalibrieren")
try:
    _sand, _b = _sandkasten()
    check("ohne Referenzpunkt gibt es nichts anzuwenden",
          _b.kalib_anwenden({})["ok"] is False)

    _erg = _b.kalib_referenz({"nummer": 1, "punkt_id": 1})
    check("der Referenzpunkt laesst sich anfahren", _erg["ok"])
    _K = _b.werkzeug_daten()["kalibrierung"]
    check("und ergibt den gemessenen Versatz",
          _K["versatz"] == {"x": 40.0, "y": 30.0})
    check("die Vorschau zeigt, was sich aendern wuerde", len(_K["vorschau"]) == 3)

    # Der zweite Punkt muss ein anderer sein - sonst waere die Skalierung eine
    # Division durch null.
    check("derselbe Punkt zweimal wird abgelehnt",
          _b.kalib_referenz({"nummer": 2, "punkt_id": 1})["ok"] is False)

    # Von Hand nachziehen: mit der Maus trifft man den Pixel nicht genau.
    check("der Versatz laesst sich von Hand setzen",
          _b.kalib_versatz({"x": 50, "y": 0})["ok"])
    check("und steht dann so da",
          _b.werkzeug_daten()["kalibrierung"]["versatz"] == {"x": 50.0, "y": 0.0})
    check("Buchstaben statt Zahlen werden abgelehnt",
          _b.kalib_versatz({"x": "viel"})["ok"] is False)

    _erg = _b.kalib_anwenden({"mit_scans": True, "mit_sequenzen": True,
                              "mit_slots": False})
    check("angewendet wird mit Meldung", _erg["ok"] and "Kalibriert" in _erg["meldung"])
    check("und es entsteht eine Sicherung vorher",
          bool(_erg["sicherung"]) and _P(_erg["sicherung"]).exists())

    _punkte = {p["id"]: (p["x"], p["y"]) for p in _b.werkzeug_daten()["punkte"]}
    check("jeder Punkt ist um den Versatz gewandert",
          _punkte == {1: (150, 100), 2: (950, 600), 3: (450, 300)})
    # Der Reiter liest die Punkte danach neu ein - sonst zeigte er den Stand von
    # vor der Kalibrierung, waehrend auf Platte der neue steht.
    check("und der Reiter zeigt den neuen Stand",
          [(p.id, p.x) for p in _b.points] == [(1, 150), (2, 950), (3, 450)])

    _slot = _js.loads(_P("slots/slots.json").read_text(encoding="utf-8"))["Slot 1"]
    check("die Slots bleiben stehen, wenn ihr Haken aus ist",
          tuple(_slot["scan_region"]) == (10, 20, 70, 80))
    check("nach dem Anwenden laeuft keine Kalibrierung mehr",
          _b.werkzeug_daten()["kalibrierung"] == {})
finally:
    _os.chdir(_cwd)


section("Studio-Werkzeuge: was die Kalibrierung NICHT tut")
try:
    _sand, _b = _sandkasten()
    # Ein Punkt, der sich nicht bewegt hat, ergibt einen Transform ohne Wirkung.
    # Ihn anzuwenden waere ein Schreibvorgang samt Sicherung fuer nichts.
    _b._stelle_abwarten = lambda: (100, 100, "")
    _b.kalib_referenz({"nummer": 1, "punkt_id": 1})
    check("ein Transform ohne Wirkung wird abgelehnt",
          _b.kalib_anwenden({})["ok"] is False)
    check("und die Ansicht sagt es vorher",
          _b.werkzeug_daten()["kalibrierung"]["identitaet"] is True)

    # Abbrechen darf nichts geschrieben haben - bis dahin steht alles nur im Kopf.
    _vorher = _P("sequences/points.json").read_text(encoding="utf-8")
    _b._stelle_abwarten = lambda: (500, 500, "")
    _b.kalib_referenz({"nummer": 1, "punkt_id": 1})
    check("abbrechen raeumt die Kalibrierung weg", _b.kalib_abbrechen()["ok"])
    check("und hat nichts geschrieben",
          _P("sequences/points.json").read_text(encoding="utf-8") == _vorher)
    check("danach ist der Stand leer", _b.werkzeug_daten()["kalibrierung"] == {})

    # Ein unbekannter Punkt ist kein Grund, irgendetwas zu rechnen.
    check("ein Punkt, den es nicht gibt, wird abgelehnt",
          _b.kalib_referenz({"nummer": 1, "punkt_id": 99})["ok"] is False)

    # Waehrend eines Laufs wird nicht umgerechnet: die Sequenz klickt sonst
    # mitten im Umbau auf halb verschobene Stellen.
    _b._stelle_abwarten = lambda: (140, 130, "")
    _b.kalib_referenz({"nummer": 1, "punkt_id": 1})
    _b._laeuft = lambda: True
    check("ein laufender Lauf blockiert das Anwenden",
          _b.kalib_anwenden({})["ok"] is False)
finally:
    _os.chdir(_cwd)


# --------------------------------------------------------- Vorschau doppelt?

section("Studio-Werkzeuge: die Vorschau zaehlt keine Stelle doppelt")
try:
    _sand, _b = _sandkasten()
    _b.kalib_referenz({"nummer": 1, "punkt_id": 1})
    _was = [z["was"] for z in _b.werkzeug_daten()["kalibrierung"]["vorschau"]]
    # Die Sequenz hat zwei Klick-Schritte, beide ueber `point_id`. Ihre x/y sind
    # abgeleitet und werden NICHT einzeln umgerechnet - sie hier zu listen hiesse,
    # dieselbe Aenderung zweimal zu versprechen.
    check("nur die Punkte selbst stehen drin", all(w.startswith("Punkt #") for w in _was))
    check("und kein Sequenz-Schritt daneben", not any("Seq " in w for w in _was))
    check("es sind genau so viele wie Punkte", len(_was) == 3)

    # Gegenprobe: ein Schritt OHNE Punkt hat seine eigene Stelle und gehoert sehr
    # wohl in die Liste - sonst raeumte der Fix zu viel weg.
    from autoclicker.import_export import collect_click_positions
    _st = _ST()
    _st.points = [_CP(id=1, x=10, y=10, name="A")]
    _st.sequences["S"] = _SEQ(name="S", loop_phases=[_LP(name="L", steps=[
        _SS(x=70, y=80, point_id=None), _SS(x=10, y=10, point_id=1)])])
    _labels = [lb for lb, _, _ in collect_click_positions(_st)]
    check("ein Schritt ohne point_id bleibt sichtbar",
          any("Seq 'S'" in lb for lb in _labels))
    check("und der mit point_id nicht", sum("Seq 'S'" in lb for lb in _labels) == 1)
finally:
    _os.chdir(_cwd)


# ---------------------------------------------------------------- Klick-Runde

section("Studio-Werkzeuge: die Klick-Runde geht an den Hauptprozess")
try:
    _sand, _b = _sandkasten()
    _bf.BEFEHL_DATEI = _P("befehl.json")
    check("gestartet wird ueber den Briefkasten", _b.nachklick_starten()["ok"])
    _auftrag = _bf.hole()
    check("und der Befehl heisst 'nachklick'",
          _auftrag is not None and _auftrag["befehl"] == "nachklick")
    # DIE Sache, die hier schiefgehen kann: der Hauptprozess hat womoeglich eine
    # ganz andere Sequenz geladen. Ohne die Datei klickt man eine Runde lang die
    # Punkte einer fremden Sequenz nach - und merkt es nicht, weil jeder Klick
    # ja im Spiel etwas tut.
    check("die offene Sequenz kommt MIT",
          _P(_auftrag["argumente"].get("datei", "")).exists())
    check("und der Knopf sagt, welche er meint",
          "Farm" in _b.nachklick_starten()["meldung"])
    _bf.hole()

    # Ungespeichertes zuerst: die Runde klickt die Sequenz von PLATTE nach.
    _b._dirty = True
    _erg = _b.nachklick_starten()
    check("mit offenen Aenderungen wird nicht gestartet", _erg["ok"] is False)
    check("und der Grund steht dabei", "speichern" in _erg["meldung"].lower())
    check("es liegt auch kein Befehl im Briefkasten", _bf.hole() is None)

    _b._dirty = False
    _b._laeuft = lambda: True
    check("waehrend eines Laufs auch nicht", _b.nachklick_starten()["ok"] is False)
finally:
    _os.chdir(_cwd)


section("Studio-Werkzeuge: die Klick-Runde nimmt die MITGESCHICKTE Sequenz")
try:
    _sand, _b = _sandkasten()
    # Der Hauptprozess haelt eine andere Sequenz aktiv als die im Studio offene -
    # genau der Fall, in dem die alte Fassung die falsche nachklicken liess.
    _fremd = _SEQ(name="Fremd", loop_phases=[_LP(name="X", steps=[_SS(point_id=3)])])
    _st2 = _ST()
    _st2.points = [_CP(id=1, x=100, y=100, name="Sammeln"),
                   _CP(id=2, x=900, y=600, name="Bestaetigen"),
                   _CP(id=3, x=400, y=300, name="Menue")]
    _st2.sequences["Fremd"] = _fremd
    _st2.active_sequence = _fremd
    save_data(_st2)

    from autoclicker.handlers import befehl_nachklick as _bn
    import autoclicker.editors.nachklick as _nk
    _gestartet = {}

    def _fake_start(state):
        _gestartet["name"] = state.active_sequence.name
        return True

    _echt = _nk.start_nachklick
    _nk.start_nachklick = _fake_start
    try:
        _farm_pfad = str(dict(list_available_sequences())["Farm"])
        _bn(_st2, {"datei": _farm_pfad})
        check("geladen wird die mitgeschickte Datei", _gestartet.get("name") == "Farm")
        check("und sie wird auch aktiv gesetzt",
              _st2.active_sequence is not None and _st2.active_sequence.name == "Farm")

        # Ohne Datei passiert NICHTS - lieber gar keine Runde als eine auf der
        # falschen Sequenz.
        _gestartet.clear()
        _bn(_st2, {})
        check("ohne Datei startet keine Runde", not _gestartet)

        _gestartet.clear()
        _bn(_st2, {"datei": "sequences/gibtsnicht.json"})
        check("und eine unlesbare Datei startet auch keine", not _gestartet)
    finally:
        _nk.start_nachklick = _echt
finally:
    _os.chdir(_cwd)


# ------------------------------------------------------- Farbe gegenpruefen

section("Studio-Werkzeuge: ein Referenzpunkt mit falscher Farbe fragt nach")
try:
    _sand, _b = _sandkasten()
    # Punkt #1 bekommt eine gespeicherte Farbe; die Stelle, die angefahren wird,
    # zeigt eine ganz andere.
    _b.points[0].color = (10, 200, 30)
    _b._farbe_an = staticmethod(lambda x, y: (200, 10, 30))

    _erg = _b.kalib_referenz({"nummer": 1, "punkt_id": 1})
    check("gesetzt wird erst mal nichts", _erg["ok"] is False)
    check("stattdessen kommt eine Rueckfrage", _erg.get("bestaetigen") is True)
    check("mit beiden Farben zum Vergleich",
          _erg["erwartet"] == [10, 200, 30] and _erg["gemessen"] == [200, 10, 30])
    check("und dem Abstand samt erlaubter Toleranz",
          _erg["abstand"] == 190 and _erg["toleranz"] >= 0)
    check("die Kalibrierung ist noch leer", _b.werkzeug_daten()["kalibrierung"] == {})

    # Bestaetigt gilt der Punkt trotzdem - manchmal hat sich das Spiel geaendert.
    _erg = _b.kalib_referenz({"nummer": 1, "punkt_id": 1, "bestaetigt": True})
    check("bestaetigt wird er gesetzt", _erg["ok"])
    check("und die Meldung sagt, dass die Farbe abweicht", "weicht ab" in _erg["meldung"])
    check("jetzt steht die Kalibrierung",
          _b.werkzeug_daten()["kalibrierung"]["versatz"] == {"x": 40.0, "y": 30.0})
finally:
    _os.chdir(_cwd)


section("Studio-Werkzeuge: wann NICHT nach der Farbe gefragt wird")
try:
    _sand, _b = _sandkasten()
    # Passende Farbe: keine Rueckfrage, direkt gesetzt.
    _b.points[0].color = (10, 200, 30)
    _b._farbe_an = staticmethod(lambda x, y: (12, 198, 33))
    _erg = _b.kalib_referenz({"nummer": 1, "punkt_id": 1})
    check("eine passende Farbe geht direkt durch", _erg["ok"])
    check("und sagt es auch", "passt" in _erg["meldung"])

    # Ein Punkt OHNE gespeicherte Farbe hat nichts, womit man vergleichen kann.
    # Eine Rueckfrage ohne Grundlage gewoehnt man sich ab wegzuklicken.
    _b.kalib_abbrechen()
    _b.points[1].color = None
    _b._farbe_an = staticmethod(lambda x, y: (200, 10, 30))
    check("ein Punkt ohne Farbe fragt nicht",
          _b.kalib_referenz({"nummer": 1, "punkt_id": 2})["ok"])

    # Und wenn der Bildschirm sich nicht lesen laesst, ebenfalls nicht.
    _b.kalib_abbrechen()
    _b.points[0].color = (10, 200, 30)
    _b._farbe_an = staticmethod(lambda x, y: None)
    check("eine unlesbare Stelle fragt auch nicht",
          _b.kalib_referenz({"nummer": 1, "punkt_id": 1})["ok"])
finally:
    _os.chdir(_cwd)


section("Studio-Werkzeuge: die Klick-Runde laesst sich beenden")
try:
    _sand, _b = _sandkasten()
    _bf.BEFEHL_DATEI = _P("befehl.json")
    check("beenden geht ueber den Briefkasten", _b.nachklick_beenden()["ok"])
    _auftrag = _bf.hole()
    check("und heisst 'nachklick_stop'",
          _auftrag is not None and _auftrag["befehl"] == "nachklick_stop")

    # Der Hauptprozess sagt, was er vorgefunden hat - hier wird nicht geraten.
    from autoclicker.handlers import befehl_nachklick_stop as _bns
    import autoclicker.editors.nachklick as _nk
    _st3 = _ST()
    _gestoppt = {}
    _echt = _nk.stop_nachklick
    _nk.stop_nachklick = lambda state, grund="beendet": _gestoppt.setdefault("grund", grund)
    try:
        _bns(_st3, {})
        check("ohne laufende Runde passiert nichts", not _gestoppt)
        _st3.nachklick_aktiv = True
        _bns(_st3, {})
        check("mit laufender Runde wird gestoppt", "grund" in _gestoppt)
    finally:
        _nk.stop_nachklick = _echt
finally:
    _os.chdir(_cwd)
