"""🍓 きのみ戦略ページ。

全きのみのボックス監査。監査フィールドを選ぶと好物3種に×2を反映し、
きのみごとの担当個体（育成後でなく現状Lv・現構成のエナジー/日）を上位2体まで表示。
好物なのに担当ゼロのきのみをチームの穴として警告する。
"""

from __future__ import annotations

import streamlit as st

import db
from image_utils import berry_icon_url
from ui import components as c
from ui.widgets import pokemon_status_popover
from utils.berry_coverage import (
    berry_audit,
    favorite_holes,
    load_audit_field,
    load_random_favs,
    resolve_fav_berries,
    save_audit_field,
    save_random_favs,
)

st.html(c.page_banner("きのみ戦略", "box", icon="🍓"))
st.caption("全きのみのボックス監査。フィールドの好物3種に×2を反映し、担当ゼロの穴を洗い出す。")

db.init_db()
owned = [dict(r) for r in db.list_pokemon()]
owned_by_id = {p["id"]: p for p in owned}

if not owned:
    st.html(c.empty_state("所持ポケモンがいません。先に「個体登録」から追加してください。"))
    st.stop()

st.html(c.section_header("きのみ充足度"))
st.caption(
    "数値は現在Lv・現在の個体構成でのきのみエナジー/日（フィールド開拓ボーナスは含まない）。"
    "編成に乗るのは1〜2体なので担当は上位2体まで。ポケモン名を押すと簡易ステータス。"
)

fields = db.list_all_field_records()
field_options = ["（未選択）"] + [f["name"] for f in fields]
saved_field = load_audit_field()
sel_field_name = st.selectbox(
    "監査フィールド（保存され、次回も引き継がれる）",
    field_options,
    index=field_options.index(saved_field) if saved_field in field_options else 0,
    key="berry_audit_field",
)
audit_field = sel_field_name if sel_field_name != "（未選択）" else None
if audit_field != saved_field:
    save_audit_field(audit_field)

sel_field = next((f for f in fields if f["name"] == audit_field), None)
saved_favs = load_random_favs()
if sel_field and sel_field.get("favorite_berries_random"):
    all_berry_names = [r["name"] for r in db.list_all_berry_records()]
    picked = st.multiselect(
        "🎲 ランダム好物フィールド：今週の好物3種（保存される）",
        all_berry_names,
        default=[n for n in saved_favs if n in all_berry_names],
        max_selections=3,
        key="berry_audit_random_favs",
    )
    if set(picked) != set(saved_favs):
        save_random_favs(picked)
    fav_set = resolve_fav_berries(audit_field, picked)
else:
    fav_set = resolve_fav_berries(audit_field, saved_favs)

coverages = berry_audit(owned, fav_set)
holes = favorite_holes(coverages)
if holes:
    st.warning("好物(×2)なのに担当ゼロ: " + "、".join(holes))

for cov in coverages:
    b_name = cov.berry["name"]
    star = "⭐" if cov.is_favorite else ""
    top = cov.top
    rest = len(cov.providers) - len(top)
    _summary = (
        "主力: " + " / ".join(f"{p.label} {p.count_per_day:.1f}個/日" for p in top)
        + (f"・他{rest}体" if rest > 0 else "")
        if top else "担当ゼロ"
    )
    _burl = berry_icon_url(b_name)
    _icon = (
        f'<img src="{_burl}" width="20" loading="lazy" '
        f'style="vertical-align:middle; margin-right:5px;">' if _burl else ""
    )
    st.html(
        f'<div style="font-size:0.9rem; margin:3px 0;">{_icon}<b>{star}{b_name}</b>'
        f'<span style="color:#7a7a7a;"> — {_summary}</span></div>'
    )
    with st.expander("担当ポケモンを見る", expanded=False):
        if top:
            for p in top:
                lbl = f"{p.label} Lv{p.level}　{p.energy_per_day:,.0f}en/日（{p.count_per_day:.1f}個）"
                pk = owned_by_id.get(p.pokemon_id)
                if pk:
                    pokemon_status_popover(pk, label=lbl, use_container_width=True)
                else:
                    st.html(c.icon_chip(berry_icon_url(b_name), lbl, title=p.species_name))
            if rest > 0:
                st.caption(f"他{rest}体は編成に乗らないため省略（充足は上位{len(top)}体で判定）")
        else:
            st.html(c.empty_state("担当できる所持ポケモンがいない"))
