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
)

ui.apply_theme()

st.logo(
    "https://www.serebii.net/pokemonsleep/logo.png",
    size="large",
    link="https://pokemon-sleep-sr.streamlit.app/",
)

db.init_db()
perf.mark("app.py: テーマ＋init_db")

# ナビは「ユーザーの目的」でグループ化する（ui_design_policy.md）。
# 並びは実際の運用フローの順: ホーム → 今週の手持ちを決める → 箱を見る →
# 足りないものを捕りに行く → 資料を引く。
pages = {
    # ホームだけはカテゴリを付けず最上段に置く（毎回ここから始まるため）
    "": [
        st.Page("views/home.py", title="ホーム", icon="🏠", default=True),
    ],
    "てもち": [
        st.Page("views/party.py", title="編成", icon="🧭"),
        st.Page("views/items.py", title="育成・アイテム", icon="🎁"),
    ],
    "ボックス": [
        st.Page("views/hand.py", title="役割", icon="🧩"),
        st.Page("views/owned.py", title="所持ポケデータ", icon="📦"),
    ],
    "ほかく": [
        # 「何を狙うか」は捕獲の前の話なので、登録・修正（捕獲後の作業）より先に置く
        st.Page("views/catch_policy.py", title="強ポケ捕獲方針", icon="🏅"),
        st.Page("views/register.py", title="個体登録", icon="📝"),
        st.Page("views/update.py", title="個体強化・進化", icon="🔧"),
        st.Page("views/edit_record.py", title="登録情報の修正", icon="✏️"),
    ],
    "データ・ガイド": [
        st.Page("views/master.py", title="全ポケデータ", icon="📚"),
        st.Page("views/data_collection.py", title="データ集", icon="🗂"),
        st.Page("views/guide.py", title="使い方", icon="📖"),
    ],
}

nav = st.navigation(pages)

# サイドバー下部の「今日の寝顔」— 所持ポケから日替わりで1匹
with st.sidebar:
    try:
        from datetime import date

        from image_utils import pokemon_image_url

        owned_species = sorted({r["species_name"] for r in db.list_pokemon()})
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
