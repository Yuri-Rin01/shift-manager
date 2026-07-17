import json
import sqlite3

from db.database import get_connection
from data.night_eligibility import resolve_night_flags
from data.staffing_basis import get_default_staffing_basis_ratios, parse_staffing_basis_raw
from data.masters import filter_staff_for_facility
from schemas.staff import StaffBulkUpdate, StaffCreate, StaffUpdate

STAFF_COLUMNS = (
    "id, name, department, job_type, position, can_work_night, can_be_night_leader, "
    "staffing_basis, exclude_from_staffing, off_days_per_period, "
    "night_shift_count, fix_night_shift_count"
)

NIGHT_INCOMPAT_TABLE = "staff_night_incompatibilities"
DAY_INCOMPAT_TABLE = "staff_day_incompatibilities"


def _merge_day_into_night(night_ids: list[int], day_ids: list[int]) -> list[int]:
    return sorted(set(night_ids) | set(day_ids))


def _parse_staffing_basis(raw: str | None) -> dict[str, int]:
    return parse_staffing_basis_raw(raw)


def _serialize_staffing_basis(values: dict[str, int]) -> str:
    return json.dumps(values, ensure_ascii=False)


def _primary_department(floors: list[str]) -> str:
    return floors[0] if floors else ""


def _load_floors_map(conn: sqlite3.Connection, table: str = "staff_floors") -> dict[int, list[str]]:
    mapping: dict[int, list[str]] = {}
    rows = conn.execute(
        f"""
        SELECT staff_id, floor
        FROM {table}
        ORDER BY floor
        """
    ).fetchall()
    for row in rows:
        mapping.setdefault(row["staff_id"], []).append(row["floor"])
    return mapping


def _load_floors(conn: sqlite3.Connection, staff_id: int, table: str = "staff_floors") -> list[str]:
    rows = conn.execute(
        f"""
        SELECT floor
        FROM {table}
        WHERE staff_id = ?
        ORDER BY floor
        """,
        (staff_id,),
    ).fetchall()
    if rows:
        return [row["floor"] for row in rows]
    if table == "staff_floors":
        row = conn.execute("SELECT department FROM staff WHERE id = ?", (staff_id,)).fetchone()
        return [row["department"]] if row and row["department"] else []
    return _load_floors(conn, staff_id, "staff_floors")


def _set_floors(conn: sqlite3.Connection, staff_id: int, floors: list[str], table: str = "staff_floors") -> None:
    unique_floors = list(dict.fromkeys(floors))
    conn.execute(f"DELETE FROM {table} WHERE staff_id = ?", (staff_id,))
    conn.executemany(
        f"INSERT INTO {table} (staff_id, floor) VALUES (?, ?)",
        [(staff_id, floor) for floor in unique_floors],
    )


def _load_incompatibilities_map(conn: sqlite3.Connection, table: str) -> dict[int, list[int]]:
    mapping: dict[int, list[int]] = {}
    rows = conn.execute(
        f"""
        SELECT staff_id, incompatible_staff_id
        FROM {table}
        ORDER BY incompatible_staff_id
        """
    ).fetchall()
    for row in rows:
        mapping.setdefault(row["staff_id"], []).append(row["incompatible_staff_id"])
    return mapping


def _load_incompatibilities(conn: sqlite3.Connection, staff_id: int, table: str) -> list[int]:
    rows = conn.execute(
        f"""
        SELECT incompatible_staff_id
        FROM {table}
        WHERE staff_id = ?
        ORDER BY incompatible_staff_id
        """,
        (staff_id,),
    ).fetchall()
    return [row["incompatible_staff_id"] for row in rows]


def _set_incompatibilities(
    conn: sqlite3.Connection,
    staff_id: int,
    incompatible_ids: list[int],
    table: str,
) -> None:
    unique_ids = sorted({other_id for other_id in incompatible_ids if other_id != staff_id})
    conn.execute(f"DELETE FROM {table} WHERE staff_id = ?", (staff_id,))
    conn.executemany(
        f"""
        INSERT INTO {table} (staff_id, incompatible_staff_id)
        VALUES (?, ?)
        """,
        [(staff_id, other_id) for other_id in unique_ids],
    )


