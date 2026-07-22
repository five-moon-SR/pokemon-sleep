"""パーティー編成の純ロジック層。

views/party.py から切り出した計算・スコアリング関数群（挙動不変の移設）。
Streamlit に依存しないので、CLIやオプティマイザ(utils/optimizer.py)からも使える。
スコア係数は仮置き。後でいろんなサイトを参考にしながら齋藤さんと調整する想定。
"""

from __future__ import annotations

import db
from image_utils import ingredient_icon_url
from utils.food_expectation import expected_berry_per_day, expected_ingredients_per_day
from utils.play_context import load_play_context

_play_ctx_cache = None


def get_play_ctx():
    """プレイ前提(PlayContext)を遅延ロードして使い回す。

    module import時にDB接続しない（CLI/オプティマイザから安全にimportするため）。
    """
    global _play_ctx_cache
    if _play_ctx_cache is None:
        _play_ctx_cache = load_play_context()
    return _play_ctx_cache

# -------------- 定数 --------------

RECIPE_CATEGORY_LABELS = {
    "curry_stew": "カレー・シチュー",
    "salad": "サラダ",
    "drink_dessert": "デザート・ドリンク",
}

# 役割キー → ラベル。②の役割タブと役割×目標数スライダーで共通利用。
ROLE_LABELS: dict[str, str] = {
    "recovery": "💚 げんき回復",
    "energy_supply": "⚡ エナジー供給",
    "pot_up": "🍳 鍋容量UP",
    "berry_focus": "🍓 きのみ枠",
    "food_focus": "🥕 食材枠",
}

# 役割プリセット → 各役割の目標人数。selectbox で選んで「適用」するとスライダーに初期値が入る。
ROLE_PRESETS: dict[str, dict[str, int] | None] = {
    "✏ カスタム": None,  # 適用ボタンを無効化
    "⚖ バランス": {"recovery": 1, "energy_supply": 0, "pot_up": 0, "berry_focus": 2, "food_focus": 2},
    "🥕 食材寄せ": {"recovery": 1, "energy_supply": 0, "pot_up": 0, "berry_focus": 1, "food_focus": 3},
    "🍓 きのみ全ツッパ": {"recovery": 1, "energy_supply": 0, "pot_up": 0, "berry_focus": 3, "food_focus": 1},
    "💚 回復多め": {"recovery": 2, "energy_supply": 1, "pot_up": 0, "berry_focus": 1, "food_focus": 1},
    "🍳 鍋拡張型": {"recovery": 1, "energy_supply": 0, "pot_up": 1, "berry_focus": 1, "food_focus": 2},
}

# 今週のイベント補正。複数選択可。空＝補正なし週。役割スコアの重みと表示エナジーに反映。
EVENT_BONUSES: dict[str, str] = {
    "berry_2x": "🍓 きのみエナジー2倍週",
    "dish_2x": "🍳 料理エナジー2倍週",
    "food_2x": "🥕 食材獲得2倍週",
    "all_energy_up": "✨ 全ポケエナジーUP",
}

# 役割タグ → 該当メインスキル名集合（main_skill.json の name 単位）。役割スコアで使用。
MAIN_SKILL_TAG_MAP: dict[str, set[str]] = {
    "げんき回復枠": {
        "げんきエールS", "ほっぺすりすり", "いやしのはどう",
        "げんきチャージS", "つきのひかり",
        "げんきオールS", "みかづきのいのり", "きのみジュース",
    },
    "エナジー供給枠": {
        "エナジーチャージS", "エナジーチャージM", "たくわえる", "ナイトメア",
        "ゆめのかけらゲットS",
    },
    "鍋容量UP枠": {
        "料理パワーアップS", "マイナス",
    },
}

# 役割キー → MAIN_SKILL_TAG_MAP のキー
_ROLE_TO_TAG: dict[str, str] = {
    "recovery": "げんき回復枠",
    "energy_supply": "エナジー供給枠",
    "pot_up": "鍋容量UP枠",
}


# -------------- ヘルパ --------------

def _effective_level(p: dict) -> int:
    return p.get("current_level") or p.get("caught_level") or p.get("level") or 1


def _main_skill_of(p: dict, master: dict) -> str:
    return p.get("main_skill_name") or master.get("main_skill") or ""


