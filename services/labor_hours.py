"""勤務開始・終了・休憩から実働時間を集計する。

法令上限は固定しない。施設・職員ごとの業務上の上限設定との差分のみ示す。
必要な時刻・休憩が欠けている場合は推測せず incomplete とする。
明け・公休・有休は労働時間に含めない。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from data.calendar_period import period_bounds
from data.shift_symbols import symbol_to_key
from data.staffing_basis import get_staffing_basis_options
from data.time_coverage import to_minutes
from db.settings_repository import get_settings
from db.shift_repository import get_shifts_between
from db.staff_repository import list_staff

# 労働時間に含めない区分（明けの二重計上を防ぐ）
NON_LABOR_KEYS = frozenset({
    "morning_off",
    "off",
    "paid_leave",
    "half_leave",
    "training",
    "public",
})

WORK_BASE_KEYS = frozenset({"early", "day", "late", "night"})


def _parse_optional_hours(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        hours = float(value)
    except (TypeError, ValueError):
        return None
    if hours < 0:
        return None
    return hours


def _parse_break_minutes(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        return None
    if minutes < 0 or minutes > 24 * 60:
        return None
    return minutes


def gross_work_minutes(start_time: str, end_time: str) -> int | None:
    """開始・終了から総拘束分を返す。日付またぎにも対応。不正なら None。"""
    start_time = str(start_time or "").strip()
    end_time = str(end_time or "").strip()
    if not start_time or not end_time:
        return None
    try:
        start = to_minutes(start_time)
        end = to_minutes(end_time)
    except (TypeError, ValueError):
        return None
    if start == end:
        return None
    if end > start:
        return end - start
    # 日付またぎ（例: 16:30〜翌09:00）
    return (end + 24 * 60) - start


def net_work_minutes(start_time: str, end_time: str, break_minutes: int | None) -> tuple[int | None, str | None]:
    """実働分を返す。(minutes, incomplete_reason)。"""
    gross = gross_work_minutes(start_time, end_time)
    if gross is None:
        return None, "開始・終了時刻が不足または不正です"
    if break_minutes is None:
        return None, "休憩時間が未設定です（推測しません）"
    if break_minutes >= gross:
        return None, "休憩時間が勤務時間以上です"
    return gross - break_minutes, None


def _work_type_lookup(settings: dict) -> dict[str, dict]:
    return {item["key"]: item for item in get_staffing_basis_options(settings)}


def minutes_for_symbol(symbol: str, settings: dict, work_types: dict[str, dict] | None = None) -> dict:
    """1セル分の労働時間判定。"""
    key = symbol_to_key(symbol, settings)
    if not key:
        return {"status": "empty", "minutes": 0, "work_key": None, "reason": None}
    if key in NON_LABOR_KEYS:
        return {"status": "complete", "minutes": 0, "work_key": key, "reason": None}

    types = work_types or _work_type_lookup(settings)
    option = types.get(key)
    if option is None:
        # セミ系などがカタログに無い場合はベースキーで探す
        from data.staffing_basis import base_work_key

        base = base_work_key(key, settings)
        option = types.get(base)
        if option is None and base not in WORK_BASE_KEYS:
            return {
                "status": "complete",
                "minutes": 0,
                "work_key": key,
                "reason": None,
            }
        if option is None:
            return {
                "status": "incomplete",
                "minutes": None,
                "work_key": key,
                "reason": f"勤務区分「{key}」の開始・終了が未登録です",
            }

    break_minutes = _parse_break_minutes(option.get("break_minutes"))
    minutes, reason = net_work_minutes(
        str(option.get("start_time", "")),
        str(option.get("end_time", "")),
        break_minutes,
    )
    if minutes is None:
        return {
            "status": "incomplete",
            "minutes": None,
            "work_key": key,
            "reason": reason or "勤務時間が計算できません",
        }
    return {"status": "complete", "minutes": minutes, "work_key": key, "reason": None}


def _week_origin(first: date, week_start: str) -> date:
    offset = (first.weekday() + (1 if week_start == "sunday" else 0)) % 7
    return first - timedelta(days=offset)


def _resolve_limits(staff: dict, settings: dict) -> tuple[float | None, float | None]:
    weekly = _parse_optional_hours(staff.get("weekly_hour_limit"))
    if weekly is None:
        weekly = _parse_optional_hours(settings.get("default_weekly_hour_limit"))
    monthly = _parse_optional_hours(staff.get("monthly_hour_limit"))
    if monthly is None:
        monthly = _parse_optional_hours(settings.get("default_monthly_hour_limit"))
    return weekly, monthly


def summarize_labor_hours(year: int, month: int) -> dict:
    """表示期間の職員別・週別労働時間サマリ。"""
    settings = get_settings()
    start_day = settings.get("calendar_start_day", 1)
    period_start, period_end = period_bounds(year, month, start_day)
    week_start = settings.get("week_start", "sunday")
    origin = _week_origin(period_start, week_start)
    work_types = _work_type_lookup(settings)
    shifts = get_shifts_between(period_start, period_end)
    staff_list = list_staff()

    # 休憩未設定の勤務区分を施設全体の注意として列挙
    incomplete_types = []
    for item in work_types.values():
        if _parse_break_minutes(item.get("break_minutes")) is None:
            incomplete_types.append(item.get("label") or item.get("key"))

    staff_rows: list[dict] = []
    for person in staff_list:
        sid = person["id"]
        weekly_buckets: dict[int, dict] = {}
        period_minutes = 0
        incomplete: list[dict] = []
        complete = True

        day = period_start
        while day <= period_end:
            day_key = day.isoformat()
            cell = shifts.get((sid, day_key))
            symbol = ""
            if isinstance(cell, dict):
                symbol = cell.get("symbol") or ""
            elif cell:
                symbol = str(cell)
            if symbol:
                result = minutes_for_symbol(symbol, settings, work_types)
                week_num = (day - origin).days // 7 + 1
                bucket = weekly_buckets.setdefault(
                    week_num,
                    {
                        "week": week_num,
                        "start": (origin + timedelta(days=(week_num - 1) * 7)).isoformat(),
                        "end": (origin + timedelta(days=week_num * 7 - 1)).isoformat(),
                        "minutes": 0,
                        "status": "complete",
                        "incomplete": [],
                    },
                )
                if result["status"] == "incomplete":
                    complete = False
                    bucket["status"] = "incomplete"
                    note = {
                        "date": day_key,
                        "symbol": symbol,
                        "reason": result["reason"],
                    }
                    incomplete.append(note)
                    bucket["incomplete"].append(note)
                elif result["status"] == "complete" and result["minutes"]:
                    period_minutes += result["minutes"]
                    bucket["minutes"] += result["minutes"]
            day += timedelta(days=1)

        weekly_limit, monthly_limit = _resolve_limits(person, settings)
        weeks = []
        for week_num in sorted(weekly_buckets):
            bucket = weekly_buckets[week_num]
            hours = round(bucket["minutes"] / 60, 2) if bucket["status"] == "complete" else None
            over = None
            if (
                bucket["status"] == "complete"
                and weekly_limit is not None
                and hours is not None
            ):
                over = round(hours - weekly_limit, 2)
            weeks.append(
                {
                    **bucket,
                    "hours": hours,
                    "limit_hours": weekly_limit,
                    "diff_hours": over,
                }
            )

        period_hours = round(period_minutes / 60, 2) if complete else None
        period_diff = None
        if complete and monthly_limit is not None and period_hours is not None:
            period_diff = round(period_hours - monthly_limit, 2)

        staff_rows.append(
            {
                "staff_id": sid,
                "name": person.get("name", ""),
                "period_minutes": period_minutes if complete else None,
                "period_hours": period_hours,
                "period_status": "complete" if complete else "incomplete",
                "incomplete": incomplete,
                "weekly": weeks,
                "weekly_limit_hours": weekly_limit,
                "monthly_limit_hours": monthly_limit,
                "period_diff_hours": period_diff,
            }
        )

    return {
        "year": year,
        "month": month,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "default_weekly_hour_limit": _parse_optional_hours(settings.get("default_weekly_hour_limit")),
        "default_monthly_hour_limit": _parse_optional_hours(settings.get("default_monthly_hour_limit")),
        "incomplete_work_types": incomplete_types,
        "note": (
            "休憩時間が未設定の勤務区分があります。各種設定で休憩（分）を入力すると実働を確定できます。"
            if incomplete_types
            else "実働は開始・終了・休憩から計算します。明け・公休・有休は含みません。上限は施設の業務設定であり、法令適合の判定ではありません。"
        ),
        "staff": staff_rows,
    }
