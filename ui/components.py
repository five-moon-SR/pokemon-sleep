"""共通UIコンポーネント。HTML文字列を組み立てる純関数群。

描画は呼び出し側で st.html() / st.markdown(unsafe_allow_html=True) に渡す。
スタイルは ui/theme.py の .ps-* クラスと --ps-* トークンだけを使う
（インラインstyleは色をトークン参照する場合のみ許可）。
"""
from __future__ import annotations

from html import escape

from constants import get_subskill_rarity
from image_utils import berry_icon_url, ingredient_icon_url

# ランク → CSS変数（constants.DAIFUKU_RANKS と対応）
_RANK_VAR = {
    "増田": "--ps-rank-masuda",
    "SS": "--ps-rank-ss",
    "S": "--ps-rank-s",
    "A": "--ps-rank-a",
    "B": "--ps-rank-b",
    "C": "--ps-rank-c",
    "D": "--ps-rank-d",
}

# サブスキルレア度 → CSS変数
_SUB_VAR = {
    "gold": "--ps-sub-gold",
    "blue": "--ps-sub-blue",
    "white": "--ps-sub-white",
}

# 得意分野 → CSS変数
_SPECIALTY_VAR = {
    "きのみ": "--ps-sp-berry",
    "食材": "--ps-sp-food",
    "スキル": "--ps-sp-skill",
    "オール": "--ps-sp-all",
}


def rank_badge(rank: str | None, pct: float | None = None) -> str:
    """ランクの色バッジ。pct を渡すと「S · 92%」のように併記。"""
    if not rank:
        return ""
    var = _RANK_VAR.get(rank, "--ps-ink-dim")
    label = escape(rank)
    if pct is not None:
        label += f" · {pct:.0f}%"
    return (
        f'<span class="ps-badge" style="color: var({var}); '
        f'background: color-mix(in srgb, var({var}) 16%, transparent);">{label}</span>'
    )


def specialty_badge(specialty: str | None) -> str:
    """得意分野（きのみ/食材/スキル/オール）の色バッジ。"""
    if not specialty:
        return ""
    var = _SPECIALTY_VAR.get(specialty, "--ps-ink-dim")
    return (
        f'<span class="ps-badge" style="color: var({var}); '
        f'background: color-mix(in srgb, var({var}) 16%, transparent);">{escape(specialty)}</span>'
    )


def text_badge(label: str | None) -> str:
    """中立色のテキストバッジ（食材構成 AAA/ABB 等の属性表示用）。"""
    if not label:
        return ""
    return (
        f'<span class="ps-badge" style="color: var(--ps-ink-dim); '
        f'background: color-mix(in srgb, var(--ps-ink-dim) 14%, transparent); '
        f'letter-spacing: 0.08em;">{escape(label)}</span>'
    )


def subskill_chip(name: str | None) -> str:
    """サブスキルチップ。金/青/白のレア度ドット付き。"""
    if not name:
        return ""
    var = _SUB_VAR.get(get_subskill_rarity(name), "--ps-sub-white")
    return (
        f'<span class="ps-chip"><span class="ps-dot" style="background: var({var});"></span>'
        f"{escape(name)}</span>"
    )


def icon_chip(img_url: str | None, label: str, *, size: int = 20, title: str | None = None) -> str:
    """画像+テキストの1行チップ。画像が無ければテキストのみ。"""
    t = f' title="{escape(title)}"' if title else ""
    img = f'<img src="{img_url}" width="{size}">' if img_url else ""
    return f'<span class="ps-chip"{t}>{img}{escape(label)}</span>'


def berry_chip(berry_name: str | None, label: str | None = None) -> str:
    """きのみアイコンチップ。label 省略時はきのみ名を表示。"""
    if not berry_name:
        return ""
    return icon_chip(berry_icon_url(berry_name), label or berry_name, title=berry_name)


