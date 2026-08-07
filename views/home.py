"""ホーム画面（ダッシュボード）。

ブロック構成:
  ① 今週の攻略プラン — 料理カテゴリ×フィールドの定番5体と週見通し
  ② 所持ポケモン統計 — 統計タイル + だいふく/specialty分布
  ③ 最近登録した子 — カード行
プレイヤープロフィール編集は ⚙ ボタンから st.dialog で開く。
"""

from __future__ import annotations

from datetime import datetime
import html

import pandas as pd
import streamlit as st

import db
from image_utils import field_icon_url, pokemon_image_url, recipe_icon_url
from ui import components as c
from utils.party_logic import RECIPE_CATEGORY_LABELS
from utils.plan_simulation import capture_improvements, simulate_plan
from utils import perf, recipe_level
from utils.roster_impact import item_impact_ranking
from utils.play_context import PlayContext, load_play_context, save_play_context

STRATEGY_DIRECTION_KEY = "user.strategy_direction"
DEFAULT_STRATEGY_DIRECTION = {
    "title": "ジンジャー担当を確保する",
    "priority": "最優先: ヨーギラスを捕まえる",
    "maps": ["アンバー渓谷", "トープ洞窟", "ワカクサ本島"],
    "body": (
        "いま一番のウィークポイントは、あったかジンジャーを安定して拾える食材ポケモンが"
        "足りないこと。まずはアンバー渓谷、トープ洞窟、ワカクサ本島でヨーギラスを狙い、将来的な"
        "ジンジャー担当を作る。進化後まで見るなら、サナギラスはトープ洞窟/ワカクサ本島 EX、"
        "バンギラスはウノハナ雪原/ワカクサ本島 EXも候補。"
    ),
    "next_steps": [
        "アンバー渓谷、トープ洞窟、ワカクサ本島でヨーギラスを優先して睡眠リサーチする",
        "ジンジャー枠を2枠以上持つ個体を候補にする",
        "ヒーラー更新や他食材の補強は、ジンジャー担当確保の次点で見る",
    ],
}

ctx = load_play_context()
perf.mark("home: load_play_context")

st.html(c.page_banner("ホーム", "green", icon="🏠"))


def _eff_lv(p: dict) -> int:
    return p.get("current_level") or p.get("caught_level") or p.get("level") or 1


def _load_strategy_direction() -> dict:
    saved = db.get_setting(STRATEGY_DIRECTION_KEY, {}) or {}
    maps = saved.get("maps")
    if isinstance(maps, str):
        maps = [m.strip() for m in maps.replace("、", "/").split("/") if m.strip()]
    return {
        "title": saved.get("title") or DEFAULT_STRATEGY_DIRECTION["title"],
        "priority": saved.get("priority") or DEFAULT_STRATEGY_DIRECTION["priority"],
        "maps": list(maps or DEFAULT_STRATEGY_DIRECTION["maps"]),
        "body": saved.get("body") or DEFAULT_STRATEGY_DIRECTION["body"],
        "next_steps": list(saved.get("next_steps") or DEFAULT_STRATEGY_DIRECTION["next_steps"]),
    }


def _save_strategy_direction(direction: dict) -> None:
    db.set_setting(STRATEGY_DIRECTION_KEY, direction)


