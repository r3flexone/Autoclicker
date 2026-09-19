"""Feste Referenzwerte für die reine Marktberechnung.

Alles hier läuft **ohne pandas** – das ist kein Zufall, sondern der Grund, warum
`pricing.py` und `history.py` überhaupt eigene Module sind. Die CI installiert
pandas nicht, und solange die rechnende Logik zwischen DataFrames und
Excel-Formatierung in `analysis.py` lag, lief sie in keinem einzigen Test.
"""

import unittest
from datetime import datetime, timedelta

from market_analysis import config as cfg
from market_analysis import extended_json, history, pricing
from market_analysis.config import (
    COMPREHENSIVE_AVG_FIELDS, GOLD_ITEM_ID, net_player_price, saving_factor,
)
from market_analysis.orderbook import patience_analysis, price_position, walk_orderbook
from market_analysis.recipes import cost_factor, normalize_recipe, skill_cfg


# Ein kleiner, vollständiger Markt: Bid/Ask/Volumen wie aus dem Bulk-Endpoint.
MARKET = {
    100: {"buy": 76, "sell": 90, "buyVol": 6178, "sellVol": 5000, "avg": 78},
    200: {"buy": 120, "sell": 140, "buyVol": 20000, "sellVol": 9000, "avg": 130},
    201: {"buy": 300, "sell": 340, "buyVol": 15000, "sellVol": 7000, "avg": 310},
    400: {"buy": 3, "sell": 4, "buyVol": 900, "sellVol": 900, "avg": 3},
    500: {"buy": 0, "sell": 0, "buyVol": 0, "sellVol": 0, "avg": 0},
}
INFO = {
    100: {"name": "yew_log", "base_value": 20, "can_trade": True, "can_sell_to_npc": True},
    200: {"name": "tuna", "base_value": 30, "can_trade": True, "can_sell_to_npc": True},
    201: {"name": "cooked_tuna", "base_value": 55, "can_trade": True, "can_sell_to_npc": True},
    400: {"name": "billig", "base_value": 1, "can_trade": True, "can_sell_to_npc": True},
    500: {"name": "gebunden", "base_value": 0, "can_trade": False, "can_sell_to_npc": False},
}


def _rezept(name, skill, item_id, base_time, amount=1, costs=None, xp=0.0):
    """Ein normalisiertes Rezept, wie es aus der API käme."""
    return normalize_recipe(skill, {
        "Name": name, "BaseTime": base_time, "ItemReward": item_id,
        "ItemAmount": amount, "ExpReward": xp, "Costs": costs or [],
        "TaskId": item_id, "LevelRequirement": 1,
    })


class RezeptTest(unittest.TestCase):
    def test_mining_recipe_reference_values(self):
        recipe = _rezept("reference_ore", "Mining", 1, 10000, amount=2, xp=100)
        self.assertAlmostEqual(recipe["base_time_ms"], 3705.0)
        self.assertAlmostEqual(recipe["item_amount"], 2.1)
        self.assertAlmostEqual(recipe["xp"], 150.0)

    def test_smelting_magic_best_and_worst_case(self):
        raw = {
            "Name": "reference_bar", "BaseTime": 30000,
            "ItemReward": 2, "ItemAmount": 1, "ExpReward": 0,
            "Costs": [{"Item": 10, "Amount": 3}, {"Item": 11, "Amount": 9}],
        }
        best = normalize_recipe("Smithing", raw, case="best")
        worst = normalize_recipe("Smithing", raw, case="worst")
        expected_best = 3 * cfg.SMITHING_SMELTING_COST_MULTIPLIER
        expected_worst_side = 9 * cfg.ORE_STORAGE_COST_MULTIPLIER
        self.assertAlmostEqual(best["costs"][0]["Amount"], expected_best)
        self.assertAlmostEqual(worst["costs"][0]["Amount"], expected_best)
        self.assertAlmostEqual(worst["costs"][1]["Amount"], expected_worst_side)

    def test_brewing_hat_werkzeug(self):
        """Brewing-Ausrüstung: mit Werkzeug, nicht mehr konservativ ohne."""
        self.assertTrue(skill_cfg("Brewing").has_tool)
        self.assertAlmostEqual(skill_cfg("Brewing").equipment_speed_boost,
                               cfg.EQUIPMENT_BASE_BOOST + cfg.EQUIPPED_TOOL_BONUS)


