"""data/main_skill.json に1件追加 / 上書きする。

追加運用は会話ベースで聞き取った内容をそのまま渡す想定。
生テキスト（貼り付けデータ集/メインスキルデータ.txt）は触らない。

使い方:
  python -c "from scripts.add_main_skill import add_main_skill; add_main_skill(...)"
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "main_skill.json"


def add_main_skill(
    *,
    name: str,
    category: str,
    description: str = "",
    max_level: int | None = None,
    category_icon: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """1件をメインスキルJSONに追加/上書きして、書き込んだレコードを返す。"""
    record = {
        "category": category,
        "category_icon": category_icon,
        "name": name,
        "description": description,
        "max_level": int(max_level) if max_level is not None else None,
    }

    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    records: list[dict] = data["records"]

    existing_idx = next(
        (i for i, r in enumerate(records) if r["name"] == name), None
    )
    if existing_idx is not None and not overwrite:
        raise ValueError(f"{name!r} は既に存在します。上書きしたい場合は overwrite=True")
    if existing_idx is not None:
        records[existing_idx] = record
    else:
        records.append(record)

    data["_meta"]["count"] = len(records)
    DATA_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return record
