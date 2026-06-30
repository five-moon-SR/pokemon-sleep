# ポケスリ管理ツール プロジェクト・ブリーフィング（ChatGPT 用）

最終更新: 2026-05-08
対応バージョン想定: ポケモンスリープ Ver.3.2.0 前後

---

## 0. このドキュメントの目的

本書は、開発者（齋藤尚旺）と Claude Code（実装担当 AI）が進めている **ポケモンスリープ管理ツール** に、ChatGPT（思考・設計支援担当 AI）が途中から合流するためのオンボーディング資料です。

齋藤さんが ChatGPT セッションの最初にこのファイルをアップロードし、その後の会話で「設計判断」「拡張アイデア出し」「数式の妥当性検証」「コード設計のセカンドオピニオン」などを依頼します。Claude Code はリポジトリへの読み書きと実装を担当します。

**役割分担：**
- **齋藤さん**：プロダクトオーナー兼ユーザー。ゲームの実プレイヤー。最終的な意思決定者。
- **Claude Code**：リポジトリ内のコードと記憶ファイル（メモリ）の読み書き、実装、軽い設計、ローカル動作検証。
- **ChatGPT**（あなた）：プロジェクト外の客観的な視点で、設計案の比較・拡張アイデア・数学的モデル化・トレードオフの整理を担う。コードは出力可だが、リポジトリへの書き込みは齋藤さん経由。

**やり取りの流れ：**
1. 齋藤さんが本書 + 個別の質問パケットを ChatGPT に貼る
2. ChatGPT が設計案・分析・選択肢を返す
3. 齋藤さんが回答を Claude Code に貼って、実装に落とす
4. 必要なら追加質問を再度 ChatGPT へ

---

## 1. プロジェクト概要

### 1.1 何のツールか

スマホゲーム **ポケモンスリープ** のプレイ補助ツール。Streamlit 製のローカル Web アプリ。
ユーザー1名（齋藤さん本人）の所持ポケモン管理・編成意思決定支援が目的。Web 公開はしていない。

### 1.2 主な機能（実装済み）

1. **個体登録**：所持ポケモンの種族・Lv・サブスキル・性格などを記録
2. **個体強化・進化**：レベリングや進化、メインスキルLvアップに伴う情報更新
3. **登録情報の修正**：誤入力の修正
4. **全ポケデータ閲覧**：マスター228種を絞り込み・並び替え
5. **所持ポケデータ閲覧**：所持個体一覧＋個体評価スコア
6. **データ集**：きのみ／食材／レシピ／メインスキル／サブスキル／フィールド／進化／性格／進化アイテム／おやすみリボン
7. **パーティー編成**：5体のパーティを保存・読込
8. **ホーム（ダッシュボード）**：直近編成のショートカット、所持統計、プレイヤープロフィール編集

### 1.3 ツールの方針（重要、変えない）

- **業務ではなく趣味プロジェクト**。本人が楽しめて続けられることが最優先。
- **スクレイピングしない**。ファンサイト（だいふく／Wiki／Game8 等）は規約上グレー or NG。データは手動でCSV/JSONに転記して自前リポジトリに持つ。
- **計算式で出せる値はJSONに保存しない**。`utils/` 配下の関数で都度計算（メンテ性のため）。
- 個体評価結果も外部APIではなく、ユーザーがチェッカーで判定→結果をコピペする運用（=「だいふくチェッカー」依存）。ただし 2026-05-08 時点で **だいふく依存を撤去中**、自前評価器（`utils/evaluator.py`）に移行している。

---

## 2. 開発体制と環境

- **OS**: Windows 11
- **言語**: Python 3.12
- **フレームワーク**: Streamlit 1.56 + pandas
- **DB**: SQLite (`pokemon_sleep.db`、自動生成、gitignore済み)
- **仮想環境**: `.venv/`（プロジェクト直下）
- **起動**:
  ```bash
  cd /c/Users/naosa/claude/private/game/pokemon-sleep
  .venv/Scripts/streamlit.exe run app.py
  # → http://localhost:8501
  ```

