"""プレイヤーのプロフィール（リサーチランク・鍋容量・睡眠時間・食事タイミング）。

評価チェッカーやパーティ料理シミュレーションから共通参照される設定の窓口。
DB の user_settings (key-value) からロードし、PlayContext dataclass にまとめて返す。

key 命名規則: `user.<項目名>` で統一。

使い方:
    from utils.play_context import load_play_context, save_play_context
    ctx = load_play_context()
    print(ctx.pot_capacity, ctx.sleep_hours_weekday)
    save_play_context(ctx.with_updates(pot_capacity=507))
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any

import db


# ─────────────────────────────────────────────────────────────────────────
# キー定数
# ─────────────────────────────────────────────────────────────────────────
KEY_RESEARCH_RANK = "user.research_rank"
KEY_POT_CAPACITY = "user.pot_capacity"
KEY_SLEEP_WEEKDAY = "user.sleep_weekday_hours"
KEY_SLEEP_WEEKEND = "user.sleep_weekend_hours"
KEY_MEAL_BREAKFAST = "user.meal_breakfast"  # "HH:MM"
KEY_MEAL_LUNCH = "user.meal_lunch"
KEY_MEAL_DINNER = "user.meal_dinner"


# デフォルト値（起動直後でも動くように）
DEFAULTS: dict[str, Any] = {
    KEY_RESEARCH_RANK: 65,        # Ver.2.7.0時点の上限
    KEY_POT_CAPACITY: 69,         # 中間値はWiki未整備、recipe.json と整合させて 69 / 507 を想定
    KEY_SLEEP_WEEKDAY: 7.5,       # 平日の典型値
    KEY_SLEEP_WEEKEND: 9.0,       # 休日の典型値
    KEY_MEAL_BREAKFAST: "06:00",
    KEY_MEAL_LUNCH: "12:00",
    KEY_MEAL_DINNER: "18:00",
}


@dataclass(frozen=True)
class PlayContext:
    """プレイヤープロフィール（イミュータブル）。

    シミュ呼び出し時には with_updates() で部分書き換えしたコピーを渡す想定。
    """

    research_rank: int = 65
    pot_capacity: int = 69
    sleep_hours_weekday: float = 7.5
    sleep_hours_weekend: float = 9.0
    meal_breakfast: str = "06:00"
    meal_lunch: str = "12:00"
    meal_dinner: str = "18:00"

    @property
    def meal_times(self) -> list[str]:
        return [self.meal_breakfast, self.meal_lunch, self.meal_dinner]

    def active_hours(self, *, weekend: bool = False) -> float:
        """1日のおてつだい稼働時間（=24h - 睡眠時間）。"""
        sleep = self.sleep_hours_weekend if weekend else self.sleep_hours_weekday
        return max(0.0, 24.0 - float(sleep))

    def with_updates(self, **kwargs: Any) -> "PlayContext":
        return replace(self, **kwargs)

    def to_settings_dict(self) -> dict[str, Any]:
        """user_settings 用のキー名にマップした辞書を返す（保存時に使う）。"""
        return {
            KEY_RESEARCH_RANK: int(self.research_rank),
            KEY_POT_CAPACITY: int(self.pot_capacity),
            KEY_SLEEP_WEEKDAY: float(self.sleep_hours_weekday),
            KEY_SLEEP_WEEKEND: float(self.sleep_hours_weekend),
            KEY_MEAL_BREAKFAST: str(self.meal_breakfast),
            KEY_MEAL_LUNCH: str(self.meal_lunch),
            KEY_MEAL_DINNER: str(self.meal_dinner),
        }


def load_play_context() -> PlayContext:
    """DBの user_settings から PlayContext を組み立てる。未設定キーはデフォルト値。"""
    settings = db.get_all_settings()

    def _v(key: str) -> Any:
        return settings.get(key, DEFAULTS[key])

    return PlayContext(
        research_rank=int(_v(KEY_RESEARCH_RANK)),
        pot_capacity=int(_v(KEY_POT_CAPACITY)),
        sleep_hours_weekday=float(_v(KEY_SLEEP_WEEKDAY)),
        sleep_hours_weekend=float(_v(KEY_SLEEP_WEEKEND)),
        meal_breakfast=str(_v(KEY_MEAL_BREAKFAST)),
        meal_lunch=str(_v(KEY_MEAL_LUNCH)),
        meal_dinner=str(_v(KEY_MEAL_DINNER)),
    )


def save_play_context(ctx: PlayContext) -> None:
    """PlayContext を user_settings に書き込む（全項目 upsert）。"""
    for key, value in ctx.to_settings_dict().items():
        db.set_setting(key, value)
