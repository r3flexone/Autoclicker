#!/usr/bin/env python3
"""Schreibt den Item-/Gegner-Katalog aus der offiziellen Idle-Clans-API.

    python tools/catalog.py            # schreibt katalog.json
    python tools/catalog.py --target X   # anderer Pfad
    python tools/catalog.py --show    # nur anzeigen, nichts schreiben

Der Katalog beantwortet zwei Fragen, die der Autoclicker sonst raten muss:
**wie heisst das Item wirklich** und **womit konkurriert es**. Beides steht in
`Configuration/game-data`, derselben Quelle, aus der auch die Wiki gespeist wird
— Scraping braucht es dafuer nicht.

Dieses Werkzeug importiert **nichts** aus `autoclicker/` und nichts aus
`market_analysis/`; die Verbindung ist eine Datei, kein Import — dieselbe
Richtung wie bei `marktwert.json`. Es laeuft mit der Standardbibliothek allein.

Warum die Kategorie so gebildet wird, wie sie gebildet wird:

Eine Kategorie heisst im Autoclicker **"diese Items konkurrieren, nimm nur das
beste"** (`_filter_scan_results`, Modus `all`). Eine zu WEITE Kategorie ist
deshalb der gefaehrliche Fehler — sie laesst Klicks still ausfallen. Gebildet
wird sie darum so eng, wie es die Daten hergeben:

* `EquipmentSlot` traegt die Bedeutung schon (ein Helm, ein Schild, ein Paar
  Stiefel) und wird direkt uebernommen.
* Slot 7 ist die Ausnahme: dort liegen 200 Waffen UND Werkzeuge zusammen, weil
  das Spiel sie in derselben Hand fuehrt. Als eine Kategorie hiesse das, aus
  Spitzhacke, Beil und Bogen genau eines zu klicken. Getrennt wird deshalb am
  letzten Wort des Namens (`Godlike Pickaxe` -> `Pickaxe`).
* Slot 0 ist gar keine Ausruestung (Erze, Fische, Saatgut). Auch dort ist das
  letzte Wort die engste verlaessliche Gruppe (`Diamond Ore` -> `Ore`).

`AssociatedSkill` waere die naheliegende Alternative fuer Slot 7 und ist es
nicht: alle `godlike_*` tragen dort dieselbe 7, Bogen wie Spitzhacke.
`WeaponType` ist die STUFE (normal -> refined -> ... -> godlike), nicht die Art.
Und das Feld `Category` ist unbrauchbar — 662 von 1006 Items stehen auf 0.

Eine Prioritaet steht bewusst NICHT in der Datei, nur der Wert (`BaseValue`).
Ein Rang gilt immer relativ zu den Items EINES Scans; global vergeben bekaeme
der beste Bogen eines Bestands P49, weil 48 teurere im Katalog stehen, die man
gar nicht besitzt. Den Rang vergibt deshalb der Autoclicker beim Anwenden.
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

GAME_URL = "https://query.idleclans.com/api/Configuration/game-data"
DEFAULT_TARGET = "catalog.json"

# EquipmentSlot -> Kategorie. Die Zuordnung ist aus den Item-Namen der jeweiligen
# Gruppe abgelesen (alle 19 Eintraege von Slot 1 enden auf `_boots` usw.).
# Slot 12 kommt in den Daten nicht vor; 0 und 7 werden gesondert behandelt.
SLOTS = {
    1: "Stiefel", 2: "Ring", 3: "Handschuhe", 4: "Beine", 5: "Ruestung",
    6: "Schild", 8: "Amulett", 9: "Pfeile", 10: "Umhang", 11: "Helm",
    13: "Armband", 14: "Guertel", 15: "Pet", 16: "Ohrringe",
}


def display_name(key_name: str) -> str:
    """`godlike_bow` -> `Godlike Bow` — der Name, wie er im Spiel steht."""
    return key_name.replace("_", " ").title()


def category_for(item: dict) -> str:
    """Die Gruppe, innerhalb derer dieses Item mit anderen konkurriert."""
    slot = item.get("EquipmentSlot") or 0
    fixed = SLOTS.get(slot)
    if fixed:
        return fixed
    # Slot 7 und 0: das letzte Wort ist die engste verlaessliche Gruppe.
    last_one = display_name(item.get("Name", "")).split()
    return last_one[-1] if last_one else "Sonstiges"


# ---------------------------------------------------------------------------
# MongoDB-Shell-JSON -> JSON. **Zwilling von `market_analysis/extended_json.py`**,
# bewusst kopiert statt importiert: die beiden Teile kennen einander nicht (die
# Verbindung ist eine Datei). Wer hier etwas aendert, aendert es dort mit — ein
# Test auf jeder Seite haelt dieselben Faelle fest.
#
# Warum ein Scanner und keine Regex: hier stand `re.sub(r'ObjectId\("…"\)', …)`,
# und als die API mit den Achievements `NumberLong(0)` mitschickte, starb der
# Katalog-Knopf im Studio an einem Feld, das er nie liest. Ein Spiel-Update darf
# eine Meldung erzeugen, aber keinen Abbruch: Bekanntes wird uebersetzt,
# Unbekanntes als Wert uebernommen und gemeldet.
# ---------------------------------------------------------------------------

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
    """Index hinter der schliessenden Klammer; -1, wenn sie nie zugeht."""
    depth = 1
    i = start
    n = len(text)
    while i < n:
        c = text[i]
        if c == '"':
            i = _string_end(text, i)
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return -1


def _as_number(inner: str):
    """`5`, `"5"`, `"1.5"` -> `5` bzw. `1.5`; sonst None."""
    raw = inner.strip()
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        raw = raw[1:-1].strip()
    if re.fullmatch(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", raw):
        return raw
    return None


def _replacement(name: str, inner: str, unknown: dict) -> str:
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
    unknown[name] = unknown.get(name, 0) + 1
    return json.dumps(f"{name}({inner})")


def clean_extended_json(text: str) -> tuple:
    """`(json_text, unbekannte)` — `unbekannte` zaehlt je Konstruktname."""
    unknown: dict = {}
    parts = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == '"':
            end = _string_end(text, i)
            parts.append(text[i:end])
            i = end
            continue
        match = _CALL.match(text, i)
        if match is None:
            parts.append(c)
            i += 1
            continue
        end = _argument_end(text, match.end())
        if end < 0:
            parts.append(text[i:match.end()])
            i = match.end()
            continue
        parts.append(_replacement(match.group(1), text[match.end():end - 1], unknown))
        i = end
    return "".join(parts), unknown


def extended_json_hints(unknown: dict) -> list:
    """Die Meldungen zu unbekannten Konstrukten — eine je Name, mit Anzahl."""
    return [f"Unbekanntes Extended-JSON-Konstrukt {name}(…) {count}× — Wert "
            f"uebernommen, nicht uebersetzt. Falls es eine Zahl oder ein Text ist: "
            f"in NUMBER_WRAPPERS bzw. TEXT_WRAPPERS eintragen."
            for name, count in sorted(unknown.items())]


def fetch_game_data(url: str = GAME_URL, timeout: int = 60, hints: list = None) -> dict:
    """Laedt game-data und macht daraus gueltiges JSON.

    Der Endpunkt liefert MongoDB-Shell-JSON (`ObjectId("…")`, `NumberLong(0)`);
    `clean_extended_json` uebersetzt es. Was dabei unbekannt war, landet als
    Meldung in `hints` (falls uebergeben) — der Aufrufer entscheidet, wo sie
    hingehoert: die Kommandozeile auf stderr, das Studio in seine Statuszeile.
    """
    req = urllib.request.Request(url, headers={"User-Agent": "autoclicker-catalog"})
    with urllib.request.urlopen(req, timeout=timeout) as answer:
        raw = answer.read().decode("utf-8")
    cleaned, unknown = clean_extended_json(raw)
    if hints is not None:
        hints.extend(extended_json_hints(unknown))
    return json.loads(cleaned)


def build_catalog(game_data: dict) -> dict:
    """Aus den Spieldaten die beiden Listen, die der Autoclicker braucht."""
    items = {}
    for entry in (game_data.get("Items") or {}).get("Items") or []:
        key_name = entry.get("Name")
        if not key_name:
            continue
        items[display_name(key_name)] = {
            "kategorie": category_for(entry),
            "wert": entry.get("BaseValue") or 0,
        }

    # Gegner stehen verstreut (Kampf-Aufgaben, Raids, Clan-Bosse) und tragen mal
    # `EnemyName`, mal `MonsterName`, mal `BossNameLocalizationKey`. Eingesammelt
    # wird ueber den ganzen Baum, damit kein Zweig vergessen wird.
    enemies = set()

    def collect(node) -> None:
        if isinstance(node, dict):
            for field in ("EnemyName", "MonsterName", "BossNameLocalizationKey"):
                value = node.get(field)
                if isinstance(value, str) and value:
                    enemies.add(display_name(value))
            for value in node.values():
                collect(value)
        elif isinstance(node, list):
            for value in node:
                collect(value)

    collect(game_data)
    return {
        "_source": GAME_URL,
        "_erzeugt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "items": items,
        "gegner": sorted(enemies),
    }


def _summary(catalog: dict) -> str:
    """Was drinsteht — die Zeile, die man nach dem Lauf liest."""
    categories = {}
    for entry in catalog["items"].values():
        categories[entry["kategorie"]] = categories.get(entry["kategorie"], 0) + 1
    big = sorted(categories.items(), key=lambda kv: -kv[1])[:8]
    return (f"{len(catalog['items'])} Items in {len(categories)} Kategorien, "
            f"{len(catalog['gegner'])} Gegner\n"
            "  groesste Kategorien: "
            + ", ".join(f"{name} ({count})" for name, count in big))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Item-/Gegner-Katalog aus der Idle-Clans-API.")
    p.add_argument("--target", default=DEFAULT_TARGET,
                   help=f"Zieldatei (Standard: {DEFAULT_TARGET})")
    p.add_argument("--show", action="store_true",
                   help="nur anzeigen, nichts schreiben")
    args = p.parse_args(argv)

    print(f"Lade {GAME_URL} ...")
    hints: list = []
    try:
        game_data = fetch_game_data(hints=hints)
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"[FEHLER] Nicht erreichbar: {e}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:
        print(f"[FEHLER] Antwort ist auch nach der Uebersetzung der "
              f"Extended-JSON-Konstrukte kein JSON ({e}).", file=sys.stderr)
        return 1
    # Ein Hinweis, kein Abbruch: der Katalog braucht Namen, Slots und Werte —
    # ein neues Konstrukt in einem fremden Feld aendert daran nichts.
    for hint in hints:
        print(f"[WARNUNG] {hint}", file=sys.stderr)

    catalog = build_catalog(game_data)
    print(_summary(catalog))
    if args.show:
        return 0

    with open(args.target, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=1)
    print(f"[OK] Geschrieben: {args.target}")
    print("  Eintragen unter Einstellungen -> SCAN-EINSTELLUNGEN -> 'Item-Katalog' "
          "(config.json: scan_catalog_file)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
