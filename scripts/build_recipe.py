"""貼り付けデータ集/料理データ.txt + 料理データ+α.txt を data/recipe.json に変換する。

実行: python scripts/build_recipe.py

入力:
- 料理データ.txt: カテゴリ別レシピ一覧（食材+合計+Lv1エナジー）。レシピの全量はこちら基準。
- 料理データ+α.txt: 同レシピのレシピレベル別エナジー（Lv1/Lv30/Lv60/なべ69/なべ507）。一部新レシピは未掲載。

カテゴリ: curry_stew / salad / drink_dessert
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INPUT_BASE = ROOT / "貼り付けデータ集" / "料理データ.txt"
INPUT_PLUS = ROOT / "貼り付けデータ集" / "料理データ+α.txt"
OUTPUT = ROOT / "data" / "recipe.json"

CATEGORY_HEADERS: dict[str, str] = {
    "curry_stew": "**カレー・シチュー",
    "salad": "**サラダ",
    "drink_dessert": "**デザート・ドリンク",
}
CATEGORY_ORDER = {k: i for i, k in enumerate(CATEGORY_HEADERS)}

# 食材セル中の `&icon(20,名前);×個数` を抽出（×は全角 U+00D7）
_ING_PATTERN = re.compile(r"&icon\(\s*\d+\s*,\s*([^);]+?)\s*\)\s*;\s*×\s*(\d+)")
# 画像参照 `&ref(path,...)` `&attachref(path,...)` のファイル名抽出
_ICON_PATTERN = re.compile(r"&(?:ref|attachref)\(\s*([^,)\s]+)")
# 料理名セル中の `&tooltip(...){説明};` 部分
_TOOLTIP_PATTERN = re.compile(r"&tooltip\([^)]*\)\s*\{([^}]*)\}\s*;?")
# 装飾 `&size(11){名前};` を中身に展開
_SIZE_PATTERN = re.compile(r"&size\(\s*\d+\s*\)\s*\{([^}]*)\}\s*;?")


def _is_data_row(line: str) -> bool:
    if not line.startswith("|"):
        return False
    if line.endswith("|h") or line.endswith("|c"):
        return False
    if line.startswith(("|~", "|RIGHT", "|CENTER", "|LEFT", "|>")):
        return False
    return True


def _split_cells(line: str) -> list[str]:
    return line.strip().rstrip("|").split("|")[1:]


def _extract_icon(cell: str) -> str | None:
    m = _ICON_PATTERN.search(cell)
    if not m:
        return None
    path = m.group(1).strip().lstrip("./")
    return path.rsplit("/", 1)[-1] if "/" in path else path


def _extract_name_and_desc(cell: str) -> tuple[str, str]:
    """`料理名&tooltip(&tip;){説明};` から (name, description) を抽出。"""
    description = ""
    m = _TOOLTIP_PATTERN.search(cell)
    if m:
        description = m.group(1).replace("&br;", "").strip()
        name = (cell[: m.start()] + cell[m.end():]).strip()
    else:
        name = cell.strip()
    name = _SIZE_PATTERN.sub(r"\1", name)
    return name.strip(), description


def _extract_ingredients(cell: str) -> list[dict]:
    return [
        {"name": name.strip(), "count": int(cnt)}
        for name, cnt in _ING_PATTERN.findall(cell)
    ]


def _to_int_or_none(s: str) -> int | None:
    s = s.strip()
    if s in ("", "-"):
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _detect_category(line: str) -> str | None:
    for cat, header in CATEGORY_HEADERS.items():
        if line.startswith(header):
            return cat
    return None


def parse_base_file() -> dict[tuple[str, str], dict]:
    """料理データ.txt をパースして {(category, name): record} を返す。"""
    text = INPUT_BASE.read_text(encoding="utf-8")
    records: dict[tuple[str, str], dict] = {}
    current_category: str | None = None

    for raw in text.splitlines():
        line = raw.rstrip("\n").strip()
        new_cat = _detect_category(line)
        if new_cat is not None:
            current_category = new_cat
            continue
        if current_category is None or not _is_data_row(line):
            continue
        cells = _split_cells(line)
        if len(cells) < 6:
            continue

        no_cell = cells[0].strip()
        icon = _extract_icon(cells[1])
        name, description = _extract_name_and_desc(cells[2])
        if not name:
            continue
        ingredients_cell = cells[3]
        is_mixed = "他のレシピに該当しない" in ingredients_cell
        if is_mixed:
            ingredients: list[dict] = []
            total = None
        else:
            ingredients = _extract_ingredients(ingredients_cell)
            total = _to_int_or_none(cells[4])
        energy_lv1 = _to_int_or_none(cells[5])
        no = 0 if no_cell == "-" else (_to_int_or_none(no_cell) or 0)

        records[(current_category, name)] = {
            "no": no,
            "category": current_category,
            "name": name,
            "icon": icon,
            "ingredients": ingredients,
            "total_ingredients": total,
            "energy_lv1": energy_lv1,
            "energy_lv30": None,
            "energy_lv60": None,
            "energy_max_pot69": None,
            "energy_max_pot507": None,
            "description": description,
        }
    return records


def merge_plus_file(records: dict[tuple[str, str], dict]) -> int:
    """料理データ+α.txt をパースして Lv30/Lv60/69/507 を埋める。マージ件数を返す。"""
    text = INPUT_PLUS.read_text(encoding="utf-8")
    current_category: str | None = None
    merged = 0

    for raw in text.splitlines():
        line = raw.rstrip("\n").strip()
        new_cat = _detect_category(line)
        if new_cat is not None:
            current_category = new_cat
            continue
        if current_category is None or not _is_data_row(line):
            continue
        cells = _split_cells(line)
        if len(cells) < 10:
            continue

        name, _ = _extract_name_and_desc(cells[2])
        if not name:
            continue
        key = (current_category, name)
        if key not in records:
            continue
        rec = records[key]
        if rec.get("energy_lv1") is None:
            rec["energy_lv1"] = _to_int_or_none(cells[5])
        rec["energy_lv30"] = _to_int_or_none(cells[6])
        rec["energy_lv60"] = _to_int_or_none(cells[7])
        rec["energy_max_pot69"] = _to_int_or_none(cells[8])
        rec["energy_max_pot507"] = _to_int_or_none(cells[9])
        merged += 1
    return merged


def build() -> dict:
    records_map = parse_base_file()
    merged = merge_plus_file(records_map)
    records = sorted(
        records_map.values(),
        key=lambda r: (CATEGORY_ORDER[r["category"]], r["no"]),
    )
    return {
        "records": records,
        "_meta": {"count": len(records), "merged_with_plus": merged},
    }


def main() -> int:
    for p in (INPUT_BASE, INPUT_PLUS):
        if not p.exists():
            print(f"入力ファイルが見つかりません: {p}", file=sys.stderr)
            return 1
    result = build()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"OK: {result['_meta']['count']} 件を {OUTPUT.relative_to(ROOT)} に書き出しました "
        f"(+α.txt とマージ: {result['_meta']['merged_with_plus']} 件)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
