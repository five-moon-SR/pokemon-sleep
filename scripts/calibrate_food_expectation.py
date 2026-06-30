"""食材期待値キャリブレーション 比較スクリプト。

貼り付けデータ集/食材期待値キャリブレーション.toml を読み込んで、
utils/food_expectation.py の出力と既存ツールの値を突合する。

使い方:
    cd /c/Users/naosa/claude/private/game/pokemon-sleep
    .venv/Scripts/python.exe -m scripts.calibrate_food_expectation

オプション:
    --case-id 001        指定 id のケースだけ実行（複数指定可: --case-id 001 002）
    --tolerance 0.10     許容誤差（パーセント）。デフォルト 10%。

出力:
    各ケースの差分テーブル ＋ サマリ（平均誤差／最大誤差／一致率）
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# 親ディレクトリをパスに追加してプロジェクトルートのモジュールを import できるように
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import db
from utils.food_expectation import expected_ingredients_per_day
from utils.play_context import PlayContext

CALIB_PATH = ROOT / "貼り付けデータ集" / "食材期待値キャリブレーション.toml"


@dataclass
class CaseResult:
    case_id: str
    species_name: str
    nickname: str
    note: str
    expected_unit: str
    expected_weekend: bool
    rows: list[tuple[str, float, float, float, float]]
    # rows: (食材名, expected, actual, diff, diff_pct)
    error_msg: str = ""
    # 参考記録（現状の比較対象外、TODO 検出にも使う）
    expected_skill_activations: float = 0.0
    expected_skill_effect: str = ""
    expected_skill_total: str = ""
    expected_berry_energy: float = 0.0
    team_help_bonus_count: int = 0           # daifuku 入力「おてつだいボーナス持ちポケモン数」(0〜4)
    exclude_self_genki_recovery: bool = False # daifuku 入力「自身のげんき回復を外す」 ON
    genki_always_80: bool = False             # daifuku 入力「げんきを常に80」 ON
    favorite_berry_on: bool = True            # daifuku 入力「好きなきのみ」 ON/OFF（既存ケースは ON 前提）
    is_template: bool = False  # expected_ingredients 空 = まだ daifuku 値未入力


def _build_context_from_meta(meta: dict[str, Any]) -> PlayContext:
    """_meta から PlayContext を組み立て（指定がない項目はデフォルト）。"""
    return PlayContext(
        research_rank=int(meta.get("play_context_research_rank", 65)),
        pot_capacity=int(meta.get("play_context_pot_capacity", 69)),
        sleep_hours_weekday=float(meta.get("play_context_sleep_weekday_hours", 7.5)),
        sleep_hours_weekend=float(meta.get("play_context_sleep_weekend_hours", 9.0)),
        meal_breakfast=str(meta.get("play_context_meal_breakfast", "06:00")),
        meal_lunch=str(meta.get("play_context_meal_lunch", "12:00")),
        meal_dinner=str(meta.get("play_context_meal_dinner", "18:00")),
    )


def _build_pokemon_from_case(case: dict[str, Any]) -> dict[str, Any]:
    """case 定義 → 個体DB行に相当する dict。subskills は5枠に振る。"""
    subs = list(case.get("subskills") or [])
    # サブスキルは取得Lv順（10/25/50/75/100）に詰める。並び順は既存ツール側の運用に任せる。
    sub_slots = (subs + [None] * 5)[:5]
    lv = int(case.get("level", 1))
    return {
        "species_name": case["species_name"],
        "nickname": case.get("nickname") or "",
        "level": lv,
        "current_level": lv,
        "caught_level": lv,
        "nature": case.get("nature"),
        "subskill_lv10": sub_slots[0],
        "subskill_lv25": sub_slots[1],
        "subskill_lv50": sub_slots[2],
        "subskill_lv75": sub_slots[3],
        "subskill_lv100": sub_slots[4],
        "ingredient_1": case.get("ingredient_1") or None,
        "ingredient_2": case.get("ingredient_2") or None,
        "ingredient_3": case.get("ingredient_3") or None,
        "sleep_ribbon_stage": int(case.get("ribbon_stage", 0)),
    }


def run_case(case: dict[str, Any], ctx: PlayContext) -> CaseResult:
    case_id = str(case.get("id", "?"))
    species_name = case["species_name"]
    nickname = case.get("nickname") or ""
    note = case.get("note") or ""
    expected_unit = case.get("expected_unit", "per_day")
    weekend = bool(case.get("expected_weekend", False))
    expected = dict(case.get("expected_ingredients") or {})

    species = db.get_species_data(species_name)
    if not species:
        return CaseResult(
            case_id=case_id, species_name=species_name, nickname=nickname,
            note=note, expected_unit=expected_unit, expected_weekend=weekend,
            rows=[], error_msg=f"マスター未登録: {species_name}",
        )

    pokemon = _build_pokemon_from_case(case)
    actual_per_day = expected_ingredients_per_day(
        pokemon, species, ctx, weekend=weekend
    )

    # 単位を per_day に揃える
    if expected_unit == "per_week":
        # per_week → per_day に揃える側で割る（5平日 + 2休日 = 7日相当として近似）
        # キャリブ側で per_week は同じ稼働日数仮定が必要なので、ここではシンプルに /7
        scaled_actual = {k: v * 7.0 for k, v in actual_per_day.items()}
        compare_unit_label = "per_week"
        actual_for_compare = scaled_actual
    else:
        compare_unit_label = "per_day"
        actual_for_compare = actual_per_day

    # 食材名の和集合で比較
    all_names = sorted(set(expected) | set(actual_for_compare))
    rows: list[tuple[str, float, float, float, float]] = []
    for name in all_names:
        exp_v = float(expected.get(name, 0.0))
        act_v = float(actual_for_compare.get(name, 0.0))
        diff = act_v - exp_v
        denom = exp_v if exp_v else (act_v if act_v else 1.0)
        diff_pct = (diff / denom) * 100.0
        rows.append((name, exp_v, act_v, diff, diff_pct))

    return CaseResult(
        case_id=case_id, species_name=species_name, nickname=nickname,
        note=note, expected_unit=compare_unit_label, expected_weekend=weekend,
        rows=rows,
        expected_skill_activations=float(case.get("expected_skill_activations") or 0.0),
        expected_skill_effect=str(case.get("expected_skill_effect") or ""),
        expected_skill_total=str(case.get("expected_skill_total") or ""),
        expected_berry_energy=float(case.get("expected_berry_energy") or 0.0),
        team_help_bonus_count=int(case.get("team_help_bonus_count") or 0),
        exclude_self_genki_recovery=bool(case.get("exclude_self_genki_recovery") or False),
        genki_always_80=bool(case.get("genki_always_80") or False),
        favorite_berry_on=bool(case.get("favorite_berry_on", True)),  # デフォは ON（既存ケース踏襲）
        is_template=not bool(expected),
    )


def print_case(result: CaseResult, tolerance_pct: float) -> None:
    label = result.species_name
    if result.nickname:
        label = f"{result.nickname}（{result.species_name}）"
    header = f"\n[case {result.case_id}] {label}"
    if result.note:
        header += f" — {result.note}"
    header += f"  単位={result.expected_unit} 休日={result.expected_weekend}"
    print(header)
    if result.error_msg:
        print(f"  ⚠ {result.error_msg}")
        return
    if result.is_template:
        # daifuku 値未入力（テンプレ状態）。我々の予測値だけ表示
        actual_total = sum(r[2] for r in result.rows)
        actual_breakdown = {r[0]: round(r[2], 2) for r in result.rows if r[2] > 0}
        print(f"  ⏳ daifuku 値未入力（テンプレ）。我々の予測 = 合計 {actual_total:.2f} 個/日 → {actual_breakdown}")
        return
    if not result.rows:
        print("  （比較対象なし）")
        return

    print(f"  {'食材':16s} {'期待':>8s} {'実測':>8s} {'差分':>8s} {'誤差%':>8s}  判定")
    print(f"  {'-'*16} {'-'*8} {'-'*8} {'-'*8} {'-'*8}  {'-'*4}")
    for name, exp_v, act_v, diff, diff_pct in result.rows:
        ok = abs(diff_pct) <= tolerance_pct * 100
        mark = "✓" if ok else "✗"
        print(
            f"  {name:16s} {exp_v:8.2f} {act_v:8.2f} "
            f"{diff:+8.2f} {diff_pct:+7.1f}%  {mark}"
        )
    if result.expected_skill_activations or result.expected_berry_energy:
        line = (
            f"  📋 参考: スキル発動 {result.expected_skill_activations}回/日 "
            f"× {result.expected_skill_effect} = {result.expected_skill_total} "
            f"/ きのみE {result.expected_berry_energy:.0f}"
        )
        flags = []
        if result.team_help_bonus_count:
            flags.append(f"チームおてボ {result.team_help_bonus_count}体")
        if result.exclude_self_genki_recovery:
            flags.append("自身回復除外")
        if result.genki_always_80:
            flags.append("げんき常に80")
        if not result.favorite_berry_on:
            flags.append("好物OFF")
        if flags:
            line += " / " + " / ".join(flags)
        print(line)


def print_summary(results: list[CaseResult], tolerance_pct: float) -> None:
    template_cases = [r for r in results if r.is_template and not r.error_msg]
    filled_cases = [r for r in results if not r.is_template and not r.error_msg]
    total_rows = 0
    matched_rows = 0
    diffs_pct: list[float] = []
    for r in filled_cases:
        for _, _, _, _, diff_pct in r.rows:
            total_rows += 1
            diffs_pct.append(abs(diff_pct))
            if abs(diff_pct) <= tolerance_pct * 100:
                matched_rows += 1

    print("\n" + "=" * 60)
    print("サマリ")
    print("=" * 60)
    print(f"  ケース数:        {len(results)}")
    print(f"  daifuku 値入力済: {len(filled_cases)}")
    print(f"  テンプレ状態:    {len(template_cases)}")
    if template_cases:
        print(f"    → {' / '.join(r.case_id for r in template_cases)}")
    if total_rows == 0:
        print("  （比較対象なし — daifuku 値が未入力）")
        return
    print(f"  比較行数: {total_rows}")
    print(f"  許容誤差: ±{tolerance_pct * 100:.0f}%")
    print(f"  一致率:   {matched_rows} / {total_rows} = {matched_rows/total_rows*100:.1f}%")
    print(f"  平均誤差: {sum(diffs_pct)/len(diffs_pct):.1f}%")
    print(f"  最大誤差: {max(diffs_pct):.1f}%")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", action="append", default=[],
                        help="指定 id のケースだけ実行（複数可）")
    parser.add_argument("--tolerance", type=float, default=0.10,
                        help="許容誤差（小数表記、デフォルト 0.10 = 10%）")
    args = parser.parse_args()

    if not CALIB_PATH.exists():
        print(f"キャリブレーションファイルが見つかりません: {CALIB_PATH}", file=sys.stderr)
        return 1

    with open(CALIB_PATH, "rb") as f:
        data = tomllib.load(f)

    meta = data.get("_meta", {}) or {}
    cases = data.get("case", []) or []

    if args.case_id:
        wanted = set(args.case_id)
        cases = [c for c in cases if str(c.get("id", "")) in wanted]

    print(f"ソース: {meta.get('source_tool') or '(未設定)'}")
    print(f"取得日: {meta.get('acquired_at') or '(未設定)'}")
    if meta.get("note"):
        print(f"メモ:   {meta['note']}")

    ctx = _build_context_from_meta(meta)
    print(
        f"PlayContext: RR={ctx.research_rank} 鍋={ctx.pot_capacity} "
        f"平日睡眠={ctx.sleep_hours_weekday}h 休日睡眠={ctx.sleep_hours_weekend}h"
    )

    if not cases:
        print("\n（ケース未登録）")
        return 0

    results = [run_case(c, ctx) for c in cases]
    for r in results:
        print_case(r, args.tolerance)
    print_summary(results, args.tolerance)
    return 0


if __name__ == "__main__":
    sys.exit(main())
