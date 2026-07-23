"""食材担当・料理充足度・育成/捕獲優先度の計算層。

すべてインメモリ計算（所持数十体 × 19食材の走査はミリ秒オーダー）。
「狙いのレシピ」は db の user_settings KV（キー: user.target_recipes）に永続化する。

優先度の考え方:
- 育成優先度: 個体をマイルストーンLv(30/50/60)まで上げた時の食材供給の増分が、
  狙いレシピの料理エナジーをどれだけ改善するかを「1Lvあたり」で効率評価。
  Lv30/60 は食材スロット解放で供給が不連続に跳ねるので、マイルストーン評価が本質。
- 捕獲優先度: 未所持種族の理想個体（Lv60・補正なし）供給のうち、
  穴食材の不足分を埋める分だけを加点（min(supply, shortage)。過剰供給は加点しない）。
  進化系列は最終進化に集約して表示する。

検算: python -m utils.ingredient_coverage （DB接続が必要）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import db
from utils.food_expectation import (
    _effective_level,
    expected_ingredients_per_day,
    qty_at_slot,
)
from utils.community_tier import get_tier, tier_weight
from utils.party_logic import _main_recipe_pace, _recipe_base_energy, get_play_ctx

TARGET_RECIPES_KEY = "user.target_recipes"

# 食材スロット解放Lv（slot1=Lv1, slot2=Lv30, slot3=Lv60）
_SLOT_UNLOCK = {"a": 1, "b": 30, "c": 60}

# 育成優先度で評価するマイルストーンLv
MILESTONES = (30, 50, 60)


def load_target_recipes() -> list[str]:
    return list(db.get_setting(TARGET_RECIPES_KEY, []) or [])


def save_target_recipes(names: list[str]) -> None:
    db.set_setting(TARGET_RECIPES_KEY, list(names))


# ---------------------------------------------------------------------------
# 食材 → 担当個体の逆引き
# ---------------------------------------------------------------------------

@dataclass
class IngredientProvider:
    pokemon_id: int
    label: str                 # ニックネーム or 種族名
    species_name: str
    slot: str                  # "a"/"b"/"c"
    unlock_lv: int             # 1/30/60
    unlocked: bool             # 現在Lvで解放済みか
    per_day_now: float         # 現在の食材選択・現在Lvでの供給量/日（未選択なら0）


def build_ingredient_index(
    owned_rows: list[dict[str, Any]],
) -> dict[str, list[IngredientProvider]]:
    """全食材 → 担当可能な所持個体リスト。

    「担当可能」= 種族の a/b/c 枠にその食材がある。per_day_now は
    実際にその食材を選んでいる場合の現在供給量（expected_ingredients_per_day）。
    """
    ctx = get_play_ctx()
    all_ings = [r["name"] for r in db.list_all_ingredient_records()]
    index: dict[str, list[IngredientProvider]] = {n: [] for n in all_ings}

    for p in owned_rows:
        master = db.get_species_data(p["species_name"]) or {}
        if not master:
            continue
        current = expected_ingredients_per_day(p, master, ctx)
        lv = _effective_level(p)
        for slot_key in ("a", "b", "c"):
            slot_def = (master.get("ingredients") or {}).get(slot_key)
            if not slot_def or not slot_def.get("name"):
                continue
            name = slot_def["name"]
            if name not in index:
                index[name] = []
            index[name].append(IngredientProvider(
                pokemon_id=p["id"],
                label=p.get("nickname") or p["species_name"],
                species_name=p["species_name"],
                slot=slot_key,
                unlock_lv=_SLOT_UNLOCK[slot_key],
                unlocked=lv >= _SLOT_UNLOCK[slot_key],
                per_day_now=current.get(name, 0.0),
            ))

    for providers in index.values():
        providers.sort(key=lambda x: -x.per_day_now)
    return index


# ---------------------------------------------------------------------------
# 多能な主力（複数食材で上位担当を張れる個体）
# ---------------------------------------------------------------------------

# 「主力」とみなす上位担当の人数（編成に乗る現実枠）
MAIN_TOP_N = 2


@dataclass
class VersatileMain:
    pokemon_id: int
    label: str
    species_name: str
    duties: list[tuple[str, float]]   # (食材名, 供給量/日) を供給量降順。この個体が主力の食材のみ
    total_per_day: float              # 主力担当ぶんの供給量/日 合計


def versatile_mains(
    index: dict[str, list[IngredientProvider]],
    *,
    top_n: int = MAIN_TOP_N,
    min_duties: int = 2,
) -> list[VersatileMain]:
    """1体で複数食材の上位 top_n（=主力）に入る個体を抽出。

    build_ingredient_index() の結果を渡す。編成枠が限られる中で
    二役以上こなせる個体は価値が高いので、別枠で洗い出す用途。
    duties 数の多い順 → 合計供給量の多い順でランキング。
    """
    acc: dict[int, VersatileMain] = {}
    for name, providers in index.items():
        active = [p for p in providers if p.per_day_now > 0]
        for p in active[:top_n]:
            vm = acc.get(p.pokemon_id)
            if vm is None:
                vm = VersatileMain(
                    pokemon_id=p.pokemon_id,
                    label=p.label,
                    species_name=p.species_name,
                    duties=[],
                    total_per_day=0.0,
                )
                acc[p.pokemon_id] = vm
            vm.duties.append((name, p.per_day_now))
            vm.total_per_day += p.per_day_now

    out = [vm for vm in acc.values() if len(vm.duties) >= min_duties]
    for vm in out:
        vm.duties.sort(key=lambda d: -d[1])
    out.sort(key=lambda vm: (-len(vm.duties), -vm.total_per_day))
    return out


# ---------------------------------------------------------------------------
# レシピ充足度
# ---------------------------------------------------------------------------

@dataclass
class RecipeCoverage:
    recipe: dict
    pace: float                                    # 1日あたり作成可能回数
    daily_energy: float                            # pace × base_energy
    per_ingredient: dict[str, tuple[float, float]]  # name -> (need, have) /日換算
    holes: list[str]                               # 律速（比率最小）食材


def team_supply(owned_rows: list[dict[str, Any]]) -> dict[str, float]:
    """全所持個体の食材供給合計/日（チームバフなし・現在Lv基準）。"""
    ctx = get_play_ctx()
    total: dict[str, float] = {}
    for p in owned_rows:
        master = db.get_species_data(p["species_name"]) or {}
        if not master:
            continue
        for n, v in expected_ingredients_per_day(p, master, ctx).items():
            total[n] = total.get(n, 0.0) + v
    return total


def recipe_coverage(
    target_recipe_names: list[str],
    supply: dict[str, float],
) -> list[RecipeCoverage]:
    """狙いレシピごとの充足度。supply は team_supply() の結果を渡す。"""
    all_recipes = {r["name"]: r for r in db.list_all_recipe_records()}
    out: list[RecipeCoverage] = []
    for name in target_recipe_names:
        rec = all_recipes.get(name)
        if not rec or not rec.get("ingredients"):
            continue
        pace, holes = _main_recipe_pace(rec, supply)
        per_ing = {
            ing["name"]: (float(ing["count"]), supply.get(ing["name"], 0.0))
            for ing in rec["ingredients"]
        }
        out.append(RecipeCoverage(
            recipe=rec,
            pace=pace,
            daily_energy=pace * _recipe_base_energy(rec),
            per_ingredient=per_ing,
            holes=holes,
        ))
    return out


def _dish_energy(supply: dict[str, float], recipes: list[dict]) -> float:
    """供給量に対する狙いレシピ群の合計期待エナジー/日。"""
    total = 0.0
    for rec in recipes:
        pace, _ = _main_recipe_pace(rec, supply)
        total += pace * _recipe_base_energy(rec)
    return total


# ---------------------------------------------------------------------------
# 育成優先度
# ---------------------------------------------------------------------------

@dataclass
class TrainingPriority:
    pokemon_id: int
    label: str
    species_name: str
    current_lv: int
    best_milestone: int
    gain_per_lv: float                  # 1Lvあたりの料理エナジー改善（効率）
    total_gain: float                   # ベストマイルストーン到達時の改善合計
    delta_supply: dict[str, float] = field(default_factory=dict)  # 増える食材


def training_priorities(
    owned_rows: list[dict[str, Any]],
    target_recipe_names: list[str],
) -> list[TrainingPriority]:
    """「誰を伸ばすと狙いレシピの穴が埋まるか」を1Lvあたり効率で降順ランキング。"""
    ctx = get_play_ctx()
    all_recipes = {r["name"]: r for r in db.list_all_recipe_records()}
    recipes = [
        all_recipes[n] for n in target_recipe_names
        if n in all_recipes and all_recipes[n].get("ingredients")
    ]
    if not recipes:
        return []

    supply = team_supply(owned_rows)
    base_energy = _dish_energy(supply, recipes)

    out: list[TrainingPriority] = []
    for p in owned_rows:
        master = db.get_species_data(p["species_name"]) or {}
        if not master:
            continue
        cur_lv = _effective_level(p)
        cur_supply = expected_ingredients_per_day(p, master, ctx)

        best: TrainingPriority | None = None
        for ms in MILESTONES:
            if ms <= cur_lv:
                continue
            boosted = dict(p)
            boosted["current_level"] = ms
            new_supply = expected_ingredients_per_day(boosted, master, ctx)
            delta = {
                n: new_supply.get(n, 0.0) - cur_supply.get(n, 0.0)
                for n in set(new_supply) | set(cur_supply)
            }
            team_after = dict(supply)
            for n, v in delta.items():
                team_after[n] = team_after.get(n, 0.0) + v
            gain = _dish_energy(team_after, recipes) - base_energy
            if gain <= 0:
                continue
            eff = gain / (ms - cur_lv)
            if best is None or eff > best.gain_per_lv:
                best = TrainingPriority(
                    pokemon_id=p["id"],
                    label=p.get("nickname") or p["species_name"],
                    species_name=p["species_name"],
                    current_lv=cur_lv,
                    best_milestone=ms,
                    gain_per_lv=eff,
                    total_gain=gain,
                    delta_supply={n: v for n, v in delta.items() if v > 0.005},
                )
        if best:
            out.append(best)

    out.sort(key=lambda x: -x.gain_per_lv)
    return out


# ---------------------------------------------------------------------------
# 捕獲優先度
# ---------------------------------------------------------------------------

@dataclass
class CatchPriority:
    species_name: str
    dex_no: str
    score: float                          # 穴埋め期待エナジー/日 × コミュニティティア係数
    tier: str | None = None               # コミュニティ評価(S/A/B/C、未掲載None)
    fills: dict[str, float] = field(default_factory=dict)  # 食材 -> 埋まる量/日


def _final_evolutions() -> set[str]:
    """進化系列の最終進化のみの種族名集合（進化元にならない種族）。"""
    evolutions = db.list_all_evolution_records()
    sources = {e["from"] for e in evolutions}
    names = set(db.list_species_names())
    return {n for n in names if n not in sources}


def _ideal_supply(species: dict[str, Any]) -> dict[str, float]:
    """理想個体（Lv60・性格/サブ補正なし・各スロットにデフォルト枠食材）の供給量/日。

    food_drop_rate 未掲載種（Wiki自動取り込みの新ポケ等）は暫定20%で概算し、
    候補から漏れないようにする。
    """
    pseudo = {
        "species_name": species.get("species_name"),
        "current_level": 60,
    }
    if species.get("food_drop_rate") is None:
        species = {**species, "food_drop_rate": 20.0}
    return expected_ingredients_per_day(pseudo, species, get_play_ctx())


def catch_priorities(
    owned_rows: list[dict[str, Any]],
    target_recipe_names: list[str],
    *,
    ingredient_energy: dict[str, float] | None = None,
) -> list[CatchPriority]:
    """未所持種族の捕獲優先度。穴食材の不足分を埋める分だけ加点。"""
    all_recipes = {r["name"]: r for r in db.list_all_recipe_records()}
    recipes = [
        all_recipes[n] for n in target_recipe_names
        if n in all_recipes and all_recipes[n].get("ingredients")
    ]
    if not recipes:
        return []

    supply = team_supply(owned_rows)

    # 穴の深さ: 狙いレシピを1日1回ずつ作る need 合計に対する不足
    need: dict[str, float] = {}
    for rec in recipes:
        for ing in rec["ingredients"]:
            need[ing["name"]] = need.get(ing["name"], 0.0) + float(ing["count"])
    shortage = {
        n: max(0.0, v - supply.get(n, 0.0)) for n, v in need.items()
    }
    if not any(v > 0 for v in shortage.values()):
        return []

    if ingredient_energy is None:
        ingredient_energy = {
            r["name"]: float(r.get("base_energy") or 1.0)
            for r in db.list_all_ingredient_records()
        }

    owned_species = {p["species_name"] for p in owned_rows}
    finals = _final_evolutions()

    out: list[CatchPriority] = []
    for name in db.list_species_names():
        if name in owned_species or name not in finals:
            continue
        species = db.get_species_data(name) or {}
        ideal = _ideal_supply(species)
        fills = {
            n: min(v, shortage.get(n, 0.0))
            for n, v in ideal.items()
            if shortage.get(n, 0.0) > 0
        }
        fills = {n: v for n, v in fills.items() if v > 0.005}
        if not fills:
            continue
        # コミュニティ評価が高い種族ほど優先(強ポケは理想構成で確保したい)
        score = sum(v * ingredient_energy.get(n, 1.0) for n, v in fills.items()) * tier_weight(name)
        out.append(CatchPriority(
            species_name=name,
            dex_no=species.get("dex_no") or "",
            score=score,
            tier=get_tier(name),
            fills=fills,
        ))

    out.sort(key=lambda x: -x.score)
    return out


if __name__ == "__main__":
    # python -m utils.ingredient_coverage で検算（DB接続が必要）
    owned = [dict(r) for r in db.list_pokemon()]
    print(f"所持: {len(owned)} 体")

    idx = build_ingredient_index(owned)
    total_slots = sum(len(v) for v in idx.values())
    print(f"逆引き: {sum(1 for v in idx.values() if v)}/{len(idx)} 食材に担当あり / 全{total_slots}枠")

    targets = load_target_recipes() or [
        r["name"] for r in db.list_all_recipe_records()[:3]
    ]
    print(f"狙いレシピ: {targets}")
    for cov in recipe_coverage(targets, team_supply(owned)):
        print(f"  {cov.recipe['name']}: pace={cov.pace:.2f}/日 穴={cov.holes}")

    for tp in training_priorities(owned, targets)[:5]:
        print(
            f"  育成: {tp.label} Lv{tp.current_lv}→{tp.best_milestone} "
            f"効率{tp.gain_per_lv:.1f}en/Lv 合計+{tp.total_gain:.0f}en/日 {list(tp.delta_supply)}"
        )
    for cp in catch_priorities(owned, targets)[:5]:
        print(f"  捕獲: {cp.species_name} score={cp.score:.0f} 埋まる穴={list(cp.fills)}")
