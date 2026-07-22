"""個体評価チェッカー v1。

設計合意（メモリ参照）:
  species_total = α×species_berry + β×species_food + γ×species_skill + option_bonus
  global_total  = α×global_berry  + β×global_food  + γ×global_skill  + option_bonus

スコアは（個体の理論値 / ベンチマーク）×100 を 0〜100 にクリップして合算後、
SCORE_RANK_THRESHOLDS でランク化する。

ベンチマークは「軸ごとに別の理想性格＋最適サブスキル4枠＋Lv60＋メインスキルLv最大」
で 1 種族につき 1 回計算し lru_cache に乗せる。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from typing import Any

import db
from constants import (
    EVAL_TYPE_WEIGHTS,
    EVALUATION_VERSION,
    INGREDIENT_SLOT_RATIO,
    MAIN_SKILL_CATEGORY_COEF,
    OPTION_BONUS_NATURE,
    OPTION_BONUS_RANGE,
    OPTION_BONUS_SKILL_LVUP_EXTRA,
    OPTION_BONUS_SUBSKILL,
    SUBSKILL_UNLOCK_LEVELS,
    get_nature_modifier,
    infer_eval_type,
    normalize_subskill_name,
    score_to_rank,
)

# 食材スロット解放Lv: A=Lv1, B=Lv30, C=Lv60
_INGREDIENT_SLOT_UNLOCK_LV: tuple[tuple[str, int], ...] = (
    ("a", 1),
    ("b", 30),
    ("c", 60),
)

# 各枠デフォルト食材を「その枠で取った時」の qty list 内インデックス。
# 食材の qty list は「(食材の元枠)以降のスロット位置順」に並んでいる。
# 例: マメミート(a枠) qty=[2,5,7] → a枠で取れば 2、b枠で取れば 5、c枠で取れば 7。
# 評価器ではデフォルト食材を各枠（元枠）で取る前提なので、常に list[0]。
_SLOT_NATIVE_QTY_INDEX: int = 0

# おてつだい時間の Lv 補正係数: Lv1基準で 0.2%/Lv 線形短縮（Wiki公式）。
# Lv60 で base × 0.882。クランプは安全のため 0.5 下限。
_ASSIST_REDUCTION_PER_LEVEL: float = 0.002


def _assist_seconds_at_lv(base_assist_seconds: int, level: int) -> float:
    lv = max(1, int(level))
    factor = max(0.5, 1.0 - _ASSIST_REDUCTION_PER_LEVEL * (lv - 1))
    return float(base_assist_seconds) * factor


def _native_qty(qty_list: list[int] | int) -> int:
    """食材枠デフォルト食材を「その枠（元枠）で取った時」の qty。

    qty list はスロット位置順に並ぶため、デフォルト食材を元枠で取る場合は常に list[0]。
    （以前の Lv段階解釈は誤りだった。詳細は food_expectation.py を参照。）
    """
    if isinstance(qty_list, (int, float)):
        return int(qty_list)
    if not qty_list:
        return 0
    return int(qty_list[_SLOT_NATIVE_QTY_INDEX])


# ---------------------------------------------------------------------------
# データクラス
# ---------------------------------------------------------------------------
@dataclass
class EvaluationResult:
    eval_type: int
    eval_type_source: str  # "daifuku" | "auto"
    weights: tuple[float, float, float]  # α, β, γ

    species_total: float
    species_rank: str
    species_berry: float
    species_food: float
    species_skill: float

    global_total: float
    global_rank: str
    global_berry: float
    global_food: float
    global_skill: float

    option_bonus: float
    option_breakdown: list[tuple[str, float]] = field(default_factory=list)

    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    raw_values: dict[str, Any] = field(default_factory=dict)

    version: str = EVALUATION_VERSION
    computed_at: str = ""

    def __post_init__(self) -> None:
        if not self.computed_at:
            self.computed_at = datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# 物理計算ヘルパー
# ---------------------------------------------------------------------------
def _normalize_subs(subskills: list[str | None]) -> list[str]:
    """None と空文字を除いた正規表記サブスキルのリスト。"""
    out: list[str] = []
    for s in subskills:
        if not s:
            continue
        n = normalize_subskill_name(s)
        if n:
            out.append(n)
    return out


def _speed_mult(nature: str | None, subs: list[str]) -> float:
    """おてつだい速度倍率（1.0 が無補正）。"""
    m = 1.0 + get_nature_modifier(nature, "speed")
    if "おてつだいスピードS" in subs:
        m *= 1.07
    if "おてつだいスピードM" in subs:
        m *= 1.14
    if "おてつだいボーナス" in subs:
        # 公式は「お手伝い時間-5%」相当。bonus=+0.0526...
        m *= 1.05
    return m


def _food_drop_mult(nature: str | None, subs: list[str]) -> float:
    m = 1.0 + get_nature_modifier(nature, "ingredient")
    if "食材確率アップS" in subs:
        m *= 1.18
    if "食材確率アップM" in subs:
        m *= 1.36
    return m


def _skill_proc_mult(nature: str | None, subs: list[str]) -> float:
    m = 1.0 + get_nature_modifier(nature, "skill")
    if "スキル確率アップS" in subs:
        m *= 1.18
    if "スキル確率アップM" in subs:
        m *= 1.36
    return m


def _berry_qty_mult(subs: list[str], base_qty: int) -> float:
    """『きのみの数S』装着で個数+1。"""
    if "きのみの数S" in subs and base_qty > 0:
        return (base_qty + 1) / base_qty
    return 1.0


# 食材・きのみのマスター辞書（base_energy 引き）
@lru_cache(maxsize=1)
def _ingredient_energy_map() -> dict[str, int]:
    return {r["name"]: int(r.get("base_energy") or 0) for r in db.list_all_ingredient_records()}


@lru_cache(maxsize=1)
def _berry_energy_map() -> dict[str, int]:
    return {r["name"]: int(r.get("base_energy") or 0) for r in db.list_all_berry_records()}


@lru_cache(maxsize=1)
def _main_skill_max_level() -> dict[str, int]:
    """カテゴリ → 最大Lv の辞書（複数スキル同カテゴリは max を採用）。"""
    out: dict[str, int] = {}
    for r in db.list_all_main_skill_records():
        cat = r.get("category")
        lv = int(r.get("max_level") or 6)
        if not cat:
            continue
        out[cat] = max(out.get(cat, 0), lv)
    return out


def _main_skill_category(species: dict[str, Any]) -> str | None:
    """種族の main_skill 名 → カテゴリへ解決。

    マスターは「ばけのかわ(きのみバースト)」「エナジーチャージS(ランダム)」のような
    複合表記を55種で使うため、完全一致で見つからない場合は
    括弧の前後をカテゴリ/スキル名と突合するフォールバックで解決する。
    """
    name = species.get("main_skill")
    if not name:
        return None
    records = db.list_all_main_skill_records()
    for r in records:
        if r.get("name") == name:
            return r.get("category")

    # フォールバック: 「固有名(カテゴリ)」の括弧内・括弧前で解決
    m = re.match(r"^(.+?)\(([^)]+)\)$", name)
    if not m:
        return None
    outer, inner = m.group(1).strip(), m.group(2).strip()
    categories = {r.get("category") for r in records}
    # 括弧内がカテゴリそのもの（例: ばけのかわ(きのみバースト)）
    if inner in categories:
        return inner
    for r in records:
        # 括弧内がスキル名（例: きょううん(食材セレクトS)→name食材セレクトS）
        if r.get("name") == inner:
            return r.get("category")
        # 括弧前がスキル名（例: エナジーチャージS(ランダム)、ビルドアップ(料理アシストS)）
        if r.get("name") == outer:
            return r.get("category")
    return None


# ---------------------------------------------------------------------------
# 軸ごとの理論値計算
# ---------------------------------------------------------------------------
def _calc_berry_value(
    species: dict[str, Any],
    *,
    nature: str | None,
    subs: list[str],
    level: int = 60,
) -> float:
    """1秒あたりのきのみエナジー期待値（ポケモンLv補正込み）。"""
    from utils.berry_energy import lv_energy

    berry = species.get("berry") or {}
    base_e = _berry_energy_map().get(berry.get("name"), 0)
    qty = int(berry.get("qty") or 0)
    if base_e <= 0 or qty <= 0:
        return 0.0
    energy_per_berry = lv_energy(base_e, max(1, level))
    base_assist_raw = max(int(species.get("base_assist_seconds") or 1), 1)
    base_assist = _assist_seconds_at_lv(base_assist_raw, level)
    food_rate = float(species.get("food_drop_rate") or 0.0) / 100.0
    speed = _speed_mult(nature, subs)
    qty_mult = _berry_qty_mult(subs, qty)
    return energy_per_berry * qty * (1.0 - food_rate) * speed * qty_mult / base_assist


def _calc_food_value(
    species: dict[str, Any],
    *,
    nature: str | None,
    subs: list[str],
    consider_lv: int,
    ingredient_overrides: tuple[str | None, str | None, str | None] | None = None,
) -> float:
    """1秒あたりの食材エナジー期待値（ポケモンLv補正込み）。

    consider_lv 未満のスロットは ratio 重みごと欠落扱い（=Lv60ベンチに対するペナルティ）。
    qty は各枠デフォルト食材を「その枠（元枠）で取った時の値」= qty_list[0] を使用。
    （以前は Lv段階解釈で list[-1] 等を使っていたが、qty list は実際は
     スロット位置順に並んでおり、デフォルト食材はその元枠で取る前提。
     詳細は food_expectation.py のコメント参照。）
    """
    ings = species.get("ingredients") or {}
    energy_map = _ingredient_energy_map()
    base_assist_raw = max(int(species.get("base_assist_seconds") or 1), 1)
    base_assist = _assist_seconds_at_lv(base_assist_raw, consider_lv)
    food_rate = float(species.get("food_drop_rate") or 0.0) / 100.0
    speed = _speed_mult(nature, subs)
    drop = _food_drop_mult(nature, subs)

    total = 0.0
    for idx, (slot_key, unlock_lv) in enumerate(_INGREDIENT_SLOT_UNLOCK_LV):
        if consider_lv < unlock_lv:
            continue
        ratio = INGREDIENT_SLOT_RATIO[idx]
        ing = ings.get(slot_key) or {}
        qty = _native_qty(ing.get("qty") or [])
        if qty <= 0:
            continue
        if ingredient_overrides and ingredient_overrides[idx]:
            name = ingredient_overrides[idx]
            slot_energy = float(energy_map.get(name, 0)) * float(qty)
        else:
            slot_energy = float(energy_map.get(ing.get("name"), 0)) * float(qty)
        total += ratio * slot_energy
    return total * food_rate * speed * drop / base_assist


def _effective_skill_lv(base_lv: int, max_lv: int, subs: list[str]) -> int:
    """スキルレベルアップS/M サブスキル装着時の実効 Lv。max_lv 上限。"""
    boost = 0
    if "スキルレベルアップM" in subs:
        boost += 2
    elif "スキルレベルアップS" in subs:
        boost += 1
    return min(max_lv, base_lv + boost)


def _calc_skill_value(
    species: dict[str, Any],
    *,
    nature: str | None,
    subs: list[str],
    main_skill_level: int | None,
    level: int = 60,
) -> float:
    """1秒あたりのメインスキル発動価値（エナジー相当換算、ポケモンLv補正込み）。

    効果量テーブルがあるカテゴリは utils/skill_effects.py の精密値を使用。
    未収録カテゴリは MAIN_SKILL_CATEGORY_COEF へフォールバック（粗い旧式）。
    """
    from utils.skill_effects import get_skill_energy_per_activation, get_skill_max_lv

    cat = _main_skill_category(species)
    if not cat:
        return 0.0
    base_assist_raw = max(int(species.get("base_assist_seconds") or 1), 1)
    base_assist = _assist_seconds_at_lv(base_assist_raw, level)
    skill_rate = float(species.get("main_skill_rate") or 0.0) / 100.0
    speed = _speed_mult(nature, subs)
    proc = _skill_proc_mult(nature, subs)

    # スキルLv: 入力 or テーブル/JSON max
    table_max = get_skill_max_lv(cat)
    json_max = _main_skill_max_level().get(cat, 6)
    max_lv = table_max or json_max
    base_lv = int(main_skill_level) if main_skill_level else max_lv
    eff_lv = _effective_skill_lv(base_lv, max_lv, subs)

    # 効果量テーブル経由でエナジー相当を取得（派生スキル固有テーブルを優先）
    energy_per_activation = get_skill_energy_per_activation(
        cat, eff_lv, skill_name=species.get("main_skill")
    )
    if energy_per_activation is None:
        # 未対応カテゴリ（ゆびをふる/きのみバースト/食材セレクト/料理チャンス/料理アシスト/
        # おてつだいサポート/おてつだいブースト/スキルコピー/オールマイティー）は
        # 旧式の係数 × lv_factor で粗く近似。
        coef = MAIN_SKILL_CATEGORY_COEF.get(cat, 1.0)
        lv_factor = max(0.5, min(eff_lv / max_lv, 1.0)) if max_lv > 0 else 1.0
        # 単位スケール合わせ用の暫定 base energy（旧 coef 基準で過去スコアと連続性を保つ）
        FALLBACK_ENERGY_BASE = 1000.0
        energy_per_activation = coef * lv_factor * FALLBACK_ENERGY_BASE

    return skill_rate * speed * proc * energy_per_activation / base_assist


# ---------------------------------------------------------------------------
# ベンチマーク
# ---------------------------------------------------------------------------
# 軸別「理想性格」: その軸を最も伸ばす上昇1軸で、下げる軸が他軸への影響を最小化。
_OPTIMAL_NATURE = {
    "berry": "さみしがり",   # speed↑, energy↓
    "food":  "ひかえめ",     # ingredient↑, speed↓
    "skill": "おだやか",     # skill↑, speed↓
}
# 軸別「理想サブスキル4枠」（重複なし、効果が大きい順）
_OPTIMAL_SUBS = {
    "berry": ["きのみの数S", "おてつだいスピードM", "おてつだいスピードS", "おてつだいボーナス"],
    "food":  ["食材確率アップM", "食材確率アップS", "おてつだいスピードM", "おてつだいスピードS"],
    "skill": ["スキル確率アップM", "スキル確率アップS", "スキルレベルアップM", "スキルレベルアップS"],
}


@lru_cache(maxsize=None)
def species_benchmark(species_name: str) -> dict[str, float]:
    """ベンチマークは Lv60 固定（=ポテンシャル満開時の理想値）。"""
    sp = db.get_species_data(species_name)
    if not sp:
        return {"berry": 0.0, "food": 0.0, "skill": 0.0}
    return {
        "berry": _calc_berry_value(
            sp, nature=_OPTIMAL_NATURE["berry"], subs=_OPTIMAL_SUBS["berry"], level=60
        ),
        "food": _calc_food_value(
            sp, nature=_OPTIMAL_NATURE["food"], subs=_OPTIMAL_SUBS["food"], consider_lv=60
        ),
        "skill": _calc_skill_value(
            sp, nature=_OPTIMAL_NATURE["skill"], subs=_OPTIMAL_SUBS["skill"],
            main_skill_level=None, level=60
        ),
    }


@lru_cache(maxsize=1)
def global_benchmark() -> dict[str, float]:
    out = {"berry": 0.0, "food": 0.0, "skill": 0.0}
    for r in db.list_all_master_records():
        b = species_benchmark(r["species_name"])
        for k in out:
            if b[k] > out[k]:
                out[k] = b[k]
    return out


# ---------------------------------------------------------------------------
# option_bonus
# ---------------------------------------------------------------------------
def _option_bonus(p: dict[str, Any], eval_type: int) -> tuple[float, list[tuple[str, float]]]:
    breakdown: list[tuple[str, float]] = []
    total = 0.0

    subs = _normalize_subs(
        [p.get(f"subskill_lv{lv}") for lv in SUBSKILL_UNLOCK_LEVELS]
    )
    skill_focused = eval_type in (7, 8, 9)
    for s in subs:
        base = OPTION_BONUS_SUBSKILL.get(s)
        if base is None:
            continue
        gain = base
        if skill_focused and s in OPTION_BONUS_SKILL_LVUP_EXTRA:
            gain += OPTION_BONUS_SKILL_LVUP_EXTRA[s]
        if gain != 0.0:
            breakdown.append((s, gain))
            total += gain

    nature = p.get("nature")
    n_bonus = OPTION_BONUS_NATURE.get(nature or "", 0.0)
    if n_bonus != 0.0:
        breakdown.append((f"性格 {nature}", n_bonus))
        total += n_bonus

    lo, hi = OPTION_BONUS_RANGE
    return max(lo, min(hi, total)), breakdown


# ---------------------------------------------------------------------------
# evaluate_pokemon 本体
# ---------------------------------------------------------------------------
def _effective_level(p: dict[str, Any]) -> int:
    return int(p.get("current_level") or p.get("caught_level") or p.get("level") or 1)


def evaluate_pokemon(p: dict[str, Any], eval_level: int | None = None) -> EvaluationResult:
    """個体評価。eval_level 指定時はそのLvで再計算（食材/サブスキル枠/きのみエナジー）。"""
    species = db.get_species_data(p["species_name"]) or {}
    eff_lv = int(eval_level) if eval_level is not None else _effective_level(p)

    # 評価タイプ
    if p.get("daifuku_eval_type"):
        eval_type = int(p["daifuku_eval_type"])
        eval_type_source = "daifuku"
    else:
        eval_type = infer_eval_type(
            species.get("specialty"),
            _main_skill_category(species),
            species.get("main_skill_rate"),
        )
        eval_type_source = "auto"
    weights = EVAL_TYPE_WEIGHTS[eval_type]

    nature = p.get("nature")
    subs = _normalize_subs(
        [p.get(f"subskill_lv{lv}") for lv in SUBSKILL_UNLOCK_LEVELS if eff_lv >= lv]
    )
    main_skill_lv = p.get("main_skill_level") or 1

    # 個体の各軸理論値（eff_lv 基準で計算）
    raw_berry = _calc_berry_value(species, nature=nature, subs=subs, level=eff_lv)
    raw_food = _calc_food_value(
        species,
        nature=nature,
        subs=subs,
        consider_lv=eff_lv,
        ingredient_overrides=(
            p.get("ingredient_1"),
            p.get("ingredient_2"),
            p.get("ingredient_3"),
        ),
    )
    raw_skill = _calc_skill_value(
        species, nature=nature, subs=subs, main_skill_level=int(main_skill_lv), level=eff_lv
    )

    # ベンチマーク
    sp_bench = species_benchmark(p["species_name"])
    gl_bench = global_benchmark()

    def _score(raw: float, bench: float) -> float:
        if bench <= 0:
            return 0.0
        return max(0.0, min((raw / bench) * 100.0, 100.0))

    sp_b = _score(raw_berry, sp_bench["berry"])
    sp_f = _score(raw_food, sp_bench["food"])
    sp_s = _score(raw_skill, sp_bench["skill"])
    gl_b = _score(raw_berry, gl_bench["berry"])
    gl_f = _score(raw_food, gl_bench["food"])
    gl_s = _score(raw_skill, gl_bench["skill"])

    α, β, γ = weights
    option, option_break = _option_bonus(p, eval_type)
    sp_total = α * sp_b + β * sp_f + γ * sp_s + option
    gl_total = α * gl_b + β * gl_f + γ * gl_s + option

    # 強み・弱み（しきい値）
    axis_labels = (("きのみ", sp_b), ("食材", sp_f), ("スキル", sp_s))
    strengths = [n for n, v in axis_labels if v >= 80]
    weaknesses = [n for n, v in axis_labels if v <= 30]

    lv_source = "指定" if eval_level is not None else "現在Lv"
    assumptions = [
        f"考慮Lv={eff_lv}（{lv_source}・食材/サブスキル枠は解放済のみ計算、ベンチマークはLv60固定）"
    ]
    if not p.get("daifuku_eval_type"):
        assumptions.append(f"評価タイプは specialty='{species.get('specialty')}' から自動推定")
    if not p.get("nature"):
        assumptions.append("性格未登録のため補正なしで計算")

    return EvaluationResult(
        eval_type=eval_type,
        eval_type_source=eval_type_source,
        weights=weights,
        species_total=sp_total,
        species_rank=score_to_rank(sp_total, eval_type),
        species_berry=sp_b,
        species_food=sp_f,
        species_skill=sp_s,
        global_total=gl_total,
        global_rank=score_to_rank(gl_total, eval_type),
        global_berry=gl_b,
        global_food=gl_f,
        global_skill=gl_s,
        option_bonus=option,
        option_breakdown=option_break,
        strengths=strengths,
        weaknesses=weaknesses,
        assumptions=assumptions,
        raw_values={
            "berry": raw_berry, "food": raw_food, "skill": raw_skill,
            "species_bench": sp_bench, "global_bench": gl_bench,
        },
    )


def evaluate_and_save(pokemon_id: int) -> EvaluationResult:
    """個体評価を計算し、結果を pokemon テーブルの last_eval_* に書き戻す。"""
    p = db.get_pokemon(pokemon_id)
    if p is None:
        raise ValueError(f"pokemon id={pokemon_id} not found")
    result = evaluate_pokemon(dict(p))
    db.update_pokemon(
        pokemon_id,
        last_eval_species_total=result.species_total,
        last_eval_global_total=result.global_total,
        last_eval_version=result.version,
        last_eval_computed_at=result.computed_at,
    )
    return result


def evaluate_at_levels(
    p: dict[str, Any],
    target_levels: tuple[int, ...] = (50, 60),
) -> dict[str, EvaluationResult]:
    """現状Lv ＋ 指定Lvの評価をまとめて返す。

    キー:
      "current" — 現在の current_level/caught_level/level
      "lv50"    — Lv50想定（サブスキル3枠目解放、食材は a/b 枠の Lv30 段階）
      "lv60"    — Lv60想定（食材3枠目 c 解放）
    """
    out: dict[str, EvaluationResult] = {"current": evaluate_pokemon(p)}
    for lv in target_levels:
        out[f"lv{lv}"] = evaluate_pokemon(p, eval_level=lv)
    return out
