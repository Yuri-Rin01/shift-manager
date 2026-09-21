"""勤務表の期間確定（ロック）と解除。

ロックは絶対日付範囲で保存し、カレンダー開始日の変更後も保護を維持する。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from db.database import get_connection

TABLE = "shift_period_locks"


def ensure_lock_table(conn=None) -> None:
    owns = conn is None
    if owns:
        conn = get_connection()
    try:
        conn.execute(
            f"""CREATE TABLE IF NOT EXISTS {TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                period_start TEXT NOT NULL,
                period_end TEXT NOT NULL,
                locked_at TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                UNIQUE(period_start, period_end),
                CHECK (period_start <= period_end)
            )"""
        )
        if owns:
            conn.commit()
    finally:
        if owns:
            conn.close()


def _parse(day: str | date) -> date:
    if isinstance(day, date):
        return day
    return date.fromisoformat(str(day)[:10])


def list_locks() -> list[dict]:
    ensure_lock_table()
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT id, period_start, period_end, locked_at, note FROM {TABLE} ORDER BY period_start DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def overlapping_locks(start: date, end: date) -> list[dict]:
    ensure_lock_table()
    start_s, end_s = start.isoformat(), end.isoformat()
    with get_connection() as conn:
        rows = conn.execute(
            f"""SELECT id, period_start, period_end, locked_at, note FROM {TABLE}
                WHERE period_start <= ? AND period_end >= ?
                ORDER BY period_start""",
            (end_s, start_s),
        ).fetchall()
    return [dict(row) for row in rows]


def is_date_locked(day: str | date) -> bool:
    d = _parse(day)
    return bool(overlapping_locks(d, d))


def locked_dates_among(days: list[str | date]) -> list[str]:
    locked: list[str] = []
    for day in days:
        d = _parse(day)
        if is_date_locked(d):
            locked.append(d.isoformat())
    # unique preserve order
    seen = set()
    out = []
    for item in locked:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def assert_dates_editable(days: list[str | date], *, action: str = "変更") -> None:
    locked = locked_dates_among(days)
    if not locked:
        return
    sample = "、".join(locked[:5])
    more = f" 他{len(locked) - 5}日" if len(locked) > 5 else ""
    raise ValueError(
        f"確定済みの期間があるため{action}できません（{sample}{more}）。"
        "解除してから操作してください。"
    )


def period_status(start: date, end: date) -> dict:
    locks = overlapping_locks(start, end)
    if not locks:
        return {
            "status": "editing",
            "label": "編集中",
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "locks": [],
        }
    covers = any(
        _parse(item["period_start"]) <= start and _parse(item["period_end"]) >= end
        for item in locks
    )
    return {
        "status": "locked" if covers else "partial",
        "label": "確定済み" if covers else "一部確定",
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "locks": locks,
    }


def lock_period(start: date, end: date, *, note: str = "") -> dict:
    if end < start:
        raise ValueError("期間の終了日が開始日より前です。")
    ensure_lock_table()
    jst = timezone(timedelta(hours=9))
    locked_at = datetime.now(jst).isoformat()
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        # 完全包含される既存ロックを整理し、同一範囲は更新
        conn.execute(
            f"""DELETE FROM {TABLE}
                WHERE period_start >= ? AND period_end <= ?""",
            (start.isoformat(), end.isoformat()),
        )
        rows = conn.execute(
            f"""SELECT id, period_start, period_end FROM {TABLE}
                WHERE period_start <= ? AND period_end >= ?""",
            (end.isoformat(), start.isoformat()),
        ).fetchall()
        for row in rows:
            # 重なる場合は結合して1本にまとめる
            merged_start = min(start, _parse(row["period_start"]))
            merged_end = max(end, _parse(row["period_end"]))
            conn.execute(f"DELETE FROM {TABLE} WHERE id=?", (row["id"],))
            start, end = merged_start, merged_end
        conn.execute(
            f"""INSERT INTO {TABLE} (period_start, period_end, locked_at, note)
                VALUES (?, ?, ?, ?)""",
            (start.isoformat(), end.isoformat(), locked_at, note or ""),
        )
        conn.commit()
    return period_status(start, end)


def unlock_period(start: date, end: date, *, confirm: bool = False) -> dict:
    if not confirm:
        raise ValueError("確定解除には確認が必要です。")
    if end < start:
        raise ValueError("期間の終了日が開始日より前です。")
    ensure_lock_table()
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            f"""SELECT id, period_start, period_end, locked_at, note FROM {TABLE}
                WHERE period_start <= ? AND period_end >= ?""",
            (end.isoformat(), start.isoformat()),
        ).fetchall()
        if not rows:
            raise ValueError("指定期間に確定済みの範囲がありません。")
        for row in rows:
            lock_start = _parse(row["period_start"])
            lock_end = _parse(row["period_end"])
            conn.execute(f"DELETE FROM {TABLE} WHERE id=?", (row["id"],))
            # 解除範囲の外側は残す
            if lock_start < start:
                left_end = start - timedelta(days=1)
                conn.execute(
                    f"""INSERT INTO {TABLE} (period_start, period_end, locked_at, note)
                        VALUES (?, ?, ?, ?)""",
                    (
                        lock_start.isoformat(),
                        left_end.isoformat(),
                        row["locked_at"],
                        row["note"],
                    ),
                )
            if lock_end > end:
                right_start = end + timedelta(days=1)
                conn.execute(
                    f"""INSERT INTO {TABLE} (period_start, period_end, locked_at, note)
                        VALUES (?, ?, ?, ?)""",
                    (
                        right_start.isoformat(),
                        lock_end.isoformat(),
                        row["locked_at"],
                        row["note"],
                    ),
                )
        conn.commit()
    return period_status(start, end)
