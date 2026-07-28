"""げんき値とおてつだい時間の関係性。

仕様: ポケモンスリープWiki Ver.1.8.1
  - げんき値ごとに「おてつだい時間」が短縮される（time_multiplier）。
  - げんき150〜81 = ×0.45、80〜61 = ×0.52、60〜41 = ×0.58、40〜1 = ×0.66、0 = ×1.00。
  - 1日24h=1440分のげんき推移を加味した実効おてつだい秒数 = 132,888秒。
    これがだいふく期待値チェッカーの計算基準。

期待値計算では「げんきの瞬時倍率」ではなく **1日通算の実効秒数** を使う。
1日のおてつだい回数 = DAILY_EFFECTIVE_ASSIST_SECONDS / 個体のおてつだい時間(秒)
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_PATH = Path(__file__).parent.parent / "data" / "genki.json"


@lru_cache(maxsize=1)
def _load() -> dict:
    with open(_PATH, encoding="utf-8") as f:
        return json.load(f)


# ベース定数（公開用）。data/genki.json から再読込もできるが、頻出なのでモジュール定数として固定。
DAILY_EFFECTIVE_ASSIST_SECONDS: int = 132_888


def get_time_multiplier(genki_value: float) -> float:
    """指定げんき値での「おてつだい時間倍率」を返す（0.45〜1.00）。

    範囲外（負値や 150 超）は端の値にクランプ。
    """
    g = max(0, min(150, int(genki_value)))
    for r in _load()["ranges"]:
        if r["min"] <= g <= r["max"]:
            return float(r["time_multiplier"])
    return 1.0


def get_speed_multiplier(genki_value: float) -> float:
    """指定げんき値での「おてつだい速度倍率」（時間倍率の逆数）。"""
    return 1.0 / get_time_multiplier(genki_value)


if __name__ == "__main__":
    print(f"DAILY_EFFECTIVE_ASSIST_SECONDS = {DAILY_EFFECTIVE_ASSIST_SECONDS}")
    print("げんき値 → 時間倍率")
    for g in [150, 100, 80, 70, 60, 50, 40, 30, 10, 1, 0]:
        m = get_time_multiplier(g)
        print(f"  げんき {g:>3}: ×{m:.2f}（速度 ×{1/m:.3f}）")


# ---------------------------------------------------------------------------
# げんき回復スキルの適用計算
# ---------------------------------------------------------------------------
# DAILY_EFFECTIVE_ASSIST_SECONDS は「起床時げんき100、10分に1ずつ減る」1日を
# 積分した値。実際に 10分刻み144ステップで再現すると 133,197秒 になり、
# genki.json の 132,888秒 とは 0.23% ずれる（出典側の丸め）。
# そこで回復ありの日は **回復なしの日との比** を取り、既存の較正値に掛ける。
# こうすれば回復モデルを足しても、これまでの数字の土台は動かない。
#
# 発動タイミングは「おてつだい進捗の等分」に置く。げんきが高いほど手伝いが速く、
# スキルもその割合で発動するので、自然と午前寄りに寄る。
# （以前の実装は [0, 0.0993, ...] という表を発動回数だけで引いていた。
#  検証するとげんきオールS Lv6・発動を序盤に固めた場合の値と一致したので、
#  出所は同じ物理モデルだが **Lv固定** だった。Lv1の回復5.0%でもLv6の18.1%と
#  同じ加点になっていたことになる。）

_DECAY_PER_STEP = 1          # 10分あたり1減る
_STEPS_PER_DAY = 144         # 24h / 10分
_MINUTES_PER_STEP = 10
_START_GENKI = 100           # 起床直後
_MAX_GENKI = 150


@lru_cache(maxsize=1)
def _no_heal_profile() -> tuple[float, tuple[int, ...]]:
    """回復なしの日の (実効分, おてつだい進捗の等分点を作るための累積率)。"""
    rates = []
    genki = _START_GENKI
    for _ in range(_STEPS_PER_DAY):
        rates.append(1.0 / get_time_multiplier(genki))
        genki = max(0, genki - _DECAY_PER_STEP)
    total = sum(rates) * _MINUTES_PER_STEP
    return total, tuple(rates)


def _activation_steps(count: int) -> set[int]:
    """発動を「おてつだい進捗の等分点」に置く（高げんきほど早く回ってくる）。"""
    if count <= 0:
        return set()
    _, rates = _no_heal_profile()
    total = sum(rates)
    out: set[int] = set()
    acc = 0.0
    k = 1
    for i, r in enumerate(rates):
        acc += r
        while k <= count and acc >= total * k / (count + 1):
            out.add(i)
            k += 1
    return out


@lru_cache(maxsize=512)
def _heal_day_minutes(count: int, heal_percent_x10: int) -> float:
    """回復 count 回・1回あたり heal% の日の実効おてつだい分。"""
    at = _activation_steps(count)
    heal = heal_percent_x10 / 10.0
    genki = _START_GENKI
    total = 0.0
    for step in range(_STEPS_PER_DAY):
        if step in at:
            genki = min(_MAX_GENKI, genki + heal)
        total += _MINUTES_PER_STEP / get_time_multiplier(genki)
        genki = max(0, genki - _DECAY_PER_STEP)
    return total


def heal_assist_boost(activations: float, heal_percent: float) -> float:
    """げんき回復による、その個体のおてつだい量の増分（0.12 = +12%）。

    activations: 1日あたりの回復回数（小数可。げんきエールのように
        「5体からランダム1体」なら 発動回数/5 を渡す）
    heal_percent: 1回あたりの回復量（%）

    回復量が増えても 150 で頭打ちになるので、伸びは線形ではない。
    """
    if activations <= 0 or heal_percent <= 0:
        return 0.0
    base, _ = _no_heal_profile()
    amount = int(round(heal_percent * 10))
    # 小数回はfloor/ceilの補間（発動回数は期待値なので整数とは限らない）
    lo = int(activations)
    hi = lo + 1
    frac = activations - lo
    lo_val = _heal_day_minutes(lo, amount)
    hi_val = _heal_day_minutes(hi, amount) if frac > 0 else lo_val
    minutes = lo_val * (1.0 - frac) + hi_val * frac
    return minutes / base - 1.0


def effective_assist_seconds(activations: float = 0.0, heal_percent: float = 0.0) -> float:
    """げんき回復を織り込んだ1日の実効おてつだい秒数。

    回復なしなら較正済みの DAILY_EFFECTIVE_ASSIST_SECONDS をそのまま返す。
    """
    return DAILY_EFFECTIVE_ASSIST_SECONDS * (1.0 + heal_assist_boost(activations, heal_percent))


@lru_cache(maxsize=256)
def _heal_day_minutes_multi(heals: tuple[tuple[int, int], ...]) -> float:
    """複数のヒーラーぶんの回復を、1本のげんき曲線に重ねて積分する。

    heals は ((回数, 回復量×10), ...)。
    掛け合わせで近似すると 150 の頭打ちを跨いだ時に超線形に増えてしまうので、
    イベントを同じ曲線へ乗せて上限を効かせる。
    """
    # 別のヒーラーの発動が同じ瞬間に重なると、150上限で溢れて無駄になる。
    # 実際はばらけるので、ヒーラーごとに位相をずらして置く。
    events: dict[int, float] = {}
    for i, (count, amount_x10) in enumerate(heals):
        steps = sorted(_activation_steps(count))
        shift = round(_STEPS_PER_DAY * i / (len(heals) * max(count + 1, 1)))
        for step in steps:
            slot = min(_STEPS_PER_DAY - 1, step + shift)
            events[slot] = events.get(slot, 0.0) + amount_x10 / 10.0
    genki = _START_GENKI
    total = 0.0
    for step in range(_STEPS_PER_DAY):
        if step in events:
            genki = min(_MAX_GENKI, genki + events[step])
        total += _MINUTES_PER_STEP / get_time_multiplier(genki)
        genki = max(0, genki - _DECAY_PER_STEP)
    return total


def combined_heal_boost(heals: list[tuple[float, float]]) -> float:
    """複数の回復源をまとめた、おてつだい量の増分。

    heals は (1体あたりの回復回数/日, 1回あたりの回復量%) のリスト。
    小数回は floor/ceil の2通りを重み付き平均する（各要素で別々に丸めると
    組み合わせ爆発するので、合計回数の端数だけを補間する）。
    """
    usable = [(a, amt) for a, amt in heals if a > 0 and amt > 0]
    if not usable:
        return 0.0
    base, _ = _no_heal_profile()

    def _key(round_up: bool) -> tuple[tuple[int, int], ...]:
        return tuple(
            sorted(
                (
                    (int(a) + 1 if round_up and a != int(a) else int(a)),
                    int(round(amt * 10)),
                )
                for a, amt in usable
            )
        )

    frac = max((a - int(a)) for a, _ in usable)
    lo = _heal_day_minutes_multi(_key(False))
    if frac <= 0:
        return lo / base - 1.0
    hi = _heal_day_minutes_multi(_key(True))
    return (lo * (1.0 - frac) + hi * frac) / base - 1.0
