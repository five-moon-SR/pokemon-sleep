"""今週の目標（ホーム画面）。

手入力のメモは書いた瞬間から古びていくので、目標は「何を達成したいか」だけを
持ち、**進捗は毎回データから計算する**。対応する目標は3種類:

  - ingredient: その食材を1日あたり N個 供給できるようにする（担当を作る）
  - catch:      その種族を仲間にする
  - raise:      この個体を Lv○ まで育てる / 進化させる

週が変わっても未達成の目標はそのまま残す（繰り越し）。達成したものは達成週を
記録して畳む。週の区切りは月曜始まり。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

import db
from utils.evaluator import final_evolution_of
from utils.food_expectation import expected_ingredients_per_day
from utils.play_context import load_play_context

GOALS_KEY = "user.weekly_goals"

GOAL_TYPE_LABELS = {
    "ingredient": "🥕 食材の担当を作る",
    "catch": "🏅 仲間にする",
    "raise": "🔧 育てる",
}


def current_week_key(today: date | None = None) -> str:
    """月曜始まりの週キー（例: 2026-W38）。"""
    d = today or date.today()
    year, week, _ = d.isocalendar()
    return f"{year}-W{week:02d}"


@dataclass(frozen=True)
class GoalProgress:
    goal_id: str
    goal_type: str
    title: str
    detail: str
    current: float
    target: float
    done: bool

    @property
    def ratio(self) -> float:
        if self.target <= 0:
            return 1.0 if self.done else 0.0
        return max(0.0, min(1.0, self.current / self.target))


def load_goals() -> list[dict[str, Any]]:
    saved = db.get_setting(GOALS_KEY, []) or []
    return [g for g in saved if isinstance(g, dict) and g.get("type") in GOAL_TYPE_LABELS]


def save_goals(goals: list[dict[str, Any]]) -> None:
    db.set_setting(GOALS_KEY, goals)


def add_goal(goal: dict[str, Any]) -> list[dict[str, Any]]:
    goals = load_goals()
    goal = dict(goal)
    goal.setdefault("id", uuid.uuid4().hex[:8])
    goal.setdefault("created_week", current_week_key())
    goals.append(goal)
    save_goals(goals)
    return goals


def remove_goal(goal_id: str) -> list[dict[str, Any]]:
    goals = [g for g in load_goals() if g.get("id") != goal_id]
    save_goals(goals)
    return goals


def _ingredient_supply(owned: list[dict[str, Any]], name: str) -> tuple[float, float]:
    """(所持全体の供給 個/日, 単体で最大の供給 個/日)。"""
    ctx = load_play_context()
    total = best = 0.0
    for p in owned:
        species = db.get_species_data(p.get("species_name") or "") or {}
        qty = expected_ingredients_per_day(p, species, ctx).get(name, 0.0)
        total += qty
        best = max(best, qty)
    return total, best


def _progress_ingredient(goal: dict, owned: list[dict]) -> GoalProgress:
    name = str(goal.get("ingredient") or "")
    target = float(goal.get("per_day") or 0.0)
    total, best = _ingredient_supply(owned, name)
    return GoalProgress(
        goal_id=str(goal.get("id")),
        goal_type="ingredient",
        title=f"{name} を 1日 {target:g}個",
        detail=f"いま 合計 {total:.1f}個/日（最大の担当 {best:.1f}個/日）",
        current=total,
        target=target,
        done=total + 1e-9 >= target > 0,
    )


def _progress_catch(goal: dict, owned: list[dict]) -> GoalProgress:
    species = str(goal.get("species") or "")
    target = float(goal.get("count") or 1)
    exact = [p for p in owned if p.get("species_name") == species]
    # 進化前を持っている場合は「育てれば届く」= 途中扱い。達成にはしない。
    wanted_final = final_evolution_of(species)
    family = [
        p for p in owned
        if p not in exact
        and final_evolution_of(p.get("species_name") or "") == wanted_final
    ]
    got = float(len(exact))
    if got < target and family:
        # 進化前の在庫は半分ぶんの進捗として見せる（あと一歩が分かるように）
        got = min(target - 0.5, got + 0.5 * len(family))
    if exact:
        detail = f"所持: {len(exact)}体"
    elif family:
        names = "、".join(sorted({str(p.get("species_name")) for p in family})[:3])
        detail = f"{names} を所持（進化で到達できる）"
    else:
        detail = "まだ居ない"
    return GoalProgress(
        goal_id=str(goal.get("id")),
        goal_type="catch",
        title=f"{species} を仲間にする" + (f"（{target:g}体）" if target > 1 else ""),
        detail=detail,
        current=got,
        target=target,
        done=len(exact) >= target,
    )


def _progress_raise(goal: dict, owned: list[dict]) -> GoalProgress:
    pid = int(goal.get("pokemon_id") or 0)
    target_lv = int(goal.get("target_level") or 0)
    want_evolution = bool(goal.get("want_evolution"))
    p = next((x for x in owned if int(x.get("id") or 0) == pid), None)
    if p is None:
        return GoalProgress(
            goal_id=str(goal.get("id")), goal_type="raise",
            title="（削除された個体）", detail="対象が見つからない",
            current=0.0, target=1.0, done=False,
        )
    label = p.get("nickname") or p.get("species_name") or "—"
    level = int(p.get("current_level") or p.get("caught_level") or p.get("level") or 1)
    species_name = str(p.get("species_name") or "")
    if want_evolution:
        final_name = final_evolution_of(species_name)
        done = species_name == final_name
        return GoalProgress(
            goal_id=str(goal.get("id")), goal_type="raise",
            title=f"{label} を {final_name} まで進化させる",
            detail=f"いま {species_name} / Lv{level}",
            current=1.0 if done else 0.0, target=1.0, done=done,
        )
    return GoalProgress(
        goal_id=str(goal.get("id")), goal_type="raise",
        title=f"{label} を Lv{target_lv} まで育てる",
        detail=f"いま {species_name} / Lv{level}",
        current=float(level), target=float(target_lv or 1), done=level >= target_lv > 0,
    )


_PROGRESS_FUNCS = {
    "ingredient": _progress_ingredient,
    "catch": _progress_catch,
    "raise": _progress_raise,
}


def evaluate_goals(owned: list[dict[str, Any]]) -> list[GoalProgress]:
    """保存済みの目標を進捗つきで返す。未達成を先に、達成済みを後ろに並べる。"""
    goals = load_goals()
    out = [_PROGRESS_FUNCS[g["type"]](g, owned) for g in goals if g.get("type") in _PROGRESS_FUNCS]
    # 達成したら達成週を記録する（次の週に「先週達成」として畳めるように）
    changed = False
    done_map = {pr.goal_id: pr.done for pr in out}
    for g in goals:
        if done_map.get(str(g.get("id"))) and not g.get("done_week"):
            g["done_week"] = current_week_key()
            changed = True
        elif not done_map.get(str(g.get("id"))) and g.get("done_week"):
            # 進捗が戻った（個体を逃がした等）ら達成マークも外す
            g.pop("done_week", None)
            changed = True
    if changed:
        save_goals(goals)
    out.sort(key=lambda pr: (pr.done, -pr.ratio))
    return out
