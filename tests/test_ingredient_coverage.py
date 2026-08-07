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
                    "ingredients": {
                        "a": {"name": "とくせんリンゴ", "qty": [2, 5, 7]},
                        "b": {"name": "げきからハーブ", "qty": [4, 6]},
                        "c": {"name": "マメミート", "qty": [8]},
                    },
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
            patch(
                "utils.ingredient_coverage.expected_ingredients_per_day",
                return_value={"とくせんリンゴ": 12.3},
            ),
            patch("utils.ingredient_coverage.final_evolution_of", return_value="ホゲータ"),
            patch("utils.ingredient_coverage.get_play_ctx", return_value=SimpleNamespace()),
        ):
            rows = ingredient_recommendation_rows(owned)

        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].cleared)
        self.assertEqual(rows[0].status_label, "理想")
        self.assertIsNotNone(rows[0].best_clear_hit)
        self.assertEqual(rows[0].best_clear_hit.fit_label, "理想")
        self.assertEqual(rows[0].best_clear_hit.lv60_target_per_day, 12.3)

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
                    "ingredients": {
                        "a": {"name": "とくせんリンゴ", "qty": [2, 5, 7]},
                        "b": {"name": "げきからハーブ", "qty": [4, 6]},
                        "c": {"name": "マメミート", "qty": [8]},
                    },
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
            patch(
                "utils.ingredient_coverage.expected_ingredients_per_day",
                return_value={"とくせんリンゴ": 9.8},
            ),
            patch("utils.ingredient_coverage.final_evolution_of", return_value="ホゲータ"),
            patch("utils.ingredient_coverage.get_play_ctx", return_value=SimpleNamespace()),
        ):
            rows = ingredient_recommendation_rows(owned)

        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].cleared)
        self.assertEqual(rows[0].status_label, "即戦力")
        self.assertEqual(rows[0].best_clear_hit.fit_label, "即戦力")
        self.assertEqual(rows[0].best_clear_hit.lv60_target_per_day, 9.8)

    def test_abb_is_ideal_for_b_slot_ingredient(self) -> None:
        owned = [
            {
                "id": 4,
                "species_name": "ウェーニバル",
                "nickname": "ねぎ班",
                "subskill_lv10": "食材確率アップS",
            }
        ]

        with (
            patch("utils.ingredient_coverage.db.list_all_ingredient_records", return_value=[
                {"name": "ふといながねぎ"}
            ]),
            patch(
                "utils.ingredient_coverage.db.get_species_data",
                return_value={
                    "species_name": "ウェーニバル",
                    "specialty": "食材",
                    "ingredients": {
                        "a": {"name": "ワカクサ大豆", "qty": [2, 5, 7]},
                        "b": {"name": "ふといながねぎ", "qty": [2, 4]},
                        "c": {"name": "ピュアなオイル", "qty": [6]},
                    },
                },
            ),
            patch(
                "utils.ingredient_coverage.composition_string",
                return_value="ABB",
            ),
            patch(
                "utils.ingredient_coverage.evaluate_potential",
                return_value=SimpleNamespace(
                    species_food=CLEAR_FOOD_SCORE_THRESHOLD + 2,
                    species_rank="A",
                ),
            ),
            patch(
                "utils.ingredient_coverage.expected_ingredients_per_day",
                return_value={"ふといながねぎ": 10.4},
            ),
            patch("utils.ingredient_coverage.final_evolution_of", return_value="ウェーニバル"),
            patch("utils.ingredient_coverage.get_play_ctx", return_value=SimpleNamespace()),
        ):
            rows = ingredient_recommendation_rows(owned)

        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].cleared)
        self.assertEqual(rows[0].status_label, "理想")
        self.assertIsNotNone(rows[0].best_clear_hit)
        self.assertEqual(rows[0].best_clear_hit.fit_label, "理想")
        self.assertEqual(rows[0].best_clear_hit.lv60_target_per_day, 10.4)


if __name__ == "__main__":
    unittest.main()