def _direction_card(direction: dict) -> str:
    maps = [
        str(m).strip()
        for m in direction.get("maps", [])
        if str(m).strip()
    ]
    map_chips = "".join(
        '<span style="display:inline-flex;align-items:center;border:1px solid '
        'color-mix(in srgb,var(--ps-sp-food) 28%,#fff);background:#fff;'
        'border-radius:999px;padding:3px 9px;font-size:.78rem;font-weight:800;">'
        f'{html.escape(map_name)}</span>'
        for map_name in maps
    )
    steps = "".join(
        f"<li>{html.escape(str(step))}</li>"
        for step in direction.get("next_steps", [])
        if str(step).strip()
    )
    return (
        '<section style="background:linear-gradient(135deg,#F4FFF0,#FFF8D7);'
        'border:1px solid color-mix(in srgb,var(--ps-sp-food) 35%,#fff);'
        'border-radius:16px;padding:12px 14px;margin:8px 0 12px;'
        'box-shadow:0 4px 12px rgba(65,92,44,.08);">'
        '<div style="display:flex;gap:10px;align-items:flex-start;justify-content:space-between;">'
        '<div>'
        '<div style="font-size:.78rem;color:var(--ps-ink-dim);font-weight:800;letter-spacing:.08em;">直近の方針</div>'
        f'<h3 style="margin:.12rem 0 .2rem;font-size:1.08rem;">{html.escape(str(direction["title"]))}</h3>'
        f'<div style="font-weight:900;color:var(--ps-sp-food);">{html.escape(str(direction["priority"]))}</div>'
        + (
            '<div style="display:flex;gap:5px;flex-wrap:wrap;margin:.35rem 0 .1rem;">'
            '<span style="font-size:.78rem;color:var(--ps-ink-dim);font-weight:800;padding:3px 0;">出現マップ</span>'
            f'{map_chips}</div>'
            if map_chips
            else ""
        )
        + f'<p style="margin:.35rem 0;color:var(--ps-ink);line-height:1.55;">{html.escape(str(direction["body"]))}</p>'
        + (f'<ul style="margin:.35rem 0 0;padding-left:1.2rem;line-height:1.55;">{steps}</ul>' if steps else "")
        + '</div></div></section>'
    )


@st.dialog("🎯 直近の方針")
def _strategy_direction_dialog() -> None:
    direction = _load_strategy_direction()
    with st.form("strategy_direction_form"):
        title = st.text_input("見出し", value=direction["title"])
        priority = st.text_input("最優先", value=direction["priority"])
        maps_text = st.text_area(
            "出現マップ（1行1件）",
            value="\n".join(direction["maps"]),
            height=80,
            help="例: ヨーギラスなら アンバー渓谷 / トープ洞窟 / ワカクサ本島",
        )
        body = st.text_area("理由・背景", value=direction["body"], height=110)
        steps_text = st.text_area(
            "次にやること（1行1件）",
            value="\n".join(direction["next_steps"]),
            height=120,
        )
        if st.form_submit_button("💾 保存", type="primary", use_container_width=True):
            _save_strategy_direction({
                "title": title.strip() or DEFAULT_STRATEGY_DIRECTION["title"],
                "priority": priority.strip() or DEFAULT_STRATEGY_DIRECTION["priority"],
                "maps": [s.strip() for s in maps_text.splitlines() if s.strip()],
                "body": body.strip() or DEFAULT_STRATEGY_DIRECTION["body"],
                "next_steps": [s.strip() for s in steps_text.splitlines() if s.strip()],
            })
            st.rerun()


@st.dialog("🧑 プレイヤープロフィール")
def _profile_dialog() -> None:
    with st.form("profile_form"):
        c1 = st.columns(2)
        rr = c1[0].number_input("リサーチランク", min_value=1, max_value=80, value=int(ctx.research_rank), step=1)
        pot = c1[1].number_input(
            "鍋容量", min_value=15, max_value=2000, value=int(ctx.pot_capacity), step=1,
            help="現在の鍋の容量。料理期待値の上限として使う。",
        )
        c2 = st.columns(2)
        sleep_wd = c2[0].number_input("平日 睡眠時間 (h)", min_value=0.0, max_value=14.0, value=float(ctx.sleep_hours_weekday), step=0.5)
        sleep_we = c2[1].number_input("休日 睡眠時間 (h)", min_value=0.0, max_value=14.0, value=float(ctx.sleep_hours_weekend), step=0.5)

        c3 = st.columns(3)
        bf = c3[0].time_input("🍞 朝食", value=datetime.strptime(ctx.meal_breakfast, "%H:%M").time(), step=60 * 15)
        ln = c3[1].time_input("🍙 昼食", value=datetime.strptime(ctx.meal_lunch, "%H:%M").time(), step=60 * 15)
        dn = c3[2].time_input("🍛 夕食", value=datetime.strptime(ctx.meal_dinner, "%H:%M").time(), step=60 * 15)

        if st.form_submit_button("💾 保存", type="primary", use_container_width=True):
            save_play_context(PlayContext(
                research_rank=int(rr),
                pot_capacity=int(pot),
                sleep_hours_weekday=float(sleep_wd),
                sleep_hours_weekend=float(sleep_we),
                meal_breakfast=bf.strftime("%H:%M"),
                meal_lunch=ln.strftime("%H:%M"),
                meal_dinner=dn.strftime("%H:%M"),
            ))
            st.rerun()


