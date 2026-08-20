"""Feste Referenzwerte für die reine Marktberechnung."""

import unittest

from market_analysis.config import COMPREHENSIVE_AVG_FIELDS
from market_analysis.orderbook import patience_analysis, price_position, walk_orderbook
from market_analysis.recipes import normalize_recipe


class MarketAnalysisTest(unittest.TestCase):
    def test_mining_recipe_reference_values(self):
        recipe = normalize_recipe("Mining", {
            "Name": "reference_ore", "BaseTime": 10000,
            "ItemReward": 1, "ItemAmount": 2, "ExpReward": 100,
            "Costs": [],
        })
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
        for actual, expected in zip(
                [c["Amount"] for c in best["costs"]], [2.1, 6.3]):
            self.assertAlmostEqual(actual, expected)
        for actual, expected in zip(
                [c["Amount"] for c in worst["costs"]], [2.1, 9.0]):
            self.assertAlmostEqual(actual, expected)

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


if __name__ == "__main__":
    unittest.main()
