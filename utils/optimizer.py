"""パーティー編成の自動最適化。

戦略: 軸別プレフィルタ + プール内全探索。
  1. 所持個体ごとに MemberStat（きのみ/食材/スキルの日次期待値）を前計算
     — チーム依存は「おてつだいボーナス」の線形係数 (1+0.05N) のみなので
       N=0 で前計算し、組み合わせ評価時に係数を掛けるだけで済む。
  2. きのみ上位 / 必要食材供給上位 / 各役割上位 の和集合をプール化（〜25体）
  3. プール内 C(n,5) を全探索（5万通り程度、数秒以内）。プールが大きすぎる
     場合は貪欲初期解 + 1体スワップ山登りにフォールバック。

評価はすべて「エナジー/日」の同一単位:
  score = 主料理エナジー + きのみエナジー + スキルエナジー − 役割未充足ペナルティ
主料理エナジーは party_logic._main_recipe_recommendations と同定義
（pace × base_energy × dish_2x）なので、採用後の③サマリと数値が一致する。

自己検証: python -m utils.optimizer （DB接続が必要）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Any

import db
from utils.food_expectation import expected_berry_per_day, expected_ingredients_per_day
from utils.party_logic import (
    ROLE_LABELS,
    _main_recipe_pace,
    _recipe_base_energy,
    compute_role_scores,
    get_play_ctx,
)
from utils.skill_expectation import expected_skill_energy_per_day

# 役割目標が1人不足するごとの減点（エナジー相当）。UIから調整可能にしても良い。
DEFAULT_ROLE_PENALTY = 3000.0

# プール内全探索を諦めて山登りに切り替える閾値（C(30,5)=14万でも数秒だが余裕を見る）
EXHAUSTIVE_POOL_LIMIT = 30


@dataclass
class MemberStat:
    pokemon_id: int
    label: str
    species_name: str
    berry_energy: float                    # en/日（team_help=0 基準）
    ingredients: dict[str, float]          # 個数/日（同上）
    skill_energy: float                    # en/日（同上）
    has_help_bonus: bool
    roles: set[str] = field(default_factory=set)


@dataclass
class ComboResult:
    member_ids: tuple[int, ...]
    score: float
    dish_energy: float
    best_recipe: str | None
    bottleneck: list[str]
    berry_energy: float
    skill_energy: float
    role_fulfillment: dict[str, tuple[int, int]]  # role -> (count, target)
    labels: list[str] = field(default_factory=list)


def _has_help_bonus(p: dict[str, Any]) -> bool:
    subs = (
        p.get("subskill_lv10"), p.get("subskill_lv25"), p.get("subskill_lv50"),
        p.get("subskill_lv75"), p.get("subskill_lv100"),
    )
    return "おてつだいボーナス" in {s for s in subs if s}


def precompute_member_stats(
    owned_rows: list[dict[str, Any]],
    *,
    fav_berries: set[str],
    event_set: set[str],
    needed_ings: set[str],
) -> dict[int, MemberStat]:
    """所持個体ごとの日次期待値を team_help=0 基準で前計算する。"""
    ctx = get_play_ctx()
    field_bonus = 1.0 if "berry_2x" in event_set else 0.0
    stats: dict[int, MemberStat] = {}
    for p in owned_rows:
        master = db.get_species_data(p["species_name"]) or {}
        if not master:
            continue
        b = expected_berry_per_day(
            p, master, ctx, fav_berries=fav_berries, field_bonus=field_bonus
        )
        ings = expected_ingredients_per_day(p, master, ctx)
        skill_e = expected_skill_energy_per_day(p, master)
        roles = {
            k for k, v in compute_role_scores(
                p, master, fav_berries, event_set, needed_ings
            ).items() if v is not None
        }
        stats[p["id"]] = MemberStat(
            pokemon_id=p["id"],
            label=p.get("nickname") or p["species_name"],
            species_name=p["species_name"],
            berry_energy=b["energy"],
            ingredients=ings,
            skill_energy=skill_e,
            has_help_bonus=_has_help_bonus(p),
            roles=roles,
        )
    return stats


def build_candidate_pool(
    stats: dict[int, MemberStat],
    role_targets: dict[str, int],
    needed_ings: set[str],
    *,
    k_berry: int = 10,
    k_food: int = 10,
    k_role: int = 3,
) -> list[int]:
    """軸別上位の和集合で探索プールを作る。"""
    ids = list(stats)

    def _top(key_fn, k: int) -> list[int]:
        return sorted(ids, key=key_fn, reverse=True)[:k]

    pool: set[int] = set()
    pool.update(_top(lambda i: stats[i].berry_energy, k_berry))

    def _needed_supply(i: int) -> float:
        s = stats[i]
        if needed_ings:
            return sum(v for n, v in s.ingredients.items() if n in needed_ings)
        return sum(s.ingredients.values())

    pool.update(_top(_needed_supply, k_food))
    pool.update(_top(lambda i: stats[i].skill_energy, k_role))

    for role_key, target in role_targets.items():
        if target <= 0:
            continue
        members = [i for i in ids if role_key in stats[i].roles]
        members.sort(key=lambda i: stats[i].skill_energy, reverse=True)
        pool.update(members[:k_role])

    return sorted(pool)


def evaluate_combo(
    ids: tuple[int, ...],
    stats: dict[int, MemberStat],
    recipes: list[dict],
    role_targets: dict[str, int],
    event_set: set[str],
    *,
    role_penalty: float = DEFAULT_ROLE_PENALTY,
) -> ComboResult:
    members = [stats[i] for i in ids]
    team_help = sum(1 for m in members if m.has_help_bonus)
    factor = 1.0 + 0.05 * team_help  # 全員のspeedに掛かる線形係数

    berry_e = sum(m.berry_energy for m in members) * factor
    skill_e = sum(m.skill_energy for m in members) * factor

    combined: dict[str, float] = {}
    for m in members:
        for n, v in m.ingredients.items():
            combined[n] = combined.get(n, 0.0) + v * factor

    dish_mult = 2.0 if "dish_2x" in event_set else 1.0
    dish_e, best_recipe, bottleneck = 0.0, None, []
    for rec in recipes:
        pace, bn = _main_recipe_pace(rec, combined)
        if pace <= 0:
            continue
        e = _recipe_base_energy(rec) * pace * dish_mult
        if e > dish_e:
            dish_e, best_recipe, bottleneck = e, rec["name"], bn

    fulfillment: dict[str, tuple[int, int]] = {}
    penalty = 0.0
    for role_key, target in role_targets.items():
        if target <= 0:
            continue
        count = sum(1 for m in members if role_key in m.roles)
        fulfillment[role_key] = (count, target)
        if count < target:
            penalty += role_penalty * (target - count)

    return ComboResult(
        member_ids=ids,
        score=dish_e + berry_e + skill_e - penalty,
        dish_energy=dish_e,
        best_recipe=best_recipe,
        bottleneck=bottleneck,
        berry_energy=berry_e,
        skill_energy=skill_e,
        role_fulfillment=fulfillment,
        labels=[m.label for m in members],
    )


def _hill_climb(
    pool: list[int],
    stats: dict[int, MemberStat],
    recipes: list[dict],
    role_targets: dict[str, int],
    event_set: set[str],
) -> list[ComboResult]:
    """プールが大きい場合のフォールバック: 貪欲初期解 + 1体スワップ山登り。"""
    # 貪欲: 単体スコア(きのみ+スキル+食材総量×粗い係数)の上位5体から開始
    def _solo(i: int) -> float:
        s = stats[i]
        return s.berry_energy + s.skill_energy + sum(s.ingredients.values()) * 50
    current = tuple(sorted(sorted(pool, key=_solo, reverse=True)[:5]))
    best = evaluate_combo(current, stats, recipes, role_targets, event_set)
    improved = True
    while improved:
        improved = False
        for out_id in best.member_ids:
            for in_id in pool:
                if in_id in best.member_ids:
                    continue
                cand_ids = tuple(sorted(set(best.member_ids) - {out_id} | {in_id}))
                cand = evaluate_combo(cand_ids, stats, recipes, role_targets, event_set)
                if cand.score > best.score:
                    best = cand
                    improved = True
    return [best]


def optimize_party(
    owned_rows: list[dict[str, Any]],
    *,
    fav_berries: set[str],
    event_set: set[str],
    target_recipes: list[dict],
    role_targets: dict[str, int],
    top_n: int = 5,
) -> list[ComboResult]:
    """最適パーティー候補を score 降順で top_n 件返す。

    target_recipes: 主料理候補のレシピレコード集合（空なら料理エナジー項は0）。
    """
    needed_ings: set[str] = {
        ing["name"] for rec in target_recipes for ing in (rec.get("ingredients") or [])
    }
    stats = precompute_member_stats(
        owned_rows,
        fav_berries=fav_berries,
        event_set=event_set,
        needed_ings=needed_ings,
    )
    if len(stats) < 5:
        return []

    pool = build_candidate_pool(stats, role_targets, needed_ings)
    if len(pool) < 5:
        pool = sorted(stats)

    if len(pool) > EXHAUSTIVE_POOL_LIMIT:
        return _hill_climb(pool, stats, target_recipes, role_targets, event_set)

    results = [
        evaluate_combo(ids, stats, target_recipes, role_targets, event_set)
        for ids in combinations(pool, 5)
    ]
    results.sort(key=lambda r: -r.score)
    return results[:top_n]


if __name__ == "__main__":
    # 自己検証（DB接続が必要）:
    #  (a) プール全探索と素の全探索が一致するか（n<=20 のとき）
    #  (b) 実行時間
    import time

    owned = [dict(r) for r in db.list_pokemon()]
    print(f"所持: {len(owned)} 体")
    if len(owned) < 5:
        raise SystemExit("5体未満のため検証スキップ")

    recipes = [r for r in db.list_all_recipe_records() if r.get("ingredients")]
    role_targets = {"recovery": 1, "berry_focus": 2, "food_focus": 2}

    t0 = time.time()
    top = optimize_party(
        owned,
        fav_berries=set(),
        event_set=set(),
        target_recipes=recipes[:10],
        role_targets=role_targets,
    )
    dt = time.time() - t0
    print(f"探索時間: {dt:.2f}s")
    for r in top:
        print(
            f"  score={r.score:8.0f} dish={r.dish_energy:7.0f}({r.best_recipe}) "
            f"berry={r.berry_energy:7.0f} skill={r.skill_energy:7.0f} "
            f"members={r.labels}"
        )

    # (a) 素の全探索との一致確認（所持20体以下の場合のみ現実的）
    if len(owned) <= 20:
        stats = precompute_member_stats(
            owned, fav_berries=set(), event_set=set(),
            needed_ings={i["name"] for rec in recipes[:10] for i in rec["ingredients"]},
        )
        brute = max(
            (evaluate_combo(ids, stats, recipes[:10], role_targets, set())
             for ids in combinations(sorted(stats), 5)),
            key=lambda r: r.score,
        )
        assert abs(brute.score - top[0].score) < 1e-6, (
            f"プール探索と素全探索が不一致: {brute.score} vs {top[0].score} "
            f"({brute.labels} vs {top[0].labels})"
        )
        print("✅ 素全探索と一致")
