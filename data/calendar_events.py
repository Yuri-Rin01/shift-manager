"""カレンダーに出すイベント日。"""

from __future__ import annotations

import re

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MAX_EVENTS = 100
_MAX_LABEL = 40
_MAX_DISPLAY = 20
_FONT_MIN = 10
_FONT_MAX = 28
_FONT_DEFAULT = 12


def _clean(value, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _font_size(value) -> int:
    try:
        size = int(value)
    except (TypeError, ValueError):
        return _FONT_DEFAULT
    return min(_FONT_MAX, max(_FONT_MIN, size))


def normalize_calendar_events(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    events: list[dict] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        day = str(item.get("date") or "").strip()
        label = _clean(item.get("label"), _MAX_LABEL)
        display = _clean(item.get("display"), _MAX_DISPLAY)
        if not label and display:
            label = display[:_MAX_LABEL]
        if not _DATE.fullmatch(day) or not label or day in seen:
            continue
        seen.add(day)
        events.append({
            "date": day,
            "label": label,
            "display": display,
            "font_size": _font_size(item.get("font_size")),
        })
        if len(events) >= _MAX_EVENTS:
            break
    events.sort(key=lambda row: row["date"])
    return events


def event_label_map(value) -> dict[str, str]:
    return {row["date"]: row["label"] for row in normalize_calendar_events(value)}


def event_entry_map(value) -> dict[str, dict]:
    return {row["date"]: row for row in normalize_calendar_events(value)}
