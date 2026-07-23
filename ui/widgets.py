"""個体の簡易ステータスをポップオーバー表示する共通ウィジェット。

戦略ページ（食材・きのみ／スキル・役割 等）でポケモンを名前だけで並べると、
肉ネーム未設定の同種個体が見分けられない。押すと簡易ステータスが出る
ポップオーバーにして「どの個体か」を判別できるようにする。

DBの生フィールドのみ参照（評価計算はしない）ので、多数並べても軽い。
"""

from __future__ import annotations

from typing import Any

import streamlit as st

import db
from image_utils import pokemon_image_url

_SUB_LVS = (10, 25, 50, 75, 100)


def pokemon_popover_row(
    p: dict[str, Any] | None,
    *,
    label: str,
    caption: str,
    img_species: str | None = None,
    badges_text: str | None = None,
) -> None:
    """画像＋名前ポップオーバー＋説明キャプションの1行。

    名前ボタン（ポケモン）を押すと簡易ステータスが出る。p が None（未所持等）なら
    ポップオーバーにせず名前をそのまま表示する。
    """
    cols = st.columns([1, 3, 4], vertical_alignment="center")
    url = pokemon_image_url(img_species or (p or {}).get("species_name", ""))
    if url:
        cols[0].markdown(
            f'<img src="{url}" width="40" loading="lazy" style="border-radius:8px;">',
            unsafe_allow_html=True,
        )
    with cols[1]:
        if p is not None:
            pokemon_status_popover(p, label=label, use_container_width=True)
        else:
            st.markdown(f"**{label}**")
    cap = caption if not badges_text else f"{badges_text}　{caption}"
    cols[2].caption(cap)


def pokemon_status_popover(
    p: dict[str, Any],
    *,
    label: str,
    help_text: str | None = None,
    use_container_width: bool = False,
) -> None:
    """個体の簡易ステータスをポップオーバー表示する。

    label: トリガーボタンの文言（例: "リーフィア 3.1/日" や "🔍"）。
    p: pokemon レコード（dict）。
    """
    species = db.get_species_data(p.get("species_name", "")) or {}
    with st.popover(label, help=help_text, use_container_width=use_container_width):
        nick = p.get("nickname")
        if nick:
            st.markdown(f"**{nick}**（{p.get('species_name', '')}）")
        else:
            st.markdown(f"**{p.get('species_name', '')}**　🏷肉ネーム未設定")

        lv = p.get("current_level") or p.get("caught_level") or p.get("level")
        bits = [f"Lv{lv}" if lv else "Lv—", f"性格 {p.get('nature') or '無補正/未設定'}"]
        if species.get("specialty"):
            bits.append(str(species["specialty"]))
        st.caption(" ・ ".join(bits))

        ms = p.get("main_skill_name") or species.get("main_skill") or "—"
        st.caption(f"メインスキル: {ms} Lv{p.get('main_skill_level') or 1}")

        subs = [p.get(f"subskill_lv{n}") for n in _SUB_LVS]
        subs = [s for s in subs if s]
        st.caption("サブ: " + (" / ".join(subs) if subs else "—"))

        berry = (species.get("berry") or {}).get("name") or "—"
        ings = [p.get("ingredient_1"), p.get("ingredient_2"), p.get("ingredient_3")]
        ings = [i for i in ings if i]
        st.caption(f"きのみ: {berry}　／　食材: {'/'.join(ings) if ings else '—'}")

        ribbon = int(p.get("sleep_ribbon_stage") or 0)
        if ribbon:
            st.caption(f"🎀 おやすみリボン 段階{ribbon}")
        if p.get("note"):
            st.caption(f"📝 {p['note']}")
