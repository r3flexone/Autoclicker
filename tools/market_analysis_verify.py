"""
Einzelitem-Nachrechnung fuer tools/market_analysis.py

Schluesselt fuer einzelne Rezepte den kompletten Rechenweg auf: Rohwerte aus der API ->
jeder angewendete Boost -> Endergebnis. Dazu die konkreten Zahlen, die man ingame
gegenpruefen kann, um die verbliebenen Annahmen (Speed-Formel, Smelting-Magic-Reichweite,
Auto-Cook-Chance) zu bestaetigen oder zu widerlegen.

Gedacht fuer "warum steht bei Item X dieses Gold/h?" - der Excel-Export zeigt nur das
Ergebnis, hier sieht man jeden Zwischenschritt.

Braucht `requests` (pandas nur, wenn market_analysis importiert wird - das passiert hier).

Aufruf:
    python tools/market_analysis_verify.py                  # Standard-Auswahl
    python tools/market_analysis_verify.py oak titanium_bar # beliebige Rezeptnamen
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import market_analysis as ma  # noqa: E402

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
    m = market_map.get(item_id)
    if m is None:
        return f"{name} (ID {item_id}): KEIN Markteintrag"
    return (f"{name} (ID {item_id}): Bid {m['buy']:,} / Ask {m['sell']:,}  "
            f"(BuyVol {m['buyVol']:,}, SellVol {m['sellVol']:,}, Ø24h {m['avg']:,})")


def describe(skill_name: str, raw: dict, market_map: dict, item_info_map: dict,
             excluded_cost_items: frozenset, recipe_by_output: dict, fish_to_cooked: dict):
    cfg = ma.skill_cfg(skill_name)
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
    clan = ma.CLAN_GATHERERS_SPEED_BOOST if cfg.is_gathering else 0.0
    speed_mult = (1.0 - clan) * (1.0 - cfg.equipment_speed_boost)
    speed_add = max(0.0, 1.0 - clan - cfg.equipment_speed_boost)
    yield_factor = cfg.yield_multiplier * (1.0 + ma.GLOVES_DOUBLE_CHANCE if cfg.gloves_owned else 1.0)
    xp_factor = (1.0 + ma.XP_BOOST_TOTAL) * (1.0 + ma.DAILY_XP_BOOST)

    print("\n2) ANGEWENDETE BOOSTS (aus SKILLS)")
    print(f"     Equipment-Speed   {cfg.equipment_speed_boost:.0%}"
          f"{f' + Clan-Gatherers {clan:.0%}' if clan else '  (kein Gatherers-Perk)'}")
    print(f"     Zeit-Faktor       multiplikativ {speed_mult:.4f}   |   additiv {speed_add:.4f}")
    print(f"     Yield-Faktor      {yield_factor:.3f}"
          f"   (Upgrade {cfg.yield_multiplier:.2f}"
          f"{f' x Handschuhe {1 + ma.GLOVES_DOUBLE_CHANCE:.2f}' if cfg.gloves_owned else ', keine Handschuhe'})")
    print(f"     XP-Faktor         {xp_factor:.3f}")
    if cfg.cost_multiplier != 1.0:
        print(f"     Kosten-Faktor     {cfg.cost_multiplier:.2f} (Trickery/Magic-Ersparnis)")

    # --- 3. Ergebnis pro Case ---------------------------------------------
    results = {}
    for case in ("best", "worst"):
        r = ma.normalize_recipe(skill_name, raw, case=case, excluded_cost_items=excluded_cost_items)
        if r is None:
            print("\n   !! Rezept wird vom Script AUSSORTIERT (Disabled / raids_ / keine Zeit / kein Reward)")
            return
        actions_per_hour = 3_600_000.0 / r["base_time_ms"]
        cost_per_action = sum((market_map.get(c["Item"], {}).get("sell", 0)) * c["Amount"] for c in r["costs"])
        sell_price, sold_to_npc = ma.effective_sell_price(r["item_id"], market_map, item_info_map)
        items_per_hour = actions_per_hour * r["item_amount"]
        results[case] = {
            "r": r, "actions_per_hour": actions_per_hour, "cost_per_action": cost_per_action,
            "sell_price": sell_price, "sold_to_npc": sold_to_npc, "items_per_hour": items_per_hour,
            "gold_per_hour": items_per_hour * sell_price - cost_per_action * actions_per_hour,
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
    print(f"     -> Gold/h         {b['gold_per_hour']:,.0f}"
          + (f"   |   worst {w['gold_per_hour']:,.0f}" if abs(b["gold_per_hour"] - w["gold_per_hour"]) > 1 else ""))

    # --- 4. Was ingame zu pruefen ist -------------------------------------
    print("\n4) INGAME GEGENPRUEFEN")
    print(f"     a) Aktionsdauer: erwartet {b['r']['base_time_ms'] / 1000:.3f} s")
    if abs(speed_mult - speed_add) > 1e-9:
        print(f"        Waere die Formel additiv statt multiplikativ: {base_time_ms / 1000 * speed_add:.3f} s")
        print(f"        -> Diese beiden unterscheiden sich, hier laesst sich die Formel entscheiden.")
    else:
        print(f"        (kein Clan-Boost auf diesen Skill -> beide Formeln identisch, nicht aussagekraeftig)")
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
        print(f"        gekocht ankommen -> pro 100 Aktionen erwartet:")
        print(f"          {cooked_name:<22} {per_action * 100 * ma.AUTO_COOK_CHANCE:>10,.1f}")
        print(f"          {str(raw.get('Name')):<22} {per_action * 100 * (1 - ma.AUTO_COOK_CHANCE):>10,.1f}  (roh)")
        raw_bid = market_map.get(item_id, {}).get("buy", 0)
        cooked_bid = market_map.get(cooked_id, {}).get("buy", 0)
        if raw_bid and cooked_bid:
            secs = 3600.0 / b["actions_per_hour"]
            beide = (per_action * ma.AUTO_COOK_CHANCE * cooked_bid
                     + per_action * (1 - ma.AUTO_COOK_CHANCE) * raw_bid) / secs * 3600
            print(f"        HINWEIS: die Ketten-Analyse wirft den rohen Rest weg. Wuerde man ihn")
            print(f"        mitverkaufen, waeren es {beide:,.0f} Gold/h statt der ausgewiesenen Kette.")

    # --- 5. Kette ----------------------------------------------------------
    if item_id in recipe_by_output:
        total_ms, cost, steps, ratio, self_suff = ma.resolve_chain(
            item_id, market_map, recipe_by_output, fish_to_cooked
        )
        if total_ms > 0:
            per_hour = 3_600_000.0 / total_ms
            print("\n5) KETTE (Eigenherstellung, so steht es im Ketten-Tab)")
            print(f"     Zeit pro Stueck   {total_ms / 1000:.3f} s   ->   {per_hour:,.2f} Stueck/h")
            print(f"     Zugekauft         {cost * per_hour:,.0f} Gold/h")
            print(f"     Komplett selbst   {self_suff}")
            for sname, sskill, qty, tms in steps:
                print(f"          {sname:<34} {sskill:<14} {qty:>10,.3f} Stk   {tms / 1000:>9,.2f} s")
            print(f"     -> Gold/h         {per_hour * b['sell_price'] - cost * per_hour:,.0f}")


def main():
    names = sys.argv[1:] or DEFAULT_ITEMS
    print(f"Pruefe: {', '.join(names)}")

    market_map = ma.load_market_map()
    game = ma.load_game_data()
    item_info_map = ma.build_item_info_map(game)
    tasks = game.get("Tasks", {})

    excluded = ma.resolve_smelting_magic_exclusions(item_info_map)
    all_recipes = ma.build_all_recipes(tasks, case="best", excluded_cost_items=excluded)
    recipe_by_output = ma.build_recipe_by_output(all_recipes)
    fish_to_cooked = ma.build_fish_to_cooked_map(all_recipes, recipe_by_output)

    found = find_recipes(tasks, names)
    if not found:
        print(f"Keine Rezepte gefunden. Verfuegbare Namen stehen in der Spalte 'Item' im Excel.")
        return 1

    for skill_name, raw in found:
        describe(skill_name, raw, market_map, item_info_map, excluded, recipe_by_output, fish_to_cooked)

    print(f"\n{SEP}\nFertig. Abschnitt 4 je Item enthaelt die Zahlen, die ingame gegenzupruefen sind.\n{SEP}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
