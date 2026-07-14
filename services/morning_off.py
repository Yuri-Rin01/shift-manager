"""夜勤翌日の明け（morning_off）— 固定ルール。"""

from __future__ import annotations

from datetime import date, timedelta

from data.shift_symbols import get_shift_symbols, symbol_to_key
from db.shift_repository import delete_shift_cell, get_shifts_between, upsert_shift_cell

SEMI_TO_BASE = {
    "semi_early": "early",
    "semi_day": "day",
    "semi_late": "late",
    "semi_night": "night",
}

DAY_WORK_BASE_KEYS = frozenset({"early", "day", "late"})
LEAVE_KEYS = frozenset({"off", "paid_leave", "half_leave"})

# 設定画面のON/OFFに関わらず常に適用する固定ルール
MORNING_OFF_AFTER_NIGHT_FIXED = True
BLOCK_WORK_AFTER_NIGHT_FIXED = True


def _base_work_key(key: str) -> str:
    return SEMI_TO_BASE.get(key, key)


def morning_off_after_night_enabled(settings: dict | None = None) -> bool:
    return MORNING_OFF_AFTER_NIGHT_FIXED


def block_work_after_night_enabled(settings: dict | None = None) -> bool:
    return BLOCK_WORK_AFTER_NIGHT_FIXED


def morning_off_symbol(settings: dict | None = None) -> str | None:
    if not morning_off_after_night_enabled(settings):
        return None
    symbols = get_shift_symbols(settings)
    symbol = symbols.get("morning_off")
    return symbol if symbol else None


def is_night_work_symbol(symbol: str, settings: dict) -> bool:
    key = symbol_to_key(symbol, settings)
    if not key:
        return False
    return _base_work_key(key) == "night"


def is_morning_off_symbol(symbol: str, settings: dict) -> bool:
    return symbol_to_key(symbol, settings) == "morning_off"


def is_day_work_symbol(symbol: str, settings: dict) -> bool:
    key = symbol_to_key(symbol, settings)
    if not key or key in LEAVE_KEYS or key == "morning_off":
        return False
    return _base_work_key(key) in DAY_WORK_BASE_KEYS


def _next_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day) + timedelta(days=1)
    except ValueError:
        return None


def _prev_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day) - timedelta(days=1)
    except ValueError:
        return None


def _cell_result(staff_id: int, shift_date: date, symbol: str, source: str) -> dict:
    return {
        "staff_id": staff_id,
        "shift_date": shift_date.isoformat(),
        "symbol": symbol,
        "source": source,
    }


def _can_overwrite_with_morning_off(cell: dict | None, settings: dict) -> bool:
    if not cell:
        return True
    if cell.get("source") == "manual":
        return False
    symbol = cell.get("symbol", "")
    if not symbol:
        return True
    if is_morning_off_symbol(symbol, settings):
        return False
    key = symbol_to_key(symbol, settings)
    if key in {"paid_leave", "half_leave"}:
        return False
    return True


def would_block_day_work_after_night(
    staff_id: int,
    year: int,
    month: int,
    day: int,
    symbol: str,
    settings: dict,
) -> bool:
    """明けの翌日に日勤系を入れようとしているか。"""
    if not block_work_after_night_enabled(settings):
        return False
    if not is_day_work_symbol(symbol, settings):
        return False
    prev_day = _prev_date(year, month, day)
    if prev_day is None:
        return False
    existing = get_shifts_between(prev_day, prev_day)
    cell = existing.get((staff_id, prev_day.isoformat()))
    if not cell:
        return False
    return is_morning_off_symbol(cell.get("symbol", ""), settings)


def apply_morning_off_after_night(
    staff_id: int,
    year: int,
    month: int,
    day: int,
    symbol: str,
    settings: dict,
) -> list[dict]:
    """夜勤入力時に翌日を明けにする（固定ルール）。"""
    morning_symbol = morning_off_symbol(settings)
    if not morning_symbol or not is_night_work_symbol(symbol, settings):
        return []

    next_day = _next_date(year, month, day)
    if next_day is None:
        return []

    existing = get_shifts_between(next_day, next_day)
    cell = existing.get((staff_id, next_day.isoformat()))
    if not _can_overwrite_with_morning_off(cell, settings):
        return []

    saved = upsert_shift_cell(
        staff_id,
        next_day.year,
        next_day.month,
        next_day.day,
        morning_symbol,
        source="auto",
    )
    return [saved]


def clear_auto_morning_off_after_night(
    staff_id: int,
    year: int,
    month: int,
    day: int,
    new_symbol: str,
    settings: dict,
) -> list[dict]:
    """夜勤を外したとき、自動設定した翌日明けを解除する。"""
    if is_night_work_symbol(new_symbol, settings):
        return []

    next_day = _next_date(year, month, day)
    if next_day is None:
        return []

    existing = get_shifts_between(next_day, next_day)
    cell = existing.get((staff_id, next_day.isoformat()))
    if not cell:
        return []
    if cell.get("source") != "auto":
        return []
    if not is_morning_off_symbol(cell.get("symbol", ""), settings):
        return []

    if delete_shift_cell(staff_id, next_day):
        return [
            _cell_result(staff_id, next_day, "", "auto"),
        ]
    return []
