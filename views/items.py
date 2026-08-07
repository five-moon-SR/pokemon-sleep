"""レベル・希少などうぐを誰へ投資するか比較するページ。"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from constants import format_subskill_short
import db
from image_utils import pokemon_image_url
from ui import components as c
from utils.item_simulation import (
    analyze_subskill_seed,
    simulate_items,
    subskill_seed_paths,
)
from utils import recipe_level
from utils.play_context import load_play_context
from utils.roster_impact import (
    ImpactRow,
    baseline_insertions,
    item_impact_ranking,
    load_plan_portfolio,
)


INVENTORY_KEY = "user.item_inventory"
ITEM_DEFAULTS = {
    "main_skill_seed": 0,
    "subskill_seed": 0,
    "neutralizing_mint": 0,
}


def _label(p: dict) -> str:
    level = p.get("current_level") or p.get("caught_level") or p.get("level") or 1
    return f"{p.get('nickname') or p['species_name']}｜{p['species_name']} Lv{level}"


@st.cache_data(show_spinner="投資先を計算中…", ttl=300)
def _impact(owned_rows: list[dict], _signature: str) -> dict:
    """全プランの週エナジー改善で4種のアイテムを並べる。

    _signature にプラン構成を畳んで渡すことで、編成を保存し直したら
    キャッシュが外れるようにしている（プランはこの関数の引数に現れないため）。
    """
    ctx = load_play_context()
    owned_by_id = {int(p["id"]): p for p in owned_rows}
    plans = load_plan_portfolio(owned_by_id, ctx=ctx)
    base_map = baseline_insertions(owned_rows, plans, ctx=ctx)
    return {
        "plans": plans,
        **{
            kind: item_impact_ranking(
                owned_rows, kind, plans=plans, base_map=base_map, ctx=ctx
            )
            for kind in ("level", "main", "sub", "mint")
        },
    }


# 内訳は全部並べると読めないので、上位だけ出して残りは件数で示す
BREAKDOWN_LIMIT = 5


def _stance_badge(row: ImpactRow) -> str:
    if row.enters_plan:
        return c.text_badge("🆕 定番入り")
    if row.in_plan:
        return c.text_badge("使用中")
    return c.text_badge("ベンチ")


def _impact_row(row: ImpactRow, index: int, unit: str, *, actionable: bool) -> None:
    """投資候補1行。actionable=False は実戦の改善が無い（評価値だけの）候補。"""
    if actionable:
        # 今週ぶんが一番動かしやすい数字なので先に出し、合計は根拠として下に添える
        head = (
            f"今週 <b>+{row.this_week_delta:,.0f}</b> en"
            if row.this_week_delta > 0
            else "今週 <b>—</b>"
        )
        right = f"{head}<br><small>全{len(row.plan_deltas)}プラン計 +{row.raw_delta:,.0f}</small>"
    else:
        right = f"育成後評価 <b>{row.eval_delta:+.1f}</b>"
    badges = [_stance_badge(row)]
    if row.tier:
        badges.append(c.text_badge(f"ティア {row.tier}"))
    top = row.plan_deltas[0] if row.plan_deltas else None
    sub = row.detail
    if row.seeds_required and unit:
        sub += f"｜あと {row.seeds_required}{unit}"
    # 内訳が複数あるときは下の展開に同じ情報が出るので、主行では繰り返さない。
    # 詰め込むと2行に収まらず、肝心の「何をするか」まで切れてしまう。
    if top and len(row.plan_deltas) == 1:
        swap = f"（{top.replaced_label} と交代）" if top.replaced_label else ""
        sub += f"｜{top.plan_name} +{top.delta:,.0f}en{swap}"
    st.html(c.result_row(
        title=f"#{index} {row.label}",
        subtitle=sub,
        badges=badges,
        right=right,
        img_url=pokemon_image_url(row.final_species),
    ))
    if len(row.plan_deltas) > 1:
        with st.expander(f"　{row.label}：どのプランが伸びるか（{len(row.plan_deltas)}件）"):
            for d in row.plan_deltas[:BREAKDOWN_LIMIT]:
                mark = "★今週 " if d.is_this_week else ""
                how = f"（{d.replaced_label} と交代）" if d.replaced_label else "（そのまま強化）"
                st.markdown(f"- {mark}**{d.plan_name}** +{d.delta:,.0f} en/週 {how}")
            rest = len(row.plan_deltas) - BREAKDOWN_LIMIT
            if rest > 0:
                st.caption(f"ほか {rest} プランでも伸びます")


def _impact_list(rows: list[ImpactRow], *, limit: int = 20, unit: str = "") -> None:
    """投資候補を並べる。

    「今週 +N en」と「評価 +N.N」を同じリストに混ぜると単位が読めなくなるので、
    実戦で動く候補と、評価値しか動かない候補は節を分ける。
    """
    if not rows:
        st.html(c.empty_state("使えるアイテムの当てがありません。"))
        return
    actionable = [r for r in rows if r.weighted_delta > 0]
    eval_only = [r for r in rows if r.weighted_delta <= 0]

    for index, row in enumerate(actionable[:limit], 1):
        _impact_row(row, index, unit, actionable=True)

    if eval_only:
        rest = limit - len(actionable)
        if rest > 0:
            st.markdown("---")
            st.caption(
                "ここから下は**登録済みプランの週エナジーが動かない**候補です。"
                "育成後評価の伸びだけで並べています。"
            )
            for index, row in enumerate(eval_only[:rest], 1):
                _impact_row(row, index, unit, actionable=False)


st.html(c.page_banner("育成・どうぐ", "green", icon="🎁"))
st.caption("レベル・メインスキルのたね・サブスキルのたね・まっしろミントの使い先を比較する。")
db.init_db()
owned = [dict(row) for row in db.list_pokemon()]
owned_by_id = {int(p["id"]): p for p in owned}
if not owned:
    st.html(c.empty_state("所持ポケモンがいません。先に仲間登録してください。"))
    st.stop()

inventory = {**ITEM_DEFAULTS, **(db.get_setting(INVENTORY_KEY, {}) or {})}
with st.expander("アイテム在庫", expanded=True):
    with st.form("item_inventory_form"):
        cols = st.columns(3)
        main_count = cols[0].number_input(
            "メインスキルのたね",
            min_value=0,
            max_value=999,
            value=int(inventory["main_skill_seed"]),
        )
        sub_count = cols[1].number_input(
            "サブスキルのたね",
            min_value=0,
            max_value=999,
            value=int(inventory["subskill_seed"]),
        )
        mint_count = cols[2].number_input(
            "まっしろミント",
            min_value=0,
            max_value=2,
            value=min(2, int(inventory["neutralizing_mint"])),
        )
        if st.form_submit_button("在庫を保存", use_container_width=True):
            inventory = {
                "main_skill_seed": int(main_count),
                "subskill_seed": int(sub_count),
                "neutralizing_mint": int(mint_count),
            }
            db.set_setting(INVENTORY_KEY, inventory)
            st.success("アイテム在庫を保存しました")

saved_plans = [plan for plan in db.list_parties() if plan.get("recipe_category")]
plan_signature = "|".join(
    f"{plan['id']}:{plan.get('updated_at')}:{plan.get('main_recipe')}:{plan.get('member_ids')}"
    for plan in sorted(saved_plans, key=lambda x: int(x["id"]))
) + f"|week={(db.get_setting('user.active_strategy_week', {}) or {}).get('plan_id')}"
# 料理レベルを変えると週エナジーが動くので、署名に混ぜないと古い順位が返る
plan_signature += "|lv=" + recipe_level.levels_signature()

impact = _impact(owned, plan_signature)
plans = impact["plans"]
field_count = len(db.list_all_field_records())
slots_total = field_count * 3
this_week = next((p for p in plans if p.is_this_week), None)

st.html(
    c.stat_tiles(
        [
            c.stat_tile("メイン種", str(int(inventory["main_skill_seed"])), sub="個"),
            c.stat_tile("サブ種", str(int(inventory["subskill_seed"])), sub="個"),
            c.stat_tile("ミント", str(int(inventory["neutralizing_mint"])), sub="最大2個"),
            c.stat_tile("定番プラン", f"{len(plans)}/{slots_total}", sub="フィールド×料理"),
        ]
    )
)

if not plans:
    st.warning(
        "定番プランが1件も揃っていないので、実戦での改善量が測れません。"
        "「おてつだいチーム → チーム編成」で各フィールドのチームを保存すると、"
        "ここが評価値順ではなく**週エナジーの実改善順**になります。"
    )
    st.caption("いまは育成後評価の伸び（×種族ティア）で並べています。")
else:
    head = f"今週は **{this_week.name}** を重く見ています。" if this_week else (
        "今週のプランが未設定なので、全プランを同じ重みで見ています。"
    )
    st.caption(
        f"{head} 登録済み {len(plans)} プランの週エナジーが"
        f"どれだけ伸びるかで並べています（ベンチは差し込んで伸びれば上位に来ます）。"
        + (f" 残り {slots_total - len(plans)} 枠を埋めるほど精度が上がります。"
           if len(plans) < slots_total else "")
    )

level_tab, main_tab, sub_tab, mint_tab, detail_tab = st.tabs(
    ["🌱 レベル上げ", "⚡ メイン種", "⭐ サブ種", "🌿 ミント", "🔎 個体比較"]
)

with level_tab:
    st.caption("次の解放マイルストーンまで上げた時の実改善。食材枠（Lv30/60）が特に効きます。")
    _impact_list(impact["level"], unit="Lv")

with main_tab:
    st.caption("メインスキルのたね1個で、メインスキルLvを1つ上げた時の実改善。")
    _impact_list(impact["main"], unit="個")

with sub_tab:
    st.caption(
        "解放済みかつ強化先を別枠に持たないサブスキルだけが抽選対象。"
        "複数候補ならランダムなので、ここは期待値（分岐の確率で均した値）です。"
    )
    _impact_list(impact["sub"])

with mint_tab:
    st.warning("まっしろミントは最大2個所持・使用後に元へ戻せません。プラス補正も消える点に注意。")
    st.caption("性格補正を完全に無効化した時の実改善。下降補正で損している個体ほど伸びます。")
    _impact_list(impact["mint"])

with detail_tab:
    selected_id = st.selectbox(
        "比較する個体",
        list(owned_by_id),
        format_func=lambda pokemon_id: _label(owned_by_id[pokemon_id]),
        key="item_detail_pokemon",
    )
    target = owned_by_id[int(selected_id)]
    sim = simulate_items(target)
    st.markdown(f"##### {_label(target)}")
    metrics = st.columns(3)
    metrics[0].metric(
        "メイン種1個",
        f"{sim.main_seed_total:.1f}",
        f"{sim.main_seed_delta:+.1f}",
    )
    metrics[1].metric(
        "ミント",
        f"{sim.nature_neutral_total:.1f}",
        f"{sim.nature_neutral_delta:+.1f}",
    )
    metrics[2].metric("育成後ベース", f"{sim.base_total:.1f}", sim.base_rank)

    current_level = int(
        target.get("current_level")
        or target.get("caught_level")
        or target.get("level")
        or 1
    )
    analyses = [
        analyze_subskill_seed(target, at_level=level)
        for level in dict.fromkeys([current_level, 30, 60])
        if level >= current_level
    ]
    seed_rows = []
    for analysis in analyses:
        seed_rows.append(
            {
                "時点": f"Lv{analysis.at_level}",
                "抽選数": len(analysis.outcomes),
                "判定": (
                    "確定"
                    if analysis.is_guaranteed
                    else "使用不可"
                    if not analysis.outcomes
                    else "ランダム"
                ),
                "期待改善": round(analysis.expected_delta, 1),
                "抽選対象": " / ".join(
                    f"{format_subskill_short(outcome.from_sub)}→{format_subskill_short(outcome.to_sub)}"
                    for outcome in analysis.outcomes
                )
                or "—",
                "ブロック": " / ".join(
                    f"{format_subskill_short(blocked.from_sub)}（{blocked.reason}）"
                    for blocked in analysis.blocked
                )
                or "—",
            }
        )
    st.dataframe(pd.DataFrame(seed_rows), hide_index=True, use_container_width=True)

    if int(inventory["subskill_seed"]) > 0:
        paths = subskill_seed_paths(
            target,
            seed_count=min(3, int(inventory["subskill_seed"])),
        )
        path_rows = [
            {
                "確率": f"{path.probability:.0%}",
                "使用数": path.used_seeds,
                "強化順": " → ".join(
                    "→".join(format_subskill_short(part) for part in step.split("→"))
                    for step in path.steps
                ) or "使用不可",
                "改善": f"{path.delta:+.1f}",
            }
            for path in paths
        ]
        st.markdown(
            f"###### 所持銀種{inventory['subskill_seed']}個のうち"
            f"{min(3, int(inventory['subskill_seed']))}個まで使う分岐"
        )
        st.dataframe(pd.DataFrame(path_rows), hide_index=True, use_container_width=True)

with st.expander("判定ルールと参照情報"):
    st.markdown(
        """
- サブスキルのたねは、解放済みかつ強化可能な候補からランダムに1枠を強化します。
- 強化後と同じサブスキルを5枠のどこかに持つ場合、未解放でもその候補は抽選対象外です。
- 例：おてつだいスピードSとMを同時所持している間は、SをMへ強化できません。
- まっしろミントは性格のプラス・マイナス補正を両方なくし、最大2個まで所持できます。

[サブスキルのたねが使用できない条件（公式サポート）](https://app-psl.pokemon-support.com/hc/ja/articles/25819530448665--%E3%82%B5%E3%83%96%E3%82%B9%E3%82%AD%E3%83%AB%E3%81%AE%E3%81%9F%E3%81%AD-%E3%81%8C%E4%BD%BF%E7%94%A8%E3%81%A7%E3%81%8D%E3%81%BE%E3%81%9B%E3%82%93)

[まっしろミントの効果・所持上限（公式サイト）](https://www.pokemonsleep.net/news/343138353434383532363837333838363733/)
"""
    )
