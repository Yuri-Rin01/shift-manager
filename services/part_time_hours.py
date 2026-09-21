"""パート職員の週労働時間。

満量は労働基準法の週40時間。中央の目安は週20時間（雇用保険・社会保険の加入ライン）で、
超えても違反ではない。1日8時間超は週ごとの日数として示す。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

from services.student_labor import build_day_minutes_map, format_hours, week_start_for

PART_TIME_JOB = "パート"
STATUTORY_WEEKLY_MINUTES = 40 * 60
STATUTORY_DAILY_MINUTES = 8 * 60
INSURANCE_WEEKLY_MINUTES = 20 * 60

STATUS_LABELS = {
    "within": "20時間未満",
    "statutory": "法定内",
    "overtime": "法定超",
}


def part_time_status(week_minutes: int) -> str:
    if week_minutes > STATUTORY_WEEKLY_MINUTES:
        return "overtime"
    if week_minutes >= INSURANCE_WEEKLY_MINUTES:
        return "statutory"
    return "within"


def summarize_part_time_staff(
    *,
    staff: dict,
    period_start: date,
    period_end: date,
    assignments: Iterable[tuple[date, str]],
    settings: dict | None,
) -> dict:
    """施設の週始まりで、表示期間に重なる週を集計する。"""
    week_origin = str((settings or {}).get("week_start") or "sunday").strip().lower() or "sunday"
    day_map = build_day_minutes_map(assignments, settings)
    cursor = week_start_for(period_start, week_origin)
    weeks: list[dict] = []
    while cursor <= period_end:
        week_end = cursor + timedelta(days=6)
        minutes = 0
        daily_over = 0
        day = cursor
        while day <= week_end:
            mins = int(day_map.get(day, 0))
            minutes += mins
            if mins > STATUTORY_DAILY_MINUTES:
                daily_over += 1
            day += timedelta(days=1)
        status = part_time_status(minutes)
        weeks.append(
            {
                "week_start": cursor.isoformat(),
                "week_end": week_end.isoformat(),
                "display_start": max(cursor, period_start).isoformat(),
                "display_end": min(week_end, period_end).isoformat(),
                "week_minutes": minutes,
                "week_hours_label": format_hours(minutes),
                "limit_week_minutes": STATUTORY_WEEKLY_MINUTES,
                "limit_hours_label": format_hours(STATUTORY_WEEKLY_MINUTES),
                "insurance_week_minutes": INSURANCE_WEEKLY_MINUTES,
                "daily_over_count": daily_over,
                "status": status,
                "status_label": STATUS_LABELS[status],
            }
        )
        cursor += timedelta(days=7)

    rank = {"within": 0, "statutory": 1, "overtime": 2}
    worst = "within"
    for week in weeks:
        if rank[week["status"]] > rank[worst]:
            worst = week["status"]
    return {
        "staff_id": staff.get("id"),
        "name": staff.get("name"),
        "status": worst,
        "status_label": STATUS_LABELS[worst],
        "weeks": weeks,
    }
