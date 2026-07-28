"""手放してよさそうな個体を、根拠つきで挙げる。

ボックスが埋まってきた時に「どれを逃がすか」を決める材料。
判定は消去法ではなく**積極的な残す理由が1つも無い**ことを確認する形にする。

残す理由（1つでも当たれば候補から外す）:
  - 色違い（強さと無関係に手放さない、というNaoの明示指定）
  - 今週のプランまたは定番プランのメンバーに入っている
  - アイテム投資で定番プランの週エナジーが伸びる（roster_impact）
  - 種族ティアが高い
  - その種族・その食材構成で手札の最上位（＝上位互換を持っていない）

削除は不可逆なので、この関数は**一覧を出すだけ**でDBには触らない。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import db
from utils.community_tier import TIER_ORDER, get_tier
from utils.evaluator import evaluate_potential, final_evolution_of
from utils.food_expectation import _effective_level, composition_string

# これ以上のティアは、今使っていなくても残す
KEEP_TIER_AT_LEAST = "A"

# 同じ最終進化形でこの数より多く持っていたら、下位は入れ替え候補
MAX_PER_FINAL_SPECIES = 2


@dataclass
class ReleaseCandidate:
    """1体ぶんの処分候補。"""

    pokemon_id: int
    label: str
    species_name: str
    final_species: str
    level: int
    composition: str
    potential_total: float
    tier: str | None
    reasons: list[str] = field(default_factory=list)   # なぜ手放してよいか
    better_ones: list[str] = field(default_factory=list)  # 上位互換の個体


def _tier_at_least(tier: str | None, threshold: str) -> bool:
    if not tier:
        return False
    return TIER_ORDER.index(tier) <= TIER_ORDER.index(threshold)


def release_candidates(
    owned: list[dict[str, Any]],
    *,
    plan_member_ids: set[int] | None = None,
    investable_ids: set[int] | None = None,
    limit: int = 30,
) -> list[ReleaseCandidate]:
    """処分してよさそうな個体を、弱い順に返す。

    plan_member_ids: 定番プランに入っている個体（残す）
    investable_ids: アイテム投資で実改善が出る個体（残す）
    """
    plan_member_ids = plan_member_ids or set()
    investable_ids = investable_ids or set()

    # 最終進化形ごとに、育成後の強さで並べて「上位互換」を割り出す
    by_final: dict[str, list[tuple[float, dict[str, Any]]]] = {}
    scores: dict[int, float] = {}
    for p in owned:
        final = final_evolution_of(p["species_name"])
        total = evaluate_potential(p).species_total
        scores[int(p["id"])] = total
        by_final.setdefault(final, []).append((total, p))
    for rows in by_final.values():
        rows.sort(key=lambda x: -x[0])

    out: list[ReleaseCandidate] = []
    for p in owned:
        pid = int(p["id"])
        final = final_evolution_of(p["species_name"])
        tier = get_tier(final)

        # ── 残す理由があるなら候補にしない ──
        if p.get("is_shiny"):
            continue
        if pid in plan_member_ids:
            continue
        if pid in investable_ids:
            continue
        if _tier_at_least(tier, KEEP_TIER_AT_LEAST):
            continue

        ranked = by_final.get(final, [])
        rank = next((i for i, (_, q) in enumerate(ranked) if int(q["id"]) == pid), 0)
        if rank < MAX_PER_FINAL_SPECIES:
            continue  # その進化系統で上位なので残す

        reasons = [
            "どの定番プランにも入っていない",
            "アイテム投資でもプランの週エナジーが動かない",
            f"種族ティア {tier or '未評価'}",
            f"同じ {final} を {len(ranked)} 体持っていて {rank + 1} 番手",
        ]
        out.append(ReleaseCandidate(
            pokemon_id=pid,
            label=p.get("nickname") or p["species_name"],
            species_name=p["species_name"],
            final_species=final,
            level=_effective_level(p),
            composition=composition_string(p, db.get_species_data(p["species_name"]) or {}) or "—",
            potential_total=scores[pid],
            tier=tier,
            reasons=reasons,
            better_ones=[
                (q.get("nickname") or q["species_name"])
                for _, q in ranked[:MAX_PER_FINAL_SPECIES]
            ],
        ))

    out.sort(key=lambda r: r.potential_total)
    return out[:limit]
