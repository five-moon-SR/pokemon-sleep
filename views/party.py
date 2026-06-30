"""パーティー編成ページ。

4つのブロック構成:
  ① 今週の前提（フィールド／料理カテゴリ／候補レシピ／方針タグ）
  ② 候補ポケモン一覧（スコア順）
  ③ 編成中のパーティ（5枠＋総合能力サマリ＋警告）
  ④ パーティの保存・読込・削除

スコア係数は仮置き。後でいろんなサイトを参考にしながら齋藤さんと調整する想定。
"""

from __future__ import annotations

import streamlit as st

import db
from image_utils import berry_icon_url, ingredient_icon_url
from utils.food_expectation import expected_berry_per_day, expected_ingredients_per_day
from utils.play_context import load_play_context

_PLAY_CTX = load_play_context()

st.title("⚔ パーティー編成")
st.caption("今週の前提 → 候補ポケモンスコア → 5体選択 → 保存。スコア係数は暫定。")


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
        p, master, _PLAY_CTX, fav_berries=fav_set, field_bonus=field_bonus
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
    expected = expected_ingredients_per_day(p, master, _PLAY_CTX)
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
            m, master, _PLAY_CTX,
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
        for name, n in expected_ingredients_per_day(m, master, _PLAY_CTX, **ing_kwargs).items():
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


# -------------- セッション状態 --------------

db.init_db()
ss = st.session_state
ss.setdefault("party_member_ids", [])  # list[int]
ss.setdefault("party_loaded_id", None)


# 読込ボタンは ④ で押下されるが、その時点で ① の widget は既に描画済みのため、
# widget の key と同名の session_state を直接書き換えると Streamlit がエラーを出す。
# そこで読込ボタンは「次回rerun時に適用する dict」を _pending_load に積み、
# ここ（widget 描画前）で session_state に流し込む pending パターンを使う。
if ss.get("_pending_load") is not None:
    pt = ss["_pending_load"]
    ss.party_member_ids = list(pt.get("member_ids") or [])
    ss.party_loaded_id = pt["id"]
    ss["p_field"] = pt.get("field_name") or "（未選択）"
    ss["p_recipe_cats"] = list(pt.get("recipe_categories") or [])
    ss["p_recipes"] = list(pt.get("candidate_recipes") or [])
    ss["p_random_berries"] = list(pt.get("random_field_berries") or [])
    ss["p_role_preset"] = "✏ カスタム"
    for role_key in ROLE_LABELS:
        ss[f"p_role_{role_key}"] = (pt.get("role_targets") or {}).get(role_key, 0)
    ss["p_events"] = list(pt.get("event_bonuses") or [])
    ss["p_save_name"] = pt.get("name") or ""
    ss["p_save_note"] = pt.get("note") or ""
    if pt.get("main_recipe"):
        ss["p_main_recipe"] = pt["main_recipe"]
    ss["_just_loaded_name"] = pt.get("name") or ""
    ss["_pending_load"] = None


# -------------- ① 今週の前提 --------------

