"""カレンダーに出すイベント日。"""

from __future__ import annotations

import re

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MAX_EVENTS = 100
_MAX_LABEL = 40


def normalize_calendar_events(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    events: list[dict] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        day = str(item.get("date") or "").strip()
        label = " ".join(str(item.get("label") or "").split())
        if not _DATE.fullmatch(day) or not label or day in seen:
            continue
        seen.add(day)
        events.append({"date": day, "label": label[:_MAX_LABEL]})
        if len(events) >= _MAX_EVENTS:
            break
    events.sort(key=lambda row: row["date"])
    return events


def event_label_map(value) -> dict[str, str]:
    return {row["date"]: row["label"] for row in normalize_calendar_events(value)}
