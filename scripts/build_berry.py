"""貼り付けデータ集/きのみデータ.txt（PukiWiki形式）を data/berry.json に変換する。

実行: python scripts/build_berry.py

入力フォーマット例:
  |&ref(./persimberry.png,nolink,20%);|キーのみ|降り注ぐ太陽のエネルギーを&br;吸収すればするほど色鮮やかに成長する。|MIDDLE:&ref(アイコン/ノーマルタイプ.png,nolink,30x30);|ノーマル|28|ウノハナ雪原|
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INPUT = ROOT / "貼り付けデータ集" / "きのみデータ.txt"
OUTPUT = ROOT / "data" / "berry.json"

TYPE_ORDER = [
    "ノーマル", "ほのお", "みず", "でんき", "くさ", "こおり",
    "かくとう", "どく", "じめん", "ひこう", "エスパー", "むし",
    "いわ", "ゴースト", "ドラゴン", "あく", "はがね", "フェアリー",
]
_TYPE_INDEX = {t: i for i, t in enumerate(TYPE_ORDER)}

HEADER_PREFIXES = ("|~", "|SIZE", "|CENTER", "|RIGHT", "|LEFT")


def _is_data_row(line: str) -> bool:
    if not line.startswith("|"):
        return False
    for p in HEADER_PREFIXES:
        if line.startswith(p):
            return False
    if line.endswith("|h") or line.endswith("|c"):
        return False
    return True


def parse_line(line: str) -> dict | None:
    if not _is_data_row(line):
        return None
    cells = line.strip().rstrip("|").split("|")[1:]
    # 期待: [画像, 名前, 説明, タイプアイコン, タイプ, 基礎エナジー, 好物フィールド]
    if len(cells) < 7:
        return None

    name = cells[1].strip()
    if not name:
        return None
    description = cells[2].replace("&br;", "").strip()
    type_name = cells[4].strip()
    try:
        base_energy = int(cells[5].strip())
    except ValueError:
        base_energy = None
    preferred_field = cells[6].strip()

    # アイコンファイル名は &ref(./persimberry.png,...) から抽出
    icon_match = re.search(r"&ref\(\.?/?([^,)]+)", cells[0])
    icon = icon_match.group(1).strip() if icon_match else None

    return {
        "name": name,
        "type": type_name,
        "base_energy": base_energy,
        "preferred_field": preferred_field,
        "icon": icon,
        "description": description,
    }


def build() -> dict:
    text = INPUT.read_text(encoding="utf-8")
    records: list[dict] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        rec = parse_line(raw)
        if rec is None:
            continue
        if rec["name"] in seen:
            continue
        seen.add(rec["name"])
        records.append(rec)

    records.sort(key=lambda r: (_TYPE_INDEX.get(r["type"], 999), r["name"]))
    return {
        "records": records,
        "_meta": {"count": len(records)},
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
