"""
Idle Clans - Gold/h Farming-Analyse

Zieht Marktpreise + Rezepte aus der Idle-Clans-API, rechnet fuer jedes farmbare Item
Gold/h unter Beruecksichtigung der Account-Upgrades und exportiert nach Excel.

Was gerechnet wird, welche Annahmen ingame verifiziert sind und was noch offen ist:
siehe README.md. Alles Einstellbare steht in config.py.

    pip install pandas requests openpyxl matplotlib
    python market_analysis/analyse.py
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime

import pandas as pd
import requests
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from config import *  # noqa: F401,F403  - Einstellungen, s. config.py


# ---------------------------------------------------------------
# Daten Laden
# ---------------------------------------------------------------

def _get_json(url: str, timeout: int = 30, context: str = "API") -> requests.Response:
    """Ein Request, ein Fehlerbild: Netzwerkfehler und HTTP-Fehlercodes werden hier zu
    einer verstaendlichen Meldung. Ohne das kippt ein 500er/HTML-Fehlerdokument spaeter
    als kryptischer JSONDecodeError raus - oder schlimmer: der Lauf rechnet mit einer
    halben Antwort weiter."""
    try:
        resp = requests.get(url, timeout=timeout)
    except requests.RequestException as exc:
        raise RuntimeError(f"{context}: Request fehlgeschlagen ({exc}) - URL: {url}") from exc
    if resp.status_code != 200:
        raise RuntimeError(f"{context}: HTTP {resp.status_code} von {url}")
    return resp


def load_market_map() -> dict:
    """ItemId -> Bid/Ask/Volumen. Bid ("buy") = Preis bei Sofortverkauf, Ask ("sell") =
    Preis bei Sofortkauf. buyVol begrenzt Sofortverkauf, sellVol begrenzt Sofortkauf."""
    resp = _get_json(MARKET_URL, timeout=30, context="Markt-Endpoint")
    payload = resp.json()
    if not isinstance(payload, list) or not payload:
        raise RuntimeError(f"Markt-Endpoint: unerwartete/leere Antwort ({type(payload).__name__}) - URL: {MARKET_URL}")

    market_map = {}
    for i in payload:
        market_map[i.get("itemId")] = {
            "buy": i.get("highestBuyPrice", 0),
            "sell": i.get("lowestSellPrice", 0),
            "buyVol": i.get("highestPriceVolume", 0),
            "sellVol": i.get("lowestPriceVolume", 0),
            "avg": i.get("dailyAveragePrice", 0),
        }

    # Schema-Drift-Warnung: die Ø-Preis-Spalten (und price_anomaly()) haengen komplett an
    # dailyAveragePrice. Wenn das Feld verschwindet/umbenannt wird, wuerde das sonst nur
    # als "keine Anomalien gefunden" durchrutschen statt als Fehler aufzufallen.
    if not any(entry["avg"] for entry in market_map.values()):
        example_keys = sorted(payload[0].keys())
        print("⚠ Markt-Endpoint: 'dailyAveragePrice' ist bei KEINEM Item gesetzt. Entweder war "
              "includeAveragePrice wirkungslos oder das Feld heisst jetzt anders.\n"
              f"  Vorhandene Keys im ersten Eintrag: {example_keys}")

    return market_map


def load_game_data() -> dict:
    """Game-Data-Endpoint liefert MongoDB-Extended-JSON (ObjectId(...) ist kein valides
    JSON) - wird vor dem Parsen bereinigt."""
    resp = _get_json(GAME_URL, timeout=60, context="Game-Data-Endpoint")
    raw = re.sub(r'ObjectId\("([a-f0-9]+)"\)', r'"\1"', resp.text)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Game-Data-Endpoint: Antwort ist kein gueltiges JSON ({exc}) - "
                           "evtl. neues Extended-JSON-Konstrukt neben ObjectId(...).") from exc


def build_item_info_map(game: dict) -> dict:
    """ItemId -> {name, base_value, can_trade, can_sell_to_npc}.

    Die API-Flags heissen negiert (CanNotBeTraded / CanNotBeSoldToGameShop) und werden
    hier gedreht. Default bei fehlendem Feld: erlaubt."""
    info = {}
    for it in game.get("Items", {}).get("Items", []):
        item_id = it.get("ItemId")
        if item_id is None:
            continue
        info[item_id] = {
            "name": it.get("Name", f"item_{item_id}"),
            "base_value": it.get("BaseValue", 0),
            "can_trade": not it.get("CanNotBeTraded", False),
            "can_sell_to_npc": not it.get("CanNotBeSoldToGameShop", False),
            "market_buy_limit": it.get("PlayerMarketBuyLimit", 0),
        }
    return info


def resolve_smelting_magic_exclusions(item_info_map: dict) -> frozenset:
    """Item-IDs der Erze, auf die Smelting Magic nicht wirkt (s.
    SMELTING_MAGIC_EXCLUDED_ITEM_NAMES). Ueber den Namen aufgeloest statt hart verdrahtet,
    damit eine ID-Verschiebung in der API das nicht still kaputt macht."""
    return frozenset(
        iid for iid, entry in item_info_map.items()
        if any(name in str(entry.get("name", "")).lower() for name in SMELTING_MAGIC_EXCLUDED_ITEM_NAMES)
    )


# ---------------------------------------------------------------
# Markt-/Preis-Hilfsfunktionen
# ---------------------------------------------------------------

def valid_market(item: dict) -> bool:
    """Hard-Filter: hat das Item ueberhaupt einen echten, liquiden Markt? Spread ist
    bewusst KEIN Ausschlusskriterium mehr (siehe wide_spread()) - manche Items haben
    legitim einen breiten Spread (tiefer Markt), sind aber ueber eine Sell-Order statt
    Sofortverkauf trotzdem gut handelbar."""
    buy, sell = item["buy"], item["sell"]
    if buy <= 0 or sell <= 0:
        return False
    if item["buyVol"] < MIN_MARKET_VOLUME or item["sellVol"] < MIN_MARKET_VOLUME:
        return False
    return True


def wide_spread(item: dict) -> bool:
    """Weiche WARNUNG: Ask (sell) liegt um mehr als MAX_SPREAD_RATIO ueber Bid (buy).
    Kein Ausschlusskriterium - nur ein Hinweis, dass der Markt tief/duenn ist."""
    buy, sell = item["buy"], item["sell"]
    if buy <= 0:
        return False
    return abs(sell - buy) / buy > MAX_SPREAD_RATIO


def price_anomaly(item: dict) -> bool:
    """Weiche WARNUNG (kein Hard-Filter): weicht Bid/Ask stark vom 24h-Avg ab?"""
    avg = item.get("avg", 0)
    if avg <= 0:
        return False
    return abs(item["buy"] - avg) / avg > MAX_AVG_DEVIATION_RATIO or abs(item["sell"] - avg) / avg > MAX_AVG_DEVIATION_RATIO


def npc_sell_price(item_id: int, item_info_map: dict) -> float:
    """Sofortverkauf an den NPC-Vendor (unbegrenztes Volumen). Items mit
    CanNotBeSoldToGameShop bekommen 0."""
    entry = item_info_map.get(item_id)
    if entry is None or not entry.get("can_sell_to_npc", True):
        return 0.0
    return entry.get("base_value", 0) * NPC_SELL_BOOST_MULTIPLIER


def effective_sell_price(item_id: int, market_map: dict, item_info_map: dict) -> tuple[float, bool]:
    """Bester Verkaufsweg fuer das Endprodukt: Player-Market-Bid (nur wenn handelbar UND
    liquide genug, sonst Verlustgefahr durch fehlende Abnahme) vs. NPC-Vendor-Preis. Gibt
    (Preis, sold_to_npc) zurueck. sold_to_npc=True heisst: NPC ist die bessere/einzige Option.
    Sind beide Wege gesperrt, kommt 0 zurueck -> das Item faellt aus Ketten raus und
    bekommt in Rohdaten einen Klartext-Grund."""
    m = market_map.get(item_id)
    tradeable = is_player_shop_tradeable(item_info_map.get(item_id, {}))
    # Netto: der Player-Markt zieht Steuer ab, der NPC nicht - sonst waere der Vergleich
    # der beiden Wege systematisch zugunsten der Spieler verzerrt.
    market_price = (
        net_player_price(m["buy"])
        if (tradeable and m is not None and valid_market(m) and m["buyVol"] >= MIN_SELL_VOLUME) else 0.0
    )
    npc_price = npc_sell_price(item_id, item_info_map)
    if npc_price > market_price:
        return npc_price, True
    return market_price, False


def is_player_shop_tradeable(item_info: dict) -> bool:
    """Kann das Item im Player Market gelistet werden? Basiert auf dem per Live-Check
    bestaetigten Item-Feld CanNotBeTraded (in build_item_info_map als can_trade
    gespeichert). Fehlt die Angabe, wird - wie frueher - Handelbarkeit angenommen."""
    return bool(item_info.get("can_trade", True))


def is_raid_recipe(name: str) -> bool:
    return "raids_" in str(name).lower()


# ---------------------------------------------------------------
# Rezept-Normalisierung
# ---------------------------------------------------------------

def _is_smelting_magic_recipe(skill_name: str, recipe_name: str) -> bool:
    """Ore -> Bar Schmelzen, auf das Smelting Magic ueberhaupt wirkt. Welche einzelnen
    ZUTATEN davon ausgenommen sind, entscheidet normalize_recipe pro Cost-Zeile
    (s. SMELTING_MAGIC_EXCLUDED_ITEM_NAMES)."""
    return skill_name == "Smithing" and recipe_name.endswith("_bar")


def normalize_recipe(skill_name: str, raw_recipe: dict, case: str = "best",
                      excluded_cost_items: frozenset = frozenset()) -> dict | None:
    if raw_recipe.get("Disabled", False):
        return None  # z.B. Citadel-Raid-only-Content (bestaetigt per Live-Check: Disabled=True)

    if is_raid_recipe(raw_recipe.get("Name", "")):
        return None

    base_time = raw_recipe.get("BaseTime", 0.0)
    if base_time <= 0:
        return None  # Kategorie-Platzhalter, keine echte Aktion

    item_id = raw_recipe.get("ItemReward", -1)
    item_amount = raw_recipe.get("ItemAmount", 0)
    if item_id is None or item_id < 0 or item_amount <= 0:
        return None  # kein direkter Item-Reward (z.B. Scrolls)

    cfg = skill_cfg(skill_name)
    clan_boost = CLAN_GATHERERS_SPEED_BOOST if cfg.is_gathering else 0.0
    speed_factor = (1.0 - clan_boost) * (1.0 - cfg.equipment_speed_boost)
    if speed_factor <= 0:
        # Ein Speed-Boost von >=100% ist keine gueltige Konfiguration (Aktionszeit 0 oder
        # negativ). Lieber laut und einmalig scheitern als stillschweigend Gold/h=inf.
        raise ValueError(
            f"Skill '{skill_name}': equipment_speed_boost={cfg.equipment_speed_boost} ergibt "
            "Aktionszeit <= 0. Wert in SKILLS pruefen (0.61 = 61% schneller, nicht 61)."
        )
    yield_factor = cfg.yield_multiplier * (1.0 + GLOVES_DOUBLE_CHANCE if cfg.gloves_owned else 1.0)

    # Smelting Magic wirkt nur beim Ore->Bar-Schmelzen (Recipe-Name endet auf "_bar"),
    # nicht generell auf alle Smithing-Rezepte (siehe Kommentar bei SMITHING_SMELTING_COST_MULTIPLIER).
    # Reichweite innerhalb des Rezepts ist unklar (s. Kommentar oben) -> pro Cost-Zeile:
    # Best-Case = Rabatt auf ALLE Zeilen, Worst-Case = nur auf die erste Zeile (Haupt-Erz).
    is_bar_smelt = _is_smelting_magic_recipe(skill_name, raw_recipe.get("Name", ""))
    costs = []
    for i, c in enumerate(raw_recipe.get("Costs") or []):
        if is_bar_smelt:
            if c.get("Item") in excluded_cost_items:
                line_mult = 1.0   # Astronomical ore: vom Perk ausgenommen, immer voller Preis
            elif case == "best" or i == 0:
                line_mult = SMITHING_SMELTING_COST_MULTIPLIER
            else:
                line_mult = 1.0
        else:
            line_mult = cfg.cost_multiplier
        costs.append({"Item": c.get("Item"), "Amount": c.get("Amount", 0) * line_mult})

    return {
        "name": raw_recipe.get("Name", "unknown"),
        "skill": skill_name,
        "item_id": item_id,
        "base_time_ms": base_time * speed_factor,
        "item_amount": item_amount * yield_factor,
        "xp": raw_recipe.get("ExpReward", 0.0) * (1.0 + XP_BOOST_TOTAL) * (1.0 + DAILY_XP_BOOST),
        "level": raw_recipe.get("LevelRequirement"),
        "costs": costs,
        "task_id": raw_recipe.get("TaskId"),
        "cost_case_ambiguous": is_bar_smelt and len(costs) > 1,
    }


def build_all_recipes(tasks: dict, case: str = "best",
                       excluded_cost_items: frozenset = frozenset()) -> list:
    all_recipes = []
    unknown_skills = []
    for skill_name, blocks in tasks.items():
        if skill_name not in SKILLS:
            unknown_skills.append(skill_name)
        if skill_cfg(skill_name).excluded:
            continue
        for block in blocks:
            for raw_recipe in block.get("Items", []):
                normalized = normalize_recipe(skill_name, raw_recipe, case=case,
                                              excluded_cost_items=excluded_cost_items)
                if normalized is not None:
                    all_recipes.append(normalized)

    # Ein Skill, den SKILLS nicht kennt, laeuft still auf DEFAULT_SKILL_CONFIG - also
    # ohne JEDEN Boost. Genau so ist frueher "ItemCreation" (Script-Key hatte ein
    # Leerzeichen) unbemerkt in die Auswertung gerutscht.
    if unknown_skills and case == "best":
        print(f"⚠ Skills aus der API ohne Eintrag in SKILLS: {sorted(unknown_skills)} - sie laufen "
              "ohne Speed-/Yield-/Cost-Boosts mit. In SKILLS ergaenzen (oder excluded=True setzen).")
    return all_recipes


def check_action_time_plausibility(all_recipes: list):
    if not all_recipes:
        return
    times = sorted(r["base_time_ms"] / 1000.0 for r in all_recipes)
    median = times[len(times) // 2]
    if MIN_PLAUSIBLE_ACTION_SEC <= median <= MAX_PLAUSIBLE_ACTION_SEC:
        return
    print(f"⚠ Median-Aktionszeit liegt bei {median:.4f}s (erwartet {MIN_PLAUSIBLE_ACTION_SEC}-"
          f"{MAX_PLAUSIBLE_ACTION_SEC}s). Das Script setzt voraus, dass 'BaseTime' in "
          "MILLISEKUNDEN geliefert wird - stimmt das nicht mehr, sind ALLE Gold/h- und "
          "XP/h-Werte um denselben Faktor falsch. Einheit im API-Feld pruefen.")


def build_recipe_by_output(all_recipes: list) -> dict:
    """1 Eintrag pro ItemId: das Recipe mit der kuerzesten Zeit/Stueck.

    Vereinfachung: Auswahl rein nach Zeit, nicht nach Gewinn (s. README, "Bekannte
    Vereinfachungen")."""
    best = {}
    for r in all_recipes:
        time_per_unit = r["base_time_ms"] / r["item_amount"]
        current = best.get(r["item_id"])
        if current is None or time_per_unit < current["base_time_ms"] / current["item_amount"]:
            best[r["item_id"]] = r
    return best


def build_fish_to_cooked_map(all_recipes: list, recipe_by_output: dict) -> dict:
    """RawFishId -> CookedFishId, fuer Recipes mit genau 1 Zutat aus Fishing (Auto-Cook-Upgrade).
    Unabhaengig vom Best-/Worst-Case (betrifft nur Anzahl/Struktur der Cost-Zeilen, nicht
    deren Menge) - kann mit den Recipes aus einem beliebigen Case gebaut werden."""
    fishing_ids = {iid for iid, r in recipe_by_output.items() if r["skill"] == AUTO_COOK_SOURCE_SKILL}
    fish_to_cooked = {}
    for r in all_recipes:
        if r["skill"] == "Cooking" and len(r["costs"]) == 1:
            raw_id = r["costs"][0]["Item"]
            if raw_id in fishing_ids:
                fish_to_cooked[raw_id] = r["item_id"]
    return fish_to_cooked


# ============================================================
# 7. EINZELSCHRITT-ANALYSE ("Rohdaten"-Tab)
# ============================================================

def build_single_step_df(all_recipes: list, market_map: dict, item_info_map: dict) -> pd.DataFrame:
    results = []
    for r in all_recipes:
        # Nicht handelbare Items werden NICHT uebersprungen: sie koennen ueber den
        # NPC-Vendor trotzdem Gold bringen, und wenn nicht, ist der Grund im Rohdaten-Tab
        # sichtbar statt still zu verschwinden.
        item_info = item_info_map.get(r["item_id"], {})
        can_trade = is_player_shop_tradeable(item_info)
        can_sell_npc = bool(item_info.get("can_sell_to_npc", True))

        sell_price, sold_to_npc = effective_sell_price(r["item_id"], market_map, item_info_map)

        # m wird fuer Zusatzinfos (Avg-Preis, Volumen, Anomalie-Checks) weiterverwendet.
        # Bei sold_to_npc=True ist der Player-Markt entweder nicht liquide genug oder
        # schlechter als der NPC-Preis - Markt-Warnungen/Volumen sind dann irrelevant.
        m = market_map.get(r["item_id"]) or {"buy": 0, "sell": 0, "buyVol": 0, "sellVol": 0, "avg": 0}

        # Rohdaten hat keinen Hard-Filter: jedes Recipe bleibt sichtbar, der Grund steht
        # im Klartext in "AusschlussGrund". InKetten=True heisst nur "verkaufbar" - das
        # Item kann trotzdem im Ketten-Tab fehlen (s. README).
        in_ketten = sell_price > 0
        exclusion_reason = ""
        if not in_ketten:
            # Beide Verkaufswege einzeln begruenden: Player-Markt und NPC-Vendor koennen
            # aus voellig verschiedenen Gruenden ausfallen.
            if not can_trade:
                market_reason = "Nicht am Player-Markt handelbar (CanNotBeTraded)"
            elif m["buy"] <= 0 or m["sell"] <= 0:
                market_reason = "Kein Markteintrag"
            elif not valid_market(m):
                market_reason = f"Markt zu duenn (Volumen < {MIN_MARKET_VOLUME})"
            elif m["buyVol"] < MIN_SELL_VOLUME:
                market_reason = f"Zu wenig Nachfrage (BuyVol {m['buyVol']:,} < {MIN_SELL_VOLUME:,})"
            else:
                market_reason = "Kein Verkaufspreis"
            npc_reason = ("kein NPC-Verkauf erlaubt (CanNotBeSoldToGameShop)" if not can_sell_npc
                          else "kein NPC-Preis (BaseValue 0)")
            exclusion_reason = f"{market_reason} + {npc_reason}"

        actions_per_hour = 3_600_000.0 / r["base_time_ms"]
        items_per_hour = actions_per_hour * r["item_amount"]
        gold_per_hour = items_per_hour * sell_price
        xp_per_hour = actions_per_hour * r["xp"]

        # Ø-Preis-Variante: dailyAveragePrice statt Bid, fuer Sell-Order-Strategie statt
        # Sofortverkauf (realistischer bei breitem Spread, siehe SpreadWarning). Nur
        # relevant, wenn ueberhaupt am Player-Markt verkauft wird.
        revenue_per_hour_avg = (items_per_hour * net_player_price(m["avg"])
                                if (not sold_to_npc and m["avg"] > 0) else None)

        cost_per_action = 0.0
        cost_data_complete = True
        ingredient_market_unhealthy = False
        ingredient_price_anomaly = False
        ingredient_spread_warning = False
        max_liquidity_ratio = 0.0

        for c in r["costs"]:
            cm = market_map.get(c["Item"])
            if cm is None:
                cost_data_complete = False
                ingredient_market_unhealthy = True
                continue
            cost_per_action += cm["sell"] * c["Amount"]
            if not valid_market(cm):
                ingredient_market_unhealthy = True
            if price_anomaly(cm):
                ingredient_price_anomaly = True
            if wide_spread(cm):
                ingredient_spread_warning = True
            if cm["sellVol"] > 0:
                max_liquidity_ratio = max(max_liquidity_ratio, (c["Amount"] * actions_per_hour) / cm["sellVol"])

        if not sold_to_npc and m["buyVol"] > 0:
            max_liquidity_ratio = max(max_liquidity_ratio, items_per_hour / m["buyVol"])

        cost_per_hour = cost_per_action * actions_per_hour
        profit_per_hour = gold_per_hour - cost_per_hour
        profit_per_hour_avg = (revenue_per_hour_avg - cost_per_hour) if revenue_per_hour_avg is not None else None
        output_anomaly = price_anomaly(m) if not sold_to_npc else False
        output_spread_warning = wide_spread(m) if not sold_to_npc else False

        liquidity_warning = max_liquidity_ratio > LIQUIDITY_WARNING_RATIO or ingredient_market_unhealthy
        price_anomaly_flag = output_anomaly or ingredient_price_anomaly
        spread_warning_flag = output_spread_warning or ingredient_spread_warning

        if in_ketten:
            status = "OK"
            warn_parts = []
            if liquidity_warning:
                warn_parts.append("Liquiditaet")
            if price_anomaly_flag:
                warn_parts.append("Preisanomalie")
            if spread_warning_flag:
                warn_parts.append("Spread")
            if warn_parts:
                status = "Warnung"
                exclusion_reason = "Warnung: " + ", ".join(warn_parts)
        else:
            status = "Ausgeschlossen"

        results.append({
            "Item": r["name"], "Skill": r["skill"], "Level": r["level"],
            "Time_sec": r["base_time_ms"] / 1000.0,
            "XP": r["xp"],
            "Gold/h": profit_per_hour,
            "Gold/h (Ø-Preis)": profit_per_hour_avg,
            "Gold pro Stück": (profit_per_hour / items_per_hour) if items_per_hour > 0 else 0.0,
            "Stück/h": items_per_hour,
            "Revenue/h": gold_per_hour,
            "Revenue/h (Ø-Preis)": revenue_per_hour_avg,
            "Cost/h": cost_per_hour,
            "SoldToNPC": sold_to_npc,
            "NPCPreis": npc_sell_price(r["item_id"], item_info_map),
            "MarketBid": m["buy"],
            "MarketAsk": m["sell"],
            "Handelbar": can_trade,
            "NPCVerkaufMoeglich": can_sell_npc,
            "CostDataComplete": cost_data_complete,
            "InKetten": in_ketten,
            "Status": status,
            "AusschlussGrund": exclusion_reason,
            "LiquidityWarning": liquidity_warning,
            "LiquidityRatio": round(max_liquidity_ratio, 1),
            "IngredientMarketUnhealthy": ingredient_market_unhealthy,
            "PriceAnomaly": price_anomaly_flag,
            "OutputPriceAnomaly": output_anomaly,
            "IngredientPriceAnomaly": ingredient_price_anomaly,
            "SpreadWarning": spread_warning_flag,
            "OutputSpreadWarning": output_spread_warning,
            "IngredientSpreadWarning": ingredient_spread_warning,
            "BuyVol": m["buyVol"], "SellVol": m["sellVol"],
            "XP/h": xp_per_hour,
            "Gold per XP": profit_per_hour / max(xp_per_hour, 1),
            "ItemID": r["item_id"], "TaskId": r["task_id"],
            "CostCaseAmbiguous": r["cost_case_ambiguous"],
        })
    return pd.DataFrame(results)


def _merge_worst_case(df_best: pd.DataFrame, df_worst: pd.DataFrame,
                       keys: list[str], worst_cols: list[str], label: str) -> pd.DataFrame:
    """Gemeinsamer Merge-Kern fuer Rohdaten und Ketten. how="left" + one_to_one, damit
    doppelte Schluessel einen Fehler geben statt still Zeilen zu vervielfachen."""
    dup_best = df_best.duplicated(subset=keys).sum()
    dup_worst = df_worst.duplicated(subset=keys).sum()
    if dup_best or dup_worst:
        print(f"⚠ {label}: {dup_best} doppelte Schluessel im Best-Case, {dup_worst} im Worst-Case "
              f"(Schluessel: {keys}). Worst-Case-Spalten werden uebersprungen, damit keine "
              "Zeilen vervielfacht werden - bitte Rezeptdaten pruefen.")
        return df_best
    return df_best.merge(df_worst[keys + worst_cols], on=keys, how="left",
                         suffixes=("", "_Worst"), validate="one_to_one")


def merge_worst_case_single_step(df_best: pd.DataFrame, df_worst: pd.DataFrame) -> pd.DataFrame:
    """Fuegt dem Rohdaten-Df die Worst-Case-Spalten hinzu (Smelting-Magic-Reichweite).
    Zeit/Stueck/XP sind vom Cost-Case unabhaengig - nur Cost/h, Gold/h, Gold pro Stück
    und Gold per XP koennen abweichen (nur bei *_bar-Rezepten mit >1 Cost-Zeile;
    fuer alle anderen Zeilen ist Best==Worst)."""
    if df_best.empty or df_worst.empty:
        return df_best
    return _merge_worst_case(
        df_best, df_worst,
        keys=["ItemID", "TaskId"],
        worst_cols=["Cost/h", "Gold/h", "Gold pro Stück", "Gold per XP"],
        label="Rohdaten-Worst-Case",
    )


# ============================================================
# 8. KETTEN-ANALYSE ("Ketten" / "Realistisch_Farmbar"-Tabs)
# ============================================================

def resolve_chain(item_id, market_map, recipe_by_output, fish_to_cooked,
                   qty_needed=1.0, visited=None, depth=0, max_depth=15):
    """Loest rekursiv auf, wie man `qty_needed` Stueck von item_id selbst herstellt statt
    am Markt zu kaufen. Beruecksichtigt das Auto-Cook-Upgrade (Fishing -> Cooking). Die
    Best-/Worst-Case-Unterscheidung steckt bereits in recipe_by_output["costs"] (s.
    normalize_recipe) - diese Funktion selbst ist Case-agnostisch.

    Gibt zurueck: (total_time_ms, total_gold_cost, steps, max_liquidity_ratio, fully_self_sufficient)
    """
    if visited is None:
        visited = set()

    if item_id in visited or depth > max_depth:
        price = market_map.get(item_id, {}).get("sell", 0)
        return 0.0, price * qty_needed, [], 0.0, False

    # Auto-Cook: gekochter Fisch kommt zu AUTO_COOK_CHANCE gratis beim Fischen mit.
    # Bewusst konservativ - der rohe Rest wird nicht mitverkauft (s. README).
    fish_source_id = next((raw for raw, cooked in fish_to_cooked.items() if cooked == item_id), None)
    if fish_source_id is not None and fish_source_id not in visited:
        fish_recipe = recipe_by_output[fish_source_id]
        visited2 = visited | {item_id, fish_source_id}

        cooked_per_action = fish_recipe["item_amount"] * AUTO_COOK_CHANCE
        actions_needed = qty_needed / cooked_per_action
        fishing_time_ms = actions_needed * fish_recipe["base_time_ms"]

        total_time_ms, total_cost, max_ratio = fishing_time_ms, 0.0, 0.0
        fully_self_sufficient = True
        steps = [(fish_recipe["name"] + " (mit Auto-Cook)", fish_recipe["skill"], qty_needed, fishing_time_ms)]

        for c in fish_recipe["costs"]:
            qty = c["Amount"] * actions_needed
            sub_time, sub_cost, sub_steps, sub_ratio, sub_ok = resolve_chain(
                c["Item"], market_map, recipe_by_output, fish_to_cooked, qty, visited2, depth + 1, max_depth
            )
            total_time_ms += sub_time
            total_cost += sub_cost
            max_ratio = max(max_ratio, sub_ratio)
            fully_self_sufficient = fully_self_sufficient and sub_ok
            steps.extend(sub_steps)

        return total_time_ms, total_cost, steps, max_ratio, fully_self_sufficient

    # Normalfall: kein eigenes Recipe -> am Markt kaufen
    if item_id not in recipe_by_output:
        market_entry = market_map.get(item_id)
        price = market_entry.get("sell", 0) if market_entry else 0
        sell_vol = market_entry.get("sellVol", 0) if market_entry else 0
        ratio = (qty_needed / sell_vol) if sell_vol > 0 else 0.0
        if market_entry is None or not valid_market(market_entry):
            ratio = max(ratio, 999.0)  # erzwingt LiquidityWarning, Markt zu unzuverlaessig
        return 0.0, price * qty_needed, [], ratio, False

    recipe = recipe_by_output[item_id]
    visited = visited | {item_id}
    actions_needed = qty_needed / recipe["item_amount"]
    own_time_ms = actions_needed * recipe["base_time_ms"]

    total_time_ms, total_cost, max_ratio = own_time_ms, 0.0, 0.0
    fully_self_sufficient = True
    steps = [(recipe["name"], recipe["skill"], qty_needed, own_time_ms)]

    for c in recipe["costs"]:
        qty = c["Amount"] * actions_needed
        sub_time, sub_cost, sub_steps, sub_ratio, sub_ok = resolve_chain(
            c["Item"], market_map, recipe_by_output, fish_to_cooked, qty, visited, depth + 1, max_depth
        )
        total_time_ms += sub_time
        total_cost += sub_cost
        max_ratio = max(max_ratio, sub_ratio)
        fully_self_sufficient = fully_self_sufficient and sub_ok
        steps.extend(sub_steps)

    return total_time_ms, total_cost, steps, max_ratio, fully_self_sufficient


def build_chain_df(recipe_by_output: dict, market_map: dict, item_info_map: dict, fish_to_cooked: dict) -> pd.DataFrame:
    chain_results = []
    for item_id, recipe in recipe_by_output.items():
        # Handelbarkeit steckt in effective_sell_price (Player-Markt vs. NPC einzeln) -
        # kein eigener Vorab-Filter mehr, sonst faellt auch raus, was man dem NPC
        # sehr wohl verkaufen kann.
        sell_price, sold_to_npc = effective_sell_price(item_id, market_map, item_info_map)
        if sell_price <= 0:
            continue

        m = market_map.get(item_id) or {"buy": 0, "sell": 0, "buyVol": 0, "sellVol": 0, "avg": 0}
        # Zwei verschiedene Dinge, die frueher vermischt waren:
        #   erlaubt  = das Item DARF im Player Shop gehandelt werden (API-Flag)
        #   liquide  = am besten Gebot liegt genug Volumen fuer den Sofortverkauf
        # Ein duennes Top-Gebot macht ein Item nicht unhandelbar - direkt darunter kann
        # tiefe Nachfrage stehen (Titanium platebody: 6 Stueck oben, 53.139 eine Stufe
        # tiefer). Fuer die Preiswahl bleibt die Schwelle massgeblich, fuer die
        # Begruendung nicht.
        spieler_erlaubt = is_player_shop_tradeable(item_info_map.get(item_id, {}))
        spieler_liquide = spieler_erlaubt and valid_market(m) and m["buyVol"] >= MIN_SELL_VOLUME
        if not sold_to_npc and not spieler_liquide:
            continue

        total_time_ms, raw_cost, steps, raw_ratio, fully_self_sufficient = resolve_chain(
            item_id, market_map, recipe_by_output, fish_to_cooked
        )
        if total_time_ms <= 0:
            continue

        actions_per_hour = 3_600_000.0 / total_time_ms
        revenue_per_hour = actions_per_hour * sell_price
        cost_per_hour = actions_per_hour * raw_cost
        profit_per_hour = revenue_per_hour - cost_per_hour

        # Ø-Preis-Variante (siehe Kommentar in build_single_step_df)
        revenue_per_hour_avg = (actions_per_hour * net_player_price(m["avg"])
                                if (not sold_to_npc and m["avg"] > 0) else None)
        profit_per_hour_avg = (revenue_per_hour_avg - cost_per_hour) if revenue_per_hour_avg is not None else None

        max_liquidity_ratio = raw_ratio * actions_per_hour
        if not sold_to_npc and m["buyVol"] > 0:
            max_liquidity_ratio = max(max_liquidity_ratio, actions_per_hour / m["buyVol"])

        skills_involved = sorted(set(s[1] for s in steps))
        # Auto-Cook: die Kette FISCHT nur, der Kochschritt findet nie statt (s.
        # resolve_chain). Das Koch-Rezept als "letzten Schritt" abzurechnen kreidete
        # XP fuer eine Aktion an, die niemand ausfuehrt - bei cooked_tuna 72.000
        # Cooking-XP/h statt der 27.000 Fishing-XP/h, die real anfallen. Skill und
        # Level muessen aus demselben Grund vom Fisch-Rezept kommen, sonst steht in
        # der Zeile "FinalSkill: Cooking" neben "ChainSkills: Fishing".
        final_recipe, final_xp_teiler = recipe, recipe["item_amount"]
        auto_cook_quelle = next(
            (raw for raw, cooked in fish_to_cooked.items() if cooked == item_id), None)
        if auto_cook_quelle is not None and auto_cook_quelle in recipe_by_output \
                and AUTO_COOK_CHANCE > 0:
            final_recipe = recipe_by_output[auto_cook_quelle]
            # Pro Fischzug kommen item_amount * AUTO_COOK_CHANCE gekochte Stueck an
            final_xp_teiler = final_recipe["item_amount"] * AUTO_COOK_CHANCE

        xp_per_unit_final_step = final_recipe["xp"] / final_xp_teiler

        chain_results.append({
            "Item": recipe["name"], "ItemID": item_id, "Level": final_recipe["level"],
            "FinalSkill": final_recipe["skill"],
            "ChainSkills": " -> ".join(skills_involved),
            "ChainDepth": len(steps),
            "FullySelfSufficient": fully_self_sufficient,
            "TimePerItem_sec": total_time_ms / 1000.0,
            "XP_letzter_Schritt_pro_Stück": xp_per_unit_final_step,
            "Gold/h (Eigenherstellung)": profit_per_hour,
            "Gold/h (Eigenherstellung, Ø-Preis)": profit_per_hour_avg,
            "Gold pro Stück": profit_per_hour / actions_per_hour,
            "Stück/h": actions_per_hour,
            "Revenue/h": revenue_per_hour,
            "Revenue/h (Ø-Preis)": revenue_per_hour_avg,
            "RawMaterialCost/h": cost_per_hour,
            "SoldToNPC": sold_to_npc,
            "Verkaufspreis": sell_price,
            "NPCPreis": npc_sell_price(item_id, item_info_map),
            "SpielerpreisBid": m["buy"] if (spieler_erlaubt and m["buy"] > 0) else 0.0,
            "SpielerVerkaufMoeglich": spieler_erlaubt,
            "SpielerMarktDuenn": bool(spieler_erlaubt and m["buy"] > 0 and not spieler_liquide),
            "BidVolumen": m["buyVol"],
            "MarketAsk": m["sell"],
            "LiquidityWarning": max_liquidity_ratio > LIQUIDITY_WARNING_RATIO,
            "LiquidityRatio": round(max_liquidity_ratio, 1),
            "PriceAnomaly": price_anomaly(m) if not sold_to_npc else False,
            "SpreadWarning": wide_spread(m) if not sold_to_npc else False,
            "XP/h (letzter Schritt)": xp_per_unit_final_step * actions_per_hour,
        })
    return pd.DataFrame(chain_results)


def merge_worst_case_chain(df_chain_best: pd.DataFrame, df_chain_worst: pd.DataFrame) -> pd.DataFrame:
    """Analog zu merge_worst_case_single_step, aber fuer die Ketten-Analyse: hier wirkt
    sich die Smelting-Magic-Reichweite auch auf alle nachgelagerten Items aus (z.B.
    haengt titanium_platebody an titanium_bar -> auch dessen Kette bekommt Worst-Spalten,
    obwohl das Platebody-Rezept selbst kein *_bar-Rezept ist)."""
    if df_chain_best.empty or df_chain_worst.empty:
        return df_chain_best
    merged = _merge_worst_case(
        df_chain_best, df_chain_worst,
        keys=["ItemID"],
        worst_cols=[
            "TimePerItem_sec", "Stück/h",
            "Gold/h (Eigenherstellung)", "Gold/h (Eigenherstellung, Ø-Preis)",
            "Gold pro Stück", "XP/h (letzter Schritt)",
        ],
        label="Ketten-Worst-Case",
    )
    if "Gold/h (Eigenherstellung)_Worst" not in merged.columns:
        return merged  # Merge wurde wegen doppelter Schluessel uebersprungen
    merged["CostCaseAmbiguous"] = (
        merged["Gold/h (Eigenherstellung)"] - merged["Gold/h (Eigenherstellung)_Worst"]
    ).abs() > 1e-6
    return merged


def fetch_orderbook_depth(item_id: int) -> dict | None:
    try:
        r = requests.get(COMPREHENSIVE_URL_TEMPLATE.format(item_id=item_id), timeout=15)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def enrich_with_longterm_averages(df: pd.DataFrame) -> pd.DataFrame:
    """Ergaenzt Rohdaten um Avg1D/Avg7D/Avg30D/Volume1D aus dem comprehensive-Endpoint -
    1 Request pro EINDEUTIGEM ItemID (dedupliziert, da dasselbe Item ueber mehrere
    Rezepte/Skills auftauchen kann). Nur aktiv bei SHOW_LONGTERM_AVERAGES=True, da das
    bei vielen Items in Rohdaten mehrere Minuten dauern kann. Nur fuer Rohdaten gedacht -
    Ketten/Realistisch_Farmbar/Nach_Skill_Level bleiben bewusst schlank (s. Absprache)."""
    unique_ids = [int(x) for x in df["ItemID"].unique().tolist()]
    print(f"Hole 1-/7-/30-Tage-Durchschnitt fuer {len(unique_ids)} eindeutige Items "
          "(comprehensive-Endpoint, 1 Request/Item, das dauert einen Moment)...")

    rows = []
    fields_missing_warned = False
    for i, item_id in enumerate(unique_ids, 1):
        depth = fetch_orderbook_depth(item_id)
        entry = {"ItemID": item_id}
        if depth is not None:
            for col, field in COMPREHENSIVE_AVG_FIELDS.items():
                entry[col] = depth.get(field)
            entry["Volume1D"] = depth.get(COMPREHENSIVE_VOLUME_FIELD)
            if not fields_missing_warned and all(entry[c] is None for c in COMPREHENSIVE_AVG_FIELDS):
                print(f"⚠ Erwartete Avg-Felder {list(COMPREHENSIVE_AVG_FIELDS.values())} nicht in der "
                      f"Antwort gefunden. Tatsaechliche Keys: {sorted(depth.keys())}\n"
                      "  -> Feldnamen in COMPREHENSIVE_AVG_FIELDS anpassen.")
                fields_missing_warned = True
        else:
            for col in COMPREHENSIVE_AVG_FIELDS:
                entry[col] = None
            entry["Volume1D"] = None
        rows.append(entry)

        if i % 25 == 0 or i == len(unique_ids):
            print(f"  ... {i}/{len(unique_ids)}")
        time.sleep(LONGTERM_AVERAGES_REQUEST_DELAY_S)

    avg_df = pd.DataFrame(rows)
    return df.merge(avg_df, on="ItemID", how="left")


def price_points_from_depth(depth: dict) -> list:
    """5 hoechste Buy-Preise (aufsteigend, niedrigster zuerst) + 5 niedrigste Sell-Preise
    (aufsteigend). Fehlende Tiefenstufen (dünner Markt) werden mit None aufgefuellt."""
    buys = sorted(depth.get("highestBuyPricesWithVolume", []), key=lambda x: x["key"], reverse=True)[:5]
    buys = sorted(buys, key=lambda x: x["key"])
    while len(buys) < 5:
        buys.insert(0, None)
    sells = sorted(depth.get("lowestSellPricesWithVolume", []), key=lambda x: x["key"])[:5]
    while len(sells) < 5:
        sells.append(None)
    return [(b["key"] if b else None) for b in buys] + [(s["key"] if s else None) for s in sells]


PRICE_SENSITIVITY_LABELS_SHORT = ["Buy1", "Buy2", "Buy3", "Buy4", "Buy5", "Sell1", "Sell2", "Sell3", "Sell4", "Sell5"]


def build_price_sensitivity_data(df_chain: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Live-Orderbook-Tiefe der Top-N FullySelfSufficient-Items, 1 Zeile pro Item mit
    Preis + Gold/s je Preispunkt. Speist Chart UND Excel-Sheet aus einem Abruf.

    Die *_Gold_h-Spalten sind NETTO: Materialkosten abgezogen und die 1% Marktsteuer
    schon eingerechnet, also direkt mit "Gold/h (Eigenherstellung)" vergleichbar.
    NPC_Gold_h ist die steuerfreie Vergleichslinie desselben Items. Zweiter
    Rueckgabewert: Items, die ohnehin ueber den NPC verkauft werden."""
    top = df_chain[df_chain["FullySelfSufficient"]].sort_values(
        "Gold/h (Eigenherstellung)", ascending=False
    ).head(PRICE_SENSITIVITY_TOP_N)

    rows = []
    npc_items = []
    for _, row in top.iterrows():
        depth = fetch_orderbook_depth(int(row["ItemID"]))
        if depth is None:
            continue
        prices = price_points_from_depth(depth)
        stueck_h = row["Stück/h"]
        cost_per_item = (row["RawMaterialCost/h"] / stueck_h) if stueck_h > 0 else 0.0
        npc_preis = row.get("NPCPreis", 0) or 0.0
        # Vergleichslinie: was dasselbe Zeitbudget beim NPC einbraechte (steuerfrei)
        npc_gold_h = stueck_h * (npc_preis - cost_per_item) if npc_preis else None

        data = {
            "Item": row["Item"], "ItemID": int(row["ItemID"]), "FinalSkill": row["FinalSkill"],
            "SoldToNPC": bool(row["SoldToNPC"]),
            "Kosten_pro_Stück": cost_per_item,
            "NPC-Preis": npc_preis or None,
            "NPC_Gold_h": round(npc_gold_h) if npc_gold_h is not None else None,
        }
        for label, p in zip(PRICE_SENSITIVITY_LABELS_SHORT, prices):
            data[f"{label}_Preis"] = p
            data[f"{label}_Gold_h"] = ((stueck_h * (net_player_price(p) - cost_per_item))
                                       if p is not None else None)
        rows.append(data)

        if bool(row["SoldToNPC"]):
            npc_items.append(str(row["Item"]))

    return pd.DataFrame(rows), npc_items


def build_price_sensitivity_chart(df_sens: pd.DataFrame, npc_items: list[str],
                                   path: str = PRICE_SENSITIVITY_CHART_PATH):
    """Liniendiagramm Gold/h (netto) ueber die 10 Orderbook-Preispunkte, eine Linie je
    Item. Punkte auf oder unter dem NPC-Niveau desselben Items werden rot markiert -
    dort lohnt der Player Shop nicht mehr. Fehlt matplotlib, wird nur der Chart
    uebersprungen; das Excel-Sheet mit denselben Zahlen entsteht trotzdem."""
    try:
        import matplotlib.pyplot as plt  # lazy: nur noetig, wenn Flag aktiv
    except ImportError:
        print("ℹ matplotlib nicht installiert - Preis-Sensitivitaets-Chart wird uebersprungen "
              "(die Zahlen stehen trotzdem im Excel-Sheet 'Preis_Sensitivitaet'). "
              "Nachinstallieren mit: pip install matplotlib")
        return

    if df_sens.empty:
        print("Preis-Sensitivitaets-Chart: keine FullySelfSufficient-Items gefunden.")
        return

    labels = ["Buy1\n(niedrigster)", "Buy2", "Buy3", "Buy4", "Buy5\n(höchster Bid)",
              "Sell1\n(billigster)", "Sell2", "Sell3", "Sell4", "Sell5\n(teuerster)"]

    fig, ax = plt.subplots(figsize=(12, 7))
    rot_x, rot_y = [], []
    for _, row in df_sens.iterrows():
        ys_raw = [row[f"{label}_Gold_h"] for label in PRICE_SENSITIVITY_LABELS_SHORT]
        xs = [i for i, v in enumerate(ys_raw) if pd.notna(v)]
        ys = [v for v in ys_raw if pd.notna(v)]
        ax.plot(xs, ys, marker="o", markersize=5, label=str(row["Item"]))

        # Punkte einsammeln, an denen der Player Shop den NPC nicht mehr schlaegt
        npc = row.get("NPC_Gold_h")
        if pd.notna(npc):
            for x, y in zip(xs, ys):
                if y <= npc:
                    rot_x.append(x)
                    rot_y.append(y)

    if rot_x:
        ax.scatter(rot_x, rot_y, color="red", s=70, zorder=5, edgecolors="darkred",
                   label="NPC-Verkauf gleich gut oder besser")

    ax.set_xticks(range(10))
    ax.set_xticklabels(labels)
    ax.axvline(4.5, color="gray", linestyle="--", linewidth=1)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_ylabel("Gold/h (netto: Materialkosten und 1% Marktsteuer abgezogen)")
    ax.set_title(f"Top-{PRICE_SENSITIVITY_TOP_N} FullySelfSufficient: Gold/h über Orderbook-Tiefe\n"
                 "rote Punkte = NPC-Vendor bringt hier mindestens genauso viel")
    ax.legend(loc="best", fontsize=8, ncol=2)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)

    print(f"Preis-Sensitivitaets-Chart gespeichert: {path}")
    if npc_items:
        print(f"ℹ Aktuell ueber NPC-Vendor verkauft (fixer Preis, nicht auf der Kurve): {', '.join(npc_items)}")


# ---------------------------------------------------------------
# Empfehlung: was farmen, was bringt es, an wen verkaufen
# ---------------------------------------------------------------

def chain_reliability(chain_skills: str) -> tuple[float, str]:
    """Wie planbar ist der Nachschub fuer diese Kette? Es zaehlt der unzuverlaessigste
    Schritt (min, nicht Produkt) - zwei zufallsabhaengige Skills machen eine Kette nicht
    doppelt so unplanbar, sie bleibt schlicht so unplanbar wie ihr schwaechstes Glied."""
    faktor, gruende = 1.0, []
    for teil in str(chain_skills or "").split("->"):
        skill = teil.strip()
        eintrag = SKILL_RELIABILITY.get(skill)
        if eintrag and eintrag[0] < 1.0:
            faktor = min(faktor, eintrag[0])
            gruende.append(f"{skill}: {eintrag[1]}")
    return faktor, "; ".join(gruende)


RECOMMENDATION_COLUMNS = [
    "Rang", "Item", "Skills", "Gold/h gewichtet", "Gold/h", "Verlässlichkeit",
    "Gold/h (ungünstigster Fall)",
    "Sek pro Stück", "Stück/h", "Gold pro Stück",
    "Verkauf an", "Erlös pro Stück", "Spieler-Gebot (brutto)", "NPC-Preis", "Vorteil",
    "Alles selbst farmbar", "Warnung", "Hinweis",
]


def build_recommendation_df(df_chain: pd.DataFrame) -> pd.DataFrame:
    """Eine Zeile pro Endprodukt, sortiert nach Gold/h - reduziert auf die Frage
    "was lohnt sich pro Zeit und an wen verkaufe ich es?". Alles andere steht in den
    ausfuehrlichen Sheets."""
    if df_chain.empty:
        return pd.DataFrame(columns=RECOMMENDATION_COLUMNS)

    # Nach gewichtetem Gold/h sortieren: unplanbarer Nachschub soll die Empfehlung nicht
    # anfuehren, auch wenn die reine Rechnung dafuer spricht (s. SKILL_RELIABILITY).
    src = df_chain.copy()
    src["_faktor"] = src["ChainSkills"].map(lambda c: chain_reliability(c)[0])
    src["_gewichtet"] = src["Gold/h (Eigenherstellung)"] * src["_faktor"]
    src = src.sort_values("_gewichtet", ascending=False)

    rows = []
    for rang, (_, r) in enumerate(src.iterrows(), 1):
        faktor, faktor_grund = chain_reliability(r["ChainSkills"])
        npc, spieler = r.get("NPCPreis", 0) or 0, r.get("SpielerpreisBid", 0) or 0
        an_npc = bool(r["SoldToNPC"])
        # Vergleich netto gegen netto: das Spielergebot verliert noch die Marktsteuer,
        # der NPC-Preis nicht.
        spieler_netto = net_player_price(spieler) if spieler else 0.0
        gewaehlt, alternative = (npc, spieler_netto) if an_npc else (spieler_netto, npc)
        vorteil = (gewaehlt / alternative - 1) if alternative > 0 else None

        warn = []
        if r.get("SpielerMarktDuenn"):
            warn.append(f"Top-Gebot dünn ({int(_num(r.get('BidVolumen'))):,} Stk)")
        if an_npc and spieler_netto > npc:
            warn.append("Spielergebot wäre höher, Top-Gebot aber zu dünn – s. Begründung")
        if r.get("LiquidityWarning"):
            warn.append("Absatz knapp")
        if r.get("SpreadWarning"):
            warn.append("breiter Spread")
        if r.get("PriceAnomaly"):
            warn.append("Preis untypisch")
        if not r.get("FullySelfSufficient"):
            warn.append("Zutat muss gekauft werden")

        worst = r.get("Gold/h (Eigenherstellung)_Worst")
        rows.append({
            "Rang": rang,
            "Item": r["Item"],
            "Skills": r["ChainSkills"],
            "Gold/h gewichtet": round(r["Gold/h (Eigenherstellung)"] * faktor),
            "Gold/h": round(r["Gold/h (Eigenherstellung)"]),
            "Verlässlichkeit": round(faktor, 2),
            "Gold/h (ungünstigster Fall)": round(worst) if pd.notna(worst) else None,
            "Sek pro Stück": round(r["TimePerItem_sec"], 2),
            "Stück/h": round(r["Stück/h"], 1),
            "Gold pro Stück": round(r["Gold pro Stück"], 1),
            "Verkauf an": "NPC-Vendor" if an_npc else "Spieler",
            "Erlös pro Stück": round(r.get("Verkaufspreis", 0), 2),
            "Spieler-Gebot (brutto)": round(spieler, 2) if spieler else None,
            "NPC-Preis": round(npc, 2) if npc else None,
            "Vorteil": (f"+{vorteil:.0%}" if vorteil is not None
                        else ("kein Spielerverkauf erlaubt" if an_npc
                              else "kein NPC-Verkauf erlaubt")),
            "Alles selbst farmbar": bool(r.get("FullySelfSufficient")),
            "Warnung": ", ".join(warn),
            "Hinweis": faktor_grund,
        })
    return pd.DataFrame(rows, columns=RECOMMENDATION_COLUMNS)


def print_recommendation(df_rec: pd.DataFrame, top_n: int = 15):
    """Antwort auf die eigentliche Frage direkt in der Konsole - ohne Excel zu oeffnen."""
    if df_rec.empty:
        print("Keine farmbaren Items gefunden.")
        return
    sauber = df_rec[df_rec["Alles selbst farmbar"] & (df_rec["Warnung"] == "")]
    liste = sauber if not sauber.empty else df_rec

    print(f"\n=== TOP {min(top_n, len(liste))}: BESTES GOLD PRO ZEIT ===")
    if not sauber.empty:
        print("(komplett selbst farmbar, ohne Warnungen)")
    print(f"{'#':>3}  {'Item':<26}{'Gold/h':>22}  {'Sek/Stk':>8}  {'an':<11}{'Erloes':>10}  Skills")
    for _, r in liste.head(top_n).iterrows():
        # Abgewertete Ketten mit beiden Zahlen zeigen, sonst wirkt die Reihenfolge falsch
        gold = (f"{r['Gold/h gewichtet']:,} ({r['Gold/h']:,})" if r["Verlässlichkeit"] < 1
                else f"{r['Gold/h']:,}")
        print(f"{r['Rang']:>3}  {str(r['Item']):<26}{gold:>22}  {r['Sek pro Stück']:>8.2f}  "
              f"{r['Verkauf an']:<11}{r['Erlös pro Stück']:>10,.0f}  {r['Skills']}")

    abgewertet = liste.head(top_n)[liste.head(top_n)["Verlässlichkeit"] < 1]
    if not abgewertet.empty:
        print("  (Klammerwert = ungewichtetes Gold/h; abgewertet wegen: "
              + "; ".join(sorted(set(abgewertet["Hinweis"]))) + ")")

    npc = df_rec[df_rec["Verkauf an"] == "NPC-Vendor"]
    print(f"\nVerkaufsweg: {len(df_rec) - len(npc)} Items an Spieler, {len(npc)} an den NPC-Vendor.")
    if not npc.empty:
        best = npc.iloc[0]
        print(f"  Bester NPC-Kandidat: {best['Item']} mit {best['Gold/h']:,} Gold/h "
              f"({best['Erlös pro Stück']:,.0f}g/Stueck).")


# ---------------------------------------------------------------
# Begruendung: warum lohnt sich ein Item - und warum nicht
# ---------------------------------------------------------------

def walk_orderbook(levels: list, qty: float) -> tuple[float, float, float]:
    """Verkauft `qty` Stueck ins Buch, beste Gebote zuerst.

    levels: [(preis, menge)], beliebige Reihenfolge. Gibt zurueck:
    (Erloes, tatsaechlich verkaufte Menge, Preis der zuletzt getroffenen Stufe)."""
    rest, erloes, letzter = qty, 0.0, 0.0
    for preis, menge in sorted(levels, key=lambda x: x[0], reverse=True):
        if rest <= 0:
            break
        nimm = min(rest, menge)
        erloes += nimm * preis
        letzter = preis
        rest -= nimm
    return erloes, qty - rest, letzter


def buy_levels_from_depth(depth: dict) -> list:
    """Kaufgebote als [(Preis, Menge)] - das ist die Seite, an die DU verkaufst."""
    return [(e["key"], float(e["value"])) for e in depth.get("highestBuyPricesWithVolume", [])
            if e.get("key") and e.get("value")]


def _format_levels(levels: list, max_n: int = 5) -> str:
    top = sorted(levels, key=lambda x: x[0], reverse=True)[:max_n]
    return "  |  ".join(f"{p:,.0f}g x {m:,.0f}" for p, m in top)


def _verdict(an_npc: bool, npc: float, top_preis: float, stunden_deckung: float,
             schnitt: float, verlust: float, warnung: str, abweichung: float = 0.0) -> str:
    """Ein Satz Klartext: warum ist das Item gut oder eben nicht."""
    if an_npc:
        if top_preis <= 0:
            return "Nur NPC: kein brauchbares Kaufgebot im Player Shop."
        return (f"NPC zahlt {npc:,.0f}g und damit mehr als das beste Spielergebot "
                f"({top_preis:,.0f}g) - unbegrenzt und sofort.")

    teile = []
    if stunden_deckung >= 8:
        teile.append(f"Top-Gebot schluckt {stunden_deckung:,.1f} h Produktion - sofort verkaufbar")
    elif stunden_deckung >= 1:
        teile.append(f"Top-Gebot reicht nur fuer {stunden_deckung:,.1f} h, danach faellt der Preis")
    elif stunden_deckung > 0:
        teile.append(f"Top-Gebot ist nach {stunden_deckung * 60:,.0f} min leer")
    else:
        teile.append("kein Volumen am Top-Gebot")

    if verlust > 0.02:
        teile.append(f"1 h Produktion druecken den Schnitt auf {schnitt:,.0f}g ({-verlust:.0%})")
    elif stunden_deckung >= 1:
        teile.append("eine Stunde Produktion bewegt den Preis kaum")

    if npc > schnitt > 0:
        teile.append(f"NPC waere mit {npc:,.0f}g besser")
    if abweichung > 0.1:
        teile.append(f"Achtung: Orderbuch weicht {abweichung:.0%} vom Listenpreis ab "
                     "(zwei Momentaufnahmen)")
    if warnung:
        teile.append(warnung)
    return "; ".join(teile) + "."


REASON_COLUMNS = [
    "Rang", "Item", "Gold/h", "Verkauf an", "Stück/h",
    "Bestes Gebot (brutto)", "Menge am besten Gebot", "Deckt Stunden",
    "Schnitt bei 1h Produktion (netto)", "Preisverlust", "Gold/h realistisch",
    "NPC-Preis", "NPC besser", "Kaufgebote (Stufen)", "Bewertung",
]


def _num(value) -> float:
    """Leere Zellen und NaN als 0 - `NaN or 0` liefert in Python NaN, nicht 0."""
    return 0.0 if value is None or pd.isna(value) else float(value)


def build_reason_df(df_rec: pd.DataFrame, df_chain: pd.DataFrame) -> pd.DataFrame:
    """Warum lohnt sich ein Item - mit den echten Kaufgebot-Stufen aus dem Player Shop.

    Der Gold/h-Wert der uebrigen Sheets unterstellt, dass du beliebig viel zum besten
    Gebot los wirst. Das stimmt nur, solange dort genug Volumen liegt. Hier wird eine
    Stunde Produktion tatsaechlich durchs Orderbuch gerechnet.

    Kostet REASON_TOP_N Live-Requests (1 pro Item)."""
    if df_rec.empty:
        return pd.DataFrame(columns=REASON_COLUMNS)

    kosten_je_h = df_chain.set_index("ItemID")["RawMaterialCost/h"].to_dict() if not df_chain.empty else {}
    id_von_item = df_chain.set_index("Item")["ItemID"].to_dict() if not df_chain.empty else {}

    print(f"\nHole Kaufgebot-Stufen fuer die Top-{REASON_TOP_N} Items "
          f"({REASON_TOP_N} Requests)...")

    rows = []
    for _, r in df_rec.head(REASON_TOP_N).iterrows():
        item_id = id_von_item.get(r["Item"])
        an_npc = r["Verkauf an"] == "NPC-Vendor"
        npc = _num(r["NPC-Preis"])
        stueck_h = _num(r["Stück/h"])
        material_h = _num(kosten_je_h.get(item_id))
        # Bezugsgroesse ist der Preis, auf dem das ausgewiesene Gold/h beruht - sonst
        # widersprechen sich "Preisverlust" und "Gold/h realistisch".
        referenz = _num(r["Erlös pro Stück"])

        depth = fetch_orderbook_depth(int(item_id)) if item_id is not None else None
        levels = buy_levels_from_depth(depth) if depth else []

        if levels:
            top_preis, top_menge = max(levels, key=lambda x: x[0])
            deckung = top_menge / stueck_h if stueck_h > 0 else 0.0
            brutto, verkauft, _ = walk_orderbook(levels, stueck_h)
            erloes = net_player_price(brutto)          # Marktsteuer auf den Spieler-Anteil
            # Was nicht mehr ins Buch passt, geht zum NPC (steuerfrei) statt verloren
            rest = stueck_h - verkauft
            erloes += rest * npc
            schnitt = erloes / stueck_h if stueck_h > 0 else 0.0
            verlust = (1 - schnitt / referenz) if referenz > 0 else 0.0
        else:
            top_preis, top_menge, deckung = 0.0, 0.0, 0.0
            schnitt = npc if an_npc else 0.0
            erloes = schnitt * stueck_h
            verlust = 0.0

        if an_npc:   # NPC hat unbegrenztes Volumen, das Buch ist dann egal
            schnitt, erloes, verlust = npc, npc * stueck_h, 0.0

        # Orderbuch und Bulk-Endpoint sind zwei Momentaufnahmen - weichen sie stark ab,
        # ist das eher ein Zeitversatz als ein echter Preissturz.
        abweichung = ((abs(net_player_price(top_preis) - referenz) / referenz)
                      if (referenz > 0 and top_preis > 0) else 0.0)

        rows.append({
            "Rang": r["Rang"],
            "Item": r["Item"],
            "Gold/h": r["Gold/h"],
            "Verkauf an": r["Verkauf an"],
            "Stück/h": round(stueck_h, 1),
            "Bestes Gebot (brutto)": round(top_preis, 2) if top_preis else None,
            "Menge am besten Gebot": round(top_menge) if top_menge else None,
            "Deckt Stunden": round(deckung, 2) if deckung else None,
            "Schnitt bei 1h Produktion (netto)": round(schnitt, 2),
            "Preisverlust": f"-{verlust:.1%}" if verlust > 0.0005 else "0%",
            "Gold/h realistisch": round(erloes - material_h),
            "NPC-Preis": round(npc, 2) if npc else None,
            "NPC besser": bool(npc > schnitt) if not an_npc else True,
            "Kaufgebote (Stufen)": _format_levels(levels) if levels else "keine",
            "Bewertung": _verdict(an_npc, npc, top_preis, deckung, schnitt, verlust,
                                  "" if pd.isna(r.get("Warnung")) else str(r.get("Warnung") or ""),
                                  abweichung),
        })
    return pd.DataFrame(rows, columns=REASON_COLUMNS)


def print_reason_highlights(df_reason: pd.DataFrame):
    """Die Faelle, in denen der ausgewiesene Gold/h-Wert nicht haltbar ist."""
    if df_reason.empty:
        return
    schoen = df_reason[df_reason["Gold/h realistisch"] < df_reason["Gold/h"] * 0.9]
    if not schoen.empty:
        print(f"\n⚠ {len(schoen)} Items halten ihren Gold/h-Wert nicht, wenn man eine ganze "
              "Stunde Produktion ins Buch verkauft:")
        for _, r in schoen.head(8).iterrows():
            print(f"    {str(r['Item']):<26}{r['Gold/h']:>11,} -> {r['Gold/h realistisch']:>11,}  "
                  f"({r['Preisverlust']} Preisverlust)")


# ---------------------------------------------------------------
# Excel-Export
# ---------------------------------------------------------------

SORT_COLUMN_PER_SHEET = {
    "Empfehlung": "Gold/h gewichtet",
    "Begruendung": "Gold/h realistisch",
    "Rohdaten": "Gold/h",
    "Nach_Skill_Level": "Level",
    "Ketten": "Gold/h (Eigenherstellung)",
    "Realistisch_Farmbar": "Gold/h (Eigenherstellung)",
}

HIGHLIGHT_FILL = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
HIGHLIGHT_HEADER_FILL = PatternFill(start_color="FFD966", end_color="FFD966", fill_type="solid")
HIGHLIGHT_HEADER_FONT = Font(bold=True)

# Auffaellige Rohdaten-Zeilen werden markiert: Zeile orange, Grund-Feld rot.
ROW_FLAG_FILL = PatternFill(start_color="F6B26B", end_color="F6B26B", fill_type="solid")     # Zeile: kraeftiges Orange
REASON_FIELD_FILL = PatternFill(start_color="E06666", end_color="E06666", fill_type="solid")  # verantwortliches Feld: kraeftiges Rot

SKILL_LEVEL_COLUMNS = ["Skill", "Level", "Item", "Gold/h", "Gold/h_Worst", "Gold pro Stück", "Stück/h",
                        "XP/h", "SoldToNPC", "NPCPreis", "ItemID"]


def export_excel(df: pd.DataFrame, df_chain: pd.DataFrame, path: str,
                 df_sensitivity: pd.DataFrame | None = None,
                 df_recommendation: pd.DataFrame | None = None,
                 df_reason: pd.DataFrame | None = None):
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        # Empfehlung zuerst: beantwortet die Frage "was farmen, an wen verkaufen?"
        if df_recommendation is not None and not df_recommendation.empty:
            df_recommendation.to_excel(writer, sheet_name="Empfehlung", index=False)
        # Begruendung: warum steht das Item da, wo es steht
        if df_reason is not None and not df_reason.empty:
            df_reason.to_excel(writer, sheet_name="Begruendung", index=False)
        # Reihenfolge bewusst: Ketten -> Realistisch_Farmbar -> Nach_Skill_Level -> Rohdaten
        # -> Preis_Sensitivitaet (die tatsaechlich farmbaren/relevanten Sichten zuerst,
        # Rohdaten + Chart-Daten als Referenz zuletzt).
        if not df_chain.empty:
            df_chain.sort_values("Gold/h (Eigenherstellung)", ascending=False).to_excel(
                writer, sheet_name="Ketten", index=False
            )
            realistic = df_chain[df_chain["FullySelfSufficient"]].sort_values(
                "Gold/h (Eigenherstellung)", ascending=False
            )
            if not realistic.empty:
                realistic.to_excel(writer, sheet_name="Realistisch_Farmbar", index=False)
        # Nach_Skill_Level bildet wie bisher nur tatsaechlich verkaufbare Items ab (InKetten=True).
        # Rohdaten (unten) bleibt die einzige vollstaendige, ungefilterte Sicht.
        skill_level_cols = [c for c in SKILL_LEVEL_COLUMNS if c in df.columns]
        df[df["InKetten"]].sort_values(["Skill", "Level"], na_position="last")[skill_level_cols].to_excel(
            writer, sheet_name="Nach_Skill_Level", index=False
        )
        df.sort_values("Gold/h", ascending=False).to_excel(writer, sheet_name="Rohdaten", index=False)
        if df_sensitivity is not None and not df_sensitivity.empty:
            df_sensitivity.to_excel(writer, sheet_name="Preis_Sensitivitaet", index=False)

        for sheet_name, sort_col in SORT_COLUMN_PER_SHEET.items():
            if sheet_name not in writer.sheets:
                continue
            ws = writer.sheets[sheet_name]
            header_cells = next(ws.iter_rows(min_row=1, max_row=1))
            col_idx = next((c.column for c in header_cells if c.value == sort_col), None)
            if col_idx is None:
                continue
            col_letter = get_column_letter(col_idx)
            ws[f"{col_letter}1"].fill = HIGHLIGHT_HEADER_FILL
            ws[f"{col_letter}1"].font = HIGHLIGHT_HEADER_FONT
            for row in range(2, ws.max_row + 1):
                ws[f"{col_letter}{row}"].fill = HIGHLIGHT_FILL

        # Rohdaten: jede Zeile mit Status != OK komplett orange, das verantwortliche Feld
        # ("AusschlussGrund") zusaetzlich rot. Gold/h-Zelle bleibt vom gelben Sortier-
        # Highlight unberuehrt (s.o.).
        if "Rohdaten" in writer.sheets:
            ws = writer.sheets["Rohdaten"]
            header_cells = next(ws.iter_rows(min_row=1, max_row=1))
            headers = {c.value: c.column for c in header_cells}
            status_col = headers.get("Status")
            gold_col = headers.get("Gold/h")
            grund_col = headers.get("AusschlussGrund")
            if status_col is not None:
                for row in range(2, ws.max_row + 1):
                    status = ws.cell(row=row, column=status_col).value
                    if status == "OK" or status is None:
                        continue
                    for col in range(1, ws.max_column + 1):
                        if col == gold_col:
                            continue
                        ws.cell(row=row, column=col).fill = ROW_FLAG_FILL
                    if grund_col is not None:
                        ws.cell(row=row, column=grund_col).fill = REASON_FIELD_FILL


# ---------------------------------------------------------------
# Lauf-Sanity-Check
# ---------------------------------------------------------------

def compute_run_stats(tasks: dict, all_recipes: list, item_info_map: dict,
                       market_map: dict, df: pd.DataFrame, df_chain: pd.DataFrame) -> dict:
    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "tasks_count": len(tasks),
        "recipes_count": len(all_recipes),
        "item_info_count": len(item_info_map),
        "market_map_count": len(market_map),
        "rohdaten_count": len(df),
        "in_ketten_count": int(df["InKetten"].sum()) if "InKetten" in df.columns else None,
        "realistic_count": (
            int(df_chain["FullySelfSufficient"].sum())
            if not df_chain.empty and "FullySelfSufficient" in df_chain.columns else 0
        ),
    }


def load_run_stats_history(path: str = RUN_STATS_PATH) -> list:
    """Liste vergangener Laeufe, aeltester zuerst. Alte Dateien enthalten nur ein einzelnes
    Dict (nur der letzte Lauf) - das wird transparent als Ein-Element-Historie gelesen."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return [entry for entry in data if isinstance(entry, dict)]
    return []


def load_last_run_stats(path: str = RUN_STATS_PATH) -> dict | None:
    history = load_run_stats_history(path)
    return history[-1] if history else None


def save_run_stats(stats: dict, path: str = RUN_STATS_PATH):
    history = load_run_stats_history(path)
    history.append(stats)
    history = history[-RUN_STATS_HISTORY_LIMIT:]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def sanity_check_run_stats(current: dict, previous: dict | None) -> list[str]:
    """Vergleicht aktuelle Kennzahlen mit dem letzten Lauf. Gibt eine Liste von
    Warntexten zurueck (leer = alles unauffaellig)."""
    if previous is None:
        return []

    warnings = []
    for key in STRUCTURAL_STATS:
        old, new = previous.get(key), current.get(key)
        if old is None or new is None:
            continue
        if new < old:
            warnings.append(
                f"'{key}': {old} -> {new} (GESUNKEN). Struktur-Werte aus der Game-Data sollten "
                "bei echten Updates nur wachsen - moeglicher Hinweis auf ein kaputtes API-Feld/Parsing."
            )

    for key in MARKET_STATS:
        old, new = previous.get(key), current.get(key)
        if old is None or new is None or old == 0:
            continue
        drop_ratio = (old - new) / old
        if drop_ratio > MARKET_DROP_WARNING_RATIO:
            warnings.append(
                f"'{key}': {old} -> {new} ({drop_ratio:.0%} Einbruch). Kann eine echte Marktbewegung "
                "sein, oder eine kaputte/unvollstaendige API-Antwort - pruefen lohnt sich."
            )

    return warnings


def print_run_sanity_check(current: dict, previous: dict | None):
    if previous is None:
        print("Lauf-Sanity-Check: erster Lauf, noch keine Vergleichsbasis (wird jetzt gespeichert).")
        return

    warnings = sanity_check_run_stats(current, previous)
    if not warnings:
        print(f"Lauf-Sanity-Check: unauffaellig (letzter Lauf: {previous.get('timestamp', '?')}).")
        return

    print(f"\n⚠⚠ LAUF-SANITY-CHECK: {len(warnings)} Auffaelligkeit(en) ggue. letztem Lauf "
          f"({previous.get('timestamp', '?')}):")
    for w in warnings:
        print(f"  - {w}")
    print("  Falls das nicht durch ein bekanntes Game-Update erklaerbar ist: API-Antwort direkt "
          "im Browser gegenpruefen statt den Zahlen blind zu vertrauen.\n")


# ---------------------------------------------------------------
# Main
# ---------------------------------------------------------------

def print_summary(df: pd.DataFrame, df_chain: pd.DataFrame):
    excluded_count = int((~df["InKetten"]).sum())
    print(f"Rohdaten: {len(df)} Einzelschritt-Recipes ({excluded_count} davon nicht in Ketten - Grund s. AusschlussGrund).")
    if not df_chain.empty:
        n_self_sufficient = int(df_chain["FullySelfSufficient"].sum())
        print(f"Ketten: {len(df_chain)} Endprodukte, davon {n_self_sufficient} 100% selbst herstellbar.")

    dupe_count = int(df.duplicated("Item", keep=False).sum())
    if dupe_count:
        print(f"ℹ {dupe_count} Zeilen mit doppeltem Item-Namen (unterschiedliche Skills/Recipes) - Details im Rohdaten-Tab.")

    if "Handelbar" in df.columns:
        no_trade = int((~df["Handelbar"]).sum())
        no_npc = int((~df["NPCVerkaufMoeglich"]).sum())
        if no_trade or no_npc:
            print(f"ℹ Laut API-Flags: {no_trade} Rezept-Ausgaben nicht am Player-Markt handelbar "
                  f"(CanNotBeTraded), {no_npc} nicht an den NPC verkaufbar (CanNotBeSoldToGameShop).")

    # Grenzfaelle an MIN_SELL_VOLUME sichtbar machen: das Gebot existiert und ist besser
    # als der NPC-Preis, wird aber verworfen, weil AM BESTEN GEBOT zu wenig Stueck liegen
    # (die Tiefe darunter kennt der Bulk-Endpoint nicht). Das kippt Items sprunghaft
    # zwischen zwei Laeufen - siehe Kommentar bei MIN_SELL_VOLUME.
    if {"MarketBid", "BuyVol", "NPCPreis", "Handelbar"} <= set(df.columns):
        borderline = df[df["Handelbar"] & (df["MarketBid"] > 0)
                        & (df["BuyVol"] < MIN_SELL_VOLUME)
                        & (df["MarketBid"] > df["NPCPreis"])]
        if not borderline.empty:
            print(f"⚠ {len(borderline)} Items verlieren ihren Marktpreis nur an der Schwelle "
                  f"MIN_SELL_VOLUME ({MIN_SELL_VOLUME:,}) - am besten Gebot liegen zu wenig Stueck, "
                  "obwohl darunter tiefe Nachfrage stehen kann:")
            worst = borderline.assign(
                _verlust=(borderline["MarketBid"] - borderline["NPCPreis"]) * borderline["Stück/h"]
            ).nlargest(5, "_verlust")
            for _, row in worst.iterrows():
                print(f"    {str(row['Item']):<26} Bid {row['MarketBid']:>8,.0f}g bei nur "
                      f"{row['BuyVol']:>8,.0f} Stueck  ->  gerechnet wird "
                      f"{'NPC ' + format(row['NPCPreis'], ',.2f') + 'g' if row['NPCPreis'] > 0 else 'gar nichts'}")

    npc_count = int(df["SoldToNPC"].sum())
    if npc_count:
        print(f"ℹ {npc_count} Items werden ueber NPC-Vendor statt Player-Markt verkauft (kein liquider Markt oder NPC-Preis besser).")

    ambiguous_count = int(df["CostCaseAmbiguous"].sum())
    if ambiguous_count:
        print(f"ℹ {ambiguous_count} Rezepte mit Best-/Worst-Case-Unterschied (Smelting-Magic-Reichweite) - s. _Worst-Spalten.")
    if not df_chain.empty and "CostCaseAmbiguous" in df_chain.columns:
        chain_ambiguous_count = int(df_chain["CostCaseAmbiguous"].sum())
        if chain_ambiguous_count:
            print(f"ℹ {chain_ambiguous_count} Ketten-Items mit Best-/Worst-Case-Unterschied (direkt/indirekt via *_bar-Zutat).")

    warn = df[df["LiquidityWarning"]]
    if not warn.empty:
        print(f"⚠ {len(warn)} Items mit LiquidityWarning (Bedarf/Absatz > {LIQUIDITY_WARNING_RATIO:.0f}x Marktvolumen).")

    anomalies = df[df["PriceAnomaly"]]
    if not anomalies.empty:
        print(f"⚠ {len(anomalies)} Items mit PriceAnomaly (>{int(MAX_AVG_DEVIATION_RATIO * 100)}% Abweichung vom 24h-Avg).")

    spread_warnings = df[df["SpreadWarning"]]
    if not spread_warnings.empty:
        print(f"ℹ {len(spread_warnings)} Items mit SpreadWarning (Ask >{int(MAX_SPREAD_RATIO * 100)}% ueber Bid - tiefer Markt, ggf. per Sell-Order statt Sofortverkauf handeln).")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    previous_run_stats = load_last_run_stats()

    try:
        market_map = load_market_map()
        game = load_game_data()
    except RuntimeError as exc:
        print(f"⚠ Abbruch: {exc}")
        return

    item_info_map = build_item_info_map(game)
    tasks = game.get("Tasks", {})
    if not tasks:
        print("⚠ Abbruch: Game-Data enthaelt keinen 'Tasks'-Block - Endpunkt/Schema pruefen.")
        return

    # Best-/Worst-Case parallel aufbauen (Smelting-Magic-Reichweite, s. Abschnitt 2/6)
    smelting_exclusions = resolve_smelting_magic_exclusions(item_info_map)
    all_recipes_best = build_all_recipes(tasks, case="best", excluded_cost_items=smelting_exclusions)
    all_recipes_worst = build_all_recipes(tasks, case="worst", excluded_cost_items=smelting_exclusions)
    check_action_time_plausibility(all_recipes_best)

    recipe_by_output_best = build_recipe_by_output(all_recipes_best)
    recipe_by_output_worst = build_recipe_by_output(all_recipes_worst)
    fish_to_cooked = build_fish_to_cooked_map(all_recipes_best, recipe_by_output_best)

    df_best = build_single_step_df(all_recipes_best, market_map, item_info_map)
    if df_best.empty:
        print("Keine brauchbaren Farming-Daten gefunden.")
        return
    df_worst = build_single_step_df(all_recipes_worst, market_map, item_info_map)
    df = merge_worst_case_single_step(df_best, df_worst)
    if SHOW_LONGTERM_AVERAGES:
        df = enrich_with_longterm_averages(df)

    df_chain_best = build_chain_df(recipe_by_output_best, market_map, item_info_map, fish_to_cooked)
    df_chain_worst = build_chain_df(recipe_by_output_worst, market_map, item_info_map, fish_to_cooked)
    df_chain = merge_worst_case_chain(df_chain_best, df_chain_worst)

    current_run_stats = compute_run_stats(tasks, all_recipes_best, item_info_map, market_map, df, df_chain)
    print_run_sanity_check(current_run_stats, previous_run_stats)
    save_run_stats(current_run_stats)

    df_recommendation = build_recommendation_df(df_chain)
    print_recommendation(df_recommendation)

    df_reason = pd.DataFrame()
    if SHOW_REASON_ANALYSIS and not df_recommendation.empty:
        df_reason = build_reason_df(df_recommendation, df_chain)
        print_reason_highlights(df_reason)

    print_summary(df, df_chain)
    df_sensitivity = pd.DataFrame()
    if SHOW_PRICE_SENSITIVITY_CHART and not df_chain.empty:
        df_sensitivity, npc_items = build_price_sensitivity_data(df_chain)
        build_price_sensitivity_chart(df_sensitivity, npc_items)

    export_path = EXPORT_PATH
    try:
        export_excel(df, df_chain, export_path, df_sensitivity, df_recommendation, df_reason)
    except PermissionError:
        print(f"⚠ '{export_path}' ist gesperrt (meist: Datei ist noch in Excel geoeffnet).")
        fallback_path = f"{EXPORT_PATH.removesuffix('.xlsx')}_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
        print(f"  Schliesse die Datei in Excel fuer den Standardnamen - speichere stattdessen unter: {fallback_path}")
        export_excel(df, df_chain, fallback_path, df_sensitivity, df_recommendation, df_reason)
        export_path = fallback_path
    sheets = "Empfehlung, Begruendung, Ketten, Realistisch_Farmbar, Nach_Skill_Level, Rohdaten"
    if not df_sensitivity.empty:
        sheets += ", Preis_Sensitivitaet"
    print(f"\nExcel gespeichert: {export_path} (Sheets: {sheets})")


if __name__ == "__main__":
    main()
