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
    list_available_item_scans, list_available_sequences, save_data, save_item_scan,
)
import autoclicker.befehl as _bf


def _sandkasten():
    """Ein vollständiger kleiner Bestand auf Platte, plus die Brücke darauf."""
    sand = _tf.mkdtemp(prefix="wz_")
    _os.chdir(sand)
    _P("sequences").mkdir()

    st = _ST()
    punkte = [_CP(id=1, x=100, y=100, name="Sammeln"),
              _CP(id=2, x=900, y=600, name="Bestaetigen"),
              _CP(id=3, x=400, y=300, name="Menue")]
    seq = _SEQ(name="Farm", loop_phases=[_LP(name="A", steps=[
        _SS(point_id=1, delay_before=3.0), _SS(point_id=2)])], points=punkte)
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
    bruecke = _SB(seq, _P(dict(list_available_sequences())["Farm"]), "sequences")
    # Die Maus gibt es im Test nicht: die Stelle kommt aus dem Stub, alles
    # andere laeuft wie im Fenster.
    bruecke._stelle_abwarten = lambda: (140, 130, "")
    return sand, bruecke


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
      all(f'{k}:' in _app for k in ("pruefen", "kalibrieren", "klicken"))
      and "function wzIcon(" in _app)
check("Werkzeugkarten statt einfacher Textknöpfe",
      'class: "wz-nav "' in _app and ".wz-nav{" in _css)
check("der Inhalt beginnt mit einem gestalteten Werkzeugkopf",
      "function wzKopf(" in _app and ".wz-hero{" in _css)
check("Prüfergebnisse haben Kennzahlen und Zustandskarten",
      "function wzKennzahl(" in _app and ".wz-kennzahlen{" in _css
      and ".wz-erfolg{" in _css)
check("Erklärtexte stecken im einheitlichen i statt in offenen Kästen",
      'function wzInfo(' in _app and 'info(text, "werkzeug-" + titel)' in _app
      and ".wz-info-kompakt{" in _css and ".wz-info{" not in _css)
