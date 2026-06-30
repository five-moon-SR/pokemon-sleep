"""data/berry.json に1件追加 / 上書きする。

追加運用は会話ベースで聞き取った内容をそのまま渡す想定。
生テキスト（貼り付けデータ集/きのみデータ.txt）は初期取り込み用アーカイブとして残し、
追加時は触らない。

使い方:
  python -c "from scripts.add_berry import add_berry; add_berry(...)"
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "berry.json"

VALID_TYPES = {
    "ノーマル", "ほのお", "みず", "でんき", "くさ", "こおり",
    "かくとう", "どく", "じめん", "ひこう", "エスパー", "むし",
    "いわ", "ゴースト", "ドラゴン", "あく", "はがね", "フェアリー",
}
TYPE_ORDER = [
    "ノーマル", "ほのお", "みず", "でんき", "くさ", "こおり",
    "かくとう", "どく", "じめん", "ひこう", "エスパー", "むし",
    "いわ", "ゴースト", "ドラゴン", "あく", "はがね", "フェアリー",
]
_TYPE_INDEX = {t: i for i, t in enumerate(TYPE_ORDER)}


def add_berry(
    *,
    name: str,
    type: str,
    base_energy: int,
    preferred_field: str,
    description: str = "",
    overwrite: bool = False,
) -> dict[str, Any]:
    """1件をきのみJSONに追加/上書きして、書き込んだレコードを返す。"""
    if type not in VALID_TYPES:
        raise ValueError(f"type は {sorted(VALID_TYPES)} のいずれか: {type!r}")

    record = {
        "name": name,
        "type": type,
        "base_energy": int(base_energy),
        "preferred_field": preferred_field,
        "description": description,
    }

    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    records: list[dict] = data["records"]

    existing_idx = next(
        (i for i, r in enumerate(records) if r["name"] == name), None
    )
    if existing_idx is not None and not overwrite:
        raise ValueError(
            f"{name!r} は既に存在します。上書きしたい場合は overwrite=True"
        )
    if existing_idx is not None:
        records[existing_idx] = record
    else:
        records.append(record)

    records.sort(key=lambda r: (_TYPE_INDEX.get(r["type"], 999), r["name"]))
    data["_meta"]["count"] = len(records)

    DATA_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return record
