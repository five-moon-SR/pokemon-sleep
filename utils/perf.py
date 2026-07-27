"""URLに `?perf=1` を付けたときだけ働く、区間別の実行時間計測。

通常の画面表示は一切変えない。無効時は start/mark/render がすべて即 return
するので、実行コストは実質ゼロ。

使い方:
    from utils import perf
    perf.start()                 # 計測開始（app.py の先頭で1回）
    ...
    perf.mark("所持ポケ読込")     # 直前の mark からの経過を記録
    ...
    perf.render()                # 表を出す（ページ末尾で1回）

本番が遅い原因を切り分けるための一時的な道具。原因が確定したら消してよい。
"""

from __future__ import annotations

import time

import streamlit as st

_marks: list[tuple[str, float]] = []
_t0: float | None = None
_last: float | None = None


def enabled() -> bool:
    """URLクエリに perf=1 が付いているか。"""
    try:
        return str(st.query_params.get("perf", "")).lower() in ("1", "true", "on")
    except Exception:
        # スクリプト実行コンテキスト外（テスト等）では黙って無効。
        return False


def start() -> None:
    global _marks, _t0, _last
    if not enabled():
        return
    _marks = []
    _t0 = _last = time.perf_counter()


def mark(label: str) -> None:
    global _last
    if not enabled() or _last is None:
        return
    now = time.perf_counter()
    _marks.append((label, (now - _last) * 1000.0))
    _last = now


def render() -> None:
    """記録した区間を表で出す。遅い順が分かるよう実測値をそのまま並べる。"""
    if not enabled() or _t0 is None:
        return
    total = (time.perf_counter() - _t0) * 1000.0
    rows = ["| 区間 | ms |", "|---|---:|"]
    for label, ms in _marks:
        rows.append(f"| {label} | {ms:,.0f} |")
    rows.append(f"| **合計** | **{total:,.0f}** |")
    with st.expander(f"⏱ サーバ実行 {total:,.0f} ms", expanded=True):
        st.markdown("\n".join(rows))
        st.caption(
            "?perf=1 が付いている間だけ表示されます。"
            "ここに出ない時間は、ネットワーク往復かフロント描画側です。"
        )