prof_cols = st.columns([3, 2])
prof_cols[0].caption(
    f"RR{ctx.research_rank} · 鍋{ctx.pot_capacity} · "
    f"おてつだい 平日{ctx.active_hours():.1f}h/休日{ctx.active_hours(weekend=True):.1f}h"
)
if prof_cols[1].button("⚙ 設定", use_container_width=True):
    _profile_dialog()

# よく使う導線を上に置く（ホームから2タップで目的のページに着けるように）。
# 役割ページはサイドバー以外からのリンクが1つも無かったので、ここに入れる。
nav_cols = st.columns(5)
nav_cols[0].page_link("views/party.py", label="編成", icon="🧭", use_container_width=True)
nav_cols[1].page_link("views/register.py", label="登録", icon="📝", use_container_width=True)
nav_cols[2].page_link("views/catch_policy.py", label="捕獲", icon="🏅", use_container_width=True)
nav_cols[3].page_link("views/events.py", label="イベント", icon="📅", use_container_width=True)
nav_cols[4].page_link("views/hand.py", label="役割", icon="🧩", use_container_width=True)

direction = _load_strategy_direction()
st.html(_direction_card(direction))
dir_cols = st.columns([3, 1])
dir_cols[0].page_link("views/catch_policy.py", label="捕獲方針を見る →", icon="🏅")
if dir_cols[1].button("方針を編集", use_container_width=True):
    _strategy_direction_dialog()

perf.mark("home: ヘッダ＋設定ボタン")

owned = [dict(r) for r in db.list_pokemon()]
perf.mark("home: list_pokemon")


# ============ ① 今週の攻略プラン ============