---

## 3. ディレクトリ構造

```
pokemon-sleep/
├ app.py                # st.navigation でマルチページ統合（21行）
├ db.py                 # SQLite CRUD ＋ JSON マスター読み込み（487行）
├ constants.py          # 評価器の重み・係数・サブスキル正規化（360行）
├ image_utils.py        # アイコン画像 URL ヘルパ（87行）
├ pokemon_sleep.db      # SQLite（gitignore）
├ data/                 # マスターJSON（11カテゴリ、ツールが読む唯一の真）
│  ├ pokemon_master.json   # ポケモン種族マスター 228件
│  ├ berry.json            # きのみ 18種
│  ├ ingredient.json       # 食材 19種
│  ├ field.json            # フィールド 8件
│  ├ recipe.json           # レシピ 79件（カレー24/サラダ27/デザート28）
│  ├ main_skill.json       # メインスキル 31件
│  ├ subskill.json         # サブスキル 17件（金7/青6/白4）
│  ├ evolution.json        # 進化系列 119件
│  ├ nature.json           # 性格 25種
│  ├ evolution_item.json   # 進化アイテム 14種
│  └ sleep_ribbon.json     # おやすみリボン 4段階
├ scripts/              # 各カテゴリ build_<C>.py / add_<C>.py
├ views/                # Streamlit 各ページ
│  ├ home.py               # ホーム（276行）
│  ├ register.py           # 個体登録（409行）
│  ├ update.py             # 個体強化・進化（422行）
│  ├ edit_record.py        # 登録情報の修正（470行）
│  ├ master.py             # 全ポケデータ（330行）
│  ├ owned.py              # 所持ポケデータ（687行、評価器を統合）
│  ├ data_collection.py    # データ集（560行）
│  └ party.py              # パーティー編成（513行）
├ utils/                # 計算ロジック
│  ├ berry_energy.py       # きのみ Lv別エナジー計算（109行）
│  ├ evaluator.py          # 個体評価チェッカー本体（555行）
│  ├ skill_effects.py      # メインスキル効果量テーブル（132行）
│  ├ sleep_ribbon.py       # おやすみリボン補正（127行）
│  └ play_context.py       # プレイヤープロフィール（108行、key-value 設定）
├ docs/                 # AI読み取り向けの仕様メモ
│  ├ chatgpt/             # ChatGPT 共有用ファイル置き場
│  │  ├ README.md
│  │  ├ 00_core_briefing.md   # 本書
│  │  └ updates/              # 日々の進捗ファイル
│  ├ data_inventory.md
│  └ eval_context/
│     ├ main_skill_notes.md      # 7主要スキルの仕様考察
│     ├ main_skill_effects.md    # 効果量テーブル圧縮版
│     ├ berry_energy_formula.md
│     ├ level_exp_notes.md
│     └ sleep_ribbon_notes.md
└ 貼り付けデータ集/      # サイトからの生テキスト（初期取り込み用、手で触らない）
   ├ ポケモンマスターデータ.txt
   ├ ポケモン確率データ.txt
   ├ きのみデータ.txt 〜 性格データ.txt
   ├ メインスキル/*.txt
   ├ きのみエナジー詳細データ.txt（検証用）
   ├ だいふく評価キャリブレーション.txt（評価器チューニング用）
   └ 画像集/                 # 各カテゴリのアイコン png
```

---

## 4. データ層

### 4.1 マスターJSON 共通構造

すべて `{ "records": [...], "_meta": { "count": N } }` 形式。
ソートキーはカテゴリごとに自然な順（例：ポケモン=dex_no、きのみ=タイプ順）。

各カテゴリには対応する `scripts/build_<C>.py`（生テキスト→JSON 一発生成）と `scripts/add_<C>.py`（1件追加・上書き、会話駆動）が存在。生テキストは初期アーカイブで、追加・更新は JSON 直更新で完結。

### 4.2 ポケモンマスター（228種）の主項目

