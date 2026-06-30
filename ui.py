"""スマホ表示を底上げするための共通UIヘルパー。

app.py から apply_mobile_css() を1回呼ぶだけで全ページに効く。
見た目の微調整はこのCSSをいじればOK（各ビューは触らない）。
"""
from __future__ import annotations

import streamlit as st

_MOBILE_CSS = """
<style>
/* ===== ポケスリ管理ツール: スマホ最適化 ===== */

/* 本文の左右余白を詰めて、狭い画面幅を活かす */
.block-container {
    padding-top: 1.2rem;
    padding-bottom: 3rem;
    padding-left: 0.9rem;
    padding-right: 0.9rem;
}

/* 横スクロールする表を指で滑らかに */
[data-testid="stDataFrame"], [data-testid="stTable"] {
    -webkit-overflow-scrolling: touch;
}

/* ===== スマホ幅（〜640px）でだけ効かせる調整 ===== */
@media (max-width: 640px) {
    /* st.columns が潰れないよう、狭い画面では折り返す */
    [data-testid="stHorizontalBlock"] {
        flex-wrap: wrap;
        gap: 0.5rem 0.6rem;
    }
    /* 各列に最低幅を確保 → 5列でも2〜3列に自動で流れる */
    [data-testid="stColumn"], [data-testid="column"] {
        flex: 1 1 7.5rem !important;
        min-width: 7.5rem !important;
    }

    /* 本文をわずかに大きく・行間ゆったり */
    html, body, [data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li {
        font-size: 1.02rem;
        line-height: 1.6;
    }

    /* ボタン・入力を指で押しやすいサイズに */
    .stButton button, .stFormSubmitButton button, .stDownloadButton button {
        min-height: 44px;
        font-size: 1rem;
    }
    input, textarea,
    [data-baseweb="select"] > div,
    [data-baseweb="input"] > div {
        min-height: 42px;
        font-size: 1rem !important;
    }

    /* メトリクスの値が大きすぎて折り返すのを防ぐ */
    [data-testid="stMetricValue"] { font-size: 1.4rem; }
    [data-testid="stMetricLabel"] { font-size: 0.8rem; }

    /* 見出しを少し控えめにして縦を節約 */
    h1 { font-size: 1.6rem; }
    h2 { font-size: 1.3rem; }
    h3 { font-size: 1.1rem; }

    /* タブが多いとき横スクロールできるように */
    [data-testid="stTabs"] [data-baseweb="tab-list"] {
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
    }
}
</style>
"""


def apply_mobile_css() -> None:
    """全ページ共通のスマホ最適化CSSを注入する。"""
    st.markdown(_MOBILE_CSS, unsafe_allow_html=True)
