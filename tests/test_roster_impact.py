from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

import db
from utils.play_context import load_play_context
from utils.roster_impact import (
    OTHER_PLAN_WEIGHT,
    THIS_WEEK_WEIGHT,
    baseline_insertions,
    item_impact_ranking,
    load_plan_portfolio,
)

APP = Path(__file__).resolve().parent.parent
MASTER = json.loads((APP / "data/pokemon_master.json").read_text(encoding="utf-8"))["records"]
RECIPES = json.loads((APP / "data/recipe.json").read_text(encoding="utf-8"))["records"]
FIELDS = json.loads((APP / "data/field.json").read_text(encoding="utf-8"))["records"]


def _mk(species: str, pid: int, *, level: int = 50, **over: Any) -> dict[str, Any]:
    row = {
        "id": pid,
        "species_name": species,
        "nickname": None,
        "level": level,
        "current_level": level,
        "caught_level": 10,
        "nature": "いじっぱり",
        "evolution_stage": 0,
        "main_skill_name": None,
        "main_skill_level": 3,
        "ingredient_1": None,
        "ingredient_2": None,
        "ingredient_3": None,
        "subskill_lv10": "食材確率アップS",
        "subskill_lv25": "おてつだいスピードS",
        "subskill_lv50": None,
        "subskill_lv75": None,
        "subskill_lv100": None,
        "sleep_ribbon_stage": 0,
        "daifuku_rank": None,
        "daifuku_evals_json": None,
        "daifuku_eval_type": None,
        "daifuku_eval_percent": None,
        "note": None,
        "created_at": "2026-07-01 00:00:00",
        "last_eval_species_total": None,
        "last_eval_global_total": None,
        "last_eval_version": None,
        "last_eval_computed_at": None,
    }
    row.update(over)
    return row


