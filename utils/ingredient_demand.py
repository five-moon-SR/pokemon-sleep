"""食材ごとの「基準量」（1日あたり何個あれば強い料理を回せるか）。

※ このファイルは独立した新規モジュールとして置いている。既存モジュールに関数を
足して from-import すると、Streamlit Cloud が古いモジュールを掴んだままのときに
ページ全体が ImportError で落ちる（過去に3回発生）。新規モジュールなら必ず新しく
読み込まれるので、この落ち方を構造的に避けられる。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import db
from utils.evaluator import final_evolution_of
from utils.food_expectation import expected_ingredients_per_day
from utils.play_context import load_play_context


# カビゴンには朝・昼・晩の1日3食を作る。
MEALS_PER_DAY = 3.0


@dataclass(frozen=True)
class IngredientDemand:
    """その食材に置く基準（1日あたり必要個数）と、その根拠になった料理。"""

    ingredient: str
    per_meal: float            # 1食あたりの必要個数（要求する料理のトップ2平均）
    meals_per_day: float
    sources: tuple[tuple[str, int], ...]  # (料理名, 必要個数) を必要量の多い順に

    @property
    def per_day(self) -> float:
        return self.per_meal * self.meals_per_day

    @property
    def label(self) -> str:
        return " / ".join(f"{name}({count})" for name, count in self.sources)


def demanding_recipes(
    *,
    meals_per_day: float = MEALS_PER_DAY,
    top_n: int = 2,
) -> dict[str, IngredientDemand]:
    """食材ごとの基準量（個/日）。

    頭数で「担当が2体いるか」を見ても、実際に回るかは量で決まる。基準は
    **その食材を必要とする料理のうち、必要量トップ2の平均**に置く。今後どの強い
    料理を狙うことになっても耐えられる水準を見たいので、鍋容量では絞らない。

    1体でこの基準に届く食材はほぼ無い。だからこそ二値の合否ではなく達成率で見て、
    「どの食材が一番遠いか」を並びで判断する使い方をする。
    """
    per_ingredient: dict[str, list[tuple[int, str]]] = {}
    for recipe in db.list_all_recipe_records():
        name = str(recipe.get("name") or "")
        for item in recipe.get("ingredients") or []:
            per_ingredient.setdefault(str(item["name"]), []).append((int(item["count"]), name))

    out: dict[str, IngredientDemand] = {}
    for ingredient, entries in per_ingredient.items():
        picked = sorted(entries, reverse=True)[:top_n]
        if not picked:
            continue
        avg = sum(count for count, _ in picked) / len(picked)
        out[ingredient] = IngredientDemand(
            ingredient=ingredient,
            per_meal=avg,
            meals_per_day=float(meals_per_day),
            sources=tuple((name, count) for count, name in picked),
        )
    return out


# 育成後の姿でどこまで伸びるかを見たいことがある（今は足りなくても、
# 最終進化のLv60まで育てれば基準に届くのか）。
POTENTIAL_LEVEL = 60


def best_supply_per_ingredient(
    owned: list[dict[str, Any]], *, grown: bool = False
) -> dict[str, float]:
    """食材ごとに「一番多く拾える1体」の供給量/日を返す。

    grown=True なら、各個体を最終進化・Lv{POTENTIAL_LEVEL} に置き換えて計算する
    （食材枠の選択は個体のものを引き継ぎ、未選択の枠は種族の既定を使う）。
    """
    ctx = load_play_context()
    best: dict[str, float] = {}
    for p in owned:
        name = str(p.get("species_name") or "")
        if grown:
            final_name = final_evolution_of(name)
            species = db.get_species_data(final_name) or db.get_species_data(name) or {}
            target = dict(p)
            target["species_name"] = final_name
            target["current_level"] = max(
                int(p.get("current_level") or 0), POTENTIAL_LEVEL
            )
        else:
            species = db.get_species_data(name) or {}
            target = p
        for ingredient, qty in expected_ingredients_per_day(target, species, ctx).items():
            if qty > best.get(ingredient, 0.0):
                best[ingredient] = qty
    return best
