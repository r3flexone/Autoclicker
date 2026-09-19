"""Preis- und Kettenlogik ohne pandas, Excel oder Netz.

Warum eigenes Modul: das hier sind die Entscheidungen, an denen der ganze Lauf
haengt - an wen wird verkauft, was kostet eine Zutat, was kostet eine Kette. Sie
lagen in `analysis.py` zwischen DataFrames und Excel-Formatierung, und damit waren
sie nur pruefbar, wenn pandas installiert ist. Die CI installiert es nicht, also
lief genau der rechnende Teil in keinem Test.

Dieselbe Richtung wie beim Studio im Hauptprojekt: nicht die Ausgabe testbar
machen, sondern die Logik aus ihr heraus.
"""

from __future__ import annotations

from typing import NamedTuple

try:
    from .config import (
        AUTO_COOK_CHANCE, AUTO_COOK_SELL_RAW_REST, GOLD_ITEM_ID, GOLD_ITEM_PRICE,
        MAX_AVG_DEVIATION_RATIO, MAX_SPREAD_RATIO, MIN_BUY_ASK_VOLUME,
        MIN_SELL_BID_VOLUME, NPC_SELL_BOOST_MULTIPLIER,
        THIN_BID_HOURS, net_player_price,
    )
except ImportError:  # direkter Skriptstart
    from config import (  # type: ignore
        AUTO_COOK_CHANCE, AUTO_COOK_SELL_RAW_REST, GOLD_ITEM_ID, GOLD_ITEM_PRICE,
        MAX_AVG_DEVIATION_RATIO, MAX_SPREAD_RATIO, MIN_BUY_ASK_VOLUME,
        MIN_SELL_BID_VOLUME, NPC_SELL_BOOST_MULTIPLIER,
        THIN_BID_HOURS, net_player_price,
    )



# ---------------------------------------------------------------
# Marktzustand: verkaufen und kaufen sind zwei Fragen
# ---------------------------------------------------------------

def valid_sell_market(item: dict | None) -> bool:
    """Kann ich hier VERKAUFEN? Es zaehlen nur die Kaufgebote.

    Die Angebotsseite ist dabei voellig egal: dass niemand billig anbietet, hindert
    mich nicht daran, in ein bestehendes Gebot zu verkaufen. Frueher musste ein Item
    BEIDE Seiten erfuellen, und ausserdem 10.000 Stueck am besten Gebot - das hat
    yew_log und yew_plank auf den NPC-Preis zurueckgeworfen, obwohl im Buch darunter
    tiefe Nachfrage steht.
    """
    if not item:
        return False
    return item.get("buy", 0) > 0 and item.get("buyVol", 0) >= MIN_SELL_BID_VOLUME


def valid_buy_market(item: dict | None) -> bool:
    """Kann ich hier KAUFEN? Es zaehlen nur die Verkaufsangebote."""
    if not item:
        return False
    return item.get("sell", 0) > 0 and item.get("sellVol", 0) >= MIN_BUY_ASK_VOLUME


def wide_spread(item: dict | None) -> bool:
    """Weiche WARNUNG: Ask liegt um mehr als MAX_SPREAD_RATIO ueber Bid."""
    if not item or item.get("buy", 0) <= 0:
        return False
    return abs(item["sell"] - item["buy"]) / item["buy"] > MAX_SPREAD_RATIO


def price_anomaly(item: dict | None) -> bool:
    """Weiche WARNUNG: weicht Bid/Ask stark vom 24h-Schnitt ab?

    Alle drei Werte sind BRUTTO (so kommen sie aus der API) - hier wird nichts
    versteuert, sonst verglichen man einen Nettopreis mit einem Bruttoschnitt und
    haette bei jedem Item dieselbe kuenstliche Abweichung.
    """
    if not item:
        return False
    avg = item.get("avg", 0)
    if avg <= 0:
        return False
    return (abs(item["buy"] - avg) / avg > MAX_AVG_DEVIATION_RATIO
            or abs(item["sell"] - avg) / avg > MAX_AVG_DEVIATION_RATIO)


def thin_top_bid(item: dict | None, units_per_hour_value: float) -> bool:
    """Schluckt das beste Gebot weniger als `THIN_BID_HOURS` Stunden Produktion?

    Das ist die Frage, die `MIN_SELL_VOLUME` frueher mit einem Ausschluss beantwortet
    hat - und zwar mit einer festen Stueckzahl, die nichts damit zu tun hat, wie viel
    man ueberhaupt produziert. 10.000 Stueck sind bei 200 Stk/h zwei Tage Vorrat und
    bei 40.000 Stk/h eine Viertelstunde.

    Heute ist es eine Warnung: das Item wird trotzdem am Markt gerechnet, denn wie
    tief das Buch unter dem Top-Gebot ist, weiss der Bulk-Endpoint gar nicht.
    """
    if not item or units_per_hour_value <= 0:
        return False
    amount_value = item.get("buyVol", 0)
    if amount_value <= 0:
        return False
    return amount_value / units_per_hour_value < THIN_BID_HOURS


