import streamlit as st

import db
from constants import (
    NATURE_AXIS_GROUPS,
    NATURES,
    SUBSKILL_OPTIONS,
    SUBSKILL_RARITY_EMOJI,
    SUBSKILL_RARITY_ORDER,
    SUBSKILL_UNLOCK_LEVELS,
    format_nature_label,
    get_subskill_rarity,
)
from image_utils import sleep_ribbon_icon_url
from ui import components as c


def _sub_sort_key(name: str) -> tuple[int, str]:
    """金→青→白 → 名前 の順にソート（旧表記も自動マッチ）。"""
    rarity = get_subskill_rarity(name)
    return (SUBSKILL_RARITY_ORDER[rarity], name)


def _sub_filter_label(name: str) -> str:
    """selectbox 表示用: 「🟡 きのみの数S」等。プレースホルダはそのまま。"""
    if name in ("（未入力）", "（未解放）"):
        return name
    rarity = get_subskill_rarity(name)
    return f"{SUBSKILL_RARITY_EMOJI[rarity]} {name}"


# Streamlit selectbox の検索でひらがな入力も拾えるように、
# 表示文字列に ZWSP で区切ってひらがな読みを併記する。
ZWSP = "​"


def _katakana_to_hiragana(text: str) -> str:
    return "".join(
        chr(ord(c) - 0x60) if 0x30A1 <= ord(c) <= 0x30F6 else c
        for c in text
    )


def _searchable_label(species_name: str) -> str:
    return f"{species_name}{ZWSP}{_katakana_to_hiragana(species_name)}"


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


SUB_SLOT_KEYS: tuple[str, ...] = (
    "sub_lv10_select",
    "sub_lv25_select",
    "sub_lv50_select",
    "sub_lv75_select",
    "sub_lv100_select",
)


def _nature_select_label(name: str) -> str:
    """selectbox 用: プレースホルダはそのまま、それ以外は format_nature_label に委譲。"""
    if name == "（未指定）":
        return name
    return format_nature_label(name)


def _reset_nature_pick() -> None:
    """軸カテゴリが変わったら性格セレクトをリセット（前の選択肢が新カテゴリに無いと不整合になるため）。"""
    st.session_state.pop("nature_select", None)


SLEEP_RIBBON_OPTIONS: list[tuple[str, int]] = [
    ("なし（未獲得）", 0),
    ("段階1（200h）", 1),
    ("段階2（500h）", 2),
    ("段階3（1,000h）", 3),
    ("段階4（2,000h）", 4),
]


RESET_KEYS = [
    "species_select",
    "lv_input",
    "lv_step",
    "nature_axis",
    "nature_select",
    "main_skill_lv_input",
    "slot2_radio",
    "slot3_radio",
    *SUB_SLOT_KEYS,
    "nickname_input",
    "note_input",
    "sleep_ribbon_select",
]


def _apply_lv_step() -> None:
    """±ボタンの選択を Lv に反映して、選択自体は解除する（同じ幅を連打できるように）。"""
    delta = st.session_state.get("lv_step")
    if delta:
        _bump_level(int(delta))
    st.session_state.lv_step = None


def _reset_form() -> None:
    """入力欄を全部クリア（on_click から呼ぶと次の実行前に効くので rerun 不要）。"""
    for k in RESET_KEYS:
        st.session_state.pop(k, None)


def _bump_level(delta: int) -> None:
    """lv_input を delta だけ増減（[0, 65] にクランプ）。"""
    cur = int(st.session_state.get("lv_input", 0) or 0)
    st.session_state.lv_input = max(0, min(65, cur + delta))


st.title("📝 個体登録")

species_names = db.list_species_names()
if not species_names:
    st.warning(
        "マスターデータが見つかりません。"
        "`python scripts/build_master.py` を実行してマスターを生成してください。"
    )
    st.stop()


# ============================================================================
# ステップ1: 種族選択 --------------------------------------------------------
# ============================================================================

