"""所持ポケデータ。

機能:
  - master.py 並みの絞り込み・並び替え
  - 「将来性モード」: 未開放の食材枠/サブスキルも検索対象に含めるかの切替
    - OFF: caught_level（=現在Lvの代理）で開放済の枠のみで絞り込み
    - ON: 登録済みなら全て対象
  - きのみ・食材の画像列
  - 行選択ベースの詳細パネル＋削除UI（確認チェック必須）
"""

from __future__ import annotations

import math

import pandas as pd
import streamlit as st

import db
from constants import (
    DAIFUKU_EVAL_LABELS,
    DAIFUKU_RANK_COLORS,
    DAIFUKU_RANK_EMOJI,
    DAIFUKU_RANKS,
    SUBSKILL_RARITY_COLORS,
    SUBSKILL_RARITY_EMOJI,
    SUBSKILL_RARITY_ORDER,
    SUBSKILL_UNLOCK_LEVELS,
    THEME_INK_DIM,
    blend_hex,
    format_nature_label,
    get_subskill_rarity,
)
from utils.evaluator import evaluate_and_save, evaluate_at_levels, evaluate_pokemon
from utils.food_expectation import composition_string
from ui import components as uic

# ランク並び替え用の順位（SS=0, S=1, ..., D=5）。
# 「昇順」で SS が最上段に来るよう、強い順から 0 を振る。
RANK_ORDER_MAP: dict[str, int] = {r: i for i, r in enumerate(DAIFUKU_RANKS)}
from image_utils import berry_icon_url, ingredient_icon_url, pokemon_image_url, sleep_ribbon_icon_url

st.title("📦 所持ポケデータ")

owned = [dict(r) for r in db.list_pokemon()]
if not owned:
    st.info("まだ登録されていません。「個体登録」から追加してください。")
    st.stop()


# 食材スロット解放Lv（slot1=Lv1、slot2=Lv30、slot3=Lv60）
INGREDIENT_UNLOCK_LV: list[tuple[int, str]] = [(1, "食材1"), (30, "食材2"), (60, "食材3")]


def _effective_level(p: dict) -> int:
    """現在Lvの代理値: current_level → caught_level → level（だいふく評価Lv=60）の優先順。"""
    return p.get("current_level") or p.get("caught_level") or p.get("level") or 1


def _truncate_pct(x):
    """評価%は小数第3位以下を切り捨てて2桁にする。None/NaN はそのまま。"""
    if x is None or pd.isna(x):
        return None
    return math.floor(x * 100) / 100


def _sub_filter_label(name: str) -> str:
    """サブスキル絞り込み用のラベル: 🟡 きのみの数S のようにレアリティ絵文字を前置。
    旧表記（お手伝い/寝顔EXP）も自動でレアリティ判定される。"""
    rarity = get_subskill_rarity(name)
    return f"{SUBSKILL_RARITY_EMOJI[rarity]} {name}"


def _sub_sort_key(name: str) -> tuple[int, str]:
    """金→青→白 → 名前 の順にソート。"""
    rarity = get_subskill_rarity(name)
    return (SUBSKILL_RARITY_ORDER[rarity], name)


def _rank_filter_label(rank: str) -> str:
    return f"{DAIFUKU_RANK_EMOJI.get(rank, '')} {rank}".strip()


# セル色（高ランクほど暖色 / レアリティに対応）。「増田」は SS 超えの伝説ランク。
# ダークテーマ用: 淡い同系面 + 明るい同系文字（constants の色トークンから生成）。
RANK_BG_STYLE: dict[str, str] = {
    rank: (
        f"background-color: {blend_hex(color)}; color: {color}"
        + ("; font-weight: bold" if rank in ("増田", "SS") else "")
    )
    for rank, color in DAIFUKU_RANK_COLORS.items()
}
SUBSKILL_BG_STYLE: dict[str, str] = {
    rarity: f"background-color: {blend_hex(color)}; color: {color}"
    for rarity, color in SUBSKILL_RARITY_COLORS.items()
}


def _rank_bg(val) -> str:
    if pd.isna(val):
        return ""
    return RANK_BG_STYLE.get(val, "")


