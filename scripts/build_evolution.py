"""進化系列データを data/evolution.json に書き出す。

進化情報の生テキスト元（`貼り付けデータ集/進化データ.txt`）が空のため、
このスクリプトは外部参照で取得した進化系列をハードコードでJSON化する。

参照元: https://jara-blog.com/sleep_shinka  (取得日 2026-05-01)

実行: python scripts/build_evolution.py

スキーマ:
  records: [
    {
      "from": "フシギダネ",
      "to": "フシギソウ",
      "candy": 40,
      "conditions": {
        # 以下のキーが任意で含まれる:
        "min_level": int,         # 進化に必要な最低Lv
        "min_sleep_hours": int,   # 累計睡眠時間（仲間にしてからの）
        "items": [str, ...],      # 進化アイテム（複数同時所持必須あり）
        "time_of_day": "day"|"night",  # 進化時刻（日中6:00-17:59 / 夜間18:00-5:59）
        "gender": "male"|"female",     # 性別条件
      }
    }
  ]
  _meta: {count, source, fetched_at}

分岐進化（イーブイ等）は from が同一の records が複数並ぶ。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "data" / "evolution.json"
MASTER = ROOT / "data" / "pokemon_master.json"

SOURCE_URL = "https://jara-blog.com/sleep_shinka"
FETCHED_AT = "2026-05-01"


# 形式: (from, to, candy, conditions_dict)
# conditions の空辞書は「アメだけで進化（条件なし）」を意味する（現状該当なし）。
EVOLUTIONS: list[tuple[str, str, int, dict]] = [
    # --- 第1世代 ---
    ("フシギダネ", "フシギソウ", 40, {"min_level": 12}),
    ("フシギソウ", "フシギバナ", 80, {"min_level": 27}),
    ("ヒトカゲ", "リザード", 40, {"min_level": 12}),
    ("リザード", "リザードン", 80, {"min_level": 27}),
    ("ゼニガメ", "カメール", 40, {"min_level": 12}),
    ("カメール", "カメックス", 80, {"min_level": 27}),
    ("キャタピー", "トランセル", 40, {"min_level": 5}),
    ("トランセル", "バタフリー", 80, {"min_level": 8}),
    ("コラッタ", "ラッタ", 40, {"min_level": 15}),
    ("アーボ", "アーボック", 40, {"min_level": 17}),
    ("ピチュー", "ピカチュウ", 20, {"min_sleep_hours": 50}),
    ("ピカチュウ", "ライチュウ", 80, {"items": ["かみなりのいし"]}),
    ("ピィ", "ピッピ", 20, {"min_sleep_hours": 50}),
    ("ピッピ", "ピクシー", 80, {"items": ["つきのいし"]}),
    ("ロコン", "キュウコン", 80, {"items": ["ほのおのいし"]}),
    ("ロコン(アローラ)", "キュウコン(アローラ)", 80, {"items": ["こおりのいし"]}),
    ("ププリン", "プリン", 20, {"min_sleep_hours": 50}),
    ("プリン", "プクリン", 80, {"items": ["つきのいし"]}),
    ("ディグダ", "ダグトリオ", 40, {"min_level": 20}),
    ("ニャース", "ペルシアン", 40, {"min_level": 21}),
    ("コダック", "ゴルダック", 40, {"min_level": 25}),
    ("マンキー", "オコリザル", 40, {"min_level": 21}),
    ("ガーディ", "ウインディ", 80, {"items": ["ほのおのいし"]}),
    ("マダツボミ", "ウツドン", 40, {"min_level": 16}),
    ("ウツドン", "ウツボット", 80, {"items": ["リーフのいし"]}),
    ("イシツブテ", "ゴローン", 40, {"min_level": 19}),
    ("ゴローン", "ゴローニャ", 80, {"items": ["つながりのヒモ"]}),
    ("ヤドン", "ヤドラン", 40, {"min_level": 28}),
    ("ヤドン", "ヤドキング", 80, {"items": ["おうじゃのしるし", "つながりのヒモ"]}),
    ("コイル", "レアコイル", 40, {"min_level": 23}),
    ("レアコイル", "ジバコイル", 80, {"items": ["かみなりのいし"]}),
    ("ドードー", "ドードリオ", 40, {"min_level": 23}),
    ("ゴース", "ゴースト", 40, {"min_level": 19}),
    ("ゴースト", "ゲンガー", 80, {"items": ["つながりのヒモ"]}),
    ("イワーク", "ハガネール", 80, {"items": ["つながりのヒモ", "メタルコート"]}),
    ("カラカラ", "ガラガラ", 40, {"min_level": 21}),
    ("ピンプク", "ラッキー", 80, {"items": ["まんまるいし"], "time_of_day": "day"}),
    ("ラッキー", "ハピナス", 80, {"min_sleep_hours": 150}),
    ("マネネ", "バリヤード", 40, {"min_level": 12}),
    ("イーブイ", "シャワーズ", 80, {"items": ["みずのいし"]}),
    ("イーブイ", "サンダース", 80, {"items": ["かみなりのいし"]}),
    ("イーブイ", "ブースター", 80, {"items": ["ほのおのいし"]}),
    ("イーブイ", "エーフィ", 80, {"min_sleep_hours": 150, "time_of_day": "day"}),
    ("イーブイ", "ブラッキー", 80, {"min_sleep_hours": 150, "time_of_day": "night"}),
    ("イーブイ", "リーフィア", 80, {"items": ["リーフのいし"]}),
    ("イーブイ", "グレイシア", 80, {"items": ["こおりのいし"]}),
    ("イーブイ", "ニンフィア", 80, {"min_sleep_hours": 150}),
    ("ミニリュウ", "ハクリュー", 40, {"min_level": 23}),
    ("ハクリュー", "カイリュー", 100, {"min_level": 41}),

    # --- 第2世代 ---
    ("チコリータ", "ベイリーフ", 40, {"min_level": 12}),
    ("ベイリーフ", "メガニウム", 80, {"min_level": 27}),
    ("ヒノアラシ", "マグマラシ", 40, {"min_level": 12}),
    ("マグマラシ", "バクフーン", 80, {"min_level": 27}),
    ("ワニノコ", "アリゲイツ", 40, {"min_level": 12}),
    ("アリゲイツ", "オーダイル", 80, {"min_level": 27}),
    ("トゲピー", "トゲチック", 20, {"min_sleep_hours": 50}),
    ("トゲチック", "トゲキッス", 80, {"items": ["ひかりのいし"]}),
    ("メリープ", "モココ", 40, {"min_level": 11}),
    ("モココ", "デンリュウ", 80, {"min_level": 23}),
    ("ネイティ", "ネイティオ", 20, {"min_level": 17}),
    ("ウソハチ", "ウソッキー", 20, {"min_level": 12}),
    ("ウパー", "ヌオー", 40, {"min_level": 15}),
    ("ヤミカラス", "ドンカラス", 80, {"items": ["やみのいし"]}),
    ("ソーナノ", "ソーナンス", 20, {"min_level": 11}),
    ("ニューラ", "マニューラ", 80, {"items": ["するどいツメ"], "time_of_day": "night"}),
    ("デルビル", "ヘルガー", 40, {"min_level": 18}),
    ("ヨーギラス", "サナギラス", 40, {"min_level": 23}),
    ("サナギラス", "バンギラス", 100, {"min_level": 41}),

    # --- 第3世代 ---
    ("キモリ", "ジュプトル", 40, {"min_level": 12}),
    ("ジュプトル", "ジュカイン", 80, {"min_level": 27}),
    ("アチャモ", "ワカシャモ", 40, {"min_level": 12}),
    ("ワカシャモ", "バシャーモ", 80, {"min_level": 27}),
    ("ミズゴロウ", "ヌマクロー", 40, {"min_level": 12}),
    ("ヌマクロー", "ラグラージ", 80, {"min_level": 27}),
    ("ラルトス", "キルリア", 40, {"min_level": 15}),
    ("キルリア", "サーナイト", 80, {"min_level": 23}),
    ("キルリア", "エルレイド", 80, {"items": ["めざめいし"], "gender": "male"}),
    ("ナマケロ", "ヤルキモノ", 40, {"min_level": 14}),
    ("ヤルキモノ", "ケッキング", 80, {"min_level": 27}),
    ("ココドラ", "コドラ", 40, {"min_level": 24}),
    ("コドラ", "ボスゴドラ", 80, {"min_level": 32}),
    ("ゴクリン", "マルノーム", 40, {"min_level": 20}),
    ("ナックラー", "ビブラーバ", 40, {"min_level": 26}),
    ("ビブラーバ", "フライゴン", 80, {"min_level": 34}),
    ("チルット", "チルタリス", 40, {"min_level": 26}),
    ("カゲボウズ", "ジュペッタ", 40, {"min_level": 28}),
    ("タマザラシ", "トドグラー", 40, {"min_level": 24}),
    ("トドグラー", "トドゼルガ", 80, {"min_level": 33}),
    ("タツベイ", "コモルー", 40, {"min_level": 23}),
    ("コモルー", "ボーマンダ", 100, {"min_level": 38}),

    # --- 第4世代 ---
    ("コリンク", "ルクシオ", 40, {"min_level": 11}),
    ("ルクシオ", "レントラー", 80, {"min_level": 23}),
    ("フワンテ", "フワライド", 40, {"min_level": 21}),
    ("リオル", "ルカリオ", 80, {"min_sleep_hours": 150, "time_of_day": "day"}),
    ("グレッグル", "ドクロッグ", 40, {"min_level": 28}),
    ("ユキカブリ", "ユキノオー", 40, {"min_level": 30}),

    # --- 第5世代 ---
    ("ムンナ", "ムシャーナ", 80, {"items": ["つきのいし"]}),
    ("イシズマイ", "イワパレス", 40, {"min_level": 26}),
    ("ワシボン", "ウォーグル", 40, {"min_level": 41}),
    # バケッチャ/パンプジンは「だまサイズ」別に4形態あり、進化も同サイズ同士で対応する
    ("バケッチャ(おおだま)", "パンプジン(おおだま)", 80, {"items": ["つながりのヒモ"]}),
    ("バケッチャ(こだま)", "パンプジン(こだま)", 80, {"items": ["つながりのヒモ"]}),
    ("バケッチャ(ちゅうだま)", "パンプジン(ちゅうだま)", 80, {"items": ["つながりのヒモ"]}),
    ("バケッチャ(ギガだま)", "パンプジン(ギガだま)", 80, {"items": ["つながりのヒモ"]}),

    # --- 第7世代 ---
    ("アゴジムシ", "デンヂムシ", 40, {"min_level": 15}),
    ("デンヂムシ", "クワガノン", 80, {"items": ["かみなりのいし"]}),
    ("アブリー", "アブリボン", 40, {"min_level": 19}),
    ("ヌイコグマ", "キテルグマ", 40, {"min_level": 20}),

    # --- 第8世代 ---
    # ストリンダーはハイ/ローの2形態に分岐進化（本編では性格依存）
    ("エレズン", "ストリンダー(ハイ)", 80, {"min_level": 23}),
    ("エレズン", "ストリンダー(ロー)", 80, {"min_level": 23}),

    # --- 第9世代 ---
    ("ニャオハ", "ニャローテ", 40, {"min_level": 12}),
    ("ニャローテ", "マスカーニャ", 80, {"min_level": 27}),
    ("ホゲータ", "アチゲータ", 40, {"min_level": 12}),
    ("アチゲータ", "ラウドボーン", 80, {"min_level": 27}),
    ("クワッス", "ウェルカモ", 40, {"min_level": 12}),
    ("ウェルカモ", "ウェーニバル", 80, {"min_level": 27}),
    ("パモ", "パモット", 40, {"min_level": 14}),
    ("パモット", "パーモット", 80, {"min_sleep_hours": 150}),
    ("アルクジラ", "ハルクジラ", 80, {"items": ["こおりのいし"]}),
    ("ウパー(パルデア)", "ドオー", 40, {"min_level": 15}),
]


def _load_master_names() -> set[str]:
    if not MASTER.exists():
        return set()
    raw = json.loads(MASTER.read_text(encoding="utf-8"))
    return {r["species_name"] for r in raw.get("records", [])}


def build() -> dict:
    records = []
    for src, dst, candy, conditions in EVOLUTIONS:
        records.append(
            {
                "from": src,
                "to": dst,
                "candy": candy,
                "conditions": dict(conditions),
            }
        )
    return {
        "records": records,
        "_meta": {
            "count": len(records),
            "source": SOURCE_URL,
            "fetched_at": FETCHED_AT,
        },
    }


def main() -> int:
    result = build()

    # 整合性チェック: from/to の種族名がマスターに全部いるか
    master_names = _load_master_names()
    if master_names:
        missing: list[tuple[str, str]] = []
        for r in result["records"]:
            for key in ("from", "to"):
                if r[key] not in master_names:
                    missing.append((key, r[key]))
        if missing:
            print(
                "⚠️ マスターに見つからない種族名があります:",
                file=sys.stderr,
            )
            for key, name in missing:
                print(f"  - {key}: {name}", file=sys.stderr)
            print(
                "   pokemon_master.json の表記と揃えてください。",
                file=sys.stderr,
            )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"OK: {result['_meta']['count']} 件を {OUTPUT.relative_to(ROOT)} に書き出しました"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
