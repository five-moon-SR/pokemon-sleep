"""🥕 食材戦略ページ。

目的「今週の料理の穴を埋める」（ui_design_policy.md 段5）。
最上部で狙いのレシピを決め、直下 hero で全体像、以降は4モードで切替：
  🕳 料理の穴  — 狙いレシピの充足度と穴食材＋穴ごとの「次の一手」（初期表示）
  🌱 育成する  — 育成優先度ランキング
  🎯 捕まえる  — 捕獲優先度ランキング
  📚 食材索引  — 19食材×担当マトリクス＋多能な主力（参考情報を隔離）
（きのみ充足度は「きのみ戦略」ページに分離）
"""

from __future__ import annotations

import streamlit as st

import db
from image_utils import RECIPE_ICON_DIR, icon_data_url, ingredient_icon_url
from ui import components as c
from ui.widgets import pokemon_popover_row, pokemon_status_popover
from utils.party_logic import _recipe_base_energy, get_play_ctx
from utils.community_tier import recommended_composition
from utils.ingredient_coverage import (
    build_ingredient_index,
    catch_priorities,
    catch_priorities_general,
    load_target_recipes,
    recipe_coverage,
    save_target_recipes,
    team_supply,
    training_priorities,
    versatile_mains,
)

st.html(c.page_banner("食材戦略", "bag", icon="🥕"))
st.caption("狙いの料理から逆算して、食材の穴・育成すべき個体・捕まえるべき種族を洗い出す。")

db.init_db()
owned = [dict(r) for r in db.list_pokemon()]
owned_by_id = {p["id"]: p for p in owned}

if not owned:
    st.html(c.empty_state("所持ポケモンがいません。先に「個体登録」から追加してください。"))
    st.stop()


# ============ ① 料理カテゴリ & 狙いのレシピ ============

# recipe.json の category（curry_stew / salad / drink_dessert）→ 日本語ラベル
_CATEGORY_LABELS = {
    "curry_stew": "🍛 カレー・シチュー",
    "salad": "🥗 サラダ",
    "drink_dessert": "🍰 デザート・ドリンク",
}

all_recipes = [r for r in db.list_all_recipe_records() if r.get("ingredients")]
# 基礎エネルギー(Lv60基準)降順（弱い料理は下に）。
_recipe_energy = {r["name"]: _recipe_base_energy(r) for r in all_recipes}
all_recipes.sort(key=lambda r: -_recipe_energy[r["name"]])
_recipe_by_name = {r["name"]: r for r in all_recipes}
_recipe_total_map = {r["name"]: int(r.get("total_ingredients") or 0) for r in all_recipes}
_recipe_cat_map = {r["name"]: r.get("category") for r in all_recipes}

st.html(c.section_header("料理カテゴリ"))
cat_pick = st.pills(
    "料理カテゴリ", ["🍲 全部", *_CATEGORY_LABELS.values()], default="🍲 全部",
    key="ing_category", label_visibility="collapsed",
) or "🍲 全部"

st.html(c.section_header("狙いのレシピ"))

# カテゴリで選択肢を絞る（他カテゴリの選択はKVに保持したまま）
_cat_opts = [
    r["name"] for r in all_recipes
    if cat_pick == "🍲 全部" or _CATEGORY_LABELS.get(r.get("category")) == cat_pick
]

saved_targets = load_target_recipes()
_pot_cap = get_play_ctx().pot_capacity


def _opt_label(n: str) -> str:
    total = _recipe_total_map.get(n, 0)
    en = _recipe_energy.get(n, 0)
    en_str = f"{en / 1000:.0f}k" if en >= 1000 else str(en)
    # 鍋不足の警告は先頭に出す（右端で切れても見えるように）
    prefix = f"🍳✕{total - _pot_cap} " if total > _pot_cap else ""
    return f"{prefix}{n}｜{en_str}en・食材{total}"


picked_in_cat = st.multiselect(
    "作りたい料理（基礎エナジー降順・保存され次回も引き継がれる・🍳✕=鍋容量不足）",
    _cat_opts,
    default=[n for n in saved_targets if n in _cat_opts],
    format_func=_opt_label,
    key="ing_targets",
)
# 他カテゴリの保存選択を保持しつつマージ
_other = [n for n in saved_targets if n not in _cat_opts]
targets = _other + picked_in_cat
if set(targets) != set(saved_targets):
    save_target_recipes(targets)

