"""`tools/rename.py`: Bezeichner umbenennen, ohne die deutsche Prosa anzufassen.

Das Werkzeug traegt den Umbau auf englische Bezeichner. Sein Fehlerfall ist
nicht „ein Name wurde vergessen" (das faengt flake8), sondern „ein Wort in
einem Kommentar wurde mit umgeschrieben" — das faellt niemandem auf. Deshalb
misst jeder Test hier beide Seiten: was sich aendern muss UND was stehen bleibt.
"""

import io
import os
from pathlib import Path
import tempfile
import unittest

from tools.rename import Renamer, run

REPO = Path(__file__).resolve().parents[2]


class PythonRenameTest(unittest.TestCase):
    def test_identifiers_change_prose_stays(self):
        src = (
            "def punkt_setzen(punkt, neu=None):\n"
            "    # Der Punkt ist neu; `punkt_setzen()` setzt ihn. punkt_setzen wird gerufen.\n"
            "    obj.punkt_setzen(punkt=neu)\n"
            "    return f'{punkt} ist neu'\n"
        )
        neu = Renamer({"punkt_setzen": "set_point", "neu": "new", "punkt": "point"}).python(src)
        self.assertIn("def set_point(point, new=None):", neu)
        self.assertIn("obj.set_point(point=new)", neu)
        self.assertIn("f'{point} ist neu'", neu)                      # Text im f-String bleibt
        self.assertIn("# Der Punkt ist neu; `set_point()` setzt ihn. set_point wird gerufen.", neu)

    def test_fstring_as_single_token(self):
        # Vor Python 3.12 kommt ein f-String als EIN STRING-Token — genau der Weg,
        # den CI auf 3.10 nimmt und der lokal (3.14) nie betreten wird. Deshalb
        # wird die Funktion hier direkt mit dem Token gefuettert.
        r = Renamer({"punkt": "point", "breite": "width", "neu": "new"})
        self.assertEqual(r._rewrite_string_token("f'{punkt} ist neu'"), "f'{point} ist neu'")
        self.assertEqual(r._rewrite_string_token('f"{{neu}} {punkt.x:{breite}}"'),
                         'f"{{neu}} {point.x:{width}}"')
        self.assertEqual(r._rewrite_string_token('rf"\\d{punkt}"'), 'rf"\\d{point}"')

    def test_strings_only_with_flag(self):
        src = 'befehle = {"block_setzen": block_setzen, "laden": laden}\nmeld("laden fehlgeschlagen")\n'
        table = {"block_setzen": "set_block", "laden": "load"}
        ohne = Renamer(table).python(src)
        self.assertIn('"set_block": set_block', ohne)   # Unterstrich: nie ein Wort, also immer
        self.assertIn('"laden": load', ohne)            # der Wert ist ein Bezeichner, der Schluessel ein Wort
        mit = Renamer(table, strings=True).python(src)
        self.assertIn('"load": load', mit)
        self.assertIn('meld("laden fehlgeschlagen")', mit)   # ein Satz aber nie

    def test_path_strings_follow_module_rename(self):
        src = 'patch("autoclicker.befehl.hole")\nPFAD = "autoclicker/befehl.py"\n'
        mit = Renamer({"befehl": "mailbox"}, strings=True).python(src)
        self.assertIn('"autoclicker.mailbox.hole"', mit)
        self.assertIn('"autoclicker/mailbox.py"', mit)

    def test_docstring_keeps_prose(self):
        src = 'def f():\n    """Alt und neu: `alt_wert()` liefert den alten Wert.\n\n    neu ist hier ein Wort.\n    """\n'
        neu = Renamer({"alt_wert": "old_value", "neu": "new"}).python(src)
        self.assertIn("`old_value()`", neu)
        self.assertIn("Alt und neu:", neu)
        self.assertIn("neu ist hier ein Wort.", neu)


