"""きのみごとの役割充足度（ボックス監査）の計算層。

レシピや編成に依存せず、全きのみそれぞれについて
「所持ボックスの誰が担当でき、合計何エナジー/日を張れるか」を逆引きする。
監査フィールドの選択は user_settings KV（user.berry_audit_field 等）に永続化し、
好物3種には ×2 を反映する。

充足度の考え方:
- 編成は5枠しかないので、頭数でなく「最優秀が1〜2体いるか」を充足とみなす
  （TOP_N=2。3体目以降は編成に乗らないので評価に数えない）。
- きのみは食材と違い「レシピの必要数」がないので、
  好物×2の対象なのにトップ担当が薄い/ゼロのきのみを穴として扱う。
- 供給量は現在Lv・現在の個体構成（性格/サブスキル/リボン込み）の実測ベース
  （expected_berry_per_day）。フィールド開拓ボーナスは個人差が大きいので掛けない。

検算: python -m utils.berry_coverage （DB接続が必要）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import db
from utils.food_expectation import _effective_level, expected_berry_per_day
from utils.party_logic import get_play_ctx

AUDIT_FIELD_KEY = "user.berry_audit_field"
AUDIT_RANDOM_FAVS_KEY = "user.berry_audit_random_favs"

# 編成に乗る現実的な枠数。充足判定・表示はこの人数までを「戦力」とみなす
TOP_N = 2


def load_audit_field() -> str | None:
    return db.get_setting(AUDIT_FIELD_KEY, None) or None


def save_audit_field(name: str | None) -> None:
    db.set_setting(AUDIT_FIELD_KEY, name or "")


def load_random_favs() -> list[str]:
    return list(db.get_setting(AUDIT_RANDOM_FAVS_KEY, []) or [])


def save_random_favs(names: list[str]) -> None:
    db.set_setting(AUDIT_RANDOM_FAVS_KEY, list(names))


def resolve_fav_berries(field_name: str | None, random_favs: list[str]) -> set[str]:
    """フィールド名から今週の好物きのみ集合を引く。ランダム週フィールドは手動選択を使う。"""
    if not field_name:
        return set()
    fld = next(
        (f for f in db.list_all_field_records() if f["name"] == field_name), None
    )
    if not fld:
        return set()
    if fld.get("favorite_berries_random"):
        return set(random_favs)
    return {b["name"] for b in (fld.get("favorite_berries") or [])}


@dataclass
class BerryProvider:
    pokemon_id: int
    label: str                 # ニックネーム or 種族名
    species_name: str
    level: int
    energy_per_day: float      # 好物×2込みのきのみエナジー/日
    count_per_day: float       # きのみ獲得個数/日


@dataclass
class BerryCoverage:
    berry: dict                # berry.json レコード（name/type/preferred_field/icon）
    is_favorite: bool          # 監査フィールドの好物か（×2反映済み）
    total_energy: float        # 担当全員の合計エナジー/日（参考値）
    providers: list[BerryProvider]  # energy_per_day 降順

    @property
    def best(self) -> BerryProvider | None:
        return self.providers[0] if self.providers else None

    @property
    def top(self) -> list[BerryProvider]:
        """編成枠基準の戦力（上位 TOP_N 体）。"""
        return self.providers[:TOP_N]

    @property
    def top_energy(self) -> float:
        """充足度の主指標: 上位 TOP_N 体の合計エナジー/日。"""
        return sum(p.energy_per_day for p in self.top)


def berry_audit(
    owned_rows: list[dict[str, Any]],
    fav_berries: set[str],
) -> list[BerryCoverage]:
    """全きのみ → 担当個体とエナジー/日の逆引き監査。

    並び順: 好物が先、同グループ内は上位 TOP_N 体の合計エナジー降順（担当ゼロが末尾）。
    """
    ctx = get_play_ctx()
    records = {r["name"]: r for r in db.list_all_berry_records()}
    providers: dict[str, list[BerryProvider]] = {n: [] for n in records}

    for p in owned_rows:
        master = db.get_species_data(p["species_name"]) or {}
        if not master:
            continue
        b = expected_berry_per_day(p, master, ctx, fav_berries=fav_berries)
        name = b["name"]
        if not name or name not in providers:
            continue
        providers[name].append(BerryProvider(
            pokemon_id=p["id"],
            label=p.get("nickname") or p["species_name"],
            species_name=p["species_name"],
            level=_effective_level(p),
            energy_per_day=b["energy"],
            count_per_day=b["count"],
        ))

    out: list[BerryCoverage] = []
    for name, rec in records.items():
        plist = sorted(providers[name], key=lambda x: -x.energy_per_day)
        out.append(BerryCoverage(
            berry=rec,
            is_favorite=name in fav_berries,
            total_energy=sum(x.energy_per_day for x in plist),
            providers=plist,
        ))
    out.sort(key=lambda c: (not c.is_favorite, -c.top_energy))
    return out


def favorite_holes(coverages: list[BerryCoverage]) -> list[str]:
    """好物(×2)なのに担当ゼロのきのみ名。監査の最重要アラート。"""
    return [
        c.berry["name"] for c in coverages
        if c.is_favorite and not c.providers
    ]


if __name__ == "__main__":
    # python -m utils.berry_coverage で検算（DB接続が必要）
    owned = [dict(r) for r in db.list_pokemon()]
    print(f"所持: {len(owned)} 体")

    field_name = load_audit_field()
    favs = resolve_fav_berries(field_name, load_random_favs())
    print(f"監査フィールド: {field_name or '未設定'} / 好物: {sorted(favs) or 'なし'}")

    covs = berry_audit(owned, favs)
    covered = sum(1 for c in covs if c.providers)
    print(f"担当あり: {covered}/{len(covs)} きのみ")
    for c in covs:
        star = "★" if c.is_favorite else "　"
        top_str = " / ".join(
            f"{p.label} Lv{p.level} {p.energy_per_day:.0f}en/日" for p in c.top
        ) or "担当ゼロ"
        rest = len(c.providers) - len(c.top)
        print(f"  {star}{c.berry['name']}: 戦力{c.top_energy:.0f}en/日 {top_str}" + (f"（他{rest}体）" if rest > 0 else ""))
    holes = favorite_holes(covs)
    if holes:
        print(f"⚠ 好物なのに担当ゼロ: {holes}")
