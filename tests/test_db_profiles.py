from __future__ import annotations

import unittest
from unittest.mock import patch

import db


class ProfileScopeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_profile = db._active_profile_id
        db.set_current_profile_id(7)

    def tearDown(self) -> None:
        db.set_current_profile_id(self._orig_profile)

    def test_setting_key_is_scoped_to_current_profile(self) -> None:
        seen: list[tuple] = []

        def fake_fetchone(sql: str, params: tuple = ()):
            seen.append(params)
            return {"value_json": '{"ok": true}'}

        with patch.object(db, "_fetchone", side_effect=fake_fetchone):
            self.assertEqual(db.get_setting("user.example"), {"ok": True})

        self.assertEqual(seen, [("profile:7:user.example",)])

    def test_insert_pokemon_attaches_current_profile(self) -> None:
        seen: dict[str, tuple] = {}

        def fake_execute(sql: str, params: tuple = (), returning: bool = False):
            seen["sql"] = sql
            seen["params"] = params
            return {"id": 99}

        with patch.object(db, "_execute", side_effect=fake_execute):
            new_id = db.insert_pokemon({"species_name": "ピカチュウ"})

        self.assertEqual(new_id, 99)
        self.assertIn("profile_id", seen["sql"])
        self.assertIn(7, seen["params"])

    def test_pin_verification_uses_hash_not_plain_pin(self) -> None:
        with patch.object(
            db,
            "_fetchone",
            return_value={"pin_hash": db._pin_hash("7028")},
        ):
            self.assertTrue(db.verify_profile_pin(1, "7028"))
            self.assertFalse(db.verify_profile_pin(1, "0000"))


if __name__ == "__main__":
    unittest.main()