```
dex_no / name / variant / specialty (berry/ingredient/skill/all) /
sleep_type / berry / ingredients (a/b/c × スロット位置順 qty) / main_skill /
food_drop_rate / main_skill_rate / base_assist_seconds など
```

- `specialty`: きのみとくい / 食材とくい / スキルとくい / オール
- 食材枠: a枠（Lv1解放）/ b枠（Lv30解放）/ c枠（Lv60解放）。各枠に「デフォルト食材」と qty list を保持。
- **`ingredients[X].qty` はスロット位置順**（Lv段階ではない）。a枠食材の qty list 長さ3 = 第一/第二/第三スロットでの qty、b枠は2 = 第二/第三、c枠は1 = 第三のみ。例: マメミート(a枠)`[2,5,7]` は「第一2/第二5/第三7」。Lv は枠の解放にだけ効き、qty には効かない。共有ヘルパは `utils.food_expectation.qty_at_slot()`。
- 確率データ未掲載8種は `food_drop_rate=null`（サンド・サンドパン・ミュウ・ラティアス・オンバット・オンバーン・アブリー・アブリボン）
- 形態違い（イーブイ進化先など）は `_meta.PROB_NAME_ALIASES` で吸収

### 4.3 個体DB（pokemon テーブル）

主カラム（マイグレーションを重ねた結果やや膨大）:
```
id / species_name / nickname / level / nature / evolution_stage /
main_skill_name / main_skill_level /
ingredient_1/2/3 /
subskill_lv10/25/50/75/100 /
daifuku_rank / daifuku_eval_type / daifuku_eval_percent / daifuku_evals_json (廃止) /
caught_level / current_level /
last_eval_species_total / last_eval_global_total / last_eval_version / last_eval_computed_at /
sleep_ribbon_stage /
note / created_at
```

- `level` カラムは「だいふく評価Lv（=60固定）」、`caught_level` は捕獲時、`current_level` は現在Lv。混在しているのは経緯。
- `daifuku_*` は段階的に撤去中（自前評価器に移行）。だいふく値は新規 NULL、既存値は温存。
- `sleep_ribbon_stage` は 0=未獲得、1〜4。

### 4.4 パーティ（party テーブル）

```
id / name / field_name /
recipe_categories[JSON] / candidate_recipes[JSON] / policy_tags[JSON] /
member_ids[JSON] / random_field_berries[JSON] /
note / created_at / updated_at
```

JSON カラムは sqlite では TEXT で保存し、`db.py` 側で自動 dumps/loads。

### 4.5 プレイヤープロフィール（user_settings テーブル、新規）

```
key (TEXT PK) / value_json (TEXT) / updated_at
```

key 命名規則: `user.<項目名>`。現在の項目（`utils/play_context.py` の PlayContext dataclass）:

| キー | 型 | デフォルト | 用途 |
|---|---|---|---|
| user.research_rank | int | 65 | リサーチランク |
| user.pot_capacity | int | 69 | カビゴンの鍋容量 |
| user.sleep_weekday_hours | float | 7.5 | 平日睡眠時間 |
| user.sleep_weekend_hours | float | 9.0 | 休日睡眠時間 |
| user.meal_breakfast | str "HH:MM" | "06:00" | 朝食時刻 |
| user.meal_lunch | str | "12:00" | 昼食時刻 |
| user.meal_dinner | str | "18:00" | 夕食時刻 |

`active_hours(weekend=False)` ヘルパ: `24 - 睡眠時間` を返す（おてつだい稼働時間）。

---

## 5. ページ構成（views/）

