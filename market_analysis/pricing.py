"""Preis- und Kettenlogik ohne pandas, Excel oder Netz.

Warum eigenes Modul: das hier sind die Entscheidungen, an denen der ganze Lauf
haengt - an wen wird verkauft, was kostet eine Zutat, was kostet eine Kette. Sie
lagen in `analyse.py` zwischen DataFrames und Excel-Formatierung, und damit waren
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
        MIN_MARKET_VOLUME, MIN_SELL_BID_VOLUME, NPC_SELL_BOOST_MULTIPLIER,
        THIN_BID_HOURS, net_player_price,
    )
except ImportError:  # direkter Skriptstart
    from config import (  # type: ignore
        AUTO_COOK_CHANCE, AUTO_COOK_SELL_RAW_REST, GOLD_ITEM_ID, GOLD_ITEM_PRICE,
        MAX_AVG_DEVIATION_RATIO, MAX_SPREAD_RATIO, MIN_BUY_ASK_VOLUME,
        MIN_MARKET_VOLUME, MIN_SELL_BID_VOLUME, NPC_SELL_BOOST_MULTIPLIER,
        THIN_BID_HOURS, net_player_price,
    )


LEERER_MARKT = {"buy": 0, "sell": 0, "buyVol": 0, "sellVol": 0, "avg": 0}


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


def valid_market(item: dict | None) -> bool:
    """Beidseitig echter Markt - nur noch fuer Warnungen, nicht fuer Entscheidungen."""
    if not item:
        return False
    return (item.get("buy", 0) > 0 and item.get("sell", 0) > 0
            and item.get("buyVol", 0) >= MIN_MARKET_VOLUME
            and item.get("sellVol", 0) >= MIN_MARKET_VOLUME)


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


def duennes_top_gebot(item: dict | None, stueck_pro_stunde: float) -> bool:
    """Schluckt das beste Gebot weniger als `THIN_BID_HOURS` Stunden Produktion?

    Das ist die Frage, die `MIN_SELL_VOLUME` frueher mit einem Ausschluss beantwortet
    hat - und zwar mit einer festen Stueckzahl, die nichts damit zu tun hat, wie viel
    man ueberhaupt produziert. 10.000 Stueck sind bei 200 Stk/h zwei Tage Vorrat und
    bei 40.000 Stk/h eine Viertelstunde.

    Heute ist es eine Warnung: das Item wird trotzdem am Markt gerechnet, denn wie
    tief das Buch unter dem Top-Gebot ist, weiss der Bulk-Endpoint gar nicht.
    """
    if not item or stueck_pro_stunde <= 0:
        return False
    menge = item.get("buyVol", 0)
    if menge <= 0:
        return False
    return menge / stueck_pro_stunde < THIN_BID_HOURS


def is_player_shop_tradeable(item_info: dict) -> bool:
    """Darf das Item im Player Market gelistet werden? (API-Flag CanNotBeTraded)"""
    return bool(item_info.get("can_trade", True))


def npc_sell_price(item_id: int, item_info_map: dict) -> float:
    """Sofortverkauf an den NPC-Vendor (unbegrenztes Volumen), steuerfrei."""
    entry = item_info_map.get(item_id)
    if entry is None or not entry.get("can_sell_to_npc", True):
        return 0.0
    return entry.get("base_value", 0) * NPC_SELL_BOOST_MULTIPLIER


class Verkaufsweg(NamedTuple):
    """Wohin das Endprodukt geht - und wie sicher das ist."""
    preis: float           # netto je Stueck, auf diesem Weg
    an_npc: bool
    spieler_netto: float   # was der Player-Markt netto braechte (0 = kein Weg)
    npc_preis: float
    grund: str             # leer, solange ueberhaupt ein Weg existiert


def effective_sell_price(item_id: int, market_map: dict, item_info_map: dict,
                         menge: float = 1.0) -> Verkaufsweg:
    """Bester Verkaufsweg: Kaufgebot im Player Shop gegen NPC-Vendor, netto gegen netto.

    `menge` ist die Stueckzahl, die in EINEM Angebot landet (typisch: Stueck pro
    Stunde). Sie entscheidet ueber die Marktsteuer, denn die greift erst ab 100 Gold
    Gesamtwert - ohne sie verloere ein 3-Gold-Item bei jedem Vergleich 1%, das es
    im Spiel nie zahlt.

    Verkauft wird ins GEBOT, also zaehlt auch nur die Gebotsseite (`valid_sell_market`).
    Wie tief das Buch darunter ist, beantwortet der Orderbuch-Durchlauf im Sheet
    "Begruendung"; hier waere jede Schaetzung darueber geraten.
    """
    m = market_map.get(item_id)
    info = item_info_map.get(item_id, {})
    handelbar = is_player_shop_tradeable(info)
    npc_moeglich = bool(info.get("can_sell_to_npc", True))

    spieler_netto = (net_player_price(m["buy"], menge)
                     if (handelbar and valid_sell_market(m)) else 0.0)
    npc = npc_sell_price(item_id, item_info_map)

    if npc <= 0 and spieler_netto <= 0:
        if not handelbar:
            markt_grund = "Nicht am Player-Markt handelbar (CanNotBeTraded)"
        elif not m or m.get("buy", 0) <= 0:
            markt_grund = "Kein Kaufgebot im Player Shop"
        else:
            markt_grund = f"Kaufgebot ohne Menge (BuyVol < {MIN_SELL_BID_VOLUME})"
        npc_grund = ("kein NPC-Verkauf erlaubt (CanNotBeSoldToGameShop)"
                     if not npc_moeglich else "kein NPC-Preis (BaseValue 0)")
        return Verkaufsweg(0.0, False, 0.0, npc, f"{markt_grund} + {npc_grund}")

    if npc > spieler_netto:
        return Verkaufsweg(npc, True, spieler_netto, npc, "")
    return Verkaufsweg(spieler_netto, False, spieler_netto, npc, "")


# ---------------------------------------------------------------
# Zutatenpreise
# ---------------------------------------------------------------

class Zutatenpreis(NamedTuple):
    preis: float
    bekannt: bool


def zutat_preis(item_id, market_map: dict) -> Zutatenpreis:
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
        return Zutatenpreis(GOLD_ITEM_PRICE, True)
    eintrag = market_map.get(item_id)
    if not eintrag:
        return Zutatenpreis(0.0, False)
    preis = eintrag.get("sell", 0) or 0.0
    if preis <= 0:
        return Zutatenpreis(0.0, False)
    return Zutatenpreis(float(preis), True)


class Kostenbild(NamedTuple):
    """Materialkosten EINER Aktion, plus was daran unsicher ist."""
    kosten: float
    vollstaendig: bool
    fehlende: tuple
    markt_ungesund: bool
    preisanomalie: bool
    spread_warnung: bool
    max_liquiditaet: float


def kosten_pro_aktion(costs: list, market_map: dict, aktionen_pro_stunde: float = 0.0,
                      item_info_map: dict | None = None) -> Kostenbild:
    """Summiert die Kostenzeilen eines Rezepts und meldet, was fehlt."""
    kosten = 0.0
    vollstaendig = True
    fehlende: list = []
    ungesund = anomalie = spread = False
    max_ratio = 0.0

    for c in costs:
        item_id = c.get("Item")
        menge = c.get("Amount", 0) or 0.0
        preis, bekannt = zutat_preis(item_id, market_map)
        if not bekannt:
            vollstaendig = False
            ungesund = True
            fehlende.append(_zutat_name(item_id, item_info_map))
            continue
        kosten += preis * menge
        if item_id == GOLD_ITEM_ID:
            continue          # Gold hat keinen Markt, den man bewerten koennte
        cm = market_map.get(item_id)
        if not valid_buy_market(cm):
            ungesund = True
        if price_anomaly(cm):
            anomalie = True
        if wide_spread(cm):
            spread = True
        if cm and cm.get("sellVol", 0) > 0 and aktionen_pro_stunde > 0:
            max_ratio = max(max_ratio, (menge * aktionen_pro_stunde) / cm["sellVol"])

    return Kostenbild(kosten, vollstaendig, tuple(fehlende), ungesund, anomalie,
                      spread, max_ratio)


def _zutat_name(item_id, item_info_map: dict | None) -> str:
    if item_info_map:
        eintrag = item_info_map.get(item_id)
        if eintrag and eintrag.get("name"):
            return str(eintrag["name"])
    return f"item_{item_id}"


# ---------------------------------------------------------------
# Ketten
# ---------------------------------------------------------------

class Kette(NamedTuple):
    """Ergebnis einer rekursiven Kettenaufloesung."""
    zeit_ms: float
    kosten: float
    schritte: list
    liquiditaet: float
    autark: bool
    nebenertrag: float       # z.B. der rohe Fischrest beim Auto-Cook
    kosten_bekannt: bool
    fehlende: tuple


def _leer(kosten: float = 0.0, liquiditaet: float = 0.0, autark: bool = False,
          kosten_bekannt: bool = True, fehlende: tuple = ()) -> Kette:
    return Kette(0.0, kosten, [], liquiditaet, autark, 0.0, kosten_bekannt, fehlende)


def resolve_chain(item_id, market_map: dict, recipe_by_output: dict, fish_to_cooked: dict,
                  item_info_map: dict | None = None, qty_needed: float = 1.0,
                  visited: set | None = None, depth: int = 0, max_depth: int = 15) -> Kette:
    """Wie man `qty_needed` Stueck selbst herstellt, statt sie zu kaufen.

    Zwei Dinge, die diese Funktion beantwortet und die man leicht falsch macht:

    - **Ein unbekannter Zutatenpreis ist keine kostenlose Zutat.** Wer keinen Preis
      findet, setzt `kosten_bekannt=False` und nennt die Zutat, statt 0 zu addieren.
      Sonst steht ein Rezept mit unbekannter Zutat ganz oben in der Rangliste.
    - **Auto-Cook wirft den rohen Rest nicht weg.** Ein Fischzug liefert
      `AUTO_COOK_CHANCE` gekocht und den Rest roh; der rohe Teil wird ueber den
      normalen Verkaufsweg gutgeschrieben (`nebenertrag`).
    """
    if visited is None:
        visited = set()
    item_info_map = item_info_map or {}

    if item_id in visited or depth > max_depth:
        preis, bekannt = zutat_preis(item_id, market_map)
        return _leer(preis * qty_needed, 0.0, False, bekannt,
                     () if bekannt else (_zutat_name(item_id, item_info_map),))

    fish_source_id = next((raw for raw, cooked in fish_to_cooked.items() if cooked == item_id), None)
    if fish_source_id is not None and fish_source_id not in visited and AUTO_COOK_CHANCE > 0:
        return _auto_cook_kette(item_id, fish_source_id, market_map, recipe_by_output,
                                fish_to_cooked, item_info_map, qty_needed, visited,
                                depth, max_depth)

    # Gold ist eine Kostenzeile, aber kein Einkauf: es hat keinen Markt, an dem es
    # knapp werden koennte, und man "farmt" es auch nicht als Zutat. Es zaehlt voll
    # in die Kosten und laesst die Kette trotzdem autark - sonst traegt jedes
    # Carpentry-Rezept die Warnung "Zutat muss gekauft werden" fuer die Naegel, und
    # eine Warnung, die immer ansteht, warnt nicht mehr.
    if item_id == GOLD_ITEM_ID:
        preis, _ = zutat_preis(item_id, market_map)
        return _leer(preis * qty_needed, 0.0, autark=True)

    # Kein eigenes Recipe -> am Markt kaufen
    if item_id not in recipe_by_output:
        eintrag = market_map.get(item_id)
        preis, bekannt = zutat_preis(item_id, market_map)
        sell_vol = eintrag.get("sellVol", 0) if eintrag else 0
        ratio = (qty_needed / sell_vol) if sell_vol > 0 else 0.0
        if not valid_buy_market(eintrag):
            ratio = max(ratio, 999.0)   # erzwingt LiquidityWarning
        return _leer(preis * qty_needed, ratio, False, bekannt,
                     () if bekannt else (_zutat_name(item_id, item_info_map),))

    recipe = recipe_by_output[item_id]
    visited = visited | {item_id}
    actions_needed = qty_needed / recipe["item_amount"]
    zeit_ms = actions_needed * recipe["base_time_ms"]
    schritte = [(recipe["name"], recipe["skill"], qty_needed, zeit_ms)]

    return _unterketten(recipe["costs"], actions_needed, market_map, recipe_by_output,
                        fish_to_cooked, item_info_map, visited, depth, max_depth,
                        zeit_ms, schritte, 0.0)


def _auto_cook_kette(item_id, fish_source_id, market_map, recipe_by_output, fish_to_cooked,
                     item_info_map, qty_needed, visited, depth, max_depth) -> Kette:
    """Fischen statt kochen - der Kochschritt findet beim Auto-Cook nie statt.

    Pro Fischzug kommen `item_amount` Stueck an, davon `AUTO_COOK_CHANCE` gekocht.
    Fuer `qty_needed` gekochte braucht es entsprechend mehr Zuege, und dabei faellt
    zwangslaeufig roher Fisch an. Der wird verkauft, nicht weggeworfen: er ist ein
    handelbares Item wie jedes andere und geht ueber denselben Weg (Gebot oder NPC).
    """
    fish_recipe = recipe_by_output[fish_source_id]
    visited2 = visited | {item_id, fish_source_id}

    gekocht_pro_aktion = fish_recipe["item_amount"] * AUTO_COOK_CHANCE
    actions_needed = qty_needed / gekocht_pro_aktion
    zeit_ms = actions_needed * fish_recipe["base_time_ms"]
    schritte = [(fish_recipe["name"] + " (mit Auto-Cook)", fish_recipe["skill"],
                 qty_needed, zeit_ms)]

    roh_menge = actions_needed * fish_recipe["item_amount"] * (1.0 - AUTO_COOK_CHANCE)
    nebenertrag = 0.0
    if AUTO_COOK_SELL_RAW_REST and roh_menge > 0:
        weg = effective_sell_price(fish_source_id, market_map, item_info_map, roh_menge)
        nebenertrag = weg.preis * roh_menge

    return _unterketten(fish_recipe["costs"], actions_needed, market_map, recipe_by_output,
                        fish_to_cooked, item_info_map, visited2, depth, max_depth,
                        zeit_ms, schritte, nebenertrag)


def _unterketten(costs, actions_needed, market_map, recipe_by_output, fish_to_cooked,
                 item_info_map, visited, depth, max_depth, zeit_ms, schritte,
                 nebenertrag) -> Kette:
    """Die Zutaten einer Stufe aufloesen und alles zu einer Kette zusammenfuehren."""
    kosten, max_ratio = 0.0, 0.0
    autark = True
    kosten_bekannt = True
    fehlende: list = []

    for c in costs:
        qty = (c.get("Amount", 0) or 0.0) * actions_needed
        teil = resolve_chain(c.get("Item"), market_map, recipe_by_output, fish_to_cooked,
                             item_info_map, qty, visited, depth + 1, max_depth)
        zeit_ms += teil.zeit_ms
        kosten += teil.kosten
        nebenertrag += teil.nebenertrag
        max_ratio = max(max_ratio, teil.liquiditaet)
        autark = autark and teil.autark
        kosten_bekannt = kosten_bekannt and teil.kosten_bekannt
        fehlende.extend(teil.fehlende)
        schritte.extend(teil.schritte)

    return Kette(zeit_ms, kosten, schritte, max_ratio, autark, nebenertrag,
                 kosten_bekannt, tuple(dict.fromkeys(fehlende)))
