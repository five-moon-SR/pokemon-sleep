from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch
import unittest

from utils.ingredient_coverage import (
    CLEAR_FOOD_SCORE_THRESHOLD,
    INGREDIENT_RECOMMENDATIONS,
    ingredient_recommendation_rows,
)


class IngredientRecommendationMapTest(unittest.TestCase):
    def test_contains_expected_species(self) -> None:
        self.assertIn("とくせんリンゴ", INGREDIENT_RECOMMENDATIONS)
        self.assertIn("ホゲータ", INGREDIENT_RECOMMENDATIONS["とくせんリンゴ"])


class IngredientClearTest(unittest.TestCase):
    def test_aaa_is_ideal(self) -> None:
        owned = [
            {
                "id": 1,
                "species_name": "ホゲータ",
                "nickname": "りんご班",
                "subskill_lv10": "食材確率アップS",
            }
        ]

        with (
            patch("utils.ingredient_coverage.db.list_all_ingredient_records", return_value=[
                {"name": "とくせんリンゴ"}
            ]),
            patch(
                "utils.ingredient_coverage.db.get_species_data",
                return_value={
                    "species_name": "ホゲータ",
                    "specialty": "食材",
                },
            ),
            patch(
                "utils.ingredient_coverage.composition_string",
                return_value="AAA",
            ),
            patch(
                "utils.ingredient_coverage.evaluate_potential",
                return_value=SimpleNamespace(
                    species_food=CLEAR_FOOD_SCORE_THRESHOLD + 1,
                    species_rank="A",
                ),
            ),
        ):
            rows = ingredient_recommendation_rows(owned)

        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].cleared)
        self.assertEqual(rows[0].status_label, "理想")
        self.assertIsNotNone(rows[0].best_clear_hit)
        self.assertEqual(rows[0].best_clear_hit.fit_label, "理想")

    def test_aab_is_immediate_and_aba_is_practical(self) -> None:
        owned = [
            {
                "id": 2,
                "species_name": "ホゲータ",
                "nickname": "りんご班",
                "subskill_lv10": "食材確率アップS",
            },
            {
                "id": 3,
                "species_name": "ホゲータ",
                "nickname": "りんご班2",
                "subskill_lv10": "食材確率アップS",
            },
        ]

        with (
            patch("utils.ingredient_coverage.db.list_all_ingredient_records", return_value=[
                {"name": "とくせんリンゴ"}
            ]),
            patch(
                "utils.ingredient_coverage.db.get_species_data",
                return_value={
                    "species_name": "ホゲータ",
                    "specialty": "食材",
                },
            ),
            patch(
                "utils.ingredient_coverage.composition_string",
                side_effect=["AAB", "ABA"],
            ),
            patch(
                "utils.ingredient_coverage.evaluate_potential",
                return_value=SimpleNamespace(
                    species_food=CLEAR_FOOD_SCORE_THRESHOLD + 5,
                    species_rank="A",
                ),
            ),
        ):
            rows = ingredient_recommendation_rows(owned)

        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].cleared)
        self.assertEqual(rows[0].status_label, "即戦力")
        self.assertEqual(rows[0].best_clear_hit.fit_label, "即戦力")


if __name__ == "__main__":
    unittest.main()
