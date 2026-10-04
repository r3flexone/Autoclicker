"""Studio: Orientierung statt Suchen — die Regeln hinter dem UI-Durchgang.

Zehn Stellen, an denen die Oberflaeche etwas wusste und es nicht sagte (welche
Phasen es rechts noch gibt, wem eine Meldung gehoert, was „Blöcke 13" ist) oder
etwas sagte und keinen Weg anbot („erst speichern" ohne Speichern-Knopf). Was
sich im Browser zeigt, misst `tests/smoke/guidance.py`; hier stehen die Regeln,
die man am Quelltext und an der Bruecke festhalten kann.
"""
import os as _os
import re
import tempfile
from pathlib import Path

from ._harness import check, section, studio_web_source
from autoclicker.models import (
    ClickPoint as _CP,
    LoopPhase as _PHASE,
    Sequence as _SEQ,
    SequenceStep as _STEP,
)

_web = studio_web_source()
_WEB = Path(__file__).resolve().parents[2] / "autoclicker/editors/sequence_studio/web"
_js = (_WEB / "app.js").read_text(encoding="utf-8")
_css = (_WEB / "styles.css").read_text(encoding="utf-8")
_html = (_WEB / "index.html").read_text(encoding="utf-8")


def _body(name: str, source: str = _js, length: int = 4000) -> str:
    """Der Quelltext einer Funktion (grob: ab ihrem Kopf, `length` Zeichen)."""
    start = source.index("function " + name + "(")
    return source[start:start + length]


# ----------------------------------------------------------------------
section("Statusleiste: eine Meldung gehoert ihrem Reiter")

from autoclicker.editors.sequence_studio.bridge import StudioBridge as _SB

_cwd = _os.getcwd()
_os.chdir(tempfile.mkdtemp(prefix="guidance_"))
try:
    Path("sequences").mkdir()
    _seq = _SEQ(name="Leit", loop_phases=[_PHASE(name="A", steps=[
        _STEP(point_id=1), _STEP(point_id=1)])],
        points=[_CP(x=5, y=5, id=1, name="Knopf")])
    _b = _SB(_seq, Path("sequences/leit/sequence.json"), "sequences")
    _first = _b.snapshot()["status"]
    check("die Momentaufnahme nummeriert ihre Meldung", "id" in _first)
    _after_select = _b.select({"phase": 1, "row": 0, "mode": "single"})["status"]
    check("ein Befehl ohne eigene Meldung behaelt die Nummer",
          _after_select["id"] == _first["id"])
    _after_change = _b.selection_delete()["status"]
    check("eine neue Meldung bekommt eine neue Nummer",
          _after_change["id"] > _first["id"] and _after_change["text"])
    check("und dieselbe Meldung beim naechsten Klick wieder dieselbe",
          _b.select({"phase": 1, "row": 0, "mode": "single"})["status"]["id"]
          == _after_change["id"])
finally:
    _os.chdir(_cwd)

# Die Seite zeichnet nur NEUE Meldungen — sonst holte jeder Klick auf eine
# Karte die Meldung zurueck, die der Reiterwechsel gerade weggeraeumt hat.
check("die Seite zeichnet nur eine neue Meldung",
      "if (status.id !== statusEditorId)" in _body("render"))
# Der Klick auf einen Reiter raeumt auf; ein Wechsel aus dem Code (Starten
# springt in den Live-Run) nimmt die Meldung mit. Eine Uhr war die falsche
# Regel — wer schnell klickt, nahm die Meldung trotzdem mit.
check("die Reiter melden sich als Reiter-Klick",
      'setView(t.dataset.view, true)' in _js)
check("und nur dann wird geraeumt",
      "if (switched && navigated)" in _body("setView"))
check("keine Uhr entscheidet mehr, was mitgeht",
      "STATUS_CARRY_MS" not in _js and "statusAt" not in _js)


# ----------------------------------------------------------------------
section("Board: die Phasen, die nicht hineinpassen, stehen trotzdem da")

check("ueber dem Board steht die Phasenleiste",
      'id="phase-nav"' in _html and "renderPhaseNav(visible)" in _body("renderPhases"))
check("jede Spalte traegt ihre Phase, damit die Leiste hinscrollen kann",
      '"data-phase": String(phase.index)' in _body("renderPhase", length=9000))
check("was ausserhalb liegt, wird blass markiert",
      'chip.classList.toggle("off", !seen)' in _body("updateBoardEdges")
      and ".phase-nav-chip.off{" in _css)
check("die Kanten sagen, dass links bzw. rechts noch etwas kommt",
      'id="board-edge-left"' in _html and 'id="board-edge-right"' in _html
      and '$("board-edge-right").hidden = !moreRight' in _body("updateBoardEdges"))
# Die dunkle Kante liegt ueber den Karten — nimmt sie Klicks an, ist der
# Rand jeder rechten Spalte tot.
check("die Kante nimmt keine Klicks an, nur ihr Knopf",
      re.search(r"\.board-edge\{[^}]*pointer-events:none", _css) is not None
      and re.search(r"\.board-step\{[^}]*pointer-events:auto", _css) is not None)
check("die Seitenleiste laesst sich wegklappen",
      ".body.left-closed > .page.left{display:none}" in _css
      and "function setLeftClosed(" in _js)
check("und der Zustand wird gemerkt, aber ohne Speicher trotzdem gezeichnet",
      'localStorage.setItem("studio.leftClosed"' in _js
      and "try {" in _body("setLeftClosed"))


# ----------------------------------------------------------------------
section("Inspektor ohne Block: ein Ueberblick statt einer leeren Spalte")

_overview = _body("renderOverview", length=5000)
check("ohne Auswahl steht der Ueberblick da",
      "renderOverview(target);" in _body("renderInspector"))