def _subskill_bg(val) -> str:
    if pd.isna(val) or not val:
        return ""
    rarity = get_subskill_rarity(val)
    return SUBSKILL_BG_STYLE.get(rarity, "")


# ---------------------------------------------------------------------------
# DataFrame 構築（種族マスター情報をマージ）
# ---------------------------------------------------------------------------
records = []
for p in owned:
    species = db.get_species_data(p["species_name"]) or {}
    berry = species.get("berry") or {}
    # 現状/Lv50/Lv60 の3点評価
    er_set = evaluate_at_levels(p, target_levels=(50, 60))
    er = er_set["current"]
    er_lv50 = er_set["lv50"]
    er_lv60 = er_set["lv60"]
    records.append(
        {
            # ↓ ユーザー指定の表示順（先頭から）
            # ニックネームが空なら種族名をフォールバック表示（既存NULLレコードにも適用）
            "ニックネーム": p.get("nickname") or p["species_name"],
            "種族": p["species_name"],
            # ↓ 自前評価（メイン）。「ランク」「評価%」は species_* に意味を切り替え。
            "ランク": er.species_rank,
            "評価%": _truncate_pct(er.species_total),
            "Lv50ランク": er_lv50.species_rank,
            "Lv50%": _truncate_pct(er_lv50.species_total),
            "Lv60ランク": er_lv60.species_rank,
            "Lv60%": _truncate_pct(er_lv60.species_total),
            "全体ランク": er.global_rank,
            "全体%": _truncate_pct(er.global_total),
            "得意": species.get("specialty"),
            "構成": composition_string(p, species),
            "現在Lv": p.get("current_level"),
            "メインスキル": p.get("main_skill_name") or species.get("main_skill"),
            "メインスキルLv": p.get("main_skill_level") or 1,
            "サブLv10": p.get("subskill_lv10"),
            "サブLv25": p.get("subskill_lv25"),
            "サブLv50": p.get("subskill_lv50"),
            "サブLv75": p.get("subskill_lv75"),
            "サブLv100": p.get("subskill_lv100"),
            "性格": format_nature_label(p.get("nature")),
            "捕獲時Lv": p.get("caught_level"),
            "睡眠": species.get("sleep_type"),
            "🌳": berry_icon_url(berry.get("name")),
            "きのみ": berry.get("name"),
            "🥕1": ingredient_icon_url(p.get("ingredient_1")),
            "食材1": p.get("ingredient_1"),
            "🥕2": ingredient_icon_url(p.get("ingredient_2")),
            "食材2": p.get("ingredient_2"),
            "🥕3": ingredient_icon_url(p.get("ingredient_3")),
            "食材3": p.get("ingredient_3"),
            "🎀": sleep_ribbon_icon_url(p.get("sleep_ribbon_stage")),
            "リボン": int(p.get("sleep_ribbon_stage") or 0),
            "評価タイプ": er.eval_type,
            "メモ": p.get("note"),
            # ↓ だいふく由来の元値（移行期間中の参考表示）
            "だいふくランク": p.get("daifuku_rank"),
            "だいふく%": _truncate_pct(p.get("daifuku_eval_percent")),
            "だいふくタイプ": p.get("daifuku_eval_type"),
            # ↓ 内部用（_接頭辞は表示から除外される）
            "_ID": p["id"],
            "_食材確率%": species.get("food_drop_rate"),
            "_スキル確率%": species.get("main_skill_rate"),
            "_effective_lv": _effective_level(p),
            "_eval_type_source": er.eval_type_source,
            "_eval_berry": er.species_berry,
            "_eval_food": er.species_food,
            "_eval_skill": er.species_skill,
            "_eval_option": er.option_bonus,
            "_eval_strengths": ",".join(er.strengths),
            "_eval_weaknesses": ",".join(er.weaknesses),
        }
    )
df_full = pd.DataFrame(records)


# ---------------------------------------------------------------------------
# 絞り込み・並び替え UI
# ---------------------------------------------------------------------------
def _uniques(col: str) -> list:
    return sorted(df_full[col].dropna().unique().tolist())