class ErsparnisTest(unittest.TestCase):
    """Storage-Boni und Potion of Trickery – Schalter und Kombination."""

    def test_spar_faktor_ist_multiplikativ(self):
        # 25% + 10% sparen zusammen 32.5%, nicht 35%.
        self.assertAlmostEqual(saving_factor((True, 0.25), (True, 0.10)), 0.675)
        self.assertAlmostEqual(saving_factor((False, 0.25), (True, 0.10)), 0.90)
        self.assertAlmostEqual(saving_factor((False, 0.25), (False, 0.10)), 1.0)

    def test_potion_of_trickery_ist_25_prozent(self):
        """Update 18.08.2026: 25%, vorher waren 50% fest verdrahtet."""
        self.assertAlmostEqual(cfg.POTION_OF_TRICKERY_SAVE, 0.25)
        only_trickery = saving_factor((True, cfg.POTION_OF_TRICKERY_SAVE))
        self.assertAlmostEqual(only_trickery, 0.75)

    def test_seed_storage_kombiniert_mit_trickery(self):
        with_both = saving_factor((True, cfg.POTION_OF_TRICKERY_SAVE),
                                 (True, cfg.SEED_STORAGE_SAVE))
        self.assertAlmostEqual(with_both, 0.675)
        # Und der Schalter greift wirklich am Skill.
        self.assertAlmostEqual(skill_cfg("Farming").cost_multiplier,
                               cfg.FARMING_COST_MULTIPLIER)

    def test_ore_storage_kombiniert_mit_smelting_magic(self):
        """Beide sparen Erz an derselben Zeile – multiplikativ, nicht addiert."""
        with_both = saving_factor((True, 0.30), (True, 0.10))
        self.assertAlmostEqual(with_both, 0.63)
        self.assertNotAlmostEqual(with_both, 0.60)
        # Und der Konfigurationswert wird wirklich so gebildet – sonst prüft der
        # Test die Rechenregel, während die Config etwas anderes tut.
        self.assertAlmostEqual(
            cfg.SMITHING_SMELTING_COST_MULTIPLIER,
            saving_factor((cfg.SMELTING_MAGIC_ACTIVE, cfg.SMELTING_MAGIC_SAVE),
                        (cfg.ORE_STORAGE_ACTIVE, cfg.ORE_STORAGE_SAVE)))

    def test_ore_storage_gilt_auch_ohne_smelting_magic(self):
        """Eine vom Perk ausgenommene Zeile verliert das Lager nicht mit.

        Gemessen mit EINGESCHALTETEN Upgrades (0,63 Schmelzen / 0,90 Lager). Mit den
        Standardwerten stehen beide auf 1.0, und der Test hielte auch dann, wenn die
        Regel die Zeile auf 1.0 zurückfallen liesse.
        """
        cfg_smith = skill_cfg("Smithing")
        ausgenommen = cost_factor(cfg_smith, True, 0, 10, "best", frozenset({10}),
                                    smelt_factor=0.63, storage_factor=0.90)
        self.assertAlmostEqual(ausgenommen, 0.90)
        # Nebenzutat im Worst Case: ebenfalls nur das Lager, nicht der volle Preis.
        side = cost_factor(cfg_smith, True, 1, 11, "worst", frozenset(),
                              smelt_factor=0.63, storage_factor=0.90)
        self.assertAlmostEqual(side, 0.90)
        # Die Erz-Zeile selbst bekommt beide Ersparnisse.
        erz = cost_factor(cfg_smith, True, 0, 10, "worst", frozenset(),
                            smelt_factor=0.63, storage_factor=0.90)
        self.assertAlmostEqual(erz, 0.63)

    def test_kosten_faktor_ausserhalb_des_schmelzens(self):
        self.assertAlmostEqual(
            cost_factor(skill_cfg("Farming"), False, 0, 7, "best", frozenset(),
                          smelt_factor=0.63, storage_factor=0.90),
            cfg.FARMING_COST_MULTIPLIER)


class TaxTest(unittest.TestCase):
    """Marktsteuer erst ab 100 Gold Gesamtwert."""

    def test_kleinbetrag_bleibt_steuerfrei(self):
        self.assertEqual(net_player_price(76), 76)
        self.assertEqual(net_player_price(3, 30), 3)      # 90 Gold gesamt

    def test_ab_hundert_gold_faellt_steuer_an(self):
        self.assertAlmostEqual(net_player_price(100), 99.0)
        self.assertAlmostEqual(net_player_price(3, 34), 2.97)   # 102 Gold gesamt

    def test_menge_entscheidet_nicht_der_stueckpreis(self):
        """Eine Stunde Produktion billiger Items ist ein steuerpflichtiges Angebot."""
        self.assertEqual(net_player_price(3), 3)
        self.assertAlmostEqual(net_player_price(3, 1000), 2.97)


