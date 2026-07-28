from __future__ import annotations

import unittest
from typing import Any

import db
from utils.release_candidates import (
    KEEP_TIER_AT_LEAST,
    MAX_PER_FINAL_SPECIES,
    release_candidates,
)


def _mk(species: str, pid: int, *, level: int = 30, **over: Any) -> dict[str, Any]:
    row = {
        "id": pid, "species_name": species, "nickname": None,
        "level": level, "current_level": level, "caught_level": 10,
        "nature": None, "evolution_stage": 0,
        "main_skill_name": None, "main_skill_level": 1,
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
    row.update(over)
    return row


class ReleaseCandidateTest(unittest.TestCase):
    """処分候補は「残す理由が1つも無い」個体だけ。

    削除は取り消せないので、除外条件が1つでも壊れると取り返しがつかない。
    条件ごとに1本ずつ固定する。
    """

    def setUp(self) -> None:
        self._orig = db.get_all_settings
        db.get_all_settings = dict
        # 同じ進化系統を多めに持たせて、下位が候補に落ちる状況を作る
        self.owned = [_mk("キャタピー", i + 1, level=20 + i) for i in range(5)]

    def tearDown(self) -> None:
        db.get_all_settings = self._orig

    def test_lower_duplicates_become_candidates(self) -> None:
        rows = release_candidates(self.owned)
        self.assertTrue(rows, "同系統を5体持っていても候補が出ない")
        self.assertLessEqual(
            len(rows), len(self.owned) - MAX_PER_FINAL_SPECIES,
            "上位を残さずに候補へ入れている",
        )

    def test_shiny_is_never_a_candidate(self) -> None:
        """色違いは弱くても必ず残す（Naoの明示指定）。"""
        weakest = min(self.owned, key=lambda p: p["current_level"])
        weakest["is_shiny"] = True
        ids = {r.pokemon_id for r in release_candidates(self.owned)}
        self.assertNotIn(int(weakest["id"]), ids, "色違いが処分候補に出ている")

    def test_plan_members_are_kept(self) -> None:
        ids_before = {r.pokemon_id for r in release_candidates(self.owned)}
        self.assertTrue(ids_before)
        keep = next(iter(ids_before))
        ids_after = {
            r.pokemon_id
            for r in release_candidates(self.owned, plan_member_ids={keep})
        }
        self.assertNotIn(keep, ids_after, "定番プランのメンバーが候補に出ている")

    def test_investable_individuals_are_kept(self) -> None:
        ids_before = {r.pokemon_id for r in release_candidates(self.owned)}
        keep = next(iter(ids_before))
        ids_after = {
            r.pokemon_id
            for r in release_candidates(self.owned, investable_ids={keep})
        }
        self.assertNotIn(keep, ids_after, "投資で伸びる個体が候補に出ている")

    def test_high_tier_species_are_kept(self) -> None:
        """ティアA以上の種は、今使っていなくても残す。"""
        from utils.community_tier import get_tier

        owned = [_mk("ミニリュウ", i + 1, level=20 + i) for i in range(5)]
        self.assertEqual(get_tier("カイリュー"), "SS", "前提が変わっている")
        rows = release_candidates(owned)
        self.assertFalse(rows, f"ティア{KEEP_TIER_AT_LEAST}以上の系統が候補に出ている")

    def test_sorted_weakest_first(self) -> None:
        rows = release_candidates(self.owned)
        totals = [r.potential_total for r in rows]
        self.assertEqual(totals, sorted(totals), "弱い順に並んでいない")

    def test_every_candidate_carries_its_reasons(self) -> None:
        """なぜ処分してよいのかを必ず添える（根拠なしで消させない）。"""
        for r in release_candidates(self.owned):
            self.assertTrue(r.reasons, f"{r.label} に根拠が付いていない")
            self.assertTrue(r.better_ones, f"{r.label} の上位互換が示されていない")


if __name__ == "__main__":
    unittest.main()
