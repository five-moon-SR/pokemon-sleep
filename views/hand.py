"""編成や料理を決める前に、所持全体の役割充足を眺める手札ボード。"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import db
from ui import components as c
from ui.widgets import pokemon_popover_row
from utils.ingredient_coverage import build_ingredient_index, versatile_mains
from utils.skill_role_coverage import TOP_N, skill_role_audit


@st.cache_data(show_spinner=False, ttl=300)
def _ingredient_index(owned_rows: list[dict]) -> dict:
    return build_ingredient_index(owned_rows)


@st.cache_data(show_spinner=False, ttl=300)
def _skill_roles(owned_rows: list[dict], main_skill_max: bool) -> list:
    return skill_role_audit(owned_rows, main_skill_max=main_skill_max)


st.html(c.page_banner("手札ボード", "bag", icon="🧩"))
st.caption("フィールド・料理・固定5体を決めずに、ボックス全体の食材とスキル役割を棚卸しする。")

db.init_db()
owned = [dict(row) for row in db.list_pokemon()]
owned_by_id = {int(p["id"]): p for p in owned}
if not owned:
    st.html(c.empty_state("所持ポケモンがいません。先に「個体登録」から追加してください。"))
    st.stop()

index = _ingredient_index(owned)
active_food_count = sum(
    any(provider.per_day_now > 0 for provider in providers)
    for providers in index.values()
)
food_holes = [
    name
    for name, providers in index.items()
    if not any(provider.per_day_now > 0 for provider in providers)
]

st.html(
    c.stat_tiles(
        [
            c.stat_tile("所持個体", f"{len(owned)}", sub="体"),
            c.stat_tile(
                "食材カバー",
                f"{active_food_count}/{len(index)}",
                sub="現在供給あり",
            ),
            c.stat_tile("食材の穴", f"{len(food_holes)}", sub="担当ゼロ"),
        ]
    )
)

food_tab, skill_tab = st.tabs(["🥕 食材充足", "🎯 スキル役割"])

with food_tab:
    st.caption(
        "現在のLv・食材構成で供給できる個体を担当として集計。"
        "編成に1〜2体置ける想定で、2体以上なら充足とみなします。"
    )
    food_rows = []
    for name, providers in index.items():
        active = [p for p in providers if p.per_day_now > 0]
        idle = [p for p in providers if p.per_day_now <= 0]
        if len(active) >= 2:
            status = "◎ 充足"
        elif len(active) == 1:
            status = "○ 1体"
        else:
            status = "× 担当ゼロ"
        food_rows.append(
            {
                "食材": name,
                "充足": status,
                "現在担当": len(active),
                "候補枠": len(idle),
                "主力": " / ".join(
                    f"{p.label} {p.per_day_now:.1f}/日" for p in active[:2]
                )
                or "—",
            }
        )
    st.dataframe(
        pd.DataFrame(food_rows),
        hide_index=True,
        use_container_width=True,
        column_config={
            "現在担当": st.column_config.NumberColumn("現在担当", format="%d体"),
            "候補枠": st.column_config.NumberColumn("候補枠", format="%d体"),
        },
    )
    st.caption(
        "候補枠は、その種族の食材候補にはあるものの現在供給ゼロの個体。"
        "未解放Lvや別の食材構成も含みます。"
    )
    if food_holes:
        st.warning("現在担当がいない食材：" + " / ".join(food_holes))

    detail_name = st.selectbox(
        "担当個体を見る食材",
        list(index),
        index=list(index).index(food_holes[0]) if food_holes else 0,
        key="hand_food_detail",
    )
    detail_providers = index[detail_name]
    active_detail = [p for p in detail_providers if p.per_day_now > 0]
    idle_detail = [p for p in detail_providers if p.per_day_now <= 0]
    for provider in active_detail[:5]:
        pokemon_popover_row(
            owned_by_id.get(int(provider.pokemon_id)),
            label=provider.label,
            img_species=provider.species_name,
            badges_text="現在担当",
            caption=f"{provider.per_day_now:.1f}個/日",
        )
    for provider in idle_detail[:3]:
        pokemon_popover_row(
            owned_by_id.get(int(provider.pokemon_id)),
            label=provider.label,
            img_species=provider.species_name,
            badges_text="候補枠",
            caption=(
                f"{provider.slot.upper()}枠・Lv{provider.unlock_lv}解放"
                f"{'済' if provider.unlocked else '前'}"
            ),
        )
    if not detail_providers:
        st.html(c.empty_state("この食材を候補枠に持つ所持個体はいません。"))

    versatile = versatile_mains(index)
    with st.expander(f"複数食材を任せられる主力 — {len(versatile)}体"):
        for main in versatile:
            pokemon_popover_row(
                owned_by_id.get(int(main.pokemon_id)),
                label=main.label,
                img_species=main.species_name,
                badges_text=f"{len(main.duties)}食材",
                caption=" / ".join(
                    f"{name} {daily:.1f}/日" for name, daily in main.duties
                ),
            )

with skill_tab:
    max_skill = st.toggle(
        "メインスキルLv最大の天井で見る",
        key="hand_skill_max",
        help="OFFでは進化後の想定Lv、ONでは育て切った最大Lvで比較します。",
    )
    coverages = _skill_roles(owned, max_skill)
    skill_rows = []
    for coverage in coverages:
        count = len(coverage.providers)
        if count >= TOP_N:
            status = "◎ 充足"
        elif count == 1:
            status = "○ 1体"
        else:
            status = "× 担当ゼロ"
        skill_rows.append(
            {
                "役割": coverage.label,
                "充足": status,
                "所持": count,
                "主力": " / ".join(p.label for p in coverage.top) or "—",
            }
        )
    st.dataframe(
        pd.DataFrame(skill_rows),
        hide_index=True,
        use_container_width=True,
        column_config={
            "所持": st.column_config.NumberColumn("所持", format="%d体"),
        },
    )
    st.caption(
        "最終進化後のメインスキルで判定。編成に1〜2体置ける想定で、"
        f"各役割の上位{TOP_N}体を主力として扱います。"
    )

    for coverage in coverages:
        with st.expander(
            f"{coverage.label} — "
            + (
                " / ".join(p.label for p in coverage.top)
                if coverage.top
                else "担当ゼロ"
            )
        ):
            st.caption("対象スキル：" + " / ".join(sorted(coverage.categories)))
            if not coverage.top:
                st.html(c.empty_state("この役割を担える所持個体はいません。"))
            for provider in coverage.top:
                pokemon_popover_row(
                    owned_by_id.get(int(provider.pokemon_id)),
                    label=provider.label,
                    img_species=provider.species_name,
                    badges_text=f"育成後 {provider.potential_rank}",
                    caption=(
                        f"最終進化 {provider.final_species}｜"
                        f"スキル軸 {provider.skill_axis:.0f}/100｜"
                        f"想定MSLv{provider.main_skill_level}"
                    ),
                )
