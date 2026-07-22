# 2026-07-22〜23 v2大改修 + Wiki出典データ統合の記録

本番: https://pokemon-sleep-sr.streamlit.app/ （Streamlit Community Cloud、main push で自動デプロイ）

## 1. 新機能

### Wiki自動取り込み（scripts/fetch_wiki_master.py 新設）
- 出典: ポケモンスリープ攻略・検証Wiki（wikiwiki.jp/poke_sleep）
- 通常モード: 「ポケモンの一覧」HTML表をパース → pokemon_master.json と差分検出。dry-run既定、`--apply` で**新種族のみ**追記（既存は上書きしない）
- `--probs`: 「食材確率・スキル発動確率の推定値一覧」と突合。null穴埋めのみ自動、`--overwrite` 併用で既存値もWiki値へ統一
- 表記揺れは `WIKI_NAME_ALIASES` に追記して吸収する運用
- 注意: wikiwiki は curl だと Cloudflare チャレンジで弾かれる。スクリプトは urllib+UA で通っているが、手動調査は Playwright 経由が確実

### 編成自動最適化（utils/optimizer.py + party「🤖自動編成提案」）
- MemberStat 前計算（team_help_bonus は線形係数なので N=0 で前計算し後掛け）→ 軸別プレフィルタ → プール内 C(n,5) 全探索
- 評価は主料理/きのみ/スキルすべて「エナジー/日」の同一単位 − 役割未充足ペナルティ
- `python -m utils.optimizer` で素全探索との一致を自己検証

### 食材・育成戦略ページ（views/ingredients.py + utils/ingredient_coverage.py）
- 食材×担当ポケ逆引き / 狙いレシピ充足度（律速食材検出） / 育成優先度（Lv30/50/60マイルストーンの1Lvあたり改善効率） / 捕獲優先度（穴を埋める分のみ加点、最終進化に集約）
- 狙いレシピは user_settings KV `user.target_recipes` に永続化

## 2. UI「月夜のリサーチノート」
- .streamlit/config.toml（ダーク群青 #131A2A × 月光金 #F5D06F、Zen Maru Gothic）+ ui/ パッケージ（theme.py=CSSトークン、components.py=カード/バッジ/チップ純関数）
- ポケモン画像は **serebii.net/pokemonsleep/pokemon/<dex>.png（寝顔アート）をホットリンク**（image_utils.pokemon_image_url。ローカル保存なし）
- サイドバー: 公式ロゴ（st.logo）+ ナビ44pxタッチ + 選択中ページ月光金 + 日替わり「今日の寝顔」マスコット。favicon=プリン
- owned: カード（2列グリッド）/表 デュアルモード + 詳細 st.dialog。home: ダッシュボード化＋プロフィールdialog
- スマホ調整の教訓: 全要素への font-family 指定は Material アイコンの ligature を壊す（stIconMaterial に復元指定が必須）／モバイル等幅カラム化CSSはタイトル行の比率カラムを壊す

## 3. データ統合（Wiki出典で一本化）
- **新ポケ13種追加（228→241種）**: ラティオス / ナエトル・ヒコザル・ポッチャマ各系列 / チゴラス系 / ジジーロン
- **確率データ完全化**: null 21件（新種13+既存8）を穴埋め、既存60件もWiki推定値へ統一（`--probs --apply --overwrite`）→ 全241種 null ゼロ
- **進化7件追加（119→126件）**: ナエトル系(Lv14/40,Lv24/80)、ヒコザル系(Lv11/40,Lv27/80)、ポッチャマ系(Lv12/40,Lv27/80)、チゴラス→ガチゴラス(Lv29/80・日中限定)
- **レシピ**: 新レシピ0・全79件一致。null だった8件の Lv30/60 をWiki倍率（Lv30=×1.61 / Lv60=×3.03）で補完、誤記2点修正（ネロリ lv30=8155、めざめるパワー lv60=57755）
- **食材**: 新レシピ（みつあつめチョコワッフル等）由来の最大ボーナス系8点更新
- **監査で完全一致（変更なし）**: field(8) / subskill(17) / berry(18) / nature(25) / sleep_ribbon(4)

## 4. スキル評価の刷新（utils/skill_effects.py / evaluator.py）
- **バグ修正**: 「ばけのかわ(きのみバースト)」等の複合表記55種がカテゴリ解決に失敗しスキル評価0だった → `_main_skill_category` に括弧内カテゴリ/括弧内外スキル名の3段フォールバック。全241種解決を確認
- カテゴリ表を6件追加: おてつだいサポートS(6-12回) / おてつだいブースト / 料理チャンスS(大成功+4-10%) / 料理アシスト / 食材セレクトS / オールマイティー(アメ=週間エナジー外0換算)
- **SKILL_NAME_EFFECT_TABLE 新設**（master の main_skill 表記キー、エナジー直値、カテゴリ表より優先）: りゅうせいぐん(ドラゴン1種16-60個) / ばけのかわ / マイナス(なべ+げんき複合) / プラス / プレゼント / ナイトメア / たくわえる / いやしのはどう / みかづきのいのり / ほっぺすりすり
- 換算係数: きのみ1個=100 / 食材1個=144.8 / なべ容量1=100 / おてつだい1回=200 / げんき1%=80(エール系)・200(オール系) / 大成功1%=200
- 既存9カテゴリはWiki現行値と全一致（エナジーチャージ/げんきエールのページには**新旧2組の表**が並ぶ罠あり。現行=先に掲載されている方）
- テーブル未収録はゆびをふる/スキルコピーのみ（仕様スキル、係数フォールバック）

## 5. 既知の割り切り・残メモ
- りゅうせいぐんは「ドラゴン1種ボーナス」基準（編成5種で28-78まで上振れするが未考慮）
- プラスの追加食材列がWiki上2列（6-12と6-14）あり区別未確定 → 現状は基本食材のみ換算
- たくわえるは「たくわえ0回ではきだし」基準で過小評価気味
- iOS「ホーム画面に追加」アイコンは apple-touch-icon 非対応（Streamlit制約）で favicon 頼み
- 定期運用: `python scripts/fetch_wiki_master.py`（新種検出）と `--probs`（確率更新）を回すだけ
