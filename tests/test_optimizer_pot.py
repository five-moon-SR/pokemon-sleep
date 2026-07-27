from __future__ import annotations

import unittest

from utils.optimizer import _effective_pot_capacity, _recipe_fits_pot


class EffectivePotCapacityTest(unittest.TestCase):
    """到達しうる鍋容量の上限＝素の容量＋1日ぶんの容量UP積み上げ。"""

    def test_without_pot_up_it_is_the_raw_capacity(self) -> None:
        self.assertEqual(_effective_pot_capacity(63, 0.0), 63.0)

    def test_pot_up_raises_the_ceiling_by_one_day_of_activations(self) -> None:
        self.assertEqual(_effective_pot_capacity(63, 17.0), 80.0)

    def test_no_capacity_means_no_ceiling(self) -> None:
        self.assertIsNone(_effective_pot_capacity(None, 17.0))


class RecipeFitsPotTest(unittest.TestCase):
    """鍋に入らない料理を主料理候補から外す判定。"""

    HUGE = {"name": "みつあつめチョコワッフル", "total_ingredients": 115}
    OVER = {"name": "れんごくコーンキーマカレー", "total_ingredients": 77}
    FITS = {"name": "ぜったいねむりバターカレー", "total_ingredients": 55}
    UNKNOWN = {"name": "ごちゃまぜカレー", "total_ingredients": None}

    def test_over_capacity_is_rejected_without_pot_up(self) -> None:
        self.assertFalse(_recipe_fits_pot(self.OVER, 63, 0.0))

    def test_within_capacity_is_accepted(self) -> None:
        self.assertTrue(_recipe_fits_pot(self.FITS, 63, 0.0))

    def test_boundary_is_inclusive(self) -> None:
        self.assertTrue(_recipe_fits_pot({"total_ingredients": 63}, 63, 0.0))
        self.assertFalse(_recipe_fits_pot({"total_ingredients": 64}, 63, 0.0))

    def test_pot_up_allows_overflow_within_its_reach(self) -> None:
        """77食材は、1日+17積める編成なら上限80に収まるので候補に残る。"""
        self.assertTrue(_recipe_fits_pot(self.OVER, 63, 17.0))

    def test_pot_up_does_not_allow_unreachable_recipes(self) -> None:
        """容量UPを積んでも115食材には届かない。青天井にはしない。"""
        self.assertFalse(_recipe_fits_pot(self.HUGE, 63, 17.0))
        self.assertFalse(_recipe_fits_pot(self.HUGE, 63, 40.0))

    def test_unknown_total_is_not_filtered(self) -> None:
        self.assertTrue(_recipe_fits_pot(self.UNKNOWN, 63, 0.0))

    def test_no_capacity_given_disables_the_filter(self) -> None:
        self.assertTrue(_recipe_fits_pot(self.HUGE, None, 0.0))


if __name__ == "__main__":
    unittest.main()
