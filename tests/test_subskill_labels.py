from __future__ import annotations

import unittest

from constants import format_ingredient_short, format_subskill_short


class SubskillLabelTest(unittest.TestCase):
    def test_formats_known_subskills_for_ui(self) -> None:
        self.assertEqual(format_subskill_short("食材確率アップM"), "食確M")
        self.assertEqual(format_subskill_short("最大所持数アップL"), "所持L")
        self.assertEqual(format_subskill_short("おてつだいスピードS"), "おてスピS")
        self.assertEqual(format_subskill_short("おてつだいボーナス"), "おてボ")

    def test_normalizes_legacy_names_before_formatting(self) -> None:
        self.assertEqual(format_subskill_short("お手伝いスピードM"), "おてスピM")
        self.assertEqual(format_subskill_short("寝顔EXPボーナス"), "睡眠EXP")

    def test_keeps_unknown_names_readable(self) -> None:
        self.assertEqual(format_subskill_short("未知のサブ"), "未知のサブ")
        self.assertEqual(format_subskill_short(None), "")


class IngredientLabelTest(unittest.TestCase):
    def test_formats_known_ingredients_for_ui(self) -> None:
        self.assertEqual(format_ingredient_short("あじわいキノコ"), "キノコ")
        self.assertEqual(format_ingredient_short("ふといながねぎ"), "ネギ")
        self.assertEqual(format_ingredient_short("リラックスカカオ"), "カカオ")
        self.assertEqual(format_ingredient_short("ワカクサコーン"), "コーン")

    def test_keeps_unknown_ingredients_readable(self) -> None:
        self.assertEqual(format_ingredient_short("未知の食材"), "未知の食材")
        self.assertEqual(format_ingredient_short(None), "")


if __name__ == "__main__":
    unittest.main()
