# data/*.json 棚卸し（AI読み取り用索引）

最終更新: 2026-05-08

ポケスリツールで使う全マスターJSONの一覧。各ファイルの**件数・スキーマ・読み込みヘルパ・追加運用**を一望できるようにする。
全カテゴリ共通: `{ "records": [...], "_meta": { "count": N, ... } }` 構造（`game_pokemon_sleep_master_rules`）。

---

## 1. ポケモン種族マスター (`pokemon_master.json`)
- 件数: **228種**
- 主要フィールド: `dex_no` / `species_name` / `sleep_type` / `specialty` (きのみ/食材/スキル) / `berry` {name,qty} / `ingredients` {a/b/c → {name, qty:[第n枠位置順]}} / `main_skill` / `base_assist_seconds` / `food_drop_rate` / `main_skill_rate`
- `ingredients[X].qty` の解釈（重要）：**スロット位置順**であって Lv段階ではない。a枠食材の qty list 長さは3 (=第一/第二/第三スロット時の qty)、b枠は2 (=第二/第三)、c枠は1 (=第三のみ)。例: マメミート(a枠)`[2,5,7]` は「第一2/第二5/第三7」、あったかジンジャー(b枠)`[4,7]` は「第二4/第三7」、げきからハーブ(c枠)`[6]` は「第三6」。Lv は枠の解放（b=Lv30, c=Lv60）にだけ効き、qty には効かない。共有ヘルパは `utils.food_expectation.qty_at_slot(species, food_name, slot_idx)`。
- 読み込み: `db.list_all_master_records()` / `db.get_species_data(name)` / `db.list_species_names()`
- 追加: `add_pokemon` （11項目聞き取り、運用は `game_pokemon_sleep_add_workflow`）
- 特殊: 確率データ未掲載8種は `food_drop_rate=null`（サンド/サンドパン/ミュウ/ラティアス/オンバット/オンバーン/アブリー/アブリボン）

## 2. きのみ (`berry.json`)
- 件数: **18種**（18タイプ全て）
- 主要フィールド: `name` / `type` / `base_energy` / `preferred_field` / `icon` / `description`
- 読み込み: `db.list_all_berry_records()`
- 追加: `add_berry`（5項目、運用は `game_pokemon_sleep_add_berry`）
- Lv補正: JSON化せず `utils/berry_energy.lv_energy(base, lv)` で都度計算

## 3. 食材 (`ingredient.json`)
- 件数: **19種**
- 主要フィールド: `name` / `icon` / `base_energy` / `max_bonus_pct` / `max_bonus_recipes` (レシピ名リスト) / `effective_max_energy` / `dream_shard_price` / `description`
- 読み込み: `db.list_all_ingredient_records()`
- 追加: `add_ingredient`（運用は `game_pokemon_sleep_add_ingredient`）

## 4. フィールド (`field.json`)
- 件数: **8件**（通常7+EX1）
- 主要フィールド: `no` / `type` (normal/ex) / `name` / `icon` / `unlock_condition` / `favorite_berries_random` (bool) / `favorite_berries` [{name, type}] / `recommended_sp_min`
- 読み込み: `db.list_all_field_records()`
- 追加: `add_field`（運用は `game_pokemon_sleep_add_field`）
- 特殊: ワカクサ本島系は `favorite_berries_random=true` で配列空（週ごとランダム）

## 5. レシピ (`recipe.json`)
- 件数: **79件**（カレー24・サラダ27・デザート28）
- 主要フィールド: `no` / `category` (curry_stew/salad/dessert) / `name` / `icon` / `ingredients` / `total_ingredients` / `energy_lv1` / `energy_lv30` / `energy_lv60` / `energy_max_pot69` / `energy_max_pot507` / `description`
- 読み込み: `db.list_all_recipe_records()`
- 追加: `add_recipe`（運用は `game_pokemon_sleep_add_recipe`）
- 特殊: 新8件は Lv30以降 null。「ごちゃまぜ系」3種は ingredients=[]

