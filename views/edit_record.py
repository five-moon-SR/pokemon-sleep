"""登録情報の修正ページ。

「個体強化・進化」ページから対象を選んで「📝 登録情報の修正」で遷移。
通常のレベリング更新と違い、種族・メインスキル名・食材スロット・サブスキル等まで含む
全項目を修正できる。登録時の入力ミスや、進化先の状態で誤登録した個体の修正用。
"""

from __future__ import annotations

import streamlit as st

import db
from constants import (
    NATURE_AXIS_GROUPS,
    NATURES,
    SUBSKILL_OPTIONS,
    SUBSKILL_RARITY_EMOJI,
    SUBSKILL_RARITY_ORDER,
    SUBSKILL_UNLOCK_LEVELS,
    find_nature_axis,
    format_nature_label,
    get_subskill_rarity,
)
from image_utils import sleep_ribbon_icon_url


SLEEP_RIBBON_OPTIONS: list[tuple[str, int]] = [
    ("なし（未獲得）", 0),
    ("段階1（200h）", 1),
    ("段階2（500h）", 2),
    ("段階3（1,000h）", 3),
    ("段階4（2,000h）", 4),
]

st.title("✏️ 登録情報の修正")
st.caption(
    "登録時の入力ミスや、進化先の状態で誤登録した個体を修正するためのページです。"
    "種族・食材・サブスキル・各種Lv等、登録情報の全項目を編集できます。"
    "通常のレベリング更新は「個体強化・進化」から行ってください。"
)


# ============================================================================
# 対象 ID 取得
# ============================================================================
target_id = st.session_state.get("edit_target_id")
if target_id is None:
    st.info(
        "「🔧 個体強化・進化」ページで対象を選択してから、"
        "「📝 登録情報の修正」ボタンで来てください。"
    )
    st.stop()

target_row = db.get_pokemon(int(target_id))
if target_row is None:
    st.error(f"id={target_id} の個体が見つかりません。一覧から選び直してください。")
    st.session_state.pop("edit_target_id", None)
    st.stop()
target = dict(target_row)


# ============================================================================
# ヘッダ
# ============================================================================
species_now = target["species_name"]
nick_now = target.get("nickname")
nick_label = f"「{nick_now}」" if nick_now and nick_now != species_now else ""
st.subheader(f"📌 {species_now}{nick_label}（id={target_id}）")


# ============================================================================
# ヘルパ
# ============================================================================
def _sub_sort_key(name: str) -> tuple[int, str]:
    return (SUBSKILL_RARITY_ORDER[get_subskill_rarity(name)], name)


def _sub_label(name: str) -> str:
    if name == "（未入力）":
        return name
    return f"{SUBSKILL_RARITY_EMOJI[get_subskill_rarity(name)]} {name}"


def _nature_select_label(name: str) -> str:
    """selectbox 用: プレースホルダはそのまま、それ以外は format_nature_label に委譲。"""
    if name == "（未指定）":
        return name
    return format_nature_label(name)


def _reset_nature_pick(target_id: int) -> None:
    """軸カテゴリが変わったら性格セレクトをリセット。"""
    st.session_state.pop(f"e_nature_pick_{target_id}", None)


def _slot2_options(species: dict) -> list[tuple[str, str]]:
    opts: list[tuple[str, str]] = []
    a = species["ingredients"]["a"]
    b = species["ingredients"]["b"]
    if a:
        qty = a["qty"][1] if len(a["qty"]) >= 2 else "?"
        opts.append((f"A: {a['name']} ×{qty}", a["name"]))
    if b:
        qty = b["qty"][0] if b["qty"] else "?"
        opts.append((f"B: {b['name']} ×{qty}", b["name"]))
    return opts


def _slot3_options(species: dict) -> list[tuple[str, str]]:
    opts: list[tuple[str, str]] = []
    a = species["ingredients"]["a"]
    b = species["ingredients"]["b"]
    c = species["ingredients"]["c"]
    if a:
        qty = a["qty"][2] if len(a["qty"]) >= 3 else "?"
        opts.append((f"A: {a['name']} ×{qty}", a["name"]))
    if b:
        qty = b["qty"][1] if len(b["qty"]) >= 2 else "?"
        opts.append((f"B: {b['name']} ×{qty}", b["name"]))
    if c:
        qty = c["qty"][0] if c["qty"] else "?"
        opts.append((f"C: {c['name']} ×{qty}", c["name"]))
    return opts


