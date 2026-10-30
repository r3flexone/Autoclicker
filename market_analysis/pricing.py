"""Preis- und Kettenlogik ohne pandas, Excel oder Netz.

Warum eigenes Modul: das hier sind die Entscheidungen, an denen der ganze Lauf
haengt - an wen wird verkauft, was kostet eine Zutat, was kostet eine Kette. Sie
lagen in `analysis.py` zwischen DataFrames und Excel-Formatierung, und damit waren
sie nur pruefbar, wenn pandas installiert ist. Die CI installiert es nicht, also
lief genau der rechnende Teil in keinem Test.

Dieselbe Richtung wie beim Studio im Hauptprojekt: nicht die Ausgabe testbar
machen, sondern die Logik aus ihr heraus. Dazu gehoert die Marktwert-Datei fuer
den Autoclicker (`export_market_values`): sie braucht nur `sale_values()` und die
Standardbibliothek, lag aber lange in `analysis.py` und war deshalb nur mit pandas
pruefbar.
"""

from __future__ import annotations

import json
import os
from typing import NamedTuple

try:
    from .config import (
        AUTO_COOK_CHANCE, AUTO_COOK_SELL_REST, GOLD_ITEM_ID, GOLD_ITEM_PRICE,
        MAX_AVG_DEVIATION_RATIO, MAX_SPREAD_RATIO, MIN_BUY_ASK_VOLUME,
        MIN_SELL_BID_VOLUME, NPC_SELL_BOOST_MULTIPLIER, SKILL_RELIABILITY,
        THIN_BID_HOURS, net_player_price,
    )
