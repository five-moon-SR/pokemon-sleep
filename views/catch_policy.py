"""🏅 強ポケ捕獲方針ページ。

攻略サイト4ソースの人間評価を統合した独自ティアの上位種を一覧し、未所持は理想構成での
捕獲候補、所持済みでも構成が狙いと違えば引き直し候補として提示する。
定石: 食材得意=AAA / きのみ=不問 / スキル=低食材。

ティアは種族の「強さ」であって個体の当たり判定ではない（そちらは所持ポケデータの評価%）。
"""

from __future__ import annotations

import streamlit as st

import db
from image_utils import pokemon_image_url
from ui import components as c
from ui.widgets import pokemon_status_popover
from utils.community_tier import (
    get_tier_detail,
    recommended_composition,
    top_tier_species,
)
from utils.food_expectation import composition_string

# 意見が割れていると見なす閾値（統合スコアの最大-最小）。
SPREAD_ALERT = 0.30

st.html(c.page_banner("強ポケ捕獲方針", "green", icon="🏅"))
st.caption(
    "攻略サイト4ソース（ポケらく／ゲームエイト／Pokelog／こいき10選）の**人間による評価**を"
    "統合した独自ティア。とくいタイプ別に並べ、未所持は捕獲候補、"
    "所持済みでも構成が狙いと違えば引き直し候補として出す。"
    "定石: 食材得意=AAA / きのみ=不問 / スキル=低食材。"
)

db.init_db()
owned = [dict(r) for r in db.list_pokemon()]

owned_by_species: dict[str, list[dict]] = {}
for p in owned:
    owned_by_species.setdefault(p["species_name"], []).append(p)

# ティア帯フィルタ
tier_pick = st.pills(
    "表示するティア帯", ["SS", "S以上", "A以上", "B以上", "C以上"], default="B以上",
    key="cp_tier",
) or "B以上"
_min_tier = {"SS": "SS", "S以上": "S", "A以上": "A", "B以上": "B", "C以上": "C"}[tier_pick]

# 1ソースしか評価していない種は多数決が成立しないので既定では隠す
show_provisional = st.toggle(
    "1ソースのみの種も含める（参考値）", value=False, key="cp_provisional",
    help="評価しているサイトが1つしかない種族。新実装・伝説・ニッチな種が多い。",
)

rows = []
for species_name, tier in top_tier_species(_min_tier, reliable_only=not show_provisional):
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
    rows.append((species_name, tier, want, status, todo, holders, specialty,
                 get_tier_detail(species_name) or {}))

# ---- とくいタイプ別に分割（存在する得意だけ物理ボタン化） ----
_SP_ORDER = [("食材", "🥕 食材"), ("きのみ", "🍓 きのみ"), ("スキル", "⚡ スキル"), ("オール", "✨ オール")]
_counts = {k: sum(1 for r in rows if r[6] == k) for k, _ in _SP_ORDER}
_opts = [f"{lbl}（{_counts[k]}）" for k, lbl in _SP_ORDER if _counts[k] > 0]
_opt_to_key = {f"{lbl}（{_counts[k]}）": k for k, lbl in _SP_ORDER if _counts[k] > 0}

if not _opts:
    st.html(c.empty_state("表示できる種がいない（ティア帯を広げてみて）。"))
    st.stop()

# 旧データは食材軸だったので食材を既定にしていたが、統合ティアは総合評価なので
# 偏りを持たせず、単に該当数が最も多いタイプを既定にする。
_default = max(_opts, key=lambda o: _counts[_opt_to_key[o]])
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

for species_name, tier, want, status, todo, holders, specialty, detail in view:
    n_src = int(detail.get("sources") or 0)
    spread = float(detail.get("spread") or 0.0)
    by_source: dict[str, str] = detail.get("by_source") or {}

    with st.container(border=True):
        cols = st.columns([1, 3, 4], vertical_alignment="center")
        url = pokemon_image_url(species_name)
        if url:
            cols[0].markdown(
                f'<img src="{url}" width="52" loading="lazy" style="border-radius:10px;">',
                unsafe_allow_html=True,
            )
        cols[1].markdown(f"### {species_name}")

        # ティア＋狙い構成＋評価の確からしさをバッジで一列に
        badges = c.rank_badge(tier) + c.text_badge(f"狙い: {want}")
        if n_src:
            unanimous = len(set(by_source.values())) == 1 and n_src >= 3
            badges += c.text_badge(
                f"{n_src}サイト一致" if unanimous else f"{n_src}サイト評価"
            )
        if n_src == 1:
            badges += c.text_badge("参考値")
        elif spread >= SPREAD_ALERT:
            badges += c.text_badge("評価が割れている")
        cols[1].html(badges)

        cols[2].markdown(("🎯 " if todo else "✅ ") + status)
        with cols[2]:
            if by_source:
                with st.popover("📊 評価の内訳", use_container_width=False):
                    st.caption(
                        f"統合スコア {detail.get('score', 0):.2f}"
                        + (f"／意見の幅 {spread:.2f}" if n_src > 1 else "")
                    )
                    for src, t in by_source.items():
                        st.markdown(f"- **{src}** … {t}")
                    if spread >= SPREAD_ALERT:
                        st.caption(
                            "サイトによって評価軸が違うため割れている"
                            "（食材収集で見るか、スキル性能で見るか等）。"
                        )
            for hp in holders:
                pokemon_status_popover(
                    hp, label=f"🔍 {hp.get('nickname') or species_name}",
                )
