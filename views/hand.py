"""ボックス全体の役割充足度（食材・きのみ・スキル）を棚卸しするページ。

編成やレシピを決める前に「何が足りていないか」を見る場所。

きのみ充足度は utils/berry_coverage.py に実装があったのに、
それを出すページがナビ未登録で到達不能になっていた（この統合で削除）。
食材・スキルと同じ土俵に並べて、3軸そろえてここで見る。

用語は編成ページ（views/party.py）に合わせる:
  即戦力 = 現在のLv・構成で供給できる個体 / 将来候補 = 候補枠にはあるが供給ゼロ
"""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st

import db
from image_utils import berry_icon_url, ingredient_icon_url, pokemon_image_url
from ui import components as c
from ui.widgets import pokemon_popover_row
from utils.berry_coverage import (
    berry_audit,
    favorite_holes,
    load_audit_field,
    load_random_favs,
    resolve_fav_berries,
    save_audit_field,
    save_random_favs,
)
from utils.berry_coverage import TOP_N as BERRY_TOP_N
from utils.ingredient_coverage import build_ingredient_index, versatile_mains
from utils.ingredient_coverage import ingredient_recommendation_rows
from utils.skill_role_coverage import TOP_N, role_holes, skill_role_audit

# 食材は編成に1〜2体置ける想定。ここを満たせば「充足」
FOOD_TOP_N = 2


@st.cache_data(show_spinner=False, ttl=300)
def _ingredient_index(owned_rows: list[dict]) -> dict:
    return build_ingredient_index(owned_rows)


@st.cache_data(show_spinner=False, ttl=300)
def _skill_roles(owned_rows: list[dict], main_skill_max: bool) -> list:
    return skill_role_audit(owned_rows, main_skill_max=main_skill_max)


@st.cache_data(show_spinner=False, ttl=300)
def _berries(owned_rows: list[dict], fav: tuple[str, ...]) -> list:
    return berry_audit(owned_rows, set(fav))


def _fill_ratio(count: int, need: int) -> float:
    return min(1.0, count / need) if need else 0.0


def _status_label(count: int, need: int) -> str:
    """充足の言い方をページ全体でそろえる（記号だけだと意味が読めない）。"""
    if count >= need:
        return "充足"
    if count > 0:
        return f"あと{need - count}体"
    return "担当ゼロ"


def _coverage_table(
    rows: list[dict],
    *,
    icon_col: str,
    height: int,
) -> None:
    """充足度テーブル。列幅と高さを明示して、表の中で二重スクロールさせない。"""
    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        use_container_width=True,
        height=height,
        column_config={
            icon_col: st.column_config.ImageColumn(icon_col, width="small"),
            "充足": st.column_config.ProgressColumn(
                "充足", format="%.0f%%", min_value=0, max_value=100, width="small"
            ),
            "状態": st.column_config.TextColumn("状態", width="small"),
            "即戦力": st.column_config.NumberColumn("即戦力", format="%d体", width="small"),
            "将来候補": st.column_config.NumberColumn("将来候補", format="%d体", width="small"),
            "供給/日": st.column_config.NumberColumn("供給/日", format="%.1f", width="small"),
            "エナジー/日": st.column_config.NumberColumn("エナジー/日", format="%.0f", width="small"),
        },
    )


def _species_chip_html(species_name: str) -> str:
    img_url = pokemon_image_url(species_name)
    img = (
        f'<img src="{img_url}" loading="lazy" style="width:22px;height:22px;object-fit:contain;'
        f'flex:0 0 auto">'
        if img_url
        else ""
    )
    return (
        f'<span class="rec-species-chip" style="display:inline-flex;align-items:center;gap:4px;'
        f'background:#fff;border:1px solid #e2e2e2;border-radius:999px;'
        f'padding:3px 8px;white-space:nowrap;font-size:12px">'
        f'{img}{html.escape(species_name)}</span>'
    )


def _recommendation_status_html(label: str) -> str:
    colors = {
        "理想": ("#dff2e3", "#2f7a38"),
        "即戦力": ("#e5f0ff", "#245c9e"),
        "実用": ("#fff3cd", "#8a6500"),
        "要育成": ("#fff3cd", "#8a6500"),
        "未所持": ("#f1f1f1", "#666"),
    }
    bg, fg = colors.get(label, ("#f1f1f1", "#666"))
    return (
        f'<span class="rec-status" style="background:{bg};color:{fg};">'
        f'{html.escape(label)}</span>'
    )


