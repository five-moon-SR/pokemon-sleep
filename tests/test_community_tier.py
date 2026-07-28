from __future__ import annotations

import unittest

from utils.community_tier import (
    MIN_RELIABLE_SOURCES,
    TIER_ORDER,
    TIER_WEIGHT,
    get_tier,
    get_tier_detail,
    is_reliable,
    tier_weight,
    top_tier_species,
)


class CommunityTierTest(unittest.TestCase):
    """人間評価4ソースを統合した独自ティアのアクセサ。"""

    def test_top_tier_is_ordered_by_tier_then_score(self) -> None:
        items = top_tier_species("SS")
        self.assertTrue(items, "SS帯が空になっている")
        tiers = [t for _, t in items]
        self.assertEqual(tiers, sorted(tiers, key=TIER_ORDER.index))

    def test_unanimous_species_are_top_tier(self) -> None:
        """全ソースが最上位に置いた種族はSSに来る。"""
        for name in ("サーナイト", "カイリュー"):
            self.assertEqual(get_tier(name), "SS", f"{name} がSSでない")

    def test_detail_exposes_per_source_breakdown(self) -> None:
        d = get_tier_detail("サーナイト")
        self.assertIsNotNone(d)
        self.assertGreaterEqual(d["sources"], MIN_RELIABLE_SOURCES)
        self.assertTrue(d["by_source"], "ソース内訳が空")
        self.assertIn(d["tier"], TIER_ORDER)

    def test_skill_type_pokemon_are_not_buried(self) -> None:
        """計算ティア(食材軸)ではF帯だったスキル型が、人間評価では上位に来る。

        この逆転こそが人間評価へ切り替えた理由なので、退行しないよう固定する。
        """
        for name in ("ジバコイル", "ツボツボ"):
            self.assertIn(get_tier(name), {"SS", "S", "A"}, f"{name} が沈んでいる")

    def test_unknown_species_is_neutral(self) -> None:
        self.assertIsNone(get_tier("存在しないポケモン"))
        self.assertEqual(tier_weight("存在しないポケモン"), 1.0)

    def test_weight_is_monotonic_in_tier(self) -> None:
        ws = [TIER_WEIGHT[t] for t in TIER_ORDER]
        self.assertEqual(ws, sorted(ws, reverse=True))

    def test_single_source_species_are_excluded_by_default(self) -> None:
        """1ソースのみの種族は多数決が成立しないので既定では出さない。"""
        strict = {n for n, _ in top_tier_species("D", reliable_only=True)}
        loose = {n for n, _ in top_tier_species("D", reliable_only=False)}
        self.assertTrue(loose - strict, "参考値の種族が1件も除外されていない")
        for n in strict:
            self.assertTrue(is_reliable(n))




class PreEvolutionTest(unittest.TestCase):
    """進化前の逆引き（捕獲方針で「進化前なら持っている」を出すのに使う）。"""

    def test_three_stage_line(self) -> None:
        from utils.evaluator import pre_evolutions_of
        self.assertEqual(pre_evolutions_of("フシギバナ"), ("フシギダネ", "フシギソウ"))

    def test_two_stage_line(self) -> None:
        from utils.evaluator import pre_evolutions_of
        self.assertEqual(pre_evolutions_of("サンドパン"), ("サンド",))

    def test_base_form_has_none(self) -> None:
        from utils.evaluator import pre_evolutions_of
        self.assertEqual(pre_evolutions_of("フシギダネ"), ())

    def test_standalone_species_has_none(self) -> None:
        from utils.evaluator import pre_evolutions_of
        for n in ("カモネギ", "メタモン", "ダークライ"):
            self.assertEqual(pre_evolutions_of(n), (), f"{n} に進化前がある扱いになっている")

    def test_branching_line_collects_all_paths(self) -> None:
        """イーブイ系のような分岐でも、手前の種を取りこぼさない。"""
        from utils.evaluator import pre_evolutions_of
        self.assertIn("イーブイ", pre_evolutions_of("エーフィ"))

    def test_no_self_reference(self) -> None:
        from utils.evaluator import pre_evolutions_of
        for n in ("フシギバナ", "エーフィ", "サンドパン"):
            self.assertNotIn(n, pre_evolutions_of(n))


if __name__ == "__main__":
    unittest.main()
