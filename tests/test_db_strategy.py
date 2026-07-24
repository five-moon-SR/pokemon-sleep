from __future__ import annotations

import unittest
from unittest.mock import patch

import db


class StrategyMigrationTest(unittest.TestCase):
    def test_single_legacy_category_is_migrated_to_key(self) -> None:
        with (
            patch.object(
                db,
                "_fetchall",
                return_value=[
                    {"id": 1, "recipe_categories": '["サラダ"]'},
                    {"id": 2, "recipe_categories": '["カレー・シチュー", "サラダ"]'},
                ],
            ),
            patch.object(db, "_execute") as execute,
        ):
            db._migrate_party_recipe_categories()
        execute.assert_called_once_with(
            "UPDATE party SET recipe_category = %s WHERE id = %s",
            ("salad", 1),
        )

    def test_duplicate_strategy_is_kept_as_legacy(self) -> None:
        rows = [
            {"id": 9, "field_name": "シアンの砂浜", "recipe_category": "salad"},
            {"id": 4, "field_name": "シアンの砂浜", "recipe_category": "salad"},
            {"id": 3, "field_name": "シアンの砂浜", "recipe_category": "curry_stew"},
        ]
        with (
            patch.object(db, "_fetchall", return_value=rows),
            patch.object(db, "_execute") as execute,
        ):
            db._normalize_strategy_plan_uniqueness()
        execute.assert_called_once_with(
            "UPDATE party SET recipe_category = NULL WHERE id = %s",
            (4,),
        )


if __name__ == "__main__":
    unittest.main()
