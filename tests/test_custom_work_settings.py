"""Regression coverage for shifts created by the integrated settings editor."""
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from copy import deepcopy

from data.settings_defaults import DEFAULT_SETTINGS
from data.shift_symbols import get_shift_symbols, symbol_to_key, build_shift_legend, validate_shift_symbols
from data.time_coverage import get_assignable_work_types
from db.settings_repository import _merge_settings, save_settings, get_settings
from db.database import init_db
from schemas.settings import AppSettings
from services.morning_off import is_night_work_symbol
from test_shift_generator import settings_for, staff_member, generate


def custom_settings(base='day'):
    cfg = settings_for(night_staff=0, day_staff=0)
    cfg['staffing_basis_options'] = deepcopy(DEFAULT_SETTINGS['staffing_basis_options']) + [
        dict(key='work_1', label='追加勤務', base_key=base, start_time='17:00' if base == 'night' else '10:00', end_time='09:00' if base == 'night' else '14:00')]
    cfg['shift_symbols']['work_1'] = '追'
    cfg['min_staff_by_floor']['1F']['work_1'] = 1
    return cfg


class CustomWorkSettingsTests(unittest.TestCase):
    def test_new_shift_survives_schema_and_repository_merge(self):
        cfg = custom_settings('night')
        cfg['visible_work_types']['work_1'] = False
        payload = AppSettings(**cfg).model_dump()
        self.assertFalse(payload['visible_work_types']['work_1'])
        self.assertEqual(payload['min_staff_by_floor']['1F']['work_1'], 1)
        # JSON field order must not affect added work types' minimum counts.
        merged = _merge_settings(dict(reversed(list(payload.items()))))
        self.assertEqual(merged['min_staff_by_floor']['1F']['work_1'], 1)
        self.assertEqual(next(x for x in merged['staffing_basis_options'] if x['key']=='work_1')['base_key'], 'night')

    def test_save_and_reload_custom_work(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("db.database.DB_PATH", Path(directory) / "test.db"):
                init_db()
                saved = save_settings(AppSettings(**custom_settings()).model_dump())
                loaded = get_settings()
                self.assertEqual(saved['staffing_basis_options'], loaded['staffing_basis_options'])
                self.assertEqual(loaded['shift_symbols']['work_1'], '追')
                self.assertEqual(loaded['min_staff_by_floor']['1F']['work_1'], 1)

    def test_custom_symbol_is_available_in_calendar_and_placement(self):
        cfg = custom_settings('night')
        self.assertEqual(symbol_to_key('追', cfg), 'work_1')
        self.assertTrue(is_night_work_symbol('追', cfg))
        self.assertIn('追', [x['symbol'] for x in build_shift_legend(cfg)])
        self.assertEqual(next(x for x in get_assignable_work_types(cfg) if x['key']=='work_1')['base_key'], 'night')
        validate_shift_symbols(cfg)

    def test_duplicate_symbol_is_rejected(self):
        cfg = custom_settings()
        cfg['shift_symbols']['work_1'] = get_shift_symbols(cfg)['day']
        with self.assertRaises(ValueError):
            validate_shift_symbols(cfg)

    def test_custom_day_minimum_is_assigned(self):
        cfg = custom_settings()
        staff = [staff_member(i) for i in range(1, 7)]
        engine, _ = generate(staff, cfg)
        for day in engine.period_dates:
            self.assertGreaterEqual(sum(engine.grid.get((s['id'],day)) == '追' for s in staff), 1)

    def test_custom_night_keeps_quota_and_recovery(self):
        cfg = custom_settings('night')
        staff = [staff_member(i, 5) for i in range(1, 7)]
        engine, _ = generate(staff, cfg)
        for member in staff:
            nights = [day for day in engine.period_dates if is_night_work_symbol(engine.grid.get((member['id'],day), ''), cfg)]
            self.assertEqual(len(nights), 5)
            for day in nights:
                index = engine.date_index[day]
                if index+1 < len(engine.period_dates):
                    self.assertEqual(symbol_to_key(engine.grid[(member['id'],engine.period_dates[index+1])],cfg),'morning_off')
        for day in engine.period_dates:
            self.assertTrue(any(engine.grid.get((s['id'],day)) == '追' for s in staff))

    def test_edited_label_in_calendar_legend(self):
        cfg = custom_settings()
        cfg['staffing_basis_options'][0]['label'] = '早朝勤務'
        key = cfg['staffing_basis_options'][0]['key']
        self.assertEqual(next(x for x in build_shift_legend(cfg) if x['key']==key)['label'], '早朝勤務')