def _recommendation_hit_html(row) -> tuple[str, str]:
    """カード内の主役表示と Lv60 指標を返す。"""
    best = row.best_clear_hit or row.best_any_hit
    if not best:
        return (
            '<div class="rec-owned rec-empty">おすすめ種族の所持なし</div>',
            '<div class="rec-metric rec-metric-empty"><span>Lv60期待</span><strong>—</strong></div>',
        )

    support = (
        f'<span>支援 {best.food_supports}</span>'
        if row.best_clear_hit
        else '<span>支援は未判定</span>'
    )
    body = (
        '<div class="rec-owned">'
        f'<div class="rec-owned-name">{html.escape(best.label)}</div>'
        '<div class="rec-owned-meta">'
        f'<span>{html.escape(best.species_name)}</span>'
        f'<span>{html.escape(best.composition)}</span>'
        f'<span>食材 {best.food_score:.1f}%</span>'
        f'{support}'
        '</div>'
        '</div>'
    )
    metric = (
        '<div class="rec-metric">'
        '<span>Lv60期待</span>'
        f'<strong>{best.lv60_target_per_day:.1f}</strong>'
        '<small>個/日</small>'
        '</div>'
    )
    return body, metric


def _ingredient_recommendation_html(rows) -> str:
    parts = []
    for row in rows:
        icon = ingredient_icon_url(row.ingredient_name)
        icon_html = (
            f'<img src="{icon}" loading="lazy" style="width:34px;height:34px;object-fit:contain">'
            if icon
            else ""
        )
        rec_html = "".join(_species_chip_html(name) for name in row.recommended_species)
        status = _recommendation_status_html(row.status_label)
        owned_html, metric_html = _recommendation_hit_html(row)

        parts.append(
            '<article class="rec-card">'
            '<div class="rec-head">'
            f'<div class="rec-icon">{icon_html}</div>'
            '<div class="rec-title-block">'
            f'<div class="rec-title">{html.escape(row.ingredient_name)}</div>'
            f'<div class="rec-status-line">{status}</div>'
            '</div>'
            f'{metric_html}'
            '</div>'
            f'<div class="rec-species-row">{rec_html}</div>'
            f'{owned_html}'
            '</article>'
        )

    return (
        '<style>'
        '.rec-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:10px;}'
        '.rec-card{background:var(--ps-dusk);border:1px solid var(--ps-line);border-radius:12px;'
        'padding:10px;box-shadow:0 2px 6px rgba(90,70,30,.08);min-width:0;}'
        '.rec-head{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:8px;align-items:center;}'
        '.rec-icon{width:38px;height:38px;display:flex;align-items:center;justify-content:center;}'
        '.rec-title{font-weight:800;font-size:.96rem;line-height:1.25;word-break:keep-all;overflow-wrap:anywhere;}'
        '.rec-status-line{margin-top:3px;}'
        '.rec-status{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;font-weight:800;white-space:nowrap;}'
        '.rec-metric{min-width:74px;text-align:right;line-height:1.05;color:var(--ps-ink);}'
        '.rec-metric span{display:block;font-size:10px;color:var(--ps-ink-dim);white-space:nowrap;}'
        '.rec-metric strong{font-size:1.08rem;font-variant-numeric:tabular-nums;}'
        '.rec-metric small{font-size:10px;color:var(--ps-ink-dim);margin-left:1px;white-space:nowrap;}'
        '.rec-metric-empty strong{color:var(--ps-ink-dim);}'
        '.rec-species-row{display:flex;gap:5px;overflow-x:auto;-webkit-overflow-scrolling:touch;padding:8px 0 7px;margin:0 -2px;}'
        '.rec-owned{border-top:1px solid rgba(0,0,0,.08);padding-top:7px;min-width:0;}'
        '.rec-owned-name{font-weight:700;font-size:.86rem;line-height:1.25;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}'
        '.rec-owned-meta{display:flex;flex-wrap:wrap;gap:4px 6px;margin-top:3px;color:var(--ps-ink-dim);font-size:12px;line-height:1.35;}'
        '.rec-owned-meta span{white-space:nowrap;}'
        '.rec-empty{color:var(--ps-ink-dim);font-size:12px;line-height:1.35;}'
        '@media (max-width:480px){.rec-grid{grid-template-columns:1fr;}'
        '.rec-card{border-radius:10px;padding:9px;}'
        '.rec-head{grid-template-columns:auto minmax(0,1fr) auto;}'
        '.rec-title{font-size:.92rem;}'
        '.rec-metric{min-width:68px;}}'
        '</style>'
        f'<div class="rec-grid">{"".join(parts)}</div>'
    )


