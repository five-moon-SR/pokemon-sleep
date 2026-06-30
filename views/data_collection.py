import html
from collections.abc import Callable

import pandas as pd
import streamlit as st

import db
from image_utils import (
    BERRY_ICON_DIR,
    FIELD_ICON_DIR,
    INGREDIENT_ICON_DIR,
    MAIN_SKILL_ICON_DIR,
    RECIPE_ICON_DIR,
    icon_data_url as _icon_data_url,
)

SUBSKILL_RARITY_LABELS = {"gold": "金", "blue": "青", "white": "白"}
SUBSKILL_RARITY_COLORS = {
    "gold":  {"bg": "#fee570", "fg": "#722d00"},
    "blue":  {"bg": "#d5edfd", "fg": "#001541"},
    "white": {"bg": "#f3f3f3", "fg": "#722d00"},
}

RECIPE_CATEGORY_LABELS = {
    "curry_stew": "カレー・シチュー",
    "salad": "サラダ",
    "drink_dessert": "デザート・ドリンク",
}

# カテゴリごとの色テーマ（淡い背景＋濃い目の左ボーダー）
RECIPE_CATEGORY_COLORS = {
    "curry_stew":    {"bg": "#fdecea", "border": "#d34a3a", "tag_bg": "#f5b6ad"},
    "salad":         {"bg": "#e8f4ea", "border": "#3a9a4f", "tag_bg": "#b6dcc0"},
    "drink_dessert": {"bg": "#e7eef8", "border": "#3a6cd3", "tag_bg": "#b6c8e6"},
}


@st.cache_data
def _ingredient_icon_map() -> dict[str, str]:
    """食材名 → アイコンファイル名 のマップ（レシピ表のチップ表示用）。"""
    return {
        r["name"]: r["icon"]
        for r in db.list_all_ingredient_records()
        if r.get("icon")
    }


st.title("🗂 データ集")
st.caption(
    "ゲーム内データの参照ページ。各データが揃い次第、対応するタブの中身を埋めていく。"
)


def render_berry() -> None:
    records = db.list_all_berry_records()
    if not records:
        st.info(
            "きのみデータが未登録。`python scripts/build_berry.py` を実行してください。"
        )
        return

    rows = [
        {
            "画像": _icon_data_url(str(BERRY_ICON_DIR), r.get("icon")),
            "名前": r.get("name"),
            "タイプ": r.get("type"),
            "基礎エナジー": r.get("base_energy"),
            "好物フィールド": r.get("preferred_field"),
            "説明": r.get("description"),
        }
        for r in records
    ]
    df = pd.DataFrame(rows)

    filter_cols = st.columns([2, 2])
    with filter_cols[0]:
        keyword = st.text_input(
            "🔍 名前で検索", placeholder="例: キーのみ", key="berry_kw"
        )
    with filter_cols[1]:
        types = sorted(t for t in df["タイプ"].dropna().unique())
        sel_types = st.multiselect("タイプ", types, key="berry_types")

    filtered = df
    if keyword:
        filtered = filtered[filtered["名前"].str.contains(keyword, na=False)]
    if sel_types:
        filtered = filtered[filtered["タイプ"].isin(sel_types)]

    st.caption(f"{len(filtered)} / {len(df)} 件")
    st.dataframe(
        filtered,
        hide_index=True,
        use_container_width=True,
        column_config={
            "画像": st.column_config.ImageColumn("", width="small"),
        },
    )


