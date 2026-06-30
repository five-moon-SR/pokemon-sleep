# スマホで使う（クラウド公開）手順

ローカルの SQLite を Supabase(Postgres) に移し、Streamlit Community Cloud に載せて、
スマホのブラウザからいつでも使えるようにする手順。**1回やれば完了**。

---

## 全体像

- **ホスティング**: Streamlit Community Cloud（無料）
- **データ置き場**: Supabase Postgres の `pokesleep` スキーマ（無料・既存プロジェクトに同居）
- マスターデータ（きのみ・食材・レシピ等）は `data/*.json` 同梱のまま。引っ越し対象は
  `pokemon` / `party` / `user_settings` の3テーブルだけ。

---

## STEP 1. Supabase にテーブルとデータを入れる

1. Supabase ダッシュボード → 対象プロジェクト → 左メニュー **SQL Editor**
2. このフォルダの **`pokesleep_setup.sql`** を全部コピーして貼り付け → **Run**
   - これでスキーマ `pokesleep`・3テーブル作成＋既存データ（ポケ93/パーティ3/設定7）が入る
3. うまくいくと `pokesleep.pokemon` に93行入っているはず（Table Editor で確認可）

> `pokesleep_setup.sql` は個人データ入りなので `.gitignore` 済み（GitHubには上がらない）。

## STEP 2. 接続文字列(DB_URL)を用意

1. Supabase → プロジェクト上部の **Connect** ボタン
2. **Connection string → Session pooler** をコピー
3. `[YOUR-PASSWORD]` をプロジェクト作成時のDBパスワードに置き換える
   → これが `DB_URL`。形は↓
   ```
   postgresql://postgres.xxxx:本物のパスワード@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres
   ```

## STEP 3.（任意）ローカルでも新DBで動作確認

1. `pip install -r requirements.txt`
2. `.streamlit/secrets.toml.example` をコピーして `.streamlit/secrets.toml` を作り、`DB_URL` を入れる
3. `streamlit run app.py` → ローカルでSupabaseのデータが見えればOK
   （※これ以降ローカルも SQLite ではなく Supabase を見る）

## STEP 4. GitHub に push

1. GitHub で空のリポジトリを作る（private 推奨）
2. このフォルダを push
   ```
   git init
   git add .
   git commit -m "pokemon-sleep tool"
   git branch -M main
   git remote add origin https://github.com/<あなた>/<repo>.git
   git push -u origin main
   ```
   - `.gitignore` により `*.db` / `secrets.toml` / `pokesleep_setup.sql` は**上がらない**（安全）

## STEP 5. Streamlit Community Cloud でデプロイ

1. https://share.streamlit.io にGitHubでログイン
2. **Create app** → 対象リポジトリ・ブランチ `main`・Main file `app.py` を選択
3. **Advanced settings → Secrets** に↓を貼る（STEP2のDB_URL）
   ```toml
   DB_URL = "postgresql://postgres.xxxx:本物のパスワード@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres"
   ```
4. **Deploy** → 数分で `https://xxxx.streamlit.app` が発行される
5. そのURLをスマホのホーム画面に追加すればアプリっぽく使える

---

## 注意

- URLを知っていれば誰でも開ける（パスワード保護なし設定）。URLは共有しないこと。
- `DB_URL` は全DBアクセス権を持つ秘密情報。GitHubやチャットに貼らない。Secretsだけに置く。
- 以後データは Supabase が正本。ローカルの `pokemon_sleep.db` は使われなくなる
  （バックアップとして残しておくと安心）。
