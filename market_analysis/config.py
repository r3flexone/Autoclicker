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
# Schlanke Item-Name -> Gold-pro-Stueck-Tabelle. EINZIGE Beruehrung mit dem
# Autoclicker, und zwar nur als Datei: der Autoclicker LIEST sie (falls in seiner
# config.json ein Pfad eingetragen ist), diese Analyse weiss nichts von ihm. Kein
# Import in beide Richtungen, keine gemeinsame Abhaengigkeit - nur eine JSON.
MARKET_VALUE_PATH = os.path.join(OUTPUT_DIR, "marktwert.json")


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
    extra_yield_xp: bool = False     # "Better fisherman"/"Better lumberjack" vorhanden (s.u.)


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


# ------------------------------------------------------------------
# Material-Ersparnisse (Stand 18.08.2026)
# ------------------------------------------------------------------
#
# Jede Ersparnis ist ein EIGENER Schalter, weil jede ein eigener Kauf ist: wer
# Trickery hat, hat deshalb noch lange kein Seed Storage. Ein gemeinsamer
# "Materialkosten"-Prozentwert waere kuerzer und waere falsch - man koennte ihn
# fuer den eigenen Account nicht mehr richtig einstellen.
#
# Kombiniert wird MULTIPLIKATIV (`spar_faktor`): zwei Upgrades, die je 10% sparen,
# sparen zusammen 19%, nicht 20%. Jedes greift auf das, was nach dem vorigen noch
# uebrig ist - genauso wie Clan- und Equipment-Boost bei der Geschwindigkeit, und
# an derselben Stelle schon einmal per Stoppuhr bestaetigt.

def spar_faktor(*paare: tuple[bool, float]) -> float:
    """Mehrere Ersparnisse zu einem Kostenfaktor kombinieren.

    `(aktiv, anteil)`-Paare, inaktive zaehlen nicht mit. Ergebnis ist der Anteil
    der Kosten, der UEBRIG bleibt: `spar_faktor((True, 0.25), (True, 0.10))` = 0.675.
    """
    faktor = 1.0
    for aktiv, anteil in paare:
        if aktiv:
            faktor *= (1.0 - anteil)
    return faktor


# Potion of Trickery: spart Saatgut beim Farming. Seit dem Update vom 18.08.2026
# sind es 25% - vorher lag hier ein fest verdrahtetes cost_multiplier=0.5 (T5).
POTION_OF_TRICKERY_ACTIVE = True
POTION_OF_TRICKERY_SAVE = 0.25

# Seed Storage (18.08.2026): 10% Samen gespart. Wirkt auf dieselben Kosten wie
# Trickery, also multiplikativ dazu -> mit beiden bleiben 67,5% der Samen uebrig.
SEED_STORAGE_ACTIVE = False
SEED_STORAGE_SAVE = 0.10

# Ore Storage (18.08.2026): 10% Erz gespart. Wirkt auf die Erz-Zeile der
# *_bar-Rezepte, also auf dieselbe Zeile wie Smelting Magic - und damit ebenfalls
# multiplikativ: 30% + 10% ergeben 37%, nicht 40%.
ORE_STORAGE_ACTIVE = False
ORE_STORAGE_SAVE = 0.10

# Kostenanteil, der beim Farming uebrig bleibt (Saatgut).
FARMING_COST_MULTIPLIER = spar_faktor(
    (POTION_OF_TRICKERY_ACTIVE, POTION_OF_TRICKERY_SAVE),
    (SEED_STORAGE_ACTIVE, SEED_STORAGE_SAVE),
)

# "Better fisherman"/"Better lumberjack": 25% XP fuer die ZUSAETZLICHE Beute aus The
# fisherman/The lumberjack (ohne die Perks gibt es dafuer gar keine XP). Wirkt nur auf
# den yield_multiplier, nicht auf die Handschuh-Verdopplung. Standardmaessig AUS, weil
# es ein eigener Kauf ist - besitzt du sie, extra_yield_xp=True beim Skill setzen.
EXTRA_YIELD_XP_SHARE = 0.25

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

