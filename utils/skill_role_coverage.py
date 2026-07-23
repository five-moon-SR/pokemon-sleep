"""スキル役割充足度（ボックス監査）の計算層。

きのみ/食材の充足度と同じ発想で、メインスキルの「役割」ごとに
「所持ボックスの誰が担当でき、育成後（最終進化Lv60）にどれだけ強いか」を逆引きする。

役割はメインスキルの category を意味単位でグルーピングしたもの（全体げんき回復・
エナジー供給・鍋容量UP・料理成功率・おてつだいサポート・食材ゲット・きのみバースト等）。
強さは育成後のスキル軸スコア（evaluate_potential の species_skill、0〜100）で測る。
育成後は「進化でメインスキルLv+1」も反映済みなので、スキル型の伸びしろが正しく出る。

検算: python -m utils.skill_role_coverage （DB接続が必要）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import db
from utils.evaluator import (
    _main_skill_category,
    evaluate_potential,
    final_evolution_of,
    max_skill_level_of,
)

# 編成に乗る現実枠（各役割この人数までを戦力とみなす）
TOP_N = 2

# スキル役割の定義: (キー, ラベル, 該当カテゴリ集合)。表示はこの順。
SKILL_ROLES: list[tuple[str, str, set[str]]] = [
    ("recovery_all", "💚 全体げんき回復", {"げんきオールS"}),
    ("recovery_single", "💚 単体げんき回復", {"げんきエールS", "げんきチャージS"}),
    ("energy", "⚡ エナジー供給", {"エナジーチャージS", "エナジーチャージM", "ゆめのかけらゲットS"}),
    ("pot_up", "🍳 鍋容量UP", {"料理パワーアップS"}),
    ("dish_chance", "🍀 料理成功率", {"料理チャンスS"}),
    ("help_support", "🤝 おてつだいサポート", {"おてつだいサポートS", "おてつだいブースト"}),
    ("food_get", "🥕 食材ゲット/セレクト", {"食材ゲットS", "食材セレクトS"}),
    ("berry_burst", "🍓 きのみバースト", {"きのみバースト"}),
    ("wildcard", "🎲 その他・特殊", {"ゆびをふる", "スキルコピー", "オールマイティー", "料理アシスト"}),
]

# カテゴリ → 役割キー の逆引き
_CATEGORY_TO_ROLE: dict[str, str] = {
    cat: key for key, _, cats in SKILL_ROLES for cat in cats
}


@dataclass
class SkillProvider:
    pokemon_id: int
    label: str
    species_name: str            # 現種族
    final_species: str           # 最終進化形
    skill_category: str          # メインスキルのカテゴリ
    skill_axis: float            # 育成後のスキル軸スコア(0-100)
    potential_total: float       # 育成後 総合スコア
    potential_rank: str          # 育成後 ランク
    main_skill_level: int        # 育成後の想定メインスキルLv（進化+1込み）


@dataclass
class SkillRoleCoverage:
    key: str
    label: str
    categories: set[str]
    providers: list[SkillProvider]   # skill_axis 降順

    @property
    def best(self) -> SkillProvider | None:
        return self.providers[0] if self.providers else None

    @property
    def top(self) -> list[SkillProvider]:
        return self.providers[:TOP_N]


def _resolve_role(final_species_name: str) -> tuple[str, str] | None:
    """最終進化種族のメインスキル → (役割キー, カテゴリ) を返す。該当なしは None。"""
    sp = db.get_species_data(final_species_name) or {}
    cat = _main_skill_category(sp)
    if not cat:
        return None
    role = _CATEGORY_TO_ROLE.get(cat)
    if not role:
        return None
    return role, cat


def skill_role_audit(
    owned_rows: list[dict[str, Any]],
    *,
    main_skill_max: bool = False,
) -> list[SkillRoleCoverage]:
    """全スキル役割 → 担当個体（育成後スキル軸降順）の逆引き監査。

    main_skill_max=True で「メインスキルLv最大の天井」で評価する（育て切った比較）。
    """
    buckets: dict[str, list[SkillProvider]] = {key: [] for key, _, _ in SKILL_ROLES}

    for p in owned_rows:
        final_sp = final_evolution_of(p["species_name"])
        resolved = _resolve_role(final_sp)
        if not resolved:
            continue
        role_key, cat = resolved
        res = evaluate_potential(p, main_skill_max=main_skill_max)
        if main_skill_max:
            shown_msl = max_skill_level_of(final_sp)
        else:
            shown_msl = int(p.get("main_skill_level") or 1) + _remaining(p["species_name"])
        buckets[role_key].append(SkillProvider(
            pokemon_id=p["id"],
            label=p.get("nickname") or p["species_name"],
            species_name=p["species_name"],
            final_species=final_sp,
            skill_category=cat,
            skill_axis=res.species_skill,
            potential_total=res.species_total,
            potential_rank=res.species_rank,
            main_skill_level=shown_msl,
        ))

    out: list[SkillRoleCoverage] = []
    for key, label, cats in SKILL_ROLES:
        plist = sorted(buckets[key], key=lambda x: -x.skill_axis)
        out.append(SkillRoleCoverage(key=key, label=label, categories=cats, providers=plist))
    return out


def _remaining(species_name: str) -> int:
    from utils.sleep_ribbon import count_remaining_evolutions
    return count_remaining_evolutions(species_name)


def role_holes(coverages: list[SkillRoleCoverage]) -> list[str]:
    """担当ゼロの役割ラベル（穴）。"""
    return [c.label for c in coverages if not c.providers]


if __name__ == "__main__":
    # python -m utils.skill_role_coverage で検算（DB接続が必要）
    owned = [dict(r) for r in db.list_pokemon()]
    print(f"所持: {len(owned)} 体")
    covs = skill_role_audit(owned)
    for c in covs:
        if not c.providers:
            print(f"  {c.label}: ⚠ 担当ゼロ")
            continue
        tops = " / ".join(
            f"{p.label}(育成後{p.potential_rank}・スキル軸{p.skill_axis:.0f}・MSLv{p.main_skill_level})"
            for p in c.top
        )
        rest = len(c.providers) - len(c.top)
        print(f"  {c.label}: {tops}" + (f"（他{rest}体）" if rest > 0 else ""))
    holes = role_holes(covs)
    if holes:
        print(f"\n⚠ 担当ゼロの役割: {holes}")
