from datetime import date, timedelta

from db.database import get_connection

ShiftCell = dict[str, str]


def get_shifts_between(start: date, end: date) -> dict[tuple[int, str], ShiftCell]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT staff_id, shift_date, symbol, source
            FROM shift_assignments
            WHERE shift_date >= ? AND shift_date <= ?
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()

    return {
        (row["staff_id"], row["shift_date"]): {
            "symbol": row["symbol"],
            "source": row["source"] or "auto",
        }
        for row in rows
    }


def get_month_shifts(year: int, month: int) -> dict[tuple[int, str], ShiftCell]:
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return get_shifts_between(start, end)


def upsert_shift_cell(
    staff_id: int,
    year: int,
    month: int,
    day: int,
    symbol: str,
    *,
    source: str = "manual",
) -> dict:
    try:
        shift_date = date(year, month, day).isoformat()
    except ValueError as exc:
        raise ValueError("日付が不正です") from exc

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO shift_assignments (staff_id, shift_date, symbol, source)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(staff_id, shift_date) DO UPDATE SET
                symbol = excluded.symbol,
                source = excluded.source
            """,
            (staff_id, shift_date, symbol, source),
        )
        conn.commit()
    return {
        "staff_id": staff_id,
        "shift_date": shift_date,
        "symbol": symbol,
        "source": source,
    }


def get_shift_cell(staff_id: int, shift_date: date) -> ShiftCell | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT symbol, source
            FROM shift_assignments
            WHERE staff_id = ? AND shift_date = ?
            """,
            (staff_id, shift_date.isoformat()),
        ).fetchone()
    if row is None:
        return None
    return {
        "symbol": row["symbol"],
        "source": row["source"] or "auto",
    }


def delete_shift_cell(staff_id: int, shift_date: date) -> bool:
    """1セル分の割当を削除。削除できた場合 True。"""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            DELETE FROM shift_assignments
            WHERE staff_id = ? AND shift_date = ?
            """,
            (staff_id, shift_date.isoformat()),
        )
        conn.commit()
        return cursor.rowcount > 0


def delete_shifts_between(start: date, end: date) -> int:
    """指定期間のシフト割当を削除。削除件数を返す。"""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            DELETE FROM shift_assignments
            WHERE shift_date >= ? AND shift_date <= ?
            """,
            (start.isoformat(), end.isoformat()),
        )
        conn.commit()
        return cursor.rowcount


def bulk_upsert_shifts(assignments: list[tuple[int, str, str, str]]) -> int:
    """(staff_id, shift_date ISO, symbol, source) の一覧を一括保存。件数を返す。"""
    if not assignments:
        return 0
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO shift_assignments (staff_id, shift_date, symbol, source)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(staff_id, shift_date) DO UPDATE SET
                symbol = CASE
                    WHEN shift_assignments.source = 'manual' THEN shift_assignments.symbol
                    ELSE excluded.symbol
                END,
                source = CASE
                    WHEN shift_assignments.source = 'manual' THEN shift_assignments.source
                    ELSE excluded.source
                END
            """,
            assignments,
        )
        conn.commit()
    return len(assignments)
