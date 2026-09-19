"""MongoDB-Shell-JSON der Spiel-API in gueltiges JSON uebersetzen.

`Configuration/game-data` kommt nicht als JSON, sondern in der Schreibweise der
Mongo-Shell: `ObjectId("…")`, `NumberLong(0)`, `ISODate("…")` — Funktionsaufrufe
um einen Wert herum, die kein JSON-Parser kennt. Lange stand hier eine Regex,
die genau EIN Konstrukt kannte (`ObjectId`), an drei Stellen im Baum
ausgeschrieben; als das Spiel mit den Achievements `NumberLong` mitschickte,
brachen alle drei an derselben Zeile ab — und die Meldung riet („evtl. ein
neues Konstrukt") statt zu sagen, welches.

**Ein Update darf den Lauf nicht stoppen, nur eine Meldung erzeugen.** Deshalb:

- Bekannte Konstrukte werden richtig uebersetzt (Zahl bleibt Zahl, Text bleibt
  Text).
- Ein unbekanntes `Name(…)` mit einem einzelnen Skalar darin wird zu genau diesem
  Skalar — das ist, was jede Shell-Huelle bedeutet — und **gemeldet**.
- Ein unbekanntes Konstrukt mit mehreren oder verschachtelten Argumenten
  (`Timestamp(1, 2)`) wird als Text uebernommen, damit das Dokument parst; der
  Wert steht dann als `"Timestamp(1, 2)"` da. Gemeldet ebenso.

Gescannt wird zeichenweise mit Ruecksicht auf JSON-Strings: ein `ObjectId(` in
einer Beschreibung bleibt, was es ist. Die Regex von frueher haette es
umgeschrieben.

Nur Standardbibliothek. `tools/catalog.py` im Autoclicker traegt eine Kopie
dieser Funktionen — die beiden Teile importieren einander bewusst nicht (die
Verbindung ist eine Datei, kein Import).
"""

from __future__ import annotations

import json
import re

# Was die Mongo-Shell um Zahlen bzw. um Text legt. Beides mit oder ohne
# Anfuehrungszeichen um das Argument: `NumberLong(5)` und `NumberLong("5")`
# meinen dieselbe Zahl.
NUMBER_WRAPPERS = frozenset({"NumberLong", "NumberInt", "NumberDecimal", "Long", "Int32", "Int64"})
TEXT_WRAPPERS = frozenset({"ObjectId", "ISODate", "UUID", "Date", "DBRef"})

_CALL = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_SCALAR = re.compile(r'^(?:"(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null)$')


def _string_end(text: str, start: int) -> int:
    """Index hinter dem schliessenden Anfuehrungszeichen des Strings ab `start`."""
    i = start + 1
    n = len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == '"':
            return i + 1
        i += 1
    return n


def _argument_end(text: str, start: int) -> int:
    """Index hinter der schliessenden Klammer, Strings und Verschachtelung beachtet.

    Gibt -1 zurueck, wenn die Klammer nie zugeht — dann wird nichts ersetzt.
    """
    depth_value = 1
    i = start
    n = len(text)
    while i < n:
        c = text[i]
        if c == '"':
            i = _string_end(text, i)
            continue
        if c == "(":
            depth_value += 1
        elif c == ")":
            depth_value -= 1
            if depth_value == 0:
                return i + 1
        i += 1
    return -1


def _as_number(inner: str) -> str | None:
    """`5`, `"5"`, `"1.5"` -> `5` bzw. `1.5`; sonst None."""
    raw = inner.strip()
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        raw = raw[1:-1].strip()
    if re.fullmatch(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", raw):
        return raw
    return None


def _replacement(name: str, inner: str, unknown: dict[str, int]) -> str:
    """Der JSON-Text, der fuer `Name(inneres)` an dieselbe Stelle kommt."""
    inner = inner.strip()
    if name in NUMBER_WRAPPERS:
        number = _as_number(inner)
        if number is not None:
            return number
    elif name in TEXT_WRAPPERS:
        if _SCALAR.match(inner) and inner.startswith('"'):
            return inner
        if not inner:
            return "null"
    else:
        unknown[name] = unknown.get(name, 0) + 1
        if _SCALAR.match(inner):
            return inner
        return json.dumps(f"{name}({inner})")
    # Bekannte Huelle, unerwarteter Inhalt: als Text uebernehmen und melden —
    # ein `NumberLong(NaN)` soll auffallen, nicht den Lauf beenden.
    unknown[name] = unknown.get(name, 0) + 1
    return json.dumps(f"{name}({inner})")


def clean_up(text: str) -> tuple[str, dict[str, int]]:
    """Gibt `(json_text, unbekannte)` zurueck.

    `unbekannte` zaehlt je Konstruktname, wie oft es nicht sicher uebersetzt
    werden konnte — leer, wenn alles bekannt war.
    """
    unknown: dict[str, int] = {}
    parts: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == '"':
            end_value = _string_end(text, i)
            parts.append(text[i:end_value])
            i = end_value
            continue
        match = _CALL.match(text, i)
        if match is None:
            parts.append(c)
            i += 1
            continue
        end_value = _argument_end(text, match.end())
        if end_value < 0:
            parts.append(text[i:match.end()])
            i = match.end()
            continue
        parts.append(_replacement(match.group(1), text[match.end():end_value - 1], unknown))
        i = end_value
    return "".join(parts), unknown


def hints(unknown: dict[str, int]) -> list[str]:
    """Die Meldungen zu unbekannten Konstrukten — eine je Name, mit Anzahl."""
    return [f"Unbekanntes Extended-JSON-Konstrukt {name}(…) {count}× — Wert "
            f"uebernommen, nicht uebersetzt. Falls es eine Zahl oder ein Text ist: "
            f"in extended_json.NUMBER_WRAPPERS bzw. TEXT_WRAPPERS eintragen."
            for name, count in sorted(unknown.items())]


def load(text: str) -> tuple[object, list[str]]:
    """Text der API -> `(daten, hinweise)`; wirft `json.JSONDecodeError`, wenn
    auch nach der Uebersetzung kein JSON herauskommt."""
    clean, unknown = clean_up(text)
    return json.loads(clean), hints(unknown)
