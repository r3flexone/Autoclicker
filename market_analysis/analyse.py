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

try:
    from .config import (
        AUTO_COOK_CHANCE, AUTO_COOK_SOURCE_SKILL, COMPREHENSIVE_AVG_FIELDS,
        COMPREHENSIVE_URL_TEMPLATE, COMPREHENSIVE_VOLUME_FIELD, EXPORT_PATH,
        GAME_URL, HISTORY_ENABLED, HISTORY_ORDERBOOK_TOP_N, HISTORY_PATH,
        LIQUIDITY_WARNING_RATIO, LONGTERM_AVERAGES_REQUEST_DELAY_S,
        MARKET_DROP_WARNING_RATIO, MARKET_STATS, MARKET_URL, MARKET_VALUE_PATH,
        MAX_AVG_DEVIATION_RATIO, MAX_PLAUSIBLE_ACTION_SEC, MAX_SPREAD_RATIO,
        MIN_PLAUSIBLE_ACTION_SEC, NPC_MARKER_COLOR, OUTPUT_DIR,
        PRICE_POSITION_HINT_RATIO, PRICE_SENSITIVITY_CHART_PATH,
        PRICE_SENSITIVITY_SERIES_COLORS, PRICE_SENSITIVITY_SERIES_STYLES,
        PRICE_SENSITIVITY_TOP_N, RANKING_BASIS, REASON_CANDIDATES, REASON_TOP_N,
        RUN_STATS_HISTORY_LIMIT, RUN_STATS_PATH, SHOW_LONGTERM_AVERAGES,
        SHOW_PRICE_SENSITIVITY_CHART, SHOW_REASON_ANALYSIS,
        SKILL_RELIABILITY, SMELTING_MAGIC_EXCLUDED_ITEM_NAMES, STRUCTURAL_STATS,
        THIN_BID_HOURS, net_player_price,
    )
    from .orderbook import (
        buy_levels_from_depth, patience_analysis as geduld_analyse,
        price_position as preis_position, sell_levels_from_depth, walk_orderbook,
    )
    from .pricing import (
        duennes_top_gebot, effective_sell_price, is_player_shop_tradeable,
        kosten_pro_aktion, price_anomaly, resolve_chain, wide_spread,
    )
    from .recipes import build_all_recipes
    from . import history as historie
