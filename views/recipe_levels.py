"""料理レベルの一覧編集ページ。

編成ページには「いま選んでいる主料理1品」のレベル欄しか無く、
作り込んだ料理をまとめて入れ直す手段が無かった。ここで全料理を一覧し、
表の中で直接 Lv を打ち込んで一括保存する。

料理エナジーは Lv1 → Lv70 で最大3.58倍まで動く（utils/recipe_level.py）。
つまりここの入力は編成の最適解そのものを動かすので、保存時は
料理エナジーに依存する集計キャッシュを全部落とす。
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import db
from image_utils import recipe_icon_url
from ui import components as c
from utils import recipe_level
from utils.party_logic import RECIPE_CATEGORY_LABELS

st.html(c.page_banner("料理レベル", "cyan", icon="🍳"))

if recipe_level.load_error():
    st.warning(
        "料理レベルの設定が読み込めませんでした。全料理をLv1として計算しています"
        f"（{recipe_level.load_error()}）。"
    )

saved = recipe_level.load_recipe_levels()
records = [r for r in db.list_all_recipe_records() if recipe_level.base_energy(r) > 0]

st.caption(
    f"ゲーム内の料理レベルを入れる場所。登録済み **{len(saved)}件** / 全{len(records)}品。"
    "　ここに無い（Lv1のままの）料理は「まだ作り込んでいない」として計算します。"
)

# ── 絞り込み ──────────────────────────────────────────────────────────
f1, f2 = st.columns([3, 2])
with f1:
    cats = st.multiselect(
        "カテゴリ",
        list(RECIPE_CATEGORY_LABELS),
        default=list(RECIPE_CATEGORY_LABELS),
        format_func=lambda k: RECIPE_CATEGORY_LABELS[k],
    )
with f2:
    scope = st.segmented_control(
        "表示",
        ["すべて", "登録済みのみ", "未登録のみ"],
        default="すべて",
        key="recipe_level_scope",
    ) or "すべて"

query = st.text_input("料理名で絞り込み", placeholder="例: ねっとう", key="recipe_level_q").strip()

rows = []
for r in records:
    name = r.get("name") or ""
    if r.get("category") not in cats:
        continue
    if query and query not in name:
        continue
    lv = saved.get(name, recipe_level.MIN_LEVEL)
    registered = name in saved
    if scope == "登録済みのみ" and not registered:
        continue
    if scope == "未登録のみ" and registered:
        continue
    rows.append(
        {
            "icon": recipe_icon_url(name),
            "料理": name,
            "カテゴリ": RECIPE_CATEGORY_LABELS.get(r.get("category"), r.get("category") or ""),
            "Lv": int(lv),
            "倍率": recipe_level.level_multiplier(lv),
            "いまのエナジー": round(recipe_level.recipe_energy(r, lv)),
            "Lv70なら": round(recipe_level.recipe_energy(r, recipe_level.MAX_LEVEL)),
        }
    )

if not rows:
    st.html(c.empty_state("条件に合う料理がありません。"))
    st.stop()

df = pd.DataFrame(rows).sort_values("Lv70なら", ascending=False).reset_index(drop=True)

st.caption("表の **Lv 列を直接編集**して、下の保存ボタンを押してください（1〜70）。")
edited = st.data_editor(
    df,
    hide_index=True,
    use_container_width=True,
    height=min(620, 44 + 36 * len(df)),
    disabled=["icon", "料理", "カテゴリ", "倍率", "いまのエナジー", "Lv70なら"],
    column_config={
        "icon": st.column_config.ImageColumn("", width="small"),
        "料理": st.column_config.TextColumn("料理", width="medium"),
        "カテゴリ": st.column_config.TextColumn("カテゴリ", width="small"),
        "Lv": st.column_config.NumberColumn(
            "Lv",
            min_value=recipe_level.MIN_LEVEL,
            max_value=recipe_level.MAX_LEVEL,
            step=1,
            width="small",
            help="ゲーム内のレシピレベル。未開拓は1。",
        ),
        "倍率": st.column_config.NumberColumn("倍率", format="×%.2f", width="small"),
        "いまのエナジー": st.column_config.NumberColumn("いまのエナジー", format="%d en"),
        "Lv70なら": st.column_config.NumberColumn("Lv70なら", format="%d en"),
    },
    key="recipe_level_editor",
)

# ── 差分 ─────────────────────────────────────────────────────────────
# 保存前に「何がどう変わるか」を必ず見せる。料理レベルは編成の最適解を動かすので、
# 黙って書き換えると後で数字が動いた理由が追えなくなる。
changes: list[tuple[str, int, int]] = []
for _, row in edited.iterrows():
    name = str(row["料理"])
    new_lv = recipe_level.clamp_level(row["Lv"])
    old_lv = saved.get(name, recipe_level.MIN_LEVEL)
    if new_lv != old_lv:
        changes.append((name, old_lv, new_lv))

if changes:
    st.markdown(f"**変更 {len(changes)}件**")
    st.dataframe(
        pd.DataFrame(
            [{"料理": n, "いま": f"Lv{o}", "変更後": f"Lv{v}"} for n, o, v in changes]
        ),
        hide_index=True,
        use_container_width=True,
        height=min(300, 44 + 36 * len(changes)),
    )
    if st.button(f"{len(changes)}件を保存", type="primary", key="save_recipe_levels_bulk"):
        merged = dict(saved)
        for name, _old, new_lv in changes:
            if new_lv <= recipe_level.MIN_LEVEL:
                merged.pop(name, None)
            else:
                merged[name] = new_lv
        recipe_level.save_recipe_levels(merged)
        st.cache_data.clear()  # 料理エナジーに依存する集計を全部作り直す
        st.success(f"{len(changes)}件を保存しました。編成の再計算に反映されます。")
        st.rerun()
else:
    st.caption("変更はありません。")

if saved:
    with st.expander("登録を全部消す"):
        st.caption("全料理をLv1（未開拓）に戻します。編成の評価が下がります。")
        if st.button("全消去", key="clear_recipe_levels"):
            recipe_level.save_recipe_levels({})
            st.cache_data.clear()
            st.rerun()

st.caption(
    "レベルボーナスは全料理共通（Lv30で×1.61 / Lv60で×3.03 / Lv70で×3.58）。"
    "ごちゃまぜ系はレシピレベルの恩恵が無いため一覧から除いています。"
)
