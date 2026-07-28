from __future__ import annotations

import json
import unittest
from pathlib import Path

import db
from utils.recipe_level import (
    LEVEL_MULTIPLIER,
    MAX_LEVEL,
    MIN_LEVEL,
    base_energy,
    clamp_level,
    clear_cache,
    get_recipe_level,
    level_multiplier,
    levels_signature,
    load_recipe_levels,
    recipe_energy,
    save_recipe_levels,
)

APP = Path(__file__).resolve().parent.parent
RECIPES = json.loads((APP / "data/recipe.json").read_text(encoding="utf-8"))["records"]
COOKABLE = [r for r in RECIPES if r.get("energy_lv1")]
MIXED = [r for r in RECIPES if not r.get("energy_lv1")]


class LevelTableTest(unittest.TestCase):
    """レシピレベルの倍率テーブル。全料理共通で、Lv1=1.00 / Lv30=1.61 / Lv60=3.03。"""

    def test_covers_every_level_up_to_cap(self) -> None:
        self.assertEqual(min(LEVEL_MULTIPLIER), MIN_LEVEL)
        self.assertEqual(max(LEVEL_MULTIPLIER), MAX_LEVEL)
        self.assertEqual(len(LEVEL_MULTIPLIER), MAX_LEVEL - MIN_LEVEL + 1)

    def test_is_monotonic(self) -> None:
        values = [LEVEL_MULTIPLIER[lv] for lv in range(MIN_LEVEL, MAX_LEVEL + 1)]
        self.assertEqual(values, sorted(values))

    def test_known_anchor_points(self) -> None:
        """出典（wikiwiki 料理）の代表値。ここがズレると全エナジーがズレる。"""
        for lv, expected in ((1, 1.00), (30, 1.61), (50, 2.42), (60, 3.03), (70, 3.58)):
            self.assertAlmostEqual(LEVEL_MULTIPLIER[lv], expected, places=6, msg=f"Lv{lv}")

    def test_clamp_handles_out_of_range_and_garbage(self) -> None:
        self.assertEqual(clamp_level(0), MIN_LEVEL)
        self.assertEqual(clamp_level(-5), MIN_LEVEL)
        self.assertEqual(clamp_level(999), MAX_LEVEL)
        self.assertEqual(clamp_level(None), MIN_LEVEL)
        self.assertEqual(clamp_level("なんか"), MIN_LEVEL)
        self.assertEqual(clamp_level("30"), 30)
        self.assertEqual(level_multiplier(999), LEVEL_MULTIPLIER[MAX_LEVEL])


class RecipeEnergyTest(unittest.TestCase):
    """マスターの実値と突き合わせる。倍率が狂ったら必ずここで落ちる。"""

    def test_level1_matches_master_base(self) -> None:
        for r in COOKABLE:
            self.assertAlmostEqual(
                recipe_energy(r, 1), float(r["energy_lv1"]), places=6, msg=r["name"]
            )

    def test_level30_and_60_match_master_within_rounding(self) -> None:
        """Lv30/Lv60 はマスターに実値がある。誤差は整数丸めぶんの1まで。"""
        for r in COOKABLE:
            for lv, key in ((30, "energy_lv30"), (60, "energy_lv60")):
                got = recipe_energy(r, lv)
                self.assertLessEqual(
                    abs(got - float(r[key])), 1.0,
                    f"{r['name']} Lv{lv}: 計算 {got:.1f} / マスター {r[key]}",
                )

    def test_mixed_recipes_are_zero_at_any_level(self) -> None:
        """ごちゃまぜ系はレシピレベルの恩恵を受けない（基準エナジーが0）。"""
        self.assertTrue(MIXED, "ごちゃまぜ系がマスターに見つからない")
        for r in MIXED:
            for lv in (1, 30, 60, 70):
                self.assertEqual(recipe_energy(r, lv), 0.0, f"{r['name']} Lv{lv}")

    def test_base_energy_can_be_recovered_from_lv30_or_lv60(self) -> None:
        """マスター更新の過渡期で energy_lv1 が欠けても基準値を拾える。"""
        sample = COOKABLE[0]
        only30 = {"name": sample["name"], "energy_lv30": sample["energy_lv30"]}
        only60 = {"name": sample["name"], "energy_lv60": sample["energy_lv60"]}
        for partial in (only30, only60):
            self.assertLessEqual(
                abs(base_energy(partial) - sample["energy_lv1"]), 1,
                f"{partial}: 基準エナジーを復元できていない",
            )

    def test_none_recipe_is_zero(self) -> None:
        self.assertEqual(recipe_energy(None), 0.0)