class MarktwegTest(unittest.TestCase):
    """Verkaufen zählt Kaufgebote, kaufen zählt Angebote."""

    def test_verkauf_ignoriert_die_angebotsseite(self):
        only_bids = {"buy": 50, "sell": 0, "buyVol": 500, "sellVol": 0, "avg": 50}
        self.assertTrue(pricing.valid_sell_market(only_bids))
        self.assertFalse(pricing.valid_buy_market(only_bids))

    def test_kauf_ignoriert_die_gebotsseite(self):
        only_offers = {"buy": 0, "sell": 60, "buyVol": 0, "sellVol": 500, "avg": 60}
        self.assertTrue(pricing.valid_buy_market(only_offers))
        self.assertFalse(pricing.valid_sell_market(only_offers))

    def test_duennes_top_gebot_verwirft_den_marktpreis_nicht(self):
        """yew_log: 6.178 Stück am besten Gebot – früher unter MIN_SELL_VOLUME=10000.

        Ohne den Fix fiel das Item auf den NPC-Preis (20 x 1,155 = 23,1) zurück,
        obwohl 76 g geboten werden.
        """
        channel = pricing.effective_sell_price(100, MARKET, INFO, amount_value=1000)
        self.assertFalse(channel.to_npc)
        self.assertAlmostEqual(channel.price_value, 76 * 0.99)
        self.assertGreater(channel.price_value, channel.npc_price)

    def test_npc_gewinnt_wenn_er_mehr_zahlt(self):
        info = dict(INFO)
        info[100] = dict(INFO[100], base_value=200)      # NPC: 231 > 75,24
        channel = pricing.effective_sell_price(100, MARKET, info, amount_value=1000)
        self.assertTrue(channel.to_npc)
        self.assertAlmostEqual(channel.price_value, 200 * cfg.NPC_SELL_BOOST_MULTIPLIER)

    def test_duennes_gebot_ist_eine_frage_der_produktion(self):
        """Nicht 'unter 10.000 Stück', sondern 'reicht keine Stunde'."""
        market = {"buy": 76, "sell": 90, "buyVol": 6178, "sellVol": 500, "avg": 78}
        self.assertFalse(pricing.thin_top_bid(market, 200))     # 30 h Vorrat
        self.assertTrue(pricing.thin_top_bid(market, 40000))    # 9 min
        self.assertFalse(pricing.thin_top_bid(market, 0))
        self.assertFalse(pricing.thin_top_bid(None, 200))

    def test_ohne_jeden_weg_kommt_ein_grund(self):
        channel = pricing.effective_sell_price(500, MARKET, INFO)
        self.assertEqual(channel.price_value, 0.0)
        self.assertIn("CanNotBeTraded", channel.reason)
        self.assertIn("CanNotBeSoldToGameShop", channel.reason)

    def test_vergleich_laeuft_netto_gegen_netto(self):
        """Spielergebot verliert Steuer, der NPC nicht – sonst wäre der Vergleich schief."""
        info = dict(INFO)
        info[100] = dict(INFO[100], base_value=65)       # NPC: 75,075
        channel = pricing.effective_sell_price(100, MARKET, info, amount_value=1000)
        self.assertAlmostEqual(channel.player_net, 75.24)
        self.assertFalse(channel.to_npc)                     # 75,24 > 75,075, aber knapp


class IngredientPriceTest(unittest.TestCase):
    def test_gold_ist_ein_item_und_kostet_eins(self):
        """API-Item 19 ist direktes Gold – früher als 'kein Markteintrag' mit 0 gerechnet."""
        self.assertEqual(GOLD_ITEM_ID, 19)
        price_value, known = pricing.ingredient_price(19, MARKET)
        self.assertTrue(known)
        self.assertEqual(price_value, 1.0)
        # Gegenprobe: ohne den Sonderfall wäre die Zeile "unbekannt" und die
        # Carpentry-Kosten fielen auf 0 zurück.
        self.assertFalse(pricing.ingredient_price(18, MARKET).known)

    def test_fehlender_preis_ist_nicht_null(self):
        price_value, known = pricing.ingredient_price(999, MARKET)
        self.assertFalse(known)
        self.assertEqual(price_value, 0.0)

    def test_markteintrag_ohne_angebot_gilt_als_unbekannt(self):
        _, known = pricing.ingredient_price(500, MARKET)
        self.assertFalse(known)

    def test_goldkosten_landen_in_der_summe(self):
        image = pricing.cost_per_action(
            [{"Item": 100, "Amount": 1}, {"Item": GOLD_ITEM_ID, "Amount": 250}],
            MARKET, item_info_map=INFO)
        self.assertTrue(image.complete)
        self.assertAlmostEqual(image.costs_value, 90 + 250)

    def test_fehlende_zutat_macht_die_kosten_unvollstaendig(self):
        image = pricing.cost_per_action(
            [{"Item": 100, "Amount": 1}, {"Item": 999, "Amount": 2}],
            MARKET, item_info_map=INFO)
        self.assertFalse(image.complete)
        self.assertEqual(image.missing_ones, ("item_999",))
        self.assertAlmostEqual(image.costs_value, 90)       # nur die bekannte Zeile


