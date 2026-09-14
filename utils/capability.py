"""個体の「素の能力」（1日あたり）を1箇所で出す層。

各編成画面がそれぞれ期待値を計算し直すと、必ずどこかがズレるか二重計上する。
ここで出すのは **状況に依らない素の値** だけ:

  - おてつだい回数 / 日
  - きのみ: 種類・個数/日・1個あたりエナジー（好物倍率やフィールド補正は乗せない）
  - 食材: {名前: 個数/日}（おてつだい由来 + メインスキル由来の内訳つき）
  - メインスキル: 発動回数/日・カテゴリ・マスタの yield 宣言・エナジー/日

好物きのみ×2、フィールドボーナス、週イベント、げんき回復によるチーム稼働ブースト
といった **状況依存の倍率は呼び出し側（編成画面）で掛ける**。

「そのスキルが素で何をどれだけ生むか」は data/main_skill.json の `ingredient_yield`
などの宣言が正本で、コードにスキル名は埋めない。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from utils.food_expectation import (
    expected_berry_per_day,
    expected_ingredients_per_day,
    expected_skill_activations_per_day,
    expected_skill_ingredients_per_day,
    has_skill_ingredients,
)
from utils.play_context import PlayContext
from utils.skill_expectation import expected_skill_energy_per_day


@dataclass(frozen=True)
class Capability:
    """個体の素の能力（1日あたり）。倍率は掛かっていない。"""

    berry_name: str | None
    berry_count_per_day: float
    berry_energy_per_unit: float
    # おてつだい由来 + スキル由来の合算（画面が普通に使うのはこちら）
    ingredients_per_day: dict[str, float] = field(default_factory=dict)
    # うちメインスキル由来（内訳表示や二重計上の判定に使う）
    skill_ingredients_per_day: dict[str, float] = field(default_factory=dict)
    skill_activations_per_day: float = 0.0
    # 食材・きのみを産むスキルは 0。そのぶんは供給側に計上済みで、
    # ここでエナジーとしても数えると二重計上になる。
    skill_energy_per_day: float = 0.0

    @property
    def berry_energy_per_day(self) -> float:
        """好物倍率・フィールド補正なしのきのみエナジー/日。"""
        return self.berry_count_per_day * self.berry_energy_per_unit

    def ingredients_without_skill(self) -> dict[str, float]:
        """おてつだいで拾う分だけ（スキル由来を除く）。"""
        out = dict(self.ingredients_per_day)
        for name, qty in self.skill_ingredients_per_day.items():
            remain = out.get(name, 0.0) - qty
            if remain > 1e-9:
                out[name] = remain
            else:
                out.pop(name, None)
        return out


def capability_of(
    pokemon: dict[str, Any],
    species: dict[str, Any],
    play_context: PlayContext | None = None,
    *,
    team_help_bonus_count: int = 0,
) -> Capability:
    """個体の素の能力をまとめて返す。

    team_help_bonus_count だけは「チームのおてつだいボーナス数」で速度軸に効くため、
    素の能力の一部として受け取る（好物・フィールド・イベントとは性質が違う）。
    """
    berry = expected_berry_per_day(
        pokemon,
        species,
        play_context,
        fav_berries=None,          # 好物倍率は掛けない（呼び出し側の責任）
        field_bonus=0.0,
        team_help_bonus_count=team_help_bonus_count,
    )
    ings = expected_ingredients_per_day(
        pokemon, species, play_context, team_help_bonus_count=team_help_bonus_count
    )
    skill_ings = expected_skill_ingredients_per_day(
        pokemon, species, team_help_bonus_count=team_help_bonus_count
    )
    skill_energy = (
        0.0
        if has_skill_ingredients(species)
        else expected_skill_energy_per_day(
            pokemon, species, team_help_bonus_count=team_help_bonus_count
        )
    )
    return Capability(
        berry_name=berry.get("name"),
        berry_count_per_day=float(berry.get("count") or 0.0),
        berry_energy_per_unit=float(berry.get("energy_per_unit") or 0.0),
        ingredients_per_day=ings,
        skill_ingredients_per_day=skill_ings,
        skill_activations_per_day=expected_skill_activations_per_day(
            pokemon, species, team_help_bonus_count=team_help_bonus_count
        ),
        skill_energy_per_day=skill_energy,
    )
