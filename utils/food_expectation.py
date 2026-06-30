"""1日あたりの食材獲得期待値（個数ベース、v0.2）。

party.py の料理期待値計算から呼び出して、メンバー個別の食材産出を集計する。
評価器（utils/evaluator.py）の物理計算ヘルパを流用しているので、補正係数は両者で一貫する。

v0.2 で変更:
  * 1日のおてつだい総時間を「active_hours × 3600」から
    DAILY_EFFECTIVE_ASSIST_SECONDS (=132,888秒) に変更。
    これはげんきの値帯ごとの時間倍率（150〜81=0.45 など）を24h分積分した値で、
    だいふく期待値チェッカーと同じモデル。
    リザードン Lv60 サブなしの校正で誤差 0.4% に縮小。

v0.2 の対象範囲:
  * おてつだい補正：性格・サブスキル（おてスピS/M、おてつだいボーナス）・Lv補正
  * 食材確率補正：性格・サブスキル（食材確率S/M）
  * 食材枠の解放Lv（a=Lv1, b=Lv30, c=Lv60）と Lv段階別 qty
  * おやすみリボンによる時間倍率（リボン × 性格 × サブスキルの独立3軸乗算）
  * げんき値帯ごとの実効おてつだい秒数（24h通算 132,888秒モデル）

v0.3 以降の予定:
  * メインスキル「食材ゲットS / 食材セレクトS」の追加食材
  * 最大所持数による取りこぼし（夜のキャップ）
  * げんき回復系スキルの自身げんき回復ループ補正
  * 食事タイミングと料理成功率
  * きのみ獲得期待値の同種関数
  * PlayContext.sleep_hours と連動した「日中/睡眠中」分割モデル
"""

from __future__ import annotations

from typing import Any

from constants import INGREDIENT_SLOT_RATIO
from utils.berry_energy import lv_energy
from utils.evaluator import (
    _INGREDIENT_SLOT_UNLOCK_LV,
    _assist_seconds_at_lv,
    _berry_energy_map,
    _berry_qty_mult,
    _food_drop_mult,
    _normalize_subs,
    _speed_mult,
)
from utils.genki import DAILY_EFFECTIVE_ASSIST_SECONDS
from utils.play_context import PlayContext
from utils.sleep_ribbon import get_time_multiplier

# 各枠が「最初に取れるスロット位置（0始まり）」。a枠食材は第一スロット(0)から、b枠は第二(1)から、c枠は第三(2)から。
_SLOT_ORIGIN_INDEX: dict[str, int] = {"a": 0, "b": 1, "c": 2}


def _effective_level(p: dict[str, Any]) -> int:
    return int(p.get("current_level") or p.get("caught_level") or p.get("level") or 1)


def _individual_subs(p: dict[str, Any]) -> list[str]:
    return _normalize_subs(
        [
            p.get("subskill_lv10"),
            p.get("subskill_lv25"),
            p.get("subskill_lv50"),
            p.get("subskill_lv75"),
            p.get("subskill_lv100"),
        ]
    )


def find_food_origin(species: dict[str, Any], food_name: str) -> str | None:
    """指定食材名が species の a/b/c どの枠の食材かを返す。見つからなければ None。"""
    ings = species.get("ingredients") or {}
    for slot_key in ("a", "b", "c"):
        slot_def = ings.get(slot_key)
        if slot_def and slot_def.get("name") == food_name:
            return slot_key
    return None


def qty_at_slot(species: dict[str, Any], food_name: str, slot_idx: int) -> int:
    """個体が第 (slot_idx+1) スロットでこの食材を取った時の獲得個数。

    qty list は「枠スタート位置（食材の元枠）から先のスロット位置順」に並んでいる前提。
    例: マメミート(a枠) qty=[2,5,7] → 第一=2 / 第二=5 / 第三=7
        あったかジンジャー(b枠) qty=[4,7] → 第二=4 / 第三=7（第一は不可）
        げきからハーブ(c枠) qty=[6] → 第三=6（第一・第二は不可）
    """
    origin = find_food_origin(species, food_name)
    if origin is None:
        return 0
    origin_idx = _SLOT_ORIGIN_INDEX[origin]
    if slot_idx < origin_idx:
        return 0  # その食材はそのスロット位置では取れない
    qty_list = ((species.get("ingredients") or {}).get(origin) or {}).get("qty") or []
    rel = slot_idx - origin_idx
    if rel >= len(qty_list):
        return 0
    return int(qty_list[rel])


