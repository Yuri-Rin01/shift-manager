"""A person's eligible floors must never multiply their actual headcount."""
import json
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from db.database import init_db, get_connection
from db.settings_repository import save_settings
from db.shift_repository import get_placements_between, upsert_shift_cell, save_placements, delete_shifts_between
from schemas.generation_preview import GenerationPreviewRequest
from services.generation_preview import create_preview, apply_preview
from services.shift_generator import _Generator
from test_shift_generator import settings_for, staff_member, generate


def configuration(mode='work_type', night=False):
    cfg = settings_for(mode, night_staff=int(night), day_staff=int(not night))
    cfg['min_staff_by_floor']['2F']['night' if night else 'day'] = 1
    cfg['require_leader_on_night'] = night
    cfg['time_slot_staffing_rules'] = [
        {'label': '夜勤帯' if night else '日勤帯', 'start_time': '16:30' if night else '09:00',
         'end_time': '09:00' if night else '16:00', 'min_staff': 1, 'floor': floor}
        for floor in ['1F', '2F']]
    return cfg


def member(sid, floors, leader=False, night=False):
    person = staff_member(sid, 8 if night else None)
    person.update(departments=floors, position='リーダー' if leader else '一般')
    return person


class FloorPlacementTests(unittest.TestCase):
    def test_one_day_worker_cannot_cover_two_floors(self):
        for mode in ['work_type', 'time_slot']:
            e = _Generator(2026, 9, configuration(mode), staff_members=[member(1, ['1F', '2F'])])
            e._phase_manual({(1, '2026-09-01'): {'symbol': '○', 'source': 'manual'}})
            e._collect_staffing_shortfalls()
            self.assertEqual(sum(e._count_work_on_day('2026-09-01', 'day', floor=f) for f in ['1F','2F']), 1)
            if mode == 'time_slot':
                self.assertEqual(sum(e._count_segment_staff('2026-09-01', (600,660), 0, floor=f)[0] for f in ['1F','2F']), 1)
                self.assertTrue(any(r[0]=='2026-09-01' for r in e.time_slot_shortfalls))
            else:
                self.assertTrue(any(r[0]=='2026-09-01' for r in e.understaffed_shortfalls))

    def test_day_leader_also_has_only_one_floor(self):
        e = _Generator(2026,9,configuration(),staff_members=[member(1,['1F','2F'],leader=True)])
        e._phase_manual({(1,'2026-09-01'):{'symbol':'○','source':'manual'}})
        self.assertEqual(e.placements[(1,'2026-09-01')]['role'], 'floor')
        self.assertEqual(sum(e._count_work_on_day('2026-09-01','day',floor=f) for f in ['1F','2F']),1)

    def test_flexible_worker_leaves_room_for_single_floor_colleague(self):
        e = _Generator(2026,9,configuration(),staff_members=[member(1,['1F','2F']),member(2,['1F'])])
        for floor in ['1F','2F']:
            e._assign_for_day('2026-09-01','day',1,floor=floor)
        self.assertEqual(e.placements[(2,'2026-09-01')]['floor'],'1F')
        self.assertEqual(e.placements[(1,'2026-09-01')]['floor'],'2F')

    def test_three_distinct_people_fill_two_floors_and_night_leader(self):
        for mode in ['work_type','time_slot']:
            people=[member(1,['1F'],night=True),member(2,['2F'],night=True),member(3,['1F','2F'],leader=True,night=True)]
            e=_Generator(2026,9,configuration(mode,night=True),staff_members=people)
            e._phase_night_leaders()
            if mode=='time_slot':
                e._phase_time_slot_staffing(night_only=True)
            else:
                e._phase_night_assignments()
            day='2026-09-01'
            self.assertEqual(e._count_work_on_day(day,'night'),3)
            self.assertEqual(e._count_work_on_day(day,'night',floor='1F'),1)
            self.assertEqual(e._count_work_on_day(day,'night',floor='2F'),1)
            self.assertEqual(e.placements[(3,day)],{'floor':'','role':'night_leader'})
            self.assertTrue(e._has_leader_on_night(day))
            if mode=='time_slot':
                self.assertEqual(e._count_segment_staff('2026-09-02',(0,540),-1,floor='1F')[0],1)
                self.assertEqual(e._count_segment_staff('2026-09-02',(0,540),-1,floor='2F')[0],1)
                self.assertEqual(e._count_segment_staff('2026-09-02',(0,540),-1)[0],3)

    def test_lone_night_leader_does_not_fill_either_floor(self):
        e=_Generator(2026,9,configuration(night=True),staff_members=[member(1,['1F','2F'],leader=True,night=True)])
        e._phase_manual({(1,'2026-09-01'):{'symbol':'夜','source':'manual'}})
        e._collect_staffing_shortfalls()
        self.assertTrue(e._has_leader_on_night('2026-09-01'))
        self.assertEqual(e._count_work_on_day('2026-09-01','night'),1)
        short=[r for r in e.understaffed_shortfalls if r[0]=='2026-09-01' and r[1]=='night']
        self.assertEqual({r[2] for r in short},{'1F','2F'})
        self.assertTrue(all(r[4]==0 for r in short))

    def test_leader_must_be_eligible_for_both_night_floors(self):
        for mode in ['work_type','time_slot']:
            people=[member(1,['1F'],leader=True,night=True),member(2,['1F','2F'],leader=True,night=True)]
            e=_Generator(2026,9,configuration(mode,night=True),staff_members=people)
            e._phase_night_leaders()
            self.assertEqual(e.placements[(2,'2026-09-01')]['role'],'night_leader')
            self.assertNotIn((1,'2026-09-01'),e.placements)

    def test_missing_leader_warns_even_when_floors_are_full(self):
        people=[member(1,['1F'],night=True),member(2,['2F'],night=True)]
        e=_Generator(2026,9,configuration(night=True),staff_members=people)
        e._phase_manual({(s['id'],'2026-09-01'):{'symbol':'夜','source':'manual'} for s in people})
        e._validate_leader_on_night()
        self.assertTrue(any(w['code']=='leader_on_night_missing' and '2026-09-01' in w['message'] for w in e.warnings))

    def test_leader_respects_night_quota_and_incompatibility(self):
        people=[member(1,['1F'],night=True),member(2,['1F','2F'],leader=True,night=True),
                member(3,['1F','2F'],leader=True,night=True),member(4,['1F','2F'],leader=True,night=True)]
        people[1]['night_shift_count']=0
        people[2]['night_incompatible_ids']=[1]
        e=_Generator(2026,9,configuration(night=True),staff_members=people)
        e._phase_manual({(1,'2026-09-01'):{'symbol':'夜','source':'manual'}})
        e._phase_night_leaders()
        self.assertEqual(e.placements[(4,'2026-09-01')]['role'],'night_leader')
        self.assertNotEqual(e.grid.get((2,'2026-09-01')),'夜')
        self.assertNotEqual(e.grid.get((3,'2026-09-01')),'夜')

    def test_custom_work_and_morning_segment_keep_same_location(self):
        from test_custom_work_settings import custom_settings
        cfg=custom_settings('night');cfg['min_staff_by_floor']['2F']['work_1']=1
        e=_Generator(2026,9,cfg,staff_members=[member(1,['1F','2F'],night=True)])
        e._phase_manual({(1,'2026-09-01'):{'symbol':'追','source':'manual'}})
        e._collect_staffing_shortfalls()
        self.assertTrue(any(r[0]=='2026-09-01' and r[1]=='work_1' for r in e.understaffed_shortfalls))

    def test_full_month_preserves_one_location_and_separate_leaders(self):
        people=[member(i,['1F'] if i<=4 else ['2F'] if i<=8 else ['1F','2F'],leader=i>8,night=True) for i in range(1,13)]
        e,result=generate(people,configuration(night=True))
        self.assertEqual(len(result['placements']),len({(p['staff_id'],p['date']) for p in result['placements']}))
        for day in e.period_dates:
            self.assertTrue(e._has_leader_on_night(day),day)
            self.assertGreaterEqual(e._count_work_on_day(day,'night',floor='1F'),1,day)
            self.assertGreaterEqual(e._count_work_on_day(day,'night',floor='2F'),1,day)
            self.assertGreaterEqual(e._count_work_on_day(day,'night'),3,day)


class PlacementStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.mock=patch('db.database.DB_PATH',Path(self.temp.name)/'placements.db');self.mock.start()
        init_db()
        with get_connection() as conn:
            self.ids=[r[0] for r in conn.execute('SELECT id FROM staff ORDER BY id LIMIT 3')]
            conn.execute('UPDATE staff SET exclude_from_staffing=1')
            conn.execute('DELETE FROM staff_day_incompatibilities');conn.execute('DELETE FROM staff_night_incompatibilities')
            for index,sid in enumerate(self.ids):
                floors=['1F'] if index==0 else ['2F'] if index==1 else ['1F','2F']
                conn.execute('UPDATE staff SET exclude_from_staffing=0,can_work_night=1,fix_night_shift_count=1,night_shift_count=4,staffing_basis=?,position=?,department=? WHERE id=?',
                             (json.dumps({'day':60,'night':40}),'リーダー' if index==2 else '一般',floors[0],sid))
                conn.execute('DELETE FROM staff_floors WHERE staff_id=?',(sid,))
                conn.executemany('INSERT INTO staff_floors(staff_id,floor) VALUES(?,?)',[(sid,f) for f in floors])
        save_settings(configuration(night=True))

    def tearDown(self):
        self.mock.stop();self.temp.cleanup()

    def placements(self):
        return get_placements_between(date(2026,9,1),date(2026,9,30))

    def preview(self,**kw):
        return create_preview(GenerationPreviewRequest(year=2026,month=9,**kw))

    def test_exact_placements_are_applied_and_blank_regeneration_keeps_them(self):
        draft=self.preview()
        self.assertEqual(self.placements(),{})
        expected={(p['staff_id'],p['date']):{'floor':p['floor'],'role':p['role']} for p in draft['placements']}
        apply_preview(draft['token'])
        self.assertEqual(self.placements(),expected)
        again=self.preview(mode='blank');apply_preview(again['token'])
        self.assertEqual(self.placements(),expected)
        init_db()  # Migration is idempotent and does not rewrite locations.
        self.assertEqual(self.placements(),expected)

    def test_other_floor_location_preserved_during_scoped_apply(self):
        sid=self.ids[1]
        upsert_shift_cell(sid,2026,9,1,'夜',source='auto')
        with get_connection() as conn:
            save_placements(conn,[dict(staff_id=sid,date='2026-09-01',floor='2F',role='floor')])
        draft=self.preview(floor='1F');apply_preview(draft['token'])
        self.assertEqual(self.placements()[(sid,'2026-09-01')],{'floor':'2F','role':'floor'})

    def test_changed_location_invalidates_preview_and_failed_apply_rolls_back(self):
        sid=self.ids[0];upsert_shift_cell(sid,2026,9,1,'○')
        draft=self.preview()
        with get_connection() as conn:
            save_placements(conn,[dict(staff_id=sid,date='2026-09-01',floor='1F',role='floor')])
        with self.assertRaisesRegex(ValueError,'変更'):apply_preview(draft['token'])
        draft=self.preview();before=self.placements()
        with get_connection() as conn:
            conn.execute("CREATE TRIGGER fail_placement BEFORE INSERT ON shift_placements BEGIN SELECT RAISE(ABORT,'failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):apply_preview(draft['token'])
        self.assertEqual(self.placements(),before)

    def test_editing_shift_invalidates_location_and_clear_cascades(self):
        draft=self.preview();apply_preview(draft['token'])
        (sid,day),placement=next(iter(self.placements().items()))
        upsert_shift_cell(sid,2026,9,int(day[-2:]),'有休')
        self.assertNotIn((sid,day),self.placements())
        delete_shifts_between(date(2026,9,1),date(2026,9,30))
        self.assertEqual(self.placements(),{})

    def test_leave_approval_bulk_write_clears_old_work_location(self):
        from db.shift_repository import bulk_upsert_shifts
        draft=self.preview();apply_preview(draft['token'])
        (sid,day),_=next(iter(self.placements().items()))
        bulk_upsert_shifts([(sid,day,'有休','leave')])
        self.assertNotIn((sid,day),self.placements())
