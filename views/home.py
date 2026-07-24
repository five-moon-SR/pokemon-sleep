"""ホーム画面（ダッシュボード）。

ブロック構成:
  ① 今週の攻略プラン — 料理カテゴリ×フィールドの定番5体と週見通し
  ② 所持ポケモン統計 — 統計タイル + だいふく/specialty分布
  ③ 最近登録した子 — カード行
プレイヤープロフィール編集は ⚙ ボタンから st.dialog で開く。
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

import db
from image_utils import RECIPE_ICON_DIR, field_icon_url, icon_data_url, pokemon_image_url
from ui import components as c
from utils.party_logic import RECIPE_CATEGORY_LABELS
from utils.plan_simulation import capture_improvements, level_improvements, simulate_plan
from utils.play_context import PlayContext, load_play_context, save_play_context

ctx = load_play_context()

st.html(c.page_banner("ホーム", "green", icon="🏠"))


def _eff_lv(p: dict) -> int:
    return p.get("current_level") or p.get("caught_level") or p.get("level") or 1


@st.dialog("🧑 プレイヤープロフィール")
def _profile_dialog() -> None:
    with st.form("profile_form"):
        c1 = st.columns(2)
        rr = c1[0].number_input("リサーチランク", min_value=1, max_value=80, value=int(ctx.research_rank), step=1)
        pot = c1[1].number_input(
            "鍋容量", min_value=15, max_value=2000, value=int(ctx.pot_capacity), step=1,
            help="現在の鍋の容量。料理期待値の上限として使う。",
        )
        c2 = st.columns(2)
        sleep_wd = c2[0].number_input("平日 睡眠時間 (h)", min_value=0.0, max_value=14.0, value=float(ctx.sleep_hours_weekday), step=0.5)
        sleep_we = c2[1].number_input("休日 睡眠時間 (h)", min_value=0.0, max_value=14.0, value=float(ctx.sleep_hours_weekend), step=0.5)

        c3 = st.columns(3)
        bf = c3[0].time_input("🍞 朝食", value=datetime.strptime(ctx.meal_breakfast, "%H:%M").time(), step=60 * 15)
        ln = c3[1].time_input("🍙 昼食", value=datetime.strptime(ctx.meal_lunch, "%H:%M").time(), step=60 * 15)
        dn = c3[2].time_input("🍛 夕食", value=datetime.strptime(ctx.meal_dinner, "%H:%M").time(), step=60 * 15)

        if st.form_submit_button("💾 保存", type="primary", use_container_width=True):
            save_play_context(PlayContext(
                research_rank=int(rr),
                pot_capacity=int(pot),
                sleep_hours_weekday=float(sleep_wd),
                sleep_hours_weekend=float(sleep_we),
                meal_breakfast=bf.strftime("%H:%M"),
                meal_lunch=ln.strftime("%H:%M"),
                meal_dinner=dn.strftime("%H:%M"),
            ))
            st.rerun()


prof_cols = st.columns([3, 2])
prof_cols[0].caption(
    f"RR{ctx.research_rank} · 鍋{ctx.pot_capacity} · "
    f"おてつだい 平日{ctx.active_hours():.1f}h/休日{ctx.active_hours(weekend=True):.1f}h"
)
if prof_cols[1].button("⚙ 設定", use_container_width=True):
    _profile_dialog()

owned = [dict(r) for r in db.list_pokemon()]


# ============ ① 今週の攻略プラン ============

active_week = db.get_setting("user.active_strategy_week", {}) or {}
pt = db.get_party(int(active_week["plan_id"])) if active_week.get("plan_id") else None
if pt:
    st.html(c.section_header(f"今週の攻略プラン: {pt['name']}"))

    # フィールド/好みきのみ/候補レシピ を1行のチップにまとめる
    field_name = pt.get("field_name") or "（未設定）"
    if active_week.get("random_berries"):
        fav = list(active_week["random_berries"])
    else:
        fr = next((f for f in db.list_all_field_records() if f["name"] == field_name), None)
        fav = [b["name"] for b in (fr.get("favorite_berries") or [])] if fr else []

    chips = [c.icon_chip(field_icon_url(field_name), field_name, size=24)]
    chips += [c.berry_chip(b) for b in fav]
    for rname in [pt.get("main_recipe")]:
        if not rname:
            continue
        rec = next((r for r in db.list_all_recipe_records() if r["name"] == rname), None)
        url = icon_data_url(str(RECIPE_ICON_DIR), rec["icon"]) if rec and rec.get("icon") else None
        chips.append(c.icon_chip(url, rname))
    st.html('<div style="display:flex; flex-wrap:wrap; gap:4px;">' + "".join(chips) + "</div>")

    cards = []
    for mid in (pt.get("member_ids") or [])[:5]:
        m_row = db.get_pokemon(mid)
        if m_row is None:
            cards.append(c.pokemon_card(title="（削除済み）", mini=True))
            continue
        m = dict(m_row)
        master = db.get_species_data(m["species_name"]) or {}
        cards.append(c.pokemon_card(
            title=m.get("nickname") or m["species_name"],
            subtitle=f"{m['species_name']} · Lv{_eff_lv(m)}",
            specialty=master.get("specialty"),
            berry_name=(master.get("berry") or {}).get("name"),
            img_url=pokemon_image_url(m["species_name"]),
            badges=[c.rank_badge(m.get("daifuku_rank"))],
            mini=True,
        ))
    if cards:
        st.html(c.row_scroll(cards))

    members = [
        dict(row)
        for mid in (pt.get("member_ids") or [])
        if (row := db.get_pokemon(mid)) is not None
    ]
    recipe = next(
        (
            r for r in db.list_all_recipe_records()
            if r["name"] == pt.get("main_recipe")
        ),
        None,
    )
    if len(members) == 5 and recipe:
        sim = simulate_plan(
            members,
            recipe,
            fav_berries=set(fav),
            ctx=ctx,
            starting_inventory=active_week.get("starting_inventory", {}),
            event_set=set(active_week.get("event_bonuses", [])),
        )
        metric_cols = st.columns(4)
        metric_cols[0].metric("主料理", pt.get("main_recipe") or "—")
        metric_cols[1].metric("3食安定度", f"{sim.stability:.0%}", f"{sim.cooked_meals}/21食")
        metric_cols[2].metric("週期待値", f"{sim.weekly_energy:,.0f} en")
        metric_cols[3].metric(
            "律速",
            " / ".join(sim.bottlenecks) if sim.bottlenecks else "なし",
        )

        advice_key = f"_home_advice_{pt['id']}:{pt.get('updated_at')}"
        if advice_key not in st.session_state:
            growth = level_improvements(
                members, recipe, fav_berries=set(fav), ctx=ctx
            )
            catches = capture_improvements(
                members, recipe, fav_berries=set(fav), ctx=ctx, limit=3
            )
            st.session_state[advice_key] = (growth[:3], catches[:3])
        growth, catches = st.session_state[advice_key]
        advice_cols = st.columns(2)
        with advice_cols[0]:
            st.markdown("**🌱 次の育成候補**")
            for item in growth:
                st.caption(
                    f"{item['label']} → Lv{item['target_level']}｜"
                    f"週 {item['energy_delta']:+,.0f} en"
                )
        with advice_cols[1]:
            st.markdown("**🎯 次の捕獲候補**")
            for item in catches:
                st.caption(
                    f"{item['species_name']} {item['composition']}｜"
                    f"{' / '.join(item['fills'])}｜安定度 {item['stability_delta']:+.0%}"
                )

    meta_cols = st.columns([3, 1])
    category = pt.get("recipe_category")
    meta_cols[0].caption(
        f"{RECIPE_CATEGORY_LABELS.get(category, category or '旧編成')}　"
        f"最終更新: {(pt.get('updated_at') or '')[:16]}"
    )
    meta_cols[1].page_link("views/party.py", label="→ 攻略プランを調整", icon="🧭")
else:
    st.html(c.section_header("今週の攻略プラン"))
    st.html(c.empty_state("料理カテゴリとフィールドを選び、今週の攻略プランを設定してください。"))
    st.page_link("views/party.py", label="攻略プランを作る →", icon="🧭")


# ============ ② 所持ポケモン統計 ============

st.html(c.section_header("所持ポケモン"))

if not owned:
    st.html(c.empty_state("まだ登録されていません。「個体登録」から追加できます。"))
else:
    species_count = len({p["species_name"] for p in owned})
    lv60_count = sum(1 for p in owned if _eff_lv(p) >= 60)
    slot3_count = sum(1 for p in owned if p.get("ingredient_3"))
    rank_evaluated = sum(1 for p in owned if p.get("daifuku_rank"))

    st.html(c.stat_tiles([
        c.stat_tile("個体数", str(len(owned))),
        c.stat_tile("種族数", str(species_count)),
        c.stat_tile("Lv60到達", str(lv60_count)),
        c.stat_tile("食材枠3解放", str(slot3_count)),
        c.stat_tile("だいふく評価済", str(rank_evaluated)),
    ]))

    chart_cols = st.columns(2)

    # だいふくランク分布
    rank_counts: dict[str, int] = {}
    for p in owned:
        r = p.get("daifuku_rank") or "未評価"
        rank_counts[r] = rank_counts.get(r, 0) + 1
    rank_order = ["SS", "S", "A", "B", "C", "D", "未評価"]
    rank_rows = [(r, rank_counts[r]) for r in rank_order if r in rank_counts]
    with chart_cols[0]:
        st.markdown("**だいふくランク分布**")
        if rank_rows:
            df = pd.DataFrame(rank_rows, columns=["ランク", "人数"])
            st.bar_chart(df.set_index("ランク"), height=180, color="#F0B32E")
        else:
            st.caption("—")

    # とくいなもの分布
    sp_counts: dict[str, int] = {}
    for p in owned:
        master = db.get_species_data(p["species_name"]) or {}
        sp = master.get("specialty") or "?"
        sp_counts[sp] = sp_counts.get(sp, 0) + 1
    with chart_cols[1]:
        st.markdown("**とくいなもの分布**")
        if sp_counts:
            df = pd.DataFrame({"区分": list(sp_counts), "人数": list(sp_counts.values())})
            st.bar_chart(df.set_index("区分"), height=180, color="#3E87C7")
        else:
            st.caption("—")


# ============ ③ 最近登録した子 ============

st.html(c.section_header("最近登録した子"))
if not owned:
    st.html(c.empty_state("まだ登録されていません。"))
else:
    cards = []
    for p in owned[:6]:
        master = db.get_species_data(p["species_name"]) or {}
        cards.append(c.pokemon_card(
            title=p.get("nickname") or p["species_name"],
            subtitle=f"{p['species_name']} · Lv{_eff_lv(p)}",
            specialty=master.get("specialty"),
            berry_name=(master.get("berry") or {}).get("name"),
            img_url=pokemon_image_url(p["species_name"]),
            badges=[c.rank_badge(p.get("daifuku_rank"))],
            mini=True,
        ))
    st.html(c.row_scroll(cards))
