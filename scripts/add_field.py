"""data/field.json に1件追加 / 上書きする。

追加運用は会話ベースで聞き取った内容をそのまま渡す想定。
生テキスト（貼り付けデータ集/フィールドデータ.txt）は触らない。

使い方:
  python -c "from scripts.add_field import add_field; add_field(...)"
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "field.json"

VALID_TYPES = {"normal", "ex"}


def add_field(
    *,
    no: int,
    type: str,  # "normal" or "ex"
    name: str,
    unlock_condition: str,
    recommended_sp_min: int,
    favorite_berries_random: bool = False,
    favorite_berries: list[dict] | None = None,  # [{"name": "オレンのみ", "type": "みず"}, ...]
    icon: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """1件をフィールドJSONに追加/上書きして、書き込んだレコードを返す。"""
    if type not in VALID_TYPES:
        raise ValueError(f"type は {sorted(VALID_TYPES)} のいずれか: {type!r}")

    record = {
        "no": int(no),
        "type": type,
        "name": name,
        "icon": icon,
        "unlock_condition": unlock_condition,
        "favorite_berries_random": bool(favorite_berries_random),
        "favorite_berries": list(favorite_berries or []),
        "recommended_sp_min": int(recommended_sp_min),
    }

    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    records: list[dict] = data["records"]

    existing_idx = next(
        (i for i, r in enumerate(records) if r["type"] == type and r["name"] == name),
        None,
    )
    if existing_idx is not None and not overwrite:
        raise ValueError(
            f"{name!r}（{type}）は既に存在します。上書きしたい場合は overwrite=True"
        )
    if existing_idx is not None:
        records[existing_idx] = record
    else:
        records.append(record)

    records.sort(key=lambda r: (0 if r["type"] == "normal" else 1, r["no"]))
    data["_meta"]["count"] = len(records)
    DATA_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return record
