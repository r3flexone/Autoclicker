"""Reiter „Werkzeuge": prüfen, kalibrieren, Klick-Runde starten."""

from ._harness import check, section

import json as _js
import os as _os
import tempfile as _tf
from pathlib import Path as _P

from autoclicker.editors.sequence_studio.bridge import StudioBridge as _SB
from autoclicker.editors.sequence_studio.bridge_tools import CALIB_EXTENT
from autoclicker.models import (
    AutoClickerState as _ST, ClickPoint as _CP, ItemProfile as _IP,
    ItemScanConfig as _ISC, ItemSlot as _IS, LoopPhase as _LP, Sequence as _SEQ,
    SequenceStep as _SS,
)
from autoclicker.persistence import (
    list_available_item_scans, list_available_sequences, save_data, save_item_scan,
)
import autoclicker.mailbox as _bf


def _sandbox_dir():
    """Ein vollständiger kleiner Bestand auf Platte, plus die Brücke darauf."""
    sandbox_dir = _tf.mkdtemp(prefix="wz_")
    _os.chdir(sandbox_dir)
    _P("sequences").mkdir()

    st = _ST()
    points = [_CP(id=1, x=100, y=100, name="Sammeln"),
              _CP(id=2, x=900, y=600, name="Bestaetigen"),
              _CP(id=3, x=400, y=300, name="Menue")]
    seq = _SEQ(name="Farm", loop_phases=[_LP(name="A", steps=[
        _SS(point_id=1, delay_before=3.0), _SS(point_id=2)])], points=points)
    st.sequences["Farm"] = seq
    st.active_sequence = seq
    st.points = seq.points
    save_data(st)
    save_item_scan(_ISC(
        name="Inventar", owner_sequence="Farm",
        slots=[_IS(name="Slot 1", scan_region=(10, 20, 70, 80),
                   click_pos=(40, 50))],
        items=[_IP(name="Bekannt", marker_colors=[(20, 40, 60)])],
    ))
    # Den Pfad NICHT von Hand bauen: `save_data` bereinigt den Namen (klein, ohne
    # Sonderzeichen), und die App holt ihn ueber `list_available_sequences()`. Ein
    # getippter Pfad geht daran vorbei - und genau der Unterschied entscheidet,
    # ob die Klick-Runde ihre Datei findet.
    bridge = _SB(seq, _P(dict(list_available_sequences())["Farm"]), "sequences")
    # Die Maus gibt es im Test nicht: die Stelle kommt aus dem Stub, alles
    # andere laeuft wie im Fenster.
    bridge._await_position = lambda: (140, 130, "")
    return sandbox_dir, bridge


_cwd = _os.getcwd()

# Die Werkzeuge sind keine drei Textblöcke mehr. Diese Prüfung misst beide
# Seiten des Vertrags: JavaScript baut die visuellen Bausteine, CSS gibt ihnen
# eine eigene Gestalt. Fehlt eine Seite, bleibt der Reiter technisch bedienbar,
# sieht aber wieder wie unformatierter Hilfetext aus.
section("Studio-Werkzeuge: visuelle Hierarchie")
_web = _P(__file__).resolve().parents[2] / "autoclicker/editors/sequence_studio/web"
_app = (_web / "app.js").read_text(encoding="utf-8")
_css = (_web / "styles.css").read_text(encoding="utf-8")
check("jedes Werkzeug hat ein eigenes Linien-Icon",
      all(f'{k}:' in _app for k in ("check", "calibrate", "reclick"))
      and "function wzIcon(" in _app)
check("Werkzeugkarten statt einfacher Textknöpfe",
      'class: "wz-nav "' in _app and ".wz-nav{" in _css)
check("der Inhalt beginnt mit einem gestalteten Werkzeugkopf",
      "function wzHeader(" in _app and ".wz-hero{" in _css)
check("Prüfergebnisse haben Kennzahlen und Zustandskarten",
      "function wzMetric(" in _app and ".wz-metrics{" in _css
      and ".wz-success{" in _css)
check("Erklärtexte stecken im einheitlichen i statt in offenen Kästen",
      'function wzInfo(' in _app and 'info(text, "werkzeug-" + title)' in _app
      and ".wz-info-compact{" in _css and ".wz-info{" not in _css)
check("das i ist eine einzelne SVG-Glyphe statt doppelt gerendertem Text",
      'class: "info-glyph"' in _app
      and '"data-help": key || text}, "i")' not in _app
      and 'r: "6.5"' in _app and ".info-glyph{" in _css
      and 'styles.css?v=' in (_web / "index.html").read_text(encoding="utf-8")
      and 'app.js?v=' in (_web / "index.html").read_text(encoding="utf-8"))

# --------------------------------------------------------------------- Prüfen

