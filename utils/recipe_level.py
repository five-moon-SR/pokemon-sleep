"""レシピレベルと、それを踏まえた料理エナジー。

ゲーム内の料理エナジーは次の式で決まる:

    料理エナジー(Lv) = 基準エナジー(Lv1) × (1 + レベルボーナス)

レベルボーナスは**全料理共通**で、レシピごとに違わない。
出典側（wikiwiki「料理」）の表と、`貼り付けデータ集/料理データ+α.txt` の
ヘッダ行「Lv1 1.00倍 / Lv30 1.61倍 / Lv60 3.03倍」が一致している。

data/recipe.json の実測比でも lv30/lv1 = 1.6099、lv60/lv1 = 3.0299（76件の中央値）で、
ズレは整数丸めのぶんだけ（最大1）。つまり energy_lv1 さえあれば任意のレベルを再現できる。

これまでアプリは常に energy_lv60 を使っていたため、まだ作り込んでいない料理を
3倍に過大評価していた。ここを実レベルに合わせると、編成の最適解そのものが動く。

レベルは user_settings の `user.recipe_levels` に {レシピ名: Lv} で持つ。
未登録は Lv1（＝未開拓）とみなす。

「ごちゃまぜ」3種は energy_lv1 が 0 で、仕様上もレシピレベルの恩恵を受けない。
どのレベルでも 0 を返す。
"""

from __future__ import annotations

import threading
from typing import Any

import db

RECIPE_LEVELS_KEY = "user.recipe_levels"

MIN_LEVEL = 1
MAX_LEVEL = 70

# Lv1〜Lv70 のボーナス（%）。添字 0 が Lv1。
_BONUS_PERCENT: tuple[int, ...] = (
    0, 2, 4, 6, 8, 9, 11, 13, 16, 18,          # Lv1-10
    19, 21, 23, 24, 26, 28, 30, 31, 33, 35,     # Lv11-20
    37, 40, 42, 45, 47, 50, 52, 55, 58, 61,     # Lv21-30
    64, 67, 70, 74, 77, 81, 84, 88, 92, 96,     # Lv31-40
    100, 104, 108, 113, 117, 122, 127, 132, 137, 142,  # Lv41-50
    148, 153, 159, 165, 171, 177, 183, 190, 197, 203,  # Lv51-60
    209, 215, 221, 227, 234, 239, 243, 248, 252, 258,  # Lv61-70
)

# レベル → 倍率（1.00 / 1.61 / 3.03 …）
LEVEL_MULTIPLIER: dict[int, float] = {
    lv: 1.0 + pct / 100.0 for lv, pct in enumerate(_BONUS_PERCENT, start=MIN_LEVEL)
}


def clamp_level(level: Any) -> int:
    """Lv を [1, 70] に丸める。数値でなければ Lv1。"""
    try:
        value = int(level)
    except (TypeError, ValueError):
        return MIN_LEVEL
    return max(MIN_LEVEL, min(MAX_LEVEL, value))


def level_multiplier(level: Any) -> float:
    """そのレベルの倍率。Lv1 なら 1.0。"""
    return LEVEL_MULTIPLIER[clamp_level(level)]


# ---------------------------------------------------------------------------
# 保存された料理レベル
# ---------------------------------------------------------------------------
# recipe_energy() は計算の深いところ（optimizer の内側など）から呼ばれるので、
# 引数で引き回さずここで握る。DBを叩き続けないようプロセス内にキャッシュし、
# 保存時に clear_cache() で落とす。
_levels_cache: dict[str, int] | None = None
_cache_lock = threading.Lock()
_load_error: str | None = None


def clear_cache() -> None:
    """保存済みレベルのキャッシュを捨てる（保存直後に呼ぶ）。"""
    global _levels_cache, _load_error
    with _cache_lock:
        _levels_cache = None
        _load_error = None


def load_error() -> str | None:
    """レベルの読み込みに失敗していればその理由。

    読めなかった場合は全レシピ Lv1 として扱うが、それを黙ってやると
    「本当に未開拓」と「設定が読めていない」が区別できなくなる。
    UI 側はこれを見て警告を出すこと。
    """
    return _load_error


def load_recipe_levels() -> dict[str, int]:
    """{レシピ名: Lv}。未登録のレシピは含まれない（＝Lv1扱い）。

    料理エナジーは計算の深いところから引かれるので、設定が読めない環境
    （DB未設定のテストなど）でもシミュレーション自体は動くようにする。
    失敗は load_error() で拾えるようにして、黙って握り潰さない。
    """
    global _levels_cache, _load_error
    with _cache_lock:
        if _levels_cache is not None:
            return dict(_levels_cache)
    try:
        raw = db.get_setting(RECIPE_LEVELS_KEY, {}) or {}
    except Exception as exc:
        with _cache_lock:
            _levels_cache = {}
            _load_error = str(exc)
        return {}
    levels = {
        str(name): clamp_level(lv)
        for name, lv in raw.items()
        if clamp_level(lv) > MIN_LEVEL  # Lv1 は既定値なので保存しない
    }
    with _cache_lock:
        _levels_cache = dict(levels)
        _load_error = None
    return levels


def save_recipe_levels(levels: dict[str, int]) -> None:
    """{レシピ名: Lv} を保存する。Lv1 は既定値なので落とす。"""
    cleaned = {
        str(name): clamp_level(lv)
        for name, lv in (levels or {}).items()
        if clamp_level(lv) > MIN_LEVEL
    }
    db.set_setting(RECIPE_LEVELS_KEY, cleaned)
    clear_cache()


def get_recipe_level(recipe_name: str | None) -> int:
    """1品ぶんの登録レベル。未登録は Lv1。"""
    if not recipe_name:
        return MIN_LEVEL
    return load_recipe_levels().get(str(recipe_name), MIN_LEVEL)


def levels_signature() -> str:
    """st.cache_data のキーに混ぜるための短い署名。

    レベルを変えてもキャッシュが外れないと、古いエナジーで並んだ結果が返る。
    """
    levels = load_recipe_levels()
    return ";".join(f"{name}={lv}" for name, lv in sorted(levels.items()))


# ---------------------------------------------------------------------------
# 料理エナジー
# ---------------------------------------------------------------------------
def base_energy(recipe: dict[str, Any]) -> int:
    """レシピの基準エナジー（Lv1 の値）。

    energy_lv1 が欠けている場合だけ、Lv30/Lv60 から逆算して拾う
    （マスター更新の過渡期に片方しか無いことがあるため）。
    """
    lv1 = recipe.get("energy_lv1")
    if lv1:
        return int(lv1)
    lv30 = recipe.get("energy_lv30")
    if lv30:
        return int(round(int(lv30) / LEVEL_MULTIPLIER[30]))
    lv60 = recipe.get("energy_lv60")
    if lv60:
        return int(round(int(lv60) / LEVEL_MULTIPLIER[60]))
    return 0


def recipe_energy(recipe: dict[str, Any] | None, level: Any = None) -> float:
    """そのレシピを1回作ったときのエナジー。

    level を省略すると、保存済みの料理レベル（未登録なら Lv1）を使う。
    ごちゃまぜ系は基準エナジーが 0 なので、どのレベルでも 0。
    """
    if not recipe:
        return 0.0
    base = base_energy(recipe)
    if base <= 0:
        return 0.0
    lv = clamp_level(level) if level is not None else get_recipe_level(recipe.get("name"))
    return base * level_multiplier(lv)