## 6. メインスキル (`main_skill.json`)
- 件数: **31件**
- 主要フィールド: `category` / `category_icon` / `name` / `description` / `max_level`
- 読み込み: `db.list_all_main_skill_records()`
- 追加: `add_main_skill`
- Lv別効果量: 別途 `utils/skill_effects.py` に集約（対応カテゴリ: エナチャS/M、ゆめのかけらS、げんきオール/エール/チャージS、食材ゲットS、料理パワーアップS）

## 7. サブスキル (`subskill.json`) ★2026-05-08 数値カラム拡充
- 件数: **17件**（金7・青6・白4）
- 主要フィールド: `rarity` (gold/blue/white) / `name` / `category` / `effect_kind` (percent/count/multiplier) / `effect_value` (文字列) / `effect_value_num` (数値) / `scope` (self/team) / `description` / `is_max_rank` / `can_upgrade_with_seed`
- 読み込み: `db.list_all_subskill_records()`
- 追加: `add_subskill`（effect_kind/effect_value_num は文字列から自動推論）
- カテゴリ: speed / skill_trigger / ingredient_rate / berry_count / inventory / skill_level / sleep_exp / research_exp / energy_recovery / dream_shard / help_bonus

## 8. 進化 (`evolution.json`)
- 件数: **119件**（72系列＋分岐）
- 主要フィールド: `from` / `to` / `candy` / `conditions` {min_level?, items?[], time_of_day?, gender?}
- 読み込み: `db.list_all_evolution_records()` / `list_evolutions_from(name)` / `list_evolutions_to(name)` / `list_evolutions_using_item(item)`
- 追加: `add_evolution`（運用は `game_pokemon_sleep_add_evolution`）

## 9. 性格 (`nature.json`) ★2026-05-08 新規
- 件数: **25種**（無補正5＋▲▼20）
- 主要フィールド: `name` / `up` / `down` (speed/energy/ingredient/skill/exp) / `is_neutral`
- `_meta.modifiers`: 補正項目別の倍率（▲1.11/▼0.93 など）
- 読み込み: `db.list_all_nature_records()` / `db.get_nature_modifiers()` / `db.get_nature_record(name)`
- 追加: `add_nature`（25種固定なので使用頻度低）

## 10. 進化アイテム (`evolution_item.json`) ★2026-05-08 新規
- 件数: **14種**
- 主要フィールド: `name` / `icon` / `category` (connection/stone/seal/coat/claw/round) / `description`
- 読み込み: `db.list_all_evolution_item_records()` / `db.list_evolutions_using_item(name)` (evolution.json逆引き)
- 追加: `add_evolution_item`

---

## 補助モジュール（JSONではないがデータ的位置づけ）
- `utils/berry_energy.py` — きのみLv別エナジー計算式（Wiki検証データ133点で±1以内）
- `utils/skill_effects.py` — メインスキルLv別効果量＋エナジー換算（ENERGY_PER_UNIT）
- `utils/evaluator.py` — 個体評価チェッカー v1.1
- `docs/eval_context/main_skill_notes.md` — メインスキル仕様まとめ
- `docs/eval_context/berry_energy_formula.md` — きのみエナジー式と検証データ
- `docs/eval_context/level_exp_notes.md` — Lv/EXP/アメ仕様まとめ

## 構造的なメモ
- すべて `{records, _meta}` 構造に揃っている（マスター表共通ルール）
- `_meta.count` が真値（書き込み時に更新）
- 計算で出せる値（Lv別エナジー・効率比較）は **JSON に持たない** （`game_pokemon_sleep_calc_policy`）
- 表記揺れ吸収: サブスキル名は `constants.normalize_subskill_name()` で旧表記→新表記に変換
- ポケモンマスターは `dex_no` 順、サブスキルは rarity (gold→blue→white) 順、進化はWebFetch順