active_week = db.get_setting("user.active_strategy_week", {}) or {}
pt = db.get_party(int(active_week["plan_id"])) if active_week.get("plan_id") else None
perf.mark("home: get_setting + get_party")
if pt:
    st.html(c.section_header(f"今週の攻略プラン: {pt['name']}"))

    # フィールド/好みきのみ/候補レシピ を1行のチップにまとめる
    field_name = pt.get("field_name") or "（未設定）"
    if active_week.get("random_berries"):
        fav = list(active_week["random_berries"])
    else:
        fr = next((f for f in db.list_all_field_records() if f["name"] == field_name), None)
        fav = [b["name"] for b in (fr.get("favorite_berries") or [])] if fr else []

    chips = [c.icon_chip(field_icon_url(field_name), field_name, size=24)]
    chips += [c.berry_chip(b) for b in fav]
    if pt.get("main_recipe"):
        rname = pt["main_recipe"]
        chips.append(c.icon_chip(recipe_icon_url(rname), rname))
    st.html('<div style="display:flex; flex-wrap:wrap; gap:4px;">' + "".join(chips) + "</div>")
    perf.mark("home: フィールド/きのみ/レシピのチップ")

    cards = []
    for mid in (pt.get("member_ids") or [])[:5]:
        m_row = db.get_pokemon(mid)
        if m_row is None:
            cards.append(c.pokemon_card(title="（削除済み）", mini=True))
            continue
        m = dict(m_row)
        master = db.get_species_data(m["species_name"]) or {}
        cards.append(c.pokemon_card(
            title=m.get("nickname") or m["species_name"],
            subtitle=f"{m['species_name']} · Lv{_eff_lv(m)}",
            specialty=master.get("specialty"),
            berry_name=(master.get("berry") or {}).get("name"),
            img_url=pokemon_image_url(m["species_name"]),
            badges=[c.rank_badge(m.get("daifuku_rank"))],
            mini=True,
        ))
    if cards:
        st.html(c.row_scroll(cards))
    perf.mark("home: メンバー5体のカード")

    members = [
        dict(row)
        for mid in (pt.get("member_ids") or [])
        if (row := db.get_pokemon(mid)) is not None
    ]
    recipe = next(
        (
            r for r in db.list_all_recipe_records()
            if r["name"] == pt.get("main_recipe")
        ),
        None,
    )
    perf.mark("home: members再取得＋レシピ検索")

    if len(members) == 5 and recipe:
        sim = simulate_plan(
            members,
            recipe,
            fav_berries=set(fav),
            ctx=ctx,
            starting_inventory=active_week.get("starting_inventory", {}),
            event_set=set(active_week.get("event_bonuses", [])),
        )
        # st.metric は長い料理名や律速食材が「みつあつめチョコワッ…」と省略されるので、
        # 数値はタイル、テキストは1行の文として出す。
        st.html(c.stat_tiles([
            c.stat_tile("3食安定度", f"{sim.stability:.0%}", f"{sim.cooked_meals}/21食"),
            c.stat_tile("週期待エナジー", f"{sim.weekly_energy:,.0f}", "en"),
            c.stat_tile("1日の料理", f"{sim.cooked_per_day:.1f}", "回"),
        ]))
        bottleneck = " / ".join(sim.bottlenecks) if sim.bottlenecks else "なし"
        st.caption(f"主料理: **{pt.get('main_recipe') or '—'}**　｜　律速: {bottleneck}")

        perf.mark("home: simulate_plan＋指標4つ")

        # 育成おすすめは「育成・アイテム」ページと同じ物差し（全定番プランの
        # 週エナジー実改善・今週は重み2倍）を使う。ページごとに順位が違うと
        # どれを信じればいいか分からなくなるため。
        # キャッシュキーには所持状態も混ぜる（レベルを上げても更新されなかった）。
        roster_sig = ";".join(
            f"{p['id']}:{p.get('current_level')}:{p.get('main_skill_level')}"
            for p in sorted(owned, key=lambda x: int(x["id"]))
        )
        advice_key = (
            f"_home_advice_{pt['id']}:{pt.get('updated_at')}:"
            f"{hash(roster_sig)}:{hash(recipe_level.levels_signature())}"
        )
        if advice_key not in st.session_state:
            growth = item_impact_ranking(owned, "level")
            catches = capture_improvements(
                members, recipe, fav_berries=set(fav), ctx=ctx, limit=3
            )
            st.session_state[advice_key] = (growth[:3], catches[:3])
        perf.mark("home: 育成/捕獲アドバイス計算")

        growth, catches = st.session_state[advice_key]
        # スマホでは2列に割ると1項目が3行に折れて読めないので、全幅で縦に並べる
        with st.expander("🌱 次の一手（育成・捕獲の候補）", expanded=True):
            if growth:
                st.markdown("**育てる**")
                for item in growth:
                    if item.weighted_delta > 0:
                        gain = (
                            f"今週 {item.this_week_delta:+,.0f} en"
                            if item.this_week_delta > 0
                            else f"全プラン {item.raw_delta:+,.0f} en"
                        )
                    else:
                        gain = f"育成後評価 {item.eval_delta:+.1f}"
                    st.markdown(f"- {item.label} → **{item.detail}**　{gain}")
                st.caption("並びは登録済みプランの週エナジー改善（今週は重み2倍）。")
            if catches:
                st.markdown("**捕まえる**")
                for item in catches:
                    st.markdown(
                        f"- {item['species_name']}（{item['composition']}）"
                        f"　{' / '.join(item['fills'])}　安定度 {item['stability_delta']:+.0%}"
                    )
            if not growth and not catches:
                st.caption("いまの編成で伸ばせる余地は見つからなかった。")
            st.page_link("views/items.py", label="投資先をすべて見る →", icon="🎁")

    meta_cols = st.columns([3, 1])
    category = pt.get("recipe_category")
    meta_cols[0].caption(
        f"{RECIPE_CATEGORY_LABELS.get(category, category or '旧編成')}　"
        f"最終更新: {(pt.get('updated_at') or '')[:16]}"
    )
    meta_cols[1].page_link("views/party.py", label="→ 攻略プランを調整", icon="🧭")
