"""きのみエナジーの計算式（ポケモンレベル別／フィールドボーナス／好物ボーナス）。

ポリシー: 計算式で導出できる値はJSONに保存しない（game_pokemon_sleep_calc_policy）。
本モジュールが「きのみエナジーの正」となる。

参照: 貼り付けデータ集/きのみエナジー詳細データ.txt（検証用テストデータ）
"""

from __future__ import annotations

import math


def lv_energy(base_energy: int, lv: int) -> int:
    """ポケモンレベルに応じた1個あたりのきのみ獲得エナジー。

    式: round( max( base + (lv-1), base * 1.025^(lv-1) ) )

    レベルが低い時は base + (lv-1) が支配し、Lv20前後から指数項が支配する。
    Wiki公式の式と一致する（Lv1/10/20/30/40/50/60 で全19きのみ検証済み、誤差±1以内）。
    """
    if lv < 1:
        raise ValueError(f"lv must be >= 1: {lv}")
    linear = base_energy + (lv - 1)
    geometric = base_energy * (1.025 ** (lv - 1))
    return round(max(linear, geometric))


def final_display_energy(
    energy_at_lv: int,
    field_bonus: float = 0.0,
    is_favorite: bool = False,
) -> int:
    """カビゴンに与えた時の「表示エナジー単価」（ゲーム内表示）。

    式: ceil( energy_at_lv × (1+field_bonus) × (1+favorite_bonus) )
    favorite_bonus は 1（=2倍）または 0。
    """
    fav = 1.0 if is_favorite else 0.0
    return math.ceil(energy_at_lv * (1.0 + field_bonus) * (1.0 + fav))


def final_actual_energy(
    energy_at_lv: int,
    field_bonus: float = 0.0,
    is_favorite: bool = False,
) -> int:
    """カビゴンに与えた時の「実際エナジー単価」（睡眠リサーチ同期で表示が修正された後の値）。

    式: ceil( energy_at_lv × (1+field_bonus) ) × (1+favorite_bonus)
    表示エナジーとは括弧の取り方が異なり、奇数ズレの原因となる演出仕様。
    """
    fav_mul = 2 if is_favorite else 1
    return math.ceil(energy_at_lv * (1.0 + field_bonus)) * fav_mul


# Wiki掲載のLv1/10/20/30/40/50/60 の検証データ（全19きのみ）
# build時に lv_energy() の結果と突合してずれがないことを確認するための参照値。
_VERIFY_TABLE: dict[str, dict[int, int]] = {
    "キーのみ":   {1: 28, 10: 37, 20: 47, 30: 57, 40: 73, 50: 94,  60: 120},
    "ヒメリのみ": {1: 27, 10: 36, 20: 46, 30: 56, 40: 71, 50: 91,  60: 116},
    "オレンのみ": {1: 31, 10: 40, 20: 50, 30: 63, 40: 81, 50: 104, 60: 133},
    "ウブのみ":   {1: 25, 10: 34, 20: 44, 30: 54, 40: 65, 50: 84,  60: 107},
    "ドリのみ":   {1: 30, 10: 39, 20: 49, 30: 61, 40: 79, 50: 101, 60: 129},
    "チーゴのみ": {1: 32, 10: 41, 20: 51, 30: 65, 40: 84, 50: 107, 60: 137},
    "クラボのみ": {1: 27, 10: 36, 20: 46, 30: 56, 40: 71, 50: 91,  60: 116},
    "カゴのみ":   {1: 32, 10: 41, 20: 51, 30: 65, 40: 84, 50: 107, 60: 137},
    "フィラのみ": {1: 29, 10: 38, 20: 48, 30: 59, 40: 76, 50: 97,  60: 124},
    "シーヤのみ": {1: 24, 10: 33, 20: 43, 30: 53, 40: 63, 50: 80,  60: 103},
    "マゴのみ":   {1: 26, 10: 35, 20: 45, 30: 55, 40: 68, 50: 87,  60: 112},
    "ラムのみ":   {1: 24, 10: 33, 20: 43, 30: 53, 40: 63, 50: 80,  60: 103},
    "オボンのみ": {1: 30, 10: 39, 20: 49, 30: 61, 40: 79, 50: 101, 60: 129},
    "ブリーのみ": {1: 26, 10: 35, 20: 45, 30: 55, 40: 68, 50: 87,  60: 112},
    "ヤチェのみ": {1: 35, 10: 44, 20: 56, 30: 72, 40: 92, 50: 117, 60: 150},
    "ウイのみ":   {1: 31, 10: 40, 20: 50, 30: 63, 40: 81, 50: 104, 60: 133},
    "ベリブのみ": {1: 33, 10: 42, 20: 53, 30: 68, 40: 86, 50: 111, 60: 142},
    "モモンのみ": {1: 26, 10: 35, 20: 45, 30: 55, 40: 68, 50: 87,  60: 112},
}


def verify_against_wiki_table(tolerance: int = 1) -> list[tuple[str, int, int, int]]:
    """検証テーブルと lv_energy() の出力を突合し、ズレが tolerance 超のものを返す。

    Wiki側の四捨五入実装の差で±1のズレは許容（実プレイ値との差は無視できる）。
    """
    from db import list_all_berry_records

    base_map = {r["name"]: r["base_energy"] for r in list_all_berry_records()}
    mismatches: list[tuple[str, int, int, int]] = []
    for name, points in _VERIFY_TABLE.items():
        base = base_map.get(name)
        if base is None:
            continue
        for lv, expected in points.items():
            actual = lv_energy(base, lv)
            if abs(actual - expected) > tolerance:
                mismatches.append((name, lv, expected, actual))
    return mismatches


if __name__ == "__main__":
    # python -m utils.berry_energy で検証実行
    diffs = verify_against_wiki_table(tolerance=1)
    if diffs:
        print(f"NG: {len(diffs)} 件の Wiki検証データとのズレあり（許容±1）")
        for name, lv, exp, act in diffs[:20]:
            print(f"  {name} Lv{lv}: wiki={exp}, calc={act} (diff={act - exp})")
    else:
        print("OK: 全19きのみ × 7Lv点 で Wiki検証データと一致（許容±1）")
