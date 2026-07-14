"""休み希望ポータル連携の設定・上限・メッセージ。"""

from __future__ import annotations

from data.calendar_period import period_bounds, resolve_configured_period_off_days
from data.leave_request_types import (
    DEFAULT_LEAVE_REQUEST_VISIBLE_TYPES,
    LEAVE_REQUEST_TYPE_META,
    LEAVE_REQUEST_TYPES,
)

DEFAULT_LEAVE_REQUEST_MAX_BY_TYPE: dict[str, int] = {
    "off": 0,
    "paid_leave": 0,
    "half_leave": 0,
}

DEFAULT_LEAVE_REQUEST_OVER_LIMIT_MESSAGE = (
    "希望数が上限（{max}件）を超えています。現在 {count} 件です。内容を見直すか、管理者にお問い合わせください。"
)


def normalize_leave_request_visible_types(raw: dict | None) -> dict[str, bool]:
    source = raw if isinstance(raw, dict) else {}
    result: dict[str, bool] = {}
    for key in LEAVE_REQUEST_TYPES:
        if key in source:
            result[key] = bool(source[key])
        else:
            result[key] = DEFAULT_LEAVE_REQUEST_VISIBLE_TYPES.get(key, True)
    if not any(result.values()):
        result["off"] = True
    return result


def normalize_leave_request_max_by_type(raw: dict | None) -> dict[str, int]:
    source = raw if isinstance(raw, dict) else {}
    result: dict[str, int] = {}
    for key in LEAVE_REQUEST_TYPES:
        if key not in source:
            result[key] = 0
            continue
        try:
            value = int(source[key])
        except (TypeError, ValueError):
            value = 0
        result[key] = max(0, min(31, value))
    return result


def normalize_leave_request_settings(settings: dict | None = None) -> dict:
    from db.settings_repository import get_settings

    cfg = settings or get_settings()
    max_total = cfg.get("leave_request_max_total")
    if max_total is not None and max_total != "":
        try:
            max_total = max(0, min(31, int(max_total)))
        except (TypeError, ValueError):
            max_total = None
    else:
        max_total = None

    message = str(cfg.get("leave_request_over_limit_message") or "").strip()
    if not message:
        message = DEFAULT_LEAVE_REQUEST_OVER_LIMIT_MESSAGE

    return {
        "leave_request_visible_types": normalize_leave_request_visible_types(
            cfg.get("leave_request_visible_types")
        ),
        "leave_request_max_total": max_total,
        "leave_request_max_by_type": normalize_leave_request_max_by_type(
            cfg.get("leave_request_max_by_type")
        ),
        "leave_request_over_limit_message": message[:500],
    }


def resolve_max_total_for_period(settings: dict, year: int, month: int) -> int:
    cfg = normalize_leave_request_settings(settings)
    if cfg["leave_request_max_total"] is not None:
        return int(cfg["leave_request_max_total"])
    start_day = int(settings.get("calendar_start_day", 1) or 1)
    _, default_off, _ = resolve_configured_period_off_days(settings, year, month, start_day)
    return max(0, default_off)


def get_portal_request_options(settings: dict | None = None) -> list[dict]:
    cfg = normalize_leave_request_settings(settings)
    visible = cfg["leave_request_visible_types"]
    options: list[dict] = []
    for key in ("off", "paid_leave", "half_leave"):
        if key == "half_leave":
            from db.settings_repository import get_settings

            base = settings or get_settings()
            if not base.get("allow_paid_leave_half", True):
                continue
        if not visible.get(key, True):
            continue
        meta = LEAVE_REQUEST_TYPE_META[key]
        options.append(
            {
                "key": key,
                "label": meta["label"],
                "short_label": meta["short_label"],
            }
        )
    if not options:
        meta = LEAVE_REQUEST_TYPE_META["off"]
        options.append({"key": "off", "label": meta["label"], "short_label": meta["short_label"]})
    return options


def format_over_limit_message(
    template: str,
    *,
    count: int,
    max_count: int,
    staff_name: str = "",
    request_type: str = "",
) -> str:
    type_label = LEAVE_REQUEST_TYPE_META.get(request_type, {}).get("label", request_type)
    return (
        template.replace("{count}", str(count))
        .replace("{max}", str(max_count))
        .replace("{staff_name}", staff_name)
        .replace("{type}", type_label)
        .replace("{type_label}", type_label)
    )


def check_request_limits(
    counts: dict[str, int],
    *,
    settings: dict,
    year: int,
    month: int,
    staff_name: str = "",
    adding_type: str | None = None,
) -> str | None:
    """上限超過時はメッセージ文字列、問題なければ None。"""
    cfg = normalize_leave_request_settings(settings)
    total = sum(counts.values())
    max_total = resolve_max_total_for_period(settings, year, month)

    if adding_type:
        projected = total + 1
        if projected > max_total:
            return format_over_limit_message(
                cfg["leave_request_over_limit_message"],
                count=projected,
                max_count=max_total,
                staff_name=staff_name,
                request_type=adding_type,
            )
        type_limit = cfg["leave_request_max_by_type"].get(adding_type, 0)
        if type_limit > 0 and counts.get(adding_type, 0) + 1 > type_limit:
            return format_over_limit_message(
                cfg["leave_request_over_limit_message"],
                count=counts.get(adding_type, 0) + 1,
                max_count=type_limit,
                staff_name=staff_name,
                request_type=adding_type,
            )
        return None

    if total > max_total:
        return format_over_limit_message(
            cfg["leave_request_over_limit_message"],
            count=total,
            max_count=max_total,
            staff_name=staff_name,
        )
    return None


def period_for_year_month(settings: dict, year: int, month: int) -> tuple:
    start_day = int(settings.get("calendar_start_day", 1) or 1)
    return period_bounds(year, month, start_day)