check("das i ist eine einzelne SVG-Glyphe statt doppelt gerendertem Text",
      'class: "info-glyphe"' in _app
      and '"data-hilfe": schluessel || text}, "i")' not in _app
      and 'r: "6.5"' in _app and ".info-glyphe{" in _css
      and 'styles.css?v=' in (_web / "index.html").read_text(encoding="utf-8")
      and 'app.js?v=' in (_web / "index.html").read_text(encoding="utf-8"))

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
    check("samt Ordnernamen, wie er auf Platte heisst",
          _d["datei"] == _b.filepath.parent.name
          and _P("sequences", _d["datei"], "sequence.json").exists())
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

    # Jetzt absichtlich kaputt: ein lokaler Scan ohne Slot und Erkennung.
    save_item_scan(_ISC(name="Inventar", owner_sequence="Farm"))
    _kaputt = _b.werkzeug_pruefen()
    _texte = " | ".join(f"{x['bereich']} {x['text']}" for x in _kaputt["befunde"])
    check("ein Scan ohne Slot wird gemeldet", "kein einziger Slot" in _texte)
    check("ein Scan ohne Erkennung ebenso", "keine aktiven Items" in _texte)
    check("Fehler und Hinweise werden getrennt gezaehlt",
          _kaputt["fehler"] >= 1 and _kaputt["hinweise"] >= 1)
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

    _scan_pfad = dict(list_available_item_scans("Farm"))["Inventar"]
    _slot = _js.loads(_scan_pfad.read_text(encoding="utf-8"))["slots"]["Slot 1"]
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
    _sequenzdatei = _P("sequences/farm/sequence.json")
    _vorher = _sequenzdatei.read_text(encoding="utf-8")
    _b._stelle_abwarten = lambda: (500, 500, "")
    _b.kalib_referenz({"nummer": 1, "punkt_id": 1})
    check("abbrechen raeumt die Kalibrierung weg", _b.kalib_abbrechen()["ok"])
    check("und hat nichts geschrieben",
          _sequenzdatei.read_text(encoding="utf-8") == _vorher)
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
    _sand, _b = _sandkasten()
    _bf.BEFEHL_DATEI = _P("befehl.json")
    check("der Studio-Knopf kann eine Aufnahme starten",
          _b.aufnahme_starten({"name": "Aufnahme UI", "zyklen": 3,
                               "beschreibung": "sichtbar"})["ok"])
    _auftrag = _bf.hole()
    check("und schickt genau den begrenzten Aufnahme-Befehl",
          _auftrag is not None and _auftrag["befehl"] == "aufnahme")
    check("alle Angaben stehen vor dem Spielen fest",
          _auftrag["argumente"] == {"name": "aufnahme_ui", "zyklen": 3,
                                     "beschreibung": "sichtbar"})
    check("auch Stoppen geht sichtbar im Studio", _b.aufnahme_stoppen()["ok"])
    _stopp = _bf.hole()
    check("und sendet den eigenen Stopp-Befehl",
          _stopp is not None and _stopp["befehl"] == "aufnahme_stop")
    _html = (_web / "index.html").read_text(encoding="utf-8")
    check("der sichtbare Knopf steht unter Notiz und ueber den Punkten",
          _html.index('id="seq-info"') < _html.index('id="btn-aufnahme"') <
          _html.index('id="punkte-zahl"'))
    check("der reine Werkzeug-Verweis braucht kein Info-i",
          "aufnahme-info" not in _html)
    check("die Blockanzahl bleibt eine berechnete Ausgabe",
          '<output class="mono" id="seq-bloecke">' in _html)
    _js = (_web / "app.js").read_text(encoding="utf-8")
    check("auch JavaScript baut dort kein Info-i mehr",
          "aufnahme-info" not in _js)
    check("der Editor-Knopf verweist auf das Werkzeug",
          'wzOeffnen("aufnahme")' in _js)
    check("Start, Stopp und automatisches Oeffnen sind im UI verdrahtet",
          all(wort in _js for wort in ("wzAufnahmeStarten", "wzAufnahmeStoppen",
                                       "wzAufnahmeBeobachten")))
    from autoclicker.editors.sequence_recorder import AUFNAHME_HOTKEYS
    check("alle Aufnahme-Hotkeys kommen aus derselben Quelle",
          _b.werkzeug_daten()["aufnahme_tasten"] ==
          [list(zeile) for zeile in AUFNAHME_HOTKEYS])
finally:
    _os.chdir(_cwd)


section("Studio-Werkzeuge: Punkte sind vollständig verwaltbar")
try:
    _sand, _b = _sandkasten()
    _daten = _b.werkzeug_daten()
    _p1 = next(p for p in _daten["punkte"] if p["id"] == 1)
    check("Verwendungen stehen am Punkt", any("Block 1" in v for v in _p1["verwendungen"]))
    _erg = _b.werkzeug_punkt_loeschen({"punkt_id": 1})
    check("ein verwendeter Punkt wird nicht gelöscht",
          not _erg["ok"] and _b._punkt_mit_id(1) is not None)
    check("der Löschschutz nennt die Verwendungen", bool(_erg.get("verwendungen")))

    _b._stelle_abwarten = lambda: (333, 444, "")
    _b._farbe_an = staticmethod(lambda x, y: (12, 34, 56))
    _erg = _b.werkzeug_punkt_aufnehmen({"name": "Neu"})
    _neu = _b._punkt_mit_id(_erg.get("punkt_id"))
    check("ein freier Punkt lässt sich im Studio aufnehmen",
          _erg["ok"] and (_neu.x, _neu.y) == (333, 444))
    check("die Farbe wird dabei mitgemessen", _neu.color == (12, 34, 56))
    check("und die Sequenz ist danach ungespeichert", _b._dirty)

    _erg = _b.werkzeug_farben({"art": "punkt"})
    check("der Farbanalysator liefert RGB und Hex",
          _erg["ok"] and _erg["farben"][0]["rgb"] == [12, 34, 56]
          and _erg["farben"][0]["hex"] == "#0C2238")
finally:
    _os.chdir(_cwd)