def is_player_shop_tradeable(item_info: dict) -> bool:
    """Darf das Item im Player Market gelistet werden? (API-Flag CanNotBeTraded)"""
    return bool(item_info.get("can_trade", True))


def npc_sell_price(item_id: int, item_info_map: dict) -> float:
    """Sofortverkauf an den NPC-Vendor (unbegrenztes Volumen), steuerfrei."""
    entry = item_info_map.get(item_id)
    if entry is None or not entry.get("can_sell_to_npc", True):
        return 0.0
    return entry.get("base_value", 0) * NPC_SELL_BOOST_MULTIPLIER


class SalesChannel(NamedTuple):
    """Wohin das Endprodukt geht - und wie sicher das ist."""
    price_value: float           # netto je Stueck, auf diesem Weg
    to_npc: bool
    player_net: float   # was der Player-Markt netto braechte (0 = kein Weg)
    npc_price: float
    reason: str             # leer, solange ueberhaupt ein Weg existiert


def effective_sell_price(item_id: int, market_map: dict, item_info_map: dict,
                         amount_value: float = 1.0) -> SalesChannel:
    """Bester Verkaufsweg: Kaufgebot im Player Shop gegen NPC-Vendor, netto gegen netto.

    `amount_value` ist die Stueckzahl, die in EINEM Angebot landet (typisch: Stueck pro
    Stunde). Sie entscheidet ueber die Marktsteuer, denn die greift erst ab 100 Gold
    Gesamtwert - ohne sie verloere ein 3-Gold-Item bei jedem Vergleich 1%, das es
    im Spiel nie zahlt.

    Verkauft wird ins GEBOT, also zaehlt auch nur die Gebotsseite (`valid_sell_market`).
    Wie tief das Buch darunter ist, beantwortet der Orderbuch-Durchlauf im Sheet
    "Begruendung"; hier waere jede Schaetzung darueber geraten.
    """
    m = market_map.get(item_id)
    info = item_info_map.get(item_id, {})
    tradeable = is_player_shop_tradeable(info)
    npc_possible = bool(info.get("can_sell_to_npc", True))

    player_net = (net_player_price(m["buy"], amount_value)
                     if (tradeable and valid_sell_market(m)) else 0.0)
    npc = npc_sell_price(item_id, item_info_map)

    if npc <= 0 and player_net <= 0:
        if not tradeable:
            market_reason = "Nicht am Player-Markt handelbar (CanNotBeTraded)"
        elif not m or m.get("buy", 0) <= 0:
            market_reason = "Kein Kaufgebot im Player Shop"
        else:
            market_reason = f"Kaufgebot ohne Menge (BuyVol < {MIN_SELL_BID_VOLUME})"
        npc_reason = ("kein NPC-Verkauf erlaubt (CanNotBeSoldToGameShop)"
                     if not npc_possible else "kein NPC-Preis (BaseValue 0)")
        return SalesChannel(0.0, False, 0.0, npc, f"{market_reason} + {npc_reason}")

    if npc > player_net:
        return SalesChannel(npc, True, player_net, npc, "")
    return SalesChannel(player_net, False, player_net, npc, "")


# ---------------------------------------------------------------
# Zutatenpreise
# ---------------------------------------------------------------

class IngredientPrice(NamedTuple):
    price_value: float
    known: bool


def ingredient_price(item_id, market_map: dict) -> IngredientPrice:
    """Was ein Stueck dieser Zutat am Markt kostet - und ob der Preis bekannt IST.

    Zwei Faelle, die frueher beide als 0 durchgingen und damit ein Rezept billiger
    aussehen liessen, als es ist:

    - **Gold ist ein Item.** Die API fuehrt Gold als ItemId 19, und Carpentry-Rezepte
      zahlen damit. Ein Markteintrag existiert dafuer natuerlich nicht - die Zeile
      fiel also unter "unbekannt" und kostete nichts. Ein Gold kostet ein Gold.
    - **Wirklich unbekannt.** Kein Markteintrag, kein Angebot, Preis 0: dann ist der
      Preis nicht null, sondern nicht bekannt. Der Aufrufer muss das Ergebnis als
      unvollstaendig kennzeichnen, statt weiterzurechnen (`bekannt=False`).
    """
    if item_id == GOLD_ITEM_ID:
        return IngredientPrice(GOLD_ITEM_PRICE, True)
    entry = market_map.get(item_id)
    if not entry:
        return IngredientPrice(0.0, False)
    price_value = entry.get("sell", 0) or 0.0
    if price_value <= 0:
        return IngredientPrice(0.0, False)
    return IngredientPrice(float(price_value), True)


