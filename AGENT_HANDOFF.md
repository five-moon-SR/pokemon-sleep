# AGENT HANDOFF

- 2026-08-07 Codex: 食材ごとの攻略おすすめ表を [views/hand.py](/Users/nao/claude/private/pokemon-sleep/views/hand.py) に追加し、[utils/ingredient_coverage.py](/Users/nao/claude/private/pokemon-sleep/utils/ingredient_coverage.py) へおすすめマッピングと AAA クリア判定を実装。テスト [tests/test_ingredient_coverage.py](/Users/nao/claude/private/pokemon-sleep/tests/test_ingredient_coverage.py) を追加して `main` へ push 済み。検証は `py_compile` 成功、ローカル unittest は `psycopg2` 未導入で未実行。
- 2026-08-24 Codex: 実アプリのエラー調査。Streamlit 旧環境で `st.selectbox(filter_mode=...)` が落ちる可能性に対し、[app.py](/Users/nao/claude/private/pokemon-sleep/app.py) に未対応時だけ `filter_mode` を落とす互換パッチを追加。`python3 -m compileall -q app.py views utils ui` は成功。ローカル環境は `streamlit` / `psycopg2` / `pandas` 未導入のため実起動は未検証。
