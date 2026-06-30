import pandas as pd
import streamlit as st

import db
from image_utils import berry_icon_url, ingredient_icon_url

st.title("📚 全ポケデータ")

records = db.list_all_master_records()
if not records:
    st.warning(
        "マスターデータが見つかりません。"
        "`python scripts/build_master.py` を実行してください。"
    )
    st.stop()


def _ing_text(ing: dict | None) -> str:
    if not ing or not ing.get("name"):
        return ""
    qty = "/".join(str(q) for q in ing.get("qty", []))
    return f"{ing['name']} {qty}" if qty else ing["name"]


def _ing_qty_at(ing: dict | None, idx: int) -> int | None:
    if not ing:
        return None
    qty = ing.get("qty") or []
    return qty[idx] if idx < len(qty) else None


# 所持ポケモンの集計（同種族で複数個体登録されてる場合は数として保持）
owned_counts: dict[str, int] = {}
for owned in db.list_pokemon():
    name = owned["species_name"]
    owned_counts[name] = owned_counts.get(name, 0) + 1

# DataFrame 構築 -------------------------------------------------------------
rows = []
for r in records:
    berry = r.get("berry") or {}
    ings = r.get("ingredients") or {}
    a = ings.get("a") or {}
    b = ings.get("b") or {}
    c = ings.get("c") or {}
    name = r.get("species_name")
    rows.append(
        {
            "所持": owned_counts.get(name, 0),
            "図鑑No": r.get("dex_no"),
            "種族名": name,
            "睡眠": r.get("sleep_type"),
            "得意": r.get("specialty"),
            "メインスキル": r.get("main_skill"),
            "🌳": berry_icon_url(berry.get("name")),
            "きのみ": berry.get("name"),
            "きのみ個数": berry.get("qty"),
            "🥕A": ingredient_icon_url(a.get("name")),
            "食材A": _ing_text(a),
            "🥕B": ingredient_icon_url(b.get("name")),
            "食材B": _ing_text(b),
            "🥕C": ingredient_icon_url(c.get("name")),
            "食材C": _ing_text(c),
            "_食材A名": a.get("name"),
            "_食材B名": b.get("name"),
            "_食材C名": c.get("name"),
            "基準秒": r.get("base_assist_seconds"),
            "食材確率%": r.get("food_drop_rate"),
            "スキル確率%": r.get("main_skill_rate"),
        }
    )
df_full = pd.DataFrame(rows)

# 食材名・きのみ名の選択肢（_xxx カラムから集計、Aだけでなく全枠から拾う）
all_ingredient_names: list[str] = sorted(
    {
        n
        for col in ("_食材A名", "_食材B名", "_食材C名")
        for n in df_full[col].dropna().unique()
    }
)
all_berries: list[str] = sorted(df_full["きのみ"].dropna().unique())
all_specialties: list[str] = sorted(df_full["得意"].dropna().unique())
all_sleep_types: list[str] = sorted(df_full["睡眠"].dropna().unique())
all_main_skills: list[str] = sorted(df_full["メインスキル"].dropna().unique())