section("Studio: Phasen-Zeiten skalieren und Block testen")
try:
    _sand, _b = _sandkasten()
    _loop_index = next(i for i, lane in enumerate(_b.board.lanes) if lane.kind == "loop")
    _b.phase_skalieren({"phase": _loop_index, "faktor": "0,5"})
    check("die Wartezeit wird mit deutschem Komma skaliert",
          _b.board.lanes[_loop_index].steps[0].delay_before == 1.5)
    _bf.BEFEHL_DATEI = _P("befehl.json")
    _b.waehlen({"phase": _loop_index, "zeile": 0})
    _erg = _b.block_testen()
    _auftrag = _bf.hole()
    check("der Block-Test wird ausdrücklich angekündigt", "echter" in _erg["status"]["text"])
    check("getestet wird nur die gespeicherte Blockposition",
          _auftrag and _auftrag["befehl"] == "block_test"
          and _auftrag["argumente"]["phase"] == "loop"
          and _auftrag["argumente"]["block"] == 0)
    _erg = _b.lauf_befehl({"befehl": "skip_step"})
    _auftrag = _bf.hole()
    check("der echte Block-Skip wird ohne KeyError abgelegt und bestätigt",
          _auftrag and _auftrag["befehl"] == "skip_step"
          and "vollständig" in _erg["status"]["text"])
finally:
    _os.chdir(_cwd)


section("Studio-Live-Run: alle Laufentscheidungen sind verdrahtet")
from autoclicker.handlers import BEFEHLE as _BEFEHLE_NEU
check("Studio und Hauptprozess kennen dieselben Befehle",
      sorted(_SB.ALLE_BEFEHLE) == sorted(_BEFEHLE_NEU))
check("Warte- und Block-Skip, sanftes Ende, Schrittmodus und Zeitplan sind im Vertrag",
      {"skip", "skip_step", "finish", "start_manuell", "manuell_aktion", "zeitplan"}
      <= set(_SB.LAUF_BEFEHLE))
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
      '" gewaehlt"' in _app and '.karte.gewaehlt{' in _css)
check("Mehrfachauswahl ist erreichbar und benannt",
      '"phase_auswahl"' in _app
      and 'e.ctrlKey || e.metaKey ? "dazu"' in _app
      and 'e.shiftKey ? "bereich" : "einzeln"' in _app
      and "STRG+Klick" in _app)
check("kein Auswahl-Kästchen auf der Karte — der Ring sagt es schon",
      "karte-auswahl" not in _app and "karte-auswahl" not in _css)
check("Mehrfachauswahl hat gemeinsame Wartezeiten und den 0,5-s-Knopf",
      'function zeichneSammelEditor' in _app and '[0, 0.5, 1]' in _app)
check("leere Start- und Abschlussphasen werden nur bei Bedarf eingeblendet",
      'offeneSonderphasen' in _app and "+ Startphase" in _app
      and "+ Abschlussphase" in _app)
check("der eindeutige Block-Test startet ohne zusätzlichen Browser-Dialog",
      'window.confirm("Diesen Block' not in _app)
check("unter den eindeutigen Aktionsknöpfen steht kein doppelter Erklärungstext",
      "Zeigen setzt nur die Maus" not in _app)
check("die Phasen-Skalierung ist am Knopf eindeutig benannt",
      "Wartezeiten ×" in _app and '"Zeit ×"' not in _app)
_stelle_ui = _app[_app.index("function baueStelle"):
                  _app.index("function setzeStelle")]
check("die Anleitung zum Maus-Setzen steht nur im Info-Text",
      "Mit ‚Stelle mit der Maus setzen‘" in _stelle_ui
      and 'el("p", {class: "hinweis"},\n    "Danach:' not in _stelle_ui)
_inspektor_ui = _app[_app.index("function zeichneInspektor"):
                     _app.index("/* -------------------------------------------------------------------- Dialog")]
# Offene Texte im Inspektor sind nur ZUSTAND, keine Bedienungsanleitung:
# fehlender Punkt, fehlende Scan-Datei, Screenshot-Mass, fehlender Prüfpunkt,
# ein ELSE, das wegen einer fehlenden Bedingung nicht greifen kann — und ein
# Punkt, den andere Blöcke mitbenutzen (wer, nicht warum; das steht im ⓘ).
check("alle Block-Typen haben nur noch sechs begründete offene Zustandsmeldungen",
      _inspektor_ui.count('ziel.appendChild(el("p", {class: "hinweis') == 6)