class CostPicture(NamedTuple):
    """Materialkosten EINER Aktion, plus was daran unsicher ist."""
    costs_value: float
    complete: bool
    missing_ones: tuple
    market_unhealthy: bool
    anomaly_price: bool
    spread_warning_value: bool
    max_liquidity: float


def cost_per_action(costs: list, market_map: dict, actions_per_hour_value: float = 0.0,
                      item_info_map: dict | None = None) -> CostPicture:
    """Summiert die Kostenzeilen eines Rezepts und meldet, was fehlt."""
    costs_value = 0.0
    complete = True
    missing_ones: list = []
    unhealthy = anomaly = spread = False
    max_ratio = 0.0

    for c in costs:
        item_id = c.get("Item")
        amount_value = c.get("Amount", 0) or 0.0
        price_value, known = ingredient_price(item_id, market_map)
        if not known:
            complete = False
            unhealthy = True
            missing_ones.append(_ingredient_name(item_id, item_info_map))
            continue
        costs_value += price_value * amount_value
        if item_id == GOLD_ITEM_ID:
            continue          # Gold hat keinen Markt, den man bewerten koennte
        cm = market_map.get(item_id)
        if not valid_buy_market(cm):
            unhealthy = True
        if price_anomaly(cm):
            anomaly = True
        if wide_spread(cm):
            spread = True
        if cm and cm.get("sellVol", 0) > 0 and actions_per_hour_value > 0:
            max_ratio = max(max_ratio, (amount_value * actions_per_hour_value) / cm["sellVol"])

    return CostPicture(costs_value, complete, tuple(missing_ones), unhealthy, anomaly,
                      spread, max_ratio)


def _ingredient_name(item_id, item_info_map: dict | None) -> str:
    if item_info_map:
        entry = item_info_map.get(item_id)
        if entry and entry.get("name"):
            return str(entry["name"])
    return f"item_{item_id}"


# ---------------------------------------------------------------
# Ketten
# ---------------------------------------------------------------

class Chain(NamedTuple):
    """Ergebnis einer rekursiven Kettenaufloesung."""
    time_ms: float
    costs_value: float
    steps_list: list
    liquidity: float
    self_sufficient: bool
    side_yield: float       # z.B. der rohe Fischrest beim Auto-Cook
    costs_known: bool
    missing_ones: tuple


def _empty(costs_value: float = 0.0, liquidity: float = 0.0, self_sufficient: bool = False,
          costs_known: bool = True, missing_ones: tuple = ()) -> Chain:
    return Chain(0.0, costs_value, [], liquidity, self_sufficient, 0.0, costs_known, missing_ones)


def resolve_chain(item_id, market_map: dict, recipe_by_output: dict, fish_to_cooked: dict,
                  item_info_map: dict | None = None, qty_needed: float = 1.0,
                  visited: set | None = None, depth: int = 0, max_depth: int = 15) -> Chain:
    """Wie man `qty_needed` Stueck selbst herstellt, statt sie zu kaufen.

    Zwei Dinge, die diese Funktion beantwortet und die man leicht falsch macht:

    - **Ein unbekannter Zutatenpreis ist keine kostenlose Zutat.** Wer keinen Preis
      findet, setzt `costs_known=False` und nennt die Zutat, statt 0 zu addieren.
      Sonst steht ein Rezept mit unbekannter Zutat ganz oben in der Rangliste.
    - **Auto-Cook wirft den rohen Rest nicht weg.** Ein Fischzug liefert
      `AUTO_COOK_CHANCE` gekocht und den Rest roh; der rohe Teil wird ueber den
      normalen Verkaufsweg gutgeschrieben (`side_yield`).
    """
    if visited is None:
        visited = set()
    item_info_map = item_info_map or {}

    if item_id in visited or depth > max_depth:
        price_value, known = ingredient_price(item_id, market_map)
        return _empty(price_value * qty_needed, 0.0, False, known,
                     () if known else (_ingredient_name(item_id, item_info_map),))

    fish_source_id = next((raw for raw, cooked in fish_to_cooked.items() if cooked == item_id), None)
    if fish_source_id is not None and fish_source_id not in visited and AUTO_COOK_CHANCE > 0:
        return _auto_cook_chain(item_id, fish_source_id, market_map, recipe_by_output,
                                fish_to_cooked, item_info_map, qty_needed, visited,
                                depth, max_depth)

    # Gold ist eine Kostenzeile, aber kein Einkauf: es hat keinen Markt, an dem es
    # knapp werden koennte, und man "farmt" es auch nicht als Zutat. Es zaehlt voll
    # in die Kosten und laesst die Kette trotzdem autark - sonst traegt jedes
    # Carpentry-Rezept die Warnung "Zutat muss gekauft werden" fuer die Naegel, und
    # eine Warnung, die immer ansteht, warnt nicht mehr.
    if item_id == GOLD_ITEM_ID:
        price_value, _ = ingredient_price(item_id, market_map)
        return _empty(price_value * qty_needed, 0.0, self_sufficient=True)

    # Kein eigenes Recipe -> am Markt kaufen
    if item_id not in recipe_by_output:
        entry = market_map.get(item_id)
        price_value, known = ingredient_price(item_id, market_map)
        sell_vol = entry.get("sellVol", 0) if entry else 0
        ratio = (qty_needed / sell_vol) if sell_vol > 0 else 0.0
        if not valid_buy_market(entry):
            ratio = max(ratio, 999.0)   # erzwingt LiquidityWarning
        return _empty(price_value * qty_needed, ratio, False, known,
                     () if known else (_ingredient_name(item_id, item_info_map),))

    recipe = recipe_by_output[item_id]
    visited = visited | {item_id}
    actions_needed = qty_needed / recipe["item_amount"]
    time_ms = actions_needed * recipe["base_time_ms"]
    steps_list = [(recipe["name"], recipe["skill"], qty_needed, time_ms)]

    return _subchains(recipe["costs"], actions_needed, market_map, recipe_by_output,
                        fish_to_cooked, item_info_map, visited, depth, max_depth,
                        time_ms, steps_list, 0.0)


