"""画像（アイコン）データを base64 データURL化するヘルパ。

`貼り付けデータ集/画像集/<カテゴリ>/<filename>` を読み、
`<img src="data:image/png;base64,...">` で使える形に変換する。
Streamlit の `st.column_config.ImageColumn` にもそのまま渡せる。

各 view から `from image_utils import berry_icon_url, ...` で利用する。
"""

from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st

import db

ROOT = Path(__file__).resolve().parent
BERRY_ICON_DIR = ROOT / "貼り付けデータ集" / "画像集" / "きのみ"
INGREDIENT_ICON_DIR = ROOT / "貼り付けデータ集" / "画像集" / "食材"
FIELD_ICON_DIR = ROOT / "貼り付けデータ集" / "画像集" / "フィールド"
RECIPE_ICON_DIR = ROOT / "貼り付けデータ集" / "画像集" / "料理"
MAIN_SKILL_ICON_DIR = ROOT / "貼り付けデータ集" / "画像集" / "メインスキル"
SLEEP_RIBBON_ICON_DIR = ROOT / "貼り付けデータ集" / "画像集" / "おやすみリボン"


@st.cache_data
def icon_data_url(folder_str: str, filename: str | None) -> str | None:
    """ローカルPNGを base64 データURLに変換。見つからなければ None。"""
    if not filename:
        return None
    path = Path(folder_str) / filename
    if not path.exists():
        return None
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


@st.cache_data
def _berry_icon_map() -> dict[str, str]:
    return {
        r["name"]: r["icon"]
        for r in db.list_all_berry_records()
        if r.get("icon")
    }


@st.cache_data
def _ingredient_icon_map() -> dict[str, str]:
    return {
        r["name"]: r["icon"]
        for r in db.list_all_ingredient_records()
        if r.get("icon")
    }


def berry_icon_url(berry_name: str | None) -> str | None:
    if not berry_name:
        return None
    return icon_data_url(str(BERRY_ICON_DIR), _berry_icon_map().get(berry_name))


def ingredient_icon_url(ingredient_name: str | None) -> str | None:
    if not ingredient_name:
        return None
    return icon_data_url(str(INGREDIENT_ICON_DIR), _ingredient_icon_map().get(ingredient_name))


@st.cache_data
def _sleep_ribbon_icon_map() -> dict[int, str]:
    return {
        int(r["stage"]): r["icon"]
        for r in db.list_all_sleep_ribbon_records()
        if r.get("icon")
    }


def sleep_ribbon_icon_url(stage: int | None) -> str | None:
    """段階番号(1〜4)に対応する画像のデータURLを返す。0/None なら None。

    画像ファイルは 貼り付けデータ集/画像集/おやすみリボン/ に置く想定。
    """
    if not stage or stage <= 0:
        return None
    icon = _sleep_ribbon_icon_map().get(int(stage))
    return icon_data_url(str(SLEEP_RIBBON_ICON_DIR), icon)
