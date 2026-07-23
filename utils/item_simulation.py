"""アイテム使用のifシミュレーションと使用優先度ランキング。

育成後（最終進化形 × Lv60）を基準に、以下のアイテムを使った場合の評価変化を出す:
- 性格変更アイテム（無補正化）: 個体の性格を無補正（上下なし）にした場合
- サブスキルランクUP（S→M）: 装着中の S サブスキルを対応する M に上げた場合

evaluator.evaluate_pokemon は種族・性格・サブをすべて個体 dict から読むので、
dict を射影（書き換え）して渡すだけで全ケースを表現できる。ランク帯・%計算・
重みには一切触れない（rank_calibration_v1_4 の担保を維持）。

検算: python -m utils.item_simulation （DB接続が必要）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from utils.evaluator import (
    SUBSKILL_RANK_UP,
    SUBSKILL_UNLOCK_LEVELS,
    EvaluationResult,
    evaluate_pokemon,
    evaluate_potential,
    final_evolution_of,
    normalize_subskill_name,
)
from utils.sleep_ribbon import count_remaining_evolutions

# 育成後の基準Lv（最終進化・Lv60）
POTENTIAL_LEVEL = 60


def _potential_dict(p: dict[str, Any]) -> dict[str, Any]:
    """最終進化形に射影した個体 dict（育成後評価の土台）。

    メインスキルLvは「1進化ごとに +1」される仕様を反映（evaluate_potential と整合）。
    """
    q = dict(p)
    q["species_name"] = final_evolution_of(p["species_name"])
    q["main_skill_level"] = int(p.get("main_skill_level") or 1) + count_remaining_evolutions(p["species_name"])
    return q


def _equipped_subskill_fields(p: dict[str, Any]) -> list[tuple[str, str]]:
    """(フィールド名, 正規化サブスキル名) のリスト。Lv60で解放済みの枠のみ。"""
    out: list[tuple[str, str]] = []
    for lv in SUBSKILL_UNLOCK_LEVELS:
        if lv > POTENTIAL_LEVEL:
            continue
        field_name = f"subskill_lv{lv}"
        raw = p.get(field_name)
        norm = normalize_subskill_name(raw) if raw else None
        if norm:
            out.append((field_name, norm))
    return out


# ---------------------------------------------------------------------------
# ifシミュレーション（1個体）
# ---------------------------------------------------------------------------

@dataclass
class SubUpgradeOption:
    field_name: str        # subskill_lvNN
    from_sub: str          # 例: おてつだいスピードS
    to_sub: str            # 例: おてつだいスピードM
    total: float           # 適用後の species_total
    delta: float           # base からの差分


@dataclass
class ItemSimResult:
    base_total: float                          # 育成後(最終進化Lv60)ベース
    base_rank: str
    nature_neutral_total: float                # 無補正化後
    nature_neutral_delta: float
    nature_is_neutral: bool                    # 既に無補正なら True（アイテム不要）
    sub_upgrades: list[SubUpgradeOption] = field(default_factory=list)  # delta降順

    @property
    def best_sub_upgrade(self) -> SubUpgradeOption | None:
        return self.sub_upgrades[0] if self.sub_upgrades else None


def _eval_total(q: dict[str, Any]) -> tuple[float, str]:
    res: EvaluationResult = evaluate_pokemon(q, eval_level=POTENTIAL_LEVEL)
    return res.species_total, res.species_rank


def simulate_items(p: dict[str, Any]) -> ItemSimResult:
    """育成後ベースに対する各アイテムの評価変化を計算する。"""
    base_q = _potential_dict(p)
    base_total, base_rank = _eval_total(base_q)

    # 性格無補正化
    nature_is_neutral = not p.get("nature")
    neutral_q = dict(base_q)
    neutral_q["nature"] = None
    neutral_total, _ = _eval_total(neutral_q)

    # サブスキル S→M（装着中の対象サブを1つずつ上げる）
    upgrades: list[SubUpgradeOption] = []
    for field_name, sub in _equipped_subskill_fields(p):
        to_sub = SUBSKILL_RANK_UP.get(sub)
        if not to_sub:
            continue
        up_q = dict(base_q)
        up_q[field_name] = to_sub
        total, _ = _eval_total(up_q)
        upgrades.append(SubUpgradeOption(
            field_name=field_name, from_sub=sub, to_sub=to_sub,
            total=total, delta=total - base_total,
        ))
    upgrades.sort(key=lambda u: -u.delta)

    return ItemSimResult(
        base_total=base_total,
        base_rank=base_rank,
        nature_neutral_total=neutral_total,
        nature_neutral_delta=neutral_total - base_total,
        nature_is_neutral=nature_is_neutral,
        sub_upgrades=upgrades,
    )


# ---------------------------------------------------------------------------
# 使用優先度ランキング（全所持個体）
# ---------------------------------------------------------------------------

@dataclass
class ItemPriority:
    pokemon_id: int
    label: str
    species_name: str            # 現種族
    final_species: str           # 最終進化形
    base_total: float
    after_total: float
    delta: float                 # 伸び幅（育成後スコア）
    detail: str                  # 何を上げるか（サブ名など）


def nature_item_priorities(owned_rows: list[dict[str, Any]]) -> list[ItemPriority]:
    """性格変更アイテム（無補正化）の使用優先度。delta>0 の個体のみ降順。

    下降補正で損している個体だけが無補正化で得をする（上昇補正個体は損）。
    """
    out: list[ItemPriority] = []
    for p in owned_rows:
        if not p.get("nature"):
            continue  # 既に無補正＝アイテム不要
        sim = simulate_items(p)
        if sim.nature_neutral_delta <= 0.05:
            continue
        out.append(ItemPriority(
            pokemon_id=p["id"],
            label=p.get("nickname") or p["species_name"],
            species_name=p["species_name"],
            final_species=final_evolution_of(p["species_name"]),
            base_total=sim.base_total,
            after_total=sim.nature_neutral_total,
            delta=sim.nature_neutral_delta,
            detail=f"性格 {p['nature']} → 無補正",
        ))
    out.sort(key=lambda x: -x.delta)
    return out


def subskill_item_priorities(owned_rows: list[dict[str, Any]]) -> list[ItemPriority]:
    """サブスキルランクUP（S→M）の使用優先度。最良の1枠昇格の伸び順。"""
    out: list[ItemPriority] = []
    for p in owned_rows:
        sim = simulate_items(p)
        best = sim.best_sub_upgrade
        if not best or best.delta <= 0.05:
            continue
        out.append(ItemPriority(
            pokemon_id=p["id"],
            label=p.get("nickname") or p["species_name"],
            species_name=p["species_name"],
            final_species=final_evolution_of(p["species_name"]),
            base_total=sim.base_total,
            after_total=best.total,
            delta=best.delta,
            detail=f"{best.from_sub} → {best.to_sub}",
        ))
    out.sort(key=lambda x: -x.delta)
    return out


if __name__ == "__main__":
    # python -m utils.item_simulation で検算（DB接続が必要）
    import db

    owned = [dict(r) for r in db.list_pokemon()]
    print(f"所持: {len(owned)} 体")

    print("\n=== 性格アイテム（無補正化）使用優先度 上位10 ===")
    for i, ip in enumerate(nature_item_priorities(owned)[:10], 1):
        arrow = f"（→{ip.final_species}）" if ip.final_species != ip.species_name else ""
        print(f"  #{i} {ip.label}{arrow}: {ip.base_total:.1f} → {ip.after_total:.1f} (+{ip.delta:.1f}) {ip.detail}")

    print("\n=== サブスキルS→M 使用優先度 上位10 ===")
    for i, ip in enumerate(subskill_item_priorities(owned)[:10], 1):
        arrow = f"（→{ip.final_species}）" if ip.final_species != ip.species_name else ""
        print(f"  #{i} {ip.label}{arrow}: {ip.base_total:.1f} → {ip.after_total:.1f} (+{ip.delta:.1f}) {ip.detail}")

    if owned:
        print("\n=== 個体詳細シミュ例（先頭個体） ===")
        sim = simulate_items(owned[0])
        print(f"  育成後ベース: {sim.base_total:.1f} ({sim.base_rank})")
        print(f"  無補正化: {sim.nature_neutral_total:.1f} ({sim.nature_neutral_delta:+.1f})"
              + ("  ※既に無補正" if sim.nature_is_neutral else ""))
        for u in sim.sub_upgrades:
            print(f"  {u.from_sub}→{u.to_sub}: {u.total:.1f} ({u.delta:+.1f})")