SUB_COLS = [f"サブLv{lv}" for lv in SUBSKILL_UNLOCK_LEVELS]
all_ingredients = sorted(
    {n for col in ("食材1", "食材2", "食材3") for n in df_full[col].dropna().unique()}
)
# サブスキル一覧は 金→青→白 の順に並べる（レアリティ既知のみ）
all_subskills = sorted(
    {s for col in SUB_COLS for s in df_full[col].dropna().unique()},
    key=_sub_sort_key,
)


CONSIDER_LV_OPTIONS: list[tuple[str, int | None]] = [
    ("📍 現在Lvまで（既開放のみ）", None),
    ("🔮 Lv10まで（サブLv10 解放）", 10),
    ("🔮 Lv25まで（サブLv25 解放）", 25),
    ("🔮 Lv30まで（食材2 解放）", 30),
    ("🔮 Lv50まで（サブLv50 解放）", 50),
    ("🔮 Lv60まで（食材3 解放）", 60),
    ("🔮 Lv75まで（サブLv75 解放）", 75),
    ("🔮 Lv100まで（サブLv100 解放／全枠）", 100),
]
_CONSIDER_LV_MAP = dict(CONSIDER_LV_OPTIONS)


with st.expander("🔍 絞り込み・並び替え", expanded=True):
    consider_label = st.selectbox(
        "将来性モード（どこまで育てる前提で絞り込むか）",
        options=[lbl for lbl, _ in CONSIDER_LV_OPTIONS],
        index=0,
        help=(
            "選んだLvまで育つ前提で食材枠・サブスキル枠を検索対象に含めます。"
            "現在Lvが既にそれ以上の個体は、現在Lvがそのまま使われます。"
            "Lv30で食材2、Lv60で食材3、Lv10/25/50/75/100でサブスキルが順に解放。"
        ),
    )
    consider_lv: int | None = _CONSIDER_LV_MAP[consider_label]

    row1 = st.columns(5)
    with row1[0]:
        keyword = st.text_input("種族/ニックネーム検索", placeholder="例: ばなお")
    with row1[1]:
        sel_sleep = st.multiselect("睡眠", _uniques("睡眠"))
    with row1[2]:
        sel_specialty = st.multiselect("得意", _uniques("得意"))
    with row1[3]:
        sel_skill = st.multiselect("メインスキル", _uniques("メインスキル"))
    with row1[4]:
        sel_rank = st.multiselect(
            "ランク（自前評価・種族内）",
            DAIFUKU_RANKS,
            format_func=_rank_filter_label,
            help="自前評価の種族内ランク。※ DAIFUKU_RANKS の文字列セット（増田/SS/S/A/B/C/D）を流用。",
        )

    row2 = st.columns(5)
    with row2[0]:
        sel_berries = st.multiselect("きのみ", _uniques("きのみ"))
    with row2[1]:
        sel_ingredients = st.multiselect("食材（いずれかに含む）", all_ingredients)
    with row2[2]:
        sel_subskills = st.multiselect(
            "サブスキル（金→青→白 / いずれかに含む）",
            all_subskills,
            format_func=_sub_filter_label,
        )
    with row2[3]:
        sel_natures = st.multiselect("性格", _uniques("性格"))
    with row2[4]:
        sel_eval_type = st.multiselect("評価タイプ", list(range(1, 10)))

    row2b = st.columns(5)
    with row2b[0]:
        sel_compositions = st.multiselect(
            "食材構成（AAA/ABB等）",
            _uniques("構成"),
            help="個体の3スロットがどの枠(A/B/C)の食材かの並び。未入力スロットは ? 表示。",
        )

    st.caption("数値レンジ")
    row3 = st.columns(4)
    with row3[0]:
        lv_range = st.slider("現在Lv", min_value=1, max_value=65, value=(1, 65))
    with row3[1]:
        skill_lv_range = st.slider(
            "メインスキルLv", min_value=1, max_value=8, value=(1, 8)
        )
    with row3[2]:
        pct_range = st.slider(
            "種族内%", min_value=0.0, max_value=120.0, value=(0.0, 120.0), step=0.5
        )
    with row3[3]:
        ribbon_options = [
            ("未獲得", 0),
            ("段階1", 1),
            ("段階2", 2),
            ("段階3", 3),
            ("段階4", 4),
        ]
        sel_ribbons = st.multiselect(
            "🎀 おやすみリボン",
            options=[v for _, v in ribbon_options],
            format_func=lambda v: dict((vv, lbl) for lbl, vv in ribbon_options).get(v, str(v)),
            help="複数選択可。空＝絞り込みなし。",
        )

    st.caption("並び替え（上から順に第1キー → 第2キー）　※「登録順」は新→旧で固定")
    sortable_cols = [
        "登録順",
        "ニックネーム",
        "種族",
        "現在Lv",
        "捕獲時Lv",
        "ランク",
        "評価%",
        "Lv50ランク",
        "Lv50%",
        "Lv60ランク",
        "Lv60%",
        "全体ランク",
        "全体%",
        "メインスキルLv",
    ]
    row4 = st.columns([2, 1, 2, 1])
    with row4[0]:
        sort_key1 = st.selectbox("並び替え1", options=sortable_cols, index=0, key="o_sk1")
    with row4[1]:
        sort_dir1 = st.radio("方向1", ["昇順", "降順"], horizontal=True, key="o_dir1")
    with row4[2]:
        sort_key2 = st.selectbox(
            "並び替え2", options=["（なし）", *sortable_cols], index=0, key="o_sk2"
        )
    with row4[3]:
        sort_dir2 = st.radio("方向2", ["昇順", "降順"], horizontal=True, key="o_dir2")


