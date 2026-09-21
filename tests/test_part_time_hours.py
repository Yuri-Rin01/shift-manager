"""パート週労働時間バーの集計。"""

from datetime import date, timedelta

from data.shift_symbols import DEFAULT_SHIFT_SYMBOLS
from services.part_time_hours import (
    INSURANCE_WEEKLY_MINUTES,
    STATUTORY_DAILY_MINUTES,
    STATUTORY_WEEKLY_MINUTES,
    summarize_part_time_staff,
)


def _settings(**overrides) -> dict:
    settings = {
        "week_start": "sunday",
        "shift_symbols": dict(DEFAULT_SHIFT_SYMBOLS),
        "staffing_basis_options": [
            {
                "key": "early",
                "label": "3時間",
                "start_time": "09:00",
                "end_time": "12:00",
                "break_minutes": 0,
            },
            {
                "key": "day",
                "label": "8時間",
                "start_time": "09:00",
                "end_time": "18:00",
                "break_minutes": 60,
            },
            {
                "key": "late",
                "label": "4時間",
                "start_time": "13:00",
                "end_time": "17:00",
                "break_minutes": 0,
            },
            {
                "key": "long",
                "label": "9時間",
                "start_time": "09:00",
                "end_time": "19:00",
                "break_minutes": 60,
            },
        ],
    }
    settings.update(overrides)
    return settings


STAFF = {"id": 7, "name": "パート 花子", "job_type": "パート"}
# 2026-08-02 は日曜。週始まり日曜なら 8/2〜8/8 が1週。
SUN = date(2026, 8, 2)
PERIOD_START = date(2026, 8, 1)
PERIOD_END = date(2026, 8, 31)
DAY = DEFAULT_SHIFT_SYMBOLS["day"]
EARLY = DEFAULT_SHIFT_SYMBOLS["early"]
LONG = "長"


def _summary(assignments, **settings_overrides):
    settings = _settings(**settings_overrides)
    if any(symbol == LONG for _, symbol in assignments):
        settings["shift_symbols"] = {**settings["shift_symbols"], "long": LONG}
    return summarize_part_time_staff(
        staff=STAFF,
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        assignments=assignments,
        settings=settings,
    )


def _week(summary, start: date):
    for week in summary["weeks"]:
        if week["week_start"] == start.isoformat():
            return week
    raise AssertionError(start.isoformat())


def test_four_day_shifts_stay_inside_statutory_week():
    assignments = [(SUN + timedelta(days=offset), DAY) for offset in range(1, 5)]
    week = _week(_summary(assignments), SUN)
    assert week["week_minutes"] == 32 * 60
    assert week["status"] == "statutory"
    assert week["daily_over_count"] == 0
    assert week["limit_week_minutes"] == STATUTORY_WEEKLY_MINUTES
    assert week["insurance_week_minutes"] == INSURANCE_WEEKLY_MINUTES


def test_six_day_shifts_are_overtime_not_a_hard_cap_flag():
    assignments = [(SUN + timedelta(days=offset), DAY) for offset in range(1, 7)]
    week = _week(_summary(assignments), SUN)
    assert week["week_minutes"] == 48 * 60
    assert week["status"] == "overtime"
    assert week["status_label"] == "法定超"
    assert week["daily_over_count"] == 0


def test_exactly_forty_hours_is_still_statutory():
    assignments = [(SUN + timedelta(days=offset), DAY) for offset in range(1, 6)]
    week = _week(_summary(assignments), SUN)
    assert week["week_minutes"] == STATUTORY_WEEKLY_MINUTES
    assert week["status"] == "statutory"


def test_twenty_hours_is_the_enrollment_line():
    assignments = [
        (date(2026, 8, 3), DAY),
        (date(2026, 8, 4), DAY),
        (date(2026, 8, 5), DEFAULT_SHIFT_SYMBOLS["late"]),
    ]
    week = _week(_summary(assignments), SUN)
    assert week["week_minutes"] == INSURANCE_WEEKLY_MINUTES
    assert week["status"] == "statutory"


def test_short_shift_stays_under_twenty_hours():
    week = _week(_summary([(date(2026, 8, 3), EARLY)]), SUN)
    assert week["week_minutes"] == 3 * 60
    assert week["status"] == "within"
    assert week["daily_over_count"] == 0


def test_nine_hour_day_is_counted_without_marking_the_week_over():
    week = _week(_summary([(date(2026, 8, 3), LONG)]), SUN)
    assert week["week_minutes"] == 9 * 60
    assert week["week_minutes"] > STATUTORY_DAILY_MINUTES
    assert week["daily_over_count"] == 1
    assert week["status"] == "within"


def test_facility_week_starts_on_sunday():
    summary = _summary(
        [
            (date(2026, 8, 2), DAY),
            (date(2026, 8, 9), DAY),
        ]
    )
    first = _week(summary, date(2026, 7, 26))
    second = _week(summary, SUN)
    third = _week(summary, date(2026, 8, 9))
    assert first["week_minutes"] == 0
    assert second["week_minutes"] == 8 * 60
    assert third["week_minutes"] == 8 * 60
    assert second["display_start"] == "2026-08-02"
    assert second["display_end"] == "2026-08-08"
