import unittest
from datetime import date, timedelta
from services.shift_generator import _Generator
from test_shift_generator import settings_for, staff_member
import test_floor_placements
from db.database import get_connection
from db.settings_repository import get_settings, save_settings
from db.shift_repository import upsert_shift_cell, get_shifts_between, save_placements
from services.shift_edit import edit_cell, restore_cells, snapshot


class BoundaryTests(unittest.TestCase):
    def engine(self, year=2026, month=9, **settings):
        cfg=settings_for(night_staff=0, day_staff=0);cfg.update(settings)
        return _Generator(year, month, cfg, staff_members=[staff_member(1, 4)])

    def test_previous_night_chain_across_calendar_and_custom_periods(self):
        for year,month,start in [(2026,9,1),(2027,1,1),(2028,3,1),(2026,9,16)]:
            e=self.engine(year,month,calendar_start_day=start)
            previous=(e.period_start-timedelta(days=1)).isoformat()
            result=e.run({}, boundary={(1,previous):dict(symbol='夜',source='auto')})
            self.assertEqual(e.grid[(1,e.period_dates[0])],'明')
            self.assertEqual(e.grid[(1,e.period_dates[1])],'×')
            self.assertFalse(any(a[1]==previous for a in result['assignments']))

    def test_two_days_back_night_requires_rest_even_without_saved_morning(self):
        e=self.engine();e.run({},boundary={(1,'2026-08-30'):dict(symbol='夜',source='manual')})
        self.assertEqual(e.grid[(1,'2026-09-01')],'×')

    def test_next_period_work_blocks_final_night_and_consecutive_work(self):
        e=self.engine(max_consecutive_days=2)
        e.boundary={(1,'2026-10-01'):dict(symbol='○'),(1,'2026-10-02'):dict(symbol='○')}
        self.assertFalse(e._can_work(e.staff_list[0],'night','2026-09-30'))
        self.assertFalse(e._can_work(e.staff_list[0],'day','2026-09-30'))
        e.boundary={(1,'2026-08-31'):dict(symbol='○'),(1,'2026-08-30'):dict(symbol='○')}
        self.assertFalse(e._can_work(e.staff_list[0],'day','2026-09-01'))

    def test_week_limit_includes_external_nights_without_monthly_count(self):
        e=self.engine(max_night_per_week=1, week_start='monday')
        e.run({},boundary={(1,'2026-08-31'):dict(symbol='夜',source='auto')})
        self.assertEqual(sum(e.grid.get((1,f'2026-09-{d:02}'))=='夜' for d in range(1,7)),0)
        self.assertEqual(e.night_counts[1],sum(s=='夜' for s in e.grid.values()))

    def test_boundary_manual_conflict_is_preserved_and_reported(self):
        e=self.engine();r=e.run({(1,'2026-09-01'):dict(symbol='○',source='manual')},boundary={(1,'2026-08-31'):dict(symbol='夜',source='auto')})
        self.assertEqual(e.grid[(1,'2026-09-01')],'○')
        self.assertTrue(any(w['code']=='boundary_rest_conflict' for w in r['warnings']))

    def test_day_incompatibility_is_symmetric_for_both_orders(self):
        a,b=staff_member(1),staff_member(2);a['day_incompatible_ids']=[2]
        for fixed,candidate in [(1,2),(2,1)]:
            e=_Generator(2026,9,settings_for(night_staff=0),staff_members=[a,b])
            e._set_symbol(fixed,'2026-09-01','○')
            self.assertFalse(e._can_work(e.staff_by_id[candidate],'early','2026-09-01'))


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_floor_placements.PlacementStorageTests();self.fixture.setUp();self.sid=self.fixture.ids[0]
    def tearDown(self):
        self.fixture.tearDown()

    def test_symbol_rename_preserves_sources_and_floor_with_swap(self):
        sid=self.sid
        upsert_shift_cell(sid,2026,9,1,'○',source='auto')
        upsert_shift_cell(sid,2026,9,2,'夜',source='manual')
        with get_connection() as c: save_placements(c,[dict(staff_id=sid,date='2026-09-01',floor='1F',role='floor')])
        cfg=get_settings();cfg['shift_symbols']['day']='夜';cfg['shift_symbols']['night']='○';save_settings(cfg)
        with get_connection() as c:
            first=snapshot(c,sid,'2026-09-01');second=snapshot(c,sid,'2026-09-02')
        self.assertEqual((first['symbol'],first['source'],first['placement']['floor']),('夜','auto','1F'))
        self.assertEqual((second['symbol'],second['source']),('○','manual'))

    def test_undo_redo_empty_and_offscreen_morning_are_atomic(self):
        r=edit_cell(self.sid,date(2026,9,30),'夜',get_settings())
        self.assertEqual(len(r['history_after']),2)
        restore_cells(r['history_before'],r['history_after'])
        self.assertFalse(get_shifts_between(date(2026,9,30),date(2026,10,1)))
        restore_cells(r['history_after'],r['history_before'])
        self.assertEqual(get_shifts_between(date(2026,10,1),date(2026,10,1))[(self.sid,'2026-10-01')]['symbol'],'明')

    def test_undo_restores_auto_source_and_placement_and_rejects_conflict(self):
        upsert_shift_cell(self.sid,2026,9,1,'○',source='auto')
        with get_connection() as c: save_placements(c,[dict(staff_id=self.sid,date='2026-09-01',floor='1F',role='floor')])
        r=edit_cell(self.sid,date(2026,9,1),'夜',get_settings())
        restore_cells(r['history_before'],r['history_after'])
        with get_connection() as c: cell=snapshot(c,self.sid,'2026-09-01')
        self.assertEqual(cell['source'],'auto');self.assertEqual(cell['placement']['floor'],'1F')
        restore_cells(r['history_after'],r['history_before'])
        upsert_shift_cell(self.sid,2026,9,2,'×',source='manual')
        with self.assertRaises(ValueError): restore_cells(r['history_before'],r['history_after'])
        with get_connection() as c: self.assertEqual(snapshot(c,self.sid,'2026-09-01')['symbol'],'夜')