| ページ | 主機能 | 状態 |
|---|---|---|
| 🏠 ホーム | 直近編成ショートカット／プレイヤープロフィール編集／所持統計／最近登録した子 | 拡張中 |
| 📝 個体登録 | 種族選択→（旧：だいふく結果コピペ→）個体情報入力 | 自前評価器移行に伴いだいふく欄撤去済 |
| 🔧 個体強化・進化 | 検索→候補→1枚フォームで4項目編集（進化／現在Lv／メインスキルLv／サブスキル） | 完成 |
| ✏️ 登録情報の修正 | 誤入力の救済 | 完成 |
| 📚 全ポケデータ | 228種マスター閲覧、絞り込み多軸、所持ハイライト | 完成 |
| 📦 所持ポケデータ | 個体一覧、絞り込み、評価スコア（自前評価器を統合）、表示モード切替、ピン留め | 完成、評価軸追加が継続課題 |
| 🗂 データ集 | 10カテゴリ全部のタブ閲覧 | 完成 |
| ⚔ パーティー編成 | 4ブロック構成（前提／候補スコア順／編成5枠／保存・読込） | 骨組み実装、料理期待値が未精緻 |

---

## 6. 計算系ユーティリティ（utils/）

### 6.1 berry_energy.py（きのみエナジー）

```python
lv_energy(base_energy, lv)
  = round( max(base + (lv-1), base × 1.025^(lv-1)) )
final_display_energy(e, field_bonus, is_favorite)
  = ceil( e × (1+field_bonus) × (1+favorite_bonus) )   # 表示
final_actual_energy(e, field_bonus, is_favorite)
  = ceil( e × (1+field_bonus) ) × (1+favorite_bonus)   # 実値
```

- favorite_bonus は 1（=2倍）または 0
- 全19きのみ × Lv1/10/20/30/40/50/60 の Wiki検証値と±1で一致

### 6.2 sleep_ribbon.py（おやすみリボン補正）

4段階×進化残り回数(0/1/2)のテーブル。所持数+効果と時間短縮効果を持つ。

| 段階 | 累積時間 | 所持+ | 残0 | 残1 | 残2 |
|---:|---:|---:|---:|---:|---:|
| 1 | 200h  | +1 | 1.00 | 1.00 | 1.00 |
| 2 | 500h  | +3 | 1.00 | 0.95 | 0.89 |
| 3 | 1000h | +6 | 1.00 | 0.95 | 0.89 |
| 4 | 2000h | +8 | 1.00 | 0.88 | 0.75 |

時間倍率は **リボン × 性格 × サブスキル** の独立3軸乗算。
特殊：ピカチュウ(ハロウィン/ホリデー) は最終進化扱いで残0。

### 6.3 evaluator.py（個体評価チェッカー、詳細は §8）

### 6.4 skill_effects.py（メインスキル効果量）

メインスキルカテゴリごとに Lv→効果量を返すテーブル。
対応済：エナジーチャージS/M、ゆめのかけらゲットS、げんきオール/エール/チャージS、食材ゲットS、料理パワーアップS。
未対応はカテゴリ係数（`MAIN_SKILL_CATEGORY_COEF`）にフォールバック。

### 6.5 play_context.py（プレイヤープロフィール）

§4.5 参照。`load_play_context()` / `save_play_context(ctx)` / `ctx.active_hours(weekend=...)` / `ctx.with_updates(**kwargs)`。

---

## 7. 設計上の合意事項（ポリシー）

1. **データ運用**：スクレイピング禁止。手動転記でJSON化、自前リポジトリで完結。
2. **計算系**：式で出せる値はJSONに保存しない。`utils/` の関数で都度計算。
3. **マスター追加運用**：齋藤さんが「○○追加します」と言ったら、聞き取り→`add_<C>.py` 経由でJSON直更新。生テキストは触らない。
4. **AI ノート優先**：`docs/eval_context/*.md` は人間も読めるが「主な読み手はAI」想定で書く。生テキストの代わりにこれを参照する。
5. **段階的実装**：マスターも機能も「全部一気に揃える」のではなく必要時に段階追加。
6. **個人開発スコープ**：業務プロジェクトとは独立。継続性とおもしろさを優先、過剰なエンジニアリングはしない。

---

## 8. 個体評価チェッカー（v1.2、2026-05-08 時点）

ポケスリの「だいふくチェッカー」を参考にした、自前の個体値評価ロジック。所持85体に対して **だいふく評価との一致率 94.1%**（v1.0 では 68.2% から +25.9pt）。