section("Studio-Werkzeuge: pruefen findet, was der Konsolen-`check` findet")
try:
    _sandbox, _b = _sandbox_dir()
    _d = _b.tool_data()
    check("die Punkte stehen zur Auswahl", [p["id"] for p in _d["points"]] == [1, 2, 3])
    # Die Kopfleiste blendet ihre Sequenz-Bedienelemente in diesem Reiter aus.
    # Ohne diese Angabe stuende nirgends, welche Sequenz die Klick-Runde meint.
    # Der NAME behaelt seine Schreibweise, der Dateiname wird entschaerft. Beide
    # stehen da, weil beide vorkommen: den Namen sucht man im Fenster, den
    # Dateinamen im Ordner.
    check("und der Reiter weiss, welche Sequenz offen ist", _d["sequence"] == "Farm")
    check("samt Ordnernamen, wie er auf Platte heisst",
          _d["file"] == _b.filepath.parent.name
          and _P("sequences", _d["file"], "sequence.json").exists())
    check("samt der Frage, ob sie ungespeichert ist", _d["open"] is False)
    _b._dirty = True
    check("und die Antwort aendert sich mit", _b.tool_data()["open"] is True)
    _b._dirty = False
    check("und der Umfang kommt aus der Tabelle",
          [u["key"] for u in _d["scope"]] == [k for k, _, _ in CALIB_EXTENT])
    # Die Ansicht zeigt dieselben Schalter; laufen sie auseinander, schaltet ein
    # Haken etwas anderes als beschriftet.
    check("Slots sind standardmaessig AUS",
          {u["key"]: u["default_value"] for u in _d["scope"]}["with_slots"] is False)

    _clean = _b.tool_check()
    check("ein sauberer Bestand meldet nichts", _clean["ok"] and not _clean["findings"])
    check("und sagt trotzdem, was geprueft wurde", len(_clean["checked"]) > 0)

    # Jetzt absichtlich kaputt: ein lokaler Scan ohne Slot und Erkennung.
    save_item_scan(_ISC(name="Inventar", owner_sequence="Farm"))
    _broken = _b.tool_check()
    _texts = " | ".join(f"{x['area']} {x['text']}" for x in _broken["findings"])
    check("ein Scan ohne Slot wird gemeldet", "kein einziger Slot" in _texts)
    check("ein Scan ohne Erkennung ebenso", "keine aktiven Items" in _texts)
    check("Fehler und Hinweise werden getrennt gezaehlt",
          _broken["errors"] >= 1 and _broken["hints"] >= 1)
    # Gelesen wird von PLATTE, nicht aus dem, was die Reiter offen haben - sonst
    # meldete die Pruefung "sauber", weil sie die halben Daten gar nicht kennt.
    check("gelesen wird vom gespeicherten Stand", _broken["ok"])
finally:
    _os.chdir(_cwd)


# ---------------------------------------------------------------- Kalibrieren

section("Studio-Werkzeuge: kalibrieren")
try:
    _sandbox, _b = _sandbox_dir()
    check("ohne Referenzpunkt gibt es nichts anzuwenden",
          _b.calib_apply({})["ok"] is False)

    _res = _b.calib_reference({"number": 1, "point_id": 1})
    check("der Referenzpunkt laesst sich anfahren", _res["ok"])
    _K = _b.tool_data()["calibration"]
    check("und ergibt den gemessenen Versatz",
          _K["offset"] == {"x": 40.0, "y": 30.0})
    check("die Vorschau zeigt, was sich aendern wuerde", len(_K["preview"]) == 3)

    # Der zweite Punkt muss ein anderer sein - sonst waere die Skalierung eine
    # Division durch null.
    check("derselbe Punkt zweimal wird abgelehnt",
          _b.calib_reference({"number": 2, "point_id": 1})["ok"] is False)

    # Von Hand nachziehen: mit der Maus trifft man den Pixel nicht genau.
    check("der Versatz laesst sich von Hand setzen",
          _b.calib_offset({"x": 50, "y": 0})["ok"])
    check("und steht dann so da",
          _b.tool_data()["calibration"]["offset"] == {"x": 50.0, "y": 0.0})
    check("Buchstaben statt Zahlen werden abgelehnt",
          _b.calib_offset({"x": "viel"})["ok"] is False)

    _res = _b.calib_apply({"with_scans": True, "with_sequences": True,
                              "with_slots": False})
    check("angewendet wird mit Meldung", _res["ok"] and "Kalibriert" in _res["message"])
    check("und es entsteht eine Sicherung vorher",
          bool(_res["backup"]) and _P(_res["backup"]).exists())

    _points = {p["id"]: (p["x"], p["y"]) for p in _b.tool_data()["points"]}
    check("jeder Punkt ist um den Versatz gewandert",
          _points == {1: (150, 100), 2: (950, 600), 3: (450, 300)})
    # Der Reiter liest die Punkte danach neu ein - sonst zeigte er den Stand von
    # vor der Kalibrierung, waehrend auf Platte der neue steht.
    check("und der Reiter zeigt den neuen Stand",
          [(p.id, p.x) for p in _b.points] == [(1, 150), (2, 950), (3, 450)])

    _scan_path = dict(list_available_item_scans("Farm"))["Inventar"]
    _slot = _js.loads(_scan_path.read_text(encoding="utf-8"))["slots"]["Slot 1"]
    check("die Slots bleiben stehen, wenn ihr Haken aus ist",
          tuple(_slot["scan_region"]) == (10, 20, 70, 80))
    check("nach dem Anwenden laeuft keine Kalibrierung mehr",
          _b.tool_data()["calibration"] == {})
