"""
Konfiguration der Gold/h-Analyse - die einzige Datei, die du normalerweise anfasst.

Hintergrund zu jedem Wert, welche Werte ingame verifiziert sind und was noch offen
ist: siehe README.md im selben Ordner.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# ------------------------------------------------------------------
# API + Ausgabepfade
# ------------------------------------------------------------------

MARKET_URL = "https://query.idleclans.com/api/PlayerMarket/items/prices/latest?includeAveragePrice=true"
GAME_URL = "https://query.idleclans.com/api/Configuration/game-data"
COMPREHENSIVE_URL_TEMPLATE = "https://query.idleclans.com/api/PlayerMarket/items/prices/latest/comprehensive/{item_id}"

# Alles Generierte landet in market_analysis/output/ statt im Projektordner.
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
EXPORT_PATH = os.path.join(OUTPUT_DIR, "idle_clans_farming.xlsx")
PRICE_SENSITIVITY_CHART_PATH = os.path.join(OUTPUT_DIR, "price_sensitivity_chart.png")
RUN_STATS_PATH = os.path.join(OUTPUT_DIR, "run_stats_history.json")


# ------------------------------------------------------------------
# Account: Skills, Ausruestung, Upgrades
# ------------------------------------------------------------------

@dataclass
class SkillConfig:
    equipment_speed_boost: float = 0.0
    is_gathering: bool = False       # bekommt den Gatherers-Clanbonus (nur echte Gathering-Skills)
    gloves_owned: bool = False       # Skilling-Handschuhe: 5% Chance auf doppelte Beute
    yield_multiplier: float = 1.0    # fixe Verdopplungs-Upgrades (Fisherman/Lumberjack/Power Forager)
    cost_multiplier: float = 1.0     # Anteil der Materialkosten nach Trickery-Ersparnis
    excluded: bool = False           # Skill komplett ignorieren
    has_tool: bool = False           # Werkzeug fuer diesen Skill vorhanden (+EQUIPPED_TOOL_BONUS)


# Grundausruestung 55% bei allen Skilling-Skills, +6% durch das Werkzeug des gerade
# aktiven Skills. Die Loadouts wechseln ingame automatisch mit der Taetigkeit, deshalb
# zaehlt has_tool (= Werkzeug vorhanden), nicht der Momentanwert im Boosts-Screen.
EQUIPMENT_BASE_BOOST = 0.55
EQUIPPED_TOOL_BONUS = 0.06

# False friert den Ist-Zustand ein: nur CURRENTLY_EQUIPPED_TOOL_SKILL bekommt den Bonus.
ASSUME_TOOL_EQUIPPED_PER_SKILL = True
CURRENTLY_EQUIPPED_TOOL_SKILL = "Woodcutting"


def equip(has_tool: bool = True) -> float:
    return EQUIPMENT_BASE_BOOST + (EQUIPPED_TOOL_BONUS if has_tool else 0.0)


GLOVES_DOUBLE_CHANCE = 0.05          # alle Skilling-Handschuhe
CLAN_GATHERERS_SPEED_BOOST = 0.05    # Clan-Upgrade "Gatherers", nur is_gathering=True

XP_BOOST_TOTAL = 0.25 + 0.25         # Clan house + House

# Daily Boost ("Flamme" im Profil) - temporaer, vor dem Lauf kurz pruefen.
DAILY_BOOST_ACTIVE = False
DAILY_XP_BOOST_PERCENT = 0.04
DAILY_XP_BOOST = DAILY_XP_BOOST_PERCENT if DAILY_BOOST_ACTIVE else 0.0

# NPC-Verkaufspreis: beide Quellen multiplikativ = 1.155x (per Wiki bestaetigt).
OFFER_THEY_CANT_REFUSE_ACTIVE = True   # Clan-Upgrade, +10%
POTION_OF_NEGOTIATION_ACTIVE = True    # permanent, +5%
NPC_SELL_BOOST_MULTIPLIER = (
    (1.10 if OFFER_THEY_CANT_REFUSE_ACTIVE else 1.0)
    * (1.05 if POTION_OF_NEGOTIATION_ACTIVE else 1.0)
)

AUTO_COOK_CHANCE = 0.5               # Anteil der Faenge, der bereits gekocht ankommt
AUTO_COOK_SOURCE_SKILL = "Fishing"

# Smelting Magic: Chance, Erz beim Ore->Bar-Schmelzen nicht zu verbrauchen (hoechster
# Tier = 30%, Tiers stacken nicht). Wirkt nur auf *_bar-Rezepte, nicht aufs Schmieden.
SMITHING_SMELTING_COST_MULTIPLIER = 1.0 - 0.3

# Zutaten, auf die der Perk laut Wiki NICHT wirkt. Abgleich ueber den Item-Namen, damit
# auch otherworldly_bar erfasst wird (enthaelt Astronomical ore, heisst aber nicht so).
SMELTING_MAGIC_EXCLUDED_ITEM_NAMES = ("astronomical_ore",)


SKILLS: dict[str, SkillConfig] = {
    "Mining":      SkillConfig(equipment_speed_boost=equip(), has_tool=True, is_gathering=True, gloves_owned=True),
    "Fishing":     SkillConfig(equipment_speed_boost=equip(), has_tool=True, is_gathering=True, gloves_owned=True,
                               yield_multiplier=2.0),    # Fisherman: 100% doppelte Ausbeute
    "Foraging":    SkillConfig(equipment_speed_boost=equip(), has_tool=True, is_gathering=True, gloves_owned=True,
                               yield_multiplier=1.5),    # Power Forager: 50% Chance auf doppelte Beute
    "Woodcutting": SkillConfig(equipment_speed_boost=equip(), has_tool=True, is_gathering=True, gloves_owned=True,
                               yield_multiplier=2.0),    # Lumberjack: 100% doppelte Ausbeute
    "Cooking":     SkillConfig(equipment_speed_boost=equip(), has_tool=True, gloves_owned=True),
    "Carpentry":   SkillConfig(equipment_speed_boost=equip(False), gloves_owned=True),
    "Smithing":    SkillConfig(equipment_speed_boost=equip(False)),
    "Farming":     SkillConfig(equipment_speed_boost=equip(False), cost_multiplier=0.5),  # Trickery T5: 50% Saatgut gespart
    "Crafting":    SkillConfig(equipment_speed_boost=equip(), has_tool=True),
    "Agility":     SkillConfig(equipment_speed_boost=equip(), has_tool=True),
    "Plundering":  SkillConfig(equipment_speed_boost=equip(), has_tool=True, gloves_owned=True),
    "Brewing":     SkillConfig(equipment_speed_boost=equip(False)),  # Werkzeug unbekannt -> konservativ ohne

    # Keine normalen Markt-Item-Rezepte. Namen exakt wie im Tasks-Block der API.
    "Combat": SkillConfig(excluded=True),
    "Enchanting": SkillConfig(excluded=True),
    "Invocation": SkillConfig(excluded=True),
    "ItemCreation": SkillConfig(excluded=True),
}

if not ASSUME_TOOL_EQUIPPED_PER_SKILL:
    for _name, _cfg in SKILLS.items():
        if _cfg.has_tool and _name != CURRENTLY_EQUIPPED_TOOL_SKILL:
            _cfg.equipment_speed_boost -= EQUIPPED_TOOL_BONUS
            _cfg.has_tool = False

DEFAULT_SKILL_CONFIG = SkillConfig()  # unbekannte/neue Skills: keine Boosts, aber drin


def skill_cfg(skill_name: str) -> SkillConfig:
    return SKILLS.get(skill_name, DEFAULT_SKILL_CONFIG)


# ------------------------------------------------------------------
# Markt-Filter (account-unabhaengig)
# ------------------------------------------------------------------

# Achtung: buyVol ist die Menge AM BESTEN GEBOT, nicht die Tiefe des Buchs - ein Item
# kann hier scheitern und trotzdem bestens handelbar sein (Details im README).
MIN_SELL_VOLUME = 10000        # Mindest-BuyVol des Endprodukts fuer den Sofortverkauf
MIN_MARKET_VOLUME = 50         # Mindest-Volumen je Seite, damit ein Markt als echt gilt
MAX_SPREAD_RATIO = 1.0         # Warnung ab Ask > 2x Bid
MAX_AVG_DEVIATION_RATIO = 0.5  # Warnung ab >50% Abweichung vom 24h-Schnitt
LIQUIDITY_WARNING_RATIO = 5.0  # Warnung ab Bedarf/Absatz > 5x Marktvolumen


# ------------------------------------------------------------------
# Optionale Auswertungen (kosten zusaetzliche Live-Requests)
# ------------------------------------------------------------------

SHOW_PRICE_SENSITIVITY_CHART = True   # PNG + Excel-Sheet, 1 Request je Top-N-Item
PRICE_SENSITIVITY_TOP_N = 10

# Sheet "Begruendung": rechnet eine Stunde Produktion durch die echten Kaufgebot-Stufen
# im Player Shop, statt zu unterstellen, dass alles zum besten Gebot weggeht.
SHOW_REASON_ANALYSIS = True
REASON_TOP_N = 10                     # nur die Top-Items, 1 Request pro Item

SHOW_LONGTERM_AVERAGES = False        # 1 Request PRO ITEM in Rohdaten -> Minuten
LONGTERM_AVERAGES_REQUEST_DELAY_S = 0.05

# Feldnamen des comprehensive-Endpoints, live verifiziert.
COMPREHENSIVE_AVG_FIELDS = {
    "Avg1D": "averagePrice1Day",
    "Avg7D": "averagePrice7Days",
    "Avg30D": "averagePrice30Days",
}
COMPREHENSIVE_VOLUME_FIELD = "tradeVolume1Day"


# ------------------------------------------------------------------
# Lauf-Sanity-Check
# ------------------------------------------------------------------

RUN_STATS_HISTORY_LIMIT = 50     # so viele Laeufe werden aufgehoben
MARKET_DROP_WARNING_RATIO = 0.3  # Einbruch bei Markt-Kennzahlen, ab dem gewarnt wird

# Struktur-Werte aus der Game-Data sollten nur wachsen; Markt-Werte duerfen schwanken.
STRUCTURAL_STATS = ["tasks_count", "recipes_count", "item_info_count"]
MARKET_STATS = ["market_map_count", "rohdaten_count", "in_ketten_count", "realistic_count"]

# Plausibilitaetsfenster fuer eine Aktion (deckt auf, wenn BaseTime nicht mehr in ms kommt)
MIN_PLAUSIBLE_ACTION_SEC = 0.3
MAX_PLAUSIBLE_ACTION_SEC = 300.0