def _row_to_dict(
    row: sqlite3.Row,
    floors: list[str],
    placement_floors: list[str] | None = None,
    night_incompatible_ids: list[int] | None = None,
    day_incompatible_ids: list[int] | None = None,
) -> dict:
    raw_floors = floors or ([row["department"]] if row["department"] else [])
    # 担当フロアは表示用に1つのみ。過去データで複数ある場合は先頭を採用し余剰は配置可能へ。
    primary = row["department"] if row["department"] in raw_floors else (raw_floors[0] if raw_floors else "")
    departments = [primary] if primary else []
    placement = placement_floors if placement_floors is not None else list(raw_floors)
    if not placement:
        placement = list(raw_floors) or list(departments)
    else:
        # 旧・担当の余剰フロアを配置可能から落とさない
        merged = list(dict.fromkeys([*placement, *raw_floors]))
        placement = merged
    keys = row.keys()
    can_work_night, can_be_night_leader = resolve_night_flags(
        can_work_night=bool(row["can_work_night"]),
        can_be_night_leader=bool(row["can_be_night_leader"]) if "can_be_night_leader" in keys else False,
    )
    return {
        "id": row["id"],
        "name": row["name"],
        "departments": departments,
        "department": _primary_department(departments),
        "placement_floors": placement,
        "job_type": row["job_type"],
        "position": row["position"],
        "can_work_night": can_work_night,
        "can_be_night_leader": can_be_night_leader,
        "staffing_basis": _parse_staffing_basis(row["staffing_basis"]),
        "exclude_from_staffing": bool(row["exclude_from_staffing"]),
        "off_days_per_period": (
            int(row["off_days_per_period"])
            if "off_days_per_period" in keys and row["off_days_per_period"] is not None
            else None
        ),
        "night_shift_count": (
            int(row["night_shift_count"])
            if row["night_shift_count"] is not None
            else None
        ),
        "fix_night_shift_count": bool(row["fix_night_shift_count"]),
        "night_incompatible_ids": night_incompatible_ids or [],
        "day_incompatible_ids": day_incompatible_ids or [],
    }


def list_staff() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT {STAFF_COLUMNS} FROM staff ORDER BY department, name"
        ).fetchall()
        floors_map = _load_floors_map(conn)
        placement_map = _load_floors_map(conn, "staff_placement_floors")
        night_map = _load_incompatibilities_map(conn, NIGHT_INCOMPAT_TABLE)
        day_map = _load_incompatibilities_map(conn, DAY_INCOMPAT_TABLE)
    staff = [
        _row_to_dict(
            row,
            floors_map.get(row["id"], []),
            placement_map.get(row["id"], floors_map.get(row["id"], [])),
            night_map.get(row["id"], []),
            day_map.get(row["id"], []),
        )
        for row in rows
    ]
    return filter_staff_for_facility(staff)


def get_staff(staff_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            f"SELECT {STAFF_COLUMNS} FROM staff WHERE id = ?",
            (staff_id,),
        ).fetchone()
        if row is None:
            return None
        floors = _load_floors(conn, staff_id)
        placement_floors = _load_floors(conn, staff_id, "staff_placement_floors")
        night_ids = _load_incompatibilities(conn, staff_id, NIGHT_INCOMPAT_TABLE)
        day_ids = _load_incompatibilities(conn, staff_id, DAY_INCOMPAT_TABLE)
    return _row_to_dict(row, floors, placement_floors, night_ids, day_ids)


def create_staff(data: StaffCreate) -> dict:
    primary = _primary_department(data.departments)
    can_work_night, can_be_night_leader = resolve_night_flags(
        can_work_night=data.can_work_night,
        can_be_night_leader=data.can_be_night_leader,
    )
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO staff (
                name, department, job_type, position, can_work_night, can_be_night_leader,
                staffing_basis, exclude_from_staffing, off_days_per_period,
                night_shift_count, fix_night_shift_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.name,
                primary,
                data.job_type,
                data.position,
                int(can_work_night),
                int(can_be_night_leader),
                _serialize_staffing_basis(data.staffing_basis),
                int(data.exclude_from_staffing),
                data.off_days_per_period,
                data.night_shift_count if data.fix_night_shift_count else None,
                int(data.fix_night_shift_count),
            ),
        )
        staff_id = cursor.lastrowid
        _set_floors(conn, staff_id, data.departments)
        _set_floors(conn, staff_id, data.placement_floors, "staff_placement_floors")
        night_ids = _merge_day_into_night(data.night_incompatible_ids, data.day_incompatible_ids)
        _set_incompatibilities(conn, staff_id, night_ids, NIGHT_INCOMPAT_TABLE)
        _set_incompatibilities(conn, staff_id, data.day_incompatible_ids, DAY_INCOMPAT_TABLE)
        conn.commit()
    staff = get_staff(staff_id)
    assert staff is not None
    return staff