finally:
    _os.chdir(_cwd)


section("Studio-Werkzeuge: was die Kalibrierung NICHT tut")
try:
    _sandbox, _b = _sandbox_dir()
    # Ein Punkt, der sich nicht bewegt hat, ergibt einen Transform ohne Wirkung.
    # Ihn anzuwenden waere ein Schreibvorgang samt Sicherung fuer nichts.
    _b._await_position = lambda: (100, 100, "")
    _b.calib_reference({"number": 1, "point_id": 1})
    check("ein Transform ohne Wirkung wird abgelehnt",
          _b.calib_apply({})["ok"] is False)
    check("und die Ansicht sagt es vorher",
          _b.tool_data()["calibration"]["identity"] is True)

    # Abbrechen darf nichts geschrieben haben - bis dahin steht alles nur im Kopf.
    _sequence_file = _P("sequences/farm/sequence.json")
    _before = _sequence_file.read_text(encoding="utf-8")
    _b._await_position = lambda: (500, 500, "")
    _b.calib_reference({"number": 1, "point_id": 1})
    check("abbrechen raeumt die Kalibrierung weg", _b.calib_cancel()["ok"])
    check("und hat nichts geschrieben",
          _sequence_file.read_text(encoding="utf-8") == _before)
    check("danach ist der Stand leer", _b.tool_data()["calibration"] == {})

    # Ein unbekannter Punkt ist kein Grund, irgendetwas zu rechnen.
    check("ein Punkt, den es nicht gibt, wird abgelehnt",
          _b.calib_reference({"number": 1, "point_id": 99})["ok"] is False)

    # Waehrend eines Laufs wird nicht umgerechnet: die Sequenz klickt sonst
    # mitten im Umbau auf halb verschobene Stellen.
    _b._await_position = lambda: (140, 130, "")
    _b.calib_reference({"number": 1, "point_id": 1})
    _b._running = lambda: True
    check("ein laufender Lauf blockiert das Anwenden",
          _b.calib_apply({})["ok"] is False)
finally:
    _os.chdir(_cwd)


# --------------------------------------------------------- Vorschau doppelt?

section("Studio-Werkzeuge: die Vorschau zaehlt keine Stelle doppelt")
try:
    _sandbox, _b = _sandbox_dir()
    _b.calib_reference({"number": 1, "point_id": 1})
    _was = [z["what"] for z in _b.tool_data()["calibration"]["preview"]]
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
    _st.sequences["S"] = _SEQ(name="S", points=[_CP(id=1, x=10, y=10, name="A")],
                              loop_phases=[_LP(name="L", steps=[
        _SS(x=70, y=80, point_id=None), _SS(x=10, y=10, point_id=1)])])
    _labels = [lb for lb, _, _ in collect_click_positions(_st)]
    check("ein Schritt ohne point_id bleibt sichtbar",
          any("Seq 'S'" in lb for lb in _labels))
    check("und der mit point_id nicht", sum("Seq 'S'" in lb for lb in _labels) == 1)
finally:
    _os.chdir(_cwd)


# ---------------------------------------------------------------- Klick-Runde

section("Studio: Sequenz-Aufnahme geht an den Hauptprozess")
try:
    _sandbox, _b = _sandbox_dir()
    _bf.COMMAND_PATH = _P("command.json")
    check("der Studio-Knopf kann eine Aufnahme starten",
          _b.recording_start({"name": "Aufnahme UI", "cycles": 3,
                               "description": "sichtbar"})["ok"])
    _job = _bf.fetch_command()
    check("und schickt genau den begrenzten Aufnahme-Befehl",
          _job is not None and _job["command"] == "recording")
    check("alle Angaben stehen vor dem Spielen fest",
          _job["arguments"] == {"name": "aufnahme_ui", "cycles": 3,
                                     "description": "sichtbar"})
    check("auch Stoppen geht sichtbar im Studio", _b.recording_stop()["ok"])
    _stopp = _bf.fetch_command()
    check("und sendet den eigenen Stopp-Befehl",
          _stopp is not None and _stopp["command"] == "recording_stop")
    _html = (_web / "index.html").read_text(encoding="utf-8")
    check("der sichtbare Knopf steht unter Notiz und ueber den Punkten",
          _html.index('id="seq-info"') < _html.index('id="btn-recording"') <
          _html.index('id="points-count"'))
    check("der reine Werkzeug-Verweis braucht kein Info-i",
          "aufnahme-info" not in _html)
    check("die Blockanzahl bleibt eine berechnete Ausgabe",
          '<output class="mono" id="seq-blocks">' in _html)
    _js = (_web / "app.js").read_text(encoding="utf-8")
    check("auch JavaScript baut dort kein Info-i mehr",
          "aufnahme-info" not in _js)
    check("der Editor-Knopf verweist auf das Werkzeug",
          'wzOpen("recording")' in _js)
    check("Start, Stopp und automatisches Oeffnen sind im UI verdrahtet",
          all(word in _js for word in ("wzStartRecording", "wzStopRecording",
                                       "wzWatchRecording")))
    from autoclicker.editors.sequence_recorder import RECORDING_HOTKEYS
    check("alle Aufnahme-Hotkeys kommen aus derselben Quelle",
          _b.tool_data()["recording_keys"] ==
          [list(line) for line in RECORDING_HOTKEYS])
