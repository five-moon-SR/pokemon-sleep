"""個体強化・進化ページ。

フロー:
  1. 検索（ニックネーム or 種族名）
  2. 候補一覧から行選択で1体に絞る
  3. 編集フォーム1枚に全項目を縦並びで表示
     - 進化 / 捕獲時Lv / メインスキルLv / 食材スロット / サブスキル
     - 一番下の「💾 一括更新」で変更分だけまとめてDB反映
"""

from __future__ import annotations

import math

import pandas as pd
import streamlit as st

import db
from constants import (
    SUBSKILL_UNLOCK_LEVELS,
    format_nature_label,
    get_subskill_upgrades,
)
from image_utils import berry_icon_url, ingredient_icon_url, sleep_ribbon_icon_url
from utils.evaluator import evaluate_at_levels


SLEEP_RIBBON_OPTIONS: list[tuple[str, int]] = [
    ("なし（未獲得）", 0),
    ("段階1（200h）", 1),
    ("段階2（500h）", 2),
    ("段階3（1,000h）", 3),
    ("段階4（2,000h）", 4),
]

st.title("🔧 個体強化・進化")


def _truncate_pct(x):
    """評価%は小数第3位以下を切り捨てて2桁にする。None/NaN はそのまま。"""
    if x is None:
        return None
    return math.floor(x * 100) / 100


def _format_subskills(row: dict) -> str:
    parts = []
    for lv in SUBSKILL_UNLOCK_LEVELS:
        v = row.get(f"subskill_lv{lv}")
        if v:
            parts.append(f"Lv{lv}:{v}")
    return " / ".join(parts) if parts else "—"


def _conditions_text(conditions: dict) -> str:
    parts = []
    if conditions.get("min_level") is not None:
        parts.append(f"Lv{conditions['min_level']}以上")
    if conditions.get("min_sleep_hours") is not None:
        parts.append(f"累計睡眠{conditions['min_sleep_hours']}時間")
    if conditions.get("items"):
        parts.append("＋".join(conditions["items"]))
    if conditions.get("time_of_day") == "day":
        parts.append("日中(6:00-17:59)")
    if conditions.get("time_of_day") == "night":
        parts.append("夜間(18:00-5:59)")
    if conditions.get("gender") == "male":
        parts.append("♂限定")
    if conditions.get("gender") == "female":
        parts.append("♀限定")
    return " / ".join(parts) if parts else "条件なし"


def _upgrade_options(current: str | None) -> list[str]:
    """サブスキルのたねで到達可能な選択肢を返す（旧表記も自動マッチ）。
    返り値は正規表記の強化先のみ。空なら「強化先なし」。"""
    return get_subskill_upgrades(current)


# ============================================================================
# ステップ1: 検索 → 一覧 → 選択
# ============================================================================

owned = [dict(r) for r in db.list_pokemon()]
if not owned:
    st.info("まだ登録されていません。「個体登録」から追加してください。")
    st.stop()

header_cols = st.columns([4, 1])
with header_cols[0]:
    st.markdown("### 1️⃣ 更新したい個体を選ぶ")
with header_cols[1]:
    if st.button(
        "🔄 一括リセット",
        help="検索/選択/編集中の値を全てクリアして、ポケモン選択前の状態に戻ります。",
    ):
        for k in list(st.session_state.keys()):
            if k.startswith(("update_search", "update_table", "f_")):
                del st.session_state[k]
        st.rerun()

keyword = st.text_input(
    "検索（ニックネーム or 種族名 / 部分一致）",
    placeholder="例: ばなお / フシギ",
    key="update_search",
)

filtered = owned
if keyword:
    kw = keyword.strip()
    filtered = [
        p for p in owned
        if (p.get("nickname") and kw in p["nickname"])
        or (p.get("species_name") and kw in p["species_name"])
    ]

if not filtered:
    st.warning(f"「{keyword}」に一致する個体は見つかりません。")
    st.stop()

