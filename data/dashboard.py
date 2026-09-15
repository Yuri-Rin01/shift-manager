"""ダッシュボード用の集計データを組み立てる。"""

from __future__ import annotations

from collections import Counter
from datetime import date

from data.calendar_period import (
    format_month_label,
    period_bounds,
    resolve_configured_period_off_days,
)
from data.masters import get_departments, get_job_types
from data.shift_symbols import symbol_to_key
from db.settings_repository import get_settings
from db.shift_repository import get_shifts_between
from db import leave_request_repository as leave_repo
from db.staff_repository import list_staff


def _count_by_floor(staff: list[dict]) -> list[dict]:
    counts: Counter[str] = Counter()
    for person in staff:
        floors = person.get("departments") or [person.get("department") or "未設定"]
        for floor in floors:
            if floor:
                counts[floor] += 1
    dept_order = {item["label"]: index for index, item in enumerate(get_departments())}
    rows = [{"label": label, "count": count} for label, count in counts.items()]
    rows.sort(key=lambda row: (dept_order.get(row["label"], 999), row["label"]))
    if not rows:
        rows.append({"label": "（未登録）", "count": 0})
    return rows


def _count_by_job(staff: list[dict]) -> list[dict]:
    counts: Counter[str] = Counter()
    for person in staff:
        job = person.get("job_type") or "未設定"
        counts[job] += 1
    job_order = {item["label"]: index for index, item in enumerate(get_job_types())}
    rows = [{"label": label, "count": count} for label, count in counts.items()]
    rows.sort(key=lambda row: (job_order.get(row["label"], 999), row["label"]))
    if not rows:
        rows.append({"label": "（未登録）", "count": 0})
    return rows


def _shift_type_counts(
    shifts: dict[tuple[int, str], dict],
    staff_ids: set[int],
    settings: dict,
) -> list[dict]:
    counts: Counter[str] = Counter()
    for (staff_id, _shift_date), cell in shifts.items():
        if staff_id not in staff_ids:
            continue
        symbol = cell["symbol"] if isinstance(cell, dict) else cell
        key = symbol_to_key(symbol, settings) or "other"
        counts[key] += 1

    labels = {
        "early": "早番",
        "day": "日勤",
        "late": "遅出",
        "special": "当直",
        "night": "夜勤",
        "morning_off": "明け",
        "paid_leave": "有休",
        "half_leave": "半日有休",
        "off": "休み",
        "training": "研修",
        "other": "その他",
    }
    order = list(labels.keys())
    rows = []
    for key in order:
        count = counts.get(key, 0)
        if count > 0 or key in {"early", "day", "late", "night", "off", "paid_leave"}:
            rows.append({"key": key, "label": labels[key], "count": count})
    return [row for row in rows if row["count"] > 0]


def _leave_fulfillment_rate(
    period_start,
    period_end,
    staff_ids: set[int],
    settings: dict,
) -> tuple[int, int, int]:
    """承認済み希望の充足率（シフト表に leave ソースで反映された件数ベース）。"""
    approved = leave_repo.list_requests_between(
        period_start,
        period_end,
        statuses=("approved",),
    )
    if not approved:
        return 0, 0, 0

    shifts = get_shifts_between(period_start, period_end)
    fulfilled = 0
    for item in approved:
        if item["staff_id"] not in staff_ids:
            continue
        cell = shifts.get((item["staff_id"], item["shift_date"]))
        if cell and cell.get("source") == "leave":
            fulfilled += 1
    total = sum(1 for item in approved if item["staff_id"] in staff_ids)
    rate = round(fulfilled / total * 100) if total else 0
    return rate, fulfilled, total


