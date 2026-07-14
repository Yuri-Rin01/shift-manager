from __future__ import annotations

from datetime import date

from data.calendar_period import build_period_days, format_period_label, period_bounds
from data.leave_request_config import (
    check_request_limits,
    get_portal_request_options,
    normalize_leave_request_settings,
    resolve_max_total_for_period,
)
from db import leave_request_repository as leave_repo
from db.staff_repository import get_staff, list_staff


def list_portal_staff() -> list[dict]:
    return [
        {
            "id": staff["id"],
            "name": staff["name"],
            "departments": staff.get("departments") or [staff.get("department", "")],
            "job_type": staff["job_type"],
        }
        for staff in list_staff()
    ]


def _build_limit_info(
    staff_id: int,
    staff_name: str,
    year: int,
    month: int,
    period_start: date,
    period_end: date,
    settings: dict,
) -> dict:
    leave_cfg = normalize_leave_request_settings(settings)
    counts = leave_repo.count_active_requests_by_staff(staff_id, period_start, period_end)
    total = sum(counts.values())
    max_total = resolve_max_total_for_period(settings, year, month)
    over_limit_message = check_request_limits(
        counts,
        settings=settings,
        year=year,
        month=month,
        staff_name=staff_name,
    )
    return {
        "counts": counts,
        "total": total,
        "max_total": max_total,
        "max_by_type": leave_cfg["leave_request_max_by_type"],
        "is_over_limit": over_limit_message is not None,
        "over_limit_message": over_limit_message or "",
    }


def build_portal_calendar(staff_id: int, year: int, month: int) -> dict:
    staff = get_staff(staff_id)
    if staff is None:
        raise ValueError("職員が見つかりません。")

    from db.settings_repository import get_settings

    settings = get_settings()
    start_day = int(settings.get("calendar_start_day", 1) or 1)
    period_start, period_end = period_bounds(year, month, start_day)
    days = build_period_days(year, month, start_day, week_start=settings.get("week_start", "sunday"))
    requests = leave_repo.list_requests_for_staff_between(staff_id, period_start, period_end)

    today = date.today()
    deadline_day = int(settings.get("deadline_day_of_month", 20) or 20)
    deadline_day = max(1, min(28, deadline_day))
    is_past_deadline = today.day > deadline_day and today.year == year and today.month == month

    request_by_date = {item["shift_date"]: item for item in requests}
    day_rows = []
    for item in days:
        request = request_by_date.get(item["date"])
        day_rows.append(
            {
                **item,
                "is_past": date.fromisoformat(item["date"]) < today,
                "request": request,
            }
        )

    limit_info = _build_limit_info(
        staff_id,
        staff["name"],
        year,
        month,
        period_start,
        period_end,
        settings,
    )

    return {
        "staff_id": staff_id,
        "staff_name": staff["name"],
        "year": year,
        "month": month,
        "period_label": format_period_label(
            period_start, period_end, year=year, month=month, start_day=start_day
        ),
        "deadline_day_of_month": deadline_day,
        "is_past_deadline": is_past_deadline,
        "request_options": get_portal_request_options(settings),
        "days": day_rows,
        "requests": requests,
        "limit_info": limit_info,
    }


def save_leave_request(staff_id: int, shift_date: date, request_type: str, *, note: str = "") -> dict:
    staff = get_staff(staff_id)
    if staff is None:
        raise ValueError("職員が見つかりません。")

    today = date.today()
    if shift_date < today:
        raise ValueError("過去の日付には希望を登録できません。")

    from db.settings_repository import get_settings

    settings = get_settings()
    start_day = int(settings.get("calendar_start_day", 1) or 1)
    period_year = shift_date.year
    period_month = shift_date.month
    period_start, period_end = period_bounds(period_year, period_month, start_day)
    if shift_date < period_start or shift_date > period_end:
        if period_month == 1:
            period_year -= 1
            period_month = 12
        else:
            period_month -= 1
        period_start, period_end = period_bounds(period_year, period_month, start_day)

    existing = leave_repo.get_request_for_staff_date(staff_id, shift_date)
    counts = leave_repo.count_active_requests_by_staff(
        staff_id,
        period_start,
        period_end,
        exclude_date=shift_date if existing else None,
    )
    limit_message = check_request_limits(
        counts,
        settings=settings,
        year=period_year,
        month=period_month,
        staff_name=staff["name"],
        adding_type=request_type,
    )
    if limit_message:
        raise ValueError(limit_message)

    visible = normalize_leave_request_settings(settings)["leave_request_visible_types"]
    if not visible.get(request_type, True):
        raise ValueError("この種別の希望は現在受け付けていません。")

    options = {item["key"] for item in get_portal_request_options(settings)}
    if request_type not in options:
        raise ValueError("選択できない希望種別です。")

    return leave_repo.upsert_pending_request(
        staff_id,
        shift_date,
        request_type,
        note=note,
    )


def remove_leave_request(staff_id: int, shift_date: date) -> bool:
    staff = get_staff(staff_id)
    if staff is None:
        raise ValueError("職員が見つかりません。")

    existing = leave_repo.get_request_for_staff_date(staff_id, shift_date)
    if existing is None:
        return False
    if existing["status"] == "approved":
        raise ValueError("承認済みの希望日は取り消せません。管理者に連絡してください。")
    return leave_repo.cancel_pending_request(staff_id, shift_date)