finally:
    _os.chdir(_cwd)


section("Studio-Werkzeuge: Punkte sind vollständig verwaltbar")
try:
    _sandbox, _b = _sandbox_dir()
    _data = _b.tool_data()
    _p1 = next(p for p in _data["points"] if p["id"] == 1)
    check("Verwendungen stehen am Punkt", any("Block 1" in v for v in _p1["usages"]))
    _res = _b.tool_point_delete({"point_id": 1})
    check("ein verwendeter Punkt wird nicht gelöscht",
          not _res["ok"] and _b._point_with_id(1) is not None)
    check("der Löschschutz nennt die Verwendungen", bool(_res.get("usages")))

    _b._await_position = lambda: (333, 444, "")
    _b._color_at = staticmethod(lambda x, y: (12, 34, 56))
    _res = _b.tool_point_capture({"name": "Neu"})
    _new = _b._point_with_id(_res.get("point_id"))
    check("ein freier Punkt lässt sich im Studio aufnehmen",
          _res["ok"] and (_new.x, _new.y) == (333, 444))
    check("die Farbe wird dabei mitgemessen", _new.color == (12, 34, 56))
    check("und die Sequenz ist danach ungespeichert", _b._dirty)

    _res = _b.tool_colors({"kind": "point"})
    check("der Farbanalysator liefert RGB und Hex",
          _res["ok"] and _res["colors"][0]["rgb"] == [12, 34, 56]
          and _res["colors"][0]["hex"] == "#0C2238")
finally:
    _os.chdir(_cwd)


section("Studio: Phasen-Zeiten skalieren und Block testen")
try:
    _sandbox, _b = _sandbox_dir()
    _loop_index = next(i for i, lane in enumerate(_b.board.lanes) if lane.kind == "loop")
    _b.phase_scale({"phase": _loop_index, "factor": "0,5"})
    check("die Wartezeit wird mit deutschem Komma skaliert",
          _b.board.lanes[_loop_index].steps[0].delay_before == 1.5)
    _bf.COMMAND_PATH = _P("command.json")
    _b.select({"phase": _loop_index, "row": 0})
    _res = _b.block_test()
    _job = _bf.fetch_command()
    check("der Block-Test wird ausdrücklich angekündigt", "echter" in _res["status"]["text"])
    check("getestet wird nur die gespeicherte Blockposition",
          _job and _job["command"] == "block_test"
          and _job["arguments"]["phase"] == "loop"
          and _job["arguments"]["block"] == 0)
    _res = _b.run_command({"command": "skip_step"})
    _job = _bf.fetch_command()
    check("der echte Block-Skip wird ohne KeyError abgelegt und bestätigt",
          _job and _job["command"] == "skip_step"
          and "vollständig" in _res["status"]["text"])
finally:
    _os.chdir(_cwd)


section("Studio-Live-Run: alle Laufentscheidungen sind verdrahtet")
from autoclicker.handlers import COMMANDS as _BEFEHLE_NEU
check("Studio und Hauptprozess kennen dieselben Befehle",
      sorted(_SB.ALL_COMMANDS) == sorted(_BEFEHLE_NEU))
check("Warte- und Block-Skip, sanftes Ende, Schrittmodus und Zeitplan sind im Vertrag",
      {"skip", "skip_step", "finish", "start_manual", "manual_action", "schedule"}
      <= set(_SB.RUN_COMMANDS))
check("alle Laufentscheidungen haben sichtbare Knöpfe",
      all(text in _app for text in ("Warten überspringen", "Block überspringen",
                                    "Zyklus abschliessen",
                                    "Schrittweise", "Start planen", "Ausführen")))
# Die Auswahl ist SICHTBAR und ERREICHBAR — aber nicht mehr über ein Kästchen.
# Das sagte dasselbe wie der Amber-Ring, konnte nichts, was STRG+Klick nicht auch
# kann („dazu" ist derselbe Befehl), und ein Kästchen heisst im Rest des Fensters
# „gehört dazu"/„ist an". Geprüft wird deshalb die Eigenschaft, nicht das Bauteil:
# eine gewählte Karte trägt eine eigene Klasse, die Gesten stehen an der Karte,
# und „alle wählen" gibt es weiterhin.
check("die gewählte Blockkarte ist sichtbar markiert",
      '" selected"' in _app and '.card.selected{' in _css)
check("Mehrfachauswahl ist erreichbar und benannt",
      '"phase_selection"' in _app
      and 'e.ctrlKey || e.metaKey ? "add"' in _app
      and 'e.shiftKey ? "area" : "single"' in _app
      and "STRG+Klick" in _app)
check("kein Auswahl-Kästchen auf der Karte — der Ring sagt es schon",
      "karte-auswahl" not in _app and "karte-auswahl" not in _css)
check("Mehrfachauswahl hat gemeinsame Wartezeiten und den 0,5-s-Knopf",
      'function renderBulkEditor' in _app and '[0, 0.5, 1]' in _app)
