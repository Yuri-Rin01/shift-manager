"""留学生労働時間の計算・上限判定（分単位・日本時間）。"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Iterable

from data.shift_symbols import symbol_to_key
from data.staffing_basis import DEFAULT_BREAK_MINUTES_BY_KEY, get_staffing_basis_options
from data.student_labor_limits import (
    PERMISSION_NO,
    PERMISSION_UNKNOWN,
    PERMISSION_YES,
    RESIDENCE_STATUS_STUDENT,
    WEEKDAY_INDEX,
    is_student_labor_restricted,
    normalize_student_labor_limits,
    normalize_student_labor_profile,
)

JST = timezone(timedelta(hours=9))

# 勤務区分の既定休憩（分）。設定に break_minutes があればそちら優先。
DEFAULT_BREAK_MINUTES = DEFAULT_BREAK_MINUTES_BY_KEY

LEAVE_OR_OFF_KEYS = frozenset(
    {
        "off",
        "public",
        "paid_leave",
        "morning_off",
        "am_off",
        "pm_off",
        "training",
        "special",
    }
)


def _parse_hhmm(value: str) -> int | None:
    text = str(value or "").strip()
    if len(text) != 5 or text[2] != ":":
        return None
    try:
        hour = int(text[:2])
        minute = int(text[3:])
    except ValueError:
        return None
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None
    return hour * 60 + minute


def net_work_minutes(start_time: str, end_time: str, break_minutes: int = 0) -> int | None:
    """1勤務の実労働時間（分）。時刻未設定は None。"""
    start = _parse_hhmm(start_time)
    end = _parse_hhmm(end_time)
    if start is None or end is None:
        return None
    span = end - start
    if span <= 0:
        span += 24 * 60
    return max(0, span - max(0, int(break_minutes)))


def split_shift_day_minutes(
    work_date: date,
    start_time: str,
    end_time: str,
    break_minutes: int = 0,
) -> list[tuple[date, int]]:
    """勤務を暦日ごとに分割した実労働分。週境界をまたぐ夜勤向け。"""
    start = _parse_hhmm(start_time)
    end = _parse_hhmm(end_time)
    if start is None or end is None:
        return []

    overnight = end <= start
    if not overnight:
        net = max(0, (end - start) - max(0, int(break_minutes)))
        return [(work_date, net)] if net else []

    day1_gross = 24 * 60 - start
    day2_gross = end
    gross = day1_gross + day2_gross
    break_left = max(0, int(break_minutes))
    # 休憩は勤務終盤（翌日側）から差し引く
    day2_net = max(0, day2_gross - min(break_left, day2_gross))
    break_left -= min(break_left, day2_gross)
    day1_net = max(0, day1_gross - break_left)
    result: list[tuple[date, int]] = []
    if day1_net:
        result.append((work_date, day1_net))
    if day2_net:
        result.append((work_date + timedelta(days=1), day2_net))
    # 合計が net_work_minutes と一致することを保証
    expected = max(0, gross - max(0, int(break_minutes)))
    actual = sum(m for _, m in result)
    if actual != expected and result:
        diff = expected - actual
        d, m = result[-1]
        result[-1] = (d, max(0, m + diff))
    return [(d, m) for d, m in result if m > 0]


def week_start_for(day: date, week_start: str = "monday") -> date:
    index = WEEKDAY_INDEX.get(str(week_start).lower(), 0)  # monday=0
    # Python: Monday=0 .. Sunday=6
    delta = (day.weekday() - index) % 7
    return day - timedelta(days=delta)


def week_range_containing(day: date, week_start: str = "monday") -> tuple[date, date]:
    start = week_start_for(day, week_start)
    return start, start + timedelta(days=6)


def is_long_vacation_day(day: date, profile: dict) -> bool:
    start = profile.get("long_vacation_start")
    end = profile.get("long_vacation_end")
    if not start or not end:
        return False
    try:
        start_d = date.fromisoformat(str(start))
        end_d = date.fromisoformat(str(end))
    except ValueError:
        return False
    if start_d > end_d:
        return False
    return start_d <= day <= end_d


def long_vacation_invalid(profile: dict) -> bool:
    start = profile.get("long_vacation_start")
    end = profile.get("long_vacation_end")
    if not start and not end:
        return False
    if bool(start) != bool(end):
        return True
    try:
        start_d = date.fromisoformat(str(start))
        end_d = date.fromisoformat(str(end))
    except ValueError:
        return True
    return start_d > end_d


def card_expired_on(profile: dict, on_day: date) -> bool:
    expires = profile.get("card_expires_on")
    if not expires:
        return False
    try:
        exp = date.fromisoformat(str(expires))
    except ValueError:
        return True
    return on_day > exp


def work_type_lookup(settings: dict | None) -> dict[str, dict]:
    options = get_staffing_basis_options(settings)
    return {item["key"]: item for item in options}


def break_minutes_for(work_key: str, option: dict | None = None) -> int:
    if option and option.get("break_minutes") is not None:
        try:
            return max(0, int(option["break_minutes"]))
        except (TypeError, ValueError):
            pass
    return int(DEFAULT_BREAK_MINUTES.get(work_key, 60))


def minutes_for_symbol(
    symbol: str,
    work_date: date,
    settings: dict | None,
    *,
    by_day: bool = False,
) -> int | list[tuple[date, int]]:
    """記号1件の実労働分。by_day=True なら [(date, minutes), ...]。"""
    key = symbol_to_key(symbol, settings)
    if not key or key in LEAVE_OR_OFF_KEYS:
        return [] if by_day else 0
    option = work_type_lookup(settings).get(key)
    if not option:
        return [] if by_day else 0
    start = option.get("start_time") or ""
    end = option.get("end_time") or ""
    brk = break_minutes_for(key, option)
    segments = split_shift_day_minutes(work_date, start, end, brk)
    if by_day:
        return segments
    return sum(m for _, m in segments)


def build_day_minutes_map(
    assignments: Iterable[tuple[date, str]],
    settings: dict | None,
) -> dict[date, int]:
    """自施設の日別実労働分。assignments: (work_date, symbol)。"""
    totals: dict[date, int] = {}
    for work_date, symbol in assignments:
        segments = minutes_for_symbol(symbol, work_date, settings, by_day=True)
        if isinstance(segments, list):
            for day, mins in segments:
                totals[day] = totals.get(day, 0) + mins
    return totals


def status_for_remaining(remaining_minutes: int, approach_minutes: int) -> str:
    if remaining_minutes < 0:
        return "over"
    if remaining_minutes == 0:
        return "reached"
    if remaining_minutes <= approach_minutes:
        return "approach"
    return "ok"


STATUS_LABELS = {
    "ok": "正常",
    "approach": "上限接近",
    "reached": "上限到達",
    "over": "超過",
    "need_confirm": "確認必要",
    "blocked": "配置不可",
}


def evaluate_eligibility(profile: dict, on_day: date) -> tuple[bool, str | None]:
    """勤務配置してよいか。False のとき理由コード。"""
    data = normalize_student_labor_profile(profile)
    if data["residence_status"] != RESIDENCE_STATUS_STUDENT:
        return True, None
    if not data["limit_enabled"]:
        return True, None
    if data["permission_status"] == PERMISSION_NO:
        return False, "permission_no"
    if data["permission_status"] == PERMISSION_UNKNOWN:
        return False, "permission_unknown"
    if data["permission_status"] != PERMISSION_YES:
        return False, "permission_unknown"
    if card_expired_on(data, on_day):
        return False, "card_expired"
    if long_vacation_invalid(data):
        return False, "vacation_invalid"
    return True, None


REASON_MESSAGES = {
    "permission_no": "資格外活動許可がありません",
    "permission_unknown": "資格外活動許可が未確認です",
    "card_expired": "在留カードまたは許可の有効期限が切れています",
    "vacation_invalid": "長期休業期間の登録内容が不正です",
    "missing_hours": "勤務時間または休憩時間が未設定です",
    "daily_over": "長期休業期間の1日上限を超えます",
    "weekly_over": "週の労働時間上限を超えます",
    "normal_weekly_over": "通常期間の週28時間上限を超えます",
    "vacation_weekly_over": "長期休業期間の週40時間上限を超えます",
}


def can_assign_shift(
    *,
    staff: dict,
    work_date: date,
    symbol: str,
    existing_assignments: Iterable[tuple[date, str]],
    settings: dict | None,
) -> tuple[bool, str | None, dict]:
    """
    割当可能か判定する。
    existing_assignments は対象職員の既存シフト（work_date, symbol）。今回分は含めない。
    """
    profile = normalize_student_labor_profile(
        staff.get("student_labor") or {},
        job_type=staff.get("job_type"),
    )
    limits = normalize_student_labor_limits((settings or {}).get("student_labor_limits"))
    detail = {
        "profile": profile,
        "limits": limits,
        "facility_week_minutes": 0,
        "other_job_weekly_minutes": profile["other_job_weekly_minutes"],
        "total_week_minutes": 0,
        "limit_week_minutes": limits["normal_weekly_minutes"],
        "remaining_minutes": 0,
        "period_mode": "normal",
        "status": "ok",
        "week_start": None,
        "week_end": None,
    }

    if not is_student_labor_restricted(profile):
        return True, None, detail

    ok, reason = evaluate_eligibility(profile, work_date)
    if not ok:
        detail["status"] = "blocked" if reason != "permission_unknown" else "need_confirm"
        return False, reason, detail

    key = symbol_to_key(symbol, settings)
    option = work_type_lookup(settings).get(key or "")
    if key and key not in LEAVE_OR_OFF_KEYS:
        if not option or not option.get("start_time") or not option.get("end_time"):
            detail["status"] = "blocked"
            return False, "missing_hours", detail

    added_segments = minutes_for_symbol(symbol, work_date, settings, by_day=True)
    if not isinstance(added_segments, list):
        added_segments = []

    # 日上限（長期休業日）
    day_map = build_day_minutes_map(existing_assignments, settings)
    for day, mins in added_segments:
        projected = day_map.get(day, 0) + mins
        if is_long_vacation_day(day, profile) and projected > limits["vacation_daily_minutes"]:
            detail["status"] = "over"
            detail["period_mode"] = "vacation"
            return False, "daily_over", detail

    week_start, week_end = week_range_containing(work_date, limits["week_start"])
    detail["week_start"] = week_start.isoformat()
    detail["week_end"] = week_end.isoformat()

    # 週合計（自施設）: 既存 + 追加分のうち週内
    week_minutes = 0
    for day, mins in day_map.items():
        if week_start <= day <= week_end:
            week_minutes += mins
    for day, mins in added_segments:
        if week_start <= day <= week_end:
            week_minutes += mins

    other = (
        int(profile["other_job_weekly_minutes"] or 0)
        if profile.get("has_other_job")
        else 0
    )
    total = week_minutes + other
    detail["facility_week_minutes"] = week_minutes
    detail["other_job_weekly_minutes"] = other
    detail["total_week_minutes"] = total

    # 週に通常期間の勤務が含まれるか／長期のみか
    has_normal = False
    has_vacation = False
    cursor = week_start
    while cursor <= week_end:
        if is_long_vacation_day(cursor, profile):
            has_vacation = True
        else:
            has_normal = True
        cursor += timedelta(days=1)

    if has_normal:
        detail["period_mode"] = "normal" if not has_vacation else "mixed"
        detail["limit_week_minutes"] = limits["normal_weekly_minutes"]
        if total > limits["normal_weekly_minutes"]:
            detail["remaining_minutes"] = limits["normal_weekly_minutes"] - total
            detail["status"] = "over"
            return False, "normal_weekly_over", detail
    else:
        detail["period_mode"] = "vacation"
        detail["limit_week_minutes"] = limits["vacation_weekly_minutes"]
        if total > limits["vacation_weekly_minutes"]:
            detail["remaining_minutes"] = limits["vacation_weekly_minutes"] - total
            detail["status"] = "over"
            return False, "vacation_weekly_over", detail

    remaining = detail["limit_week_minutes"] - total
    detail["remaining_minutes"] = remaining
    detail["status"] = status_for_remaining(remaining, limits["approach_remaining_minutes"])
    return True, None, detail


def summarize_staff_week(
    *,
    staff: dict,
    focus_day: date,
    assignments: Iterable[tuple[date, str]],
    settings: dict | None,
) -> dict:
    """留学生シート表示用の週サマリー。"""
    profile = normalize_student_labor_profile(
        staff.get("student_labor") or {},
        job_type=staff.get("job_type"),
    )
    limits = normalize_student_labor_limits((settings or {}).get("student_labor_limits"))
    week_start, week_end = week_range_containing(focus_day, limits["week_start"])
    day_map = build_day_minutes_map(assignments, settings)
    facility = sum(m for d, m in day_map.items() if week_start <= d <= week_end)
    other = int(profile["other_job_weekly_minutes"] or 0) if profile.get("has_other_job") else 0
    total = facility + other

    has_normal = False
    has_vacation = False
    cursor = week_start
    while cursor <= week_end:
        if is_long_vacation_day(cursor, profile):
            has_vacation = True
        else:
            has_normal = True
        cursor += timedelta(days=1)

    if not is_student_labor_restricted(profile):
        period_mode = "none"
        limit = 0
        status = "ok"
    elif has_normal:
        period_mode = "mixed" if has_vacation else "normal"
        limit = limits["normal_weekly_minutes"]
        status = status_for_remaining(limit - total, limits["approach_remaining_minutes"])
    else:
        period_mode = "vacation"
        limit = limits["vacation_weekly_minutes"]
        status = status_for_remaining(limit - total, limits["approach_remaining_minutes"])

    ok, reason = evaluate_eligibility(profile, focus_day)
    if is_student_labor_restricted(profile) and not ok:
        status = "need_confirm" if reason == "permission_unknown" else "blocked"

    remaining = (limit - total) if limit else 0
    period_label = {
        "none": "制限なし",
        "normal": "通常期間",
        "vacation": "長期休業期間",
        "mixed": "通常／長期混在",
    }.get(period_mode, period_mode)

    return {
        "staff_id": staff.get("id"),
        "name": staff.get("name"),
        "period_mode": period_mode,
        "period_label": period_label,
        "facility_week_minutes": facility,
        "other_job_weekly_minutes": other,
        "total_week_minutes": total,
        "limit_week_minutes": limit,
        "remaining_minutes": remaining,
        "status": status,
        "status_label": STATUS_LABELS.get(status, status),
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "reason": reason,
        "reason_label": REASON_MESSAGES.get(reason or "", ""),
    }


def summarize_staff_month(
    *,
    staff: dict,
    year: int,
    month: int,
    assignments: Iterable[tuple[date, str]],
    settings: dict | None,
) -> dict:
    """月別集計（確認用）。法令判定は日・週単位で別途行う。"""
    profile = normalize_student_labor_profile(
        staff.get("student_labor") or {},
        job_type=staff.get("job_type"),
    )
    limits = normalize_student_labor_limits((settings or {}).get("student_labor_limits"))
    day_map = build_day_minutes_map(assignments, settings)
    normal = 0
    vacation = 0
    for day, mins in day_map.items():
        if day.year != year or day.month != month:
            continue
        if is_long_vacation_day(day, profile):
            vacation += mins
        else:
            normal += mins

    other = int(profile["other_job_weekly_minutes"] or 0) if profile.get("has_other_job") else 0
    # 他勤務先は週単位のため、当該月に含まれる週数で概算（確認用）
    weeks_in_month = set()
    cursor = date(year, month, 1)
    if month == 12:
        month_end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        month_end = date(year, month + 1, 1) - timedelta(days=1)
    while cursor <= month_end:
        ws, _ = week_range_containing(cursor, limits["week_start"])
        weeks_in_month.add(ws)
        cursor += timedelta(days=1)
    other_month = other * len(weeks_in_month)

    warning_count = 0
    if is_student_labor_restricted(profile):
        for day, mins in day_map.items():
            if day.year != year or day.month != month:
                continue
            if is_long_vacation_day(day, profile) and mins > limits["vacation_daily_minutes"]:
                warning_count += 1
        for ws in weeks_in_month:
            we = ws + timedelta(days=6)
            facility = sum(m for d, m in day_map.items() if ws <= d <= we)
            total = facility + other
            has_normal = any(
                not is_long_vacation_day(ws + timedelta(days=i), profile) for i in range(7)
            )
            limit = (
                limits["normal_weekly_minutes"]
                if has_normal
                else limits["vacation_weekly_minutes"]
            )
            if total > limit:
                warning_count += 1
        ok, reason = evaluate_eligibility(profile, date(year, month, 1))
        if not ok:
            warning_count += 1

    return {
        "staff_id": staff.get("id"),
        "name": staff.get("name"),
        "year": year,
        "month": month,
        "normal_minutes": normal,
        "vacation_minutes": vacation,
        "other_job_minutes_estimate": other_month,
        "total_with_other_minutes": normal + vacation + other_month,
        "warning_count": warning_count,
        "normal_hours_label": format_hours(normal),
        "vacation_hours_label": format_hours(vacation),
        "total_with_other_hours_label": format_hours(normal + vacation + other_month),
    }


def format_hours(minutes: int) -> str:
    sign = "-" if minutes < 0 else ""
    m = abs(int(minutes))
    hours = m // 60
    mins = m % 60
    if mins:
        return f"{sign}{hours}時間{mins}分"
    return f"{sign}{hours}時間"


def today_jst() -> date:
    return datetime.now(JST).date()