with st.container(border=True):
    st.subheader("① 今週の前提")

    fields = db.list_all_field_records()
    field_options = ["（未選択）"] + [f["name"] for f in fields]
    sel_field_name = st.selectbox("フィールド", field_options, key="p_field")
    sel_field = next((f for f in fields if f["name"] == sel_field_name), None)

    fav_berries: list[str] = []
    if sel_field:
        if sel_field.get("favorite_berries_random"):
            st.caption(
                "🎲 ランダム好物フィールド：週の始まりに3種が決まるので、今週の3種を選んでください。"
            )
            all_berry_names = [b["name"] for b in db.list_all_berry_records()]
            picked = st.multiselect(
                "今週の好みきのみ（最大3種）",
                all_berry_names,
                max_selections=3,
                key="p_random_berries",
            )
            fav_berries = list(picked)
            if fav_berries:
                cols = st.columns(len(fav_berries) + 1)
                cols[0].caption("適用中:")
                for i, name in enumerate(fav_berries):
                    url = berry_icon_url(name)
                    if url:
                        cols[i + 1].markdown(
                            f'<img src="{url}" width="20" style="vertical-align:middle">'
                            f' {name}',
                            unsafe_allow_html=True,
                        )
                    else:
                        cols[i + 1].caption(name)
        else:
            fav_berries = [b["name"] for b in (sel_field.get("favorite_berries") or [])]
            if fav_berries:
                cols = st.columns(len(fav_berries) + 1)
                cols[0].caption("好みのきのみ:")
                for i, name in enumerate(fav_berries):
                    url = berry_icon_url(name)
                    label = f"{name}"
                    if url:
                        cols[i + 1].markdown(
                            f'<img src="{url}" width="20" style="vertical-align:middle">'
                            f' {label}',
                            unsafe_allow_html=True,
                        )
                    else:
                        cols[i + 1].caption(label)

    sel_categories = st.multiselect(
        "作る料理カテゴリ",
        list(RECIPE_CATEGORY_LABELS.values()),
        key="p_recipe_cats",
    )

    all_recipes = db.list_all_recipe_records()
    if sel_categories:
        cat_keys = {k for k, v in RECIPE_CATEGORY_LABELS.items() if v in sel_categories}
        recipe_pool = [r for r in all_recipes if r.get("category") in cat_keys]
    else:
        recipe_pool = all_recipes
    recipe_pool = [r for r in recipe_pool if r.get("ingredients")]
    sel_recipe_names = st.multiselect(
        "候補レシピ（必要食材を ② のスコアに反映）",
        [r["name"] for r in recipe_pool],
        key="p_recipes",
    )

    needed_ings: set[str] = set()
    for rname in sel_recipe_names:
        rec = next((r for r in all_recipes if r["name"] == rname), None)
        if rec:
            for ing in rec.get("ingredients") or []:
                needed_ings.add(ing["name"])

    if needed_ings:
        cols = st.columns(min(len(needed_ings), 6) + 1)
        cols[0].caption("必要食材:")
        for i, name in enumerate(sorted(needed_ings)):
            url = ingredient_icon_url(name)
            slot = cols[(i % 6) + 1]
            if url:
                slot.markdown(
                    f'<img src="{url}" width="20" style="vertical-align:middle"> {name}',
                    unsafe_allow_html=True,
                )
            else:
                slot.caption(name)

    st.divider()
    st.markdown("##### 🎯 役割×目標人数")
    preset_cols = st.columns([3, 1])
    with preset_cols[0]:
        sel_preset = st.selectbox(
            "プリセット",
            list(ROLE_PRESETS.keys()),
            index=1,  # ⚖ バランス
            key="p_role_preset",
            label_visibility="collapsed",
        )
    with preset_cols[1]:
        apply_preset = st.button(
            "📋 適用",
            key="p_preset_apply",
            use_container_width=True,
            disabled=ROLE_PRESETS[sel_preset] is None,
            help="プリセットの値を各スライダーに反映します。",
        )

    if apply_preset and ROLE_PRESETS[sel_preset] is not None:
        for role_key, count in ROLE_PRESETS[sel_preset].items():
            ss[f"p_role_{role_key}"] = count
        st.rerun()

    role_target_cols = st.columns(5)
    role_targets: dict[str, int] = {}
    for i, (role_key, label) in enumerate(ROLE_LABELS.items()):
        with role_target_cols[i]:
            role_targets[role_key] = st.slider(
                label, min_value=0, max_value=5, value=0, step=1,
                key=f"p_role_{role_key}",
            )
    total_target = sum(role_targets.values())
    if total_target > 5:
        st.caption(f"⚠ 目標合計 {total_target}/5 超過")
    else:
        st.caption(f"目標合計: {total_target}/5")

    st.divider()
    sel_event_keys = st.multiselect(
        "✨ 今週のイベント補正（複数可。空＝補正なし週）",
        list(EVENT_BONUSES.keys()),
        format_func=lambda k: EVENT_BONUSES[k],
        key="p_events",
    )