def expected_ingredients_per_day(
    pokemon: dict[str, Any],
    species: dict[str, Any],
    play_context: PlayContext | None = None,
    *,
    weekend: bool = False,
    team_help_bonus_count: int = 0,
) -> dict[str, float]:
    """個体ごとの 1日あたり食材獲得期待値を {食材名: 個数} で返す。

    複数枠で同じ食材を選んでいる場合は同じキーに合算される。
    現在Lvは current_level → caught_level → level の順でフォールバック。
    food_drop_rate が null の8種は空辞書を返す（=食材は出ない扱い）。

    team_help_bonus_count: 自身含むチームの「おてつだいボーナス」装着数（0-5）。
        speed × (1 + 0.05 × N)。daifuku 期待値チェッカー検証で確定（v0.3 補正1）。

    play_context / weekend 引数は v0.3 で「日中/睡眠中」分割モデルに移行する際に使う予定。
    v0.2 では使用しない（げんき変動を加味した日合計実効秒数で1日を表す）。
    """
    food_rate = float(species.get("food_drop_rate") or 0.0) / 100.0
    if food_rate <= 0.0:
        return {}

    level = _effective_level(pokemon)
    nature = pokemon.get("nature")
    subs = _individual_subs(pokemon)

    base_assist_raw = max(int(species.get("base_assist_seconds") or 1), 1)
    base_assist = _assist_seconds_at_lv(base_assist_raw, level)

    ribbon_stage = int(pokemon.get("sleep_ribbon_stage") or 0)
    species_name = pokemon.get("species_name") or species.get("name") or ""
    ribbon_time_mult = (
        get_time_multiplier(species_name=species_name, stage=ribbon_stage)
        if ribbon_stage > 0
        else 1.0
    )

    speed = _speed_mult(nature, subs)
    if team_help_bonus_count > 0:
        speed *= 1.0 + 0.05 * team_help_bonus_count
    drop = _food_drop_mult(nature, subs)

    # 1日のおてつだい回数 = 実効秒数 × 速度倍率 / 個体のおてつだい時間
    # 実効秒数 132,888 はげんき変動を加味した1日通算（だいふく互換）。
    # リボンは時間軸、speed は速度軸なので逆数で乗算する独立2軸補正。
    assists_per_day = (
        DAILY_EFFECTIVE_ASSIST_SECONDS * speed / (base_assist * ribbon_time_mult)
    )
    food_assists_per_day = assists_per_day * food_rate * drop

    if food_assists_per_day <= 0.0:
        return {}

    ings = species.get("ingredients") or {}
    # 個体が選んだ各スロットの食材（未指定なら master のデフォルト枠食材を当てる）
    default_names = (
        (ings.get("a") or {}).get("name"),
        (ings.get("b") or {}).get("name"),
        (ings.get("c") or {}).get("name"),
    )
    chosen = (
        pokemon.get("ingredient_1") or default_names[0],
        pokemon.get("ingredient_2") or default_names[1],
        pokemon.get("ingredient_3") or default_names[2],
    )

    # 開放スロットで正規化（実ゲームでは食材獲得時に開放枠から1つ等確率で選ばれる）。
    # c枠なし種族（=ペルシアン等）でも、第三スロットは a/b 枠の食材から選択可能。
    # 個体側で ingredient_3 が指定されていれば第三スロットを「使う」と判定する。
    # ingredient_n が None かつ master のデフォルトも無い場合のみスロットを除外。
    unlocked_indices: list[int] = []
    for idx, (_, unlock_lv) in enumerate(_INGREDIENT_SLOT_UNLOCK_LV):
        if level < unlock_lv:
            continue
        if not chosen[idx]:
            continue  # 個体が食材を入れていない（c枠なし種族で ingredient_3 未指定など）
        unlocked_indices.append(idx)
    total_weight = sum(INGREDIENT_SLOT_RATIO[i] for i in unlocked_indices) or 1.0

    result: dict[str, float] = {}
    for idx in unlocked_indices:
        name = chosen[idx]
        if not name:
            continue
        qty = qty_at_slot(species, name, idx)
        if qty <= 0:
            continue
        slot_ratio = INGREDIENT_SLOT_RATIO[idx] / total_weight
        slot_count = food_assists_per_day * slot_ratio * float(qty)
        result[name] = result.get(name, 0.0) + slot_count

    return result


