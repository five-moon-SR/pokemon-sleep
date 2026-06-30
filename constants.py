"""ポケスリ管理ツールの定数定義。

ユーザーの確認・修正が想定される値はここに集約しておく。
"""

DAIFUKU_RANKS: list[str] = ["増田", "SS", "S", "A", "B", "C", "D"]

# だいふくランクの視覚表示用カラー絵文字（高ランクほど暖色／伝説的に明るい）。
DAIFUKU_RANK_EMOJI: dict[str, str] = {
    "増田": "👑",
    "SS":  "🔴",
    "S":   "🟠",
    "A":   "🟡",
    "B":   "🟢",
    "C":   "🔵",
    "D":   "⚪",
}

# だいふくチェッカーの9項目評価。3×3行列（得意分野 × 寄り）。
# 配列の並びはだいふく公式サイトの表示順に準拠。
DAIFUKU_EVAL_LABELS: list[str] = [
    "①きのみ得意",
    "②食材型きのみ得意",
    "③スキル型きのみ得意",
    "④きのみ型食材得意",
    "⑤食材得意",
    "⑥スキル型食材得意",
    "⑦きのみ型スキル得意",
    "⑧食材型スキル得意",
    "⑨スキル得意",
]

EVOLUTION_STAGES: list[int] = [0, 1, 2]

SUBSKILL_UNLOCK_LEVELS: list[int] = [10, 25, 50, 75, 100]

DAIFUKU_CHECKER_URL: str = "https://www.pokemonsleepdaifuku.com/checker/"

# サブスキル選択肢（暫定）。data/subskill.json が整備されたら差し替える。
# 表記は「おてつだい」（ひらがな）／「睡眠EXPボーナス」を正とする。
# 旧表記（お手伝い／寝顔EXPボーナス／きのみ確率アップM）は normalize_subskill_name() で吸収。
SUBSKILL_OPTIONS: list[str] = [
    "きのみの数S",
    "食材確率アップS",
    "食材確率アップM",
    "スキル確率アップS",
    "スキル確率アップM",
    "スキルレベルアップS",
    "スキルレベルアップM",
    "おてつだいスピードS",
    "おてつだいスピードM",
    "おてつだいボーナス",
    "げんき回復ボーナス",
    "最大所持数アップS",
    "最大所持数アップM",
    "最大所持数アップL",
    "リサーチEXPボーナス",
    "睡眠EXPボーナス",
    "ゆめのかけらボーナス",
]

# サブスキルのレアリティ（金 > 青 > 白）。data/subskill.json 整備後はそちら参照に切替。
# キーは正規表記。get_subskill_rarity() 経由で旧表記も自動マッチする。
SUBSKILL_RARITY: dict[str, str] = {
    # 金スキル
    "きのみの数S": "gold",
    "スキルレベルアップM": "gold",
    "おてつだいボーナス": "gold",
    "げんき回復ボーナス": "gold",
    "リサーチEXPボーナス": "gold",
    "睡眠EXPボーナス": "gold",
    "ゆめのかけらボーナス": "gold",
    # 青スキル
    "スキルレベルアップS": "blue",
    "最大所持数アップL": "blue",
    "最大所持数アップM": "blue",
    "おてつだいスピードM": "blue",
    "食材確率アップM": "blue",
    "スキル確率アップM": "blue",
    # 白スキル
    "最大所持数アップS": "white",
    "おてつだいスピードS": "white",
    "食材確率アップS": "white",
    "スキル確率アップS": "white",
}

SUBSKILL_RARITY_ORDER: dict[str, int] = {"gold": 0, "blue": 1, "white": 2, "unknown": 9}
SUBSKILL_RARITY_LABELS: dict[str, str] = {"gold": "金", "blue": "青", "white": "白"}
SUBSKILL_RARITY_EMOJI: dict[str, str] = {
    "gold":    "🟡",
    "blue":    "🔵",
    "white":   "⚪",
    "unknown": "❔",
}

