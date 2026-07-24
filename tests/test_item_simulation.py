from __future__ import annotations

import unittest

from utils.item_simulation import eligible_subskill_upgrades


def pokemon(*, level: int, subs: dict[int, str]) -> dict:
    row = {
        "id": 1,
        "species_name": "ピカチュウ",
        "current_level": level,
    }
    for unlock in (10, 25, 50, 75, 100):
        row[f"subskill_lv{unlock}"] = subs.get(unlock)
    return row


class SubSkillSeedEligibilityTest(unittest.TestCase):
    def test_upgrade_is_blocked_by_locked_higher_rank(self) -> None:
        row = pokemon(
            level=10,
            subs={10: "おてつだいスピードS", 75: "おてつだいスピードM"},
        )
        eligible, blocked = eligible_subskill_upgrades(row)
        self.assertEqual([], eligible)
        self.assertEqual("おてつだいスピードMを別枠に所持", blocked[0].reason)

    def test_only_unlocked_subskills_enter_the_lottery(self) -> None:
        row = pokemon(
            level=24,
            subs={
                10: "食材確率アップS",
                25: "スキル確率アップS",
            },
        )
        eligible, blocked = eligible_subskill_upgrades(row)
        self.assertEqual(["食材確率アップS"], [x.from_sub for x in eligible])
        self.assertEqual("Lv25で未解放", blocked[0].reason)

    def test_inventory_chain_can_free_the_lower_upgrade(self) -> None:
        row = pokemon(
            level=30,
            subs={
                10: "最大所持数アップS",
                25: "最大所持数アップM",
            },
        )
        eligible, blocked = eligible_subskill_upgrades(row)
        self.assertEqual(
            ["最大所持数アップM"],
            [x.from_sub for x in eligible],
        )
        self.assertEqual(
            "最大所持数アップMを別枠に所持",
            blocked[0].reason,
        )

        after = dict(row)
        after["subskill_lv25"] = "最大所持数アップL"
        eligible_after, _ = eligible_subskill_upgrades(after)
        self.assertEqual(
            ["最大所持数アップS"],
            [x.from_sub for x in eligible_after],
        )


if __name__ == "__main__":
    unittest.main()
