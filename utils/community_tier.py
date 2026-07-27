"""コミュニティ評価ティア(data/community_tier.json)のアクセサと捕獲方針ロジック。

出典: 攻略サイト4ソース(ポケらく/ゲームエイト/Pokelog/こいき10選)の**人間による評価**を
統合した独自ティア。計算由来のティア(RaenonX等)は、スキル型の強ポケを食材軸で
F評価してしまうため採用していない。詳細は _meta.note 参照。
「強いポケモンほど理想構成(AAA等)で優先確保する」という捕獲方針に使う。
概念の背景: docs/eval_context/community_concepts.md
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

TIER_PATH = Path(__file__).resolve().parent.parent / "data" / "community_tier.json"

# 捕獲優先度スコアに掛けるティア係数。未掲載は1.0の等倍。
TIER_WEIGHT: dict[str, float] = {"SS": 2.4, "S": 2.0, "A": 1.6, "B": 1.3, "C": 1.1, "D": 1.0}

# この票数を下回る種族は「参考値」。多数決として成立していないので強く推さない。
MIN_RELIABLE_SOURCES = 2


@lru_cache(maxsize=1)
def _records() -> dict[str, dict[str, Any]]:
    if not TIER_PATH.exists():
        return {}
    data = json.loads(TIER_PATH.read_text(encoding="utf-8"))
    return {r["species_name"]: r for r in data.get("records", [])}


@lru_cache(maxsize=1)
def _tier_map() -> dict[str, str]:
    return {n: r["tier"] for n, r in _records().items()}


def get_tier(species_name: str | None) -> str | None:
    """種族の統合ティア(SS/S/A/B/C/D)。未掲載は None。"""
    if not species_name:
        return None
    return _tier_map().get(species_name)


def get_tier_detail(species_name: str | None) -> dict[str, Any] | None:
    """ティアの内訳。何ソースがどう評価したか、意見の割れ幅まで返す。

    UI で「3サイト中3つがSS」「評価が割れている」を出すために使う。
    """
    if not species_name:
        return None
    return _records().get(species_name)


def is_reliable(species_name: str | None) -> bool:
    """多数決として成立している(2ソース以上で評価されている)か。"""
    r = get_tier_detail(species_name)
    return bool(r) and int(r.get("sources") or 0) >= MIN_RELIABLE_SOURCES


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


TIER_ORDER = ["SS", "S", "A", "B", "C", "D"]


def top_tier_species(min_tier: str = "B", reliable_only: bool = True) -> list[tuple[str, str]]:
    """min_tier 以上の (species_name, tier) をティア順→統合スコア順で返す。

    reliable_only=True なら1ソースしか評価していない種族を除く（多数決が成立しないため）。
    """
    limit = TIER_ORDER.index(min_tier) if min_tier in TIER_ORDER else len(TIER_ORDER) - 1
    allowed = set(TIER_ORDER[: limit + 1])
    recs = _records()
    items = [(n, r["tier"]) for n, r in recs.items()
             if r["tier"] in allowed and (not reliable_only or is_reliable(n))]
    items.sort(key=lambda x: (TIER_ORDER.index(x[1]), -float(recs[x[0]].get("score") or 0)))
    return items