# ---------------------------------------------------------------------------
# フィルタ適用
# ---------------------------------------------------------------------------
filtered = df_full.copy()

if keyword:
    kw = keyword.strip()
    mask = filtered["種族"].str.contains(kw, na=False) | filtered[
        "ニックネーム"
    ].fillna("").str.contains(kw, na=False)
    filtered = filtered[mask]
if sel_sleep:
    filtered = filtered[filtered["睡眠"].isin(sel_sleep)]
if sel_specialty:
    filtered = filtered[filtered["得意"].isin(sel_specialty)]
if sel_skill:
    filtered = filtered[filtered["メインスキル"].isin(sel_skill)]
if sel_rank:
    filtered = filtered[filtered["ランク"].isin(sel_rank)]
if sel_berries:
    filtered = filtered[filtered["きのみ"].isin(sel_berries)]
if sel_natures:
    filtered = filtered[filtered["性格"].isin(sel_natures)]
if sel_eval_type:
    filtered = filtered[filtered["評価タイプ"].isin(sel_eval_type)]
if sel_compositions:
    filtered = filtered[filtered["構成"].isin(sel_compositions)]
if sel_ribbons:
    filtered = filtered[filtered["リボン"].isin(sel_ribbons)]


def _consider_lv_for(eff_lv: int) -> int:
    """個体の現在Lvと「考慮Lv」のうち高い方。考慮Lv未指定なら現在Lvそのまま。"""
    base = eff_lv or 1
    if consider_lv is None:
        return base
    return max(base, consider_lv)


def _has_ingredient_in(row: pd.Series, target_names: set[str]) -> bool:
    cl = _consider_lv_for(row.get("_effective_lv") or 1)
    for unlock_lv, col in INGREDIENT_UNLOCK_LV:
        if cl < unlock_lv:
            continue
        v = row.get(col)
        if v in target_names:
            return True
    return False


def _has_subskill_in(row: pd.Series, target_names: set[str]) -> bool:
    cl = _consider_lv_for(row.get("_effective_lv") or 1)
    for lv in SUBSKILL_UNLOCK_LEVELS:
        if cl < lv:
            continue
        v = row.get(f"サブLv{lv}")
        if v in target_names:
            return True
    return False


if sel_ingredients:
    target_set = set(sel_ingredients)
    filtered = filtered[filtered.apply(lambda r: _has_ingredient_in(r, target_set), axis=1)]
if sel_subskills:
    target_set = set(sel_subskills)
    filtered = filtered[filtered.apply(lambda r: _has_subskill_in(r, target_set), axis=1)]

