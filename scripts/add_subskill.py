"""data/subskill.json に1件追加 / 上書きする。

追加運用は会話ベースで聞き取った内容をそのまま渡す想定。
生テキスト（貼り付けデータ集/サブスキルデータ.txt）は触らない。

使い方:
  python -c "from scripts.add_subskill import add_subskill; add_subskill(...)"
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "subskill.json"

VALID_RARITIES = {"gold", "blue", "white"}
RARITY_ORDER = {"gold": 0, "blue": 1, "white": 2}

VALID_CATEGORIES = {
    "speed", "skill_trigger", "ingredient_rate", "berry_count",
    "inventory", "skill_level", "sleep_exp", "research_exp",
    "energy_recovery", "dream_shard", "help_bonus", "other",
}
VALID_KINDS = {"percent", "count", "multiplier", "other"}
VALID_SCOPES = {"self", "team"}


def _infer_kind_and_num(effect_value: str) -> tuple[str, float | int | None]:
    """effect_value 文字列から effect_kind と effect_value_num を推論する。

    例:
      "14%"  -> ("percent", 14.0)
      "+1"   -> ("count", 1)
      "×1.14"-> ("multiplier", 1.14)
    """
    s = effect_value.strip()
    m = re.match(r"^([+-]?)(\d+(?:\.\d+)?)\s*%$", s)
    if m:
        return "percent", float(m.group(2)) * (-1.0 if m.group(1) == "-" else 1.0)
    m = re.match(r"^([+-])(\d+)$", s)
    if m:
        n = int(m.group(2))
        return "count", -n if m.group(1) == "-" else n
    m = re.match(r"^[×x*]?\s*(\d+(?:\.\d+)?)$", s)
    if m:
        return "multiplier", float(m.group(1))
    return "other", None


def add_subskill(
    *,
    name: str,
    rarity: str,
    effect_value: str,
    description: str = "",
    is_max_rank: bool = False,
    can_upgrade_with_seed: bool = False,
    category: str = "other",
    effect_kind: str | None = None,
    effect_value_num: float | int | None = None,
    scope: str = "self",
    overwrite: bool = False,
) -> dict[str, Any]:
    """1件をサブスキルJSONに追加/上書きして、書き込んだレコードを返す。"""
    if rarity not in VALID_RARITIES:
        raise ValueError(f"rarity は {sorted(VALID_RARITIES)} のいずれか: {rarity!r}")
    if category not in VALID_CATEGORIES:
        raise ValueError(f"category は {sorted(VALID_CATEGORIES)} のいずれか: {category!r}")
    if scope not in VALID_SCOPES:
        raise ValueError(f"scope は {sorted(VALID_SCOPES)} のいずれか: {scope!r}")

    if effect_kind is None or effect_value_num is None:
        inferred_kind, inferred_num = _infer_kind_and_num(str(effect_value))
        effect_kind = effect_kind or inferred_kind
        if effect_value_num is None:
            effect_value_num = inferred_num
    if effect_kind not in VALID_KINDS:
        raise ValueError(f"effect_kind は {sorted(VALID_KINDS)} のいずれか: {effect_kind!r}")

    record = {
        "rarity": rarity,
        "name": name,
        "category": category,
        "effect_kind": effect_kind,
        "effect_value": str(effect_value),
        "effect_value_num": effect_value_num,
        "scope": scope,
        "description": description,
        "is_max_rank": bool(is_max_rank),
        "can_upgrade_with_seed": bool(can_upgrade_with_seed),
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

    records.sort(key=lambda r: RARITY_ORDER.get(r.get("rarity") or "white", 99))
    data["_meta"]["count"] = len(records)
    DATA_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return record
