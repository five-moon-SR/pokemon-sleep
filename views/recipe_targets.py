"""料理ページ。

週の料理カテゴリごとに「伸ばす料理を1つ決める」ターゲット相談と、
作り込んだ料理レベルの軽量編集をまとめて扱う。
"""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st

import db
from constants import format_ingredient_short
from image_utils import ingredient_icon_url, pokemon_image_url, recipe_icon_url
from ui import components as c
from utils.evaluator import final_evolution_of
from utils.field_encounters import recommend_fields, species_fields
from utils.food_expectation import composition_string, expected_ingredients_per_day, qty_at_slot
from utils.ingredient_coverage import INGREDIENT_RECOMMENDATIONS
from utils.play_context import load_play_context
from utils.party_logic import RECIPE_CATEGORY_LABELS
from utils.plan_simulation import _skill_effect
from utils import recipe_level

CATEGORY_ORDER = ("curry_stew", "salad", "drink_dessert")
MEALS_PER_DAY = 3
DEFAULT_POT_BONUS = 27
INGREDIENT_SLOT_LABELS = ("Lv1", "Lv30", "Lv60")
SUPPLY_MODE_CURRENT = "現状"
SUPPLY_MODE_LV60 = "Lv60育成後"


@st.cache_data(show_spinner=False, ttl=300)
def _owned_rows() -> list[dict]:
    return [dict(row) for row in db.list_pokemon()]


@st.cache_data(show_spinner=False, ttl=300)
def _recipes_by_category() -> dict[str, list[dict]]:
    out = {key: [] for key in CATEGORY_ORDER}
    for rec in db.list_all_recipe_records():
        if not rec.get("ingredients"):
            continue
        cat = rec.get("category")
        if cat in out:
            out[cat].append(rec)
    for rows in out.values():
        rows.sort(key=lambda r: recipe_level.recipe_energy(r, 60), reverse=True)
    return out


def _pot_skill_label(owned: list[dict]) -> tuple[str, int]:
    best: tuple[str, int] | None = None
    for p in owned:
        species = db.get_species_data(p.get("species_name") or "") or {}
        category, effect = _skill_effect(p, species)
        if category != "料理パワーアップS" or effect <= 0:
            continue
        label = p.get("nickname") or p.get("species_name") or "鍋役"
        value = int(effect)
        if best is None or value > best[1]:
            best = (label, value)
    return best or ("書帳", DEFAULT_POT_BONUS)


def _pot_status(total: int | None, base_capacity: int, pot_bonus: int) -> tuple[str, str, int]:
    if not total:
        return ("対象外", "ごちゃまぜ", 0)
    if total <= base_capacity:
        return ("通常OK", "鍋スキル不要", 0)
    if total <= base_capacity + pot_bonus:
        return ("+1回", f"+{pot_bonus}で届く", 1)
    if total <= base_capacity + pot_bonus * 2:
        return ("+2回", f"+{pot_bonus * 2}で届く", 2)
    over = total - (base_capacity + pot_bonus * 2)
    return ("まだ無理", f"+2回でも{over}超過", 3)


def _recipe_option_label(name: str, recipe_map: dict[str, dict], base_capacity: int, pot_bonus: int) -> str:
    rec = recipe_map[name]
    total = rec.get("total_ingredients")
    status, detail, _ = _pot_status(total, base_capacity, pot_bonus)
    return f"{name}｜食材{total}｜{status}（{detail}）"


