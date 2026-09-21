"""労働時間集計のテスト。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from db.database import init_db, get_connection
from db.settings_repository import save_settings, get_settings
from db.shift_repository import upsert_shift_cell
from services.labor_hours import gross_work_minutes, net_work_minutes, summarize_labor_hours
from test_shift_generator import settings_for


class LaborHoursUnitTests(unittest.TestCase):
    def test_overnight_gross_minutes(self):
        self.assertEqual(gross_work_minutes("16:30", "09:00"), 16 * 60 + 30)

    def test_same_day_net_requires_break(self):
        minutes, reason = net_work_minutes("08:30", "17:30", None)
        self.assertIsNone(minutes)
        self.assertIn("休憩", reason or "")
        minutes, reason = net_work_minutes("08:30", "17:30", 60)
        self.assertEqual(minutes, 8 * 60)
        self.assertIsNone(reason)

    def test_does_not_invent_break_as_zero(self):
        minutes, _ = net_work_minutes("09:00", "18:00", None)
        self.assertIsNone(minutes)


class LaborHoursIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "labor.db"
        self.mock = patch("db.database.DB_PATH", self.db_path)
        self.mock.start()
        init_db()
        cfg = settings_for(night_staff=1, day_staff=1)
        options = []
        for item in cfg["staffing_basis_options"]:
            row = dict(item)
            if row["key"] == "day":
                row["break_minutes"] = 60
            if row["key"] == "night":
                row["break_minutes"] = 60
            options.append(row)
        cfg["staffing_basis_options"] = options
        cfg["default_weekly_hour_limit"] = 40
        cfg["default_monthly_hour_limit"] = 160
        save_settings(cfg)
        with get_connection() as conn:
            row = conn.execute("SELECT id FROM staff ORDER BY id LIMIT 1").fetchone()
            self.staff_id = row[0]
            conn.execute(
                "UPDATE staff SET weekly_hour_limit=?, monthly_hour_limit=? WHERE id=?",
                (32, 120, self.staff_id),
            )

    def tearDown(self):
        self.mock.stop()
        self.temp.cleanup()

    def test_morning_off_not_counted_and_day_hours_apply(self):
        upsert_shift_cell(self.staff_id, 2026, 9, 1, "○", source="manual")
        upsert_shift_cell(self.staff_id, 2026, 9, 2, "明", source="manual")
        result = summarize_labor_hours(2026, 9)
        person = next(item for item in result["staff"] if item["staff_id"] == self.staff_id)
        self.assertEqual(person["period_status"], "complete")
        self.assertEqual(person["period_hours"], 8.0)
        self.assertEqual(person["weekly_limit_hours"], 32)
        self.assertEqual(person["monthly_limit_hours"], 120)

    def test_incomplete_when_break_missing(self):
        cfg = get_settings()
        options = []
        for item in cfg["staffing_basis_options"]:
            row = dict(item)
            if row["key"] == "day":
                row.pop("break_minutes", None)
            options.append(row)
        cfg["staffing_basis_options"] = options
        save_settings(cfg)
        upsert_shift_cell(self.staff_id, 2026, 9, 3, "○", source="manual")
        result = summarize_labor_hours(2026, 9)
        person = next(item for item in result["staff"] if item["staff_id"] == self.staff_id)
        self.assertEqual(person["period_status"], "incomplete")
        self.assertIsNone(person["period_hours"])
        self.assertTrue(person["incomplete"])

    def test_overnight_night_counts_once_on_assignment_day(self):
        upsert_shift_cell(self.staff_id, 2026, 9, 4, "夜", source="manual")
        upsert_shift_cell(self.staff_id, 2026, 9, 5, "明", source="manual")
        result = summarize_labor_hours(2026, 9)
        person = next(item for item in result["staff"] if item["staff_id"] == self.staff_id)
        self.assertEqual(person["period_status"], "complete")
        # 16:30-09:00 = 16.5h - 60m break = 15.5h
        self.assertEqual(person["period_hours"], 15.5)


if __name__ == "__main__":
    unittest.main()