st.html(c.page_banner("役割", "bag", icon="🧩"))
st.caption(
    "編成を決める前に、ボックス全体で食材・きのみ・スキルの担当が"
    "どこまで埋まっているかを見る。"
)

db.init_db()
owned = [dict(row) for row in db.list_pokemon()]
owned_by_id = {int(p["id"]): p for p in owned}
if not owned:
    st.html(c.empty_state("所持ポケモンがいません。先に「個体登録」から追加してください。"))
    st.stop()

index = _ingredient_index(owned)
food_active = {
    name: [p for p in providers if p.per_day_now > 0]
    for name, providers in index.items()
}
food_holes = [name for name, active in food_active.items() if not active]

audit_field = load_audit_field()
random_favs = load_random_favs()
fav_berries = resolve_fav_berries(audit_field, random_favs)
berry_covs = _berries(owned, tuple(sorted(fav_berries)))
berry_holes = favorite_holes(berry_covs)

skill_covs = _skill_roles(owned, False)
skill_holes = role_holes(skill_covs)

st.html(
    c.stat_tiles(
        [
            c.stat_tile("所持個体", f"{len(owned)}", sub="体"),
            c.stat_tile(
                "食材の穴", f"{len(food_holes)}", sub=f"/{len(index)}種"
            ),
            c.stat_tile(
                "好物きのみの穴", f"{len(berry_holes)}", sub=f"/{len(fav_berries) or '—'}種"
            ),
            c.stat_tile(
                "スキル役割の穴", f"{len(skill_holes)}", sub=f"/{len(skill_covs)}役割"
            ),
        ]
    )
)

food_tab, rec_tab, berry_tab, skill_tab = st.tabs(
    ["🥕 食材", "📖 攻略おすすめ", "🌳 きのみ", "🎯 スキル"]
)


# ── 食材 ────────────────────────────────────────────────────────────────
with food_tab:
    st.caption(
        f"現在のLv・食材構成で供給できる個体を数えています。編成枠の都合で"
        f"**{FOOD_TOP_N}体そろえば充足**、1体なら「あと1体」、0体が穴です。"
    )
    food_rows = [
        {
            "🥕": ingredient_icon_url(name),
            "食材": name,
            "充足": _fill_ratio(len(active), FOOD_TOP_N) * 100,
            "状態": _status_label(len(active), FOOD_TOP_N),
            "供給/日": sum(p.per_day_now for p in active[:FOOD_TOP_N]),
            "即戦力": len(active),
            "将来候補": len(index[name]) - len(active),
        }
        for name, active in food_active.items()
    ]
    food_rows.sort(key=lambda r: (r["充足"], r["供給/日"]))
    _coverage_table(food_rows, icon_col="🥕", height=380)

    if food_holes:
        st.html(
            '<div style="display:flex;flex-wrap:wrap;gap:4px;margin:6px 0">'
            + "".join(c.ingredient_chip(n) for n in food_holes)
            + "</div>"
        )
        st.caption("↑ 現在の担当がゼロの食材。")

    detail_name = st.selectbox(
        "担当個体を見る食材",
        list(index),
        index=list(index).index(food_holes[0]) if food_holes else 0,
        key="hand_food_detail",
        filter_mode=None,  # スマホでキーボードを出さない（食材19件なので検索不要）
        help="穴がある場合は、その先頭を最初に選んでいます。",
    )
    detail_providers = index[detail_name]
    for provider in [p for p in detail_providers if p.per_day_now > 0][:5]:
        pokemon_popover_row(
            owned_by_id.get(int(provider.pokemon_id)),
            label=provider.label,
            img_species=provider.species_name,
            badges_text="即戦力",
            caption=f"{provider.per_day_now:.1f}個/日",
        )
    for provider in [p for p in detail_providers if p.per_day_now <= 0][:3]:
        pokemon_popover_row(
            owned_by_id.get(int(provider.pokemon_id)),
            label=provider.label,
            img_species=provider.species_name,
            badges_text="将来候補",
            caption=(
                f"{provider.slot.upper()}枠・Lv{provider.unlock_lv}解放"
                f"{'済' if provider.unlocked else '前'}"
            ),
        )
    if not detail_providers:
        st.html(c.empty_state("この食材を候補枠に持つ所持個体はいません。"))

    versatile = versatile_mains(index)
    with st.expander(f"複数食材を任せられる主力 — {len(versatile)}体"):
        for main in versatile:
            pokemon_popover_row(
                owned_by_id.get(int(main.pokemon_id)),
                label=main.label,
                img_species=main.species_name,
                badges_text=f"{len(main.duties)}食材",
                caption=" / ".join(
                    f"{name} {daily:.1f}/日" for name, daily in main.duties
                ),
            )


