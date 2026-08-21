"""Einzelitem-Nachrechnung fuer analyse.py

Schluesselt fuer einzelne Rezepte den Rechenweg auf: Rohwerte aus der API ->
jeder angewendete Boost -> Endergebnis, samt der Zahlen, die man ingame
gegenpruefen kann. Fuer "warum steht bei Item X dieses Gold/h?".

Schwerpunkt ist die KETTE (alles selbst gefarmt): Abschnitt 5 zeigt Zeitanteil
und Gold/h, Abschnitt 6 die Ingame-Checkliste fuer jeden Schritt darin. Der
Einzelschritt (3/4, Zutaten zum Ask-Preis) bleibt als Vergleich stehen.

    python market_analysis/verify.py                  # Standard-Auswahl
    python market_analysis/verify.py oak titanium_bar # beliebige Rezeptnamen
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Die Konfigurationswerte kommen aus `config`, nicht aus `analyse`: sie standen
# hier lange als `ma.XP_BOOST_TOTAL` & Co. und existierten dort gar nicht -
# `analyse` importiert sie einzeln und reicht sie nicht weiter. Das Skript brach
# damit bei der ersten Ausgabe ab.
try:
    from . import analyse as ma  # noqa: E402
    from . import config as conf  # noqa: E402
    from .recipes import normalize_recipe, skill_cfg  # noqa: E402
except ImportError:
    import analyse as ma  # type: ignore  # noqa: E402
    import config as conf  # type: ignore  # noqa: E402
    from recipes import normalize_recipe, skill_cfg  # type: ignore  # noqa: E402

DEFAULT_ITEMS = ["oak", "titanium_bar", "tuna", "cooked_tuna"]

SEP = "=" * 78


def find_recipes(tasks: dict, names: list[str]) -> list[tuple[str, dict]]:
    """Rohe (ungerechnete) Rezepte zu den gesuchten Namen, aus allen Skills."""
    wanted = {n.lower() for n in names}
    found = []
    for skill_name, blocks in tasks.items():
        for block in blocks or []:
            for raw in block.get("Items", []) or []:
                if str(raw.get("Name", "")).lower() in wanted:
                    found.append((skill_name, raw))
    return found


def price_line(item_id: int, market_map: dict, item_info_map: dict) -> str:
    name = item_info_map.get(item_id, {}).get("name", f"item_{item_id}")
    # Gold hat keinen Markteintrag und braucht auch keinen - "KEIN Markteintrag"
    # las sich hier wie ein Datenfehler, obwohl die Zeile voll mitgerechnet wird.
    if item_id == conf.GOLD_ITEM_ID:
        return f"{name} (ID {item_id}): direktes Gold, {conf.GOLD_ITEM_PRICE:g} je Stueck"
    m = market_map.get(item_id)
    if m is None:
        return f"{name} (ID {item_id}): KEIN Markteintrag - Preis unbekannt, nicht 0"
    return (f"{name} (ID {item_id}): Bid {m['buy']:,} / Ask {m['sell']:,}  "
            f"(BuyVol {m['buyVol']:,}, SellVol {m['sellVol']:,}, Ø24h {m['avg']:,})")


def describe(skill_name: str, raw: dict, market_map: dict, item_info_map: dict,
             excluded_cost_items: frozenset, recipe_by_output: dict, fish_to_cooked: dict,
             tasks: dict):
    cfg = skill_cfg(skill_name)
    name = raw.get("Name")
    item_id = raw.get("ItemReward")

    print(f"\n{SEP}\n{name}   (Skill: {skill_name}, Level {raw.get('LevelRequirement')})\n{SEP}")

    # --- 1. Rohwerte -------------------------------------------------------
    base_time_ms = raw.get("BaseTime", 0.0)
    base_amount = raw.get("ItemAmount", 0)
    base_xp = raw.get("ExpReward", 0.0)
    print("1) ROHWERTE AUS DER API")
    print(f"     BaseTime      {base_time_ms:,.0f} ms  = {base_time_ms / 1000:.3f} s")
    print(f"     ItemAmount    {base_amount}")
    print(f"     ExpReward     {base_xp:,.1f}")
    print(f"     Ausgabe-Item  {price_line(item_id, market_map, item_info_map)}")
    for c in raw.get("Costs") or []:
        print(f"     Zutat         {c.get('Amount')}x {price_line(c.get('Item'), market_map, item_info_map)}")

    # --- 2. Boosts ---------------------------------------------------------
    clan = conf.CLAN_GATHERERS_SPEED_BOOST if cfg.is_gathering else 0.0
    speed_mult = (1.0 - clan) * (1.0 - cfg.equipment_speed_boost)
    speed_add = max(0.0, 1.0 - clan - cfg.equipment_speed_boost)
    yield_factor = cfg.yield_multiplier * (1.0 + conf.GLOVES_DOUBLE_CHANCE if cfg.gloves_owned else 1.0)
    # Muss dieselbe Formel sein wie in normalize_recipe — dieses Skript ist die
    # Gegenprobe zur Analyse, eine abweichende Rechnung waere hier schlimmer als keine.
    extra_yield_xp = (1.0 + conf.EXTRA_YIELD_XP_SHARE * (cfg.yield_multiplier - 1.0)
                      if cfg.extra_yield_xp and cfg.yield_multiplier > 1.0 else 1.0)
    xp_factor = extra_yield_xp * (1.0 + conf.XP_BOOST_TOTAL) * (1.0 + conf.DAILY_XP_BOOST)

    print("\n2) ANGEWENDETE BOOSTS (aus SKILLS)")
    print(f"     Equipment-Speed   {cfg.equipment_speed_boost:.0%}"
          f"{f' + Clan-Gatherers {clan:.0%}' if clan else '  (kein Gatherers-Perk)'}")
    print(f"     Zeit-Faktor       multiplikativ {speed_mult:.4f}   |   additiv {speed_add:.4f}")
    print(f"     Yield-Faktor      {yield_factor:.3f}"
          f"   (Upgrade {cfg.yield_multiplier:.2f}"
          f"{f' x Handschuhe {1 + conf.GLOVES_DOUBLE_CHANCE:.2f}' if cfg.gloves_owned else ', keine Handschuhe'})")
    print(f"     XP-Faktor         {xp_factor:.3f}"
          + (f"   (davon {extra_yield_xp:.3f} aus 'Better fisherman/lumberjack')"
             if extra_yield_xp != 1.0 else ""))
    if cfg.cost_multiplier != 1.0:
        print(f"     Kosten-Faktor     {cfg.cost_multiplier:.2f} "
              "(Potion of Trickery / Seed Storage)")

    # --- 3. Ergebnis pro Case ---------------------------------------------
    results = {}
    for case in ("best", "worst"):
        r = normalize_recipe(skill_name, raw, case=case,
                             excluded_cost_items=excluded_cost_items)
        if r is None:
            print("\n   !! Rezept wird vom Script AUSSORTIERT (Disabled / raids_ / keine Zeit / kein Reward)")
            return
        actions_per_hour = 3_600_000.0 / r["base_time_ms"]
        items_per_hour = actions_per_hour * r["item_amount"]
        # Dieselbe Kostenrechnung wie im Lauf: Gold (Item 19) zaehlt mit, ein
        # unbekannter Preis wird gemeldet statt als 0 durchgereicht.
        kosten = ma.kosten_pro_aktion(r["costs"], market_map, actions_per_hour, item_info_map)
        weg = ma.effective_sell_price(r["item_id"], market_map, item_info_map, items_per_hour)
        results[case] = {
            "r": r, "actions_per_hour": actions_per_hour, "cost_per_action": kosten.kosten,
            "kosten": kosten,
            "sell_price": weg.preis, "sold_to_npc": weg.an_npc, "items_per_hour": items_per_hour,
            "gold_per_hour": (items_per_hour * weg.preis - kosten.kosten * actions_per_hour
                              if kosten.vollstaendig else None),
        }

    b, w = results["best"], results["worst"]
    print("\n3) ERGEBNIS EINZELSCHRITT (so steht es im Rohdaten-Tab)")
    print(f"     Aktionsdauer      {b['r']['base_time_ms'] / 1000:.4f} s")
    print(f"     Stueck/Aktion     {b['r']['item_amount']:.4f}")
    print(f"     XP/Aktion         {b['r']['xp']:,.2f}")
    print(f"     Verkauf ueber     {'NPC-Vendor' if b['sold_to_npc'] else 'Player-Markt (Bid)'} "
          f"zu {b['sell_price']:,.2f} Gold/Stueck")
    if b["cost_per_action"]:
        print(f"     Material/Aktion   {b['cost_per_action']:,.2f} Gold (best)"
              f"   |   {w['cost_per_action']:,.2f} Gold (worst)")
    if b["gold_per_hour"] is None:
        print("     -> Gold/h         unbekannt - Zutatenpreis fehlt: "
              + ", ".join(b["kosten"].fehlende))
    else:
        print(f"     -> Gold/h         {b['gold_per_hour']:,.0f}"
              + (f"   |   worst {w['gold_per_hour']:,.0f}"
                 if w["gold_per_hour"] is not None
                 and abs(b["gold_per_hour"] - w["gold_per_hour"]) > 1 else ""))

    # --- 4. Was ingame zu pruefen ist -------------------------------------
    print("\n4) INGAME GEGENPRUEFEN")
    print(f"     a) Aktionsdauer: erwartet {b['r']['base_time_ms'] / 1000:.3f} s")
    if abs(speed_mult - speed_add) > 1e-9:
        print(f"        Waere die Formel additiv statt multiplikativ: {base_time_ms / 1000 * speed_add:.3f} s")
        print("        -> Diese beiden unterscheiden sich, hier laesst sich die Formel entscheiden.")
    else:
        print("        (kein Clan-Boost auf diesen Skill -> beide Formeln identisch, nicht aussagekraeftig)")
    print(f"     b) Ausbeute: erwartet {b['r']['item_amount'] * 100:,.1f} Stueck pro 100 Aktionen")
    print(f"     c) XP: erwartet {b['r']['xp']:,.2f} pro Aktion")

    if b["cost_per_action"]:
        print("     d) Materialverbrauch pro 100 Aktionen (entscheidet Best- vs. Worst-Case):")
        for cb, cw in zip(b["r"]["costs"], w["r"]["costs"]):
            iname = item_info_map.get(cb["Item"], {}).get("name", f"item_{cb['Item']}")
            marker = "  <-- hier liegt der Unterschied" if abs(cb["Amount"] - cw["Amount"]) > 1e-9 else ""
            print(f"          {iname:<22} best {cb['Amount'] * 100:>10,.1f}   worst {cw['Amount'] * 100:>10,.1f}{marker}")

    # Auto-Cook: nur relevant, wenn dieses Item als Rohfisch ein Koch-Pendant hat
    cooked_id = fish_to_cooked.get(item_id)
    if cooked_id is not None:
        cooked_name = item_info_map.get(cooked_id, {}).get("name", f"item_{cooked_id}")
        per_action = b["r"]["item_amount"]
        print(f"     e) Auto-Cook: das Script nimmt an, dass {ma.AUTO_COOK_CHANCE:.0%} der Faenge bereits")
        print("        gekocht ankommen -> pro 100 Aktionen erwartet:")
        print(f"          {cooked_name:<22} {per_action * 100 * ma.AUTO_COOK_CHANCE:>10,.1f}")
        print(f"          {str(raw.get('Name')):<22} {per_action * 100 * (1 - ma.AUTO_COOK_CHANCE):>10,.1f}  (roh)")
        raw_bid = market_map.get(item_id, {}).get("buy", 0)
        cooked_bid = market_map.get(cooked_id, {}).get("buy", 0)
        if raw_bid and cooked_bid:
            secs = 3600.0 / b["actions_per_hour"]
            beide = (per_action * ma.AUTO_COOK_CHANCE * cooked_bid
                     + per_action * (1 - ma.AUTO_COOK_CHANCE) * raw_bid) / secs * 3600
            if conf.AUTO_COOK_SELL_RAW_REST:
                print(f"        Der rohe Rest wird MITVERKAUFT - zusammen rund {beide:,.0f} Gold/h.")
            else:
                print("        HINWEIS: AUTO_COOK_SELL_RAW_REST steht auf False, der rohe Rest")
                print(f"        faellt unter den Tisch. Mitverkauft waeren es {beide:,.0f} Gold/h.")

    # --- 5. Kette ----------------------------------------------------------
    if item_id not in recipe_by_output:
        return
    kette = ma.resolve_chain(item_id, market_map, recipe_by_output, fish_to_cooked,
                             item_info_map)
    total_ms, cost, steps = kette.zeit_ms, kette.kosten, kette.schritte
    if total_ms <= 0:
        return

    per_hour = 3_600_000.0 / total_ms
    neben_h = per_hour * kette.nebenertrag
    chain_gold = per_hour * b["sell_price"] + neben_h - cost * per_hour
    print("\n5) KETTE - DAS IST DIE ZAHL, WENN DU ES WIRKLICH SELBST FARMST")
    print(f"     Zeit pro Stueck   {total_ms / 1000:.3f} s   ->   {per_hour:,.2f} Stueck/h")
    print(f"     Zugekauft         {cost * per_hour:,.0f} Gold/h")
    if neben_h:
        print(f"     Nebenertrag       {neben_h:,.0f} Gold/h (roher Rest aus Auto-Cook)")
    print(f"     Komplett selbst   {kette.autark}")
    if kette.kosten_bekannt:
        print(f"     -> Gold/h         {chain_gold:,.0f}")
    else:
        # Keine Zahl ausgeben, die auf einer kostenlosen Zutat beruht - die haette
        # hier bei 9,1 Mio gestanden und wie ein Spitzenfund ausgesehen.
        print(f"     -> Gold/h         unbekannt, Zutatenpreis fehlt: "
              f"{', '.join(kette.fehlende)}")
    print("     Zeitanteile je Schritt:")
    for sname, sskill, qty, tms in steps:
        share = tms / total_ms if total_ms else 0
        bar = "#" * max(1, round(share * 30))
        print(f"          {sname:<30} {sskill:<13} {qty:>9,.3f} Stk  {tms / 1000:>8,.2f} s  "
              f"{share:>5.1%} {bar}")

    # --- 6. Ingame-Checkliste fuer JEDEN Schritt der Kette ------------------
    # Nur diese Zahlen bestimmen das Ketten-Gold/h - was der Markt fuer Zutaten
    # verlangt, ist beim Selbstfarmen egal.
    print("\n6) INGAME-CHECKLISTE FUER DIE GANZE KETTE")
    by_name = {r["name"]: r for r in recipe_by_output.values()}
    seen = set()
    alt_total_ms = 0.0
    for sname, sskill, qty, tms in steps:
        clean = sname.replace(" (mit Auto-Cook)", "")
        step_recipe = by_name.get(clean)
        step_cfg = skill_cfg(sskill)
        step_clan = conf.CLAN_GATHERERS_SPEED_BOOST if step_cfg.is_gathering else 0.0
        s_mult = (1.0 - step_clan) * (1.0 - step_cfg.equipment_speed_boost)
        s_add = max(0.0, 1.0 - step_clan - step_cfg.equipment_speed_boost)
        alt_total_ms += tms * (s_add / s_mult) if s_mult > 0 else tms
        if clean in seen or step_recipe is None:
            continue
        seen.add(clean)

        dur = step_recipe["base_time_ms"] / 1000
        print(f"\n     [{clean}]  ({sskill})")
        print(f"       Aktionsdauer     erwartet {dur:.3f} s"
              + (f"   (additiv waeren es {dur * s_add / s_mult:.3f} s)" if abs(s_mult - s_add) > 1e-9
                 else "   (kein Clan-Boost -> beide Formeln gleich)"))
        print(f"       Ausbeute         erwartet {step_recipe['item_amount'] * 100:,.1f} Stueck / 100 Aktionen")
        if step_recipe["costs"]:
            worst_recipe = normalize_recipe(
                sskill, _raw_of(tasks, sskill, clean), case="worst",
                excluded_cost_items=excluded_cost_items)
            print("       Verbrauch / 100 Aktionen:")
            for idx, cb in enumerate(step_recipe["costs"]):
                iname = item_info_map.get(cb["Item"], {}).get("name", f"item_{cb['Item']}")
                cw_amount = worst_recipe["costs"][idx]["Amount"] if worst_recipe else cb["Amount"]
                marker = "  <-- entscheidet best/worst" if abs(cb["Amount"] - cw_amount) > 1e-9 else ""
                print(f"          {iname:<22} best {cb['Amount'] * 100:>10,.1f}   "
                      f"worst {cw_amount * 100:>10,.1f}{marker}")

    if abs(alt_total_ms - total_ms) > 1 and kette.kosten_bekannt and chain_gold:
        alt_hour = 3_600_000.0 / alt_total_ms
        alt_gold = (alt_hour * b["sell_price"] + alt_hour * kette.nebenertrag
                    - cost * alt_hour)
        print("\n     Waere die Speed-Formel additiv statt multiplikativ, ergaebe die Kette "
              f"{alt_gold:,.0f} Gold/h statt {chain_gold:,.0f} ({(alt_gold / chain_gold - 1):+.1%}).")

    # Auto-Cook: beide Haelften des Fangs, gegen die Kettenzahl gehalten
    for raw_id, cooked_id in fish_to_cooked.items():
        if item_id not in (raw_id, cooked_id):
            continue
        fish_recipe = recipe_by_output.get(raw_id)
        if fish_recipe is None:
            continue
        raw_bid = market_map.get(raw_id, {}).get("buy", 0)
        cooked_bid = market_map.get(cooked_id, {}).get("buy", 0)
        if not (raw_bid and cooked_bid):
            continue
        secs = fish_recipe["base_time_ms"] / 1000
        per_action = fish_recipe["item_amount"]
        both = (per_action * ma.AUTO_COOK_CHANCE * cooked_bid
                + per_action * (1 - ma.AUTO_COOK_CHANCE) * raw_bid) / secs * 3600
        rawname = item_info_map.get(raw_id, {}).get("name", raw_id)
        cookedname = item_info_map.get(cooked_id, {}).get("name", cooked_id)
        print("\n     Auto-Cook: eine Fangaktion liefert laut Annahme "
              f"{per_action * ma.AUTO_COOK_CHANCE:.2f}x {cookedname} UND "
              f"{per_action * (1 - ma.AUTO_COOK_CHANCE):.2f}x {rawname}.")
        if conf.AUTO_COOK_SELL_RAW_REST:
            print(f"     Beide Haelften werden verkauft - zusammen rund {both:,.0f} Gold/h.")
        else:
            print("     AUTO_COOK_SELL_RAW_REST steht auf False: die Kette rechnet nur EINE")
            print(f"     Haelfte. Mit beiden waeren es {both:,.0f} Gold/h.")
        break


def _raw_of(tasks: dict, skill_name: str, recipe_name: str) -> dict:
    """Rohes Rezept zurueckholen (fuer die Worst-Case-Gegenrechnung eines Kettenschritts)."""
    for block in tasks.get(skill_name, []) or []:
        for raw in block.get("Items", []) or []:
            if raw.get("Name") == recipe_name:
                return raw
    return {}


def main():
    names = sys.argv[1:] or DEFAULT_ITEMS
    print(f"Pruefe: {', '.join(names)}")

    try:
        market_map = ma.load_market_map()
        game = ma.load_game_data()
    except RuntimeError as exc:
        print(f"⚠ Abbruch: {exc}")
        return 1
    item_info_map = ma.build_item_info_map(game)
    tasks = game.get("Tasks", {})

    excluded = ma.resolve_smelting_magic_exclusions(item_info_map)
    all_recipes = ma.build_all_recipes(tasks, case="best", excluded_cost_items=excluded)
    recipe_by_output = ma.build_recipe_by_output(all_recipes)
    fish_to_cooked = ma.build_fish_to_cooked_map(all_recipes, recipe_by_output)

    found = find_recipes(tasks, names)
    if not found:
        print("Keine Rezepte gefunden. Verfuegbare Namen stehen in der Spalte 'Item' im Excel.")
        return 1

    for skill_name, raw in found:
        describe(skill_name, raw, market_map, item_info_map, excluded, recipe_by_output,
                 fish_to_cooked, tasks)

    print(f"\n{SEP}\nFertig. Abschnitt 5 = Gold/h beim echten Selbstfarmen, Abschnitt 6 = die\nIngame-Checkliste fuer jeden Schritt der Kette.\n{SEP}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