list_rows = []
for p in filtered:
    species = db.get_species_data(p["species_name"]) or {}
    berry = species.get("berry") or {}
    # 所持ポケと同じ自前評価（現状/Lv50/Lv60 の3点）
    er_set = evaluate_at_levels(p, target_levels=(50, 60))
    er = er_set["current"]
    er_lv50 = er_set["lv50"]
    er_lv60 = er_set["lv60"]
    list_rows.append(
        {
            # 所持ポケデータと揃えた列順
            # ニックネームが空なら種族名をフォールバック表示
            "ニックネーム": p.get("nickname") or p["species_name"],
            "種族": p["species_name"],
            "ランク": er.species_rank,
            "評価%": _truncate_pct(er.species_total),
            "Lv50ランク": er_lv50.species_rank,
            "Lv50%": _truncate_pct(er_lv50.species_total),
            "Lv60ランク": er_lv60.species_rank,
            "Lv60%": _truncate_pct(er_lv60.species_total),
            "全体ランク": er.global_rank,
            "全体%": _truncate_pct(er.global_total),
            "得意": species.get("specialty"),
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
            "リボン": p.get("sleep_ribbon_stage") or 0,
            "評価タイプ": er.eval_type,
            "メモ": p.get("note"),
            "_ID": p["id"],
        }
    )
list_df = pd.DataFrame(list_rows)
display_cols_list = [c for c in list_df.columns if not c.startswith("_")]

st.caption(f"{len(filtered)} / {len(owned)} 件　行をクリックで1体選択")
event = st.dataframe(
    list_df,
    hide_index=True,
    use_container_width=True,
    on_select="rerun",
    selection_mode="single-row",
    key="update_table",
    column_config={
        # 横スクロール中もニックネーム/種族が常に見えるよう左にピン留め
        "ニックネーム": st.column_config.TextColumn("ニックネーム", pinned=True),
        "種族": st.column_config.TextColumn("種族", pinned=True),
        "🌳": st.column_config.ImageColumn("🌳", width="small"),
        "🥕1": st.column_config.ImageColumn("🥕1", width="small"),
        "🥕2": st.column_config.ImageColumn("🥕2", width="small"),
        "🥕3": st.column_config.ImageColumn("🥕3", width="small"),
        "🎀": st.column_config.ImageColumn("🎀", width="small"),
        "評価%": st.column_config.NumberColumn("評価%", format="%.2f"),
        "Lv50%": st.column_config.NumberColumn("Lv50%", format="%.2f"),
        "Lv60%": st.column_config.NumberColumn("Lv60%", format="%.2f"),
        "全体%": st.column_config.NumberColumn("全体%", format="%.2f"),
    },
    column_order=display_cols_list,
)

selected_rows = event.selection.rows if event and event.selection else []
if not selected_rows:
    st.info("⬆️ 行をクリックして1体選んでください。")
    st.stop()

selected_idx = selected_rows[0]
selected_id = int(list_df.iloc[selected_idx]["_ID"])
target = next(p for p in filtered if p["id"] == selected_id)

# ============================================================================
# ステップ2: 編集フォーム（1枚に全項目）
# ============================================================================

species_name = target["species_name"]
species = db.get_species_data(species_name)
if not species:
    st.error("マスターに種族情報がありません。")
    st.stop()

nickname = target.get("nickname")
# ニックネームが種族名と同じ（or 空）ならブラケット省略
nick_label = f"「{nickname}」" if nickname and nickname != species_name else ""
header = f"{species_name}{nick_label}"
st.divider()
st.markdown(f"### 2️⃣ 編集　📌 {header}（id={selected_id}）")
st.caption(
    "変更したい項目だけ編集して、一番下の「💾 一括更新」を押すと、変更があった項目のみDBに反映されます。"
)

evolutions = db.list_evolutions_from(species_name)

cur_current = target.get("current_level")
cur_skill_lv = target.get("main_skill_level") or 1