def _slot_radio(
    label: str,
    cur_value: str | None,
    opts: list[tuple[str, str]],
    key: str,
) -> str | None:
    """食材スロット用ラジオ。候補外の旧値も保持できるよう警告ラベルで残す。"""
    label_to_name = {lbl: name for lbl, name in opts}
    name_to_label = {name: lbl for lbl, name in opts}
    options = ["（未選択）"] + [lbl for lbl, _ in opts]
    if cur_value and cur_value not in name_to_label:
        warn_label = f"⚠ {cur_value}（候補外）"
        options.insert(1, warn_label)
        label_to_name[warn_label] = cur_value
        default = warn_label
    elif cur_value:
        default = name_to_label[cur_value]
    else:
        default = "（未選択）"
    chosen = st.radio(label, options=options, index=options.index(default), key=key)
    return None if chosen == "（未選択）" else label_to_name[chosen]


# ============================================================================
# 種族
# ============================================================================
st.markdown("#### 🐲 種族")
all_species = db.list_species_names()
default_species_idx = all_species.index(species_now) if species_now in all_species else 0
new_species_name = st.selectbox(
    "種族（進化先で誤登録した場合などに変更可）",
    options=all_species,
    index=default_species_idx,
    key=f"e_species_{target_id}",
    help="種族を変えると、メインスキル名と食材スロット1（Lv1確定枠）は新種族の値に自動更新。",
)
new_species = db.get_species_data(new_species_name)
if not new_species:
    st.error(f"マスターに種族 {new_species_name} が見つかりません。")
    st.stop()

if new_species_name != species_now:
    st.warning(
        f"⚠️ 種族を **{species_now}** → **{new_species_name}** に変更します。"
        "メインスキル名・食材スロット1は新種族の値で自動更新、スロット2/3 は再選択してください。"
    )

st.divider()


# ============================================================================
# ニックネーム
# ============================================================================
st.markdown("#### 🏷 ニックネーム")
new_nickname = st.text_input(
    "ニックネーム",
    value=target.get("nickname") or "",
    key=f"e_nickname_{target_id}",
    placeholder="未入力なら種族名がデフォルト表示になります",
    label_visibility="collapsed",
)

st.divider()


# ============================================================================
# Lv（現在Lv / 捕獲時Lv）
# ============================================================================
st.markdown("#### 📍 Lv")
lv_cols = st.columns(2)
with lv_cols[0]:
    new_current = st.number_input(
        "現在Lv（0=未指定）",
        min_value=0,
        max_value=65,
        value=int(target.get("current_level") or 0),
        step=1,
        key=f"e_current_{target_id}",
    )
with lv_cols[1]:
    new_caught = st.number_input(
        "捕獲時Lv（0=未指定）",
        min_value=0,
        max_value=65,
        value=int(target.get("caught_level") or 0),
        step=1,
        key=f"e_caught_{target_id}",
    )

st.divider()


# ============================================================================
# 性格（軸カテゴリ → 性格の2段階セレクト）
# ============================================================================
st.markdown("#### 🌀 性格")

cur_nature_val = target.get("nature")
cur_axis = find_nature_axis(cur_nature_val)

axis_options = ["（未指定）", *(label for label, _ in NATURE_AXIS_GROUPS)]
default_axis = cur_axis if cur_axis else "（未指定）"
axis_idx = axis_options.index(default_axis) if default_axis in axis_options else 0

nat_cols = st.columns(2)
with nat_cols[0]:
    new_axis_choice = st.selectbox(
        "性格カテゴリ",
        options=axis_options,
        index=axis_idx,
        key=f"e_nature_axis_{target_id}",
        on_change=_reset_nature_pick,
        args=(int(target_id),),
        help="どの軸を上げる性格か。下降軸の組合せで25種が決まる。",
    )

inner_options: list[str] = ["（未指定）"]
for _label, _natures in NATURE_AXIS_GROUPS:
    if _label == new_axis_choice:
        inner_options.extend(_natures)
        break

# 軸が変わっていなくて従来値があれば、それを既定選択にする
if cur_nature_val and cur_nature_val in inner_options and new_axis_choice == cur_axis:
    nature_idx = inner_options.index(cur_nature_val)
elif cur_nature_val and cur_nature_val not in NATURES and new_axis_choice == "（未指定）":
    # 旧データに NATURES 外の文字列が残っているケース: 警告表示用に options に加える
    inner_options.insert(1, cur_nature_val)
    nature_idx = 1
