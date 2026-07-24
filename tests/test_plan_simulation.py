from __future__ import annotations

import unittest

import db
from utils.plan_simulation import simulate_plan
from utils.play_context import PlayContext


def owned(species: str, *, level: int = 60, skill_level: int = 6) -> dict:
    master = db.get_species_data(species) or {}
    ingredients = master.get("ingredients") or {}
    a = (ingredients.get("a") or {}).get("name")
    b = (ingredients.get("b") or {}).get("name") or a
    c = (ingredients.get("c") or {}).get("name") or a
    return {
        "id": hash((species, level, skill_level)),
        "species_name": species,
        "nickname": species,
        "current_level": level,
        "level": level,
        "nature": "きまぐれ (無補正)",
        "main_skill_name": master.get("main_skill"),
        "main_skill_level": skill_level,
        "ingredient_1": a,
        "ingredient_2": b,
        "ingredient_3": c,
        "sleep_ribbon_stage": 0,
    }


class PlanSimulationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = PlayContext(pot_capacity=69)
        self.recipes = db.list_all_recipe_records()

    def recipe(self, predicate):
        return next(r for r in self.recipes if r.get("ingredients") and predicate(r))

    def test_healer_changes_team_activity(self) -> None:
        recipe = self.recipe(lambda r: r["name"] == "とくせんリンゴカレー")
        members = [
            owned("ニンフィア"),
            owned("ライチュウ"),
            owned("ライチュウ"),
            owned("ライチュウ"),
            owned("ライチュウ"),
        ]
        result = simulate_plan(
            members, recipe, fav_berries={"ウブのみ"}, ctx=self.ctx
        )
        self.assertGreater(result.healer_activation_per_day, 0)
        self.assertGreater(result.healer_team_boost, 0)

    def test_pot_skill_unlocks_conditional_recipe(self) -> None:
        recipe = self.recipe(lambda r: int(r.get("total_ingredients") or 0) > 69)
        members = [
            owned("ジバコイル"),
            owned("ジバコイル"),
            owned("ジバコイル"),
            owned("ジバコイル"),
            owned("ジバコイル"),
        ]
        inventory = {
            ing["name"]: float(ing["count"]) * 21
            for ing in recipe["ingredients"]
        }
        result = simulate_plan(
            members,
            recipe,
            fav_berries=set(),
            ctx=self.ctx,
            starting_inventory=inventory,
        )
        self.assertGreater(result.pot_activation_per_day, 0)
        self.assertGreater(result.conditional_pot_meals, 0)

    def test_cooking_chance_is_reported(self) -> None:
        recipe = self.recipe(lambda r: r["name"] == "とくせんリンゴカレー")
        members = [owned("デデンネ") for _ in range(5)]
        result = simulate_plan(
            members,
            recipe,
            fav_berries=set(),
            ctx=self.ctx,
            starting_inventory={"とくせんリンゴ": 200},
        )
        self.assertGreater(result.chance_activation_per_day, 0)
        self.assertGreater(result.chance_bonus_per_activation, 0)

    def test_future_level_never_reduces_unlocked_supply(self) -> None:
        recipe = self.recipe(lambda r: r["name"] == "とくせんリンゴカレー")
        members = [owned("ホゲータ", level=10) for _ in range(5)]
        current = simulate_plan(members, recipe, fav_berries=set(), ctx=self.ctx)
        future = simulate_plan(
            members,
            recipe,
            fav_berries=set(),
            ctx=self.ctx,
            future_level=60,
        )
        self.assertGreaterEqual(
            sum(future.ingredient_supply.values()),
            sum(current.ingredient_supply.values()),
        )


if __name__ == "__main__":
    unittest.main()
