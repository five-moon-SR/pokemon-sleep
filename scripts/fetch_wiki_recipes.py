"""ポケモンスリープ攻略・検証Wiki の「料理/レシピの一覧」から新レシピを検出する。

出典: https://wikiwiki.jp/poke_sleep/料理/レシピの一覧

使い方:
  python scripts/fetch_wiki_recipes.py              # dry-run: 差分レポートのみ（既定）
  python scripts/fetch_wiki_recipes.py --apply      # 新レシピを add_recipe 経由で追記
  python scripts/fetch_wiki_recipes.py --html FILE  # 取得済みHTMLを使う（デバッグ用）

方針は fetch_wiki_master.py と同じ:
- 手動運用。Wikiには1リクエストだけ投げる（429を食らいやすいので連打しない）。
- dry-run が既定。--apply でも「新規追加」だけ書き、既存レコードは上書きしない。
- 列の位置は決め打ちにせず、ヘッダ名から引く（列が増えても壊れない）。
- エナジーは一覧表に Lv1 のぶんだけ載る。Lv30/Lv60/なべ別の値は別ページなので
  None のままにし、レポートで案内する（recipe_level 側が Lv1 から換算できる）。
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.parse
import urllib.request
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.add_recipe import add_recipe  # noqa: E402

WIKI_URL = "https://wikiwiki.jp/poke_sleep/料理/レシピの一覧"
RECIPE_PATH = ROOT / "data" / "recipe.json"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

# 一覧表はカテゴリごとに1つずつ、この順で並ぶ（カレー→サラダ→デザート・ドリンク）。
CATEGORY_ORDER = ["curry_stew", "salad", "drink_dessert"]
EXPECTED_HEADERS = ["画像", "料理名", "食材", "計", "エナジー"]

_TABLE_RE = re.compile(r"<table.*?</table>", re.S)
_TR_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
_TH_RE = re.compile(r"<th[^>]*>(.*?)</th>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_TOOLTIP_RE = re.compile(r'<span class="tooltip".*?</span>', re.S)
_LINK_TEXT_RE = re.compile(r'<a[^>]*class="rel-wiki-page"[^>]*>(.*?)</a>', re.S)


def fetch_html(url: str = WIKI_URL) -> str:
    parts = urllib.parse.urlsplit(url)
    url = urllib.parse.urlunsplit(parts._replace(path=urllib.parse.quote(parts.path)))
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def _text(cell_html: str) -> str:
    """ツールチップ（説明文）を落としてからタグを除去する。"""
    return unescape(_TAG_RE.sub("", _TOOLTIP_RE.sub("", cell_html))).strip()


def _recipe_name(cell_html: str) -> str:
    """料理名セル。食材名がリンクになっているので、リンクの中身も本文として拾う。"""
    return _text(cell_html)


def _ingredients(cell_html: str) -> list[dict]:
    """食材セル → [{"name": ..., "count": n}]。「食材名 ×個数」の並び。"""
    cleaned = _TOOLTIP_RE.sub("", cell_html)
    names = [unescape(_TAG_RE.sub("", m)).strip() for m in _LINK_TEXT_RE.findall(cleaned)]
    counts = [int(x) for x in re.findall(r"×\s*([0-9]+)", unescape(_TAG_RE.sub("", cleaned)))]
    return [
        {"name": name, "count": count}
        for name, count in zip(names, counts)
        if name and count > 0
    ]


def _column_index(table_html: str) -> dict[str, int]:
    headers = [_text(h) for h in _TH_RE.findall(table_html)]
    index = {h: i for i, h in enumerate(headers) if h in EXPECTED_HEADERS}
    missing = [h for h in EXPECTED_HEADERS if h not in index]
    if missing:
        raise RuntimeError(f"一覧表の列が見つからない: {missing} / 実ヘッダ: {headers}")
    return index


def find_recipe_tables(html: str) -> list[str]:
    """レシピ一覧表（カレー/サラダ/デザート）を出現順に返す。"""
    out = []
    for table in _TABLE_RE.findall(html):
        headers = [_text(h) for h in _TH_RE.findall(table)]
        if not all(h in headers for h in EXPECTED_HEADERS):
            continue
        # ヘッダだけの飾り表が同じ見出しで存在する。中身のある表だけ拾わないと
        # カテゴリの並び（カレー→サラダ→デザート）が1つずれる。
        if len(_TR_RE.findall(table)) < 5:
            continue
        out.append(table)
    if len(out) < len(CATEGORY_ORDER):
        raise RuntimeError(
            f"レシピ一覧表が {len(out)} 個しか見つからない（期待 {len(CATEGORY_ORDER)}）。"
            "Wikiの構造が変わった可能性あり。"
        )
    return out[: len(CATEGORY_ORDER)]


def parse_recipes(html: str) -> tuple[list[dict], list[str]]:
    records: list[dict] = []
    warnings: list[str] = []
    for category, table in zip(CATEGORY_ORDER, find_recipe_tables(html)):
        col = _column_index(table)
        need = max(col.values()) + 1
        for row_html in _TR_RE.findall(table):
            cells = _TD_RE.findall(row_html)
            if len(cells) < need:
                continue
            name = _recipe_name(cells[col["料理名"]])
            if not name or name.startswith("ごちゃまぜ"):
                continue  # ごちゃまぜ系はレシピではない（既存データも別建て）
            ings = _ingredients(cells[col["食材"]])
            if not ings:
                warnings.append(f"{name}: 食材セルをパースできない")
                continue
            total_text = _text(cells[col["計"]])
            energy_text = _text(cells[col["エナジー"]])
            try:
                total = int(re.sub(r"[^\d]", "", total_text))
            except ValueError:
                total = sum(i["count"] for i in ings)
                warnings.append(f"{name}: 合計をパースできない（食材から算出: {total}）")
            try:
                energy_lv1 = int(re.sub(r"[^\d]", "", energy_text))
            except ValueError:
                energy_lv1 = None
                warnings.append(f"{name}: エナジーをパースできない: {energy_text!r}")
            records.append({
                "name": name,
                "category": category,
                "ingredients": ings,
                "total_ingredients": total,
                "energy_lv1": energy_lv1,
            })
    return records, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="新レシピを書き込む")
    parser.add_argument("--html", help="取得済みHTMLファイル")
    args = parser.parse_args()

    if args.html:
        html = Path(args.html).read_text(encoding="utf-8")
    else:
        print(f"取得中: {WIKI_URL}\n")
        html = fetch_html()

    wiki, warnings = parse_recipes(html)
    import json

    local = json.loads(RECIPE_PATH.read_text(encoding="utf-8"))
    known = {r["name"]: r for r in local["records"]}
    print(f"Wiki掲載: {len(wiki)} 品 / ローカル: {len(known)} 品\n")

    if warnings:
        print(f"⚠ パース警告 ({len(warnings)}件):")
        for w in warnings[:20]:
            print(f"  - {w}")
        print()

    diffs = []
    for rec in wiki:
        cur = known.get(rec["name"])
        if cur is None:
            continue
        cur_total = cur.get("total_ingredients")
        if cur_total is not None and rec["total_ingredients"] != cur_total:
            diffs.append(
                f"  - {rec['name']}: 合計 {cur_total} → {rec['total_ingredients']}"
            )
    if diffs:
        print(f"△ 既存レシピで値が食い違う ({len(diffs)}件) — 自動では上書きしない:")
        print("\n".join(diffs) + "\n")

    new = [r for r in wiki if r["name"] not in known]
    if not new:
        print("★ 新レシピなし（マスタは最新）")
        return 0

    print(f"★ 新レシピ ({len(new)}品):")
    for rec in new:
        ings = " / ".join(f"{i['name']}×{i['count']}" for i in rec["ingredients"])
        print(
            f"  - [{rec['category']}] {rec['name']} 計{rec['total_ingredients']}"
            f" Lv1 {rec['energy_lv1']}en\n      {ings}"
        )

    if not args.apply:
        print("\n(dry-run) 追記するには --apply を付けて再実行。")
        return 0

    next_no = max((int(r.get("no") or 0) for r in local["records"]), default=0)
    for rec in new:
        next_no += 1
        add_recipe(
            name=rec["name"],
            category=rec["category"],
            no=next_no,
            ingredients=rec["ingredients"],
            total_ingredients=rec["total_ingredients"],
            energy_lv1=rec["energy_lv1"],
        )
    print(f"\n追記完了: {len(new)} 品 → data/recipe.json")
    print("⚠ Lv30/Lv60/なべ別のエナジーは一覧表に無いので未設定。")
    print("   recipe_level が Lv1 から換算するが、実値が要るなら別ページから補完すること。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