header_cols = st.columns([4, 1])
with header_cols[0]:
    st.markdown("**1️⃣ ポケモンを選ぶ**")
with header_cols[1]:
    st.button("🔄 入力リセット", help="全フォームをクリア", on_click=_reset_form)

label_to_name = {_searchable_label(n): n for n in species_names}
selected_label = st.selectbox(
    "所持中の個体（進化前でもOK・ひらがなでも検索可）",
    options=list(label_to_name.keys()),
    index=None,
    placeholder="種族を選択…（例: ふしぎだね / ピカチュウ）",
    format_func=lambda lbl: lbl.split(ZWSP)[0],
    key="species_select",
)
species_name = label_to_name.get(selected_label) if selected_label else None

if not species_name:
    st.info("種族を選ぶと、続きのフォームを表示します。")
    st.stop()

species = db.get_species_data(species_name)
if not species:
    st.error("マスターに見つかりませんでした。マスターを再生成してください。")
    st.stop()

# 種族の素性は metric 4枚だと縦を食うので、1〜2行のキャプションに畳む
berry = species["berry"]
a = species["ingredients"]["a"]
st.caption(
    f"No.{species['dex_no']} ／ {species['sleep_type']} ／ 得意: {species['specialty']}"
    f" ／ 基準秒: {species['base_assist_seconds']}"
)
st.caption(
    f"🌳 **{berry['name']}** ×{berry['qty']}　／　"
    f"🥕 **{a['name']}** ×{a['qty'][0] if a['qty'] else '?'}（Lv1〜確定）　／　"
    f"⚡ **{species['main_skill']}**"
)


# ============================================================================
# ステップ2: Lv --------------------------------------------------------------
# ============================================================================

st.markdown("**2️⃣ Lv**")

lv_cols = st.columns([1, 1])
with lv_cols[0]:
    lv_input = st.number_input(
        "Lv",
        min_value=0,
        max_value=65,
        value=0,
        step=1,
        key="lv_input",
        label_visibility="collapsed",
        help="0=未指定。捕獲時Lv＝現在Lv として保存。",
    )
with lv_cols[1]:
    # ±1 は入力欄そのものの − + で足りるので、ボタンは10刻みだけ。
    # st.button の列は最小幅でスマホだと折り返すので、横に詰まる segmented control で置く
    st.segmented_control(
        "Lv調整",
        options=[-10, 10],
        format_func=lambda v: f"{v:+d}",
        selection_mode="single",
        default=None,
        key="lv_step",
        label_visibility="collapsed",
        on_change=_apply_lv_step,
    )


# ============================================================================
# ステップ3: 食材スロット2・3 -----------------------------------------------
# ============================================================================

st.markdown(
    f"**3️⃣ 食材パターン**　<small>スロット1は {a['name'] if a else '—'} で確定</small>",
    unsafe_allow_html=True,
)

slot2_opts = _slot2_options(species)
slot3_opts = _slot3_options(species)

# スロット1は種族で確定なので入力欄を置かず、2列ぶんの幅をスロット2/3に回す
col_s2, col_s3 = st.columns(2)
with col_s2:
    slot2_label = st.radio(
        "スロット2（Lv30〜）",
        options=[lbl for lbl, _ in slot2_opts],
        index=None,
        key="slot2_radio",
        help="Lv30で解放。抽選候補は事前に判るので、Lv未到達でも先行入力可。",
    )
with col_s3:
    slot3_label = st.radio(
        "スロット3（Lv60〜）",
        options=[lbl for lbl, _ in slot3_opts],
        index=None,
        key="slot3_radio",
        help="Lv60で解放。抽選候補は事前に判るので、Lv未到達でも先行入力可。",
    )


# ============================================================================
# ステップ4: サブスキル ------------------------------------------------------
# ============================================================================

st.markdown(
    "**4️⃣ サブスキル**　<small>金→青→白の順。未解放でも判っていれば先行入力可</small>",
    unsafe_allow_html=True,
)

