"""1日あたりのメインスキル発動エナジー期待値。

evaluator._calc_skill_value（1秒あたりのスキル価値）を日次実効秒数モデル
（utils/genki.DAILY_EFFECTIVE_ASSIST_SECONDS、food_expectation と同じ）で日次化する。
おやすみリボン・おてつだいボーナスの扱いも food_expectation と同一軸で補正する。
"""

from __future__ import annotations

from typing import Any

from utils.evaluator import _calc_skill_value
from utils.food_expectation import _effective_level, _individual_subs
from utils.genki import DAILY_EFFECTIVE_ASSIST_SECONDS
from utils.sleep_ribbon import get_time_multiplier


def expected_skill_energy_per_day(
    pokemon: dict[str, Any],
    species: dict[str, Any],
    *,
    team_help_bonus_count: int = 0,
) -> float:
    """個体の1日あたりメインスキル発動エナジー期待値（エナジー相当）。

    未収録カテゴリは evaluator 側のフォールバック係数で粗く近似される。
    main_skill_rate が null の種は 0。
    """
    per_sec = _calc_skill_value(
        species,
        nature=pokemon.get("nature"),
        subs=_individual_subs(pokemon),
        main_skill_level=int(pokemon.get("main_skill_level") or 1),
        level=_effective_level(pokemon),
    )
    if per_sec <= 0.0:
        return 0.0

    ribbon_stage = int(pokemon.get("sleep_ribbon_stage") or 0)
    species_name = pokemon.get("species_name") or species.get("name") or ""
    ribbon_time_mult = (
        get_time_multiplier(species_name=species_name, stage=ribbon_stage)
        if ribbon_stage > 0
        else 1.0
    )
    team_mult = 1.0 + 0.05 * team_help_bonus_count

    return per_sec * DAILY_EFFECTIVE_ASSIST_SECONDS * team_mult / ribbon_time_mult


if __name__ == "__main__":
    # python -m utils.skill_expectation で簡易検算（DB接続が必要）
    import db

    owned = [dict(r) for r in db.list_pokemon()]
    for p in owned[:5]:
        species = db.get_species_data(p["species_name"]) or {}
        e = expected_skill_energy_per_day(p, species)
        print(f"{p.get('nickname') or p['species_name']:20s} {e:10.0f} en/日")
