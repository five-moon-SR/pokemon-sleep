"""フィールド×料理カテゴリの定番5体を管理する攻略プラン画面。"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import db
from image_utils import field_icon_url, ingredient_icon_url, pokemon_image_url
from ui import components as c
from ui.widgets import pokemon_popover_row
from utils.ingredient_coverage import build_ingredient_index, versatile_mains
from utils.party_logic import EVENT_BONUSES, RECIPE_CATEGORY_LABELS
from utils.plan_simulation import (
    capture_improvements,
    level_improvements,
    simulate_plan,
)
from utils.play_context import load_play_context
from utils.skill_role_coverage import skill_role_audit
from utils.strategy_optimizer import suggest_strategy_plans


ACTIVE_WEEK_KEY = "user.active_strategy_week"
CATEGORY_ORDER = ("curry_stew", "salad", "drink_dessert")

st.html(c.page_banner("攻略プラン", "cyan", icon="🧭"))
st.caption("今週の料理カテゴリからフィールドを選び、主料理1品と固定5体を育てる。")
db.init_db()
ss = st.session_state
ctx = load_play_context()


def _field_favorites(field: dict, random_names: list[str]) -> set[str]:
    if field.get("favorite_berries_random"):
        return set(random_names)
    return {x["name"] for x in (field.get("favorite_berries") or [])}


def _member_label(p: dict) -> str:
    lv = p.get("current_level") or p.get("caught_level") or p.get("level") or 1
    return f"{p.get('nickname') or p['species_name']}｜{p['species_name']} Lv{lv}"


def _sim_metrics(sim) -> None:
    cols = st.columns(4)
    cols[0].metric("3食安定度", f"{sim.stability:.0%}", f"{sim.cooked_meals}/21食")
    cols[1].metric("主料理", f"{sim.cooked_per_day:.2f} 回/日")
    cols[2].metric("週期待エナジー", f"{sim.weekly_energy:,.0f}")
    cols[3].metric(
        "げんきオール効果",
        f"+{sim.healer_team_boost:.1%}",
        f"{sim.healer_activation_per_day:.2f}回/日",
    )


@st.cache_data(show_spinner=False, ttl=300)
def _cached_skill_roles(owned_rows: list[dict]) -> list:
    """所持更新時だけ、最終進化後のスキル役割を再監査する。"""
    return skill_role_audit(owned_rows)


@st.cache_data(show_spinner=False, ttl=300)
def _cached_ingredient_index(owned_rows: list[dict]) -> dict:
    """全食材の担当逆引きを短時間キャッシュする。"""
    return build_ingredient_index(owned_rows)


# ── 週初めの入口：料理カテゴリ → フィールド ────────────────────────────
st.html(c.section_header("今週の入口"))
category = st.radio(
    "料理カテゴリ",
    CATEGORY_ORDER,
    format_func=lambda x: RECIPE_CATEGORY_LABELS[x],
    horizontal=True,
    key="strategy_category",
)
fields = db.list_all_field_records()
field_name = st.selectbox(
    "フィールド",
    [f["name"] for f in fields],
    key="strategy_field",
)
field = next(f for f in fields if f["name"] == field_name)
field_url = field_icon_url(field_name)
if field_url:
    st.html(
        f'<img src="{field_url}" style="width:100%;max-width:520px;'
        'height:120px;object-fit:cover;border-radius:16px;margin-bottom:8px">'
    )

strategy_key = f"{category}:{field_name}"
plan = db.get_strategy_plan(field_name, category)
if ss.get("_strategy_loaded_key") != strategy_key:
    ss["_strategy_loaded_key"] = strategy_key
    ss["strategy_member_ids"] = list(plan.get("member_ids") or []) if plan else []
    ss["strategy_main_recipe"] = plan.get("main_recipe") if plan else None
    ss["strategy_note"] = plan.get("note") or "" if plan else ""
    ss.pop("_strategy_suggestions", None)
    ss.pop("_capture_results", None)

active_week = db.get_setting(ACTIVE_WEEK_KEY, {}) or {}
is_active = bool(plan and active_week.get("plan_id") == plan.get("id"))
if is_active:
    st.success("✓ この組み合わせが今週の攻略プランです")
elif plan:
    st.info("保存済みの定番プランがあります。必要なら今週のプランに設定できます。")
else:
    st.warning("この組み合わせの定番プランは未作成です。所持個体から候補を作ります。")

all_berries = [b["name"] for b in db.list_all_berry_records()]
week_defaults = active_week if is_active else {}
with st.expander("今週だけの条件", expanded=field.get("favorite_berries_random", False)):
    event_labels = list(EVENT_BONUSES.values())
    default_event_labels = [
        EVENT_BONUSES[k]
        for k in week_defaults.get("event_bonuses", [])
        if k in EVENT_BONUSES
    ]
    selected_event_labels = st.multiselect(
        "イベント補正",
        event_labels,
        default=default_event_labels,
        key=f"strategy_events_{strategy_key}",
    )
    event_set = {k for k, v in EVENT_BONUSES.items() if v in selected_event_labels}
    if field.get("favorite_berries_random"):
        random_berries = st.multiselect(
            "今週の好みきのみ（最大3種）",
            all_berries,
            default=week_defaults.get("random_berries", []),
            max_selections=3,
            key=f"strategy_random_{strategy_key}",
        )
    else:
        random_berries = []

fav_berries = _field_favorites(field, random_berries)
recipes = [
    r
    for r in db.list_all_recipe_records()
    if r.get("category") == category and r.get("ingredients")
]
recipe_map = {r["name"]: r for r in recipes}
owned = [dict(p) for p in db.list_pokemon()]
owned_map = {int(p["id"]): p for p in owned}
all_recipe_map = {r["name"]: r for r in db.list_all_recipe_records()}
saved_plans = db.list_parties()


def _plan_fit_count(species_name: str) -> int:
    """保存済み攻略プランのうち、この種族が必要食材を担当できる件数。"""
    master = db.get_species_data(species_name) or {}
    available = {
        slot.get("name")
        for slot in (master.get("ingredients") or {}).values()
        if isinstance(slot, dict) and slot.get("name")
    }
    count = 0
    for saved in saved_plans:
        rec = all_recipe_map.get(saved.get("main_recipe"))
        if not saved.get("recipe_category") or not rec:
            continue
        needed = {x["name"] for x in (rec.get("ingredients") or [])}
        if available & needed:
            count += 1
    return count


# ── 自動提案 ──────────────────────────────────────────────────────────────
def _run_suggestions() -> None:
    with st.spinner("主料理と5体を探索し、上位案を7日間シミュレーション中…"):
        ss["_strategy_suggestions"] = suggest_strategy_plans(
            owned,
            recipes,
            fav_berries=fav_berries,
            ctx=ctx,
        )


if not plan and "_strategy_suggestions" not in ss:
    _run_suggestions()

suggest_col, reset_col = st.columns([3, 1])
if suggest_col.button(
    "✨ 主料理＋5体を自動提案",
    use_container_width=True,
    type="primary" if not plan else "secondary",
):
    _run_suggestions()
    st.rerun()
if reset_col.button("編成を空にする", use_container_width=True):
    ss["strategy_member_ids"] = []
    ss["strategy_main_recipe"] = None
    ss["_strategy_clear_members"] = strategy_key
    st.rerun()

suggestions = ss.get("_strategy_suggestions") or []
if suggestions:
    st.markdown("#### 自動提案")
    for idx, suggestion in enumerate(suggestions, 1):
        sim = suggestion.simulation
        with st.container(border=True):
            head, action = st.columns([5, 1])
            healer = "💚ヒーラーあり" if suggestion.has_healer else "ヒーラーなし"
            head.markdown(
                f"**#{idx}　{suggestion.recipe_name}**　{healer}  \n"
                + " / ".join(suggestion.member_labels)
            )
            head.caption(
                f"安定度 {sim.stability:.0%}｜{sim.cooked_meals}/21食｜"
                f"週 {sim.weekly_energy:,.0f} en"
            )
            if action.button("採用", key=f"adopt_strategy_{strategy_key}_{idx}"):
                ss["strategy_member_ids"] = suggestion.member_ids
                ss["_strategy_pending_members"] = {
                    "key": strategy_key,
                    "ids": suggestion.member_ids,
                }
                ss["strategy_main_recipe"] = suggestion.recipe_name
                ss["_strategy_pending_recipe"] = suggestion.recipe_name
                st.rerun()


# ── 主料理と固定5体の編集 ───────────────────────────────────────────────
st.html(c.section_header("定番プラン"))
current_recipe = ss.get("strategy_main_recipe")
if current_recipe not in recipe_map:
    current_recipe = recipes[0]["name"] if recipes else None
    ss["strategy_main_recipe"] = current_recipe
recipe_names = list(recipe_map)
recipe_widget_key = f"strategy_recipe_widget_{strategy_key}"
if ss.get("_strategy_pending_recipe") in recipe_map:
    ss[recipe_widget_key] = ss.pop("_strategy_pending_recipe")
picked_recipe = st.selectbox(
    "主料理",
    recipe_names,
    index=recipe_names.index(current_recipe) if current_recipe in recipe_names else 0,
    key=recipe_widget_key,
)
ss["strategy_main_recipe"] = picked_recipe
recipe = recipe_map[picked_recipe]

requirements = {x["name"]: int(x["count"]) for x in recipe.get("ingredients") or []}
chips = []
for name, qty in requirements.items():
    chips.append(c.icon_chip(ingredient_icon_url(name), f"{name} ×{qty}", size=24))
st.html('<div style="display:flex;flex-wrap:wrap;gap:5px">' + "".join(chips) + "</div>")

member_ids = list(ss.get("strategy_member_ids") or [])
pending_members = ss.pop("_strategy_pending_members", None)
if pending_members and pending_members.get("key") == strategy_key:
    for i, pokemon_id in enumerate(pending_members.get("ids") or []):
        ss[f"strategy_member_{strategy_key}_{i}"] = int(pokemon_id)
if ss.pop("_strategy_clear_members", None) == strategy_key:
    for i in range(5):
        ss.pop(f"strategy_member_{strategy_key}_{i}", None)
member_ids = [int(x) for x in member_ids if int(x) in owned_map][:5]
while len(member_ids) < 5:
    member_ids.append(0)

member_options = [0] + list(owned_map)
cols = st.columns(5)
new_member_ids: list[int] = []
for i, col in enumerate(cols):
    current_id = member_ids[i]
    picked = col.selectbox(
        f"{i + 1}枠目",
        member_options,
        index=member_options.index(current_id) if current_id in member_options else 0,
        format_func=lambda pid: "（空き）" if pid == 0 else _member_label(owned_map[pid]),
        key=f"strategy_member_{strategy_key}_{i}",
    )
    if picked:
        new_member_ids.append(int(picked))
        p = owned_map[int(picked)]
        img = pokemon_image_url(p["species_name"])
        if img:
            col.image(img, width=80)
ss["strategy_member_ids"] = new_member_ids

if len(set(new_member_ids)) != len(new_member_ids):
    st.error("同じ個体が複数枠に入っています。")
valid_team = len(new_member_ids) == 5 and len(set(new_member_ids)) == 5
members = [owned_map[mid] for mid in new_member_ids if mid in owned_map]

starting_inventory: dict[str, float] = {}
with st.expander("今週の持越し食材（標準評価は在庫ゼロ）"):
    inv_cols = st.columns(min(4, max(1, len(requirements))))
    defaults = week_defaults.get("starting_inventory", {})
    for i, name in enumerate(requirements):
        value = inv_cols[i % len(inv_cols)].number_input(
            name,
            min_value=0,
            max_value=999,
            value=int(defaults.get(name, 0)),
            key=f"strategy_inv_{strategy_key}_{name}",
        )
        if value:
            starting_inventory[name] = float(value)

note = st.text_input(
    "メモ",
    value=ss.get("strategy_note", ""),
    key=f"strategy_note_{strategy_key}",
)
save_col, active_col = st.columns(2)
if save_col.button(
    "💾 定番プランを保存",
    type="primary",
    use_container_width=True,
    disabled=not valid_team,
):
    plan_id = db.upsert_strategy_plan(
        {
            "name": f"{field_name}｜{RECIPE_CATEGORY_LABELS[category]}",
            "field_name": field_name,
            "recipe_category": category,
            "main_recipe": picked_recipe,
            "candidate_recipes": [picked_recipe],
            "member_ids": new_member_ids,
            "note": note,
            "random_field_berries": [],
            "role_targets": {},
            "event_bonuses": [],
            "policy_tags": [],
        }
    )
    ss["_strategy_loaded_key"] = None
    st.success(f"定番プランを保存しました（id={plan_id}）")
    st.rerun()

if active_col.button(
    "📌 今週のプランに設定",
    use_container_width=True,
    disabled=not plan and not valid_team,
):
    if not plan:
        plan_id = db.upsert_strategy_plan(
            {
                "name": f"{field_name}｜{RECIPE_CATEGORY_LABELS[category]}",
                "field_name": field_name,
                "recipe_category": category,
                "main_recipe": picked_recipe,
                "candidate_recipes": [picked_recipe],
                "member_ids": new_member_ids,
                "note": note,
                "random_field_berries": [],
                "role_targets": {},
                "event_bonuses": [],
                "policy_tags": [],
            }
        )
    else:
        plan_id = int(plan["id"])
    db.set_setting(
        ACTIVE_WEEK_KEY,
        {
            "plan_id": plan_id,
            "event_bonuses": sorted(event_set),
            "random_berries": random_berries,
            "starting_inventory": starting_inventory,
        },
    )
    st.success("今週のプランに設定しました")
    st.rerun()


# ── 分析・育成・捕獲 ────────────────────────────────────────────────────
if valid_team:
    zero_sim = simulate_plan(
        members,
        recipe,
        fav_berries=fav_berries,
        ctx=ctx,
        event_set=event_set,
    )
    carry_sim = simulate_plan(
        members,
        recipe,
        fav_berries=fav_berries,
        ctx=ctx,
        event_set=event_set,
        starting_inventory=starting_inventory,
    )
    overview_tab, hand_tab, analysis_tab, growth_tab = st.tabs(
        ["📋 今週の見通し", "🧩 手札・役割", "🔬 詳細分析", "🌱 育成・捕獲"]
    )
    with overview_tab:
        _sim_metrics(carry_sim)
        if starting_inventory:
            st.caption(
                f"持越し効果：安定度 {carry_sim.stability-zero_sim.stability:+.0%}｜"
                f"週 {carry_sim.weekly_energy-zero_sim.weekly_energy:+,.0f} en"
            )
        if carry_sim.bottlenecks:
            st.warning("律速食材：" + " / ".join(carry_sim.bottlenecks))
        if carry_sim.conditional_pot_meals:
            st.info(
                f"鍋拡張が必要な料理：{carry_sim.conditional_pot_meals}食｜"
                f"鍋スキル {carry_sim.pot_activation_per_day:.2f}回/日"
            )

    with hand_tab:
        st.caption(
            "固定5体で足りるもの、ボックスにはいるが未編成のもの、未所持の穴を分けて表示します。"
        )
        box_roles = _cached_skill_roles(owned)
        member_id_set = set(new_member_ids)
        recipe_total = sum(requirements.values())
        role_rows = []
        for coverage in box_roles:
            team_providers = [
                provider
                for provider in coverage.providers
                if int(provider.pokemon_id) in member_id_set
            ]
            if team_providers:
                status = "✓ 編成内"
            elif coverage.providers:
                status = "△ 手札あり"
            else:
                status = "× 未所持"

            if coverage.key == "pot_up" and recipe_total > ctx.pot_capacity:
                priority = "必須"
            elif coverage.key == "recovery_all":
                priority = "推奨"
            elif coverage.key in {"dish_chance", "food_get", "help_support"}:
                priority = "補助"
            else:
                priority = "任意"

            role_rows.append(
                {
                    "役割": coverage.label,
                    "今回": priority,
                    "充足": status,
                    "固定5体": " / ".join(p.label for p in team_providers) or "—",
                    "所持": len(coverage.providers),
                }
            )

        st.markdown("##### 固定5体の役割充足")
        st.dataframe(
            pd.DataFrame(role_rows),
            hide_index=True,
            use_container_width=True,
            column_config={
                "所持": st.column_config.NumberColumn("所持", format="%d体"),
            },
        )
        st.caption(
            "スキル役割は、所持個体が最終進化した時のメインスキルで判定しています。"
            "「手札あり」は交代候補がボックス内にいる状態です。"
        )

        with st.expander("スキル役割ごとの上位手札を見る"):
            for coverage in box_roles:
                st.markdown(f"**{coverage.label}**")
                if not coverage.providers:
                    st.caption("担当できる所持個体はいません。")
                    continue
                for provider in coverage.top:
                    pokemon = owned_map.get(int(provider.pokemon_id))
                    pokemon_popover_row(
                        pokemon,
                        label=provider.label,
                        img_species=provider.species_name,
                        caption=(
                            f"最終進化 {provider.final_species}｜"
                            f"スキル軸 {provider.skill_axis:.0f}｜"
                            f"想定MSLv{provider.main_skill_level}"
                        ),
                        badges_text=(
                            "編成中"
                            if int(provider.pokemon_id) in member_id_set
                            else None
                        ),
                    )

        ingredient_index = _cached_ingredient_index(owned)
        st.markdown("##### 主料理の必要食材")
        ingredient_rows = []
        for name, required in requirements.items():
            daily_need = required * 3
            team_daily = carry_sim.ingredient_supply.get(name, 0.0)
            providers = ingredient_index.get(name, [])
            active = [p for p in providers if p.per_day_now > 0]
            future = [p for p in providers if p.per_day_now <= 0]
            if team_daily >= daily_need:
                status = "✓ 3食分"
            elif team_daily > 0:
                status = "△ 不足"
            else:
                status = "× 担当なし"
            ingredient_rows.append(
                {
                    "食材": name,
                    "充足": status,
                    "固定5体/日": round(team_daily, 1),
                    "3食必要/日": daily_need,
                    "即戦力": len(active),
                    "将来候補": len(future),
                    "所持上位": " / ".join(
                        f"{p.label} {p.per_day_now:.1f}" for p in active[:2]
                    )
                    or "—",
                }
            )
        st.dataframe(
            pd.DataFrame(ingredient_rows),
            hide_index=True,
            use_container_width=True,
            column_config={
                "即戦力": st.column_config.NumberColumn("即戦力", format="%d体"),
                "将来候補": st.column_config.NumberColumn("将来候補", format="%d体"),
            },
        )
        st.caption(
            "固定5体の供給は、げんきオール・おてつだいボーナス・イベント補正込み。"
            "即戦力は現在の食材構成とLvで供給できる所持個体です。"
        )

        with st.expander("全食材の所持状況を見る"):
            all_food_rows = []
            uncovered = []
            for name, providers in ingredient_index.items():
                active = [p for p in providers if p.per_day_now > 0]
                if not active:
                    uncovered.append(name)
                all_food_rows.append(
                    {
                        "食材": name,
                        "現在担当": len(active),
                        "将来候補": len(providers) - len(active),
                        "上位担当": " / ".join(
                            f"{p.label} {p.per_day_now:.1f}/日" for p in active[:2]
                        )
                        or "—",
                    }
                )
            st.dataframe(
                pd.DataFrame(all_food_rows),
                hide_index=True,
                use_container_width=True,
                column_config={
                    "現在担当": st.column_config.NumberColumn(
                        "現在担当", format="%d体"
                    ),
                    "将来候補": st.column_config.NumberColumn(
                        "将来候補", format="%d体"
                    ),
                },
            )
            if uncovered:
                st.warning("現在担当がいない食材：" + " / ".join(uncovered))

            versatile = versatile_mains(ingredient_index)
            if versatile:
                st.markdown("###### 複数食材を任せられる主力")
                for main in versatile[:8]:
                    pokemon = owned_map.get(int(main.pokemon_id))
                    pokemon_popover_row(
                        pokemon,
                        label=main.label,
                        img_species=main.species_name,
                        caption=" / ".join(
                            f"{name} {daily:.1f}/日" for name, daily in main.duties
                        ),
                        badges_text=f"{len(main.duties)}食材",
                    )

    with analysis_tab:
        breakdown = pd.DataFrame(
            [
                {"内訳": "主料理", "週期待エナジー": carry_sim.dish_energy},
                {"内訳": "きのみ", "週期待エナジー": carry_sim.berry_energy},
                {"内訳": "直接スキル", "週期待エナジー": carry_sim.skill_energy},
            ]
        )
        st.dataframe(breakdown, hide_index=True, use_container_width=True)
        st.markdown("##### 食材の自給力")
        food_rows = []
        for name, required in requirements.items():
            daily = carry_sim.ingredient_supply.get(name, 0.0)
            food_rows.append(
                {
                    "食材": name,
                    "必要/食": required,
                    "供給/日": round(daily, 1),
                    "最大料理/日": round(daily / required, 2),
                }
            )
        st.dataframe(pd.DataFrame(food_rows), hide_index=True, use_container_width=True)
        future_rows = []
        for target in (30, 60):
            future = simulate_plan(
                members,
                recipe,
                fav_berries=fav_berries,
                ctx=ctx,
                event_set=event_set,
                future_level=target,
            )
            future_rows.append(
                {
                    "状態": f"全員Lv{target}以上",
                    "安定度": f"{future.stability:.0%}",
                    "料理/日": round(future.cooked_per_day, 2),
                    "週期待エナジー": round(future.weekly_energy),
                }
            )
        st.dataframe(pd.DataFrame(future_rows), hide_index=True, use_container_width=True)

    with growth_tab:
        st.markdown("##### 育成すると伸びる個体")
        growth = level_improvements(
            members, recipe, fav_berries=fav_berries, ctx=ctx
        )
        growth_rows = [
            {
                "個体": x["label"],
                "目標": f"Lv{x['target_level']}",
                "安定度改善": f"{x['stability_delta']:+.0%}",
                "週エナジー改善": f"{x['energy_delta']:+,.0f}",
            }
            for x in growth[:10]
            if x["stability_delta"] > 0 or x["energy_delta"] > 0
        ]
        if growth_rows:
            st.dataframe(pd.DataFrame(growth_rows), hide_index=True, use_container_width=True)
        else:
            st.caption("この主料理に対する明確な育成改善候補はありません。")

        st.markdown("##### 捕獲・厳選候補")
        if st.button("🎯 捕獲候補を計算", key=f"capture_{strategy_key}"):
            with st.spinner("未所持の最終進化AAA個体を各枠へ入れて比較中…"):
                ss["_capture_results"] = capture_improvements(
                    members,
                    recipe,
                    fav_berries=fav_berries,
                    ctx=ctx,
                )
        captures = ss.get("_capture_results") or []
        plan_fit_counts = {
            x["species_name"]: _plan_fit_count(x["species_name"])
            for x in captures
        }
        capture_rows = [
            {
                "候補": f"{x['species_name']} {x['composition']}",
                "交代": x["replace_label"],
                "埋まる食材": " / ".join(x["fills"]),
                "汎用性": (
                    f"⭐ {plan_fit_counts[x['species_name']]}プラン"
                    if plan_fit_counts[x["species_name"]] >= 2
                    else "—"
                ),
                "安定度改善": f"{x['stability_delta']:+.0%}",
                "週エナジー改善": f"{x['energy_delta']:+,.0f}",
            }
            for x in captures
            if x["stability_delta"] > 0 or x["energy_delta"] > 0
        ]
        if capture_rows:
            st.dataframe(pd.DataFrame(capture_rows), hide_index=True, use_container_width=True)
        elif "_capture_results" in ss:
            st.caption("現在の5体を明確に改善する未所持候補はありません。")
else:
    st.info("固定メンバーを5体選ぶと、今週の見通しと育成・捕獲候補を表示します。")
