"""テーマ「月夜のリサーチノート」のCSSトークンと共通スタイル注入。

役割分担:
- 標準ウィジェットの色・角丸 → .streamlit/config.toml（ここでは触らない）
- 自作コンポーネント(.ps-*)のスタイルとスマホ最適化 → このファイル

セレクタの優先順位ルール（Streamlit更新で壊れない書き方）:
  1. 自前クラス（.ps-card 等）
  2. st.container(key=...) が生成する安定クラス st-key-<key>
  3. data-testid
  st-emotion-cache-* クラスへの依存は禁止。
"""
from __future__ import annotations

import streamlit as st

# --- カラートークン（config.toml と同じ世界観。コンポーネントHTMLはCSS変数だけ参照する） ---

NIGHT = "#131A2A"      # 夜空/アプリ背景
DUSK = "#1C2438"       # カード面
LINE = "#2C3650"       # 罫線
INK = "#E8EAF2"        # 本文
INK_DIM = "#98A0B8"    # キャプション
MOON = "#F5D06F"       # 月光ゴールド（アクセントはこの1色のみ）

_THEME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Zen+Maru+Gothic:wght@400;500;700&display=swap');

:root {
    --ps-night: #131A2A;
    --ps-dusk: #1C2438;
    --ps-line: #2C3650;
    --ps-ink: #E8EAF2;
    --ps-ink-dim: #98A0B8;
    --ps-moon: #F5D06F;

    /* 機能色（ゲーム由来なので固定。ダーク面用に彩度調整済み） */
    --ps-rank-masuda: #F5D06F;
    --ps-rank-ss: #FF8A9A;
    --ps-rank-s: #FFAB70;
    --ps-rank-a: #E8C84A;
    --ps-rank-b: #7FC77F;
    --ps-rank-c: #6FA8DC;
    --ps-rank-d: #8890A8;
    --ps-sub-gold: #E8C84A;
    --ps-sub-blue: #6FA8DC;
    --ps-sub-white: #C8CEDC;
    --ps-sp-berry: #7FC77F;
    --ps-sp-food: #FFAB70;
    --ps-sp-skill: #6FA8DC;
    --ps-sp-all: #C0A8E0;
}

html, body, [data-testid="stAppViewContainer"] * {
    font-family: "Zen Maru Gothic", "Hiragino Maru Gothic ProN", sans-serif;
}
code, pre, [data-testid="stCode"] * { font-family: ui-monospace, monospace; }

/* Materialアイコンはアイコンフォントに戻す（上の全要素フォント指定が
   ligature を壊して "keyboard_double_arrow_right" 等の生テキストが出るのを防ぐ） */
[data-testid="stIconMaterial"],
[class*="material-symbols"] {
    font-family: "Material Symbols Rounded" !important;
}

/* 数値は桁が揃う字形で */
[data-testid="stMetricValue"], .ps-num { font-variant-numeric: tabular-nums; }

/* ===== 自作コンポーネント ===== */

/* カード: 影は1段のみ（夜なので光らせない） */
.ps-card {
    background: var(--ps-dusk);
    border: 1px solid var(--ps-line);
    border-radius: 12px;
    padding: 12px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25);
    color: var(--ps-ink);
}
.ps-card .ps-card-title {
    font-weight: 700;
    font-size: 0.95rem;
    line-height: 1.3;
}
.ps-card .ps-card-sub {
    color: var(--ps-ink-dim);
    font-size: 0.78rem;
}

/* カードグリッド（owned カードモード等）: スマホで2列に落ちる */
.ps-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: 10px;
}
@media (max-width: 480px) {
    .ps-grid { grid-template-columns: repeat(2, 1fr); }
}

/* ミニカードの横スクロール行（home 直近編成 / party スロット） */
.ps-row-scroll {
    display: flex;
    gap: 8px;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    padding-bottom: 4px;
}
.ps-row-scroll > * { flex: 0 0 auto; }

/* バッジ（ランク等）: 淡い同系面 + 明るい文字 */
.ps-badge {
    display: inline-block;
    padding: 1px 8px;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 700;
    line-height: 1.5;
    white-space: nowrap;
}

