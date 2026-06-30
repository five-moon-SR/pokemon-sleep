"""ポケモンマスターデータ.txt（PukiWiki形式）を data/pokemon_master.json に変換する。

実行: python scripts/build_master.py

入力フォーマット例:
  |[[&icon(30,フシギダネ);>フシギダネ]]|0001|[[フシギダネ]]|BGCOLOR(#fff094):うとうと|食材
  |[[&icon(30,ドリのみ);&br;1>きのみ/ドリのみ]]
  |[[&icon(30,あまいミツ);&br;2,5,7>食材/あまいミツ]]
  |[[&icon(30,あんみんトマト);&br;4,7>食材/あんみんトマト]]
  |[[&icon(30,ほっこりポテト);&br;6>食材/ほっこりポテト]]
  |食材ゲットS|5|4400|

食材スロット仕様:
  スロット1（Lv1解放）: A確定
  スロット2（Lv30解放）: A or B 抽選
  スロット3（Lv60解放）: A or B or C 抽選
  → 食Aの数値は最大3個（slot1/2/3）、Bは最大2個（slot2/3）、Cは最大1個（slot3）。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INPUT = ROOT / "ポケモンマスターデータ.txt"
PROB_INPUT = ROOT / "ポケモン確率データ.txt"
OUTPUT = ROOT / "data" / "pokemon_master.json"

# 確率データ側の種族名 → マスター側の種族名 への正規化テーブル。
# 元サイトが違うと表記揺れがあるのでここで吸収する。
PROB_NAME_ALIASES: dict[str, str] = {
    "ハロウィンピカチュウ": "ピカチュウ(ハロウィン)",
    "ホリデーピカチュウ": "ピカチュウ(ホリデー)",
    "ロコン（アローラのすがた）": "ロコン(アローラ)",
    "キュウコン（アローラのすがた）": "キュウコン(アローラ)",
    "ホリデーイーブイ": "イーブイ(ホリデー)",
    "ハロウィンイーブイ": "イーブイ(ハロウィン)",
    "ウパー（パルデアの姿）": "ウパー(パルデア)",
    "タマザラシ（ホリデー）": "タマザラシ(ホリデー)",
    "ストリンダー（ローなすがた）": "ストリンダー(ロー)",
    "ストリンダー（ハイなすがた）": "ストリンダー(ハイ)",
    "バケッチャ（こだましゅ）": "バケッチャ(こだま)",
    "バケッチャ（ちゅうだましゅ）": "バケッチャ(ちゅうだま)",
    "バケッチャ（おおだましゅ）": "バケッチャ(おおだま)",
    "バケッチャ（ギガだましゅ）": "バケッチャ(ギガだま)",
    "パンプジン（こだましゅ）": "パンプジン(こだま)",
    "パンプジン（ちゅうだましゅ）": "パンプジン(ちゅうだま)",
    "パンプジン（おおだましゅ）": "パンプジン(おおだま)",
    "パンプジン（ギガだましゅ）": "パンプジン(ギガだま)",
}

# データ行は `|` で始まる。ただしヘッダ・書式行・閉じタグは除外する。
HEADER_PREFIXES = ("|~", "|SIZE", "|CENTER", "|RIGHT", "|LEFT")


def _strip_bgcolor(cell: str) -> str:
    """`BGCOLOR(xxx):中身` → `中身`、何もなければそのまま返す。"""
    return re.sub(r"^BGCOLOR\([^)]+\):(?:COLOR\([^)]+\):)?", "", cell)


def _extract_link_text(cell: str) -> str:
    """PukiWikiリンク `[[表示>リンク先]]` または `[[表示]]` から表示部を取り出す。

    `&br;` は除去（同名扱い）。リンクが無ければセルそのまま。
    """
    m = re.search(r"\[\[(.+?)\]\]", cell)
    text = m.group(1) if m else cell
    if ">" in text:
        text = text.split(">", 1)[0]
    return text.replace("&br;", "").strip()


def _parse_food_cell(cell: str) -> tuple[str, list[int]] | None:
    """食材セル `[[&icon(30,あまいミツ);&br;2,5,7>食材/あまいミツ]]` を (名前, [2,5,7]) に分解。

    空セルや不正な形式なら None。
    オール系の `2,7種変化` のような数値+文字列表記は、数値部分だけを抽出する。
    `&ref(...)` のひらめきのたね型セルは食材名が取れないので None。
    """
    cell = cell.strip()
    if not cell:
        return None
    name_match = re.search(r"&icon\(\s*\d+\s*,\s*([^)]+?)\s*\)", cell)
    if not name_match:
        return None
    name = name_match.group(1).strip()
    qty_segment = re.search(r"&br;([^>]*?)>", cell)
    if not qty_segment:
        return name, []
    qtys = [int(x) for x in re.findall(r"\d+", qty_segment.group(1))]
    return name, qtys


def _is_data_row(line: str) -> bool:
    if not line.startswith("|"):
        return False
    for prefix in HEADER_PREFIXES:
        if line.startswith(prefix):
            return False
    if line.endswith("|h") or line.endswith("|c"):
        return False
    return True


def parse_line(line: str) -> dict | None:
    """1行のデータ行をパースして dict を返す。データ行でなければ None。"""
    if not _is_data_row(line):
        return None

    # 末尾の `|` を落として split
    cells = line.strip().rstrip("|").split("|")[1:]
    if len(cells) < 12:
        return None

    icon_cell, dex_cell, name_cell, sleep_cell, specialty_cell = cells[0:5]
    berry_cell = cells[5]
    food_a_cell, food_b_cell, food_c_cell = cells[6:9]
    main_skill_cell = cells[9]
    # cells[10] = FP（不要）
    base_assist_cell = cells[11]

    species_name = _extract_link_text(_strip_bgcolor(name_cell))
    if not species_name:
        return None

    dex_no = _strip_bgcolor(dex_cell).strip()
    sleep_type = _strip_bgcolor(sleep_cell).strip()
    specialty = _strip_bgcolor(specialty_cell).strip()

    berry = _parse_food_cell(berry_cell)
    food_a = _parse_food_cell(food_a_cell)
    food_b = _parse_food_cell(food_b_cell)
    food_c = _parse_food_cell(food_c_cell)

    # メインスキルは Wiki link or 素のテキスト。&br; を除去して形を整える。
    main_skill = _extract_link_text(main_skill_cell) if "[[" in main_skill_cell else main_skill_cell.replace("&br;", "").strip()

    try:
        base_assist = int(base_assist_cell.strip())
    except ValueError:
        base_assist = None

    return {
        "dex_no": dex_no,
        "species_name": species_name,
        "sleep_type": sleep_type,
        "specialty": specialty,
        "berry": {
            "name": berry[0] if berry else None,
            "qty": berry[1][0] if berry and berry[1] else None,
        },
        "ingredients": {
            "a": {"name": food_a[0], "qty": food_a[1]} if food_a else None,
            "b": {"name": food_b[0], "qty": food_b[1]} if food_b else None,
            "c": {"name": food_c[0], "qty": food_c[1]} if food_c else None,
        },
        "main_skill": main_skill,
        "base_assist_seconds": base_assist,
    }


_SPECIALTIES = {"食材", "きのみ", "スキル", "オール"}


def parse_probability_data(text: str) -> tuple[dict[str, dict], list[str]]:
    """確率データテキストをパースして {種族名: {food_drop_rate, main_skill_rate}} を返す。

    各ポケモンは「種族名行 → 数値行 → 食A名行」の3行で構成。
    バケッチャ/パンプジン系のみ種族名行と数値行の間に空行が入るため、状態機械で読む。
    種族名行の判別: タブ分割した3列目が「食材/きのみ/スキル/オール」のどれか。

    返り値: (確率辞書, 警告ログのリスト)
    """
    probs: dict[str, dict] = {}
    warnings: list[str] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        cols = line.split("\t")
        is_header = len(cols) >= 3 and cols[2].strip() in _SPECIALTIES
        if not is_header:
            i += 1
            continue

        raw_name = cols[0].strip()
        name = PROB_NAME_ALIASES.get(raw_name, raw_name)

        # 次の非空行を数値行とみなす
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1

        if j >= len(lines):
            warnings.append(f"数値行が見つからない: {raw_name}")
            i += 1
            continue

        stats = lines[j].split("\t")
        if len(stats) < 4:
            warnings.append(f"数値行の列数不足: {raw_name}")
            i = j + 1
            continue

        try:
            probs[name] = {
                "food_drop_rate": float(stats[2]),
                "main_skill_rate": float(stats[3]),
            }
        except ValueError:
            warnings.append(f"数値パース失敗: {raw_name}")

        i = j + 1

    return probs, warnings


def build() -> dict:
    # メインのマスターデータをパース
    text = INPUT.read_text(encoding="utf-8")
    records: list[dict] = []
    seen_names: set[str] = set()
    skipped_dupes: list[str] = []

    for raw_line in text.splitlines():
        rec = parse_line(raw_line)
        if rec is None:
            continue
        name = rec["species_name"]
        if name in seen_names:
            skipped_dupes.append(name)
            continue
        seen_names.add(name)
        records.append(rec)

    # 確率データをマージ
    prob_warnings: list[str] = []
    matched = 0
    unmatched_in_prob: list[str] = []
    if PROB_INPUT.exists():
        prob_text = PROB_INPUT.read_text(encoding="utf-8")
        probs, prob_warnings = parse_probability_data(prob_text)

        for rec in records:
            name = rec["species_name"]
            if name in probs:
                rec["food_drop_rate"] = probs[name]["food_drop_rate"]
                rec["main_skill_rate"] = probs[name]["main_skill_rate"]
                matched += 1
            else:
                rec["food_drop_rate"] = None
                rec["main_skill_rate"] = None

        master_names = {r["species_name"] for r in records}
        unmatched_in_prob = [n for n in probs.keys() if n not in master_names]

    # add_pokemon.py と並びを統一（再生成と個別追加で差分が出ないように）
    records.sort(key=lambda r: (r["dex_no"], r["species_name"]))

    return {
        "records": records,
        "_meta": {
            "count": len(records),
            "skipped_duplicates": skipped_dupes,
            "probability_matched": matched,
            "probability_master_missing": [
                r["species_name"]
                for r in records
                if r.get("food_drop_rate") is None
            ],
            "probability_unmatched": unmatched_in_prob,
            "probability_warnings": prob_warnings,
        },
    }


def main() -> int:
    if not INPUT.exists():
        print(f"入力ファイルが見つかりません: {INPUT}", file=sys.stderr)
        return 1

    result = build()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    meta = result["_meta"]
    print(f"OK: {meta['count']} 種を {OUTPUT.relative_to(ROOT)} に書き出しました")
    if meta["skipped_duplicates"]:
        print(f"重複スキップ ({len(meta['skipped_duplicates'])}件): {meta['skipped_duplicates']}")
    if meta.get("probability_matched") is not None:
        print(f"確率データ突合: {meta['probability_matched']}/{meta['count']} 種")
        if meta["probability_master_missing"]:
            print(f"  確率データ未提供 ({len(meta['probability_master_missing'])}件): {meta['probability_master_missing']}")
        if meta["probability_unmatched"]:
            print(f"  突合できない確率データ ({len(meta['probability_unmatched'])}件): {meta['probability_unmatched']}")
        if meta["probability_warnings"]:
            print(f"  警告: {meta['probability_warnings']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