if lv_range != (1, 65):
    filtered = filtered[
        filtered["現在Lv"].fillna(-1).between(lv_range[0], lv_range[1])
    ]
if skill_lv_range != (1, 8):
    filtered = filtered[
        filtered["メインスキルLv"].fillna(-1).between(skill_lv_range[0], skill_lv_range[1])
    ]
if pct_range != (0.0, 120.0):
    filtered = filtered[
        filtered["評価%"].fillna(-1).between(pct_range[0], pct_range[1])
    ]

# ソート
_RANK_SORT_COLS = {
    "ランク": "_rank_sort",
    "Lv50ランク": "_lv50_rank_sort",
    "Lv60ランク": "_lv60_rank_sort",
    "全体ランク": "_global_rank_sort",
}


def _sort_pair(key: str, dir_label: str) -> tuple[str, bool]:
    """「登録順」は内部の _ID 降順に固定。ランク系はランク順位で並び替え（SS,S,A,B,C,D）。
    それ以外は radio の昇/降順を尊重。"""
    if key == "登録順":
        return ("_ID", False)
    if key in _RANK_SORT_COLS:
        return (_RANK_SORT_COLS[key], dir_label == "昇順")
    return (key, dir_label == "昇順")


sort_keys: list[str] = []
sort_asc: list[bool] = []
k1, a1 = _sort_pair(sort_key1, sort_dir1)
sort_keys.append(k1)
sort_asc.append(a1)
if sort_key2 != "（なし）":
    k2, a2 = _sort_pair(sort_key2, sort_dir2)
    sort_keys.append(k2)
    sort_asc.append(a2)
if "_rank_sort" in sort_keys:
    filtered = filtered.assign(_rank_sort=filtered["ランク"].map(RANK_ORDER_MAP))
if "_lv50_rank_sort" in sort_keys:
    filtered = filtered.assign(_lv50_rank_sort=filtered["Lv50ランク"].map(RANK_ORDER_MAP))
if "_lv60_rank_sort" in sort_keys:
    filtered = filtered.assign(_lv60_rank_sort=filtered["Lv60ランク"].map(RANK_ORDER_MAP))
if "_global_rank_sort" in sort_keys:
    filtered = filtered.assign(
        _global_rank_sort=filtered["全体ランク"].map(RANK_ORDER_MAP)
    )
filtered = filtered.sort_values(by=sort_keys, ascending=sort_asc, na_position="last")


# ---------------------------------------------------------------------------
# 表示用 DataFrame の整形（未開放スロットを「未解放」表示にしてアイコン消す）
# ---------------------------------------------------------------------------
display_df = filtered.copy()

UNRELEASED_LABEL = "未解放"

# 「考慮Lv」を個体ごとに算出（現在Lvと選択Lvの max）
display_df["_consider_lv"] = display_df["_effective_lv"].apply(_consider_lv_for)

# 食材スロット: スロット2/3 が考慮Lv未満なら未開放扱い
for unlock_lv, name_col in INGREDIENT_UNLOCK_LV:
    if unlock_lv == 1 or name_col not in display_df.columns:
        continue
    eff_below = display_df["_consider_lv"] < unlock_lv
    # 値が空なら "未解放" を入れる（先取り入力済みなら値を残してスタイルだけ薄く）
    null_mask = eff_below & display_df[name_col].isna()
    display_df.loc[null_mask, name_col] = UNRELEASED_LABEL
    # アイコンは未開放なら一律消す
    img_col = "🥕" + name_col[-1]
    if img_col in display_df.columns:
        display_df.loc[eff_below, img_col] = None

# サブスキル
for unlock_lv in SUBSKILL_UNLOCK_LEVELS:
    sub_col = f"サブLv{unlock_lv}"
    if sub_col not in display_df.columns:
        continue
    eff_below = display_df["_consider_lv"] < unlock_lv
    null_mask = eff_below & display_df[sub_col].isna()
    display_df.loc[null_mask, sub_col] = UNRELEASED_LABEL


display_cols = [c for c in display_df.columns if not c.startswith("_")]