def render_ingredient() -> None:
    records = db.list_all_ingredient_records()
    if not records:
        st.info(
            "食材データが未登録。`python scripts/build_ingredient.py` を実行してください。"
        )
        return

    rows = [
        {
            "画像": _icon_data_url(str(INGREDIENT_ICON_DIR), r.get("icon")),
            "名前": r.get("name"),
            "基礎エナジー": r.get("base_energy"),
            "実質エナジー最大": r.get("effective_max_energy"),
            "数ボーナス最大%": r.get("max_bonus_pct"),
            "ボーナス対応レシピ": "、".join(r.get("max_bonus_recipes") or []),
            "かけら売価": r.get("dream_shard_price"),
            "説明": r.get("description"),
        }
        for r in records
    ]
    df = pd.DataFrame(rows)

    filter_cols = st.columns([3, 2])
    with filter_cols[0]:
        keyword = st.text_input(
            "🔍 名前で検索", placeholder="例: とくせんリンゴ", key="ing_kw"
        )
    with filter_cols[1]:
        sort_by = st.selectbox(
            "並び替え",
            options=[
                "登録順",
                "基礎エナジー（高→低）",
                "実質エナジー最大（高→低）",
                "かけら売価（高→低）",
            ],
            key="ing_sort",
        )

    filtered = df
    if keyword:
        filtered = filtered[filtered["名前"].str.contains(keyword, na=False)]
    if sort_by == "基礎エナジー（高→低）":
        filtered = filtered.sort_values("基礎エナジー", ascending=False, na_position="last")
    elif sort_by == "実質エナジー最大（高→低）":
        filtered = filtered.sort_values("実質エナジー最大", ascending=False, na_position="last")
    elif sort_by == "かけら売価（高→低）":
        filtered = filtered.sort_values("かけら売価", ascending=False, na_position="last")

    st.caption(f"{len(filtered)} / {len(df)} 件")
    st.dataframe(
        filtered,
        hide_index=True,
        use_container_width=True,
        column_config={
            "画像": st.column_config.ImageColumn("", width="small"),
        },
    )


def render_field() -> None:
    records = db.list_all_field_records()
    if not records:
        st.info(
            "フィールドデータが未登録。`python scripts/build_field.py` を実行してください。"
        )
        return

    def _berries_text(r: dict) -> str:
        if r.get("favorite_berries_random"):
            return "ランダム"
        return "、".join(
            f"{b['name']}({b['type']})" for b in r.get("favorite_berries", [])
        )

    rows = [
        {
            "画像": _icon_data_url(str(FIELD_ICON_DIR), r.get("icon")),
            "種別": "通常" if r.get("type") == "normal" else "EX",
            "No.": r.get("no"),
            "名前": r.get("name"),
            "アンロック条件": r.get("unlock_condition"),
            "好みのきのみ": _berries_text(r),
            "適正SP": r.get("recommended_sp_min"),
        }
        for r in records
    ]
    df = pd.DataFrame(rows)

    sel_type = st.multiselect(
        "種別", ["通常", "EX"], key="field_type"
    )
    filtered = df
    if sel_type:
        filtered = filtered[filtered["種別"].isin(sel_type)]

    st.caption(f"{len(filtered)} / {len(df)} 件")
    st.dataframe(
        filtered,
        hide_index=True,
        use_container_width=True,
        column_config={
            "画像": st.column_config.ImageColumn("", width="small"),
            "適正SP": st.column_config.NumberColumn(format="%d 以上"),
        },
    )


def _ingredient_chips_html(items: list[dict]) -> str:
    """食材リストを「アイコン+名前×個数」のチップ列にする。"""
    if not items:
        return '<span style="color:#999">—</span>'
    icon_map = _ingredient_icon_map()
    parts: list[str] = []
    for it in items:
        name = it.get("name", "")
        count = it.get("count", "?")
        icon = icon_map.get(name)
        url = _icon_data_url(str(INGREDIENT_ICON_DIR), icon)
        img = (
            f'<img src="{url}" style="width:18px;height:18px;vertical-align:middle;margin-right:2px">'
            if url
            else ""
        )
        parts.append(
            f'<span style="display:inline-flex;align-items:center;'
            f'background:#fff;border:1px solid #e2e2e2;border-radius:10px;'
            f'padding:1px 6px;margin:1px 3px 1px 0;white-space:nowrap;font-size:12px">'
            f'{img}{html.escape(name)}<span style="color:#666;margin-left:3px">×{count}</span>'
            f'</span>'
        )
    return "".join(parts)


def _fmt_num(n) -> str:
    if n is None or pd.isna(n):
        return '<span style="color:#bbb">—</span>'
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return str(n)


