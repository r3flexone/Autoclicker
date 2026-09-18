#!/usr/bin/env python3
"""Benennt Bezeichner im ganzen Repo um — token-basiert, nicht per Textersatz.

    python tools/rename.py alt=neu [alt2=neu2 ...]        # anwenden
    python tools/rename.py alt=neu --dry-run              # nur zeigen
    python tools/rename.py alt=neu --strings              # auch Protokoll-Strings
    python tools/rename.py scan-marke=scan-badge          # CSS-Klasse (Bindestrich)

Warum kein Suchen/Ersetzen: `neu`, `alt`, `leer`, `punkt` sind zugleich Woerter
in den Kommentaren, und die bleiben deutsch. Ein Textersatz macht aus „ist neu"
ein „ist new". Deshalb liest dieses Werkzeug Python mit `tokenize` und
JavaScript mit einem kleinen Lexer und schreibt NUR Namens-Token um.

Drei Regeln, die dabei gelten:

* **Bezeichner** (Python-NAME, JS-Identifier — auch nach `.`, in `${...}` und
  als Schluessel `{alt: 1}`) werden immer umgeschrieben.
* **Kommentare, Docstrings und Markdown** bleiben Prosa — dort wird nur
  ersetzt, was erkennbar ein Verweis auf den Bezeichner ist: in Backticks,
  gefolgt von `(`, oder wenn der Name selbst einen Unterstrich traegt
  (`punkt_setzen` ist nie ein deutsches Wort).
* **Strings** folgen derselben Verweis-Regel. Mit `--strings` kommen dazu die
  Strings, die den Bezeichner als GANZES tragen oder als Glied eines Pfads
  (`"block_setzen"`, `"autoclicker.befehl"`, `"autoclicker/befehl.py"`) —
  das sind die Bruecken-Aufrufe der Seite, die Dispatch-Tabellen und die
  Gegenproben, die per Namensstring monkeypatchen. Ein Satz mit Leerzeichen
  ist nie gemeint.

Ein Name mit Bindestrich ist eine CSS-Klasse: die lebt ohnehin nur in Strings
und Stylesheet, also wird sie ueberall mit Wortgrenze ersetzt.

Vor dem Schreiben prueft das Werkzeug, ob der NEUE Name schon irgendwo als
Bezeichner vorkommt — dann bricht es ab, denn zwei Dinge unter einem Namen sind
der Fehler, den man hinterher nicht mehr findet (`--force` uebergeht das).
"""

import argparse
import io
import re
import sys
import tokenize
from pathlib import Path

ROOTS = ["autoclicker", "market_analysis", "tools", "tests", "main.py",
         "README.md", "CLAUDE.md", "IDEAS.md", ".github"]
SKIP_DIRS = {"__pycache__", ".git", ".venv", "node_modules", "output", "symbol"}
TEXT_SUFFIXES = {".py", ".js", ".html", ".css", ".md", ".yml", ".yaml", ".txt"}

_JS_IDENT = re.compile(r"[A-Za-z_$][\w$]*")
# Nach diesen Token faengt ein `/` ein Regex-Literal an, sonst ist es Division.
_JS_REGEX_BEFORE = {"(", ",", "=", ":", "[", "!", "&", "|", "?", "{", "}", ";",
                    "return", "typeof", "in", "of", "+", "-", "*", "%", "<", ">"}


