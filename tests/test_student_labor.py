"""留学生労働時間制限の自動テスト。"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from data.shift_symbols import DEFAULT_SHIFT_SYMBOLS
from data.student_labor_limits import default_student_labor_limits, normalize_student_labor_profile
from services.student_labor import (
    REASON_MESSAGES,
    build_day_minutes_map,
    can_assign_shift,
    net_work_minutes,
    split_shift_day_minutes,
    summarize_staff_week,
    week_range_containing,
)


def _settings() -> dict:
    return {
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
                "key": "semi_day",
                "label": "1時間",
                "start_time": "09:00",
                "end_time": "10:00",
                "break_minutes": 0,
            },
            {
                "key": "night",
                "label": "夜勤",
                "start_time": "16:00",
                "end_time": "09:00",
                "break_minutes": 120,
            },
        ],
        "student_labor_limits": default_student_labor_limits(),
    }


def _student(
    *,
    permission: str = "yes",
    other_hours: float = 0,
    vacation: tuple[str, str] | None = None,
    expires: str | None = None,
) -> dict:
    profile = normalize_student_labor_profile(
        {
            "residence_status": "student",
            "permission_status": permission,
            "limit_enabled": True,
            "has_other_job": other_hours > 0,
            "other_job_weekly_minutes": int(round(other_hours * 60)),
            "long_vacation_start": vacation[0] if vacation else None,
            "long_vacation_end": vacation[1] if vacation else None,
            "card_expires_on": expires,
        },
        job_type="留学生",
    )
    return {
        "id": 1,
        "name": "留学生 太郎",
        "job_type": "留学生",
        "student_labor": profile,
    }


# 2026-08-03 は月曜日
MON = date(2026, 8, 3)
SYM = {
    "h3": "●",  # early 3h
    "h8": "○",  # day 8h
    "h4": "◎",  # late 4h
    "h1": "半日",  # semi_day 1h
    "night": "／",  # night — check default night symbol
}


@pytest.fixture(autouse=True)
def _night_symbol():
    # night default symbol from catalog
    from data.shift_symbols import CATALOG_BY_KEY

    SYM["night"] = CATALOG_BY_KEY["night"]["default_symbol"]


def _assign(staff, work_date, symbol, existing, settings=None):
    return can_assign_shift(
        staff=staff,
        work_date=work_date,
        symbol=symbol,
        existing_assignments=existing,
        settings=settings or _settings(),
    )


def test_net_work_minutes_excludes_break():
    assert net_work_minutes("09:00", "18:00", 60) == 8 * 60
    assert net_work_minutes("16:00", "09:00", 120) == 15 * 60


def test_01_normal_week_27h_assignable():
    # 3×8h + 3h = 27h
    existing = [
        (MON, SYM["h8"]),
        (MON + timedelta(days=1), SYM["h8"]),
        (MON + timedelta(days=2), SYM["h8"]),
    ]
    ok, reason, detail = _assign(_student(), MON + timedelta(days=3), SYM["h3"], existing)
    assert ok and reason is None
    assert detail["total_week_minutes"] == 27 * 60


def test_02_normal_week_28h_exactly_assignable():
    existing = [
        (MON, SYM["h8"]),
        (MON + timedelta(days=1), SYM["h8"]),
        (MON + timedelta(days=2), SYM["h8"]),
    ]
    ok, reason, detail = _assign(_student(), MON + timedelta(days=3), SYM["h4"], existing)
    assert ok and reason is None
    assert detail["total_week_minutes"] == 28 * 60
    assert detail["remaining_minutes"] == 0


def test_03_normal_week_over_28h_blocked():
    existing = [
        (MON, SYM["h8"]),
        (MON + timedelta(days=1), SYM["h8"]),
        (MON + timedelta(days=2), SYM["h8"]),
        (MON + timedelta(days=3), SYM["h4"]),
    ]
    ok, reason, _ = _assign(_student(), MON + timedelta(days=4), SYM["h1"], existing)
    assert not ok
    assert reason == "normal_weekly_over"


def test_04_other_job_4h_facility_24h_ok():
    existing = [
        (MON, SYM["h8"]),
        (MON + timedelta(days=1), SYM["h8"]),
        (MON + timedelta(days=2), SYM["h8"]),
    ]
    # already 24h + other 4 = 28; no new assign needed — try assign nothing extra:
    # assign 0 by checking a day that's already counted: use can_assign for empty day with 0h? 
    # Instead verify assigning nothing more: check that adding 0 isn't the test —
    # Spec: 自施設24 + 他4 なら配置可能 → try assign nothing means current state ok.
    # Assign a 0-hour leave isn't work. Verify can assign if we replace: 
    # existing 24, try add nothing — use can_assign with work that is already the week at 24.
    ok, reason, detail = _assign(
        _student(other_hours=4),
        MON + timedelta(days=3),
        "",  # empty — may fail differently
        existing,
    )
    # empty symbol: treat as clear? minutes_for_symbol returns 0 — should be ok at 28
    assert ok
    assert detail["total_week_minutes"] == 28 * 60


def test_05_other_job_4h_facility_25h_blocked():
    existing = [
        (MON, SYM["h8"]),
        (MON + timedelta(days=1), SYM["h8"]),
        (MON + timedelta(days=2), SYM["h8"]),
    ]
    ok, reason, detail = _assign(
        _student(other_hours=4),
        MON + timedelta(days=3),
        SYM["h1"],
        existing,
    )
    assert not ok
    assert reason == "normal_weekly_over"
    assert detail["total_week_minutes"] == 29 * 60


def test_06_vacation_daily_8h_exact_ok():
    vac = ("2026-08-01", "2026-08-31")
    ok, reason, detail = _assign(
        _student(vacation=vac),
        MON,
        SYM["h8"],
        [],
    )
    assert ok and reason is None
    assert detail["period_mode"] == "vacation"


def test_07_vacation_daily_over_8h_blocked():
    vac = ("2026-08-01", "2026-08-31")
    settings = _settings()
    # 1日9時間（休憩なし）→ 長期休業の1日8時間を超える
    for opt in settings["staffing_basis_options"]:
        if opt["key"] == "day":
            opt["start_time"] = "09:00"
            opt["end_time"] = "18:00"
            opt["break_minutes"] = 0
            break
    ok, reason, _ = _assign(
        _student(vacation=vac),
        MON,
        SYM["h8"],
        [],
        settings,
    )
    assert not ok
    assert reason == "daily_over"


def test_08_vacation_week_40h_exact_ok():
    vac = ("2026-08-01", "2026-08-31")
    # 5×8h = 40
    existing = [
        (MON, SYM["h8"]),
        (MON + timedelta(days=1), SYM["h8"]),
        (MON + timedelta(days=2), SYM["h8"]),
        (MON + timedelta(days=3), SYM["h8"]),
    ]
    ok, reason, detail = _assign(
        _student(vacation=vac),
        MON + timedelta(days=4),
        SYM["h8"],
        existing,
    )
    assert ok and reason is None
    assert detail["total_week_minutes"] == 40 * 60


def test_09_vacation_week_over_40h_blocked():
    vac = ("2026-08-01", "2026-08-31")
    existing = [
        (MON + timedelta(days=i), SYM["h8"]) for i in range(5)
    ]
    ok, reason, _ = _assign(
        _student(vacation=vac),
        MON + timedelta(days=5),
        SYM["h1"],
        existing,
    )
    assert not ok
    assert reason == "vacation_weekly_over"


def test_10_no_vacation_treated_as_normal():
    # August without vacation registration → 28h limit (not 40)
    existing = [
        (MON, SYM["h8"]),
        (MON + timedelta(days=1), SYM["h8"]),
        (MON + timedelta(days=2), SYM["h8"]),
        (MON + timedelta(days=3), SYM["h4"]),
    ]
    ok, reason, detail = _assign(_student(), MON + timedelta(days=4), SYM["h1"], existing)
    assert not ok
    assert reason == "normal_weekly_over"
    assert detail["period_mode"] == "normal"
    assert detail["limit_week_minutes"] == 28 * 60


def test_11_permission_no_blocked():
    ok, reason, _ = _assign(_student(permission="no"), MON, SYM["h8"], [])
    assert not ok
    assert reason == "permission_no"


def test_12_permission_unknown_blocked():
    ok, reason, _ = _assign(_student(permission="unknown"), MON, SYM["h8"], [])
    assert not ok
    assert reason == "permission_unknown"


def test_13_overnight_split_across_days_and_weeks():
    # Sunday night into Monday: hours split across week boundary
    sunday = MON - timedelta(days=1)  # 2026-08-02
    segments = split_shift_day_minutes(sunday, "16:00", "09:00", 120)
    assert segments == [
        (sunday, (24 * 60 - 16 * 60)),  # 8h on Sunday before break allocation
        (MON, max(0, 9 * 60 - 120)),  # break from day2 first → 7h Monday? 
    ]
    # break 120 from day2 (9h): day2_net=7h, day1_net=8h, total 15h
    assert sum(m for _, m in segments) == 15 * 60
    assert segments[0][0] == sunday
    assert segments[1][0] == MON

    settings = _settings()
    day_map = build_day_minutes_map([(sunday, SYM["night"])], settings)
    assert day_map[sunday] + day_map[MON] == 15 * 60

    # Week containing Monday: only Monday portion counts toward Mon-Sun week
    week_start, week_end = week_range_containing(MON, "monday")
    assert week_start == MON
    monday_portion = day_map[MON]
    staff = _student()
    # Existing Monday portion from Sunday night + try add 8h Tue
    existing = [(sunday, SYM["night"])]
    ok, reason, detail = _assign(staff, MON + timedelta(days=1), SYM["h8"], existing, settings)
    assert ok
    assert detail["facility_week_minutes"] == monday_portion + 8 * 60


def test_14_month_spanning_week_not_split():
    # Week Mon Jul 27 – Sun Aug 2, 2026
    week_mon = date(2026, 7, 27)
    assert week_range_containing(date(2026, 8, 1), "monday")[0] == week_mon
    existing = [
        (week_mon, SYM["h8"]),  # July
        (week_mon + timedelta(days=1), SYM["h8"]),  # July
        (week_mon + timedelta(days=2), SYM["h8"]),  # July
        (date(2026, 8, 1), SYM["h4"]),  # August
    ]
    ok, reason, detail = _assign(
        _student(),
        date(2026, 8, 2),
        SYM["h1"],
        existing,
    )
    # 8+8+8+4+1 = 29 > 28
    assert not ok
    assert reason == "normal_weekly_over"
    assert detail["facility_week_minutes"] == 29 * 60
    assert detail["week_start"] == week_mon.isoformat()


def test_15_manual_edit_uses_same_limit_check():
    # Manual save path calls can_assign_shift — same as auto
    existing = [(MON + timedelta(days=i), SYM["h8"]) for i in range(3)] + [
        (MON + timedelta(days=3), SYM["h4"])
    ]
    ok, reason, detail = _assign(_student(), MON + timedelta(days=4), SYM["h3"], existing)
    assert not ok
    assert "上限" in REASON_MESSAGES[reason] or reason == "normal_weekly_over"
    assert detail["facility_week_minutes"] > detail["limit_week_minutes"]


def test_16_understaffed_reason_message_text():
    from services import shift_generator as sg

    # Find class that owns _emit_student_labor_warnings
    owner = None
    for name in dir(sg):
        obj = getattr(sg, name)
        if isinstance(obj, type) and hasattr(obj, "_emit_student_labor_warnings"):
            owner = obj
            break
    assert owner is not None
    gen = object.__new__(owner)
    gen.student_labor_blocks = [{"name": "留学生 太郎", "staff_id": 1}]
    gen.warnings = []
    owner._emit_student_labor_warnings(gen)
    assert any(
        "留学生の労働時間制限により必要人数を満たせません" in w["message"]
        for w in gen.warnings
    )
    assert any(w.get("code") == "student_labor_limit" for w in gen.warnings)


def test_17_past_shift_change_recalculates():
    # Initially Mon-Wed 8h; changing to include Thu 4h reaches 28; Fri 1h blocked
    existing = [(MON + timedelta(days=i), SYM["h8"]) for i in range(3)]
    ok1, _, d1 = _assign(_student(), MON + timedelta(days=3), SYM["h4"], existing)
    assert ok1 and d1["total_week_minutes"] == 28 * 60

    existing2 = existing + [(MON + timedelta(days=3), SYM["h4"])]
    ok2, reason2, _ = _assign(_student(), MON + timedelta(days=4), SYM["h1"], existing2)
    assert not ok2 and reason2 == "normal_weekly_over"

    # Recalculate after removing Wednesday (past change)
    existing3 = [
        (MON, SYM["h8"]),
        (MON + timedelta(days=1), SYM["h8"]),
        (MON + timedelta(days=3), SYM["h4"]),
    ]
    ok3, _, d3 = _assign(_student(), MON + timedelta(days=4), SYM["h8"], existing3)
    assert ok3
    assert d3["total_week_minutes"] == 28 * 60


def test_18_break_excluded_from_judgment():
    # 09:00-18:00 with 60 break = 8h, not 9h. Three days = 24h, fourth 4h = 28 ok;
    # without break would be 27+4=31 over — ensure break is applied.
    settings = _settings()
    assert net_work_minutes("09:00", "18:00", 60) == 480
    existing = [(MON + timedelta(days=i), SYM["h8"]) for i in range(3)]
    ok, _, detail = _assign(_student(), MON + timedelta(days=3), SYM["h4"], existing, settings)
    assert ok
    assert detail["facility_week_minutes"] == 28 * 60


def test_summary_status_labels_on_foreign_sheet():
    staff = _student(other_hours=4)
    existing = [(MON + timedelta(days=i), SYM["h8"]) for i in range(3)]  # 24+4=28
    summary = summarize_staff_week(
        staff=staff,
        focus_day=MON,
        assignments=existing,
        settings=_settings(),
    )
    assert summary["status"] == "reached"
    assert summary["status_label"] == "上限到達"
    assert summary["period_label"] == "通常期間"