supply = team_supply(owned)
index = build_ingredient_index(owned)

# 狙いレシピの充足度は複数モードで使うので一度だけ計算
covs = recipe_coverage(targets, supply) if targets else []
# 穴食材（狙いレシピ横断でユニーク）
hole_ings = sorted({h for cov in covs for h in cov.holes})
total_pace = sum(cov.pace for cov in covs)


# ============ hero（今の答え：全体像） ============

if targets:
    st.html(c.stat_tiles([
        c.stat_tile("狙い料理", f"{len(targets)}", sub="品"),
        c.stat_tile("不足食材", f"{len(hole_ings)}", sub="律速の穴"),
        c.stat_tile("合計ペース", f"{total_pace:.1f}", sub="回/日"),
    ]))
else:
    st.info("上で狙いのレシピを選ぶと、不足食材・育成・捕獲の優先度が出ます。")


# ============ モード切替（segmented） ============

_MODE_HOLE = "🕳 料理の穴"
_MODE_TRAIN = "🌱 育成する"
_MODE_CATCH = "🎯 捕まえる"
_MODE_INDEX = "📚 食材索引"

if "ing_mode" not in st.session_state:
    st.session_state["ing_mode"] = _MODE_HOLE


def _goto(mode: str) -> None:
    """穴食材の「次の一手」ボタンからモードを切り替える。"""
    st.session_state["ing_mode"] = mode


# key が session_state に既にあるため default は渡さない（初期値は session_state 主導）
mode = st.segmented_control(
    "表示モード",
    options=[_MODE_HOLE, _MODE_TRAIN, _MODE_CATCH, _MODE_INDEX],
    key="ing_mode",
    label_visibility="collapsed",
) or _MODE_HOLE


# ============ 🕳 料理の穴（初期表示：狙いレシピの充足度＋次の一手） ============

if mode == _MODE_HOLE:
    if not targets:
        st.html(c.empty_state("狙いのレシピを選ぶと、食材ごとの充足度と穴が表示されます。"))
    else:
        for cov in covs:
            # 現状の鍋容量で作れるか（不足なら赤字＋不足量）
            _pot = _pot_cap
            _total_need = int(cov.recipe.get("total_ingredients") or 0)
            _fits = _total_need <= _pot
            _short = _total_need - _pot
            with st.container(border=True):
                head = st.columns([3, 2])
                _rurl = icon_data_url(str(RECIPE_ICON_DIR), cov.recipe.get("icon"))
                _name_color = "" if _fits else " style='color:#D95A44;'"
                head[0].markdown(
                    (f'<img src="{_rurl}" width="34" style="vertical-align:middle; margin-right:6px;">' if _rurl else "")
                    + f"<b{_name_color}>{cov.recipe['name']}</b>"
                    + ("" if _fits else " 🍳✕"),
                    unsafe_allow_html=True,
                )
                head[1].caption(
                    f"作成ペース {cov.pace:.2f}回/日 ・ 期待 {cov.daily_energy:,.0f} en/日"
                )

                _need_list = "、".join(
                    f"{i['name']}×{int(i['count'])}" for i in cov.recipe.get("ingredients") or []
                )
                st.markdown(
                    f"必要食材: {_need_list}　→　**総量 {_total_need}個** ／ 鍋容量 {_pot}　"
                    + (f"<span style='color:#17AE54; font-weight:700;'>✅ 現状の鍋で作れる</span>"
                       if _fits else
                       f"<span style='color:#D95A44; font-weight:700;'>🍳 鍋容量不足：あと {_short}個（鍋を{_total_need}以上に）</span>"),
                    unsafe_allow_html=True,
                )

                for ing_name, (need, have) in cov.per_ingredient.items():
                    ratio = have / need if need > 0 else 0.0
                    is_hole = ing_name in cov.holes
                    cols = st.columns([2, 3, 2])
                    cols[0].html(c.ingredient_chip(ing_name, f"{have:.1f}/{need:.0f}"))
                    cols[1].html(c.meter(ratio))
                    cols[2].caption(("🕳 律速" if is_hole else "") + f" ×{ratio:.2f}")

        # ---- 穴食材ごとの「次の一手」 ----
        st.html(c.section_header("穴を埋める次の一手"))
        if not hole_ings:
            st.success("狙いレシピに律速の穴なし。今の編成で回せる。")
        else:
            st.caption("不足食材ごとに、育成で伸ばせる所持個体がいるか／捕獲で埋めるかを提案。")
            for h in hole_ings:
                providers = index.get(h, [])
                # 枠は持つが今は供給ゼロ＝育成/選択変更で伸ばせる候補
                idle = [p for p in providers if p.per_day_now <= 0]
                _iurl = ingredient_icon_url(h)
                _icon = (
                    f'<img src="{_iurl}" width="18" loading="lazy" '
                    f'style="vertical-align:middle; margin-right:5px;">' if _iurl else ""
                )
                with st.container(border=True):
                    hint = (
                        f"枠を持つ所持個体が{len(idle)}体（育成・食材選択で供給を起こせる）"
                        if idle else "所持個体に枠なし → 捕獲で埋めるのが早い"
                    )
                    st.html(
                        f'<div style="font-size:0.92rem;">{_icon}<b>{h}</b>'
                        f'<span style="color:#7a7a7a;"> — {hint}</span></div>'
                    )
                    btns = st.columns(2)
                    btns[0].button(
                        "🌱 育成対象を見る", key=f"hole_train_{h}",
                        on_click=_goto, args=(_MODE_TRAIN,),
                        use_container_width=True, disabled=not idle,
                    )
                    btns[1].button(
                        "🎯 捕獲候補を見る", key=f"hole_catch_{h}",
                        on_click=_goto, args=(_MODE_CATCH,),
                        use_container_width=True,
                    )