class Renamer:
    """Ein Durchgang mit einer Tabelle alt -> neu."""

    def __init__(self, table: dict, strings: bool = False) -> None:
        self.table = dict(table)
        self.strings = strings
        self.ident = {a: n for a, n in table.items() if "-" not in a}
        self.css_table = {a: n for a, n in table.items() if "-" in a}
        self.seen = set()     # jeder JS-Identifier, den der Lexer gesehen hat
        self._compile()

    # ----------------------------------------------------------- Verweise

    def _compile(self) -> None:
        """Ein Muster je Regel statt eines je Name — 200 Namen mal 10.000 Token
        waren sonst zwei Millionen Regex-Laeufe."""
        def alternation(namen):
            return "(?:" + "|".join(re.escape(n) for n in sorted(namen, key=len, reverse=True)) + ")"
        mit = [a for a in self.ident if "_" in a]
        ohne = [a for a in self.ident if "_" not in a]
        self._re_underscore = re.compile(r"(?<!\w)" + alternation(mit) + r"\b") if mit else None
        self._re_backtick = (re.compile(r"`" + alternation(ohne) + r"(?=[`(.])|\b" + alternation(ohne) + r"(?=\()")
                             if ohne else None)
        self._re_ident = re.compile(r"(?<![\w$])" + alternation(self.ident) + r"(?![\w$])") if self.ident else None
        self._re_css = re.compile(r"(?<![\w-])" + alternation(self.css_table) + r"(?![\w-])") if self.css_table else None

    def _doc_rule(self, text: str) -> str:
        """Prosa: nur erkennbare Verweise ersetzen (Backticks, `(`, Unterstrich)."""
        if self._re_underscore is not None:
            text = self._re_underscore.sub(lambda m: self.ident[m.group(0)], text)
        if self._re_backtick is not None:
            text = self._re_backtick.sub(
                lambda m: m.group(0).replace(m.group(0).lstrip("`"), self.ident[m.group(0).lstrip("`")]), text)
        return text

    def _string_rule(self, inhalt: str) -> str:
        """String-Inhalt: Verweis-Regel, mit --strings zusaetzlich Pfad-Glieder."""
        neu = self._doc_rule(inhalt)
        if self.strings and self._re_ident is not None and neu.strip() == neu and " " not in neu and neu:
            neu = self._re_ident.sub(lambda m: self.ident[m.group(0)], neu)
        return neu

    def _css_rule(self, text: str) -> str:
        if self._re_css is not None:
            text = self._re_css.sub(lambda m: self.css_table[m.group(0)], text)
        return text

    # ------------------------------------------------------------- Python

    def python(self, src: str) -> str:
        """NAME-Token umbenennen; Kommentare/Strings nach den Verweis-Regeln."""
        lines = src.splitlines(keepends=True)
        edits = []   # (row, col_start, col_end, neu)
        try:
            tokens = list(tokenize.generate_tokens(io.StringIO(src).readline))
        except (tokenize.TokenError, SyntaxError) as e:
            raise ValueError(f"nicht tokenisierbar: {e}")
        for tok in tokens:
            (r1, c1), (r2, c2) = tok.start, tok.end
            if tok.type == tokenize.NAME and tok.string in self.ident:
                edits.append((r1, c1, r2, c2, self.ident[tok.string]))
            elif tok.type == tokenize.COMMENT:
                neu = self._doc_rule(tok.string)
                if neu != tok.string:
                    edits.append((r1, c1, r2, c2, neu))
            elif tok.type == tokenize.STRING:
                neu = self._rewrite_string_token(tok.string)
                if neu != tok.string:
                    edits.append((r1, c1, r2, c2, neu))
            elif tok.type == getattr(tokenize, "FSTRING_MIDDLE", -1):
                neu = self._doc_rule(tok.string)
                if neu != tok.string:
                    edits.append((r1, c1, r2, c2, neu))
        return self._apply(lines, edits)

    def _rewrite_string_token(self, literal: str) -> str:
        m = re.match(r"([A-Za-z]*)(\"\"\"|'''|\"|')", literal)
        if not m:
            return literal
        prefix, quote = m.group(1), m.group(2)
        inhalt = literal[len(prefix) + len(quote):-len(quote)]
        if "\n" in inhalt or len(inhalt) > 200:
            neu = self._doc_rule(inhalt)           # Docstring / langer Text
        else:
            neu = self._string_rule(inhalt)
        return prefix + quote + neu + quote

    @staticmethod
    def _apply(lines: list, edits: list) -> str:
        for r1, c1, r2, c2, neu in sorted(edits, reverse=True):
            if r1 == r2:
                zeile = lines[r1 - 1]
                lines[r1 - 1] = zeile[:c1] + neu + zeile[c2:]
            else:
                kopf = lines[r1 - 1][:c1]
                schwanz = lines[r2 - 1][c2:]
                lines[r1 - 1:r2] = [kopf + neu + schwanz]
        return "".join(lines)

    # --------------------------------------------------------- JavaScript

    def javascript(self, src: str) -> str:
        """Identifier umbenennen; Strings, Templates und Kommentare nach Regel."""
        out = []
        i, n = 0, len(src)
        last_sig = ""      # letztes bedeutsames Token (fuer Regex-Erkennung)
        while i < n:
            ch = src[i]
            if src.startswith("//", i):
                j = src.find("\n", i)
                j = n if j < 0 else j
                out.append(self._doc_rule(src[i:j])); i = j; continue
            if src.startswith("/*", i):
                j = src.find("*/", i + 2)
                j = n if j < 0 else j + 2
                out.append(self._doc_rule(src[i:j])); i = j; continue
            if ch in "\"'":
                j = self._js_string_end(src, i, ch)
                out.append(ch + self._string_rule(src[i + 1:j - 1]) + ch)
                i = j; last_sig = "str"; continue
            if ch == "`":
                j, text = self._js_template(src, i)
                out.append(text); i = j; last_sig = "str"; continue
            if ch == "/" and last_sig in _JS_REGEX_BEFORE:
                j = self._js_regex_end(src, i)
                out.append(src[i:j]); i = j; last_sig = "re"; continue
            m = _JS_IDENT.match(src, i)
            if m:
                wort = m.group(0)
                self.seen.add(wort)
                out.append(self.ident.get(wort, wort))
                i = m.end(); last_sig = wort; continue
            if not ch.isspace():
                last_sig = ch
            out.append(ch); i += 1
        return self._css_rule("".join(out))

    @staticmethod
    def _js_string_end(src: str, i: int, quote: str) -> int:
        j = i + 1
        while j < len(src):
            if src[j] == "\\":
                j += 2; continue
            if src[j] == quote:
                return j + 1
            j += 1
        return len(src)

    @staticmethod
    def _js_regex_end(src: str, i: int) -> int:
        j, in_class = i + 1, False
        while j < len(src):
            c = src[j]
            if c == "\\":
                j += 2; continue
            if in_class:
                in_class = c != "]"
            elif c == "[":
                in_class = True
            elif c == "/":
                j += 1
                while j < len(src) and src[j].isalpha():
                    j += 1
                return j
            elif c == "\n":
                return j
            j += 1
        return len(src)

    def _js_template(self, src: str, i: int) -> tuple:
        """Template-Literal: Text nach Verweis-Regel, `${...}` als Code."""
        out = ["`"]
        j = i + 1
        text_start = j
        while j < len(src):
            c = src[j]
            if c == "\\":
                j += 2; continue
            if c == "`":
                out.append(self._doc_rule(src[text_start:j]) + "`")
                return j + 1, "".join(out)
            if src.startswith("${", j):
                out.append(self._doc_rule(src[text_start:j]))
                k, depth = j + 2, 1
                while k < len(src) and depth:
                    if src[k] == "{":
                        depth += 1
                    elif src[k] == "}":
                        depth -= 1
                    elif src[k] == "`":
                        k, _ = self._js_template(src, k); continue
                    elif src[k] in "\"'":
                        k = self._js_string_end(src, k, src[k]); continue
                    k += 1
                out.append("${" + self.javascript(src[j + 2:k - 1]) + "}")
                j = k; text_start = j; continue
            j += 1
        out.append(self._doc_rule(src[text_start:]))
        return len(src), "".join(out)

    # ------------------------------------------------------------- Rest

    def html(self, src: str) -> str:
        def script(m):
            return m.group(1) + self.javascript(m.group(2)) + m.group(3)
        src = re.sub(r"(<script[^>]*>)(.*?)(</script>)", script, src, flags=re.S)
        return self._css_rule(self._doc_rule(src))

    def prose(self, src: str) -> str:
        return self._css_rule(self._doc_rule(src))

    def css(self, src: str) -> str:
        return self._css_rule(src)

    def rewrite(self, path: Path, src: str) -> str:
        suffix = path.suffix.lower()
        if suffix == ".py":
            return self.python(src)
        if suffix == ".js":
            return self.javascript(src)
        if suffix == ".html":
            return self.html(src)
        if suffix == ".css":
            return self.css(src)
        return self.prose(src)


