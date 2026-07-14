from __future__ import annotations

from datetime import date

from data.calendar_period import format_period_label, period_bounds
from data.leave_request_config import (
    check_request_limits,
    get_portal_request_options,
    normalize_leave_request_settings,
    resolve_max_total_for_period,
)
from data.leave_request_types import LEAVE_REQUEST_TYPE_META
from data.shift_symbols import DEFAULT_SHIFT_SYMBOLS
from db import leave_request_repository as leave_repo
from db.settings_repository import get_settings, save_settings
from db.shift_repository import bulk_upsert_shifts, delete_shift_cell, get_shift_cell
from db.staff_repository import get_staff, list_staff


def _symbol_for_request_type(request_type: str, settings: dict) -> str:
    symbols = settings.get("shift_symbols") or DEFAULT_SHIFT_SYMBOLS
    return symbols.get(request_type) or DEFAULT_SHIFT_SYMBOLS.get(request_type, "休")


def build_admin_page_data(year: int, month: int) -> dict:
    settings = get_settings()
    start_day = int(settings.get("calendar_start_day", 1) or 1)
    period_start, period_end = period_bounds(year, month, start_day)
    leave_cfg = normalize_leave_request_settings(settings)
    max_total = resolve_max_total_for_period(settings, year, month)
    summary = leave_repo.summarize_period(period_start, period_end)
    requests = leave_repo.list_requests_between(
        period_start,
        period_end,
        statuses=("pending", "approved", "rejected"),
    )

    staff_by_id = {person["id"]: person for person in list_staff()}
    staff_rows = []
    over_limit_count = 0
    for staff_id, person in sorted(staff_by_id.items(), key=lambda item: item[1]["name"]):
        bucket = summary["by_staff"].get(
            staff_id,
            {"total": 0, "pending": 0, "approved": 0, "by_type": {}},
        )
        over_limit = check_request_limits(
            bucket.get("by_type", {}),
            settings=settings,
            year=year,
            month=month,
            staff_name=person["name"],
        )
        if over_limit:
            over_limit_count += 1
        staff_rows.append(
            {
                "staff_id": staff_id,
                "name": person["name"],
                "departments": person.get("departments") or [person.get("department", "")],
                "job_type": person.get("job_type", ""),
                "pending": bucket.get("pending", 0),
                "approved": bucket.get("approved", 0),
                "total": bucket.get("total", 0),
                "by_type": bucket.get("by_type", {}),
                "over_limit": over_limit is not None,
                "over_limit_message": over_limit or "",
            }
        )

    request_rows = []
    for item in requests:
        person = staff_by_id.get(item["staff_id"])
        meta = LEAVE_REQUEST_TYPE_META.get(item["request_type"], {})
        request_rows.append(
            {
                **item,
                "staff_name": person["name"] if person else f"ID:{item['staff_id']}",
                "type_label": meta.get("label", item["request_type"]),
                "type_short": meta.get("short_label", item["request_type"]),
            }
        )

    return {
        "year": year,
        "month": month,
        "period_label": format_period_label(
            period_start, period_end, year=year, month=month, start_day=start_day
        ),
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "summary": {
            "total": summary["total"],
            "pending": summary["pending"],
            "approved": summary["approved"],
            "over_limit_staff": over_limit_count,
        },
        "staff_rows": staff_rows,
        "requests": request_rows,
        "portal_options": get_portal_request_options(settings),
        "leave_settings": {
            **leave_cfg,
            "leave_request_max_total_resolved": max_total,
        },
        "type_meta": [
            {
                "key": key,
                "label": LEAVE_REQUEST_TYPE_META[key]["label"],
                "short_label": LEAVE_REQUEST_TYPE_META[key]["short_label"],
            }
            for key in ("off", "paid_leave", "half_leave")
        ],
    }


def update_leave_request_settings(payload: dict) -> dict:
    current = get_settings()
    merged = {**current}
    if "leave_request_visible_types" in payload:
        merged["leave_request_visible_types"] = payload["leave_request_visible_types"]
    if "leave_request_max_total" in payload:
        value = payload["leave_request_max_total"]
        merged["leave_request_max_total"] = value if value is not None and value != "" else None
    if "leave_request_max_by_type" in payload:
        merged["leave_request_max_by_type"] = payload["leave_request_max_by_type"]
    if "leave_request_over_limit_message" in payload:
        merged["leave_request_over_limit_message"] = payload["leave_request_over_limit_message"]
    saved = save_settings(merged)
    return build_leave_settings_response(saved)


def build_leave_settings_response(settings: dict | None = None) -> dict:
    from db.settings_repository import get_settings

    cfg = settings or get_settings()
    leave_cfg = normalize_leave_request_settings(cfg)
    today = date.today()
    start_day = int(cfg.get("calendar_start_day", 1) or 1)
    return {
        **leave_cfg,
        "leave_request_max_total_resolved": resolve_max_total_for_period(
            cfg, today.year, today.month
        ),
    }


def approve_request(request_id: int) -> dict:
    settings = get_settings()
    request = leave_repo.get_request_by_id(request_id)
    if request is None:
        raise ValueError("希望が見つかりません。")
    if request["status"] != "pending":
        raise ValueError("承認待ちの希望のみ承認できます。")

    staff = get_staff(request["staff_id"])
    if staff is None:
        raise ValueError("職員が見つかりません。")

    shift_date = date.fromisoformat(request["shift_date"])
    existing_shift = get_shift_cell(request["staff_id"], shift_date)
    if existing_shift and existing_shift.get("source") == "manual":
        raise ValueError("手動入力済みのシフトがある日は承認できません。")

    symbol = _symbol_for_request_type(request["request_type"], settings)
    bulk_upsert_shifts(
        [
            (
                request["staff_id"],
                request["shift_date"],
                symbol,
                "leave",
            )
        ]
    )
    updated = leave_repo.update_request_status(request_id, "approved")
    if updated is None:
        raise ValueError("希望の更新に失敗しました。")
    return updated


def reject_request(request_id: int) -> dict:
    request = leave_repo.get_request_by_id(request_id)
    if request is None:
        raise ValueError("希望が見つかりません。")
    if request["status"] != "pending":
        raise ValueError("承認待ちの希望のみ却下できます。")
    updated = leave_repo.update_request_status(request_id, "rejected")
    if updated is None:
        raise ValueError("希望の更新に失敗しました。")
    return updated


def bulk_update_requests(request_ids: list[int], action: str) -> dict:
    if action not in {"approve", "reject"}:
        raise ValueError("操作が不正です。")
    updated: list[dict] = []
    errors: list[dict] = []
    for request_id in request_ids:
        try:
            if action == "approve":
                updated.append(approve_request(request_id))
            else:
                updated.append(reject_request(request_id))
        except ValueError as exc:
            errors.append({"id": request_id, "detail": str(exc)})
    return {"updated": updated, "errors": errors}
