"""フロア追加・改名・削除保護のテスト。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from data.floors import assert_floor_deletable, floor_usage, get_floors
from db.database import get_connection, init_db
from db.settings_repository import get_settings, save_settings
from db.shift_repository import save_placements, upsert_shift_cell
from test_shift_generator import settings_for


class FloorSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "floors.db"
        self.mock = patch("db.database.DB_PATH", self.db_path)
        self.mock.start()
        init_db()
        save_settings(settings_for())

    def tearDown(self):
        self.mock.stop()
        self.temp.cleanup()

    def test_rename_keeps_staff_and_placement_links(self):
        with get_connection() as conn:
            sid = conn.execute("SELECT id FROM staff ORDER BY id LIMIT 1").fetchone()[0]
            conn.execute("UPDATE staff SET department=? WHERE id=?", ("1F", sid))
            conn.execute("DELETE FROM staff_floors WHERE staff_id=?", (sid,))
            conn.execute("INSERT INTO staff_floors(staff_id,floor) VALUES(?,?)", (sid, "1F"))
        upsert_shift_cell(sid, 2026, 9, 1, "○", source="manual")
        with get_connection() as conn:
            save_placements(conn, [dict(staff_id=sid, date="2026-09-01", floor="1F", role="floor")])
            conn.commit()

        cfg = get_settings()
        floors = get_floors(cfg)
        renamed = []
        for item in floors:
            if item["id"] == "1f":
                renamed.append({"id": "1f", "label": "1階"})
            else:
                renamed.append(dict(item))
        cfg["floors"] = renamed
        # 必要人数キーも旧名のまま渡しても save 側で付け替える
        min_map = dict(cfg.get("min_staff_by_floor") or {})
        if "1F" in min_map:
            pass  # leave as 1F; save_settings remaps
        save_settings(cfg)

        after = get_settings()
        labels = [item["label"] for item in after["floors"]]
        self.assertIn("1階", labels)
        self.assertNotIn("1F", labels)
        with get_connection() as conn:
            floor = conn.execute("SELECT floor FROM staff_floors WHERE staff_id=?", (sid,)).fetchone()["floor"]
            placement = conn.execute(
                "SELECT floor FROM shift_placements WHERE staff_id=? AND shift_date=?",
                (sid, "2026-09-01"),
            ).fetchone()["floor"]
            department = conn.execute("SELECT department FROM staff WHERE id=?", (sid,)).fetchone()["department"]
        self.assertEqual(floor, "1階")
        self.assertEqual(placement, "1階")
        self.assertEqual(department, "1階")
        self.assertIn("1階", after.get("min_staff_by_floor") or {})

    def test_cannot_delete_floor_in_use(self):
        with get_connection() as conn:
            sid = conn.execute("SELECT id FROM staff ORDER BY id LIMIT 1").fetchone()[0]
            conn.execute("DELETE FROM staff_floors WHERE staff_id=?", (sid,))
            conn.execute("INSERT INTO staff_floors(staff_id,floor) VALUES(?,?)", (sid, "2F"))
        self.assertTrue(floor_usage("2F")["in_use"])
        with self.assertRaises(ValueError):
            assert_floor_deletable("2F")
        cfg = get_settings()
        cfg["floors"] = [item for item in get_floors(cfg) if item["id"] != "2f"]
        with self.assertRaises(ValueError):
            save_settings(cfg)

    def test_can_add_floor(self):
        cfg = get_settings()
        floors = get_floors(cfg)
        floors.append({"id": "east", "label": "東館"})
        cfg["floors"] = floors
        saved = save_settings(cfg)
        self.assertTrue(any(item["label"] == "東館" for item in saved["floors"]))


if __name__ == "__main__":
    unittest.main()
