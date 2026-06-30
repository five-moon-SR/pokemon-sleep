"""data/pokemon_master.json に1種を追加 / 上書きする。

追加運用は私（Claude）が会話ベースで聞き取った内容をそのまま渡す想定。
生テキスト（ポケモンマスターデータ.txt / ポケモン確率データ.txt）は
初期取り込み用アーカイブとして残し、追加時は触らない。

使い方:
  python -c "from scripts.add_pokemon import add_pokemon; add_pokemon(...)"
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
MASTER_PATH = ROOT / "data" / "pokemon_master.json"

VALID_SLEEPS = {"うとうと", "すやすや", "ぐっすり"}
VALID_SPECIALTIES = {"食材", "きのみ", "スキル", "オール"}


def _validate(
    sleep_type: str,
    specialty: str,
    ingredient_a: dict,
    ingredient_b: dict | None,
    ingredient_c: dict | None,
) -> None:
    if sleep_type not in VALID_SLEEPS:
        raise ValueError(f"sleep_type は {sorted(VALID_SLEEPS)} のいずれか: {sleep_type!r}")
    if specialty not in VALID_SPECIALTIES:
        raise ValueError(f"specialty は {sorted(VALID_SPECIALTIES)} のいずれか: {specialty!r}")

    a_qty = ingredient_a.get("qty", [])
    if not 1 <= len(a_qty) <= 3:
        raise ValueError(f"ingredient_a.qty は 1〜3 個（食A: スロット1/2/3 の個数）: {a_qty}")
    if ingredient_b:
        b_qty = ingredient_b.get("qty", [])
        if not 1 <= len(b_qty) <= 2:
            raise ValueError(f"ingredient_b.qty は 1〜2 個（食B: スロット2/3 の個数）: {b_qty}")
    if ingredient_c:
        c_qty = ingredient_c.get("qty", [])
        if len(c_qty) != 1:
            raise ValueError(f"ingredient_c.qty は 1 個（食C: スロット3 の個数）: {c_qty}")
        if not ingredient_b:
            raise ValueError("ingredient_c があるのに ingredient_b が無いのは仕様上ありえない")


def add_pokemon(
    *,
    dex_no: str,
    species_name: str,
    sleep_type: str,
    specialty: str,
    berry_name: str,
    berry_qty: int,
    ingredient_a: dict,  # {"name": str, "qty": list[int]}
    main_skill: str,
    base_assist_seconds: int,
    ingredient_b: dict | None = None,
    ingredient_c: dict | None = None,
    food_drop_rate: float | None = None,
    main_skill_rate: float | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """1種をマスターJSONに追加/上書きして、書き込んだレコードを返す。

    既存と同じ species_name があれば overwrite=True でのみ上書き。
    確率データが未掲載の場合は food_drop_rate / main_skill_rate を None にする。
    """
    _validate(sleep_type, specialty, ingredient_a, ingredient_b, ingredient_c)

    record = {
        "dex_no": dex_no,
        "species_name": species_name,
        "sleep_type": sleep_type,
        "specialty": specialty,
        "berry": {"name": berry_name, "qty": berry_qty},
        "ingredients": {
            "a": ingredient_a,
            "b": ingredient_b,
            "c": ingredient_c,
        },
        "main_skill": main_skill,
        "base_assist_seconds": base_assist_seconds,
        "food_drop_rate": food_drop_rate,
        "main_skill_rate": main_skill_rate,
    }

    data = json.loads(MASTER_PATH.read_text(encoding="utf-8"))
    records: list[dict] = data["records"]

    existing_idx = next(
        (i for i, r in enumerate(records) if r["species_name"] == species_name),
        None,
    )
    if existing_idx is not None and not overwrite:
        raise ValueError(
            f"{species_name!r} は既に存在します。上書きしたい場合は overwrite=True"
        )
    if existing_idx is not None:
        records[existing_idx] = record
    else:
        records.append(record)

    records.sort(key=lambda r: (r["dex_no"], r["species_name"]))
    data["_meta"]["count"] = len(records)

    MASTER_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return record