# ─────────────────────────────────────────────────────────────────────────
# フォーム本体
# ─────────────────────────────────────────────────────────────────────────
with st.form(f"update_form_{selected_id}"):
    # --- ニックネーム（予備機能：登録後に名前を変えたいとき）---
    st.markdown("#### 🏷 ニックネーム")
    cur_nick = target.get("nickname") or ""
    new_nickname = st.text_input(
        "ニックネーム",
        value=cur_nick,
        key=f"f_nickname_{selected_id}",
        placeholder="未入力なら種族名がそのまま使われます",
        help="登録時に未入力なら種族名がデフォルト。後で気に入った名前に変更できます。",
    )

    st.divider()

    # --- 進化 ---
    st.markdown("#### 🔄 進化")
    if evolutions:
        evo_options = ["（進化させない）"] + [
            f"{e['to']}（アメ×{e['candy']} / {_conditions_text(e['conditions'])}）"
            for e in evolutions
        ]
        evo_choice = st.radio(
            "進化先",
            options=evo_options,
            index=0,
            key=f"f_evo_{selected_id}",
            help="ゲーム内で進化済みの場合のみ選択してください。選ぶとメインスキルLvが自動で+1されます。",
        )
    else:
        evo_choice = None
        st.caption(f"💡 「{species_name}」には登録されている進化先がありません。")

    st.divider()

    # --- 現在Lv ---
    st.markdown("#### 📍 現在Lv")
    new_current = st.number_input(
        "現在Lv（0=未指定）",
        min_value=0,
        max_value=65,
        value=int(cur_current) if cur_current else 0,
        step=1,
        key=f"f_current_{selected_id}",
        help="レベリングに合わせて更新する。Lvが上がれば食材スロット/サブスキルの開放状態も自動判定。",
    )

    st.divider()

    # --- 🎀 おやすみリボン ---
    st.markdown("#### 🎀 おやすみリボン")
    cur_ribbon = int(target.get("sleep_ribbon_stage") or 0)
    rib_col_sel, rib_col_img = st.columns([3, 1])
    with rib_col_sel:
        ribbon_labels = [lbl for lbl, _ in SLEEP_RIBBON_OPTIONS]
        cur_label = next((lbl for lbl, v in SLEEP_RIBBON_OPTIONS if v == cur_ribbon), ribbon_labels[0])
        new_ribbon_label = st.selectbox(
            "段階",
            options=ribbon_labels,
            index=ribbon_labels.index(cur_label),
            key=f"f_ribbon_{selected_id}",
            help="累積眠時間で自動付与される証。所持数+ や時間短縮（進化残り回数別）に効く。段階アップで更新。",
        )
    new_ribbon = dict(SLEEP_RIBBON_OPTIONS).get(new_ribbon_label, 0)
    with rib_col_img:
        url = sleep_ribbon_icon_url(new_ribbon)
        if url:
            st.image(url, width=48)

    st.divider()

    # --- メインスキルLv ---
    st.markdown("#### ⚡ メインスキルLv")
    new_skill_lv = st.number_input(
        "メインスキルLv",
        min_value=1,
        max_value=8,
        value=int(cur_skill_lv),
        step=1,
        key=f"f_skill_{selected_id}",
        help=(
            "メインスキルのたねで+1、サブスキル「スキルレベルアップS」で+1、Mで+2。"
            "進化を選ぶと自動で+1されます（手動指定が優先）。"
        ),
    )

    st.divider()

    # --- サブスキル（サブスキルのたねによる強化のみ受付）---
    st.markdown("#### ⭐ サブスキル")
    st.caption(
        "サブスキルのたねで強化できる枠だけ選択肢を表示します。"
        "金スキルや既に最大ランクのものは編集不可。"
        "未入力の枠は「📝 登録情報の修正」から記入してください。"
    )
    new_subs: dict[int, str | None] = {}
    for lv in SUBSKILL_UNLOCK_LEVELS:
        cur = target.get(f"subskill_lv{lv}")
        if cur is None:
            # 未入力: 編集不可（記入は edit_record.py で）
            st.text_input(
                f"Lv{lv}",
                value="未入力",
                disabled=True,
                key=f"f_sub_{lv}_{selected_id}",
            )
            new_subs[lv] = None
            continue

        upgrades = _upgrade_options(cur)
        if not upgrades:
            # 強化先なし: 表示のみ
            st.text_input(
                f"Lv{lv}",
                value=f"{cur}（強化先なし）",
                disabled=True,
                key=f"f_sub_{lv}_{selected_id}",
            )
            new_subs[lv] = cur
            continue

        # 強化先あり: 現在値 + 強化先を選択肢に
        options = [cur, *upgrades]
        choice = st.selectbox(
            f"Lv{lv}",
            options=options,
            index=0,
            key=f"f_sub_{lv}_{selected_id}",
            help=f"サブスキルのたね使用時に「{cur}」から選べる強化先のみ表示。",
        )
        new_subs[lv] = choice

    st.divider()
    btn_cols = st.columns([1, 1])
    with btn_cols[0]:
        submitted = st.form_submit_button(
            "💾 一括更新", type="primary", use_container_width=True
        )
    with btn_cols[1]:
        edit_full_clicked = st.form_submit_button(
            "📝 登録情報の修正",
            type="secondary",
            use_container_width=True,
            help="種族・食材・サブスキル等を含む全項目を修正できる専用ページに飛びます。",
        )


