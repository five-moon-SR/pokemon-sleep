"""貼り付けデータ集/性格データ.txt（PukiWiki形式）を data/nature.json に変換する。

実行: python scripts/build_nature.py

入力フォーマットの該当部（5×5マトリクス）:
  |BGCOLOR(...):''おてつだい&br;スピード''|BGCOLOR(...):がんばりや※|さみしがり|いじっぱり|やんちゃ|ゆうかん|
  |BGCOLOR(...):''げんき&br;回復量''|ずぶとい|BGCOLOR(...):すなお※|わんぱく|のうてんき|のんき|
  ...

行=上昇補正、列=下降補正。「※」付きの対角要素は無補正（is_neutral=true）。
倍率はWiki記載の固定値を埋め込む（▲1.11/▼0.93 等）。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INPUT = ROOT / "貼り付けデータ集" / "性格データ.txt"
OUTPUT = ROOT / "data" / "nature.json"

# マトリクスの行・列の順序（生テキストの並びに合わせる）
AXES = ["speed", "energy", "ingredient", "skill", "exp"]
LABEL_TO_AXIS = {
    "おてつだいスピード": "speed",
    "げんき回復量": "energy",
    "食材おてつだい確率": "ingredient",
    "メインスキル発生確率": "skill",
    "EXP獲得量": "exp",
}

MODIFIERS = {
    "speed": {
        "label": "おてつだいスピード",
        "up": 1.11,
        "down": 0.93,
        "note": "おてつだい時間が▲で×0.9, ▼で×1.075になり、その逆数として効果はこの倍率",
    },
    "energy": {
        "label": "げんき回復量",
        "up": 1.20,
        "down": 0.88,
        "note": "Ver1.1.0で▼が0.8→0.88に緩和",
    },
    "ingredient": {
        "label": "食材おてつだい確率",
        "up": 1.20,
        "down": 0.80,
        "note": "要検証",
    },
    "skill": {
        "label": "メインスキル発生確率",
        "up": 1.20,
        "down": 0.80,
        "note": "要検証",
    },
    "exp": {
        "label": "EXP獲得量",
        "up": 1.18,
        "down": 0.82,
        "note": "アメ・睡眠リサーチによるEXP獲得量・Lv上限ボーナスに適用",
    },
}


_CLEAN_RE = re.compile(r"BGCOLOR\([^)]+\):|''|&br;|^[★※]")


def _clean_cell(cell: str) -> tuple[str, bool]:
    """セル文字列から装飾を取り除き、性格名と無補正フラグを返す。"""
    raw = cell.strip()
    is_neutral = "※" in raw
    cleaned = _CLEAN_RE.sub("", raw)
    cleaned = cleaned.replace("※", "").strip()
    return cleaned, is_neutral


def parse_matrix(text: str) -> list[dict]:
    """性格データ.txt から 5×5 のマトリクス行を抽出して 25 件のレコードを返す。"""
    records: list[dict] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("|BGCOLOR"):
            continue
        cells = line.rstrip("|").split("|")[1:]
        if len(cells) < 6:
            continue
        # 1セル目は "BGCOLOR(...):''おてつだいスピード''" のような行ラベル
        label_cell = cells[0]
        label_match = re.search(r"''([^']+)''", label_cell)
        if not label_match:
            continue
        row_label = label_match.group(1).replace("&br;", "")
        up_axis = LABEL_TO_AXIS.get(row_label)
        if up_axis is None:
            continue
        # 2〜6セル目は性格名
        for i, cell in enumerate(cells[1:6]):
            name, is_neutral = _clean_cell(cell)
            if not name:
                continue
            records.append(
                {
                    "name": name,
                    "up": up_axis,
                    "down": AXES[i],
                    "is_neutral": is_neutral,
                }
            )
    return records


def build() -> dict:
    text = INPUT.read_text(encoding="utf-8")
    records = parse_matrix(text)
    if len(records) != 25:
        raise RuntimeError(f"expected 25 natures, got {len(records)}")
    neutrals = [r["name"] for r in records if r["is_neutral"]]
    return {
        "records": records,
        "_meta": {
            "count": len(records),
            "modifiers": MODIFIERS,
            "neutrals": neutrals,
            "source": "貼り付けデータ集/性格データ.txt",
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
