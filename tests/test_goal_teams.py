from __future__ import annotations

import unittest

from utils import goal_teams
from utils.goal_teams import MAX_STAGE, ribbon_progress, ribbon_thresholds, stage_from_hours


class RibbonThresholdTest(unittest.TestCase):
    """しきい値は data/sleep_ribbon.json を単一の出所にする。"""

    def test_thresholds_are_the_known_four(self) -> None:
        self.assertEqual(ribbon_thresholds(), [(1, 200.0), (2, 500.0), (3, 1000.0), (4, 2000.0)])

    def test_stage_from_hours(self) -> None:
        self.assertEqual(stage_from_hours(None), 0)
        self.assertEqual(stage_from_hours(0), 0)
        self.assertEqual(stage_from_hours(199), 0)
        self.assertEqual(stage_from_hours(200), 1)
        self.assertEqual(stage_from_hours(999), 2)
        self.assertEqual(stage_from_hours(2500), MAX_STAGE)


def _mon(species: str, *, hours=None, stage=0, pid=1) -> dict:
    return {
        "id": pid,
        "species_name": species,
        "sleep_hours": hours,
        "sleep_ribbon_stage": stage,
        "current_level": 30,
    }


class RibbonProgressTest(unittest.TestCase):
    def test_remaining_uses_entered_hours(self) -> None:
        r = ribbon_progress(_mon("ピチュー", hours=430))
        self.assertEqual(r.stage, 1)
        self.assertEqual(r.next_stage, 2)
        self.assertAlmostEqual(r.remaining_hours, 70.0)
        self.assertFalse(r.remaining_is_estimate)

    def test_missing_hours_is_the_pessimistic_estimate(self) -> None:
        """未入力は「今の段階に着いたばかり」＝いちばん遠い、と安全側に見る。

        逆（近いと仮定）にすると、実際は遠い個体を編成に呼び込んでしまう。
        """
        r = ribbon_progress(_mon("ピチュー", stage=1))
        self.assertTrue(r.remaining_is_estimate)
        self.assertAlmostEqual(r.remaining_hours, 300.0)  # 500 - 200

    def test_hours_win_over_a_stale_stage(self) -> None:
        """段階の登録が古くても、時間の方が進んでいればそちらを信じる。"""
        r = ribbon_progress(_mon("ピチュー", hours=1200, stage=1))
        self.assertEqual(r.stage, 3)
        self.assertEqual(r.next_stage, 4)

    def test_final_evolution_gains_no_speed(self) -> None:
        """最終進化形はどの段階でも時間短縮ゼロ（所持数だけ増える）。

        ここが崩れると「リボン日に最終進化形を連れて行け」という誤った推奨が出る。
        """
        pichu = ribbon_progress(_mon("ピチュー", hours=450))
        raichu = ribbon_progress(_mon("ライチュウ", hours=450))
        self.assertGreater(pichu.speed_gain, 0.0)
        self.assertEqual(raichu.speed_gain, 0.0)
        self.assertGreater(raichu.inventory_gain, 0)
        self.assertGreater(pichu.efficiency, raichu.efficiency)

    def test_maxed_individual_is_done(self) -> None:
        r = ribbon_progress(_mon("ピチュー", hours=2400, stage=4))
        self.assertTrue(r.done)
        self.assertIsNone(r.remaining_hours)


class RibbonPriorityTest(unittest.TestCase):
    def test_done_individuals_are_excluded(self) -> None:
        owned = [
            _mon("ピチュー", hours=2400, stage=4, pid=1),
            _mon("ピチュー", hours=450, pid=2),
        ]
        rows = goal_teams.ribbon_priorities(owned)
        self.assertEqual([r.pokemon["id"] for r in rows], [2])

    def test_nearly_there_beats_far_away(self) -> None:
        owned = [
            _mon("ピチュー", hours=210, pid=1),   # あと290h
            _mon("ピチュー", hours=490, pid=2),   # あと10h
        ]
        rows = goal_teams.ribbon_priorities(owned, sort_by="効率")
        self.assertEqual(rows[0].pokemon["id"], 2)

    def test_team_is_capped_at_five(self) -> None:
        owned = [_mon("ピチュー", hours=100 + i, pid=i) for i in range(9)]
        self.assertEqual(len(goal_teams.best_ribbon_team(owned)), 5)


class ShardTeamTest(unittest.TestCase):
    """かけらは週エナジー0扱いなので、専用の物差しが要る。"""

    def test_shard_skill_is_worth_zero_energy(self) -> None:
        from utils.skill_effects import ENERGY_PER_UNIT

        self.assertEqual(ENERGY_PER_UNIT[goal_teams.SHARD_CATEGORY], 0.0)

    def test_only_shard_holders_produce_shards(self) -> None:
        import db

        holder = None
        other = None
        for name in db.list_species_names():
            species = db.get_species_data(name) or {}
            mon = {"id": 1, "species_name": name, "current_level": 30, "main_skill_level": 3}
            category, _ = goal_teams._skill_effect(mon, species)
            if category == goal_teams.SHARD_CATEGORY and holder is None:
                holder = mon
            elif category not in goal_teams.HEAL_CATEGORIES and other is None:
                other = dict(mon, id=2)
            if holder and other:
                break
        self.assertIsNotNone(holder, "かけら型の種族がマスターに1つも無い")
        team = goal_teams.evaluate_shard_team([holder, other, other, other, other])
        by_role = {r.role for r in team.rows}
        self.assertIn("かけら", by_role)
        self.assertGreater(team.shards_per_day, 0)
        # かけら型以外は 0 でなければならない
        for row in team.rows:
            if row.role != "かけら":
                self.assertEqual(row.shards, 0.0)


if __name__ == "__main__":
    unittest.main()
