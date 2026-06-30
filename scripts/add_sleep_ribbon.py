"""data/sleep_ribbon.json に1段階追加 / 上書きする。

将来のVerアップで段階5以降が実装された場合の窓口。基本は build_sleep_ribbon.py の STAGES に追加するほうが綺麗。

使い方:
  python -c "from scripts.add_sleep_ribbon import add_sleep_ribbon; add_sleep_ribbon(stage=5, hours=5000, increment_inventory=2, increment_reduction_pct={'0':0,'1':5,'2':10}, overwrite=True)"
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "sleep_ribbon.json"


def _recompute_cumulative(records: list[dict]) -> None:
    cum_inv = 0
    cum_pct = {"0": 0, "1": 0, "2": 0}
    records.sort(key=lambda r: r["stage"])
    for r in records:
        inc = r.get("increment", {})
        cum_inv += int(inc.get("inventory", 0))
        for k in ("0", "1", "2"):
            cum_pct[k] += int((inc.get("time_reduction_pct") or {}).get(k, 0))
        r["cumulative"] = {
            "inventory": cum_inv,
            "time_reduction_pct": dict(cum_pct),
            "time_multiplier": {k: round(1.0 - cum_pct[k] / 100.0, 4) for k in ("0", "1", "2")},
        }


def add_sleep_ribbon(
    *,
    stage: int,
    hours: int,
    increment_inventory: int = 0,
    increment_reduction_pct: dict[str, int] | None = None,
    extras: list[str] | None = None,
    icon: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """1段階を sleep_ribbon.json に追加/上書きして、書き込んだレコードを返す。

    cumulative は全段階を再計算して整合性を保つ。
    """
    increment_reduction_pct = dict(increment_reduction_pct or {})
    for k in ("0", "1", "2"):
        increment_reduction_pct.setdefault(k, 0)

    record = {
        "stage": int(stage),
        "hours": int(hours),
        "icon": icon or f"おやすみリボン{stage}.png",
        "increment": {
            "inventory": int(increment_inventory),
            "time_reduction_pct": {k: int(v) for k, v in increment_reduction_pct.items()},
        },
        "cumulative": {},  # _recompute_cumulative で埋まる
        "extras": list(extras or []),
    }

    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    records: list[dict] = data["records"]

    existing_idx = next(
        (i for i, r in enumerate(records) if r["stage"] == stage), None
    )
    if existing_idx is not None and not overwrite:
        raise ValueError(
            f"stage={stage} は既に存在します。上書きしたい場合は overwrite=True"
        )
    if existing_idx is not None:
        records[existing_idx] = record
    else:
        records.append(record)

    _recompute_cumulative(records)
    data["_meta"]["count"] = len(records)

    DATA_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return record
