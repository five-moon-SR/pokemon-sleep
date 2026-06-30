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
