"""貼り付けデータ集/おやすみリボン.txt から data/sleep_ribbon.json を生成する。

実行: python scripts/build_sleep_ribbon.py

仕様（参照: 貼り付けデータ集/おやすみリボン.txt L12-17, L46-49）:
  段階1=200h: 所持数+1
  段階2=500h: 所持数+2 / 進化残1で-5% / 進化残2で-11%
  段階3=1000h: 所持数+3 / プロフィールアイコン
  段階4=2000h: 所持数+2 / 進化残1で-7%(合計-12%) / 進化残2で-14%(合計-25%)

生テキスト側はテーブル混在の PukiWiki 表記でパース困難なので、ここは仕様確定値を埋め込む方式。
将来のVerアップで段階追加・補正値変更があったら本ファイルの STAGES を更新する。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INPUT = ROOT / "貼り付けデータ集" / "おやすみリボン.txt"
OUTPUT = ROOT / "data" / "sleep_ribbon.json"

# 段階別 increment（その段階で「新たに加わる」効果）
STAGES = [
    {
        "stage": 1,
        "hours": 200,
        "increment_inventory": 1,
        "increment_reduction_pct": {0: 0, 1: 0, 2: 0},
        "extras": [],
    },
    {
        "stage": 2,
        "hours": 500,
        "increment_inventory": 2,
        "increment_reduction_pct": {0: 0, 1: 5, 2: 11},
        "extras": [],
    },
    {
        "stage": 3,
        "hours": 1000,
        "increment_inventory": 3,
        "increment_reduction_pct": {0: 0, 1: 0, 2: 0},
        "extras": ["プロフィールアイコン獲得"],
    },
    {
        "stage": 4,
        "hours": 2000,
        "increment_inventory": 2,
        "increment_reduction_pct": {0: 0, 1: 7, 2: 14},
        "extras": [],
    },
]


def build() -> dict:
    records = []
    cum_inventory = 0
    cum_reduction_pct = {0: 0, 1: 0, 2: 0}
    for s in STAGES:
        cum_inventory += s["increment_inventory"]
        for k in (0, 1, 2):
            cum_reduction_pct[k] += s["increment_reduction_pct"][k]
        records.append(
            {
                "stage": s["stage"],
                "hours": s["hours"],
                "icon": f"おやすみリボン{s['stage']}.png",
                "increment": {
                    "inventory": s["increment_inventory"],
                    "time_reduction_pct": {str(k): v for k, v in s["increment_reduction_pct"].items()},
                },
                "cumulative": {
                    "inventory": cum_inventory,
                    "time_reduction_pct": {str(k): v for k, v in cum_reduction_pct.items()},
                    "time_multiplier": {
                        str(k): round(1.0 - cum_reduction_pct[k] / 100.0, 4)
                        for k in (0, 1, 2)
                    },
                },
                "extras": s["extras"],
            }
        )

    return {
        "records": records,
        "_meta": {
            "count": len(records),
            "remaining_evolution_keys": {
                "0": "最終進化形（時間短縮なし、所持数のみ）",
                "1": "あと1回進化可能",
                "2": "あと2回進化可能",
            },
            "stacking_rule": "おやすみリボンの時間短縮は性格・サブスキルとは別軸で乗算する。例: ピチュー(進化残2) × リボン4(0.75) × おてつだいスピードM(0.86) × いじっぱり(0.9) = 0.58倍",
            "inventory_rule": "段階を達成するごとに increment.inventory が加算され、cumulative.inventory が現在の合計上昇値",
            "extras_rule": "stage3 でプロフィールアイコン獲得（おてつだい能力には影響しない演出効果）",
            "version": "Ver.1.10.0実装",
            "source": "貼り付けデータ集/おやすみリボン.txt",
        },
    }


def main() -> int:
    if not INPUT.exists():
        print(f"入力ファイルが見つかりません: {INPUT}", file=sys.stderr)
        return 1
    result = build()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"OK: {result['_meta']['count']} 段階を {OUTPUT.relative_to(ROOT)} に書き出しました")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