def _render_pot_overview(recipes: list[dict], base_capacity: int, pot_label: str, pot_bonus: int) -> None:
    buckets = [
        ("通常OK", "鍋スキルなし", 0),
        ("+1回", f"{pot_label} 1回", 1),
        ("+2回", f"{pot_label} 2回", 2),
        ("未到達", "鍋拡張待ち", 3),
    ]
    panels = []
    for title, subtitle, bucket in buckets:
        rows = [
            r for r in recipes
            if _pot_status(r.get("total_ingredients"), base_capacity, pot_bonus)[2] == bucket
        ]
        rows.sort(key=lambda r: int(r.get("total_ingredients") or 0), reverse=True)
        cards = []
        for rec in rows[:5]:
            name = rec.get("name") or "—"
            icon = recipe_icon_url(name)
            img = f'<img src="{icon}" loading="lazy">' if icon else ""
            cards.append(
                '<div class="rt-pot-card">'
                f'<div class="rt-pot-img">{img}</div>'
                '<div class="rt-pot-main">'
                f'<div class="rt-pot-name" title="{html.escape(name)}">{html.escape(name)}</div>'
                f'<div class="rt-pot-meta">食材{int(rec.get("total_ingredients") or 0)}'
                f' / Lv60 {recipe_level.recipe_energy(rec, 60):,.0f}en</div>'
                '</div></div>'
            )
        if not cards:
            cards.append('<div class="rt-pot-empty">該当なし</div>')
        panels.append(
            '<section class="rt-pot-panel">'
            '<div class="rt-pot-panel-head">'
            f'<strong>{html.escape(title)}</strong>'
            f'<span>{html.escape(subtitle)}</span>'
            '</div>'
            '<div class="rt-pot-strip">'
            + "".join(cards)
            + '</div></section>'
        )
    st.html('<div class="rt-pot-board">' + "".join(panels) + '</div>')


@st.cache_data(show_spinner=False, ttl=300)
def _family_names(recommended_species: tuple[str, ...]) -> set[str]:
    finals = {
        final_evolution_of(name)
        for name in recommended_species
        if db.get_species_data(name)
    }
    return {
        sp["species_name"]
        for sp in db.list_all_master_records()
        if final_evolution_of(sp.get("species_name") or "") in finals
    }


def _lv60_target_supply(p: dict, target_name: str) -> float:
    final_name = final_evolution_of(p.get("species_name") or "")
    species = (
        db.get_species_data(final_name)
        or db.get_species_data(p.get("species_name") or "")
        or {}
    )
    boosted = dict(p)
    boosted["species_name"] = final_name
    boosted["current_level"] = 60
    return expected_ingredients_per_day(boosted, species).get(target_name, 0.0)


def _current_target_supply(p: dict, target_name: str) -> float:
    species = db.get_species_data(p.get("species_name") or "") or {}
    return expected_ingredients_per_day(p, species).get(target_name, 0.0)


def _target_supply(p: dict, target_name: str, supply_mode: str) -> float:
    if supply_mode == SUPPLY_MODE_CURRENT:
        return _current_target_supply(p, target_name)
    return _lv60_target_supply(p, target_name)


def _food_slot_chips(p: dict, species: dict, target_name: str) -> list[str]:
    ings = species.get("ingredients") or {}
    defaults = (
        (ings.get("a") or {}).get("name"),
        (ings.get("b") or {}).get("name"),
        (ings.get("c") or {}).get("name"),
    )
    chosen = (
        p.get("ingredient_1") or defaults[0],
        p.get("ingredient_2") or defaults[1],
        p.get("ingredient_3") or defaults[2],
    )
    chips = []
    for idx, name in enumerate(chosen):
        if not name:
            continue
        qty = qty_at_slot(species, name, idx)
        qty_label = f"×{qty}" if qty > 0 else "?"
        active = name == target_name
        cls = "rt-slot-chip rt-slot-chip-active" if active else "rt-slot-chip"
        icon = ingredient_icon_url(name)
        img = f'<img src="{icon}" width="18" loading="lazy">' if icon else ""
        label = f"{INGREDIENT_SLOT_LABELS[idx]} {format_ingredient_short(name)}{qty_label}"
        chips.append(
            f'<span class="{cls}" title="{html.escape(name)}">'
            f'{img}{html.escape(label)}</span>'
        )
    return chips


