#!/usr/bin/env python3
"""マスターデータ(data/*.json)の整合性を総点検する。

DBには繋がない。data/ 配下のJSONだけを読み、以下を検査する:

  A. 参照整合性   … 他ファイルを指す名前が実在するか
  B. 数値の妥当性 … 範囲・単調性・自己矛盾
  C. 重複と欠損   … 主キー重複、必須項目のnull
  D. 派生値の再計算 … total_ingredients など「計算で出せる値」の突き合わせ

使い方:
    python scripts/audit_master_data.py            # 要約のみ
    python scripts/audit_master_data.py --verbose  # 全件列挙

終了コード: 重大(ERROR)が1件でもあれば 1、警告のみなら 0。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

DATA = Path(__file__).resolve().parent.parent / "data"

ERRORS: list[tuple[str, str]] = []
WARNINGS: list[tuple[str, str]] = []


def err(check: str, msg: str) -> None:
    ERRORS.append((check, msg))


def warn(check: str, msg: str) -> None:
    WARNINGS.append((check, msg))


def load(name: str) -> Any:
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


def records(name: str) -> list[dict]:
    d = load(name)
    return d["records"] if isinstance(d, dict) and "records" in d else d


# ---------------------------------------------------------------------------
# データ読み込み
# ---------------------------------------------------------------------------
master = records("pokemon_master")
berries = records("berry")
ingredients = records("ingredient")
fields = records("field")
recipes = records("recipe")
main_skills = records("main_skill")
subskills = records("subskill")
evolutions = records("evolution")
natures = records("nature")
tiers = records("community_tier")

berry_names = {b["name"] for b in berries}
ingredient_names = {i["name"] for i in ingredients}
species_names = {m["species_name"] for m in master}
skill_names = {s["name"] for s in main_skills}
skill_categories = {s["category"] for s in main_skills}


# ---------------------------------------------------------------------------
# C. 重複と欠損
# ---------------------------------------------------------------------------
def check_duplicates() -> None:
    for label, rows, key in (
        ("pokemon_master", master, "species_name"),
        ("berry", berries, "name"),
        ("ingredient", ingredients, "name"),
        ("recipe", recipes, "name"),
        ("main_skill", main_skills, "name"),
        ("subskill", subskills, "name"),
        ("field", fields, "name"),
        ("nature", natures, "name"),
    ):
        dup = [k for k, n in Counter(r.get(key) for r in rows).items() if n > 1]
        for d in dup:
            err("重複キー", f"{label}: {key}={d!r} が複数件")

    dex = Counter(m.get("dex_no") for m in master)
    for d, n in dex.items():
        if n > 1:
            names = [m["species_name"] for m in master if m.get("dex_no") == d]
            # 同一dex_noはリージョン/イベント違いで正常。名前まで同じなら異常。
            warn("dex_no重複", f"dex_no={d} が{n}件: {names}")


def check_required_fields() -> None:
    required = {
        "pokemon_master": (master, ["dex_no", "species_name", "specialty",
                                    "berry", "main_skill", "base_assist_seconds"]),
        "berry": (berries, ["name", "base_energy"]),
        "ingredient": (ingredients, ["name", "base_energy"]),
        "recipe": (recipes, ["name", "category"]),
        "main_skill": (main_skills, ["name", "category", "max_level"]),
    }
    for label, (rows, keys) in required.items():
        for r in rows:
            for k in keys:
                if r.get(k) in (None, "", []):
                    err("必須欠損", f"{label}: {r.get('name') or r.get('species_name')!r} の {k} が空")


# ---------------------------------------------------------------------------
# A. 参照整合性
# ---------------------------------------------------------------------------
def check_master_references() -> None:
    for m in master:
        name = m["species_name"]
        b = (m.get("berry") or {}).get("name")
        if b and b not in berry_names:
            err("参照切れ", f"pokemon_master[{name}]: きのみ {b!r} が berry.json に無い")

        ings = m.get("ingredients") or {}
        for slot, v in ings.items():
            if v is None:
                continue  # 未登録は check_ingredient_slots で別途扱う
            if not isinstance(v, dict):
                err("型不正", f"pokemon_master[{name}]: ingredients.{slot} が dict でない")
                continue
            n = v.get("name")
            if n and n not in ingredient_names:
                err("参照切れ", f"pokemon_master[{name}]: 食材 {n!r} が ingredient.json に無い")

        # 「ばけのかわ(きのみバースト)」のような複合表記があるので、
        # 評価器と同じ解決ロジック(_main_skill_category)で突合する。
        ms = m.get("main_skill")
        if ms and _resolve_skill_category(m) is None:
            err("参照切れ", f"pokemon_master[{name}]: メインスキル {ms!r} をカテゴリに解決できない")


def _resolve_skill_category(species: dict) -> str | None:
    sys.path.insert(0, str(DATA.parent))
    try:
        from utils.evaluator import _main_skill_category
    except Exception:
        return species.get("main_skill")
    return _main_skill_category(species)


def check_ingredient_slots() -> None:
    """食材スロットの登録状態を「実際の計算結果」で検査する。

    c枠が null なのは異常ではない（食材2種の種族。第三スロットは a/b から選ぶ）。
    見た目の欠損ではなく、qty_at_slot() が返す実数で判定する:
      - 第二スロットで1個も取れない → b枠が無い＝異常
      - 第三スロットで1個も取れない → Lv60で食材が増えない＝異常
    """
    sys.path.insert(0, str(DATA.parent))
    try:
        from utils.food_expectation import qty_at_slot
    except Exception as e:  # pragma: no cover
        warn("検査不能", f"food_expectation を読み込めず: {e}")
        return

    for m in master:
        name = m["species_name"]
        ings = m.get("ingredients") or {}
        if "a" not in ings or ings.get("a") is None:
            err("食材未登録", f"pokemon_master[{name}]: 食材スロット a(必須) が無い")
            continue

        best = {1: 0, 2: 0}
        for slot_key in ("a", "b", "c"):
            v = ings.get(slot_key)
            if not isinstance(v, dict) or not v.get("name"):
                continue
            for idx in (1, 2):
                try:
                    best[idx] = max(best[idx], int(qty_at_slot(m, v["name"], idx)))
                except Exception:
                    pass

        if best[1] <= 0:
            err("第二スロット無効",
                f"pokemon_master[{name}]: 第二スロット(Lv30解放)で取れる食材が0個")
        if best[2] <= 0:
            err("第三スロット無効",
                f"pokemon_master[{name}]: 第三スロット(Lv60解放)で取れる食材が0個 "
                f"— Lv60にしても食材が増えない")

        # 形の検査は参考情報に留める（c枠nullは仕様）。
        if ings.get("c") is None:
            warn("食材2種の種族", f"pokemon_master[{name}]: c枠なし（第三スロットは a/b から選択）")
        alen = len((ings.get("a") or {}).get("qty") or [])
        if alen != 3:
            err("qty段数", f"pokemon_master[{name}]: a枠のqtyが{alen}要素 (仕様は3要素)")


def check_recipe_references() -> None:
    for r in recipes:
        for ing in r.get("ingredients") or []:
            if ing.get("name") not in ingredient_names:
                err("参照切れ", f"recipe[{r['name']}]: 食材 {ing.get('name')!r} が ingredient.json に無い")


def check_field_references() -> None:
    for f in fields:
        for b in f.get("favorite_berries") or []:
            bname = b.get("name") if isinstance(b, dict) else b
            if bname not in berry_names:
                err("参照切れ", f"field[{f['name']}]: 好みきのみ {bname!r} が berry.json に無い")
            btype = b.get("type") if isinstance(b, dict) else None
            if btype:
                declared = next((x.get("type") for x in berries if x["name"] == bname), None)
                if declared and declared != btype:
                    err("矛盾", f"field[{f['name']}]: {bname} のタイプが "
                                f"{btype!r} だが berry.json では {declared!r}")
        if not f.get("favorite_berries") and not f.get("favorite_berries_random"):
            warn("空データ", f"field[{f['name']}]: 好みきのみが空でランダム指定も無い")


def check_berry_field_crossref() -> None:
    """きのみ側 preferred_field と フィールド側 favorite_berries の双方向突合。

    片方だけ直して片方を直し忘れる事故を検出する。
    """
    f2b: dict[str, list[str]] = defaultdict(list)
    for f in fields:
        for b in f.get("favorite_berries") or []:
            bname = b.get("name") if isinstance(b, dict) else b
            f2b[bname].append(f["name"])

    for b in berries:
        pf, listed = b.get("preferred_field"), f2b.get(b["name"], [])
        if not listed:
            err("双方向不一致",
                f"berry[{b['name']}]: preferred_field={pf!r} だが、どのフィールドの"
                f"好みきのみにも載っていない")
        elif pf not in listed:
            err("双方向不一致",
                f"berry[{b['name']}]: preferred_field={pf!r} だが、実際に載っているのは {listed}")

    for bname, flds in f2b.items():
        if len(flds) > 1:
            warn("要確認", f"きのみ {bname} が複数フィールドの好みに載っている: {flds}")


def check_evolution_references() -> None:
    for e in evolutions:
        for side in ("from", "to"):
            if e.get(side) not in species_names:
                err("参照切れ", f"evolution: {side}={e.get(side)!r} が pokemon_master に無い")

    # 進化の循環検出
    nxt = defaultdict(list)
    for e in evolutions:
        nxt[e.get("from")].append(e.get("to"))
    for start in list(nxt):
        seen, stack = set(), [start]
        while stack:
            cur = stack.pop()
            if cur in seen:
                err("進化ループ", f"evolution: {start} から辿ると循環する ({cur})")
                break
            seen.add(cur)
            stack.extend(nxt.get(cur, []))


def check_evolution_completeness() -> None:
    """進化ラインの登録漏れを検出する。

    「進化しない種族」は実在する（伝説・単体種）ので、未登場そのものは異常ではない。
    ただし master に居て evolution.json に一切登場しない種族は、
    本当に進化しないのか登録漏れなのかを人が確認する必要があるため一覧に出す。
    """
    known_standalone = {
        "カモネギ", "ガルーラ", "カイロス", "メタモン", "ミュウ", "ツボツボ",
        "ヘラクロス", "デリバード", "ライコウ", "エンテイ", "スイクン", "ヤミラミ",
        "クチート", "プラスル", "マイナン", "アブソル", "ラティアス", "ラティオス",
        "ミカルゲ", "クレセリア", "ダークライ", "デデンネ", "キュワワー",
        "トゲデマル", "ミミッキュ", "ジジーロン", "ウッウ",
    }
    in_evo = {e.get("from") for e in evolutions} | {e.get("to") for e in evolutions}
    for m in master:
        n = m["species_name"]
        if "(" in n:            # リージョン/イベント違いは対象外
            continue
        if n in in_evo or n in known_standalone:
            continue
        err("進化ライン欠損",
            f"pokemon_master[{n}]: evolution.json に一切登場しない。"
            f"進化しない種族なら known_standalone に追記すること")


def check_tier_references() -> None:
    for t in tiers:
        if t.get("species_name") not in species_names:
            err("参照切れ", f"community_tier: {t.get('species_name')!r} が pokemon_master に無い")


def check_ingredient_recipe_backrefs() -> None:
    recipe_names = {r["name"] for r in recipes}
    for i in ingredients:
        for rn in i.get("max_bonus_recipes") or []:
            if rn not in recipe_names:
                err("参照切れ", f"ingredient[{i['name']}]: max_bonus_recipes の {rn!r} が recipe.json に無い")


# ---------------------------------------------------------------------------
# D. 派生値の再計算
# ---------------------------------------------------------------------------
def check_recipe_totals() -> None:
    """total_ingredients が ingredients の合計と一致するか。

    鍋容量の判定に直接使われる値なので、ここがズレると
    「作れる/作れない」の判断そのものが壊れる。
    """
    for r in recipes:
        ings = r.get("ingredients") or []
        declared = r.get("total_ingredients")
        if not ings:
            if declared:
                err("派生値不一致",
                    f"recipe[{r['name']}]: 食材リストが空なのに total_ingredients={declared}")
            continue
        actual = sum(int(x.get("count") or 0) for x in ings)
        if declared is None:
            err("派生値欠損",
                f"recipe[{r['name']}]: total_ingredients が未設定 (実際の合計={actual})")
        elif int(declared) != actual:
            err("派生値不一致",
                f"recipe[{r['name']}]: total_ingredients={declared} だが "
                f"食材の合計は {actual} (差{actual - int(declared):+d})")


def check_recipe_energy_monotonic() -> None:
    for r in recipes:
        e1, e30, e60 = r.get("energy_lv1"), r.get("energy_lv30"), r.get("energy_lv60")
        if None in (e1, e30, e60):
            continue
        if not (e1 <= e30 <= e60):
            err("単調性違反",
                f"recipe[{r['name']}]: エナジーがLv順に増えていない "
                f"(lv1={e1} lv30={e30} lv60={e60})")
        p69, p507 = r.get("energy_max_pot69"), r.get("energy_max_pot507")
        if p69 is not None and p507 is not None and p69 > p507:
            err("単調性違反",
                f"recipe[{r['name']}]: 鍋69({p69}) が 鍋507({p507}) を上回っている")
        if e60 and p69 and e60 > p69:
            warn("要確認",
                 f"recipe[{r['name']}]: energy_lv60({e60}) が energy_max_pot69({p69}) を超える")


def check_ingredient_qty_monotonic() -> None:
    """食材個数は解放順(Lv30/60)で増えるはず。"""
    for m in master:
        for slot, v in (m.get("ingredients") or {}).items():
            if not isinstance(v, dict):
                continue
            qty = v.get("qty")
            if not isinstance(qty, list) or not qty:
                err("型不正", f"pokemon_master[{m['species_name']}]: ingredients.{slot}.qty={qty!r}")
                continue
            if any(not isinstance(q, int) or q <= 0 for q in qty):
                err("値不正", f"pokemon_master[{m['species_name']}]: {slot}.qty に非正の値 {qty}")
            if list(qty) != sorted(qty):
                err("単調性違反",
                    f"pokemon_master[{m['species_name']}]: {slot}.qty={qty} が昇順でない")


# ---------------------------------------------------------------------------
# B. 数値の妥当性
# ---------------------------------------------------------------------------
ALLOWED_SPECIALTY = {"きのみ", "食材", "スキル", "オール"}
ALLOWED_SLEEP_TYPE = {"うとうと", "すやすや", "ぐっすり"}


def check_master_values() -> None:
    for m in master:
        name = m["species_name"]
        sp = m.get("specialty")
        if sp not in ALLOWED_SPECIALTY:
            err("値不正", f"pokemon_master[{name}]: specialty={sp!r} が想定外")
        stype = m.get("sleep_type")
        if stype and stype not in ALLOWED_SLEEP_TYPE:
            err("値不正", f"pokemon_master[{name}]: sleep_type={stype!r} が想定外")

        bas = m.get("base_assist_seconds")
        # 実データの実測レンジは 2100-6400。外れ値検出用に少し広く取る。
        if not isinstance(bas, int) or not (1000 <= bas <= 8000):
            err("範囲外", f"pokemon_master[{name}]: base_assist_seconds={bas} が想定範囲(1000-8000)外")

        fdr = m.get("food_drop_rate")
        if fdr is None:
            warn("欠損", f"pokemon_master[{name}]: food_drop_rate が未設定")
        elif not (0 < float(fdr) <= 100):
            err("範囲外", f"pokemon_master[{name}]: food_drop_rate={fdr} が0-100外")

        msr = m.get("main_skill_rate")
        if msr is None:
            warn("欠損", f"pokemon_master[{name}]: main_skill_rate が未設定")
        elif not (0 < float(msr) <= 100):
            err("範囲外", f"pokemon_master[{name}]: main_skill_rate={msr} が0-100外")

        nslots = len(m.get("ingredients") or {})
        if nslots != 3:
            warn("スロット数", f"pokemon_master[{name}]: 食材スロットが{nslots}個 (通常3)")

        bqty = (m.get("berry") or {}).get("qty")
        if bqty is not None and (not isinstance(bqty, int) or bqty <= 0):
            err("値不正", f"pokemon_master[{name}]: berry.qty={bqty!r}")


def check_specialty_consistency() -> None:
    """とくいなものと基礎値の噛み合わせ。

    絶対値の閾値は根拠が無いので、同じ specialty 集団の中での外れ値
    （下位5%かつ集団中央の6割未満）だけを拾う。
    """
    def pct(values: list[float], q: float) -> float:
        if not values:
            return 0.0
        xs = sorted(values)
        i = max(0, min(len(xs) - 1, int(round(q * (len(xs) - 1)))))
        return xs[i]

    by_sp = defaultdict(list)
    for m in master:
        by_sp[m.get("specialty")].append(m)

    axis = {"食材": "food_drop_rate", "スキル": "main_skill_rate", "きのみ": "food_drop_rate"}
    for sp, rows in sorted(by_sp.items(), key=lambda x: str(x[0])):
        key = axis.get(sp)
        if not key or len(rows) < 10:
            continue
        vals = [float(r[key]) for r in rows if r.get(key)]
        p05, med = pct(vals, 0.05), pct(vals, 0.5)
        for r in rows:
            v = r.get(key)
            if v and float(v) <= p05 and float(v) < med * 0.6:
                warn("外れ値",
                     f"specialty={sp} の {r['species_name']}: {key}={v} "
                     f"(集団の下位5%={p05:.1f} 中央={med:.1f})")


def check_skill_levels() -> None:
    for s in main_skills:
        ml = s.get("max_level")
        if not isinstance(ml, int) or not (1 <= ml <= 10):
            err("範囲外", f"main_skill[{s['name']}]: max_level={ml}")


def check_subskills() -> None:
    for s in subskills:
        if s.get("effect_kind") == "percent":
            v = s.get("effect_value_num")
            if v is None:
                err("欠損", f"subskill[{s['name']}]: effect_value_num が無い")
            elif not (-100 <= float(v) <= 100):
                err("範囲外", f"subskill[{s['name']}]: effect_value_num={v}")
        if s.get("rarity") not in {"gold", "blue", "white", None}:
            warn("値不正", f"subskill[{s['name']}]: rarity={s.get('rarity')!r}")


def check_natures() -> None:
    for n in natures:
        up, down, neutral = n.get("up"), n.get("down"), n.get("is_neutral")
        if neutral:
            # 無補正は「同じ軸を上げて下げる」表現が正（up==down）。
            if up != down:
                err("矛盾", f"nature[{n['name']}]: 無補正なのに up({up!r}) と down({down!r}) が違う")
        elif not up or not down:
            err("欠損", f"nature[{n['name']}]: up/down のどちらかが空 (up={up!r} down={down!r})")
        elif up == down:
            err("矛盾", f"nature[{n['name']}]: up と down が同じ ({up!r})")


def check_skill_effect_coverage() -> None:
    """評価器が精密テーブルを引けないメインスキルを洗い出す。"""
    sys.path.insert(0, str(DATA.parent))
    try:
        from utils.skill_effects import get_skill_energy_per_activation, get_skill_max_lv
    except Exception as e:  # pragma: no cover
        warn("検査不能", f"skill_effects を読み込めず: {e}")
        return
    missing = defaultdict(list)
    for m in master:
        ms = m.get("main_skill")
        cat = _resolve_skill_category(m) or ms
        mx = get_skill_max_lv(cat) or 6
        if get_skill_energy_per_activation(cat, mx, skill_name=ms) is None:
            missing[cat].append(m["species_name"])
    for cat, names in sorted(missing.items(), key=lambda x: -len(x[1])):
        warn("効果量未収録",
             f"{cat}: {len(names)}種が粗い近似で評価される ({', '.join(names[:4])}"
             f"{' ほか' if len(names) > 4 else ''})")


# ---------------------------------------------------------------------------
# 実行
# ---------------------------------------------------------------------------
CHECKS = [
    ("重複キー", check_duplicates),
    ("必須項目", check_required_fields),
    ("master参照", check_master_references),
    ("食材スロット", check_ingredient_slots),
    ("recipe参照", check_recipe_references),
    ("field参照", check_field_references),
    ("きのみ↔フィールド", check_berry_field_crossref),
    ("evolution参照", check_evolution_references),
    ("進化ライン網羅", check_evolution_completeness),
    ("tier参照", check_tier_references),
    ("ingredient逆参照", check_ingredient_recipe_backrefs),
    ("recipe合計値", check_recipe_totals),
    ("recipeエナジー", check_recipe_energy_monotonic),
    ("食材個数の単調性", check_ingredient_qty_monotonic),
    ("master数値", check_master_values),
    ("とくい噛み合わせ", check_specialty_consistency),
    ("スキルLv", check_skill_levels),
    ("サブスキル", check_subskills),
    ("せいかく", check_natures),
    ("効果量カバレッジ", check_skill_effect_coverage),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true", help="全件を列挙する")
    args = ap.parse_args()

    print(f"マスターデータ監査  (pokemon={len(master)} recipe={len(recipes)} "
          f"berry={len(berries)} ingredient={len(ingredients)})\n")

    for label, fn in CHECKS:
        before = (len(ERRORS), len(WARNINGS))
        fn()
        de, dw = len(ERRORS) - before[0], len(WARNINGS) - before[1]
        mark = "NG" if de else ("－" if dw else "OK")
        detail = []
        if de:
            detail.append(f"エラー{de}")
        if dw:
            detail.append(f"警告{dw}")
        print(f"  [{mark}] {label:20s} {'/'.join(detail)}")

    def dump(title: str, items: list[tuple[str, str]]) -> None:
        if not items:
            return
        print(f"\n=== {title} ({len(items)}件) ===")
        grouped = defaultdict(list)
        for check, msg in items:
            grouped[check].append(msg)
        for check, msgs in grouped.items():
            print(f"\n[{check}] {len(msgs)}件")
            shown = msgs if args.verbose else msgs[:8]
            for m in shown:
                print(f"  - {m}")
            if len(msgs) > len(shown):
                print(f"  … 他{len(msgs) - len(shown)}件 (--verbose で全件)")

    dump("エラー（要修正）", ERRORS)
    dump("警告（要確認）", WARNINGS)

    print(f"\n結果: エラー {len(ERRORS)}件 / 警告 {len(WARNINGS)}件")
    return 1 if ERRORS else 0


if __name__ == "__main__":
    sys.exit(main())
