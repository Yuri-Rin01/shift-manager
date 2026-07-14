"""カレンダー表示期間（開始日〜翌月前日）の計算。"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta

WEEKDAY_LABELS = ["月", "火", "水", "木", "金", "土", "日"]


def normalize_start_day(start_day: int | None) -> int:
    if not start_day or start_day < 1:
        return 1
    return min(int(start_day), 28)


def period_bounds(year: int, month: int, start_day: int = 1) -> tuple[date, date]:
    """基準年月と開始日から、表示期間の開始・終了日を返す。"""
    start_day = normalize_start_day(start_day)
    if start_day <= 1:
        last = monthrange(year, month)[1]
        return date(year, month, 1), date(year, month, last)

    period_start = date(year, month, start_day)
    if month == 12:
        period_end = date(year + 1, 1, start_day - 1)
    else:
        period_end = date(year, month + 1, start_day - 1)
    return period_start, period_end


def auto_generate_days(
    year: int,
    month: int,
    start_day: int = 1,
    *,
    week_start: str = "sunday",
) -> list[dict]:
    """自動生成の対象日（カレンダーに表示されている全期間）。"""
    return build_period_days(year, month, start_day, week_start=week_start)


def auto_generate_bounds(
    year: int,
    month: int,
    start_day: int = 1,
    *,
    week_start: str = "sunday",
) -> tuple[date | None, date | None]:
    days = auto_generate_days(year, month, start_day, week_start=week_start)
    if not days:
        return None, None
    return date.fromisoformat(days[0]["date"]), date.fromisoformat(days[-1]["date"])


def format_scope_range(start: date, end: date) -> str:
    """自動生成の対象期間ラベル（表示区間）。"""
    if start == end:
        return f"{start.year}年{start.month}月{start.day}日"
    if start.year == end.year and start.month == end.month:
        return f"{start.year}年{start.month}月{start.day}日〜{end.day}日"
    return f"{start.year}年{start.month}月{start.day}日〜{end.year}年{end.month}月{end.day}日"


def _week_number(day_index: int, period_start: date, week_start: str) -> int:
    if week_start == "monday":
        offset = period_start.weekday()
    else:
        offset = (period_start.weekday() + 1) % 7
    return (day_index + offset) // 7 + 1


def build_period_days(
    year: int,
    month: int,
    start_day: int = 1,
    *,
    week_start: str = "sunday",
) -> list[dict]:
    period_start, period_end = period_bounds(year, month, start_day)
    today = date.today()
    days: list[dict] = []
    current = period_start
    index = 0
    while current <= period_end:
        weekday = current.weekday()
        days.append(
            {
                "year": current.year,
                "month": current.month,
                "day": current.day,
                "date": current.isoformat(),
                "weekday": weekday,
                "weekday_label": WEEKDAY_LABELS[weekday],
                "week_number": _week_number(index, period_start, week_start),
                "is_today": current == today,
                "is_saturday": weekday == 5,
                "is_sunday": weekday == 6,
            }
        )
        current += timedelta(days=1)
        index += 1
    return days


def period_day_count(year: int, month: int, start_day: int = 1) -> int:
    period_start, period_end = period_bounds(year, month, start_day)
    return (period_end - period_start).days + 1


def count_weekend_days(period_start: date, period_end: date) -> int:
    count = 0
    current = period_start
    while current <= period_end:
        if current.weekday() >= 5:
            count += 1
        current += timedelta(days=1)
    return count


def resolve_period_off_days(
    year: int,
    month: int,
    start_day: int = 1,
    off_days: int | None = None,
) -> tuple[int, int, int]:
    """期間日数・休み日数・勤務日数を返す。"""
    period_start, period_end = period_bounds(year, month, start_day)
    total_days = (period_end - period_start).days + 1
    default_off_days = count_weekend_days(period_start, period_end)
    resolved_off = default_off_days if off_days is None else max(0, min(int(off_days), total_days - 1))
    working_days = max(1, total_days - resolved_off)
    return total_days, resolved_off, working_days


def resolve_configured_period_off_days(
    settings: dict | None,
    year: int,
    month: int,
    start_day: int = 1,
) -> tuple[int, int, int]:
    """設定の休み日数（全職員共通）を反映した期間日数・休み・勤務日数。"""
    configured = None
    if settings:
        raw = settings.get("off_days_per_period")
        if raw is not None and raw != "":
            try:
                configured = int(raw)
            except (TypeError, ValueError):
                configured = None
    return resolve_period_off_days(year, month, start_day, configured)


def format_month_label(year: int, month: int, start_day: int = 1) -> str:
    """職員管理・カレンダーで使う月ラベル。"""
    if normalize_start_day(start_day) <= 1:
        return f"{year}年{month}月"
    return f"{year}年{month}月（{normalize_start_day(start_day)}日始まり）"


def format_period_label(start: date, end: date, *, year: int | None = None, month: int | None = None, start_day: int = 1) -> str:
    """後方互換のエイリアス。月ラベルを返す。"""
    anchor_year = year if year is not None else start.year
    anchor_month = month if month is not None else start.month
    return format_month_label(anchor_year, anchor_month, start_day)


def calendar_start_day_options() -> list[dict]:
    return [{"value": day, "label": f"{day}日"} for day in range(1, 29)]