def ingredient_chip(name: str, qty: float | str | None = None) -> str:
    """食材アイコンチップ。qty があれば「×N」を添える。"""
    if qty is None:
        label = name
    elif isinstance(qty, str):
        label = f"{qty}"
    elif qty == int(qty):
        label = f"×{int(qty)}"
    else:
        label = f"×{qty:.1f}"
    return icon_chip(ingredient_icon_url(name), label, title=name)


def pokemon_card(
    *,
    title: str,
    subtitle: str | None = None,
    specialty: str | None = None,
    berry_name: str | None = None,
    img_url: str | None = None,
    badges: list[str] | None = None,
    chips: list[str] | None = None,
    footer: str | None = None,
    mini: bool = False,
) -> str:
    """個体/種族カード。

    title: ニックネームまたは種族名 / subtitle: 「種族名 · Lv25」等
    specialty: 左縁のアクセント色に使う / berry_name: 右上のきのみアイコン
    img_url: ポケモン本体画像（image_utils.pokemon_image_url）。右上に表示
    badges: rank_badge() 等のHTML / chips: subskill_chip() 等のHTML
    mini: 横スクロール行・スロット用の小型版
    """
    sp_var = _SPECIALTY_VAR.get(specialty or "", "--ps-line")
    berry = ""
    if img_url:
        berry += (
            f'<img src="{img_url}" width="{36 if mini else 56}" loading="lazy" '
            f'style="float:right; margin-left:6px;">'
        )
    if berry_name:
        url = berry_icon_url(berry_name)
        if url:
            berry += f'<img src="{url}" width="{20 if mini else 24}" title="{escape(berry_name)}" style="float:right; margin-left:4px;">'
    parts = [
        f'<div class="ps-card" style="border-left: 3px solid var({sp_var});'
        + ("padding:8px 10px; min-width:150px;" if mini else "")
        + '">',
        berry,
        f'<div class="ps-card-title">{escape(title)}</div>',
    ]
    if subtitle:
        parts.append(f'<div class="ps-card-sub">{escape(subtitle)}</div>')
    if badges:
        parts.append('<div style="margin-top:6px; display:flex; flex-wrap:wrap; gap:4px;">' + "".join(badges) + "</div>")
    if chips:
        parts.append('<div style="margin-top:6px; display:flex; flex-wrap:wrap; gap:4px;">' + "".join(chips) + "</div>")
    if footer:
        parts.append(f'<div class="ps-card-sub" style="margin-top:6px;">{footer}</div>')
    parts.append("</div>")
    return "".join(parts)


def card_grid(cards: list[str]) -> str:
    """カードをレスポンシブgridで並べる（スマホ2列）。"""
    return '<div class="ps-grid">' + "".join(cards) + "</div>"


def row_scroll(cards: list[str]) -> str:
    """ミニカードの横スクロール行。"""
    return '<div class="ps-row-scroll">' + "".join(cards) + "</div>"


def stat_tile(label: str, value: str, sub: str | None = None) -> str:
    """統計タイル1枚。stat_tiles() でまとめて描画する。"""
    s = f'<div class="ps-tile-sub">{escape(sub)}</div>' if sub else ""
    return (
        f'<div class="ps-tile"><div class="ps-tile-label">{escape(label)}</div>'
        f'<div class="ps-tile-value">{escape(value)}</div>{s}</div>'
    )


def stat_tiles(tiles: list[str]) -> str:
    """統計タイルの列（st.metric 横並びの代替。スマホで潰れない）。"""
    return '<div class="ps-tiles">' + "".join(tiles) + "</div>"


def section_header(title: str) -> str:
    """セクション見出し（細線+月アイコン様式）。"""
    return f'<div class="ps-section">{escape(title)}</div>'


def empty_state(msg: str) -> str:
    """空状態の表示。"""
    return f'<div class="ps-empty">{escape(msg)}</div>'


def meter(ratio: float) -> str:
    """0〜1の充足度メーター。"""
    pct = max(0.0, min(1.0, ratio)) * 100
    return f'<div class="ps-meter"><span style="width:{pct:.0f}%;"></span></div>'