_SUB_OPTIONS = ["（未入力）", *sorted(SUBSKILL_OPTIONS, key=_sub_sort_key)]

sub_choices: dict[str, str | None] = {}
# 5列だとスマホで選択中の名前が「（未入…」まで潰れて読めないので2列
sub_cols = [c2 for _ in range(3) for c2 in st.columns(2)]
for col, key, unlock_lv in zip(sub_cols, SUB_SLOT_KEYS, SUBSKILL_UNLOCK_LEVELS):
    with col:
        sub_choices[key] = st.selectbox(
            f"Lv{unlock_lv}",
            options=_SUB_OPTIONS,
            index=0,
            key=key,
            format_func=_sub_filter_label,
            filter_mode=None,  # スマホでキーボードを出さない（サブスキル17件なので検索不要）
        )


# ============================================================================
# ステップ5: せいかく --------------------------------------------------------
# ============================================================================

st.markdown("**5️⃣ せいかく**")

nature_cols = st.columns(2)
with nature_cols[0]:
    axis_options = ["（未指定）", *(label for label, _ in NATURE_AXIS_GROUPS)]
    axis_choice = st.selectbox(
        "性格カテゴリ",
        options=axis_options,
        index=0,
        key="nature_axis",
        filter_mode=None,  # スマホでキーボードを出さない（性格カテゴリなので検索不要）
        on_change=_reset_nature_pick,
        help="どの軸を上げる性格か。下降軸の組合せで25種が決まる。",
    )

    inner_options: list[str] = ["（未指定）"]
    for label, natures in NATURE_AXIS_GROUPS:
        if label == axis_choice:
            inner_options.extend(natures)
            break

with nature_cols[1]:
    nature_choice = st.selectbox(
        "性格",
        options=inner_options,
        index=0,
        key="nature_select",
        filter_mode=None,  # スマホでキーボードを出さない（性格25件なので検索不要）
        format_func=_nature_select_label,
        disabled=axis_choice == "（未指定）",
        help="↓ は下降軸（不利になる軸）。",
    )


# ============================================================================
# 任意項目 ------------------------------------------------------------------
# ============================================================================

with st.expander("📝 任意項目（メインスキルLv / ニックネーム / 🎀リボン / メモ）", expanded=False):
    # メインスキルLv は捕獲時点で 1 のことがほとんどなので、既定値のまま畳んでおく。
    main_skill_lv_input = st.number_input(
        "メインスキルLv",
        min_value=1,
        max_value=8,
        value=1,
        step=1,
        key="main_skill_lv_input",
        help="捕獲時点で既に上昇済みなら指定。未上昇は 1（通常はこのまま）。",
    )

    nickname = st.text_input("ニックネーム", key="nickname_input")

    rib_col_sel, rib_col_img = st.columns([3, 1])
    with rib_col_sel:
        ribbon_label = st.selectbox(
            "🎀 おやすみリボン",
            options=[lbl for lbl, _ in SLEEP_RIBBON_OPTIONS],
            index=0,
            key="sleep_ribbon_select",
            filter_mode=None,  # スマホでキーボードを出さない（リボン5件なので検索不要）
            help="累積眠時間で自動付与される証。所持数+ や時間短縮（進化残り回数別）に効く。",
        )
    sleep_ribbon_stage = dict(SLEEP_RIBBON_OPTIONS).get(ribbon_label, 0)
    with rib_col_img:
        url = sleep_ribbon_icon_url(sleep_ribbon_stage)
        if url:
            st.image(url, width=48)

    note = st.text_area("メモ", key="note_input")


# ============================================================================
# 登録ボタン -----------------------------------------------------------------
# ={76}

errors: list[str] = []
if lv_input <= 0:
    errors.append("Lvを1以上で指定")
if slot2_opts and lv_input >= 30 and not slot2_label:
    errors.append("食材スロット2を選択")
if slot3_opts and lv_input >= 60 and not slot3_label:
    errors.append("食材スロット3を選択")
