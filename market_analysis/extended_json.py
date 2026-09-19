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
ZAHL_HUELLEN = frozenset({"NumberLong", "NumberInt", "NumberDecimal", "Long", "Int32", "Int64"})
TEXT_HUELLEN = frozenset({"ObjectId", "ISODate", "UUID", "Date", "DBRef"})

_AUFRUF = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_SKALAR = re.compile(r'^(?:"(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null)$')


def _string_ende(text: str, start: int) -> int:
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


def _argument_ende(text: str, start: int) -> int:
    """Index hinter der schliessenden Klammer, Strings und Verschachtelung beachtet.

    Gibt -1 zurueck, wenn die Klammer nie zugeht — dann wird nichts ersetzt.
    """
    tiefe = 1
    i = start
    n = len(text)
    while i < n:
        c = text[i]
        if c == '"':
            i = _string_ende(text, i)
            continue
        if c == "(":
            tiefe += 1
        elif c == ")":
            tiefe -= 1
            if tiefe == 0:
                return i + 1
        i += 1
    return -1


def _als_zahl(inneres: str) -> str | None:
    """`5`, `"5"`, `"1.5"` -> `5` bzw. `1.5`; sonst None."""
    raw = inneres.strip()
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        raw = raw[1:-1].strip()
    if re.fullmatch(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", raw):
        return raw
    return None


def _ersatz(name: str, inneres: str, unbekannt: dict[str, int]) -> str:
    """Der JSON-Text, der fuer `Name(inneres)` an dieselbe Stelle kommt."""
    inneres = inneres.strip()
    if name in ZAHL_HUELLEN:
        number = _als_zahl(inneres)
        if number is not None:
            return number
    elif name in TEXT_HUELLEN:
        if _SKALAR.match(inneres) and inneres.startswith('"'):
            return inneres
        if not inneres:
            return "null"
    else:
        unbekannt[name] = unbekannt.get(name, 0) + 1
        if _SKALAR.match(inneres):
            return inneres
        return json.dumps(f"{name}({inneres})")
    # Bekannte Huelle, unerwarteter Inhalt: als Text uebernehmen und melden —
    # ein `NumberLong(NaN)` soll auffallen, nicht den Lauf beenden.
    unbekannt[name] = unbekannt.get(name, 0) + 1
    return json.dumps(f"{name}({inneres})")


def bereinigen(text: str) -> tuple[str, dict[str, int]]:
    """Gibt `(json_text, unbekannte)` zurueck.

    `unbekannte` zaehlt je Konstruktname, wie oft es nicht sicher uebersetzt
    werden konnte — leer, wenn alles bekannt war.
    """
    unbekannt: dict[str, int] = {}
    parts: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == '"':
            ende = _string_ende(text, i)
            parts.append(text[i:ende])
            i = ende
            continue
        match = _AUFRUF.match(text, i)
        if match is None:
            parts.append(c)
            i += 1
            continue
        ende = _argument_ende(text, match.end())
        if ende < 0:
            parts.append(text[i:match.end()])
            i = match.end()
            continue
        parts.append(_ersatz(match.group(1), text[match.end():ende - 1], unbekannt))
        i = ende
    return "".join(parts), unbekannt


def hinweise(unbekannt: dict[str, int]) -> list[str]:
    """Die Meldungen zu unbekannten Konstrukten — eine je Name, mit Anzahl."""
    return [f"Unbekanntes Extended-JSON-Konstrukt {name}(…) {count}× — Wert "
            f"uebernommen, nicht uebersetzt. Falls es eine Zahl oder ein Text ist: "
            f"in extended_json.ZAHL_HUELLEN bzw. TEXT_HUELLEN eintragen."
            for name, count in sorted(unbekannt.items())]


def load(text: str) -> tuple[object, list[str]]:
    """Text der API -> `(daten, hinweise)`; wirft `json.JSONDecodeError`, wenn
    auch nach der Uebersetzung kein JSON herauskommt."""
    sauber, unbekannt = bereinigen(text)
    return json.loads(sauber), hinweise(unbekannt)
