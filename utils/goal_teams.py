"""カビゴン評価とは別の目的で組む編成。

このアプリの編成計算は一貫して「週エナジー」を物差しにしている。だが実際の運用には
エナジーにならない目的の日がある。

1. **ゆめのかけら稼ぎ** — かけらは `ENERGY_PER_UNIT["ゆめのかけらゲットS"] = 0.0`
   （utils/skill_effects.py）の通り週エナジーに一切乗らない。つまり通常の編成計算では
   かけら型は「何も出さないポケモン」として扱われる。専用の物差しが要る。
2. **おやすみリボン稼ぎ** — リボンは「一緒に寝た累計時間」が 200/500/1000/2000h を
   跨ぐと上がり、おてつだい時間が最大25%短縮される（data/sleep_ribbon.json）。
   寝た時間は**編成に入れていた5体にだけ**積まれるので、「今日は誰を連れて寝るか」が
   そのまま将来の強さになる。

どちらも1日単位で編成を差し替える運用なので、7日シミュレーションは使わない。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

import db
from utils.genki import heal_assist_boost
from utils.plan_simulation import (
    HEAL_CATEGORIES,
    RANDOM_HEAL_CATEGORIES,
    SELF_HEAL_CATEGORIES,
    TEAM_HEAL_CATEGORIES,
    _has_help_bonus,
    _healer_boost,
    _skill_effect,
    expected_skill_activations_per_day,
)
from utils.sleep_ribbon import count_remaining_evolutions, get_time_multiplier

TEAM_SIZE = 5

# ---------------------------------------------------------------------------
# ゆめのかけら
# ---------------------------------------------------------------------------
SHARD_CATEGORY = "ゆめのかけらゲットS"


@dataclass
class ShardRow:
    """編成1体ぶんの内訳。"""

    pokemon: dict[str, Any]
    activations: float          # スキル発動回数/日（チーム補正込み）
    per_activation: float       # 1発動あたりのかけら
    shards: float               # かけら/日
    role: str                   # "かけら" / "回復" / "サポート"


@dataclass
class ShardTeam:
    rows: list[ShardRow]
    shards_per_day: float
    help_bonus_count: int
    healer_boost: float         # げんき回復による稼働増（0.12 = +12%）

    @property
    def members(self) -> list[dict[str, Any]]:
        return [r.pokemon for r in self.rows]


def _role_of(category: str) -> str:
    if category == SHARD_CATEGORY:
        return "かけら"
    if category in HEAL_CATEGORIES:
        return "回復"
    return "サポート"


def evaluate_shard_team(members: Sequence[dict[str, Any]]) -> ShardTeam:
    """この5体で1日に得られるゆめのかけらの期待値。

    発動回数の出し方は utils.plan_simulation.simulate_plan と同じ軸を使う
    （おてつだいボーナスの人数・げんき回復による稼働増を効かせる）。
    ここを独自計算にすると、同じ編成なのにページごとに発動回数が違う事態になる。
    """
    members = [dict(p) for p in members]
    masters = [db.get_species_data(p["species_name"]) or {} for p in members]
    team_help = sum(_has_help_bonus(p) for p in members)

    base_acts = [
        expected_skill_activations_per_day(p, s, team_help_bonus_count=team_help)
        for p, s in zip(members, masters)
    ]

    team_heals: list[tuple[float, float]] = []
    self_heals = [0.0] * len(members)
    for idx, (p, s, acts) in enumerate(zip(members, masters, base_acts)):
        category, amount = _skill_effect(p, s)
        if category in TEAM_HEAL_CATEGORIES:
            team_heals.append((acts, amount))
        elif category in RANDOM_HEAL_CATEGORIES and members:
            team_heals.append((acts / len(members), amount))
        elif category in SELF_HEAL_CATEGORIES:
            self_heals[idx] = heal_assist_boost(acts, amount)

    healer_boost = _healer_boost(team_heals)
    activity = 1.0 + healer_boost
    boosts = [activity * (1.0 + extra) for extra in self_heals]

    rows: list[ShardRow] = []
    total = 0.0
    for p, s, acts, boost in zip(members, masters, base_acts, boosts):
        category, amount = _skill_effect(p, s)
        real_acts = acts * boost
        per = amount if category == SHARD_CATEGORY else 0.0
        shards = real_acts * per
        total += shards
        rows.append(
            ShardRow(
                pokemon=p,
                activations=real_acts,
                per_activation=per,
                shards=shards,
                role=_role_of(category),
            )
        )
    return ShardTeam(
        rows=rows,
        shards_per_day=total,
        help_bonus_count=team_help,
        healer_boost=healer_boost,
    )


def _shard_pool(owned: Iterable[dict[str, Any]], *, limit: int = 40) -> list[dict[str, Any]]:
    """探索に入れる候補。かけら型・回復型・おてつだいボーナス持ちだけ残す。

    かけらを出すのはかけら型だけで、他はその発動回数を増やす役にしかならない。
    無関係な個体を混ぜても最適解には入らないので、先に落として探索を軽くする。
    """
    scored: list[tuple[float, dict[str, Any]]] = []
    for p in owned:
        species = db.get_species_data(p.get("species_name") or "") or {}
        if not species:
            continue
        category, amount = _skill_effect(p, species)
        acts = expected_skill_activations_per_day(p, species)
        if category == SHARD_CATEGORY:
            scored.append((acts * amount, p))
        elif category in HEAL_CATEGORIES:
            # 回復役は「かけら型の発動回数を底上げする」価値。桁を揃えるため粗く見積もる
            scored.append((acts * amount * 20.0, p))
        elif _has_help_bonus(p):
            scored.append((acts * 100.0, p))
    scored.sort(key=lambda x: -x[0])
    return [p for _, p in scored[:limit]]


def best_shard_team(
    owned: Sequence[dict[str, Any]],
    *,
    size: int = TEAM_SIZE,
    locked_ids: Sequence[int] = (),
) -> ShardTeam | None:
    """かけら/日が最大になる編成を探す。

    かけら量はチーム内の相互作用（おてつだいボーナスの人数・回復による稼働増）で決まるので、
    1体ずつ独立に評価して上位を並べるだけでは最適にならない。貪欲法で組んでから
    「1体入れ替えて良くなるなら入れ替える」を改善が止まるまで回す（局所探索）。
    """
    pool = _shard_pool(owned)
    locked = [p for p in owned if int(p.get("id") or 0) in set(locked_ids)]
    if len(locked) > size:
        locked = locked[:size]
    pool = locked + [p for p in pool if p not in locked]
    if len(pool) < size:
        pool = list(locked) + [p for p in owned if p not in locked]
    if len(pool) < size:
        return None

    locked_id_set = {int(p.get("id") or 0) for p in locked}

    # 貪欲法: 空から1体ずつ「今いちばん増える子」を足す
    current: list[dict[str, Any]] = list(locked)
    while len(current) < size:
        best_gain = None
        best_pick = None
        for cand in pool:
            if cand in current:
                continue
            score = evaluate_shard_team(current + [cand]).shards_per_day
            if best_gain is None or score > best_gain:
                best_gain, best_pick = score, cand
        if best_pick is None:
            break
        current.append(best_pick)
    if len(current) < size:
        return None

    # 局所探索: 1体入れ替えで改善しなくなるまで
    best = evaluate_shard_team(current)
    improved = True
    guard = 0
    while improved and guard < 20:
        improved = False
        guard += 1
        for i, member in enumerate(list(current)):
            if int(member.get("id") or 0) in locked_id_set:
                continue
            for cand in pool:
                if cand in current:
                    continue
                trial = list(current)
                trial[i] = cand
                result = evaluate_shard_team(trial)
                if result.shards_per_day > best.shards_per_day + 1e-9:
                    current, best, improved = trial, result, True
                    break
            if improved:
                break
    return best


# ---------------------------------------------------------------------------
# おやすみリボン（一緒に寝た時間）
# ---------------------------------------------------------------------------
# data/sleep_ribbon.json の hours（200/500/1000/2000）を単一の出所にする。
def ribbon_thresholds() -> list[tuple[int, float]]:
    """[(段階, 到達に必要な累計時間), ...] を段階順で返す。"""
    return sorted(
        (int(r["stage"]), float(r["hours"])) for r in db.list_all_sleep_ribbon_records()
    )


MAX_STAGE = 4


@dataclass
class RibbonProgress:
    pokemon: dict[str, Any]
    stage: int
    hours: float | None          # 入力された累計時間（未入力は None）
    hours_known: bool
    next_stage: int | None       # None = 最終段階に到達済み
    next_threshold: float | None
    remaining_hours: float | None
    remaining_is_estimate: bool  # 未入力で「今の段階に着いたばかり」と仮定した推定値か
    speed_gain: float            # 次段階でのおてつだい時間の改善（0.067 = +6.7%速くなる）
    inventory_gain: int          # 次段階での所持数ボーナスの増分
    efficiency: float            # 恩恵 ÷ 残り時間（1時間寝るごとの得）

    @property
    def done(self) -> bool:
        return self.next_stage is None


def stage_from_hours(hours: float | None) -> int:
    """累計時間から到達している段階を出す。"""
    if hours is None:
        return 0
    stage = 0
    for st, need in ribbon_thresholds():
        if hours >= need:
            stage = st
    return stage


def ribbon_progress(pokemon: dict[str, Any]) -> RibbonProgress:
    """1体ぶんのリボン進捗と「次の段階に上げる価値」。

    速度の恩恵は**残り進化回数で全く違う**。最終進化形はどの段階でも時間短縮ゼロ
    （所持数だけ増える）で、進化を2回残している個体は段階4で0.75倍まで縮む。
    つまり「リボンを稼ぐ日」に連れて行くべきなのは、原則として進化前の個体になる。
    """
    species_name = pokemon.get("species_name") or ""
    raw_hours = pokemon.get("sleep_hours")
    hours = float(raw_hours) if raw_hours not in (None, "") else None
    recorded = int(pokemon.get("sleep_ribbon_stage") or 0)
    # 時間から分かる段階と登録済みの段階は食い違いうる。進んでいる方を信じる。
    stage = max(recorded, stage_from_hours(hours))

    thresholds = dict(ribbon_thresholds())
    if stage >= MAX_STAGE:
        return RibbonProgress(
            pokemon=pokemon, stage=stage, hours=hours, hours_known=hours is not None,
            next_stage=None, next_threshold=None, remaining_hours=None,
            remaining_is_estimate=False, speed_gain=0.0, inventory_gain=0,
            efficiency=0.0,
        )

    next_stage = stage + 1
    next_threshold = thresholds[next_stage]
    if hours is not None:
        remaining = max(0.0, next_threshold - hours)
        estimate = False
    else:
        # 未入力。今の段階に着いたばかり＝いちばん遠い、と安全側に見積もる。
        current_threshold = thresholds.get(stage, 0.0)
        remaining = next_threshold - current_threshold
        estimate = True

    remaining_evo = count_remaining_evolutions(species_name)
    now_mult = get_time_multiplier(stage=stage, remaining_evolutions=remaining_evo)
    next_mult = get_time_multiplier(stage=next_stage, remaining_evolutions=remaining_evo)
    speed_gain = (now_mult / next_mult - 1.0) if next_mult > 0 else 0.0

    inv_now = db.get_sleep_ribbon_record(stage) if stage > 0 else None
    inv_next = db.get_sleep_ribbon_record(next_stage) or {}
    inventory_gain = int(inv_next.get("cumulative", {}).get("inventory", 0)) - (
        int(inv_now["cumulative"]["inventory"]) if inv_now else 0
    )

    # 「1時間寝るごとにどれだけ得か」。所持数は速度と単位が違うので、
    # +1枠 ≈ おてつだい1%相当という粗い重みで足す（順位付けのためだけの係数）。
    benefit = speed_gain + 0.01 * inventory_gain
    efficiency = benefit / remaining if remaining > 0 else benefit

    return RibbonProgress(
        pokemon=pokemon, stage=stage, hours=hours, hours_known=hours is not None,
        next_stage=next_stage, next_threshold=next_threshold,
        remaining_hours=remaining, remaining_is_estimate=estimate,
        speed_gain=speed_gain, inventory_gain=inventory_gain, efficiency=efficiency,
    )


SORT_KEYS = ("効率", "残り時間", "恩恵")


def ribbon_priorities(
    owned: Iterable[dict[str, Any]], *, sort_by: str = "効率"
) -> list[RibbonProgress]:
    """次の段階に上げる価値が高い順。到達済みの個体は除く。

    寝た時間は編成の5体全員に同じだけ積まれるので、ここには枠の取り合いが無い。
    上位5体をそのまま連れて行けばよい。
    """
    rows = [ribbon_progress(p) for p in owned]
    rows = [r for r in rows if not r.done]
    if sort_by == "残り時間":
        rows.sort(key=lambda r: (r.remaining_hours or 0.0, -r.speed_gain))
    elif sort_by == "恩恵":
        rows.sort(key=lambda r: -(r.speed_gain + 0.01 * r.inventory_gain))
    else:
        rows.sort(key=lambda r: -r.efficiency)
    return rows


def best_ribbon_team(
    owned: Iterable[dict[str, Any]], *, size: int = TEAM_SIZE, sort_by: str = "効率"
) -> list[RibbonProgress]:
    return ribbon_priorities(owned, sort_by=sort_by)[:size]
