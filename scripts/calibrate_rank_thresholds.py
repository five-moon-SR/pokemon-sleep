"""ランク閾値の独自キャリブレーション。

背景(2026-07-23): だいふく公式のランク帯(特にタイプ⑤〜⑨のS=60%〜)は甘く、
そこそこの個体が軒並みSになる。スコア%自体はだいふくと一致することを実サイトで
検証済み(リザードンLv60良個体: だいふく61.44% vs 自前60.0%)なので、
%は互換のままランク帯だけを「育成済みLv60個体群の分布」から厳格化する。

母集団: 全種族 × 品質4段(無補正/並/良/優)のLv60合成個体。
品質アンカー方式: ランクに「個体の質」の意味を持たせる。
  C=無補正の中央値 / B=並の中央値 / A=良(金1+スピM)の中央値
  S=良と優の中間 / SS=優(適正金2+M)の中央値 / 増田=優の上位10%
→ Sは「明確に良く仕上がった個体」、SS以上は理想ビルド級だけになる。

実行: .venv/bin/python scripts/calibrate_rank_thresholds.py
出力: 評価タイプ別の閾値表(constants.py の RANK_THRESHOLDS_BY_TYPE に貼る)
"""

from __future__ import annotations

import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402
from utils.evaluator import evaluate_pokemon  # noqa: E402

GOLD = ["きのみの数S", "おてつだいボーナス", "げんき回復ボーナス", "ゆめのかけらボーナス"]
QUALITIES = ("plain", "mid", "good", "great")


# 得意分野に噛み合ったサブスキル/性格でビルドする(ミスマッチだと帯が潰れる)
_AXIS_BUILD = {
    "きのみ": {"nature": "さみしがり", "subs": ["きのみの数S", "おてつだいスピードM", "おてつだいボーナス"]},
    "食材":   {"nature": "ひかえめ",   "subs": ["食材確率アップM", "おてつだいスピードM", "食材確率アップS"]},
    "スキル": {"nature": "おだやか",   "subs": ["スキル確率アップM", "スキルレベルアップM", "おてつだいスピードM"]},
    "オール": {"nature": "ひかえめ",   "subs": ["おてつだいスピードM", "きのみの数S", "食材確率アップM"]},
}


def _variant(quality: str, specialty: str) -> dict:
    build = _AXIS_BUILD.get(specialty or "きのみ", _AXIS_BUILD["きのみ"])
    if quality == "plain":
        return {"nature": None, "main_skill_level": 3}
    if quality == "mid":
        return {"nature": "てれや", "subskill_lv10": "おてつだいスピードS", "main_skill_level": 4}
    if quality == "good":
        return {"nature": build["nature"], "subskill_lv10": build["subs"][0],
                "subskill_lv25": "おてつだいスピードS", "main_skill_level": 6}
    return {"nature": build["nature"],
            "subskill_lv10": build["subs"][0],
            "subskill_lv25": build["subs"][1],
            "subskill_lv50": build["subs"][2],
            "main_skill_level": 6}


def build_population() -> dict[int, dict[str, list[float]]]:
    random.seed(20260723)
    pools: dict[int, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for name in db.list_species_names():
        specialty = (db.get_species_data(name) or {}).get("specialty") or "きのみ"
        for q in QUALITIES:
            p = {"species_name": name, "current_level": 60, **_variant(q, specialty)}
            er = evaluate_pokemon(p)
            pools[er.eval_type][q].append(er.species_total)
    return pools


def _pctl(xs: list[float], q: float) -> float:
    s = sorted(xs)
    return s[max(0, min(len(s) - 1, int(len(s) * q)))]


def thresholds_from(qpool: dict[str, list[float]]) -> list[tuple[float, str]]:
    good_med = _pctl(qpool["good"], 0.50)
    great_med = _pctl(qpool["great"], 0.50)
    anchors = [
        ("増田", _pctl(qpool["great"], 0.90)),   # 理想ビルドの上位1割だけ
        ("SS",  great_med),                      # 理想ビルドの半数
        ("S",   (good_med + great_med) / 2),     # 良と理想の中間 = 「明確に良く仕上がった個体」
        ("A",   good_med),                       # 金1+スピM級
        ("B",   _pctl(qpool["mid"], 0.50)),      # 並(白サブ)級
        ("C",   _pctl(qpool["plain"], 0.50)),    # 無補正級
    ]
    out = []
    prev = 999.0
    for rank, v in anchors:
        th = round(v * 2) / 2
        th = min(th, prev - 2.0)  # 最低2ptの帯を保証
        out.append((th, rank))
        prev = th
    return out


def main() -> None:
    pools = build_population()
    # 全体プール(品質別)
    merged: dict[str, list[float]] = defaultdict(list)
    for t, qp in pools.items():
        for q, xs in qp.items():
            merged[q].extend(xs)
    n_total = sum(len(xs) for xs in merged.values())
    print(f"母集団: {n_total} 個体 / タイプ: {sorted(pools)}")

    print("\nRANK_THRESHOLDS_BY_TYPE: dict[int, list[tuple[float, str]]] = {")
    for t in range(1, 10):
        qp = pools.get(t)
        small = qp is None or len(qp["great"]) < 10
        use = merged if small else qp
        ths = thresholds_from(use)
        body = ", ".join(f'({th}, "{rk}")' for th, rk in ths)
        note = "  # 標本少: 全体分布で代用" if small else f"  # n={len(qp['great'])}種"
        print(f"    {t}: [{body}],{note}")
    print("}")


if __name__ == "__main__":
    main()