# 列プリセット: 全列だと横スクロールが面倒なので、用途別に絞り込めるようにする
VIEW_PRESETS: dict[str, list[str] | None] = {
    "📊 評価": [
        "ニックネーム", "種族",
        "ランク", "評価%", "Lv50ランク", "Lv50%", "Lv60ランク", "Lv60%",
        "全体ランク", "全体%",
        "評価タイプ", "得意", "構成", "メインスキル", "現在Lv", "性格",
    ],
    "📋 ステータス": [
        "ニックネーム", "種族", "ランク", "評価%", "得意",
        "現在Lv", "性格", "メインスキル", "メインスキルLv",
        "🎀", "リボン",
    ],
    "⚡ スキル": [
        "ニックネーム", "種族", "ランク", "評価%", "現在Lv",
        "メインスキル", "メインスキルLv",
        "サブLv10", "サブLv25", "サブLv50", "サブLv75", "サブLv100",
    ],
    "🥕 食材・きのみ": [
        "ニックネーム", "種族", "現在Lv", "構成", "メインスキル",
        "🌳", "きのみ",
        "🥕1", "食材1", "🥕2", "食材2", "🥕3", "食材3",
        "🎀", "リボン",
    ],
    "🍡 だいふく（旧）": [
        "ニックネーム", "種族", "ランク", "評価%",
        "だいふくランク", "だいふく%", "だいふくタイプ",
    ],
    "🌐 全部": None,  # = display_cols（全列）
}

mode_label = (
    "📍 現在Lvモード（current_level基準）"
    if consider_lv is None
    else f"🔮 将来性モード（Lv{consider_lv}まで考慮）"
)

disp_mode = st.segmented_control(
    "表示",
    options=["🃏 カード", "📋 表"],
    default="🃏 カード",
    key="owned_disp_mode",
    label_visibility="collapsed",
)

header_cols = st.columns([3, 4])
with header_cols[0]:
    st.caption(f"{len(display_df)} / {len(df_full)} 件　— {mode_label}")
view_mode = list(VIEW_PRESETS.keys())[0]
if disp_mode == "📋 表":
    with header_cols[1]:
        view_mode = st.radio(
            "表示モード",
            options=list(VIEW_PRESETS.keys()),
            index=0,
            horizontal=True,
            key="owned_view_mode",
            label_visibility="collapsed",
            help="列が多くて横スクロールが面倒な時はモードで絞ってください。",
        )

active_cols = VIEW_PRESETS[view_mode] or display_cols

_IMG_COL_CONFIG = {
    # ニックネーム/種族/ランクは左にピン留めして横スクロール中も常に見えるように
    "ニックネーム": st.column_config.TextColumn("ニックネーム", pinned=True),
    "種族": st.column_config.TextColumn("種族", pinned=True),
    "ランク": st.column_config.TextColumn("ランク", pinned=True),
    "🌳": st.column_config.ImageColumn("🌳", width="small"),
    "🥕1": st.column_config.ImageColumn("🥕1", width="small"),
    "🥕2": st.column_config.ImageColumn("🥕2", width="small"),
    "🥕3": st.column_config.ImageColumn("🥕3", width="small"),
    "🎀": st.column_config.ImageColumn("🎀", width="small"),
    "評価%": st.column_config.NumberColumn("評価%", format="%.2f"),
    "Lv50%": st.column_config.NumberColumn("Lv50%", format="%.2f"),
    "Lv60%": st.column_config.NumberColumn("Lv60%", format="%.2f"),
    "全体%": st.column_config.NumberColumn("全体%", format="%.2f"),
    "だいふく%": st.column_config.NumberColumn("だいふく%", format="%.2f"),
}

# 未開放セル用の薄いスタイル
GRAY_STYLE = f"color: {THEME_INK_DIM}; background-color: #F4EFE2; font-style: italic"


