from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

import db
from utils.party_logic import RECIPE_CATEGORY_LABELS
from utils.strategy_optimizer import generate_all_strategy_plans, plan_slots

APP = Path(__file__).resolve().parent.parent
MASTER = json.loads((APP / "data/pokemon_master.json").read_text(encoding="utf-8"))["records"]


def _mk(species: str, pid: int) -> dict[str, Any]:
    return {
        "id": pid, "species_name": species, "nickname": None,
        "level": 50, "current_level": 50, "caught_level": 10,
        "nature": "いじっぱり", "evolution_stage": 0,
        "main_skill_name": None, "main_skill_level": 3,
        "ingredient_1": None, "ingredient_2": None, "ingredient_3": None,
        "subskill_lv10": "食材確率アップS", "subskill_lv25": "おてつだいスピードS",
        "subskill_lv50": None, "subskill_lv75": None, "subskill_lv100": None,
        "sleep_ribbon_stage": 0, "daifuku_rank": None, "daifuku_evals_json": None,
        "daifuku_eval_type": None, "daifuku_eval_percent": None, "note": None,
        "created_at": "2026-07-01 00:00:00",
        "last_eval_species_total": None, "last_eval_global_total": None,
        "last_eval_version": None, "last_eval_computed_at": None,
    }


class BulkPlanGenerationTest(unittest.TestCase):
    """フィールド×料理カテゴリの全枠を自動生成する。

    保存だけ差し替えて、マスター・レシピ・フィールドは実データを使う。
    """

    def setUp(self) -> None:
        self._orig = {
            "list_pokemon": db.list_pokemon,
            "get_strategy_plan": db.get_strategy_plan,
            "upsert_strategy_plan": db.upsert_strategy_plan,
            "get_all_settings": db.get_all_settings,
            "list_all_field_records": db.list_all_field_records,
        }
        # 探索を回す本数を減らすため、フィールドは2つに絞る（枠 = 2 × 3カテゴリ）
        _fields = self._orig["list_all_field_records"]()[:2]
        db.list_all_field_records = lambda: [dict(f) for f in _fields]
        self.owned = [_mk(m["species_name"], i + 1) for i, m in enumerate(MASTER[:24])]
        self.saved: dict[tuple[str, str], dict[str, Any]] = {}
        self.next_id = 100

        def _upsert(data: dict[str, Any]) -> int:
            self.next_id += 1
            key = (data["field_name"], data["recipe_category"])
            self.saved[key] = {**data, "id": self.saved.get(key, {}).get("id", self.next_id)}
            return int(self.saved[key]["id"])

        db.list_pokemon = lambda: [dict(p) for p in self.owned]
        db.get_strategy_plan = lambda f, c: self.saved.get((f, c))
        db.upsert_strategy_plan = _upsert
        db.get_all_settings = dict

    def tearDown(self) -> None:
        for name, fn in self._orig.items():
            setattr(db, name, fn)

    def test_fills_every_slot_with_a_valid_plan(self) -> None:
        results = list(generate_all_strategy_plans())
        slots = plan_slots()
        self.assertEqual(len(results), len(slots))
        self.assertTrue(all(r.status == "created" for r in results), "全枠が新規生成にならない")

        recipes = {r["name"]: r for r in db.list_all_recipe_records()}
        for (field_name, category), saved in self.saved.items():
            self.assertEqual(len(saved["member_ids"]), 5, f"{field_name} の固定5体が揃っていない")
            self.assertEqual(len(set(saved["member_ids"])), 5, "同じ個体が重複している")
            self.assertIn(saved["main_recipe"], recipes)
            self.assertEqual(
                recipes[saved["main_recipe"]]["category"], category,
                f"{field_name} に別カテゴリの料理が入っている",
            )
            self.assertIn(RECIPE_CATEGORY_LABELS[category], saved["name"])

    def test_existing_plans_are_kept_unless_overwrite(self) -> None:
        """既定では手で組んだ編成を黙って壊さない。"""
        list(generate_all_strategy_plans())
        before = {k: dict(v) for k, v in self.saved.items()}
        # 1枠だけ手で書き換えた体にする
        key = next(iter(self.saved))
        self.saved[key]["main_recipe"] = "手で選んだ料理"

        again = list(generate_all_strategy_plans())
        self.assertTrue(all(r.status == "skipped" for r in again))
        self.assertEqual(self.saved[key]["main_recipe"], "手で選んだ料理")
        self.assertEqual(
            {k: v["member_ids"] for k, v in self.saved.items()},
            {k: v["member_ids"] for k, v in before.items()},
        )

    def test_overwrite_reports_what_changed(self) -> None:
        """上書き時は、変わった枠だけ前後が判るようにする。"""
        list(generate_all_strategy_plans())
        key = next(iter(self.saved))
        self.saved[key]["member_ids"] = [1, 2, 3, 4, 5]
        self.saved[key]["main_recipe"] = "ごちゃまぜカレー"

        results = list(generate_all_strategy_plans(overwrite=True))
        changed = [r for r in results if r.status == "updated"]
        self.assertEqual(len(changed), 1, "書き換えた1枠だけが変更扱いにならない")
        row = changed[0]
        self.assertEqual(row.prev_recipe, "ごちゃまぜカレー")
        self.assertTrue(row.recipe_changed)
        self.assertTrue(row.members_in or row.members_out, "メンバーの出入りが取れていない")
        # 決定的な探索なので、書き換えていない枠は「変更なし」に落ちる
        self.assertTrue(all(r.status == "unchanged" for r in results if r is not row))


if __name__ == "__main__":
    unittest.main()
