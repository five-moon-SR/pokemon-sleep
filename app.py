import inspect

import streamlit as st

import db
import ui
from utils import perf

perf.start()  # ?perf=1 のときだけ働く区間計測

# page_icon: プリンの寝顔（ブラウザタブ/ホーム画面追加時のアイコン）
st.set_page_config(
    page_title="ポケスリ管理",
    page_icon="https://www.serebii.net/pokemonsleep/pokemon/39.png",
    layout="wide",
    # initial_sidebar_state は既定の "auto" のまま。
    # "expanded" にするとスマホでは毎回サイドバーが本文を覆ってしまい、
    # 開くより閉じる手間の方が増える。開きにくさは展開ボタンを46pxに
    # 広げること（ui/theme.py）で解いている。
)

ui.apply_theme()


def _patch_streamlit_compat() -> None:
    """古い Streamlit 環境でも、新しめの widget 引数でアプリ全体を落とさない。"""
    if "filter_mode" in inspect.signature(st.selectbox).parameters:
        return

    original_selectbox = st.selectbox

    def selectbox_compat(*args, **kwargs):
        kwargs.pop("filter_mode", None)
        return original_selectbox(*args, **kwargs)

    st.selectbox = selectbox_compat


_patch_streamlit_compat()

# ── 起動時の自己診断 ─────────────────────────────────────────────────
# 本番で views/home.py の `from image_utils import ...` が ImportError になり、
# しかも Cloud はエラー本文を伏字にするため原因が読めなかった。
# ここで先に取り込んで、失敗したら**伏せられない形**で中身を出す。
# （image_utils は streamlit 内部の streamlit.elements.lib.image_utils と
#   同名なので、別物を掴んでいないかも併せて確認する）
try:
    import image_utils as _img

    _missing = [
        n for n in (
            "berry_icon_url", "ingredient_icon_url", "field_icon_url",
            "recipe_icon_url", "sleep_ribbon_icon_url", "pokemon_image_url",
        )
        if not hasattr(_img, n)
    ]
    if _missing:
        st.error(
            "image_utils の読み込みがおかしい。\n\n"
            f"- 足りない名前: {_missing}\n"
            f"- 実際に読んだファイル: `{getattr(_img, '__file__', '不明')}`\n"
            f"- 持っている名前: {[n for n in dir(_img) if not n.startswith('_')]}"
        )
        st.stop()
except ImportError as exc:  # 取り込み自体が落ちた場合の生メッセージ
    st.error(f"image_utils を取り込めない: {type(exc).__name__}: {exc}")
    st.stop()

st.logo(
    "https://www.serebii.net/pokemonsleep/logo.png",
    size="large",
    link="https://pokemon-sleep-sr.streamlit.app/",
)

try:
    db.init_db()
except Exception as exc:
    st.error(
        "DB接続でエラーが出ています。\n\n"
        f"`{db.safe_db_error(exc)}`\n\n"
        "Streamlit Cloud の Secrets に入っている `DB_URL` と、Supabase 側の接続先/SSL設定を確認してください。"
    )
    st.stop()
perf.mark("app.py: テーマ＋init_db")


# ログイン（プロフィール選択＋4桁PIN）は廃止した。
# 使うのは Nao 一人なので、db.init_db() が既定プロフィールを現在プロフィールとして
# 固定する（db.set_current_profile_id）。profiles テーブルと profile_id 列は
# 残してあるので、必要になればここにゲートを戻すだけで復活できる。

# ナビは「ユーザーの目的」でグループ化する（ui_design_policy.md）。
# 公式寄りの語彙で、ホーム → チームを決める → 料理を伸ばす →
# 仲間を探す → ボックスを見る → 資料を引く、の順にする。
pages = {
    # ホームだけはカテゴリを付けず最上段に置く（毎回ここから始まるため）
    "": [
        st.Page("views/home.py", title="ホーム", icon="🏠", default=True),
    ],
    "おてつだいチーム": [
        st.Page("views/party.py", title="チーム編成", icon="🧭"),
        st.Page("views/items.py", title="育成・どうぐ", icon="🎁"),
        # 週エナジー以外の目的（かけら稼ぎ・リボン稼ぎ）で1日だけ組むチーム
        st.Page("views/goal_party.py", title="目的別チーム", icon="🌙"),
    ],
    "料理メニュー": [
        # 料理レベルと長期ターゲットは同じ「料理を伸ばす」導線なので1ページにまとめる。
        st.Page("views/recipe_targets.py", title="料理メニュー", icon="🍽"),
    ],
    "仲間さがし": [
        # 「何を狙うか」は仲間にする前の話なので、登録・修正（仲間になった後の作業）より先に置く
        st.Page("views/catch_policy.py", title="注目ポケモン", icon="🏅"),
        st.Page("views/register.py", title="仲間登録", icon="📝"),
        st.Page("views/update.py", title="育成・進化", icon="🔧"),
        st.Page("views/edit_record.py", title="登録情報の修正", icon="✏️"),
    ],
    "ポケモンボックス": [
        st.Page("views/owned.py", title="ポケモンボックス", icon="📦"),
        st.Page("views/hand.py", title="ボックス診断", icon="🧩"),
    ],
    "リサーチノート": [
        st.Page("views/events.py", title="イベント", icon="📅"),
        st.Page("views/master.py", title="ポケモン図鑑", icon="📚"),
        st.Page("views/data_collection.py", title="データノート", icon="🗂"),
        st.Page("views/guide.py", title="はじめてガイド", icon="📖"),
    ],
}

nav = st.navigation(pages)

# サイドバー下部の「今日の寝顔」— 所持ポケから日替わりで1匹
with st.sidebar:
    try:
        from datetime import date

        pokemon_image_url = _img.pokemon_image_url

        # 飾りのために毎リラン所持一覧を引いていたので、日付ごとにキャッシュする
        @st.cache_data(show_spinner=False, ttl=3600)
        def _mascot_species(day: int) -> list[str]:
            return sorted({r["species_name"] for r in db.list_pokemon()})

        owned_species = _mascot_species(date.today().toordinal())
        if owned_species:
            pick = owned_species[date.today().toordinal() % len(owned_species)]
            url = pokemon_image_url(pick)
            if url:
                st.markdown(
                    f'<div style="text-align:center; margin-top:1.2rem; opacity:0.9;">'
                    f'<img src="{url}" width="96" loading="lazy"><br>'
                    f'<span style="font-size:0.75rem; color:var(--ps-ink-dim);">'
                    f"今日の寝顔: {pick}</span></div>",
                    unsafe_allow_html=True,
                )
    except Exception:
        pass  # マスコットは飾りなので何があってもアプリを止めない

perf.mark("app.py: ナビ構築＋サイドバー")

nav.run()
