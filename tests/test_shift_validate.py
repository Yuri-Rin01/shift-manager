"""手動編集後のルール確認テスト。"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from db.database import init_db, get_connection
from db.shift_repository import upsert_shift_cell
from db.settings_repository import save_settings, get_settings
from services.shift_validate import validate_period
from test_shift_generator import settings_for


class ShiftValidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "validate.db"
        self.mock = patch("db.database.DB_PATH", self.db_path)
        self.mock.start()
        init_db()
        cfg = settings_for(night_staff=1, day_staff=1)
        cfg["min_staff_by_floor"]["1F"]["day"] = 2
        cfg["min_staff_by_floor"]["2F"]["day"] = 0
        save_settings(cfg)
        with get_connection() as conn:
            rows = conn.execute("SELECT id FROM staff ORDER BY id LIMIT 2").fetchall()
            self.ids = [r[0] for r in rows]
            for sid in self.ids:
                conn.execute(
                    "UPDATE staff SET exclude_from_staffing=0, department='1F', staffing_basis=? WHERE id=?",
                    (json.dumps({"day": 100}), sid),
                )
                conn.execute("DELETE FROM staff_floors WHERE staff_id=?", (sid,))
                conn.execute("INSERT INTO staff_floors(staff_id,floor) VALUES(?,?)", (sid, "1F"))

    def tearDown(self):
        self.mock.stop()
        self.temp.cleanup()

    def test_understaffed_is_reported_without_rewriting_cells(self):
        upsert_shift_cell(self.ids[0], 2026, 9, 1, "○", source="manual")
        before = get_settings()
        result = validate_period(2026, 9, focus_dates=["2026-09-01"])
        codes = {w["code"] for w in result["warnings"]}
        self.assertIn("understaffed", codes)
        # 検証はセルを書き換えない
        from db.shift_repository import get_shifts_between

        cells = get_shifts_between(date(2026, 9, 1), date(2026, 9, 1))
        self.assertEqual(cells[(self.ids[0], "2026-09-01")]["symbol"], "○")
        self.assertEqual(get_settings(), before)

    def test_day_incompatibility_is_flagged(self):
        with get_connection() as conn:
            conn.execute("DELETE FROM staff_day_incompatibilities")
            conn.execute(
                "INSERT INTO staff_day_incompatibilities(staff_id, incompatible_staff_id) VALUES (?,?)",
                (self.ids[0], self.ids[1]),
            )
        upsert_shift_cell(self.ids[0], 2026, 9, 2, "○", source="manual")
        upsert_shift_cell(self.ids[1], 2026, 9, 2, "○", source="manual")
        result = validate_period(2026, 9, focus_dates=["2026-09-02"])
        self.assertTrue(any(w["code"] == "day_incompatibility_conflict" for w in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
