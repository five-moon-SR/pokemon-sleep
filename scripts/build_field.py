"""貼り付けデータ集/フィールドデータ.txt（PukiWiki形式）を data/field.json に変換する。

実行: python scripts/build_field.py

入力フォーマット例:
  ***通常フィールド [#xxxx]
  |1|&attachref(アイコン/ワカクサ本島.png,nolink,40x40);&br;ワカクサ本島|なし|ランダム|1,400以上|
  |2|&attachref(アイコン/シアンの砂浜.png,nolink,40x40);&br;シアンの砂浜|20種類|&attachref(アイコン/オレンのみ.png,nolink,20x20);オレンのみ(みず)&br;…|2,500以上|

  ***EXフィールド [#xxxx]
  |1|...|

通常/EX のどちらに属するかは直前の `***...` 見出しで判定。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INPUT = ROOT / "貼り付けデータ集" / "フィールドデータ.txt"
OUTPUT = ROOT / "data" / "field.json"

HEADER_PREFIXES = ("|~", "|SIZE", "|CENTER", "|RIGHT", "|LEFT", "|>")


def _is_data_row(line: str) -> bool:
    if not line.startswith("|"):
        return False
    for p in HEADER_PREFIXES:
        if line.startswith(p):
            return False
    if line.endswith("|h") or line.endswith("|c"):
        return False
    return True


def _parse_name_cell(cell: str) -> tuple[str | None, str]:
    """`&attachref(アイコン/ワカクサ本島.png,...);&br;ワカクサ本島` → (icon, name)"""
    icon_match = re.search(r"&attachref\(([^,)]+)", cell)
    icon: str | None = None
    if icon_match:
        path = icon_match.group(1).strip()
        icon = path.rsplit("/", 1)[-1] if "/" in path else path

    # &attachref(...); と &br; を取り除いた残りを名前として扱う
    name = re.sub(r"&attachref\([^)]*\);?", "", cell)
    name = name.replace("&br;", "").strip()
    return icon, name


def _parse_berries_cell(cell: str) -> list[dict]:
    """`&attachref(...);オレンのみ(みず)&br;&attachref(...);モモンのみ(フェアリー)&br;…`
    → [{"name": "オレンのみ", "type": "みず"}, ...]
    `ランダム` の場合は空リストを返す（呼び出し側でランダム判定）。
    """
    cleaned = re.sub(r"&attachref\([^)]*\);?", "", cell)
    parts = [p.strip() for p in cleaned.split("&br;") if p.strip()]
    out: list[dict] = []
    for part in parts:
        m = re.match(r"(.+?)\(([^)]+)\)\s*$", part)
        if m:
            out.append({"name": m.group(1).strip(), "type": m.group(2).strip()})
    return out


def _parse_sp_cell(cell: str) -> int | None:
    digits = re.sub(r"[,\s]", "", cell)
    m = re.match(r"(\d+)", digits)
    return int(m.group(1)) if m else None


def parse_line(line: str, field_type: str) -> dict | None:
    if not _is_data_row(line):
        return None
    cells = line.strip().rstrip("|").split("|")[1:]
    if len(cells) < 5:
        return None

    try:
        no = int(cells[0].strip())
    except ValueError:
        return None

    icon, name = _parse_name_cell(cells[1])
    if not name:
        return None

    unlock_condition = cells[2].replace("&br;", "").strip()

    berries_cell = cells[3].strip()
    is_random = "ランダム" in berries_cell and "アイコン" not in berries_cell
    favorite_berries = [] if is_random else _parse_berries_cell(berries_cell)

    recommended_sp = _parse_sp_cell(cells[4])

    return {
        "no": no,
        "type": field_type,
        "name": name,
        "icon": icon,
        "unlock_condition": unlock_condition,
        "favorite_berries_random": is_random,
        "favorite_berries": favorite_berries,
        "recommended_sp_min": recommended_sp,
    }


def build() -> dict:
    text = INPUT.read_text(encoding="utf-8")
    records: list[dict] = []
    seen: set[tuple[str, str]] = set()
    current_type: str | None = None

    for raw in text.splitlines():
        stripped = raw.strip()
        # 見出しでセクション判定
        if stripped.startswith("***"):
            if "EX" in stripped:
                current_type = "ex"
            elif "通常" in stripped:
                current_type = "normal"
            else:
                current_type = None
            continue

        if current_type is None:
            continue

        rec = parse_line(raw, current_type)
        if rec is None:
            continue
        key = (rec["type"], rec["name"])
        if key in seen:
            continue
        seen.add(key)
        records.append(rec)

    # ソート: 通常→EXの順、その中で no 昇順
    records.sort(key=lambda r: (0 if r["type"] == "normal" else 1, r["no"]))
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
