#!/usr/bin/env python3
"""Schreibt den Item-/Gegner-Katalog aus der offiziellen Idle-Clans-API.

    python tools/katalog.py            # schreibt katalog.json
    python tools/katalog.py --ziel X   # anderer Pfad
    python tools/katalog.py --zeige    # nur anzeigen, nichts schreiben

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
STANDARD_ZIEL = "katalog.json"

# EquipmentSlot -> Kategorie. Die Zuordnung ist aus den Item-Namen der jeweiligen
# Gruppe abgelesen (alle 19 Eintraege von Slot 1 enden auf `_boots` usw.).
# Slot 12 kommt in den Daten nicht vor; 0 und 7 werden gesondert behandelt.
SLOTS = {
    1: "Stiefel", 2: "Ring", 3: "Handschuhe", 4: "Beine", 5: "Ruestung",
    6: "Schild", 8: "Amulett", 9: "Pfeile", 10: "Umhang", 11: "Helm",
    13: "Armband", 14: "Guertel", 15: "Pet", 16: "Ohrringe",
}
SLOT_WAFFE = 7          # Waffen und Werkzeuge gemeinsam — wird aufgetrennt
SLOT_KEINE = 0          # keine Ausruestung (Rohstoffe, Verbrauch)


def anzeigename(schluessel: str) -> str:
    """`godlike_bow` -> `Godlike Bow` — der Name, wie er im Spiel steht."""
    return schluessel.replace("_", " ").title()


def kategorie_fuer(item: dict) -> str:
    """Die Gruppe, innerhalb derer dieses Item mit anderen konkurriert."""
    slot = item.get("EquipmentSlot") or 0
    fest = SLOTS.get(slot)
    if fest:
        return fest
    # Slot 7 und 0: das letzte Wort ist die engste verlaessliche Gruppe.
    letztes = anzeigename(item.get("Name", "")).split()
    return letztes[-1] if letztes else "Sonstiges"


def hole_spieldaten(url: str = GAME_URL, timeout: int = 60) -> dict:
    """Laedt game-data und macht daraus gueltiges JSON.

    Der Endpunkt liefert MongoDB-Extended-JSON: `ObjectId("…")` ist kein
    gueltiger JSON-Wert und muss vorher weg. Dieselbe Behandlung wie in
    `market_analysis/analyse.py::load_game_data` — nur ohne `requests`.
    """
    req = urllib.request.Request(url, headers={"User-Agent": "autoclicker-katalog"})
    with urllib.request.urlopen(req, timeout=timeout) as antwort:
        roh = antwort.read().decode("utf-8")
    bereinigt = re.sub(r'ObjectId\("([a-f0-9]+)"\)', r'"\1"', roh)
    return json.loads(bereinigt)


def baue_katalog(spieldaten: dict) -> dict:
    """Aus den Spieldaten die beiden Listen, die der Autoclicker braucht."""
    items = {}
    for eintrag in (spieldaten.get("Items") or {}).get("Items") or []:
        schluessel = eintrag.get("Name")
        if not schluessel:
            continue
        items[anzeigename(schluessel)] = {
            "kategorie": kategorie_fuer(eintrag),
            "wert": eintrag.get("BaseValue") or 0,
        }

    # Gegner stehen verstreut (Kampf-Aufgaben, Raids, Clan-Bosse) und tragen mal
    # `EnemyName`, mal `MonsterName`, mal `BossNameLocalizationKey`. Eingesammelt
    # wird ueber den ganzen Baum, damit kein Zweig vergessen wird.
    gegner = set()

    def sammle(knoten) -> None:
        if isinstance(knoten, dict):
            for feld in ("EnemyName", "MonsterName", "BossNameLocalizationKey"):
                wert = knoten.get(feld)
                if isinstance(wert, str) and wert:
                    gegner.add(anzeigename(wert))
            for wert in knoten.values():
                sammle(wert)
        elif isinstance(knoten, list):
            for wert in knoten:
                sammle(wert)

    sammle(spieldaten)
    return {
        "_quelle": GAME_URL,
        "_erzeugt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "items": items,
        "gegner": sorted(gegner),
    }


def _zusammenfassung(katalog: dict) -> str:
    """Was drinsteht — die Zeile, die man nach dem Lauf liest."""
    kategorien = {}
    for eintrag in katalog["items"].values():
        kategorien[eintrag["kategorie"]] = kategorien.get(eintrag["kategorie"], 0) + 1
    gross = sorted(kategorien.items(), key=lambda kv: -kv[1])[:8]
    return (f"{len(katalog['items'])} Items in {len(kategorien)} Kategorien, "
            f"{len(katalog['gegner'])} Gegner\n"
            "  groesste Kategorien: "
            + ", ".join(f"{name} ({anzahl})" for name, anzahl in gross))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Item-/Gegner-Katalog aus der Idle-Clans-API.")
    p.add_argument("--ziel", default=STANDARD_ZIEL,
                   help=f"Zieldatei (Standard: {STANDARD_ZIEL})")
    p.add_argument("--zeige", action="store_true",
                   help="nur anzeigen, nichts schreiben")
    args = p.parse_args(argv)

    print(f"Lade {GAME_URL} ...")
    try:
        spieldaten = hole_spieldaten()
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"[FEHLER] Nicht erreichbar: {e}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:
        print(f"[FEHLER] Antwort ist kein JSON ({e}) — evtl. ein neues "
              "Extended-JSON-Konstrukt neben ObjectId(...).", file=sys.stderr)
        return 1

    katalog = baue_katalog(spieldaten)
    print(_zusammenfassung(katalog))
    if args.zeige:
        return 0

    with open(args.ziel, "w", encoding="utf-8") as f:
        json.dump(katalog, f, ensure_ascii=False, indent=1)
    print(f"[OK] Geschrieben: {args.ziel}")
    print("  Eintragen unter Einstellungen -> SCAN-EINSTELLUNGEN -> 'Item-Katalog' "
          "(config.json: scan_catalog_file)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