# Player-Market-Steuer: 1% auf Verkaufsangebote AB 100 GOLD GESAMTWERT (Wiki). Kauf-
# angebote sind steuerfrei -> Materialkosten bleiben unveraendert. Der NPC-Vendor kennt
# keine Steuer, was den Vergleich Spieler vs. NPC leicht Richtung NPC verschiebt.
PLAYER_MARKET_TAX = 0.01
PLAYER_MARKET_TAX_MIN_TOTAL = 100.0


def net_player_price(preis: float, menge: float = 1.0) -> float:
    """Was je Stueck nach Marktsteuer beim Verkaeufer ankommt.

    Die Steuer greift erst ab `PLAYER_MARKET_TAX_MIN_TOTAL` Gold GESAMTWERT eines
    Angebots, deshalb gehoert die Menge dazu: ein einzelner Eichenstamm zu 76 g ist
    steuerfrei, dieselben 76 g mal 500 Stueck in einem Angebot nicht. Wer die Menge
    weglaesst, fragt nach genau einem Stueck - und bekommt bei billigen Items dann
    auch den steuerfreien Preis, statt stillschweigend 1% zu verlieren.
    """
    if preis <= 0 or preis * max(menge, 0.0) < PLAYER_MARKET_TAX_MIN_TOTAL:
        return preis
    return preis * (1.0 - PLAYER_MARKET_TAX)


# Gold ist in der API ein Item wie jedes andere und taucht als Kostenzeile auf
# (Carpentry zahlt Gold fuer Naegel und Leim). Es hat keinen Markteintrag - ohne
# diesen Sonderfall kam die Zeile mit Preis 0 durch, und die betroffenen Rezepte
# sahen billiger aus, als sie sind. Ein Gold kostet ein Gold.
GOLD_ITEM_ID = 19
GOLD_ITEM_PRICE = 1.0


# Verlaesslichkeit des Nachschubs je Skill: 1.0 = planbar farmbar, kleiner = die
# Zutaten kommen nur zufaellig. Farming braucht Samen, die als Zufallsdrop anfallen -
# ein Papaya-Gold/h ist rechnerisch korrekt, aber du kannst es nicht auf Zuruf farmen.
#
# Wirkt AUSSCHLIESSLICH auf die Rangfolge im Empfehlungs-Sheet (Spalte
# "Gold/h gewichtet"). Gold/h selbst, Ketten, Rohdaten und alle anderen Sheets bleiben
# unveraendert - dort steht weiter der echte Ertrag.
SKILL_RELIABILITY: dict[str, tuple[float, str]] = {
    "Farming": (0.5, "Samen nur als Zufallsdrop"),
}

AUTO_COOK_CHANCE = 0.5               # Anteil der Faenge, der bereits gekocht ankommt
AUTO_COOK_SOURCE_SKILL = "Fishing"

# Der Rest des Fangs ist ROHER Fisch, und der ist verkaeuflich. Die Kette hat ihn
# lange weggeworfen und dabei rund ein Drittel des Ertrags unterschlagen (bei tuna:
# 154.170 statt ~198.800 Gold/h ausgewiesen). Er wird als Nebenertrag gutgeschrieben,
# ueber denselben Verkaufsweg wie jedes andere Item - also Kaufgebot oder NPC, je
# nachdem, was mehr bringt. Auf False steht wieder die alte, pessimistische Rechnung.
AUTO_COOK_SELL_RAW_REST = True

# Smelting Magic: Chance, Erz beim Ore->Bar-Schmelzen nicht zu verbrauchen (hoechster
# Tier = 30%, Tiers stacken nicht). Wirkt nur auf *_bar-Rezepte, nicht aufs Schmieden.
SMELTING_MAGIC_ACTIVE = True
SMELTING_MAGIC_SAVE = 0.30

# Was von der Erz-Zeile eines *_bar-Rezepts uebrig bleibt: Smelting Magic und Ore
# Storage greifen an derselben Stelle und werden multiplikativ kombiniert.
SMITHING_SMELTING_COST_MULTIPLIER = spar_faktor(
    (SMELTING_MAGIC_ACTIVE, SMELTING_MAGIC_SAVE),
    (ORE_STORAGE_ACTIVE, ORE_STORAGE_SAVE),
)

