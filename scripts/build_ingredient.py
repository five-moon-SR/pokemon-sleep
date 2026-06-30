"""貼り付けデータ集/食材データ.txt（PukiWiki形式）を data/ingredient.json に変換する。

実行: python scripts/build_ingredient.py

入力フォーマット例:
  |&attachref(./largeleek.png,nolink,30x30);|[[ふといながねぎ>食材/ふといながねぎ]]|カモネギが好む&br;植物のクキなのかは謎。|185|61%&br;(いあいぎりすき焼きカレー)&br;(スパークスパイスコーラ)|995|7|

列: [画像, 名前, 説明, 基礎エナジー, 食材数ボーナス最大値, 実質エナジー最大値, かけら売価]
食材数ボーナス最大値の中身: 「<percent>%&br;(<レシピ1>)&br;(<レシピ2>)…」
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INPUT = ROOT / "貼り付けデータ集" / "食材データ.txt"
OUTPUT = ROOT / "data" / "ingredient.json"

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


def _extract_link_text(cell: str) -> str:
    """`[[表示>リンク先]]` または `[[表示]]` から表示部を取り出す。"""
    m = re.search(r"\[\[(.+?)\]\]", cell)
    text = m.group(1) if m else cell
    if ">" in text:
        text = text.split(">", 1)[0]
    return text.replace("&br;", "").strip()


def _extract_icon(cell: str) -> str | None:
    """`&attachref(./largeleek.png,...)` や `&attachref(アイコン/めざましコーヒー.png,...)` から
    ファイル名（basename）を取り出す。"""
    m = re.search(r"&attachref\(([^,)]+)", cell)
    if not m:
        return None
    path = m.group(1).strip()
    return path.rsplit("/", 1)[-1] if "/" in path else path


def _parse_max_bonus(cell: str) -> tuple[int | None, list[str]]:
    """`61%&br;(いあいぎりすき焼きカレー)&br;(スパークスパイスコーラ)` を (61, [...]) に。"""
    pct_match = re.search(r"(\d+)\s*%", cell)
    pct = int(pct_match.group(1)) if pct_match else None
    recipes = [m.strip() for m in re.findall(r"\(([^)]+)\)", cell)]
    return pct, recipes


def parse_line(line: str) -> dict | None:
    if not _is_data_row(line):
        return None
    cells = line.strip().rstrip("|").split("|")[1:]
    if len(cells) < 7:
        return None

    name = _extract_link_text(cells[1])
    if not name:
        return None
    icon = _extract_icon(cells[0])
    description = cells[2].replace("&br;", "").strip()
    try:
        base_energy = int(cells[3].strip())
    except ValueError:
        base_energy = None
    max_bonus_pct, max_bonus_recipes = _parse_max_bonus(cells[4])
    try:
        effective_max_energy = int(cells[5].strip())
    except ValueError:
        effective_max_energy = None
    try:
        dream_shard_price = int(cells[6].strip())
    except ValueError:
        dream_shard_price = None

    return {
        "name": name,
        "icon": icon,
        "base_energy": base_energy,
        "max_bonus_pct": max_bonus_pct,
        "max_bonus_recipes": max_bonus_recipes,
        "effective_max_energy": effective_max_energy,
        "dream_shard_price": dream_shard_price,
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

    # ソート: 生テキスト記載順（≒wikiでの表示順）を保持
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
