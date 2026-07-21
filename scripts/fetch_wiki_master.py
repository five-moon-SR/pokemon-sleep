"""ポケモンスリープ攻略・検証Wiki の「ポケモンの一覧」から新ポケモンを自動検出する。

出典: https://wikiwiki.jp/poke_sleep/ポケモンの一覧 （HTMLテーブルをパース）

使い方:
  python scripts/fetch_wiki_master.py                 # dry-run: 差分レポートのみ（既定）
  python scripts/fetch_wiki_master.py --apply         # 新種族を add_pokemon 経由で追記
  python scripts/fetch_wiki_master.py --html FILE     # 取得済みHTMLを使う（デバッグ用）

方針:
- 手動運用（cron常駐しない）。Wikiには1リクエストだけ投げる。
- dry-run が既定。--apply でも「新規追加」だけを書き、既存レコードの上書きはしない
  （値の食い違いは差分レポートに出すので、直したい場合は会話で add_pokemon(overwrite=True)）。
- 確率データ（food_drop_rate / main_skill_rate）はこのページに無いので None で入れる
  （既存にも確率未掲載の種がある運用と同じ。build_master.py 参照）。
- 進化系列（evolution.json）は自動化しない。新種族の追加後に警告として案内する。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.add_pokemon import add_pokemon  # noqa: E402

MASTER_PATH = ROOT / "data" / "pokemon_master.json"
WIKI_URL = "https://wikiwiki.jp/poke_sleep/ポケモンの一覧"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

# Wiki側の種族名表記 → ローカルマスターの種族名表記。
# build_master.py の PROB_NAME_ALIASES と同じ役割（出典が違うので別テーブル）。
# 初回 dry-run の「名前が突合できない」報告を見て育てる。
WIKI_NAME_ALIASES: dict[str, str] = {}

_TABLE_RE = re.compile(r"<table.*?</table>", re.S)
_TR_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
_TH_RE = re.compile(r"<th[^>]*>(.*?)</th>", re.S)
_ALT_RE = re.compile(r'alt="([^"]+)"')
_TAG_RE = re.compile(r"<[^>]+>")

EXPECTED_HEADERS = ["No.", "名前", "睡眠", "得意", "木実", "食A", "食B", "食C", "メインスキル", "FP", "手伝"]


def fetch_html(url: str = WIKI_URL) -> str:
    # 日本語パスをパーセントエンコード（urllib は生の非ASCII URLを送れない）
    parts = urllib.parse.urlsplit(url)
    url = urllib.parse.urlunsplit(parts._replace(path=urllib.parse.quote(parts.path)))
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def _cell_text(cell_html: str) -> str:
    """タグを除去してプレーンテキストを取り出す。"""
    return unescape(_TAG_RE.sub("", cell_html)).strip()


def _parse_item_cell(cell_html: str) -> tuple[str, list[int]] | None:
    """きのみ/食材セルをパース。img の alt がアイテム名、テキストが個数リスト。

    例: alt="あまいミツ" + テキスト "2,5,7" → ("あまいミツ", [2, 5, 7])
    空セル（食B/Cが無いポケモン）は None。
    「2,7種変化」のようなオール系表記は数値部分だけを拾う。
    """
    alt = _ALT_RE.search(cell_html)
    if not alt:
        return None
    name = unescape(alt.group(1)).strip()
    # 空セルはspacer.gif、ミュウ等の「ひらめきのたね」は画像ファイル名のaltになる。
    # ローカルマスターはどちらも None 扱い（build_master._parse_food_cell と同じ方針）。
    if "." in name:
        return None
    qtys = [int(x) for x in re.findall(r"\d+", _cell_text(cell_html))]
    return name, qtys


def find_pokemon_table(html: str) -> str:
    """全<table>から「No./名前/睡眠/…」ヘッダを持つ一覧表を特定する。"""
    for table in _TABLE_RE.findall(html):
        headers = [_cell_text(h) for h in _TH_RE.findall(table)]
        if all(h in headers for h in EXPECTED_HEADERS):
            return table
    raise RuntimeError(
        "ポケモン一覧テーブルが見つからない。Wikiのページ構造が変わった可能性あり。"
        f" 期待ヘッダ: {EXPECTED_HEADERS}"
    )


def parse_rows(table_html: str) -> tuple[list[dict], list[str]]:
    """一覧表の各行を pokemon_master.json のレコード形式にパースする。

    返り値: (レコードのリスト, 警告のリスト)
    列: 画像 | No. | 名前 | 睡眠 | 得意 | 木実 | 食A | 食B | 食C | メインスキル | FP | 手伝
    """
    records: list[dict] = []
    warnings: list[str] = []

    for row_html in _TR_RE.findall(table_html):
        cells = _TD_RE.findall(row_html)
        if len(cells) < 12:
            continue  # ヘッダ行（th）や区切り行

        raw_name = _cell_text(cells[2])
        if not raw_name:
            continue
        name = WIKI_NAME_ALIASES.get(raw_name, raw_name)

        dex_no = _cell_text(cells[1])
        sleep_type = _cell_text(cells[3])
        specialty = _cell_text(cells[4])
        berry = _parse_item_cell(cells[5])
        food_a = _parse_item_cell(cells[6])
        food_b = _parse_item_cell(cells[7])
        food_c = _parse_item_cell(cells[8])
        main_skill = _cell_text(cells[9])

        try:
            base_assist = int(re.sub(r"[^\d]", "", _cell_text(cells[11])))
        except ValueError:
            base_assist = None
            warnings.append(f"{name}: 手伝時間がパースできない: {_cell_text(cells[11])!r}")

        if not berry:
            warnings.append(f"{name}: きのみセルがパースできない（スキップ）")
            continue
        if not food_a:
            warnings.append(f"{name}: 食Aセルがパースできない（スキップ）")
            continue

        records.append(
            {
                "dex_no": dex_no,
                "species_name": name,
                "sleep_type": sleep_type,
                "specialty": specialty,
                "berry": {"name": berry[0], "qty": berry[1][0] if berry[1] else None},
                "ingredients": {
                    "a": {"name": food_a[0], "qty": food_a[1]},
                    "b": {"name": food_b[0], "qty": food_b[1]} if food_b else None,
                    "c": {"name": food_c[0], "qty": food_c[1]} if food_c else None,
                },
                "main_skill": main_skill,
                "base_assist_seconds": base_assist,
            }
        )

    return records, warnings


def check_reference_masters(new_records: list[dict]) -> list[str]:
    """新種族が参照するきのみ/食材/メインスキルが既存マスターに居るか確認する。

    居ないものは期待値計算(food_expectation/berry_energy/skill_effects)が
    落ちるか0扱いになるので、add_berry / add_ingredient / add_main_skill の案内を出す。
    """
    def _names(path: Path) -> set[str]:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {r["name"] for r in data["records"]}

    berries = _names(ROOT / "data" / "berry.json")
    ingredients = _names(ROOT / "data" / "ingredient.json")
    skill_data = json.loads((ROOT / "data" / "main_skill.json").read_text(encoding="utf-8"))
    skills = {r["name"] for r in skill_data["records"]}
    skill_categories = {r["category"] for r in skill_data["records"]}

    def _skill_known(skill: str) -> bool:
        """完全一致 or 「固有名(カテゴリ)」の括弧内カテゴリで解決できればOK（既存55種と同じ規約）。"""
        if skill in skills:
            return True
        m = re.search(r"\(([^)]+)\)$", skill)
        return bool(m) and m.group(1) in skill_categories

    issues: list[str] = []
    for r in new_records:
        if r["berry"]["name"] not in berries:
            issues.append(f"{r['species_name']}: 未知のきのみ {r['berry']['name']!r} → add_berry が必要")
        for slot in ("a", "b", "c"):
            ing = r["ingredients"].get(slot)
            if ing and ing["name"] not in ingredients:
                issues.append(f"{r['species_name']}: 未知の食材 {ing['name']!r} → add_ingredient が必要")
        if not _skill_known(r["main_skill"]):
            issues.append(f"{r['species_name']}: 未知のメインスキル {r['main_skill']!r} → add_main_skill + skill_effects.py 追記が必要")
    return issues


def _field_diffs(local: dict, wiki: dict) -> list[str]:
    """既存種族の値の食い違いを「フィールド: ローカル → Wiki」形式で列挙する。"""
    diffs: list[str] = []
    for key in ("dex_no", "sleep_type", "specialty", "main_skill", "base_assist_seconds"):
        if local.get(key) != wiki.get(key):
            diffs.append(f"{key}: {local.get(key)!r} → {wiki.get(key)!r}")
    if local["berry"]["name"] != wiki["berry"]["name"]:
        diffs.append(f"berry: {local['berry']['name']!r} → {wiki['berry']['name']!r}")
    for slot in ("a", "b", "c"):
        lv, wv = local["ingredients"].get(slot), wiki["ingredients"].get(slot)
        if (lv or None) != (wv or None):
            diffs.append(f"ingredients.{slot}: {lv} → {wv}")
    return diffs


def diff_master(wiki_records: list[dict]) -> dict:
    data = json.loads(MASTER_PATH.read_text(encoding="utf-8"))
    local_by_name = {r["species_name"]: r for r in data["records"]}
    wiki_by_name = {r["species_name"]: r for r in wiki_records}

    new_records = [r for n, r in wiki_by_name.items() if n not in local_by_name]
    missing_on_wiki = sorted(n for n in local_by_name if n not in wiki_by_name)
    changed = {
        n: d
        for n, r in wiki_by_name.items()
        if n in local_by_name and (d := _field_diffs(local_by_name[n], r))
    }
    return {
        "new": sorted(new_records, key=lambda r: (r["dex_no"], r["species_name"])),
        "missing_on_wiki": missing_on_wiki,
        "changed": changed,
        "local_count": len(local_by_name),
        "wiki_count": len(wiki_by_name),
    }


def apply_new(new_records: list[dict]) -> tuple[list[str], list[str]]:
    """新種族を add_pokemon()（既存の検証ロジック）経由で追記する。"""
    added: list[str] = []
    failed: list[str] = []
    for r in new_records:
        try:
            add_pokemon(
                dex_no=r["dex_no"],
                species_name=r["species_name"],
                sleep_type=r["sleep_type"],
                specialty=r["specialty"],
                berry_name=r["berry"]["name"],
                berry_qty=r["berry"]["qty"],
                ingredient_a=r["ingredients"]["a"],
                ingredient_b=r["ingredients"]["b"],
                ingredient_c=r["ingredients"]["c"],
                main_skill=r["main_skill"],
                base_assist_seconds=r["base_assist_seconds"],
            )
            added.append(r["species_name"])
        except (ValueError, TypeError) as e:
            failed.append(f"{r['species_name']}: {e}")
    return added, failed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="新種族をマスターに追記する（既定はdry-run）")
    ap.add_argument("--html", type=Path, help="取得済みHTMLファイルを使う（Wikiにアクセスしない）")
    args = ap.parse_args()

    if args.html:
        html = args.html.read_text(encoding="utf-8")
        print(f"ローカルHTMLを使用: {args.html}")
    else:
        print(f"取得中: {WIKI_URL}")
        html = fetch_html()

    table = find_pokemon_table(html)
    wiki_records, warnings = parse_rows(table)
    report = diff_master(wiki_records)

    print(f"\nWiki掲載: {report['wiki_count']} 種 / ローカル: {report['local_count']} 種")

    if warnings:
        print(f"\n⚠ パース警告 ({len(warnings)}件):")
        for w in warnings:
            print(f"  - {w}")

    if report["missing_on_wiki"]:
        print(f"\n⚠ ローカルにあってWikiで突合できない種族 ({len(report['missing_on_wiki'])}件) — 表記揺れなら WIKI_NAME_ALIASES に追加:")
        for n in report["missing_on_wiki"]:
            print(f"  - {n}")

    if report["changed"]:
        print(f"\n△ 値が食い違う既存種族 ({len(report['changed'])}件) — 自動では上書きしない:")
        for n, diffs in report["changed"].items():
            print(f"  - {n}")
            for d in diffs:
                print(f"      {d}")

    if not report["new"]:
        print("\n✅ 新ポケモンなし。マスターは最新。")
        return 0

    ref_issues = check_reference_masters(report["new"])
    if ref_issues:
        print(f"\n⚠ 参照マスター不足 ({len(ref_issues)}件) — 追記後も期待値計算が不完全になる:")
        for issue in ref_issues:
            print(f"  - {issue}")

    print(f"\n★ 新ポケモン ({len(report['new'])}件):")
    for r in report["new"]:
        ings = " / ".join(
            f"{s}:{v['name']}{v['qty']}"
            for s, v in r["ingredients"].items()
            if v
        )
        print(
            f"  - {r['dex_no']} {r['species_name']} [{r['sleep_type']}/{r['specialty']}] "
            f"きのみ:{r['berry']['name']}x{r['berry']['qty']} {ings} "
            f"skill:{r['main_skill']} 手伝:{r['base_assist_seconds']}s"
        )

    if not args.apply:
        print("\n(dry-run) 追記するには --apply を付けて再実行。")
        return 0

    added, failed = apply_new(report["new"])
    print(f"\n追記完了: {len(added)} 件 → {MASTER_PATH.relative_to(ROOT)}")
    if failed:
        print(f"⚠ 追記失敗 ({len(failed)}件):")
        for f in failed:
            print(f"  - {f}")
    if added:
        print("\n⚠ 忘れずに: 追加種族の確率データ(food_drop_rate等)は未設定(None)。")
        print("⚠ 進化系列がある場合は evolution.json への追記も必要（scripts/add_evolution.py を会話で）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