check("die offenen Meldungen betreffen ausschließlich fehlende Daten oder Messwerte",
      all(text in _inspektor_ui for text in (
          "Keine Punkte vorhanden", "Keine Konfiguration vorhanden", "Grösse: ",
          "Ohne Punkt gibt es nichts zu prüfen", "Dieser Block hat keine Bedingung",
          "wird auch benutzt von")))
check("die Erklärung der ELSE-Wirkung steckt im i statt unter den Kacheln",
      "const auswirkung = b.else_aktion" in _inspektor_ui
      and 'Nochmal auf die markierte Kachel klicken = kein ELSE.' not in _inspektor_ui)

section("Studio-Aufnahme: kein unsichtbarer Prompt und kein UI-Klick im Block")
try:
    _sand, _b = _sandkasten()
    import time as _time
    import autoclicker.editors.sequence_recorder as _rec
    from autoclicker.models import AutoClickerState as _State, RecordEvent as _RE, REC_CLICK as _RC

    _st = _State()
    _st.recording_active = True
    _st.recording_events = [_RE(_RC, _time.monotonic(), 321, 456, (11, 22, 33))]
    _st.recording_ui_name = "aufnahme_ui"
    _st.recording_ui_cycles = 2
    _st.recording_ui_description = "ohne Konsole"
    _alt_input = _rec.safe_input
    _alt_maus_weg = _rec.remove_mouse_hook
    _alt_tasten_weg = _rec.remove_keyboard_hook
    _rec.safe_input = lambda *_a, **_k: (_ for _ in ()).throw(
        AssertionError("UI-Aufnahme darf nichts in der Konsole fragen"))
    _rec.remove_mouse_hook = lambda: None
    _rec.remove_keyboard_hook = lambda: None
    try:
        _gespeichert = _rec.stop_recording(_st)
    finally:
        _rec.safe_input = _alt_input
        _rec.remove_mouse_hook = _alt_maus_weg
        _rec.remove_keyboard_hook = _alt_tasten_weg
    check("die UI-Vorgaben speichern ohne safe_input", _gespeichert == "aufnahme_ui")
    from autoclicker.persistence import load_sequence_file as _load_sequence_file
    _geladen = _load_sequence_file(_rec.aufnahme_datei("aufnahme_ui"))
    check("die Aufnahme wird wirklich zur Sequenz", _geladen is not None)
    check("Zyklen und Notiz kommen aus dem UI",
          _geladen.total_cycles == 2 and _geladen.description == "ohne Konsole")
    check("und aus dem Ereignis entsteht ein Block", _geladen.total_steps() == 1)

    # **Gefragt wird das Fenster UNTER dem Klick, nicht der Vordergrund.** Die
    # Aufnahme wird mit einem Knopf im Studio gestartet, also ist das Studio
    # vorn — und der erste Klick ins Spiel holt es erst nach vorn. Im Hook
    # steht zu dem Zeitpunkt noch das Studio im Vordergrund; wer den fragt,
    # wirft genau diesen Klick weg. In jeder Studio-Aufnahme fehlte damit der
    # erste Schritt, und am Ende stand umgekehrt der Klick auf „Aufnahme
    # stoppen" als Spielklick in der Sequenz (gemessen: `(1347, 709)`, Farbe
    # `#1C2333` = Panel-Grau des Studios). Derselbe Fehler wie in der
    # Klick-Runde, deshalb derselbe Helfer — und dieselben vier Faelle.
    import autoclicker.editors._klickfenster as _kf
    _klick_state = _State(recording_active=True)
    _vorn, _unter = ["Idle Clans"], [None]   # None = wie der Vordergrund
    _alt_vorn, _alt_unter = _kf.get_foreground_window_title, _kf.get_window_title_at
    _kf.get_foreground_window_title = lambda: _vorn[0]
    _kf.get_window_title_at = lambda x, y: (
        _vorn[0] if _unter[0] is None else _unter[0])
    _aufnehmen = _rec._on_click_factory(_klick_state)
    try:
        _vorn[0] = "Sequenz-Studio"
        _aufnehmen(10, 20, (1, 2, 3))
        check("der Stopp-Klick im Studio wird nicht aufgenommen",
              not _klick_state.recording_events)
        _vorn[0] = "Idle Clans"
        _aufnehmen(10, 20, (1, 2, 3))
        check("derselbe Klick im Spiel wird aufgenommen",
              len(_klick_state.recording_events) == 1)

        # Der Fall, an dem jede Studio-Aufnahme ihren ersten Schritt verlor.
        _vorn[0], _unter[0] = "Sequenz-Studio", "Idle Clans"
        _aufnehmen(4578, 490, (140, 77, 74))
        check("der erste Klick ins Spiel zaehlt, obwohl das Studio noch vorn ist",
              [(e.x, e.y) for e in _klick_state.recording_events][-1] == (4578, 490))
        # Und der Klick auf „Aufnahme stoppen" bei vorn stehendem Spiel.
        _vorn[0], _unter[0] = "Idle Clans", "Sequenz-Studio"
        _anzahl = len(_klick_state.recording_events)
        _aufnehmen(1347, 709, (28, 35, 51))
        check("der Stopp-Klick zaehlt nicht, obwohl das Spiel noch vorn ist",
              len(_klick_state.recording_events) == _anzahl)
        # Ohne auffindbares Fenster gilt der Vordergrund — ein Filter, der
        # dann alles wegwirft, saehe aus wie ein kaputter Hook.
        _vorn[0], _unter[0] = "Idle Clans", ""
        _aufnehmen(5, 5, (0, 0, 0))
        check("ohne Fenster unter dem Zeiger entscheidet der Vordergrund",
              len(_klick_state.recording_events) == _anzahl + 1)
    finally:
        _kf.get_foreground_window_title = _alt_vorn
        _kf.get_window_title_at = _alt_unter

    _live_events = [
        _RE(_RC, 1.00, 10, 20, (1, 2, 3)),
        _RE(_RC, 2.00, 11, 21, (20, 30, 40)),
        _RE(_RC, 4.61, 12, 22, (123, 51, 65)),
        _RE(_RC, 7.22, 1378, 756, (123, 51, 65)),
    ]
    _live = _rec._status_ereignisse(_live_events)
    check("die Live-Ausgabe behaelt genau die letzten drei", len(_live) == 3)
    check("ihre laufenden Nummern bleiben erhalten",
          [z["nummer"] for z in _live] == [2, 3, 4])
    check("Zeit, Klick und Farbname stehen getrennt zur Darstellung bereit",
          _live[-1]["zeit"] == "+2.61s" and
          _live[-1]["text"] == "Klick (1378, 756)" and
          "Dunkelrot (123,51,65)" in _live[-1]["farbtext"])
    _live_state = _State(recording_active=True, recording_events=_live_events)
    _rec._status_schreiben(_live_state)
    _gelesen = _b.aufnahme_status()
    check("die Bruecke liefert denselben ueberschriebenen Live-Stand",
          _gelesen["anzahl"] == 4 and len(_gelesen["ereignisse"]) == 3)
