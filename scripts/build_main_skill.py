"""貼り付けデータ集/メインスキルデータ.txt を data/main_skill.json に変換する。

実行: python scripts/build_main_skill.py

入力フォーマット:
  |~分類|~スキル名|~スキル説明|~最大レベル|
  |&attachref(アイコン/エナジーチャージ.png,...);|エナジーチャージS|''エナジーチャージS''|...|7|
  |~|~|''たくわえる''|...|~|
  |&attachref(アイコン/ゆめのかけらゲット.png,...);|>|''ゆめのかけらゲットS''|...|8|

特記:
- 1セル目（分類アイコン）が `~` のときは直前のアイコンを継承
- 2セル目（分類名）が `~` のときは直前の分類名を継承、`>` のときは横結合（分類==スキル名）
- 5セル目（最大レベル）が `~` のときは直前を継承
- スキル名は `''…''` または `'''…'''` のボールド表記を優先
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INPUT = ROOT / "貼り付けデータ集" / "メインスキルデータ.txt"
OUTPUT = ROOT / "data" / "main_skill.json"


def _strip_deco(text: str) -> str:
    s = text
    s = re.sub(r"&attachref\([^)]*\)\s*;", "", s)
    s = re.sub(r"&ref\([^)]*\)\s*;", "", s)
    s = re.sub(r"&aname\([^)]*\)\s*;", "", s)
    s = re.sub(r"&shy;", "", s)
    s = re.sub(r"&size\(\s*\d+\s*\)\s*\{([^}]*)\}\s*;", r"\1", s)
    s = re.sub(r"&color\([^)]*\)\s*\{([^}]*)\}\s*;", r"\1", s)
    s = re.sub(r"\(\(.*?\)\)", "", s)  # 注釈
    s = re.sub(r"&br;", "\n", s)
    s = re.sub(r"&#?\w+;", "", s)
    s = re.sub(r"\[\[([^\]>]+?)(?:>[^\]]+)?\]\]", r"\1", s)
    s = s.replace("'''", "").replace("''", "")
    return s.strip()


def _extract_skill_name(cell: str) -> str:
    """`''…''` または `'''…'''` の中身を取り出して整形。"""
    m = re.search(r"'''(.+?)'''", cell)
    if m:
        return _strip_deco(m.group(1))
    m = re.search(r"''(.+?)''", cell)
    if m:
        return _strip_deco(m.group(1))
    return _strip_deco(cell)


def _extract_icon(cell: str) -> str | None:
    m = re.search(r"&(?:ref|attachref)\(\s*([^,)\s]+)", cell)
    if not m:
        return None
    path = m.group(1).strip().lstrip("./")
    return path.rsplit("/", 1)[-1] if "/" in path else path


def _is_data_row(line: str) -> bool:
    if not line.startswith("|"):
        return False
    if line.endswith("|h") or line.endswith("|c"):
        return False
    if line.startswith(("|RIGHT", "|CENTER", "|LEFT")):
        return False
    cells = line.strip().rstrip("|").split("|")[1:]
    # 全セルが `~`/`>` 始まりまたは空ならヘッダ行
    if cells and all(
        c.strip() in (">", "") or c.strip().startswith("~") for c in cells
    ):
        return False
    return True


def _split_cells(line: str) -> list[str]:
    return line.strip().rstrip("|").split("|")[1:]


def _to_int(s: str) -> int | None:
    try:
        return int(s.strip())
    except (TypeError, ValueError):
        return None


def parse_line(line: str, state: dict) -> dict | None:
    if not _is_data_row(line):
        return None
    cells = _split_cells(line)
    if len(cells) < 5:
        return None

    icon_cell = cells[0].strip()
    if icon_cell != "~":
        new_icon = _extract_icon(icon_cell)
        if new_icon:
            state["category_icon"] = new_icon

    cat_cell = cells[1].strip()
    horizontal_merge = cat_cell == ">"
    if cat_cell == "~":
        category = state.get("category")
    elif horizontal_merge:
        category = None  # 後で name と同じにする
    else:
        category = _strip_deco(cat_cell)
        state["category"] = category

    name = _extract_skill_name(cells[2])
    if not name:
        return None
    if horizontal_merge:
        category = name
        state["category"] = name

    description = _strip_deco(cells[3])

    level_cell = cells[4].strip()
    if level_cell == "~":
        max_level = state.get("max_level")
    else:
        lv = _to_int(level_cell)
        if lv is not None:
            state["max_level"] = lv
            max_level = lv
        else:
            max_level = state.get("max_level")

    return {
        "category": category,
        "category_icon": state.get("category_icon"),
        "name": name,
        "description": description,
        "max_level": max_level,
    }


def build() -> dict:
    text = INPUT.read_text(encoding="utf-8")
    state: dict = {"category": None, "category_icon": None, "max_level": None}
    records: list[dict] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        rec = parse_line(raw.rstrip("\n"), state)
        if rec is None:
            continue
        if rec["name"] in seen:
            continue
        seen.add(rec["name"])
        records.append(rec)
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