check("leere Start- und Abschlussphasen werden nur bei Bedarf eingeblendet",
      'openSpecialPhases' in _app and "+ Startphase" in _app
      and "+ Abschlussphase" in _app)
check("der eindeutige Block-Test startet ohne zusätzlichen Browser-Dialog",
      'window.confirm("Diesen Block' not in _app)
check("unter den eindeutigen Aktionsknöpfen steht kein doppelter Erklärungstext",
      "Zeigen setzt nur die Maus" not in _app)
check("die Phasen-Skalierung ist am Knopf eindeutig benannt",
      "Wartezeiten ×" in _app and '"Zeit ×"' not in _app)
_position_ui = _app[_app.index("function buildPosition"):
                  _app.index("function setPosition")]
check("die Anleitung zum Maus-Setzen steht nur im Info-Text",
      "Mit ‚Stelle mit der Maus setzen‘" in _position_ui
      and 'el("p", {class: "hint"},\n    "Danach:' not in _position_ui)
_inspector_ui = _app[_app.index("function renderInspector"):
                     _app.index("/* -------------------------------------------------------------------- Dialog")]
# Offene Texte im Inspektor sind nur ZUSTAND, keine Bedienungsanleitung:
# fehlender Punkt, fehlende Scan-Datei, Screenshot-Mass, fehlender Prüfpunkt,
# ein ELSE, das wegen einer fehlenden Bedingung nicht greifen kann — und ein
# Punkt, den andere Blöcke mitbenutzen (wer, nicht warum; das steht im ⓘ).
check("alle Block-Typen haben nur noch sechs begründete offene Zustandsmeldungen",
      _inspector_ui.count('target.appendChild(el("p", {class: "hint') == 6)
check("die offenen Meldungen betreffen ausschließlich fehlende Daten oder Messwerte",
      all(text in _inspector_ui for text in (
          "Keine Punkte vorhanden", "Keine Konfiguration vorhanden", "Grösse: ",
          "Ohne Punkt gibt es nichts zu prüfen", "Dieser Block hat keine Bedingung",
          "wird auch benutzt von")))
check("die Erklärung der ELSE-Wirkung steckt im i statt unter den Kacheln",
      "const effect = b.else_action" in _inspector_ui
      and 'Nochmal auf die markierte Kachel klicken = kein ELSE.' not in _inspector_ui)