else:
    nature_idx = 0

with nat_cols[1]:
    new_nature_choice = st.selectbox(
        "性格",
        options=inner_options,
        index=nature_idx,
        key=f"e_nature_pick_{target_id}",
        format_func=_nature_select_label,
        disabled=new_axis_choice == "（未指定）",
        help="↓ は下降軸（不利になる軸）。",
    )

new_nature: str | None = (
    None if new_nature_choice == "（未指定）" else new_nature_choice
)

st.divider()


# ============================================================================
# メインスキル
# ============================================================================
st.markdown("#### ⚡ メインスキル")
new_main_skill_name = new_species.get("main_skill") or target.get("main_skill_name") or ""
ms_cols = st.columns([3, 1])
with ms_cols[0]:
    st.text_input(
        "メインスキル名（種族から自動取得）",
        value=new_main_skill_name,
        disabled=True,
        key=f"e_main_skill_name_{target_id}",
    )
with ms_cols[1]:
    new_main_skill_lv = st.number_input(
        "Lv",
        min_value=1,
        max_value=8,
        value=int(target.get("main_skill_level") or 1),
        step=1,
        key=f"e_main_skill_lv_{target_id}",
    )

st.divider()


# ============================================================================
# 食材スロット
# ============================================================================
st.markdown("#### 🥕 食材スロット")
st.caption("スロット1は種族のA食材で確定。スロット2/3は新種族の候補から選択。")

slot1_default = (new_species["ingredients"]["a"] or {}).get("name")
slot2_opts = _slot2_options(new_species)
slot3_opts = _slot3_options(new_species)

slot_cols = st.columns(3)
with slot_cols[0]:
    st.text_input(
        "スロット1（Lv1〜・確定）",
        value=slot1_default or "—",
        disabled=True,
        key=f"e_slot1_{target_id}",
    )
with slot_cols[1]:
    new_slot2 = _slot_radio(
        "スロット2（Lv30〜）",
        target.get("ingredient_2"),
        slot2_opts,
        key=f"e_slot2_{target_id}",
    )
with slot_cols[2]:
    new_slot3 = _slot_radio(
        "スロット3（Lv60〜）",
        target.get("ingredient_3"),
        slot3_opts,
        key=f"e_slot3_{target_id}",
    )

st.divider()


# ============================================================================
# サブスキル
# ============================================================================
st.markdown("#### ⭐ サブスキル")
st.caption("各Lvで解放されるサブスキルを直接編集できます。読み取りミスや誤登録を直すための欄です。")

sorted_subs = sorted(SUBSKILL_OPTIONS, key=_sub_sort_key)
new_subs: dict[int, str | None] = {}
sub_cols = st.columns(5)
for col, lv in zip(sub_cols, SUBSKILL_UNLOCK_LEVELS):
    with col:
        cur_val = target.get(f"subskill_lv{lv}")
        options = ["（未入力）", *sorted_subs]
        if cur_val and cur_val not in options:
            options.insert(1, cur_val)
        idx = options.index(cur_val) if cur_val in options else 0
        choice = st.selectbox(
            f"Lv{lv}",
            options=options,
            index=idx,
            format_func=_sub_label,
            key=f"e_sub_{lv}_{target_id}",
        )
        new_subs[lv] = None if choice == "（未入力）" else choice

st.divider()


# ============================================================================
# 🎀 おやすみリボン
# ============================================================================
st.markdown("#### 🎀 おやすみリボン")
cur_ribbon = int(target.get("sleep_ribbon_stage") or 0)
rib_col_sel, rib_col_img = st.columns([3, 1])
with rib_col_sel:
    ribbon_labels = [lbl for lbl, _ in SLEEP_RIBBON_OPTIONS]
    cur_label = next(
        (lbl for lbl, v in SLEEP_RIBBON_OPTIONS if v == cur_ribbon), ribbon_labels[0]
    )
    new_ribbon_label = st.selectbox(
        "段階",
        options=ribbon_labels,
        index=ribbon_labels.index(cur_label),
        key=f"e_ribbon_{target_id}",
        help="累積眠時間で自動付与される証。所持数+ や時間短縮（進化残り回数別）に効く。",
    )
new_ribbon = dict(SLEEP_RIBBON_OPTIONS).get(new_ribbon_label, 0)
with rib_col_img:
    url = sleep_ribbon_icon_url(new_ribbon)
    if url:
        st.image(url, width=48)

st.divider()


