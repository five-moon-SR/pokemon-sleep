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

_SUB_LVS = (10, 25, 50, 75, 100)


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
