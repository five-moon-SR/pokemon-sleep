"""イベント情報ページ。

公式ニュースを主ソースに、直近の予定・開催中・公式予告をアプリ内で見る。
攻略サイト由来の未確定情報は source_level で明示し、恒久データと混ぜない。
"""

from __future__ import annotations

from datetime import date
import html
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from ui import components as c

EVENT_PATH = Path(__file__).resolve().parent.parent / "data" / "events.json"

STATUS_ORDER = {
    "開催中": 0,
    "予定": 1,
    "公式予告": 2,
    "Sleep公式未確認": 3,
    "終了": 4,
}
STATUS_COLORS = {
    "開催中": "--ps-sp-food",
    "予定": "--ps-rank-s",
    "公式予告": "--ps-sp-skill",
    "Sleep公式未確認": "--ps-rank-a",
    "終了": "--ps-ink-dim",
}


@st.cache_data(show_spinner=False)
def _load_events() -> dict:
    if not EVENT_PATH.exists():
        return {"updated_at": "", "records": []}
    return json.loads(EVENT_PATH.read_text(encoding="utf-8"))


def _parse_day(value: str | None) -> date | None:
    if not value or len(value) != 10:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _computed_status(event: dict) -> str:
    """日付が明確なものだけ現在日で補正する。月だけの公式予告は手入力statusを尊重。"""
    start = _parse_day(event.get("start"))
    end = _parse_day(event.get("end"))
    today = date.today()
    if start and end:
        if today < start:
            return "予定"
        if start <= today <= end:
            return "開催中"
        return "終了"
    if start and today < start:
        return "予定"
    return event.get("status") or "予定"


def _event_card(event: dict) -> str:
    status = _computed_status(event)
    var = STATUS_COLORS.get(status, "--ps-ink-dim")
    fields = event.get("fields") or []
    field_line = " / ".join(fields) if fields else "未定・対象外"
    highlights = "".join(
        f"<li>{html.escape(str(item))}</li>"
        for item in event.get("highlights", [])
        if str(item).strip()
    )
    sources = "".join(
        f'<a href="{html.escape(src["url"])}" target="_blank" rel="noreferrer">'
        f'{html.escape(src["label"])}</a>'
        for src in event.get("sources", [])
        if src.get("url") and src.get("label")
    )
    return (
        '<article class="ev-card">'
        '<div class="ev-head">'
        '<div>'
        f'<div class="ev-kind">{html.escape(event.get("kind") or "イベント")}</div>'
        f'<h3>{html.escape(event.get("title") or "—")}</h3>'
        '</div>'
        f'<span class="ev-status" style="color:var({var});'
        f'background:color-mix(in srgb,var({var}) 14%,#fff);">'
        f'{html.escape(status)}</span>'
        '</div>'
        '<div class="ev-meta">'
        f'<span>期間: {html.escape(str(event.get("start") or "未定"))}'
        f' 〜 {html.escape(str(event.get("end") or "未定"))}</span>'
        f'<span>フィールド: {html.escape(field_line)}</span>'
        f'<span>{html.escape(event.get("source_level") or "")}</span>'
        '</div>'
        f'<p>{html.escape(event.get("summary") or "")}</p>'
        + (f'<ul>{highlights}</ul>' if highlights else "")
        + f'<div class="ev-action"><b>見ること:</b> {html.escape(event.get("action") or "—")}</div>'
        + (f'<div class="ev-sources">{sources}</div>' if sources else "")
        + '</article>'
    )


st.html(c.page_banner("イベント", "blue", icon="📅"))

data = _load_events()
events = list(data.get("records") or [])
events.sort(key=lambda ev: (STATUS_ORDER.get(_computed_status(ev), 9), ev.get("start") or "9999"))

st.caption(
    f"公式ニュースを主ソースにした直近イベントメモ。最終更新: {data.get('updated_at') or '—'}。"
    "攻略サイト由来の情報は、公式確定と分けて表示します。"
)

st.html(
    '<style>'
    '.ev-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:10px;}'
    '.ev-card{background:linear-gradient(180deg,#fff,var(--ps-dusk));border:1px solid var(--ps-line);border-radius:16px;padding:12px;box-shadow:0 3px 10px rgba(45,57,80,.08);}'
    '.ev-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start;}'
    '.ev-kind{font-size:.72rem;color:var(--ps-ink-dim);font-weight:800;letter-spacing:.08em;}'
    '.ev-card h3{margin:.12rem 0 .3rem;font-size:1.02rem;line-height:1.25;}'
    '.ev-status{border-radius:999px;padding:3px 9px;font-size:.78rem;font-weight:900;white-space:nowrap;}'
    '.ev-meta{display:flex;flex-wrap:wrap;gap:4px;margin:5px 0 7px;}'
    '.ev-meta span{background:#fff;border:1px solid var(--ps-line);border-radius:999px;padding:2px 8px;font-size:.74rem;color:var(--ps-ink-dim);}'
    '.ev-card p{margin:.35rem 0;line-height:1.55;}'
    '.ev-card ul{margin:.35rem 0;padding-left:1.2rem;line-height:1.5;}'
    '.ev-action{border-top:1px solid rgba(0,0,0,.08);padding-top:7px;margin-top:7px;font-size:.9rem;}'
    '.ev-sources{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px;}'
    '.ev-sources a{font-size:.78rem;text-decoration:none;border:1px solid var(--ps-line);border-radius:999px;padding:3px 8px;background:#fff;}'
    '@media (max-width:480px){.ev-grid{grid-template-columns:1fr;}.ev-card{border-radius:12px;padding:10px;}}'
    '</style>'
)

if not events:
    st.html(c.empty_state("登録されているイベント情報がありません。"))
    st.stop()

st.html('<div class="ev-grid">' + "".join(_event_card(ev) for ev in events) + '</div>')

with st.expander("更新ルール"):
    st.markdown(
        """
- 公式ニュースを最優先に見る
- Wikiはマスター、料理、出現表の更新確認に使う
- 攻略サイト情報は補助扱い。予想・未確定値は恒久データに入れない
- イベント限定出現と常設出現は分ける
- 新情報を入れたら、参照URLと未反映理由も残す
"""
    )

rows = [
    {
        "状態": _computed_status(ev),
        "イベント": ev.get("title"),
        "期間": f"{ev.get('start') or '未定'} 〜 {ev.get('end') or '未定'}",
        "根拠": ev.get("source_level"),
    }
    for ev in events
]
st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
