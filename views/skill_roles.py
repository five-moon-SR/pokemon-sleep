"""🎯 スキル・役割ページ。

メインスキルの役割ごとに、所持ボックスの担当状況を監査する（きのみ/食材の
充足度と同じボックス監査の発想）。強さは育成後（最終進化Lv60・進化でMSLv+1込み）の
スキル軸スコアで測り、担当ゼロの役割を穴として洗い出す。
"""

from __future__ import annotations

import streamlit as st

import db
from image_utils import pokemon_image_url
from ui import components as c
from ui.widgets import pokemon_status_popover
from utils.skill_role_coverage import (
    TOP_N,
    role_holes,
    skill_role_audit,
)

st.html(c.page_banner("スキル・役割", "green", icon="🎯"))
st.caption(
    "メインスキルの役割ごとの担当ボックス監査。強さは育成後（最終進化Lv60・進化でスキルLv+1込み）の"
    "スキル軸で評価。担当ゼロの役割はチームの穴。"
)

db.init_db()
owned = [dict(r) for r in db.list_pokemon()]
owned_by_id = {p["id"]: p for p in owned}

if not owned:
    st.html(c.empty_state("所持ポケモンがいません。先に「個体登録」から追加してください。"))
    st.stop()

tcol = st.columns(2)
run = tcol[0].toggle("計算する（所持全体を走査）", key="skill_role_compute")
maxskill = tcol[1].toggle(
    "🔺 メインスキルLv最大の天井で見る", key="skill_role_maxskill",
    help="メインスキルを育て切った場合の各役割の天井を比較する。",
)
if not run:
    st.info("トグルをONにすると、育成後スコアで各スキル役割の担当を集計します。")
    st.stop()

coverages = skill_role_audit(owned, main_skill_max=maxskill)
if maxskill:
    st.caption("🔺 メインスキルLv最大（育て切った天井）で評価中。")

holes = role_holes(coverages)
if holes:
    st.warning("担当ゼロの役割: " + "、".join(holes))

st.caption(f"編成に乗るのは1〜2体なので、各役割の担当は上位{TOP_N}体まで表示。")

for cov in coverages:
    top = cov.top
    rest = len(cov.providers) - len(top)
    title = (
        f"{cov.label}　—　"
        + ("主力: " + " / ".join(p.label for p in top) + (f"・他{rest}体" if rest > 0 else "")
           if top else "担当ゼロ")
    )
    with st.expander(title, expanded=bool(top)):
        cats = "・".join(sorted(cov.categories))
        st.caption(f"対象スキル: {cats}")
        if not top:
            st.html(c.empty_state("この役割を担えるメインスキル持ちが所持にいない。"))
            continue
        for p in top:
            cols = st.columns([3, 4, 1], vertical_alignment="center")
            arrow = f"　→{p.final_species}" if p.final_species != p.species_name else ""
            cols[0].html(c.result_row(
                title=f"{p.label}{arrow}",
                img_url=pokemon_image_url(p.final_species),
                badges=[c.rank_badge(p.potential_rank, p.potential_total, prefix="育成後")],
            ))
            cols[1].caption(
                f"スキル軸 **{p.skill_axis:.0f}**/100　・　"
                f"想定メインスキルLv {p.main_skill_level}　・　{p.skill_category}"
            )
            pk = owned_by_id.get(p.pokemon_id)
            if pk:
                with cols[2]:
                    pokemon_status_popover(pk, label="🔍", help_text="この個体の簡易ステータス")
        if rest > 0:
            st.caption(f"他{rest}体は編成に乗らないため省略（充足は上位{TOP_N}体で判定）。")