class RosterImpactTest(unittest.TestCase):
    """アイテム投資を「登録済みプランの週エナジー改善」で測る土台。

    DBは触らず、party / user_settings だけ差し替える
    （マスター・レシピ・フィールドは JSON 読みなので接続不要）。
    """

    def setUp(self) -> None:
        self._orig_parties = db.list_parties
        self._orig_setting = db.get_setting
        self._orig_all_settings = db.get_all_settings
        db.get_all_settings = dict  # プレイ設定は既定値でよい

        names = [m["species_name"] for m in MASTER[:20]]
        # 1〜5 が定番メンバー、6 以降はベンチ
        self.owned = [_mk(n, i + 1) for i, n in enumerate(names)]
        self.owned_by_id = {int(p["id"]): p for p in self.owned}

        recipe = max(RECIPES, key=lambda r: r.get("energy_lv60") or 0)
        self.parties = [
            {
                "id": 1,
                "name": "今週のやつ",
                "field_name": FIELDS[0]["name"],
                "recipe_category": "curry_stew",
                "member_ids": [1, 2, 3, 4, 5],
                "main_recipe": recipe["name"],
            },
            {
                "id": 2,
                "name": "別フィールド",
                "field_name": FIELDS[1]["name"],
                "recipe_category": "salad",
                "member_ids": [1, 2, 3, 4, 5],
                "main_recipe": recipe["name"],
            },
        ]
        db.list_parties = lambda: [dict(p) for p in self.parties]
        db.get_setting = lambda key, default=None: (
            {"plan_id": 1} if key == "user.active_strategy_week" else default
        )
        self.ctx = load_play_context()

    def tearDown(self) -> None:
        db.list_parties = self._orig_parties
        db.get_setting = self._orig_setting
        db.get_all_settings = self._orig_all_settings

    # -- プラン読み込み ---------------------------------------------------
    def test_portfolio_marks_this_week_and_weights_it_heavier(self) -> None:
        plans = load_plan_portfolio(self.owned_by_id, ctx=self.ctx)
        self.assertEqual(len(plans), 2)
        this_week = [p for p in plans if p.is_this_week]
        self.assertEqual([p.plan_id for p in this_week], [1])
        self.assertEqual(this_week[0].weight, THIS_WEEK_WEIGHT)
        self.assertEqual([p.weight for p in plans if not p.is_this_week], [OTHER_PLAN_WEIGHT])
        self.assertGreater(THIS_WEEK_WEIGHT, OTHER_PLAN_WEIGHT)

    def test_incomplete_plans_are_dropped(self) -> None:
        """5体揃っていない・主料理が無いプランは比較の土俵に乗せない。"""
        self.parties.append({
            "id": 3, "name": "作りかけ", "field_name": FIELDS[2]["name"],
            "recipe_category": "salad", "member_ids": [1, 2], "main_recipe": None,
        })
        plans = load_plan_portfolio(self.owned_by_id, ctx=self.ctx)
        self.assertEqual({p.plan_id for p in plans}, {1, 2})

    # -- 計測の中身 -------------------------------------------------------
    def test_item_is_applied_to_current_state_not_final_evolution(self) -> None:
        """進化前にたねを使っても、進化ぶんの伸びが手柄に混ざらない。

        最終進化Lv60へ射影した個体を差し込むと、アイテムではなく進化とレベルの
        効果を測ってしまう。これを踏むと数字が桁で狂うので固定しておく。
        """
        from utils.roster_impact import _variants_main_seed

        pre = _mk("フシギダネ", 99, level=25, main_skill_level=1)
        variants = _variants_main_seed(pre)
        self.assertTrue(variants)
        after = variants[0].mutate(pre)
        self.assertEqual(after["species_name"], "フシギダネ")
        self.assertEqual(after["current_level"], 25)
        self.assertEqual(after["main_skill_level"], 2)

    def test_bench_pokemon_can_rank_by_swapping_in(self) -> None:
        """ベンチでも、差し込んで伸びるなら候補に出る（0点に沈めない）。"""
        plans = load_plan_portfolio(self.owned_by_id, ctx=self.ctx)
        base_map = baseline_insertions(self.owned, plans, ctx=self.ctx)
        member_ids = {1, 2, 3, 4, 5}
        rows = item_impact_ranking(
            self.owned, "level", plans=plans, base_map=base_map, ctx=self.ctx
        )
        bench = [r for r in rows if r.pokemon_id not in member_ids and r.weighted_delta > 0]
        self.assertTrue(bench, "ベンチが一律0点になっている")
        self.assertTrue(all(r.enters_plan for r in bench))

    def test_member_is_replaced_in_place(self) -> None:
        """定番メンバーは同じ枠で差し替える（同じ個体が2体並ばない）。"""
        from utils.roster_impact import _best_insertion, _variants_level

        plans = load_plan_portfolio(self.owned_by_id, ctx=self.ctx)
        target = self.owned[0]  # id=1 は両プランのメンバー
        variant = _variants_level(_mk(target["species_name"], 1, level=25))[0].mutate(
            _mk(target["species_name"], 1, level=25)
        )
        energy, idx = _best_insertion(plans[0], variant, ctx=self.ctx)
        self.assertEqual(idx, 0, "メンバーなのに別枠へ差し込まれている")
        self.assertGreater(energy, 0)

    def test_baseline_is_best_insertion_without_item(self) -> None:
        """基準は「素のまま差し込んだ最良」。素で足りている個体にアイテムの手柄を付けない。"""
        plans = load_plan_portfolio(self.owned_by_id, ctx=self.ctx)
        base_map = baseline_insertions(self.owned, plans, ctx=self.ctx)
        for slot in plans:
            for p in self.owned:
                key = (int(p["id"]), slot.plan_id)
                self.assertIn(key, base_map)
                self.assertGreaterEqual(base_map[key], slot.baseline_energy)

    def test_no_plans_falls_back_to_evaluation(self) -> None:
        """プランが1件も無くても、評価値の伸びで並べて候補は出す。"""
        self.parties.clear()
        rows = item_impact_ranking(self.owned, "mint", ctx=self.ctx)
        self.assertTrue(rows, "プラン未登録だと候補が空になっている")
        self.assertTrue(all(r.weighted_delta == 0 for r in rows))
        deltas = [r.eval_delta for r in rows]
        self.assertGreater(max(deltas), 0)

    def test_subskill_seed_is_probability_weighted(self) -> None:
        """銀種は抽選なので、分岐の期待値になっている（最良値をそのまま出さない）。"""
        from utils.roster_impact import _variants_sub_seed

        p = _mk(MASTER[0]["species_name"], 1, level=60)
        variants = _variants_sub_seed(p)
        if not variants:
            self.skipTest("この個体には銀種の抽選対象が無い")
        total = sum(v.probability for v in variants)
        self.assertAlmostEqual(total, 1.0, places=6)

    def test_ranking_is_sorted_by_weighted_delta(self) -> None:
        plans = load_plan_portfolio(self.owned_by_id, ctx=self.ctx)
        base_map = baseline_insertions(self.owned, plans, ctx=self.ctx)
        rows = item_impact_ranking(
            self.owned, "main", plans=plans, base_map=base_map, ctx=self.ctx
        )
        values = [round(r.weighted_delta, 1) for r in rows]
        self.assertEqual(values, sorted(values, reverse=True))


if __name__ == "__main__":
    unittest.main()