# サブスキルのたねによる強化先マップ。同名で末尾の S/M/L だけ上がる。
# 値は 1段階以上の強化先を昇順で並べたリスト。空 or 未掲載は強化不可（金スキル等）。
# キーは正規表記。get_subskill_upgrades() 経由で旧表記も自動マッチし、強化先は正規表記で返す。
SUBSKILL_UPGRADES: dict[str, list[str]] = {
    "スキル確率アップS": ["スキル確率アップM"],
    "スキルレベルアップS": ["スキルレベルアップM"],
    "食材確率アップS": ["食材確率アップM"],
    "おてつだいスピードS": ["おてつだいスピードM"],
    "最大所持数アップS": ["最大所持数アップM", "最大所持数アップL"],
    "最大所持数アップM": ["最大所持数アップL"],
}


def normalize_subskill_name(name: str | None) -> str | None:
    """サブスキル名の表記揺れを正規表記に揃える。

    - 「お手伝い〜」 → 「おてつだい〜」
    - 「寝顔EXPボーナス」 → 「睡眠EXPボーナス」
    None/空はそのまま返す。
    """
    if not name:
        return name
    n = name
    if n == "寝顔EXPボーナス":
        n = "睡眠EXPボーナス"
    if n.startswith("お手伝い"):
        n = "おてつだい" + n[len("お手伝い"):]
    return n


def get_subskill_rarity(name: str | None) -> str:
    """旧表記も含めてレアリティを返す。未登録は 'unknown'。"""
    if not name:
        return "unknown"
    return SUBSKILL_RARITY.get(normalize_subskill_name(name) or "", "unknown")


def get_subskill_upgrades(name: str | None) -> list[str]:
    """旧表記も含めて強化先リストを返す。強化不可は []。返り値は正規表記。"""
    if not name:
        return []
    return list(SUBSKILL_UPGRADES.get(normalize_subskill_name(name) or "", []))


# ---------------------------------------------------------------------------
# 性格（NATURES）
# ---------------------------------------------------------------------------
# 個体評価チェッカー v1 で使用する 25 種の性格補正テーブル。
#
# 軸:
#   speed             … おてつだい速度（速度倍率-1。正=高速化＝有利）
#   energy_recovery   … げんき回復量（倍率-1。正=回復増＝有利）
#   ingredient        … 食材おてつだい確率（倍率-1。正=確率UP＝有利。要検証値含む）
#   skill             … メインスキル発生確率（倍率-1。正=発生UP＝有利。要検証値含む）
#   exp               … EXP獲得量（倍率-1。正=獲得増＝有利）
#
# 値の出典: 公式倍率（おてスピ 1.11/0.93、げんき回復 1.2/0.88、食材確率 1.2/0.8、
# スキル発生 1.2/0.8、EXP 1.18/0.82）から「倍率-1」で算出。
# 補正のかからない軸はキー省略（get_nature_modifier() で 0.0 が返る）。
NATURE_AXES: tuple[str, ...] = ("speed", "energy_recovery", "ingredient", "skill", "exp")

NATURES: dict[str, dict[str, float]] = {
    # 無補正（上昇と下降が同じ軸で相殺）
    "がんばりや": {},
    "すなお": {},
    "てれや": {},
    "きまぐれ": {},
    "まじめ": {},
    # おてつだいスピード ↑
    "さみしがり": {"speed": +0.11, "energy_recovery": -0.12},
    "いじっぱり": {"speed": +0.11, "ingredient": -0.20},
    "やんちゃ":   {"speed": +0.11, "skill": -0.20},
    "ゆうかん":   {"speed": +0.11, "exp": -0.18},
    # げんき回復量 ↑
    "ずぶとい":   {"energy_recovery": +0.20, "speed": -0.07},
    "わんぱく":   {"energy_recovery": +0.20, "ingredient": -0.20},
    "のうてんき": {"energy_recovery": +0.20, "skill": -0.20},
    "のんき":     {"energy_recovery": +0.20, "exp": -0.18},
    # 食材おてつだい確率 ↑
    "ひかえめ":   {"ingredient": +0.20, "speed": -0.07},
    "おっとり":   {"ingredient": +0.20, "energy_recovery": -0.12},
    "うっかりや": {"ingredient": +0.20, "skill": -0.20},
    "れいせい":   {"ingredient": +0.20, "exp": -0.18},
    # メインスキル発生確率 ↑
    "おだやか":   {"skill": +0.20, "speed": -0.07},
    "おとなしい": {"skill": +0.20, "energy_recovery": -0.12},
    "しんちょう": {"skill": +0.20, "ingredient": -0.20},
    "なまいき":   {"skill": +0.20, "exp": -0.18},
    # EXP獲得量 ↑
    "おくびょう": {"exp": +0.18, "speed": -0.07},
    "せっかち":   {"exp": +0.18, "energy_recovery": -0.12},
    "ようき":     {"exp": +0.18, "ingredient": -0.20},
    "むじゃき":   {"exp": +0.18, "skill": -0.20},
}


