"""留学生の労働時間制限（設定値）。"""

from __future__ import annotations

from copy import deepcopy

DEFAULT_STUDENT_LABOR_LIMITS: dict = {
    "normal_weekly_minutes": 28 * 60,
    "vacation_daily_minutes": 8 * 60,
    "vacation_weekly_minutes": 40 * 60,
    "approach_remaining_minutes": 4 * 60,
    "week_start": "monday",  # monday..sunday
}

WEEKDAY_IDS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
WEEKDAY_INDEX = {name: index for index, name in enumerate(WEEKDAY_IDS)}


def default_student_labor_limits() -> dict:
    return deepcopy(DEFAULT_STUDENT_LABOR_LIMITS)


def normalize_student_labor_limits(value: object) -> dict:
    base = default_student_labor_limits()
    if not isinstance(value, dict):
        return base

    for key in (
        "normal_weekly_minutes",
        "vacation_daily_minutes",
        "vacation_weekly_minutes",
        "approach_remaining_minutes",
    ):
        raw = value.get(key, base[key])
        try:
            minutes = int(raw)
        except (TypeError, ValueError):
            minutes = base[key]
        base[key] = max(0, min(24 * 60 * 14, minutes))

    week_start = str(value.get("week_start") or base["week_start"]).strip().lower()
    if week_start not in WEEKDAY_INDEX:
        week_start = "monday"
    base["week_start"] = week_start
    return base


# 職員プロフィール
RESIDENCE_STATUS_NONE = "none"
RESIDENCE_STATUS_STUDENT = "student"
RESIDENCE_STATUS_OTHER = "other"
RESIDENCE_STATUSES = (RESIDENCE_STATUS_NONE, RESIDENCE_STATUS_STUDENT, RESIDENCE_STATUS_OTHER)

PERMISSION_YES = "yes"
PERMISSION_NO = "no"
PERMISSION_UNKNOWN = "unknown"
PERMISSION_STATUSES = (PERMISSION_YES, PERMISSION_NO, PERMISSION_UNKNOWN)

DEFAULT_STUDENT_LABOR_PROFILE: dict = {
    "residence_status": RESIDENCE_STATUS_NONE,
    "permission_status": PERMISSION_UNKNOWN,
    "limit_enabled": True,
    "has_other_job": False,
    "other_job_weekly_minutes": 0,
    "school_name": "",
    "long_vacation_start": None,
    "long_vacation_end": None,
    "notes": "",
    "confirmed_on": None,
    "card_expires_on": None,
}


def default_student_labor_profile() -> dict:
    return deepcopy(DEFAULT_STUDENT_LABOR_PROFILE)


def _normalize_date(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    # YYYY-MM-DD
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return None


def normalize_student_labor_profile(value: object, *, job_type: str | None = None) -> dict:
    base = default_student_labor_profile()
    raw = value if isinstance(value, dict) else {}

    residence = str(raw.get("residence_status") or base["residence_status"]).strip().lower()
    if residence not in RESIDENCE_STATUSES:
        residence = RESIDENCE_STATUS_NONE
    # 職種が留学生なら既定を留学へ寄せる（明示 none のままなら維持）
    if job_type == "留学生" and "residence_status" not in raw:
        residence = RESIDENCE_STATUS_STUDENT
    base["residence_status"] = residence

    permission = str(raw.get("permission_status") or base["permission_status"]).strip().lower()
    if permission not in PERMISSION_STATUSES:
        permission = PERMISSION_UNKNOWN
    base["permission_status"] = permission

    if "limit_enabled" in raw:
        base["limit_enabled"] = bool(raw.get("limit_enabled"))
    elif residence == RESIDENCE_STATUS_STUDENT:
        base["limit_enabled"] = True

    base["has_other_job"] = bool(raw.get("has_other_job", False))
    try:
        other_minutes = int(raw.get("other_job_weekly_minutes") or 0)
    except (TypeError, ValueError):
        other_minutes = 0
    base["other_job_weekly_minutes"] = max(0, min(40 * 60, other_minutes))
    if not base["has_other_job"]:
        base["other_job_weekly_minutes"] = 0

    base["school_name"] = str(raw.get("school_name") or "")[:100]
    base["long_vacation_start"] = _normalize_date(raw.get("long_vacation_start"))
    base["long_vacation_end"] = _normalize_date(raw.get("long_vacation_end"))
    base["notes"] = str(raw.get("notes") or "")[:500]
    base["confirmed_on"] = _normalize_date(raw.get("confirmed_on"))
    base["card_expires_on"] = _normalize_date(raw.get("card_expires_on"))
    return base


def is_student_labor_restricted(profile: dict | None) -> bool:
    data = normalize_student_labor_profile(profile or {})
    return (
        data["residence_status"] == RESIDENCE_STATUS_STUDENT
        and bool(data["limit_enabled"])
    )