### 8.1 評価式

```
species_total = α × species_berry + β × species_food + γ × species_skill + option_bonus
global_total  = α × global_berry  + β × global_food  + γ × global_skill  + option_bonus

α + β + γ = 1.0
score = max(0, min((個体理論値 / ベンチマーク) × 100, 100))
option_bonus は [-10, +30] にクリップ
```

- **species_score（種族内評価）**：「この個体を育てるべきか」の判断。主表示。
- **global_score（全体評価）**：「全所持の中での強さ」。補足。
- ベンチマーク = 軸ごとに別の理想性格＋最適サブスキル4枠＋Lv60＋メインスキルLv最大。`@lru_cache` で起動時1回計算。

### 8.2 ランク区分（DAIFUKU_RANK_EMOJI と整合）

```
SS≥95 / S≥85 / A≥70 / B≥50 / C≥30 / D<30
```

### 8.3 評価タイプ（9分類、実在は6）

得意分野（きのみ／食材／スキル）× メインスキルの flavor（berry／skill／pure）の3×3行列。
ただし「食材独立 flavor」が存在しないため ②④⑧ は不可達。実在 6 セル：
```
①(きのみ, pure/berry) ③(きのみ, skill)
⑤(食材, pure)         ⑥(食材, skill)
⑦(スキル, berry)      ⑨(スキル, pure/skill)
```

flavor 分類（`MAIN_SKILL_CATEGORY_FLAVOR`）:
- **berry**: きのみバースト（rate無関係で常時発動）
- **skill**: エナジーチャージS/M、ゆめのかけらゲットS、食材ゲットS／セレクトS、料理パワーアップS／チャンスS、料理アシスト
- **pure**: げんきエール/オール/チャージS、おてつだいサポート/ブースト、ゆびをふる、スキルコピー、オールマイティー

評価タイプ自動推定 `infer_eval_type(specialty, category, main_skill_rate)` は、`FLAVOR_RATE_THRESHOLD = 6.0`（メインスキル発動率6%以上で flavor が effective になる、berry と pure_only は閾値なし）を使う。

### 8.4 OPTION_BONUS_SUBSKILL（v1.1 確定、specialty 非依存）

だいふくキャリブ31体実測ベース：
| サブスキル | 値 |
|---|---|
| 睡眠EXPボーナス | +3.0 |
| げんき回復ボーナス | +2.5 |
| ゆめのかけらボーナス | 0.0 |
| リサーチEXPボーナス | 0.0 |
| おてつだいボーナス | +14.5 |
| スキルレベルアップS | +3.0（スキル特化時 +2 上乗せ） |
| スキルレベルアップM | +5.0（スキル特化時 +5 上乗せ） |

OPTION_BONUS_RANGE = (-10.0, +30.0)。性格は EXP↑=+3 / EXP↓=-5。

### 8.5 v1.2 追加（Lv別補正）

- `lv_energy()` を `_calc_berry_value()` から使用 → ポケモンLv別の獲得エナジーが反映
- おてつだい時間 Lv あたり 0.2% 線形短縮（Wiki公式準拠）を全 `_calc_*` に適用
- ~~食材qty を Lv段階で取得~~ → **2026-05-08 訂正**：qty list は Lv段階ではなく**スロット位置順**だった。評価器は各枠デフォルト食材を「その枠（元枠）で取った値」= `qty_list[0]` を使う形に修正済み（旧実装は a/b 枠で 1.75〜3.5倍 過大評価していた）。
- `evaluate_pokemon(p, eval_level=None)` で評価Lv指定可、`evaluate_at_levels(p, target_levels)` で複数Lv一括取得
- 所持ポケページの「📊評価」モードで現状/Lv50/Lv60 を3点並列表示
- ベンチマークは Lv60 固定

### 8.5b qty バグ修正の影響（2026-05-08 v1.3）

