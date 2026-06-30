"""pokesleep_setup.sql を Supabase(Postgres) に流し込む一発移行スクリプト。

接続文字列の取得優先順:
  1. 環境変数 POKESLEEP_DB_URL / DB_URL
  2. .streamlit/secrets.toml の DB_URL

使い方:
  python scripts/apply_setup.py
"""
import os
import sys
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parent.parent
SQL_FILE = ROOT / "pokesleep_setup.sql"
SECRETS = ROOT / ".streamlit" / "secrets.toml"


def get_db_url() -> str:
    url = os.environ.get("POKESLEEP_DB_URL") or os.environ.get("DB_URL")
    if url:
        return url
    if SECRETS.exists():
        try:
            import tomllib

            data = tomllib.loads(SECRETS.read_text(encoding="utf-8"))
            if data.get("DB_URL"):
                return str(data["DB_URL"])
        except Exception as e:  # noqa: BLE001
            print(f"secrets.toml の読み込みに失敗: {e}")
    print(
        "DB_URL が見つかりません。環境変数 DB_URL か "
        ".streamlit/secrets.toml に設定してください。"
    )
    sys.exit(1)


def main() -> None:
    if not SQL_FILE.exists():
        print(f"{SQL_FILE} がありません。")
        sys.exit(1)

    sql = SQL_FILE.read_text(encoding="utf-8")
    url = get_db_url()

    conn = psycopg2.connect(url)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        print("pokesleep_setup.sql を適用しました。")

        with conn.cursor() as cur:
            for t in ("pokemon", "party", "user_settings"):
                cur.execute(f"SELECT count(*) FROM pokesleep.{t}")
                print(f"  pokesleep.{t}: {cur.fetchone()[0]} rows")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
