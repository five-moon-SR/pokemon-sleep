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

import db
from constants import INGREDIENT_SLOT_RATIO
from utils.berry_energy import lv_energy
from utils.evaluator import (
    _INGREDIENT_SLOT_UNLOCK_LV,
    _assist_seconds_at_lv,
    _berry_energy_map,
    _berry_qty_mult,
    _effective_skill_lv,
    _food_drop_mult,
    _normalize_subs,
    _skill_proc_mult,
    _speed_mult,
)
from utils.genki import DAILY_EFFECTIVE_ASSIST_SECONDS
from utils.skill_effects import get_skill_effect_amount, get_skill_max_lv
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


def composition_string(pokemon: dict[str, Any], species: dict[str, Any]) -> str:
    """個体の食材構成表記（AAA / ABB / ABC 等）を返す。

    各スロットの選択食材を枠(a/b/c)に逆引きして大文字で並べる。
    未入力スロットは「?」（スロット1だけは仕様上A確定なのでAを返す）。
    例: "AAA" / "AB?" / "A??"
    """
    letters: list[str] = []
    default_a = ((species.get("ingredients") or {}).get("a") or {}).get("name")
    for i, key in enumerate(("ingredient_1", "ingredient_2", "ingredient_3")):
        name = pokemon.get(key) or (default_a if i == 0 else None)
        if not name:
            letters.append("?")
            continue
        origin = find_food_origin(species, name)
        letters.append(origin.upper() if origin else "?")
    return "".join(letters)


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


# ---------------------------------------------------------------------------
# メインスキルで増える「食材」
# ---------------------------------------------------------------------------
# どのスキルが食材を何から拾うかは data/main_skill.json の `ingredient_yield` に
# 宣言する（コード側にスキル名を埋めない）。形式:
#   "ingredient_yield": {"pool": "own_slots", "pick": 1}          … 自分の食材3枠から1種
#   "ingredient_yield": {"pool": "fixed", "names": [...], "pick": 1} … 固定候補から1種
# 1発動あたりの個数は utils/skill_effects.py のカテゴリ表（例: 食材セレクトS）を使う。
#
# 食材セレクトS の仕様（wikiwiki / ゲームエイトで確認、2026-09）:
#   発動すると、その個体の食材構成3種のうち 1種をランダムに選んで N個 獲得する。
#   食材枠の解放状況は問わない（Lv30/60 未解放でも b/c 枠の食材が出る）。
# 「食材ゲットS」は全食材からのランダムで種類を特定できないため宣言していない
# （従来どおりエナジー換算のまま）。派生表記の「きょううん(食材セレクトS)」
# 「かいりきバサミ(食材セレクトS)」は候補4種の内訳が未確認なので同じく未宣言。
# 分かった時点で main_skill.json に1行足せば、この計算はそのまま効く。


def _ingredient_yield_spec(species: dict[str, Any]) -> dict[str, Any] | None:
    """食材が増えるスキルの宣言を引く。無ければ None。

    種族側（data/pokemon_master.json）の宣言を優先し、無ければスキル側
    （data/main_skill.json）を見る。きょううん・かいりきバサミの4種プールは
    種族ごとに中身が違う（統一規則は見つかっていない）ので種族側に持たせている。
    """
    own = species.get("ingredient_yield")
    if isinstance(own, dict):
        return own
    name = (species.get("main_skill") or "").strip()
    if not name:
        return None
    for rec in db.list_all_main_skill_records():
        if rec.get("name") == name:
            spec = rec.get("ingredient_yield")
            return spec if isinstance(spec, dict) else None
    return None


def _skill_category_of(species: dict[str, Any]) -> str:
    """種族の main_skill 名 → カテゴリ（マスタ引き。見つからなければ名前そのまま）。"""
    name = (species.get("main_skill") or "").strip()
    for rec in db.list_all_main_skill_records():
        if rec.get("name") == name:
            return str(rec.get("category") or name)
    return name


def has_skill_ingredients(species: dict[str, Any]) -> bool:
    """メインスキルで食材が増える種族か（マスタに ingredient_yield 宣言があるか）。"""
    return _ingredient_yield_spec(species) is not None


