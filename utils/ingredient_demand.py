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
# 育てれば基準に届くのか）。食材枠は Lv30 で2枠目、Lv60 で3枠目が開くので、
# 見たい段階は基本この2つ。
GROWTH_LEVELS = (30, 60)


def best_supply_per_ingredient(
    owned: list[dict[str, Any]], *, level: int | None = None
) -> dict[str, float]:
    """食材ごとに「一番多く拾える1体」の供給量/日を返す。

    level を指定すると、各個体をその段階まで育てた姿で計算する:
      - レベルは max(現在Lv, level)。すでに上回っている個体を下げたりはしない
      - 種族は最終進化に置き換える（そのLvなら進化しているのが普通のため）
      - 食材枠の選択は個体のものを引き継ぎ、未選択の枠は種族の既定を使う
    level=None なら現在のLv・構成そのまま。
    """
    ctx = load_play_context()
    best: dict[str, float] = {}
    for p in owned:
        name = str(p.get("species_name") or "")
        if level is None:
            species = db.get_species_data(name) or {}
            target = p
        else:
            final_name = final_evolution_of(name)
            species = db.get_species_data(final_name) or db.get_species_data(name) or {}
            target = dict(p)
            target["species_name"] = final_name
            target["current_level"] = max(int(p.get("current_level") or 0), int(level))
        for ingredient, qty in expected_ingredients_per_day(target, species, ctx).items():
            if qty > best.get(ingredient, 0.0):
                best[ingredient] = qty
    return best


# ---------------------------------------------------------------------------
# 料理ごとの到達度
# ---------------------------------------------------------------------------
# 不足の「量」は強い個体を1体引いた瞬間に消える。あと数個の差はサブスキルや
# おてつだいボーナス、編成で吸収できる。だから達成率はしきい値で丸めて
# 「ここまで来ていれば足りている」と扱い、**同じ料理を組む相方のうち本当に遠い
# 食材だけ**が残るようにする。
REACH_THRESHOLD = 0.7


@dataclass(frozen=True)
class RecipeReach:
    recipe_name: str
    category: str
    energy_lv60: int
    total_ingredients: int
    reach: float                       # 0〜1。全食材の実質達成率の積
    missing: tuple[tuple[str, float], ...]  # (食材名, 実質達成率) を低い順に

    @property
    def missing_count(self) -> int:
        return len(self.missing)


def recipe_reachability(
    best_supply: dict[str, float],
    *,
    meals_per_day: float = MEALS_PER_DAY,
    threshold: float = REACH_THRESHOLD,
) -> list[RecipeReach]:
    """料理ごとの到達度。「あとこの食材さえあれば作れる」を読むための一覧。

    best_supply: 食材 → 一番多く拾える1体の供給量/日（段階はここで決めて渡す）
    threshold:   達成率がこの水準を超えたら「足りている」と丸める

    実質達成率 r' = min(1, r / threshold)。到達度は r' の積なので、
    相方が全部そろっている料理ほど、残り1つの食材の影響がそのまま出る。
    """
    from utils.recipe_level import recipe_energy  # 循環を避けて遅延取り込み

    out: list[RecipeReach] = []
    for recipe in db.list_all_recipe_records():
        items = recipe.get("ingredients") or []
        if not items:
            continue  # ごちゃまぜ系
        reach = 1.0
        missing: list[tuple[str, float]] = []
        for item in items:
            name = str(item["name"])
            need = float(item["count"]) * meals_per_day
            got = float(best_supply.get(name, 0.0))
            ratio = min(1.0, (got / need) / threshold) if need > 0 else 1.0
            reach *= ratio
            if ratio < 1.0:
                missing.append((name, ratio))
        missing.sort(key=lambda x: x[1])
        out.append(RecipeReach(
            recipe_name=str(recipe.get("name") or ""),
            category=str(recipe.get("category") or ""),
            energy_lv60=int(recipe_energy(recipe, 60)),
            total_ingredients=int(recipe.get("total_ingredients") or 0),
            reach=reach,
            missing=tuple(missing),
        ))
    # 「あと1つで届く」ものを上に、その中はエナジーの高い順
    out.sort(key=lambda r: (r.missing_count, -r.energy_lv60))
    return out