class ChainTest(unittest.TestCase):
    """Komplette Ketten: Zeit, Kosten, Autarkie, Nebenertrag."""

    def setUp(self):
        self.recipes = {
            100: _rezept("yew_log", "Woodcutting", 100, 8000),
            200: _rezept("tuna", "Fishing", 200, 9000),
            201: _rezept("cooked_tuna", "Cooking", 201, 3000,
                         costs=[{"Item": 200, "Amount": 1}]),
        }
        self.fisch = {200: 201}

    def test_einzelne_stufe_ohne_zutaten(self):
        k = pricing.resolve_chain(100, MARKET, self.recipes, {}, INFO)
        self.assertTrue(k.self_sufficient)
        self.assertTrue(k.costs_known)
        self.assertEqual(k.costs_value, 0.0)
        # Zeit für EIN Stück: die Aktionszeit geteilt durch die Ausbeute je Aktion.
        # Gegen das Rezept gerechnet statt gegen eine getippte Zahl – sonst prüft der
        # Test die Boost-Formel mit, und die hat ihren eigenen Test.
        rezept = self.recipes[100]
        self.assertAlmostEqual(k.time_ms, rezept["base_time_ms"] / rezept["item_amount"])

    def test_zutat_wird_selbst_hergestellt_statt_gekauft(self):
        recipes = dict(self.recipes)
        recipes[300] = _rezept("plank", "Carpentry", 300, 6000,
                               costs=[{"Item": 100, "Amount": 2}])
        k = pricing.resolve_chain(300, MARKET, recipes, {}, INFO)
        self.assertTrue(k.self_sufficient)
        self.assertEqual(k.costs_value, 0.0)            # Holz wird gefarmt, nicht gekauft
        self.assertEqual(len(k.steps_list), 2)

    def test_gekaufte_zutat_bricht_die_autarkie(self):
        recipes = {300: _rezept("ring", "Crafting", 300, 5000,
                                costs=[{"Item": 100, "Amount": 2}])}
        k = pricing.resolve_chain(300, MARKET, recipes, {}, INFO)
        self.assertFalse(k.self_sufficient)
        self.assertGreater(k.costs_value, 0.0)

    def test_gold_kostet_bricht_aber_die_autarkie_nicht(self):
        recipes = {300: _rezept("plank", "Carpentry", 300, 6000,
                                costs=[{"Item": GOLD_ITEM_ID, "Amount": 250}])}
        k = pricing.resolve_chain(300, MARKET, recipes, {}, INFO)
        self.assertTrue(k.self_sufficient)
        self.assertAlmostEqual(k.costs_value, 250 / (1 * 1.05))     # je Stück Ausbeute
        self.assertEqual(k.liquidity, 0.0)       # Gold hat keinen Markt, der knapp wird

    def test_unbekannter_zutatenpreis_wird_gemeldet_nicht_genullt(self):
        recipes = {300: _rezept("ring", "Crafting", 300, 5000,
                                costs=[{"Item": 999, "Amount": 2}])}
        k = pricing.resolve_chain(300, MARKET, recipes, {}, INFO)
        self.assertFalse(k.costs_known)
        self.assertEqual(k.missing_ones, ("item_999",))

    def test_auto_cook_verkauft_den_rohen_rest(self):
        """Ein Fischzug liefert je zur Hälfte gekocht und roh – der rohe Teil zählt."""
        k = pricing.resolve_chain(201, MARKET, self.recipes, self.fisch, INFO)
        self.assertGreater(k.side_yield, 0.0)
        # Pro gekochtem Stück fällt genau ein rohes an (Chance 0,5).
        raw_per_unit = (1.0 - cfg.AUTO_COOK_CHANCE) / cfg.AUTO_COOK_CHANCE
        channel = pricing.effective_sell_price(200, MARKET, INFO, raw_per_unit)
        self.assertAlmostEqual(k.side_yield, raw_per_unit * channel.price_value)

    def test_auto_cook_fischt_statt_zu_kochen(self):
        k = pricing.resolve_chain(201, MARKET, self.recipes, self.fisch, INFO)
        self.assertEqual([s[1] for s in k.steps_list], ["Fishing"])

    def test_auto_cook_abschaltbar(self):
        """Ohne den Schalter steht wieder die alte, pessimistische Rechnung da."""
        old = pricing.AUTO_COOK_SELL_RAW_REST
        try:
            pricing.AUTO_COOK_SELL_RAW_REST = False
            k = pricing.resolve_chain(201, MARKET, self.recipes, self.fisch, INFO)
            self.assertEqual(k.side_yield, 0.0)
        finally:
            pricing.AUTO_COOK_SELL_RAW_REST = old

    def test_zyklus_bricht_die_rekursion(self):
        recipes = {
            300: _rezept("a", "Crafting", 300, 1000, costs=[{"Item": 301, "Amount": 1}]),
            301: _rezept("b", "Crafting", 301, 1000, costs=[{"Item": 300, "Amount": 1}]),
        }
        k = pricing.resolve_chain(300, MARKET, recipes, {}, INFO)
        self.assertFalse(k.self_sufficient)


