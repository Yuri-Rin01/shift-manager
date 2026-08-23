"""夜勤翌日の明け・休み（固定ルール）。

手動入力でも自動生成と同じく:
  夜勤 → 翌日「明け」 → その翌日「休み（公休）」
"""

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
# 明け翌日の休みを自動で置く（自動生成の rest 鎖と同等）
REST_AFTER_MORNING_OFF_FIXED = True

# DB上で連鎖休みを識別する source（解除時に誤って通常の公休を消さない）
CHAIN_REST_SOURCE = "rest"


def _base_work_key(key: str) -> str:
    return SEMI_TO_BASE.get(key, key)


def morning_off_after_night_enabled(settings: dict | None = None) -> bool:
    return MORNING_OFF_AFTER_NIGHT_FIXED


def block_work_after_night_enabled(settings: dict | None = None) -> bool:
    return BLOCK_WORK_AFTER_NIGHT_FIXED


def rest_after_morning_off_enabled(settings: dict | None = None) -> bool:
    return REST_AFTER_MORNING_OFF_FIXED


def morning_off_symbol(settings: dict | None = None) -> str | None:
    if not morning_off_after_night_enabled(settings):
        return None
    symbols = get_shift_symbols(settings)
    symbol = symbols.get("morning_off")
    return symbol if symbol else None


def off_symbol(settings: dict | None = None) -> str:
    symbols = get_shift_symbols(settings)
    return symbols.get("off") or "×"


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
    if cell.get("source") == "leave":
        return False
    symbol = cell.get("symbol", "")
    if not symbol:
        return True
    if is_morning_off_symbol(symbol, settings):
        return True  # 既に明けならそのまま確定扱いにする
    key = symbol_to_key(symbol, settings)
    if key in {"paid_leave", "half_leave"}:
        return False
    return True


def _can_overwrite_with_chain_rest(cell: dict | None, settings: dict) -> bool:
    """連鎖休み: 空セルか、自動生成の日勤／既に rest のセルだけ上書き。"""
    if not cell:
        return True
    if cell.get("source") in {"manual", "leave"}:
        return False
    symbol = cell.get("symbol", "")
    if not symbol:
        return True
    key = symbol_to_key(symbol, settings)
    if key in {"paid_leave", "half_leave"}:
        return False
    if cell.get("source") == CHAIN_REST_SOURCE:
        return True
    # 通常の公休（休み日数カウント）は潰さない
    if key == "off" and cell.get("source") != CHAIN_REST_SOURCE:
        return False
    if is_morning_off_symbol(symbol, settings):
        return False
    if is_night_work_symbol(symbol, settings):
        return False
    # 自動の日勤帯などは連鎖休みで上書き
    if cell.get("source") == "auto" and is_day_work_symbol(symbol, settings):
        return True
    return False


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


def apply_rest_after_morning_off(
    staff_id: int,
    morning_off_date: date,
    settings: dict,
) -> list[dict]:
    """明けの翌日を休み（公休・連鎖）にする。"""
    if not rest_after_morning_off_enabled(settings):
        return []
    rest_day = morning_off_date + timedelta(days=1)
    rest_sym = off_symbol(settings)
    existing = get_shifts_between(rest_day, rest_day)
    cell = existing.get((staff_id, rest_day.isoformat()))
    if cell and cell.get("source") == CHAIN_REST_SOURCE and cell.get("symbol") == rest_sym:
        return []
    if not _can_overwrite_with_chain_rest(cell, settings):
        return []
    saved = upsert_shift_cell(
        staff_id,
        rest_day.year,
        rest_day.month,
        rest_day.day,
        rest_sym,
        source=CHAIN_REST_SOURCE,
    )
    return [saved]


def apply_morning_off_after_night(
    staff_id: int,
    year: int,
    month: int,
    day: int,
    symbol: str,
    settings: dict,
) -> list[dict]:
    """夜勤入力時に翌日を明け、その翌日を休みにする（固定ルール）。"""
    morning_symbol = morning_off_symbol(settings)
    if not morning_symbol or not is_night_work_symbol(symbol, settings):
        return []

    next_day = _next_date(year, month, day)
    if next_day is None:
        return []

    existing = get_shifts_between(next_day, next_day)
    cell = existing.get((staff_id, next_day.isoformat()))
    results: list[dict] = []

    already_morning = bool(
        cell
        and is_morning_off_symbol(cell.get("symbol", ""), settings)
        and cell.get("source") != "manual"
    )

    if already_morning:
        results.extend(apply_rest_after_morning_off(staff_id, next_day, settings))
        return results

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
    results.append(saved)
    results.extend(apply_rest_after_morning_off(staff_id, next_day, settings))
    return results


def _clear_chain_rest_after(staff_id: int, morning_off_date: date) -> list[dict]:
    rest_day = morning_off_date + timedelta(days=1)
    existing = get_shifts_between(rest_day, rest_day)
    cell = existing.get((staff_id, rest_day.isoformat()))
    if not cell:
        return []
    if cell.get("source") != CHAIN_REST_SOURCE:
        return []
    if delete_shift_cell(staff_id, rest_day):
        return [_cell_result(staff_id, rest_day, "", CHAIN_REST_SOURCE)]
    return []


def clear_auto_morning_off_after_night(
    staff_id: int,
    year: int,
    month: int,
    day: int,
    new_symbol: str,
    settings: dict,
) -> list[dict]:
    """夜勤を外したとき、自動設定した明け・連鎖休みを解除する。"""
    if is_night_work_symbol(new_symbol, settings):
        return []

    next_day = _next_date(year, month, day)
    if next_day is None:
        return []

    results: list[dict] = []
    existing = get_shifts_between(next_day, next_day)
    cell = existing.get((staff_id, next_day.isoformat()))
    if cell and cell.get("source") == "auto" and is_morning_off_symbol(cell.get("symbol", ""), settings):
        if delete_shift_cell(staff_id, next_day):
            results.append(_cell_result(staff_id, next_day, "", "auto"))

    results.extend(_clear_chain_rest_after(staff_id, next_day))
    return results
