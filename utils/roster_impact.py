"""アイテム投資を「手札全体で実際にどれだけ得か」で並べる。

従来の使用優先度は個体の評価値がいくら伸びるかだけを見ていたので、
次の2つが表現できなかった:

1. その個体が実戦（定番攻略プラン）で使われているかどうか
2. ベンチの個体が、アイテムを使った結果**定番入りする**ケース

ここでは登録済みの定番プラン（フィールド×料理カテゴリで1件）を土台に、
「アイテム後の個体を5枠のどこかに差し込んで、週エナジーがいくら伸びるか」を
全枠ぶん試して最大値を取る。差し込みで伸びなければ 0 なので、
プラン内の個体もベンチも同じ土俵で比較できる。

アイテムを使わなくても差し込むだけで伸びる個体がいるため、基準は
「素のまま差し込んだ最良」に取る。つまりここで出る値は**アイテムの限界貢献**。

simulate_plan は 0.07ms/回なので、93体 × 24プラン × 5枠 でも 1 秒程度。
基準側（素のまま差し込んだ最良）はアイテム種別によらないので使い回す。

検算: python -m utils.roster_impact （DB接続が必要）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import db
from constants import normalize_subskill_name
from utils.community_tier import get_tier, tier_weight
from utils.evaluator import final_evolution_of
from utils.food_expectation import _effective_level
from utils.item_simulation import (
    LEVEL_MILESTONES,
    POTENTIAL_LEVEL,
    _potential_dict,
    eligible_subskill_upgrades,
)
from utils.plan_simulation import simulate_plan
from utils.play_context import PlayContext, load_play_context

ACTIVE_WEEK_KEY = "user.active_strategy_week"

# 今週のプランは他フィールドより重く見る（Naoの指定: 今週を自動で最優先）
THIS_WEEK_WEIGHT = 2.0
OTHER_PLAN_WEIGHT = 1.0

# これ未満の伸びは誤差として捨てる（en/週）
MIN_ENERGY_DELTA = 1.0


@dataclass
class PlanSlot:
    """1つの定番プラン（フィールド×料理カテゴリ）と、その素の週エナジー。"""

    plan_id: int
    name: str
    field_name: str
    recipe_category: str
    members: list[dict[str, Any]]
    member_ids: set[int]
    recipe: dict[str, Any]
    fav_berries: set[str]
    weight: float
    is_this_week: bool
    baseline_energy: float


@dataclass
class PlanDelta:
    """あるプランでの伸び幅と、その伸ばし方。"""

    plan_name: str
    field_name: str
    delta: float
    is_this_week: bool
    swapped_in: bool          # ベンチから差し込んで伸びた（＝定番入り）
    replaced_label: str | None  # 押し出される個体


@dataclass
class ImpactRow:
    """アイテム1個ぶんの投資候補。"""

    pokemon_id: int
    label: str
    species_name: str
    final_species: str
    detail: str                      # 何をするか（サブ名・MSLvなど）
    weighted_delta: float            # 重み付き合計（並べ替えの主軸）
    raw_delta: float                 # 重みなし合計 en/週
    this_week_delta: float
    plan_deltas: list[PlanDelta] = field(default_factory=list)
    tier: str | None = None
    eval_delta: float = 0.0          # 汎用評価の伸び（プラン非依存の参考値）
    enters_plan: bool = False        # アイテム後に新たに定番入りする
    seeds_required: int | None = None
    probability: float = 1.0

    @property
    def in_plan(self) -> bool:
        return any(not d.swapped_in for d in self.plan_deltas)


# ---------------------------------------------------------------------------
# プラン一覧の組み立て
# ---------------------------------------------------------------------------
def load_plan_portfolio(
    owned_by_id: dict[int, dict[str, Any]],
    *,
    ctx: PlayContext | None = None,
) -> list[PlanSlot]:
    """登録済みの定番プランを、シミュレーション可能な形にして返す。

    主料理・フィールド・5体が揃っていないプランは、比較の土俵に乗らないので落とす。
    """
    ctx = ctx or load_play_context()
    recipes = {r["name"]: r for r in db.list_all_recipe_records()}
    fields = {f["name"]: f for f in db.list_all_field_records()}
    active_week = db.get_setting(ACTIVE_WEEK_KEY, {}) or {}
    active_id = active_week.get("plan_id")

    out: list[PlanSlot] = []
    for plan in db.list_parties():
        if not plan.get("recipe_category"):
            continue
        recipe = recipes.get(plan.get("main_recipe"))
        fld = fields.get(plan.get("field_name"))
        members = [
            owned_by_id[int(pid)]
            for pid in (plan.get("member_ids") or [])
            if int(pid) in owned_by_id
        ]
        if not recipe or not fld or len(members) != 5:
            continue
        fav = {x["name"] for x in (fld.get("favorite_berries") or [])}
        is_this_week = active_id is not None and int(active_id) == int(plan["id"])
        base = simulate_plan(members, recipe, fav_berries=fav, ctx=ctx)
        out.append(
            PlanSlot(
                plan_id=int(plan["id"]),
                name=plan.get("name") or f"{plan.get('field_name')}",
                field_name=str(plan.get("field_name")),
                recipe_category=str(plan.get("recipe_category")),
                members=members,
                member_ids={int(m["id"]) for m in members},
                recipe=recipe,
                fav_berries=fav,
                weight=THIS_WEEK_WEIGHT if is_this_week else OTHER_PLAN_WEIGHT,
                is_this_week=is_this_week,
                baseline_energy=base.weekly_energy,
            )
        )
    return out


# ---------------------------------------------------------------------------
# 差し込み評価
# ---------------------------------------------------------------------------
def _best_insertion(
    slot: PlanSlot,
    variant: dict[str, Any],
    *,
    ctx: PlayContext,
) -> tuple[float, int | None]:
    """variant をプランに入れた時の最良の週エナジーと、押し出した枠の index。

    既にメンバーなら同じ枠を差し替える（別枠に増やすと2体になってしまう）。
    メンバーでなければ5枠すべてを試して最良を採る。
    素のままが最良なら (baseline, None)。
    """
    pid = int(variant.get("id") or -1)
    if pid in slot.member_ids:
        members = [
            variant if int(m["id"]) == pid else m
            for m in slot.members
        ]
        result = simulate_plan(
            members, slot.recipe, fav_berries=slot.fav_berries, ctx=ctx
        )
        idx = next(i for i, m in enumerate(slot.members) if int(m["id"]) == pid)
        return result.weekly_energy, idx

    best = slot.baseline_energy
    best_idx: int | None = None
    for idx in range(len(slot.members)):
        members = list(slot.members)
        members[idx] = variant
        result = simulate_plan(
            members, slot.recipe, fav_berries=slot.fav_berries, ctx=ctx
        )
        if result.weekly_energy > best:
            best = result.weekly_energy
            best_idx = idx
    return best, best_idx


def baseline_insertions(
    owned: list[dict[str, Any]],
    plans: list[PlanSlot],
    *,
    ctx: PlayContext,
) -> dict[tuple[int, int], float]:
    """(個体id, プランid) → 素のまま差し込んだ時の最良エナジー。

    アイテム種別によらないので一度だけ計算して使い回す。
    """
    out: dict[tuple[int, int], float] = {}
    for p in owned:
        pid = int(p["id"])
        for slot in plans:
            energy, _ = _best_insertion(slot, p, ctx=ctx)
            out[(pid, slot.plan_id)] = energy
    return out


def _measure(
    p: dict[str, Any],
    variant: dict[str, Any],
    plans: list[PlanSlot],
    base_map: dict[tuple[int, int], float],
    *,
    ctx: PlayContext,
) -> tuple[float, float, float, list[PlanDelta]]:
    """アイテム後の個体が全プランをどれだけ伸ばすかを測る。

    返り値: (重み付き合計, 生の合計, 今週ぶん, プラン別内訳)
    """
    pid = int(p["id"])
    weighted = raw = this_week = 0.0
    details: list[PlanDelta] = []
    for slot in plans:
        before = base_map.get((pid, slot.plan_id), slot.baseline_energy)
        after, idx = _best_insertion(slot, variant, ctx=ctx)
        delta = after - before
        if delta < MIN_ENERGY_DELTA:
            continue
        swapped_in = pid not in slot.member_ids
        replaced = None
        if swapped_in and idx is not None:
            target = slot.members[idx]
            replaced = target.get("nickname") or target.get("species_name")
        weighted += delta * slot.weight
        raw += delta
        if slot.is_this_week:
            this_week += delta
        details.append(
            PlanDelta(
                plan_name=slot.name,
                field_name=slot.field_name,
                delta=delta,
                is_this_week=slot.is_this_week,
                swapped_in=swapped_in,
                replaced_label=replaced,
            )
        )
    details.sort(key=lambda d: -d.delta)
    return weighted, raw, this_week, details


# ---------------------------------------------------------------------------
# アイテム種別ごとの「使った後の個体」
# ---------------------------------------------------------------------------
@dataclass
class Variant:
    """アイテム使用後への変換。

    mutate は「今の個体」にも「育成後に射影した個体」にも同じ意味で効く必要が
    あるので、絶対値ではなく渡された dict を基準に相対で書き換える。
    最終進化Lv60に射影した dict を差し込むと、進化とレベルの効果まで
    アイテムの手柄に混ざるため、プラン計測は必ず今の個体に対して行う。
    """

    mutate: Callable[[dict[str, Any]], dict[str, Any]]
    text: str
    probability: float = 1.0
    seeds_required: int = 1


def _variants_main_seed(p: dict[str, Any]) -> list[Variant]:
    """メインスキルのたね1個。"""
    from utils.evaluator import max_skill_level_of

    q = _potential_dict(p)
    projected = int(q.get("main_skill_level") or 1)
    max_lv = max_skill_level_of(q["species_name"])
    if projected >= max_lv:
        return []

    def _bump(target: dict[str, Any]) -> dict[str, Any]:
        after = dict(target)
        cur = int(target.get("main_skill_level") or 1)
        cap = max_skill_level_of(target.get("species_name") or "") or max_lv
        after["main_skill_level"] = min(cur + 1, cap)
        return after

    return [Variant(_bump, f"メインスキルLv {projected}→{projected + 1}", 1.0, max_lv - projected)]


def _variants_sub_seed(p: dict[str, Any]) -> list[Variant]:
    """サブスキルのたね1個。抽選なので候補ぶんの分岐を等確率で返す。"""
    candidates, _ = eligible_subskill_upgrades(p, at_level=POTENTIAL_LEVEL)
    if not candidates:
        return []
    prob = 1.0 / len(candidates)
    out: list[Variant] = []
    for cand in candidates:
        def _apply(target: dict[str, Any], _c=cand) -> dict[str, Any]:
            after = dict(target)
            after[_c.field_name] = _c.to_sub
            return after

        out.append(Variant(_apply, f"{cand.from_sub}→{cand.to_sub}", prob, 1))
    return out


def _variants_mint(p: dict[str, Any]) -> list[Variant]:
    """まっしろミント（無補正化）。既に無補正なら候補なし。"""
    if not p.get("nature"):
        return []

    def _neutral(target: dict[str, Any]) -> dict[str, Any]:
        after = dict(target)
        after["nature"] = None
        return after

    return [Variant(_neutral, f"性格 {p['nature']} → 無補正", 1.0, 1)]


def _variants_level(p: dict[str, Any]) -> list[Variant]:
    """次の解放マイルストーンまでのレベル上げ（アメ）。"""
    current = _effective_level(p)
    target_lv = next((m for m in LEVEL_MILESTONES if m > current), None)
    if target_lv is None:
        return []
    if target_lv in (30, 60):
        unlock = f"食材{2 if target_lv == 30 else 3}枠目"
    else:
        unlock = (
            normalize_subskill_name(p.get(f"subskill_lv{target_lv}"))
            or f"Lv{target_lv}のサブ枠（未入力）"
        )

    def _raise(target: dict[str, Any]) -> dict[str, Any]:
        after = dict(target)
        after["current_level"] = max(int(target.get("current_level") or 0), target_lv)
        return after

    return [Variant(_raise, f"Lv{current}→{target_lv}（{unlock}）", 1.0, target_lv - current)]


VARIANT_BUILDERS: dict[str, Callable[[dict[str, Any]], list[Variant]]] = {
    "main": _variants_main_seed,
    "sub": _variants_sub_seed,
    "mint": _variants_mint,
    "level": _variants_level,
}


# ---------------------------------------------------------------------------
# ランキング
# ---------------------------------------------------------------------------
def item_impact_ranking(
    owned: list[dict[str, Any]],
    kind: str,
    *,
    plans: list[PlanSlot] | None = None,
    base_map: dict[tuple[int, int], float] | None = None,
    ctx: PlayContext | None = None,
) -> list[ImpactRow]:
    """アイテム1個の投資先を「全プランの週エナジー改善」で並べる。

    kind: "main" | "sub" | "mint" | "level"
    サブスキルのたねのように結果が抽選なら、分岐の期待値を取る。
    """
    build = VARIANT_BUILDERS[kind]
    ctx = ctx or load_play_context()
    owned_by_id = {int(p["id"]): p for p in owned}
    plans = load_plan_portfolio(owned_by_id, ctx=ctx) if plans is None else plans
    if base_map is None:
        base_map = baseline_insertions(owned, plans, ctx=ctx)

    from utils.evaluator import evaluate_pokemon

    rows: list[ImpactRow] = []
    for p in owned:
        variants = build(p)
        if not variants:
            continue
        base_eval = evaluate_pokemon(_potential_dict(p), eval_level=POTENTIAL_LEVEL).species_total

        weighted = raw = this_week = eval_delta = 0.0
        merged: dict[str, PlanDelta] = {}
        details_text: list[str] = []
        seeds = variants[0].seeds_required
        for variant in variants:
            prob = variant.probability
            # プラン計測は「今の個体」に対して。評価値は育成後に射影して見る
            w, r, tw, plan_deltas = _measure(
                p, variant.mutate(p), plans, base_map, ctx=ctx
            )
            weighted += w * prob
            raw += r * prob
            this_week += tw * prob
            after_eval = evaluate_pokemon(
                variant.mutate(_potential_dict(p)), eval_level=POTENTIAL_LEVEL
            ).species_total
            eval_delta += (after_eval - base_eval) * prob
            details_text.append(variant.text)
            # 分岐ごとの内訳は期待値に均してから1本にまとめる
            for d in plan_deltas:
                cur = merged.get(d.plan_name)
                if cur is None:
                    merged[d.plan_name] = PlanDelta(
                        plan_name=d.plan_name,
                        field_name=d.field_name,
                        delta=d.delta * prob,
                        is_this_week=d.is_this_week,
                        swapped_in=d.swapped_in,
                        replaced_label=d.replaced_label,
                    )
                else:
                    cur.delta += d.delta * prob

        if weighted < MIN_ENERGY_DELTA and eval_delta <= 0.05:
            continue
        plan_deltas = sorted(merged.values(), key=lambda d: -d.delta)
        rows.append(
            ImpactRow(
                pokemon_id=int(p["id"]),
                label=p.get("nickname") or p["species_name"],
                species_name=p["species_name"],
                final_species=final_evolution_of(p["species_name"]),
                detail=" / ".join(details_text),
                weighted_delta=weighted,
                raw_delta=raw,
                this_week_delta=this_week,
                plan_deltas=plan_deltas,
                tier=get_tier(final_evolution_of(p["species_name"])),
                eval_delta=eval_delta,
                enters_plan=any(d.swapped_in for d in plan_deltas),
                seeds_required=seeds if kind in ("main", "level") else None,
                probability=variants[0].probability,
            )
        )

    # 実改善が主軸。並ばない（プラン未登録など）ときはティア×汎用評価で救う
    rows.sort(
        key=lambda r: (
            -round(r.weighted_delta, 1),
            -r.eval_delta * tier_weight(r.final_species),
        )
    )
    return rows


if __name__ == "__main__":
    ctx = load_play_context()
    owned = [dict(r) for r in db.list_pokemon()]
    owned_by_id = {int(p["id"]): p for p in owned}
    plans = load_plan_portfolio(owned_by_id, ctx=ctx)
    print(f"所持 {len(owned)} 体 / 定番プラン {len(plans)} 件")
    for s in plans:
        mark = "★今週" if s.is_this_week else "　　　"
        print(f"  {mark} {s.name}（{s.field_name}）: {s.baseline_energy:,.0f} en/週")
    if not plans:
        print("  ※プランが1件も揃っていないので実改善は測れない")
    base_map = baseline_insertions(owned, plans, ctx=ctx)
    for kind, title in (
        ("level", "レベル上げ"),
        ("main", "メインスキルのたね"),
        ("sub", "サブスキルのたね"),
        ("mint", "まっしろミント"),
    ):
        print(f"\n=== {title} 上位10 ===")
        for i, row in enumerate(
            item_impact_ranking(owned, kind, plans=plans, base_map=base_map, ctx=ctx)[:10], 1
        ):
            badge = "🆕定番入り" if row.enters_plan else ("使用中" if row.in_plan else "ベンチ")
            print(
                f"  #{i} {row.label}（{row.tier or '—'}／{badge}）"
                f" 週+{row.raw_delta:,.0f} en（今週+{row.this_week_delta:,.0f}）"
                f" 評価{row.eval_delta:+.1f} ｜ {row.detail}"
            )
