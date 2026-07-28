from __future__ import annotations

import unittest

from utils.genki import (
    DAILY_EFFECTIVE_ASSIST_SECONDS,
    effective_assist_seconds,
    get_time_multiplier,
    heal_assist_boost,
)

# げんきオールS の Lv別回復量（utils/skill_effects.py と同じ値）
ALL_HEAL = {1: 5.0, 2: 7.0, 3: 9.0, 4: 11.4, 5: 15.0, 6: 18.1}


class HealApplicationTest(unittest.TestCase):
    """げんき回復を「おてつだい量の増分」へ換算する適用計算。

    以前は発動回数だけを引く固定表で、回復量を見ていなかった。
    そのため げんきオールS Lv1（5.0%）が Lv6（18.1%）と同じ加点になっていた。
    """

    def test_no_heal_keeps_the_calibrated_baseline(self) -> None:
        """回復なしの日は較正済みの定数そのまま。ここがズレると全数字が動く。"""
        self.assertEqual(effective_assist_seconds(), DAILY_EFFECTIVE_ASSIST_SECONDS)
        self.assertEqual(heal_assist_boost(0, 18.1), 0.0)
        self.assertEqual(heal_assist_boost(3, 0), 0.0)

    def test_boost_grows_with_skill_level(self) -> None:
        """Lvが上がるほど効く。固定表ではここが潰れていた。"""
        boosts = [heal_assist_boost(3, ALL_HEAL[lv]) for lv in sorted(ALL_HEAL)]
        self.assertEqual(boosts, sorted(boosts), "Lvに対して単調でない")
        self.assertGreater(
            boosts[-1], boosts[0] * 2,
            "Lv6がLv1の2倍未満。回復量が効いていない疑い",
        )

    def test_boost_grows_with_activation_count(self) -> None:
        boosts = [heal_assist_boost(n, 18.1) for n in range(6)]
        self.assertEqual(boosts, sorted(boosts), "発動回数に対して単調でない")

    def test_fractional_activations_interpolate(self) -> None:
        """げんきエールのように「発動数÷5」で小数になるケース。"""
        lo = heal_assist_boost(2, 18.1)
        hi = heal_assist_boost(3, 18.1)
        mid = heal_assist_boost(2.5, 18.1)
        self.assertGreater(mid, lo)
        self.assertLess(mid, hi)

    def test_saturates_because_of_the_150_cap(self) -> None:
        """げんきは150で頭打ちなので、回復量に対して線形には伸びない。"""
        small = heal_assist_boost(3, 10.0)
        large = heal_assist_boost(3, 100.0)
        self.assertLess(large, small * 10, "150上限を無視して線形に伸びている")

    def test_time_multiplier_bands(self) -> None:
        """帯の境界。ここがズレると回復の価値が丸ごと変わる。"""
        self.assertAlmostEqual(get_time_multiplier(150), 0.45)
        self.assertAlmostEqual(get_time_multiplier(81), 0.45)
        self.assertAlmostEqual(get_time_multiplier(80), 0.52)
        self.assertAlmostEqual(get_time_multiplier(41), 0.58)
        self.assertAlmostEqual(get_time_multiplier(40), 0.66)
        self.assertAlmostEqual(get_time_multiplier(0), 1.00)

    def test_matches_the_previous_hardcoded_table_in_shape(self) -> None:
        """旧実装の固定表は「げんきオールS Lv6」相当だったので、
        Lv6 で桁が合っていることを確かめる（完全一致は狙わない）。

        旧表: 1回 +9.93% / 3回 +27.71% / 5回 +38.63%
        """
        for count, old in ((1, 0.0993), (3, 0.2771), (5, 0.3863)):
            got = heal_assist_boost(count, ALL_HEAL[6])
            self.assertGreater(got, old * 0.5, f"{count}回: 旧表の半分未満（{got:.2%}）")
            self.assertLess(got, old * 1.5, f"{count}回: 旧表の1.5倍超（{got:.2%}）")


class SimulationWiringTest(unittest.TestCase):
    """回復スキルの種類ごとに、効く範囲が違うことを固定する。"""

    def test_heal_categories_are_disjoint(self) -> None:
        from utils.plan_simulation import (
            HEAL_CATEGORIES,
            RANDOM_HEAL_CATEGORIES,
            SELF_HEAL_CATEGORIES,
            TEAM_HEAL_CATEGORIES,
        )

        self.assertFalse(TEAM_HEAL_CATEGORIES & RANDOM_HEAL_CATEGORIES)
        self.assertFalse(TEAM_HEAL_CATEGORIES & SELF_HEAL_CATEGORIES)
        self.assertFalse(RANDOM_HEAL_CATEGORIES & SELF_HEAL_CATEGORIES)
        self.assertEqual(
            HEAL_CATEGORIES,
            TEAM_HEAL_CATEGORIES | RANDOM_HEAL_CATEGORIES | SELF_HEAL_CATEGORIES,
        )

    def test_random_heal_is_divided_across_the_party(self) -> None:
        """げんきエールはランダム1体なので、1体あたりは発動数÷5になる。

        同じ発動回数・同じ回復量なら、全体回復より必ず弱い。
        """
        team = heal_assist_boost(5, 20.0)
        random_one = heal_assist_boost(5 / 5, 20.0)
        self.assertLess(random_one, team)

    def test_multiple_healers_stack_sublinearly(self) -> None:
        """ヒーラー2体でも、単純な足し算にはならない（150上限があるため）。"""
        from utils.plan_simulation import _healer_boost

        single = _healer_boost([(3, 18.1)])
        double = _healer_boost([(3, 18.1), (3, 18.1)])
        self.assertGreater(double, single)
        self.assertLess(double, single * 2 + 1e-9)


if __name__ == "__main__":
    unittest.main()
