"""Der Reiter „Bericht": Session-Logs lesen und bewerten.

Zwei Dinge werden hier gemessen, und das erste ist das wichtigere: **die
Auswertung gibt Daten zurück und druckt nichts.** Sie ist aus `report()`
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
_ROOT = str(Path(__file__).resolve().parents[2])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from tools.log_report import evaluate as _auswerten, report as _bericht  # noqa: E402


_COLUMNS = ["timestamp", "elapsed_sec", "event", "detail", "x", "y", "extra"]


def _log(path: Path, lines: list) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(_COLUMNS)
        w.writerows(lines)
    return path


section("Bericht: die Auswertung rechnet, sie druckt nicht")

_sandbox = Path(tempfile.mkdtemp(prefix="bericht_"))
_one = _log(_sandbox / "logs" / "20260101_000000_farm.csv", [
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
_two = _log(_sandbox / "logs" / "20260102_000000_farm.csv", [
    ("2026-01-02 00:00:00", 0, "session_start", "Farm", "", "", ""),
    ("2026-01-02 00:00:01", 1, "click", "Bank", 10, 20, ""),
    ("2026-01-02 00:00:02", 2, "item_found", "Erz", "", "", ""),
    ("2026-01-02 00:30:00", 1800, "session_end", "Farm", "", "", ""),
])

_buffer = io.StringIO()
with redirect_stdout(_buffer):
    _d = _auswerten([_one, _two])
check("die Auswertung gibt keine Zeile aus", _buffer.getvalue() == "")
check("beide Sitzungen sind erfasst", len(_d["sessions"]) == 2)
check("die Laufzeit zaehlt zusammen", _d["duration"] == 5400.0)
check("und jede Sitzung traegt ihre eigene", _d["sessions"][1]["duration"] == 1800.0)
check("jede Sitzung kennt ihren Dateinamen",
      [s["file"] for s in _d["sessions"]] == [_one.name, _two.name])
check("und den Beginn aus der ersten Zeile",
      _d["sessions"][0]["begin"] == "2026-01-01 00:00:00")

# DIE Frage, fuer die es den Reiter gibt: der oberste Timeout ist der Schritt,
# den es zu reparieren lohnt — also muss die Liste absteigend sortiert sein.
check("die Timeouts stehen absteigend", _d["timeouts"] == [["Bank oeffnen", 2],
                                                           ["Truhe", 1]])
check("die Items ebenso", _d["items"] == [["Erz", 3], ["Holz", 1]])
check("die Nachpruefung kommt von beiden Seiten",
      _d["verify_miss"] == [["Verkaufen", 1]] and _d["verify_ok"] == {"Verkaufen": 1})
check("Unterbrechungen werden getrennt gefuehrt", _d["disturbances"] == [["focus_lost", 1]])
check("und nichts bleibt unausgewertet", _d["unknown"] == [])

# Gegenprobe: eine neue Ereignisart soll auffallen, nicht stillschweigend fehlen.
_new = _log(_sandbox / "logs2" / "x.csv", [
    ("2026-01-03 00:00:00", 0, "irgendwas_neues", "", "", "", ""),
])
check("eine unbekannte Ereignisart wird gemeldet",
      _auswerten([_new])["unknown"] == ["irgendwas_neues"])

# Eine kaputte Datei ist ein Grund, kein Absturz — und keine Konsolenausgabe.
_broken = _sandbox / "logs3" / "gibtsnicht.csv"
_buffer = io.StringIO()
with redirect_stdout(_buffer):
    _d_broken = _auswerten([_broken])
check("eine unlesbare Datei kommt als Grund zurueck",
      len(_d_broken["unreadable"]) == 1 and _d_broken["unreadable"][0][0] == "gibtsnicht.csv")
check("und auch dabei wird nichts gedruckt", _buffer.getvalue() == "")

# Die Konsole druckt weiterhin — sie ist der zweite Nutzer derselben Auswertung.
_buffer = io.StringIO()
with redirect_stdout(_buffer):
    _bericht([_one, _two])
_text = _buffer.getvalue()
check("der Kommandozeilen-Bericht druckt nach wie vor", "TIMEOUTS" in _text)
check("und nennt dieselbe Zahl wie die Auswertung", "2x  Bank oeffnen" in _text)


section("Bericht: was der Reiter daraus macht")

_cwd = _os.getcwd()
_os.chdir(_sandbox)
try:
    Path("sequences").mkdir(exist_ok=True)
    from autoclicker.config import CONFIG
    from autoclicker.persistence import list_available_sequences, save_sequence_file, sequence_file
    _st = _ST()
    _seq = _SEQ(name="Farm", loop_phases=[_PHASE(name="A", steps=[_STEP(point_id=1)])],
                points=[_CP(id=1, x=10, y=20, name="A")])
    _st.active_sequence = _seq
    _st.points = _seq.points
    save_sequence_file(_seq, sequence_file(_seq.name))
    _b = _SB(_seq, dict(list_available_sequences())["Farm"], "sequences")

    _old_dir, _old_market = CONFIG.session_log_dir, CONFIG.scan_market_value_file
    CONFIG.session_log_dir = "logs"
    CONFIG.scan_market_value_file = ""

    _z = _b.report_data()
    check("der Reiter findet die Logs", len(_z["sessions"]) == 2)
    check("die neueste steht oben", _z["sessions"][0]["file"] == _two.name)
    check("ohne Wahl gilt alles zusammen",
          _z["selected"] == "" and _z["brief"]["sessions"] == 2)
    check("und die Zahlen sind die der Auswertung",
          _z["brief"]["timeouts_total"] == 3 and _z["brief"]["clicks"] == 3)
    # Die Ranglisten kommen gekuerzt — angezeigt werden ohnehin nur die obersten.
    check("die Rangliste ist gedeckelt",
          len(_z["brief"]["timeouts"]) <= 10)
    check("die Nachpruefung traegt beide Seiten je Zeile",
          _z["brief"]["verify_miss"] == [["Verkaufen", 1, 1]])

    _z = _b.report_data({"file": _two.name})
    check("eine einzelne Sitzung laesst sich waehlen",
          _z["selected"] == _two.name and _z["brief"]["sessions"] == 1)
    check("und zeigt nur deren Zahlen", _z["brief"]["clicks"] == 1)
    check("die Liste links bleibt vollstaendig", len(_z["sessions"]) == 2)

    # Eine Wahl, deren Datei es nicht mehr gibt, faellt auf „alle" zurueck statt
    # einen leeren Bericht zu zeigen: der Ordner wird aufgeraeumt, waehrend das
    # Fenster offen steht.
    _z = _b.report_data({"file": "weggeraeumt.csv"})
    check("eine verschwundene Wahl faellt auf alle zurueck",
          _z["selected"] == "" and _z["brief"]["sessions"] == 2)

    check("ohne Marktwert-Datei gibt es keine Bewertung", _z["yield_value"] is None)

    # --- Ertrag: Stueckzahl mal Wert, und es ist eine Obergrenze -------------
    Path("marktwert.json").write_text('{"Erz": 100, "Silber": 5}', encoding="utf-8")
    CONFIG.scan_market_value_file = "marktwert.json"
    _z = _b.report_data({"file": ""})
    _e = _z["yield_value"]
    check("mit Marktwert-Datei wird gerechnet", _e is not None and _e["readable"])
    # 3x Erz a 100 = 300. Holz hat keinen Wert und darf nicht mitzaehlen.
    check("gezaehlt wird Stueckzahl mal Wert", _e["gold"] == 300.0)
    check("und pro Stunde ueber die Laufzeit", round(_e["per_hour"], 2) == 200.0)
    check("Items ohne Wert stehen getrennt", _e["without_value"] == [["Holz", 1]])
    check("die Zeilen tragen Anzahl, Wert und Summe",
          _e["rows"] == [["Erz", 3, 100.0, 300.0]])
    # Ein Wert in der Tabelle, den der Lauf nie gesehen hat, taucht nicht auf:
    # gezaehlt wird, was IM LOG steht.
    check("ein ungesehenes Item taucht nicht auf",
          all(z[0] != "Silber" for z in _e["rows"]))

    Path("marktwert.json").write_text("kaputt{", encoding="utf-8")
    from autoclicker.runtime.item_scan import _marktwert_cache
    _marktwert_cache.clear()
    check("eine unlesbare Wertetabelle wird gemeldet, nicht verschluckt",
          _b.report_data()["yield_value"]["readable"] is False)

    CONFIG.scan_market_value_file = ""
    CONFIG.session_log_dir = "gibtsnicht"
    _z = _b.report_data()
    check("ohne Log-Ordner bleibt der Reiter leer statt zu werfen",
          _z["sessions"] == [] and _z["brief"]["sessions"] == 0)

    CONFIG.session_log_dir, CONFIG.scan_market_value_file = _old_dir, _old_market
finally:
    _os.chdir(_cwd)


section("Bericht: der achte Reiter ist verdrahtet und symmetrisch")

check("die Seite hat einen Reiter dafuer", 'data-view="report"' in _web)
check("und einen Behaelter in derselben Dreiteilung",
      'id="view-report"' in _web and 'id="rep-middle"' in _web)

# **Jeder Reiter muss im Umschalter stehen.** Ein Knopf ohne die passende
# `hidden`-Zeile ist ein Reiter, der sich nicht oeffnet — und der Fehler faellt
# erst beim Klicken auf. Beide Richtungen: kein Knopf ohne Zeile, keine Zeile
# ohne Knopf.
_buttons = set(re.findall(r'data-view="(\w+)"', _web))
# Gemerkt wird der ANSICHTSNAME, nicht die Element-Id: die beiden sind nicht
# ueberall gleich (der Reiter „einstellungen" wohnt in `view-settings`), und ein
# Test auf die Id meldete genau diesen Reiter als nicht verdrahtet.
_switched = {b for _, b in re.findall(
    r'\$\("view-([\w-]+)"\)\.hidden = next !== "(\w+)"', _web)}
# Der Editor liegt als `editor-body` im Dokument, nicht als `view-editor`.
_open = (_buttons - _switched) - {"editor"}
check("jeder Reiter-Knopf hat seine Umschalt-Zeile", _open == set())
if _open:
    print("        ohne Umschaltung: " + ", ".join(sorted(_open)))
_orphaned = _switched - _buttons
check("und keine Umschalt-Zeile ohne Knopf", _orphaned == set())

# **Die Kopfleiste blendet ihre Sequenz-Knoepfe in JEDEM fremden Reiter aus.**
# Der Bericht liest `logs/`, nicht die offene Sequenz — bliebe „Speichern"
# stehen, staenden zwei Speichern-Bedeutungen in einer Leiste.
_list = re.search(r'n\.hidden = \[([^\]]*)\]\.includes\(next\)', _web)
check("der Bericht steht bei den Reitern ohne Sequenz-Knoepfe",
      _list is not None and '"report"' in _list.group(1))

# **Symmetrie:** der Reiter baut mit dem, was da ist. Die Kennzahlen sind
# dieselben Kacheln wie im Werkzeuge-Reiter, die Karten dieselben wie im Teilen-
# Reiter — und jede eigene Klasse, die er trotzdem braucht, ist definiert.
_report_js = _web[_web.index("async function renderReport"):
                   _web.index("/* ----------------------------------------------------- "
                              "Ansicht: Einstellungen */")]
check("die Kennzahlen sind dieselben Kacheln wie im Werkzeuge-Reiter",
      "wz-metrics" in _report_js and "wzMetric(" in _report_js)
check("und die Karten dieselben wie im Teilen-Reiter",
      "share-card" in _report_js)
# Dieselbe Pruefung wie bei den `--slot-*`-Variablen: eine benutzte Klasse, die
# niemand definiert, ist ein unsichtbarer Kasten.
# Nur was wirklich als KLASSE gesetzt wird. Ein blosses `"ber-..."` faengt auch
# die Element-Ids (`$("rep-middle")`) und die Schluessel der Erklaerungen —
# beides ist keine Klasse, und der Test meldete zehn Fehlalarme.
_used = set()
for _raw in re.findall(r'class: "([^"]+)"', _report_js):
    _used |= {k for k in _raw.split() if k.startswith("ber-")}
_css = (Path(_ROOT) / "autoclicker/editors/sequence_studio/web/styles.css"
        ).read_text(encoding="utf-8")
_without_css = sorted(k for k in _used if "." + k not in _css)
check("jede eigene Bericht-Klasse ist auch gestaltet", _without_css == [])
if _without_css:
    print("        ohne CSS: " + ", ".join(_without_css))

# Der Reiter fragt nur — er aendert die Sequenz nicht und darf deshalb nie
# ueber `call()` laufen: eine Antwort von hier als Momentaufnahme zu behandeln
# zerschoesse den Editor-Zustand.
check("der Reiter geht ueber den fragenden Kanal",
      'ask("report_data"' in _report_js)
check("und nicht ueber den befehlenden", 'call("report_data"' not in _web)

import shutil as _sh  # noqa: E402
_sh.rmtree(_sandbox, ignore_errors=True)


section("Kein Rauchtest bleibt unaufgerufen")

# `SMOKE_TESTS` in `tests/all_tests.py` ist eine getippte Liste — genau die Sorte
# Stelle, die man beim Hinzufuegen einer Datei vergisst. Der Lauf bleibt dann
# gruen und meldet "5 Ansichten", waehrend die sechste nie lief.
from tests.all_tests import SMOKE_TESTS as _RT   # noqa: E402
_present = sorted(p.stem for p in (Path(_ROOT) / "tests/smoke").glob("*.py")
             if not p.stem.startswith("_"))
_forgotten = [n for n in _present if n not in _RT]
check("jeder Rauchtest steht in der Liste des Sammel-Laufs", _forgotten == [])
if _forgotten:
    print("        laeuft nie: " + ", ".join(_forgotten))
check("und kein Eintrag zeigt auf eine Datei, die es nicht gibt",
      [n for n in _RT if n not in _present] == [])


section("Einstellungen: der Schreiber laedt sich selbst neu")

# **Der Schreiber war der Einzige, der sich nicht neu lud.** Der Hauptprozess
# bekommt den Briefkasten-Befehl und ruft `command_config()`; der Studio-Prozess
# schrieb die Datei und blieb danach auf den Werten vom Programmstart sitzen.
# Aufgefallen ist es am Bericht-Reiter — „session_log_enabled ist aus", direkt
# nachdem man es eingeschaltet hatte —, betroffen war aber jeder Reiter, der
# `CONFIG` liest: OCR/LLM-Lampen und Marker-Schwellen im Scans-Reiter, die
# Farbtoleranz im Werkzeuge-Reiter, der Fenstertitel im Teilen-Reiter.
_sandbox2 = Path(tempfile.mkdtemp(prefix="bericht_cfg_"))
_cwd = _os.getcwd()
_os.chdir(_sandbox2)
try:
    Path("sequences").mkdir(exist_ok=True)
    from autoclicker.config import CONFIG as _CFG, AppConfig as _AC, save_config as _sc
    from autoclicker.persistence import list_available_sequences, save_sequence_file, sequence_file
    _sc(_AC())
    _st = _ST()
    _seq = _SEQ(name="Farm", loop_phases=[_PHASE(name="A", steps=[_STEP(point_id=1)])],
                points=[_CP(id=1, x=10, y=20, name="A")])
    _st.active_sequence = _seq
    _st.points = _seq.points
    save_sequence_file(_seq, sequence_file(_seq.name))
    _b2 = _SB(_seq, dict(list_available_sequences())["Farm"], "sequences")

    _old_log, _old_tol = _CFG.session_log_enabled, _CFG.punkt_farbtoleranz
    _CFG.session_log_enabled = False
    _before = id(_CFG)
    check("vorher steht der Reiter auf aus", _b2.report_data()["active"] is False)

    _r = _b2.config_write({"values": {"session_log_enabled": True,
                                         "punkt_farbtoleranz": 42}})
    check("das Schreiben geht durch", _r["ok"] is True)
    check("der Prozess kennt den neuen Wert sofort",
          _CFG.session_log_enabled is True)
    check("und der Reiter zeigt ihn ohne Neustart",
          _b2.report_data()["active"] is True)
    # Nicht nur das eine Feld: uebernommen wird die ganze Config, also auch das,
    # was ANDERE Reiter lesen.
    check("auch Felder anderer Reiter ziehen mit", _CFG.punkt_farbtoleranz == 42)
    # **Das Objekt darf nicht getauscht werden.** Wer es ersetzt, laesst jeden
    # mit `from ...config import CONFIG` (imaging, die Scan-Module) dauerhaft auf
    # den Werten vom Programmstart sitzen — genau der Fehler, gegen den es
    # `apply_config()` gibt.
    check("und das Config-Objekt bleibt dasselbe", id(_CFG) == _before)

    _CFG.session_log_enabled, _CFG.punkt_farbtoleranz = _old_log, _old_tol
finally:
    _os.chdir(_cwd)
    _sh.rmtree(_sandbox2, ignore_errors=True)