def expected_berry_per_day(
    pokemon: dict[str, Any],
    species: dict[str, Any],
    play_context: PlayContext | None = None,
    *,
    fav_berries: set[str] | None = None,
    field_bonus: float = 0.0,
    team_help_bonus_count: int = 0,
) -> dict[str, Any]:
    """個体の1日あたりきのみ獲得個数とエナジーを返す。

    Returns: {name, count, energy_per_unit, energy, is_favorite, qty_per_assist}
        species にきのみ未設定なら name=None で 0埋め辞書を返す。

    fav_berries: 今週の好物きのみ集合（フィールド固有 or ランダム週の3種）。当該きのみが
        含まれていれば is_favorite=True、エナジー単価 ×2。
    field_bonus: フィールドのきのみエナジーボーナス（0.5=+50% 等）。週イベ補正で上乗せ可。
    team_help_bonus_count: 自身含むチームの「おてつだいボーナス」装着数（0-5）。
        speed × (1 + 0.05 × N)。
    """
    berry = species.get("berry") or {}
    name = berry.get("name")
    if not name:
        return {
            "name": None, "count": 0.0, "energy_per_unit": 0.0, "energy": 0.0,
            "is_favorite": False, "qty_per_assist": 0.0,
        }

    food_rate = float(species.get("food_drop_rate") or 0.0) / 100.0
    level = _effective_level(pokemon)
    nature = pokemon.get("nature")
    subs = _individual_subs(pokemon)

    base_assist_raw = max(int(species.get("base_assist_seconds") or 1), 1)
    base_assist = _assist_seconds_at_lv(base_assist_raw, level)

    ribbon_stage = int(pokemon.get("sleep_ribbon_stage") or 0)
    species_name = pokemon.get("species_name") or species.get("name") or ""
    ribbon_time_mult = (
        get_time_multiplier(species_name=species_name, stage=ribbon_stage)
        if ribbon_stage > 0
        else 1.0
    )

    speed = _speed_mult(nature, subs)
    if team_help_bonus_count > 0:
        speed *= 1.0 + 0.05 * team_help_bonus_count

    assists_per_day = (
        DAILY_EFFECTIVE_ASSIST_SECONDS * speed / (base_assist * ribbon_time_mult)
    )
    berry_assists = assists_per_day * (1.0 - food_rate)

    base_qty = int(berry.get("qty") or 0)
    qty = base_qty * _berry_qty_mult(subs, base_qty)
    count = berry_assists * qty

    base_energy = _berry_energy_map().get(name, 0)
    is_favorite = bool(fav_berries) and name in fav_berries
    fav_mul = 2.0 if is_favorite else 1.0
    energy_per_unit = (
        lv_energy(base_energy, max(1, level)) * (1.0 + field_bonus) * fav_mul
        if base_energy > 0 else 0.0
    )
    energy = count * energy_per_unit

    return {
        "name": name,
        "count": count,
        "energy_per_unit": energy_per_unit,
        "energy": energy,
        "is_favorite": is_favorite,
        "qty_per_assist": qty,
    }


if __name__ == "__main__":
    # python -m utils.food_expectation で簡易検算
    import db
    from utils.play_context import load_play_context

    ctx = load_play_context()
    print(f"DAILY_EFFECTIVE_ASSIST_SECONDS = {DAILY_EFFECTIVE_ASSIST_SECONDS}")

    owned = [dict(r) for r in db.list_pokemon()]
    if not owned:
        print("所持ポケモンなし。検算スキップ。")
    else:
        sample = owned[: min(3, len(owned))]
        for p in sample:
            species = db.get_species_data(p["species_name"]) or {}
            if not species:
                print(f"  {p['species_name']}: マスター未登録、スキップ")
                continue
            res = expected_ingredients_per_day(p, species, ctx)
            label = p.get("nickname") or p["species_name"]
            lv = _effective_level(p)
            print(f"\n[{label}] {p['species_name']} Lv{lv}")
            print(f"  1日合計: {sum(res.values()):.2f} 個 → {dict((k, round(v, 2)) for k, v in res.items())}")