class SavedLevelsTest(unittest.TestCase):
    """保存済みレベルの読み書き（user_settings の user.recipe_levels）。"""

    def setUp(self) -> None:
        self._orig_get = db.get_setting
        self._orig_set = db.set_setting
        self.store: dict[str, object] = {}
        db.get_setting = lambda key, default=None: self.store.get(key, default)
        db.set_setting = lambda key, value: self.store.__setitem__(key, value)
        clear_cache()

    def tearDown(self) -> None:
        db.get_setting = self._orig_get
        db.set_setting = self._orig_set
        clear_cache()

    def test_unregistered_recipe_is_level_one(self) -> None:
        self.assertEqual(get_recipe_level("登録していない料理"), MIN_LEVEL)
        self.assertEqual(get_recipe_level(None), MIN_LEVEL)

    def test_saved_level_is_used_when_level_is_omitted(self) -> None:
        recipe = COOKABLE[0]
        save_recipe_levels({recipe["name"]: 30})
        self.assertEqual(get_recipe_level(recipe["name"]), 30)
        self.assertAlmostEqual(
            recipe_energy(recipe), recipe_energy(recipe, 30), places=6
        )
        # 未登録の料理は Lv1 のまま
        other = COOKABLE[1]
        self.assertAlmostEqual(
            recipe_energy(other), float(other["energy_lv1"]), places=6
        )

    def test_level_one_is_not_persisted(self) -> None:
        """Lv1 は既定値なので保存しない（設定を無駄に太らせない）。"""
        save_recipe_levels({"A": 1, "B": 30})
        self.assertEqual(load_recipe_levels(), {"B": 30})

    def test_out_of_range_levels_are_clamped_on_save(self) -> None:
        save_recipe_levels({"A": 999, "B": -3})
        self.assertEqual(load_recipe_levels(), {"A": MAX_LEVEL})

    def test_signature_changes_with_levels(self) -> None:
        """キャッシュキーに混ぜる署名。変わらないと古い結果が返り続ける。"""
        save_recipe_levels({"A": 10})
        first = levels_signature()
        save_recipe_levels({"A": 40})
        self.assertNotEqual(first, levels_signature())

    def test_cache_is_dropped_on_save(self) -> None:
        recipe = COOKABLE[0]
        self.assertEqual(get_recipe_level(recipe["name"]), MIN_LEVEL)
        save_recipe_levels({recipe["name"]: 60})
        self.assertEqual(get_recipe_level(recipe["name"]), 60, "保存後もキャッシュが残っている")


class LoadFailureTest(unittest.TestCase):
    """設定が読めない環境でも計算は動く。ただし黙って握り潰さない。"""

    def setUp(self) -> None:
        self._orig_get = db.get_setting

        def _boom(key, default=None):
            raise RuntimeError("DB_URL が未設定です")

        db.get_setting = _boom
        clear_cache()

    def tearDown(self) -> None:
        db.get_setting = self._orig_get
        clear_cache()

    def test_falls_back_to_level_one_and_records_the_reason(self) -> None:
        from utils.recipe_level import load_error

        recipe = COOKABLE[0]
        self.assertAlmostEqual(
            recipe_energy(recipe), float(recipe["energy_lv1"]), places=6
        )
        self.assertIsNotNone(load_error(), "失敗が記録されていない（UIが警告を出せない）")


if __name__ == "__main__":
    unittest.main()