def _recipe_row_html(r: dict) -> str:
    cat = r.get("category") or ""
    style = RECIPE_CATEGORY_COLORS.get(cat, {"bg": "#fff", "border": "#ccc", "tag_bg": "#eee"})
    label = RECIPE_CATEGORY_LABELS.get(cat, cat)

    img_url = _icon_data_url(str(RECIPE_ICON_DIR), r.get("icon"))
    img_html = (
        f'<img src="{img_url}" style="width:42px;height:42px;object-fit:contain">'
        if img_url
        else '<div style="width:42px;height:42px;background:#f0f0f0;border-radius:4px"></div>'
    )

    tag_html = (
        f'<span style="background:{style["tag_bg"]};color:#333;'
        f'padding:1px 6px;border-radius:8px;font-size:11px;white-space:nowrap">'
        f'{html.escape(label)}</span>'
    )

    desc = r.get("description") or ""
    desc_html = (
        f'<div style="color:#666;font-size:11px;margin-top:2px">{html.escape(desc)}</div>'
        if desc
        else ""
    )

    return (
        f'<tr style="background:{style["bg"]};border-left:4px solid {style["border"]}">'
        f'<td style="border-left:4px solid {style["border"]};padding:6px 8px">{img_html}</td>'
        f'<td style="padding:6px 8px">{tag_html}</td>'
        f'<td style="padding:6px 8px;text-align:right;color:#666">{r.get("no", "")}</td>'
        f'<td style="padding:6px 8px"><div style="font-weight:600">{html.escape(r.get("name") or "")}</div>{desc_html}</td>'
        f'<td style="padding:6px 8px;max-width:340px">{_ingredient_chips_html(r.get("ingredients") or [])}</td>'
        f'<td style="padding:6px 8px;text-align:right">{_fmt_num(r.get("total_ingredients"))}</td>'
        f'<td style="padding:6px 8px;text-align:right">{_fmt_num(r.get("energy_lv1"))}</td>'
        f'<td style="padding:6px 8px;text-align:right">{_fmt_num(r.get("energy_lv30"))}</td>'
        f'<td style="padding:6px 8px;text-align:right;font-weight:600">{_fmt_num(r.get("energy_lv60"))}</td>'
        f'<td style="padding:6px 8px;text-align:right">{_fmt_num(r.get("energy_max_pot69"))}</td>'
        f'<td style="padding:6px 8px;text-align:right">{_fmt_num(r.get("energy_max_pot507"))}</td>'
        f'</tr>'
    )


_RECIPE_TABLE_CSS = """
<style>
.recipe-table { border-collapse: collapse; width: 100%; font-size: 13px; }
.recipe-table thead th {
  background: #f6f6f6; text-align: left; padding: 6px 8px;
  border-bottom: 2px solid #ddd; position: sticky; top: 0; z-index: 1;
}
.recipe-table tbody tr { border-bottom: 1px solid #eee; }
.recipe-wrap { overflow-x: auto; max-height: 720px; overflow-y: auto; border-radius: 6px; }
</style>
"""


