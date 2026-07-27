"""リサーチフィールド別の出現ポケモン(data/field_encounters.json)のアクセサ。

「今週のマップで出る種だけに絞る」「未所持の強ポケが一番出るマップを薦める」に使う。
取得は scripts/fetch_field_encounters.py（wikiwiki のリサーチフィールド各ページ）。

EXフィールドは表の構造が違い取得できていない。データが無いフィールドは
「出現不明」として扱い、絞り込みをかけない（誤って候補を消さないため）。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ENCOUNTER_PATH = Path(__file__).resolve().parent.parent / "data" / "field_encounters.json"


@lru_cache(maxsize=1)
def _by_field() -> dict[str, set[str]]:
    if not ENCOUNTER_PATH.exists():
        return {}
    data = json.loads(ENCOUNTER_PATH.read_text(encoding="utf-8"))
    return {
        r["field_name"]: {e["species_name"] for e in r.get("encounters") or []}
        for r in data.get("records", [])
    }


@lru_cache(maxsize=1)
def _by_species() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for field, names in _by_field().items():
        for n in names:
            out.setdefault(n, []).append(field)
    return {k: sorted(v) for k, v in out.items()}


def has_data(field_name: str | None) -> bool:
    """そのフィールドの出現データを持っているか。EX等は未取得。"""
    return bool(field_name) and bool(_by_field().get(field_name))


def field_species(field_name: str | None) -> set[str]:
    """フィールドに出現する種族。データが無ければ空集合。"""
    return set(_by_field().get(field_name or "", set()))


def species_fields(species_name: str | None) -> list[str]:
    """その種族が出現するフィールド一覧。"""
    return list(_by_species().get(species_name or "", []))


def appears_in(species_name: str | None, field_name: str | None) -> bool | None:
    """出現するか。データが無いフィールドは判定不能として None を返す。"""
    if not has_data(field_name):
        return None
    return species_name in field_species(field_name)


def recommend_fields(wanted: set[str], limit: int = 8) -> list[tuple[str, int, list[str]]]:
    """欲しい種族が何体出るかでフィールドを並べる。

    Returns: [(フィールド名, 該当数, 該当する種族名リスト)] を該当数の降順で。
    """
    rows = []
    for field, names in _by_field().items():
        hit = sorted(wanted & names)
        if hit:
            rows.append((field, len(hit), hit))
    rows.sort(key=lambda x: (-x[1], x[0]))
    return rows[:limit]
