"""フィールド×料理カテゴリ攻略プランの7日間シミュレーション。

組み合わせ探索は optimizer の高速な期待値計算に任せ、このモジュールは採用候補を
食事時刻・食材在庫・鍋拡張・料理チャンス・げんきオール込みで精査する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import db
from utils.evaluator import (
    _assist_seconds_at_lv,
    _effective_skill_lv,
    _main_skill_category,
    _skill_proc_mult,
    _speed_mult,
)
from utils.food_expectation import (
    _effective_level,
    _individual_subs,
    expected_berry_per_day,
    expected_ingredients_per_day,
    find_food_origin,
    qty_at_slot,
)
from utils.genki import DAILY_EFFECTIVE_ASSIST_SECONDS
from utils.play_context import PlayContext
from utils.skill_effects import get_skill_effect_amount, get_skill_max_lv
from utils.skill_expectation import expected_skill_energy_per_day
from utils.sleep_ribbon import get_time_multiplier


COOKING_CATEGORIES = {"料理パワーアップS", "料理チャンスS", "料理アシスト"}
TEAM_HEAL_CATEGORIES = {"げんきオールS"}
BASE_GREAT_CHANCE = 0.10
MAX_GREAT_CHANCE = 0.70


@dataclass
class PlanSimulation:
    recipe_name: str
    cooked_meals: int
    total_meals: int
    stability: float
    dish_energy: float
    berry_energy: float
    skill_energy: float
    weekly_energy: float
    bottlenecks: list[str] = field(default_factory=list)
    ingredient_supply: dict[str, float] = field(default_factory=dict)
    ingredient_remaining: dict[str, float] = field(default_factory=dict)
    pot_activation_per_day: float = 0.0
    pot_bonus_per_activation: float = 0.0
    chance_activation_per_day: float = 0.0
    chance_bonus_per_activation: float = 0.0
    healer_activation_per_day: float = 0.0
    healer_team_boost: float = 0.0
    conditional_pot_meals: int = 0

    @property
    def cooked_per_day(self) -> float:
        return self.cooked_meals / 7.0


def _levelled(pokemon: dict[str, Any], level: int | None) -> dict[str, Any]:
    p = dict(pokemon)
    if level is not None:
        p["current_level"] = max(_effective_level(p), int(level))
    return p


def _has_help_bonus(pokemon: dict[str, Any]) -> bool:
    return "おてつだいボーナス" in set(_individual_subs(pokemon))


def expected_skill_activations_per_day(
    pokemon: dict[str, Any],
    species: dict[str, Any],
    *,
    team_help_bonus_count: int = 0,
    activity_boost: float = 1.0,
) -> float:
    """個体のスキル発動期待回数/日。既存期待値と同じ時間・補正軸を使う。"""
    rate = float(species.get("main_skill_rate") or 0.0) / 100.0
    if rate <= 0:
        return 0.0
    level = _effective_level(pokemon)
    subs = _individual_subs(pokemon)
    base = _assist_seconds_at_lv(
        max(int(species.get("base_assist_seconds") or 1), 1), level
    )
    speed = _speed_mult(pokemon.get("nature"), subs)
    speed *= 1.0 + 0.05 * max(0, team_help_bonus_count)
    ribbon_stage = int(pokemon.get("sleep_ribbon_stage") or 0)
    ribbon = (
        get_time_multiplier(
            species_name=pokemon.get("species_name") or species.get("name") or "",
            stage=ribbon_stage,
        )
        if ribbon_stage > 0
        else 1.0
    )
    assists = DAILY_EFFECTIVE_ASSIST_SECONDS * speed * activity_boost / (base * ribbon)
    return assists * rate * _skill_proc_mult(pokemon.get("nature"), subs)


def _skill_effect(pokemon: dict[str, Any], species: dict[str, Any]) -> tuple[str, float]:
    category = _main_skill_category(species) or ""
    max_lv = get_skill_max_lv(category) or 6
    level = _effective_skill_lv(
        int(pokemon.get("main_skill_level") or 1),
        max_lv,
        _individual_subs(pokemon),
    )
    return category, float(get_skill_effect_amount(category, level) or 0.0)


def _healer_boost(activations: float) -> float:
    """既存の検証表（1〜5回/日）を線形補間してチーム稼働増分へ変換する。"""
    points = [0.0, 0.0993, 0.1987, 0.2771, 0.3345, 0.3863]
    activations = max(0.0, min(float(activations), 5.0))
    lo = int(activations)
    hi = min(lo + 1, 5)
    frac = activations - lo
    return points[lo] * (1.0 - frac) + points[hi] * frac


def _meal_fractions(ctx: PlayContext) -> list[float]:
    parsed: list[int] = []
    for raw in ctx.meal_times:
        try:
            dt = datetime.strptime(raw, "%H:%M")
            parsed.append(dt.hour * 60 + dt.minute)
        except ValueError:
            parsed.append(12 * 60)
    parsed.sort()
    fractions: list[float] = []
    previous = 0
    for minute in parsed:
        fractions.append(max(0, minute - previous) / 1440.0)
        previous = minute
    fractions.append(max(0, 1440 - previous) / 1440.0)
    return fractions


def simulate_plan(
    members: list[dict[str, Any]],
    recipe: dict[str, Any],
    *,
    fav_berries: set[str],
    ctx: PlayContext,
    starting_inventory: dict[str, float] | None = None,
    event_set: set[str] | None = None,
    future_level: int | None = None,
) -> PlanSimulation:
    """固定5体と主料理を、月曜0時から7日間・1日3食で決定論的に評価する。"""
    event_set = set(event_set or set())
    members = [_levelled(dict(p), future_level) for p in members]
    masters = [db.get_species_data(p["species_name"]) or {} for p in members]
    team_help = sum(_has_help_bonus(p) for p in members)

    base_activations = [
        expected_skill_activations_per_day(
            p, s, team_help_bonus_count=team_help
        )
        for p, s in zip(members, masters)
    ]
    healer_acts = sum(
        acts
        for p, s, acts in zip(members, masters, base_activations)
        if _skill_effect(p, s)[0] in TEAM_HEAL_CATEGORIES
    )
    activity_boost = 1.0 + _healer_boost(healer_acts)
    activations = [a * activity_boost for a in base_activations]

    supply: dict[str, float] = {}
    berry_daily = 0.0
    direct_skill_daily = 0.0
    pot_acts = pot_effect = chance_acts = chance_effect = 0.0
    food_mult = 2.0 if "food_2x" in event_set else 1.0
    berry_field_bonus = 1.0 if "berry_2x" in event_set else 0.0

    for p, s, acts in zip(members, masters, activations):
        for name, qty in expected_ingredients_per_day(
            p, s, ctx, team_help_bonus_count=team_help
        ).items():
            supply[name] = supply.get(name, 0.0) + qty * activity_boost * food_mult
        berry_daily += expected_berry_per_day(
            p,
            s,
            ctx,
            fav_berries=fav_berries,
            field_bonus=berry_field_bonus,
            team_help_bonus_count=team_help,
        )["energy"] * activity_boost
        category, effect = _skill_effect(p, s)
        if category == "料理パワーアップS":
            pot_acts += acts
            pot_effect = max(pot_effect, effect)
        elif category in {"料理チャンスS", "料理アシスト"}:
            chance_acts += acts
            chance_effect = max(chance_effect, effect if category == "料理チャンスS" else 1.0)
        elif category not in TEAM_HEAL_CATEGORIES:
            direct_skill_daily += expected_skill_energy_per_day(
                p, s, team_help_bonus_count=team_help
            ) * activity_boost

    inventory = {k: float(v) for k, v in (starting_inventory or {}).items() if v > 0}
    requirements = {
        ing["name"]: float(ing["count"])
        for ing in (recipe.get("ingredients") or [])
    }
    total_required = int(recipe.get("total_ingredients") or sum(requirements.values()))
    base_energy = float(
        recipe.get("energy_lv60")
        or recipe.get("energy_lv30")
        or recipe.get("energy_lv1")
        or 0
    )
    meal_fractions = _meal_fractions(ctx)
    cooked = conditional = 0
    dish_energy = 0.0
    pot_bonus = chance_bonus = 0.0
    dish_mult = 2.0 if "dish_2x" in event_set else 1.0

    for day in range(7):
        for fraction in meal_fractions[:3]:
            for name, qty in supply.items():
                inventory[name] = inventory.get(name, 0.0) + qty * fraction
            pot_bonus += pot_acts * pot_effect * fraction
            chance_bonus = min(
                MAX_GREAT_CHANCE - BASE_GREAT_CHANCE,
                chance_bonus + chance_acts * chance_effect / 100.0 * fraction,
            )
            has_food = all(inventory.get(name, 0.0) + 1e-9 >= qty for name, qty in requirements.items())
            capacity = ctx.pot_capacity + pot_bonus
            if not has_food or capacity + 1e-9 < total_required:
                continue
            if total_required > ctx.pot_capacity:
                conditional += 1
            for name, qty in requirements.items():
                inventory[name] -= qty
            cooked += 1
            great_chance = min(MAX_GREAT_CHANCE, BASE_GREAT_CHANCE + chance_bonus)
            dish_energy += base_energy * (1.0 + great_chance) * dish_mult
            pot_bonus = 0.0
            # 大成功時だけリセットされる蓄積を期待値で減衰させる。
            chance_bonus *= 1.0 - great_chance
        # 夕食後〜翌日0時の生産分
        tail = meal_fractions[3]
        for name, qty in supply.items():
            inventory[name] = inventory.get(name, 0.0) + qty * tail
        pot_bonus += pot_acts * pot_effect * tail
        chance_bonus = min(
            MAX_GREAT_CHANCE - BASE_GREAT_CHANCE,
            chance_bonus + chance_acts * chance_effect / 100.0 * tail,
        )

    bottlenecks = sorted(
        requirements,
        key=lambda name: supply.get(name, 0.0) / max(requirements[name], 1.0),
    )[:2]
    berry_energy = berry_daily * 7
    skill_energy = direct_skill_daily * 7
    return PlanSimulation(
        recipe_name=str(recipe.get("name") or ""),
        cooked_meals=cooked,
        total_meals=21,
        stability=cooked / 21.0,
        dish_energy=dish_energy,
        berry_energy=berry_energy,
        skill_energy=skill_energy,
        weekly_energy=dish_energy + berry_energy + skill_energy,
        bottlenecks=bottlenecks if cooked < 21 else [],
        ingredient_supply=supply,
        ingredient_remaining=inventory,
        pot_activation_per_day=pot_acts,
        pot_bonus_per_activation=pot_effect,
        chance_activation_per_day=chance_acts,
        chance_bonus_per_activation=chance_effect,
        healer_activation_per_day=healer_acts,
        healer_team_boost=activity_boost - 1.0,
        conditional_pot_meals=conditional,
    )


def level_improvements(
    members: list[dict[str, Any]],
    recipe: dict[str, Any],
    *,
    fav_berries: set[str],
    ctx: PlayContext,
) -> list[dict[str, Any]]:
    """固定メンバーをLv30/60へ育成した時の料理改善を返す。"""
    baseline = simulate_plan(members, recipe, fav_berries=fav_berries, ctx=ctx)
    out: list[dict[str, Any]] = []
    for idx, pokemon in enumerate(members):
        current = _effective_level(pokemon)
        for target in (30, 60):
            if current >= target:
                continue
            changed = [dict(p) for p in members]
            changed[idx]["current_level"] = target
            result = simulate_plan(changed, recipe, fav_berries=fav_berries, ctx=ctx)
            out.append(
                {
                    "pokemon_id": pokemon.get("id"),
                    "label": pokemon.get("nickname") or pokemon.get("species_name"),
                    "target_level": target,
                    "stability_delta": result.stability - baseline.stability,
                    "energy_delta": result.weekly_energy - baseline.weekly_energy,
                    "result": result,
                }
            )
    return sorted(
        out,
        key=lambda x: (x["stability_delta"], x["energy_delta"]),
        reverse=True,
    )


def capture_improvements(
    members: list[dict[str, Any]],
    recipe: dict[str, Any],
    *,
    fav_berries: set[str],
    ctx: PlayContext,
    limit: int = 12,
) -> list[dict[str, Any]]:
    """未所持の最終進化AAA理想個体を各枠へ入れた改善量を試算する。"""
    from utils.ingredient_coverage import _final_evolutions

    baseline = simulate_plan(members, recipe, fav_berries=fav_berries, ctx=ctx)
    owned_species = {p.get("species_name") for p in db.list_pokemon()}
    needed = {i["name"] for i in (recipe.get("ingredients") or [])}
    finals = _final_evolutions()
    results: list[dict[str, Any]] = []

    for species in db.list_all_master_records():
        name = species.get("species_name")
        if not name or name in owned_species or name not in finals:
            continue
        ingredients = species.get("ingredients") or {}
        available = {
            slot.get("name")
            for slot in ingredients.values()
            if isinstance(slot, dict) and slot.get("name")
        }
        fills = sorted(needed & available)
        category = _main_skill_category(species) or ""
        if not fills and category not in COOKING_CATEGORIES | TEAM_HEAL_CATEGORIES:
            continue
        a_name = (ingredients.get("a") or {}).get("name")
        if not a_name:
            continue
        chosen = [a_name]
        for slot_idx, slot_keys in ((1, ("a", "b")), (2, ("a", "b", "c"))):
            options = [
                (ingredients.get(k) or {}).get("name")
                for k in slot_keys
                if (ingredients.get(k) or {}).get("name")
            ]
            target_options = [name for name in options if name in needed]
            pool = target_options or options or [a_name]
            chosen.append(
                max(pool, key=lambda name: qty_at_slot(species, name, slot_idx))
            )
        composition = "".join(
            (find_food_origin(species, name) or "?").upper()
            for name in chosen
        )
        ideal = {
            "id": -1,
            "species_name": name,
            "nickname": name,
            "current_level": 60,
            "caught_level": 60,
            "level": 60,
            "nature": "きまぐれ (無補正)",
            "main_skill_name": species.get("main_skill"),
            "main_skill_level": get_skill_max_lv(_main_skill_category(species) or "") or 6,
            "ingredient_1": chosen[0],
            "ingredient_2": chosen[1],
            "ingredient_3": chosen[2],
            "sleep_ribbon_stage": 0,
        }
        best: tuple[int, PlanSimulation] | None = None
        for idx in range(len(members)):
            changed = [dict(p) for p in members]
            changed[idx] = ideal
            sim = simulate_plan(changed, recipe, fav_berries=fav_berries, ctx=ctx)
            if best is None or (sim.stability, sim.weekly_energy) > (
                best[1].stability,
                best[1].weekly_energy,
            ):
                best = (idx, sim)
        if best is None:
            continue
        idx, sim = best
        results.append(
            {
                "species_name": name,
                "composition": composition,
                "fills": fills,
                "replace_label": members[idx].get("nickname")
                or members[idx].get("species_name"),
                "stability_delta": sim.stability - baseline.stability,
                "energy_delta": sim.weekly_energy - baseline.weekly_energy,
                "result": sim,
            }
        )
    results.sort(
        key=lambda x: (x["stability_delta"], x["energy_delta"]),
        reverse=True,
    )
    return results[:limit]