# 絞り込みUI ---------------------------------------------------------------
with st.expander("🔍 絞り込み・並び替え", expanded=True):
    row1 = st.columns([2, 2, 2, 2, 2])
    with row1[0]:
        keyword = st.text_input("種族名で検索", placeholder="例: ピカチュウ")
    with row1[1]:
        sel_specialty = st.multiselect("得意", all_specialties)
    with row1[2]:
        sel_sleep = st.multiselect("睡眠", all_sleep_types)
    with row1[3]:
        sel_skill = st.multiselect("メインスキル", all_main_skills)
    with row1[4]:
        owned_count_total = sum(1 for v in owned_counts.values() if v > 0)
        ownership_filter = st.radio(
            f"所持状況（{owned_count_total}/{len(records)}種）",
            ["すべて", "所持のみ", "未所持のみ"],
            horizontal=False,
        )

    row2 = st.columns([3, 3])
    with row2[0]:
        sel_ingredients = st.multiselect(
            "食材（A/B/Cいずれかに含むもの）",
            all_ingredient_names,
            help="複数選ぶと「いずれかを持つ」種族を表示（OR条件）",
        )
    with row2[1]:
        sel_berries = st.multiselect("きのみ", all_berries)

    st.caption("数値レンジ")
    row3 = st.columns(3)
    with row3[0]:
        min_food = st.slider(
            "食材確率% 下限",
            min_value=0.0,
            max_value=40.0,
            value=0.0,
            step=0.5,
        )
    with row3[1]:
        min_skill = st.slider(
            "スキル確率% 下限",
            min_value=0.0,
            max_value=10.0,
            value=0.0,
            step=0.1,
        )
    with row3[2]:
        max_assist = st.slider(
            "基準秒 上限",
            min_value=2000,
            max_value=7000,
            value=7000,
            step=100,
        )

    st.caption("並び替え（上から順に第1キー → 第2キー）")
    sortable_cols = [
        "図鑑No", "種族名", "睡眠", "得意", "メインスキル",
        "きのみ", "基準秒", "食材確率%", "スキル確率%",
    ]
    row4 = st.columns([2, 1, 2, 1])
    with row4[0]:
        sort_key1 = st.selectbox("並び替え1", options=sortable_cols, index=0)
    with row4[1]:
        sort_dir1 = st.radio("方向1", ["昇順", "降順"], horizontal=True, key="dir1")
    with row4[2]:
        sort_key2 = st.selectbox(
            "並び替え2",
            options=["（なし）", *sortable_cols],
            index=0,
            key="sort_key2",
        )
    with row4[3]:
        sort_dir2 = st.radio("方向2", ["昇順", "降順"], horizontal=True, key="dir2")


# フィルタ適用 -------------------------------------------------------------
filtered = df_full.copy()
if keyword:
    filtered = filtered[filtered["種族名"].str.contains(keyword, na=False)]
if sel_specialty:
    filtered = filtered[filtered["得意"].isin(sel_specialty)]
if sel_sleep:
    filtered = filtered[filtered["睡眠"].isin(sel_sleep)]
if sel_skill:
    filtered = filtered[filtered["メインスキル"].isin(sel_skill)]
if sel_ingredients:
    mask = (
        filtered["_食材A名"].isin(sel_ingredients)
        | filtered["_食材B名"].isin(sel_ingredients)
        | filtered["_食材C名"].isin(sel_ingredients)
    )
    filtered = filtered[mask]
if sel_berries:
    filtered = filtered[filtered["きのみ"].isin(sel_berries)]
if min_food > 0:
    filtered = filtered[filtered["食材確率%"].fillna(-1) >= min_food]
if min_skill > 0:
    filtered = filtered[filtered["スキル確率%"].fillna(-1) >= min_skill]
if max_assist < 7000:
    filtered = filtered[filtered["基準秒"].fillna(99999) <= max_assist]
if ownership_filter == "所持のみ":
    filtered = filtered[filtered["所持"] > 0]
elif ownership_filter == "未所持のみ":
    filtered = filtered[filtered["所持"] == 0]

# ソート適用
sort_keys = [sort_key1]
sort_asc = [sort_dir1 == "昇順"]
if sort_key2 != "（なし）":
    sort_keys.append(sort_key2)
    sort_asc.append(sort_dir2 == "昇順")
filtered = filtered.sort_values(by=sort_keys, ascending=sort_asc, na_position="last")

# 表示用カラム（内部用 _xxx を落とす）
display_cols = [c for c in filtered.columns if not c.startswith("_")]


def _style_owned(df: pd.DataFrame):
    """所持済みの行を薄く色付け。Streamlit dataframe にそのまま渡せる Styler を返す。"""
    def _row_style(row: pd.Series) -> list[str]:
        if row.get("所持", 0) and row["所持"] > 0:
            return ["background-color: #e8f5e9"] * len(row)
        return [""] * len(row)
    return df.style.apply(_row_style, axis=1)


_IMG_COL_CONFIG = {
    "🌳": st.column_config.ImageColumn("🌳", width="small"),
    "🥕A": st.column_config.ImageColumn("🥕A", width="small"),
    "🥕B": st.column_config.ImageColumn("🥕B", width="small"),
    "🥕C": st.column_config.ImageColumn("🥕C", width="small"),
}