# ── 攻略おすすめ ───────────────────────────────────────────────────────
with rec_tab:
    st.caption(
        "攻略ページでよく挙がる食材ごとのおすすめ種族を、イラスト付きで並べた参照表。"
        "判定は **対象食材を取れる全スロット=理想**、"
        "**Lv30時点で主食材化=即戦力**、**将来2枠以上=実用**。"
        f"その上で **食材軸評価 {80:.0f}% 以上**、さらに **食材支援サブ1本以上** の所持個体を採用しています。"
        " 右端には、その候補をLv60まで育てて食材3枠目が開いた時の1日期待個数も出しています。"
    )
    rec_rows = ingredient_recommendation_rows(owned)
    total_ingredients = len(rec_rows)
    clear_count = sum(1 for r in rec_rows if r.cleared)
    any_count = sum(1 for r in rec_rows if r.best_any_hit)
    st.html(
        c.stat_tiles(
            [
                c.stat_tile("クリア済み", f"{clear_count}", sub=f"/{total_ingredients}食材"),
                c.stat_tile("要育成", f"{any_count - clear_count}", sub=f"/{total_ingredients}食材"),
                c.stat_tile("未所持", f"{total_ingredients - any_count}", sub=f"/{total_ingredients}食材"),
            ]
        )
    )
    st.html(_ingredient_recommendation_html(rec_rows))
    st.caption(
        "※ ここでの上位表示は、攻略おすすめ種族のうち食材軸が十分強い個体を"
        "対象食材の元枠に合わせて 理想 / 即戦力 / 実用 の順で拾った目安。"
        "実運用はレシピや鍋容量でも変わるので、最終判断は食材担当ページと合わせて見るといい。"
    )


