"""エナジー以外の目的で組む1日限りの編成（ゆめのかけら / おやすみリボン）。

通常の「編成」ページは週エナジーを最大化する。だが実際には
「今週はもう十分だから、かけらを稼ぐ日／リボンを進める日にする」という運用がある。
その2つはどちらも週エナジーの物差しでは0点になるので、ここで別建てに評価する。
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import db
from image_utils import pokemon_image_url
from ui import components as c
from utils import goal_teams

st.html(c.page_banner("目的別編成", "bag", icon="🌙"))

owned = db.list_pokemon()
if not owned:
    st.html(c.empty_state("所持ポケモンが登録されていません。先に「個体登録」から登録してください。"))
    st.stop()


def _label(p: dict) -> str:
    return f"{p.get('nickname') or p['species_name']}"


shard_tab, ribbon_tab = st.tabs(["💠 ゆめのかけら稼ぎ", "🎀 一緒に寝た時間（リボン）"])

# ---------------------------------------------------------------------------
# ゆめのかけら
# ---------------------------------------------------------------------------
with shard_tab:
    st.caption(
        "ゆめのかけらは週エナジーに一切乗らないので、通常の編成計算では"
        "かけら型は「何も出さない子」として扱われます。ここだけは"
        "**1日あたりのかけら期待値**で組みます。"
    )

    holders = [
        p
        for p in owned
        if goal_teams._skill_effect(p, db.get_species_data(p["species_name"]) or {})[0]
        == goal_teams.SHARD_CATEGORY
    ]
    if not holders:
        st.html(
            c.empty_state(
                "ゆめのかけらゲットS を持つ個体が登録されていません。"
                "（プクリン系・ヨノワール系などが該当します）"
            )
        )
    else:
        st.caption(f"かけらゲットS 持ち: **{len(holders)}体**")

        @st.cache_data(show_spinner="かけら編成を探索中…", ttl=600)
        def _best(signature: str):
            team = goal_teams.best_shard_team(owned)
            if team is None:
                return None
            return {
                "rows": [
                    {
                        "id": int(r.pokemon.get("id") or 0),
                        "label": _label(r.pokemon),
                        "species": r.pokemon["species_name"],
                        "role": r.role,
                        "acts": r.activations,
                        "per": r.per_activation,
                        "shards": r.shards,
                    }
                    for r in team.rows
                ],
                "total": team.shards_per_day,
                "help": team.help_bonus_count,
                "heal": team.healer_boost,
            }

        signature = ";".join(
            f"{p.get('id')}:{p.get('current_level')}:{p.get('main_skill_level')}"
            for p in owned
        )
        best = _best(signature)

        if not best:
            st.html(c.empty_state("編成を組めませんでした（所持数が5体に満たない可能性があります）。"))
        else:
            st.html(
                c.stat_tiles(
                    [
                        c.stat_tile("かけら / 日", f"{best['total']:,.0f}"),
                        c.stat_tile("かけら / 週", f"{best['total'] * 7:,.0f}"),
                        c.stat_tile(
                            "稼働ボーナス",
                            f"+{best['heal'] * 100:.1f}%",
                            sub=f"おてつだいボーナス {best['help']}体",
                        ),
                    ]
                )
            )
            df = pd.DataFrame(
                [
                    {
                        "": pokemon_image_url(r["species"]),
                        "個体": r["label"],
                        "種族": r["species"],
                        "役割": r["role"],
                        "発動/日": round(r["acts"], 2),
                        "1発動あたり": round(r["per"]),
                        "かけら/日": round(r["shards"]),
                    }
                    for r in sorted(best["rows"], key=lambda x: -x["shards"])
                ]
            )
            st.dataframe(
                df,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "": st.column_config.ImageColumn("", width="small"),
                    "1発動あたり": st.column_config.NumberColumn("1発動あたり", format="%d"),
                    "かけら/日": st.column_config.NumberColumn("かけら/日", format="%d"),
                },
            )
            st.caption(
                "「回復」「サポート」役はかけらを出しませんが、げんき回復と"
                "おてつだいボーナスでかけら型の発動回数を底上げするために入っています。"
            )
            st.caption(
                "※ ゆびをふる／スキルコピー は抽選でかけらを出すことがありますが、"
                "期待値が定まらないためこの計算には入れていません。"
            )

# ---------------------------------------------------------------------------
# おやすみリボン
# ---------------------------------------------------------------------------
with ribbon_tab:
    st.caption(
        "おやすみリボンは**一緒に寝た累計時間**が 200 / 500 / 1000 / 2000 時間を跨ぐと上がり、"
        "おてつだい時間が最大25%短くなります。時間は**編成に入れていた5体にだけ**積まれるので、"
        "「今日は誰を連れて寝るか」がそのまま将来の強さになります。"
    )
    st.info(
        "時間短縮は**進化を残している個体ほど大きい**（最終進化形は所持数が増えるだけ）。"
        "リボンを稼ぐ日に連れて行くべきなのは、原則として進化前の個体です。",
        icon="💡",
    )

    sort_by = st.segmented_control(
        "優先の付け方",
        list(goal_teams.SORT_KEYS),
        default="効率",
        key="ribbon_sort",
        help="効率 = 恩恵 ÷ 残り時間（1時間寝るごとの得）。あと少しで上がる子が上に来ます。",
    ) or "効率"

    rows = goal_teams.ribbon_priorities(owned, sort_by=sort_by)
    # st.stop() は使わない（タブの外まで止めてしまい、かけらタブごと消える）
    if not rows:
        st.html(c.empty_state("全個体がリボン最終段階に到達しています。"))

    unknown = sum(1 for r in rows if not r.hours_known)
    top = rows[: goal_teams.TEAM_SIZE]
    if top:
        st.markdown("#### 今日連れて寝る5体")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "": pokemon_image_url(r.pokemon["species_name"]),
                        "個体": _label(r.pokemon),
                        "いま": f"リボン{r.stage}" if r.stage else "リボンなし",
                        "次": f"リボン{r.next_stage}",
                        "残り": (
                            f"{r.remaining_hours:,.0f}h（推定）"
                            if r.remaining_is_estimate
                            else f"{r.remaining_hours:,.0f}h"
                        ),
                        "上がると": (
                            f"おてつだい +{r.speed_gain * 100:.1f}%"
                            if r.speed_gain > 0
                            else f"所持数 +{r.inventory_gain}"
                        ),
                    }
                    for r in top
                ]
            ),
            hide_index=True,
            use_container_width=True,
            column_config={"": st.column_config.ImageColumn("", width="small")},
        )
    if unknown:
        st.caption(
            f"累計時間が未入力の個体が **{unknown}体** あります。"
            "未入力は「今の段階に着いたばかり」＝いちばん遠いと安全側に見積もっているので、"
            "分かるものを下で入れると順位が正確になります。"
        )

    # ── 累計時間の入力 ────────────────────────────────────────────────
    st.markdown("#### 一緒に寝た時間を入れる")
    st.caption(
        "ゲーム内のポケモン詳細で見られる累計時間。分かるものだけでかまいません"
        "（空欄のままでも動きます）。"
    )
    only_unknown = st.toggle("未入力の個体だけ表示", value=False, key="ribbon_only_unknown")
    query = st.text_input("名前で絞り込み", key="ribbon_q", placeholder="例: ピチュー").strip()

    editable = [r for r in rows if not (only_unknown and r.hours_known)]
    if query:
        editable = [
            r
            for r in editable
            if query in (r.pokemon.get("nickname") or "")
            or query in r.pokemon["species_name"]
        ]
    editable = editable[:200]

    if not editable:
        st.caption("条件に合う個体がいません。")
    else:
        base = pd.DataFrame(
            [
                {
                    "id": int(r.pokemon.get("id") or 0),
                    "個体": _label(r.pokemon),
                    "種族": r.pokemon["species_name"],
                    "リボン": r.stage,
                    "累計時間": r.hours,
                }
                for r in editable
            ]
        )
        edited = st.data_editor(
            base,
            hide_index=True,
            use_container_width=True,
            height=min(560, 44 + 36 * len(base)),
            disabled=["id", "個体", "種族", "リボン"],
            column_config={
                "id": None,
                "リボン": st.column_config.NumberColumn("リボン", width="small"),
                "累計時間": st.column_config.NumberColumn(
                    "累計時間(h)", min_value=0.0, max_value=100000.0, step=10.0,
                    help="一緒に寝た累計時間。空欄は未入力。",
                ),
            },
            key="ribbon_hours_editor",
        )

        changes = []
        for old, new in zip(base.itertuples(), edited.itertuples()):
            old_h = None if pd.isna(old.累計時間) else float(old.累計時間)
            new_h = None if pd.isna(new.累計時間) else float(new.累計時間)
            if old_h != new_h:
                changes.append((int(old.id), old.個体, new_h))

        if changes:
            st.markdown(f"**変更 {len(changes)}件**")
            for _pid, label, hours in changes[:20]:
                st.caption(f"・{label} → {'未入力' if hours is None else f'{hours:,.0f}h'}")
            if st.button(f"{len(changes)}件を保存", type="primary", key="save_sleep_hours"):
                for pid, _label_, hours in changes:
                    db.update_pokemon(pid, sleep_hours=hours)
                st.cache_data.clear()
                st.success(f"{len(changes)}件を保存しました。")
                st.rerun()
