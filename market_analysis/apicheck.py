"""
API-Check fuer analyse.py

Prueft die Annahmen, die die Gold/h-Analyse ueber die Idle-Clans-API trifft, gegen die
echte API - alles, was ohne Live-Zugriff nicht verifizierbar ist:

  1. Markt-Endpoint: heissen die Felder noch so? Liefert /latest dasselbe wie /latest/all?
  2. Game-Data: Struktur von Items/Tasks, unbekannte Felder, Skill-Namen ggue. SKILLS
  3. BaseTime-Einheit: Millisekunden (Annahme des Scripts) oder Sekunden?
  4. comprehensive-Endpoint: echte Feldnamen fuer Avg1D/7D/30D + Orderbook-Tiefe
  5. Player-Market-Handelbarkeit: gibt es ein Item-Feld dafuer? (is_player_shop_tradeable
     ist aktuell ein NO-OP-Stub)
  6. *_bar-Rezepte: welche haben mehr als eine Cost-Zeile? (Smelting-Magic-Reichweite)
  7. Speed-Formel: multiplikativ vs. additiv - druckt beide Varianten fuer ein paar
     Aktionen zum Stoppuhr-Abgleich im Spiel
  8. NPC-Preis: BaseValue ausgewaehlter Items zum Abgleich mit dem Vendor-Preis ingame

Braucht NUR `requests` (kein pandas/openpyxl/matplotlib) und aendert nichts - reines Lesen.

Aufruf:  python market_analysis/apicheck.py

Schreibt zusaetzlich api_check_report.json mit allen Rohbefunden. Die Datei enthaelt nur
oeffentliche Spiel-/Marktdaten (keine Accountdaten) und kann direkt weitergegeben werden.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter

import requests

MARKET_URL = "https://query.idleclans.com/api/PlayerMarket/items/prices/latest?includeAveragePrice=true"
MARKET_ALL_URL = "https://query.idleclans.com/api/PlayerMarket/items/prices/latest/all"
GAME_URL = "https://query.idleclans.com/api/Configuration/game-data"
COMPREHENSIVE_URL_TEMPLATE = "https://query.idleclans.com/api/PlayerMarket/items/prices/latest/comprehensive/{item_id}"

# Erwartungen, die analyse.py/config.py fest verdrahtet hat:
EXPECTED_MARKET_FIELDS = ["itemId", "highestBuyPrice", "lowestSellPrice",
                          "highestPriceVolume", "lowestPriceVolume", "dailyAveragePrice"]
EXPECTED_RECIPE_FIELDS = ["Name", "BaseTime", "ItemReward", "ItemAmount", "ExpReward",
                          "LevelRequirement", "Costs", "TaskId", "Disabled"]
EXPECTED_ITEM_FIELDS = ["ItemId", "Name", "BaseValue", "CanNotBeTraded", "CanNotBeSoldToGameShop"]
EXPECTED_COMPREHENSIVE_AVG_FIELDS = ["averagePrice1Day", "averagePrice7Days", "averagePrice30Days"]
EXPECTED_COMPREHENSIVE_VOLUME_FIELD = "tradeVolume1Day"

# Skill-Namen wie sie config.py in SKILLS erwartet (Punkt 2 des Checks).
KNOWN_SKILL_NAMES = [
    "Mining", "Fishing", "Foraging", "Woodcutting", "Cooking", "Carpentry", "Smithing",
    "Farming", "Crafting", "Agility", "Plundering", "Brewing",
    "Combat", "Enchanting", "Invocation", "ItemCreation",
]

# Fuer Punkt 7: so rechnet analyse.py aktuell (multiplikativ).
SPEED_CHECK_SKILLS = ["Mining", "Fishing", "Woodcutting", "Smithing"]
SPEED_CHECK_EQUIP_BOOST = 0.55 + 0.06
SPEED_CHECK_CLAN_BOOST = 0.05

REPORT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "api_check_report.json")

report: dict = {}


# ------------------------------------------------------------------
# Helfer
# ------------------------------------------------------------------

def head(title: str):
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def ok(msg):
    print(f"  [OK]   {msg}")


def bad(msg):
    print(f"  [!!]   {msg}")


def info(msg):
    print(f"  [ ]    {msg}")


def union_keys(dicts) -> list:
    keys = set()
    for d in dicts:
        if isinstance(d, dict):
            keys.update(d.keys())
    return sorted(keys)


def get(url, timeout=60, context="API"):
    try:
        resp = requests.get(url, timeout=timeout)
    except requests.RequestException as exc:
        bad(f"{context}: Request fehlgeschlagen: {exc}")
        return None
    if resp.status_code != 200:
        bad(f"{context}: HTTP {resp.status_code}")
        return None
    return resp


def check_fields(present: list, expected: list, label: str) -> dict:
    missing = [f for f in expected if f not in present]
    if missing:
        bad(f"{label}: FEHLENDE Felder: {missing}")
    else:
        ok(f"{label}: alle vom Script erwarteten Felder vorhanden")
    extra = [f for f in present if f not in expected]
    if extra:
        info(f"{label}: zusaetzliche Felder (vom Script ignoriert): {extra}")
    return {"present": present, "missing": missing, "extra": extra}


# ------------------------------------------------------------------
# 1. Markt-Endpoint
# ------------------------------------------------------------------

def check_market():
    head("1. MARKT-ENDPUNKT")
    resp = get(MARKET_URL, timeout=30, context="Markt")
    if resp is None:
        report["market"] = {"error": "nicht erreichbar"}
        return None
    data = resp.json()
    if not isinstance(data, list) or not data:
        bad(f"Antwort ist kein nicht-leeres Array, sondern {type(data).__name__}")
        report["market"] = {"error": "unerwarteter Typ"}
        return None

    ok(f"{len(data)} Eintraege")
    keys = union_keys(data[:200])
    field_report = check_fields(keys, EXPECTED_MARKET_FIELDS, "Markt-Felder")

    with_avg = sum(1 for i in data if i.get("dailyAveragePrice"))
    if with_avg == 0:
        bad("dailyAveragePrice ist bei KEINEM Item gesetzt -> alle Ø-Preis-Spalten waeren leer")
    else:
        ok(f"dailyAveragePrice bei {with_avg}/{len(data)} Items gesetzt")

    # Gegenprobe: liefert /latest/all mehr Items als /latest?
    # /latest/all ist optional - existiert der Endpunkt nicht, ist das kein Problem.
    all_resp = get(MARKET_ALL_URL, timeout=30, context="Markt (/latest/all, optional)")
    all_count = len(all_resp.json()) if all_resp is not None and isinstance(all_resp.json(), list) else None
    if all_count is not None:
        if all_count > len(data):
            bad(f"/latest/all liefert {all_count} Items, /latest nur {len(data)} "
                f"-> in config.py auf /latest/all wechseln")
        else:
            ok(f"/latest/all liefert {all_count} Items (nicht mehr als /latest) - aktueller Endpunkt reicht")
    else:
        ok("/latest/all nicht verfuegbar - /latest ist der richtige Endpunkt")

    report["market"] = {
        "count": len(data),
        "count_latest_all": all_count,
        "fields": field_report,
        "with_daily_average": with_avg,
        "sample": data[0],
    }
    return data


# ------------------------------------------------------------------
# 2./5. Game-Data: Items
# ------------------------------------------------------------------

def load_game():
    head("2. GAME-DATA LADEN")
    resp = get(GAME_URL, timeout=90, context="Game-Data")
    if resp is None:
        report["game_data"] = {"error": "nicht erreichbar"}
        return None
    raw = re.sub(r'ObjectId\("([a-f0-9]+)"\)', r'"\1"', resp.text)
    try:
        game = json.loads(raw)
    except json.JSONDecodeError as exc:
        bad(f"Kein gueltiges JSON nach ObjectId-Bereinigung: {exc}")
        # Kontext um die Fehlerstelle, damit man sieht, welches Konstrukt stoert
        start = max(0, exc.pos - 200)
        info(f"Kontext: ...{raw[start:exc.pos + 200]}...")
        report["game_data"] = {"error": f"JSONDecodeError: {exc}"}
        return None
    ok(f"geladen, Top-Level-Keys: {sorted(game.keys())}")
    report["game_data"] = {"top_level_keys": sorted(game.keys())}
    return game


def check_items(game: dict):
    head("2b. ITEMS + PLAYER-MARKET-FLAG")
    items = game.get("Items", {}).get("Items", [])
    if not items:
        bad("Items.Items ist leer - Pfad im Script (game['Items']['Items']) stimmt nicht mehr")
        report["items"] = {"error": "leer"}
        return
    ok(f"{len(items)} Items")

    keys = union_keys(items)
    field_report = check_fields(keys, EXPECTED_ITEM_FIELDS, "Item-Felder")

    without_id = sum(1 for it in items if it.get("ItemId") is None)
    if without_id:
        bad(f"{without_id} Items ohne ItemId (werden vom Script uebersprungen)")

    # Kandidaten fuer is_player_shop_tradeable() (aktuell NO-OP-Stub)
    candidates = [k for k in keys
                  if any(w in k.lower() for w in ("trade", "market", "sell", "shop", "vendor", "untradeable"))]
    if candidates:
        ok(f"Kandidaten-Felder fuer die Handelbarkeit: {candidates}")
        for k in candidates:
            values = Counter(repr(it.get(k)) for it in items)
            info(f"    {k}: {dict(values.most_common(5))}")
    else:
        info("Kein Feld gefunden, das nach Handelbarkeit aussieht "
             "-> is_player_shop_tradeable() bleibt zu Recht ein NO-OP")

    sample = next((it for it in items if it.get("ItemId") is not None), items[0])
    info(f"Beispiel-Item: {json.dumps(sample, ensure_ascii=False)[:600]}")

    report["items"] = {
        "count": len(items),
        "fields": field_report,
        "without_item_id": without_id,
        "tradeable_flag_candidates": candidates,
        "sample": sample,
    }


# ------------------------------------------------------------------
# 3./6. Tasks: Rezepte, Skill-Namen, BaseTime-Einheit
# ------------------------------------------------------------------

def collect_recipes(game: dict):
    tasks = game.get("Tasks", {})
    recipes = []
    for skill_name, blocks in tasks.items():
        for block in blocks or []:
            for r in block.get("Items", []) or []:
                recipes.append((skill_name, r))
    return tasks, recipes


def check_tasks(game: dict):
    head("3. TASKS / REZEPTE")
    tasks, recipes = collect_recipes(game)
    if not recipes:
        bad("Keine Rezepte gefunden - Pfad Tasks[skill][block]['Items'] stimmt nicht mehr")
        report["tasks"] = {"error": "leer"}
        return []
    ok(f"{len(tasks)} Skills, {len(recipes)} Rezepte gesamt")

    keys = union_keys(r for _, r in recipes)
    field_report = check_fields(keys, EXPECTED_RECIPE_FIELDS, "Rezept-Felder")

    cost_keys = union_keys(c for _, r in recipes for c in (r.get("Costs") or []))
    if set(cost_keys) >= {"Item", "Amount"}:
        ok(f"Cost-Zeilen-Felder: {cost_keys}")
    else:
        bad(f"Cost-Zeilen haben NICHT Item/Amount, sondern: {cost_keys}")

    # Skill-Namen abgleichen (z.B. ist "Item creation" im Script unbestaetigt)
    api_skills = sorted(tasks.keys())
    unknown = [s for s in api_skills if s not in KNOWN_SKILL_NAMES]
    stale = [s for s in KNOWN_SKILL_NAMES if s not in api_skills]
    info(f"Skills in der API: {api_skills}")
    if unknown:
        bad(f"Skills in der API, die SKILLS nicht kennt (laufen auf DEFAULT_SKILL_CONFIG "
            f"= keine Boosts!): {unknown}")
    else:
        ok("Alle API-Skills sind in SKILLS konfiguriert")
    if stale:
        bad(f"In SKILLS konfiguriert, aber in der API nicht vorhanden (toter Eintrag/Tippfehler): {stale}")

    disabled = sum(1 for _, r in recipes if r.get("Disabled"))
    raids = sum(1 for _, r in recipes if "raids_" in str(r.get("Name", "")).lower())
    no_time = sum(1 for _, r in recipes if not r.get("BaseTime"))
    no_reward = sum(1 for _, r in recipes
                    if r.get("ItemReward") is None or r.get("ItemReward", -1) < 0 or not r.get("ItemAmount"))
    info(f"Vom Script gefiltert: Disabled={disabled}, raids_={raids}, BaseTime<=0={no_time}, "
         f"kein Item-Reward={no_reward}")

    report["tasks"] = {
        "skill_count": len(tasks),
        "recipe_count": len(recipes),
        "api_skills": api_skills,
        "skills_unknown_to_script": unknown,
        "skills_missing_in_api": stale,
        "fields": field_report,
        "cost_keys": cost_keys,
        "filtered": {"disabled": disabled, "raids": raids, "no_base_time": no_time, "no_reward": no_reward},
        "sample": recipes[0][1],
    }
    return recipes


def check_base_time_unit(recipes):
    head("4. EINHEIT VON BaseTime (ms vs. s)")
    times = sorted(r.get("BaseTime", 0) for _, r in recipes if r.get("BaseTime"))
    if not times:
        bad("Keine BaseTime-Werte gefunden")
        return
    median = times[len(times) // 2]
    info(f"min={times[0]}  median={median}  max={times[-1]}  (n={len(times)})")
    if median >= 500:
        ok(f"Median {median} -> plausibel als MILLISEKUNDEN ({median / 1000:.1f}s pro Aktion). "
           f"Annahme im Script stimmt.")
    else:
        bad(f"Median {median} sieht nach SEKUNDEN aus. Dann rechnet analyse.py mit "
            f"3_600_000ms/h um Faktor 1000 falsch - dort auf 3600 umstellen!")
    report["base_time"] = {"min": times[0], "median": median, "max": times[-1], "count": len(times)}


def check_bar_recipes(recipes, items):
    head("5. *_bar-REZEPTE (Smelting-Magic-Reichweite)")
    ASTRO_ITEMS = [it for it in items if "astronomical_ore" in str(it.get("Name", "")).lower()]
    bars = [(s, r) for s, r in recipes
            if s == "Smithing" and str(r.get("Name", "")).endswith("_bar") and not r.get("Disabled")]
    if not bars:
        bad("Keine Smithing-Rezepte mit Namensendung '_bar' gefunden -> die Erkennung im "
            "Script (name.endswith('_bar')) greift nicht mehr!")
        report["bar_recipes"] = {"error": "keine gefunden"}
        return
    ok(f"{len(bars)} Bar-Rezepte")
    rows = []
    for _, r in bars:
        costs = r.get("Costs") or []
        rows.append({"name": r.get("Name"), "cost_lines": len(costs),
                     "costs": [{"Item": c.get("Item"), "Amount": c.get("Amount")} for c in costs]})
        marker = " <- Best/Worst-Case relevant" if len(costs) > 1 else ""
        print(f"    {r.get('Name'):<28} {len(costs)} Cost-Zeile(n){marker}")
    # config.py nimmt Astronomical ore als ZUTAT vom Rabatt aus (nicht das Rezept
    # als Ganzes) - hier gegenpruefen, ob diese Zutat ueberhaupt in Bar-Rezepten vorkommt.
    astro_ids = {it.get("ItemId") for it in ASTRO_ITEMS}
    using_astro = [row for row in rows
                   if any(c["Item"] in astro_ids for c in row["costs"])]
    if astro_ids:
        ok(f"Astronomical-Erz Item-ID(s): {sorted(i for i in astro_ids if i is not None)}")
        if using_astro:
            ok(f"Bar-Rezepte mit Astronomical ore als Zutat (dort greift die Ausnahme): "
               f"{[r['name'] for r in using_astro]}")
        else:
            info("Kein Bar-Rezept nutzt Astronomical ore - die Ausnahme greift aktuell fuer nichts")
    else:
        bad("Kein Item mit 'astronomical_ore' im Namen gefunden -> die Ausnahme in "
            "SMELTING_MAGIC_EXCLUDED_ITEM_NAMES matcht nichts mehr")
    report["bar_recipes"] = {"recipes": rows,
                             "astronomical_ore_item_ids": sorted(i for i in astro_ids if i is not None),
                             "recipes_using_astronomical_ore": [r["name"] for r in using_astro]}


def check_speed_formula(recipes):
    head("6. SPEED-FORMEL: MULTIPLIKATIV vs. ADDITIV (Stoppuhr-Abgleich)")
    print("  Starte die genannte Aktion ingame und vergleiche die angezeigte/gestoppte")
    print("  Aktionsdauer mit den beiden Spalten. Passt 'additiv' besser, in")
    print("  analyse.py normalize_recipe() die Formel umstellen.\n")
    print(f"  (angenommen: Equipment {SPEED_CHECK_EQUIP_BOOST:.0%}, Clan-Gatherers "
          f"{SPEED_CHECK_CLAN_BOOST:.0%} wo zutreffend)\n")
    rows = []
    for skill in SPEED_CHECK_SKILLS:
        candidates = [r for s, r in recipes
                      if s == skill and r.get("BaseTime") and not r.get("Disabled")
                      and not str(r.get("Name", "")).lower().startswith("raids_")]
        if not candidates:
            continue
        r = min(candidates, key=lambda x: (x.get("LevelRequirement") or 0, x.get("BaseTime")))
        clan = SPEED_CHECK_CLAN_BOOST if skill in ("Mining", "Fishing", "Foraging", "Woodcutting") else 0.0
        base_s = r["BaseTime"] / 1000.0
        mult = base_s * (1 - clan) * (1 - SPEED_CHECK_EQUIP_BOOST)
        add = base_s * max(0.0, 1 - clan - SPEED_CHECK_EQUIP_BOOST)
        # Ohne Clan-Boost sind beide Formeln identisch - dort ist nichts zu messen.
        note = "" if clan else "   (kein Clan-Boost -> beide Formeln gleich, nicht aussagekraeftig)"
        print(f"    {skill:<12} {str(r.get('Name')):<24} basis={base_s:6.2f}s   "
              f"multiplikativ={mult:5.2f}s   additiv={add:5.2f}s{note}")
        rows.append({"skill": skill, "name": r.get("Name"), "base_sec": base_s,
                     "multiplicative_sec": mult, "additive_sec": add})
    report["speed_formula"] = {
        "equipment_boost": SPEED_CHECK_EQUIP_BOOST,
        "clan_boost": SPEED_CHECK_CLAN_BOOST,
        "rows": rows,
    }


def check_npc_values(game: dict, recipes):
    head("7. NPC-PREIS (BaseValue x 1.155) - Abgleich mit dem Vendor ingame")
    print("  Vergleiche 'erwartet' mit dem Preis, den der NPC-Shop dir tatsaechlich bietet.")
    print("  Passt es nicht, ist entweder BaseValue etwas anderes als der Vendor-Basispreis")
    print("  oder der Boost-Faktor (An offer they can't refuse + Potion of negotiation).\n")
    items = {it["ItemId"]: it for it in game.get("Items", {}).get("Items", []) if it.get("ItemId") is not None}
    seen, rows = set(), []
    for skill, r in recipes:
        iid = r.get("ItemReward")
        if iid in items and iid not in seen and items[iid].get("BaseValue"):
            seen.add(iid)
            it = items[iid]
            expected = it["BaseValue"] * 1.155
            print(f"    {str(it.get('Name')):<28} BaseValue={it['BaseValue']:>8,}  erwartet={expected:>10,.1f}")
            rows.append({"item_id": iid, "name": it.get("Name"),
                         "base_value": it["BaseValue"], "expected_with_boost": expected})
        if len(rows) >= 6:
            break
    report["npc_values"] = rows


# ------------------------------------------------------------------
# 8. comprehensive-Endpoint
# ------------------------------------------------------------------

def check_comprehensive(market_data):
    head("8. COMPREHENSIVE-ENDPUNKT (Avg1D/7D/30D + Orderbook-Tiefe)")
    if not market_data:
        info("uebersprungen (keine Marktdaten)")
        return
    # ein gut gehandeltes Item nehmen, damit die Tiefen-Arrays gefuellt sind
    liquid = max(market_data, key=lambda i: (i.get("highestPriceVolume") or 0))
    item_id = liquid.get("itemId")
    info(f"Testitem: itemId={item_id} (hoechstes Buy-Volumen)")

    resp = get(COMPREHENSIVE_URL_TEMPLATE.format(item_id=item_id), timeout=30, context="comprehensive")
    if resp is None:
        report["comprehensive"] = {"error": "nicht erreichbar"}
        return
    data = resp.json()
    keys = sorted(data.keys()) if isinstance(data, dict) else []
    if not keys:
        bad(f"Antwort ist kein Objekt, sondern {type(data).__name__}")
        report["comprehensive"] = {"error": "unerwarteter Typ", "raw": str(data)[:500]}
        return
    info(f"Alle Keys: {keys}")

    avg_report = check_fields(keys, EXPECTED_COMPREHENSIVE_AVG_FIELDS, "Avg-Felder (COMPREHENSIVE_AVG_FIELDS)")
    if avg_report["missing"]:
        guesses = [k for k in keys if any(w in k.lower() for w in ("average", "avg", "week", "month", "daily"))]
        bad(f"-> COMPREHENSIVE_AVG_FIELDS in config.py anpassen. Kandidaten: {guesses}")

    if EXPECTED_COMPREHENSIVE_VOLUME_FIELD in keys:
        ok(f"Volumen-Feld '{EXPECTED_COMPREHENSIVE_VOLUME_FIELD}' vorhanden")
    else:
        vol_guesses = [k for k in keys if "volume" in k.lower()]
        bad(f"'{EXPECTED_COMPREHENSIVE_VOLUME_FIELD}' fehlt. Kandidaten: {vol_guesses}")

    # Orderbook-Tiefe: das Script erwartet Listen mit {"key": preis, "value": menge}
    depth_report = {}
    for field in ("highestBuyPricesWithVolume", "lowestSellPricesWithVolume"):
        entries = data.get(field)
        if not isinstance(entries, list):
            bad(f"'{field}' fehlt oder ist keine Liste (Preis-Sensitivitaet/Orderbook-Tiefe kaputt)")
            depth_report[field] = None
            continue
        entry_keys = union_keys(entries)
        if set(entry_keys) >= {"key", "value"}:
            ok(f"{field}: {len(entries)} Stufen, Felder {entry_keys}")
        else:
            bad(f"{field}: erwartet key/value, gefunden {entry_keys}")
        depth_report[field] = {"count": len(entries), "entry_keys": entry_keys, "sample": entries[:3]}

    report["comprehensive"] = {"item_id": item_id, "keys": keys, "avg_fields": avg_report,
                               "depth": depth_report, "sample": {k: data[k] for k in keys[:15]}}


# ------------------------------------------------------------------

def main():
    print("API-Check fuer analyse.py - reines Lesen, aendert nichts.\n")
    market_data = check_market()
    game = load_game()
    recipes = []
    if game is not None:
        check_items(game)
        recipes = check_tasks(game)
        if recipes:
            check_base_time_unit(recipes)
            check_bar_recipes(recipes, game.get('Items', {}).get('Items', []))
            check_speed_formula(recipes)
            check_npc_values(game, recipes)
    check_comprehensive(market_data)

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)

    head("FERTIG")
    problems = []
    for section, content in report.items():
        if not isinstance(content, dict):
            continue
        if content.get("error"):
            problems.append(f"{section}: {content['error']}")
        # "fields" (Markt/Items/Tasks) und "avg_fields" (comprehensive) gleich behandeln
        for sub in content.values():
            if isinstance(sub, dict) and sub.get("missing"):
                problems.append(f"{section}: fehlende Felder {sub['missing']}")
    if problems:
        print("  Auffaelligkeiten:")
        for p in problems:
            print(f"    - {p}")
    else:
        print("  Keine fehlenden Pflichtfelder gefunden.")
    print(f"\n  Vollstaendiger Bericht: {REPORT_PATH}")
    print("  -> Diese Datei (oder die Konsolenausgabe) zurueckschicken.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
