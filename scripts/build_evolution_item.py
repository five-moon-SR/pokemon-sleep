"""貼り付けデータ集/基本データ.txt の進化アイテム表（L289-307）を data/evolution_item.json に変換する。

実行: python scripts/build_evolution_item.py

入力フォーマット例:
  |&attachref(アイコン/ほのおのいし.png,nolink,30x30);|ほのおのいし|#includex(...)|
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INPUT = ROOT / "貼り付けデータ集" / "基本データ.txt"
OUTPUT = ROOT / "data" / "evolution_item.json"

CATEGORIES = {
    "connection": "進化リンク用（通信進化代替）",
    "stone": "○○のいし系（タイプ進化）",
    "seal": "おうじゃのしるし",
    "coat": "メタルコート",
    "claw": "するどいツメ",
    "round": "まんまるいし",
}


def categorize(name: str) -> str:
    if "ヒモ" in name:
        return "connection"
    if "しるし" in name:
        return "seal"
    if "コート" in name:
        return "coat"
    if "ツメ" in name:
        return "claw"
    if "まんまる" in name:
        return "round"
    if "いし" in name:
        return "stone"
    return "other"


def parse_text(text: str) -> list[dict]:
    """進化アイテムの表行を抽出する。"""
    records: list[dict] = []
    in_section = False
    seen: set[str] = set()
    for raw in text.splitlines():
        line = raw.rstrip()
        if "進化アイテム" in line and line.startswith("***"):
            in_section = True
            continue
        if not in_section:
            continue
        # 別の見出し（*** または **）が来たら終了
        if line.startswith("***") or line.startswith("**"):
            if "進化アイテム" not in line:
                break
        if not line.startswith("|"):
            continue
        # ヘッダ行や書式行はスキップ
        if line.startswith("|~") or line.startswith("|35") or line.endswith("|h") or line.endswith("|c"):
            continue
        cells = line.rstrip("|").split("|")[1:]
        if len(cells) < 2:
            continue
        # 期待: [画像, 名前, 入手方法]
        icon_match = re.search(r"&attachref\(アイコン/([^,)]+)", cells[0])
        if not icon_match:
            continue
        icon = icon_match.group(1).strip()
        name = cells[1].strip()
        if not name or name in seen:
            continue
        seen.add(name)
        records.append(
            {
                "name": name,
                "icon": icon,
                "category": categorize(name),
                "description": "",
            }
        )
    return records


def build() -> dict:
    text = INPUT.read_text(encoding="utf-8")
    records = parse_text(text)
    if not records:
        raise RuntimeError("進化アイテムが1件も抽出できませんでした")
    return {
        "records": records,
        "_meta": {
            "count": len(records),
            "categories": CATEGORIES,
            "source": "貼り付けデータ集/基本データ.txt L289-307",
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
    print(f"OK: {result['_meta']['count']} 件を {OUTPUT.relative_to(ROOT)} に書き出しました")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
