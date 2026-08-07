from __future__ import annotations

import json
import unittest
from pathlib import Path

from utils.field_encounters import (
    appears_in,
    field_species,
    is_exclusive,
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
        self.assertIn("サーナイト", field_species("ワカクサ本島 EX"))

    def test_species_fields_is_reverse_of_field_species(self) -> None:
        for f in FIELDS:
            name = f["name"]
            for sp in list(field_species(name))[:5]:
                self.assertIn(name, species_fields(sp))

    def test_missing_field_is_undecidable_not_false(self) -> None:
        """出現データが無いフィールドは False ではなく None（＝絞り込まない）。"""
        self.assertIsNone(appears_in("カイリュー", "存在しないマップ"))

    def test_appears_in_is_boolean_when_data_exists(self) -> None:
        self.assertTrue(appears_in("カイリュー", "アンバー渓谷"))
        self.assertFalse(appears_in("カイリュー", "ウノハナ雪原"))

    def test_recommend_fields_prioritises_exclusives(self) -> None:
        """専属数を第1キー、該当数を第2キーに並ぶ。"""
        wanted = {"カイリュー", "ゲンガー", "カメックス", "ツボツボ"}
        recs = recommend_fields(wanted)
        self.assertTrue(recs)
        keys = [(-r["exclusive"], -r["total"]) for r in recs]
        self.assertEqual(keys, sorted(keys))
        for r in recs:
            self.assertEqual(r["total"], len(r["names"]))
            self.assertEqual(r["exclusive"], len(r["exclusive_names"]))
            self.assertTrue(set(r["names"]) <= wanted)
            self.assertTrue(set(r["exclusive_names"]) <= set(r["names"]))
            for n in r["exclusive_names"]:
                self.assertTrue(is_exclusive(n))

    def test_exclusive_flag_matches_field_count(self) -> None:
        for sp in ("カイリュー", "ゲンガー", "カメックス"):
            self.assertEqual(is_exclusive(sp), len(species_fields(sp)) == 1)

    def test_multi_map_species_exist(self) -> None:
        """複数マップに出る種が実在する（専属前提で組まないための固定）。"""
        multi = [sp for sp in {e for f in FIELDS for e in field_species(f["name"])}
                 if len(species_fields(sp)) > 1]
        self.assertTrue(multi, "複数マップに出る種が1つも無い＝取得漏れの疑い")

    def test_recommend_fields_ignores_unwanted(self) -> None:
        self.assertEqual(recommend_fields(set()), [])


if __name__ == "__main__":
    unittest.main()