def _candidate_rows(owned: list[dict], ingredient_name: str, supply_mode: str) -> list[dict]:
    rec_species = tuple(INGREDIENT_RECOMMENDATIONS.get(ingredient_name, []))
    families = _family_names(rec_species)
    rows = []
    for p in owned:
        if (p.get("species_name") or "") not in families:
            continue
        current_species = db.get_species_data(p.get("species_name") or "") or {}
        final_name = final_evolution_of(p.get("species_name") or "")
        final_species = db.get_species_data(final_name) or current_species
        species = final_species if supply_mode == SUPPLY_MODE_LV60 else current_species
        comp = composition_string(p, species)
        daily = _target_supply(p, ingredient_name, supply_mode)
        subs = [
            p.get(f"subskill_lv{lv}")
            for lv in (10, 25, 50, 75, 100)
            if p.get(f"subskill_lv{lv}")
        ]
        rows.append(
            {
                "id": int(p["id"]),
                "label": p.get("nickname") or p.get("species_name") or "—",
                "species_name": p.get("species_name") or "—",
                "level": int(p.get("current_level") or p.get("caught_level") or p.get("level") or 1),
                "composition": comp,
                "daily": daily,
                "food_slots": _food_slot_chips(p, species, ingredient_name),
                "subs": subs,
            }
        )
    rows.sort(key=lambda r: (-r["daily"], r["species_name"], r["label"]))
    return rows


def _wanted_family_species(ingredient_names: list[str]) -> set[str]:
    wanted: set[str] = set()
    for ing in ingredient_names:
        for name in INGREDIENT_RECOMMENDATIONS.get(ing, []):
            family = _family_names((name,))
            wanted.update(family or {name})
    return wanted


def _ingredient_header(name: str, count: int, best_daily: float) -> str:
    need = count * MEALS_PER_DAY
    state = "足りる" if best_daily >= need else f"不足 {need - best_daily:.1f}/日"
    state_color = "--ps-sp-food" if best_daily >= need else "--ps-rank-ss"
    icon = ingredient_icon_url(name)
    img = f'<img src="{icon}" width="30" loading="lazy">' if icon else ""
    return (
        '<div class="rt-ing-head">'
        f'<div class="rt-ing-name">{img}<strong title="{html.escape(name)}">'
        f'{html.escape(format_ingredient_short(name))}</strong>'
        f'<span>1食 {count}個 / 3食 {need}個</span></div>'
        f'<div class="rt-ing-state" style="color:var({state_color})">{html.escape(state)}</div>'
        '</div>'
    )


def _candidate_card(row: dict, need_per_day: float, supply_mode: str) -> str:
    img_url = pokemon_image_url(row["species_name"])
    img = (
        f'<img src="{img_url}" loading="lazy" style="width:48px;height:48px;object-fit:contain">'
        if img_url
        else ""
    )
    cover = row["daily"] / need_per_day if need_per_day else 0.0
    sub_html = "".join(c.subskill_chip(s) for s in row["subs"][:5]) or '<span class="rt-muted">サブ未入力</span>'
    slot_html = "".join(row.get("food_slots") or []) or '<span class="rt-muted">食材枠未入力</span>'
    return (
        '<article class="rt-cand-card">'
        '<div class="rt-cand-top">'
        f'<div class="rt-cand-img">{img}</div>'
        '<div class="rt-cand-main">'
        f'<div class="rt-cand-name">{html.escape(row["label"])}</div>'
        f'<div class="rt-muted">{html.escape(row["species_name"])} / Lv{row["level"]} / {html.escape(row["composition"])}</div>'
        '</div>'
        '<div class="rt-daily">'
        f'<span>{html.escape(supply_mode)}期待</span>'
        f'<strong>{row["daily"]:.1f}</strong>'
        '<small>個/日</small>'
        '</div>'
        '</div>'
        f'<div class="rt-progress"><div style="width:{min(100, cover * 100):.0f}%"></div></div>'
        f'<div class="rt-muted">3食必要量に対して {cover:.0%}</div>'
        f'<div class="rt-slotrow">{slot_html}</div>'
        f'<div class="rt-subrow">{sub_html}</div>'
        '</article>'
    )


