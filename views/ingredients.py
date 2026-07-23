"""🥕 食材戦略ページ。

ブロック構成:
  ① 狙いのレシピ設定（user_settings KV に永続化）
  ② 食材×担当マトリクス — 19食材それぞれの担当個体と供給量、担当ゼロをハイライト
  ②'' 多能な主力 — 複数食材の上位担当を張れる個体
  ③ レシピ充足度 — 食材ごとの need/have バーと穴食材
  ④ 育成優先度 / 捕獲優先度ランキング
  ⑤ 強ポケ捕獲方針
（きのみ充足度は「きのみ戦略」ページに分離）
"""

from __future__ import annotations

import streamlit as st

import db
from image_utils import RECIPE_ICON_DIR, icon_data_url, pokemon_image_url
from ui import components as c
from ui.widgets import pokemon_popover_row, pokemon_status_popover
from utils.community_tier import get_tier, recommended_composition, top_tier_species
from utils.food_expectation import composition_string
from utils.ingredient_coverage import (
    build_ingredient_index,
    catch_priorities,
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


# ============ ① 狙いのレシピ ============

st.html(c.section_header("狙いのレシピ"))

all_recipes = [r for r in db.list_all_recipe_records() if r.get("ingredients")]
saved_targets = load_target_recipes()
targets = st.multiselect(
    "作りたい料理（保存され、次回も引き継がれる）",
    [r["name"] for r in all_recipes],
    default=[n for n in saved_targets if any(r["name"] == n for r in all_recipes)],
    key="ing_targets",
)
if set(targets) != set(saved_targets):
    save_target_recipes(targets)

supply = team_supply(owned)


# ============ ② 食材×担当マトリクス ============

st.html(c.section_header("食材×担当ポケモン"))
st.caption(
    "全所持個体の枠から逆引き。数値は現在Lv・現在の食材選択での供給量/日。"
    "「枠のみ」= その食材の枠は持っているが現在選んでいない/未解放。"
    "編成に乗るのは1〜2体なので、表示は各食材の上位2体まで。"
)

index = build_ingredient_index(owned)
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
    with st.expander(
        f"{name}　—　"
        + (f"主力: {best_str}" if best_str else f"担当{len(active)}体")
        + f"・枠のみ{len(idle)}体",
        expanded=False,
    ):
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


# ============ ②'' 多能な主力（複数食材の上位担当） ============

st.html(c.section_header("多能な主力"))
st.caption("1体で複数食材の主力（上位2体）を張れる個体。編成枠が少ないほど二役こなせる子は価値が高い。")

vmains = versatile_mains(index)
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


# ============ ③ レシピ充足度 ============

st.html(c.section_header("レシピ充足度"))

if not targets:
    st.html(c.empty_state("狙いのレシピを選ぶと、食材ごとの充足度と穴が表示されます。"))
else:
    for cov in recipe_coverage(targets, supply):
        with st.container(border=True):
            head = st.columns([3, 2])
            _rurl = icon_data_url(str(RECIPE_ICON_DIR), cov.recipe.get("icon"))
            head[0].markdown(
                (f'<img src="{_rurl}" width="34" style="vertical-align:middle; margin-right:6px;">' if _rurl else "")
                + f"**{cov.recipe['name']}**",
                unsafe_allow_html=True,
            )
            head[1].caption(
                f"作成ペース {cov.pace:.2f}回/日 ・ 期待 {cov.daily_energy:,.0f} en/日"
            )
            for ing_name, (need, have) in cov.per_ingredient.items():
                ratio = have / need if need > 0 else 0.0
                is_hole = ing_name in cov.holes
                cols = st.columns([2, 3, 2])
                cols[0].html(c.ingredient_chip(ing_name, f"{have:.1f}/{need:.0f}"))
                cols[1].html(c.meter(ratio))
                cols[2].caption(("🕳 律速" if is_hole else "") + f" ×{ratio:.2f}")


# ============ ④ 育成・捕獲優先度 ============

st.html(c.section_header("育成優先度"))
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

st.html(c.section_header("捕獲優先度"))
st.caption("未所持種族（最終進化に集約）のうち、狙いレシピの穴食材を埋められる子。理想個体Lv60前提の概算。")

if not targets:
    st.html(c.empty_state("狙いのレシピを選ぶと計算されます。"))
else:
    cps = catch_priorities(owned, targets)
    if not cps:
        st.html(c.empty_state("穴食材なし、または埋められる未所持種族がいない。"))
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
                f"穴埋め価値 **{cp.score:,.0f} en/日**"
                + (f" ・ Tier{cp.tier}補正込み" if cp.tier else "")
                + f" ・ {fills}"
            )


# ============ ⑤ 強ポケ捕獲方針（コミュニティTier × 構成厳選） ============

st.html(c.section_header("強ポケ捕獲方針"))
st.caption(
    "RaenonXティア表(食材軸)の上位種。未所持は理想構成での捕獲候補、"
    "所持済みでも構成が狙いと違えば引き直し候補。定石: 食材得意=AAA / きのみ=不問 / スキル=低食材。"
)

owned_by_species: dict[str, list[dict]] = {}
for p in owned:
    owned_by_species.setdefault(p["species_name"], []).append(p)

rows = []
for species_name, tier in top_tier_species("C"):
    sp = db.get_species_data(species_name) or {}
    want = recommended_composition(sp)
    holders = owned_by_species.get(species_name, [])
    comps = [composition_string(p, sp) for p in holders]
    if not holders:
        status = "未所持 → 捕獲候補"
    elif want == "AAA" and not any(cs == "AAA" for cs in comps):
        status = f"所持({'/'.join(comps)}) → AAA引き直し候補"
    else:
        status = f"所持({'/'.join(comps)}) ✓"
    rows.append((species_name, tier, want, status))

with st.container(key="tier_policy"):
    for species_name, tier, want, status in rows:
        cols = st.columns([5, 4], vertical_alignment="center")
        cols[0].html(c.result_row(
            title=species_name,
            img_url=pokemon_image_url(species_name),
            badges=[c.rank_badge(tier), c.text_badge(f"狙い: {want}")],
        ))
        cols[1].caption(status)
