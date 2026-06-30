import streamlit as st

import db

st.set_page_config(page_title="ポケスリ管理", page_icon="🌙", layout="wide")

db.init_db()

pages = [
    st.Page("views/home.py", title="ホーム", icon="🏠", default=True),
    st.Page("views/register.py", title="個体登録", icon="📝"),
    st.Page("views/update.py", title="個体強化・進化", icon="🔧"),
    st.Page("views/edit_record.py", title="登録情報の修正", icon="✏️"),
    st.Page("views/master.py", title="全ポケデータ", icon="📚"),
    st.Page("views/owned.py", title="所持ポケデータ", icon="📦"),
    st.Page("views/data_collection.py", title="データ集", icon="🗂"),
    st.Page("views/party.py", title="パーティー編成", icon="⚔"),
    st.Page("views/guide.py", title="使い方", icon="📖"),
]

nav = st.navigation(pages)
nav.run()