# ── きのみ ──────────────────────────────────────────────────────────────
with berry_tab:
    fields = db.list_all_field_records()
    field_names = [f["name"] for f in fields]
    pick_cols = st.columns([2, 3])
    with pick_cols[0]:
        picked_field = st.selectbox(
            "監査フィールド",
            ["（好物なし）"] + field_names,
            index=(field_names.index(audit_field) + 1) if audit_field in field_names else 0,
            key="hand_berry_field",
            filter_mode=None,  # スマホでキーボードを出さない（8件なので検索不要）
            help="好物きのみは獲得エナジーが2倍になるので、どのフィールドで見るかで穴が変わります。",
        )
    chosen_field = None if picked_field == "（好物なし）" else picked_field
    field_rec = next((f for f in fields if f["name"] == chosen_field), None)
    with pick_cols[1]:
        if field_rec and field_rec.get("favorite_berries_random"):
            picked_random = st.multiselect(
                "今週の好みきのみ（最大3種）",
                [b["name"] for b in db.list_all_berry_records()],
                default=random_favs,
                max_selections=3,
                key="hand_berry_random",
            )
        else:
            picked_random = random_favs
    if chosen_field != audit_field or list(picked_random) != list(random_favs):
        save_audit_field(chosen_field)
        save_random_favs(list(picked_random))
        st.cache_data.clear()
        st.rerun()

    st.caption(
        f"好物きのみ（×2）を優先して並べています。編成枠の都合で"
        f"**{BERRY_TOP_N}体そろえば充足**とみなします。"
    )
    berry_rows = [
        {
            "🌳": berry_icon_url(cov.berry["name"]),
            "きのみ": cov.berry["name"] + ("　★好物" if cov.is_favorite else ""),
            "充足": _fill_ratio(len(cov.providers), BERRY_TOP_N) * 100,
            "状態": _status_label(len(cov.providers), BERRY_TOP_N),
            "エナジー/日": cov.top_energy,
            "即戦力": len(cov.providers),
        }
        for cov in berry_covs
    ]
    _coverage_table(berry_rows, icon_col="🌳", height=380)

    if berry_holes:
        st.html(
            '<div style="display:flex;flex-wrap:wrap;gap:4px;margin:6px 0">'
            + "".join(c.berry_chip(n) for n in berry_holes)
            + "</div>"
        )
        st.caption("↑ 好物（×2）なのに担当がゼロのきのみ。ここが一番もったいない。")
    elif fav_berries:
        st.success("好物きのみはすべて担当がいます。")

    berry_names = [cov.berry["name"] for cov in berry_covs]
    berry_detail = st.selectbox(
        "担当個体を見るきのみ",
        berry_names,
        index=berry_names.index(berry_holes[0]) if berry_holes else 0,
        key="hand_berry_detail",
        filter_mode=None,  # スマホでキーボードを出さない（18件なので検索不要）
    )
    cov = next(x for x in berry_covs if x.berry["name"] == berry_detail)
    for provider in cov.providers[:5]:
        pokemon_popover_row(
            owned_by_id.get(int(provider.pokemon_id)),
            label=provider.label,
            img_species=provider.species_name,
            badges_text=f"{provider.energy_per_day:,.0f} en/日",
            caption=f"Lv{provider.level}｜{provider.count_per_day:.1f}個/日",
        )
    if not cov.providers:
        st.html(c.empty_state("このきのみを持つ所持個体はいません。"))


# ── スキル ──────────────────────────────────────────────────────────────
with skill_tab:
    max_skill = st.toggle(
        "メインスキルLv最大の天井で見る",
        key="hand_skill_max",
        help="OFFでは進化後の想定Lv、ONでは育て切った最大Lvで比較します。",
    )
    coverages = _skill_roles(owned, max_skill)
    st.caption(
        f"最終進化後のメインスキルで判定。編成枠の都合で**{TOP_N}体そろえば充足**とみなします。"
    )
    skill_rows = [
        {
            # 担当ゼロだと None がそのまま "None" と描画されるので空文字にする
            "🎯": (pokemon_image_url(cov.top[0].species_name) or "") if cov.top else "",
            "役割": cov.label,
            "充足": _fill_ratio(len(cov.providers), TOP_N) * 100,
            "状態": _status_label(len(cov.providers), TOP_N),
            "即戦力": len(cov.providers),
            "主力": " / ".join(p.label for p in cov.top) or "—",
        }
        for cov in coverages
    ]
    _coverage_table(skill_rows, icon_col="🎯", height=360)

    if skill_holes:
        st.warning("担当がいない役割：" + " / ".join(skill_holes))

    # 以前は役割9件ぶんの expander を全部畳んで縦に積んでいた。
    # 均質なカードの等間隔積みは読みにくいので、1つ選んで中身を出す形にする。
    labels = [cov.label for cov in coverages]
    picked_role = st.selectbox(
        "担当個体を見る役割",
        labels,
        index=labels.index(skill_holes[0]) if skill_holes else 0,
        key="hand_skill_detail",
        filter_mode=None,  # スマホでキーボードを出さない（9件なので検索不要）
    )
    role = next(x for x in coverages if x.label == picked_role)
    st.caption("対象スキル：" + " / ".join(sorted(role.categories)))
    if not role.top:
        st.html(c.empty_state("この役割を担える所持個体はいません。"))
    for provider in role.top:
        pokemon_popover_row(
            owned_by_id.get(int(provider.pokemon_id)),
            label=provider.label,
            img_species=provider.species_name,
            badges_text=f"育成後 {provider.potential_rank}",
            caption=(
                f"{provider.final_species}｜スキル軸 {provider.skill_axis:.0f}"
                f"｜MSLv{provider.main_skill_level}"
            ),
        )
