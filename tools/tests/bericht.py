"""Der Reiter „Bericht": Session-Logs lesen und bewerten.

Zwei Dinge werden hier gemessen, und das erste ist das wichtigere: **die
Auswertung gibt Daten zurück und druckt nichts.** Sie ist aus `bericht()`
herausgeschnitten worden, damit die Brücke sie benutzen kann — bleibt eine
`print`-Zeile darin stehen, landet sie in der Konsole des Studios statt in
seinem Reiter, und dort sieht sie niemand.

Das zweite ist der Ertrag. Er ist eine **Obergrenze**, und genau das ist die
Eigenschaft, die ein Test festhalten muss: `item_found` heisst „erkannt", nicht
„verkauft".
"""
import csv
import io
import os as _os
import re
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

from ._harness import check, section, studio_web_source
from autoclicker.editors.sequence_studio.bridge import StudioBridge as _SB
from autoclicker.models import (
    AutoClickerState as _ST, ClickPoint as _CP, LoopPhase as _PHASE,
    Sequence as _SEQ, SequenceStep as _STEP,
)

_web = studio_web_source()

# `tools/` ist kein installiertes Paket — dieselbe Zeile wie in der Bruecke.
_WURZEL = str(Path(__file__).resolve().parents[2])
if _WURZEL not in sys.path:
    sys.path.insert(0, _WURZEL)
from tools.log_report import auswerten as _auswerten, bericht as _bericht  # noqa: E402


_SPALTEN = ["timestamp", "elapsed_sec", "event", "detail", "x", "y", "extra"]


