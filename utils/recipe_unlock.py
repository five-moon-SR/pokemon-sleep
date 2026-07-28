"""「この強い料理を作るには誰が要るか」を逆引きする。

既存の capture_improvements は、主料理を1品に固定したうえで
「未所持の1体を差し込むと安定度/週エナジーがいくら伸びるか」を測る。
ところが**必要食材を2つ以上欠いている料理**では、素の編成も候補入り編成も
1食も作れず（cooked=0）、差分が丸ごと 0 に潰れる。呼び出し側は
delta>0 でフィルタしているので、**一番知りたい「まだ作れない強料理」ほど
「候補なし」と表示される**という逆転が起きていた。

ここでは料理側からたどる:

  1. カテゴリ内の全レシピについて、今の手札で供給できる食材と突き合わせ、
     「あと何種の食材が足りないか」を出す
  2. 足りない食材ごとに、それを供給できる未所持の最終進化種を挙げる
  3. 何体そろえば「作れる」状態に届くかと、そこまで行った時の週エナジーを出す

つまり評価軸は「1体入れた時の差分」ではなく**到達までの距離**。
これなら作れない料理でも 0 に潰れない。

捕獲場所（utils.field_encounters）と種族ティア（utils.community_tier）も
併せて返すので、「どこで捕まえるか・どれくらい強い種族か」まで一度に判る。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import db
from utils.community_tier import get_tier
from utils.food_expectation import expected_ingredients_per_day
from utils.party_logic import get_play_ctx
from utils.play_context import PlayContext
from utils.recipe_level import get_recipe_level, recipe_energy

# 1日3食ぶん賄えていれば「供給できている」とみなす
MEALS_PER_DAY = 3


@dataclass
class MissingIngredient:
    """足りない食材と、それを埋められる未所持種。"""

    name: str
    required_per_day: float      # 3食ぶん必要な量/日
    supplied_per_day: float      # 今の手札で供給できる量/日
    candidates: list[dict[str, Any]] = field(default_factory=list)

    @property
    def shortfall(self) -> float:
        return max(0.0, self.required_per_day - self.supplied_per_day)


@dataclass
class RecipeGap:
    """1レシピぶんの「作れるまでの距離」。"""

    recipe: dict[str, Any]
    level: int
    energy_now: float            # 今の料理レベルで1回作った時のエナジー
    energy_at_60: float          # 育て切った時の目安（伸びしろの提示用）
    missing: list[MissingIngredient]
    cookable: bool               # 今の手札で食材が足りているか

    @property
    def missing_count(self) -> int:
        return len(self.missing)

    @property
    def needed_species(self) -> list[str]:
        """穴ごとに最有力の1体を拾った、最小の必要種リスト。"""
        out: list[str] = []
        for m in self.missing:
            if m.candidates and m.candidates[0]["species_name"] not in out:
                out.append(m.candidates[0]["species_name"])
        return out



def _supply_per_day(owned: list[dict[str, Any]], ctx: PlayContext) -> dict[str, float]:
    """手札全体の食材供給量/日。誰が編成に入るかは問わない粗い上限。"""
    out: dict[str, float] = {}
    for p in owned:
        master = db.get_species_data(p.get("species_name") or "")
        if not master:
            continue
        # 返りは {食材名: 個数/日} の辞書
        for name, count in expected_ingredients_per_day(p, master, ctx).items():
            if count > 0:
                out[name] = out.get(name, 0.0) + float(count)
    return out


def _species_for_ingredient(
    ingredient: str,
    owned_species: set[str],
    finals: set[str],
) -> list[dict[str, Any]]:
    """その食材を供給できる未所持の最終進化種。ティアと出現マップつき。"""
    from utils.field_encounters import species_fields

    out: list[dict[str, Any]] = []
    for species in db.list_all_master_records():
        name = species.get("species_name")
        if not name or name in owned_species or name not in finals:
            continue
        slots = species.get("ingredients") or {}
        available = {
            slot.get("name")
            for slot in slots.values()
            if isinstance(slot, dict) and slot.get("name")
        }
        if ingredient not in available:
            continue
        out.append({
            "species_name": name,
            "tier": get_tier(name),
            "fields": list(species_fields(name) or []),
            "specialty": species.get("specialty"),
        })
    # ティアの高い順（未評価は後ろ）→ 名前順で安定させる
    order = {"SS": 0, "S": 1, "A": 2, "B": 3, "C": 4, "D": 5}
    out.sort(key=lambda x: (order.get(x["tier"] or "", 9), x["species_name"]))
    return out


def recipe_gaps(
    owned: list[dict[str, Any]],
    recipes: list[dict[str, Any]],
    *,
    ctx: PlayContext | None = None,
    limit: int = 8,
) -> list[RecipeGap]:
    """料理ごとに「作れるまで何が足りないか」を出し、エナジーの高い順に返す。

    recipes は同カテゴリのレシピ一覧。所持全体の供給量と突き合わせるだけなので
    7日シミュレーションは回さない（実測 0.01 秒）。
    """
    ctx = ctx or get_play_ctx()
    supply = _supply_per_day(owned, ctx)
    owned_species = {p.get("species_name") for p in owned}
    from utils.ingredient_coverage import _final_evolutions

    finals = set(_final_evolutions())

    gaps: list[RecipeGap] = []
    for rec in recipes:
        reqs = rec.get("ingredients") or []
        if not reqs:
            continue  # ごちゃまぜ系は対象外
        missing: list[MissingIngredient] = []
        for item in reqs:
            name = item["name"]
            need = float(item["count"]) * MEALS_PER_DAY
            have = supply.get(name, 0.0)
            if have + 1e-9 >= need:
                continue
            missing.append(MissingIngredient(
                name=name,
                required_per_day=need,
                supplied_per_day=have,
                candidates=_species_for_ingredient(name, owned_species, finals)[:3],
            ))
        gaps.append(RecipeGap(
            recipe=rec,
            level=get_recipe_level(rec.get("name")),
            energy_now=recipe_energy(rec),
            energy_at_60=recipe_energy(rec, 60),
            missing=missing,
            cookable=not missing,
        ))

    # 並びはエナジーの高い順。作れる/作れないで先に切ると、
    # 一番知りたい「まだ作れない強料理」が下に埋まってしまう。
    gaps.sort(key=lambda g: -g.energy_at_60)
    return gaps[:limit]


if __name__ == "__main__":
    # python -m utils.recipe_unlock で検算（DB接続が必要）
    ctx = get_play_ctx()
    owned = [dict(r) for r in db.list_pokemon()]
    recipes = [r for r in db.list_all_recipe_records() if r.get("category") == "salad"]
    for gap in recipe_gaps(owned, recipes, ctx=ctx):
        state = "作れる" if gap.cookable else f"あと{gap.missing_count}種"
        print(f"{gap.recipe['name']:26} {state:8} 現在 {gap.energy_now:>9,.0f} / Lv60 {gap.energy_at_60:>9,.0f}")
        for m in gap.missing:
            names = " / ".join(
                f"{cd['species_name']}({cd['tier'] or '—'})" for cd in m.candidates
            ) or "候補なし"
            print(f"    {m.name}: {m.supplied_per_day:.1f}/{m.required_per_day:.1f} → {names}")