section("Studio-Aufnahme: kein unsichtbarer Prompt und kein UI-Klick im Block")
try:
    _sandbox, _b = _sandbox_dir()
    import time as _time
    import autoclicker.editors.sequence_recorder as _rec
    from autoclicker.models import AutoClickerState as _State, RecordEvent as _RE, REC_CLICK as _RC

    _st = _State()
    _st.recording_active = True
    _st.recording_events = [_RE(_RC, _time.monotonic(), 321, 456, (11, 22, 33))]
    _st.recording_ui_name = "aufnahme_ui"
    _st.recording_ui_cycles = 2
    _st.recording_ui_description = "ohne Konsole"
    _old_input = _rec.safe_input
    _old_mouse_gone = _rec.remove_mouse_hook
    _old_keys_gone = _rec.remove_keyboard_hook
    _rec.safe_input = lambda *_a, **_k: (_ for _ in ()).throw(
        AssertionError("UI-Aufnahme darf nichts in der Konsole fragen"))
    _rec.remove_mouse_hook = lambda: None
    _rec.remove_keyboard_hook = lambda: None
    try:
        _saved = _rec.stop_recording(_st)
    finally:
        _rec.safe_input = _old_input
        _rec.remove_mouse_hook = _old_mouse_gone
        _rec.remove_keyboard_hook = _old_keys_gone
    check("die UI-Vorgaben speichern ohne safe_input", _saved == "aufnahme_ui")
    from autoclicker.persistence import load_sequence_file as _load_sequence_file
    _loaded = _load_sequence_file(_rec.recording_file("aufnahme_ui"))
    check("die Aufnahme wird wirklich zur Sequenz", _loaded is not None)
    check("Zyklen und Notiz kommen aus dem UI",
          _loaded.total_cycles == 2 and _loaded.description == "ohne Konsole")
    check("und aus dem Ereignis entsteht ein Block", _loaded.total_steps() == 1)

    # **Gefragt wird das Fenster UNTER dem Klick, nicht der Vordergrund.** Die
    # Aufnahme wird mit einem Knopf im Studio gestartet, also ist das Studio
    # vorn — und der erste Klick ins Spiel holt es erst nach vorn. Im Hook
    # steht zu dem Zeitpunkt noch das Studio im Vordergrund; wer den fragt,
    # wirft genau diesen Klick weg. In jeder Studio-Aufnahme fehlte damit der
    # erste Schritt, und am Ende stand umgekehrt der Klick auf „Aufnahme
    # stoppen" als Spielklick in der Sequenz (gemessen: `(1347, 709)`, Farbe
    # `#1C2333` = Panel-Grau des Studios). Derselbe Fehler wie in der
    # Klick-Runde, deshalb derselbe Helfer — und dieselben vier Faelle.
    import autoclicker.editors._click_window as _kf
    _click_state = _State(recording_active=True)
    _front, _under = ["Idle Clans"], [None]   # None = wie der Vordergrund
    _old_front, _old_below = _kf.get_foreground_window_title, _kf.get_window_title_at
    _kf.get_foreground_window_title = lambda: _front[0]
    _kf.get_window_title_at = lambda x, y: (
        _front[0] if _under[0] is None else _under[0])
    _capture_fn = _rec._on_click_factory(_click_state)
    try:
        _front[0] = "Sequenz-Studio"
        _capture_fn(10, 20, (1, 2, 3))
        check("der Stopp-Klick im Studio wird nicht aufgenommen",
              not _click_state.recording_events)
        _front[0] = "Idle Clans"
        _capture_fn(10, 20, (1, 2, 3))
        check("derselbe Klick im Spiel wird aufgenommen",
              len(_click_state.recording_events) == 1)

        # Der Fall, an dem jede Studio-Aufnahme ihren ersten Schritt verlor.
        _front[0], _under[0] = "Sequenz-Studio", "Idle Clans"
        _capture_fn(4578, 490, (140, 77, 74))
        check("der erste Klick ins Spiel zaehlt, obwohl das Studio noch vorn ist",
              [(e.x, e.y) for e in _click_state.recording_events][-1] == (4578, 490))
        # Und der Klick auf „Aufnahme stoppen" bei vorn stehendem Spiel.
        _front[0], _under[0] = "Idle Clans", "Sequenz-Studio"
        _count = len(_click_state.recording_events)
        _capture_fn(1347, 709, (28, 35, 51))
        check("der Stopp-Klick zaehlt nicht, obwohl das Spiel noch vorn ist",
              len(_click_state.recording_events) == _count)
        # Ohne auffindbares Fenster gilt der Vordergrund — ein Filter, der
        # dann alles wegwirft, saehe aus wie ein kaputter Hook.
        _front[0], _under[0] = "Idle Clans", ""
        _capture_fn(5, 5, (0, 0, 0))
        check("ohne Fenster unter dem Zeiger entscheidet der Vordergrund",
              len(_click_state.recording_events) == _count + 1)
    finally:
        _kf.get_foreground_window_title = _old_front
        _kf.get_window_title_at = _old_below

    _live_events = [
        _RE(_RC, 1.00, 10, 20, (1, 2, 3)),
        _RE(_RC, 2.00, 11, 21, (20, 30, 40)),
        _RE(_RC, 4.61, 12, 22, (123, 51, 65)),
        _RE(_RC, 7.22, 1378, 756, (123, 51, 65)),
    ]
    _live = _rec._status_events(_live_events)
    check("die Live-Ausgabe behaelt genau die letzten drei", len(_live) == 3)
    check("ihre laufenden Nummern bleiben erhalten",
          [z["number"] for z in _live] == [2, 3, 4])
    check("Zeit, Klick und Farbname stehen getrennt zur Darstellung bereit",
          _live[-1]["time"] == "+2.61s" and
          _live[-1]["text"] == "Klick (1378, 756)" and
          "Dunkelrot (123,51,65)" in _live[-1]["color_text"])
    _live_state = _State(recording_active=True, recording_events=_live_events)
    _rec._write_status(_live_state)
    _read_value = _b.recording_status()
    check("die Bruecke liefert denselben ueberschriebenen Live-Stand",
          _read_value["count"] == 4 and len(_read_value["events"]) == 3)
finally:
    _os.chdir(_cwd)

section("Studio-Werkzeuge: die Klick-Runde geht an den Hauptprozess")
try:
    _sandbox, _b = _sandbox_dir()
    _bf.COMMAND_PATH = _P("command.json")
    check("gestartet wird ueber den Briefkasten", _b.reclick_start()["ok"])
    _job = _bf.fetch_command()
    check("und der Befehl heisst 'nachklick'",
          _job is not None and _job["command"] == "reclick")
    # DIE Sache, die hier schiefgehen kann: der Hauptprozess hat womoeglich eine
    # ganz andere Sequenz geladen. Ohne die Datei klickt man eine Runde lang die
    # Punkte einer fremden Sequenz nach - und merkt es nicht, weil jeder Klick
    # ja im Spiel etwas tut.
    check("die offene Sequenz kommt MIT",
          _P(_job["arguments"].get("file", "")).exists())
    check("und der Knopf sagt, welche er meint",
          "Farm" in _b.reclick_start()["message"])
    _bf.fetch_command()

    # Ungespeichertes zuerst: die Runde klickt die Sequenz von PLATTE nach.
    _b._dirty = True
    _res = _b.reclick_start()
    check("mit offenen Aenderungen wird nicht gestartet", _res["ok"] is False)
    check("und der Grund steht dabei", "speichern" in _res["message"].lower())
    check("es liegt auch kein Befehl im Briefkasten", _bf.fetch_command() is None)

    _b._dirty = False
    _b._running = lambda: True
    check("waehrend eines Laufs auch nicht", _b.reclick_start()["ok"] is False)
finally:
    _os.chdir(_cwd)


