"""攻略プラン用の二段階自動提案。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import db
from utils.evaluator import _main_skill_category
from utils.optimizer import optimize_party
from utils.plan_simulation import PlanSimulation, simulate_plan
from utils.play_context import PlayContext


@dataclass
class StrategySuggestion:
    member_ids: list[int]
    member_labels: list[str]
    recipe_name: str
    simulation: PlanSimulation
    has_healer: bool
    recommendation_score: float


def _is_team_healer(pokemon: dict[str, Any]) -> bool:
    master = db.get_species_data(pokemon.get("species_name") or "") or {}
    return _main_skill_category(master) == "げんきオールS"


def suggest_strategy_plans(
    owned: list[dict[str, Any]],
    recipes: list[dict[str, Any]],
    *,
    fav_berries: set[str],
    ctx: PlayContext,
    top_n: int = 5,
) -> list[StrategySuggestion]:
    """高速探索の上位を7日間シミュレーションし、安定度＋期待値で並べ直す。"""
    if len(owned) < 5 or not recipes:
        return []
    recipe_map = {r["name"]: r for r in recipes}
    role_targets = {
        "recovery": 0,
        "energy_supply": 0,
        "pot_up": 0,
        "berry_focus": 1,
        "food_focus": 3,
    }
    fast = optimize_party(
        owned,
        fav_berries=fav_berries,
        event_set=set(),
        target_recipes=recipes,
        role_targets=role_targets,
        top_n=12,
    )
    # ヒーラーなし案を必ず比較に残す。
    no_healer_owned = [p for p in owned if not _is_team_healer(p)]
    if len(no_healer_owned) >= 5:
        fast += optimize_party(
            no_healer_owned,
            fav_berries=fav_berries,
            event_set=set(),
            target_recipes=recipes,
            role_targets=role_targets,
            top_n=5,
        )

    owned_map = {int(p["id"]): p for p in owned}
    seen: set[tuple[tuple[int, ...], str]] = set()
    detailed: list[StrategySuggestion] = []
    for candidate in fast:
        if not candidate.best_recipe or candidate.best_recipe not in recipe_map:
            continue
        key = (tuple(candidate.member_ids), candidate.best_recipe)
        if key in seen:
            continue
        seen.add(key)
        members = [owned_map[i] for i in candidate.member_ids if i in owned_map]
        if len(members) != 5:
            continue
        sim = simulate_plan(
            members,
            recipe_map[candidate.best_recipe],
            fav_berries=fav_berries,
            ctx=ctx,
        )
        has_healer = any(_is_team_healer(p) for p in members)
        score = sim.weekly_energy + sim.stability * 200_000
        detailed.append(
            StrategySuggestion(
                member_ids=list(candidate.member_ids),
                member_labels=[p.get("nickname") or p["species_name"] for p in members],
                recipe_name=candidate.best_recipe,
                simulation=sim,
                has_healer=has_healer,
                recommendation_score=score,
            )
        )

    detailed.sort(key=lambda x: x.recommendation_score, reverse=True)
    selected = detailed[:top_n]
    if detailed and not any(x.has_healer for x in selected):
        healer = next((x for x in detailed if x.has_healer), None)
        if healer:
            selected[-1:] = [healer]
    if detailed and not any(not x.has_healer for x in selected):
        no_healer = next((x for x in detailed if not x.has_healer), None)
        if no_healer:
            selected[-1:] = [no_healer]
    return selected