# ============ 🌱 育成する（育成優先度） ============

elif mode == _MODE_TRAIN:
    st.caption("狙いレシピの料理エナジー改善を「1Lvあたり効率」で評価。Lv30/60の食材枠解放が大きく効く。")
    if not targets:
        st.html(c.empty_state("狙いのレシピを選ぶと計算されます。"))
    else:
        tps = training_priorities(owned, targets)
        if not tps:
            st.html(c.empty_state("これ以上伸ばしても狙いレシピは改善しない（すでに充足 or 対象食材の担当がいない）。"))
        for i, tp in enumerate(tps[:10]):
            with st.container(border=True):
                delta = "、".join(f"{n} +{v:.1f}/日" for n, v in sorted(tp.delta_supply.items(), key=lambda x: -x[1]))
                pokemon_popover_row(
                    owned_by_id.get(tp.pokemon_id),
                    label=f"#{i + 1} {tp.label}",
                    img_species=tp.species_name,
                    badges_text=f"Lv{tp.current_lv}→Lv{tp.best_milestone}",
                    caption=(
                        f"効率 {tp.gain_per_lv:,.0f} en/Lv ・ 到達で +{tp.total_gain:,.0f} en/日"
                        + (f" ・ 増える食材: {delta}" if delta else "")
                    ),
                )


# ============ 🎯 捕まえる（捕獲優先度） ============

elif mode == _MODE_CATCH:
    if targets:
        st.caption("未所持種族（最終進化に集約）のうち、狙いレシピの穴食材を埋められる子。理想個体Lv60前提の概算。")
        cps = catch_priorities(owned, targets)
        _value_label = "穴埋め価値"
    else:
        st.caption("狙いレシピ未選択時は、未所持の最終進化種を『理想個体Lv60の食材エナジー×ティア』で汎用評価。")
        cps = catch_priorities_general(owned)
        _value_label = "理想食材価値"

    if not cps:
        st.html(c.empty_state("埋められる/評価できる未所持種族がいない。"))
    for i, cp in enumerate(cps[:10]):
        with st.container(border=True):
            cols = st.columns([3, 4])
            sp = db.get_species_data(cp.species_name) or {}
            tier_html = (
                c.rank_badge(cp.tier) if cp.tier else ""
            ) + c.text_badge(f"狙い: {recommended_composition(sp)}")
            cols[0].markdown(f"**#{i + 1} {cp.species_name}**　(No.{cp.dex_no})")
            cols[0].html(tier_html)
            fills = "、".join(f"{n} +{v:.1f}/日" for n, v in sorted(cp.fills.items(), key=lambda x: -x[1]))
            cols[1].caption(
                f"{_value_label} **{cp.score:,.0f} en/日**"
                + (f" ・ Tier{cp.tier}補正込み" if cp.tier else "")
                + f" ・ {fills}"
            )