def _render_recipe(
    category: str,
    recipes: list[dict],
    owned: list[dict],
    *,
    base_capacity: int,
    pot_label: str,
    pot_bonus: int,
    supply_mode: str,
) -> None:
    if not recipes:
        st.html(c.empty_state("このカテゴリに対象料理がありません。"))
        return

    recipe_map = {r["name"]: r for r in recipes}
    st.caption(
        f"現在の鍋容量は **{base_capacity}**。"
        f"鍋役は **{pot_label}** 想定で、1回発動 +{pot_bonus} / 2回発動 +{pot_bonus * 2} として見ます。"
    )
    _render_pot_overview(recipes, base_capacity, pot_label, pot_bonus)

    recipe_name = st.selectbox(
        "伸ばす料理",
        [r["name"] for r in recipes],
        format_func=lambda n: _recipe_option_label(n, recipe_map, base_capacity, pot_bonus),
        key=f"recipe_target_{category}",
        filter_mode=None,
    )
    recipe = next(r for r in recipes if r["name"] == recipe_name)
    level = recipe_level.get_recipe_level(recipe_name)
    energy_now = recipe_level.recipe_energy(recipe)
    energy_60 = recipe_level.recipe_energy(recipe, 60)
    total = recipe.get("total_ingredients")
    pot_status, pot_detail, pot_bucket = _pot_status(total, base_capacity, pot_bonus)
    icon = recipe_icon_url(recipe_name)

    st.html(
        '<div class="rt-recipe-head">'
        + (f'<img src="{icon}" loading="lazy">' if icon else "")
        + '<div>'
        + f'<h3>{html.escape(recipe_name)}</h3>'
        + f'<p>現在 Lv{level}: {energy_now:,.0f} en/回　/　Lv60: {energy_60:,.0f} en/回</p>'
        + f'<p>食材{total} / 鍋{base_capacity} / {html.escape(pot_status)}（{html.escape(pot_detail)}）</p>'
        + '</div></div>'
    )
    if pot_bucket == 1:
        st.info(f"{pot_label} の料理パワーアップSが1回発動すれば作れる料理です。")
    elif pot_bucket == 2:
        st.warning(f"{pot_label} の料理パワーアップSが2回重複すれば作れる、今後期待のデカ料理です。")
    elif pot_bucket >= 3:
        st.error("現在の鍋容量と鍋スキル2回分ではまだ届きません。鍋拡張かさらに発動数が必要です。")
    else:
        st.success("鍋スキルに頼らず、今の鍋容量だけで作れます。")
    st.html(
        '<div class="rt-req-row">'
        + "".join(c.ingredient_chip(i["name"], i["count"]) for i in recipe.get("ingredients") or [])
        + "</div>"
    )

    lacking: list[str] = []
    st.markdown("**食材担当候補**")
    for item in recipe.get("ingredients") or []:
        ing = item["name"]
        need = float(item["count"]) * MEALS_PER_DAY
        candidates = _candidate_rows(owned, ing, supply_mode)
        best_daily = candidates[0]["daily"] if candidates else 0.0
        if best_daily < need:
            lacking.append(ing)
        with st.container(border=True):
            st.html(_ingredient_header(ing, int(item["count"]), best_daily))
            if candidates:
                st.html(
                    '<div class="rt-cand-grid">'
                    + "".join(_candidate_card(row, need, supply_mode) for row in candidates[:6])
                    + "</div>"
                )
            else:
                st.html(c.empty_state("おすすめ進化系統の手持ち候補はまだいません。"))

    st.markdown("**不足時の捕獲エリア**")
    if not lacking:
        st.success("この料理の必要食材は、Lv60想定なら各食材1担当で足りる見込みです。")
        return

    wanted = _wanted_family_species(lacking)
    recs = recommend_fields(wanted)
    if not recs:
        st.caption("不足食材のおすすめ捕獲エリアを出せる候補がありません。")
        return

    st.caption(
        "不足している食材のおすすめ進化系統について、出現候補が多いフィールド順です。"
        "専属が多いマップほど優先度を上げています。"
    )
    for rec in recs[:5]:
        with st.container(border=True):
            st.markdown(
                f"**{rec['field']}**　候補{rec['total']}種"
                + (f" / 専属{rec['exclusive']}種" if rec["exclusive"] else "")
            )
            if rec["exclusive_names"]:
                st.caption("専属: " + "、".join(rec["exclusive_names"][:10]))
            shared = [n for n in rec["names"] if n not in set(rec["exclusive_names"])]
            if shared:
                st.caption("他でも可: " + "、".join(shared[:12]))

    rows = []
    for ing in lacking:
        for name in INGREDIENT_RECOMMENDATIONS.get(ing, []):
            fields = species_fields(name)
            rows.append(
                {
                    "不足食材": format_ingredient_short(ing),
                    "候補": name,
                    "出現": "、".join(fields) if fields else "不明",
                }
            )
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def _change_recipe_level(recipe_name: str, delta: int) -> None:
    saved = recipe_level.load_recipe_levels()
    current = saved.get(recipe_name, recipe_level.MIN_LEVEL)
    new_level = recipe_level.clamp_level(current + delta)
    merged = dict(saved)
    if new_level <= recipe_level.MIN_LEVEL:
        merged.pop(recipe_name, None)
    else:
        merged[recipe_name] = new_level
    recipe_level.save_recipe_levels(merged)
    st.cache_data.clear()