class OrderbookTest(unittest.TestCase):
    def test_orderbook_walk_reference_values(self):
        self.assertEqual(walk_orderbook([(90, 5), (100, 2)], 4), (380.0, 4, 90))

    def test_patience_and_trend_reference_values(self):
        depth = {
            "lowestSellPricesWithVolume": [{"key": 120, "value": 10}],
            "tradeVolume1Day": 240,
            COMPREHENSIVE_AVG_FIELDS["Avg1D"]: 120,
            COMPREHENSIVE_AVG_FIELDS["Avg7D"]: 110,
            COMPREHENSIVE_AVG_FIELDS["Avg30D"]: 100,
        }
        result = patience_analysis(depth, 100, 20, 50)
        self.assertEqual(result["price_value"], 119)
        self.assertAlmostEqual(result["wartezeit_h"], 2.0)
        position, trend = price_position(120, depth)
        self.assertAlmostEqual(position, 0.2)
        self.assertEqual(trend, "steigend")

    def test_preis_position_erwartet_brutto(self):
        """Netto gegen den Brutto-Schnitt zu halten meldet bei jedem Item -1%."""
        depth = {COMPREHENSIVE_AVG_FIELDS["Avg30D"]: 100}
        gross, _ = price_position(100, depth)
        self.assertAlmostEqual(gross, 0.0)
        net, _ = price_position(net_player_price(100), depth)
        self.assertAlmostEqual(net, -0.01)