fav_set = set(fav_berries)
event_set = set(sel_event_keys)


# -------------- ② 候補ポケモン（役割別） --------------

def _render_role_candidates(
    role_key: str,
    owned_rows: list[dict],
    scores_map: dict[int, dict[str, tuple[float, str] | None]],
    ss,
) -> None:
    candidates = [
        (scores_map[p["id"]][role_key], p)
        for p in owned_rows
        if scores_map[p["id"]][role_key] is not None
    ]
    if not candidates:
        st.info(f"{ROLE_LABELS[role_key]} に該当する所持ポケモンはいません。")
        return
    candidates.sort(key=lambda x: (-x[0][0], x[1]["species_name"]))

    top_n_options = [n for n in (10, 20, 30, len(candidates)) if n <= len(candidates)]
    if not top_n_options:
        top_n_options = [len(candidates)]
    with st.columns([1, 4])[0]:
        top_n = st.selectbox(
            "表示件数", top_n_options, key=f"p_role_topn_{role_key}",
        )

    for (score, breakdown), p in candidates[:top_n]:
        in_party = p["id"] in ss.party_member_ids
        full = len(ss.party_member_ids) >= 5
        master = db.get_species_data(p["species_name"]) or {}

        cols = st.columns([0.6, 2.4, 0.7, 3, 0.9])
        burl = berry_icon_url((master.get("berry") or {}).get("name"))
        cols[0].markdown(
            f'<img src="{burl}" width="32">' if burl else "",
            unsafe_allow_html=True,
        )
        label = (
            f'**{p.get("nickname") or p["species_name"]}** '
            f'({p["species_name"]}) Lv{_effective_level(p)} '
            f'/ {master.get("specialty") or "?"}'
        )
        cols[1].markdown(label)
        cols[2].markdown(f"**{score:.0f}**")
        cols[3].caption(breakdown)
        btn_label = "✓編成中" if in_party else "追加"
        if cols[4].button(
            btn_label,
            key=f"add_{role_key}_{p['id']}",
            disabled=in_party or full,
            use_container_width=True,
        ):
            ss.party_member_ids.append(p["id"])
            st.rerun()


# ② と ③ で共通利用するため、所持ポケと役割スコアを先に計算
owned_rows: list[dict] = [dict(r) for r in db.list_pokemon()]
scores_map: dict[int, dict[str, tuple[float, str] | None]] = {}
for p in owned_rows:
    master = db.get_species_data(p["species_name"]) or {}
    scores_map[p["id"]] = compute_role_scores(
        p, master, fav_set, event_set, needed_ings
    )

with st.container(border=True):
    st.subheader("② 候補ポケモン（役割別）")
    st.caption(
        "①で設定した役割の目標数 / イベント補正 / 候補レシピが各タブのスコアに反映されます。"
    )

    if not owned_rows:
        st.info("所持ポケモンがいません。先に「個体登録」から追加してください。")
    else:
        roles_with_target = [k for k in ROLE_LABELS if role_targets.get(k, 0) > 0]
        roles_to_show = roles_with_target or list(ROLE_LABELS.keys())

        tab_labels = []
        for k in roles_to_show:
            tgt = role_targets.get(k, 0)
            tab_labels.append(
                f"{ROLE_LABELS[k]}" + (f" (目標{tgt})" if tgt > 0 else "")
            )

        tabs = st.tabs(tab_labels)
        for tab, role_key in zip(tabs, roles_to_show):
            with tab:
                _render_role_candidates(role_key, owned_rows, scores_map, ss)


# -------------- ③ 編成中のパーティ --------------

