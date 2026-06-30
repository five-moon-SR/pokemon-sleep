# 2026-05-08 ホーム画面拡張＋プレイヤープロフィール土台

## 何があったか
1. 前夜（01:33〜01:34）に着手していたプレイヤープロフィール土台（`utils/play_context.py` + `db.user_settings`）の存在を再確認・メモリ化。
2. ホーム画面（`views/home.py`）にプロフィール編集ブロックを追加し、データ整備度ブロックを撤去。
3. ChatGPT との橋渡し運用を開始。コア・ブリーフィング（`docs/chatgpt/00_core_briefing.md`）を整備。

## 実装・決定の中身

### プレイヤープロフィール土台（既存、5/8 朝のセッションで確認）
- DB: `user_settings (key TEXT PK, value_json TEXT, updated_at TIMESTAMP)` テーブル
- `db.py`: `get_setting(key, default)` / `set_setting(key, value)` / `get_all_settings()`（JSON encode/decode 込み・upsert）
- `utils/play_context.py`:
  - `PlayContext` dataclass（frozen, 7項目）
  - `KEY_*` 定数（`user.<項目名>` 命名規則）
  - `DEFAULTS` 辞書
  - `load_play_context()` / `save_play_context(ctx)`
  - `active_hours(weekend=False)` ヘルパ：`24 - 睡眠時間` を返す
  - `with_updates(**kwargs)`、`to_settings_dict()`、`meal_times` プロパティ

7項目：
| キー | 型 | デフォルト |
|---|---|---|
| `user.research_rank` | int | 65 |
| `user.pot_capacity` | int | 69 |
| `user.sleep_weekday_hours` | float | 7.5 |
| `user.sleep_weekend_hours` | float | 9.0 |
| `user.meal_breakfast` | str "HH:MM" | "06:00" |
| `user.meal_lunch` | str | "12:00" |
| `user.meal_dinner` | str | "18:00" |

### ホーム画面の改修（`views/home.py`）
**追加**：🧑 プレイヤープロフィールブロック（直近編成と所持ポケモン統計の間）
- `st.form` で7項目を一括編集
  - 上段4列：リサーチランク／鍋容量／平日睡眠（0〜14h, step=0.5）／休日睡眠
  - 下段3列：朝・昼・晩（time_input、15分刻み）
- 💾 保存ボタン → `PlayContext` を組み立てて `save_play_context()` → `st.rerun()`
- フォーム下にサマリ：「⏰ おてつだい時間 — 平日 ◯h / 休日 ◯h」（`active_hours()` の派生）

**削除**：③ データ整備度ブロック（`DATA_TARGETS` dict、`_progress` 関数も含めて）

**保持**：直近編成 / 所持ポケモン統計 / 最近登録した子

### ChatGPT 橋渡し運用の開始
- `docs/chatgpt/00_core_briefing.md` を新設（13セクション、A4 6〜7ページ相当）
- `docs/chatgpt/updates/` で日々の差分を蓄積
- `docs/chatgpt/README.md` に運用方法
- `memory/collab_chatgpt_bridge.md` でこのコラボ自体の運用ルールを保存

## 残課題・未確定事項

### プレイヤープロフィール
- 「meal_breakfast/lunch/dinner」の解釈が未確定
  - 候補A：「カビゴンが食事するタイミング = その時刻までに鍋を満たす」
  - 候補B：「プレイヤーが鍋を仕込む時刻」
  - 候補C：単に1日の生活リズムの目安
- `pot_capacity` のデフォルト 69 は Wiki 中間値。齋藤さん本人の実値（本人入力待ち）
- 平日／休日睡眠以外の「不規則な日」をどう扱うか未定

### ホーム拡張
- プロフィール編集のほか、ホームに何を置くべきかが open question
- ChatGPT に最初に投げる予定のトピック：「ホーム画面に何を追加すると意思決定が捗るか」

## ChatGPTに今後相談したいこと

1. **ホーム画面拡張のアイデア出し**（次のターン候補）
   - プレイヤープロフィールが入ったあとの、ホームのあるべき姿
   - 「今週の推奨アクション」を出すなら何を入力にすべきか
   - 朝晩でホーム表示を変えるべきか（朝＝今日の予定、夜＝今日の振り返り、的な）
2. **パーティ料理期待値の数式設計**（中期）
   - `food_drop_rate` × `base_assist_seconds` × サブスキル × 性格 × リボン × `active_hours` をどう組み合わせるか
3. **`meal_*` 時刻の意味づけ**（小ネタ）
   - ゲーム上の食事タイミング仕様と PlayContext の項目をどう接続するか