def get_nature_modifier(name: str | None, axis: str) -> float:
    """性格による軸補正値を返す（正=有利、負=不利）。未登録/無補正/未定義軸は 0.0。"""
    if not name:
        return 0.0
    return NATURES.get(name, {}).get(axis, 0.0)


# 性格を上昇軸でグルーピング（UI 表示用 / register.py / edit_record.py 共有）。
# tuple[グループ名, 含まれる性格名のリスト] の順序＝表示順。
NATURE_AXIS_GROUPS: list[tuple[str, list[str]]] = [
    ("無補正", ["がんばりや", "すなお", "てれや", "きまぐれ", "まじめ"]),
    ("おてつだいスピード ↑", ["さみしがり", "いじっぱり", "やんちゃ", "ゆうかん"]),
    ("げんき回復 ↑", ["ずぶとい", "わんぱく", "のうてんき", "のんき"]),
    ("食材確率 ↑", ["ひかえめ", "おっとり", "うっかりや", "れいせい"]),
    ("メインスキル発生 ↑", ["おだやか", "おとなしい", "しんちょう", "なまいき"]),
    ("EXP獲得 ↑", ["おくびょう", "せっかち", "ようき", "むじゃき"]),
]

# 下降軸の表示ラベル（性格名の隣に「(げんき↓・食材↓)」のように併記する用途）。
NATURE_DOWN_AXIS_LABEL: dict[str, str] = {
    "speed": "おてスピ↓",
    "energy_recovery": "げんき↓",
    "ingredient": "食材↓",
    "skill": "スキル↓",
    "exp": "EXP↓",
}


def find_nature_axis(name: str | None) -> str | None:
    """性格名から所属する軸グループ名を返す。未登録は None。"""
    if not name:
        return None
    for label, natures in NATURE_AXIS_GROUPS:
        if name in natures:
            return label
    return None


def format_nature_label(name: str | None) -> str:
    """性格名 + 下降軸の併記。
    - None / 空 → "—"
    - NATURES に無い名前 → 名前そのまま
    - 無補正の5種 → "(無補正)" を付記
    - 通常 → "(げんき↓・食材↓)" 形式
    """
    if not name:
        return "—"
    if name not in NATURES:
        return str(name)
    mods = NATURES[name]
    downs = [NATURE_DOWN_AXIS_LABEL[ax] for ax, v in mods.items() if v < 0]
    if not downs:
        return f"{name}（無補正）"
    return f"{name}（{'・'.join(downs)}）"


# ---------------------------------------------------------------------------
# 個体評価チェッカー v1（utils/evaluator.py から参照）
# ---------------------------------------------------------------------------
EVALUATION_VERSION: str = "v1.3"

# 9 評価タイプの重み (α=きのみ, β=食材, γ=スキル)。DAIFUKU_EVAL_LABELS の番号と対応。
# 純粋型(①⑤⑨)=0.75/0.15/0.10、サブ寄り型=0.55/0.35/0.10、メイン軸最低0.10。
EVAL_TYPE_WEIGHTS: dict[int, tuple[float, float, float]] = {
    1: (0.75, 0.15, 0.10),
    2: (0.55, 0.35, 0.10),
    3: (0.55, 0.10, 0.35),
    4: (0.35, 0.55, 0.10),
    5: (0.15, 0.75, 0.10),
    6: (0.10, 0.55, 0.35),
    7: (0.35, 0.10, 0.55),
    8: (0.10, 0.35, 0.55),
    9: (0.10, 0.15, 0.75),
}

