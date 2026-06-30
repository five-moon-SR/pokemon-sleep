"""data/evolution_item.json に1件追加 / 上書きする。

使い方:
  python -c "from scripts.add_evolution_item import add_evolution_item; add_evolution_item(name='○○のいし', icon='○○のいし.png', category='stone', description='...')"
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "evolution_item.json"

VALID_CATEGORIES = {"connection", "stone", "seal", "coat", "claw", "round", "other"}


def add_evolution_item(
    *,
    name: str,
    icon: str | None = None,
    category: str = "other",
    description: str = "",
    overwrite: bool = False,
) -> dict[str, Any]:
    if category not in VALID_CATEGORIES:
        raise ValueError(f"category は {sorted(VALID_CATEGORIES)} のいずれか: {category!r}")
    record = {
        "name": name,
        "icon": icon or f"{name}.png",
        "category": category,
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