check("er nennt, was Aufmerksamkeit braucht — mit Sprung zum Block",
      "block.warning" in _overview
      and 'goTo({view: "editor", phase: phase.index, row: block.row})' in _overview)
check("und ein ELSE, das nie greift",
      "!block.else_applies" in _overview)
check("im Ueberblick gibt es keine gesperrten Knoepfe",
      '$("btn-block-delete").hidden = nothing;' in _body("renderInspector"))


# ----------------------------------------------------------------------
section("Live-Run im Leerlauf: ein Start-Knopf, eine Erklaerung, eine Vorschau")

_controls = _body("controls", length=3500)
check("Starten sieht aus wie oben im Kopf",
      'button("Starten", "start", "launch", "play"' in _controls)
check("der zweite, fast gleiche Erklaersatz ist weg",
      "startet die gespeicherte Fassung — ungespeicherte" not in _controls)
check("die leere Flaeche zeigt, was gleich laeuft",
      "target.appendChild(runPreview())" in _body("renderRun", length=6000)
      and "function runPreview(" in _js)


# ----------------------------------------------------------------------
section("Scans: der Kopf laesst der Liste Platz, Loeschen steht am Ende")

_head = _body("scanBuildInspector", length=9000)
check("Speichern und Zurueck teilen sich eine Zeile",
      re.search(r'el\("div", \{class: "button-pair"\},\s*scanSaveButton\(\)',
                _head) is not None)
check("Sortieren und Alle aus teilen sich eine Zeile",
      re.search(r'filter\.appendChild\(el\("div", \{class: "button-pair"\},',
                _head) is not None)
check("das Sammel-Loeschen steht nicht mehr im Kopf",
      "scan_delete_all" not in _body("scanFilterRow", length=900)
      and "scan_delete_all" not in _head)
check("sondern am Ende der Liste",
      "scanDeleteAll(target, open);" in _body("scanListBlock", length=3000))
# Rot erst beim Zeigen hiess: „15 Items löschen" sah aus wie „Sortieren".
check("ein gefaehrlicher Knopf ist auch in Ruhe getoent",
      ".btn.danger,.btn.quiet.danger{color:" in _css)
check("ein Name je Slot, und er steht im Rechteck",
      "y: y2 - 4 * px" in _body("scanOverlay", length=6000)
      and "y: y2 + 12 * px" not in _body("scanOverlay", length=6000))
check("der Slot-Name nur beim gewaehlten und beim Slot unter dem Zeiger",
      "if (selected || pointedAt) {" in _body("scanOverlay", length=6000))


# ----------------------------------------------------------------------
section("Leere Zustaende bieten den Handgriff an")

check("Teilen: die Warnung traegt ihren Speichern-Knopf",
      "saveEverythingForShare" in _body("shareRenderExport", length=1600))
check("Bericht: das Session-Log laesst sich direkt einschalten",
      'values: {session_log_enabled: true}' in _body("enableSessionLog"))
check("und nirgends steht mehr der rohe Schluessel als Satz",
      '"session_log_enabled ist aus' not in _js
      and "scan_market_value_file ist leer" not in _js)
check("Bericht: der Ertrag springt zur Einstellung",
      'goTo({view: "settings", key: "scan_market_value_file"})' in _js)
check("die Sprungmarke kennt die Einstellungen",
      'if (t.view === "settings")' in _body("goTo"))


# ----------------------------------------------------------------------
section("Einstellungen: eine Seite, lesbare Abschnitte, blasse Abhaengige")

from autoclicker.config import config_sections as _sections

_titles = [t for t, _ in _sections()]
check("kein Abschnittstitel in Grossbuchstaben",
      all(any(c.islower() for c in t) for t in _titles))
check("und keiner mit „ue\" statt „ü\"", "Nachprüfung" in _titles
      and not any("PRUEF" in t.upper() for t in _titles))
check("alle Abschnitte stehen auf einer Seite",
      "[C.sections[cfgSection]]" not in _js
      and "C.sections.map((a, i) => [a, i])" in _body("renderCfgFields"))
check("die Liste folgt dem Scrollen",
      '$("cfg-fields").addEventListener("scroll", cfgSpy' in _js)
# Der Fehler, der dabei auffiel: `cfgRow()` setzte `blass`, das CSS kannte
# nur `.cfg-row.faded` — abhaengige Felder waren nie blass.
check("ein abhaengiges Feld traegt die Klasse, die das CSS kennt",
      '" faded"' in _body("cfgRow") and ".cfg-row.faded{" in _css)
check("und die deutsche Fassung ist weg", '" blass"' not in _js)
check("der Pfad bricht an seinen Trennern, nicht mitten im Wort",
      'style: "word-break:break-all"' not in _js
      and "pathWithBreaks(C.path" in _js)


# ----------------------------------------------------------------------
section("Werkzeuge und Editor: ein Name, eine Bedeutung")

# Links „Bestand prüfen", rechts „Setup prüfen": man fragt sich, ob man im
# richtigen Werkzeug gelandet ist.
check("der Kopf eines Werkzeugs nimmt seinen Namen aus WZ_TOOLS",
      "function wzHeader(key, text)" in _js
      and "WZ_TOOLS.find((w) => w.key === key)" in _body("wzHeader"))
check("kein Werkzeug-Kopf traegt einen eigenen Titel mehr",
      re.search(r'wzHeader\("\w+", "', _js) is None)
check("ein Konsolen-Befehl steht nur, wo es ihn gibt",
      'command: "rec"' not in _js and 'command: "points"' not in _js
      and 'command: "color"' not in _js)
check("die Blockanzahl sieht nicht aus wie ein Eingabefeld",
      re.search(r"\.field-quiet output\{[^}]*border:1px dashed", _css) is not None)