def _render_level_row(recipe: dict) -> None:
    name = recipe.get("name") or "—"
    level = recipe_level.get_recipe_level(name)
    icon = recipe_icon_url(name)
    img = f'<img src="{icon}" loading="lazy">' if icon else ""
    disabled_minus = level <= recipe_level.MIN_LEVEL
    disabled_plus = level >= recipe_level.MAX_LEVEL

    with st.container(border=True):
        img_col, name_col, lv_col, minus_col, plus_col = st.columns([0.8, 4.2, 1.0, 1.0, 1.0])
        img_col.html(f'<div class="rt-level-img">{img}</div>')
        name_col.html(f'<div class="rt-level-name">{html.escape(name)}</div>')
        lv_col.html(f'<div class="rt-level-current">Lv{level}</div>')
        if minus_col.button("−1", key=f"recipe_lv_minus_{name}", disabled=disabled_minus, use_container_width=True):
            _change_recipe_level(name, -1)
            st.rerun()
        if plus_col.button("+1", key=f"recipe_lv_plus_{name}", disabled=disabled_plus, use_container_width=True):
            _change_recipe_level(name, 1)
            st.rerun()


def _render_level_editor(recipes_by_category: dict[str, list[dict]]) -> None:
    if recipe_level.load_error():
        st.warning(
            "料理レベルの設定が読み込めませんでした。全料理をLv1として計算しています"
            f"（{recipe_level.load_error()}）。"
        )

    saved = recipe_level.load_recipe_levels()
    total = sum(len(rows) for rows in recipes_by_category.values())
    st.caption(
        f"ゲーム内で上がった分だけ、料理ごとに `+1` / `−1` を押します。"
        f"登録済み **{len(saved)}件** / 全{total}品。"
    )

    tabs = st.tabs([RECIPE_CATEGORY_LABELS[key] for key in CATEGORY_ORDER])
    for tab, category in zip(tabs, CATEGORY_ORDER, strict=False):
        with tab:
            rows = recipes_by_category[category]
            if not rows:
                st.html(c.empty_state("このカテゴリに対象料理がありません。"))
                continue
            for recipe in rows:
                _render_level_row(recipe)

    if saved:
        with st.expander("全部 Lv1 に戻す"):
            st.caption("登録済みレベルを消して、すべて未開拓扱いに戻します。")
            if st.button("全消去", key="clear_recipe_levels"):
                recipe_level.save_recipe_levels({})
                st.cache_data.clear()
                st.rerun()


