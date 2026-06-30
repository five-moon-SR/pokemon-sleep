"""個体評価チェッカーの精度を測定するスクリプト。

所持DBの「daifuku 評価済み」個体について、以下を検証する:
  1. infer_eval_type 一致率（=だいふくの eval_type と推定が一致した割合）
  2. species_total（％換算）と daifuku_eval_percent の数値誤差

旧 v1.2 では infer_eval_type 一致率 80/85 = 94.1% だった。
v1.3 で食材qty解釈を修正したため再測定する。

評価モード（--mode で切り替え）:
  - individual: 個体の現状（種族・Lv60・サブスキル・性格・msl=現状）
  - max:        個体の現状種族・Lv60・msl=MAX（旧 v1.2 メモリの基準）
  - projected:  最終進化形態へ projection・Lv60・msl=現在値 + 残り進化回数（推奨）
                  - 食材枠は最終進化形態のデフォルトを採用（個体の選択は無視）
                  - 分岐進化（イーブイ等）は最初に出てきた進化先を採用する近似

使い方:
    cd /c/Users/naosa/claude/private/game/pokemon-sleep
    .venv/Scripts/python.exe -m scripts.verify_evaluator_accuracy --mode projected

オプション:
    --mode {individual|max|projected}   評価モード（デフォルト: projected）
    --show-mismatches    eval_type 不一致個体を全リスト出力
    --show-all           全個体の比較結果を出力
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import db
from constants import infer_eval_type
from utils.evaluator import _main_skill_category, evaluate_pokemon
from utils.skill_effects import get_skill_max_lv


def project_to_final_evolution(species_name: str) -> tuple[str, int]:
    """指定種族から最終進化形態を辿り、(最終進化名, 残り進化回数) を返す。

    分岐進化（イーブイ等）は最初の進化先を採用する近似。
    特殊フォーム（ピカチュウ(ハロウィン)等）は最終進化扱いで残り0。
    """
    visited = {species_name}
    count = 0
    current = species_name
    while True:
        nexts = db.list_evolutions_from(current)
        if not nexts:
            break
        next_name = nexts[0]["to"]
        if next_name in visited:
            break  # cycle protection
        visited.add(next_name)
        current = next_name
        count += 1
    return current, count


def _build_eval_subject(p: dict, mode: str) -> tuple[dict, str | None]:
    """評価モードに応じて評価対象 dict を組み立てる。

    返り値: (評価用 p, 元の表示名と異なる場合の最終進化形態名 or None)
    """
    p_eval = dict(p)
    p_eval["daifuku_eval_type"] = None  # auto 推定

    if mode == "individual":
        species = db.get_species_data(p["species_name"]) or {}
        return p_eval, None

    if mode == "max":
        species = db.get_species_data(p["species_name"]) or {}
        cat = _main_skill_category(species)
        max_lv = get_skill_max_lv(cat) if cat else None
        if max_lv:
            p_eval["main_skill_level"] = max_lv
        return p_eval, None

    if mode == "projected":
        final_name, evos = project_to_final_evolution(p["species_name"])
        final_species = db.get_species_data(final_name) or {}
        if not final_species:
            final_name = p["species_name"]
            final_species = db.get_species_data(final_name) or {}
            evos = 0
        p_eval["species_name"] = final_name
        # 食材枠は最終進化形態のデフォルトに任せる（個体の選択は無効化）
        p_eval["ingredient_1"] = None
        p_eval["ingredient_2"] = None
        p_eval["ingredient_3"] = None
        # main_skill_lv = 現在値 + 残り進化回数（max_lv 上限）
        current_msl = p.get("main_skill_level") or 1
        cat = _main_skill_category(final_species)
        max_lv = get_skill_max_lv(cat) if cat else None
        msl = current_msl + evos
        if max_lv:
            msl = min(msl, max_lv)
        p_eval["main_skill_level"] = msl
        projected_label = final_name if final_name != p["species_name"] else None
        return p_eval, projected_label

    raise ValueError(f"unknown mode: {mode}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["individual", "max", "projected"],
                        default="projected", help="評価モード（デフォルト: projected）")
    parser.add_argument("--show-mismatches", action="store_true",
                        help="eval_type 不一致個体を全リスト出力")
    parser.add_argument("--show-all", action="store_true",
                        help="全個体の比較結果を出力")
    args = parser.parse_args()
    print(f"評価モード: {args.mode}")

    rows = [dict(r) for r in db.list_pokemon() if r["daifuku_eval_type"] is not None]
    print(f"daifuku 評価済み個体: {len(rows)} 体")

    type_match = 0
    type_mismatch_rows: list[tuple[str, str, int, int, float]] = []
    pct_diffs: list[tuple[str, float, float, float]] = []  # name, daifuku%, our%, diff
    eval_errors: list[tuple[str, str]] = []

    for p in rows:
        nick = p.get("nickname") or p["species_name"]
        species = db.get_species_data(p["species_name"]) or {}

        # --- infer_eval_type 一致判定 ---
        inferred = infer_eval_type(
            species.get("specialty"),
            _main_skill_category(species),
            species.get("main_skill_rate"),
        )
        daifuku_type = int(p["daifuku_eval_type"])
        rate = float(species.get("main_skill_rate") or 0.0)
        if inferred == daifuku_type:
            type_match += 1
        else:
            type_mismatch_rows.append(
                (nick, p["species_name"], daifuku_type, inferred, rate)
            )

        # --- species_total 数値誤差 ---
        # 評価モードに応じて daifuku 整合用の対象を組み立て、Lv60 で評価する。
        try:
            p_eval, projected_label = _build_eval_subject(p, args.mode)
            res = evaluate_pokemon(p_eval, eval_level=60)
        except Exception as e:
            eval_errors.append((nick, str(e)))
            continue
        if projected_label and args.show_all:
            nick = f"{nick}→{projected_label}"

        daifuku_pct = p.get("daifuku_eval_percent")
        if daifuku_pct is None:
            continue
        diff = res.species_total - float(daifuku_pct)
        pct_diffs.append((nick, float(daifuku_pct), res.species_total, diff))

    # --- レポート ---
    print()
    print("=" * 70)
    print("【1】infer_eval_type 一致率（評価タイプ自動推定の精度）")
    print("=" * 70)
    print(f"  一致: {type_match} / {len(rows)} = {type_match/len(rows)*100:.1f}%")

    if type_mismatch_rows:
        print(f"  不一致: {len(type_mismatch_rows)} 体")
        if args.show_mismatches or args.show_all:
            print()
            print(f"  {'ニックネーム':12s} {'種族':16s} だいふく → 推定 (rate)")
            print(f"  {'-'*12} {'-'*16} {'-'*22}")
            for nick, sp, dt, it, rate in type_mismatch_rows:
                print(f"  {nick:12s} {sp:16s} ⑨{dt} → ⑨{it} ({rate:.2f}%)"
                      .replace("⑨1", "①").replace("⑨2", "②").replace("⑨3", "③")
                      .replace("⑨4", "④").replace("⑨5", "⑤").replace("⑨6", "⑥")
                      .replace("⑨7", "⑦").replace("⑨8", "⑧"))

    print()
    print("=" * 70)
    print("【2】species_total スコア vs daifuku 評価%（数値精度）")
    print("=" * 70)
    if not pct_diffs:
        print("  比較対象なし")
    else:
        abs_diffs = [abs(d[3]) for d in pct_diffs]
        avg_diff = sum(d[3] for d in pct_diffs) / len(pct_diffs)
        avg_abs = sum(abs_diffs) / len(abs_diffs)
        max_abs = max(abs_diffs)
        within_5 = sum(1 for d in abs_diffs if d <= 5.0)
        within_10 = sum(1 for d in abs_diffs if d <= 10.0)
        within_15 = sum(1 for d in abs_diffs if d <= 15.0)
        n = len(pct_diffs)
        print(f"  測定数:        {n} 体")
        print(f"  平均差分:      {avg_diff:+.2f} pt（符号付き）")
        print(f"  平均絶対誤差:  {avg_abs:.2f} pt")
        print(f"  最大絶対誤差:  {max_abs:.2f} pt")
        print(f"  ±5pt 以内:    {within_5} / {n} = {within_5/n*100:.1f}%")
        print(f"  ±10pt 以内:   {within_10} / {n} = {within_10/n*100:.1f}%")
        print(f"  ±15pt 以内:   {within_15} / {n} = {within_15/n*100:.1f}%")

        if args.show_all:
            print()
            print(f"  {'ニックネーム':12s} {'だいふく%':>9s} {'我々%':>8s} {'差分':>8s}")
            print(f"  {'-'*12} {'-'*9} {'-'*8} {'-'*8}")
            for nick, dp, op, diff in sorted(pct_diffs, key=lambda x: -abs(x[3]))[:30]:
                print(f"  {nick:12s} {dp:9.2f} {op:8.2f} {diff:+8.2f}")
            if n > 30:
                print(f"  ... 上位30体のみ表示（全{n}体）")

    if eval_errors:
        print()
        print(f"⚠ 評価エラー: {len(eval_errors)} 体")
        for nick, err in eval_errors[:5]:
            print(f"  {nick}: {err}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
