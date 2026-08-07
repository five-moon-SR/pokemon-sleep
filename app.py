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

db.init_db()
perf.mark("app.py: テーマ＋init_db")


def _profile_gate() -> bool:
    """4桁PINでプロフィールを選んでから本体へ進む。"""
    profiles = db.list_profiles()
    if not profiles:
        st.error("プロフィールがありません。DB初期化を確認してください。")
        return False

    active_id = st.session_state.get(db.PROFILE_SESSION_KEY)
    active = next((p for p in profiles if int(p["id"]) == int(active_id or 0)), None)

    with st.sidebar:
        st.markdown("### プロフィール")
        if active:
            db.set_current_profile_id(int(active["id"]))
            st.success(f"{active['name']} で使用中")
            if st.button("プロフィールを切り替える", use_container_width=True):
                st.session_state.pop(db.PROFILE_SESSION_KEY, None)
                st.rerun()
            return True

        options = {f"{p['name']}": int(p["id"]) for p in profiles}
        with st.form("profile_login_form"):
            selected_name = st.selectbox("ユーザー", list(options.keys()))
            pin = st.text_input("4桁PIN", type="password", max_chars=4)
            submitted = st.form_submit_button("入る", type="primary", use_container_width=True)
        if submitted:
            profile_id = options[selected_name]
            if db.verify_profile_pin(profile_id, pin):
                st.session_state[db.PROFILE_SESSION_KEY] = profile_id
                st.rerun()
            else:
                st.error("PINが違います")

        with st.expander("新しいプロフィールを作る"):
            with st.form("profile_create_form"):
                name = st.text_input("名前", placeholder="例: 友達A")
                new_pin = st.text_input("4桁PINを設定", type="password", max_chars=4)
                create = st.form_submit_button("作成", use_container_width=True)
            if create:
                try:
                    profile_id = db.create_profile(name, new_pin)
                    st.session_state[db.PROFILE_SESSION_KEY] = profile_id
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    st.html(
        """
        <section style="max-width:520px;margin:12vh auto 0;padding:20px;border-radius:18px;
        background:linear-gradient(135deg,#fff,#F0F8FF);border:1px solid var(--ps-line);
        box-shadow:0 10px 28px rgba(45,57,80,.10);">
          <div style="font-size:.8rem;font-weight:900;color:var(--ps-ink-dim);letter-spacing:.08em;">PROFILE LOCK</div>
          <h2 style="margin:.25rem 0 .45rem;">プロフィールを選んでPINを入力</h2>
          <p style="line-height:1.65;margin:0;color:var(--ps-ink);">
            登録ポケモン、編成、料理レベル、ユーザー設定はプロフィールごとに分かれます。
            既存データは「なお」に入っています。
          </p>
        </section>
        """
    )
    return False


if not _profile_gate():
    st.stop()

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
        # 料理レベルと長期ターゲットは同じ「料理を伸ばす」導線なので1ページにまとめる。
        st.Page("views/recipe_targets.py", title="料理", icon="🍽"),
        st.Page("views/events.py", title="イベント", icon="📅"),
        # 週エナジー以外の目的（かけら稼ぎ・リボン稼ぎ）で1日だけ組む編成
        st.Page("views/goal_party.py", title="目的別編成", icon="🌙"),
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
