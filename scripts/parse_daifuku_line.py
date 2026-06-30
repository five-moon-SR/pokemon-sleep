"""だいふく期待値チェッカーのタブ区切り単行出力をパースする。

出力フォーマット（25項目、タブ区切り）:
  ポケモン / スキル名 / スキル効果 / スキル発動回数 / スキル効果合計 /
  きのみエナジー / 合計食材数 / 第一食材数 / 第二食材数 / 第三食材数 /
  ポケモンLv / メインスキルLv / 最大所持数 /
  サブスキル1 / サブスキル2 / サブスキル3 / サブスキル4 / サブスキル5 /
  性格 / 好みのきのみ / EXモード / EXモード状態 / EXフィールド効果 /
  キャンプチケット / フィールドボーナス

ただし daifuku 出力には食材枠の選択名（マメミート/あったかジンジャー…）が
直接出ないため、利用側で「食材編成」（AAA / ABC / ABB 等）を別途指定する必要がある。

使い方（モジュール）:
    from scripts.parse_daifuku_line import parse_daifuku_line, line_to_case
    parsed = parse_daifuku_line(LINE)
    case = line_to_case(parsed, case_id="013", species=SPECIES_DICT,
                       composition="AAA")  # 食材編成

CLI:
    python -m scripts.parse_daifuku_line --line "<タブ区切り>" --case-id 013 --comp AAA
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import db


COLUMNS: tuple[str, ...] = (
    "species_name",
    "skill_name",
    "skill_effect",       # "11 個"
    "skill_activations",  # 1.01
    "skill_total",        # "11 個"
    "berry_energy",       # 11377.78
    "ingredients_total",  # 66
    "ingredient_1_count", # 9.4
    "ingredient_2_count", # 23.6
    "ingredient_3_count", # 33
    "level",              # 60
    "main_skill_level",   # 3
    "max_inventory",      # 29
    "subskill_1", "subskill_2", "subskill_3", "subskill_4", "subskill_5",
    "nature_label",       # "きまぐれ (無補正)"
    "favorite_berry",     # "オン"
    "ex_mode",            # "オフ"
    "ex_state",           # ""
    "ex_field",           # ""
    "camp_ticket",        # "オフ"
    "field_bonus",        # "オフ" or "%"
)


@dataclass
class ParsedDaifuku:
    species_name: str
    skill_name: str
    skill_effect: str
    skill_activations: float
    skill_total: str
    berry_energy: float
    ingredients_total: float
    ingredient_counts: tuple[float, float, float]  # 第一/第二/第三
    level: int
    main_skill_level: int
    max_inventory: int
    subskills: list[str]   # 空 "-" は除外済
    nature: str            # "きまぐれ" だけ抽出
    nature_label: str      # 元ラベル（"きまぐれ (無補正)"）
    favorite_berry_on: bool
    ex_mode_on: bool
    camp_ticket_on: bool
    field_bonus_pct: float
    raw: dict[str, str] = field(default_factory=dict)


def _to_float(s: str, default: float = 0.0) -> float:
    s = (s or "").strip().replace(",", "")
    if not s or s == "-":
        return default
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else default


def _to_int(s: str, default: int = 0) -> int:
    return int(_to_float(s, default))


def _to_bool_on(s: str) -> bool:
    return (s or "").strip() == "オン"


def parse_daifuku_line(line: str) -> ParsedDaifuku:
    """タブ区切り単行を ParsedDaifuku にパース。"""
    parts = [p.strip() for p in line.rstrip("\n").split("\t")]
    if len(parts) < 13:
        raise ValueError(
            f"タブ区切り項目数が不足（{len(parts)}）。期待25項目。\n受信: {line!r}"
        )
    while len(parts) < len(COLUMNS):
        parts.append("")

    raw = dict(zip(COLUMNS, parts))

    nature_label = raw["nature_label"]
    nature = nature_label.split("(")[0].strip() or nature_label

    subs = [
        s for s in [raw[f"subskill_{i}"] for i in range(1, 6)]
        if s and s != "-"
    ]

    field_bonus_str = raw["field_bonus"]
    if field_bonus_str in ("オフ", "", "オン"):
        field_bonus_pct = 0.0
    else:
        field_bonus_pct = _to_float(field_bonus_str, 0.0)

    return ParsedDaifuku(
        species_name=raw["species_name"],
        skill_name=raw["skill_name"],
        skill_effect=raw["skill_effect"],
        skill_activations=_to_float(raw["skill_activations"]),
        skill_total=raw["skill_total"],
        berry_energy=_to_float(raw["berry_energy"]),
        ingredients_total=_to_float(raw["ingredients_total"]),
        ingredient_counts=(
            _to_float(raw["ingredient_1_count"]),
            _to_float(raw["ingredient_2_count"]),
            _to_float(raw["ingredient_3_count"]),
        ),
        level=_to_int(raw["level"]),
        main_skill_level=_to_int(raw["main_skill_level"]),
        max_inventory=_to_int(raw["max_inventory"]),
        subskills=subs,
        nature=nature,
        nature_label=nature_label,
        favorite_berry_on=_to_bool_on(raw["favorite_berry"]),
        ex_mode_on=_to_bool_on(raw["ex_mode"]),
        camp_ticket_on=_to_bool_on(raw["camp_ticket"]),
        field_bonus_pct=field_bonus_pct,
        raw=raw,
    )


# ──────────────────────────────────────────────────────────
# 食材編成（AAA / ABC / 任意名）→ 個別食材名
# ──────────────────────────────────────────────────────────
def composition_to_ingredient_names(
    species: dict[str, Any], composition: str
) -> tuple[str | None, str | None, str | None]:
    """食材編成ラベルから 3スロットの食材名を返す。

    composition の解釈:
      - "AAA" / "AAB" / "ABC" 等の3文字パターン: 各文字が a/b/c枠のデフォルト食材を指す
      - "<食材1>/<食材2>/<食材3>" のスラッシュ区切り: 名前直接指定
    """
    ings = species.get("ingredients") or {}
    if "/" in composition:
        names = composition.split("/")
        names = (names + ["", "", ""])[:3]
        return tuple(n.strip() or None for n in names)

    # "AAA" 等のパターン
    if len(composition) == 3 and all(c in "abc" for c in composition.lower()):
        out: list[str | None] = []
        for ch in composition.lower():
            slot = (ings.get(ch) or {}).get("name")
            out.append(slot)
        return tuple(out)
    raise ValueError(f"composition の解釈に失敗: {composition!r}")


def line_to_case(
    parsed: ParsedDaifuku,
    *,
    case_id: str,
    composition: str = "AAA",
    ribbon_stage: int = 0,
    note: str = "",
) -> dict[str, Any]:
    """ParsedDaifuku → TOML case dict（[[case]] のフィールドに対応）。

    expected_ingredients は「食材名→個数」に集約（AAA 等で同じ食材が複数枠なら合算）。
    """
    species = db.get_species_data(parsed.species_name)
    if not species:
        raise ValueError(f"マスター未登録: {parsed.species_name}")

    ing_names = composition_to_ingredient_names(species, composition)
    expected: dict[str, float] = {}
    for name, qty in zip(ing_names, parsed.ingredient_counts):
        if not name or qty <= 0:
            continue
        expected[name] = expected.get(name, 0.0) + float(qty)

    return {
        "id": case_id,
        "species_name": parsed.species_name,
        "level": parsed.level or 60,
        "nature": parsed.nature,
        "subskills": list(parsed.subskills),
        "ingredient_1": ing_names[0] or "",
        "ingredient_2": ing_names[1] or "",
        "ingredient_3": ing_names[2] or "",
        "ribbon_stage": ribbon_stage,
        "expected_unit": "per_day",
        "expected_weekend": False,
        "expected_ingredients": expected,
        "expected_skill_activations": parsed.skill_activations,
        "expected_skill_effect": parsed.skill_effect,
        "expected_berry_energy": parsed.berry_energy,
        "note": note or f"daifuku 出力: 合計{parsed.ingredients_total} / "
                       f"内訳{parsed.ingredient_counts[0]}/{parsed.ingredient_counts[1]}/{parsed.ingredient_counts[2]}",
    }


def format_toml_block(case: dict[str, Any]) -> str:
    """case dict を TOML の [[case]] ブロック表記に書き出す（手動ペースト用）。"""
    def _kv(k: str, v: Any) -> str:
        if isinstance(v, str):
            return f'{k} = "{v}"'
        if isinstance(v, bool):
            return f"{k} = {str(v).lower()}"
        if isinstance(v, list):
            inner = ", ".join(f'"{x}"' for x in v)
            return f"{k} = [{inner}]"
        if isinstance(v, dict):
            inner = ", ".join(f'"{x}" = {y}' for x, y in v.items())
            return f"{k} = {{ {inner} }}"
        return f"{k} = {v}"

    keys = (
        "id", "species_name", "level", "nature", "subskills",
        "ingredient_1", "ingredient_2", "ingredient_3", "ribbon_stage",
        "expected_unit", "expected_weekend", "expected_ingredients",
        "expected_skill_activations", "expected_skill_effect",
        "expected_berry_energy", "note",
    )
    lines = ["[[case]]"]
    for k in keys:
        if k in case:
            lines.append(_kv(k, case[k]))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--line", required=True, help="daifuku のタブ区切り単行")
    parser.add_argument("--case-id", required=True, help="ケースID（例: 013）")
    parser.add_argument("--comp", default="AAA",
                        help="食材編成（AAA/ABC/ABB or 食材名/食材名/食材名）")
    parser.add_argument("--ribbon", type=int, default=0,
                        help="リボン段階（0〜4）")
    parser.add_argument("--note", default="", help="ケース備考")
    args = parser.parse_args()

    parsed = parse_daifuku_line(args.line)
    case = line_to_case(
        parsed, case_id=args.case_id, composition=args.comp,
        ribbon_stage=args.ribbon, note=args.note,
    )
    print(format_toml_block(case))
    return 0


if __name__ == "__main__":
    sys.exit(main())
