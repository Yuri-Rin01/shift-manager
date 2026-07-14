import json

from db.database import get_connection
from data.settings_defaults import DEFAULT_SETTINGS
from data.shift_symbols import DEFAULT_SHIFT_SYMBOLS, validate_shift_symbols
from data.placement_rules import (
    normalize_min_staff_by_floor,
    normalize_min_staff_by_work_type,
    normalize_staffing_requirement_mode,
    normalize_time_slot_staffing_rules,
    validate_min_staff_by_floor,
    validate_min_staff_by_work_type,
    validate_time_slot_staffing_rules,
)
from data.leave_request_config import (
    normalize_leave_request_max_by_type,
    normalize_leave_request_settings,
    normalize_leave_request_visible_types,
)

SETTINGS_ID = 1


def _merge_settings(data: dict | None) -> dict:
    merged = {**DEFAULT_SETTINGS}
    if not data:
        return merged
    for key, value in data.items():
        if key not in DEFAULT_SETTINGS:
            continue
        if key == "shift_symbols" and isinstance(value, dict):
            cleaned = {k: v for k, v in value.items() if k != "public"}
            merged[key] = {**DEFAULT_SHIFT_SYMBOLS, **cleaned}
        elif key == "visible_work_types" and isinstance(value, dict):
            from data.shift_symbols import normalize_visible_work_types

            merged[key] = normalize_visible_work_types({**merged, "visible_work_types": value})
        elif key == "staffing_basis_options" and isinstance(value, list) and value:
            from data.staffing_basis import normalize_staffing_basis_options

            merged[key] = normalize_staffing_basis_options(value)
        elif key == "min_staff_by_work_type" and isinstance(value, dict):
            merged[key] = normalize_min_staff_by_work_type(value, merged)
        elif key == "min_staff_by_floor" and isinstance(value, dict):
            merged[key] = normalize_min_staff_by_floor(value, merged)
        elif key == "time_slot_staffing_rules" and isinstance(value, list):
            merged[key] = normalize_time_slot_staffing_rules(value)
        elif key == "staffing_requirement_mode":
            merged[key] = normalize_staffing_requirement_mode(value)
        elif key == "leave_request_visible_types" and isinstance(value, dict):
            merged[key] = normalize_leave_request_visible_types(value)
        elif key == "leave_request_max_by_type" and isinstance(value, dict):
            merged[key] = normalize_leave_request_max_by_type(value)
        else:
            merged[key] = value
    from data.shift_symbols import normalize_visible_work_types

    merged["visible_work_types"] = normalize_visible_work_types(merged)
    merged["allow_paid_leave_half"] = merged["visible_work_types"].get("half_leave", True)
    merged["show_training_mark"] = merged["visible_work_types"].get("training", True)
    merged["min_staff_by_work_type"] = normalize_min_staff_by_work_type(
        merged.get("min_staff_by_work_type"), merged
    )
    merged["min_staff_by_floor"] = normalize_min_staff_by_floor(
        merged.get("min_staff_by_floor"), merged
    )
    merged["staffing_requirement_mode"] = normalize_staffing_requirement_mode(
        merged.get("staffing_requirement_mode")
    )
    merged["time_slot_staffing_rules"] = normalize_time_slot_staffing_rules(
        merged.get("time_slot_staffing_rules")
    )
    merged["block_work_after_night"] = True
    merged["morning_off_after_night"] = True
    leave_cfg = normalize_leave_request_settings(merged)
    merged.update(leave_cfg)
    return merged

def get_settings() -> dict:
    with get_connection() as conn:
        row = conn.execute("SELECT data FROM app_settings WHERE id = ?", (SETTINGS_ID,)).fetchone()
    if row is None:
        return dict(DEFAULT_SETTINGS)
    try:
        stored = json.loads(row["data"])
    except json.JSONDecodeError:
        stored = {}
    return _merge_settings(stored)


def save_settings(data: dict) -> dict:
    merged = _merge_settings(data)
    validate_shift_symbols(merged)
    validate_staffing_basis_options(merged)
    validate_min_staff_by_work_type(merged)
    validate_min_staff_by_floor(merged)
    validate_time_slot_staffing_rules(merged)
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO app_settings (id, data) VALUES (?, ?)
            ON CONFLICT(id) DO UPDATE SET data = excluded.data
            """,
            (SETTINGS_ID, json.dumps(merged, ensure_ascii=False)),
        )
        conn.commit()
    return merged
