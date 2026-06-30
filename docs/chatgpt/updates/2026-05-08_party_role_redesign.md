# 2026-05-08 party.py 役割タブ刷新＋期待値結線＋team-buff

## 何があったか
パーティー編成ページ（views/party.py）を「全体スコア順の単一リスト」から「役割×目標数 / 今週のイベント補正 / 役割別タブ」を軸にした編成支援ツールへ全面刷新。食材・きのみの獲得期待値を精緻化し、team-buff (+5%/人) も反映。旧「方針タグ」UIは廃止。

## 実装・決定の中身

### 1. 食材獲得期待値の結線（ステップ1）
- `views/party.py` の `party_summary` / `score_pokemon` が `utils/food_expectation.expected_ingredients_per_day(p, master, ctx)` を使うように変更
- 性格・サブスキル・Lv・おやすみリボン補正が反映された **1日獲得個数（小数）** がベース
- `score_pokemon` の旧 `ingredient_per_match`（枠数×10点）→ `ingredient_per_unit`（期待値1個=2点）

### 2. きのみ獲得期待値モジュール追加（ステップ2）
- `utils/food_expectation.py` に **`expected_berry_per_day(pokemon, species, ctx, *, fav_berries, field_bonus, team_help_bonus_count)`** を新設
  - 1日のおてつだい回数 × `(1 - food_rate)` × qty(きのみの数S込み) で個数
  - `lv_energy(base, lv)` × `(1+field_bonus)` × 好物倍率(2x) で1個あたりエナジー
  - 戻り値: `{name, count, energy_per_unit, energy, is_favorite, qty_per_assist}`
- `evaluator._berry_energy_map` / `_berry_qty_mult` を流用（依存方向は既存と一致）
- `party_summary` のきのみ集計を `{count, energy, is_favorite}` 構造に拡張
- ③編成サマリの表示は **個数/日 ／ エナジー/日** 両方

### 3. ①「今週の前提」拡張（ステップ3a）
- **役割×目標数スライダー5本**（`recovery / energy_supply / pot_up / berry_focus / food_focus`）
- **プリセット6種**（カスタム／バランス／食材寄せ／きのみ全ツッパ／回復多め／鍋拡張型）→「📋 適用」で各スライダーに初期値投入のハイブリッド型
- **今週のイベント補正4項目**（`berry_2x / dish_2x / food_2x / all_energy_up`、複数選択可・空=補正なし週）
- DB拡張: `party` テーブルに `role_targets`(JSON dict) ・ `event_bonuses`(JSON list) カラム追加
- `db._PARTY_JSON_FIELDS` を `_PARTY_JSON_LIST_FIELDS` と `_PARTY_JSON_DICT_FIELDS` に分離（dict 型と list 型でデフォルト値を区別）

### 4. ②候補ポケを役割タブに刷新（ステップ3b）
- 5役割タブ。目標数 > 0 の役割が優先表示、全0なら全役割
- 役割別スコア関数:
  - `_role_score_skill(p, master, role, axis)`: メインスキル該当 + 性格軸 + メインスキルLv + サブスキル(スキル確率/Lv系)
  - `_role_score_berry`: 1日獲得エナジー / 100（フィールドボーナス・好物2x・きのみ2x週込み）
  - `_role_score_food`: 必要食材一致量×10 + 全食材量×1（× 食材2x週倍率）
- 役割スコアが None のポケは候補から自動除外（=該当しない役割タブには出てこない）
- `compute_role_scores(p, master, fav_set, event_set, needed_ings)` で5役割まとめて辞書返し

### 5. ③編成チェック拡充（ステップ3c）
- **役割充足度**プログレスバー（現在 / 目標）
- **レシピ達成進捗**: 律速食材で日数決定、`< 7 日` は「X.X 日」、それ以上は「X.X 週間」。不足食材があれば赤警告
- 旧 `_check_warnings` の policy_tags ベース警告は撤去 → 役割充足度ベースに統一

### 6. 方針タグUI削除
- `POLICY_TAGS` 定数 / `sel_policies` multiselect / `_check_warnings` / 旧 `policies_set` ロジックを撤去
- `MAIN_SKILL_TAG_MAP` は役割スコアで使うので残置
- 保存・読込から `policy_tags` キー削除（DBカラムは互換のため残置）

### 7. team-buff (+5%/人) 反映（v0.3 補正1の実装）
- `expected_ingredients_per_day` / `expected_berry_per_day` に **`team_help_bonus_count: int = 0`** 引数を追加
  - `speed × (1 + 0.05 × N)`（メモの v0.3 式準拠）
- `views/party.py` に `_team_help_bonus_count(member_ids)` 追加（編成全体の「おてつだいボーナス」装着数集計）
- `party_summary` がチーム全体で1回計算 → 各メンバーの期待値関数に同じ値を渡す
- ③編成サマリに `🤝 team-buff: 装着N人 → 全員のスピード ×1.XX` info バナー
- ②候補スコアは個別計算のまま（チームコンテキスト不明なので未反映、要望あれば①に「想定 team-buff 装着数」スライダー追加で解決可）
- スモークテスト: team_help_bonus_count=3 で食材・きのみとも **+15.0%** が線形に乗ることを確認

## 影響を受けるファイル
- `views/party.py`（大幅刷新）
- `utils/food_expectation.py`（`expected_berry_per_day` 追加、両関数に `team_help_bonus_count` 引数追加）
- `db.py`（party テーブルに `role_targets` / `event_bonuses` カラム追加、`_PARTY_JSON_DICT_FIELDS` 新設）

## 残課題・未確定事項
- **チームげんき回復補正**（v0.3 式 `food_mult × (1 + 0.00374 × チーム合計回復量/日)`）→ スキル発動回数×効果値の推定が必要。次回。
- **おてつだいサポートS／おてつだいブースト**（メインスキル）→ `utils/skill_effects.py` に効果値テーブル整備が前提。
- **げんき常に80** オプション（v0.3 式 `food_mult ×= 1.179`）→ ユーザー設定との結線が必要。
- ②候補スコアでも team-buff を仮定した数値を出したい場合は、①に「想定 team-buff 装着数」スライダーを追加する形で対応可能。
- 役割スコアの重みは仮置き（特に skill 系の `+5/Lv` や食材枠の必要食材一致重み `×10` など）。
- 1体が複数役割を兼任する場合、充足度カウントで二重カウントされる仕様（例：きのみ枠かつ回復枠を持つピジョットが両方+1）。仕様として残置。
- `policy_tags` カラム・きのみエナジーのフィールド固有ボーナス（`field_bonus=0` 固定）は今回未対応。

## ChatGPTに今後相談したいこと
- **役割スコアの重み付け**: 役割タブで上位に出すべき個体は実プレイ感とどれくらい合ってる？特に「回復枠でメインスキルLvより性格・サブスキルを重視するべきか」「食材枠で必要食材一致と全食材量の比率（現状 10:1）が妥当か」
- **チームげんき回復補正の式**: メモの v0.3 式 `food_mult × (1 + 0.00374 × self_recovery_per_day)` を **チーム合計回復量** に拡張する時、自身ループとの二重計算にならないか？
- **「げんき常に80」の扱い**: 個別ポケごとの設定 vs プレイヤー単位の設定 vs 編成単位のフラグ、どれが適切か。
