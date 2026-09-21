"""勤務表の期間確定（ロック）テスト。"""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from db.database import init_db, get_connection
from db.shift_repository import upsert_shift_cell, delete_shifts_between
from db.settings_repository import get_settings
from services.period_lock import lock_period, unlock_period, period_status, is_date_locked
from services.shift_edit import edit_cell


class PeriodLockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "lock.db"
        self.mock = patch("db.database.DB_PATH", self.db_path)
        self.mock.start()
        init_db()
        with get_connection() as conn:
            self.sid = conn.execute("SELECT id FROM staff ORDER BY id LIMIT 1").fetchone()[0]

    def tearDown(self):
        self.mock.stop()
        self.temp.cleanup()

    def test_lock_blocks_edit_and_survives_calendar_start_change(self):
        lock_period(date(2026, 9, 1), date(2026, 9, 30), note="9月確定")
        self.assertTrue(is_date_locked(date(2026, 9, 15)))
        status = period_status(date(2026, 9, 1), date(2026, 9, 30))
        self.assertEqual(status["status"], "locked")

        with self.assertRaises(ValueError):
            edit_cell(self.sid, date(2026, 9, 10), "○", get_settings())

        # 開始日を16日に変えても、9/1-9/30 のロックは残る
        with self.assertRaises(ValueError):
            edit_cell(self.sid, date(2026, 9, 20), "○", get_settings())

        # ロック外は編集可
        result = edit_cell(self.sid, date(2026, 10, 1), "○", get_settings())
        self.assertEqual(result["symbol"], "○")

    def test_unlock_requires_confirm_and_allows_edit_again(self):
        lock_period(date(2026, 9, 1), date(2026, 9, 30))
        with self.assertRaises(ValueError):
            unlock_period(date(2026, 9, 1), date(2026, 9, 30), confirm=False)
        unlock_period(date(2026, 9, 1), date(2026, 9, 30), confirm=True)
        self.assertFalse(is_date_locked(date(2026, 9, 10)))
        edit_cell(self.sid, date(2026, 9, 10), "○", get_settings())

    def test_clear_blocked_when_period_locked(self):
        upsert_shift_cell(self.sid, 2026, 9, 5, "○", source="manual")
        lock_period(date(2026, 9, 1), date(2026, 9, 30))
        with self.assertRaises(ValueError):
            delete_shifts_between(date(2026, 9, 1), date(2026, 9, 30))

    def test_related_morning_day_is_also_protected(self):
        # 9/30 編集は翌日 10/1 の明けも触るため、10/1 がロックなら拒否
        lock_period(date(2026, 10, 1), date(2026, 10, 15))
        with self.assertRaises(ValueError):
            edit_cell(self.sid, date(2026, 9, 30), "夜", get_settings())


if __name__ == "__main__":
    unittest.main()