def render_recipe() -> None:
    records = db.list_all_recipe_records()
    if not records:
        st.info(
            "レシピデータが未登録。`python scripts/build_recipe.py` を実行してください。"
        )
        return

    filter_cols = st.columns([2, 2, 2])
    with filter_cols[0]:
        keyword = st.text_input(
            "🔍 名前で検索", placeholder="例: ニンジャ", key="recipe_kw"
        )
    with filter_cols[1]:
        sel_cats = st.multiselect(
            "カテゴリ",
            list(RECIPE_CATEGORY_LABELS.values()),
            key="recipe_cats",
        )
    with filter_cols[2]:
        sort_by = st.selectbox(
            "並び替え",
            options=[
                "登録順（カテゴリ→No.）",
                "Lv1エナジー（高→低）",
                "Lv60エナジー（高→低）",
                "なべ507エナジー（高→低）",
                "食材合計（高→低）",
            ],
            key="recipe_sort",
        )

    filtered = list(records)
    if keyword:
        filtered = [r for r in filtered if keyword in (r.get("name") or "")]
    if sel_cats:
        cat_keys = {k for k, v in RECIPE_CATEGORY_LABELS.items() if v in sel_cats}
        filtered = [r for r in filtered if r.get("category") in cat_keys]

    def _key(field: str):
        return lambda r: (r.get(field) is None, -(r.get(field) or 0))

    if sort_by == "Lv1エナジー（高→低）":
        filtered.sort(key=_key("energy_lv1"))
    elif sort_by == "Lv60エナジー（高→低）":
        filtered.sort(key=_key("energy_lv60"))
    elif sort_by == "なべ507エナジー（高→低）":
        filtered.sort(key=_key("energy_max_pot507"))
    elif sort_by == "食材合計（高→低）":
        filtered.sort(key=_key("total_ingredients"))

    st.caption(f"{len(filtered)} / {len(records)} 件")

    header = (
        '<thead><tr>'
        '<th></th><th>カテゴリ</th><th style="text-align:right">No.</th>'
        '<th>料理名</th><th>必要食材</th>'
        '<th style="text-align:right">合計</th>'
        '<th style="text-align:right">Lv1</th>'
        '<th style="text-align:right">Lv30</th>'
        '<th style="text-align:right">Lv60</th>'
        '<th style="text-align:right">なべ69</th>'
        '<th style="text-align:right">なべ507</th>'
        '</tr></thead>'
    )
    body = "<tbody>" + "".join(_recipe_row_html(r) for r in filtered) + "</tbody>"
    table_html = (
        _RECIPE_TABLE_CSS
        + '<div class="recipe-wrap"><table class="recipe-table">'
        + header + body
        + '</table></div>'
    )
    st.markdown(table_html, unsafe_allow_html=True)


def render_main_skill() -> None:
    records = db.list_all_main_skill_records()
    if not records:
        st.info(
            "メインスキルデータが未登録。`python scripts/build_main_skill.py` を実行してください。"
        )
        return

    rows = [
        {
            "アイコン": _icon_data_url(str(MAIN_SKILL_ICON_DIR), r.get("category_icon")),
            "分類": r.get("category"),
            "スキル名": r.get("name"),
            "説明": r.get("description"),
            "最大Lv": r.get("max_level"),
        }
        for r in records
    ]
    df = pd.DataFrame(rows)

    filter_cols = st.columns([2, 2])
    with filter_cols[0]:
        keyword = st.text_input(
            "🔍 スキル名／説明で検索", placeholder="例: エナジー", key="ms_kw"
        )
    with filter_cols[1]:
        cats = sorted(df["分類"].dropna().unique())
        sel_cats = st.multiselect("分類", cats, key="ms_cats")

    filtered = df
    if keyword:
        mask = (
            filtered["スキル名"].str.contains(keyword, na=False)
            | filtered["説明"].str.contains(keyword, na=False)
            | filtered["分類"].str.contains(keyword, na=False)
        )
        filtered = filtered[mask]
    if sel_cats:
        filtered = filtered[filtered["分類"].isin(sel_cats)]

    st.caption(f"{len(filtered)} / {len(df)} 件")
    st.dataframe(
        filtered,
        hide_index=True,
        use_container_width=True,
        column_config={
            "アイコン": st.column_config.ImageColumn("", width="small"),
            "最大Lv": st.column_config.NumberColumn(format="%d"),
        },
    )


def _subskill_row_html(r: dict) -> str:
    rarity = r.get("rarity") or "white"
    style = SUBSKILL_RARITY_COLORS.get(rarity, SUBSKILL_RARITY_COLORS["white"])
    label = SUBSKILL_RARITY_LABELS.get(rarity, rarity)

    star = (
        '<span title="サブスキルのたねでランクアップ可" '
        'style="color:#d99800;font-weight:600;margin-right:4px">★</span>'
        if r.get("can_upgrade_with_seed")
        else ""
    )
    max_badge = (
        '<span style="background:#fff2cc;color:#7a5a00;font-size:10px;'
        'padding:1px 5px;border-radius:6px;margin-left:6px;'
        'border:1px solid #e7c878">MAX</span>'
        if r.get("is_max_rank")
        else ""
    )
    rarity_badge = (
        f'<span style="background:{style["bg"]};color:{style["fg"]};'
        f'font-weight:600;padding:2px 8px;border-radius:10px;font-size:11px;'
        f'white-space:nowrap">{html.escape(label)}</span>'
    )

    effect = r.get("effect_value") or ""
    effect_html = (
        f'<span style="font-weight:600">{html.escape(effect)}</span>'
        if r.get("is_max_rank")
        else html.escape(effect)
    )

    return (
        f'<tr>'
        f'<td style="padding:6px 8px">{rarity_badge}</td>'
        f'<td style="padding:6px 8px">{star}{html.escape(r.get("name") or "")}{max_badge}</td>'
        f'<td style="padding:6px 8px;text-align:right">{effect_html}</td>'
        f'<td style="padding:6px 8px;color:#444">{html.escape(r.get("description") or "")}</td>'
        f'</tr>'
    )