# Ore Storage OHNE Smelting Magic: gilt fuer Erz-Zeilen, die der Perk nicht erfasst
# (SMELTING_MAGIC_EXCLUDED_ITEM_NAMES) und - im Worst Case - fuer die Nebenzutaten,
# auf die Smelting Magic moeglicherweise gar nicht wirkt. Das Lager ist ein eigenes
# Upgrade; dass der Perk eine Zeile auslaesst, macht das Lager dort nicht unwirksam.
ORE_STORAGE_COST_MULTIPLIER = spar_faktor((ORE_STORAGE_ACTIVE, ORE_STORAGE_SAVE))

# Zutaten, auf die der Perk laut Wiki NICHT wirkt. Abgleich ueber den Item-Namen, damit
# auch otherworldly_bar erfasst wird (enthaelt Astronomical ore, heisst aber nicht so).
SMELTING_MAGIC_EXCLUDED_ITEM_NAMES = ("astronomical_ore",)


SKILLS: dict[str, SkillConfig] = {
    "Mining":      SkillConfig(equipment_speed_boost=equip(), has_tool=True, is_gathering=True, gloves_owned=True),
    "Fishing":     SkillConfig(equipment_speed_boost=equip(), has_tool=True, is_gathering=True, gloves_owned=True,
                               yield_multiplier=2.0,     # Fisherman: 100% doppelte Ausbeute
                               extra_yield_xp=False),    # True, wenn "Better fisherman" gekauft
    "Foraging":    SkillConfig(equipment_speed_boost=equip(), has_tool=True, is_gathering=True, gloves_owned=True,
                               yield_multiplier=1.5,     # Power Forager: 50% Chance auf doppelte Beute
                               extra_yield_xp=False),    # nur setzen, falls es einen XP-Rueckgabe-Perk gibt
    "Woodcutting": SkillConfig(equipment_speed_boost=equip(), has_tool=True, is_gathering=True, gloves_owned=True,
                               yield_multiplier=2.0,     # Lumberjack: 100% doppelte Ausbeute
                               extra_yield_xp=False),    # True, wenn "Better lumberjack" gekauft
    "Cooking":     SkillConfig(equipment_speed_boost=equip(), has_tool=True, gloves_owned=True),
    "Carpentry":   SkillConfig(equipment_speed_boost=equip(False), gloves_owned=True),
    "Smithing":    SkillConfig(equipment_speed_boost=equip(False)),
    # Saatgut-Ersparnis: Potion of Trickery + Seed Storage (s. FARMING_COST_MULTIPLIER)
    "Farming":     SkillConfig(equipment_speed_boost=equip(False), cost_multiplier=FARMING_COST_MULTIPLIER),
    "Crafting":    SkillConfig(equipment_speed_boost=equip(), has_tool=True),
    "Agility":     SkillConfig(equipment_speed_boost=equip(), has_tool=True),
    "Plundering":  SkillConfig(equipment_speed_boost=equip(), has_tool=True, gloves_owned=True),
    # Brewing hat ein eigenes Werkzeug (Stand 18.08.2026) - vorher stand hier
    # konservativ die Grundausruestung ohne Werkzeugbonus.
    "Brewing":     SkillConfig(equipment_speed_boost=equip(), has_tool=True),

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

# VERKAUFEN und KAUFEN sind zwei verschiedene Fragen an zwei verschiedene Seiten des
# Buchs, und sie wurden hier lange gemeinsam beantwortet:
#
#   verkaufen -> es zaehlen die KAUFGEBOTE (bid, buyVol). Ob jemand teuer anbietet,
#                ist voellig egal, wenn ich verkaufen will.
#   kaufen    -> es zaehlen die ANGEBOTE (ask, sellVol).
#
# Dazu kam eine pauschale Grenze `MIN_SELL_VOLUME = 10000` auf `buyVol`. Das Feld ist
# aber die Menge AM BESTEN GEBOT, nicht die Tiefe des Buchs - und damit verwarf die
# Grenze Items, die bestens handelbar sind: yew_log und yew_plank fielen genauso auf
# den NPC-Preis zurueck wie oak (bestes Gebot 6.178 Stueck, eine Stufe tiefer 327.915).
#
# Die Tiefe beantwortet deshalb, wer sie kennt: der Orderbuch-Durchlauf im Sheet
# "Begruendung" (`walk_orderbook`), der eine Stunde Produktion wirklich durch die
# Gebotsstufen verkauft. Hier steht nur noch die Frage, ob es ueberhaupt ein Gebot
# gibt - und ein duennes Top-Gebot ist eine WARNUNG, kein Ausschluss.
MIN_SELL_BID_VOLUME = 1        # es muss ein Kaufgebot mit Menge geben, mehr nicht
MIN_BUY_ASK_VOLUME = 50        # Zutatenkauf: die Angebotsseite muss echt sein
MIN_MARKET_VOLUME = 50         # Mindest-Volumen je Seite fuer "beidseitig echter Markt"
THIN_BID_HOURS = 1.0           # Warnung, wenn das Top-Gebot < 1 h Produktion schluckt
MAX_SPREAD_RATIO = 1.0         # Warnung ab Ask > 2x Bid
MAX_AVG_DEVIATION_RATIO = 0.5  # Warnung ab >50% Abweichung vom 24h-Schnitt
LIQUIDITY_WARNING_RATIO = 5.0  # Warnung ab Bedarf/Absatz > 5x Marktvolumen


# ------------------------------------------------------------------
# Optionale Auswertungen (kosten zusaetzliche Live-Requests)
# ------------------------------------------------------------------

SHOW_PRICE_SENSITIVITY_CHART = True   # PNG + Excel-Sheet, 1 Request je Top-N-Item
PRICE_SENSITIVITY_TOP_N = 10

# Farben der Item-Linien im Sensitivitaets-Chart. Feste Reihenfolge statt matplotlibs
# Standardzyklus: der vergibt an Position 4 ein Rot, und Rot gehoert hier der
# NPC-Markierung. Ausgeschlossen ist alles, was mit NPC_MARKER_COLOR verwechselbar ist
# (Grenze Delta-E 10 bei Normalsicht) - die Markierung traegt ihre Form.
#
# Die REIHENFOLGE ist der Sicherheitsmechanismus: geprueft werden BENACHBARTE Paare,
# aehnliche Toene duerfen sich also nicht beruehren, und die kraeftigen Farben stehen
# vorn (bei TOP_N=10 kommen genau die ersten zehn zum Einsatz). Wer umsortiert oder
# ergaenzt, prueft neu. Schlechtestes Paar: Delta-E 9.1 farbfehlsichtig, 15.6 normal.
PRICE_SENSITIVITY_SERIES_COLORS = [
    "#2a78d6",  # blau
    "#eb6834",  # orange
    "#1baf7a",  # aqua
    "#eda100",  # gelb
    "#b05fd6",  # lila
    "#e87ba4",  # magenta
    "#4a3aa7",  # violett
    "#8c2f5a",  # weinrot
    "#6da7ec",  # hellblau
    "#008300",  # gruen
    "#d95f9a",  # altrosa
    "#c77800",  # dunkelorange
    "#7b3f00",  # braun
    "#7f8c1a",  # oliv
]
# Reserve, falls TOP_N ueber 14 steigt: dann traegt zusaetzlich der Linienstil die
# Unterscheidung (14 Farben x 3 Stile = 42 Kombinationen). Bei TOP_N <= 14 bleibt jede
# Linie durchgezogen - eine fuenfzehnte Farbe zu erfinden waere der falsche Weg, die haelt
# die Abstaende nicht mehr ein.
PRICE_SENSITIVITY_SERIES_STYLES = ["-", "--", ":"]
NPC_MARKER_COLOR = "#d03b3b"          # reserviert: "NPC-Verkauf gleich gut oder besser"

# Sheet "Begruendung": rechnet eine Stunde Produktion durch die echten Kaufgebot-Stufen
# im Player Shop, statt zu unterstellen, dass alles zum besten Gebot weggeht.
SHOW_REASON_ANALYSIS = True
REASON_TOP_N = 10                     # so viele Zeilen stehen am Ende in der Begruendung

# Wie viele Kandidaten VORHER durchs Orderbuch gerechnet werden. Muss groesser sein als
# REASON_TOP_N, sonst kann die Messung die Rangfolge nicht mehr aendern: das Papier-
# Gold/h unterstellt, dass du beliebig viel zum besten Gebot los wirst, und genau das
# hebelt ein duennes Buch aus. Ein Item mit Platz 1 auf dem Papier kann nach 12 Minuten
# sein Top-Gebot leergeraeumt haben, waehrend Platz 12 acht Stunden lang traegt.
# Kostet 1 Request pro Kandidat.
REASON_CANDIDATES = 30

# Preis-Position: aktueller Erloes gegen den 30-Tage-Schnitt desselben Items. Ab dieser
# Abweichung wird es in der Bewertung erwaehnt (0.10 = 10%).
PRICE_POSITION_HINT_RATIO = 0.10

# Wonach die Top-Liste sortiert wird:
#   "sofort" - alles ins beste Gebot verkauft, Geld ist sofort da
#   "geduld" - eigenes Angebot eingestellt und gewartet
#
# Der Unterschied ist gross: ein Item kann beim Sofortverkauf einbrechen (duennes Gebot)
# und mit eigenem Angebot trotzdem das beste sein. Wer das Gold nicht sofort braucht,
# stellt hier "geduld" ein — dann zaehlt aber die Spalte "Wartezeit (h)": eine Stunde
# Produktion kann Tage im Buch liegen.
RANKING_BASIS = "sofort"

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


# ------------------------------------------------------------------
# Historie (SQLite)
# ------------------------------------------------------------------
#
# Excel und Chart werden bei jedem Lauf UEBERSCHRIEBEN - das bleibt so, sie sind die
# Antwort auf "was farme ich jetzt". Was dabei verloren ging, ist die zweite Frage:
# "war das gestern auch schon so?". Ein Preissturz sieht in einer Momentaufnahme
# genauso aus wie ein dauerhaft schlechtes Item.
#
# Deshalb eine Datenbank neben den Dateien statt datierter Excel-Kopien: hundert
# .xlsx im Ordner beantworten keine einzige Frage, ohne dass man sie alle oeffnet.
HISTORY_PATH = os.path.join(OUTPUT_DIR, "market_history.sqlite")
HISTORY_ENABLED = True

# Orderbuchtiefe nur fuer die wichtigsten Kandidaten: eine Stufe je Item und Lauf ist
# die groesste Tabelle von allen, und fuer Item 400 der Rangliste sieht sie nie jemand
# an. Gespeichert wird, was ohnehin schon abgerufen wurde (Sheet "Begruendung").
HISTORY_ORDERBOOK_TOP_N = 10

# Aufbewahrung. Die Detailzeilen sind das Grosse (ein paar hundert je Lauf), die
# Tageswerte das Kleine - deshalb werden Details nach 90 Tagen zu Tageswerten
# zusammengefasst und geloescht, statt sie ewig mitzuschleppen.
HISTORY_DETAIL_DAYS = 90
HISTORY_ORDERBOOK_DAYS = 30
HISTORY_DAILY_DAYS = 365
HISTORY_RUN_LIMIT = 100

# Diese Werte gehen in den Config-Hash jedes Laufs. Aendert sich einer, sind zwei
# Laeufe nicht mehr vergleichbar - und man sieht in der Historie, WARUM ein Item
# ploetzlich anders dasteht, statt es dem Markt anzulasten.
CONFIG_HASH_KEYS = [
    "EQUIPMENT_BASE_BOOST", "EQUIPPED_TOOL_BONUS", "GLOVES_DOUBLE_CHANCE",
    "CLAN_GATHERERS_SPEED_BOOST", "XP_BOOST_TOTAL", "DAILY_XP_BOOST",
    "NPC_SELL_BOOST_MULTIPLIER", "PLAYER_MARKET_TAX", "PLAYER_MARKET_TAX_MIN_TOTAL",
    "POTION_OF_TRICKERY_ACTIVE", "POTION_OF_TRICKERY_SAVE",
    "SEED_STORAGE_ACTIVE", "SEED_STORAGE_SAVE",
    "ORE_STORAGE_ACTIVE", "ORE_STORAGE_SAVE",
    "SMELTING_MAGIC_ACTIVE", "SMELTING_MAGIC_SAVE",
    "FARMING_COST_MULTIPLIER", "SMITHING_SMELTING_COST_MULTIPLIER",
    "AUTO_COOK_CHANCE", "AUTO_COOK_SELL_RAW_REST",
    "MIN_SELL_BID_VOLUME", "MIN_BUY_ASK_VOLUME", "MIN_MARKET_VOLUME",
    "RANKING_BASIS",
]
