from __future__ import annotations

import unittest
from unittest.mock import patch

import db


class FakeCursor:
    """発行された SQL を記録するだけの偽カーソル。"""

    def __init__(self, log: list[str]) -> None:
        self._log = log
        self._last = ""

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def execute(self, sql, params=()) -> None:
        self._last = " ".join(str(sql).split())
        self._log.append(self._last)

    def fetchall(self) -> list[dict]:
        if "FROM pokemon" in self._last:
            return [{"id": 1, "species_name": "プリン"}]
        return []

    def fetchone(self) -> dict | None:
        if "RETURNING id" in self._last:
            return {"id": 42}
        if "FROM pokemon" in self._last:
            return {"id": 1, "species_name": "プリン"}
        return None


class FakeConn:
    closed = 0

    def __init__(self, log: list[str]) -> None:
        self._log = log

    def cursor(self, **kwargs) -> FakeCursor:
        return FakeCursor(self._log)

    def commit(self) -> None:
        pass

    def close(self) -> None:
        self.closed = 1


class ConnectionTest(unittest.TestCase):
    """Supabase pooler 経由でも接続できる引数に保つ。"""

    def setUp(self) -> None:
        self._orig_conn = db._conn
        db._conn = None

    def tearDown(self) -> None:
        db._conn = self._orig_conn

    def test_search_path_is_set_after_connect_without_startup_options(self) -> None:
        sql: list[str] = []
        conn = FakeConn(sql)
        with (
            patch("db._get_db_url", return_value="postgresql://example"),
            patch("db.psycopg2.connect", return_value=conn) as connect,
        ):
            self.assertIs(db.get_connection(), conn)

        connect.assert_called_once_with("postgresql://example?sslmode=require", connect_timeout=10)
        self.assertEqual(sql, [f"set search_path to {db.SCHEMA}"])

    def test_existing_sslmode_is_preserved(self) -> None:
        self.assertEqual(
            db._db_url_for_connect("postgresql://example/db?sslmode=verify-full"),
            "postgresql://example/db?sslmode=verify-full",
        )

    def test_safe_db_error_redacts_credentials(self) -> None:
        msg = db.safe_db_error(
            RuntimeError(
                "could not connect to postgresql://alice:secret@example.supabase.co/db "
                "user=bob password=hunter2"
            )
        )
        self.assertIn("postgresql://<redacted>", msg)
        self.assertIn("user=<redacted>", msg)
        self.assertIn("password=<redacted>", msg)
        self.assertNotIn("secret", msg)
        self.assertNotIn("hunter2", msg)


class ReadCacheTest(unittest.TestCase):
    """Streamlit の再実行ごとに DB へ往復しないことを担保する。"""

    def setUp(self) -> None:
        self.sql: list[str] = []
        self._orig_get_connection = db.get_connection
        self._orig_initialized = db._initialized
        db.get_connection = lambda: FakeConn(self.sql)
        db._initialized = True
        db.clear_read_cache()

    def tearDown(self) -> None:
        db.get_connection = self._orig_get_connection
        db._initialized = self._orig_initialized
        db.clear_read_cache()

    def _selects(self) -> list[str]:
        return [s for s in self.sql if s.startswith("SELECT")]

    def test_repeated_reads_hit_the_database_once(self) -> None:
        for _ in range(10):
            db.list_pokemon()
        self.assertEqual(len(self._selects()), 1)

    def test_distinct_parameters_are_cached_separately(self) -> None:
        db.get_pokemon(1)
        db.get_pokemon(2)
        db.get_pokemon(1)
        self.assertEqual(len(self._selects()), 2)

    def test_write_invalidates_the_cache(self) -> None:
        db.list_pokemon()
        self.sql.clear()
        db.update_pokemon(1, level=30)
        db.list_pokemon()
        self.assertEqual(len(self._selects()), 1)

    def test_caller_mutation_does_not_poison_the_cache(self) -> None:
        rows = db.list_pokemon()
        rows[0]["species_name"] = "書き換えた"
        self.assertEqual(db.list_pokemon()[0]["species_name"], "プリン")

    def test_expired_entries_are_refetched(self) -> None:
        db.list_pokemon()
        db.list_pokemon()
        db._read_cache.update(
            {k: (t - db._CACHE_TTL_SEC - 1, v) for k, (t, v) in db._read_cache.items()}
        )
        db.list_pokemon()
        self.assertEqual(len(self._selects()), 2)


class InitDbOnceTest(unittest.TestCase):
    """DDL と移行が操作のたびに走らないことを担保する。"""

    def setUp(self) -> None:
        self.sql: list[str] = []
        self._orig_get_connection = db.get_connection
        self._orig_initialized = db._initialized
        db.get_connection = lambda: FakeConn(self.sql)
        db._initialized = False
        db.clear_read_cache()

    def tearDown(self) -> None:
        db.get_connection = self._orig_get_connection
        db._initialized = self._orig_initialized
        db.clear_read_cache()

    def test_second_call_issues_no_sql(self) -> None:
        db.init_db()
        after_first = len(self.sql)
        self.assertGreater(after_first, 0)
        db.init_db()
        db.init_db()
        self.assertEqual(len(self.sql), after_first)

    def test_force_reruns_the_migration(self) -> None:
        db.init_db()
        after_first = len(self.sql)
        db.init_db(force=True)
        self.assertGreater(len(self.sql), after_first)


if __name__ == "__main__":
    unittest.main()