def update_staff(staff_id: int, data: StaffUpdate) -> dict | None:
    current = get_staff(staff_id)
    if current is None:
        return None

    fields_set = data.model_fields_set
    departments = data.departments if data.departments is not None else current["departments"]
    placement_floors = (
        data.placement_floors
        if data.placement_floors is not None
        else current.get("placement_floors") or departments
    )
    updated = {
        "name": data.name if data.name is not None else current["name"],
        "departments": departments,
        "placement_floors": placement_floors,
        "department": _primary_department(departments),
        "job_type": data.job_type if data.job_type is not None else current["job_type"],
        "position": data.position if data.position is not None else current["position"],
        "can_work_night": (
            data.can_work_night if data.can_work_night is not None else current["can_work_night"]
        ),
        "can_be_night_leader": (
            data.can_be_night_leader
            if data.can_be_night_leader is not None
            else current.get("can_be_night_leader", False)
        ),
        "staffing_basis": (
            data.staffing_basis if data.staffing_basis is not None else current["staffing_basis"]
        ),
        "exclude_from_staffing": (
            data.exclude_from_staffing
            if data.exclude_from_staffing is not None
            else current["exclude_from_staffing"]
        ),
        "off_days_per_period": (
            data.off_days_per_period
            if "off_days_per_period" in fields_set
            else current.get("off_days_per_period")
        ),
        "night_shift_count": (
            data.night_shift_count
            if "night_shift_count" in fields_set
            else current["night_shift_count"]
        ),
        "fix_night_shift_count": (
            data.fix_night_shift_count
            if "fix_night_shift_count" in fields_set
            else current["fix_night_shift_count"]
        ),
        "night_incompatible_ids": (
            data.night_incompatible_ids
            if data.night_incompatible_ids is not None
            else current["night_incompatible_ids"]
        ),
        "day_incompatible_ids": (
            data.day_incompatible_ids
            if data.day_incompatible_ids is not None
            else current["day_incompatible_ids"]
        ),
    }

    can_work_night, can_be_night_leader = resolve_night_flags(
        can_work_night=updated["can_work_night"],
        can_be_night_leader=updated["can_be_night_leader"],
    )
    updated["can_work_night"] = can_work_night
    updated["can_be_night_leader"] = can_be_night_leader

    if not updated["fix_night_shift_count"]:
        updated["night_shift_count"] = None

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE staff
            SET name = ?, department = ?, job_type = ?, position = ?, can_work_night = ?,
                can_be_night_leader = ?, staffing_basis = ?, exclude_from_staffing = ?,
                off_days_per_period = ?, night_shift_count = ?, fix_night_shift_count = ?
            WHERE id = ?
            """,
            (
                updated["name"],
                updated["department"],
                updated["job_type"],
                updated["position"],
                int(updated["can_work_night"]),
                int(updated["can_be_night_leader"]),
                _serialize_staffing_basis(updated["staffing_basis"]),
                int(updated["exclude_from_staffing"]),
                updated.get("off_days_per_period"),
                updated["night_shift_count"],
                int(updated["fix_night_shift_count"]),
                staff_id,
            ),
        )
        _set_floors(conn, staff_id, updated["departments"])
        _set_floors(conn, staff_id, updated["placement_floors"], "staff_placement_floors")
        night_ids = _merge_day_into_night(
            updated["night_incompatible_ids"], updated["day_incompatible_ids"]
        )
        _set_incompatibilities(conn, staff_id, night_ids, NIGHT_INCOMPAT_TABLE)
        _set_incompatibilities(conn, staff_id, updated["day_incompatible_ids"], DAY_INCOMPAT_TABLE)
        conn.commit()
    return get_staff(staff_id)


def bulk_update_staff(data: StaffBulkUpdate) -> tuple[list[dict], list[int]]:
    fields_set = data.model_fields_set - {"ids", "departments_mode"}
    if not fields_set:
        raise ValueError("変更する項目を1つ以上指定してください。")

    updated: list[dict] = []
    not_found: list[int] = []
    for staff_id in data.ids:
        current = get_staff(staff_id)
        if current is None:
            not_found.append(staff_id)
            continue

        patch: dict = {field: getattr(data, field) for field in fields_set}

        if "fix_night_shift_count" in patch and not patch["fix_night_shift_count"]:
            patch["night_shift_count"] = None

        result = update_staff(staff_id, StaffUpdate(**patch))
        if result is not None:
            updated.append(result)

    return updated, not_found


def delete_staff(staff_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM staff WHERE id = ?", (staff_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_all_staff_ids() -> set[int]:
    with get_connection() as conn:
        rows = conn.execute("SELECT id FROM staff").fetchall()
    return {row["id"] for row in rows}