finally:
    _os.chdir(_cwd)

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
    _fremd.points = [_CP(id=1, x=100, y=100, name="Sammeln"),
                     _CP(id=2, x=900, y=600, name="Bestaetigen"),
                     _CP(id=3, x=400, y=300, name="Menue")]
    _st2.sequences["Fremd"] = _fremd
    _st2.active_sequence = _fremd
    save_data(_st2)

    from autoclicker.handlers import befehl_nachklick as _bn
    import autoclicker.editors.nachklick as _nk
    _gestartet = {}

    def _fake_start(state, seq=None):
        _gestartet["name"] = seq.name if seq is not None else None
        return True

    _echt = _nk.start_nachklick
    _nk.start_nachklick = _fake_start
    try:
        _farm_pfad = str(dict(list_available_sequences())["Farm"])
        _bn(_st2, {"datei": _farm_pfad})
        check("die Reihenfolge kommt aus der mitgeschickten Datei",
              _gestartet.get("name") == "Farm")
        # **Die geladene Sequenz wechselt dabei NICHT.** Die Runde arbeitet auf
        # Punkten; welche Sequenz der Hauptprozess scharf hat, geht sie nichts
        # an - sonst startete CTRL+ALT+S danach etwas anderes als vorher.
        check("die geladene Sequenz bleibt, wie sie war",
              _st2.active_sequence is _fremd)

        # Ohne Datei passiert NICHTS - lieber gar keine Runde als eine auf der
        # falschen Sequenz.
        _gestartet.clear()
        _bn(_st2, {})
        check("ohne Datei startet keine Runde", not _gestartet)

        _gestartet.clear()
        _bn(_st2, {"datei": "sequences/gibtsnicht/sequence.json"})
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


