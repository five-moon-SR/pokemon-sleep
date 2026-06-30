"""data/recipe.json に1件追加 / 上書きする。

追加運用は会話ベースで聞き取った内容をそのまま渡す想定。
生テキスト（貼り付けデータ集/料理データ.txt, 料理データ+α.txt）は触らない。

使い方:
  python -c "from scripts.add_recipe import add_recipe; add_recipe(...)"
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "recipe.json"

VALID_CATEGORIES = {"curry_stew", "salad", "drink_dessert"}
CATEGORY_ORDER = {"curry_stew": 0, "salad": 1, "drink_dessert": 2}


def _normalize_ingredients(
    raw: list[dict | tuple | list] | None,
) -> list[dict]:
    """[{name, count}] / [(name, count)] のどちらでも受ける。"""
    if not raw:
        return []
    out: list[dict] = []
    for item in raw:
        if isinstance(item, dict):
            name = str(item["name"]).strip()
            count = int(item["count"])
        elif isinstance(item, (tuple, list)) and len(item) == 2:
            name = str(item[0]).strip()
            count = int(item[1])
        else:
            raise ValueError(f"ingredients の要素が不正: {item!r}")
        out.append({"name": name, "count": count})
    return out


def add_recipe(
    *,
    name: str,
    category: str,  # "curry_stew" / "salad" / "drink_dessert"
    no: int,
    icon: str | None = None,
    ingredients: list[dict | tuple | list] | None = None,
    total_ingredients: int | None = None,
    energy_lv1: int | None = None,
    energy_lv30: int | None = None,
    energy_lv60: int | None = None,
    energy_max_pot69: int | None = None,
    energy_max_pot507: int | None = None,
    description: str = "",
    overwrite: bool = False,
) -> dict[str, Any]:
    """1件をレシピJSONに追加/上書きして、書き込んだレコードを返す。"""
    if category not in VALID_CATEGORIES:
        raise ValueError(f"category は {sorted(VALID_CATEGORIES)} のいずれか: {category!r}")

    ings = _normalize_ingredients(ingredients)
    if total_ingredients is None and ings:
        total_ingredients = sum(i["count"] for i in ings)

    record = {
        "no": int(no),
        "category": category,
        "name": name,
        "icon": icon,
        "ingredients": ings,
        "total_ingredients": int(total_ingredients) if total_ingredients is not None else None,
        "energy_lv1": int(energy_lv1) if energy_lv1 is not None else None,
        "energy_lv30": int(energy_lv30) if energy_lv30 is not None else None,
        "energy_lv60": int(energy_lv60) if energy_lv60 is not None else None,
        "energy_max_pot69": int(energy_max_pot69) if energy_max_pot69 is not None else None,
        "energy_max_pot507": int(energy_max_pot507) if energy_max_pot507 is not None else None,
        "description": description,
    }

    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    records: list[dict] = data["records"]

    existing_idx = next(
        (
            i
            for i, r in enumerate(records)
            if r["category"] == category and r["name"] == name
        ),
        None,
    )
    if existing_idx is not None and not overwrite:
        raise ValueError(
            f"{name!r}（{category}）は既に存在します。上書きしたい場合は overwrite=True"
        )
    if existing_idx is not None:
        records[existing_idx] = record
    else:
        records.append(record)

    records.sort(key=lambda r: (CATEGORY_ORDER[r["category"]], r["no"]))
    data["_meta"]["count"] = len(records)
    DATA_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return record
