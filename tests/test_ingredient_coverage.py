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
    def test_aaa_and_high_food_score_clears_target(self) -> None:
        owned = [
            {
                "id": 1,
                "species_name": "ホゲータ",
                "nickname": "りんご班",
            }
        ]

        with (
            patch("utils.ingredient_coverage.db.list_all_ingredient_records", return_value=[
                {"name": "とくせんリンゴ"}
            ]),
            patch(
                "utils.ingredient_coverage.db.get_species_data",
                return_value={"species_name": "ホゲータ"},
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
        self.assertEqual(rows[0].status_label, "クリア")
        self.assertIsNotNone(rows[0].best_clear_hit)
        self.assertEqual(rows[0].best_clear_hit.label, "りんご班")

    def test_non_aaa_or_low_score_is_not_cleared(self) -> None:
        owned = [
            {
                "id": 2,
                "species_name": "ホゲータ",
                "nickname": "りんご班",
            }
        ]

        with (
            patch("utils.ingredient_coverage.db.list_all_ingredient_records", return_value=[
                {"name": "とくせんリンゴ"}
            ]),
            patch(
                "utils.ingredient_coverage.db.get_species_data",
                return_value={"species_name": "ホゲータ"},
            ),
            patch(
                "utils.ingredient_coverage.composition_string",
                return_value="AAB",
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
        self.assertFalse(rows[0].cleared)
        self.assertEqual(rows[0].status_label, "要育成")
        self.assertIsNone(rows[0].best_clear_hit)
        self.assertIsNotNone(rows[0].best_any_hit)


if __name__ == "__main__":
    unittest.main()