/* チップ（サブスキル・アイコン+個数） */
.ps-chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 1px 8px;
    border-radius: 999px;
    font-size: 0.75rem;
    line-height: 1.6;
    white-space: nowrap;
    border: 1px solid var(--ps-line);
    background: color-mix(in srgb, var(--ps-dusk) 70%, transparent);
}
.ps-chip img { vertical-align: middle; }
.ps-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
}

/* 統計タイル（st.metric の代替。スマホで潰れない自前grid） */
.ps-tiles {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: 8px;
}
.ps-tile {
    background: var(--ps-dusk);
    border: 1px solid var(--ps-line);
    border-radius: 12px;
    padding: 10px 12px;
}
.ps-tile .ps-tile-label { color: var(--ps-ink-dim); font-size: 0.72rem; }
.ps-tile .ps-tile-value {
    font-size: 1.35rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    line-height: 1.3;
}
.ps-tile .ps-tile-sub { color: var(--ps-ink-dim); font-size: 0.72rem; }

/* セクション見出し: 細線 + 小さな月 */
.ps-section {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 1.1rem 0 0.5rem;
    color: var(--ps-ink);
    font-weight: 700;
    font-size: 1.05rem;
}
.ps-section::before { content: "☾"; color: var(--ps-moon); font-size: 0.9em; }
.ps-section::after {
    content: "";
    flex: 1;
    height: 1px;
    background: var(--ps-line);
}

/* 空状態 */
.ps-empty {
    border: 1px dashed var(--ps-line);
    border-radius: 12px;
    padding: 20px 14px;
    text-align: center;
    color: var(--ps-ink-dim);
    font-size: 0.9rem;
}

/* 充足度メーター（party 役割 / レシピ充足バー） */
.ps-meter {
    height: 6px;
    border-radius: 999px;
    background: var(--ps-line);
    overflow: hidden;
}
.ps-meter > span {
    display: block;
    height: 100%;
    border-radius: 999px;
    background: var(--ps-moon);
}

/* ===== スマホ最適化（旧 ui.py apply_mobile_css から移設） ===== */

.block-container {
    padding-top: 1.2rem;
    padding-bottom: 3rem;
    padding-left: 0.9rem;
    padding-right: 0.9rem;
}

[data-testid="stDataFrame"], [data-testid="stTable"] {
    -webkit-overflow-scrolling: touch;
}

@media (max-width: 640px) {
    [data-testid="stHorizontalBlock"] {
        flex-wrap: wrap;
        gap: 0.4rem 0.5rem;
    }
    [data-testid="stColumn"], [data-testid="column"] {
        flex: 1 1 7.5rem !important;
        min-width: 7.5rem !important;
    }

    /* スマホは全体的に一段締める（大きい文字は情報密度を殺す） */
    html, body, [data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li {
        font-size: 0.92rem;
        line-height: 1.55;
    }
    [data-testid="stCaptionContainer"] p { font-size: 0.75rem; }

    /* タッチターゲットは高さで確保しつつ文字は控えめに */
    .stButton button, .stFormSubmitButton button, .stDownloadButton button {
        min-height: 40px;
        font-size: 0.9rem;
    }
    input, textarea,
    [data-baseweb="select"] > div,
    [data-baseweb="input"] > div {
        min-height: 40px;
        font-size: 0.92rem !important;
    }

    [data-testid="stMetricValue"] { font-size: 1.2rem; }
    [data-testid="stMetricLabel"] { font-size: 0.72rem; }

    /* Streamlit本体のheading CSSより優先させるため !important */
    h1 { font-size: 1.3rem !important; }
    h2 { font-size: 1.15rem !important; }
    h3 { font-size: 1.0rem !important; }

    .ps-section { font-size: 0.95rem; }
    .ps-card .ps-card-title { font-size: 0.88rem; }
    .ps-tile .ps-tile-value { font-size: 1.15rem; }
    .block-container {
        padding-top: 0.8rem;
        padding-left: 0.7rem;
        padding-right: 0.7rem;
    }

    [data-testid="stTabs"] [data-baseweb="tab-list"] {
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
    }
}
</style>
"""


def apply_theme() -> None:
    """全ページ共通のテーマCSSを注入する。app.py から1回呼ぶ。"""
    st.markdown(_THEME_CSS, unsafe_allow_html=True)


# 旧APIの互換エイリアス（呼び出し側の移行が済んだら消す）
apply_mobile_css = apply_theme
