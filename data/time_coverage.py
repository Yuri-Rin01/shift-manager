"""時間帯と勤務区分の重なり判定（配置ルール用）。"""

from __future__ import annotations

from datetime import date, timedelta

from data.placement_rules import normalize_time_slot_staffing_rules
from data.shift_symbols import get_shift_symbols, is_work_type_visible
from data.staffing_basis import get_staffing_basis_options

SEMI_TO_BASE = {
    "semi_early": "early",
    "semi_day": "day",
    "semi_late": "late",
    "semi_night": "night",
}

WORK_BASE_KEYS = frozenset({"early", "day", "late", "night"})


def to_minutes(time_str: str) -> int:
    hour, minute = time_str.split(":")
    return int(hour) * 60 + int(minute)


def base_work_key(key: str) -> str:
    return SEMI_TO_BASE.get(key, key)


def segments_overlap(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left[0] < right[1] and right[0] < left[1]


def rule_segments_on_calendar_day(start_time: str, end_time: str) -> list[tuple[int, int, int]]:
    """カレンダー1日における時間帯ルールの区間。(開始分, 終了分, 割当日オフセット)。"""
    start = to_minutes(start_time)
    end = to_minutes(end_time)
    if end > start:
        return [(start, end, 0)]
    return [(0, end, -1), (start, 1440, 0)]


def work_segments_on_calendar_day(
    work_start: str,
    work_end: str,
    *,
    assignment_offset: int,
) -> list[tuple[int, int]]:
    """勤務区分のうち、カレンダー上の1日に該当する区間。"""
    start = to_minutes(work_start)
    end = to_minutes(work_end)
    if assignment_offset == 0:
        if end > start:
            return [(start, end)]
        return [(start, 1440)]
    if end < start:
        return [(0, end)]
    return []


def assignment_date_for(calendar_date: date, offset: int) -> date:
    return calendar_date + timedelta(days=offset)


def get_assignable_work_types(settings: dict) -> list[dict]:
    """配置候補となる勤務区分（記号・時間付き）。"""
    symbols = get_shift_symbols(settings)
    options: list[dict] = []
    for item in get_staffing_basis_options(settings):
        key = str(item.get("key", "")).strip()
        if not key or base_work_key(key) not in WORK_BASE_KEYS:
            continue
        if not is_work_type_visible(key, settings):
            continue
        symbol = symbols.get(key)
        if not symbol:
            continue
        start_time = str(item.get("start_time", "")).strip()
        end_time = str(item.get("end_time", "")).strip()
        if not start_time or not end_time:
            continue
        options.append(
            {
                "key": key,
                "base_key": base_work_key(key),
                "label": str(item.get("label", key)).strip() or key,
                "symbol": symbol,
                "start_time": start_time,
                "end_time": end_time,
            }
        )
    return options


def work_type_covers_segment(
    work_type: dict,
    calendar_date: date,
    segment: tuple[int, int],
    assignment_offset: int,
) -> bool:
    """指定日の区間を、assignment_offset 日に割り当てた勤務区分がカバーするか。"""
    for work_segment in work_segments_on_calendar_day(
        work_type["start_time"],
        work_type["end_time"],
        assignment_offset=assignment_offset,
    ):
        if segments_overlap(work_segment, segment):
            return True
    return False


def work_types_for_segment(
    work_types: list[dict],
    calendar_date: date,
    segment: tuple[int, int],
    assignment_offset: int,
) -> list[dict]:
    """区間をカバーできる勤務区分（重なり時間が長い順）。"""
    matches: list[tuple[int, dict]] = []
    seg_len = max(1, segment[1] - segment[0])
    for work_type in work_types:
        overlap = 0
        for work_segment in work_segments_on_calendar_day(
            work_type["start_time"],
            work_type["end_time"],
            assignment_offset=assignment_offset,
        ):
            start = max(work_segment[0], segment[0])
            end = min(work_segment[1], segment[1])
            if end > start:
                overlap += end - start
        if overlap > 0:
            matches.append((overlap, work_type))
    matches.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in matches]


def get_time_slot_rules(settings: dict) -> list[dict]:
    return normalize_time_slot_staffing_rules(settings.get("time_slot_staffing_rules"))