def _build_styler(df: pd.DataFrame):
    """ランク列・サブスキル列の通常色 + 未開放スロットを灰色で塗る。"""
    sub_cols_present = [c for c in SUB_COLS if c in df.columns]
    rank_cols_present = [
        c for c in ("ランク", "Lv50ランク", "Lv60ランク", "全体ランク", "だいふくランク")
        if c in df.columns
    ]
    has_eff_lv = "_consider_lv" in df.columns

    def _apply(df_in: pd.DataFrame) -> pd.DataFrame:
        styles = pd.DataFrame("", index=df_in.index, columns=df_in.columns)

        # ランク列（自前 / 全体 / だいふく）
        for c in rank_cols_present:
            styles[c] = df_in[c].map(_rank_bg)

        # サブスキル: 通常はレアリティ色、未開放は灰色で上書き
        for c in sub_cols_present:
            styles[c] = df_in[c].map(_subskill_bg)
        if has_eff_lv:
            eff = df_in["_consider_lv"]
            for unlock_lv in SUBSKILL_UNLOCK_LEVELS:
                col = f"サブLv{unlock_lv}"
                if col in df_in.columns:
                    styles.loc[eff < unlock_lv, col] = GRAY_STYLE

            # 食材スロット (テキスト列)
            for unlock_lv, name_col in INGREDIENT_UNLOCK_LV:
                if unlock_lv == 1 or name_col not in df_in.columns:
                    continue
                styles.loc[eff < unlock_lv, name_col] = GRAY_STYLE
                img_col = "🥕" + name_col[-1]
                if img_col in df_in.columns:
                    styles.loc[eff < unlock_lv, img_col] = "background-color: #F4EFE2"

        return styles

    return df.style.apply(_apply, axis=None)


# ---------------------------------------------------------------------------
# 個体詳細＋削除（表モード=行選択でインライン / カードモード=dialog で共用）
# ---------------------------------------------------------------------------
def _render_detail(row: pd.Series, selected_id: int) -> None:
    # ニックネームが種族名と同じなら冗長なのでブラケット省略
    species_text = row["種族"]
    nick_val = row.get("ニックネーム")
    nick = f"「{nick_val}」" if nick_val and nick_val != species_text else ""
    st.subheader(f"📌 {species_text}{nick}（id={selected_id}）")

    d_cols = st.columns(5)
    d_cols[0].metric("現在Lv", row["現在Lv"] if pd.notna(row["現在Lv"]) else "—")
    d_cols[1].metric("捕獲時Lv", row["捕獲時Lv"] if pd.notna(row["捕獲時Lv"]) else "—")
    d_cols[2].metric("性格", row["性格"] if pd.notna(row["性格"]) else "—")
    rank_disp = (
        f"{row['ランク']} ({row['評価%']:.1f}%)"
        if pd.notna(row["ランク"]) and pd.notna(row["評価%"])
        else (row["ランク"] if pd.notna(row["ランク"]) else "—")
    )
    d_cols[3].metric("種族内ランク", rank_disp)
    d_cols[4].metric(
        "メインスキルLv", row["メインスキルLv"] if pd.notna(row["メインスキルLv"]) else "—"
    )

    if row.get("メモ") and pd.notna(row.get("メモ")):
        st.caption(f"📝 {row['メモ']}")

    # ===== 評価内訳（行選択時に再計算 + DB保存） =====
    st.markdown("##### 📊 個体評価の内訳")
    detail_eval = evaluate_and_save(selected_id)
    eval_type_label = (
        f"#{detail_eval.eval_type} {DAIFUKU_EVAL_LABELS[detail_eval.eval_type - 1]}"
        f"（{'だいふく登録値' if detail_eval.eval_type_source == 'daifuku' else '自動推定'}）"
    )
    α, β, γ = detail_eval.weights
    st.caption(f"評価タイプ: **{eval_type_label}**　／　重み α={α} β={β} γ={γ}")

    e_cols = st.columns(4)
    e_cols[0].metric("種族内", f"{detail_eval.species_total:.1f}", detail_eval.species_rank)
    e_cols[1].metric("全体", f"{detail_eval.global_total:.1f}", detail_eval.global_rank)
    e_cols[2].metric("オプション加点", f"{detail_eval.option_bonus:+.1f}")
    e_cols[3].metric(
        "強み / 弱み",
        " / ".join(detail_eval.strengths) or "—",
        delta=("弱み: " + " / ".join(detail_eval.weaknesses)) if detail_eval.weaknesses else None,
        delta_color="inverse",
    )

    axis_df = pd.DataFrame(
        {
            "軸": ["きのみ (α)", "食材 (β)", "スキル (γ)"],
            "種族内": [
                detail_eval.species_berry,
                detail_eval.species_food,
                detail_eval.species_skill,
            ],
            "全体": [
                detail_eval.global_berry,
                detail_eval.global_food,
                detail_eval.global_skill,
            ],
        }
    )
    st.dataframe(
        axis_df.style.format({"種族内": "{:.1f}", "全体": "{:.1f}"}),
        hide_index=True,
        use_container_width=True,
    )

    if detail_eval.option_breakdown:
        st.caption(
            "🎁 加点内訳: "
            + ", ".join(f"{lbl} {v:+.1f}" for lbl, v in detail_eval.option_breakdown)
        )

    st.markdown("##### 削除")
    confirm = st.checkbox(
        f"id={selected_id} を本当に削除する",
        key=f"o_del_confirm_{selected_id}",
    )
    if st.button(
        "🗑 削除",
        type="secondary",
        disabled=not confirm,
        key=f"o_del_btn_{selected_id}",
    ):
        db.delete_pokemon(selected_id)
        st.success(f"id={selected_id} を削除しました。")
        st.rerun()


