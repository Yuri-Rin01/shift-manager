"""Flick / slide direction assignments for shift cell input."""

from __future__ import annotations

FLICK_DIRECTION_COUNT = 8

# Index matches home.js getFlickDirectionIndex()
FLICK_DIRECTIONS = [
    {"index": 0, "key": "up", "label": "上", "arrow": "↑"},
    {"index": 1, "key": "up_right", "label": "右上", "arrow": "↗"},
    {"index": 2, "key": "right", "label": "右", "arrow": "→"},
    {"index": 3, "key": "down_right", "label": "右下", "arrow": "↘"},
    {"index": 4, "key": "down", "label": "下", "arrow": "↓"},
    {"index": 5, "key": "down_left", "label": "左下", "arrow": "↙"},
    {"index": 6, "key": "left", "label": "左", "arrow": "←"},
    {"index": 7, "key": "up_left", "label": "左上", "arrow": "↖"},
]

# Visual grid order for settings UI (row-major 3x3, center is None)
FLICK_GRID_ORDER = [7, 0, 1, 6, None, 2, 5, 4, 3]


def default_cell_flick_directions() -> list[str]:
    """Empty list means “follow visible work types in order” (legacy behavior)."""
    return []


def normalize_cell_flick_directions(value) -> list[str]:
    if value is None:
        return default_cell_flick_directions()
    if not isinstance(value, list):
        return default_cell_flick_directions()
    out: list[str] = []
    for i in range(FLICK_DIRECTION_COUNT):
        raw = value[i] if i < len(value) else ""
        if raw is None:
            out.append("")
            continue
        text = str(raw).strip()
        # Keep at most a short symbol/key
        out.append(text[:8] if text else "")
    # All empty → treat as default (auto)
    if not any(out):
        return []
    return out