except ImportError:  # direkter Skriptstart
    from config import (  # type: ignore
        AUTO_COOK_CHANCE, AUTO_COOK_SELL_REST, GOLD_ITEM_ID, GOLD_ITEM_PRICE,
        MAX_AVG_DEVIATION_RATIO, MAX_SPREAD_RATIO, MIN_BUY_ASK_VOLUME,
        MIN_SELL_BID_VOLUME, NPC_SELL_BOOST_MULTIPLIER, SKILL_RELIABILITY,
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


def thin_top_bid(item: dict | None, units_per_hour: float) -> bool:
    """Schluckt das beste Gebot weniger als `THIN_BID_HOURS` Stunden Produktion?

    Das ist die Frage, die `MIN_SELL_VOLUME` frueher mit einem Ausschluss beantwortet
    hat - und zwar mit einer festen Stueckzahl, die nichts damit zu tun hat, wie viel
    man ueberhaupt produziert. 10.000 Stueck sind bei 200 Stk/h zwei Tage Vorrat und
    bei 40.000 Stk/h eine Viertelstunde.

    Heute ist es eine Warnung: das Item wird trotzdem am Markt gerechnet, denn wie
    tief das Buch unter dem Top-Gebot ist, weiss der Bulk-Endpoint gar nicht.
    """
    if not item or units_per_hour <= 0:
        return False
    amount = item.get("buyVol", 0)
    if amount <= 0:
        return False
    return amount / units_per_hour < THIN_BID_HOURS


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
    price: float            # netto je Stueck, auf diesem Weg
    to_npc: bool
    npc_price: float
    reason: str             # leer, solange ueberhaupt ein Weg existiert


def effective_sell_price(item_id: int, market_map: dict, item_info_map: dict,
                         amount: float = 1.0) -> SalesChannel:
    """Bester Verkaufsweg: Kaufgebot im Player Shop gegen NPC-Vendor, netto gegen netto.

    `amount` ist die Stueckzahl, die in EINEM Angebot landet (typisch: Stueck pro
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

    player_net = (net_player_price(m["buy"], amount)
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
        return SalesChannel(0.0, False, npc, f"{market_reason} + {npc_reason}")

    if npc > player_net:
        return SalesChannel(npc, True, npc, "")
    return SalesChannel(player_net, False, npc, "")


def sale_values(market_map: dict, item_info_map: dict) -> dict:
    """Item-Name -> was EIN Stueck beim Verkauf bringt: netto, ueber den besseren Weg.

    Das ist die Marktwert-Tabelle fuer den Autoclicker. Der sortiert gefundene Items
    danach, und dort zaehlt, was ein Item wert ist. Hier stand die Marge aus den
    Rohdaten - was ein Rezept abwirft, wenn man seine Zutaten kauft: titanium_platebody
    stand bei -2.430, obwohl es fuer rund 18.000 weggeht, und 105 von 194 Eintraegen
    waren negativ, die wertvollsten Items waeren also zuletzt geklickt worden. Dazu
    waren die Schluessel Rezeptnamen (`oak`) statt Item-Namen (`oak_log`).

    Jedes Item mit Preis, nicht nur Rezept-Ergebnisse - gefunden wird auch Beute.
    Ein Stueck heisst: Steuer erst ab 100 g Stueckpreis (`net_player_price`).
    """
    values: dict[str, float] = {}
    for item_id, info in item_info_map.items():
        name = str(info.get("name") or "").strip()
        price = effective_sell_price(item_id, market_map, item_info_map).price
        if name and price > values.get(name, 0.0):
            values[name] = round(price, 2)
    return values


def export_market_values(market_map: dict, item_info_map: dict, path: str) -> int:
    """Schreibt eine schlanke Item-Name -> Verkaufswert-Tabelle als JSON.

    Der Autoclicker kann seine Item-Klicks danach sortieren statt nach einer von
    Hand getippten Prioritaetszahl — ohne dass eine Seite die andere importiert.
    Was darin steht und warum es nicht mehr die Marge aus den Rohdaten ist, sagt
    `sale_values()`.

    Absichtlich nur Name -> Zahl: alles Weitere waere fuer die Klick-Reihenfolge
    bedeutungslos, und eine schmale Datei kann nicht veralten wie eine breite.
    Gibt die Anzahl geschriebener Eintraege zurueck; ohne einen einzigen Wert wird
    nichts geschrieben (eine vorhandene Datei bleibt dann, wie sie ist).
    """
    values = sale_values(market_map, item_info_map)
    if not values:
        return 0
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(values, f, ensure_ascii=False, indent=1, sort_keys=True)
    return len(values)


# ---------------------------------------------------------------
# Zutatenpreise
# ---------------------------------------------------------------

class IngredientPrice(NamedTuple):
    price: float
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
      unvollstaendig kennzeichnen, statt weiterzurechnen (`known=False`).
    """
    if item_id == GOLD_ITEM_ID:
        return IngredientPrice(GOLD_ITEM_PRICE, True)
    entry = market_map.get(item_id)
    if not entry:
        return IngredientPrice(0.0, False)
    price = entry.get("sell", 0) or 0.0
    if price <= 0:
        return IngredientPrice(0.0, False)
    return IngredientPrice(float(price), True)


class CostPicture(NamedTuple):
    """Materialkosten EINER Aktion, plus was daran unsicher ist."""
    costs: float
    complete: bool
    missing_ones: tuple
    market_unhealthy: bool
    anomaly_price: bool
    spread_warning: bool
    max_liquidity: float


def cost_per_action(costs: list, market_map: dict, actions_per_hour: float = 0.0,
                      item_info_map: dict | None = None) -> CostPicture:
    """Summiert die Kostenzeilen eines Rezepts und meldet, was fehlt."""
    total = 0.0
    complete = True
    missing_ones: list = []
    unhealthy = anomaly = spread = False
    max_ratio = 0.0

    for c in costs:
        item_id = c.get("Item")
        amount = c.get("Amount", 0) or 0.0
        price, known = ingredient_price(item_id, market_map)
        if not known:
            complete = False
            unhealthy = True
            missing_ones.append(_ingredient_name(item_id, item_info_map))
            continue
        total += price * amount
        if item_id == GOLD_ITEM_ID:
            continue          # Gold hat keinen Markt, den man bewerten koennte
        cm = market_map.get(item_id)
        if not valid_buy_market(cm):
            unhealthy = True
        if price_anomaly(cm):
            anomaly = True
        if wide_spread(cm):
            spread = True
        if cm and cm.get("sellVol", 0) > 0 and actions_per_hour > 0:
            max_ratio = max(max_ratio, (amount * actions_per_hour) / cm["sellVol"])

    return CostPicture(total, complete, tuple(missing_ones), unhealthy, anomaly,
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
    costs: float
    steps_list: list
    liquidity: float
    self_sufficient: bool
    side_yield: float       # z.B. der rohe Fischrest beim Auto-Cook
    costs_known: bool
    missing_ones: tuple
    # Je Nebenprodukt ``(item_id, Stueck je Stueck Endprodukt, NPC-Preis)`` - damit
    # die Begruendung auch den Nebenertrag durchs Orderbuch verkaufen kann statt ihn
    # zum Papier-Wert stehen zu lassen.
    side_items: tuple = ()


def _empty(costs: float = 0.0, liquidity: float = 0.0, self_sufficient: bool = False,
          costs_known: bool = True, missing_ones: tuple = ()) -> Chain:
    return Chain(0.0, costs, [], liquidity, self_sufficient, 0.0, costs_known, missing_ones)


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
        price, known = ingredient_price(item_id, market_map)
        return _empty(price * qty_needed, 0.0, False, known,
                     () if known else (_ingredient_name(item_id, item_info_map),))

    fish_source_id = next((raw for raw, cooked in fish_to_cooked.items() if cooked == item_id), None)
    if fish_source_id is not None and fish_source_id not in visited and AUTO_COOK_CHANCE > 0:
        return _fishing_with_auto_cook(item_id, fish_source_id, item_id, market_map,
                                       recipe_by_output, fish_to_cooked, item_info_map,
                                       qty_needed, visited, depth, max_depth)

    # Roher Fisch ist derselbe Fischzug, nur andersherum gefragt.
    cooked_id = fish_to_cooked.get(item_id)
    if cooked_id is not None and cooked_id not in visited and AUTO_COOK_CHANCE > 0:
        if AUTO_COOK_CHANCE < 1.0:
            return _fishing_with_auto_cook(item_id, item_id, cooked_id, market_map,
                                           recipe_by_output, fish_to_cooked, item_info_map,
                                           qty_needed, visited, depth, max_depth)
        # Kocht Auto-Cook den ganzen Fang, kommt nichts roh an - dann wird gekauft.
        return _bought(item_id, market_map, item_info_map, qty_needed)

    # Gold ist eine Kostenzeile, aber kein Einkauf: es hat keinen Markt, an dem es
    # knapp werden koennte, und man "farmt" es auch nicht als Zutat. Es zaehlt voll
    # in die Kosten und laesst die Kette trotzdem autark - sonst traegt jedes
    # Carpentry-Rezept die Warnung "Zutat muss gekauft werden" fuer die Naegel, und
    # eine Warnung, die immer ansteht, warnt nicht mehr.
    if item_id == GOLD_ITEM_ID:
        price, _ = ingredient_price(item_id, market_map)
        return _empty(price * qty_needed, 0.0, self_sufficient=True)

    if item_id not in recipe_by_output:
        return _bought(item_id, market_map, item_info_map, qty_needed)

    recipe = recipe_by_output[item_id]
    visited = visited | {item_id}
    actions_needed = qty_needed / recipe["item_amount"]
    time_ms = actions_needed * recipe["base_time_ms"]
    steps_list = [(recipe["name"], recipe["skill"], qty_needed, time_ms)]

    return _subchains(recipe["costs"], actions_needed, market_map, recipe_by_output,
                        fish_to_cooked, item_info_map, visited, depth, max_depth,
                        time_ms, steps_list, 0.0, ())


def _bought(item_id, market_map: dict, item_info_map: dict, qty_needed: float) -> Chain:
    """Am Markt gekauft statt hergestellt - zum Ask, mit Liquiditaet und Grund."""
    entry = market_map.get(item_id)
    price, known = ingredient_price(item_id, market_map)
    sell_vol = entry.get("sellVol", 0) if entry else 0
    ratio = (qty_needed / sell_vol) if sell_vol > 0 else 0.0
    if not valid_buy_market(entry):
        ratio = max(ratio, 999.0)   # erzwingt LiquidityWarning
    return _empty(price * qty_needed, ratio, False, known,
                 () if known else (_ingredient_name(item_id, item_info_map),))


def _fishing_with_auto_cook(item_id, fish_source_id, cooked_id, market_map, recipe_by_output,
                            fish_to_cooked, item_info_map, qty_needed, visited, depth,
                            max_depth) -> Chain:
    """Ein Fischzug mit Auto-Cook liefert beides: `AUTO_COOK_CHANCE` gekocht, den Rest roh.

    Gefragt ist eins davon (`item_id`), das andere faellt zwangslaeufig mit an und
    wird verkauft (`side_yield`), nicht weggeworfen - ueber denselben Weg wie jedes
    Item (Gebot oder NPC). Der Kochschritt findet nie statt, es wird nur gefischt.

    Frueher kannte nur der GEKOCHTE Fisch diesen Weg. Roher Fisch rechnete, als kaeme
    der ganze Fang roh an: raw_piranha stand bei 61.564 Gold/h, obwohl derselbe
    Fischzug real 52.256 bringt, und sea_serpent_scale bekam je Zug doppelt so viele
    rohe Seeschlangen, wie es gibt.
    """
    fish_recipe = recipe_by_output[fish_source_id]
    wants_cooked = item_id == cooked_id
    share = AUTO_COOK_CHANCE if wants_cooked else 1.0 - AUTO_COOK_CHANCE
    other_id = fish_source_id if wants_cooked else cooked_id
    per_action = fish_recipe["item_amount"]

    actions_needed = qty_needed / (per_action * share)
    time_ms = actions_needed * fish_recipe["base_time_ms"]
    steps_list = [(fish_recipe["name"] + " (mit Auto-Cook)", fish_recipe["skill"],
                 qty_needed, time_ms)]

    other_amount = actions_needed * per_action * (1.0 - share)
    side_yield, side_items = 0.0, ()
    if AUTO_COOK_SELL_REST and other_amount > 0:
        # Die Steuergrenze haengt an der Menge EINES Angebots, und angeboten wird
        # eine Stunde Fischen - nicht der Rest, der auf ein einzelnes Stueck faellt.
        # Mit dem Stueck-Rest (1 roher je gekochtem) galt billiger Fisch unter 100 g
        # als steuerfrei.
        other_per_hour = 3_600_000.0 / fish_recipe["base_time_ms"] * per_action * (1.0 - share)
        channel = effective_sell_price(other_id, market_map, item_info_map, other_per_hour)
        side_yield = channel.price * other_amount
        side_items = ((other_id, other_amount, channel.npc_price),)

    return _subchains(fish_recipe["costs"], actions_needed, market_map, recipe_by_output,
                        fish_to_cooked, item_info_map, visited | {fish_source_id, cooked_id},
                        depth, max_depth, time_ms, steps_list, side_yield, side_items)


def _subchains(costs, actions_needed, market_map, recipe_by_output, fish_to_cooked,
                 item_info_map, visited, depth, max_depth, time_ms, steps_list,
                 side_yield, side_items) -> Chain:
    """Die Zutaten einer Stufe aufloesen und alles zu einer Kette zusammenfuehren.

    Nebenprodukte werden je Item zusammengezaehlt: power_pizza fischt zander UND
    pufferfish, eine Kette mit derselben Zutat zweimal faengt denselben Fisch doppelt."""
    sides = {item: [qty, npc] for item, qty, npc in side_items}
    total, max_ratio = 0.0, 0.0
    self_sufficient = True
    costs_known = True
    missing_ones: list = []

    for c in costs:
        qty = (c.get("Amount", 0) or 0.0) * actions_needed
        part = resolve_chain(c.get("Item"), market_map, recipe_by_output, fish_to_cooked,
                             item_info_map, qty, visited, depth + 1, max_depth)
        time_ms += part.time_ms
        total += part.costs
        side_yield += part.side_yield
        max_ratio = max(max_ratio, part.liquidity)
        self_sufficient = self_sufficient and part.self_sufficient
        costs_known = costs_known and part.costs_known
        missing_ones.extend(part.missing_ones)
        steps_list.extend(part.steps_list)
        for item, qty, npc in part.side_items:
            sides.setdefault(item, [0.0, npc])[0] += qty

    return Chain(time_ms, total, steps_list, max_ratio, self_sufficient, side_yield,
                 costs_known, tuple(dict.fromkeys(missing_ones)),
                 tuple((item, qty, npc) for item, (qty, npc) in sides.items()))


# ---------------------------------------------------------------
# Verlaesslichkeit: wie sehr man sich auf ein Gold/h verlassen kann
# ---------------------------------------------------------------

def purchase_buffer(revenue_h: float, cost_h: float) -> float:
    """Um wie viel der Erloes fallen darf, bevor die Kette nichts mehr bringt.

    Dieselbe Zahl ist der Anteil des Erloeses, der nach dem Einkauf bleibt - also
    das, was das eigene Farmen beitraegt. Eine Kette ohne Zukauf hat 1,0: ihr
    Ertrag faellt mit dem Preis, wird aber nie negativ. Ohne Erloes 0.
    """
    if revenue_h <= 0:
        return 0.0
    return max(0.0, min(1.0, 1.0 - cost_h / revenue_h))


def chain_reliability(chain_skills: str, self_sufficient: bool = True,
                      revenue_h: float = 0.0, cost_h: float = 0.0) -> tuple[float, str]:
    """Faktor fuer die Rangfolge (1,0 = verlaesslich) samt Begruendung.

    Zwei Gruende, kleiner zu werden:

    - **Nachschub nur zufaellig** (`SKILL_RELIABILITY`, z.B. Farming-Samen).
    - **Zukauf.** Muss eine Zutat gekauft werden, haengt der Ertrag an zwei
      Maerkten, und der Faktor ist der `purchase_buffer()`. Gemeldet am
      11.10.2026: otherworldly_bar stand mit 1,17 Mio. Gold/h auf Platz 1, mehr als
      dreimal so viel wie Platz 2 - fuer rund 114 Mio. Zukauf je Barren, 30 Stunden
      je Stueck und neun Gebote im ganzen Buch. 77 % des Erloeses gingen an den
      Einkauf; das Gebot war zwischen zwei Laeufen um 11 % gefallen, und eine Woche
      spaeter lag das beste bei 20 Mio. - die Kette rechnete -2,9 Mio. Gold/h.

    Es zaehlt der schwaechste Grund (min, nicht Produkt): zwei unplanbare Glieder
    machen eine Kette nicht doppelt so unplanbar.
    """
    factor, reasons = 1.0, []
    for part in str(chain_skills or "").split("->"):
        skill = part.strip()
        entry = SKILL_RELIABILITY.get(skill)
        if entry and entry[0] < 1.0:
            factor = min(factor, entry[0])
            reasons.append(f"{skill}: {entry[1]}")
    if not self_sufficient:
        buffer = purchase_buffer(revenue_h, cost_h)
        if buffer < 1.0:
            factor = min(factor, buffer)
            reasons.append(f"Zukauf: {1.0 - buffer:.0%} des Erlöses gehen an den Einkauf")
    return factor, "; ".join(reasons)


def weighted_gold(gold_h: float, factor: float) -> float:
    """Gold/h fuer die Rangfolge. Abwerten heisst kleiner machen - ein Verlust wird
    durch einen Faktor unter 1 nicht kleiner, sonst stuende eine verlustreiche
    Kette mit Zukauf (Faktor 0) ueber jeder anderen verlustreichen."""
    return gold_h * factor if gold_h > 0 else gold_h
