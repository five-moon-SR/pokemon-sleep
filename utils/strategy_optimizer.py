"""攻略プラン用の二段階自動提案と、全フィールドぶんの一括生成。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterator

import db
from utils.evaluator import _main_skill_category
from utils.optimizer import optimize_party
from utils.party_logic import RECIPE_CATEGORY_LABELS
from utils.plan_simulation import PlanSimulation, simulate_plan
from utils.play_context import PlayContext, load_play_context


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
        pot_capacity=ctx.pot_capacity,
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
            pot_capacity=ctx.pot_capacity,
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


# ---------------------------------------------------------------------------
# 全フィールド × 全料理カテゴリの一括生成
# ---------------------------------------------------------------------------
@dataclass
class GeneratedPlan:
    """一括生成の1枠ぶんの結果。"""

    field_name: str
    recipe_category: str
    # "created" | "updated" | "unchanged" | "skipped" | "failed"
    status: str
    plan_id: int | None = None
    recipe_name: str | None = None
    member_labels: list[str] | None = None
    weekly_energy: float = 0.0
    stability: float = 0.0
    reason: str | None = None
    # 上書き時に「何がどう変わったか」を出すための元の姿
    prev_recipe: str | None = None
    prev_member_labels: list[str] | None = None
    prev_weekly_energy: float = 0.0

    @property
    def label(self) -> str:
        cat = RECIPE_CATEGORY_LABELS.get(self.recipe_category, self.recipe_category)
        return f"{self.field_name}｜{cat}"

    @property
    def energy_delta(self) -> float:
        return self.weekly_energy - self.prev_weekly_energy

    @property
    def recipe_changed(self) -> bool:
        return bool(self.prev_recipe) and self.prev_recipe != self.recipe_name

    @property
    def members_in(self) -> list[str]:
        """新しく入ったメンバー。"""
        return [m for m in (self.member_labels or []) if m not in (self.prev_member_labels or [])]

    @property
    def members_out(self) -> list[str]:
        """外れたメンバー。"""
        return [m for m in (self.prev_member_labels or []) if m not in (self.member_labels or [])]


def plan_slots() -> list[tuple[str, str]]:
    """埋めるべき枠（フィールド × 料理カテゴリ）の全組合せ。"""
    return [
        (str(f["name"]), cat)
        for f in db.list_all_field_records()
        for cat in RECIPE_CATEGORY_LABELS
    ]


def generate_all_strategy_plans(
    *,
    overwrite: bool = False,
    ctx: PlayContext | None = None,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> Iterator[GeneratedPlan]:
    """空いている枠（または全枠）の定番プランを自動生成して保存する。

    1枠あたり1秒弱なので、24枠でも20秒前後で終わる。
    既存プランは overwrite=True のときだけ上書きする（手で詰めた編成を
    黙って壊さないため、既定はスキップ）。

    好物きのみがランダムなフィールドは、この一括生成では確定分だけで組む。
    その週の抽選結果は編成ページで個別に指定する前提。
    """
    ctx = ctx or load_play_context()
    owned = [dict(p) for p in db.list_pokemon()]
    all_recipes = db.list_all_recipe_records()
    fields = {str(f["name"]): f for f in db.list_all_field_records()}
    slots = plan_slots()
    by_category: dict[str, list[dict[str, Any]]] = {
        cat: [r for r in all_recipes if r.get("category") == cat and r.get("ingredients")]
        for cat in RECIPE_CATEGORY_LABELS
    }

    for index, (field_name, category) in enumerate(slots, 1):
        if on_progress:
            cat_label = RECIPE_CATEGORY_LABELS.get(category, category)
            on_progress(index, len(slots), f"{field_name}｜{cat_label}")

        if len(owned) < 5:
            yield GeneratedPlan(field_name, category, "failed", reason="所持が5体未満")
            continue

        existing = db.get_strategy_plan(field_name, category)
        if existing and not overwrite:
            yield GeneratedPlan(
                field_name, category, "skipped",
                plan_id=int(existing.get("id") or 0) or None,
                recipe_name=existing.get("main_recipe"),
                reason="登録済み",
            )
            continue

        field = fields.get(field_name) or {}
        fav = {x["name"] for x in (field.get("favorite_berries") or [])}
        recipes = by_category.get(category) or []

        # 上書き前の姿を控える（何がどう変わったかを出せるように）
        prev_recipe = prev_labels = None
        prev_energy = 0.0
        if existing:
            prev_recipe = existing.get("main_recipe")
            owned_map = {int(p["id"]): p for p in owned}
            prev_members = [
                owned_map[int(i)] for i in (existing.get("member_ids") or [])
                if int(i) in owned_map
            ]
            prev_labels = [
                p.get("nickname") or p["species_name"] for p in prev_members
            ]
            prev_rec = next((r for r in all_recipes if r["name"] == prev_recipe), None)
            if prev_rec and len(prev_members) == 5:
                prev_energy = simulate_plan(
                    prev_members, prev_rec, fav_berries=fav, ctx=ctx
                ).weekly_energy
        suggestions = suggest_strategy_plans(
            owned, recipes, fav_berries=fav, ctx=ctx, top_n=3
        )
        if not suggestions:
            yield GeneratedPlan(field_name, category, "failed", reason="候補を作れなかった")
            continue

        best = suggestions[0]
        same = (
            existing is not None
            and prev_recipe == best.recipe_name
            and set(map(int, existing.get("member_ids") or [])) == set(map(int, best.member_ids))
        )
        plan_id = db.upsert_strategy_plan({
            "name": f"{field_name}｜{RECIPE_CATEGORY_LABELS[category]}",
            "field_name": field_name,
            "recipe_category": category,
            "main_recipe": best.recipe_name,
            "candidate_recipes": [s.recipe_name for s in suggestions],
            "member_ids": best.member_ids,
            "note": "自動生成",
            "random_field_berries": [],
            "role_targets": {},
            "event_bonuses": [],
            "policy_tags": [],
        })
        yield GeneratedPlan(
            field_name, category,
            "unchanged" if same else ("updated" if existing else "created"),
            plan_id=int(plan_id),
            recipe_name=best.recipe_name,
            member_labels=list(best.member_labels),
            weekly_energy=best.simulation.weekly_energy,
            stability=best.simulation.stability,
            prev_recipe=prev_recipe,
            prev_member_labels=prev_labels,
            prev_weekly_energy=prev_energy,
        )
