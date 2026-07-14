from data.settings_defaults import CALENDAR_SORT_OPTIONS, TABLE_ZOOM_OPTIONS
from data.calendar_period import build_period_days, format_period_label, period_bounds
from data.facility import get_facility_context
from data.masters import (
    filter_staff_for_facility,
    get_active_shift_legend,
    get_calendar_title,
    get_daily_summary_rows,
    get_departments,
    get_job_types,
    get_status_summary,
    sort_staff_for_calendar,
)
from data.shift_symbols import (
    build_symbol_class_map,
    get_class_for_symbol,
    normalize_symbol,
    symbol_to_key,
)
from data.navigation import get_sidebar
from db.shift_repository import get_shifts_between
from db.staff_repository import list_staff

SHIFT_LEGEND = get_active_shift_legend()

DISPLAY_GROUPS = [
    {"id": "position", "label": "役職順"},
    {"id": "dept", "label": "フロア順"},
    {"id": "job", "label": "職種順"},
    {"id": "all", "label": "名前順"},
]

DISPLAY_GROUP_TO_SORT = {
    "position": "position",
    "dept": "dept",
    "job": "job",
    "all": "name",
}

SORT_TO_DISPLAY_GROUP = {
    "position": "position",
    "dept": "dept",
    "job": "job",
    "name": "all",
}


def _resolve_calendar_display(display_group: str | None = None) -> tuple[str, str]:
    from db.settings_repository import get_settings

    settings = get_settings()
    default_sort = settings.get("calendar_sort_mode", "dept")
    if display_group and display_group in DISPLAY_GROUP_TO_SORT:
        sort_mode = DISPLAY_GROUP_TO_SORT[display_group]
        active_group = display_group
    else:
        sort_mode = default_sort
        active_group = SORT_TO_DISPLAY_GROUP.get(sort_mode, "dept")
    return sort_mode, active_group

def _build_daily_summary(staff_rows: list[dict], day_count: int, settings: dict) -> list[dict]:
    summary_rows = get_daily_summary_rows(settings)
    summaries = []
    for item in summary_rows:
        counts = []
        for day_index in range(day_count):
            count = sum(
                1
                for row in staff_rows
                if not row.get("exclude_from_staffing")
                and day_index < len(row["cells"])
                and symbol_to_key(row["cells"][day_index]["symbol"], settings) == item["key"]
            )
            counts.append(count)
        summaries.append({"label": item["label"], "symbol": item["symbol"], "counts": counts})
    return summaries


def _staff_to_row(staff: dict) -> dict:
    departments = staff.get("departments") or [staff.get("department", "")]
    primary = departments[0] if departments else staff.get("department", "")
    return {
        "id": staff["id"],
        "name": staff["name"],
        "job": staff["job_type"],
        "dept": primary,
        "departments": departments,
        "floors": ",".join(departments),
        "job_type": staff["job_type"],
        "position": staff.get("position", ""),
        "can_work_night": staff.get("can_work_night", False),
        "staffing_basis": staff.get("staffing_basis", {}),
        "exclude_from_staffing": staff.get("exclude_from_staffing", False),
    }


def _shift_symbols_for_staff(
    staff: dict,
    day_infos: list[dict],
    saved: dict[tuple[int, str], dict],
) -> list[dict]:
    cells: list[dict] = []
    for day_info in day_infos:
        key = (staff["id"], day_info["date"])
        if key in saved:
            cells.append(saved[key])
        else:
            cells.append({"symbol": "", "source": None})
    return cells


def build_calendar(year: int, month: int, display_group: str | None = None) -> dict:
    facility = get_facility_context()
    app_settings = facility.get("app_settings", {})
    start_day = app_settings.get("calendar_start_day", 1)
    week_start = app_settings.get("week_start", "sunday")

    period_start, period_end = period_bounds(year, month, start_day)
    days = build_period_days(year, month, start_day, week_start=week_start)

    staff_rows = []
    saved_shifts = get_shifts_between(period_start, period_end)

    for staff in list_staff():
        person = _staff_to_row(staff)
        shifts = _shift_symbols_for_staff(staff, days, saved_shifts)
        cells = []
        for index, day_info in enumerate(days):
            cell_data = shifts[index] if index < len(shifts) else {"symbol": "", "source": None}
            raw_symbol = cell_data.get("symbol", "")
            source = cell_data.get("source")
            display_symbol = normalize_symbol(raw_symbol, app_settings)
            cells.append(
                {
                    "year": day_info["year"],
                    "month": day_info["month"],
                    "day": day_info["day"],
                    "symbol": display_symbol,
                    "class": get_class_for_symbol(raw_symbol, app_settings),
                    "source": source,
                    "is_manual": source == "manual",
                    "is_leave_request": source == "leave",
                    "is_today": day_info["is_today"],
                }
            )
        staff_rows.append({**person, "cells": cells})

    staff_rows = filter_staff_for_facility(staff_rows)
    sort_mode, active_display_group = _resolve_calendar_display(display_group)
    staff_rows = sort_staff_for_calendar(staff_rows, sort_mode)
    shift_daily_summary = _build_daily_summary(staff_rows, len(days), app_settings)

    legend = get_active_shift_legend(app_settings)

    return {
        "symbol_class_map": build_symbol_class_map(app_settings),
        **facility,
        "calendar_title": get_calendar_title(sort_mode),
        "active_display_group": active_display_group,
        "calendar_sort_mode": sort_mode,
        "calendar_start_day": start_day,
        "period_label": format_period_label(
            period_start, period_end, year=year, month=month, start_day=start_day
        ),
        "year": year,
        "month": month,
        "days": days,
        "staff_rows": staff_rows,
        "shift_daily_summary": shift_daily_summary,
        "legend": legend,
        "departments": get_departments(),
        "job_types": get_job_types(),
        "display_groups": DISPLAY_GROUPS,
        "calendar_sort_options": CALENDAR_SORT_OPTIONS,
        "table_zoom_options": TABLE_ZOOM_OPTIONS,
        "status_summary": get_status_summary(app_settings, year, month),
        "sidebar_menu": get_sidebar("calendar"),
    }