_SUBSKILL_TABLE_CSS = """
<style>
.subskill-table { border-collapse: collapse; width: 100%; font-size: 13px; }
.subskill-table thead th {
  background: #f6f6f6; text-align: left; padding: 6px 8px;
  border-bottom: 2px solid #ddd;
}
.subskill-table tbody tr { border-bottom: 1px solid #eee; }
.subskill-table tbody tr:hover { background: #fafafa; }
</style>
"""


def render_subskill() -> None:
    records = db.list_all_subskill_records()
    if not records:
        st.info(
            "サブスキルデータが未登録。`python scripts/build_subskill.py` を実行してください。"
        )
        return

    filter_cols = st.columns([2, 2, 2])
    with filter_cols[0]:
        keyword = st.text_input(
            "🔍 名前で検索", placeholder="例: スピード", key="ss_kw"
        )
    with filter_cols[1]:
        sel_rarities = st.multiselect(
            "レア度",
            list(SUBSKILL_RARITY_LABELS.values()),
            key="ss_rarity",
        )
    with filter_cols[2]:
        sel_flags = st.multiselect(
            "条件",
            ["カテゴリ最高ランクのみ", "サブスキルのたねでランクアップ可のみ"],
            key="ss_flag",
        )

    filtered = list(records)
    if keyword:
        filtered = [
            r for r in filtered
            if keyword in (r.get("name") or "")
            or keyword in (r.get("description") or "")
        ]
    if sel_rarities:
        rarity_keys = {
            k for k, v in SUBSKILL_RARITY_LABELS.items() if v in sel_rarities
        }
        filtered = [r for r in filtered if r.get("rarity") in rarity_keys]
    if "カテゴリ最高ランクのみ" in sel_flags:
        filtered = [r for r in filtered if r.get("is_max_rank")]
    if "サブスキルのたねでランクアップ可のみ" in sel_flags:
        filtered = [r for r in filtered if r.get("can_upgrade_with_seed")]

    st.caption(f"{len(filtered)} / {len(records)} 件")

    header = (
        '<thead><tr>'
        '<th>レア度</th><th>スキル名</th>'
        '<th style="text-align:right">効果量</th><th>説明</th>'
        '</tr></thead>'
    )
    body = "<tbody>" + "".join(_subskill_row_html(r) for r in filtered) + "</tbody>"
    table_html = (
        _SUBSKILL_TABLE_CSS
        + '<table class="subskill-table">' + header + body + '</table>'
    )
    st.markdown(table_html, unsafe_allow_html=True)
    st.caption(
        "★ = サブスキルのたねでランクアップ可 ／ MAX = 同系統で効果量が最大"
    )


# 拡張ポイント: ここに (タブ名, 描画関数) を追加すれば自動でタブが増える。
# 描画関数は引数なし。未実装は None にしておけば「未実装」表示が出る。
SECTIONS: list[tuple[str, Callable[[], None] | None]] = [
    ("きのみ", render_berry),
    ("食材", render_ingredient),
    ("レシピ", render_recipe),
    ("メインスキル", render_main_skill),
    ("サブスキル", render_subskill),
    ("フィールド", render_field),
]

tabs = st.tabs([name for name, _ in SECTIONS])
for tab, (name, render_fn) in zip(tabs, SECTIONS):
    with tab:
        if render_fn is None:
            st.info(f"「{name}」のデータはまだ未登録です。データが揃い次第ここに表示します。")
        else:
            render_fn()
