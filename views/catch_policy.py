"""🏅 強ポケ捕獲方針ページ。

RaenonX ティア表（食材軸）の上位種を大きく一覧し、未所持は理想構成での捕獲候補、
所持済みでも構成が狙いと違えば引き直し候補として提示する。
定石: 食材得意=AAA / きのみ=不問 / スキル=低食材。
"""

from __future__ import annotations

import streamlit as st

import db
from image_utils import pokemon_image_url
from ui import components as c
from ui.widgets import pokemon_status_popover
from utils.community_tier import recommended_composition, top_tier_species
from utils.food_expectation import composition_string

st.html(c.page_banner("強ポケ捕獲方針", "green", icon="🏅"))
st.caption(
    "RaenonXティア表(食材軸)の上位種を、とくいタイプ（食材/きのみ/スキル/オール）別に一覧。"
    "未所持は理想構成での捕獲候補、所持済みでも構成が狙いと違えば引き直し候補。"
    "定石: 食材得意=AAA / きのみ=不問 / スキル=低食材。"
)

db.init_db()
owned = [dict(r) for r in db.list_pokemon()]

owned_by_species: dict[str, list[dict]] = {}
for p in owned:
    owned_by_species.setdefault(p["species_name"], []).append(p)

# ティア帯フィルタ
tier_pick = st.pills(
    "表示するティア帯", ["S以上", "A以上", "B以上", "C以上"], default="B以上",
    key="cp_tier",
) or "B以上"
_min_tier = {"S以上": "S", "A以上": "A", "B以上": "B", "C以上": "C"}[tier_pick]

rows = []
for species_name, tier in top_tier_species(_min_tier):
    sp = db.get_species_data(species_name) or {}
    want = recommended_composition(sp)
    specialty = sp.get("specialty") or "オール"
    holders = owned_by_species.get(species_name, [])
    comps = [composition_string(p, sp) for p in holders]
    if not holders:
        status, todo = "未所持 → 捕獲候補", True
    elif want == "AAA" and not any(cs == "AAA" for cs in comps):
        status, todo = f"所持({'/'.join(comps)}) → AAA引き直し候補", True
    else:
        status, todo = f"所持({'/'.join(comps)}) ✓", False
    rows.append((species_name, tier, want, status, todo, holders, specialty))

# ---- とくいタイプ別に分割（存在する得意だけ物理ボタン化） ----
_SP_ORDER = [("食材", "🥕 食材"), ("きのみ", "🍓 きのみ"), ("スキル", "⚡ スキル"), ("オール", "✨ オール")]
_counts = {k: sum(1 for r in rows if r[6] == k) for k, _ in _SP_ORDER}
_opts = [f"{lbl}（{_counts[k]}）" for k, lbl in _SP_ORDER if _counts[k] > 0]
_opt_to_key = {f"{lbl}（{_counts[k]}）": k for k, lbl in _SP_ORDER if _counts[k] > 0}

if not _opts:
    st.html(c.empty_state("表示できる種がいない（ティア帯を広げてみて）。"))
    st.stop()

# 既定は食材（このページは食材軸ティア表が主目的）
_default = next((o for o in _opts if o.startswith("🥕")), _opts[0])
if st.session_state.get("cp_specialty") not in _opts:
    st.session_state["cp_specialty"] = _default
sp_pick = st.segmented_control(
    "とくいタイプ", options=_opts, key="cp_specialty", label_visibility="collapsed",
) or _default
sel_specialty = _opt_to_key[sp_pick]

only_todo = st.toggle("未所持・引き直し候補のみ", value=False, key="cp_only_todo")

view = [
    r for r in rows
    if r[6] == sel_specialty and (r[4] if only_todo else True)
]
st.caption(f"{sel_specialty}得意 {len(view)} 種を表示中。")

for species_name, tier, want, status, todo, holders, specialty in view:
    with st.container(border=True):
        cols = st.columns([1, 3, 4], vertical_alignment="center")
        url = pokemon_image_url(species_name)
        if url:
            cols[0].markdown(
                f'<img src="{url}" width="52" loading="lazy" style="border-radius:10px;">',
                unsafe_allow_html=True,
            )
        cols[1].markdown(f"### {species_name}")
        cols[1].html(c.rank_badge(tier) + c.text_badge(f"狙い: {want}"))
        cols[2].markdown(("🎯 " if todo else "✅ ") + status)
        if holders:
            with cols[2]:
                for hp in holders:
                    pokemon_status_popover(
                        hp, label=f"🔍 {hp.get('nickname') or species_name}",
                    )
