#!/usr/bin/env python3
"""リサーチフィールドごとの出現ポケモンを wikiwiki から取得して data/field_encounters.json に保存する。

出典: https://wikiwiki.jp/poke_sleep/リサーチフィールド/<フィールド名>
各ページの「各カビゴン評価の詳細」表に載っている「出会えるようになるポケモン」を出現一覧として扱う。

使い方:
    python scripts/fetch_field_encounters.py            # 差分を表示するだけ
    python scripts/fetch_field_encounters.py --apply    # data/field_encounters.json を書き換える
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fetch_wiki_master import fetch_html  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "data" / "field_encounters.json"
BASE = "https://wikiwiki.jp/poke_sleep/リサーチフィールド/"
EX_BASE = "https://wikiwiki.jp/poke_sleep/リサーチフィールド/EXモード/"

NAME_ALIASES = {
    "ウパー(パルデアのすがた)": "ウパー(パルデア)",
    "ストリンダー(ハイなすがた)": "ストリンダー(ハイ)",
    "ストリンダー(ローなすがた)": "ストリンダー(ロー)",
}


def _txt(frag: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", frag)).split())


def parse_encounters(page_html: str, valid: set[str]) -> list[dict]:
    """各カビゴン評価の詳細表から出現種を返す。

    フィールドページには「好みきのみ対応ポケモン」や「きのみエナジー効率」など、
    No./名前/睡眠を含む別表もある。出現場所の根拠にするのは、リサーチ時に
    「出会えるようになるポケモン」として評価別に並ぶ表だけ。
    """
    master = _master_by_name(valid)
    rating_match = re.search(
        r'<h3[^>]*>\s*各カビゴン評価の詳細.*?</h3>(?P<body>.*?)(?:<h[23][^>]*>|$)',
        page_html,
        re.S,
    )
    if not rating_match:
        return []
    table_match = re.search(r"<table.*?</table>", rating_match.group("body"), re.S)
    if not table_match:
        return []

    rows = re.findall(r"<tr.*?</tr>", table_match.group(0), re.S)
    found: list[dict] = []
    seen: set[str] = set()
    for row in rows[2:]:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)
        if len(cells) < 7:
            continue
        for sleep_type, cell in zip(("うとうと", "すやすや", "ぐっすり"), cells[-3:]):
            for raw_name in _pokemon_names_in_cell(cell):
                name = NAME_ALIASES.get(raw_name, raw_name)
                if name not in valid or name in seen:
                    continue
                seen.add(name)
                p = master.get(name, {})
                found.append({
                    "species_name": name,
                    "dex_no": p.get("dex_no") or "",
                    "sleep_type": sleep_type,
                    "specialty": p.get("specialty") or "",
                })
    return found


def _pokemon_names_in_cell(cell_html: str) -> list[str]:
    """評価表の睡眠タイプ列から、リンク先titleのポケモン名だけを抜く。"""
    names = []
    for title in re.findall(r'<a [^>]*title="([^"]+)"[^>]*class="rel-wiki-page"', cell_html):
        name = html.unescape(title).strip()
        if name:
            names.append(name)
    return names


def _master_by_name(valid: set[str]) -> dict[str, dict]:
    master = json.loads((ROOT / "data" / "pokemon_master.json").read_text(encoding="utf-8"))
    by_name = {m["species_name"]: m for m in master["records"] if m["species_name"] in valid}
    return by_name


def parse_master_like_table(page_html: str, valid: set[str]) -> list[dict]:
    """旧パーサ。デバッグ用に残すが、出現表の根拠には使わない。"""
    found: list[dict] = []
    seen_all: set[str] = set()
    for tbl in re.findall(r"<table.*?</table>", page_html, re.S):
        rows = re.findall(r"<tr.*?</tr>", tbl, re.S)
        if len(rows) < 5:
            continue
        header = [_txt(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", rows[0], re.S)]
        if not ({"No.", "名前"} <= set(header)):
            continue
        i_no, i_name = header.index("No."), header.index("名前")
        i_sleep = header.index("睡眠") if "睡眠" in header else None
        i_spec = header.index("得意") if "得意" in header else None

        out: list[dict] = []
        seen = seen_all
        for r in rows[1:]:
            cells = [_txt(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S)]
            if len(cells) <= max(i_no, i_name):
                continue
            name = cells[i_name]
            if name not in valid or name in seen:
                continue
            seen.add(name)
            rec = {"species_name": name}
            dex = re.sub(r"\D", "", cells[i_no])
            if dex:
                rec["dex_no"] = dex
            if i_sleep is not None and len(cells) > i_sleep:
                rec["sleep_type"] = cells[i_sleep]
            if i_spec is not None and len(cells) > i_spec:
                rec["specialty"] = cells[i_spec]
            out.append(rec)
        found.extend(out)
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="JSONに書き込む")
    args = ap.parse_args()

    master = json.loads((ROOT / "data" / "pokemon_master.json").read_text(encoding="utf-8"))
    valid = {m["species_name"] for m in master["records"]}
    fields = json.loads((ROOT / "data" / "field.json").read_text(encoding="utf-8"))["records"]

    prev = {}
    if OUT_PATH.exists():
        prev = {r["field_name"]: r for r in
                json.loads(OUT_PATH.read_text(encoding="utf-8")).get("records", [])}

    records = []
    for f in fields:
        name = f["name"]
        url = (EX_BASE + name.replace(" ", "") if "EX" in name else BASE + name)
        page = None
        for attempt in range(4):
            try:
                page = fetch_html(url)
                break
            except Exception as e:  # pragma: no cover
                wait = 8 * (attempt + 1)
                print(f"  ..  {name}: {type(e).__name__} → {wait}秒待って再試行")
                time.sleep(wait)
        if page is None:
            print(f"  NG  {name}: 取得できず")
            continue
        enc = parse_encounters(page, valid)
        before = len(prev.get(name, {}).get("encounters", []))
        mark = "  " if before == len(enc) else f" (前回{before})"
        print(f"  OK  {name:14s} {len(enc):3d}種{mark}")
        records.append({"field_name": name, "source": url, "encounters": enc})
        time.sleep(4)   # wikiに負荷をかけない（429対策）

    total = sorted({e["species_name"] for r in records for e in r["encounters"]})
    print(f"\n合計 {len(records)}フィールド / のべ{sum(len(r['encounters']) for r in records)}件 "
          f"/ ユニーク{len(total)}種")
    missing = sorted(valid - set(total) - {n for n in valid if "(" in n})
    if missing:
        print(f"どのフィールドにも出現しない種: {len(missing)}種  {', '.join(missing[:12])}"
              + (" …" if len(missing) > 12 else ""))

    if args.apply:
        OUT_PATH.write_text(json.dumps(
            {"_meta": {"count": len(records), "source": BASE,
                       "note": "リサーチフィールド別の出現ポケモン。scripts/fetch_field_encounters.py で再取得。"},
             "records": records}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"→ {OUT_PATH}")
    else:
        print("(--apply で書き込み)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