def _log(pfad: Path, zeilen: list) -> Path:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    with open(pfad, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(_SPALTEN)
        w.writerows(zeilen)
    return pfad


section("Bericht: die Auswertung rechnet, sie druckt nicht")

_sand = Path(tempfile.mkdtemp(prefix="bericht_"))
_eins = _log(_sand / "logs" / "20260101_000000_farm.csv", [
    ("2026-01-01 00:00:00", 0, "session_start", "Farm", "", "", ""),
    ("2026-01-01 00:00:01", 1, "click", "Bank", 10, 20, ""),
    ("2026-01-01 00:00:02", 2, "click", "Bank", 10, 20, ""),
    ("2026-01-01 00:00:03", 3, "timeout", "Bank oeffnen", "", "", ""),
    ("2026-01-01 00:00:04", 4, "timeout", "Bank oeffnen", "", "", ""),
    ("2026-01-01 00:00:05", 5, "timeout", "Truhe", "", "", ""),
    ("2026-01-01 00:00:06", 6, "item_found", "Erz", "", "", ""),
    ("2026-01-01 00:00:07", 7, "item_found", "Erz", "", "", ""),
    ("2026-01-01 00:00:08", 8, "item_found", "Holz", "", "", ""),
    ("2026-01-01 00:00:09", 9, "verify_miss", "Verkaufen", "", "", ""),
    ("2026-01-01 00:00:10", 10, "verify_ok", "Verkaufen", "", "", ""),
    ("2026-01-01 00:00:11", 11, "focus_lost", "", "", "", ""),
    ("2026-01-01 01:00:00", 3600, "session_end", "Farm", "", "", ""),
])
_zwei = _log(_sand / "logs" / "20260102_000000_farm.csv", [
    ("2026-01-02 00:00:00", 0, "session_start", "Farm", "", "", ""),
    ("2026-01-02 00:00:01", 1, "click", "Bank", 10, 20, ""),
    ("2026-01-02 00:00:02", 2, "item_found", "Erz", "", "", ""),
    ("2026-01-02 00:30:00", 1800, "session_end", "Farm", "", "", ""),
])

_puffer = io.StringIO()
with redirect_stdout(_puffer):
    _d = _auswerten([_eins, _zwei])
check("die Auswertung gibt keine Zeile aus", _puffer.getvalue() == "")
check("beide Sitzungen sind erfasst", len(_d["sitzungen"]) == 2)
check("die Laufzeit zaehlt zusammen", _d["dauer"] == 5400.0)
check("und jede Sitzung traegt ihre eigene", _d["sitzungen"][1]["dauer"] == 1800.0)
check("jede Sitzung kennt ihren Dateinamen",
      [s["datei"] for s in _d["sitzungen"]] == [_eins.name, _zwei.name])
check("und den Beginn aus der ersten Zeile",
      _d["sitzungen"][0]["beginn"] == "2026-01-01 00:00:00")

# DIE Frage, fuer die es den Reiter gibt: der oberste Timeout ist der Schritt,
# den es zu reparieren lohnt — also muss die Liste absteigend sortiert sein.
check("die Timeouts stehen absteigend", _d["timeouts"] == [["Bank oeffnen", 2],
                                                           ["Truhe", 1]])
check("die Items ebenso", _d["items"] == [["Erz", 3], ["Holz", 1]])
check("die Nachpruefung kommt von beiden Seiten",
      _d["verify_miss"] == [["Verkaufen", 1]] and _d["verify_ok"] == {"Verkaufen": 1})
check("Unterbrechungen werden getrennt gefuehrt", _d["stoerungen"] == [["focus_lost", 1]])
check("und nichts bleibt unausgewertet", _d["unbekannt"] == [])

# Gegenprobe: eine neue Ereignisart soll auffallen, nicht stillschweigend fehlen.
_neu = _log(_sand / "logs2" / "x.csv", [
    ("2026-01-03 00:00:00", 0, "irgendwas_neues", "", "", "", ""),
])
check("eine unbekannte Ereignisart wird gemeldet",
      _auswerten([_neu])["unbekannt"] == ["irgendwas_neues"])

# Eine kaputte Datei ist ein Grund, kein Absturz — und keine Konsolenausgabe.
_kaputt = _sand / "logs3" / "gibtsnicht.csv"
_puffer = io.StringIO()
with redirect_stdout(_puffer):
    _dk = _auswerten([_kaputt])
check("eine unlesbare Datei kommt als Grund zurueck",
      len(_dk["nicht_lesbar"]) == 1 and _dk["nicht_lesbar"][0][0] == "gibtsnicht.csv")
check("und auch dabei wird nichts gedruckt", _puffer.getvalue() == "")

# Die Konsole druckt weiterhin — sie ist der zweite Nutzer derselben Auswertung.
_puffer = io.StringIO()
with redirect_stdout(_puffer):
    _bericht([_eins, _zwei])
_text = _puffer.getvalue()
check("der Kommandozeilen-Bericht druckt nach wie vor", "TIMEOUTS" in _text)
check("und nennt dieselbe Zahl wie die Auswertung", "2x  Bank oeffnen" in _text)


section("Bericht: was der Reiter daraus macht")

_cwd = _os.getcwd()
_os.chdir(_sand)
try:
    Path("sequences").mkdir(exist_ok=True)
    from autoclicker.config import CONFIG
    from autoclicker.persistence import list_available_sequences, save_data
    _st = _ST()
    _seq = _SEQ(name="Farm", loop_phases=[_PHASE(name="A", steps=[_STEP(point_id=1)])],
                points=[_CP(id=1, x=10, y=20, name="A")])
    _st.sequences["Farm"] = _seq
    _st.active_sequence = _seq
    _st.points = _seq.points
    save_data(_st)
    _b = _SB(_seq, dict(list_available_sequences())["Farm"], "sequences")

    _alt_dir, _alt_markt = CONFIG.session_log_dir, CONFIG.scan_market_value_file
    CONFIG.session_log_dir = "logs"
    CONFIG.scan_market_value_file = ""

    _z = _b.bericht_daten()
    check("der Reiter findet die Logs", len(_z["sitzungen"]) == 2)
    check("die neueste steht oben", _z["sitzungen"][0]["datei"] == _zwei.name)
    check("ohne Wahl gilt alles zusammen",
          _z["gewaehlt"] == "" and _z["bericht"]["sitzungen"] == 2)
    check("und die Zahlen sind die der Auswertung",
          _z["bericht"]["timeouts_gesamt"] == 3 and _z["bericht"]["klicks"] == 3)
    # Die Ranglisten kommen gekuerzt — angezeigt werden ohnehin nur die obersten.
    check("die Rangliste ist gedeckelt",
          len(_z["bericht"]["timeouts"]) <= 10)
    check("die Nachpruefung traegt beide Seiten je Zeile",
          _z["bericht"]["verify_miss"] == [["Verkaufen", 1, 1]])

    _z = _b.bericht_daten({"datei": _zwei.name})
    check("eine einzelne Sitzung laesst sich waehlen",
          _z["gewaehlt"] == _zwei.name and _z["bericht"]["sitzungen"] == 1)
    check("und zeigt nur deren Zahlen", _z["bericht"]["klicks"] == 1)
    check("die Liste links bleibt vollstaendig", len(_z["sitzungen"]) == 2)

    # Eine Wahl, deren Datei es nicht mehr gibt, faellt auf „alle" zurueck statt
    # einen leeren Bericht zu zeigen: der Ordner wird aufgeraeumt, waehrend das
    # Fenster offen steht.
    _z = _b.bericht_daten({"datei": "weggeraeumt.csv"})
    check("eine verschwundene Wahl faellt auf alle zurueck",
          _z["gewaehlt"] == "" and _z["bericht"]["sitzungen"] == 2)

    check("ohne Marktwert-Datei gibt es keine Bewertung", _z["ertrag"] is None)

    # --- Ertrag: Stueckzahl mal Wert, und es ist eine Obergrenze -------------
    Path("marktwert.json").write_text('{"Erz": 100, "Silber": 5}', encoding="utf-8")
    CONFIG.scan_market_value_file = "marktwert.json"
    _z = _b.bericht_daten({"datei": ""})
    _e = _z["ertrag"]
    check("mit Marktwert-Datei wird gerechnet", _e is not None and _e["lesbar"])
    # 3x Erz a 100 = 300. Holz hat keinen Wert und darf nicht mitzaehlen.
    check("gezaehlt wird Stueckzahl mal Wert", _e["gold"] == 300.0)
    check("und pro Stunde ueber die Laufzeit", round(_e["pro_stunde"], 2) == 200.0)
    check("Items ohne Wert stehen getrennt", _e["ohne_wert"] == [["Holz", 1]])
    check("die Zeilen tragen Anzahl, Wert und Summe",
          _e["zeilen"] == [["Erz", 3, 100.0, 300.0]])
    # Ein Wert in der Tabelle, den der Lauf nie gesehen hat, taucht nicht auf:
    # gezaehlt wird, was IM LOG steht.
    check("ein ungesehenes Item taucht nicht auf",
          all(z[0] != "Silber" for z in _e["zeilen"]))

    Path("marktwert.json").write_text("kaputt{", encoding="utf-8")
    from autoclicker.runtime.item_scan import _marktwert_cache
    _marktwert_cache.clear()
    check("eine unlesbare Wertetabelle wird gemeldet, nicht verschluckt",
          _b.bericht_daten()["ertrag"]["lesbar"] is False)

    CONFIG.scan_market_value_file = ""
    CONFIG.session_log_dir = "gibtsnicht"
    _z = _b.bericht_daten()
    check("ohne Log-Ordner bleibt der Reiter leer statt zu werfen",
          _z["sitzungen"] == [] and _z["bericht"]["sitzungen"] == 0)

    CONFIG.session_log_dir, CONFIG.scan_market_value_file = _alt_dir, _alt_markt
finally:
    _os.chdir(_cwd)


section("Bericht: der achte Reiter ist verdrahtet und symmetrisch")

check("die Seite hat einen Reiter dafuer", 'data-ansicht="bericht"' in _web)
check("und einen Behaelter in derselben Dreiteilung",
      'id="sicht-bericht"' in _web and 'id="ber-mitte"' in _web)

# **Jeder Reiter muss im Umschalter stehen.** Ein Knopf ohne die passende
# `hidden`-Zeile ist ein Reiter, der sich nicht oeffnet — und der Fehler faellt
# erst beim Klicken auf. Beide Richtungen: kein Knopf ohne Zeile, keine Zeile
# ohne Knopf.
_knoepfe = set(re.findall(r'data-ansicht="(\w+)"', _web))
# Gemerkt wird der ANSICHTSNAME, nicht die Element-Id: die beiden sind nicht
# ueberall gleich (der Reiter „einstellungen" wohnt in `sicht-config`), und ein
# Test auf die Id meldete genau diesen Reiter als nicht verdrahtet.
_geschaltet = {b for _, b in re.findall(
    r'\$\("sicht-(\w+)"\)\.hidden = neu !== "(\w+)"', _web)}
# Der Editor liegt als `rumpf` im Dokument, nicht als `sicht-editor`.
_offen = (_knoepfe - _geschaltet) - {"editor"}
check("jeder Reiter-Knopf hat seine Umschalt-Zeile", _offen == set())
if _offen:
    print("        ohne Umschaltung: " + ", ".join(sorted(_offen)))
_verwaist = _geschaltet - _knoepfe
check("und keine Umschalt-Zeile ohne Knopf", _verwaist == set())

# **Die Kopfleiste blendet ihre Sequenz-Knoepfe in JEDEM fremden Reiter aus.**
# Der Bericht liest `logs/`, nicht die offene Sequenz — bliebe „Speichern"
# stehen, staenden zwei Speichern-Bedeutungen in einer Leiste.
_liste = re.search(r'n\.hidden = \[([^\]]*)\]\.includes\(neu\)', _web)
check("der Bericht steht bei den Reitern ohne Sequenz-Knoepfe",
      _liste is not None and '"bericht"' in _liste.group(1))

# **Symmetrie:** der Reiter baut mit dem, was da ist. Die Kennzahlen sind
# dieselben Kacheln wie im Werkzeuge-Reiter, die Karten dieselben wie im Teilen-
# Reiter — und jede eigene Klasse, die er trotzdem braucht, ist definiert.
_bericht_js = _web[_web.index("async function zeichneBericht"):
                   _web.index("/* ----------------------------------------------------- "
                              "Ansicht: Einstellungen */")]
check("die Kennzahlen sind dieselben Kacheln wie im Werkzeuge-Reiter",
      "wz-kennzahlen" in _bericht_js and "wzKennzahl(" in _bericht_js)
check("und die Karten dieselben wie im Teilen-Reiter",
      "teilen-karte" in _bericht_js)
# Dieselbe Pruefung wie bei den `--slot-*`-Variablen: eine benutzte Klasse, die
# niemand definiert, ist ein unsichtbarer Kasten.
# Nur was wirklich als KLASSE gesetzt wird. Ein blosses `"ber-..."` faengt auch
# die Element-Ids (`$("ber-mitte")`) und die Schluessel der Erklaerungen —
# beides ist keine Klasse, und der Test meldete zehn Fehlalarme.
_benutzt = set()
for _roh in re.findall(r'class: "([^"]+)"', _bericht_js):
    _benutzt |= {k for k in _roh.split() if k.startswith("ber-")}
_css = (Path(_WURZEL) / "autoclicker/editors/sequence_studio/web/styles.css"
        ).read_text(encoding="utf-8")
_ohne_css = sorted(k for k in _benutzt if "." + k not in _css)
check("jede eigene Bericht-Klasse ist auch gestaltet", _ohne_css == [])
if _ohne_css:
    print("        ohne CSS: " + ", ".join(_ohne_css))

# Der Reiter fragt nur — er aendert die Sequenz nicht und darf deshalb nie
# ueber `ruf()` laufen: eine Antwort von hier als Momentaufnahme zu behandeln
# zerschoesse den Editor-Zustand.
check("der Reiter geht ueber den fragenden Kanal",
      'frage("bericht_daten"' in _bericht_js)
check("und nicht ueber den befehlenden", 'ruf("bericht_daten"' not in _web)

import shutil as _sh  # noqa: E402
_sh.rmtree(_sand, ignore_errors=True)


section("Kein Rauchtest bleibt unaufgerufen")

# `RAUCHTESTS` in `tools/alle_tests.py` ist eine getippte Liste — genau die Sorte
# Stelle, die man beim Hinzufuegen einer Datei vergisst. Der Lauf bleibt dann
# gruen und meldet "5 Ansichten", waehrend die sechste nie lief.
from tools.alle_tests import RAUCHTESTS as _RT   # noqa: E402
_da = sorted(p.stem for p in (Path(_WURZEL) / "tools/rauchtests").glob("*.py")
             if not p.stem.startswith("_"))
_vergessen = [n for n in _da if n not in _RT]
check("jeder Rauchtest steht in der Liste des Sammel-Laufs", _vergessen == [])
if _vergessen:
    print("        laeuft nie: " + ", ".join(_vergessen))
check("und kein Eintrag zeigt auf eine Datei, die es nicht gibt",
      [n for n in _RT if n not in _da] == [])
