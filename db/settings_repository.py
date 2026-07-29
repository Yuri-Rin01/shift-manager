import json

from db.database import get_connection
from data.settings_defaults import DEFAULT_SETTINGS
from data.shift_symbols import DEFAULT_SHIFT_SYMBOLS, validate_shift_symbols
from data.placement_rules import (
    apply_overnight_rules_to_night_mins,
    normalize_min_staff_by_floor,
    normalize_min_staff_by_work_type,
    normalize_night_leader_groups,
    normalize_staffing_requirement_mode,
    normalize_time_slot_staffing_rules,
    validate_min_staff_by_floor,
    validate_min_staff_by_work_type,
    validate_night_leader_groups,
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
            merged[key] = value
        elif key == "time_slot_staffing_rules" and isinstance(value, list):
            # 正規化前の生データを一旦保持し、夜勤帯→固定人数へ移してから落とす
            merged[key] = value
        elif key == "night_leader_groups" and isinstance(value, list):
            merged[key] = value
        elif key == "staffing_requirement_mode":
            merged[key] = normalize_staffing_requirement_mode(value)
        elif key == "leave_request_visible_types" and isinstance(value, dict):
            merged[key] = normalize_leave_request_visible_types(value)
        elif key == "leave_request_max_by_type" and isinstance(value, dict):
            merged[key] = normalize_leave_request_max_by_type(value)
        elif key == "sheet_view_colors" and isinstance(value, dict):
            from data.sheet_view_colors import normalize_sheet_view_colors

            merged[key] = normalize_sheet_view_colors(value)
        elif key == "student_labor_limits" and isinstance(value, dict):
            from data.student_labor_limits import normalize_student_labor_limits

            merged[key] = normalize_student_labor_limits(value)
        elif key == "cell_flick_directions" and isinstance(value, list):
            from data.flick_directions import normalize_cell_flick_directions

            merged[key] = normalize_cell_flick_directions(value)
        else:
            merged[key] = value
    from data.shift_symbols import normalize_visible_work_types

    merged["visible_work_types"] = normalize_visible_work_types(merged)
    merged["allow_paid_leave_half"] = merged["visible_work_types"].get("half_leave", True)
    merged["show_training_mark"] = merged["visible_work_types"].get("training", True)
    from data.flick_directions import normalize_cell_flick_directions

    merged["cell_flick_directions"] = normalize_cell_flick_directions(
        merged.get("cell_flick_directions")
    )
    merged["staffing_requirement_mode"] = normalize_staffing_requirement_mode(
        merged.get("staffing_requirement_mode")
    )
    # 時間帯ルール内の夜勤帯をフロア別夜勤人数へ移す（人数固定の別枠）
    apply_overnight_rules_to_night_mins(merged)
    merged["min_staff_by_work_type"] = normalize_min_staff_by_work_type(
        merged.get("min_staff_by_work_type"), merged
    )
    merged["min_staff_by_floor"] = normalize_min_staff_by_floor(
        merged.get("min_staff_by_floor"), merged
    )
    merged["time_slot_staffing_rules"] = normalize_time_slot_staffing_rules(
        merged.get("time_slot_staffing_rules")
    )
    merged["night_leader_groups"] = normalize_night_leader_groups(
        merged.get("night_leader_groups")
    )
    merged["block_work_after_night"] = True
    merged["morning_off_after_night"] = True
    leave_cfg = normalize_leave_request_settings(merged)
    merged.update(leave_cfg)
    from data.student_labor_limits import normalize_student_labor_limits

    merged["student_labor_limits"] = normalize_student_labor_limits(
        merged.get("student_labor_limits")
    )
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
    from data.staffing_basis import validate_staffing_basis_options

    previous = get_settings()
    merged = _merge_settings(data)
    validate_shift_symbols(merged)
    validate_staffing_basis_options(merged)
    validate_min_staff_by_work_type(merged)
    validate_min_staff_by_floor(merged)
    validate_time_slot_staffing_rules(merged)
    validate_night_leader_groups(merged)
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO app_settings (id, data) VALUES (?, ?)
            ON CONFLICT(id) DO UPDATE SET data = excluded.data
            """,
            (SETTINGS_ID, json.dumps(merged, ensure_ascii=False)),
        )
        _append_settings_change_log(
            conn,
            key="student_labor_limits",
            before=previous.get("student_labor_limits"),
            after=merged.get("student_labor_limits"),
        )
        conn.commit()
    return merged


def _append_settings_change_log(conn, *, key: str, before, after) -> None:
    if before == after:
        return
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS settings_change_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            changed_at TEXT NOT NULL,
            setting_key TEXT NOT NULL,
            before_json TEXT NOT NULL,
            after_json TEXT NOT NULL
        )
        """
    )
    from datetime import datetime, timezone, timedelta

    jst = timezone(timedelta(hours=9))
    conn.execute(
        """
        INSERT INTO settings_change_log (changed_at, setting_key, before_json, after_json)
        VALUES (?, ?, ?, ?)
        """,
        (
            datetime.now(jst).isoformat(timespec="seconds"),
            key,
            json.dumps(before, ensure_ascii=False),
            json.dumps(after, ensure_ascii=False),
        ),
    )
