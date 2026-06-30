"""おやすみリボンの効果計算（時間短縮倍率／所持数ボーナス）。

仕様: data/sleep_ribbon.json （4段階の cumulative.time_multiplier / cumulative.inventory）
進化残り回数: data/evolution.json から再帰的に算出。

例:
  >>> count_remaining_evolutions("ピチュー")
  2
  >>> get_time_multiplier("ピチュー", stage=4)
  0.75
  >>> get_inventory_bonus(stage=4)
  8

おやすみリボンの時間短縮は性格・サブスキルとは別軸で乗算する。
"""

from __future__ import annotations

from functools import lru_cache

from db import (
    get_sleep_ribbon_record,
    list_all_sleep_ribbon_records,
    list_evolutions_from,
)


# 特殊な姿で最終進化扱いになるポケモン（lvアップ進化先がない）
# 生テキスト: ピカチュウ(ハロウィン)/ピカチュウ(ホリデー) は ライチュウ へ進化できないため最終進化扱い
_FORCE_FINAL_FORMS: set[str] = {
    "ピカチュウ(ハロウィン)",
    "ピカチュウ(ホリデー)",
}


@lru_cache(maxsize=512)
def count_remaining_evolutions(species_name: str) -> int:
    """指定種族から最終進化までの残り進化回数を返す（0=最終進化形、1=あと1回、2=あと2回）。

    分岐がある場合は最大値を採用（例: イーブイなら最終形までの最長段数=1）。
    特殊フォーム（ピカチュウ(ハロウィン)等）は強制的に 0 を返す。
    """
    if species_name in _FORCE_FINAL_FORMS:
        return 0
    nexts = list_evolutions_from(species_name)
    if not nexts:
        return 0
    return 1 + max(count_remaining_evolutions(n["to"]) for n in nexts)


def _clamp_remaining_key(remaining: int) -> str:
    """テーブルのキーは "0"/"1"/"2" のみ。それ以上は "2" に丸める（将来の3段進化に備えて安全側）。"""
    return str(min(max(remaining, 0), 2))


def get_time_multiplier(species_name: str | None = None, stage: int = 0,
                        remaining_evolutions: int | None = None) -> float:
    """指定段階での時間短縮倍率を返す（性格・サブスキル補正は別途）。

    species_name が与えられれば残り進化回数を自動算出、または remaining_evolutions を直接指定可能。
    stage<=0（リボンなし）またはレコード未登録なら 1.0。
    """
    rec = get_sleep_ribbon_record(stage)
    if rec is None:
        return 1.0
    if remaining_evolutions is None:
        if species_name is None:
            raise ValueError("species_name か remaining_evolutions のどちらかが必要")
        remaining_evolutions = count_remaining_evolutions(species_name)
    key = _clamp_remaining_key(remaining_evolutions)
    return float(rec["cumulative"]["time_multiplier"].get(key, 1.0))


def get_inventory_bonus(stage: int) -> int:
    """指定段階での所持数ボーナス（累計）。stage<=0 なら 0。"""
    rec = get_sleep_ribbon_record(stage)
    if rec is None:
        return 0
    return int(rec["cumulative"]["inventory"])


def compose_total_time_multiplier(
    *,
    species_name: str | None = None,
    ribbon_stage: int = 0,
    nature_speed_factor: float = 1.0,
    subskill_speed_factor: float = 1.0,
    remaining_evolutions: int | None = None,
) -> float:
    """おてつだい時間の総合倍率を、リボン × 性格 × サブスキル の順で乗算して返す。

    例: ピチュー(進化残2) × リボン4(0.75) × おてつだいスピードM(0.86) × いじっぱり(0.9)
       = 0.75 * 0.86 * 0.9 = 0.5805

    nature_speed_factor: 性格による「おてつだい時間」倍率（▲1.11なら時間×0.9 → 0.9を渡す）
    subskill_speed_factor: サブスキル合算後の「おてつだい時間」倍率（35%上限後の値を渡す）
    """
    ribbon = get_time_multiplier(species_name=species_name, stage=ribbon_stage,
                                 remaining_evolutions=remaining_evolutions)
    return ribbon * nature_speed_factor * subskill_speed_factor


def stage_for_hours(hours: float) -> int:
    """累積眠時間（時間）から到達済みの最大リボン段階を返す。0=未達。"""
    achieved = 0
    for r in list_all_sleep_ribbon_records():
        if hours >= r["hours"]:
            achieved = r["stage"]
        else:
            break
    return achieved


if __name__ == "__main__":
    samples = [
        ("ピチュー", 4),
        ("ピカチュウ", 4),
        ("ライチュウ", 4),
        ("ピカチュウ(ハロウィン)", 4),
        ("フシギダネ", 2),
        ("カメックス", 4),
    ]
    for name, stage in samples:
        rem = count_remaining_evolutions(name)
        mult = get_time_multiplier(name, stage)
        inv = get_inventory_bonus(stage)
        print(f"{name:20s} stage={stage} remaining={rem} time_mul={mult} inv+{inv}")
