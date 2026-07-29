"""シフト表シート（ファイル）ごとのアクセント色。"""

from __future__ import annotations

import re

SHEET_VIEW_IDS = ("all", "foreign-students")

DEFAULT_SHEET_VIEW_COLORS: dict[str, str] = {
    "all": "#3B82F6",
    "foreign-students": "#217346",
}

_HEX_RE = re.compile(r"^#?[0-9A-Fa-f]{6}$")


def normalize_sheet_color(value: object, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    raw = value.strip()
    if not _HEX_RE.fullmatch(raw):
        return fallback
    if not raw.startswith("#"):
        raw = f"#{raw}"
    return raw.upper()


def default_sheet_view_colors() -> dict[str, str]:
    return dict(DEFAULT_SHEET_VIEW_COLORS)


def normalize_sheet_view_colors(value: object) -> dict[str, str]:
    base = default_sheet_view_colors()
    if not isinstance(value, dict):
        return base
    for key in SHEET_VIEW_IDS:
        if key in value:
            base[key] = normalize_sheet_color(value.get(key), base[key])
    return base
