"""ホーム画面（ダッシュボード）。

ブロック構成:
  ① 直近編成のショートカット — 直近の保存パーティをそのままサマリ表示
  ② プレイヤープロフィール — RR・鍋容量・睡眠時間・食事時刻の編集
  ③ 所持ポケモン統計 — 個体数・Lv60到達・食材枠3・だいふく/specialty分布
  最近登録した子
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

import db
from image_utils import (
    RECIPE_ICON_DIR,
    berry_icon_url,
    icon_data_url,
)
from utils.play_context import PlayContext, load_play_context, save_play_context

st.title("🏠 ホーム")


def _eff_lv(p: dict) -> int:
    return p.get("current_level") or p.get("caught_level") or p.get("level") or 1


owned = [dict(r) for r in db.list_pokemon()]


# ============ ① 今週のショートカット ============

parties = db.list_parties()
if parties:
    pt = parties[0]  # updated_at 降順なので最新
    with st.container(border=True):
        st.subheader(f"🗓 直近の編成: {pt['name']}")

        head = st.columns([2, 3])

        # 左: フィールド + 好みきのみ
        with head[0]:
            field_name = pt.get("field_name") or "（未設定）"
            st.markdown(f"**🏝 フィールド**  \n{field_name}")

            if pt.get("random_field_berries"):
                fav = list(pt["random_field_berries"])
                fav_label = "今週の好みきのみ"
            else:
                fr = next(
                    (
                        f
                        for f in db.list_all_field_records()
                        if f["name"] == field_name
                    ),
                    None,
                )
                fav = [b["name"] for b in (fr.get("favorite_berries") or [])] if fr else []
                fav_label = "好みのきのみ"

            st.markdown(f"**🍒 {fav_label}**")
            if fav:
                inner = st.columns(min(len(fav), 3))
                for i, name in enumerate(fav):
                    url = berry_icon_url(name)
                    with inner[i % len(inner)]:
                        if url:
                            st.markdown(
                                f'<img src="{url}" width="28" style="vertical-align:middle"> {name}',
                                unsafe_allow_html=True,
                            )
                        else:
                            st.caption(name)
            else:
                st.caption("—")

        # 右: 候補レシピ
        with head[1]:
            st.markdown("**🍳 候補レシピ**")
            recipes_list = pt.get("candidate_recipes") or []
            if recipes_list:
                rec_map = {r["name"]: r for r in db.list_all_recipe_records()}
                inner = st.columns(min(len(recipes_list), 5))
                for i, rname in enumerate(recipes_list[:5]):
                    rec = rec_map.get(rname)
                    with inner[i % len(inner)]:
                        if rec and rec.get("icon"):
                            url = icon_data_url(str(RECIPE_ICON_DIR), rec["icon"])
                            if url:
                                st.markdown(
                                    f'<img src="{url}" width="40">',
                                    unsafe_allow_html=True,
                                )
                        st.caption(rname)
                if len(recipes_list) > 5:
                    st.caption(f"…他{len(recipes_list) - 5}件")
            else:
                st.caption("—")

        # 編成メンバー
        st.markdown("**👥 編成メンバー**")
        member_ids = pt.get("member_ids") or []
        mem_cols = st.columns(5)
        for i in range(5):
            with mem_cols[i]:
                if i < len(member_ids):
                    m_row = db.get_pokemon(member_ids[i])
                    if m_row is None:
                        st.caption("（削除済み）")
                        continue
                    m = dict(m_row)
                    master = db.get_species_data(m["species_name"]) or {}
                    burl = berry_icon_url((master.get("berry") or {}).get("name"))
                    if burl:
                        st.markdown(
                            f'<img src="{burl}" width="32">', unsafe_allow_html=True
                        )
                    st.caption(f"**{m.get('nickname') or m['species_name']}**")
                    st.caption(f"Lv{_eff_lv(m)}")
                else:
                    st.caption("—")

        meta_cols = st.columns([3, 1])
        meta_cols[0].caption(
            f"方針: {' / '.join(pt.get('policy_tags') or []) or '—'}"
            f"　最終更新: {(pt.get('updated_at') or '')[:16]}"
        )
        meta_cols[1].page_link("views/party.py", label="→ 編成ページへ", icon="⚔")
else:
    with st.container(border=True):
        st.subheader("🗓 直近の編成")
        st.info("まだ保存されたパーティがありません。「パーティー編成」から作成してください。")


# ============ ② プレイヤープロフィール ============

ctx = load_play_context()

with st.container(border=True):
    st.subheader("🧑 プレイヤープロフィール")

    with st.form("profile_form"):
        c1 = st.columns(4)
        rr = c1[0].number_input(
            "リサーチランク",
            min_value=1,
            max_value=80,
            value=int(ctx.research_rank),
            step=1,
        )
        pot = c1[1].number_input(
            "鍋容量",
            min_value=15,
            max_value=2000,
            value=int(ctx.pot_capacity),
            step=1,
            help="現在の鍋の容量。料理期待値の上限として使う。",
        )
        sleep_wd = c1[2].number_input(
            "平日 睡眠時間 (h)",
            min_value=0.0,
            max_value=14.0,
            value=float(ctx.sleep_hours_weekday),
            step=0.5,
        )
        sleep_we = c1[3].number_input(
            "休日 睡眠時間 (h)",
            min_value=0.0,
            max_value=14.0,
            value=float(ctx.sleep_hours_weekend),
            step=0.5,
        )

        c2 = st.columns(3)
        bf_default = datetime.strptime(ctx.meal_breakfast, "%H:%M").time()
        ln_default = datetime.strptime(ctx.meal_lunch, "%H:%M").time()
        dn_default = datetime.strptime(ctx.meal_dinner, "%H:%M").time()
        bf = c2[0].time_input("🍞 朝食", value=bf_default, step=60 * 15)
        ln = c2[1].time_input("🍙 昼食", value=ln_default, step=60 * 15)
        dn = c2[2].time_input("🍛 夕食", value=dn_default, step=60 * 15)

        if st.form_submit_button("💾 保存", type="primary"):
            new_ctx = PlayContext(
                research_rank=int(rr),
                pot_capacity=int(pot),
                sleep_hours_weekday=float(sleep_wd),
                sleep_hours_weekend=float(sleep_we),
                meal_breakfast=bf.strftime("%H:%M"),
                meal_lunch=ln.strftime("%H:%M"),
                meal_dinner=dn.strftime("%H:%M"),
            )
            save_play_context(new_ctx)
            st.success("保存しました")
            st.rerun()

    st.caption(
        f"⏰ おてつだい時間 — 平日 **{ctx.active_hours():.1f}h** / "
        f"休日 **{ctx.active_hours(weekend=True):.1f}h**"
    )


# ============ ③ 所持ポケモン統計 ============

with st.container(border=True):
    st.subheader("📦 所持ポケモン")

    if not owned:
        st.info("まだ登録されていません。「個体登録」から追加してください。")
    else:
        species_count = len({p["species_name"] for p in owned})
        lv60_count = sum(1 for p in owned if _eff_lv(p) >= 60)
        slot3_count = sum(1 for p in owned if p.get("ingredient_3"))
        rank_evaluated = sum(1 for p in owned if p.get("daifuku_rank"))

        m = st.columns(5)
        m[0].metric("個体数", len(owned))
        m[1].metric("種族数", species_count)
        m[2].metric("Lv60到達", lv60_count)
        m[3].metric("食材枠3解放", slot3_count)
        m[4].metric("だいふく評価済", rank_evaluated)

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
                st.bar_chart(df.set_index("ランク"), height=180)
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
                df = pd.DataFrame(
                    {"区分": list(sp_counts), "人数": list(sp_counts.values())}
                )
                st.bar_chart(df.set_index("区分"), height=180)
            else:
                st.caption("—")


# ============ 最近登録した子（既存ブロック・残しておく） ============

st.divider()
st.subheader("最近登録した子")
if not owned:
    st.info("まだ登録されていません。")
else:
    for r in owned[:5]:
        d = dict(r)
        nick = d.get("nickname")
        species = d.get("species_name")
        rank = d.get("daifuku_rank") or "—"
        line = f"- **{species}**"
        if nick:
            line += f"「{nick}」"
        line += f"  Lv{_eff_lv(d)}　ランク: {rank}"
        st.markdown(line)