# 「登録情報の修正」ページへ遷移
if edit_full_clicked:
    st.session_state["edit_target_id"] = selected_id
    st.switch_page("views/edit_record.py")


# ─────────────────────────────────────────────────────────────────────────
# 提出処理
# ─────────────────────────────────────────────────────────────────────────
if submitted:
    updates: dict = {}
    msgs: list[str] = []

    # ニックネーム
    new_nick_val = new_nickname.strip() or None
    if new_nick_val != target.get("nickname"):
        updates["nickname"] = new_nick_val
        msgs.append(f"ニックネーム: {target.get('nickname') or '未設定'} → {new_nick_val or '未設定'}")

    # 進化（ラジオ index で進化レコードを引く）
    skill_lv_after = new_skill_lv
    user_changed_skill = new_skill_lv != cur_skill_lv
    if evolutions and evo_choice and evo_choice != "（進化させない）":
        idx = evo_options.index(evo_choice) - 1
        chosen = evolutions[idx]
        updates["species_name"] = chosen["to"]
        msgs.append(f"進化: {species_name} → {chosen['to']}")
        # 手動でLv変えてなければ +1
        if not user_changed_skill:
            skill_lv_after = min(cur_skill_lv + 1, 8)

    # メインスキルLv
    if skill_lv_after != cur_skill_lv:
        updates["main_skill_level"] = int(skill_lv_after)
        msgs.append(f"メインスキルLv: {cur_skill_lv} → {skill_lv_after}")

    # 現在Lv
    new_current_val = int(new_current) if new_current > 0 else None
    if new_current_val != cur_current:
        updates["current_level"] = new_current_val
        msgs.append(f"現在Lv: {cur_current or '未指定'} → {new_current_val or '未指定'}")

    # 🎀 おやすみリボン
    if int(new_ribbon) != cur_ribbon:
        updates["sleep_ribbon_stage"] = int(new_ribbon)
        msgs.append(f"おやすみリボン: 段階{cur_ribbon} → 段階{new_ribbon}")

    # サブスキル
    for lv in SUBSKILL_UNLOCK_LEVELS:
        cur_val = target.get(f"subskill_lv{lv}")
        if new_subs[lv] != cur_val:
            updates[f"subskill_lv{lv}"] = new_subs[lv]
            msgs.append(f"サブスキルLv{lv}: {cur_val or '未解放'} → {new_subs[lv] or '未解放'}")

    if not updates:
        st.warning("変更がありません。")
    else:
        db.update_pokemon(selected_id, **updates)
        st.success("✅ 更新しました：\n\n" + "\n".join(f"- {m}" for m in msgs))
        st.rerun()
