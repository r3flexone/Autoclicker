"""Reine Orderbuchrechnungen der Marktanalyse."""

try:
    from .config import (
        COMPREHENSIVE_AVG_FIELDS, COMPREHENSIVE_VOLUME_FIELD, net_player_price,
    )
except ImportError:
    from config import (  # type: ignore
        COMPREHENSIVE_AVG_FIELDS, COMPREHENSIVE_VOLUME_FIELD, net_player_price,
    )


def walk_orderbook(levels: list, qty: float) -> tuple[float, float, float]:
    """Verkauft ``qty`` Stück ins Buch, beste Gebote zuerst."""
    remaining, revenue, last_price = max(0.0, qty), 0.0, 0.0
    for price, amount in sorted(levels, key=lambda level: level[0], reverse=True):
        if remaining <= 0:
            break
        taken = min(remaining, max(0.0, amount))
        revenue += taken * price
        if taken:
            last_price = price
        remaining -= taken
    return revenue, max(0.0, qty) - remaining, last_price


def buy_levels_from_depth(depth: dict) -> list:
    """Kaufgebote als ``(Preis, Menge)``."""
    return [(entry["key"], float(entry["value"]))
            for entry in depth.get("highestBuyPricesWithVolume", [])
            if entry.get("key") and entry.get("value")]


def sell_levels_from_depth(depth: dict) -> list:
    """Verkaufsangebote als ``(Preis, Menge)``."""
    return [(entry["key"], float(entry["value"]))
            for entry in depth.get("lowestSellPricesWithVolume", [])
            if entry.get("key") and entry.get("value")]


def patience_analysis(depth: dict | None, top_bid: float, units_per_hour: float,
                      cost_per_unit: float) -> dict:
    """Berechnet Preis, Ertrag und Wartezeit eines eigenen Angebots."""
    empty = {"preis": None, "erloes": None, "gold_h": None, "aufschlag": None,
             "wartezeit_h": None, "angebot_im_buch": None}
    if not depth or units_per_hour <= 0:
        return empty

    offers = sell_levels_from_depth(depth)
    if offers:
        price = max(min(p for p, _ in offers) - 1, top_bid)
    elif top_bid > 0:
        price = depth.get(COMPREHENSIVE_AVG_FIELDS["Avg30D"]) or top_bid
    else:
        return empty
    if price <= 0:
        return empty

    # Menge mitgeben: die Marktsteuer greift erst ab 100 Gold Gesamtwert, und
    # angeboten wird eine Stunde Produktion, nicht ein Stueck.
    revenue = net_player_price(price, units_per_hour)
    daily_volume = depth.get(COMPREHENSIVE_VOLUME_FIELD) or 0
    waiting = units_per_hour / daily_volume * 24.0 if daily_volume > 0 else None
    net_bid = net_player_price(top_bid, units_per_hour) if top_bid > 0 else 0.0
    return {
        "preis": price,
        "erloes": revenue,
        "gold_h": units_per_hour * (revenue - cost_per_unit),
        "aufschlag": revenue / net_bid - 1.0 if net_bid > 0 else None,
        "wartezeit_h": waiting,
        "angebot_im_buch": sum(amount for _, amount in offers),
    }


def price_position(reference: float, depth: dict | None) -> tuple[float | None, str]:
    """Position gegen 30-Tage-Schnitt und vorsichtiger 1/7/30-Tage-Trend.

    `reference` muss BRUTTO sein - die Durchschnitte aus der API kennen keine
    Marktsteuer. Wer einen Nettoerlös hineingibt, bekommt bei jedem Item dieselbe
    kuenstliche Abweichung von einem Prozent nach unten und haelt einen Messfehler
    fuer eine Marktlage.
    """
    if not depth or reference <= 0:
        return None, ""
    avg30 = depth.get(COMPREHENSIVE_AVG_FIELDS["Avg30D"]) or 0
    avg7 = depth.get(COMPREHENSIVE_AVG_FIELDS["Avg7D"]) or 0
    avg1 = depth.get(COMPREHENSIVE_AVG_FIELDS["Avg1D"]) or 0
    position = reference / avg30 - 1.0 if avg30 > 0 else None
    trend = ""
    if avg1 > 0 and avg7 > 0 and avg30 > 0:
        if avg1 > avg7 > avg30:
            trend = "steigend"
        elif avg1 < avg7 < avg30:
            trend = "fallend"
        else:
            trend = "seitwaerts"
    return position, trend
