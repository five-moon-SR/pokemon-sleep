from __future__ import annotations

import unittest
from typing import Any

import db
from utils.recipe_unlock import recipe_gaps


def _mk(species: str, pid: int, level: int = 60) -> dict[str, Any]:
    return {
        "id": pid, "species_name": species, "nickname": None,
        "level": level, "current_level": level, "caught_level": 10,
        "nature": None, "evolution_stage": 0,
        "main_skill_name": None, "main_skill_level": 3,
        "ingredient_1": None, "ingredient_2": None, "ingredient_3": None,
        "subskill_lv10": None, "subskill_lv25": None, "subskill_lv50": None,
        "subskill_lv75": None, "subskill_lv100": None,
        "sleep_ribbon_stage": 0, "is_shiny": False,
        "daifuku_rank": None, "daifuku_evals_json": None,
        "daifuku_eval_type": None, "daifuku_eval_percent": None, "note": None,
        "created_at": "2026-07-01 00:00:00",
        "last_eval_species_total": None, "last_eval_global_total": None,
        "last_eval_version": None, "last_eval_computed_at": None,
    }


class RecipeUnlockTest(unittest.TestCase):
    """「この料理を作るには誰が要るか」の逆引き。

    既存の capture_improvements は主料理を1品に固定するため、必要食材を
    2つ以上欠いた料理では素も候補も cooked=0 になり、差分が丸ごと 0 に潰れて
    「候補なし」と出ていた。ここはその穴を埋めるための経路なので、
    **作れない料理で候補が空にならないこと**を最優先で固定する。
    """

    def setUp(self) -> None:
        self._orig_settings = db.get_all_settings
        self._orig_get = db.get_setting
        db.get_all_settings = dict
        db.get_setting = lambda key, default=None: default
        self.recipes = [
            r for r in db.list_all_recipe_records()
            if r.get("category") == "salad" and r.get("ingredients")
        ]

    def tearDown(self) -> None:
        db.get_all_settings = self._orig_settings
        db.get_setting = self._orig_get

    def test_uncookable_recipe_still_names_the_species_needed(self) -> None:
        """手札がほぼ空でも、強い料理に対して「誰が要るか」が出る。"""
        gaps = recipe_gaps([_mk("フシギダネ", 1)], self.recipes, limit=5)
        self.assertTrue(gaps, "候補が空になっている（回帰）")
        uncookable = [g for g in gaps if not g.cookable]
        self.assertTrue(uncookable, "手札1体なのに全部作れる判定になっている")
        top = uncookable[0]
        self.assertTrue(top.missing, "不足食材が取れていない")
        self.assertTrue(
            any(m.candidates for m in top.missing),
            "不足食材を埋められる未所持種が1件も挙がっていない",
        )
        self.assertTrue(top.needed_species, "最短で狙う種が出ていない")

    def test_candidates_are_unowned_and_tier_sorted(self) -> None:
        """候補は未所持種のみ。ティアの高い順に並ぶ。"""
        owned_name = "カイリュー"
        gaps = recipe_gaps([_mk(owned_name, 1)], self.recipes, limit=8)
        order = {"SS": 0, "S": 1, "A": 2, "B": 3, "C": 4, "D": 5}
        for gap in gaps:
            for m in gap.missing:
                names = [cd["species_name"] for cd in m.candidates]
                self.assertNotIn(owned_name, names, "所持済みの種が候補に出ている")
                ranks = [order.get(cd["tier"] or "", 9) for cd in m.candidates]
                self.assertEqual(ranks, sorted(ranks), "ティア順になっていない")

    def test_sorted_by_energy_not_by_cookability(self) -> None:
        """並びはエナジー順。作れる料理を先に出すと強い料理が下に埋まる。"""
        gaps = recipe_gaps([_mk("フシギダネ", 1)], self.recipes, limit=8)
        energies = [g.energy_at_60 for g in gaps]
        self.assertEqual(energies, sorted(energies, reverse=True))

    def test_mixed_recipes_are_excluded(self) -> None:
        """ごちゃまぜ系は食材リストが空なので対象外。"""
        allr = db.list_all_recipe_records()
        gaps = recipe_gaps([_mk("フシギダネ", 1)], allr, limit=99)
        names = {g.recipe["name"] for g in gaps}
        self.assertNotIn("ごちゃまぜサラダ", names)

    def test_shortfall_never_negative(self) -> None:
        gaps = recipe_gaps([_mk("フシギダネ", 1)], self.recipes, limit=8)
        for gap in gaps:
            for m in gap.missing:
                self.assertGreater(m.shortfall, 0, "不足していない食材が missing に入っている")


if __name__ == "__main__":
    unittest.main()