- 旧実装は `qty_list` を Lv段階（Lv1/Lv30/Lv60）と誤解釈し、Lv60個体で a枠qty=7、b枠qty=7、c枠qty=6 を使っていた。
- 正しくは「a枠デフォ食材を a枠で取る → qty_list[0] = 2（リザードンの場合）」。
- 結果として species_food / global_food が修正後はかなり下がる。所持85体ベースの精度（旧 94.1%）は再キャリブが必要（未実施）。

### 8.6 評価チェッカーの未着手・拡張候補

- フィールドボーナス／好物倍率の取り込み（party.py 側で扱う方針）
- 食材ロール特化評価（AAA/ABB集中型）
- 料理レシピ連動の評価軸（recipe_match_score）
- パーティ編成連動（週ボーナス対象きのみ持ち優遇など）
- プレイスタイル適合度（睡眠取れない期間→げんき回復系優先）
- 動的更新方針の見直し余地（100ms超えたらキャッシュ方式に切替判断）
- 派生スキル個別値の調査（ナイトメア / きのみジュース / みかづきのいのり等）
- 育成しやすさ軸（C2 EXP表 / C3 進化アイテム希少度 / C4 メインスキルのたね必要数）
- 厳選効率軸（C5 性格出現率 / C6 捕獲しやすさ）

---

## 9. 進行中・直近のロードマップ

### 9.1 着手中：ホーム画面拡張

2026-05-08 にプレイヤープロフィール編集ブロックを追加。ここから何を表示・編集できるべきかを ChatGPT と詰めたい。
- 候補：今週の推奨アクション／足りないデータ／KPI／よく使うショートカット／プロフィールに基づく稼働時間サマリ
- 削除：データ整備度ブロック（実装済→撤去）

### 9.2 食材期待値計算（v0.2 完了、2026-05-08）

`utils/food_expectation.py` に `expected_ingredients_per_day(pokemon, species, play_context, weekend=False) -> dict[str, float]` を実装。だいふく期待値チェッカーとの校正で誤差 0.4%（リザードン Lv60 サブなしAAA編成）。

**取り込み済み**：
- `food_drop_rate`、`base_assist_seconds`、Lv補正（0.2%/Lv 線形短縮）
- 性格補正（おてスピ↑↓、食材確率↑↓）、サブスキル（おてスピS/M、おてボ、食材確率S/M）
- おやすみリボン時間倍率（性格・サブと独立3軸乗算）
- **げんき変動の1日通算**：`utils/genki.py` に `DAILY_EFFECTIVE_ASSIST_SECONDS = 132,888秒` を定義し、おてつだい時間で割って1日のおてつだい回数を出す（だいふく互換式）。
- 食材枠の正しい qty 解釈（スロット位置基準、`qty_at_slot()` 経由）

**v0.3 候補**（未着手）：
- メインスキル「食材ゲットS / 食材セレクトS」の追加食材
- 最大所持数による取りこぼし（夜のキャップ）
- げんき回復系スキルの自身げんき回復ループ補正
- 候補レシピの必要食材との差分表示（views/party.py への組み込み）
- きのみ獲得期待値の同種関数
2. **きのみ獲得期待値**：今は `master.berry.qty` をそのまま合算。きのみの数S、好物倍率、フィールドボーナスを乗せる。
3. **カビゴンへの「足りない食材」差分表示**：候補レシピの必要食材 − 編成の食材獲得期待値。
4. **メインスキル名で絞り込み**するUI。

### 9.3 評価チェッカーの拡張（中期）

§8.6 参照。

### 9.4 既知の不一致・調査余地

- 評価チェッカー残5件の不一致：ピクシー（ゆびをふる skill flavor 仮説）、キュワワー（食材×team-buff）、マスカーニャ（入力ミス濃厚）
- 料理アイコン未配置（`貼り付けデータ集/画像集/料理/`）
- メインスキルアイコン未配置
- 新レシピ8件の Lv30/Lv60/なべ69/507 値が null

---

## 10. ChatGPT に依頼したい思考の種類

具体的に得意としてほしい領域：