# ============ 📚 食材索引（19食材マトリクス＋多能な主力・参考情報） ============

elif mode == _MODE_INDEX:
    st.caption(
        "全所持個体の枠から逆引き。数値は現在Lv・現在の食材選択での供給量/日。"
        "「枠のみ」= その食材の枠は持っているが現在選んでいない/未解放。"
        "編成に乗るのは1〜2体なので、表示は各食材の上位2体まで。"
    )

    uncovered = [n for n, providers in index.items() if not any(p.per_day_now > 0 for p in providers)]
    if uncovered:
        st.warning("担当ゼロの食材: " + "、".join(uncovered))

    target_ings: set[str] = set()
    for rec in all_recipes:
        if rec["name"] in targets:
            target_ings.update(i["name"] for i in rec["ingredients"])

    show_all = st.toggle("全食材を表示（OFF: 狙いレシピの食材のみ）", value=not targets)
    for name, providers in index.items():
        if not show_all and name not in target_ings:
            continue
        active = [p for p in providers if p.per_day_now > 0]
        idle = [p for p in providers if p.per_day_now <= 0]
        top_active, rest_active = active[:2], active[2:]
        top_idle, rest_idle = idle[:2], idle[2:]
        best_str = "・".join(f"{p.label} {p.per_day_now:.1f}個/日" for p in top_active)
        _iurl = ingredient_icon_url(name)
        _icon = (
            f'<img src="{_iurl}" width="20" loading="lazy" '
            f'style="vertical-align:middle; margin-right:5px;">' if _iurl else ""
        )
        _summary = (f"主力: {best_str}" if best_str else f"担当{len(active)}体") + f"・枠のみ{len(idle)}体"
        st.html(
            f'<div style="font-size:0.9rem; margin:3px 0;">{_icon}<b>{name}</b>'
            f'<span style="color:#7a7a7a;"> — {_summary}</span></div>'
        )
        with st.expander("担当ポケモンを見る", expanded=False):
            shown = [(p, f"{p.label}　{p.per_day_now:.1f}/日") for p in top_active] + [
                (p, f"{p.label}（枠{p.slot.upper()}・Lv{p.unlock_lv}解放{'済' if p.unlocked else '前'}）")
                for p in top_idle
            ]
            if shown:
                for prov, lbl in shown:
                    pk = owned_by_id.get(prov.pokemon_id)
                    if pk:
                        pokemon_status_popover(pk, label=lbl, use_container_width=True)
                    else:
                        st.html(c.icon_chip(None, lbl, title=prov.species_name))
                omitted = len(rest_active) + len(rest_idle)
                if omitted > 0:
                    st.caption(f"他{omitted}体は省略（編成に乗る上位2体＋枠のみ上位2体まで表示）")
            else:
                st.html(c.empty_state("担当できる所持ポケモンがいない"))

    # ---- 多能な主力（複数食材の上位担当・折りたたみ） ----
    vmains = versatile_mains(index)
    with st.expander(f"🧩 多能な主力（複数食材の上位担当）— {len(vmains)}体", expanded=False):
        st.caption("1体で複数食材の主力（上位2体）を張れる個体。編成枠が少ないほど二役こなせる子は価値が高い。")
        if not vmains:
            st.html(c.empty_state("複数食材の主力を兼ねる個体はいない（各食材の担当が分散している）。"))
        for vm in vmains:
            with st.container(border=True):
                duties = "、".join(f"{n} {v:.1f}個/日" for n, v in vm.duties)
                pokemon_popover_row(
                    owned_by_id.get(vm.pokemon_id),
                    label=vm.label,
                    img_species=vm.species_name,
                    badges_text=f"{len(vm.duties)}食材の主力",
                    caption=duties,
                )