with st.container(border=True):
    st.subheader(f"③ 編成中のパーティ（{len(ss.party_member_ids)}/5）")

    if not ss.party_member_ids:
        st.caption("まだ未編成。② から「追加」してください。")
    else:
        slot_cols = st.columns(5)
        for i in range(5):
            with slot_cols[i]:
                if i < len(ss.party_member_ids):
                    mid = ss.party_member_ids[i]
                    row = db.get_pokemon(mid)
                    if row is None:
                        st.warning("削除済み")
                        if st.button("外す", key=f"rm_{i}_missing"):
                            ss.party_member_ids.pop(i)
                            st.rerun()
                        continue
                    m = dict(row)
                    master = db.get_species_data(m["species_name"]) or {}
                    burl = berry_icon_url((master.get("berry") or {}).get("name"))
                    if burl:
                        st.markdown(
                            f'<img src="{burl}" width="40">', unsafe_allow_html=True
                        )
                    st.markdown(
                        f"**{m.get('nickname') or m['species_name']}**  \n"
                        f"{m['species_name']}  \nLv{_effective_level(m)}"
                    )
                    st.caption(_main_skill_of(m, master) or "?")
                    if st.button("外す", key=f"rm_{i}"):
                        ss.party_member_ids.pop(i)
                        st.rerun()
                else:
                    st.caption("（空き枠）")

    if ss.party_member_ids:
        summary = party_summary(
            ss.party_member_ids, fav_berries=fav_set, field_bonus=0.0
        )

        team_help = summary["team_help_bonus_count"]
        if team_help > 0:
            st.info(
                f"🤝 **team-buff**: おてつだいボーナス装着 {team_help} 人 "
                f"→ 全員のスピード ×{1.0 + 0.05 * team_help:.2f}（食材・きのみ獲得に反映済）"
            )

        st.markdown("**🍓 きのみ獲得（1日あたり個数 ／ エナジー）**")
        if summary["berries"]:
            cols = st.columns(min(len(summary["berries"]), 5))
            sorted_berries = sorted(
                summary["berries"].items(), key=lambda x: -x[1]["energy"]
            )
            for i, (name, data) in enumerate(sorted_berries):
                url = berry_icon_url(name)
                fav_mark = " ⭐" if data["is_favorite"] else ""
                count_text = f"×{data['count']:.1f}/日"
                energy_text = f"{int(round(data['energy'])):,} en"
                with cols[i % len(cols)]:
                    if url:
                        st.markdown(
                            f'<img src="{url}" width="22"> {name}{fav_mark}<br>'
                            f'{count_text} ／ {energy_text}',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(f"{name}{fav_mark} {count_text} ／ {energy_text}")

        st.markdown("**🥕 食材1日獲得期待値（性格/サブ/Lv/リボン補正込み）**")
        if summary["ingredients"]:
            cols = st.columns(min(len(summary["ingredients"]), 5))
            for i, (name, qty) in enumerate(sorted(summary["ingredients"].items(), key=lambda x: -x[1])):
                url = ingredient_icon_url(name)
                with cols[i % len(cols)]:
                    if url:
                        st.markdown(
                            f'<img src="{url}" width="22"> {name} ×{qty:.1f}/日',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(f"{name} ×{qty:.1f}/日")
        else:
            st.caption("—")

        st.markdown("**🎯 メインスキル構成**")
        skill_text = "、".join(summary["main_skills"]) if summary["main_skills"] else "—"
        st.write(skill_text)

        warnings: list[str] = []

        fulfillment = _role_fulfillment(ss.party_member_ids, role_targets, scores_map)
        if fulfillment:
            st.markdown("**🎯 役割充足度**")
            for role_key, (curr, tgt) in fulfillment.items():
                ratio = min(curr / tgt, 1.0) if tgt > 0 else 0.0
                icon = "✅" if curr >= tgt else "🔸"
                fcols = st.columns([3, 1])
                fcols[0].progress(ratio)
                fcols[1].markdown(f"{icon} **{ROLE_LABELS[role_key]}**: {curr} / {tgt}")
                if curr < tgt:
                    warnings.append(
                        f"{ROLE_LABELS[role_key]} 目標 {tgt} に対して現在 {curr} 体"
                    )

        if sel_recipe_names:
            st.markdown("**🍳 レシピ達成進捗**（1日獲得期待値ベース・律速食材で日数決定）")
            for prog in _recipe_progress(summary["ingredients"], sel_recipe_names, all_recipes):
                req_text = " / ".join(f"{k}×{v}" for k, v in prog["required"].items())
                if prog["days"] == float("inf"):
                    miss_text = " / ".join(
                        f"{k}×{v:g}" for k, v in prog["missing"].items()
                    )
                    st.warning(
                        f"❌ **{prog['name']}** — 不足食材: {miss_text}（必要: {req_text}）"
                    )
                else:
                    d = prog["days"]
                    day_text = (
                        f"{d:.1f} 日"
                        if d < 7
                        else f"{d/7:.1f} 週間（{d:.0f} 日）"
                    )
                    st.write(
                        f"🍳 **{prog['name']}** — 約 **{day_text}** で完成（必要: {req_text}）"
                    )

        st.divider()
        st.markdown("##### 🍽 主料理＋つなぎ料理提案")

        # 主料理プール: ①の候補レシピがあればそこから、なければカテゴリ絞り、それもなければ全レシピ
        if sel_recipe_names:
            main_pool = [r for r in all_recipes if r["name"] in sel_recipe_names]
            pool_label = "①の候補レシピ"
        elif sel_categories:
            cat_keys = {k for k, v in RECIPE_CATEGORY_LABELS.items() if v in sel_categories}
            main_pool = [
                r for r in all_recipes
                if r.get("category") in cat_keys and r.get("ingredients")
            ]
            pool_label = "①の料理カテゴリ"
        else:
            main_pool = [r for r in all_recipes if r.get("ingredients")]
            pool_label = "全レシピ"

        if not main_pool:
            st.caption("主料理候補がありません。①でレシピかカテゴリを選んでください。")
        else:
            recs = _main_recipe_recommendations(
                main_pool, summary["ingredients"], event_set
            )

            if not recs:
                st.caption(f"主料理プール: {pool_label}（{len(main_pool)}件）")
                st.warning(
                    "現在の編成では作成可能な主料理候補がありません。"
                    "律速食材の獲得手段を編成してください。"
                )
            else:
                dish_2x_note = " 🍳2x週" if "dish_2x" in event_set else ""
                st.caption(
                    f"主料理プール: {pool_label}（{len(main_pool)}件、作成可能 {len(recs)}件）"
                    f"／ 1日あたり期待エナジー降順{dish_2x_note}"
                )

                # 現在の選択。未設定 or 候補外 ならトップを採用。
                rec_names = [r["recipe"]["name"] for r in recs]
                if ss.get("p_main_recipe") not in rec_names:
                    ss["p_main_recipe"] = rec_names[0]
                current = ss["p_main_recipe"]

                def _render_main_row(rank: int, r: dict) -> None:
                    rec = r["recipe"]
                    is_current = rec["name"] == current
                    cols = st.columns([0.4, 3, 2.2, 1.4, 0.9])
                    cols[0].markdown(f"**#{rank}**")
                    cat_label = RECIPE_CATEGORY_LABELS.get(
                        rec.get("category"), rec.get("category") or ""
                    )
                    cols[1].markdown(f"**{rec['name']}**  \n_{cat_label}_")
                    cols[2].markdown(
                        f"<b>{int(round(r['daily_energy'])):,}</b> en/日<br>"
                        f"<span style='color:#666; font-size:0.9em'>"
                        f"{int(r['base_energy']):,}en × {r['pace']:.2f}回</span>",
                        unsafe_allow_html=True,
                    )
                    cols[3].caption(
                        "🔻 " + " / ".join(r["bottleneck"]) if r["bottleneck"] else "—"
                    )
                    btn_label = "✓選択中" if is_current else "選択"
                    if cols[4].button(
                        btn_label,
                        key=f"p_main_pick_{rec['name']}",
                        disabled=is_current,
                        use_container_width=True,
                    ):
                        ss["p_main_recipe"] = rec["name"]
                        st.rerun()

                show_top = 5
                for rank, r in enumerate(recs[:show_top], 1):
                    _render_main_row(rank, r)

                if len(recs) > show_top:
                    with st.expander(
                        f"残り {len(recs) - show_top} 件を表示", expanded=False
                    ):
                        for rank, r in enumerate(recs[show_top:], show_top + 1):
                            _render_main_row(rank, r)

                sel = next(r for r in recs if r["recipe"]["name"] == current)
                main_recipe = sel["recipe"]
                pace = sel["pace"]
                bottleneck = sel["bottleneck"]

                mc1, mc2, mc3 = st.columns([1, 1, 2])
                mc1.metric("作成可能 / 日", f"{pace:.2f} 回")
                mc2.metric("完成までの日数", f"{1/pace:.1f} 日")
                mc3.metric(
                    "🔻 律速食材",
                    " / ".join(bottleneck) if bottleneck else "—",
                )

                surplus = _surplus_after_main(main_recipe, pace, summary["ingredients"])

                with st.expander(f"📦 余剰食材（主料理を {pace:.2f}回/日 で作る前提）", expanded=False):
                    if surplus:
                        cols = st.columns(min(len(surplus), 5))
                        for i, (name, qty) in enumerate(
                            sorted(surplus.items(), key=lambda x: -x[1])
                        ):
                            url = ingredient_icon_url(name)
                            with cols[i % len(cols)]:
                                if url:
                                    st.markdown(
                                        f'<img src="{url}" width="22"> {name} ×{qty:.1f}/日',
                                        unsafe_allow_html=True,
                                    )
                                else:
                                    st.markdown(f"{name} ×{qty:.1f}/日")
                    else:
                        st.caption("—")

                st.markdown("**🍳 つなぎ料理候補**（余剰食材で作れる別レシピ・スコア順）")
                filter_cols = st.columns([1, 3])
                with filter_cols[0]:
                    sub_min_energy = st.number_input(
                        "🚫 最小1個エナジー",
                        min_value=0,
                        max_value=10000,
                        value=0,
                        step=500,
                        key="p_sub_min_energy",
                        help=(
                            "これ未満の base エナジーのレシピは候補から除外。"
                            "単一食材で量産可能だが1個あたりエナジーが低い料理を弾きたい時に。"
                            "0 で全候補表示。"
                        ),
                    )
                sel_cat_keys = {
                    k for k, v in RECIPE_CATEGORY_LABELS.items() if v in sel_categories
                }
                pot_capacity = _PLAY_CTX.pot_capacity
                sub_candidates = _propose_sub_recipes(
                    main_recipe, surplus, set(bottleneck),
                    all_recipes, sel_cat_keys, pot_capacity,
                    top_n=8, min_base_energy=int(sub_min_energy),
                )
                if not sub_candidates:
                    st.caption("つなぎ料理候補なし。余剰食材が少ないか、必要食材が揃いません。")
                else:
                    st.caption(
                        "🍳 = 余剰だけで作れる ／ 🥄 = ストック前提（先週の残りなどで補う）"
                        " ／ 並び順は 1日あたり期待エナジー降順"
                    )
                    for cand in sub_candidates:
                        rec = cand["recipe"]
                        badges = []
                        if cand["consumes_bottleneck"]:
                            badges.append("⚠律速食材使用")
                        if not cand["fits_pot"]:
                            badges.append(
                                f"❌鍋超過({cand['total_ingredients']}>{pot_capacity})"
                            )
                        badge_text = " ".join(badges)

                        req_chips = "".join(
                            _ingredient_chip(ing["name"], ing["count"])
                            for ing in (rec.get("ingredients") or [])
                        )

                        base_e = cand.get("base_energy", 0)
                        daily_e = cand.get("daily_energy", 0)
                        if cand["mode"] == "surplus":
                            energy_text = (
                                f"{int(base_e):,}en × {cand['max_create']:.2f}回 "
                                f"≒ <b>{int(daily_e):,} en/日</b>"
                            )
                            head_line = f"🍳 <b>{rec['name']}</b> — {energy_text}"
                            extra = ""
                        else:
                            shortage_chips = "".join(
                                _ingredient_chip(n, s)
                                for n, s in sorted(
                                    cand["shortage_items"].items(),
                                    key=lambda x: -x[1],
                                )
                            )
                            energy_text = (
                                f"1個 {int(base_e):,}en"
                                f"（充足率 {cand['progress']*100:.0f}%）"
                            )
                            head_line = f"🥄 <b>{rec['name']}</b> — {energy_text}"
                            extra = f"<div style='margin-left:1.5em'>あと {shortage_chips}で作れる</div>"
                        if badge_text:
                            head_line += f" <span style='color:#c66'>{badge_text}</span>"

                        st.markdown(
                            f"<div style='margin:6px 0'>{head_line}</div>"
                            f"{extra}"
                            f"<div style='margin-left:1.5em; color:#666; font-size:0.9em'>"
                            f"必要: {req_chips}</div>",
                            unsafe_allow_html=True,
                        )

        if warnings:
            for w in warnings:
                st.warning(w)
        elif fulfillment:
            st.success("役割の条件をクリア")


# -------------- ④ 保存・読込 --------------

with st.container(border=True):
    st.subheader("④ 保存・読込")

    if ss.get("_just_loaded_name"):
        st.success(f"読み込みました: {ss['_just_loaded_name']}")
        ss["_just_loaded_name"] = None

    save_cols = st.columns([3, 2, 1])
    with save_cols[0]:
        party_name = st.text_input(
            "パーティ名",
            value=f"{sel_field_name if sel_field else ''}編成"
            if sel_field
            else "",
            key="p_save_name",
        )
    with save_cols[1]:
        note = st.text_input("メモ（任意）", key="p_save_note")
    with save_cols[2]:
        st.write("")
        st.write("")
        if st.button(
            "💾 保存",
            disabled=not party_name or not ss.party_member_ids,
            use_container_width=True,
        ):
            payload = {
                "name": party_name,
                "field_name": sel_field_name if sel_field else None,
                "recipe_categories": sel_categories,
                "candidate_recipes": sel_recipe_names,
                "member_ids": ss.party_member_ids,
                "note": note,
                "random_field_berries": fav_berries
                if sel_field and sel_field.get("favorite_berries_random")
                else [],
                "role_targets": role_targets,
                "event_bonuses": list(event_set),
                "main_recipe": ss.get("p_main_recipe") or None,
            }
            if ss.party_loaded_id:
                db.update_party(ss.party_loaded_id, **payload)
                st.success(f"上書き保存しました（id={ss.party_loaded_id}）")
            else:
                new_id = db.insert_party(payload)
                ss.party_loaded_id = new_id
                st.success(f"新規保存しました（id={new_id}）")
            st.rerun()

    st.divider()
    parties = db.list_parties()
    if not parties:
        st.caption("まだ保存されたパーティはありません。")
    else:
        for pt in parties:
            cols = st.columns([3, 2, 2, 1, 1])
            cols[0].markdown(
                f"**{pt['name']}** "
                f"({pt.get('field_name') or '—'})"
            )
            cols[1].caption(
                "／".join(pt.get("policy_tags") or []) or "—"
            )
            cols[2].caption(f"{len(pt.get('member_ids') or [])}体・{pt.get('updated_at','')[:16]}")
            if cols[3].button("読込", key=f"load_{pt['id']}"):
                # widget 描画後の直接書き換えは Streamlit が拒否するため、
                # ここでは _pending_load にだけ積んで rerun。次回描画の冒頭で適用する。
                ss["_pending_load"] = pt
                st.rerun()
            if cols[4].button("削除", key=f"del_{pt['id']}"):
                db.delete_party(pt["id"])
                if ss.party_loaded_id == pt["id"]:
                    ss.party_loaded_id = None
                st.rerun()

    if ss.party_member_ids or ss.party_loaded_id:
        if st.button("🆕 新規編成（クリア）"):
            ss.party_member_ids = []
            ss.party_loaded_id = None
            st.rerun()
