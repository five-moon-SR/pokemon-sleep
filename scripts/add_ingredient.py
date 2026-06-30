"""data/ingredient.json に1件追加 / 上書きする。

追加運用は会話ベースで聞き取った内容をそのまま渡す想定。
生テキスト（貼り付けデータ集/食材データ.txt）は触らない。

使い方:
  python -c "from scripts.add_ingredient import add_ingredient; add_ingredient(...)"
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "ingredient.json"


def add_ingredient(
    *,
    name: str,
    base_energy: int,
    icon: str | None = None,
    max_bonus_pct: int | None = None,
    max_bonus_recipes: list[str] | None = None,
    effective_max_energy: int | None = None,
    dream_shard_price: int | None = None,
    description: str = "",
    overwrite: bool = False,
) -> dict[str, Any]:
    """1件を食材JSONに追加/上書きして、書き込んだレコードを返す。"""
    record = {
        "name": name,
        "icon": icon,
        "base_energy": int(base_energy),
        "max_bonus_pct": int(max_bonus_pct) if max_bonus_pct is not None else None,
        "max_bonus_recipes": list(max_bonus_recipes or []),
        "effective_max_energy": int(effective_max_energy) if effective_max_energy is not None else None,
        "dream_shard_price": int(dream_shard_price) if dream_shard_price is not None else None,
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

    data["_meta"]["count"] = len(records)
    DATA_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return record
