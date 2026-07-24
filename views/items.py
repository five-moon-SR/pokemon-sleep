"""レベル・希少アイテムを誰へ投資するか比較するページ。"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import db
from ui import components as c
from ui.widgets import pokemon_popover_row
from utils.item_simulation import (
    analyze_subskill_seed,
    level_up_priorities,
    main_skill_item_priorities,
    nature_item_priorities,
    simulate_items,
    subskill_item_priorities,
    subskill_seed_paths,
)
from utils.plan_simulation import level_improvements
from utils.play_context import load_play_context


INVENTORY_KEY = "user.item_inventory"
ITEM_DEFAULTS = {
    "main_skill_seed": 0,
    "subskill_seed": 0,
    "neutralizing_mint": 0,
}


def _label(p: dict) -> str:
    level = p.get("current_level") or p.get("caught_level") or p.get("level") or 1
    return f"{p.get('nickname') or p['species_name']}｜{p['species_name']} Lv{level}"


@st.cache_data(show_spinner=False, ttl=300)
def _rankings(owned_rows: list[dict]) -> dict:
    return {
        "level": level_up_priorities(owned_rows),
        "main": main_skill_item_priorities(owned_rows),
        "sub": subskill_item_priorities(owned_rows),
        "mint": nature_item_priorities(owned_rows),
    }


st.html(c.page_banner("育成・アイテム戦略", "green", icon="🎁"))
st.caption("レベル・メインスキルのたね・サブスキルのたね・まっしろミントの投資先を比較する。")
db.init_db()
owned = [dict(row) for row in db.list_pokemon()]
owned_by_id = {int(p["id"]): p for p in owned}
if not owned:
    st.html(c.empty_state("所持ポケモンがいません。先に個体登録してください。"))
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

rankings = _rankings(owned)
saved_plans = [plan for plan in db.list_parties() if plan.get("recipe_category")]
plan_memberships: dict[int, list[str]] = {}
for plan in saved_plans:
    for pokemon_id in plan.get("member_ids") or []:
        plan_memberships.setdefault(int(pokemon_id), []).append(plan["name"])

st.html(
    c.stat_tiles(
        [
            c.stat_tile("メイン種", str(int(inventory["main_skill_seed"])), sub="個"),
            c.stat_tile("サブ種", str(int(inventory["subskill_seed"])), sub="個"),
            c.stat_tile("ミント", str(int(inventory["neutralizing_mint"])), sub="最大2個"),
        ]
    )
)

level_tab, main_tab, sub_tab, mint_tab, detail_tab = st.tabs(
    ["🌱 レベル上げ", "⚡ メイン種", "⭐ サブ種", "🌿 ミント", "🔎 個体比較"]
)

with level_tab:
    st.markdown("##### 保存済み攻略プラン内の優先度")
    st.caption("固定5体をLv30・60へ上げた時の、主料理を含む週期待エナジー改善。")
    ctx = load_play_context()
    recipes = {recipe["name"]: recipe for recipe in db.list_all_recipe_records()}
    fields = {field["name"]: field for field in db.list_all_field_records()}
    plan_rows = []
    for plan in saved_plans:
        recipe = recipes.get(plan.get("main_recipe"))
        field = fields.get(plan.get("field_name"))
        members = [
            owned_by_id[int(pokemon_id)]
            for pokemon_id in (plan.get("member_ids") or [])
            if int(pokemon_id) in owned_by_id
        ]
        if not recipe or not field or len(members) != 5:
            continue
        favorites = {x["name"] for x in (field.get("favorite_berries") or [])}
        for result in level_improvements(
            members,
            recipe,
            fav_berries=favorites,
            ctx=ctx,
        ):
            if result["energy_delta"] <= 0 and result["stability_delta"] <= 0:
                continue
            plan_rows.append(
                {
                    "プラン": plan["name"],
                    "個体": result["label"],
                    "目標": f"Lv{result['target_level']}",
                    "安定度": f"{result['stability_delta']:+.0%}",
                    "週改善": result["energy_delta"],
                }
            )
    plan_rows.sort(key=lambda row: -row["週改善"])
    if plan_rows:
        st.dataframe(
            pd.DataFrame(plan_rows[:20]),
            hide_index=True,
            use_container_width=True,
            column_config={
                "週改善": st.column_config.NumberColumn(
                    "週改善", format="%+.0f en"
                )
            },
        )
    else:
        st.html(c.empty_state("比較できる保存済み攻略プランがありません。"))

    st.markdown("##### 手札全体の次マイルストーン")
    st.caption("食材枠・サブスキル解放までの汎用評価改善を、必要Lv数で割った効率順。")
    level_rows = [
        {
            "個体": item.label,
            "現在": f"Lv{item.current_level}",
            "目標": f"Lv{item.target_level}",
            "解放": item.unlock,
            "改善": round(item.delta, 1),
            "1Lv効率": round(item.delta_per_level, 2),
            "使用プラン": " / ".join(plan_memberships.get(item.pokemon_id, [])) or "—",
        }
        for item in rankings["level"][:30]
    ]
    st.dataframe(pd.DataFrame(level_rows), hide_index=True, use_container_width=True)

with main_tab:
    st.caption("最終進化・Lv60時点でメインスキルのたねを1個使った改善順。進化によるLv上昇は先に加味。")
    for index, item in enumerate(rankings["main"][:20], 1):
        pokemon_popover_row(
            owned_by_id.get(item.pokemon_id),
            label=f"#{index} {item.label}",
            img_species=item.final_species,
            badges_text=f"+{item.delta:.1f}",
            caption=(
                f"{item.detail}｜最大まで残り{item.seeds_required}個｜"
                f"使用プラン {' / '.join(plan_memberships.get(item.pokemon_id, [])) or 'なし'}"
            ),
        )

with sub_tab:
    st.caption(
        "現在解放済みで、強化先を別枠に持っていないサブスキルだけが抽選対象。"
        "候補1個なら確定、複数ならランダムです。"
    )
    for index, item in enumerate(rankings["sub"][:20], 1):
        lottery = "確定" if item.probability >= 1 else f"各{item.probability:.0%}"
        range_text = (
            f"{item.worst_delta:+.1f}〜{item.best_delta:+.1f}"
            if item.worst_delta is not None and item.best_delta is not None
            else f"{item.delta:+.1f}"
        )
        pokemon_popover_row(
            owned_by_id.get(item.pokemon_id),
            label=f"#{index} {item.label}",
            img_species=item.species_name,
            badges_text=f"期待 +{item.delta:.1f}",
            caption=f"{lottery}｜幅 {range_text}｜{item.detail}",
        )

with mint_tab:
    st.warning("まっしろミントは最大2個所持・使用後に元へ戻せません。プラス補正も消える点に注意。")
    st.caption("最終進化・Lv60時点で、性格補正を完全に無効化した時の改善順。")
    for index, item in enumerate(rankings["mint"][:20], 1):
        pokemon_popover_row(
            owned_by_id.get(item.pokemon_id),
            label=f"#{index} {item.label}",
            img_species=item.final_species,
            badges_text=f"+{item.delta:.1f}",
            caption=(
                f"{item.detail}｜"
                f"使用プラン {' / '.join(plan_memberships.get(item.pokemon_id, [])) or 'なし'}"
            ),
        )

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
                    f"{outcome.from_sub}→{outcome.to_sub}"
                    for outcome in analysis.outcomes
                )
                or "—",
                "ブロック": " / ".join(
                    f"{blocked.from_sub}（{blocked.reason}）"
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
                "強化順": " → ".join(path.steps) or "使用不可",
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