class HistoryTest(unittest.TestCase):
    def setUp(self):
        self.conn = history.open_db(":memory:")

    def tearDown(self):
        self.conn.close()

    def _row(self, item="oak", **remainder):
        basis = {"item": item, "item_id": 1, "skill": "Woodcutting", "bid": 76,
                 "ask": 90, "npc_preis": 23, "kosten_h": 0, "gold_h": 1000,
                 "gold_h_real": 900, "verkaufsweg": "Spieler", "rang": 1,
                 "warnings": ""}
        basis.update(remainder)
        return basis

    def test_lauf_speichert_zeitpunkt_version_und_confighash(self):
        with history.run_ctx(self.conn) as run_id:
            history.write_items(self.conn, run_id, [self._row()])
        run_ctx = history.last_runs(self.conn)[0]
        self.assertTrue(run_ctx["ts"])
        self.assertTrue(run_ctx["code_version"])
        self.assertEqual(len(run_ctx["config_hash"]), 12)
        self.assertEqual(run_ctx["items"], 1)

    def test_nur_erfolgreiche_laeufe_werden_uebernommen(self):
        with self.assertRaises(RuntimeError):
            with history.run_ctx(self.conn) as run_id:
                history.write_items(self.conn, run_id, [self._row()])
                raise RuntimeError("Abbruch mitten im Lauf")
        self.assertEqual(history.last_runs(self.conn), [])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM items").fetchone()[0], 0)

    def test_config_hash_aendert_sich_mit_den_annahmen(self):
        class Other:
            pass
        other = Other()
        for name in cfg.CONFIG_HASH_KEYS:
            setattr(other, name, getattr(cfg, name, None))
        before = history.config_hash(other)
        other.POTION_OF_TRICKERY_SAVE = 0.5
        self.assertNotEqual(before, history.config_hash(other))

    def test_orderbuch_nur_fuer_die_wichtigsten_kandidaten(self):
        books = [{"item": f"i{n}", "item_id": n, "kauf": [(10, 5)], "verkauf": []}
                   for n in range(5)]
        with history.run_ctx(self.conn) as run_id:
            history.write_orderbook(self.conn, run_id, books, top_n=2)
        ids = {z["item_id"] for z in
               self.conn.execute("SELECT item_id FROM orderbook").fetchall()}
        self.assertEqual(ids, {0, 1})

    def test_alte_details_werden_zu_tageswerten_und_verschwinden(self):
        old = datetime.now() - timedelta(days=cfg.HISTORY_DETAIL_DAYS + 5)
        with history.run_ctx(self.conn, timestamp=old) as run_id:
            history.write_items(self.conn, run_id, [self._row(gold_h=1000)])
        with history.run_ctx(self.conn) as run_id:
            history.write_items(self.conn, run_id, [self._row(gold_h=2000)])

        report = history.tidy_up(self.conn)
        self.assertEqual(report["condensed"], 1)
        self.assertEqual(report["items"], 1)
        days_count = self.conn.execute("SELECT tag, gold_h FROM daily").fetchall()
        self.assertEqual(len(days_count), 1)
        self.assertAlmostEqual(days_count[0]["gold_h"], 1000)
        # Der junge Lauf bleibt als Detailzeile stehen.
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM items").fetchone()[0], 1)

    def test_verdichten_ist_wiederholbar(self):
        old = datetime.now() - timedelta(days=cfg.HISTORY_DETAIL_DAYS + 5)
        with history.run_ctx(self.conn, timestamp=old) as run_id:
            history.write_items(self.conn, run_id, [self._row()])
        limit = (datetime.now() - timedelta(days=cfg.HISTORY_DETAIL_DAYS)).strftime("%Y-%m-%d")
        history.condense_until(self.conn, limit)
        history.condense_until(self.conn, limit)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM daily").fetchone()[0], 1)

    def test_alte_orderbuecher_verschwinden_frueher_als_details(self):
        old = datetime.now() - timedelta(days=cfg.HISTORY_ORDERBOOK_DAYS + 2)
        with history.run_ctx(self.conn, timestamp=old) as run_id:
            history.write_items(self.conn, run_id, [self._row()])
            history.write_orderbook(
                self.conn, run_id,
                [{"item": "oak", "item_id": 1, "kauf": [(76, 10)], "verkauf": []}])
        history.tidy_up(self.conn)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM orderbook").fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM items").fetchone()[0], 1)

    def test_hoechstens_hundert_laufprotokolle(self):
        for _ in range(cfg.HISTORY_RUN_LIMIT + 5):
            with history.run_ctx(self.conn) as run_id:
                history.write_items(self.conn, run_id, [self._row()])
        history.tidy_up(self.conn)
        count = self.conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        self.assertEqual(count, cfg.HISTORY_RUN_LIMIT)

    def test_verlauf_liest_details_und_tageswerte(self):
        with history.run_ctx(self.conn) as run_id:
            history.write_items(self.conn, run_id, [self._row()])
        entries = history.trend_rows(self.conn, "oak")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["quelle"], "detail")
        self.assertAlmostEqual(entries[0]["gold_h"], 1000)

    def test_leere_werte_bleiben_leer(self):
        """Ein fehlendes Gold/h ist nicht 0 – auch nicht in der Datenbank."""
        with history.run_ctx(self.conn) as run_id:
            history.write_items(self.conn, run_id,
                                   [self._row(gold_h=None, gold_h_real=float("nan"))])
        line = self.conn.execute("SELECT gold_h, gold_h_real FROM items").fetchone()
        self.assertIsNone(line["gold_h"])
        self.assertIsNone(line["gold_h_real"])


class ExtendedJsonTest(unittest.TestCase):
    """Die Spiel-API schreibt Mongo-Shell-JSON, und ein Update darf den Lauf
    nicht beenden.

    Hier stand eine Regex, die genau `ObjectId` kannte — als die Achievements
    `NumberLong(0)` mitbrachten, brach die Analyse ab, obwohl sie diese Felder
    nie liest. Dieselben Faelle stehen in `tests/vertrag/katalog.py` fuer den
    Zwilling in `tools/catalog.py`; die beiden Kopien duerfen nicht
    auseinanderlaufen.
    """

    RAW = ('{"_id": ObjectId("61e2b1b0"), "n": NumberLong(0), "m": NumberLong("42"),'
           ' "d": NumberDecimal("1.5"), "t": "nutze ObjectId(\\"x\\") hier",'
           ' "u": NumberFoo(3), "w": Timestamp(1, 2), "leer": ISODate()}')

    def test_bekannte_huellen_werden_uebersetzt(self):
        data, hints = extended_json.load(self.RAW)
        self.assertEqual(data["_id"], "61e2b1b0")
        self.assertEqual(data["n"], 0)
        self.assertEqual(data["m"], 42)        # mit Anfuehrungszeichen: trotzdem Zahl
        self.assertEqual(data["d"], 1.5)
        self.assertIsNone(data["leer"])

    def test_konstrukt_im_string_bleibt_text(self):
        data, _ = extended_json.load(self.RAW)
        self.assertEqual(data["t"], 'nutze ObjectId("x") hier')

    def test_unbekanntes_ueberlebt_und_wird_gemeldet(self):
        data, hints = extended_json.load(self.RAW)
        self.assertEqual(data["u"], 3)                    # ein Skalar bleibt der Skalar
        self.assertEqual(data["w"], "Timestamp(1, 2)")    # mehrere Argumente: als Text
        self.assertEqual(len(hints), 2)
        self.assertIn("NumberFoo", hints[0])
        self.assertIn("Timestamp", hints[1])

    def test_bekanntes_erzeugt_keinen_hinweis(self):
        _, hints = extended_json.load('{"a": ObjectId("ab"), "b": NumberLong(7)}')
        self.assertEqual(hints, [])

    def test_der_echte_achievement_block(self):
        """Wortlaut der Zeile, an der der Lauf am 12.09.2026 abbrach."""
        raw = ('{"Achievements": [{"Name": "achievement_tutorial_completed", '
               '"CriteriaThreshold" : NumberLong(0), "CriteriaTaskIds" : [], '
               '"CriteriaValue" : NumberLong(100)}]}')
        data, hints = extended_json.load(raw)
        self.assertEqual(data["Achievements"][0]["CriteriaValue"], 100)
        self.assertEqual(hints, [])

    def test_unparsbares_wirft_weiterhin(self):
        """Uebersetzt wird, was uebersetzbar ist — kaputtes JSON bleibt ein Fehler."""
        import json
        with self.assertRaises(json.JSONDecodeError):
            extended_json.load('{"a": NumberLong(1), "b": }')


