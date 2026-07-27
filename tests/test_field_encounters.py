from __future__ import annotations

import json
import unittest
from pathlib import Path

from utils.field_encounters import (
    appears_in,
    field_species,
    has_data,
    recommend_fields,
    species_fields,
)

ROOT = Path(__file__).resolve().parent.parent
MASTER = json.loads((ROOT / "data" / "pokemon_master.json").read_text(encoding="utf-8"))["records"]
FIELDS = json.loads((ROOT / "data" / "field.json").read_text(encoding="utf-8"))["records"]


class FieldEncounterTest(unittest.TestCase):
    """フィールド別の出現ポケモン。"""

    def test_every_encounter_exists_in_master(self) -> None:
        valid = {m["species_name"] for m in MASTER}
        for f in FIELDS:
            for n in field_species(f["name"]):
                self.assertIn(n, valid, f"{f['name']} の {n} が master に無い")

    def test_known_pairs(self) -> None:
        """代表的な出現関係が取れていること。"""
        self.assertIn("カイリュー", field_species("アンバー渓谷"))
        self.assertIn("ゲンガー", field_species("ゴールド旧発電所"))
        self.assertIn("カメックス", field_species("シアンの砂浜"))

    def test_species_fields_is_reverse_of_field_species(self) -> None:
        for f in FIELDS:
            name = f["name"]
            for sp in list(field_species(name))[:5]:
                self.assertIn(name, species_fields(sp))

    def test_missing_field_is_undecidable_not_false(self) -> None:
        """出現データが無いフィールドは False ではなく None（＝絞り込まない）。"""
        self.assertFalse(has_data("ワカクサ本島 EX"))
        self.assertIsNone(appears_in("カイリュー", "ワカクサ本島 EX"))
        self.assertIsNone(appears_in("カイリュー", "存在しないマップ"))

    def test_appears_in_is_boolean_when_data_exists(self) -> None:
        self.assertTrue(appears_in("カイリュー", "アンバー渓谷"))
        self.assertFalse(appears_in("カイリュー", "ウノハナ雪原"))

    def test_recommend_fields_sorts_by_hit_count(self) -> None:
        wanted = {"カイリュー", "ゲンガー", "カメックス", "ツボツボ"}
        recs = recommend_fields(wanted)
        self.assertTrue(recs)
        counts = [n for _, n, _ in recs]
        self.assertEqual(counts, sorted(counts, reverse=True))
        for _, n, names in recs:
            self.assertEqual(n, len(names))
            self.assertTrue(set(names) <= wanted)

    def test_recommend_fields_ignores_unwanted(self) -> None:
        self.assertEqual(recommend_fields(set()), [])


if __name__ == "__main__":
    unittest.main()
