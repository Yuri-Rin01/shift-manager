import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import date

from db.database import init_db, get_connection
from db.settings_repository import save_settings, get_settings
from db.shift_repository import get_shifts_between, upsert_shift_cell
from db.staff_repository import list_staff
from schemas.generation_preview import GenerationPreviewRequest
from services.generation_preview import create_preview, apply_preview
from test_shift_generator import settings_for


class GenerationPreviewTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.patch=patch('db.database.DB_PATH',Path(self.directory.name)/'test.db')
        self.patch.start();init_db()
        with get_connection() as conn:
            ids=[r[0] for r in conn.execute('SELECT id FROM staff ORDER BY id LIMIT 3')]
            self.a,self.b,self.outside=ids
            conn.execute('UPDATE staff SET exclude_from_staffing=1')
            for sid,floor in zip(ids,['1F','1F','2F']):
                conn.execute('UPDATE staff SET exclude_from_staffing=0, can_work_night=1, night_shift_count=4, fix_night_shift_count=1, staffing_basis=?, department=? WHERE id=?',(json.dumps({'day':60,'night':40}),floor,sid))
                conn.execute('DELETE FROM staff_floors WHERE staff_id=?',(sid,))
                conn.execute('INSERT INTO staff_floors(staff_id,floor) VALUES(?,?)',(sid,floor))
            conn.execute('DELETE FROM staff_night_incompatibilities')
            conn.execute('DELETE FROM staff_day_incompatibilities')
        save_settings(settings_for(night_staff=0,day_staff=0))

    def tearDown(self):
        self.patch.stop();self.directory.cleanup()

    def request(self, **extra):
        return GenerationPreviewRequest(year=2026,month=9,floor='1F',**extra)

    def shifts(self):
        return get_shifts_between(date(2026,9,1),date(2026,9,30))

    def test_preview_does_not_write_and_apply_uses_exact_candidate(self):
        before_settings=get_settings()
        result=create_preview(self.request(night_counts={self.a:0},conditions={'off_days_per_period':9}))
        self.assertEqual(self.shifts(),{})
        self.assertEqual(get_settings(),before_settings)
        self.assertEqual(next(x for x in result['summary'] if x['id']==self.a)['nights'],0)
        apply_preview(result['token'])
        self.assertEqual(self.shifts(),{(sid,d):{'symbol':sym,'source':src} for sid,d,sym,src in result['assignments']})
        self.assertEqual(get_settings(),before_settings)
        self.assertEqual(next(s for s in list_staff() if s['id']==self.a)['night_shift_count'],4)
        with self.assertRaises(ValueError):apply_preview(result['token'])

    def test_other_floor_manual_and_leave_are_preserved(self):
        upsert_shift_cell(self.a,2026,9,1,'○',source='manual')
        upsert_shift_cell(self.b,2026,9,2,'有休',source='leave')
        upsert_shift_cell(self.outside,2026,9,3,'夜',source='auto')
        old=self.shifts()
        result=create_preview(self.request())
        self.assertEqual(set(a[0] for a in result['assignments']),{self.a,self.b})
        apply_preview(result['token'])
        for key,cell in old.items():self.assertEqual(self.shifts()[key],cell)

    def test_blank_only_preserves_auto_cells_and_sources(self):
        upsert_shift_cell(self.a,2026,9,1,'○',source='auto')
        result=create_preview(self.request(mode='blank'))
        apply_preview(result['token'])
        self.assertEqual(self.shifts()[(self.a,'2026-09-01')],{'symbol':'○','source':'auto'})

    def test_changed_shift_rejects_stale_candidate(self):
        result=create_preview(self.request())
        upsert_shift_cell(self.a,2026,9,1,'有休',source='manual')
        before=self.shifts()
        with self.assertRaisesRegex(ValueError,'変更'):apply_preview(result['token'])
        self.assertEqual(self.shifts(),before)

    def test_settings_and_staff_edits_reject_stale_candidate(self):
        result=create_preview(self.request())
        cfg=get_settings();cfg['off_days_per_period']=10;save_settings(cfg)
        with self.assertRaisesRegex(ValueError,'変更'):apply_preview(result['token'])
        result=create_preview(self.request())
        with get_connection() as conn:conn.execute('UPDATE staff SET name=? WHERE id=?',('変更済み',self.a))
        with self.assertRaisesRegex(ValueError,'変更'):apply_preview(result['token'])

    def test_defaults_only_saved_when_applying(self):
        result=create_preview(self.request(conditions={'off_days_per_period':9},save_defaults=True))
        self.assertEqual(get_settings()['off_days_per_period'],8)
        apply_preview(result['token'])
        self.assertEqual(get_settings()['off_days_per_period'],9)

    def test_transaction_failure_rolls_back_all_cells(self):
        result=create_preview(self.request(save_defaults=True,conditions={'off_days_per_period':9}))
        before=self.shifts()
        with get_connection() as conn:
            conn.execute("CREATE TRIGGER fail_apply BEFORE INSERT ON shift_assignments WHEN NEW.shift_date='2026-09-15' BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):apply_preview(result['token'])
        self.assertEqual(self.shifts(),before)
        self.assertEqual(get_settings()['off_days_per_period'],8)
        with get_connection() as conn:conn.execute('DROP TRIGGER fail_apply')
        self.assertTrue(apply_preview(result['token'])['applied'])

    def test_expired_and_invalid_conditions(self):
        result=create_preview(self.request())
        with get_connection() as conn:conn.execute('UPDATE generation_previews SET expires=0')
        with self.assertRaisesRegex(ValueError,'有効期限'):apply_preview(result['token'])
        with self.assertRaises(ValueError):create_preview(self.request(night_counts={self.outside:3}))
        with self.assertRaises(ValueError):create_preview(self.request(conditions={'min_staff_by_floor':{'1F':{'day':-1}}}))

    def test_external_floor_night_incompatibility_is_respected(self):
        with get_connection() as conn:conn.execute('INSERT INTO staff_night_incompatibilities(staff_id,incompatible_staff_id) VALUES(?,?)',(self.outside,self.a))
        upsert_shift_cell(self.outside,2026,9,1,'夜',source='manual')
        result=create_preview(self.request())
        cell=next(a for a in result['assignments'] if a[0]==self.a and a[1]=='2026-09-01')
        self.assertNotEqual(cell[2],'夜')

    def test_month_boundary_and_time_slot_mode(self):
        cfg=get_settings();cfg.update(calendar_start_day=16,staffing_requirement_mode='time_slot');save_settings(cfg)
        result=create_preview(self.request())
        self.assertEqual(result['start'],'2026-09-16')
        self.assertEqual(result['end'],'2026-10-15')
        apply_preview(result['token'])

    def test_time_slot_counts_preserved_other_floor_for_facility_rule(self):
        from services.shift_generator import _Generator
        cfg=get_settings();cfg['staffing_requirement_mode']='time_slot'
        engine=_Generator(2026,9,cfg)
        engine.staff_list=[s for s in engine.staff_list if s['id'] != self.outside]
        engine._phase_manual({(self.outside,'2026-09-01'):{'symbol':'○','source':'manual'}})
        count,_=engine._count_segment_staff('2026-09-01',(600,660),0)
        self.assertEqual(count,1)

    def test_partial_floor_defaults_preserve_other_floors(self):
        before=get_settings()['min_staff_by_floor']['2F']
        result=create_preview(self.request(conditions={'min_staff_by_floor':{'1F':{'day':2}}},save_defaults=True))
        apply_preview(result['token'])
        after=get_settings()['min_staff_by_floor']
        self.assertEqual(after['1F']['day'],2)
        self.assertEqual(after['2F'],before)
