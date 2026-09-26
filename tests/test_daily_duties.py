import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from db.database import get_connection, init_db
from db.shift_repository import upsert_shift_cell
from db.settings_repository import get_settings, save_settings
from services.daily_duties import get_sheet, save_duty, save_roles, DutyConflict


class DailyDutyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patch = patch('db.database.DB_PATH', Path(self.temp.name)/'test.db'); self.patch.start()
        init_db()
        with get_connection() as conn:
            self.sid = conn.execute('SELECT id FROM staff ORDER BY id LIMIT 1').fetchone()[0]
            conn.execute('DELETE FROM shift_assignments')
        self.day = date(2026, 9, 21)
        upsert_shift_cell(self.sid, 2026, 9, 21, '○')

    def tearDown(self):
        self.patch.stop(); self.temp.cleanup()

    def cell(self):
        return next(r for r in get_sheet(self.day, 7)['rows'] if r['id'] == self.sid)['cells'][0]

    def save(self, am='着脱', pm='物品補充', cell=None):
        c = cell or self.cell()
        return save_duty(self.sid, self.day, am, pm, c['signature'], c['revision'])

    def test_save_reload_preserves_shift_and_persists_over_init(self):
        self.save(); init_db(); cell = self.cell()
        self.assertEqual((cell['am'], cell['pm'], cell['symbol']), ('着脱', '物品補充', '○'))
        self.assertFalse(cell['stale'])

    def test_off_night_and_empty_cannot_receive_daytime_duties(self):
        for symbol in ['×', '有休', '明', '夜']:
            upsert_shift_cell(self.sid, 2026, 9, 21, symbol)
            with self.assertRaises(ValueError): self.save()
        with get_connection() as conn: conn.execute('DELETE FROM shift_assignments')
        with self.assertRaises(ValueError): self.save()

    def test_changed_shift_requires_review_and_clear_retains_revision(self):
        old = self.save()
        upsert_shift_cell(self.sid, 2026, 9, 21, '×')
        self.assertTrue(self.cell()['stale'])
        with self.assertRaises(DutyConflict): self.save(cell=old)
        new = self.save('', '')
        self.assertFalse(new['stale']); self.assertEqual(new['revision'], 2)

    def test_concurrent_edit_conflict(self):
        old = self.cell(); self.save(cell=old)
        with self.assertRaises(DutyConflict): self.save('L', '居室整理', old)
        self.assertEqual(self.cell()['am'], '着脱')

    def test_regeneration_retains_duties_for_review(self):
        self.save()
        with get_connection() as conn:
            conn.execute('DELETE FROM shift_assignments WHERE staff_id=?', (self.sid,))
        self.assertTrue(self.cell()['stale'])
        upsert_shift_cell(self.sid, 2026, 9, 21, '○')
        self.assertFalse(self.cell()['stale']); self.assertEqual(self.cell()['am'], '着脱')

    def test_candidate_edit_does_not_rewrite_existing_assignments(self):
        self.save(); sheet = get_sheet(self.day, 1)
        save_roles(['入浴', '入浴', ''], sheet['roles_revision'])
        self.assertEqual(get_sheet(self.day, 1)['roles'], ['入浴'])
        self.assertEqual(self.cell()['am'], '着脱')
        with self.assertRaises(DutyConflict): save_roles(['他'], sheet['roles_revision'])

    def test_time_and_placement_changes_require_review(self):
        self.save()
        with get_connection() as conn:
            conn.execute('INSERT INTO shift_placements(staff_id,shift_date,floor,role) VALUES(?,?,?,?)', (self.sid, self.day.isoformat(), '1F', 'floor'))
        self.assertTrue(self.cell()['stale'])
        self.save()
        settings=get_settings()
        for item in settings['staffing_basis_options']:
            if item['key']=='day': item['end_time']='12:00'
        save_settings(settings)
        self.assertTrue(self.cell()['stale']); self.assertFalse(self.cell()['pm_enabled'])

    def test_week_crosses_month_and_year(self):
        sheet=get_sheet(date(2026,12,28),7)
        self.assertEqual(sheet['dates'][-1], '2027-01-03')
        self.assertFalse(get_sheet(self.day,7,'不存在')['rows'])


class DailyDutyApiTests(unittest.TestCase):
    setUp = DailyDutyTests.setUp
    tearDown = DailyDutyTests.tearDown
    cell = DailyDutyTests.cell

    def test_authenticated_api_and_html(self):
        from fastapi.testclient import TestClient
        from main import app
        from services.auth import require_admin
        from fastapi import HTTPException
        client=TestClient(app)
        page=client.get('/daily-duties')
        self.assertEqual(page.status_code,200)
        self.assertNotIn('出勤する人に、今日の担当を。', page.text)
        c=self.cell()
        body=dict(staff_id=self.sid,date=self.day.isoformat(),am='L',pm='入浴準備',signature=c['signature'],revision=c['revision'])
        response=client.put('/api/daily-duties/cell',json=body)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(client.put('/api/daily-duties/cell',json=body).status_code,409)
        def denied(): raise HTTPException(401,'login required')
        app.dependency_overrides[require_admin]=denied
        try:
            self.assertEqual(client.get('/api/daily-duties?start=2026-09-21').status_code,401)
            self.assertEqual(client.put('/api/daily-duties/cell',json=body).status_code,401)
            self.assertEqual(client.put('/api/daily-duties/roles',json={'labels':['x'],'revision':1}).status_code,401)
        finally: app.dependency_overrides.clear()

        from services.auth import create_admin
        with patch.dict(os.environ, {'SHIFT_MANAGER_SECRET_FILE': str(Path(self.temp.name)/'secret')}):
            create_admin('daily_admin', 'daily-password-123', '管理者')
            anon=TestClient(app)
            self.assertEqual(anon.get('/api/daily-duties?start=2026-09-21').status_code,401)
            self.assertEqual(anon.get('/daily-duties',follow_redirects=False).status_code,303)
            self.assertEqual(anon.post('/api/auth/login',json={'username':'daily_admin','password':'daily-password-123'}).status_code,200)
            self.assertEqual(anon.get('/api/daily-duties?start=2026-09-21').status_code,200)
