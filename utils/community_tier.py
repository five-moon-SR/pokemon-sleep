"""コミュニティ評価ティア(data/community_tier.json)のアクセサと捕獲方針ロジック。

出典: RaenonX ポケモンティア表(食材軸)。取得運用は _meta.note 参照。
「強いポケモンほど理想構成(AAA等)で優先確保する」という捕獲方針に使う。
概念の背景: docs/eval_context/community_concepts.md
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

TIER_PATH = Path(__file__).resolve().parent.parent / "data" / "community_tier.json"

# 捕獲優先度スコアに掛けるティア係数。未掲載(=D以下 or 未収集)は1.0の等倍。
TIER_WEIGHT: dict[str, float] = {"S": 2.0, "A": 1.6, "B": 1.3, "C": 1.1}


@lru_cache(maxsize=1)
def _tier_map() -> dict[str, str]:
    if not TIER_PATH.exists():
        return {}
    data = json.loads(TIER_PATH.read_text(encoding="utf-8"))
    return {r["species_name"]: r["tier"] for r in data.get("records", [])}


def get_tier(species_name: str | None) -> str | None:
    """種族のコミュニティティア(S/A/B/C)。未掲載は None。"""
    if not species_name:
        return None
    return _tier_map().get(species_name)


def tier_weight(species_name: str | None) -> float:
    return TIER_WEIGHT.get(get_tier(species_name) or "", 1.0)


def recommended_composition(species: dict[str, Any]) -> str:
    """得意分野ごとの厳選定石に基づく狙い構成(community_concepts.md)。"""
    specialty = species.get("specialty")
    if specialty == "食材":
        return "AAA"
    if specialty == "きのみ":
        return "構成不問"
    if specialty == "スキル":
        return "低食材推奨"
    return "AAA寄り"


def top_tier_species(min_tier: str = "B") -> list[tuple[str, str]]:
    """min_tier 以上の (species_name, tier) をティア順で返す。"""
    order = ["S", "A", "B", "C"]
    limit = order.index(min_tier) if min_tier in order else len(order) - 1
    allowed = set(order[: limit + 1])
    items = [(n, t) for n, t in _tier_map().items() if t in allowed]
    items.sort(key=lambda x: order.index(x[1]))
    return items