# タブ切替 -----------------------------------------------------------------
tab_all, tab_by_skill, tab_by_specialty = st.tabs(
    ["🌐 全体", "⚡ メインスキル別", "🍱 得意別"]
)

with tab_all:
    st.caption(f"{len(filtered)} / {len(df_full)} 件　（緑背景=所持済）")
    event = st.dataframe(
        _style_owned(filtered[display_cols]),
        hide_index=True,
        use_container_width=True,
        height=600,
        on_select="rerun",
        selection_mode="single-row",
        key="master_table",
        column_config=_IMG_COL_CONFIG,
    )

    # 詳細パネル -----------------------------------------------------------
    selected_rows = event.selection.rows if event and event.selection else []
    if selected_rows:
        idx = selected_rows[0]
        row = filtered.iloc[idx]
        species_name = row["種族名"]
        rec = db.get_species_data(species_name)
        if rec:
            st.divider()
            st.subheader(f"📌 {species_name}（図鑑No.{rec['dex_no']}）")
            d_cols = st.columns(4)
            d_cols[0].metric("睡眠", rec["sleep_type"])
            d_cols[1].metric("得意", rec["specialty"])
            d_cols[2].metric(
                "食材確率",
                f"{rec.get('food_drop_rate')}%" if rec.get("food_drop_rate") is not None else "未掲載",
            )
            d_cols[3].metric(
                "スキル確率",
                f"{rec.get('main_skill_rate')}%" if rec.get("main_skill_rate") is not None else "未掲載",
            )

            st.markdown(
                f"⚡ **メインスキル**: {rec['main_skill']}　／　"
                f"⏱ **基準お手伝い時間**: {rec['base_assist_seconds']}秒"
            )

            berry = rec["berry"]
            st.markdown(f"🌳 **きのみ**: {berry['name']} ×{berry['qty']}")

            ings = rec["ingredients"]
            st.markdown("🥕 **食材スロット仕様**")
            ing_table = []
            for slot_label, slot_idx, key in [
                ("スロット1（Lv1〜・確定）", 0, "a"),
                ("スロット2（Lv30〜・抽選）", 1, "a"),
                ("スロット2（Lv30〜・抽選）", 0, "b"),
                ("スロット3（Lv60〜・抽選）", 2, "a"),
                ("スロット3（Lv60〜・抽選）", 1, "b"),
                ("スロット3（Lv60〜・抽選）", 0, "c"),
            ]:
                ing = ings.get(key)
                qty = _ing_qty_at(ing, slot_idx)
                if ing and qty is not None:
                    ing_table.append(
                        {"スロット": slot_label, "食材": ing["name"], "個数": qty}
                    )
            if ing_table:
                st.dataframe(
                    pd.DataFrame(ing_table),
                    hide_index=True,
                    use_container_width=False,
                )

            # 同名種族（形態違い）の表示
            base_name = species_name.split("(")[0]
            forms = [
                r for r in records
                if r["species_name"].startswith(base_name)
                and r["species_name"] != species_name
            ]
            if forms:
                st.caption("関連する形態違い")
                for f in forms:
                    st.markdown(f"- {f['species_name']}（No.{f['dex_no']}）")

with tab_by_skill:
    st.caption("メインスキルごとにグループ化（折りたたみ・緑背景=所持済）")
    for skill in sorted(filtered["メインスキル"].dropna().unique()):
        group = filtered[filtered["メインスキル"] == skill]
        with st.expander(f"⚡ {skill}（{len(group)}種）"):
            st.dataframe(
                _style_owned(group[display_cols]),
                hide_index=True,
                use_container_width=True,
                column_config=_IMG_COL_CONFIG,
            )

with tab_by_specialty:
    spec_tabs = st.tabs([f"{s}（{len(filtered[filtered['得意'] == s])}）" for s in all_specialties])
    for tab, spec in zip(spec_tabs, all_specialties):
        with tab:
            group = filtered[filtered["得意"] == spec]
            st.dataframe(
                _style_owned(group[display_cols]),
                hide_index=True,
                use_container_width=True,
                height=600,
                column_config=_IMG_COL_CONFIG,
            )