1. **数式・統計モデル化**
   - 「食材獲得期待値の式をどう組むか」のような、確率と時間の絡む期待値計算の設計
   - サブスキル・性格・リボン・フィールドの乗算/加算ルールの整理
2. **設計の選択肢出し**
   - 「ホーム画面に何を置くべきか」のような open-ended な構造設計
   - 既存コードに対する代替アーキテクチャの叩き台
3. **ゲーム仕様の解釈支援**
   - PukiWiki 由来の生テキストや効果説明の言い換え・モデル化
   - 「この仕様だと何が言えるか」の論理整理
4. **トレードオフの言語化**
   - 「精度 vs 計算速度」「汎用性 vs 個別最適化」のような判断軸の整理
5. **第三者視点のセカンドオピニオン**
   - Claude Code が出した実装案について、別解や見落としがないかチェック

逆に **依頼しない** こと：
- リポジトリのファイル直接読み書き（ChatGPT からは見えない）
- ローカル環境での動作確認
- ポケモンスリープの最新仕様の Web 取得（古い情報・誤情報のリスク）

---

## 11. 用語集・略語

| 略語 | 意味 |
|---|---|
| ポケスリ | ポケモンスリープ |
| RR | リサーチランク（Ver.2.7時点で上限65、Lv上限と連動） |
| だいふく | だいふくチェッカー（外部の個体値評価サイト）。本ツールの当初の評価基準だが現在撤去中 |
| 得意（specialty） | ポケモンの食料収集の偏り。きのみ/食材/スキル/オール |
| flavor | メインスキルの「色」。berry/skill/pure の3分類（評価チェッカー独自概念） |
| 食材枠 a/b/c | 食材スロット1/2/3。Lv30/Lv60で順次解放 |
| AAA / ABB | 食材枠 a/b/c の選び方。同じ食材を集中させる構成 |
| エナチャ / エナチャS / エナチャM | エナジーチャージS/M（メインスキル） |
| メインスキルのたね | メインスキルLvを+1する道具 |
| サブスキルのたね | サブスキルのレアリティを上げる道具（S→M / M→L） |
| ★ サブスキル | サブスキルのたねでランクUP可能なもの（6件該当） |
| MAX サブスキル | 同系統で最大効果のもの（5件該当） |
| 好物 / 好みのきのみ | カビゴンが好むきのみ。エナジー2倍 |
| フィールドボーナス | フィールド固有のエナジー倍率 |
| なべ容量 | カビゴンに与えるカレー/サラダ/デザートの鍋の最大食材数。69 や 507 など段階あり |
| カビゴン | フィールドの主、料理を食べさせてエナジーを稼ぐ |
| ごちゃまぜ | 食材構成自由のレシピ |

---

## 12. 補遺：参照すべき外部資料

このリポジトリ内 docs に以下のAI向けノートがあります（ChatGPT には別途必要に応じて渡す想定）：

- `docs/eval_context/main_skill_notes.md` — 7主要メインスキルの仕様考察（性格補正・Lv依存・発動回数閾値など）
- `docs/eval_context/main_skill_effects.md` — 効果量テーブル圧縮版
- `docs/eval_context/berry_energy_formula.md` — きのみエナジー式の説明
- `docs/eval_context/sleep_ribbon_notes.md` — おやすみリボン仕様
- `docs/eval_context/level_exp_notes.md` — レベル/EXP/アメ仕様
- `docs/data_inventory.md` — データの棚卸し

---

## 13. 質問パケットのテンプレ

齋藤さんが ChatGPT に投げる際は、本書の上に以下のフォーマットで質問パケットを追加してください。

```
## いま判断したいこと
（1〜2行で）

## 現状の選択肢（あれば）
A. ...
B. ...

## 制約・前提
- ...
- ...

## ChatGPTに聞きたいこと
- ...
- ...

## 補足コンテキスト（あれば）
（関連する数式、コード断片、ゲーム仕様の引用など）
```

---

(End of briefing — 約12 KB / A4換算 6〜7ページ)
