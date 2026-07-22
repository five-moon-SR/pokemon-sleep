"""テーマ・共通UIコンポーネントのパッケージ。

使い方:
    import ui
    ui.apply_theme()          # app.py で1回（テーマCSS注入）
    from ui import components # 各ビューでカード/バッジ等を組み立て
"""
from ui.theme import apply_mobile_css, apply_theme  # noqa: F401