def _individual_subs(p: dict) -> list[str]:
    return [
        s for s in (
            p.get("subskill_lv10"),
            p.get("subskill_lv25"),
            p.get("subskill_lv50"),
            p.get("subskill_lv75"),
            p.get("subskill_lv100"),
        ) if s
    ]


def _role_score_skill(
    p: dict, master: dict, role_key: str, axis_key: str
) -> tuple[float, str] | None:
    """メインスキル系役割（recovery / energy_supply / pot_up）の共通スコア計算。

    axis_key: 性格上昇軸の名前（speed/energy/ingredient/skill/exp）。
    """
    skill = _main_skill_of(p, master)
    target_skills = MAIN_SKILL_TAG_MAP.get(_ROLE_TO_TAG[role_key], set())
    if skill not in target_skills:
        return None

    score = 100.0
    nature = p.get("nature")
    nat_rec = db.get_nature_record(nature) if nature else None
    if nat_rec:
        if nat_rec.get("up") == axis_key:
            score += 20
        if nat_rec.get("down") == axis_key:
            score -= 20
    msl = int(p.get("main_skill_level") or 1)
    score += msl * 5

    subs = _individual_subs(p)
    if "スキル確率アップM" in subs:
        score += 15
    elif "スキル確率アップS" in subs:
        score += 8
    if "スキルレベルアップM" in subs:
        score += 10
    elif "スキルレベルアップS" in subs:
        score += 5

    score += min(_effective_level(p) // 10, 6)

    breakdown = f"{skill} Lv{msl}"
    if nat_rec and nat_rec.get("up") == axis_key:
        breakdown += f" / 性格⊕"
    return score, breakdown


def _role_score_berry(
    p: dict, master: dict, fav_set: set[str], event_set: set[str]
) -> tuple[float, str] | None:
    """きのみ枠スコア = 1日獲得エナジー（好物倍率＋イベント補正込み）/ 100。"""
    field_bonus = 1.0 if "berry_2x" in event_set else 0.0
    b = expected_berry_per_day(
        p, master, get_play_ctx(), fav_berries=fav_set, field_bonus=field_bonus
    )
    if not b["name"] or b["energy"] <= 0:
        return None
    score = b["energy"] / 100.0  # 100エナジー=1点

    parts = [f"🍓{b['name']}", f"{int(round(b['energy'])):,} en/日", f"{b['count']:.1f}個"]
    if b["is_favorite"]:
        parts.append("⭐好物")
    if "berry_2x" in event_set:
        parts.append("🍓2x週")
    return score, " / ".join(parts)


def _role_score_food(
    p: dict, master: dict, needed_ings: set[str], event_set: set[str]
) -> tuple[float, str] | None:
    """食材枠スコア = 必要食材一致量 ×10 + 全体食材量 ×1（× 食材2倍週倍率）。"""
    expected = expected_ingredients_per_day(p, master, get_play_ctx())
    if not expected:
        return None
    food_mult = 2.0 if "food_2x" in event_set else 1.0

    if needed_ings:
        matched = {nm: n for nm, n in expected.items() if nm in needed_ings}
        unmatched_total = sum(n for nm, n in expected.items() if nm not in needed_ings)
        matched_total = sum(matched.values())
        score = (matched_total * 10 + unmatched_total) * food_mult
        if matched:
            top = sorted(matched.items(), key=lambda x: -x[1])[:3]
            top_str = " / ".join(f"{nm}{n:.1f}" for nm, n in top)
            breakdown = f"必要食材 {matched_total:.1f}/日 ({top_str})"
        else:
            total = sum(expected.values())
            breakdown = f"必要食材一致なし / 全食材 {total:.1f}/日"
    else:
        total = sum(expected.values())
        score = total * food_mult
        top = sorted(expected.items(), key=lambda x: -x[1])[:3]
        top_str = " / ".join(f"{nm}{n:.1f}" for nm, n in top)
        breakdown = f"全食材 {total:.1f}/日 ({top_str})"

    if "food_2x" in event_set:
        breakdown += " 🥕2x週"
    return score, breakdown


def compute_role_scores(
    p: dict,
    master: dict,
    fav_set: set[str],
    event_set: set[str],
    needed_ings: set[str],
) -> dict[str, tuple[float, str] | None]:
    return {
        "recovery": _role_score_skill(p, master, "recovery", "energy"),
        "energy_supply": _role_score_skill(p, master, "energy_supply", "skill"),
        "pot_up": _role_score_skill(p, master, "pot_up", "skill"),
        "berry_focus": _role_score_berry(p, master, fav_set, event_set),
        "food_focus": _role_score_food(p, master, needed_ings, event_set),
    }


def _team_help_bonus_count(member_ids: list[int]) -> int:
    """編成メンバーの「おてつだいボーナス」サブスキル装着数（自身含む合計）。"""
    count = 0
    for mid in member_ids:
        if not mid:
            continue
        row = db.get_pokemon(mid)
        if row is None:
            continue
        if "おてつだいボーナス" in _individual_subs(dict(row)):
            count += 1
    return count


def party_summary(
    member_ids: list[int],
    *,
    fav_berries: set[str] | None = None,
    field_bonus: float = 0.0,
) -> dict:
    summary = {
        "berries": {},        # name -> {"count": float, "energy": float, "is_favorite": bool}
        "ingredients": {},    # name -> 1日獲得個数（float、性格・サブ・Lv・リボン補正済）
        "main_skills": [],    # スキル名のリスト
        "specialties": {},    # 区分 -> 件数
        "team_help_bonus_count": 0,
    }
    fav_set: set[str] = set(fav_berries or [])
    team_help = _team_help_bonus_count(member_ids)
    summary["team_help_bonus_count"] = team_help

    for mid in member_ids:
        if not mid:
            continue
        row = db.get_pokemon(mid)
        if row is None:
            continue
        m = dict(row)
        master = db.get_species_data(m["species_name"]) or {}

        b = expected_berry_per_day(
            m, master, get_play_ctx(),
            fav_berries=fav_set, field_bonus=field_bonus,
            team_help_bonus_count=team_help,
        )
        if b["name"]:
            ent = summary["berries"].setdefault(
                b["name"], {"count": 0.0, "energy": 0.0, "is_favorite": False}
            )
            ent["count"] += b["count"]
            ent["energy"] += b["energy"]
            ent["is_favorite"] = ent["is_favorite"] or b["is_favorite"]

        ing_kwargs = {"team_help_bonus_count": team_help}
        for name, n in expected_ingredients_per_day(m, master, get_play_ctx(), **ing_kwargs).items():
            summary["ingredients"][name] = summary["ingredients"].get(name, 0.0) + n

        summary["main_skills"].append(_main_skill_of(m, master) or "?")
        sp = master.get("specialty") or "?"
        summary["specialties"][sp] = summary["specialties"].get(sp, 0) + 1

    return summary


def _role_fulfillment(
    member_ids: list[int],
    role_targets: dict[str, int],
    scores_map: dict[int, dict[str, tuple[float, str] | None]],
) -> dict[str, tuple[int, int]]:
    """各役割について (現在数, 目標数) を返す。target>0 の役割のみ含む。"""
    out: dict[str, tuple[int, int]] = {}
    for role_key, target in role_targets.items():
        if target <= 0:
            continue
        count = sum(
            1 for mid in member_ids
            if mid in scores_map and scores_map[mid].get(role_key) is not None
        )
        out[role_key] = (count, target)
    return out


def _ingredient_chip(name: str, qty: float) -> str:
    """食材アイコン + ×N の inline HTML チップ。アイコンが無ければ名前にフォールバック。

    qty は整数なら "×N"、小数なら "×N.N" 表示。つなぎ料理の必要量・不足量どちらでも使える。
    """
    if qty == int(qty):
        qty_str = f"×{int(qty)}"
    else:
        qty_str = f"×{qty:.1f}"
    url = ingredient_icon_url(name)
    if url:
        return (
            f'<span style="display:inline-block; margin:0 6px 0 0; white-space:nowrap;" '
            f'title="{name}">'
            f'<img src="{url}" width="22" style="vertical-align:middle">'
            f'<span style="margin-left:2px; vertical-align:middle">{qty_str}</span>'
            f'</span>'
        )
    return f'<span style="margin-right:6px">{name}{qty_str}</span>'


def _recipe_base_energy(recipe: dict) -> int:
    """レシピの基準エナジー。Lv60 → Lv30 → Lv1 の順でフォールバック。

    新レシピ8件は Lv30 以降が null なので Lv1 値が使われる。
    どれも null なら 0（評価上はほぼ最低スコア）。
    """
    return int(
        (recipe.get("energy_lv60") or 0)
        or (recipe.get("energy_lv30") or 0)
        or (recipe.get("energy_lv1") or 0)
    )


def _main_recipe_recommendations(
    main_pool: list[dict],
    ingredients_per_day: dict[str, float],
    event_set: set[str],
) -> list[dict]:
    """主料理候補を 1日あたり期待エナジー降順で返す。

    daily_energy = pace × base_energy（dish_2x 週なら ×2）。pace=0 の候補は除外。
    """
    dish_mult = 2.0 if "dish_2x" in event_set else 1.0
    out: list[dict] = []
    for rec in main_pool:
        pace, bottleneck = _main_recipe_pace(rec, ingredients_per_day)
        if pace <= 0:
            continue
        base_e = _recipe_base_energy(rec)
        out.append({
            "recipe": rec,
            "pace": pace,
            "bottleneck": bottleneck,
            "base_energy": base_e,
            "daily_energy": base_e * pace * dish_mult,
        })
    out.sort(key=lambda x: -x["daily_energy"])
    return out


def _main_recipe_pace(
    recipe: dict,
    ingredients_per_day: dict[str, float],
) -> tuple[float, list[str]]:
    """主料理の1日作成可能回数と律速食材リストを返す。

    回数 = min(獲得量 / 必要量) for 各食材。律速食材は比率最小タイの全食材。
    """
    required = {ing["name"]: ing["count"] for ing in (recipe.get("ingredients") or [])}
    if not required:
        return 0.0, []
    ratios: list[tuple[float, str]] = []
    for name, need in required.items():
        if need <= 0:
            continue
        have = ingredients_per_day.get(name, 0.0)
        ratios.append((have / need, name))
    if not ratios:
        return 0.0, []
    min_ratio = min(r for r, _ in ratios)
    bottleneck = [name for r, name in ratios if r == min_ratio]
    return min_ratio, bottleneck


def _surplus_after_main(
    main_recipe: dict,
    main_pace: float,
    ingredients_per_day: dict[str, float],
) -> dict[str, float]:
    """主料理を main_pace で作る前提の各食材の余剰量/日。

    律速食材は実質0、それ以外は獲得量 - 主料理消費量。主料理に含まれない食材は全量余剰。
    """
    required = {ing["name"]: ing["count"] for ing in (main_recipe.get("ingredients") or [])}
    surplus: dict[str, float] = {}
    for name, have in ingredients_per_day.items():
        used = required.get(name, 0) * main_pace
        s = max(0.0, have - used)
        if s > 0:
            surplus[name] = s
    return surplus


def _sub_recipe_score(
    sub_recipe: dict,
    surplus: dict[str, float],
    main_bottleneck: set[str],
    sel_cat_keys: set[str],
    pot_capacity: int,
) -> tuple[float, dict]:
    """つなぎ料理候補のスコアと内訳。

    モード:
      - surplus: 余剰だけで 1回以上作れる（max_create >= 1）
      - stock: 余剰だけでは作れないが、不足が少なくストック消費で作れる（不足合計 ≤ 必要合計 ×50%）

    要素:
      - カテゴリ不一致は完全除外（sel_cat_keys 指定時）
      - 律速食材を消費するなら ×0.3 ペナルティ
      - 鍋容量超過なら ×0.5 ペナルティ
    """
    required = {ing["name"]: ing["count"] for ing in (sub_recipe.get("ingredients") or [])}
    if not required:
        return 0.0, {}

    cat = sub_recipe.get("category")
    if sel_cat_keys and cat not in sel_cat_keys:
        return 0.0, {}

    max_create = float("inf")
    for name, need in required.items():
        if need <= 0:
            continue
        have = surplus.get(name, 0.0)
        cap = have / need
        if cap < max_create:
            max_create = cap
    if max_create == float("inf"):
        max_create = 0.0

    total_required = float(sum(required.values()))
    shortage_items: dict[str, float] = {}
    for name, need in required.items():
        have = surplus.get(name, 0.0)
        if have < need:
            shortage_items[name] = need - have
    shortage_total = sum(shortage_items.values())

    consumes_bottleneck = bool(main_bottleneck & set(required.keys()))
    total_ingr = sub_recipe.get("total_ingredients")
    fits_pot = total_ingr is None or total_ingr <= pot_capacity

    base_energy = _recipe_base_energy(sub_recipe)

    if max_create >= 1.0:
        mode = "surplus"
        total_consumed = max_create * total_required
        # スコア = 1日あたり期待エナジー（=エナジー×作成回数）。
        # 再現可能性は max_create が大きいほど自動的に高評価になる。
        daily_energy = base_energy * max_create
        score = daily_energy
        progress = 1.0
    else:
        if total_required <= 0 or shortage_total / total_required > 0.5:
            return 0.0, {}
        mode = "stock"
        progress = 1.0 - (shortage_total / total_required)  # 0〜1
        # 余剰で max_create 回 + ストック消費で progress 充足分の作成。
        # 充足率が高い（=ちょっと足せば作れる）料理ほど期待値が高くなる。
        daily_energy = base_energy * (max_create + progress)
        score = daily_energy
        total_consumed = max_create * total_required

    if consumes_bottleneck:
        score *= 0.3
    if not fits_pot:
        score *= 0.5

    return score, {
        "mode": mode,
        "max_create": max_create,
        "total_consumed": total_consumed,
        "consumes_bottleneck": consumes_bottleneck,
        "fits_pot": fits_pot,
        "category": cat,
        "total_ingredients": total_ingr,
        "shortage_items": shortage_items,
        "shortage_total": shortage_total,
        "base_energy": base_energy,
        "daily_energy": daily_energy,
        "progress": progress,
    }


def _propose_sub_recipes(
    main_recipe: dict,
    surplus: dict[str, float],
    main_bottleneck: set[str],
    all_recipes: list[dict],
    sel_cat_keys: set[str],
    pot_capacity: int,
    *,
    top_n: int = 8,
    min_base_energy: int = 0,
) -> list[dict]:
    """つなぎ料理候補をスコア順に返す。

    min_base_energy: これ未満の `_recipe_base_energy` のレシピは候補化しない。
        単一食材で量産できるが1個あたりのエナジーが低い料理を弾きたい時に使う。0=全候補対象。
    """
    main_name = main_recipe.get("name")
    candidates: list[dict] = []
    for rec in all_recipes:
        if rec.get("name") == main_name:
            continue
        if not rec.get("ingredients"):
            continue
        if min_base_energy > 0 and _recipe_base_energy(rec) < min_base_energy:
            continue
        sc, info = _sub_recipe_score(
            rec, surplus, main_bottleneck, sel_cat_keys, pot_capacity
        )
        if sc <= 0:
            continue
        candidates.append({"recipe": rec, "score": sc, **info})
    candidates.sort(key=lambda x: -x["score"])
    return candidates[:top_n]


def _recipe_progress(
    ingredients_per_day: dict[str, float],
    recipe_names: list[str],
    all_recipes: list[dict],
) -> list[dict]:
    """候補レシピの達成日数を計算。律速食材で日数決定、不足食材は別途列挙。

    Returns: [{name, category, days(float|inf), required: dict, missing: dict}, ...]
    """
    progress: list[dict] = []
    for rname in recipe_names:
        rec = next((r for r in all_recipes if r["name"] == rname), None)
        if not rec:
            continue
        required = {ing["name"]: ing["count"] for ing in (rec.get("ingredients") or [])}
        if not required:
            continue
        days = 0.0
        missing: dict[str, float] = {}
        for ing_name, need in required.items():
            have = ingredients_per_day.get(ing_name, 0.0)
            if have <= 0:
                days = float("inf")
                missing[ing_name] = need
                continue
            d = need / have
            if d > days:
                days = d
        progress.append({
            "name": rname,
            "category": rec.get("category"),
            "required": required,
            "days": days,
            "missing": missing,
        })
    progress.sort(key=lambda x: (x["days"] == float("inf"), x["days"]))
    return progress