def _build_checks(
    staff: list[dict],
    fill_rate: int,
    night_assignments: int,
    night_capable: int,
    settings: dict,
    leave_fulfill_rate: int,
    leave_fulfilled: int,
    leave_approved: int,
) -> list[dict]:
    fulfill_target = settings.get("leave_fulfill_target", 90)
    facility_type = settings.get("facility_type", "all")
    checks: list[dict] = []

    if not staff:
        checks.append(
            {
                "label": "職員登録",
                "value": "未登録",
                "status": "warn",
            }
        )
    else:
        checks.append(
            {
                "label": "職員登録",
                "value": f"{len(staff)}名",
                "status": "ok",
            }
        )

    if fill_rate >= 80:
        checks.append(
            {
                "label": "シフト入力",
                "value": f"OK（{fill_rate}%）",
                "status": "ok",
            }
        )
    elif fill_rate >= 30:
        checks.append(
            {
                "label": "シフト入力",
                "value": f"進行中（{fill_rate}%）",
                "status": "warn",
            }
        )
    else:
        checks.append(
            {
                "label": "シフト入力",
                "value": f"未入力が多い（{fill_rate}%）",
                "status": "warn",
            }
        )

    night_label = "夜勤配置" if facility_type == "care" else "夜勤・当直"
    if night_capable == 0:
        checks.append(
            {
                "label": night_label,
                "value": "夜勤可の職員なし",
                "status": "warn",
            }
        )
    elif night_assignments == 0:
        checks.append(
            {
                "label": night_label,
                "value": "当月の夜勤未配置",
                "status": "warn",
            }
        )
    else:
        checks.append(
            {
                "label": night_label,
                "value": f"配置 {night_assignments}件 / 夜勤可 {night_capable}名",
                "status": "ok",
            }
        )

    if leave_approved == 0:
        checks.append(
            {
                "label": "休み希望充足",
                "value": "承認済み希望なし",
                "status": "ok",
            }
        )
    elif leave_fulfill_rate >= fulfill_target:
        checks.append(
            {
                "label": "休み希望充足",
                "value": f"OK（{leave_fulfill_rate}% / {leave_fulfilled}/{leave_approved}件）",
                "status": "ok",
            }
        )
    elif leave_fulfill_rate >= 50:
        checks.append(
            {
                "label": "休み希望充足",
                "value": f"進行中（{leave_fulfill_rate}% / 目標{fulfill_target}%）",
                "status": "warn",
            }
        )
    else:
        checks.append(
            {
                "label": "休み希望充足",
                "value": f"未反映あり（{leave_fulfill_rate}% / {leave_fulfilled}/{leave_approved}件）",
                "status": "warn",
            }
        )
    return checks


def build_dashboard(year: int | None = None, month: int | None = None) -> dict:
    today = date.today()
    resolved_year = year or today.year
    resolved_month = month or today.month
    if resolved_month < 1 or resolved_month > 12:
        resolved_month = today.month

    settings = get_settings()
    calendar_start_day = settings.get("calendar_start_day", 1)
    period_start, period_end = period_bounds(resolved_year, resolved_month, calendar_start_day)
    period_days, off_days, working_days = resolve_configured_period_off_days(
        settings, resolved_year, resolved_month, calendar_start_day
    )
    period_label = format_month_label(resolved_year, resolved_month, calendar_start_day)

    staff = list_staff()
    staff_ids = {person["id"] for person in staff}
    staffing_staff = [person for person in staff if not person.get("exclude_from_staffing")]
    night_capable = sum(1 for person in staff if person.get("can_work_night") or person.get("can_be_night_leader"))
    fixed_night = sum(1 for person in staff if person.get("fix_night_shift_count"))

    shifts = get_shifts_between(period_start, period_end)
    period_shift_cells = sum(1 for (staff_id, _date) in shifts if staff_id in staff_ids)
    total_cells = len(staff) * period_days if staff else 0
    fill_rate = round(period_shift_cells / total_cells * 100) if total_cells else 0

    shift_counts = _shift_type_counts(shifts, staff_ids, settings)
    night_assignments = sum(row["count"] for row in shift_counts if row["key"] == "night")
    special_assignments = sum(row["count"] for row in shift_counts if row["key"] == "special")
    paid_leave_count = sum(
        row["count"] for row in shift_counts if row["key"] in {"paid_leave", "half_leave"}
    )

    leave_fulfill_rate, leave_fulfilled, leave_approved = _leave_fulfillment_rate(
        period_start, period_end, staff_ids, settings
    )

    checks = _build_checks(
        staff,
        fill_rate,
        night_assignments + special_assignments,
        night_capable,
        settings,
        leave_fulfill_rate,
        leave_fulfilled,
        leave_approved,
    )

    calendar_query = ""
    if resolved_year != today.year or resolved_month != today.month:
        calendar_query = f"?year={resolved_year}&month={resolved_month}"

    return {
        "year": resolved_year,
        "month": resolved_month,
        "period_label": period_label,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "period_days": period_days,
        "off_days": off_days,
        "working_days": working_days,
        "stats": {
            "total_staff": len(staff),
            "staffing_staff": len(staffing_staff),
            "excluded_staff": len(staff) - len(staffing_staff),
            "night_capable": night_capable,
            "fixed_night": fixed_night,
            "shift_cells": period_shift_cells,
            "total_cells": total_cells,
            "fill_rate": fill_rate,
            "night_assignments": night_assignments,
            "special_assignments": special_assignments,
            "paid_leave_count": paid_leave_count,
            "leave_fulfill_rate": leave_fulfill_rate,
            "leave_fulfilled": leave_fulfilled,
            "leave_approved": leave_approved,
        },
        "floor_breakdown": _count_by_floor(staff),
        "job_breakdown": _count_by_job(staff),
        "shift_counts": shift_counts,
        "checks": checks,
        "calendar_href": f"/{calendar_query}",
        "is_current_month": resolved_year == today.year and resolved_month == today.month,
    }
