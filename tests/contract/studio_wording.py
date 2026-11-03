"""Die Sprache des Studios: deutsch, mit Umlauten, ein Wort je Begriff.

Gefunden an den Bildern der Rauchtests, nicht an einer Meldung: die Kacheln
„SKIP CYCLE“ und „RESTART“ im Boss-Scan, ELSE-Kacheln mit dem rohen Wert
(`skip_cycle`), „50 Schritte“ im Phasenkopf neben „Blöcke 50“, „1 Klicks“ und
„2 Sitzung(en)“ im Bericht, eine Überschrift „WO DIE SEQUENZ HAENGT“. Jede
Stelle für sich war ein Tippfehler; zusammen waren es rund fünfzig, und keine
davon fiel einem Test auf, weil keiner auf die Sprache schaute.
"""
import ast
import contextlib as _cl
import io as _io
import os as _os
import re
import tempfile as _tmp
from pathlib import Path as _P

from ._harness import REPO, check, section

from autoclicker.editors.sequence_studio.bridge import StudioBridge as _SB
from autoclicker.editors.sequence_studio.bridge_contract import ELSE_ACTIONS as _ELSE
from autoclicker.editors.sequence_studio.scan_detect import _BOSS_ACTIONS
from autoclicker.models import ACTION_SHORT, ACTION_TEXT, Sequence as _SEQ

_STUDIO = REPO / "autoclicker" / "editors" / "sequence_studio"
_APP = (_STUDIO / "web" / "app.js").read_text("utf-8")


def _js_strings(text):
    """Die doppelt gequoteten Zeichenketten aus app.js, ohne Kommentarzeilen.

    Kein JavaScript-Parser: die Seite schreibt ihre Texte durchgehend in
    doppelten Anführungszeichen, und eine Kommentarzeile beginnt mit `//`
    oder `*`. Was so nicht erfasst wird, fällt höchstens durch, nie falsch an.
    """
    for nr, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith(("//", "*", "/*")):
            continue
        for m in re.finditer(r'"(?:[^"\\\n]|\\.)*"', line):
            yield nr, m.group(0)