class JavascriptRenameTest(unittest.TestCase):
    def test_identifiers_properties_keys_and_template_expressions(self):
        src = (
            "// zeichne ist neu; `zeichne()` baut alles\n"
            "function zeichne(neu) {\n"
            "  const s = {neu: 1, zeile: neu};\n"
            "  el.zeichne(s.neu);\n"
            "  return `neu: ${neu} ${s.zeile}`;\n"
            "}\n"
        )
        neu = Renamer({"zeichne": "render", "neu": "fresh"}).javascript(src)
        self.assertIn("function render(fresh) {", neu)
        self.assertIn("{fresh: 1, zeile: fresh}", neu)
        self.assertIn("el.render(s.fresh)", neu)
        self.assertIn("`neu: ${fresh} ${s.zeile}`", neu)         # Text im Template bleibt
        self.assertIn("// zeichne ist neu; `render()` baut alles", neu)

    def test_bridge_strings_only_with_flag(self):
        src = 'ruf("block_setzen", {feld: "neu"});\nstatus("neu geladen");\n'
        ohne = Renamer({"block_setzen": "set_block", "neu": "fresh"}).javascript(src)
        self.assertIn('ruf("set_block", {feld: "neu"})', ohne)   # Unterstrich-Regel
        mit = Renamer({"block_setzen": "set_block", "neu": "fresh"}, strings=True).javascript(src)
        self.assertIn('{feld: "fresh"}', mit)
        self.assertIn('status("neu geladen")', mit)

    def test_regex_literal_and_division(self):
        src = "const a = b / 2; const r = /neu\\/x/g; s.replace(/neu/, neu);\n"
        neu = Renamer({"neu": "fresh"}).javascript(src)
        self.assertIn("b / 2", neu)
        self.assertIn("/neu\\/x/g", neu)
        self.assertIn("s.replace(/neu/, fresh)", neu)

    def test_real_page_survives_the_lexer_unchanged(self):
        # Ein Lexer, der eine Zeile verschluckt, faellt an der echten Seite auf:
        # ohne Tabelle muss sie Zeichen fuer Zeichen zurueckkommen.
        js = (REPO / "autoclicker/editors/sequence_studio/web/app.js").read_text(encoding="utf-8")
        renamer = Renamer({"gibt_es_nicht_xyz": "nope"})
        self.assertEqual(renamer.javascript(js), js)
        self.assertIn("render", renamer.seen)
        self.assertNotIn("Studio", renamer.seen)      # steht nur in Strings/Kommentaren …
        self.assertGreater(len(renamer.seen), 500)


class KeysModeTest(unittest.TestCase):
    def test_keys_touch_only_exact_strings(self):
        # JSON-Schluessel der Bruecke: in Python ein String, in JS ein Identifier.
        # `--strings` traefe `art` auch in "scan-art" (CSS-Klasse); `--keys` nicht.
        r = Renamer({"art": "kind"}, keys=True)
        self.assertEqual(r.python('d = {"art": 1, "scan-art": 2}\nk = "art"\n'),
                         'd = {"kind": 1, "scan-art": 2}\nk = "kind"\n')
        self.assertEqual(r.javascript('z.art; ({art: 1}); x["art"]; c("scan-art"); ds.art'),
                         'z.kind; ({kind: 1}); x["kind"]; c("scan-art"); ds.kind')

    def test_js_scope_collision_stops(self):
        # `farbe -> color` in einer Funktion, die schon ein nacktes `color` hat,
        # wuerde still ueberschatten; `x.color` (Eigenschaft) zaehlt nicht.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "autoclicker").mkdir()
            (root / "autoclicker/a.js").write_text(
                "function f(farbe) { const color = 1; return farbe; }\n"
                "function g(farbe) { return x.color + farbe; }\n", encoding="utf-8")
            out = io.StringIO()
            self.assertEqual(run(root, {"farbe": "color"}, False, True, False, out=out), 2)
            self.assertIn("a.js:f()  farbe und color", out.getvalue())
            self.assertNotIn("a.js:g()", out.getvalue())