def _render_target_planner(
    recipes_by_category: dict[str, list[dict]],
    owned: list[dict],
    ctx,
    pot_label: str,
    pot_bonus: int,
) -> None:
    if not owned:
        st.html(c.empty_state("所持ポケモンがいません。先に「仲間登録」から追加してください。"))
        return

    st.caption(
        "週のカテゴリごとに、伸ばす料理を1品に絞って、必要食材・担当候補・出会えるフィールドを確認します。"
    )
    with st.container(border=True):
        st.html('<div class="rt-sticky-toggle-anchor"></div>')
        supply_mode = st.segmented_control(
            "担当候補の期待値",
            [SUPPLY_MODE_CURRENT, SUPPLY_MODE_LV60],
            default=SUPPLY_MODE_LV60,
            key="recipe_target_supply_mode",
            help="現状は今の進化段階・レベルで計算。Lv60育成後は最終進化Lv60まで育てた完成形で計算します。",
        ) or SUPPLY_MODE_LV60
        st.caption(
            "現状: いまの進化段階・レベル / Lv60育成後: 最終進化Lv60。"
            "足りる判定と候補の並び順もここに連動します。"
        )
    tabs = st.tabs([RECIPE_CATEGORY_LABELS[key] for key in CATEGORY_ORDER])
    for tab, category in zip(tabs, CATEGORY_ORDER, strict=False):
        with tab:
            _render_recipe(
                category,
                recipes_by_category[category],
                owned,
                base_capacity=int(ctx.pot_capacity),
                pot_label=pot_label,
                pot_bonus=pot_bonus,
                supply_mode=str(supply_mode),
            )


st.html(c.page_banner("料理メニュー", "cyan", icon="🍽"))

db.init_db()
owned = _owned_rows()
ctx = load_play_context()
pot_label, pot_bonus = _pot_skill_label(owned)

