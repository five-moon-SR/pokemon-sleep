"""data/evolution.json に1件追加 / 上書きする。

進化系列は会話ベースで個別追加することを想定。

使い方:
  python -c "from scripts.add_evolution import add_evolution; \
             add_evolution(src='X', dst='Y', candy=80, items=['つながりのヒモ'])"
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "evolution.json"
MASTER_PATH = ROOT / "data" / "pokemon_master.json"


def _load_master_names() -> set[str]:
    if not MASTER_PATH.exists():
        return set()
    raw = json.loads(MASTER_PATH.read_text(encoding="utf-8"))
    return {r["species_name"] for r in raw.get("records", [])}


def add_evolution(
    *,
    src: str,
    dst: str,
    candy: int,
    min_level: int | None = None,
    min_sleep_hours: int | None = None,
    items: list[str] | None = None,
    time_of_day: Literal["day", "night"] | None = None,
    gender: Literal["male", "female"] | None = None,
    overwrite: bool = False,
    skip_master_check: bool = False,
) -> dict[str, Any]:
    """1件を進化JSONに追加/上書きして、書き込んだレコードを返す。

    src=進化前 / dst=進化後 / candy=必要アメ数（必須）
    その他は条件として該当するキーだけ渡す。
    """
    if not src or not dst:
        raise ValueError("src と dst は必須です")
    if candy <= 0:
        raise ValueError("candy は正の整数")

    if not skip_master_check:
        master_names = _load_master_names()
        for label, name in [("src", src), ("dst", dst)]:
            if master_names and name not in master_names:
                raise ValueError(
                    f"{label}={name!r} が pokemon_master.json に存在しません。"
                    "表記を確認するか skip_master_check=True で強制追加できます。"
                )

    conditions: dict[str, Any] = {}
    if min_level is not None:
        conditions["min_level"] = int(min_level)
    if min_sleep_hours is not None:
        conditions["min_sleep_hours"] = int(min_sleep_hours)
    if items:
        conditions["items"] = list(items)
    if time_of_day is not None:
        if time_of_day not in ("day", "night"):
            raise ValueError("time_of_day は 'day' または 'night'")
        conditions["time_of_day"] = time_of_day
    if gender is not None:
        if gender not in ("male", "female"):
            raise ValueError("gender は 'male' または 'female'")
        conditions["gender"] = gender

    record = {
        "from": src,
        "to": dst,
        "candy": int(candy),
        "conditions": conditions,
    }

    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    records: list[dict] = data["records"]

    existing_idx = next(
        (i for i, r in enumerate(records) if r["from"] == src and r["to"] == dst),
        None,
    )
    if existing_idx is not None and not overwrite:
        raise ValueError(
            f"{src} → {dst} は既に存在します。上書きしたい場合は overwrite=True"
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