def _auto_cook_chain(item_id, fish_source_id, market_map, recipe_by_output, fish_to_cooked,
                     item_info_map, qty_needed, visited, depth, max_depth) -> Chain:
    """Fischen statt kochen - der Kochschritt findet beim Auto-Cook nie statt.

    Pro Fischzug kommen `item_amount` Stueck an, davon `AUTO_COOK_CHANCE` gekocht.
    Fuer `qty_needed` gekochte braucht es entsprechend mehr Zuege, und dabei faellt
    zwangslaeufig roher Fisch an. Der wird verkauft, nicht weggeworfen: er ist ein
    handelbares Item wie jedes andere und geht ueber denselben Weg (Gebot oder NPC).
    """
    fish_recipe = recipe_by_output[fish_source_id]
    visited2 = visited | {item_id, fish_source_id}

    cooked_per_action = fish_recipe["item_amount"] * AUTO_COOK_CHANCE
    actions_needed = qty_needed / cooked_per_action
    time_ms = actions_needed * fish_recipe["base_time_ms"]
    steps_list = [(fish_recipe["name"] + " (mit Auto-Cook)", fish_recipe["skill"],
                 qty_needed, time_ms)]

    raw_amount = actions_needed * fish_recipe["item_amount"] * (1.0 - AUTO_COOK_CHANCE)
    side_yield = 0.0
    if AUTO_COOK_SELL_RAW_REST and raw_amount > 0:
        channel = effective_sell_price(fish_source_id, market_map, item_info_map, raw_amount)
        side_yield = channel.price_value * raw_amount

    return _subchains(fish_recipe["costs"], actions_needed, market_map, recipe_by_output,
                        fish_to_cooked, item_info_map, visited2, depth, max_depth,
                        time_ms, steps_list, side_yield)


def _subchains(costs, actions_needed, market_map, recipe_by_output, fish_to_cooked,
                 item_info_map, visited, depth, max_depth, time_ms, steps_list,
                 side_yield) -> Chain:
    """Die Zutaten einer Stufe aufloesen und alles zu einer Kette zusammenfuehren."""
    costs_value, max_ratio = 0.0, 0.0
    self_sufficient = True
    costs_known = True
    missing_ones: list = []

    for c in costs:
        qty = (c.get("Amount", 0) or 0.0) * actions_needed
        part = resolve_chain(c.get("Item"), market_map, recipe_by_output, fish_to_cooked,
                             item_info_map, qty, visited, depth + 1, max_depth)
        time_ms += part.time_ms
        costs_value += part.costs_value
        side_yield += part.side_yield
        max_ratio = max(max_ratio, part.liquidity)
        self_sufficient = self_sufficient and part.self_sufficient
        costs_known = costs_known and part.costs_known
        missing_ones.extend(part.missing_ones)
        steps_list.extend(part.steps_list)

    return Chain(time_ms, costs_value, steps_list, max_ratio, self_sufficient, side_yield,
                 costs_known, tuple(dict.fromkeys(missing_ones)))