st.html(
    '<style>'
    '.rt-recipe-head{display:flex;gap:12px;align-items:center;background:var(--ps-dusk);border:1px solid var(--ps-line);border-radius:16px;padding:12px;margin:8px 0;}'
    '.rt-recipe-head img{width:58px;height:58px;object-fit:contain;flex:0 0 auto;}'
    '.rt-recipe-head h3{margin:0;font-size:1.15rem;}'
    '.rt-recipe-head p{margin:.2rem 0 0;color:var(--ps-ink-dim);font-size:.86rem;}'
    '.rt-req-row{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 14px;}'
    '.rt-ing-head{display:flex;justify-content:space-between;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px;}'
    '.rt-ing-name{display:flex;gap:6px;align-items:center;flex-wrap:wrap;}'
    '.rt-ing-name span{color:var(--ps-ink-dim);font-size:.82rem;}'
    '.rt-ing-state{font-weight:800;font-size:.9rem;}'
    'div[data-testid="stVerticalBlockBorderWrapper"]:has(.rt-sticky-toggle-anchor){position:sticky;top:.35rem;z-index:20;background:rgba(255,255,255,.88);backdrop-filter:blur(10px);box-shadow:0 8px 18px rgba(38,46,64,.08);}'
    '.rt-pot-board{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:10px 0 16px;}'
    '.rt-pot-panel{min-width:0;background:linear-gradient(180deg,#fff,var(--ps-dusk));border:1px solid var(--ps-line);border-radius:14px;padding:9px;}'
    '.rt-pot-panel-head{display:flex;align-items:baseline;justify-content:space-between;gap:8px;margin-bottom:7px;}'
    '.rt-pot-panel-head strong{font-size:.9rem;}'
    '.rt-pot-panel-head span{font-size:.72rem;color:var(--ps-ink-dim);white-space:nowrap;}'
    '.rt-pot-strip{display:flex;gap:7px;overflow-x:auto;padding-bottom:2px;scroll-snap-type:x proximity;}'
    '.rt-pot-card{display:flex;gap:6px;align-items:center;min-width:178px;max-width:178px;background:#fff;border:1px solid color-mix(in srgb,var(--ps-line) 82%,transparent);border-radius:12px;padding:7px;scroll-snap-align:start;}'
    '.rt-pot-img{width:34px;height:34px;display:flex;align-items:center;justify-content:center;flex:0 0 auto;}'
    '.rt-pot-img img{max-width:34px;max-height:34px;object-fit:contain;}'
    '.rt-pot-main{min-width:0;}'
    '.rt-pot-name{font-weight:800;font-size:.8rem;line-height:1.2;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}'
    '.rt-pot-meta{font-size:.68rem;color:var(--ps-ink-dim);line-height:1.2;margin-top:2px;white-space:nowrap;}'
    '.rt-pot-empty{min-width:120px;color:var(--ps-ink-dim);font-size:.8rem;padding:8px;}'
    '.rt-cand-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(245px,1fr));gap:8px;}'
    '.rt-cand-card{background:var(--ps-dusk);border:1px solid var(--ps-line);border-radius:12px;padding:10px;min-width:0;}'
    '.rt-cand-top{display:flex;gap:8px;align-items:center;}'
    '.rt-cand-img{width:50px;height:50px;display:flex;align-items:center;justify-content:center;flex:0 0 auto;}'
    '.rt-cand-main{min-width:0;flex:1 1 auto;}'
    '.rt-cand-name{font-weight:800;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}'
    '.rt-muted{color:var(--ps-ink-dim);font-size:12px;line-height:1.35;}'
    '.rt-daily{text-align:right;min-width:72px;line-height:1.05;flex:0 0 auto;}'
    '.rt-daily span{display:block;color:var(--ps-ink-dim);font-size:10px;white-space:nowrap;}'
    '.rt-daily strong{font-size:1.12rem;color:var(--ps-sp-food);font-variant-numeric:tabular-nums;}'
    '.rt-daily small{font-size:10px;color:var(--ps-ink-dim);margin-left:1px;}'
    '.rt-progress{height:6px;border-radius:999px;background:#eee;overflow:hidden;margin:8px 0 4px;}'
    '.rt-progress div{height:100%;background:var(--ps-sp-food);border-radius:999px;}'
    '.rt-slotrow{display:flex;flex-wrap:wrap;gap:4px;margin-top:7px;}'
    '.rt-slot-chip{display:inline-flex;align-items:center;gap:3px;border:1px solid var(--ps-line);background:#fff;border-radius:999px;padding:2px 7px;font-size:11px;font-weight:750;line-height:1.25;}'
    '.rt-slot-chip-active{color:var(--ps-sp-food);border-color:color-mix(in srgb,var(--ps-sp-food) 55%,#fff);background:color-mix(in srgb,var(--ps-sp-food) 16%,#fff);}'
    '.rt-subrow{display:flex;flex-wrap:wrap;gap:4px;margin-top:7px;}'
    '.rt-level-img{height:48px;display:flex;align-items:center;justify-content:center;}'
    '.rt-level-img img{max-width:54px;max-height:54px;object-fit:contain;}'
    '.rt-level-name{min-height:48px;display:flex;align-items:center;font-weight:850;line-height:1.25;}'
    '.rt-level-current{min-height:48px;display:flex;align-items:center;justify-content:center;font-size:1.05rem;font-weight:900;font-variant-numeric:tabular-nums;color:var(--ps-sp-food);}'
    '@media (max-width:900px){.rt-pot-board{grid-template-columns:repeat(2,minmax(0,1fr));}}'
    '@media (max-width:480px){.rt-pot-board{grid-template-columns:1fr;}.rt-cand-grid{grid-template-columns:1fr;}.rt-recipe-head{border-radius:12px;padding:10px;}.rt-level-name{font-size:.9rem;}}'
    '</style>'
)

recipes_by_category = _recipes_by_category()
mode_tabs = st.tabs(["ターゲット", "レベル"])
with mode_tabs[0]:
    _render_target_planner(recipes_by_category, owned, ctx, pot_label, pot_bonus)
with mode_tabs[1]:
    _render_level_editor(recipes_by_category)
