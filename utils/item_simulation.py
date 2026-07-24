"""アイテム使用のifシミュレーションと使用優先度ランキング。

育成後（最終進化形 × Lv60）を基準に、以下のアイテムを使った場合の評価変化を出す:
- 性格変更アイテム（無補正化）: 個体の性格を無補正（上下なし）にした場合
- サブスキルランクUP（S→M）: 装着中の S サブスキルを対応する M に上げた場合

evaluator.evaluate_pokemon は種族・性格・サブをすべて個体 dict から読むので、
dict を射影（書き換え）して渡すだけで全ケースを表現できる。ランク帯・%計算・
重みには一切触れない（rank_calibration_v1_4 の担保を維持）。

検算: python -m utils.item_simulation （DB接続が必要）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from constants import SUBSKILL_UNLOCK_LEVELS, SUBSKILL_UPGRADES, normalize_subskill_name
from utils.evaluator import (
    EvaluationResult,
    evaluate_pokemon,
    evaluate_potential,
    final_evolution_of,
    max_skill_level_of,
)
from utils.food_expectation import _effective_level
from utils.sleep_ribbon import count_remaining_evolutions

# 育成後の基準Lv（最終進化・Lv60）
POTENTIAL_LEVEL = 60
LEVEL_MILESTONES = (10, 25, 30, 50, 60)
_IMMEDIATE_SUB_UPGRADE = {
    name: upgrades[0] for name, upgrades in SUBSKILL_UPGRADES.items() if upgrades
}


def _potential_dict(p: dict[str, Any]) -> dict[str, Any]:
    """最終進化形に射影した個体 dict（育成後評価の土台）。

    メインスキルLvは「1進化ごとに +1」される仕様を反映（evaluate_potential と整合）。
    """
    q = dict(p)
    q["species_name"] = final_evolution_of(p["species_name"])
    q["main_skill_level"] = int(p.get("main_skill_level") or 1) + count_remaining_evolutions(p["species_name"])
    return q


def _equipped_subskill_fields(p: dict[str, Any]) -> list[tuple[str, str]]:
    """(フィールド名, 正規化サブスキル名) のリスト。Lv60で解放済みの枠のみ。"""
    out: list[tuple[str, str]] = []
    for lv in SUBSKILL_UNLOCK_LEVELS:
        if lv > POTENTIAL_LEVEL:
            continue
        field_name = f"subskill_lv{lv}"
        raw = p.get(field_name)
        norm = normalize_subskill_name(raw) if raw else None
        if norm:
            out.append((field_name, norm))
    return out


@dataclass
class SubSeedCandidate:
    field_name: str
    unlock_level: int
    from_sub: str
    to_sub: str


@dataclass
class BlockedSubSeed:
    field_name: str
    unlock_level: int
    from_sub: str
    to_sub: str
    reason: str


def eligible_subskill_upgrades(
    p: dict[str, Any],
    *,
    at_level: int | None = None,
) -> tuple[list[SubSeedCandidate], list[BlockedSubSeed]]:
    """銀種の抽選対象とブロック理由を返す。

    - 抽選対象は指定Lvで解放済みの枠のみ。
    - 強化先の重複判定は、未解放を含む5枠すべてを見る。
    """
    level = int(at_level if at_level is not None else _effective_level(p))
    all_owned = {
        normalize_subskill_name(p.get(f"subskill_lv{lv}"))
        for lv in SUBSKILL_UNLOCK_LEVELS
        if p.get(f"subskill_lv{lv}")
    }
    eligible: list[SubSeedCandidate] = []
    blocked: list[BlockedSubSeed] = []
    for unlock_level in SUBSKILL_UNLOCK_LEVELS:
        field_name = f"subskill_lv{unlock_level}"
        raw = p.get(field_name)
        sub = normalize_subskill_name(raw) if raw else None
        to_sub = _IMMEDIATE_SUB_UPGRADE.get(sub or "")
        if not sub or not to_sub:
            continue
        if unlock_level > level:
            blocked.append(
                BlockedSubSeed(
                    field_name,
                    unlock_level,
                    sub,
                    to_sub,
                    f"Lv{unlock_level}で未解放",
                )
            )
        elif to_sub in all_owned:
            blocked.append(
                BlockedSubSeed(
                    field_name,
                    unlock_level,
                    sub,
                    to_sub,
                    f"{to_sub}を別枠に所持",
                )
            )
        else:
            eligible.append(
                SubSeedCandidate(field_name, unlock_level, sub, to_sub)
            )
    return eligible, blocked


# ---------------------------------------------------------------------------
# ifシミュレーション（1個体）
# ---------------------------------------------------------------------------

@dataclass
class SubUpgradeOption:
    field_name: str        # subskill_lvNN
    from_sub: str          # 例: おてつだいスピードS
    to_sub: str            # 例: おてつだいスピードM
    total: float           # 適用後の species_total
    delta: float           # base からの差分
    probability: float = 1.0


@dataclass
class SubSeedAnalysis:
    at_level: int
    base_total: float
    outcomes: list[SubUpgradeOption]
    blocked: list[BlockedSubSeed]

    @property
    def expected_delta(self) -> float:
        return sum(outcome.delta * outcome.probability for outcome in self.outcomes)

    @property
    def best_delta(self) -> float:
        return max((outcome.delta for outcome in self.outcomes), default=0.0)

    @property
    def worst_delta(self) -> float:
        return min((outcome.delta for outcome in self.outcomes), default=0.0)

    @property
    def is_guaranteed(self) -> bool:
        return len(self.outcomes) == 1


@dataclass
class SubSeedPath:
    probability: float
    used_seeds: int
    steps: list[str]
    total: float
    delta: float


@dataclass
class ItemSimResult:
    base_total: float                          # 育成後(最終進化Lv60)ベース
    base_rank: str
    projected_msl: int                         # 育成後の想定メインスキルLv（進化+1込み）
    max_msl: int                               # 種族のメインスキル最大Lv
    maxskill_total: float                      # メインスキルLv最大の天井
    maxskill_rank: str
    maxskill_delta: float                      # base からの差分
    nature_neutral_total: float                # 無補正化後
    nature_neutral_delta: float
    nature_is_neutral: bool                    # 既に無補正なら True（アイテム不要）
    sub_upgrades: list[SubUpgradeOption] = field(default_factory=list)  # delta降順
    main_seed_total: float = 0.0
    main_seed_delta: float = 0.0
    main_seeds_to_max: int = 0

    @property
    def best_sub_upgrade(self) -> SubUpgradeOption | None:
        return self.sub_upgrades[0] if self.sub_upgrades else None

    @property
    def already_max_skill(self) -> bool:
        return self.projected_msl >= self.max_msl


def _eval_total(q: dict[str, Any]) -> tuple[float, str]:
    res: EvaluationResult = evaluate_pokemon(q, eval_level=POTENTIAL_LEVEL)
    return res.species_total, res.species_rank


def analyze_subskill_seed(
    p: dict[str, Any],
    *,
    at_level: int | None = None,
) -> SubSeedAnalysis:
    """指定Lv時点で銀種を1個使ったランダム結果を評価する。"""
    level = int(at_level if at_level is not None else _effective_level(p))
    base_q = dict(p)
    base_q["current_level"] = level
    base_total = evaluate_pokemon(base_q, eval_level=level).species_total
    candidates, blocked = eligible_subskill_upgrades(p, at_level=level)
    probability = 1.0 / len(candidates) if candidates else 0.0
    outcomes: list[SubUpgradeOption] = []
    for candidate in candidates:
        after = dict(base_q)
        after[candidate.field_name] = candidate.to_sub
        total = evaluate_pokemon(after, eval_level=level).species_total
        outcomes.append(
            SubUpgradeOption(
                field_name=candidate.field_name,
                from_sub=candidate.from_sub,
                to_sub=candidate.to_sub,
                total=total,
                delta=total - base_total,
                probability=probability,
            )
        )
    outcomes.sort(key=lambda outcome: -outcome.delta)
    return SubSeedAnalysis(level, base_total, outcomes, blocked)


def subskill_seed_paths(
    p: dict[str, Any],
    *,
    seed_count: int,
    at_level: int | None = None,
) -> list[SubSeedPath]:
    """最大 seed_count 個まで銀種を使う全分岐を列挙する。"""
    level = int(at_level if at_level is not None else _effective_level(p))
    base = dict(p)
    base["current_level"] = level
    base_total = evaluate_pokemon(base, eval_level=level).species_total
    states: list[tuple[dict[str, Any], float, list[str], int]] = [
        (base, 1.0, [], 0)
    ]
    for _ in range(max(0, int(seed_count))):
        next_states: list[tuple[dict[str, Any], float, list[str], int]] = []
        advanced = False
        for state, probability, steps, used in states:
            candidates, _ = eligible_subskill_upgrades(state, at_level=level)
            if not candidates:
                next_states.append((state, probability, steps, used))
                continue
            advanced = True
            branch_probability = probability / len(candidates)
            for candidate in candidates:
                after = dict(state)
                after[candidate.field_name] = candidate.to_sub
                next_states.append(
                    (
                        after,
                        branch_probability,
                        [*steps, f"{candidate.from_sub}→{candidate.to_sub}"],
                        used + 1,
                    )
                )
        states = next_states
        if not advanced:
            break
    paths: list[SubSeedPath] = []
    for state, probability, steps, used in states:
        total = evaluate_pokemon(state, eval_level=level).species_total
        paths.append(
            SubSeedPath(probability, used, steps, total, total - base_total)
        )
    paths.sort(key=lambda path: (-path.probability, -path.delta, path.steps))
    return paths


def simulate_items(p: dict[str, Any]) -> ItemSimResult:
    """育成後ベースに対する各アイテムの評価変化を計算する。"""
    base_q = _potential_dict(p)
    base_total, base_rank = _eval_total(base_q)

    final_sp = base_q["species_name"]
    projected_msl = int(base_q.get("main_skill_level") or 1)
    max_msl = max_skill_level_of(final_sp)

    # メインスキルLv最大の天井
    max_res = evaluate_potential(p, main_skill_max=True)
    maxskill_total, maxskill_rank = max_res.species_total, max_res.species_rank
    main_seed_q = dict(base_q)
    main_seed_q["main_skill_level"] = min(projected_msl + 1, max_msl)
    main_seed_total, _ = _eval_total(main_seed_q)
    main_seeds_to_max = max(0, max_msl - projected_msl)

    # 性格無補正化
    nature_is_neutral = not p.get("nature")
    neutral_q = dict(base_q)
    neutral_q["nature"] = None
    neutral_total, _ = _eval_total(neutral_q)

    # Lv60時点で実際に銀種の抽選対象になるサブスキル。
    upgrades: list[SubUpgradeOption] = []
    candidates, _ = eligible_subskill_upgrades(p, at_level=POTENTIAL_LEVEL)
    for candidate in candidates:
        up_q = dict(base_q)
        up_q[candidate.field_name] = candidate.to_sub
        total, _ = _eval_total(up_q)
        upgrades.append(SubUpgradeOption(
            field_name=candidate.field_name,
            from_sub=candidate.from_sub,
            to_sub=candidate.to_sub,
            total=total, delta=total - base_total,
        ))
    upgrades.sort(key=lambda u: -u.delta)

    return ItemSimResult(
        base_total=base_total,
        base_rank=base_rank,
        projected_msl=projected_msl,
        max_msl=max_msl,
        maxskill_total=maxskill_total,
        maxskill_rank=maxskill_rank,
        maxskill_delta=maxskill_total - base_total,
        nature_neutral_total=neutral_total,
        nature_neutral_delta=neutral_total - base_total,
        nature_is_neutral=nature_is_neutral,
        sub_upgrades=upgrades,
        main_seed_total=main_seed_total,
        main_seed_delta=main_seed_total - base_total,
        main_seeds_to_max=main_seeds_to_max,
    )


# ---------------------------------------------------------------------------
# 使用優先度ランキング（全所持個体）
# ---------------------------------------------------------------------------

@dataclass
class ItemPriority:
    pokemon_id: int
    label: str
    species_name: str            # 現種族
    final_species: str           # 最終進化形
    base_total: float
    after_total: float
    delta: float                 # 伸び幅（育成後スコア）
    detail: str                  # 何を上げるか（サブ名など）
    probability: float = 1.0
    worst_delta: float | None = None
    best_delta: float | None = None
    seeds_required: int | None = None


@dataclass
class LevelPriority:
    pokemon_id: int
    label: str
    species_name: str
    current_level: int
    target_level: int
    base_total: float
    after_total: float
    delta: float
    delta_per_level: float
    unlock: str


def level_up_priorities(
    owned_rows: list[dict[str, Any]],
) -> list[LevelPriority]:
    """次の解放マイルストーンまで上げた時の1Lvあたり改善順。"""
    out: list[LevelPriority] = []
    for p in owned_rows:
        current = _effective_level(p)
        base = evaluate_pokemon(p, eval_level=current).species_total
        target = next(
            (milestone for milestone in LEVEL_MILESTONES if milestone > current),
            None,
        )
        if target is None:
            continue
        after = evaluate_pokemon(p, eval_level=target).species_total
        delta = after - base
        if delta <= 0.05:
            continue
        if target in (30, 60):
            unlock = f"食材{2 if target == 30 else 3}枠目"
        else:
            unlock = (
                normalize_subskill_name(p.get(f"subskill_lv{target}"))
                or f"Lv{target}"
            )
        out.append(
            LevelPriority(
                pokemon_id=int(p["id"]),
                label=p.get("nickname") or p["species_name"],
                species_name=p["species_name"],
                current_level=current,
                target_level=target,
                base_total=base,
                after_total=after,
                delta=delta,
                delta_per_level=delta / max(1, target - current),
                unlock=unlock,
            )
        )
    out.sort(key=lambda item: (-item.delta_per_level, -item.delta))
    return out


def nature_item_priorities(owned_rows: list[dict[str, Any]]) -> list[ItemPriority]:
    """性格変更アイテム（無補正化）の使用優先度。delta>0 の個体のみ降順。

    下降補正で損している個体だけが無補正化で得をする（上昇補正個体は損）。
    """
    out: list[ItemPriority] = []
    for p in owned_rows:
        if not p.get("nature"):
            continue  # 既に無補正＝アイテム不要
        sim = simulate_items(p)
        if sim.nature_neutral_delta <= 0.05:
            continue
        out.append(ItemPriority(
            pokemon_id=p["id"],
            label=p.get("nickname") or p["species_name"],
            species_name=p["species_name"],
            final_species=final_evolution_of(p["species_name"]),
            base_total=sim.base_total,
            after_total=sim.nature_neutral_total,
            delta=sim.nature_neutral_delta,
            detail=f"性格 {p['nature']} → 無補正",
        ))
    out.sort(key=lambda x: -x.delta)
    return out


def subskill_item_priorities(owned_rows: list[dict[str, Any]]) -> list[ItemPriority]:
    """現在使った銀種1個の期待改善量順。"""
    out: list[ItemPriority] = []
    for p in owned_rows:
        analysis = analyze_subskill_seed(p)
        if not analysis.outcomes or analysis.expected_delta <= 0.05:
            continue
        best = analysis.outcomes[0]
        detail = " / ".join(
            f"{outcome.from_sub}→{outcome.to_sub}"
            for outcome in analysis.outcomes
        )
        out.append(ItemPriority(
            pokemon_id=p["id"],
            label=p.get("nickname") or p["species_name"],
            species_name=p["species_name"],
            final_species=final_evolution_of(p["species_name"]),
            base_total=analysis.base_total,
            after_total=analysis.base_total + analysis.expected_delta,
            delta=analysis.expected_delta,
            detail=detail,
            probability=best.probability,
            worst_delta=analysis.worst_delta,
            best_delta=analysis.best_delta,
        ))
    out.sort(key=lambda x: -x.delta)
    return out


def main_skill_item_priorities(
    owned_rows: list[dict[str, Any]],
) -> list[ItemPriority]:
    """メイン種1個の育成後スコア改善量順。"""
    out: list[ItemPriority] = []
    for p in owned_rows:
        sim = simulate_items(p)
        if sim.main_seeds_to_max <= 0 or sim.main_seed_delta <= 0.05:
            continue
        out.append(
            ItemPriority(
                pokemon_id=p["id"],
                label=p.get("nickname") or p["species_name"],
                species_name=p["species_name"],
                final_species=final_evolution_of(p["species_name"]),
                base_total=sim.base_total,
                after_total=sim.main_seed_total,
                delta=sim.main_seed_delta,
                detail=(
                    f"想定MSLv{sim.projected_msl}→{sim.projected_msl + 1}"
                ),
                seeds_required=sim.main_seeds_to_max,
            )
        )
    out.sort(key=lambda item: -item.delta)
    return out


if __name__ == "__main__":
    # python -m utils.item_simulation で検算（DB接続が必要）
    import db

    owned = [dict(r) for r in db.list_pokemon()]
    print(f"所持: {len(owned)} 体")

    print("\n=== 性格アイテム（無補正化）使用優先度 上位10 ===")
    for i, ip in enumerate(nature_item_priorities(owned)[:10], 1):
        arrow = f"（→{ip.final_species}）" if ip.final_species != ip.species_name else ""
        print(f"  #{i} {ip.label}{arrow}: {ip.base_total:.1f} → {ip.after_total:.1f} (+{ip.delta:.1f}) {ip.detail}")

    print("\n=== サブスキルS→M 使用優先度 上位10 ===")
    for i, ip in enumerate(subskill_item_priorities(owned)[:10], 1):
        arrow = f"（→{ip.final_species}）" if ip.final_species != ip.species_name else ""
        print(f"  #{i} {ip.label}{arrow}: {ip.base_total:.1f} → {ip.after_total:.1f} (+{ip.delta:.1f}) {ip.detail}")

    if owned:
        print("\n=== 個体詳細シミュ例（先頭個体） ===")
        sim = simulate_items(owned[0])
        print(f"  育成後ベース: {sim.base_total:.1f} ({sim.base_rank})")
        print(f"  無補正化: {sim.nature_neutral_total:.1f} ({sim.nature_neutral_delta:+.1f})"
              + ("  ※既に無補正" if sim.nature_is_neutral else ""))
        for u in sim.sub_upgrades:
            print(f"  {u.from_sub}→{u.to_sub}: {u.total:.1f} ({u.delta:+.1f})")
