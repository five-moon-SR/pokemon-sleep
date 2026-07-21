"""パーティー編成ページ。

4つのブロック構成:
  ① 今週の前提（フィールド／料理カテゴリ／候補レシピ／方針タグ）
  ② 候補ポケモン一覧（スコア順）
  ③ 編成中のパーティ（5枠＋総合能力サマリ＋警告）
  ④ パーティの保存・読込・削除

計算・スコアリングの純ロジックは utils/party_logic.py に分離。
"""

from __future__ import annotations

import streamlit as st

import db
from image_utils import berry_icon_url, ingredient_icon_url
from utils.party_logic import (
    get_play_ctx,
    EVENT_BONUSES,
    RECIPE_CATEGORY_LABELS,
    ROLE_LABELS,
    ROLE_PRESETS,
    _effective_level,
    _ingredient_chip,
    _main_recipe_recommendations,
    _main_skill_of,
    _propose_sub_recipes,
    _recipe_progress,
    _role_fulfillment,
    _surplus_after_main,
    compute_role_scores,
    party_summary,
)

st.title("⚔ パーティー編成")
st.caption("今週の前提 → 候補ポケモンスコア → 5体選択 → 保存。スコア係数は暫定。")


# -------------- セッション状態 --------------

db.init_db()
ss = st.session_state
ss.setdefault("party_member_ids", [])  # list[int]
ss.setdefault("party_loaded_id", None)


# 読込ボタンは ④ で押下されるが、その時点で ① の widget は既に描画済みのため、
# widget の key と同名の session_state を直接書き換えると Streamlit がエラーを出す。
# そこで読込ボタンは「次回rerun時に適用する dict」を _pending_load に積み、
# ここ（widget 描画前）で session_state に流し込む pending パターンを使う。
if ss.get("_pending_load") is not None:
    pt = ss["_pending_load"]
    ss.party_member_ids = list(pt.get("member_ids") or [])
    ss.party_loaded_id = pt["id"]
    ss["p_field"] = pt.get("field_name") or "（未選択）"
    ss["p_recipe_cats"] = list(pt.get("recipe_categories") or [])
    ss["p_recipes"] = list(pt.get("candidate_recipes") or [])
    ss["p_random_berries"] = list(pt.get("random_field_berries") or [])
    ss["p_role_preset"] = "✏ カスタム"
    for role_key in ROLE_LABELS:
        ss[f"p_role_{role_key}"] = (pt.get("role_targets") or {}).get(role_key, 0)
    ss["p_events"] = list(pt.get("event_bonuses") or [])
    ss["p_save_name"] = pt.get("name") or ""
    ss["p_save_note"] = pt.get("note") or ""
    if pt.get("main_recipe"):
        ss["p_main_recipe"] = pt["main_recipe"]
    ss["_just_loaded_name"] = pt.get("name") or ""
    ss["_pending_load"] = None


# -------------- ① 今週の前提 --------------

