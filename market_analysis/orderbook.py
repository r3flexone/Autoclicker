"""Reine Orderbuchrechnungen der Marktanalyse."""

try:
    from .config import (
        COMPREHENSIVE_AVG_FIELDS, COMPREHENSIVE_VOLUME_FIELD, OUTLIER_PRICE_FACTOR,
        net_player_price,
    )
except ImportError:
    from config import (  # type: ignore
        COMPREHENSIVE_AVG_FIELDS, COMPREHENSIVE_VOLUME_FIELD, OUTLIER_PRICE_FACTOR,
        net_player_price,
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


def reference_price(depth: dict | None) -> float:
    """Der gehandelte Schnitt: 1 Tag, sonst 7, sonst 30 Tage - 0 heisst keiner.

    Massstab fuer Ausreisser, weil er aus Abschluessen kommt und nicht aus dem
    Buch: ein Angebot zu 464.650 g, das niemand annimmt, bewegt ihn nicht.
    """
    if not depth:
        return 0.0
    for key in ("Avg1D", "Avg7D", "Avg30D"):
        value = depth.get(COMPREHENSIVE_AVG_FIELDS[key]) or 0
        if value > 0:
            return float(value)
    return 0.0


def plausible_price(price: float, reference: float) -> bool:
    """Liegt der Preis innerhalb `OUTLIER_PRICE_FACTOR` um den gehandelten Schnitt?

    Ohne Schnitt (kein Handel) gibt es keinen Massstab - dann zaehlt jeder Preis,
    statt ein Buch ohne Vergleich leerzuraeumen.
    """
    if reference <= 0:
        return True
    return reference / OUTLIER_PRICE_FACTOR <= price <= reference * OUTLIER_PRICE_FACTOR


def _levels(depth: dict | None, field: str, reference: float | None) -> list:
    """``(Preis, Menge)`` einer Buchseite, ohne Ausreisser.

    Gefiltert wird HIER und nicht beim Leser: Verkauf durchs Buch, Geduld,
    Chart und Historie bekommen dieselben Stufen. Vorher zeichnete der Chart
    das Oak-Angebot zu 464.650 g als 1,56 Mrd. Gold/h, und alle anderen Linien
    lagen auf der Nulllinie.
    """
    if not depth:
        return []
    if reference is None:
        reference = reference_price(depth)
    return [(entry["key"], float(entry["value"]))
            for entry in depth.get(field, [])
            if entry.get("key") and entry.get("value")
            and plausible_price(entry["key"], reference)]


def buy_levels_from_depth(depth: dict | None, reference: float | None = None) -> list:
    """Kaufgebote als ``(Preis, Menge)`` - Massstab ist der Schnitt des Buchs selbst."""
    return _levels(depth, "highestBuyPricesWithVolume", reference)


def sell_levels_from_depth(depth: dict | None, reference: float | None = None) -> list:
    """Verkaufsangebote als ``(Preis, Menge)``."""
    return _levels(depth, "lowestSellPricesWithVolume", reference)


def _flattering_top(entry: dict) -> tuple[bool, bool]:
    """``(Gebot zu hoch, Angebot zu billig)`` gegen den gehandelten Schnitt.

    Nur diese Richtung: ein Bestpreis-Ausreisser, der eine Zahl SCHOENT. Ein Gebot
    weit unter dem Schnitt ist ein echter, schlechter Preis - man kann jetzt dazu
    verkaufen, und schlechter als die Wahrheit macht es nichts. Beide Richtungen zu
    verwerfen war der erste Wurf: bronze_bar verlor sein Gebot von 25 g (Schnitt
    262 g) und stand beim NPC-Preis von 13,86 g; von 36 so verworfenen Bestpreisen
    war kein einziger einer, der etwas haette schoenen koennen.
    """
    avg = entry.get("avg", 0) or 0
    if avg <= 0:
        return False, False
    return (entry.get("buy", 0) > avg * OUTLIER_PRICE_FACTOR,
            0 < entry.get("sell", 0) < avg / OUTLIER_PRICE_FACTOR)


def implausible_top(entry: dict | None) -> bool:
    """Schoent das beste Gebot oder Angebot des Bulk-Endpoints die Rechnung?

    Der Bulk-Endpoint kennt nur die oberste Stufe. Ist sie ein Ausreisser, traegt
    ein einziges Stueck die ganze Rechnung: ein Gebot zu 464.650 g fuer EINEN
    Oak-Stamm stuende als Verkaufspreis fuer eine ganze Stunde Produktion da
    (1,56 Mrd. Gold/h), ein Angebot zu 1 g machte eine Zutat fast kostenlos.
    """
    return bool(entry) and any(_flattering_top(entry))


def corrected_top(entry: dict, depth: dict | None) -> dict:
    """Der Eintrag mit der naechsten ECHTEN Stufe statt des Ausreissers.

    Massstab ist derselbe Schnitt, an dem der Ausreisser erkannt wurde. Gibt das
    Buch keine plausible Stufe her (oder fehlt es), faellt die Seite weg (0): ein
    Item ohne echtes Gebot geht an den NPC, eine Zutat ohne echtes Angebot hat
    keinen bekannten Preis - beides sagt die Rechnung dann selbst.
    """
    out = dict(entry)
    avg = entry.get("avg", 0) or 0
    bid_too_high, ask_too_low = _flattering_top(entry)
    if bid_too_high:
        bids = buy_levels_from_depth(depth, avg)
        out["buy"], out["buyVol"] = max(bids) if bids else (0, 0)
    if ask_too_low:
        asks = sell_levels_from_depth(depth, avg)
        out["sell"], out["sellVol"] = min(asks) if asks else (0, 0)
    return out


def patience_analysis(depth: dict | None, top_bid: float, units_per_hour: float,
                      cost_per_unit: float) -> dict:
    """Berechnet Preis, Ertrag und Wartezeit eines eigenen Angebots."""
    empty = {"price_value": None, "revenue_value": None, "gold_h": None, "markup": None,
             "waiting_h": None, "offers_in_book": None}
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
        "price_value": price,
        "revenue_value": revenue,
        "gold_h": units_per_hour * (revenue - cost_per_unit),
        "markup": revenue / net_bid - 1.0 if net_bid > 0 else None,
        "waiting_h": waiting,
        "offers_in_book": sum(amount for _, amount in offers),
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