# ============================================================================
section("Jeder Griff mit der Maus sagt, dass er wartet")

# `_stelle_abwarten()` und `bereich_aufnehmen()` warten GLOBAL auf ENTER — bis zu
# WARTE_TIMEOUT Sekunden, und der Bruecken-Aufruf blockiert dabei. Die Seite
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
_quellen_wt = {n: (_studio_wt / f"{n}.py").read_text(encoding="utf-8")
               for n in ("bridge_editing", "bridge_werkzeuge")}
_appjs_wt = (_studio_wt / "web" / "app.js").read_text(encoding="utf-8")

# Welche oeffentlichen Methoden warten? Eine Methode wartet, wenn ihr Rumpf
# `_stelle_abwarten()` oder `warte_auf_taste(` enthaelt.
_wartend = set()
for _text in _quellen_wt.values():
    _teile = _re_wt.split(r"\n    def ", _text)
    for _teil in _teile[1:]:
        _name = _teil.split("(", 1)[0]
        if _name.startswith("_"):
            continue
        if "_stelle_abwarten()" in _teil or "warte_auf_taste(" in _teil:
            _wartend.add(_name)

check("der Test findet ueberhaupt wartende Methoden", len(_wartend) >= 5)

_tabelle_wt = _appjs_wt[_appjs_wt.index("const WARTE_GRIFFE = {"):]
_tabelle_wt = _tabelle_wt[:_tabelle_wt.index("};")]
_genannt = set(_re_wt.findall(r"^\s*(\w+):\s*\[", _tabelle_wt, _re_wt.M))

_fehlt = sorted(_wartend - _genannt)
check("jede wartende Bruecken-Methode steht in WARTE_GRIFFE", _fehlt == [])
if _fehlt:
    print("        ohne Hinweis: " + ", ".join(_fehlt))

# Gegenrichtung: ein Eintrag fuer etwas, das gar nicht mehr wartet, verspricht
# einen Kasten, den niemand je sieht.
_zuviel = sorted(_genannt - _wartend)
check("und kein Eintrag fuer etwas, das nicht wartet", _zuviel == [])
if _zuviel:
    print("        wartet gar nicht: " + ", ".join(_zuviel))

# Und die Seite muss sie auch WIRKLICH ueber mitWarten() rufen — ein Eintrag in
# der Tabelle allein zeigt noch keinen Kasten.
for _m in sorted(_wartend):
    _direkt = _re_wt.findall(r'(?:ruf|frage|rufWerkzeug)\("' + _m + r'"', _appjs_wt)
    check(f"'{_m}' wird nur ueber mitWarten gerufen", not _direkt)

# Die Zeitgrenze steht an EINER Stelle und wird mitgeliefert: ohne das liefe der
# Countdown der Seite neben dem echten Zeitablauf der Bruecke.
from autoclicker.editors.sequence_studio.bridge_contract import WARTE_TIMEOUT as _WT
check("die Zeitgrenze ist eine Konstante, kein Literal im Aufruf",
      all("timeout=60" not in t for t in _quellen_wt.values()))
check("und sie steht in der Momentaufnahme",
      '"warte_timeout": WARTE_TIMEOUT' in
      (_studio_wt / "bridge_view.py").read_text(encoding="utf-8"))
check("wie auch in den Werkzeug-Daten",
      '"warte_timeout": WARTE_TIMEOUT' in _quellen_wt["bridge_werkzeuge"])
check("der Wert ist eine sinnvolle Zeitgrenze", 10 <= _WT <= 300)
