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
from utils.field_encounters import (
    has_data,
    recommend_fields,
    species_fields,
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
        status, todo, kind = "未所持 → 捕獲候補", True, "未所持"
    elif want == "AAA" and not any(cs == "AAA" for cs in comps):
        status, todo, kind = f"所持({'/'.join(comps)}) → AAA引き直し候補", True, "引き直し"
    else:
        status, todo, kind = f"所持({'/'.join(comps)}) ✓", False, "充足"
    rows.append({
        "species_name": species_name, "tier": tier, "want": want,
        "status": status, "todo": todo, "holders": holders,
        "specialty": specialty, "kind": kind,
        "detail": get_tier_detail(species_name) or {},
    })

# ---- とくいタイプ別に分割（存在する得意だけ物理ボタン化） ----
_SP_ORDER = [("食材", "🥕 食材"), ("きのみ", "🍓 きのみ"), ("スキル", "⚡ スキル"), ("オール", "✨ オール")]
_counts = {k: sum(1 for r in rows if r["specialty"] == k) for k, _ in _SP_ORDER}
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

# ── 所持状況で絞る（既に理想を持っている種を畳めるように細分化） ──
_KIND_OPTS = ["すべて", "未所持のみ", "引き直しのみ", "未所持＋引き直し"]
_counts_kind = {k: sum(1 for r in rows if r["kind"] == k) for k in ("未所持", "引き直し", "充足")}
kind_pick = st.segmented_control(
    "所持状況",
    options=_KIND_OPTS,
    default="すべて",
    key="cp_kind",
    help=(
        f"未所持 {_counts_kind['未所持']} / "
        f"引き直し {_counts_kind['引き直し']} / "
        f"充足 {_counts_kind['充足']}（表示中のティア帯での内訳）"
    ),
) or "すべて"
_KIND_FILTER = {
    "すべて": None,
    "未所持のみ": {"未所持"},
    "引き直しのみ": {"引き直し"},
    "未所持＋引き直し": {"未所持", "引き直し"},
}[kind_pick]

# ── 今週のマップで出る種だけに絞る ──
active_week = db.get_setting("user.active_strategy_week", {}) or {}
active_plan = db.get_party(int(active_week["plan_id"])) if active_week.get("plan_id") else None
week_field = (active_plan or {}).get("field_name")

field_filter = None
if week_field and has_data(week_field):
    if st.toggle(
        f"今週のマップ（{week_field}）で出る種だけ", value=False, key="cp_week_field",
        help="そのマップに出現しない種は、今週は狙えないので隠す。",
    ):
        field_filter = week_field
elif week_field:
    st.caption(f"※ {week_field} の出現データは未取得のため、マップ絞り込みは使えない。")

view = [
    r for r in rows
    if r["specialty"] == sel_specialty
    and (_KIND_FILTER is None or r["kind"] in _KIND_FILTER)
    and (field_filter is None or field_filter in species_fields(r["species_name"]))
]
st.caption(
    f"{sel_specialty}得意 {len(view)} 種を表示中。"
    + (f"（{week_field}に出る種のみ）" if field_filter else "")
)

# ── おすすめマップ: 未所持・引き直し候補が最も多く出るフィールド ──
_wanted = {r["species_name"] for r in rows if r["todo"]}
if _wanted:
    recs = recommend_fields(_wanted)
    if recs:
        with st.expander(
            f"🗺 おすすめマップ（狙える候補 {len(_wanted)} 種の出現先）", expanded=False
        ):
            st.caption(
                "表示中のティア帯で「未所持・引き直し候補」になっている種が、"
                "どのマップに何体出るか。多いマップほど厳選効率が良い。"
            )
            for fname, n, names in recs:
                mark = "▶ " if fname == week_field else ""
                st.markdown(f"**{mark}{fname}** … {n}種")
                st.caption("　" + "、".join(names[:14]) + ("…" if len(names) > 14 else ""))

for row in view:
    species_name = row["species_name"]
    tier, want, status = row["tier"], row["want"], row["status"]
    todo, holders, detail = row["todo"], row["holders"], row["detail"]
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
        fields_of = species_fields(species_name)
        if fields_of:
            here = week_field in fields_of if week_field else False
            cols[2].caption(
                ("📍 今週のマップに出る： " if here else "出現： ")
                + "、".join(fields_of)
            )
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