if nature_choice == "（未指定）":
    errors.append("性格を指定")

ready = not errors
submit = st.button(
    "登録する",
    type="primary",
    disabled=not ready,
    help=" / ".join(errors) if errors else None,
)

if submit and ready:
    slot2_name = dict(slot2_opts).get(slot2_label) if slot2_label else None
    slot3_name = dict(slot3_opts).get(slot3_label) if slot3_label else None

    def _sub_value(choice: str | None) -> str | None:
        if not choice or choice in ("（未入力）", "（未解放）"):
            return None
        return choice

    nickname_val = nickname.strip() or species_name
    lv_val = int(lv_input)
    row_data: dict = {
        "species_name": species_name,
        "nickname": nickname_val,
        "level": lv_val,
        "caught_level": lv_val,
        "current_level": lv_val,
        "nature": nature_choice,
        "main_skill_name": species["main_skill"],
        "main_skill_level": int(main_skill_lv_input),
        "ingredient_1": a["name"] if a else None,
        "ingredient_2": slot2_name,
        "ingredient_3": slot3_name,
        "subskill_lv10": _sub_value(sub_choices.get("sub_lv10_select")),
        "subskill_lv25": _sub_value(sub_choices.get("sub_lv25_select")),
        "subskill_lv50": _sub_value(sub_choices.get("sub_lv50_select")),
        "subskill_lv75": _sub_value(sub_choices.get("sub_lv75_select")),
        "subskill_lv100": _sub_value(sub_choices.get("sub_lv100_select")),
        "sleep_ribbon_stage": int(sleep_ribbon_stage),
        "note": note.strip() or None,
    }
    new_id = db.insert_pokemon(row_data)
    msg = f"登録しました (id={new_id}): {species_name}"
    if row_data["nickname"]:
        msg += f"「{row_data['nickname']}」"
    st.success(msg)

    # 登録直後にその場で評価を出す（所持ポケデータへ回らないと判らないのは面倒なので）
    from utils.evaluator import evaluate_and_save, evaluate_potential

    try:
        ev = evaluate_and_save(new_id)
        pot = evaluate_potential(db.get_pokemon(new_id))
    except Exception as exc:  # 評価が転んでも「登録は成功した」事実は消さない
        st.caption(f"評価の計算に失敗しました（登録自体は完了しています）: {exc}")
    else:
        st.toast(
            f"{nickname_val}の評価 ｜ 現在 {ev.species_rank}（種族内 {ev.species_total:.1f}）"
            f" → 育成後 {pot.species_rank}（{pot.species_total:.1f}）",
            icon="⭐",
        )

        st.markdown(c.section_header("この個体の評価"), unsafe_allow_html=True)
        st.markdown(
            c.stat_tiles([
                c.stat_tile("現在 種族内", f"{ev.species_total:.1f}", ev.species_rank),
                c.stat_tile("現在 全体", f"{ev.global_total:.1f}", ev.global_rank),
                c.stat_tile("育成後 種族内", f"{pot.species_total:.1f}", pot.species_rank),
                c.stat_tile("育成後 全体", f"{pot.global_total:.1f}", pot.global_rank),
            ]),
            unsafe_allow_html=True,
        )
        if ev.strengths:
            st.markdown("**強み**: " + " / ".join(ev.strengths))
        if ev.weaknesses:
            st.markdown("**弱み**: " + " / ".join(ev.weaknesses))
        st.caption(
            "「育成後」は最終進化形 × Lv60 想定（メインスキルLvは進化ぶん加算）。"
            "詳しい内訳は ボックス → 所持ポケデータ で見られます。"
        )

    # 連続登録の動線。評価を見た流れでそのまま次の個体へ入れる
    st.button(
        "🆕 次のポケモンを入力",
        type="primary",
        key="reset_after_register",
        on_click=_reset_form,
        use_container_width=True,
        help="入力を全部クリアして種族選択に戻る",
    )