except ImportError:  # direkter Skriptstart bleibt unterstützt
    from config import (  # type: ignore
        AUTO_COOK_CHANCE, AUTO_COOK_SOURCE_SKILL, COMPREHENSIVE_AVG_FIELDS,
        COMPREHENSIVE_URL_TEMPLATE, COMPREHENSIVE_VOLUME_FIELD, EXPORT_PATH,
        GAME_URL, HISTORY_ENABLED, HISTORY_ORDERBOOK_TOP_N, HISTORY_PATH,
        LIQUIDITY_WARNING_RATIO, LONGTERM_AVERAGES_REQUEST_DELAY_S,
        MARKET_DROP_WARNING_RATIO, MARKET_STATS, MARKET_URL, MARKET_VALUE_PATH,
        MAX_AVG_DEVIATION_RATIO, MAX_PLAUSIBLE_ACTION_SEC, MAX_SPREAD_RATIO,
        MIN_PLAUSIBLE_ACTION_SEC, NPC_MARKER_COLOR, OUTPUT_DIR,
        PRICE_POSITION_HINT_RATIO, PRICE_SENSITIVITY_CHART_PATH,
        PRICE_SENSITIVITY_SERIES_COLORS, PRICE_SENSITIVITY_SERIES_STYLES,
        PRICE_SENSITIVITY_TOP_N, RANKING_BASIS, REASON_CANDIDATES, REASON_TOP_N,
        RUN_STATS_HISTORY_LIMIT, RUN_STATS_PATH, SHOW_LONGTERM_AVERAGES,
        SHOW_PRICE_SENSITIVITY_CHART, SHOW_REASON_ANALYSIS,
        SKILL_RELIABILITY, SMELTING_MAGIC_EXCLUDED_ITEM_NAMES, STRUCTURAL_STATS,
        THIN_BID_HOURS, net_player_price,
    )
    from orderbook import (  # type: ignore
        buy_levels_from_depth, patience_analysis as geduld_analyse,
        price_position as preis_position, sell_levels_from_depth, walk_orderbook,
    )
    from pricing import (  # type: ignore
        duennes_top_gebot, effective_sell_price, is_player_shop_tradeable,
        kosten_pro_aktion, price_anomaly, resolve_chain, wide_spread,
    )
    from recipes import build_all_recipes  # type: ignore
    import history as historie  # type: ignore


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

        actions_per_hour = 3_600_000.0 / r["base_time_ms"]
        items_per_hour = actions_per_hour * r["item_amount"]

        # Die Menge gehoert in die Preisfrage: die Marktsteuer greift erst ab 100 Gold
        # Gesamtwert, und eine Stunde Produktion ist die Menge, die man am Stueck
        # anbietet. Ohne sie verloere ein 3-Gold-Item bei jedem Vergleich 1%, das es
        # im Spiel nie zahlt.
        weg = effective_sell_price(r["item_id"], market_map, item_info_map, items_per_hour)
        sell_price, sold_to_npc = weg.preis, weg.an_npc

        # m wird fuer Zusatzinfos (Avg-Preis, Volumen, Anomalie-Checks) weiterverwendet.
        m = market_map.get(r["item_id"]) or {"buy": 0, "sell": 0, "buyVol": 0, "sellVol": 0, "avg": 0}

        # Rohdaten hat keinen Hard-Filter: jedes Recipe bleibt sichtbar, der Grund steht
        # im Klartext in "AusschlussGrund". InKetten=True heisst nur "verkaufbar" - das
        # Item kann trotzdem im Ketten-Tab fehlen (s. README).
        in_ketten = sell_price > 0
        exclusion_reason = weg.grund

        gold_per_hour = items_per_hour * sell_price
        xp_per_hour = actions_per_hour * r["xp"]

        # Ø-Preis-Variante: dailyAveragePrice statt Bid, fuer Sell-Order-Strategie statt
        # Sofortverkauf (realistischer bei breitem Spread, siehe SpreadWarning). Nur
        # relevant, wenn ueberhaupt am Player-Markt verkauft wird.
        revenue_per_hour_avg = (items_per_hour * net_player_price(m["avg"], items_per_hour)
                                if (not sold_to_npc and m["avg"] > 0) else None)

        kosten = kosten_pro_aktion(r["costs"], market_map, actions_per_hour, item_info_map)
        max_liquidity_ratio = kosten.max_liquiditaet
        if not sold_to_npc and m["buyVol"] > 0:
            max_liquidity_ratio = max(max_liquidity_ratio, items_per_hour / m["buyVol"])

        cost_per_hour = kosten.kosten * actions_per_hour

        # **Ein unbekannter Zutatenpreis ist keine kostenlose Zutat.** Frueher fiel die
        # Zeile hier stillschweigend mit 0 durch, und das Rezept stand mit vollem
        # Gewinn in der Rangliste. Jetzt bleibt Gold/h leer, und die fehlende Zutat
        # steht beim Namen im Grund.
        if kosten.vollstaendig:
            profit_per_hour = gold_per_hour - cost_per_hour
            profit_per_hour_avg = (revenue_per_hour_avg - cost_per_hour
                                   if revenue_per_hour_avg is not None else None)
            gold_pro_stueck = (profit_per_hour / items_per_hour) if items_per_hour > 0 else 0.0
            gold_pro_xp = profit_per_hour / max(xp_per_hour, 1)
        else:
            profit_per_hour = profit_per_hour_avg = None
            gold_pro_stueck = gold_pro_xp = None
            cost_per_hour = None
            fehlt = ", ".join(kosten.fehlende[:3]) or "unbekannt"
            grund = f"Zutatenpreis unbekannt ({fehlt})"
            exclusion_reason = f"{exclusion_reason} + {grund}" if exclusion_reason else grund

        output_anomaly = price_anomaly(m) if not sold_to_npc else False
        output_spread_warning = wide_spread(m) if not sold_to_npc else False

        liquidity_warning = max_liquidity_ratio > LIQUIDITY_WARNING_RATIO or kosten.markt_ungesund
        price_anomaly_flag = output_anomaly or kosten.preisanomalie
        spread_warning_flag = output_spread_warning or kosten.spread_warnung

        # Duennes Top-Gebot: das Item wird trotzdem am Markt verkauft (die Tiefe
        # darunter kennt der Bulk-Endpoint nicht), aber die Stunde geht dort nicht
        # in einem Zug weg. Warnung statt Ausschluss - genau daran scheiterten
        # frueher yew_log und yew_plank.
        duennes_gebot = bool(not sold_to_npc and in_ketten
                             and duennes_top_gebot(m, items_per_hour))

        if not in_ketten:
            status = "Ausgeschlossen"
        elif not kosten.vollstaendig:
            status = "Ausgeschlossen"
        else:
            status = "OK"
            warn_parts = []
            if liquidity_warning:
                warn_parts.append("Liquiditaet")
            if duennes_gebot:
                warn_parts.append("Top-Gebot duenn")
            if price_anomaly_flag:
                warn_parts.append("Preisanomalie")
            if spread_warning_flag:
                warn_parts.append("Spread")
            if warn_parts:
                status = "Warnung"
                exclusion_reason = "Warnung: " + ", ".join(warn_parts)

        results.append({
            "Item": r["name"], "Skill": r["skill"], "Level": r["level"],
            "Time_sec": r["base_time_ms"] / 1000.0,
            "XP": r["xp"],
            "Gold/h": profit_per_hour,
            "Gold/h (Ø-Preis)": profit_per_hour_avg,
            "Gold pro Stück": gold_pro_stueck,
            "Stück/h": items_per_hour,
            "Revenue/h": gold_per_hour,
            "Revenue/h (Ø-Preis)": revenue_per_hour_avg,
            "Cost/h": cost_per_hour,
            "SoldToNPC": sold_to_npc,
            "NPCPreis": weg.npc_preis,
            "MarketBid": m["buy"],
            "MarketAsk": m["sell"],
            "Handelbar": can_trade,
            "NPCVerkaufMoeglich": can_sell_npc,
            "CostDataComplete": kosten.vollstaendig,
            "FehlendeZutaten": ", ".join(kosten.fehlende),
            "TopGebotDuenn": duennes_gebot,
            "InKetten": in_ketten and kosten.vollstaendig,
            "Status": status,
            "AusschlussGrund": exclusion_reason,
            "LiquidityWarning": liquidity_warning,
            "LiquidityRatio": round(max_liquidity_ratio, 1),
            "IngredientMarketUnhealthy": kosten.markt_ungesund,
            "PriceAnomaly": price_anomaly_flag,
            "OutputPriceAnomaly": output_anomaly,
            "IngredientPriceAnomaly": kosten.preisanomalie,
            "SpreadWarning": spread_warning_flag,
            "OutputSpreadWarning": output_spread_warning,
            "IngredientSpreadWarning": kosten.spread_warnung,
            "BuyVol": m["buyVol"], "SellVol": m["sellVol"],
            "XP/h": xp_per_hour,
            "Gold per XP": gold_pro_xp,
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

def build_chain_df(recipe_by_output: dict, market_map: dict, item_info_map: dict, fish_to_cooked: dict) -> pd.DataFrame:
    chain_results = []
    for item_id, recipe in recipe_by_output.items():
        # Handelbarkeit steckt in effective_sell_price (Player-Markt vs. NPC einzeln) -
        # kein eigener Vorab-Filter mehr, sonst faellt auch raus, was man dem NPC
        # sehr wohl verkaufen kann.
        kette = resolve_chain(item_id, market_map, recipe_by_output, fish_to_cooked,
                              item_info_map)
        if kette.zeit_ms <= 0:
            continue

        actions_per_hour = 3_600_000.0 / kette.zeit_ms
        weg = effective_sell_price(item_id, market_map, item_info_map, actions_per_hour)
        sell_price, sold_to_npc = weg.preis, weg.an_npc
        if sell_price <= 0:
            continue

        m = market_map.get(item_id) or {"buy": 0, "sell": 0, "buyVol": 0, "sellVol": 0, "avg": 0}
        # Zwei verschiedene Dinge, die frueher vermischt waren und ein Item verworfen
        # haben, das bestens handelbar ist:
        #   erlaubt = das Item DARF im Player Shop gehandelt werden (API-Flag)
        #   duenn   = am besten Gebot liegt weniger als eine Stunde Produktion
        # Ein duennes Top-Gebot ist eine Warnung, kein Ausschluss: direkt darunter kann
        # tiefe Nachfrage stehen (Oak: 6.178 Stueck oben, 327.915 eine Stufe tiefer),
        # und wie tief das Buch wirklich ist, misst das Sheet "Begruendung".
        spieler_erlaubt = is_player_shop_tradeable(item_info_map.get(item_id, {}))
        duennes_gebot = bool(not sold_to_npc and duennes_top_gebot(m, actions_per_hour))

        revenue_per_hour = actions_per_hour * sell_price
        # Auto-Cook: der rohe Rest des Fangs ist verkaeuflich und wird gutgeschrieben.
        # `nebenertrag` steht pro Stueck Endprodukt, also mit derselben Rate wie alles
        # andere in dieser Zeile.
        nebenertrag_pro_stunde = actions_per_hour * kette.nebenertrag
        cost_per_hour = actions_per_hour * kette.kosten

        if kette.kosten_bekannt:
            profit_per_hour = revenue_per_hour + nebenertrag_pro_stunde - cost_per_hour
        else:
            profit_per_hour = None
            cost_per_hour = None

        # Ø-Preis-Variante (siehe Kommentar in build_single_step_df)
        revenue_per_hour_avg = (actions_per_hour * net_player_price(m["avg"], actions_per_hour)
                                if (not sold_to_npc and m["avg"] > 0) else None)
        profit_per_hour_avg = (revenue_per_hour_avg + nebenertrag_pro_stunde - cost_per_hour
                               if (revenue_per_hour_avg is not None and kette.kosten_bekannt)
                               else None)

        max_liquidity_ratio = kette.liquiditaet * actions_per_hour
        if not sold_to_npc and m["buyVol"] > 0:
            max_liquidity_ratio = max(max_liquidity_ratio, actions_per_hour / m["buyVol"])

        skills_involved = sorted(set(s[1] for s in kette.schritte))
        # Auto-Cook: die Kette FISCHT nur, der Kochschritt findet nie statt (s.
        # resolve_chain). Das Koch-Rezept als "letzten Schritt" abzurechnen kreidete
        # XP fuer eine Aktion an, die niemand ausfuehrt - bei cooked_tuna 72.000
        # Cooking-XP/h statt der 27.000 Fishing-XP/h, die real anfallen. Skill und
        # Level muessen aus demselben Grund vom Fisch-Rezept kommen.
        final_recipe, final_xp_teiler = recipe, recipe["item_amount"]
        auto_cook_quelle = next(
            (raw for raw, cooked in fish_to_cooked.items() if cooked == item_id), None)
        if auto_cook_quelle is not None and auto_cook_quelle in recipe_by_output \
                and AUTO_COOK_CHANCE > 0:
            final_recipe = recipe_by_output[auto_cook_quelle]
            final_xp_teiler = final_recipe["item_amount"] * AUTO_COOK_CHANCE

        xp_per_unit_final_step = final_recipe["xp"] / final_xp_teiler

        chain_results.append({
            "Item": recipe["name"], "ItemID": item_id, "Level": final_recipe["level"],
            "FinalSkill": final_recipe["skill"],
            "ChainSkills": " -> ".join(skills_involved),
            "ChainDepth": len(kette.schritte),
            "FullySelfSufficient": kette.autark,
            "TimePerItem_sec": kette.zeit_ms / 1000.0,
            "XP_letzter_Schritt_pro_Stück": xp_per_unit_final_step,
            "Gold/h (Eigenherstellung)": profit_per_hour,
            "Gold/h (Eigenherstellung, Ø-Preis)": profit_per_hour_avg,
            "Gold pro Stück": (profit_per_hour / actions_per_hour
                               if profit_per_hour is not None else None),
            "Stück/h": actions_per_hour,
            "Revenue/h": revenue_per_hour,
            "Revenue/h (Ø-Preis)": revenue_per_hour_avg,
            "Nebenertrag/h": nebenertrag_pro_stunde,
            "RawMaterialCost/h": cost_per_hour,
            "KostenVollstaendig": kette.kosten_bekannt,
            "FehlendeZutaten": ", ".join(kette.fehlende),
            "SoldToNPC": sold_to_npc,
            "Verkaufspreis": sell_price,
            "NPCPreis": weg.npc_preis,
            "SpielerpreisBid": m["buy"] if (spieler_erlaubt and m["buy"] > 0) else 0.0,
            "SpielerVerkaufMoeglich": spieler_erlaubt,
            "SpielerMarktDuenn": duennes_gebot,
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
    # Nur Ketten mit bekannten Kosten: eine Kurve ueber einen Gewinn, dessen Kosten
    # niemand kennt, waere eine Linie ohne Aussage.
    top = df_chain[df_chain["FullySelfSufficient"]
                   & df_chain["Gold/h (Eigenherstellung)"].notna()].sort_values(
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
        cost_per_item = (_num(row["RawMaterialCost/h"]) / stueck_h) if stueck_h > 0 else 0.0
        # Auto-Cook-Nebenertrag gehoert dazu: er faellt bei jedem Preispunkt gleich an
        # und verschoebe sonst die ganze Kurve nach unten.
        neben_pro_stueck = (_num(row.get("Nebenertrag/h")) / stueck_h) if stueck_h > 0 else 0.0
        npc_preis = row.get("NPCPreis", 0) or 0.0
        # Vergleichslinie: was dasselbe Zeitbudget beim NPC einbraechte (steuerfrei)
        npc_gold_h = (stueck_h * (npc_preis + neben_pro_stueck - cost_per_item)
                      if npc_preis else None)

        data = {
            "Item": row["Item"], "ItemID": int(row["ItemID"]), "FinalSkill": row["FinalSkill"],
            "SoldToNPC": bool(row["SoldToNPC"]),
            "Kosten_pro_Stück": cost_per_item,
            "NPC-Preis": npc_preis or None,
            "NPC_Gold_h": round(npc_gold_h) if npc_gold_h is not None else None,
        }
        for label, p in zip(PRICE_SENSITIVITY_LABELS_SHORT, prices):
            data[f"{label}_Preis"] = p
            data[f"{label}_Gold_h"] = (
                (stueck_h * (net_player_price(p, stueck_h) + neben_pro_stueck - cost_per_item))
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
    farben = PRICE_SENSITIVITY_SERIES_COLORS
    stile = PRICE_SENSITIVITY_SERIES_STYLES
    # Das Aussehen haengt am ITEM-NAMEN, nicht an der Rangposition. Gezeichnet (und in der
    # Legende gelistet) wird weiter nach Gold/h, aber die Farbe kommt aus der alphabetisch
    # sortierten Liste. Sonst waere oak heute blau und morgen aqua, sobald sich die
    # Rangfolge durch Preisbewegungen dreht - und ein Vergleich zweier Laeufe waere wertlos.
    # Der Index ist je Item eindeutig, also kann sich keine Kombination doppeln.
    farb_index = {name: i for i, name in enumerate(sorted(str(n) for n in df_sens["Item"]))}
    for _, row in df_sens.iterrows():
        ys_raw = [row[f"{label}_Gold_h"] for label in PRICE_SENSITIVITY_LABELS_SHORT]
        xs = [i2 for i2, v in enumerate(ys_raw) if pd.notna(v)]
        ys = [v for v in ys_raw if pd.notna(v)]
        idx = farb_index[str(row["Item"])]
        ax.plot(xs, ys, marker="o", markersize=5, linewidth=2,
                color=farben[idx % len(farben)],
                linestyle=stile[(idx // len(farben)) % len(stile)],
                label=str(row["Item"]))

        # Punkte einsammeln, an denen der Player Shop den NPC nicht mehr schlaegt
        npc = row.get("NPC_Gold_h")
        if pd.notna(npc):
            for x, y in zip(xs, ys):
                if y <= npc:
                    rot_x.append(x)
                    rot_y.append(y)

    if rot_x:
        # Weisser Ring statt dunkelrotem: die Punkte liegen AUF den Linien, und der Ring
        # in Hintergrundfarbe trennt sie davon ab. Keine Serienfarbe liegt naeher als
        # Delta-E 16.8 an diesem Rot - die Punkte sind also auch als Farbe eindeutig,
        # nicht nur durch ihre Form.
        ax.scatter(rot_x, rot_y, color=NPC_MARKER_COLOR, s=70, zorder=5,
                   edgecolors="white", linewidths=1.2,
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
    "Rang", "Item", "Skills", "Gold/h realistisch", "Gold/h gewichtet", "Gold/h",
    "Verlässlichkeit",
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

    # Ketten mit unbekanntem Zutatenpreis koennen nicht ranken: ihr Gold/h ist leer,
    # und eine 0 einzusetzen hiesse, sie als "verdient nichts" einzusortieren, obwohl
    # niemand weiss, was sie verdienen. Sie stehen weiter im Ketten-Sheet, mit Grund.
    src = df_chain[df_chain["Gold/h (Eigenherstellung)"].notna()].copy()
    if src.empty:
        return pd.DataFrame(columns=RECOMMENDATION_COLUMNS)

    # Nach gewichtetem Gold/h sortieren: unplanbarer Nachschub soll die Empfehlung nicht
    # anfuehren, auch wenn die reine Rechnung dafuer spricht (s. SKILL_RELIABILITY).
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
        stueck_h = _num(r.get("Stück/h"))
        spieler_netto = net_player_price(spieler, stueck_h or 1.0) if spieler else 0.0
        gewaehlt, alternative = (npc, spieler_netto) if an_npc else (spieler_netto, npc)
        vorteil = (gewaehlt / alternative - 1) if alternative > 0 else None

        warn = []
        if r.get("SpielerMarktDuenn"):
            warn.append(f"Top-Gebot dünn ({int(_num(r.get('BidVolumen'))):,} Stk)")
        if an_npc and spieler_netto > npc:
            warn.append("Spielergebot wäre höher, aber nicht erreichbar – s. Begründung")
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
        gemessen = r.get("Gold/h realistisch")
        if gemessen is not None and not pd.isna(gemessen):
            # Gemessen schlaegt gerechnet: das ist die Zahl, nach der auch sortiert wird
            gold = f"{int(gemessen):,} ({r['Gold/h']:,})"
        elif r["Verlässlichkeit"] < 1:
            gold = f"{r['Gold/h gewichtet']:,} ({r['Gold/h']:,})"
        else:
            gold = f"{r['Gold/h']:,}"
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

def _format_levels(levels: list, max_n: int = 5) -> str:
    top = sorted(levels, key=lambda x: x[0], reverse=True)[:max_n]
    return "  |  ".join(f"{p:,.0f}g x {m:,.0f}" for p, m in top)


def _preis_position_text(position: float | None, trend: str) -> str:
    """Einordnung der Momentaufnahme gegen den eigenen 30-Tage-Verlauf."""
    if position is None or abs(position) < PRICE_POSITION_HINT_RATIO:
        return ""
    if position < 0:
        satz = f"Kurs liegt {-position:.0%} UNTER dem 30-Tage-Schnitt (Verkauf in eine Delle)"
    else:
        satz = f"Kurs liegt {position:.0%} ueber dem 30-Tage-Schnitt (eher Ausnahme als Normalfall)"
    return f"{satz}, Trend {trend}" if trend else satz


def _geduld_text(geduld: dict | None) -> str:
    """Was ein eigenes Angebot brächte - nur erwähnen, wenn es sich lohnt."""
    if not geduld or geduld.get("aufschlag") is None or geduld["aufschlag"] < 0.02:
        return ""
    satz = (f"mit eigenem Angebot zu {geduld['preis']:,.0f}g waeren es "
            f"{geduld['aufschlag']:+.0%} ({geduld['gold_h']:,.0f} Gold/h)")
    warte = geduld.get("wartezeit_h")
    if warte is not None:
        satz += (f", 1 h Produktion liegt dann ~{warte:,.0f} h im Buch"
                 if warte >= 1 else ", 1 h Produktion ist in unter 1 h weg")
    return satz


def _verdict(an_npc: bool, npc: float, top_preis: float, stunden_deckung: float,
             schnitt: float, verlust: float, warnung: str, abweichung: float = 0.0,
             position: float | None = None, trend: str = "",
             geduld: dict | None = None) -> str:
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
    pos_text = _preis_position_text(position, trend)
    if pos_text:
        teile.append(pos_text)
    geduld_text = _geduld_text(geduld)
    if geduld_text:
        teile.append(geduld_text)
    if warnung:
        teile.append(warnung)
    return "; ".join(teile) + "."


REASON_COLUMNS = [
    "Rang", "Item", "Gold/h realistisch", "Gold/h (Papier)", "Verkauf an", "Stück/h",
    "Bestes Gebot (brutto)", "Menge am besten Gebot", "Deckt Stunden",
    "Schnitt bei 1h Produktion (netto)", "Preisverlust",
    # Wer nicht sofort verkaufen muss: eigenes Angebot einstellen statt ins Gebot
    "Ansetzbarer Preis", "Erlös dabei (netto)", "Gold/h mit Geduld",
    "Aufschlag vs Sofort", "Wartezeit (h)", "Angebot im Buch",
    "Preis vs 30-Tage-Schnitt", "Markt-Trend",
    "NPC-Preis", "NPC besser", "Kaufgebote (Stufen)", "Bewertung",
]


def _num(value) -> float:
    """Leere Zellen und NaN als 0 - `NaN or 0` liefert in Python NaN, nicht 0."""
    return 0.0 if value is None or pd.isna(value) else float(value)


def build_reason_df(df_rec: pd.DataFrame, df_chain: pd.DataFrame) -> tuple[pd.DataFrame, list]:
    """Warum lohnt sich ein Item - mit den echten Kaufgebot-Stufen aus dem Player Shop.

    Der Gold/h-Wert der uebrigen Sheets unterstellt, dass du beliebig viel zum besten
    Gebot los wirst. Das stimmt nur, solange dort genug Volumen liegt. Hier wird eine
    Stunde Produktion tatsaechlich durchs Orderbuch gerechnet.

    Kostet REASON_TOP_N Live-Requests (1 pro Item).

    Zweiter Rueckgabewert sind die abgerufenen Orderbuecher - die Historie speichert
    sie, statt sie ein zweites Mal zu holen."""
    if df_rec.empty:
        return pd.DataFrame(columns=REASON_COLUMNS), []

    kosten_je_h = df_chain.set_index("ItemID")["RawMaterialCost/h"].to_dict() if not df_chain.empty else {}
    id_von_item = df_chain.set_index("Item")["ItemID"].to_dict() if not df_chain.empty else {}
    neben_je_h = (df_chain.set_index("ItemID")["Nebenertrag/h"].to_dict()
                  if not df_chain.empty and "Nebenertrag/h" in df_chain.columns else {})
    buecher: list = []      # fuer die Historie - abgerufen wird ohnehin schon

    kandidaten = max(REASON_CANDIDATES, REASON_TOP_N)
    print(f"\nHole Kaufgebot-Stufen fuer {min(kandidaten, len(df_rec))} Kandidaten "
          f"(1 Request pro Item), sortiere danach nach 'Gold/h realistisch'...")

    rows = []
    for _, r in df_rec.head(kandidaten).iterrows():
        item_id = id_von_item.get(r["Item"])
        an_npc = r["Verkauf an"] == "NPC-Vendor"
        npc = _num(r["NPC-Preis"])
        stueck_h = _num(r["Stück/h"])
        material_h = _num(kosten_je_h.get(item_id))
        nebenertrag_h = _num(neben_je_h.get(item_id))
        # Bezugsgroesse ist der Preis, auf dem das ausgewiesene Gold/h beruht - sonst
        # widersprechen sich "Preisverlust" und "Gold/h realistisch".
        referenz = _num(r["Erlös pro Stück"])
        # Und BRUTTO daneben, fuer den Vergleich mit den API-Durchschnitten: die sind
        # Bruttopreise. Mit dem Netto-Erloes gefuettert meldete `preis_position()` bei
        # jedem Item dieselben -1%, also einen Messfehler, der wie eine Marktlage
        # aussieht.
        #
        # Es zaehlt nur ein SPIELER-Preis. Der NPC-Preis gehoert nicht auf diese
        # Skala - er ist fest und hat mit dem 30-Tage-Schnitt des Player Shops nichts
        # zu tun; ihn dort einzusetzen ergaebe eine Abweichung, die nichts misst.
        referenz_brutto = _num(r.get("Spieler-Gebot (brutto)"))

        depth = fetch_orderbook_depth(int(item_id)) if item_id is not None else None
        levels = buy_levels_from_depth(depth) if depth else []
        if depth is not None and item_id is not None:
            buecher.append({"item": r["Item"], "item_id": int(item_id),
                            "kauf": levels,
                            "verkauf": sell_levels_from_depth(depth)})

        if levels:
            top_preis, top_menge = max(levels, key=lambda x: x[0])
            if top_preis > 0:
                referenz_brutto = referenz_brutto or top_preis
            deckung = top_menge / stueck_h if stueck_h > 0 else 0.0
            brutto, verkauft, _ = walk_orderbook(levels, stueck_h)
            # Marktsteuer auf den Spieler-Anteil. `brutto` ist bereits der GESAMTwert
            # der Stunde, also entscheidet er selbst ueber die 100-Gold-Schwelle -
            # deshalb Menge 1, nicht `verkauft`.
            erloes = net_player_price(brutto, 1.0)
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
        abweichung = ((abs(net_player_price(top_preis, stueck_h) - referenz) / referenz)
                      if (referenz > 0 and top_preis > 0) else 0.0)

        # Aus derselben Antwort, ohne zusaetzlichen Request. BRUTTO gegen BRUTTO:
        # der 30-Tage-Schnitt kennt keine Steuer.
        position, trend = preis_position(referenz_brutto, depth)
        kosten_je_stueck = (material_h / stueck_h) if stueck_h > 0 else 0.0
        # Beim NPC gibt es nichts zu verhandeln — der zahlt immer denselben Preis.
        geduld = (geduld_analyse(depth, top_preis, stueck_h, kosten_je_stueck)
                  if not an_npc else geduld_analyse(None, 0.0, 0.0, 0.0))

        rows.append({
            "Rang": 0,   # wird nach der Neusortierung vergeben
            "Item": r["Item"],
            "Gold/h (Papier)": r["Gold/h"],
            "Verkauf an": r["Verkauf an"],
            "Stück/h": round(stueck_h, 1),
            "Bestes Gebot (brutto)": round(top_preis, 2) if top_preis else None,
            "Menge am besten Gebot": round(top_menge) if top_menge else None,
            "Deckt Stunden": round(deckung, 2) if deckung else None,
            "Schnitt bei 1h Produktion (netto)": round(schnitt, 2),
            "Preisverlust": f"-{verlust:.1%}" if verlust > 0.0005 else "0%",
            "Ansetzbarer Preis": round(geduld["preis"], 2) if geduld["preis"] else None,
            "Erlös dabei (netto)": round(geduld["erloes"], 2) if geduld["erloes"] else None,
            "Gold/h mit Geduld": round(geduld["gold_h"]) if geduld["gold_h"] is not None else None,
            "Aufschlag vs Sofort": (f"{geduld['aufschlag']:+.0%}"
                                    if geduld["aufschlag"] is not None else None),
            "Wartezeit (h)": (round(geduld["wartezeit_h"], 1)
                              if geduld["wartezeit_h"] is not None else None),
            "Angebot im Buch": (round(geduld["angebot_im_buch"])
                                if geduld["angebot_im_buch"] is not None else None),
            "Preis vs 30-Tage-Schnitt": f"{position:+.0%}" if position is not None else None,
            "Markt-Trend": trend or None,
            "Gold/h realistisch": round(erloes + nebenertrag_h - material_h),
            "NPC-Preis": round(npc, 2) if npc else None,
            "NPC besser": bool(npc > schnitt) if not an_npc else True,
            "Kaufgebote (Stufen)": _format_levels(levels) if levels else "keine",
            "Bewertung": _verdict(an_npc, npc, top_preis, deckung, schnitt, verlust,
                                  "" if pd.isna(r.get("Warnung")) else str(r.get("Warnung") or ""),
                                  abweichung, position, trend, geduld),
        })

    if not rows:
        return pd.DataFrame(columns=REASON_COLUMNS), buecher

    # DER eigentliche Punkt: nach der gemessenen Zahl sortieren, nicht nach der
    # gerechneten. Vorher wurde 'Gold/h realistisch' erst fuer die bereits feststehende
    # Top-10 ermittelt und konnte die Reihenfolge gar nicht mehr beeinflussen.
    df_reason = pd.DataFrame(rows, columns=REASON_COLUMNS)

    # Welche der beiden gemessenen Zahlen den Rang bestimmt, haengt davon ab, ob das
    # Gold sofort gebraucht wird (s. RANKING_BASIS). Fehlt die Geduld-Zahl - beim
    # NPC-Verkauf gibt es nichts zu verhandeln -, zaehlt die Sofort-Zahl.
    if RANKING_BASIS == "geduld":
        schluessel = df_reason["Gold/h mit Geduld"].fillna(df_reason["Gold/h realistisch"])
    else:
        schluessel = df_reason["Gold/h realistisch"]
    df_reason = df_reason.assign(_rang=schluessel).sort_values(
        "_rang", ascending=False).drop(columns=["_rang"]).head(REASON_TOP_N)
    df_reason["Rang"] = range(1, len(df_reason) + 1)
    df_reason = df_reason.reset_index(drop=True)
    # Die Buecher in der Reihenfolge der gemessenen Rangliste: die Historie hebt nur
    # die vordersten auf, und "vorderste" soll heissen "die besten", nicht "die zuerst
    # abgerufenen".
    rang = {item: i for i, item in enumerate(df_reason["Item"])}
    buecher.sort(key=lambda b: rang.get(b["item"], len(rang)))
    return df_reason, buecher


def sortiere_nach_messung(df_rec: pd.DataFrame, df_reason: pd.DataFrame) -> pd.DataFrame:
    """Bringt die Empfehlung in die Reihenfolge der gemessenen Zahl.

    Gemessene Items zuerst (nach 'Gold/h realistisch'), dahinter unveraendert der Rest —
    der wurde nicht durchs Orderbuch gerechnet und darf deshalb nicht so tun, als waere
    er geprueft. `Rang` wird durchgezaehlt, damit Empfehlung und Begruendung dieselbe
    Nummer meinen.
    """
    if df_rec.empty or df_reason.empty:
        return df_rec
    reihenfolge = {item: i for i, item in enumerate(df_reason["Item"])}
    src = df_rec.copy()
    src["_pos"] = src["Item"].map(reihenfolge)
    gemessen = src[src["_pos"].notna()].sort_values("_pos")
    rest = src[src["_pos"].isna()]
    raus = pd.concat([gemessen, rest], ignore_index=True).drop(columns=["_pos"])
    raus["Rang"] = range(1, len(raus) + 1)
    # Die gemessene Zahl mitnehmen, damit das Empfehlungs-Blatt fuer sich steht.
    # Leer bei allem, was nicht durchs Orderbuch gerechnet wurde - eine Zahl dort
    # waere eine Behauptung, die niemand geprueft hat.
    gemessene_werte = dict(zip(df_reason["Item"], df_reason["Gold/h realistisch"]))
    raus["Gold/h realistisch"] = raus["Item"].map(gemessene_werte)
    return raus[[c for c in RECOMMENDATION_COLUMNS if c in raus.columns]]


def print_reason_highlights(df_reason: pd.DataFrame):
    """Die Faelle, in denen der ausgewiesene Gold/h-Wert nicht haltbar ist."""
    if df_reason.empty:
        return
    schoen = df_reason[df_reason["Gold/h realistisch"] < df_reason["Gold/h (Papier)"] * 0.9]
    if not schoen.empty:
        print(f"\n⚠ {len(schoen)} Items halten ihren Gold/h-Wert nicht, wenn man eine ganze "
              "Stunde Produktion ins Buch verkauft:")
        for _, r in schoen.head(8).iterrows():
            print(f"    {str(r['Item']):<26}{r['Gold/h (Papier)']:>11,} -> {r['Gold/h realistisch']:>11,}  "
                  f"({r['Preisverlust']} Preisverlust)")


# ---------------------------------------------------------------
# Excel-Export
# ---------------------------------------------------------------

SORT_COLUMN_PER_SHEET = {
    "Empfehlung": "Gold/h realistisch",
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


def export_market_values(df: pd.DataFrame, path: str) -> int:
    """Schreibt eine schlanke Item-Name -> Gold-pro-Stueck-Tabelle als JSON.

    Der Autoclicker kann seine Item-Klicks danach sortieren statt nach einer von
    Hand getippten Prioritaetszahl — ohne dass eine Seite die andere importiert.

    Absichtlich nur Name -> Zahl: alles Weitere waere fuer die Klick-Reihenfolge
    bedeutungslos, und eine schmale Datei kann nicht veralten wie eine breite.
    Gibt die Anzahl geschriebener Eintraege zurueck.
    """
    if df is None or df.empty or "Item" not in df.columns:
        return 0
    spalte = "Gold pro Stück" if "Gold pro Stück" in df.columns else None
    if spalte is None:
        return 0
    werte: dict[str, float] = {}
    for _, zeile in df.iterrows():
        name = str(zeile["Item"]).strip()
        try:
            wert = float(zeile[spalte])
        except (TypeError, ValueError):
            continue
        if not name or wert != wert:          # NaN faellt hier raus
            continue
        # Mehrere Rezepte auf dasselbe Item: der beste Wert gewinnt.
        if name not in werte or wert > werte[name]:
            werte[name] = round(wert, 2)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(werte, f, ensure_ascii=False, indent=1, sort_keys=True)
    return len(werte)


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
# Historie
# ---------------------------------------------------------------

def historie_zeilen(df_chain: pd.DataFrame, df_reason: pd.DataFrame) -> list:
    """Eine Zeile je Endprodukt fuer die Historie - aus dem, was ohnehin dasteht.

    Bezugspunkt ist die Kette und nicht Rohdaten: sie ist die Sicht, nach der man
    handelt (Zutaten selbst farmen), und sie hat genau eine Zeile je Item. Die
    gemessene Zahl und der Rang kommen aus der Begruendung, soweit sie dort steht -
    fuer alles Weitere bleibt das Feld leer, statt eine Zahl zu behaupten, die
    niemand durchs Orderbuch gerechnet hat.
    """
    if df_chain.empty:
        return []
    gemessen, raenge = {}, {}
    if not df_reason.empty:
        gemessen = dict(zip(df_reason["Item"], df_reason["Gold/h realistisch"]))
        raenge = dict(zip(df_reason["Item"], df_reason["Rang"]))

    zeilen = []
    for _, r in df_chain.iterrows():
        name = str(r["Item"])
        warnungen = [text for flag, text in (
            (r.get("LiquidityWarning"), "Liquiditaet"),
            (r.get("SpielerMarktDuenn"), "Top-Gebot duenn"),
            (r.get("PriceAnomaly"), "Preisanomalie"),
            (r.get("SpreadWarning"), "Spread"),
            (not r.get("KostenVollstaendig", True), "Zutatenpreis unbekannt"),
            (not r.get("FullySelfSufficient"), "Zutat muss gekauft werden"),
        ) if bool(flag)]
        zeilen.append({
            "item": name,
            "item_id": r.get("ItemID"),
            "skill": r.get("FinalSkill"),
            "bid": r.get("SpielerpreisBid"),
            "ask": r.get("MarketAsk"),
            "avg": None,
            "bid_vol": r.get("BidVolumen"),
            "ask_vol": None,
            "npc_preis": r.get("NPCPreis"),
            "kosten_h": r.get("RawMaterialCost/h"),
            "gold_h": r.get("Gold/h (Eigenherstellung)"),
            "gold_h_real": gemessen.get(name),
            "verkaufsweg": "NPC-Vendor" if bool(r.get("SoldToNPC")) else "Spieler",
            "rang": raenge.get(name),
            "warnungen": ", ".join(warnungen),
        })
    return zeilen


def schreibe_historie(df_chain: pd.DataFrame, df_reason: pd.DataFrame, buecher: list,
                      pfad: str = HISTORY_PATH) -> str:
    """Den fertigen Lauf in die SQLite-Historie schreiben und alte Bestaende aufraeumen.

    Laeuft ganz am Ende, NACH dem Excel-Export: was hier landet, ist damit ein Lauf,
    der auch ein Ergebnis produziert hat. Ein Fehlschlag kostet nur die Historie -
    die Excel-Datei ist das eigentliche Ergebnis und steht bereits.
    """
    zeilen = historie_zeilen(df_chain, df_reason)
    if not zeilen:
        return ""
    conn = historie.oeffne(pfad)
    try:
        with historie.lauf(conn) as run_id:
            historie.schreibe_items(conn, run_id, zeilen)
            historie.schreibe_orderbuch(conn, run_id, buecher, HISTORY_ORDERBOOK_TOP_N)
        weg = historie.aufraeumen(conn)
    finally:
        conn.close()
    geloescht = sum(v for k, v in weg.items() if k != "verdichtet")
    hinweis = f" ({weg['verdichtet']} Tageswerte, {geloescht} Altzeilen entfernt)" if geloescht or weg["verdichtet"] else ""
    return f"{len(zeilen)} Items{hinweis}"


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

    # Duenne Top-Gebote: das Item wird am Markt verkauft, aber eine Stunde Produktion
    # geht dort nicht in einem Zug weg. Frueher war das ein Ausschluss (MIN_SELL_VOLUME)
    # und warf Items wie yew_log auf den NPC-Preis zurueck; heute eine Warnung - wie
    # tief das Buch wirklich ist, misst das Sheet "Begruendung".
    if "TopGebotDuenn" in df.columns:
        duenn = df[df["TopGebotDuenn"]]
        if not duenn.empty:
            print(f"ℹ {len(duenn)} Items mit duennem Top-Gebot (weniger als "
                  f"{THIN_BID_HOURS:g} h Produktion) - sie werden trotzdem am Markt "
                  "gerechnet, die echte Tiefe steht im Sheet 'Begruendung':")
            for _, row in duenn.nlargest(5, "Stück/h").iterrows():
                print(f"    {str(row['Item']):<26} Bid {row['MarketBid']:>8,.0f}g bei "
                      f"{row['BuyVol']:>10,.0f} Stueck  ({row['Stück/h']:,.0f} Stk/h)")

    # Unbekannte Zutatenpreise: die betroffenen Rezepte haben KEIN Gold/h, statt mit
    # einer kostenlosen Zutat zu rechnen. Ohne diese Zeile verschwaende der Unterschied
    # zwischen "verdient nichts" und "wissen wir nicht".
    if "CostDataComplete" in df.columns:
        unklar = df[~df["CostDataComplete"]]
        if not unklar.empty:
            print(f"⚠ {len(unklar)} Rezepte ohne vollstaendige Zutatenpreise - Gold/h "
                  "bleibt dort leer (nicht 0), Grund steht in 'FehlendeZutaten':")
            for _, row in unklar.head(5).iterrows():
                print(f"    {str(row['Item']):<26} fehlt: {row['FehlendeZutaten']}")

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

    # Erst messen, dann drucken: die Begruendung rechnet eine Stunde Produktion durchs
    # echte Orderbuch und liefert damit die belastbarere Rangfolge. Wird sie wie frueher
    # NACH der Ausgabe gebaut, kann sie die Reihenfolge nicht mehr beeinflussen.
    df_reason = pd.DataFrame()
    buecher: list = []
    if SHOW_REASON_ANALYSIS and not df_recommendation.empty:
        df_reason, buecher = build_reason_df(df_recommendation, df_chain)
        df_recommendation = sortiere_nach_messung(df_recommendation, df_reason)

    print_recommendation(df_recommendation)
    if not df_reason.empty:
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

    # Historie zuletzt: nur ein Lauf, der bis hierher gekommen ist, gehoert hinein.
    # Ein halber Lauf saehe in der Zeitreihe wie ein Markteinbruch aus.
    if HISTORY_ENABLED:
        try:
            bericht = schreibe_historie(df_chain, df_reason, buecher)
            if bericht:
                print(f"Historie ergaenzt: {HISTORY_PATH} - {bericht}")
        except Exception as e:      # noqa: BLE001 - die Historie ist Beiwerk
            print(f"⚠ Historie konnte nicht geschrieben werden: {e}")

    # Schlanke Wertetabelle nebenher - schlaegt sie fehl, ist das kein Grund, den
    # ganzen Lauf zu verlieren: die Excel-Datei ist das eigentliche Ergebnis.
    try:
        n_werte = export_market_values(df, MARKET_VALUE_PATH)
        if n_werte:
            print(f"Marktwerte gespeichert: {MARKET_VALUE_PATH} ({n_werte} Items)")
            print("  Der Autoclicker kann danach sortieren - Pfad in seiner config.json "
                  "unter 'scan_market_value_file' eintragen.")
    except (IOError, OSError) as e:
        print(f"⚠ Marktwerte konnten nicht geschrieben werden: {e}")


if __name__ == "__main__":
    main()