with st.container(border=True):
    st.subheader("① 今週の前提")

    fields = db.list_all_field_records()
    field_options = ["（未選択）"] + [f["name"] for f in fields]
    sel_field_name = st.selectbox("フィールド", field_options, key="p_field")
    sel_field = next((f for f in fields if f["name"] == sel_field_name), None)

    fav_berries: list[str] = []
    if sel_field:
        if sel_field.get("favorite_berries_random"):
            st.caption(
                "🎲 ランダム好物フィールド：週の始まりに3種が決まるので、今週の3種を選んでください。"
            )
            all_berry_names = [b["name"] for b in db.list_all_berry_records()]
            picked = st.multiselect(
                "今週の好みきのみ（最大3種）",
                all_berry_names,
                max_selections=3,
                key="p_random_berries",
            )
            fav_berries = list(picked)
            if fav_berries:
                cols = st.columns(len(fav_berries) + 1)
                cols[0].caption("適用中:")
                for i, name in enumerate(fav_berries):
                    url = berry_icon_url(name)
                    if url:
                        cols[i + 1].markdown(
                            f'<img src="{url}" width="20" style="vertical-align:middle">'
                            f' {name}',
                            unsafe_allow_html=True,
                        )
                    else:
                        cols[i + 1].caption(name)
        else:
            fav_berries = [b["name"] for b in (sel_field.get("favorite_berries") or [])]
            if fav_berries:
                cols = st.columns(len(fav_berries) + 1)
                cols[0].caption("好みのきのみ:")
                for i, name in enumerate(fav_berries):
                    url = berry_icon_url(name)
                    label = f"{name}"
                    if url:
                        cols[i + 1].markdown(
                            f'<img src="{url}" width="20" style="vertical-align:middle">'
                            f' {label}',
                            unsafe_allow_html=True,
                        )
                    else:
                        cols[i + 1].caption(label)

    sel_categories = st.multiselect(
        "作る料理カテゴリ",
        list(RECIPE_CATEGORY_LABELS.values()),
        key="p_recipe_cats",
    )

    all_recipes = db.list_all_recipe_records()
    if sel_categories:
        cat_keys = {k for k, v in RECIPE_CATEGORY_LABELS.items() if v in sel_categories}
        recipe_pool = [r for r in all_recipes if r.get("category") in cat_keys]
    else:
        recipe_pool = all_recipes
    recipe_pool = [r for r in recipe_pool if r.get("ingredients")]
    sel_recipe_names = st.multiselect(
        "候補レシピ（必要食材を ② のスコアに反映）",
        [r["name"] for r in recipe_pool],
        key="p_recipes",
    )

    needed_ings: set[str] = set()
    for rname in sel_recipe_names:
        rec = next((r for r in all_recipes if r["name"] == rname), None)
        if rec:
            for ing in rec.get("ingredients") or []:
                needed_ings.add(ing["name"])

    if needed_ings:
        cols = st.columns(min(len(needed_ings), 6) + 1)
        cols[0].caption("必要食材:")
        for i, name in enumerate(sorted(needed_ings)):
            url = ingredient_icon_url(name)
            slot = cols[(i % 6) + 1]
            if url:
                slot.markdown(
                    f'<img src="{url}" width="20" style="vertical-align:middle"> {name}',
                    unsafe_allow_html=True,
                )
            else:
                slot.caption(name)

    st.divider()
    st.markdown("##### 🎯 役割×目標人数")
    preset_cols = st.columns([3, 1])
    with preset_cols[0]:
        sel_preset = st.selectbox(
            "プリセット",
            list(ROLE_PRESETS.keys()),
            index=1,  # ⚖ バランス
            key="p_role_preset",
            label_visibility="collapsed",
        )
    with preset_cols[1]:
        apply_preset = st.button(
            "📋 適用",
            key="p_preset_apply",
            use_container_width=True,
            disabled=ROLE_PRESETS[sel_preset] is None,
            help="プリセットの値を各スライダーに反映します。",
        )

    if apply_preset and ROLE_PRESETS[sel_preset] is not None:
        for role_key, count in ROLE_PRESETS[sel_preset].items():
            ss[f"p_role_{role_key}"] = count
        st.rerun()

    role_target_cols = st.columns(5)
    role_targets: dict[str, int] = {}
    for i, (role_key, label) in enumerate(ROLE_LABELS.items()):
        with role_target_cols[i]:
            role_targets[role_key] = st.slider(
                label, min_value=0, max_value=5, value=0, step=1,
                key=f"p_role_{role_key}",
            )
    total_target = sum(role_targets.values())
    if total_target > 5:
        st.caption(f"⚠ 目標合計 {total_target}/5 超過")
    else:
        st.caption(f"目標合計: {total_target}/5")

    st.divider()
    sel_event_keys = st.multiselect(
        "✨ 今週のイベント補正（複数可。空＝補正なし週）",
        list(EVENT_BONUSES.keys()),
        format_func=lambda k: EVENT_BONUSES[k],
        key="p_events",
    )

fav_set = set(fav_berries)
event_set = set(sel_event_keys)


# -------------- ①.5 🤖 自動編成提案 --------------