# 17 メインスキルカテゴリの主観係数。後でユーザー実プレイ感に合わせて調整可。
MAIN_SKILL_CATEGORY_COEF: dict[str, float] = {
    "エナジーチャージS":   1.20,
    "エナジーチャージM":   1.50,
    "ゆめのかけらゲットS": 1.30,
    "げんきエールS":       0.80,
    "げんきチャージS":     0.60,
    "げんきオールS":       1.10,
    "おてつだいサポートS": 1.20,
    "食材ゲットS":         1.00,
    "料理パワーアップS":   1.00,
    "ゆびをふる":          1.00,
    "料理チャンスS":       1.00,
    "おてつだいブースト":  1.40,
    "きのみバースト":      1.40,
    "スキルコピー":        1.00,
    "食材セレクトS":       1.00,
    "料理アシスト":        1.00,
    "オールマイティー":    1.50,
}

# 食材スロット A/B/C の重み。5:3:2 説は確証薄いため均等に倒す。
INGREDIENT_SLOT_RATIO: tuple[float, float, float] = (1 / 3, 1 / 3, 1 / 3)

# 装着サブスキルの加点（評価タイプ非依存の基本値）。キーは正規表記。
# 値は 2026-05-08 のだいふくキャリブレーション実測（specialty 別検証込み）に基づく。
# 「今週のカビゴンエナジー獲得への寄与」軸で評価。長期育成寄与（ゆめかけら等）は 0。
OPTION_BONUS_SUBSKILL: dict[str, float] = {
    "睡眠EXPボーナス":         3.0,   # 実測 +3.00（specialty 非依存）
    "げんき回復ボーナス":      2.5,   # 実測 +2.26（だいふく値の丸め）
    "ゆめのかけらボーナス":    0.0,   # 実測 ±0、整合ボーナスも無し
    "リサーチEXPボーナス":     0.0,   # 実測 ±0
    "おてつだいボーナス":     14.5,   # 実測 +14.5平均（specialty 非依存、加法的）
    "スキルレベルアップS":     3.0,   # 実測 +5（スキル特化 +2 込み）
    "スキルレベルアップM":     5.0,   # 実測 +10（スキル特化 +5 込み）
}

# 評価タイプ ⑦⑧⑨（スキル得意系）の場合にスキル系サブスキルへ上乗せする差分。
# 例: スキルLvUpM は通常 +5 → スキル得意 +10 になるので、ここでは +5 を加算。
OPTION_BONUS_SKILL_LVUP_EXTRA: dict[str, float] = {
    "スキルレベルアップS": 2.0,
    "スキルレベルアップM": 5.0,
}

# 性格の option_bonus（EXP軸の上下のみ加減点。他軸は species/global スコア側で吸収）。
OPTION_BONUS_NATURE: dict[str, float] = {
    "おくびょう": +3.0, "せっかち": +3.0, "ようき":   +3.0, "むじゃき": +3.0,
    "ゆうかん":   -5.0, "のんき":   -5.0, "れいせい": -5.0, "なまいき": -5.0,
}

OPTION_BONUS_RANGE: tuple[float, float] = (-10.0, 30.0)

# タイプ別「総合スコア%→ランク」閾値（だいふく公式準拠）。
# 各リストは [(下限%, ランク), ...] を高い順に並べる。
# 「増田」は SS のさらに上の伝説ランク。
RANK_THRESHOLDS_BY_TYPE: dict[int, list[tuple[float, str]]] = {
    1: [(100.0, "増田"), (90.0, "SS"), (77.0, "S"), (65.0, "A"), (50.0, "B"), (45.0, "C")],
    2: [(115.0, "増田"), (103.0, "SS"), (88.0, "S"), (74.0, "A"), (57.0, "B"), (51.0, "C")],
    3: [(115.0, "増田"), (103.0, "SS"), (88.0, "S"), (74.0, "A"), (57.0, "B"), (51.0, "C")],
    4: [(94.0, "増田"),  (83.0, "SS"), (67.0, "S"), (61.0, "A"), (56.0, "B"), (50.0, "C")],
    5: [(84.0, "増田"),  (74.0, "SS"), (60.0, "S"), (54.0, "A"), (50.0, "B"), (45.0, "C")],
    6: [(104.0, "増田"), (91.0, "SS"), (74.0, "S"), (66.0, "A"), (62.0, "B"), (55.0, "C")],
    7: [(84.0, "増田"),  (74.0, "SS"), (60.0, "S"), (54.0, "A"), (50.0, "B"), (45.0, "C")],
    8: [(84.0, "増田"),  (74.0, "SS"), (60.0, "S"), (54.0, "A"), (50.0, "B"), (45.0, "C")],
    9: [(84.0, "増田"),  (74.0, "SS"), (60.0, "S"), (54.0, "A"), (50.0, "B"), (45.0, "C")],
}