section("Studio-Werkzeuge: die Klick-Runde nimmt die MITGESCHICKTE Sequenz")
try:
    _sandbox, _b = _sandbox_dir()
    # Der Hauptprozess haelt eine andere Sequenz aktiv als die im Studio offene -
    # genau der Fall, in dem die alte Fassung die falsche nachklicken liess.
    _foreign = _SEQ(name="Fremd", loop_phases=[_LP(name="X", steps=[_SS(point_id=3)])])
    _st2 = _ST()
    _foreign.points = [_CP(id=1, x=100, y=100, name="Sammeln"),
                     _CP(id=2, x=900, y=600, name="Bestaetigen"),
                     _CP(id=3, x=400, y=300, name="Menue")]
    _st2.sequences["Fremd"] = _foreign
    _st2.active_sequence = _foreign
    save_data(_st2)

    from autoclicker.handlers import command_reclick as _bn
    import autoclicker.editors.reclick as _nk
    _started = {}

    def _fake_start(state, seq=None):
        _started["name"] = seq.name if seq is not None else None
        return True

    _real = _nk.start_reclick
    _nk.start_reclick = _fake_start
    try:
        _farm_path = str(dict(list_available_sequences())["Farm"])
        _bn(_st2, {"file": _farm_path})
        check("die Reihenfolge kommt aus der mitgeschickten Datei",
              _started.get("name") == "Farm")
        # **Die geladene Sequenz wechselt dabei NICHT.** Die Runde arbeitet auf
        # Punkten; welche Sequenz der Hauptprozess scharf hat, geht sie nichts
        # an - sonst startete CTRL+ALT+S danach etwas anderes als vorher.
        check("die geladene Sequenz bleibt, wie sie war",
              _st2.active_sequence is _foreign)

        # Ohne Datei passiert NICHTS - lieber gar keine Runde als eine auf der
        # falschen Sequenz.
        _started.clear()
        _bn(_st2, {})
        check("ohne Datei startet keine Runde", not _started)

        _started.clear()
        _bn(_st2, {"file": "sequences/gibtsnicht/sequence.json"})
        check("und eine unlesbare Datei startet auch keine", not _started)
    finally:
        _nk.start_reclick = _real
finally:
    _os.chdir(_cwd)


# ------------------------------------------------------- Farbe gegenpruefen

section("Studio-Werkzeuge: ein Referenzpunkt mit falscher Farbe fragt nach")
try:
    _sandbox, _b = _sandbox_dir()
    # Punkt #1 bekommt eine gespeicherte Farbe; die Stelle, die angefahren wird,
    # zeigt eine ganz andere.
    _b.points[0].color = (10, 200, 30)
    _b._color_at = staticmethod(lambda x, y: (200, 10, 30))

    _res = _b.calib_reference({"number": 1, "point_id": 1})
    check("gesetzt wird erst mal nichts", _res["ok"] is False)
    check("stattdessen kommt eine Rueckfrage", _res.get("confirm") is True)
    check("mit beiden Farben zum Vergleich",
          _res["expected"] == [10, 200, 30] and _res["measured"] == [200, 10, 30])
    check("und dem Abstand samt erlaubter Toleranz",
          _res["gap"] == 190 and _res["tolerance"] >= 0)
    check("die Kalibrierung ist noch leer", _b.tool_data()["calibration"] == {})

    # Bestaetigt gilt der Punkt trotzdem - manchmal hat sich das Spiel geaendert.
    _res = _b.calib_reference({"number": 1, "point_id": 1, "confirmed": True})
    check("bestaetigt wird er gesetzt", _res["ok"])
    check("und die Meldung sagt, dass die Farbe abweicht", "weicht ab" in _res["message"])
    check("jetzt steht die Kalibrierung",
          _b.tool_data()["calibration"]["offset"] == {"x": 40.0, "y": 30.0})
finally:
    _os.chdir(_cwd)


section("Studio-Werkzeuge: wann NICHT nach der Farbe gefragt wird")
try:
    _sandbox, _b = _sandbox_dir()
    # Passende Farbe: keine Rueckfrage, direkt gesetzt.
    _b.points[0].color = (10, 200, 30)
    _b._color_at = staticmethod(lambda x, y: (12, 198, 33))
    _res = _b.calib_reference({"number": 1, "point_id": 1})
    check("eine passende Farbe geht direkt durch", _res["ok"])
    check("und sagt es auch", "passt" in _res["message"])

    # Ein Punkt OHNE gespeicherte Farbe hat nichts, womit man vergleichen kann.
    # Eine Rueckfrage ohne Grundlage gewoehnt man sich ab wegzuklicken.
    _b.calib_cancel()
    _b.points[1].color = None
    _b._color_at = staticmethod(lambda x, y: (200, 10, 30))
    check("ein Punkt ohne Farbe fragt nicht",
          _b.calib_reference({"number": 1, "point_id": 2})["ok"])

    # Und wenn der Bildschirm sich nicht lesen laesst, ebenfalls nicht.
    _b.calib_cancel()
    _b.points[0].color = (10, 200, 30)
    _b._color_at = staticmethod(lambda x, y: None)
    check("eine unlesbare Stelle fragt auch nicht",
          _b.calib_reference({"number": 1, "point_id": 1})["ok"])
