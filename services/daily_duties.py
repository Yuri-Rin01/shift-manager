"""Live shift-derived daily/weekly role sheets with optimistic edits."""
import hashlib
import json
from datetime import date, timedelta

from data.shift_symbols import symbol_to_key
from data.staffing_basis import base_work_key, get_staffing_basis_options
from db.database import get_connection
from db.settings_repository import get_settings
from db.staff_repository import list_staff


class DutyConflict(ValueError):
    pass


def duty_cell(conn, sid, day, settings):
    row = conn.execute('SELECT symbol FROM shift_assignments WHERE staff_id=? AND shift_date=?', (sid, day)).fetchone()
    placement = conn.execute('SELECT floor,role FROM shift_placements WHERE staff_id=? AND shift_date=?', (sid, day)).fetchone()
    saved = conn.execute('SELECT * FROM daily_duties WHERE staff_id=? AND shift_date=?', (sid, day)).fetchone()
    symbol = row['symbol'] if row else ''
    key = symbol_to_key(symbol, settings) if symbol else None
    base = base_work_key(key, settings) if key else None
    definition = next((v for v in get_staffing_basis_options(settings) if v['key'] == key), {})
    start, end = definition.get('start_time', ''), definition.get('end_time', '')
    am_enabled = base in ('early', 'day', 'late')
    pm_enabled = am_enabled
    # Never imply that a short morning-only shift covers afternoon duties.
    if am_enabled and start and end and start < end:
        am_enabled = start < '12:00'
        pm_enabled = end > '12:00'
    signature = hashlib.sha256(json.dumps([key, start, end, dict(placement) if placement else None], sort_keys=True).encode()).hexdigest()
    stale = bool(saved and (saved['am'] or saved['pm']) and saved['shift_signature'] != signature)
    return {'staff_id': sid, 'date': day, 'symbol': symbol, 'floor': placement['floor'] if placement else '',
            'night_leader': bool(placement and placement['role'] == 'night_leader'), 'night': base == 'night',
            'am_enabled': am_enabled, 'pm_enabled': pm_enabled,
            'am': saved['am'] if saved else '', 'pm': saved['pm'] if saved else '',
            'stale': stale, 'signature': signature, 'revision': saved['revision'] if saved else 0}


def get_sheet(start: date, days: int, floor: str = ''):
    settings = get_settings()
    dates = [(start + timedelta(days=i)).isoformat() for i in range(days)]
    staff = list_staff()
    if floor:
        staff = [s for s in staff if floor in (s.get('departments') or [s.get('department')])]
    with get_connection() as conn:
        rows = [{'id': s['id'], 'name': s['name'], 'departments': s.get('departments') or [s.get('department', '')],
                 'cells': [duty_cell(conn, s['id'], d, settings) for d in dates]} for s in staff]
        options = conn.execute('SELECT labels,revision FROM daily_duty_options WHERE id=1').fetchone()
    return {'dates': dates, 'rows': rows, 'roles': json.loads(options['labels']), 'roles_revision': options['revision'],
            'floors': [f['label'] for f in settings.get('floors', [])], 'facility_name': settings.get('facility_name', ''),
            'review_count': sum(c['stale'] for r in rows for c in r['cells'])}


def save_duty(sid: int, day: date, am: str, pm: str, signature: str, revision: int):
    settings = get_settings()
    with get_connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        if not conn.execute('SELECT id FROM staff WHERE id=?', (sid,)).fetchone():
            raise ValueError('職員が見つかりません。')
        current = duty_cell(conn, sid, day.isoformat(), settings)
        if current['signature'] != signature or current['revision'] != revision:
            raise DutyConflict('勤務または役割が変更されました。再読み込みして確認してください。')
        if (am and not current['am_enabled']) or (pm and not current['pm_enabled']):
            raise ValueError('勤務のない時間帯には担当を登録できません。休み・明け・夜勤はAM／PM担当の対象外です。')
        conn.execute('''INSERT INTO daily_duties(staff_id,shift_date,am,pm,shift_signature,revision)
            VALUES(?,?,?,?,?,1) ON CONFLICT(staff_id,shift_date) DO UPDATE SET
            am=excluded.am,pm=excluded.pm,shift_signature=excluded.shift_signature,revision=daily_duties.revision+1''',
            (sid, day.isoformat(), am.strip(), pm.strip(), signature))
        return duty_cell(conn, sid, day.isoformat(), settings)


def save_roles(labels: list[str], revision: int):
    labels = list(dict.fromkeys(x.strip() for x in labels if x.strip()))
    with get_connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        result = conn.execute('UPDATE daily_duty_options SET labels=?,revision=revision+1 WHERE id=1 AND revision=?',
                              (json.dumps(labels, ensure_ascii=False), revision))
        if not result.rowcount:
            raise DutyConflict('候補が別の操作で変更されています。再読み込みしてください。')
    return {'roles': labels, 'roles_revision': revision + 1}
