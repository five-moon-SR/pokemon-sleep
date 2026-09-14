"""ボックス全体の担当充足度（食材・きのみ・スキル）を棚卸しするページ。

チーム編成やレシピを決める前に「何が足りていないか」を見る場所。

きのみ充足度は utils/berry_coverage.py に実装があったのに、
それを出すページがナビ未登録で到達不能になっていた（この統合で削除）。
食材・スキルと同じ土俵に並べて、3軸そろえてここで見る。

用語は編成ページ（views/party.py）に合わせる:
  即戦力 = 現在のLv・構成で供給できる個体 / 将来候補 = 候補枠にはあるが供給ゼロ
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import db
from constants import format_ingredient_short
from image_utils import berry_icon_url, ingredient_icon_url, pokemon_image_url
from ui import components as c
from ui.widgets import pokemon_popover_row
from utils.berry_coverage import (
    berry_audit,
    favorite_holes,
    load_audit_field,
    load_random_favs,
    resolve_fav_berries,
    save_audit_field,
    save_random_favs,
)
from utils.berry_coverage import TOP_N as BERRY_TOP_N
from utils.ingredient_coverage import build_ingredient_index, versatile_mains
import utils.ingredient_demand as _demand

# Streamlit Cloud は既存モジュールを古いまま掴むことがある。from-import だと
# 追記したばかりの関数が無いときにページ全体が ImportError で落ちるので、
# 属性として取りに行き、無ければその機能だけ畳む。
demanding_recipes = getattr(_demand, "demanding_recipes", None)
best_supply_per_ingredient = getattr(_demand, "best_supply_per_ingredient", None)
recipe_reachability = getattr(_demand, "recipe_reachability", None)
recommend_ingredients = getattr(_demand, "recommend_ingredients", None)
REACH_THRESHOLD = getattr(_demand, "REACH_THRESHOLD", 0.85)
from utils.play_context import load_play_context
from utils.skill_role_coverage import TOP_N, role_holes, skill_role_audit

# きのみ・スキルは頭数で見る（編成に置ける枠数）。食材だけは量で見るので、
# ここには定数を置かない（基準は ingredient_coverage.demanding_recipes が出す）。


@st.cache_data(show_spinner=False, ttl=300)
def _ingredient_index(owned_rows: list[dict]) -> dict:
    return build_ingredient_index(owned_rows)


@st.cache_data(show_spinner=False, ttl=300)
def _skill_roles(owned_rows: list[dict], main_skill_max: bool) -> list:
    return skill_role_audit(owned_rows, main_skill_max=main_skill_max)


@st.cache_data(show_spinner=False, ttl=300)
def _berries(owned_rows: list[dict], fav: tuple[str, ...]) -> list:
    return berry_audit(owned_rows, set(fav))


def _fill_ratio(count: int, need: int) -> float:
    return min(1.0, count / need) if need else 0.0


def _status_label(count: int, need: int) -> str:
    """充足の言い方をページ全体でそろえる（記号だけだと意味が読めない）。"""
    if count >= need:
        return "充足"
    if count > 0:
        return f"あと{need - count}体"
    return "担当ゼロ"


def _amount_label(best_per_day: float, need_per_day: float) -> str:
    """量で見た充足の言い方。基準（強い料理×3食）は高いので、達成率で語る。"""
    if need_per_day <= 0:
        return "基準なし"
    if best_per_day >= need_per_day:
        return "足りる"
    if best_per_day <= 0:
        return "担当ゼロ"
    return f"あと{need_per_day - best_per_day:.0f}個/日"


def _coverage_table(
    rows: list[dict],
    *,
    icon_col: str,
    height: int,
) -> None:
    """充足度テーブル。列幅と高さを明示して、表の中で二重スクロールさせない。"""
    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        use_container_width=True,
        height=height,
        column_config={
            icon_col: st.column_config.ImageColumn(icon_col, width="small"),
            "充足": st.column_config.ProgressColumn(
                "充足", format="%.0f%%", min_value=0, max_value=100, width="small"
            ),
            "状態": st.column_config.TextColumn("状態", width="small"),
            "即戦力": st.column_config.NumberColumn("即戦力", format="%d体", width="small"),
            "将来候補": st.column_config.NumberColumn("将来候補", format="%d体", width="small"),
            "供給/日": st.column_config.NumberColumn("供給/日", format="%.1f", width="small"),
            "最大の1体": st.column_config.NumberColumn("最大の1体", format="%.1f個/日", width="small"),
            "Lv30での最大1体": st.column_config.NumberColumn(
                "Lv30での最大1体", format="%.1f個/日", width="small"
            ),
            "Lv60での最大1体": st.column_config.NumberColumn(
                "Lv60での最大1体", format="%.1f個/日", width="small"
            ),
            "基準/日": st.column_config.NumberColumn("基準/日", format="%.0f個/日", width="small"),
            "基準の料理": st.column_config.TextColumn("基準の料理", width="medium"),
            "エナジー/日": st.column_config.NumberColumn("エナジー/日", format="%.0f", width="small"),
        },
    )


st.html(c.page_banner("ボックス診断", "bag", icon="🧩"))
st.caption(
    "チームを決める前に、ポケモンボックス全体で食材・きのみ・スキルの担当が"
    "どこまで埋まっているかをざっくり棚卸しする。"
)

db.init_db()
ctx = load_play_context()
owned = [dict(row) for row in db.list_pokemon()]
owned_by_id = {int(p["id"]): p for p in owned}
if not owned:
    st.html(c.empty_state("所持ポケモンがいません。先に「仲間登録」から追加してください。"))
    st.stop()

index = _ingredient_index(owned)
food_active = {
    name: [p for p in providers if p.per_day_now > 0]
    for name, providers in index.items()
}
food_holes = [name for name, active in food_active.items() if not active]

audit_field = load_audit_field()
random_favs = load_random_favs()
fav_berries = resolve_fav_berries(audit_field, random_favs)
berry_covs = _berries(owned, tuple(sorted(fav_berries)))
berry_holes = favorite_holes(berry_covs)

skill_covs = _skill_roles(owned, False)
skill_holes = role_holes(skill_covs)

st.html(
    c.stat_tiles(
        [
            c.stat_tile("所持個体", f"{len(owned)}", sub="体"),
            c.stat_tile(
                "担当ゼロの食材", f"{len(food_holes)}", sub=f"/{len(index)}種"
            ),
            c.stat_tile(
                "好物きのみの穴", f"{len(berry_holes)}", sub=f"/{len(fav_berries) or '—'}種"
            ),
            c.stat_tile(
                "スキル役割の穴", f"{len(skill_holes)}", sub=f"/{len(skill_covs)}役割"
            ),
        ]
    )
)

food_tab, berry_tab, skill_tab = st.tabs(["🥕 食材", "🌳 きのみ", "🎯 スキル"])


# ── 食材 ────────────────────────────────────────────────────────────────
with food_tab:
    # 頭数で「2体そろったか」を見ても、実際に回るかは量で決まる。
    # カビゴンには1日3食作るので、基準は「その食材を必要とする料理のうち
    # 必要量トップ2の平均 × 3食」。今後どの強い料理を狙うことになっても耐えられる
    # 水準を見たいので、鍋容量では絞らない。判定は**一番多く拾える1体**で行う。
    degraded = demanding_recipes is None or best_supply_per_ingredient is None
    if degraded:
        st.warning(
            "食材の基準計算がまだ読み込めていません（再デプロイ待ち）。"
            "いまは現在の供給量だけ表示します。"
        )
    demands = demanding_recipes() if demanding_recipes else {}
    stage = st.segmented_control(
        "見る段階",
        options=["現在", "Lv30", "Lv60"],
        # 見たいのは「育て切ったときにどこが穴か」なので Lv60 を既定にする。
        default="Lv60",
        key="hand_food_stage",
        help=(
            "Lv30で食材2枠目、Lv60で3枠目が開く。指定したLvまで育てた姿"
            "（最終進化・Lvは max(現在Lv, 指定Lv)）で見る。"
        ),
    ) or "Lv60"
    stage_level = {"現在": None, "Lv30": 30, "Lv60": 60}[stage]
    best_supply = (
        best_supply_per_ingredient(owned, level=stage_level)
        if best_supply_per_ingredient
        else {n: max((p.per_day_now for p in a), default=0.0) for n, a in food_active.items()}
    )
    st.caption(
        "基準は「その食材を使う料理のうち**必要量トップ2の平均 × 1日3食**」。"
        "判定は担当の頭数ではなく、**一番多く拾える1体の供給量**です"
        + (
            "（現在のLv・構成）。" if stage_level is None
            else f"（**{stage}まで育てた姿**＝最終進化・Lvは現在値と{stage_level}の大きい方）。"
        )
        +
        "1体で埋めきれる食材はまずないので、合否ではなく**達成率の低い順**に"
        "「どこが一番遠いか」を見てください。"
    )

    food_rows = []
    for name, active in food_active.items():
        best = best_supply.get(name, 0.0)
        demand = demands.get(name)
        need = demand.per_day if demand else 0.0
        food_rows.append({
            "🥕": ingredient_icon_url(name),
            "食材": format_ingredient_short(name),
            "充足": (min(1.0, best / need) * 100) if need else 100.0,
            "状態": _amount_label(best, need),
            ("最大の1体" if stage_level is None else f"{stage}での最大1体"): best,
            "基準/日": need,
            "基準の料理": demand.label if demand else "—",
            "即戦力": len(active),
            "将来候補": len(index[name]) - len(active),
        })
    food_rows.sort(key=lambda r: (r["充足"], -r["基準/日"]))
    _coverage_table(food_rows, icon_col="🥕", height=380)

    worst = [r["食材"] for r in food_rows[:4] if r["充足"] < 100]
    if worst:
        st.caption("いま一番遠いのは： **" + "** / **".join(worst) + "**")

    # ── 料理ごとの到達度（重いので見たいときだけ計算する） ──
    st.divider()
    if recipe_reachability is not None and st.toggle(
        "料理ごとの到達度を見る",
        value=False,
        key="hand_recipe_reach",
        help=(
            "「あとこの食材さえ埋まれば、この料理に手が届く」を料理ごとに出す。"
            "Lv60エナジーが1万に満たない料理は目標にならないので除外。"
            "全レシピを走査するので、開いたときだけ計算します。"
        ),
    ):
        threshold = st.slider(
            "「足りている」とみなす達成率", min_value=0.3, max_value=1.0,
            value=float(REACH_THRESHOLD), step=0.05, key="hand_reach_threshold",
            help=(
                "不足の量は強い個体を1体引けば一気に消えるし、あと数個ならサブスキルや"
                "おてつだいボーナスで吸収できる。ここを超えた食材は『足りている』として"
                "扱い、本当に遠い相方だけが残るようにする。"
            ),
        )
        reaches = recipe_reachability(best_supply, threshold=float(threshold))
        only_one = st.toggle(
            "あと1つで届くものだけ", value=True, key="hand_reach_only_one"
        )
        shown = [r for r in reaches if r.missing_count == 1] if only_one else reaches

        reach_rows = [
            {
                "料理": r.recipe_name,
                "Lv60エナジー": r.energy_lv60,
                "到達度": r.reach * 100,
                "足りない食材": "、".join(
                    f"{format_ingredient_short(n)}({ratio:.0%})" for n, ratio in r.missing[:3]
                ) or "—",
                "不足数": r.missing_count,
            }
            for r in shown
        ]
        if reach_rows:
            st.dataframe(
                pd.DataFrame(reach_rows),
                hide_index=True,
                use_container_width=True,
                height=360,
                column_config={
                    "Lv60エナジー": st.column_config.NumberColumn(
                        "Lv60エナジー", format="%d en", width="small"
                    ),
                    "到達度": st.column_config.ProgressColumn(
                        "到達度", format="%.0f%%", min_value=0, max_value=100, width="small"
                    ),
                    "不足数": st.column_config.NumberColumn("不足数", format="%d", width="small"),
                },
            )
            done = sum(1 for r in reaches if r.missing_count == 0)
            st.caption(
                f"いまの段階（{stage}）で既に必要量を満たす料理は **{done}品**。"
                "残りは表の「足りない食材」を埋めれば届きます。"
            )
        else:
            st.html(c.empty_state("条件に合う料理がありません。"))

        # ── 食材ごとのおすすめ度 ──
        ranked, baselines = (
            recommend_ingredients(best_supply, threshold=float(threshold))
            if recommend_ingredients else ([], [])
        )
        st.markdown("**次に埋めるべき食材**")
        st.caption(
            "料理のエナジーは直線では見ず E^1.5 で効かせ、価値は"
            "**そのカテゴリの現最高をどれだけ更新するか**で測ります。"
            "カレーが既に安定していれば他のカレー用食材は自然に下がり、"
            "安定の無いカテゴリを埋める食材が上がります。"
        )
        cat_labels = {"curry_stew": "カレー・シチュー", "salad": "サラダ", "drink_dessert": "デザート・ドリンク"}
        st.caption(
            "　／　".join(
                f"**{cat_labels.get(b.category, b.category)}**: 作れる{b.cookable}品"
                + (f"・最高 {b.best_energy:,}en（{b.best_recipe}）" if b.best_energy else "・まだ無し")
                for b in baselines
            )
        )
        if ranked:
            st.dataframe(
                pd.DataFrame([
                    {"🥕": ingredient_icon_url(r.ingredient),
                     "食材": format_ingredient_short(r.ingredient),
                     "おすすめ度": r.score}
                    for r in ranked[:12]
                ]),
                hide_index=True,
                use_container_width=True,
                height=260,
                column_config={
                    "🥕": st.column_config.ImageColumn("🥕", width="small"),
                    "おすすめ度": st.column_config.ProgressColumn(
                        "おすすめ度", format="%.0f", min_value=0, max_value=100
                    ),
                },
            )
        else:
            st.caption("埋めるべき食材が見つかりません（すべて基準を満たしています）。")

    detail_name = st.selectbox(
        "担当個体を見る食材",
        list(index),
        index=list(index).index(food_holes[0]) if food_holes else 0,
        key="hand_food_detail",
        format_func=format_ingredient_short,
        filter_mode=None,  # スマホでキーボードを出さない（食材19件なので検索不要）
        help="穴がある場合は、その先頭を最初に選んでいます。",
    )
    detail_providers = index[detail_name]
    for provider in [p for p in detail_providers if p.per_day_now > 0][:5]:
        pokemon_popover_row(
            owned_by_id.get(int(provider.pokemon_id)),
            label=provider.label,
            img_species=provider.species_name,
            badges_text="即戦力",
            caption=f"{provider.per_day_now:.1f}個/日",
        )
    for provider in [p for p in detail_providers if p.per_day_now <= 0][:3]:
        pokemon_popover_row(
            owned_by_id.get(int(provider.pokemon_id)),
            label=provider.label,
            img_species=provider.species_name,
            badges_text="将来候補",
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
                    f"{format_ingredient_short(name)} {daily:.1f}/日"
                    for name, daily in main.duties
                ),
            )


# ── きのみ ──────────────────────────────────────────────────────────────
with berry_tab:
    fields = db.list_all_field_records()
    field_names = [f["name"] for f in fields]
    pick_cols = st.columns([2, 3])
    with pick_cols[0]:
        picked_field = st.selectbox(
            "監査フィールド",
            ["（好物なし）"] + field_names,
            index=(field_names.index(audit_field) + 1) if audit_field in field_names else 0,
            key="hand_berry_field",
            filter_mode=None,  # スマホでキーボードを出さない（8件なので検索不要）
            help="好物きのみは獲得エナジーが2倍になるので、どのフィールドで見るかで穴が変わります。",
        )
    chosen_field = None if picked_field == "（好物なし）" else picked_field
    field_rec = next((f for f in fields if f["name"] == chosen_field), None)
    with pick_cols[1]:
        if field_rec and field_rec.get("favorite_berries_random"):
            picked_random = st.multiselect(
                "今週の好みきのみ（最大3種）",
                [b["name"] for b in db.list_all_berry_records()],
                default=random_favs,
                max_selections=3,
                key="hand_berry_random",
            )
        else:
            picked_random = random_favs
    if chosen_field != audit_field or list(picked_random) != list(random_favs):
        save_audit_field(chosen_field)
        save_random_favs(list(picked_random))
        st.cache_data.clear()
        st.rerun()

    st.caption(
        f"好物きのみ（×2）を優先して並べています。編成枠の都合で"
        f"**{BERRY_TOP_N}体そろえば充足**とみなします。"
    )
    berry_rows = [
        {
            "🌳": berry_icon_url(cov.berry["name"]),
            "きのみ": cov.berry["name"] + ("　★好物" if cov.is_favorite else ""),
            "充足": _fill_ratio(len(cov.providers), BERRY_TOP_N) * 100,
            "状態": _status_label(len(cov.providers), BERRY_TOP_N),
            "エナジー/日": cov.top_energy,
            "即戦力": len(cov.providers),
        }
        for cov in berry_covs
    ]
    _coverage_table(berry_rows, icon_col="🌳", height=380)

    if berry_holes:
        st.html(
            '<div style="display:flex;flex-wrap:wrap;gap:4px;margin:6px 0">'
            + "".join(c.berry_chip(n) for n in berry_holes)
            + "</div>"
        )
        st.caption("↑ 好物（×2）なのに担当がゼロのきのみ。ここが一番もったいない。")
    elif fav_berries:
        st.success("好物きのみはすべて担当がいます。")

    berry_names = [cov.berry["name"] for cov in berry_covs]
    berry_detail = st.selectbox(
        "担当個体を見るきのみ",
        berry_names,
        index=berry_names.index(berry_holes[0]) if berry_holes else 0,
        key="hand_berry_detail",
        filter_mode=None,  # スマホでキーボードを出さない（18件なので検索不要）
    )
    cov = next(x for x in berry_covs if x.berry["name"] == berry_detail)
    for provider in cov.providers[:5]:
        pokemon_popover_row(
            owned_by_id.get(int(provider.pokemon_id)),
            label=provider.label,
            img_species=provider.species_name,
            badges_text=f"{provider.energy_per_day:,.0f} en/日",
            caption=f"Lv{provider.level}｜{provider.count_per_day:.1f}個/日",
        )
    if not cov.providers:
        st.html(c.empty_state("このきのみを持つ所持個体はいません。"))


# ── スキル ──────────────────────────────────────────────────────────────
with skill_tab:
    max_skill = st.toggle(
        "メインスキルLv最大の天井で見る",
        key="hand_skill_max",
        help="OFFでは進化後の想定Lv、ONでは育て切った最大Lvで比較します。",
    )
    coverages = _skill_roles(owned, max_skill)
    st.caption(
        f"最終進化後のメインスキルで判定。編成枠の都合で**{TOP_N}体そろえば充足**とみなします。"
    )
    skill_rows = [
        {
            # 担当ゼロだと None がそのまま "None" と描画されるので空文字にする
            "🎯": (pokemon_image_url(cov.top[0].species_name) or "") if cov.top else "",
            "役割": cov.label,
            "充足": _fill_ratio(len(cov.providers), TOP_N) * 100,
            "状態": _status_label(len(cov.providers), TOP_N),
            "即戦力": len(cov.providers),
            "主力": " / ".join(p.label for p in cov.top) or "—",
        }
        for cov in coverages
    ]
    _coverage_table(skill_rows, icon_col="🎯", height=360)

    if skill_holes:
        st.warning("担当がいない役割：" + " / ".join(skill_holes))

    # 以前は役割9件ぶんの expander を全部畳んで縦に積んでいた。
    # 均質なカードの等間隔積みは読みにくいので、1つ選んで中身を出す形にする。
    labels = [cov.label for cov in coverages]
    picked_role = st.selectbox(
        "担当個体を見る役割",
        labels,
        index=labels.index(skill_holes[0]) if skill_holes else 0,
        key="hand_skill_detail",
        filter_mode=None,  # スマホでキーボードを出さない（9件なので検索不要）
    )
    role = next(x for x in coverages if x.label == picked_role)
    st.caption("対象スキル：" + " / ".join(sorted(role.categories)))
    if not role.top:
        st.html(c.empty_state("この役割を担える所持個体はいません。"))
    for provider in role.top:
        pokemon_popover_row(
            owned_by_id.get(int(provider.pokemon_id)),
            label=provider.label,
            img_species=provider.species_name,
            badges_text=f"育成後 {provider.potential_rank}",
            caption=(
                f"{provider.final_species}｜スキル軸 {provider.skill_axis:.0f}"
                f"｜MSLv{provider.main_skill_level}"
            ),
        )
