"""貼り付けデータ集/サブスキルデータ.txt を data/subskill.json に変換する。

実行: python scripts/build_subskill.py

入力フォーマット:
  |~枠の色|~スキル名|~効果量|~スキルの説明|h    （ヘッダ）
  |BGCOLOR(#fee570):&color(#722d00){''金色''};|&aname(sleep_exp_bonus);　睡眠EXPボーナス|14%|...|
  |~|&aname(...);★スキルレベルアップS|+1|...|

特記:
- 1列目「枠の色」が `~` の場合は直前の rarity を継承
- スキル名先頭の `★` はサブスキルのたねでランクアップ可の印
- 効果量が `''…''` で囲まれているのはカテゴリ最高ランク
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INPUT = ROOT / "貼り付けデータ集" / "サブスキルデータ.txt"
OUTPUT = ROOT / "data" / "subskill.json"

RARITY_MAP = {"金色": "gold", "青色": "blue", "白色": "white"}
RARITY_ORDER = {"gold": 0, "blue": 1, "white": 2}


_DECORATIONS = [
    re.compile(r"&attachref\([^)]*\)\s*;"),
    re.compile(r"&ref\([^)]*\)\s*;"),
    re.compile(r"&aname\([^)]*\)\s*;"),
    re.compile(r"&shy;"),
    re.compile(r"&size\(\s*\d+\s*\)\s*\{([^}]*)\}\s*;"),
    re.compile(r"&color\([^)]*\)\s*\{([^}]*)\}\s*;"),
    re.compile(r"BGCOLOR\([^)]*\)\s*:"),
    re.compile(r"\(\(.*?\)\)"),  # 注釈
    re.compile(r"&br;"),
    re.compile(r"&#?\w+;"),
]


def _strip_deco(text: str) -> str:
    s = text
    s = _DECORATIONS[0].sub("", s)
    s = _DECORATIONS[1].sub("", s)
    s = _DECORATIONS[2].sub("", s)
    s = _DECORATIONS[3].sub("", s)
    s = _DECORATIONS[4].sub(r"\1", s)
    s = _DECORATIONS[5].sub(r"\1", s)
    s = _DECORATIONS[6].sub("", s)
    s = _DECORATIONS[7].sub("", s)
    s = _DECORATIONS[8].sub("\n", s)
    s = _DECORATIONS[9].sub("", s)
    # `[[表示>リンク]]` → 表示 / `[[表示]]` → 表示
    s = re.sub(r"\[\[([^\]>]+?)(?:>[^\]]+)?\]\]", r"\1", s)
    # 強調マーク '' は本文中では削る
    s = s.replace("''", "").replace("'''", "")
    s = re.sub(r"[　\s]+", " ", s).strip()
    return s


def _is_data_row(line: str) -> bool:
    if not line.startswith("|"):
        return False
    if line.endswith("|h") or line.endswith("|c"):
        return False
    if line.startswith(("|RIGHT", "|CENTER", "|LEFT")):
        return False
    # 全セルが `~` で始まる行はヘッダ行（`|h` 付け忘れ対策）
    cells = line.strip().rstrip("|").split("|")[1:]
    if cells and all(c.strip().startswith("~") for c in cells):
        return False
    return True


def _split_cells(line: str) -> list[str]:
    return line.strip().rstrip("|").split("|")[1:]


def _detect_rarity(cell: str) -> str | None:
    for ja, en in RARITY_MAP.items():
        if ja in cell:
            return en
    return None


def parse_line(line: str, state: dict) -> dict | None:
    if not _is_data_row(line):
        return None
    cells = _split_cells(line)
    if len(cells) < 4:
        return None

    rarity_cell = cells[0].strip()
    if rarity_cell != "~":
        rarity = _detect_rarity(rarity_cell)
        if rarity:
            state["rarity"] = rarity

    name_raw = cells[1]
    can_upgrade = "★" in name_raw
    name = _strip_deco(name_raw).lstrip("★").strip()
    if not name:
        return None

    effect_raw = cells[2].strip()
    is_max_rank = bool(re.search(r"''[^']+''", effect_raw))
    effect_value = _strip_deco(effect_raw)

    description = _strip_deco(cells[3])

    return {
        "rarity": state.get("rarity"),
        "name": name,
        "effect_value": effect_value,
        "description": description,
        "is_max_rank": is_max_rank,
        "can_upgrade_with_seed": can_upgrade,
    }


def build() -> dict:
    text = INPUT.read_text(encoding="utf-8")
    state: dict = {"rarity": None}
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

    # ソート: rarity（gold→blue→white）→ 表記載順
    records.sort(key=lambda r: RARITY_ORDER.get(r.get("rarity") or "white", 99))
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
