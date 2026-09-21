import json

from db.database import get_connection
from data.settings_defaults import DEFAULT_SETTINGS
from data.staffing_basis import validate_staffing_basis_options
from data.shift_symbols import DEFAULT_SHIFT_SYMBOLS, validate_shift_symbols, get_shift_symbols, symbol_to_key
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
from data.floors import (
    assert_floor_deletable,
    get_floors,
    normalize_floors,
    rename_floor_label,
    validate_floors,
)

SETTINGS_ID = 1


def _merge_settings(data: dict | None) -> dict:
    merged = {**DEFAULT_SETTINGS}
    if not data:
        return merged
    from data.staffing_basis import normalize_staffing_basis_options
    if data.get("staffing_basis_options"):
        merged["staffing_basis_options"] = normalize_staffing_basis_options(data["staffing_basis_options"])
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
            merged[key] = normalize_time_slot_staffing_rules(value, merged)
        elif key == "staffing_requirement_mode":
            merged[key] = normalize_staffing_requirement_mode(value)
        elif key == "leave_request_visible_types" and isinstance(value, dict):
            merged[key] = normalize_leave_request_visible_types(value)
        elif key == "leave_request_max_by_type" and isinstance(value, dict):
            merged[key] = normalize_leave_request_max_by_type(value)
        elif key == "floors" and isinstance(value, list):
            merged[key] = normalize_floors(value)
        else:
            merged[key] = value
    from data.shift_symbols import normalize_visible_work_types

    merged["visible_work_types"] = normalize_visible_work_types(merged)
    merged["allow_paid_leave_half"] = merged["visible_work_types"].get("half_leave", True)
    merged["show_training_mark"] = merged["visible_work_types"].get("training", True)
    merged["floors"] = normalize_floors(merged.get("floors"))
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
        merged.get("time_slot_staffing_rules"), merged
    )
    merged["prioritize_leave_requests"] = True
    merged["consider_night_eligibility"] = True
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
    incoming = dict(data)
    current = get_settings()
    current_floors = {item["id"]: item["label"] for item in get_floors(current)}
    next_floors = validate_floors(incoming.get("floors", current.get("floors")))
    next_by_id = {item["id"]: item["label"] for item in next_floors}

    for floor_id, label in current_floors.items():
        if floor_id not in next_by_id:
            assert_floor_deletable(label)

    working = dict(incoming)
    working["floors"] = next_floors

    # 改名に伴う設定内キーの先更新（DB更新はトランザクション内）
    for floor_id, old_label in current_floors.items():
        new_label = next_by_id.get(floor_id)
        if not new_label or new_label == old_label:
            continue
        min_by_floor = working.get("min_staff_by_floor")
        if isinstance(min_by_floor, dict) and old_label in min_by_floor:
            next_map = dict(min_by_floor)
            next_map[new_label] = next_map.pop(old_label)
            working["min_staff_by_floor"] = next_map
        rules = working.get("time_slot_staffing_rules")
        if isinstance(rules, list):
            working["time_slot_staffing_rules"] = [
                {**rule, "floor": new_label}
                if isinstance(rule, dict) and str(rule.get("floor", "")).strip() == old_label
                else rule
                for rule in rules
            ]

    merged = _merge_settings(working)
    merged["floors"] = next_floors
    validate_shift_symbols(merged)
    validate_staffing_basis_options(merged)
    validate_min_staff_by_work_type(merged)
    validate_min_staff_by_floor(merged)
    validate_time_slot_staffing_rules(merged)
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT data FROM app_settings WHERE id = ?", (SETTINGS_ID,)).fetchone()
        old = _merge_settings(json.loads(row["data"]) if row else {})
        for floor_id, old_label in current_floors.items():
            new_label = next_by_id.get(floor_id)
            if new_label and new_label != old_label:
                rename_floor_label(old_label, new_label, {"floors": get_floors(old)}, conn=conn)
        new_symbols = get_shift_symbols(merged)
        changes = []
        for cell in conn.execute("SELECT staff_id, shift_date, symbol FROM shift_assignments").fetchall():
            key = symbol_to_key(cell["symbol"], old)
            if key and key not in new_symbols:
                raise ValueError("使用中の勤務区分は削除できません。先に勤務表の割り当てを変更してください。")
            if key and new_symbols[key] != cell["symbol"]:
                changes.append((new_symbols[key], cell["staff_id"], cell["shift_date"]))
        placements = (
            conn.execute("SELECT staff_id, shift_date, floor, role FROM shift_placements").fetchall()
            if changes
            else []
        )
        conn.executemany(
            "UPDATE shift_assignments SET symbol = ? WHERE staff_id = ? AND shift_date = ?",
            changes,
        )
        conn.executemany(
            "INSERT OR REPLACE INTO shift_placements(staff_id, shift_date, floor, role) VALUES (?, ?, ?, ?)",
            [tuple(r) for r in placements],
        )
        conn.execute(
            """
            INSERT INTO app_settings (id, data) VALUES (?, ?)
            ON CONFLICT(id) DO UPDATE SET data = excluded.data
            """,
            (SETTINGS_ID, json.dumps(merged, ensure_ascii=False)),
        )
        conn.commit()
    return merged
