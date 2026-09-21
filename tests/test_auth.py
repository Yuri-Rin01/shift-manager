"""認証・認可の回帰テスト。"""

from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from db.database import init_db, get_connection
from services import auth as auth_service


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "auth.db"
        self.secret = Path(self.temp.name) / "secret"
        self.mock_db = patch("db.database.DB_PATH", self.db_path)
        self.mock_secret = patch.dict("os.environ", {"SHIFT_MANAGER_SECRET_FILE": str(self.secret)})
        self.mock_db.start()
        self.mock_secret.start()
        init_db()
        # main は import 時に設定を読むため、DB を差し替えてから読み込む
        import main as main_module
        import leave_portal_main as portal_module

        importlib.reload(main_module)
        importlib.reload(portal_module)
        from fastapi.testclient import TestClient

        self.client = TestClient(main_module.app)
        self.portal_client = TestClient(portal_module.app)

    def tearDown(self):
        self.mock_db.stop()
        self.mock_secret.stop()
        self.temp.cleanup()

    def test_open_mode_until_admin_exists(self):
        status = self.client.get("/api/auth/status").json()
        self.assertTrue(status["setup_needed"])
        self.assertFalse(status["auth_enforced"])
        response = self.client.get("/api/staff")
        self.assertEqual(response.status_code, 200)

    def test_admin_apis_require_login_after_setup(self):
        created = self.client.post(
            "/api/auth/setup",
            json={"username": "admin", "password": "password123", "display_name": "管理者"},
        )
        self.assertEqual(created.status_code, 200)
        anon = self.client.__class__(self.client.app)
        blocked = anon.get("/api/staff")
        self.assertEqual(blocked.status_code, 401)
        blocked_backup = anon.post("/api/backup/create", data={"note": "x"})
        self.assertEqual(blocked_backup.status_code, 401)

        login = anon.post("/api/auth/login", json={"username": "admin", "password": "password123"})
        self.assertEqual(login.status_code, 200)
        allowed = anon.get("/api/staff")
        self.assertEqual(allowed.status_code, 200)

    def test_staff_portal_cannot_access_other_ids(self):
        with get_connection() as conn:
            rows = conn.execute("SELECT id FROM staff ORDER BY id LIMIT 2").fetchall()
            sid_a, sid_b = rows[0][0], rows[1][0]
        auth_service.set_staff_portal_pin(sid_a, "1234")
        auth_service.set_staff_portal_pin(sid_b, "5678")

        login = self.portal_client.post("/portal/api/login", json={"staff_id": sid_a, "pin": "1234"})
        self.assertEqual(login.status_code, 200)
        ok = self.portal_client.get(f"/api/calendar?staff_id={sid_a}&year=2026&month=9")
        self.assertEqual(ok.status_code, 200)
        other = self.portal_client.get(f"/api/calendar?staff_id={sid_b}&year=2026&month=9")
        self.assertEqual(other.status_code, 403)
        from fastapi.testclient import TestClient
        import leave_portal_main as portal_module

        unauth = TestClient(portal_module.app)
        denied = unauth.get(f"/api/calendar?staff_id={sid_a}&year=2026&month=9")
        self.assertEqual(denied.status_code, 401)

    def test_password_not_stored_plaintext(self):
        auth_service.create_admin("boss", "secretpass", "施設長")
        with get_connection() as conn:
            row = conn.execute(
                "SELECT password_hash FROM admin_users WHERE username='boss'"
            ).fetchone()
        self.assertNotIn("secretpass", row["password_hash"])
        self.assertTrue(row["password_hash"].startswith("pbkdf2_sha256$"))


if __name__ == "__main__":
    unittest.main()
