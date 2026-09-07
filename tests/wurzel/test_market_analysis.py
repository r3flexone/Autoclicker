"""Feste Referenzwerte für die reine Marktberechnung.

Alles hier läuft **ohne pandas** – das ist kein Zufall, sondern der Grund, warum
`pricing.py` und `history.py` überhaupt eigene Module sind. Die CI installiert
pandas nicht, und solange die rechnende Logik zwischen DataFrames und
Excel-Formatierung in `analyse.py` lag, lief sie in keinem einzigen Test.
"""

import unittest
from datetime import datetime, timedelta

from market_analysis import config as cfg
from market_analysis import history, pricing
from market_analysis.config import (
    COMPREHENSIVE_AVG_FIELDS, GOLD_ITEM_ID, net_player_price, spar_faktor,
)
from market_analysis.orderbook import patience_analysis, price_position, walk_orderbook
from market_analysis.recipes import kosten_faktor, normalize_recipe, skill_cfg


# Ein kleiner, vollständiger Markt: Bid/Ask/Volumen wie aus dem Bulk-Endpoint.
MARKT = {
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
        erwartet_best = 3 * cfg.SMITHING_SMELTING_COST_MULTIPLIER
        erwartet_worst_neben = 9 * cfg.ORE_STORAGE_COST_MULTIPLIER
        self.assertAlmostEqual(best["costs"][0]["Amount"], erwartet_best)
        self.assertAlmostEqual(worst["costs"][0]["Amount"], erwartet_best)
        self.assertAlmostEqual(worst["costs"][1]["Amount"], erwartet_worst_neben)

    def test_brewing_hat_werkzeug(self):
        """Brewing-Ausrüstung: mit Werkzeug, nicht mehr konservativ ohne."""
        self.assertTrue(skill_cfg("Brewing").has_tool)
        self.assertAlmostEqual(skill_cfg("Brewing").equipment_speed_boost,
                               cfg.EQUIPMENT_BASE_BOOST + cfg.EQUIPPED_TOOL_BONUS)


class ErsparnisTest(unittest.TestCase):
    """Storage-Boni und Potion of Trickery – Schalter und Kombination."""

    def test_spar_faktor_ist_multiplikativ(self):
        # 25% + 10% sparen zusammen 32.5%, nicht 35%.
        self.assertAlmostEqual(spar_faktor((True, 0.25), (True, 0.10)), 0.675)
        self.assertAlmostEqual(spar_faktor((False, 0.25), (True, 0.10)), 0.90)
        self.assertAlmostEqual(spar_faktor((False, 0.25), (False, 0.10)), 1.0)

    def test_potion_of_trickery_ist_25_prozent(self):
        """Update 18.08.2026: 25%, vorher waren 50% fest verdrahtet."""
        self.assertAlmostEqual(cfg.POTION_OF_TRICKERY_SAVE, 0.25)
        nur_trickery = spar_faktor((True, cfg.POTION_OF_TRICKERY_SAVE))
        self.assertAlmostEqual(nur_trickery, 0.75)

    def test_seed_storage_kombiniert_mit_trickery(self):
        mit_beiden = spar_faktor((True, cfg.POTION_OF_TRICKERY_SAVE),
                                 (True, cfg.SEED_STORAGE_SAVE))
        self.assertAlmostEqual(mit_beiden, 0.675)
        # Und der Schalter greift wirklich am Skill.
        self.assertAlmostEqual(skill_cfg("Farming").cost_multiplier,
                               cfg.FARMING_COST_MULTIPLIER)

    def test_ore_storage_kombiniert_mit_smelting_magic(self):
        """Beide sparen Erz an derselben Zeile – multiplikativ, nicht addiert."""
        mit_beiden = spar_faktor((True, 0.30), (True, 0.10))
        self.assertAlmostEqual(mit_beiden, 0.63)
        self.assertNotAlmostEqual(mit_beiden, 0.60)
        # Und der Konfigurationswert wird wirklich so gebildet – sonst prüft der
        # Test die Rechenregel, während die Config etwas anderes tut.
        self.assertAlmostEqual(
            cfg.SMITHING_SMELTING_COST_MULTIPLIER,
            spar_faktor((cfg.SMELTING_MAGIC_ACTIVE, cfg.SMELTING_MAGIC_SAVE),
                        (cfg.ORE_STORAGE_ACTIVE, cfg.ORE_STORAGE_SAVE)))

    def test_ore_storage_gilt_auch_ohne_smelting_magic(self):
        """Eine vom Perk ausgenommene Zeile verliert das Lager nicht mit.

        Gemessen mit EINGESCHALTETEN Upgrades (0,63 Schmelzen / 0,90 Lager). Mit den
        Standardwerten stehen beide auf 1.0, und der Test hielte auch dann, wenn die
        Regel die Zeile auf 1.0 zurückfallen liesse.
        """
        cfg_smith = skill_cfg("Smithing")
        ausgenommen = kosten_faktor(cfg_smith, True, 0, 10, "best", frozenset({10}),
                                    schmelz_faktor=0.63, lager_faktor=0.90)
        self.assertAlmostEqual(ausgenommen, 0.90)
        # Nebenzutat im Worst Case: ebenfalls nur das Lager, nicht der volle Preis.
        neben = kosten_faktor(cfg_smith, True, 1, 11, "worst", frozenset(),
                              schmelz_faktor=0.63, lager_faktor=0.90)
        self.assertAlmostEqual(neben, 0.90)
        # Die Erz-Zeile selbst bekommt beide Ersparnisse.
        erz = kosten_faktor(cfg_smith, True, 0, 10, "worst", frozenset(),
                            schmelz_faktor=0.63, lager_faktor=0.90)
        self.assertAlmostEqual(erz, 0.63)

    def test_kosten_faktor_ausserhalb_des_schmelzens(self):
        self.assertAlmostEqual(
            kosten_faktor(skill_cfg("Farming"), False, 0, 7, "best", frozenset(),
                          schmelz_faktor=0.63, lager_faktor=0.90),
            cfg.FARMING_COST_MULTIPLIER)


class SteuerTest(unittest.TestCase):
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
        nur_gebote = {"buy": 50, "sell": 0, "buyVol": 500, "sellVol": 0, "avg": 50}
        self.assertTrue(pricing.valid_sell_market(nur_gebote))
        self.assertFalse(pricing.valid_buy_market(nur_gebote))

    def test_kauf_ignoriert_die_gebotsseite(self):
        nur_angebote = {"buy": 0, "sell": 60, "buyVol": 0, "sellVol": 500, "avg": 60}
        self.assertTrue(pricing.valid_buy_market(nur_angebote))
        self.assertFalse(pricing.valid_sell_market(nur_angebote))

    def test_duennes_top_gebot_verwirft_den_marktpreis_nicht(self):
        """yew_log: 6.178 Stück am besten Gebot – früher unter MIN_SELL_VOLUME=10000.

        Ohne den Fix fiel das Item auf den NPC-Preis (20 x 1,155 = 23,1) zurück,
        obwohl 76 g geboten werden.
        """
        weg = pricing.effective_sell_price(100, MARKT, INFO, menge=1000)
        self.assertFalse(weg.an_npc)
        self.assertAlmostEqual(weg.preis, 76 * 0.99)
        self.assertGreater(weg.preis, weg.npc_preis)

    def test_npc_gewinnt_wenn_er_mehr_zahlt(self):
        info = dict(INFO)
        info[100] = dict(INFO[100], base_value=200)      # NPC: 231 > 75,24
        weg = pricing.effective_sell_price(100, MARKT, info, menge=1000)
        self.assertTrue(weg.an_npc)
        self.assertAlmostEqual(weg.preis, 200 * cfg.NPC_SELL_BOOST_MULTIPLIER)

    def test_duennes_gebot_ist_eine_frage_der_produktion(self):
        """Nicht 'unter 10.000 Stück', sondern 'reicht keine Stunde'."""
        markt = {"buy": 76, "sell": 90, "buyVol": 6178, "sellVol": 500, "avg": 78}
        self.assertFalse(pricing.duennes_top_gebot(markt, 200))     # 30 h Vorrat
        self.assertTrue(pricing.duennes_top_gebot(markt, 40000))    # 9 min
        self.assertFalse(pricing.duennes_top_gebot(markt, 0))
        self.assertFalse(pricing.duennes_top_gebot(None, 200))

    def test_ohne_jeden_weg_kommt_ein_grund(self):
        weg = pricing.effective_sell_price(500, MARKT, INFO)
        self.assertEqual(weg.preis, 0.0)
        self.assertIn("CanNotBeTraded", weg.grund)
        self.assertIn("CanNotBeSoldToGameShop", weg.grund)

    def test_vergleich_laeuft_netto_gegen_netto(self):
        """Spielergebot verliert Steuer, der NPC nicht – sonst wäre der Vergleich schief."""
        info = dict(INFO)
        info[100] = dict(INFO[100], base_value=65)       # NPC: 75,075
        weg = pricing.effective_sell_price(100, MARKT, info, menge=1000)
        self.assertAlmostEqual(weg.spieler_netto, 75.24)
        self.assertFalse(weg.an_npc)                     # 75,24 > 75,075, aber knapp


class ZutatenpreisTest(unittest.TestCase):
    def test_gold_ist_ein_item_und_kostet_eins(self):
        """API-Item 19 ist direktes Gold – früher als 'kein Markteintrag' mit 0 gerechnet."""
        self.assertEqual(GOLD_ITEM_ID, 19)
        preis, bekannt = pricing.zutat_preis(19, MARKT)
        self.assertTrue(bekannt)
        self.assertEqual(preis, 1.0)
        # Gegenprobe: ohne den Sonderfall wäre die Zeile "unbekannt" und die
        # Carpentry-Kosten fielen auf 0 zurück.
        self.assertFalse(pricing.zutat_preis(18, MARKT).bekannt)

    def test_fehlender_preis_ist_nicht_null(self):
        preis, bekannt = pricing.zutat_preis(999, MARKT)
        self.assertFalse(bekannt)
        self.assertEqual(preis, 0.0)

    def test_markteintrag_ohne_angebot_gilt_als_unbekannt(self):
        _, bekannt = pricing.zutat_preis(500, MARKT)
        self.assertFalse(bekannt)

    def test_goldkosten_landen_in_der_summe(self):
        bild = pricing.kosten_pro_aktion(
            [{"Item": 100, "Amount": 1}, {"Item": GOLD_ITEM_ID, "Amount": 250}],
            MARKT, item_info_map=INFO)
        self.assertTrue(bild.vollstaendig)
        self.assertAlmostEqual(bild.kosten, 90 + 250)

    def test_fehlende_zutat_macht_die_kosten_unvollstaendig(self):
        bild = pricing.kosten_pro_aktion(
            [{"Item": 100, "Amount": 1}, {"Item": 999, "Amount": 2}],
            MARKT, item_info_map=INFO)
        self.assertFalse(bild.vollstaendig)
        self.assertEqual(bild.fehlende, ("item_999",))
        self.assertAlmostEqual(bild.kosten, 90)       # nur die bekannte Zeile


class KettenTest(unittest.TestCase):
    """Komplette Ketten: Zeit, Kosten, Autarkie, Nebenertrag."""

    def setUp(self):
        self.rezepte = {
            100: _rezept("yew_log", "Woodcutting", 100, 8000),
            200: _rezept("tuna", "Fishing", 200, 9000),
            201: _rezept("cooked_tuna", "Cooking", 201, 3000,
                         costs=[{"Item": 200, "Amount": 1}]),
        }
        self.fisch = {200: 201}

    def test_einzelne_stufe_ohne_zutaten(self):
        k = pricing.resolve_chain(100, MARKT, self.rezepte, {}, INFO)
        self.assertTrue(k.autark)
        self.assertTrue(k.kosten_bekannt)
        self.assertEqual(k.kosten, 0.0)
        # Zeit für EIN Stück: die Aktionszeit geteilt durch die Ausbeute je Aktion.
        # Gegen das Rezept gerechnet statt gegen eine getippte Zahl – sonst prüft der
        # Test die Boost-Formel mit, und die hat ihren eigenen Test.
        rezept = self.rezepte[100]
        self.assertAlmostEqual(k.zeit_ms, rezept["base_time_ms"] / rezept["item_amount"])

    def test_zutat_wird_selbst_hergestellt_statt_gekauft(self):
        rezepte = dict(self.rezepte)
        rezepte[300] = _rezept("plank", "Carpentry", 300, 6000,
                               costs=[{"Item": 100, "Amount": 2}])
        k = pricing.resolve_chain(300, MARKT, rezepte, {}, INFO)
        self.assertTrue(k.autark)
        self.assertEqual(k.kosten, 0.0)            # Holz wird gefarmt, nicht gekauft
        self.assertEqual(len(k.schritte), 2)

    def test_gekaufte_zutat_bricht_die_autarkie(self):
        rezepte = {300: _rezept("ring", "Crafting", 300, 5000,
                                costs=[{"Item": 100, "Amount": 2}])}
        k = pricing.resolve_chain(300, MARKT, rezepte, {}, INFO)
        self.assertFalse(k.autark)
        self.assertGreater(k.kosten, 0.0)

    def test_gold_kostet_bricht_aber_die_autarkie_nicht(self):
        rezepte = {300: _rezept("plank", "Carpentry", 300, 6000,
                                costs=[{"Item": GOLD_ITEM_ID, "Amount": 250}])}
        k = pricing.resolve_chain(300, MARKT, rezepte, {}, INFO)
        self.assertTrue(k.autark)
        self.assertAlmostEqual(k.kosten, 250 / (1 * 1.05))     # je Stück Ausbeute
        self.assertEqual(k.liquiditaet, 0.0)       # Gold hat keinen Markt, der knapp wird

    def test_unbekannter_zutatenpreis_wird_gemeldet_nicht_genullt(self):
        rezepte = {300: _rezept("ring", "Crafting", 300, 5000,
                                costs=[{"Item": 999, "Amount": 2}])}
        k = pricing.resolve_chain(300, MARKT, rezepte, {}, INFO)
        self.assertFalse(k.kosten_bekannt)
        self.assertEqual(k.fehlende, ("item_999",))

    def test_auto_cook_verkauft_den_rohen_rest(self):
        """Ein Fischzug liefert je zur Hälfte gekocht und roh – der rohe Teil zählt."""
        k = pricing.resolve_chain(201, MARKT, self.rezepte, self.fisch, INFO)
        self.assertGreater(k.nebenertrag, 0.0)
        # Pro gekochtem Stück fällt genau ein rohes an (Chance 0,5).
        roh_pro_stueck = (1.0 - cfg.AUTO_COOK_CHANCE) / cfg.AUTO_COOK_CHANCE
        weg = pricing.effective_sell_price(200, MARKT, INFO, roh_pro_stueck)
        self.assertAlmostEqual(k.nebenertrag, roh_pro_stueck * weg.preis)

    def test_auto_cook_fischt_statt_zu_kochen(self):
        k = pricing.resolve_chain(201, MARKT, self.rezepte, self.fisch, INFO)
        self.assertEqual([s[1] for s in k.schritte], ["Fishing"])

    def test_auto_cook_abschaltbar(self):
        """Ohne den Schalter steht wieder die alte, pessimistische Rechnung da."""
        alt = pricing.AUTO_COOK_SELL_RAW_REST
        try:
            pricing.AUTO_COOK_SELL_RAW_REST = False
            k = pricing.resolve_chain(201, MARKT, self.rezepte, self.fisch, INFO)
            self.assertEqual(k.nebenertrag, 0.0)
        finally:
            pricing.AUTO_COOK_SELL_RAW_REST = alt

    def test_zyklus_bricht_die_rekursion(self):
        rezepte = {
            300: _rezept("a", "Crafting", 300, 1000, costs=[{"Item": 301, "Amount": 1}]),
            301: _rezept("b", "Crafting", 301, 1000, costs=[{"Item": 300, "Amount": 1}]),
        }
        k = pricing.resolve_chain(300, MARKT, rezepte, {}, INFO)
        self.assertFalse(k.autark)


class OrderbuchTest(unittest.TestCase):
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
        self.assertEqual(result["preis"], 119)
        self.assertAlmostEqual(result["wartezeit_h"], 2.0)
        position, trend = price_position(120, depth)
        self.assertAlmostEqual(position, 0.2)
        self.assertEqual(trend, "steigend")

    def test_preis_position_erwartet_brutto(self):
        """Netto gegen den Brutto-Schnitt zu halten meldet bei jedem Item -1%."""
        depth = {COMPREHENSIVE_AVG_FIELDS["Avg30D"]: 100}
        brutto, _ = price_position(100, depth)
        self.assertAlmostEqual(brutto, 0.0)
        netto, _ = price_position(net_player_price(100), depth)
        self.assertAlmostEqual(netto, -0.01)


class HistorieTest(unittest.TestCase):
    def setUp(self):
        self.conn = history.oeffne(":memory:")

    def tearDown(self):
        self.conn.close()

    def _zeile(self, item="oak", **rest):
        basis = {"item": item, "item_id": 1, "skill": "Woodcutting", "bid": 76,
                 "ask": 90, "npc_preis": 23, "kosten_h": 0, "gold_h": 1000,
                 "gold_h_real": 900, "verkaufsweg": "Spieler", "rang": 1,
                 "warnungen": ""}
        basis.update(rest)
        return basis

    def test_lauf_speichert_zeitpunkt_version_und_confighash(self):
        with history.lauf(self.conn) as run_id:
            history.schreibe_items(self.conn, run_id, [self._zeile()])
        lauf = history.letzte_laeufe(self.conn)[0]
        self.assertTrue(lauf["ts"])
        self.assertTrue(lauf["code_version"])
        self.assertEqual(len(lauf["config_hash"]), 12)
        self.assertEqual(lauf["items"], 1)

    def test_nur_erfolgreiche_laeufe_werden_uebernommen(self):
        with self.assertRaises(RuntimeError):
            with history.lauf(self.conn) as run_id:
                history.schreibe_items(self.conn, run_id, [self._zeile()])
                raise RuntimeError("Abbruch mitten im Lauf")
        self.assertEqual(history.letzte_laeufe(self.conn), [])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM items").fetchone()[0], 0)

    def test_config_hash_aendert_sich_mit_den_annahmen(self):
        class Anders:
            pass
        anders = Anders()
        for name in cfg.CONFIG_HASH_KEYS:
            setattr(anders, name, getattr(cfg, name, None))
        vorher = history.config_hash(anders)
        anders.POTION_OF_TRICKERY_SAVE = 0.5
        self.assertNotEqual(vorher, history.config_hash(anders))

    def test_orderbuch_nur_fuer_die_wichtigsten_kandidaten(self):
        buecher = [{"item": f"i{n}", "item_id": n, "kauf": [(10, 5)], "verkauf": []}
                   for n in range(5)]
        with history.lauf(self.conn) as run_id:
            history.schreibe_orderbuch(self.conn, run_id, buecher, top_n=2)
        ids = {z["item_id"] for z in
               self.conn.execute("SELECT item_id FROM orderbook").fetchall()}
        self.assertEqual(ids, {0, 1})

    def test_alte_details_werden_zu_tageswerten_und_verschwinden(self):
        alt = datetime.now() - timedelta(days=cfg.HISTORY_DETAIL_DAYS + 5)
        with history.lauf(self.conn, zeitpunkt=alt) as run_id:
            history.schreibe_items(self.conn, run_id, [self._zeile(gold_h=1000)])
        with history.lauf(self.conn) as run_id:
            history.schreibe_items(self.conn, run_id, [self._zeile(gold_h=2000)])

        bericht = history.aufraeumen(self.conn)
        self.assertEqual(bericht["verdichtet"], 1)
        self.assertEqual(bericht["items"], 1)
        tage = self.conn.execute("SELECT tag, gold_h FROM daily").fetchall()
        self.assertEqual(len(tage), 1)
        self.assertAlmostEqual(tage[0]["gold_h"], 1000)
        # Der junge Lauf bleibt als Detailzeile stehen.
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM items").fetchone()[0], 1)

    def test_verdichten_ist_wiederholbar(self):
        alt = datetime.now() - timedelta(days=cfg.HISTORY_DETAIL_DAYS + 5)
        with history.lauf(self.conn, zeitpunkt=alt) as run_id:
            history.schreibe_items(self.conn, run_id, [self._zeile()])
        grenze = (datetime.now() - timedelta(days=cfg.HISTORY_DETAIL_DAYS)).strftime("%Y-%m-%d")
        history.verdichte_bis(self.conn, grenze)
        history.verdichte_bis(self.conn, grenze)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM daily").fetchone()[0], 1)

    def test_alte_orderbuecher_verschwinden_frueher_als_details(self):
        alt = datetime.now() - timedelta(days=cfg.HISTORY_ORDERBOOK_DAYS + 2)
        with history.lauf(self.conn, zeitpunkt=alt) as run_id:
            history.schreibe_items(self.conn, run_id, [self._zeile()])
            history.schreibe_orderbuch(
                self.conn, run_id,
                [{"item": "oak", "item_id": 1, "kauf": [(76, 10)], "verkauf": []}])
        history.aufraeumen(self.conn)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM orderbook").fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM items").fetchone()[0], 1)

    def test_hoechstens_hundert_laufprotokolle(self):
        for _ in range(cfg.HISTORY_RUN_LIMIT + 5):
            with history.lauf(self.conn) as run_id:
                history.schreibe_items(self.conn, run_id, [self._zeile()])
        history.aufraeumen(self.conn)
        anzahl = self.conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        self.assertEqual(anzahl, cfg.HISTORY_RUN_LIMIT)

    def test_verlauf_liest_details_und_tageswerte(self):
        with history.lauf(self.conn) as run_id:
            history.schreibe_items(self.conn, run_id, [self._zeile()])
        eintraege = history.verlauf(self.conn, "oak")
        self.assertEqual(len(eintraege), 1)
        self.assertEqual(eintraege[0]["quelle"], "detail")
        self.assertAlmostEqual(eintraege[0]["gold_h"], 1000)

    def test_leere_werte_bleiben_leer(self):
        """Ein fehlendes Gold/h ist nicht 0 – auch nicht in der Datenbank."""
        with history.lauf(self.conn) as run_id:
            history.schreibe_items(self.conn, run_id,
                                   [self._zeile(gold_h=None, gold_h_real=float("nan"))])
        zeile = self.conn.execute("SELECT gold_h, gold_h_real FROM items").fetchone()
        self.assertIsNone(zeile["gold_h"])
        self.assertIsNone(zeile["gold_h_real"])


if __name__ == "__main__":
    unittest.main()