def _py_strings(path):
    """Alle Zeichenketten eines Moduls ausser den Docstrings."""
    tree = ast.parse(path.read_text("utf-8"))
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docs.add(id(body[0].value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
            yield node.lineno, node.value


# ----------------------------------------------------------------------
section("Kacheln für Aktionen: deutsch und überall dieselben Wörter")

check("Kurzbeschriftung und Satz stehen auf denselben Aktionen",
      set(ACTION_SHORT) == set(ACTION_TEXT))
check("jede ELSE-Aktion hat eine Kurzbeschriftung", set(_ELSE) <= set(ACTION_SHORT))
check("jede Aktion eines Boss- oder Icon-Scans ebenso", set(_BOSS_ACTIONS) <= set(ACTION_SHORT))
check("keine Kachel zeigt ihren Codewert",
      all(ACTION_SHORT[a].casefold().replace(" ", "_") != a for a in ACTION_SHORT))
_english = [t for t in ACTION_SHORT.values()
            if re.search(r"\b(SKIP|CYCLE|RESTART|CLICK|KEY)\b", t)]
check(f"und keine ein englisches Wort {_english or ''}".rstrip(), not _english)

_cwd = _os.getcwd()
_os.chdir(_tmp.mkdtemp(prefix="wording_"))
try:
    _P("sequences").mkdir()
    with _cl.redirect_stdout(_io.StringIO()):
        _snap = _SB(_SEQ(name="Wortlaut"), _P("sequences/wortlaut/sequence.json"),
                    "sequences").snapshot()
finally:
    _os.chdir(_cwd)
check("die Momentaufnahme liefert die Beschriftung der ELSE-Kacheln",
      _snap.get("action_short") == {a: ACTION_SHORT[a] for a in _ELSE})
check("und die Seite zeigt sie statt des Werts", "S.action_short[a]" in _APP)
check("der Erkennungs-Umschalter sagt „Vorlage“ wie alles daneben",
      'text: "Template"' not in _APP and 'text: "Vorlage"' in _APP)

# ----------------------------------------------------------------------
section("Ein Begriff, ein Wort: das Studio zählt Blöcke, nicht Schritte")

# Die Zählweise der Seite ist `n + " Wort"` bzw. `countText(n, "Wort", …)`.
_steps = [(nr, s) for nr, s in _js_strings(_APP) if re.fullmatch(r'"\s*Schritte?\s*"', s)]
check(f"keine Zählung „N Schritte“ {_steps[:3] or ''}".rstrip(), not _steps)

# ----------------------------------------------------------------------
section("Mehrzahl: „1 Klick“, nicht „1 Klicks“ oder „Klick(s)“")

_brackets = [(nr, s) for nr, s in _js_strings(_APP)
             if re.search(r"[a-zäöü]\((?:s|e|n|en|er|r)\)", s)]
check(f"keine Mehrzahl in Klammern {_brackets[:3] or ''}".rstrip(), not _brackets)

# Ein festes Mehrzahl-Wort hinter einer Zahl („… + " Klicks"") las sich bei 1
# falsch. Steht es so da, muss die Einzahl in derselben oder der Nachbarzeile
# stehen (die Seite schreibt beides als Bedingung) — sonst gehört es in
# `countText()`.
_PLURALS = {"Klicks": "Klick", "Blöcke": "Block", "Sitzungen": "Sitzung",
            "Punkte": "Punkt", "Zyklen": "Zyklus", "Slots": "Slot", "Items": "Item",
            "Scans": "Scan", "Timeouts": "Timeout", "Bosse": "Boss",
            "Einstellungen": "Einstellung", "Ereignisse": "Ereignis",
            "Sekunden": "Sekunde", "Stellen": "Stelle"}
_lines = _APP.splitlines()
_fixed = []
for _i, _line in enumerate(_lines):
    if _line.strip().startswith(("//", "*")):
        continue
    for _many, _one in _PLURALS.items():
        if re.search(r'"\s' + re.escape(_many) + r"\b", _line):
            _near = " ".join(_lines[max(0, _i - 1):_i + 2])
            if not re.search(r'"\s' + re.escape(_one) + r"\b(?![-\w])", _near):
                _fixed.append((_i + 1, _many))
# Eine Ausnahme mit Grund: „∞ Zyklen“ hat keine Einzahl.
_fixed = [(nr, w) for nr, w in _fixed if '"∞ Zyklen"' not in _lines[nr - 1]]
check(f"jede Zählung hat ihre Einzahl {_fixed[:4] or ''}".rstrip(), not _fixed)
check("die Seite hat einen Helfer dafür", "function countText(n, one, many)" in _APP)

# ----------------------------------------------------------------------
section("Angezeigte Texte tragen Umlaute")

# Wortstämme, die es im Deutschen nur umgeschrieben gibt — „fuer“, „ueber“,
# „haengt“. Ein Stamm wie „ue“ allein ginge nicht: „neue“, „aktuell“,
# „zuerst“ sind richtig geschrieben. Kommentare und Docstrings bleiben aussen
# vor (dort schreibt das Projekt teils bewusst ohne Umlaute); geprüft wird,
# was die Seite zeigt oder die Brücke meldet.
_STEMS = re.compile(
    r"(?:fuer|ueber|aender|loesch|pruef|waehl|oeffn|zurueck|haeng|groess|koenn|"
    r"muess|schluess|naechst|hinzufueg|ausfuehr|spaeter|frueher|hoeh|laesst|"
    r"gewuensch|bestaetig|faell|zaehl|erklaer|gehoer|moeglich|rueck|gruen|"
    r"aufloes|verfueg|waehrend|wuerd|haett|duerf|natuerlich|gueltig|laeng|"
    r"fuehr|aehnlich|staerk|haeuf|ungefaehr|naeher|enthaelt|faehig|raeum|"
    r"tatsaech|zusaetz|uebrig|kuerz|schlaeg|laeuf|traeg|naemlich|aelter)",
    re.IGNORECASE)
_hits = [f"app.js:{nr}" for nr, s in _js_strings(_APP) if _STEMS.search(s)]
for _path in sorted(_STUDIO.glob("*.py")):
    _hits += [f"{_path.name}:{nr}" for nr, s in _py_strings(_path) if _STEMS.search(s)]
check(f"keine umgeschriebenen Umlaute in Seite und Brücke {_hits[:4] or ''}".rstrip(),
      not _hits)