def _skill_ingredient_pool(
    pokemon: dict[str, Any], species: dict[str, Any], spec: dict[str, Any]
) -> list[str]:
    """スキルの抽選対象になる食材名。"""
    pool = str(spec.get("pool") or "own_slots")
    if pool == "fixed":
        return [str(n) for n in (spec.get("names") or []) if n]
    # own_slots: 個体が選んだ食材（未指定なら master の既定枠）。解放状況は問わない。
    ings = species.get("ingredients") or {}
    defaults = (
        (ings.get("a") or {}).get("name"),
        (ings.get("b") or {}).get("name"),
        (ings.get("c") or {}).get("name"),
    )
    chosen = (
        pokemon.get("ingredient_1") or defaults[0],
        pokemon.get("ingredient_2") or defaults[1],
        pokemon.get("ingredient_3") or defaults[2],
    )
    return [name for name in chosen if name]


def expected_skill_activations_per_day(
    pokemon: dict[str, Any],
    species: dict[str, Any],
    *,
    team_help_bonus_count: int = 0,
) -> float:
    """1日あたりのメインスキル発動回数の期待値。

    おてつだい回数の出し方は expected_ingredients_per_day と同じ軸
    （日次実効秒数 × 速度倍率 / おてつだい時間 / リボン時間倍率）。
    """
    skill_rate = float(species.get("main_skill_rate") or 0.0) / 100.0
    if skill_rate <= 0.0:
        return 0.0

    level = _effective_level(pokemon)
    subs = _individual_subs(pokemon)
    base_assist = _assist_seconds_at_lv(
        max(int(species.get("base_assist_seconds") or 1), 1), level
    )
    ribbon_stage = int(pokemon.get("sleep_ribbon_stage") or 0)
    species_name = pokemon.get("species_name") or species.get("name") or ""
    ribbon_time_mult = (
        get_time_multiplier(species_name=species_name, stage=ribbon_stage)
        if ribbon_stage > 0
        else 1.0
    )
    speed = _speed_mult(pokemon.get("nature"), subs)
    if team_help_bonus_count > 0:
        speed *= 1.0 + 0.05 * team_help_bonus_count

    assists_per_day = (
        DAILY_EFFECTIVE_ASSIST_SECONDS * speed / (base_assist * ribbon_time_mult)
    )
    return assists_per_day * skill_rate * _skill_proc_mult(pokemon.get("nature"), subs)


def expected_skill_ingredients_per_day(
    pokemon: dict[str, Any],
    species: dict[str, Any],
    *,
    team_help_bonus_count: int = 0,
) -> dict[str, float]:
    """メインスキルで1日に増える食材 {食材名: 個数/日}。宣言が無いスキルは空辞書。

    「N個を候補のうち1種類」なので、どれが出るかは確率。期待値として
    N / 候補数 を各食材に配る（同じ食材を複数枠に持つ個体はその分だけ厚くなる）。
    """
    spec = _ingredient_yield_spec(species)
    if not spec:
        return {}
    names = _skill_ingredient_pool(pokemon, species, spec)
    if not names:
        return {}

    subs = _individual_subs(pokemon)
    # 1発動あたりの獲得個数はマスタの count_by_level を正本にする。
    # 未宣言のスキルだけ skill_effects.py のカテゴリ表にフォールバックする。
    counts = {int(k): float(v) for k, v in (spec.get("count_by_level") or {}).items()}
    category = _skill_category_of(species)
    max_lv = (max(counts) if counts else None) or get_skill_max_lv(category) or 7
    eff_lv = _effective_skill_lv(
        int(pokemon.get("main_skill_level") or 1), max_lv, subs
    )
    if counts:
        per_activation = counts.get(min(max(eff_lv, min(counts)), max(counts)), 0.0)
    else:
        per_activation = get_skill_effect_amount(category, eff_lv) or 0.0
    if per_activation <= 0.0:
        return {}

    acts = expected_skill_activations_per_day(
        pokemon, species, team_help_bonus_count=team_help_bonus_count
    )
    if acts <= 0.0:
        return {}

    picks = int(spec.get("pick") or 1)
    share = picks / len(names)
    out: dict[str, float] = {}
    for name in names:
        out[name] = out.get(name, 0.0) + per_activation * acts * share
    return out


def expected_ingredients_per_day(
    pokemon: dict[str, Any],
    species: dict[str, Any],
    play_context: PlayContext | None = None,
    *,
    weekend: bool = False,
    team_help_bonus_count: int = 0,
    include_main_skill: bool = True,
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
    skill_ings = (
        expected_skill_ingredients_per_day(
            pokemon, species, team_help_bonus_count=team_help_bonus_count
        )
        if include_main_skill
        else {}
    )

    food_rate = float(species.get("food_drop_rate") or 0.0) / 100.0
    if food_rate <= 0.0:
        return dict(skill_ings)

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
        return dict(skill_ings)

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

    for name, qty in skill_ings.items():
        result[name] = result.get(name, 0.0) + qty

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
