from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime

from db.database import get_connection

ACTIVE_STATUSES = ("pending", "approved")
ALL_STATUSES = ("pending", "approved", "rejected", "cancelled")


def _row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "staff_id": row["staff_id"],
        "shift_date": row["shift_date"],
        "request_type": row["request_type"],
        "note": row["note"] or "",
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_requests_for_staff_between(
    staff_id: int,
    start: date,
    end: date,
    *,
    statuses: tuple[str, ...] | None = None,
) -> list[dict]:
    status_filter = statuses or ACTIVE_STATUSES
    placeholders = ",".join("?" for _ in status_filter)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT id, staff_id, shift_date, request_type, note, status, created_at, updated_at
            FROM leave_requests
            WHERE staff_id = ?
              AND shift_date >= ?
              AND shift_date <= ?
              AND status IN ({placeholders})
            ORDER BY shift_date
            """,
            (staff_id, start.isoformat(), end.isoformat(), *status_filter),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def list_requests_between(
    start: date,
    end: date,
    *,
    statuses: tuple[str, ...] | None = None,
    staff_id: int | None = None,
) -> list[dict]:
    clauses = ["shift_date >= ?", "shift_date <= ?"]
    params: list = [start.isoformat(), end.isoformat()]
    if statuses:
        placeholders = ",".join("?" for _ in statuses)
        clauses.append(f"status IN ({placeholders})")
        params.extend(statuses)
    if staff_id is not None:
        clauses.append("staff_id = ?")
        params.append(staff_id)
    where = " AND ".join(clauses)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT id, staff_id, shift_date, request_type, note, status, created_at, updated_at
            FROM leave_requests
            WHERE {where}
            ORDER BY shift_date, staff_id, id
            """,
            params,
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def count_active_requests_by_staff(
    staff_id: int,
    start: date,
    end: date,
    *,
    exclude_date: date | None = None,
) -> dict[str, int]:
    requests = list_requests_for_staff_between(staff_id, start, end)
    counts: Counter[str] = Counter()
    for item in requests:
        if exclude_date and item["shift_date"] == exclude_date.isoformat():
            continue
        counts[item["request_type"]] += 1
    return dict(counts)


def get_request_by_id(request_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, staff_id, shift_date, request_type, note, status, created_at, updated_at
            FROM leave_requests WHERE id = ?
            """,
            (request_id,),
        ).fetchone()
    return _row_to_dict(row) if row else None


def get_request_for_staff_date(staff_id: int, shift_date: date) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, staff_id, shift_date, request_type, note, status, created_at, updated_at
            FROM leave_requests
            WHERE staff_id = ? AND shift_date = ? AND status IN ('pending', 'approved')
            ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, id DESC
            LIMIT 1
            """,
            (staff_id, shift_date.isoformat()),
        ).fetchone()
    return _row_to_dict(row) if row else None


def upsert_pending_request(
    staff_id: int,
    shift_date: date,
    request_type: str,
    *,
    note: str = "",
) -> dict:
    now = datetime.now().isoformat(timespec="seconds")
    iso_date = shift_date.isoformat()
    with get_connection() as conn:
        existing = conn.execute(
            """
            SELECT id, status
            FROM leave_requests
            WHERE staff_id = ? AND shift_date = ? AND status IN ('pending', 'approved')
            ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, id DESC
            LIMIT 1
            """,
            (staff_id, iso_date),
        ).fetchone()

        if existing and existing["status"] == "approved":
            raise ValueError("承認済みの希望日は変更できません。管理者に連絡してください。")

        if existing:
            conn.execute(
                """
                UPDATE leave_requests
                SET request_type = ?, note = ?, status = 'pending', updated_at = ?
                WHERE id = ?
                """,
                (request_type, note, now, existing["id"]),
            )
            request_id = existing["id"]
        else:
            cursor = conn.execute(
                """
                INSERT INTO leave_requests (
                    staff_id, shift_date, request_type, note, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'pending', ?, ?)
                """,
                (staff_id, iso_date, request_type, note, now, now),
            )
            request_id = cursor.lastrowid
        conn.commit()
        row = conn.execute(
            """
            SELECT id, staff_id, shift_date, request_type, note, status, created_at, updated_at
            FROM leave_requests WHERE id = ?
            """,
            (request_id,),
        ).fetchone()
    return _row_to_dict(row)


def cancel_pending_request(staff_id: int, shift_date: date) -> bool:
    now = datetime.now().isoformat(timespec="seconds")
    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE leave_requests
            SET status = 'cancelled', updated_at = ?
            WHERE staff_id = ? AND shift_date = ? AND status = 'pending'
            """,
            (now, staff_id, shift_date.isoformat()),
        )
        conn.commit()
        return cursor.rowcount > 0


def update_request_status(request_id: int, status: str) -> dict | None:
    if status not in ALL_STATUSES:
        raise ValueError("ステータスが不正です。")
    now = datetime.now().isoformat(timespec="seconds")
    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE leave_requests
            SET status = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, now, request_id),
        )
        if cursor.rowcount == 0:
            return None
        conn.commit()
        row = conn.execute(
            """
            SELECT id, staff_id, shift_date, request_type, note, status, created_at, updated_at
            FROM leave_requests WHERE id = ?
            """,
            (request_id,),
        ).fetchone()
    return _row_to_dict(row) if row else None


def summarize_period(
    start: date,
    end: date,
) -> dict:
    requests = list_requests_between(start, end, statuses=ACTIVE_STATUSES)
    by_status: Counter[str] = Counter()
    by_staff: dict[int, dict] = defaultdict(
        lambda: {"total": 0, "pending": 0, "approved": 0, "by_type": Counter()}
    )
    for item in requests:
        by_status[item["status"]] += 1
        staff_bucket = by_staff[item["staff_id"]]
        staff_bucket["total"] += 1
        staff_bucket[item["status"]] += 1
        staff_bucket["by_type"][item["request_type"]] += 1
    return {
        "total": len(requests),
        "pending": by_status.get("pending", 0),
        "approved": by_status.get("approved", 0),
        "by_staff": {
            staff_id: {
                "total": data["total"],
                "pending": data["pending"],
                "approved": data["approved"],
                "by_type": dict(data["by_type"]),
            }
            for staff_id, data in by_staff.items()
        },
    }