class CssAndProseTest(unittest.TestCase):
    def test_css_class_everywhere(self):
        r = Renamer({"scan-marke": "scan-badge"})
        self.assertEqual(r.css(".scan-marke{x:1}.scan-marke-2{}"), ".scan-badge{x:1}.scan-marke-2{}")
        self.assertEqual(r.javascript('el("div", {class: "scan-marke"})'), 'el("div", {class: "scan-badge"})')
        self.assertEqual(r.html('<div class="scan-marke">'), '<div class="scan-badge">')

    def test_bare_class_only_where_a_class_stands(self):
        # `karte` ist ein Wort UND eine Klasse. Ersetzt wird nur, was als Klasse
        # dasteht: Selektor, Klassenliste im class-Kontext, zitiertes Attribut.
        r = Renamer({".karte": ".card", ".zahl": ".num"})
        self.assertEqual(r.css(".karte{x:1}.seq-karte{}.karte.zahl .zahl{}"),
                         ".card{x:1}.seq-karte{}.card.num .num{}")
        self.assertEqual(r.html('<div class="karte zahl">karte</div>'),
                         '<div class="card num">karte</div>')
        js = ('el("div", {class: "karte" + (an ? " zahl" : "")}, "karte");\n'
              'x.classList.toggle("zahl", z); q(".seq-fuss .karte"); s("die karte ist zahl");\n'
              '// die karte bleibt\n')
        self.assertEqual(r.javascript(js),
                         'el("div", {class: "card" + (an ? " num" : "")}, "karte");\n'
                         'x.classList.toggle("num", z); q(".seq-fuss .card"); s("die karte ist zahl");\n'
                         '// die karte bleibt\n')
        # Python-Tests zitieren Selektoren und JS-Quelltext; ein Wort bleibt.
        py = ('f.count("#wz-rechts .karte")\ncheck("x", \'class: "karte zahl"\' in _html)\n'
              'meld("karte fehlt")\nkarte = 1\n'
              'f.seite.evaluate("""() => {\n  return q(".karte").length;\n}""")\n')
        self.assertEqual(r.python(py),
                         'f.count("#wz-rechts .card")\ncheck("x", \'class: "card num"\' in _html)\n'
                         'meld("karte fehlt")\nkarte = 1\n'
                         'f.seite.evaluate("""() => {\n  return q(".card").length;\n}""")\n')
        self.assertEqual(r.prose("Die Karte (`.karte`) traegt `.zahl`; karte bleibt."),
                         "Die Karte (`.card`) traegt `.num`; karte bleibt.")

    def test_hyphen_class_also_in_python_strings(self):
        r = Renamer({"scan-marke": "scan-badge"})
        self.assertEqual(r.python('f.count(".scan-marke .zahl")\nf.count(f".scan-marke.{n}")\n'),
                         'f.count(".scan-badge .zahl")\nf.count(f".scan-badge.{n}")\n')

    def test_markdown_references_only(self):
        md = "Der Punkt (`punkt_setzen()`) ist neu. `neu()` ist alt; neu bleibt neu.\n"
        neu = Renamer({"punkt_setzen": "set_point", "neu": "fresh"}).prose(md)
        self.assertEqual(neu, "Der Punkt (`set_point()`) ist neu. `fresh()` ist alt; neu bleibt neu.\n")


class RunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "autoclicker").mkdir()
        (self.root / "autoclicker/a.py").write_text(
            "def laden():\n    return neu\nneu = 1\n", encoding="utf-8")
        (self.root / "autoclicker/b.js").write_text(
            "function laden() { return load; }\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_same_scope_collision_refuses_and_writes_nothing(self):
        # `laden` und `load` im selben Rumpf: nach dem Rename staende `load = 2`
        # UEBER dem Parameter — ein stiller Fehler, den kein Linter sieht.
        (self.root / "autoclicker/c.py").write_text(
            "def f(laden):\n    load = 2\n    return laden + load\n", encoding="utf-8")
        out = io.StringIO()
        code = run(self.root, {"laden": "load"}, False, False, False, out=out)
        self.assertEqual(code, 2)
        self.assertIn("[STOPP] alt und neu im selben Scope: autoclicker/c.py:f", out.getvalue())
        self.assertIn("def laden():", (self.root / "autoclicker/a.py").read_text(encoding="utf-8"))

    def test_other_scopes_only_warn(self):
        # `load` gibt es in b.js — ein Hinweis, kein Stopp: andere Datei, anderer Scope.
        out = io.StringIO()
        code = run(self.root, {"laden": "load"}, False, False, False, out=out)
        self.assertEqual(code, 0)
        self.assertIn("[HINWEIS] 'load' kommt schon vor in: autoclicker/b.js", out.getvalue())
        self.assertIn("def load():", (self.root / "autoclicker/a.py").read_text(encoding="utf-8"))
        self.assertIn("function load()", (self.root / "autoclicker/b.js").read_text(encoding="utf-8"))

    def test_force_and_dry_run(self):
        (self.root / "autoclicker/c.py").write_text(
            "def f(laden):\n    load = 2\n    return laden + load\n", encoding="utf-8")
        out = io.StringIO()
        code = run(self.root, {"laden": "load"}, False, True, True, out=out)
        self.assertEqual(code, 0)
        self.assertIn("nicht geschrieben", out.getvalue())
        self.assertIn("def laden():", (self.root / "autoclicker/a.py").read_text(encoding="utf-8"))
        run(self.root, {"laden": "load"}, False, False, True, out=io.StringIO())
        self.assertIn("def load():", (self.root / "autoclicker/a.py").read_text(encoding="utf-8"))

    def test_line_endings_are_preserved(self):
        pfad = self.root / "autoclicker/crlf.py"
        pfad.write_bytes(b"x = neu\r\n")
        run(self.root, {"neu": "fresh"}, False, False, False, out=io.StringIO())
        self.assertEqual(pfad.read_bytes(), b"x = fresh\r\n")


if __name__ == "__main__":
    os.chdir(REPO)
    unittest.main()
