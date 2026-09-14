"""食材ごとの「基準量」（1日あたり何個あれば強い料理を回せるか）。

※ このファイルは独立した新規モジュールとして置いている。既存モジュールに関数を
足して from-import すると、Streamlit Cloud が古いモジュールを掴んだままのときに
ページ全体が ImportError で落ちる（過去に3回発生）。新規モジュールなら必ず新しく
読み込まれるので、この落ち方を構造的に避けられる。
"""

from __future__ import annotations

from dataclasses import dataclass

import db


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