try:                                    # braucht pandas/requests/openpyxl - lokal ja, in CI nicht
    from market_analysis import analysis as _analysis
    import pandas as _pd
except ImportError:                     # pragma: no cover - wird gesagt, nicht verschwiegen
    _analysis = _pd = None


@unittest.skipUnless(_analysis, "pandas/requests/openpyxl fehlen - Messungs-Rangfolge uebersprungen")
class MeasurementRankingTest(unittest.TestCase):
    """Jede Messung kommt ins Blatt, und die Rangfolge haelt ihr Versprechen.

    Gemeldet als „nur zehn Items haben Gold/h, der Rest ist leer": gemessen wurden
    30, die Begruendung auf zehn gekuerzt, und die Empfehlung zog ihre Zahl aus der
    gekuerzten Liste. Dazu wendete der gemessene Rang die Abwertung aus
    `SKILL_RELIABILITY` nie an - bei zehn Zeilen unsichtbar, ueber den ganzen
    Bestand ein Papaya-Feld auf Platz 1.
    """

    @staticmethod
    def _recommendation(lines):
        columns = ["Rang", "Item", "Skills", "Gold/h", "Verkauf an", "NPC-Preis",
                   "Stück/h", "Erlös pro Stück", "Spieler-Gebot (brutto)",
                   "Verlässlichkeit", "Warnung"]
        df = _pd.DataFrame([dict(zip(columns, z)) for z in lines])
        df["Gold/h gewichtet"] = df["Gold/h"] * df["Verlässlichkeit"]
        return df

    def test_kandidaten_sind_alle_mit_gold_und_der_deckel_gilt(self):
        df = self._recommendation([
            (1, "a", "Mining", 300, "NPC-Vendor", 3, 100, 3, None, 1.0, None),
            (2, "b", "Mining", 200, "NPC-Vendor", 2, 100, 2, None, 1.0, None),
            (3, "c", "Mining", 0, "NPC-Vendor", 0, 100, 0, None, 1.0, None),
            (4, "d", "Mining", -50, "NPC-Vendor", 0, 100, 0, None, 1.0, None),
        ])
        old = _analysis.REASON_CANDIDATES
        try:
            _analysis.REASON_CANDIDATES = 0
            self.assertEqual(list(_analysis.reason_candidates(df)["Item"]), ["a", "b"])
            _analysis.REASON_CANDIDATES = 1
            self.assertEqual(list(_analysis.reason_candidates(df)["Item"]), ["a"])
        finally:
            _analysis.REASON_CANDIDATES = old

    def test_jede_messung_kommt_in_die_empfehlung(self):
        """Zwoelf gemessen -> zwoelf Werte im Blatt, nicht die ersten zehn.

        Mehr als zehn, weil genau dort der alte `.head(REASON_TOP_N)` schnitt."""
        names = [f"item{i:02d}" for i in range(1, 13)]
        df_rec = self._recommendation([
            (i, name, "Mining", 200 - i, "NPC-Vendor", 2 - i / 100, 100, 2, None, 1.0, None)
            for i, name in enumerate(names, start=1)] + [
            (13, "nichts", "Mining", 0, "NPC-Vendor", 0, 100, 0, None, 1.0, None)])
        df_chain = _pd.DataFrame({"Item": names + ["nichts"], "ItemID": range(1, 14),
                                  "RawMaterialCost/h": 0.0, "Nebenertrag/h": 0.0})
        old = _analysis.fetch_orderbook_depth
        try:
            _analysis.fetch_orderbook_depth = lambda item_id: None   # kein Netz noetig
            df_reason, _ = _analysis.build_reason_df(df_rec, df_chain)
        finally:
            _analysis.fetch_orderbook_depth = old
        self.assertEqual(len(df_reason), 12)
        out = _analysis.sort_by_measurement(df_rec, df_reason)
        source = dict(zip(out["Item"], out["Gold/h Quelle"]))
        self.assertEqual(sum(q == _analysis.SOURCE_ORDERBOOK for q in source.values()), 12)
        # Das Ungemessene steht trotzdem da - mit Papier-Wert und als solches markiert.
        self.assertEqual(int(out["Gold/h realistisch"].notna().sum()), 13)
        self.assertEqual(source["nichts"], _analysis.SOURCE_PAPER)
        self.assertEqual(list(out["Item"][:2]), ["item01", "item02"])
        self.assertEqual(list(out["Item"])[-1], "nichts")
        self.assertEqual(list(out["Rang"]), list(range(1, 14)))
        # Und die Begruendung traegt dieselben Nummern wie die Empfehlung.
        self.assertEqual(dict(zip(df_reason["Item"], df_reason["Rang"])),
                         {k: v for k, v in zip(out["Item"], out["Rang"]) if k != "nichts"})

    def test_sortiert_wird_ueber_die_angezeigte_zahl(self):
        """Ein gemessenes Item, das die Messung auf 50 drueckt, steht unter einem
        ungemessenen mit 200 auf dem Papier - nicht "Gemessene zuerst"."""
        df_rec = self._recommendation([
            (1, "gedrueckt", "Mining", 300, "Spieler", 0, 100, 3, 3, 1.0, None),
            (2, "papier", "Mining", 200, "Spieler", 0, 100, 2, 2, 1.0, None),
        ])
        df_reason = _pd.DataFrame({"Rang": [1], "Item": ["gedrueckt"], "Gold/h realistisch": [50]})
        out = _analysis.sort_by_measurement(df_rec, df_reason)
        self.assertEqual(list(out["Item"]), ["papier", "gedrueckt"])
        self.assertEqual(list(out["Gold/h realistisch"]), [200, 50])
        self.assertEqual(list(out["Gold/h Quelle"]), [_analysis.SOURCE_PAPER, _analysis.SOURCE_ORDERBOOK])
        self.assertEqual(int(df_reason.loc[0, "Rang"]), 2)

    def test_ohne_messung_steht_der_papierwert_da(self):
        df_rec = self._recommendation([(1, "a", "Mining", 300, "Spieler", 0, 100, 3, 3, 1.0, None)])
        out = _analysis.sort_by_measurement(df_rec, _pd.DataFrame())
        self.assertEqual(list(out["Gold/h realistisch"]), [300])
        self.assertEqual(list(out["Gold/h Quelle"]), [_analysis.SOURCE_PAPER])

    def test_gemessener_rang_wendet_die_verlaesslichkeit_an(self):
        """NPC-Verkauf, kein Netz: gemessen = NPC-Preis x Stueck/h. Farming (0,5)
        bringt gemessen mehr und steht trotzdem hinter dem planbaren Item."""
        df_rec = self._recommendation([
            (1, "papaya", "Farming", 200, "NPC-Vendor", 2, 100, 2, None, 0.5, None),
            (2, "oak", "Woodcutting", 150, "NPC-Vendor", 1.5, 100, 1.5, None, 1.0, None),
        ])
        df_chain = _pd.DataFrame({"Item": ["papaya", "oak"], "ItemID": [1, 2],
                                  "RawMaterialCost/h": [0.0, 0.0], "Nebenertrag/h": [0.0, 0.0]})
        old = _analysis.fetch_orderbook_depth
        try:
            _analysis.fetch_orderbook_depth = lambda item_id: None
            df_reason, _ = _analysis.build_reason_df(df_rec, df_chain)
        finally:
            _analysis.fetch_orderbook_depth = old
        self.assertEqual(list(df_reason["Item"]), ["oak", "papaya"])
        self.assertEqual(list(df_reason["Rang"]), [1, 2])
        # Der WERT bleibt ungewichtet - abgewertet wird nur der Rang.
        self.assertEqual(int(df_reason.set_index("Item").loc["papaya", "Gold/h realistisch"]), 200)
        self.assertEqual(float(df_reason.set_index("Item").loc["papaya", "Verlässlichkeit"]), 0.5)


if __name__ == "__main__":
    unittest.main()
