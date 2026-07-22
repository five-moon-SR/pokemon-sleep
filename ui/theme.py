"""テーマ「ひなたのリサーチノート」（ゲーム内UI寄せ）のCSSトークンと共通スタイル注入。

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

NIGHT = "#FBF6E3"      # クリーム地/アプリ背景
DUSK = "#FFFFFF"       # カード面
LINE = "#EADFC8"       # 罫線
INK = "#3B4460"        # 本文（ネイビー）
INK_DIM = "#8B93A8"    # キャプション
MOON = "#33BEE7"       # 本家シアン（公式スクショ実測ベース）
DEEP_BLUE = "#1C629E"  # 本家の数値強調の濃青

_THEME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Zen+Maru+Gothic:wght@400;500;700&display=swap');

:root {
    --ps-night: #FBF6E3;
    --ps-dusk: #FFFFFF;
    --ps-line: #EADFC8;
    --ps-ink: #3B4460;
    --ps-ink-dim: #8B93A8;
    --ps-moon: #33BEE7;
    --ps-deep: #1C629E;

    /* 機能色（ゲーム由来なので固定。白カード面用に濃いめ調整） */
    --ps-rank-masuda: #C99A1F;
    --ps-rank-ss: #E4526E;
    --ps-rank-s: #E0813C;
    --ps-rank-a: #C9A227;
    --ps-rank-b: #4FA352;
    --ps-rank-c: #3E87C7;
    --ps-rank-d: #8B93A8;
    --ps-sub-gold: #C99A1F;
    --ps-sub-blue: #3E87C7;
    --ps-sub-white: #8B93A8;
    --ps-sp-berry: #4FA352;
    --ps-sp-food: #E0813C;
    --ps-sp-skill: #3E87C7;
    --ps-sp-all: #9B6BC7;
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

/* ボタン文言は折り返さない（「編/集」のような縦割れ防止） */
.stButton button p, .stFormSubmitButton button p { white-space: nowrap; }

/* ===== 本家アプリ風「ぷっくり押し込み」ボタン =====
   ゲーム内の主ボタン: シアン青ピル + 下端の濃い縁。押すと沈む。 */
.stButton button, .stFormSubmitButton button, .stDownloadButton button {
    border-radius: 999px;
    font-weight: 700;
    min-height: 48px;
    transition: transform 0.05s ease, box-shadow 0.05s ease;
}
[data-testid^="stBaseButton-primary"] {
    background: #33BEE7;
    color: #FFFFFF;
    border: none;
    box-shadow: 0 4px 0 #1E96BC;
}
[data-testid^="stBaseButton-primary"]:hover {
    background: #4ECAEE;
    color: #FFFFFF;
}
[data-testid^="stBaseButton-primary"]:active {
    transform: translateY(3px);
    box-shadow: 0 1px 0 #1E96BC;
}
[data-testid^="stBaseButton-secondary"] {
    background: #FFFFFF;
    border: 1px solid #EADFC8;
    box-shadow: 0 4px 0 #E3D8BE;
}
[data-testid^="stBaseButton-secondary"]:active {
    transform: translateY(3px);
    box-shadow: 0 1px 0 #E3D8BE;
}

/* 日本語見出しは文節単位で折る（Chrome系のみ。他は通常折返し） */
h1, h2, h3, [data-testid="stMarkdownContainer"] strong { word-break: auto-phrase; }

/* 数値は桁が揃う字形で */
[data-testid="stMetricValue"], .ps-num { font-variant-numeric: tabular-nums; }

/* ===== 自作コンポーネント ===== */

/* カード: 白面 + やわらか影（ゲーム内メニューのふっくら感） */
.ps-card {
    background: var(--ps-dusk);
    border: 1px solid var(--ps-line);
    border-radius: 16px;
    padding: 12px;
    box-shadow: 0 2px 6px rgba(90, 70, 30, 0.10);
    color: var(--ps-ink);
}
.ps-card .ps-card-title {
    font-weight: 700;
    font-size: 0.95rem;
    line-height: 1.3;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.ps-card .ps-card-sub {
    color: var(--ps-ink-dim);
    font-size: 0.78rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
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
.ps-row-scroll > * { flex: 0 0 auto; max-width: 200px; }

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
    border: 1px solid #CDEFF7;
    background: #EAF9FC;  /* 本家の淡シアンピル */
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
    border-radius: 16px;
    padding: 10px 12px;
    box-shadow: 0 2px 6px rgba(90, 70, 30, 0.08);
}
.ps-tile .ps-tile-label { color: var(--ps-ink-dim); font-size: 0.72rem; }
.ps-tile .ps-tile-value {
    font-size: 1.35rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    line-height: 1.3;
    color: var(--ps-deep);  /* 本家の数字は濃青 */
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
.ps-section::before { content: "❋"; color: var(--ps-moon); font-size: 0.9em; }
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

/* 検索結果行(owned): モバイルの等幅カラム化を無効にして 行+開くボタン を1行維持 */
.st-key-owned_results [data-testid="stHorizontalBlock"] { flex-wrap: nowrap; }
.st-key-owned_results [data-testid="stColumn"]:first-child {
    flex: 1 1 auto !important;
    min-width: 0 !important;
}
.st-key-owned_results [data-testid="stColumn"]:last-child {
    flex: 0 0 4.2rem !important;
    min-width: 4.2rem !important;
}

/* ===== サイドバーナビ（タッチしやすく・読みやすく大きめ） ===== */

[data-testid="stSidebarNav"] a {
    padding: 0.55rem 0.75rem;
    border-radius: 10px;
    min-height: 44px;
}
[data-testid="stSidebarNav"] a p {
    font-size: 1.02rem;
    font-weight: 500;
}
[data-testid="stSidebarNav"] a span {
    font-size: 1.15rem;  /* 絵文字アイコン */
}
[data-testid="stSidebarNav"] a[aria-current="page"] {
    background: color-mix(in srgb, var(--ps-moon) 14%, transparent);
}
[data-testid="stSidebarNav"] a[aria-current="page"] p {
    color: var(--ps-moon);
    font-weight: 700;
}
[data-testid="stLogo"] {
    height: 3.2rem;
    margin: 0.4rem auto 0.2rem;
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
        min-height: 46px;
        font-size: 0.92rem;
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
        padding-top: 2.6rem;  /* Streamlitヘッダーの重なり分を確保 */
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