# ============================================================================
# メモ
# ============================================================================
st.markdown("#### 📝 メモ")
new_note = st.text_area(
    "メモ",
    value=target.get("note") or "",
    key=f"e_note_{target_id}",
    label_visibility="collapsed",
)

st.divider()


# ============================================================================
# 保存 / 戻る
# ============================================================================
btn_cols = st.columns([1, 1])
with btn_cols[0]:
    save_clicked = st.button(
        "💾 修正を保存", type="primary", use_container_width=True
    )
with btn_cols[1]:
    if st.button(
        "↩ 個体強化ページに戻る", type="secondary", use_container_width=True
    ):
        st.session_state.pop("edit_target_id", None)
        st.switch_page("views/update.py")

if save_clicked:
    updates: dict = {}
    msgs: list[str] = []

    # 種族
    if new_species_name != target.get("species_name"):
        updates["species_name"] = new_species_name
        msgs.append(f"種族: {target.get('species_name')} → {new_species_name}")

    # ニックネーム
    new_nick_val = new_nickname.strip() or None
    if new_nick_val != target.get("nickname"):
        updates["nickname"] = new_nick_val
        msgs.append(f"ニックネーム: {target.get('nickname') or '未設定'} → {new_nick_val or '未設定'}")

    # 現在Lv
    new_current_val = int(new_current) if new_current > 0 else None
    if new_current_val != target.get("current_level"):
        updates["current_level"] = new_current_val
        msgs.append(f"現在Lv: {target.get('current_level') or '未指定'} → {new_current_val or '未指定'}")

    # 捕獲時Lv
    new_caught_val = int(new_caught) if new_caught > 0 else None
    if new_caught_val != target.get("caught_level"):
        updates["caught_level"] = new_caught_val
        msgs.append(f"捕獲時Lv: {target.get('caught_level') or '未指定'} → {new_caught_val or '未指定'}")

    # 性格
    if new_nature != target.get("nature"):
        updates["nature"] = new_nature
        msgs.append(f"性格: {target.get('nature') or '未指定'} → {new_nature or '未指定'}")

    # メインスキル名（種族変更で自動更新）
    if new_main_skill_name and new_main_skill_name != target.get("main_skill_name"):
        updates["main_skill_name"] = new_main_skill_name
        msgs.append(
            f"メインスキル: {target.get('main_skill_name') or '未指定'} → {new_main_skill_name}"
        )

    # メインスキルLv
    cur_skill_lv = target.get("main_skill_level") or 1
    if int(new_main_skill_lv) != cur_skill_lv:
        updates["main_skill_level"] = int(new_main_skill_lv)
        msgs.append(f"メインスキルLv: {cur_skill_lv} → {new_main_skill_lv}")

    # 食材スロット1（種族変更で自動）
    if slot1_default != target.get("ingredient_1"):
        updates["ingredient_1"] = slot1_default
        msgs.append(f"食材1: {target.get('ingredient_1') or '—'} → {slot1_default or '—'}")
    # 食材スロット2/3
    if new_slot2 != target.get("ingredient_2"):
        updates["ingredient_2"] = new_slot2
        msgs.append(f"食材2: {target.get('ingredient_2') or '—'} → {new_slot2 or '—'}")
    if new_slot3 != target.get("ingredient_3"):
        updates["ingredient_3"] = new_slot3
        msgs.append(f"食材3: {target.get('ingredient_3') or '—'} → {new_slot3 or '—'}")

    # サブスキル
    for lv in SUBSKILL_UNLOCK_LEVELS:
        cur_v = target.get(f"subskill_lv{lv}")
        if new_subs[lv] != cur_v:
            updates[f"subskill_lv{lv}"] = new_subs[lv]
            msgs.append(f"サブLv{lv}: {cur_v or '未入力'} → {new_subs[lv] or '未入力'}")

    # 🎀 おやすみリボン
    if int(new_ribbon) != cur_ribbon:
        updates["sleep_ribbon_stage"] = int(new_ribbon)
        msgs.append(f"おやすみリボン: 段階{cur_ribbon} → 段階{new_ribbon}")

    # メモ
    new_note_val = new_note.strip() or None
    if new_note_val != target.get("note"):
        updates["note"] = new_note_val
        msgs.append("メモ: 更新")

    if not updates:
        st.warning("変更がありません。")
    else:
        db.update_pokemon(int(target_id), **updates)
        st.success("✅ 更新しました：\n\n" + "\n".join(f"- {m}" for m in msgs))