finally:
    _os.chdir(_cwd)


section("Studio-Werkzeuge: die Klick-Runde laesst sich beenden")
try:
    _sandbox, _b = _sandbox_dir()
    _bf.COMMAND_PATH = _P("command.json")
    check("beenden geht ueber den Briefkasten", _b.reclick_end()["ok"])
    _job = _bf.fetch_command()
    check("und heisst 'reclick_stop'",
          _job is not None and _job["command"] == "reclick_stop")

    # Der Hauptprozess sagt, was er vorgefunden hat - hier wird nicht geraten.
    from autoclicker.handlers import command_reclick_stop as _bns
    import autoclicker.editors.reclick as _nk
    _st3 = _ST()
    _gestoppt = {}
    _real = _nk.stop_reclick
    _nk.stop_reclick = lambda state, reason="beendet": _gestoppt.setdefault("reason", reason)
    try:
        _bns(_st3, {})
        check("ohne laufende Runde passiert nichts", not _gestoppt)
        _st3.reclick_active = True
        _bns(_st3, {})
        check("mit laufender Runde wird gestoppt", "reason" in _gestoppt)
    finally:
        _nk.stop_reclick = _real
finally:
    _os.chdir(_cwd)


# ============================================================================
section("Jeder Griff mit der Maus sagt, dass er wartet")

# `_await_position()` und `area_capture()` warten GLOBAL auf ENTER — bis zu
# WAIT_TIMEOUT Sekunden, und der Bruecken-Aufruf blockiert dabei. Die Seite
# bekommt in dieser Zeit keine Antwort, kann also nichts anzeigen, was von drueben
# kaeme: sie muss VOR dem Aufruf sagen, worauf gewartet wird. Ohne das sah es aus,
# als tue das Fenster nichts — eine Minute lang.
#
# Der Test misst beide Seiten gegeneinander, statt eine abzuschreiben: welche
# Methoden warten, steht in der Bruecke; dass die Seite sie mit Hinweis ruft,
# steht in app.js.
import re as _re_wt
from pathlib import Path as _P_wt

_studio_wt = _P_wt(__file__).resolve().parent.parent.parent / "autoclicker" / "editors" / "sequence_studio"
_sources_wt = {n: (_studio_wt / f"{n}.py").read_text(encoding="utf-8")
               for n in ("bridge_editing", "bridge_tools")}
_appjs_wt = (_studio_wt / "web" / "app.js").read_text(encoding="utf-8")

# Welche oeffentlichen Methoden warten? Eine Methode wartet, wenn ihr Rumpf
# `_await_position()` oder `wait_for_global_key(` enthaelt.
_wartend = set()
for _text in _sources_wt.values():
    _parts = _re_wt.split(r"\n    def ", _text)
    for _part in _parts[1:]:
        _name = _part.split("(", 1)[0]
        if _name.startswith("_"):
            continue
        if "_await_position()" in _part or "wait_for_global_key(" in _part:
            _wartend.add(_name)

check("der Test findet ueberhaupt wartende Methoden", len(_wartend) >= 5)

_table_wt = _appjs_wt[_appjs_wt.index("const WAIT_ACTIONS = {"):]
_table_wt = _table_wt[:_table_wt.index("};")]
_named = set(_re_wt.findall(r"^\s*(\w+):\s*\[", _table_wt, _re_wt.M))

_missing = sorted(_wartend - _named)
check("jede wartende Bruecken-Methode steht in WAIT_ACTIONS", _missing == [])
if _missing:
    print("        ohne Hinweis: " + ", ".join(_missing))

# Gegenrichtung: ein Eintrag fuer etwas, das gar nicht mehr wartet, verspricht
# einen Kasten, den niemand je sieht.
_too_many = sorted(_named - _wartend)
check("und kein Eintrag fuer etwas, das nicht wartet", _too_many == [])
if _too_many:
    print("        wartet gar nicht: " + ", ".join(_too_many))

# Und die Seite muss sie auch WIRKLICH ueber withWait() rufen — ein Eintrag in
# der Tabelle allein zeigt noch keinen Kasten.
for _m in sorted(_wartend):
    _direct = _re_wt.findall(r'(?:call|ask|callTool)\("' + _m + r'"', _appjs_wt)
    check(f"'{_m}' wird nur ueber withWait gerufen", not _direct)

# Die Zeitgrenze steht an EINER Stelle und wird mitgeliefert: ohne das liefe der
# Countdown der Seite neben dem echten Zeitablauf der Bruecke.
from autoclicker.editors.sequence_studio.bridge_contract import WAIT_TIMEOUT as _WT
check("die Zeitgrenze ist eine Konstante, kein Literal im Aufruf",
      all("timeout=60" not in t for t in _sources_wt.values()))
check("und sie steht in der Momentaufnahme",
      '"wait_timeout": WAIT_TIMEOUT' in
      (_studio_wt / "bridge_view.py").read_text(encoding="utf-8"))
check("wie auch in den Werkzeug-Daten",
      '"wait_timeout": WAIT_TIMEOUT' in _sources_wt["bridge_tools"])
check("der Wert ist eine sinnvolle Zeitgrenze", 10 <= _WT <= 300)