@st.dialog("個体詳細", width="large")
def _detail_dialog(row: pd.Series, selected_id: int) -> None:
    _render_detail(row, selected_id)


# ---------------------------------------------------------------------------
# 一覧の描画（カード / 表）
# ---------------------------------------------------------------------------
if disp_mode == "🃏 カード":
    ss = st.session_state
    ss.setdefault("owned_cards_shown", 30)
    page_df = display_df.head(ss["owned_cards_shown"])

    CARDS_PER_ROW = 2  # スマホ主眼: 3列だとタイトルが縦割れする
    rows_iter = list(page_df.iterrows())
    for start in range(0, len(rows_iter), CARDS_PER_ROW):
        cols = st.columns(CARDS_PER_ROW)
        for col, (_, row) in zip(cols, rows_iter[start:start + CARDS_PER_ROW]):
            with col:
                pid = int(row["_ID"])
                badges = [uic.rank_badge(row["ランク"], row["評価%"] if pd.notna(row["評価%"]) else None)]
                if row.get("構成"):
                    badges.append(uic.text_badge(row["構成"]))
                if pd.notna(row.get("Lv60ランク")):
                    badges.append(uic.rank_badge(row["Lv60ランク"]))
                chips = [
                    uic.subskill_chip(row.get(f"サブLv{lv}"))
                    for lv in SUBSKILL_UNLOCK_LEVELS
                    if row.get(f"サブLv{lv}") and row.get(f"サブLv{lv}") != UNRELEASED_LABEL
                ][:3]
                lv_txt = f"Lv{int(row['現在Lv'])}" if pd.notna(row["現在Lv"]) else "Lv?"
                ribbon = "🎀" * int(row["リボン"]) if row.get("リボン") else ""
                st.html(uic.pokemon_card(
                    title=row["ニックネーム"],
                    subtitle=f"{row['種族']} · {lv_txt} {ribbon}",
                    specialty=row.get("得意"),
                    berry_name=row.get("きのみ"),
                    img_url=pokemon_image_url(row["種族"]),
                    badges=badges,
                    chips=chips,
                ))
                if st.button("詳細", key=f"o_card_{pid}", use_container_width=True):
                    _detail_dialog(row, pid)

    remaining = len(display_df) - len(page_df)
    if remaining > 0:
        if st.button(f"さらに表示（残り {remaining} 件）", use_container_width=True):
            ss["owned_cards_shown"] += 30
            st.rerun()
else:
    event = st.dataframe(
        _build_styler(display_df),
        hide_index=True,
        use_container_width=True,
        height=600,
        on_select="rerun",
        selection_mode="single-row",
        key="owned_table",
        column_config=_IMG_COL_CONFIG,
        column_order=active_cols,
    )

    selected_rows = event.selection.rows if event and event.selection else []
    if selected_rows:
        idx = selected_rows[0]
        row = display_df.iloc[idx]
        st.divider()
        _render_detail(row, int(row["_ID"]))