else:
    st.html(c.section_header("今週の攻略プラン"))
    st.html(c.empty_state("料理カテゴリとフィールドを選び、今週の攻略プランを設定してください。"))
    st.page_link("views/party.py", label="攻略プランを作る →", icon="🧭")


perf.mark("home: ①攻略プラン 仕上げ")


# ============ ② 所持ポケモン統計 ============

st.html(c.section_header("所持ポケモン"))

if not owned:
    st.html(c.empty_state("まだ登録されていません。「個体登録」から追加できます。"))
else:
    species_count = len({p["species_name"] for p in owned})
    lv60_count = sum(1 for p in owned if _eff_lv(p) >= 60)
    slot3_count = sum(1 for p in owned if p.get("ingredient_3"))
    rank_evaluated = sum(1 for p in owned if p.get("daifuku_rank"))

    st.html(c.stat_tiles([
        c.stat_tile("個体数", str(len(owned))),
        c.stat_tile("種族数", str(species_count)),
        c.stat_tile("Lv60到達", str(lv60_count)),
        c.stat_tile("食材枠3解放", str(slot3_count)),
        c.stat_tile("だいふく評価済", str(rank_evaluated)),
    ]))

    perf.mark("home: 統計タイル5枚")

    # 分布グラフは毎回見るものではないので畳む（スマホで縦を食うため）
    with st.expander("📊 分布を見る（だいふくランク / とくいなもの）", expanded=False):
        chart_cols = st.columns(2)

        # だいふくランク分布
        rank_counts: dict[str, int] = {}
        for p in owned:
            r = p.get("daifuku_rank") or "未評価"
            rank_counts[r] = rank_counts.get(r, 0) + 1
        rank_order = ["SS", "S", "A", "B", "C", "D", "未評価"]
        rank_rows = [(r, rank_counts[r]) for r in rank_order if r in rank_counts]
        with chart_cols[0]:
            st.markdown("**だいふくランク分布**")
            if rank_rows:
                df = pd.DataFrame(rank_rows, columns=["ランク", "人数"])
                st.bar_chart(df.set_index("ランク"), height=180, color="#F0B32E")
            else:
                st.caption("—")

        perf.mark("home: チャート① だいふくランク分布")

        # とくいなもの分布
        sp_counts: dict[str, int] = {}
        for p in owned:
            master = db.get_species_data(p["species_name"]) or {}
            sp = master.get("specialty") or "?"
            sp_counts[sp] = sp_counts.get(sp, 0) + 1
        with chart_cols[1]:
            st.markdown("**とくいなもの分布**")
            if sp_counts:
                df = pd.DataFrame({"区分": list(sp_counts), "人数": list(sp_counts.values())})
                st.bar_chart(df.set_index("区分"), height=180, color="#3E87C7")
            else:
                st.caption("—")


perf.mark("home: チャート② とくいなもの分布")


# ============ ③ 最近登録した子 ============

st.html(c.section_header("最近登録した子"))
if not owned:
    st.html(c.empty_state("まだ登録されていません。"))
else:
    cards = []
    for p in owned[:6]:
        master = db.get_species_data(p["species_name"]) or {}
        cards.append(c.pokemon_card(
            title=p.get("nickname") or p["species_name"],
            subtitle=f"{p['species_name']} · Lv{_eff_lv(p)}",
            specialty=master.get("specialty"),
            berry_name=(master.get("berry") or {}).get("name"),
            img_url=pokemon_image_url(p["species_name"]),
            badges=[c.rank_badge(p.get("daifuku_rank"))],
            mini=True,
        ))
    st.html(c.row_scroll(cards))

perf.mark("home: 最近登録した子")
perf.render()