def score_to_rank(score: float, eval_type: int = 1) -> str:
    """総合スコア%（0〜130）と評価タイプから、だいふく公式準拠のランクを返す。

    タイプ未指定時はタイプ①の閾値で判定（最も保守的）。
    """
    thresholds = RANK_THRESHOLDS_BY_TYPE.get(int(eval_type), RANK_THRESHOLDS_BY_TYPE[1])
    for threshold, rank in thresholds:
        if score >= threshold:
            return rank
    return "D"


# メインスキルカテゴリの「味付け」: berry / skill / pure の3分類。
# 2026-05-08 だいふくキャリブレーションで判明:
#   - 食材系メインスキル（食材ゲット/食材セレクト/料理パワー/料理チャンス/料理アシスト）は
#     skill flavor 扱い（独立した food flavor は存在しない）
#   - team-buff 系（げんきエール/オール/チャージ・おてつだいサポート/ブースト・ゆびふる・スキルコピー・オールマイティー）
#     は rate に関係なく常に pure
#   - きのみバーストのみ rate 関係なく常に berry flavor
MAIN_SKILL_CATEGORY_FLAVOR: dict[str, str] = {
    "きのみバースト":      "berry",
    "エナジーチャージS":   "skill",
    "エナジーチャージM":   "skill",
    "ゆめのかけらゲットS": "skill",
    "食材ゲットS":         "skill",
    "食材セレクトS":       "skill",
    "料理パワーアップS":   "skill",
    "料理チャンスS":       "skill",
    "料理アシスト":        "skill",
    "げんきエールS":       "pure",
    "げんきチャージS":     "pure",
    "げんきオールS":       "pure",
    "おてつだいサポートS": "pure",
    "おてつだいブースト":  "pure",
    "ゆびをふる":          "pure",
    "スキルコピー":        "pure",
    "オールマイティー":    "pure",
}

# skill flavor が発動する main_skill_rate の下限（%）。これ未満は pure 扱い。
# キャリブ実測: ジバコイル 6.19% で発動 / オーダイル 5.5% で打ち消し。
# 中間データ無いためキリよく 6.0% に置く。
FLAVOR_RATE_THRESHOLD: float = 6.0

# (specialty, flavor) → eval_type マトリクス。
# 実在する組合せは ①③⑤⑥⑦⑨。②④⑧ は不可達（食材独立 flavor が無いため）。
_EVAL_TYPE_MATRIX: dict[tuple[str, str], int] = {
    ("きのみ", "berry"): 1, ("きのみ", "skill"): 3, ("きのみ", "pure"): 1,
    ("食材",   "berry"): 4, ("食材",   "skill"): 6, ("食材",   "pure"): 5,
    ("スキル", "berry"): 7, ("スキル", "skill"): 9, ("スキル", "pure"): 9,
}


# 評価タイプ自動推定（specialty + メインスキルカテゴリ + main_skill_rate → 1〜9）。
def infer_eval_type(
    specialty: str | None,
    main_skill_category: str | None = None,
    main_skill_rate: float | None = None,
) -> int:
    s = (specialty or "").strip()
    if s.startswith("きのみ"):
        primary = "きのみ"
    elif s.startswith("食材"):
        primary = "食材"
    elif s.startswith("スキル"):
        primary = "スキル"
    else:
        return 1
    flavor_raw = MAIN_SKILL_CATEGORY_FLAVOR.get(main_skill_category or "", "pure")
    # skill flavor は rate 閾値で発動判定。berry flavor / pure はそのまま。
    if flavor_raw == "skill" and (main_skill_rate or 0.0) < FLAVOR_RATE_THRESHOLD:
        flavor = "pure"
    else:
        flavor = flavor_raw
    return _EVAL_TYPE_MATRIX.get((primary, flavor), 1)