with st.container(border=True):
    st.subheader("🤖 自動編成提案")
    st.caption(
        "①の条件（好みきのみ/候補レシピ/役割目標/イベント）で最適5体を自動探索。"
        "スコア = 主料理 + きのみ + スキルの各エナジー/日 − 役割未充足ペナルティ。"
    )

    if st.button("🔍 最適編成を探索", type="primary", use_container_width=True):
        from utils.optimizer import optimize_party

        target_recipe_recs = [
            r for r in recipe_pool
            if not sel_recipe_names or r["name"] in sel_recipe_names
        ]
        with st.spinner("探索中…（組み合わせを全探索しています）"):
            ss["opt_results"] = optimize_party(
                [dict(r) for r in db.list_pokemon()],
                fav_berries=fav_set,
                event_set=event_set,
                target_recipes=target_recipe_recs,
                role_targets=role_targets,
            )
        if not ss["opt_results"]:
            st.warning("所持ポケモンが5体未満のため探索できません。")

    for rank_i, res in enumerate(ss.get("opt_results") or []):
        with st.container(border=True):
            head = st.columns([4, 1])
            head[0].markdown(
                f"**#{rank_i + 1}**　" + "　".join(f"`{lbl}`" for lbl in res.labels)
            )
            if head[1].button(
                "採用", key=f"opt_adopt_{rank_i}", use_container_width=True
            ):
                ss.party_member_ids = list(res.member_ids)
                ss["opt_results"] = None
                st.rerun()
            detail = (
                f"score **{res.score:,.0f}** ＝ "
                f"🍳 {res.dish_energy:,.0f}"
                + (f"（{res.best_recipe}）" if res.best_recipe else "")
                + f" + 🍓 {res.berry_energy:,.0f} + ⚡ {res.skill_energy:,.0f} en/日"
            )
            if res.role_fulfillment:
                parts = [
                    f"{ROLE_LABELS[k]} {c}/{t}"
                    for k, (c, t) in res.role_fulfillment.items()
                ]
                detail += "　｜　" + " / ".join(parts)
            if res.bottleneck:
                detail += f"　｜　律速: {'、'.join(res.bottleneck)}"
            st.caption(detail)


# -------------- ② 候補ポケモン（役割別） --------------

def _render_role_candidates(
    role_key: str,
    owned_rows: list[dict],
    scores_map: dict[int, dict[str, tuple[float, str] | None]],
    ss,
) -> None:
    candidates = [
        (scores_map[p["id"]][role_key], p)
        for p in owned_rows
        if scores_map[p["id"]][role_key] is not None
    ]
    if not candidates:
        st.info(f"{ROLE_LABELS[role_key]} に該当する所持ポケモンはいません。")
        return
    candidates.sort(key=lambda x: (-x[0][0], x[1]["species_name"]))

    top_n_options = [n for n in (10, 20, 30, len(candidates)) if n <= len(candidates)]
    if not top_n_options:
        top_n_options = [len(candidates)]
    with st.columns([1, 4])[0]:
        top_n = st.selectbox(
            "表示件数", top_n_options, key=f"p_role_topn_{role_key}",
        )

    for (score, breakdown), p in candidates[:top_n]:
        in_party = p["id"] in ss.party_member_ids
        full = len(ss.party_member_ids) >= 5
        master = db.get_species_data(p["species_name"]) or {}

        cols = st.columns([0.6, 2.4, 0.7, 3, 0.9])
        burl = berry_icon_url((master.get("berry") or {}).get("name"))
        cols[0].markdown(
            f'<img src="{burl}" width="32">' if burl else "",
            unsafe_allow_html=True,
        )
        label = (
            f'**{p.get("nickname") or p["species_name"]}** '
            f'({p["species_name"]}) Lv{_effective_level(p)} '
            f'/ {master.get("specialty") or "?"}'
        )
        cols[1].markdown(label)
        cols[2].markdown(f"**{score:.0f}**")
        cols[3].caption(breakdown)
        btn_label = "✓編成中" if in_party else "追加"
        if cols[4].button(
            btn_label,
            key=f"add_{role_key}_{p['id']}",
            disabled=in_party or full,
            use_container_width=True,
        ):
            ss.party_member_ids.append(p["id"])
            st.rerun()


# ② と ③ で共通利用するため、所持ポケと役割スコアを先に計算
owned_rows: list[dict] = [dict(r) for r in db.list_pokemon()]
scores_map: dict[int, dict[str, tuple[float, str] | None]] = {}
for p in owned_rows:
    master = db.get_species_data(p["species_name"]) or {}
    scores_map[p["id"]] = compute_role_scores(
        p, master, fav_set, event_set, needed_ings
    )

