"""バックアップ・復元の回帰テスト。"""

from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from db.database import get_connection, init_db
from db.shift_repository import upsert_shift_cell, get_shifts_between
from datetime import date

from services import backup as backup_service


class BackupRestoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.db_path = root / "shift.db"
        self.backup_root = root / "backups"
        self.patches = [
            patch("db.database.DB_PATH", self.db_path),
            patch("services.backup.DB_PATH", self.db_path),
            patch("services.backup.BACKUP_ROOT", self.backup_root),
            patch("services.backup.BASE_DIR", root),
        ]
        for item in self.patches:
            item.start()
        init_db()
        with get_connection() as conn:
            sid = conn.execute("SELECT id FROM staff ORDER BY id LIMIT 1").fetchone()[0]
            self.staff_id = sid
        upsert_shift_cell(self.staff_id, 2026, 9, 1, "○", source="manual")

    def tearDown(self):
        for item in self.patches:
            item.stop()
        self.temp.cleanup()

    def test_create_backup_writes_dated_zip_with_manifest(self):
        result = backup_service.create_backup(note="テスト保存", prefix="manual")
        path = self.backup_root / result["filename"]
        self.assertTrue(path.exists())
        self.assertTrue(result["filename"].startswith("manual_"))
        self.assertTrue(result["filename"].endswith(".zip"))
        with zipfile.ZipFile(path, "r") as zf:
            self.assertIn("shift.db", zf.namelist())
            self.assertIn("manifest.json", zf.namelist())
            manifest = json.loads(zf.read("manifest.json"))
        self.assertEqual(manifest["format"], "shift-manager-backup")
        self.assertEqual(manifest["note"], "テスト保存")
        self.assertGreaterEqual(manifest["tables"].get("staff", 0), 1)
        self.assertGreaterEqual(manifest["tables"].get("shift_assignments", 0), 1)

    def test_validate_rejects_non_backup_zip(self):
        bad = self.backup_root / "bad.zip"
        self.backup_root.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(bad, "w") as zf:
            zf.writestr("readme.txt", "hello")
        with self.assertRaises(ValueError):
            backup_service.validate_backup_file(bad)

    def test_restore_replaces_data_and_keeps_safety_backup(self):
        first = backup_service.create_backup(note="復元元", prefix="manual")
        path = self.backup_root / first["filename"]

        # 現行を変更
        upsert_shift_cell(self.staff_id, 2026, 9, 2, "夜", source="auto")
        self.assertIn((self.staff_id, "2026-09-02"), get_shifts_between(date(2026, 9, 1), date(2026, 9, 2)))

        # プレビュー相当のゴミを入れておく
        with get_connection() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS generation_previews (
                    token TEXT PRIMARY KEY, expires REAL NOT NULL,
                    fingerprint TEXT NOT NULL, payload TEXT NOT NULL)"""
            )
            conn.execute(
                "INSERT OR REPLACE INTO generation_previews VALUES ('tok', 9999999999, 'fp', '{}')"
            )
            conn.commit()

        result = backup_service.restore_backup(path, confirm=True)
        self.assertTrue(result["ok"])
        self.assertTrue((self.backup_root / result["safety_backup"]["filename"]).exists())

        shifts = get_shifts_between(date(2026, 9, 1), date(2026, 9, 2))
        self.assertIn((self.staff_id, "2026-09-01"), shifts)
        self.assertNotIn((self.staff_id, "2026-09-02"), shifts)

        with get_connection() as conn:
            rows = conn.execute("SELECT COUNT(*) FROM generation_previews").fetchone()[0]
        self.assertEqual(rows, 0)

    def test_restore_requires_confirm(self):
        first = backup_service.create_backup(prefix="manual")
        path = self.backup_root / first["filename"]
        with self.assertRaises(ValueError):
            backup_service.restore_backup(path, confirm=False)

    def test_failed_restore_does_not_block_writes(self):
        with self.assertRaises(ValueError):
            backup_service.restore_backup(self.backup_root / "missing.zip", confirm=True)
        self.assertFalse(backup_service.is_write_blocked())


if __name__ == "__main__":
    unittest.main()
