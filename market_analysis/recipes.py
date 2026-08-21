"""Reine Rezept-Normalisierung ohne Netzwerk-, pandas- oder Excel-Abhängigkeit."""

try:  # Paketimport (`python -m market_analysis.analyse`)
    from .config import (
        CLAN_GATHERERS_SPEED_BOOST, DAILY_XP_BOOST, EXTRA_YIELD_XP_SHARE,
        GLOVES_DOUBLE_CHANCE, ORE_STORAGE_COST_MULTIPLIER, SKILLS,
        SMITHING_SMELTING_COST_MULTIPLIER, XP_BOOST_TOTAL, skill_cfg,
    )
except ImportError:  # Direkter Skriptstart (`python market_analysis/analyse.py`)
    from config import (  # type: ignore
        CLAN_GATHERERS_SPEED_BOOST, DAILY_XP_BOOST, EXTRA_YIELD_XP_SHARE,
        GLOVES_DOUBLE_CHANCE, ORE_STORAGE_COST_MULTIPLIER, SKILLS,
        SMITHING_SMELTING_COST_MULTIPLIER, XP_BOOST_TOTAL, skill_cfg,
    )


def is_raid_recipe(name: str) -> bool:
    return "raids_" in str(name).lower()


def _is_smelting_magic_recipe(skill_name: str, recipe_name: str) -> bool:
    return skill_name == "Smithing" and recipe_name.endswith("_bar")


def kosten_faktor(cfg, is_bar_smelt: bool, index: int, item_id, case: str,
                  excluded_cost_items: frozenset,
                  schmelz_faktor: float | None = None,
                  lager_faktor: float | None = None) -> float:
    """Anteil einer Kostenzeile, der nach allen Ersparnissen uebrig bleibt.

    Eigene Funktion, weil hier drei Upgrades aufeinandertreffen und die Reihenfolge
    zaehlt. Beim Schmelzen greifen Smelting Magic (30%) und Ore Storage (10%) an
    derselben Erz-Zeile und werden multiplikativ kombiniert - zusammen bleiben 63%,
    nicht 60%. Faellt eine Zeile aus Smelting Magic heraus (astronomical_ore) oder
    wirkt der Perk im Worst Case nur auf die erste Zeile, gilt dort trotzdem noch
    das Lager: es ist ein eigenes Upgrade und hoert nicht auf zu wirken, nur weil
    der Perk eine Zeile auslaesst.

    Ausserhalb des Schmelzens zaehlt `cfg.cost_multiplier` (beim Farming: Potion of
    Trickery + Seed Storage, s. FARMING_COST_MULTIPLIER).

    Die beiden Faktoren sind uebergebbar, damit ein Test die Regel mit eingeschalteten
    Upgrades messen kann. Ohne das prueft er nur, dass zwei ausgeschaltete Upgrades
    beide 1.0 ergeben - und das haelt auch, wenn die Regel falsch ist.
    """
    if not is_bar_smelt:
        return cfg.cost_multiplier
    schmelzen = SMITHING_SMELTING_COST_MULTIPLIER if schmelz_faktor is None else schmelz_faktor
    lager = ORE_STORAGE_COST_MULTIPLIER if lager_faktor is None else lager_faktor
    if item_id in excluded_cost_items:
        return lager
    if case == "best" or index == 0:
        return schmelzen
    return lager


def normalize_recipe(skill_name: str, raw_recipe: dict, case: str = "best",
                     excluded_cost_items: frozenset = frozenset()) -> dict | None:
    """Normalisiert einen API-Rezepteintrag mit den konfigurierten Accountwerten."""
    if raw_recipe.get("Disabled", False) or is_raid_recipe(raw_recipe.get("Name", "")):
        return None

    base_time = raw_recipe.get("BaseTime", 0.0)
    item_id = raw_recipe.get("ItemReward", -1)
    item_amount = raw_recipe.get("ItemAmount", 0)
    if base_time <= 0 or item_id is None or item_id < 0 or item_amount <= 0:
        return None

    cfg = skill_cfg(skill_name)
    clan_boost = CLAN_GATHERERS_SPEED_BOOST if cfg.is_gathering else 0.0
    speed_factor = (1.0 - clan_boost) * (1.0 - cfg.equipment_speed_boost)
    if speed_factor <= 0:
        raise ValueError(
            f"Skill '{skill_name}': equipment_speed_boost={cfg.equipment_speed_boost} "
            "ergibt Aktionszeit <= 0. Wert in SKILLS prüfen."
        )

    yield_factor = cfg.yield_multiplier * (
        1.0 + GLOVES_DOUBLE_CHANCE if cfg.gloves_owned else 1.0)
    xp_factor = 1.0
    if cfg.extra_yield_xp and cfg.yield_multiplier > 1.0:
        xp_factor += EXTRA_YIELD_XP_SHARE * (cfg.yield_multiplier - 1.0)

    is_bar_smelt = _is_smelting_magic_recipe(
        skill_name, raw_recipe.get("Name", ""))
    costs = []
    for index, cost in enumerate(raw_recipe.get("Costs") or []):
        multiplier = kosten_faktor(cfg, is_bar_smelt, index, cost.get("Item"),
                                   case, excluded_cost_items)
        costs.append({
            "Item": cost.get("Item"),
            "Amount": cost.get("Amount", 0) * multiplier,
        })

    return {
        "name": raw_recipe.get("Name", "unknown"),
        "skill": skill_name,
        "item_id": item_id,
        "base_time_ms": base_time * speed_factor,
        "item_amount": item_amount * yield_factor,
        "xp": (raw_recipe.get("ExpReward", 0.0) * xp_factor
               * (1.0 + XP_BOOST_TOTAL) * (1.0 + DAILY_XP_BOOST)),
        "level": raw_recipe.get("LevelRequirement"),
        "costs": costs,
        "task_id": raw_recipe.get("TaskId"),
        "cost_case_ambiguous": is_bar_smelt and len(costs) > 1,
    }


def build_all_recipes(tasks: dict, case: str = "best",
                      excluded_cost_items: frozenset = frozenset()) -> list:
    """Normalisiert alle Rezepte und meldet unbekannte API-Skills."""
    recipes = []
    unknown_skills = []
    for skill_name, blocks in tasks.items():
        if skill_name not in SKILLS:
            unknown_skills.append(skill_name)
        if skill_cfg(skill_name).excluded:
            continue
        for block in blocks:
            for raw_recipe in block.get("Items", []):
                normalized = normalize_recipe(
                    skill_name, raw_recipe, case=case,
                    excluded_cost_items=excluded_cost_items,
                )
                if normalized is not None:
                    recipes.append(normalized)
    if unknown_skills and case == "best":
        print("⚠ Skills aus der API ohne Eintrag in SKILLS: "
              f"{sorted(unknown_skills)} - sie laufen ohne Boosts mit.")
    return recipes
