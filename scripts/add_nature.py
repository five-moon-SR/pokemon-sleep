"""data/nature.json に1件追加 / 上書きする。

性格は本来25種固定なので追加運用はほぼ無いが、共通ルールに揃えてヘルパだけ用意しておく。
新しい性格カテゴリやどうぐ補正が追加された場合の窓口。

使い方:
  python -c "from scripts.add_nature import add_nature; add_nature(name='まじめ', up='exp', down='exp', is_neutral=True, overwrite=True)"
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "nature.json"

VALID_AXES = {"speed", "energy", "ingredient", "skill", "exp"}


def add_nature(
    *,
    name: str,
    up: str,
    down: str,
    is_neutral: bool | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """1件を性格JSONに追加/上書きして、書き込んだレコードを返す。"""
    if up not in VALID_AXES:
        raise ValueError(f"up は {sorted(VALID_AXES)} のいずれか: {up!r}")
    if down not in VALID_AXES:
        raise ValueError(f"down は {sorted(VALID_AXES)} のいずれか: {down!r}")

    if is_neutral is None:
        is_neutral = up == down

    record = {
        "name": name,
        "up": up,
        "down": down,
        "is_neutral": bool(is_neutral),
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
    data["_meta"]["neutrals"] = [r["name"] for r in records if r.get("is_neutral")]

    DATA_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return record