with st.container(border=True):
    st.subheader("② 候補ポケモン（役割別）")
    st.caption(
        "①で設定した役割の目標数 / イベント補正 / 候補レシピが各タブのスコアに反映されます。"
    )

    if not owned_rows:
        st.info("所持ポケモンがいません。先に「個体登録」から追加してください。")
    else:
        roles_with_target = [k for k in ROLE_LABELS if role_targets.get(k, 0) > 0]
        roles_to_show = roles_with_target or list(ROLE_LABELS.keys())

        tab_labels = []
        for k in roles_to_show:
            tgt = role_targets.get(k, 0)
            tab_labels.append(
                f"{ROLE_LABELS[k]}" + (f" (目標{tgt})" if tgt > 0 else "")
            )

        tabs = st.tabs(tab_labels)
        for tab, role_key in zip(tabs, roles_to_show):
            with tab:
                _render_role_candidates(role_key, owned_rows, scores_map, ss)


# -------------- ③ 編成中のパーティ --------------

with st.container(border=True):
    st.subheader(f"③ 編成中のパーティ（{len(ss.party_member_ids)}/5）")

    if not ss.party_member_ids:
        st.caption("まだ未編成。② から「追加」してください。")
    else:
        slot_cols = st.columns(5)
        for i in range(5):
            with slot_cols[i]:
                if i < len(ss.party_member_ids):
                    mid = ss.party_member_ids[i]
                    row = db.get_pokemon(mid)
                    if row is None:
                        st.warning("削除済み")
                        if st.button("外す", key=f"rm_{i}_missing"):
                            ss.party_member_ids.pop(i)
                            st.rerun()
                        continue
                    m = dict(row)
                    master = db.get_species_data(m["species_name"]) or {}
                    burl = berry_icon_url((master.get("berry") or {}).get("name"))
                    if burl:
                        st.markdown(
                            f'<img src="{burl}" width="40">', unsafe_allow_html=True
                        )
                    st.markdown(
                        f"**{m.get('nickname') or m['species_name']}**  \n"
                        f"{m['species_name']}  \nLv{_effective_level(m)}"
                    )
                    st.caption(_main_skill_of(m, master) or "?")
                    if st.button("外す", key=f"rm_{i}"):
                        ss.party_member_ids.pop(i)
                        st.rerun()
                else:
                    st.caption("（空き枠）")

    if ss.party_member_ids:
        summary = party_summary(
            ss.party_member_ids, fav_berries=fav_set, field_bonus=0.0
        )

        team_help = summary["team_help_bonus_count"]
        if team_help > 0:
            st.info(
                f"🤝 **team-buff**: おてつだいボーナス装着 {team_help} 人 "
                f"→ 全員のスピード ×{1.0 + 0.05 * team_help:.2f}（食材・きのみ獲得に反映済）"
            )

        st.markdown("**🍓 きのみ獲得（1日あたり個数 ／ エナジー）**")
        if summary["berries"]:
            cols = st.columns(min(len(summary["berries"]), 5))
            sorted_berries = sorted(
                summary["berries"].items(), key=lambda x: -x[1]["energy"]
            )
            for i, (name, data) in enumerate(sorted_berries):
                url = berry_icon_url(name)
                fav_mark = " ⭐" if data["is_favorite"] else ""
                count_text = f"×{data['count']:.1f}/日"
                energy_text = f"{int(round(data['energy'])):,} en"
                with cols[i % len(cols)]:
                    if url:
                        st.markdown(
                            f'<img src="{url}" width="22"> {name}{fav_mark}<br>'
                            f'{count_text} ／ {energy_text}',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(f"{name}{fav_mark} {count_text} ／ {energy_text}")

        st.markdown("**🥕 食材1日獲得期待値（性格/サブ/Lv/リボン補正込み）**")
        if summary["ingredients"]:
            cols = st.columns(min(len(summary["ingredients"]), 5))
            for i, (name, qty) in enumerate(sorted(summary["ingredients"].items(), key=lambda x: -x[1])):
                url = ingredient_icon_url(name)
                with cols[i % len(cols)]:
                    if url:
                        st.markdown(
                            f'<img src="{url}" width="22"> {name} ×{qty:.1f}/日',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(f"{name} ×{qty:.1f}/日")
        else:
            st.caption("—")

        st.markdown("**🎯 メインスキル構成**")
        skill_text = "、".join(summary["main_skills"]) if summary["main_skills"] else "—"
        st.write(skill_text)

        warnings: list[str] = []

        fulfillment = _role_fulfillment(ss.party_member_ids, role_targets, scores_map)
        if fulfillment:
            st.markdown("**🎯 役割充足度**")
            for role_key, (curr, tgt) in fulfillment.items():
                ratio = min(curr / tgt, 1.0) if tgt > 0 else 0.0
                icon = "✅" if curr >= tgt else "🔸"
                fcols = st.columns([3, 1])
                fcols[0].progress(ratio)
                fcols[1].markdown(f"{icon} **{ROLE_LABELS[role_key]}**: {curr} / {tgt}")
                if curr < tgt:
                    warnings.append(
                        f"{ROLE_LABELS[role_key]} 目標 {tgt} に対して現在 {curr} 体"
                    )

        if sel_recipe_names:
            st.markdown("**🍳 レシピ達成進捗**（1日獲得期待値ベース・律速食材で日数決定）")
            for prog in _recipe_progress(summary["ingredients"], sel_recipe_names, all_recipes):
                req_text = " / ".join(f"{k}×{v}" for k, v in prog["required"].items())
                if prog["days"] == float("inf"):
                    miss_text = " / ".join(
                        f"{k}×{v:g}" for k, v in prog["missing"].items()
                    )
                    st.warning(
                        f"❌ **{prog['name']}** — 不足食材: {miss_text}（必要: {req_text}）"
                    )
                else:
                    d = prog["days"]
                    day_text = (
                        f"{d:.1f} 日"
                        if d < 7
                        else f"{d/7:.1f} 週間（{d:.0f} 日）"
                    )
                    st.write(
                        f"🍳 **{prog['name']}** — 約 **{day_text}** で完成（必要: {req_text}）"
                    )

        st.divider()
        st.markdown("##### 🍽 主料理＋つなぎ料理提案")

        # 主料理プール: ①の候補レシピがあればそこから、なければカテゴリ絞り、それもなければ全レシピ
        if sel_recipe_names:
            main_pool = [r for r in all_recipes if r["name"] in sel_recipe_names]
            pool_label = "①の候補レシピ"
        elif sel_categories:
            cat_keys = {k for k, v in RECIPE_CATEGORY_LABELS.items() if v in sel_categories}
            main_pool = [
                r for r in all_recipes
                if r.get("category") in cat_keys and r.get("ingredients")
            ]
            pool_label = "①の料理カテゴリ"
        else:
            main_pool = [r for r in all_recipes if r.get("ingredients")]
            pool_label = "全レシピ"

        if not main_pool:
            st.caption("主料理候補がありません。①でレシピかカテゴリを選んでください。")
        else:
            recs = _main_recipe_recommendations(
                main_pool, summary["ingredients"], event_set
            )

            if not recs:
                st.caption(f"主料理プール: {pool_label}（{len(main_pool)}件）")
                st.warning(
                    "現在の編成では作成可能な主料理候補がありません。"
                    "律速食材の獲得手段を編成してください。"
                )
            else:
                dish_2x_note = " 🍳2x週" if "dish_2x" in event_set else ""
                st.caption(
                    f"主料理プール: {pool_label}（{len(main_pool)}件、作成可能 {len(recs)}件）"
                    f"／ 1日あたり期待エナジー降順{dish_2x_note}"
                )

                # 現在の選択。未設定 or 候補外 ならトップを採用。
                rec_names = [r["recipe"]["name"] for r in recs]
                if ss.get("p_main_recipe") not in rec_names:
                    ss["p_main_recipe"] = rec_names[0]
                current = ss["p_main_recipe"]

                def _render_main_row(rank: int, r: dict) -> None:
                    rec = r["recipe"]
                    is_current = rec["name"] == current
                    cols = st.columns([0.4, 3, 2.2, 1.4, 0.9])
                    cols[0].markdown(f"**#{rank}**")
                    cat_label = RECIPE_CATEGORY_LABELS.get(
                        rec.get("category"), rec.get("category") or ""
                    )
                    cols[1].markdown(f"**{rec['name']}**  \n_{cat_label}_")
                    cols[2].markdown(
                        f"<b>{int(round(r['daily_energy'])):,}</b> en/日<br>"
                        f"<span style='color:#666; font-size:0.9em'>"
                        f"{int(r['base_energy']):,}en × {r['pace']:.2f}回</span>",
                        unsafe_allow_html=True,
                    )
                    cols[3].caption(
                        "🔻 " + " / ".join(r["bottleneck"]) if r["bottleneck"] else "—"
                    )
                    btn_label = "✓選択中" if is_current else "選択"
                    if cols[4].button(
                        btn_label,
                        key=f"p_main_pick_{rec['name']}",
                        disabled=is_current,
                        use_container_width=True,
                    ):
                        ss["p_main_recipe"] = rec["name"]
                        st.rerun()

                show_top = 5
                for rank, r in enumerate(recs[:show_top], 1):
                    _render_main_row(rank, r)

                if len(recs) > show_top:
                    with st.expander(
                        f"残り {len(recs) - show_top} 件を表示", expanded=False
                    ):
                        for rank, r in enumerate(recs[show_top:], show_top + 1):
                            _render_main_row(rank, r)

                sel = next(r for r in recs if r["recipe"]["name"] == current)
                main_recipe = sel["recipe"]
                pace = sel["pace"]
                bottleneck = sel["bottleneck"]

                mc1, mc2, mc3 = st.columns([1, 1, 2])
                mc1.metric("作成可能 / 日", f"{pace:.2f} 回")
                mc2.metric("完成までの日数", f"{1/pace:.1f} 日")
                mc3.metric(
                    "🔻 律速食材",
                    " / ".join(bottleneck) if bottleneck else "—",
                )

                surplus = _surplus_after_main(main_recipe, pace, summary["ingredients"])

                with st.expander(f"📦 余剰食材（主料理を {pace:.2f}回/日 で作る前提）", expanded=False):
                    if surplus:
                        cols = st.columns(min(len(surplus), 5))
                        for i, (name, qty) in enumerate(
                            sorted(surplus.items(), key=lambda x: -x[1])
                        ):
                            url = ingredient_icon_url(name)
                            with cols[i % len(cols)]:
                                if url:
                                    st.markdown(
                                        f'<img src="{url}" width="22"> {name} ×{qty:.1f}/日',
                                        unsafe_allow_html=True,
                                    )
                                else:
                                    st.markdown(f"{name} ×{qty:.1f}/日")
                    else:
                        st.caption("—")

                st.markdown("**🍳 つなぎ料理候補**（余剰食材で作れる別レシピ・スコア順）")
                filter_cols = st.columns([1, 3])
                with filter_cols[0]:
                    sub_min_energy = st.number_input(
                        "🚫 最小1個エナジー",
                        min_value=0,
                        max_value=10000,
                        value=0,
                        step=500,
                        key="p_sub_min_energy",
                        help=(
                            "これ未満の base エナジーのレシピは候補から除外。"
                            "単一食材で量産可能だが1個あたりエナジーが低い料理を弾きたい時に。"
                            "0 で全候補表示。"
                        ),
                    )
                sel_cat_keys = {
                    k for k, v in RECIPE_CATEGORY_LABELS.items() if v in sel_categories
                }
                pot_capacity = get_play_ctx().pot_capacity
                sub_candidates = _propose_sub_recipes(
                    main_recipe, surplus, set(bottleneck),
                    all_recipes, sel_cat_keys, pot_capacity,
                    top_n=8, min_base_energy=int(sub_min_energy),
                )
                if not sub_candidates:
                    st.caption("つなぎ料理候補なし。余剰食材が少ないか、必要食材が揃いません。")
                else:
                    st.caption(
                        "🍳 = 余剰だけで作れる ／ 🥄 = ストック前提（先週の残りなどで補う）"
                        " ／ 並び順は 1日あたり期待エナジー降順"
                    )
                    for cand in sub_candidates:
                        rec = cand["recipe"]
                        badges = []
                        if cand["consumes_bottleneck"]:
                            badges.append("⚠律速食材使用")
                        if not cand["fits_pot"]:
                            badges.append(
                                f"❌鍋超過({cand['total_ingredients']}>{pot_capacity})"
                            )
                        badge_text = " ".join(badges)

                        req_chips = "".join(
                            _ingredient_chip(ing["name"], ing["count"])
                            for ing in (rec.get("ingredients") or [])
                        )

                        base_e = cand.get("base_energy", 0)
                        daily_e = cand.get("daily_energy", 0)
                        if cand["mode"] == "surplus":
                            energy_text = (
                                f"{int(base_e):,}en × {cand['max_create']:.2f}回 "
                                f"≒ <b>{int(daily_e):,} en/日</b>"
                            )
                            head_line = f"🍳 <b>{rec['name']}</b> — {energy_text}"
                            extra = ""
                        else:
                            shortage_chips = "".join(
                                _ingredient_chip(n, s)
                                for n, s in sorted(
                                    cand["shortage_items"].items(),
                                    key=lambda x: -x[1],
                                )
                            )
                            energy_text = (
                                f"1個 {int(base_e):,}en"
                                f"（充足率 {cand['progress']*100:.0f}%）"
                            )
                            head_line = f"🥄 <b>{rec['name']}</b> — {energy_text}"
                            extra = f"<div style='margin-left:1.5em'>あと {shortage_chips}で作れる</div>"
                        if badge_text:
                            head_line += f" <span style='color:#c66'>{badge_text}</span>"

                        st.markdown(
                            f"<div style='margin:6px 0'>{head_line}</div>"
                            f"{extra}"
                            f"<div style='margin-left:1.5em; color:#666; font-size:0.9em'>"
                            f"必要: {req_chips}</div>",
                            unsafe_allow_html=True,
                        )

        if warnings:
            for w in warnings:
                st.warning(w)
        elif fulfillment:
            st.success("役割の条件をクリア")


# -------------- ④ 保存・読込 --------------

with st.container(border=True):
    st.subheader("④ 保存・読込")

    if ss.get("_just_loaded_name"):
        st.success(f"読み込みました: {ss['_just_loaded_name']}")
        ss["_just_loaded_name"] = None

    save_cols = st.columns([3, 2, 1])
    with save_cols[0]:
        party_name = st.text_input(
            "パーティ名",
            value=f"{sel_field_name if sel_field else ''}編成"
            if sel_field
            else "",
            key="p_save_name",
        )
    with save_cols[1]:
        note = st.text_input("メモ（任意）", key="p_save_note")
    with save_cols[2]:
        st.write("")
        st.write("")
        if st.button(
            "💾 保存",
            disabled=not party_name or not ss.party_member_ids,
            use_container_width=True,
        ):
            payload = {
                "name": party_name,
                "field_name": sel_field_name if sel_field else None,
                "recipe_categories": sel_categories,
                "candidate_recipes": sel_recipe_names,
                "member_ids": ss.party_member_ids,
                "note": note,
                "random_field_berries": fav_berries
                if sel_field and sel_field.get("favorite_berries_random")
                else [],
                "role_targets": role_targets,
                "event_bonuses": list(event_set),
                "main_recipe": ss.get("p_main_recipe") or None,
            }
            if ss.party_loaded_id:
                db.update_party(ss.party_loaded_id, **payload)
                st.success(f"上書き保存しました（id={ss.party_loaded_id}）")
            else:
                new_id = db.insert_party(payload)
                ss.party_loaded_id = new_id
                st.success(f"新規保存しました（id={new_id}）")
            st.rerun()

    st.divider()
    parties = db.list_parties()
    if not parties:
        st.caption("まだ保存されたパーティはありません。")
    else:
        for pt in parties:
            cols = st.columns([3, 2, 2, 1, 1])
            cols[0].markdown(
                f"**{pt['name']}** "
                f"({pt.get('field_name') or '—'})"
            )
            cols[1].caption(
                "／".join(pt.get("policy_tags") or []) or "—"
            )
            cols[2].caption(f"{len(pt.get('member_ids') or [])}体・{pt.get('updated_at','')[:16]}")
            if cols[3].button("読込", key=f"load_{pt['id']}"):
                # widget 描画後の直接書き換えは Streamlit が拒否するため、
                # ここでは _pending_load にだけ積んで rerun。次回描画の冒頭で適用する。
                ss["_pending_load"] = pt
                st.rerun()
            if cols[4].button("削除", key=f"del_{pt['id']}"):
                db.delete_party(pt["id"])
                if ss.party_loaded_id == pt["id"]:
                    ss.party_loaded_id = None
                st.rerun()

    if ss.party_member_ids or ss.party_loaded_id:
        if st.button("🆕 新規編成（クリア）"):
            ss.party_member_ids = []
            ss.party_loaded_id = None
            st.rerun()