# ------------------------------------------------------------------ Dateien

def files(root: Path):
    for wurzel in ROOTS:
        p = root / wurzel
        if p.is_file():
            yield p
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and f.suffix.lower() in TEXT_SUFFIXES \
                        and not (SKIP_DIRS & set(f.relative_to(root).parts[:-1])):
                    yield f


def _read(path: Path) -> str:
    with path.open(encoding="utf-8", newline="") as f:
        return f.read()


def scope_name_sets(src: str) -> list:
    """Je Python-Scope (Modul, Funktion, Lambda, Klasse) die nackten Namen und
    Parameter darin — Attribute (`x.neu`) zaehlen nicht, verschachtelte
    Funktionen nur mit ihrem Namen."""
    import ast
    try:
        baum = ast.parse(src)
    except SyntaxError:
        return []

    def namen(knoten) -> set:
        gefunden = set()
        for k in ast.walk(knoten):
            if isinstance(k, ast.Name):
                gefunden.add(k.id)
            elif isinstance(k, ast.arg):
                gefunden.add(k.arg)
            elif isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                gefunden.add(k.name)
        return gefunden

    scopes = [("<modul>", baum)] + [
        (getattr(k, "name", "<lambda>"), k) for k in ast.walk(baum)
        if isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef))]
    ergebnis = []
    for bezeichnung, knoten in scopes:
        eigene = set()
        for kind in ast.iter_child_nodes(knoten):
            if isinstance(kind, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                eigene.add(kind.name)
                continue
            eigene |= namen(kind)
        ergebnis.append((bezeichnung, eigene))
    return ergebnis


def identifiers_in(path: Path, src: str) -> set:
    """Alle Bezeichner einer Datei — fuer die Kollisionspruefung."""
    if path.suffix == ".py":
        try:
            return {t.string for t in tokenize.generate_tokens(io.StringIO(src).readline)
                    if t.type == tokenize.NAME}
        except (tokenize.TokenError, SyntaxError):
            return set()
    if path.suffix == ".js":
        # Ein Leerlauf des Lexers: er merkt sich jeden Identifier, den er
        # sieht — Strings und Kommentare bleiben dabei aussen vor.
        probe = Renamer({})
        probe.javascript(src)
        return probe.seen
    return set()


def run(root: Path, table: dict, strings: bool, dry_run: bool, force: bool,
        out=sys.stdout) -> int:
    renamer = Renamer(table, strings=strings)
    # newline="" laesst CRLF unangetastet — sonst schriebe der Durchgang jede
    # CRLF-Datei still auf LF um, und der Diff zeigte die ganze Datei.
    quellen = [(f, _read(f)) for f in files(root)]

    # Zwei Stufen. Ein neuer Name, der irgendwo im Repo schon vorkommt, ist ein
    # HINWEIS (`f.write` neben `status.schreibe -> write` ist kein Problem). Ein
    # neuer Name, der im SELBEN Python-Scope wie der alte als nackter Name steht,
    # ist ein STOPP: `wert = 1; value = 2; use(wert)` wuerde nach dem Umbenennen
    # still `value = 2` benutzen, und das faengt kein Linter.
    hinweise, stopps = {}, []
    for f, src in quellen:
        for name in identifiers_in(f, src) & set(renamer.ident.values()):
            hinweise.setdefault(name, []).append(f.relative_to(root).as_posix())
        if f.suffix == ".py":
            for scope, namen in scope_name_sets(src):
                for alt, neu in renamer.ident.items():
                    if alt in namen and neu in namen:
                        stopps.append(f"{f.relative_to(root).as_posix()}:{scope}  {alt} und {neu}")
    for name, wo in sorted(hinweise.items()):
        print(f"[HINWEIS] '{name}' kommt schon vor in: "
              + ", ".join(wo[:4]) + (" ..." if len(wo) > 4 else ""), file=out)
    if stopps and not force:
        for s in stopps:
            print(f"[STOPP] alt und neu im selben Scope: {s}", file=out)
        print("Ein Rename wuerde hier still ueberschatten — von Hand aufloesen oder --force.",
              file=out)
        return 2

    gesamt = 0
    for f, src in quellen:
        try:
            neu = renamer.rewrite(f, src)
        except ValueError as e:
            print(f"[WARNUNG] {f.relative_to(root).as_posix()}: {e}", file=out)
            continue
        if neu == src:
            continue
        alt_zeilen, neu_zeilen = src.splitlines(), neu.splitlines()
        anzahl = sum(1 for a, b in zip(alt_zeilen, neu_zeilen) if a != b) + abs(len(alt_zeilen) - len(neu_zeilen))
        gesamt += anzahl
        rel = f.relative_to(root).as_posix()
        print(f"{rel}: {anzahl} Zeile(n)", file=out)
        if dry_run:
            for nr, (a, b) in enumerate(zip(alt_zeilen, neu_zeilen), 1):
                if a != b:
                    print(f"  {nr}: {b.strip()[:110]}", file=out)
        else:
            f.write_text(neu, encoding="utf-8", newline="")
    print(f"\n{gesamt} geaenderte Zeile(n)" + (" (nicht geschrieben)" if dry_run else ""),
          file=out)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Bezeichner im Repo umbenennen (token-basiert).")
    p.add_argument("pairs", nargs="*", metavar="alt=neu")
    p.add_argument("--table", metavar="DATEI",
                   help="Tabelle mit einer Zeile alt=neu je Umbenennung (# = Kommentar)")
    p.add_argument("--strings", action="store_true",
                   help="auch Strings, die den Namen als Ganzes oder Pfad-Glied tragen")
    p.add_argument("--dry-run", action="store_true", help="nur zeigen, nichts schreiben")
    p.add_argument("--force", action="store_true", help="Kollisionspruefung uebergehen")
    p.add_argument("--root", default=".", help="Repo-Wurzel (Standard: .)")
    args = p.parse_args(argv)

    paare = list(args.pairs)
    if args.table:
        for zeile in Path(args.table).read_text(encoding="utf-8").splitlines():
            zeile = zeile.split("#", 1)[0].strip()
            if zeile:
                paare.append(zeile)
    if not paare:
        p.error("keine Umbenennung angegeben (alt=neu oder --table DATEI)")
    table = {}
    for paar in paare:
        if "=" not in paar:
            p.error(f"'{paar}' ist kein alt=neu")
        alt, neu = paar.split("=", 1)
        if not alt or not neu or alt == neu:
            p.error(f"'{paar}': beide Seiten muessen gesetzt und verschieden sein")
        if "-" not in alt and not re.fullmatch(r"[A-Za-z_$][\w$]*", neu):
            p.error(f"'{neu}' ist kein gueltiger Bezeichner")
        table[alt] = neu
    return run(Path(args.root), table, args.strings, args.dry_run, args.force)


if __name__ == "__main__":
    # Dieselbe Regel wie in tests/alle_tests.py: ein Gedankenstrich in der
    # Meldung darf den Lauf nicht mit UnicodeEncodeError abbrechen.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
