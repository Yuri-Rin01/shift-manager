"""Persist the exact proposed assignments; reject applying an outdated preview."""
from collections import Counter
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
import secrets
import time

from data.placement_rules import get_floor_labels, validate_min_staff_by_floor, validate_time_slot_staffing_rules
from data.shift_symbols import symbol_to_key, get_shift_symbols
from data.staffing_basis import get_staffing_basis_options
from db.database import get_connection
from db.settings_repository import get_settings
from db.staff_repository import list_staff
from db.shift_repository import get_shifts_between, get_placements_between, save_placements
from schemas.generation_preview import GenerationPreviewRequest
from schemas.settings import AppSettings
from services.shift_generator import _Generator, _symbol_work_key

TABLE = 'generation_previews'
TTL = 3600


def _ensure_table(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS generation_previews (
        token TEXT PRIMARY KEY, expires REAL NOT NULL, fingerprint TEXT NOT NULL, payload TEXT NOT NULL)''')


def _fingerprint(conn):
    """Includes staff relationships, requests, settings and assignments, in one read snapshot."""
    tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name") if row[0] != TABLE]
    values = {}
    for table in tables:
        quoted = '"' + table.replace('"', '""') + '"'
        rows = [dict(row) for row in conn.execute('SELECT * FROM ' + quoted)]
        values[table] = sorted(rows, key=lambda row: json.dumps(row, sort_keys=True))
    return hashlib.sha256(json.dumps(values, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def generation_context():
    settings = get_settings()
    return {'settings': settings, 'floors': get_floor_labels(), 'work_types': get_staffing_basis_options(settings),
            'staff': list_staff(), 'symbols': get_shift_symbols(settings)}


def create_preview(request: GenerationPreviewRequest):
    with get_connection() as conn:
        _ensure_table(conn)
        conn.commit()
        conn.execute('BEGIN')
        fingerprint = _fingerprint(conn)
    original = get_settings()
    settings = deepcopy(original)
    supplied = request.conditions.model_dump(exclude_unset=True) if request.conditions else {}
    supplied = {key: value for key, value in supplied.items() if value is not None or key == "off_days_per_period"}
    settings.update(supplied)
    settings.update(prioritize_leave_requests=True, consider_night_eligibility=True, fairness_mode='balance')
    floors = get_floor_labels()
    if request.floor and request.floor not in floors:
        raise ValueError('対象フロアが見つかりません。')
    # Validate before normalization so invalid counts cannot be silently discarded.
    for floor, counts in (supplied.get('min_staff_by_floor') or {}).items():
        if floor not in floors or any(key not in {w['key'] for w in get_staffing_basis_options(settings)} for key in counts):
            raise ValueError('必要人数のフロアまたは勤務が不正です。')
        if any(type(value) is not int or not 0 <= value <= 99 for value in counts.values()):
            raise ValueError('必要人数は0〜99人で指定してください。')
    if supplied.get('min_staff_by_floor') is not None:
        merged_counts = deepcopy(original.get('min_staff_by_floor') or {})
        for floor, values in supplied['min_staff_by_floor'].items():
            merged_counts.setdefault(floor, {}).update(values)
        settings['min_staff_by_floor'] = merged_counts
    validate_time_slot_staffing_rules(settings)
    settings = AppSettings(**settings).model_dump()
    validate_min_staff_by_floor(settings)
    staff = deepcopy(list_staff())
    active = [s for s in staff if not s.get('exclude_from_staffing') and
              (not request.floor or request.floor in (s.get('departments') or [s.get('department')]))]
    ids = {s['id'] for s in active}
    if not active:
        raise ValueError('対象となる職員がいません。職員管理の担当フロアを確認してください。')
    if any(sid not in ids for sid in request.night_counts):
        raise ValueError('対象外の職員の夜勤回数は変更できません。')
    for member in active:
        if member['id'] in request.night_counts:
            count = request.night_counts[member['id']]
            if not 0 <= count <= 31 or (not member.get('can_work_night') and count):
                raise ValueError('夜勤回数または夜勤可否が不正です。')
            member.update(fix_night_shift_count=True, night_shift_count=count)
    engine = _Generator(request.year, request.month, settings, staff_members=staff)
    engine.staff_list = active
    if request.floor:
        engine.floors = [request.floor]
        engine.time_slot_rules = [r for r in engine.time_slot_rules if not r.get('floor') or r['floor'] == request.floor]
    if not engine.period_dates:
        raise ValueError('生成対象の日付がありません。')
    start, end = date.fromisoformat(engine.period_dates[0]), date.fromisoformat(engine.period_dates[-1])
    existing = get_shifts_between(start, end)
    fixed = {}
    for key, cell in existing.items():
        if key[0] not in ids or request.mode == 'blank':
            fixed[key] = {**cell, 'source': 'manual'}
        elif cell['source'] in ('manual', 'leave'):
            fixed[key] = cell
    result = engine.run(fixed, get_placements_between(start, end),
                        get_shifts_between(start - timedelta(days=14), end + timedelta(days=14)))
    assignments = []
    for sid, day, symbol, source in result['assignments']:
        if sid not in ids:
            continue
        old = existing.get((sid, day))
        # Fixed and blank-only cells are byte-for-byte retained, including their sources.
        if old and (old['source'] in ('manual', 'leave') or request.mode == 'blank'):
            symbol, source = old['symbol'], old['source']
        assignments.append([sid, day, symbol, source])
    summary = []
    for member in active:
        cells = [a for a in assignments if a[0] == member['id']]
        counts = Counter(symbol_to_key(a[2], settings) for a in cells)
        summary.append({'id': member['id'], 'name': member['name'], 'off': counts['off'],
                        'off_target': engine._period_off_target(),
                        'nights': sum(_symbol_work_key(a[2], settings) == 'night' for a in cells),
                        'night_target': member.get('night_shift_count') if member.get('fix_night_shift_count') else None})
    protected = [cell for key, cell in existing.items() if key[0] in ids and cell['source'] in ('manual', 'leave')]
    result['stats'].update(staff_count=len(active), manual_locked=sum(c['source']=='manual' for c in protected),
                           leave_locked=sum(c['source']=='leave' for c in protected))
    placements = [p for p in result['placements'] if p['staff_id'] in ids]
    payload = {'assignments': assignments, 'placements': placements, 'ids': sorted(ids), 'start': start.isoformat(), 'end': end.isoformat(),
               'mode': request.mode, 'defaults': {key: settings[key] for key in supplied} if request.save_defaults else {},
               'stats': result['stats'], 'warnings': result['warnings'], 'summary': summary,
               'dates': engine.period_dates, 'conditions': {key: settings[key] for key in ('off_days_per_period','max_consecutive_days','max_night_per_week')},
               'scope': request.floor or 'すべてのフロア'}
    token = secrets.token_urlsafe(32)
    with get_connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        if _fingerprint(conn) != fingerprint:
            raise ValueError('計算中に設定・職員・シフトが変更されました。もう一度案を作成してください。')
        conn.execute('DELETE FROM generation_previews WHERE expires < ?', (time.time(),))
        conn.execute('INSERT INTO generation_previews VALUES (?, ?, ?, ?)', (token, time.time()+TTL, fingerprint, json.dumps(payload, ensure_ascii=False)))
    return {**payload, 'token': token, 'expires_in': TTL}


def apply_preview(token: str):
    with get_connection() as conn:
        _ensure_table(conn)
        conn.commit()
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT * FROM generation_previews WHERE token = ?', (token,)).fetchone()
        if not row or row['expires'] < time.time():
            raise ValueError('この案の有効期限が切れています。もう一度案を作成してください。')
        if _fingerprint(conn) != row['fingerprint']:
            raise ValueError('案の作成後に設定・職員・シフトが変更されました。最新の条件で作り直してください。')
        payload = json.loads(row['payload'])
        if any(w['level'] == 'error' for w in payload['warnings']):
            raise ValueError('エラーを含む案は反映できません。条件を見直してください。')
        # One transaction: never clear another floor or leave an empty schedule on failure.
        conn.executemany('''INSERT INTO shift_assignments(staff_id,shift_date,symbol,source) VALUES (?,?,?,?)
            ON CONFLICT(staff_id,shift_date) DO UPDATE SET symbol=excluded.symbol, source=excluded.source''', payload['assignments'])
        # Replace only this draft's cells, including locations cleared by a day off.
        conn.executemany('DELETE FROM shift_placements WHERE staff_id=? AND shift_date=?',
                         [(a[0], a[1]) for a in payload['assignments']])
        save_placements(conn, payload.get('placements', []))
        if payload['defaults']:
            old = conn.execute('SELECT data FROM app_settings WHERE id=1').fetchone()
            settings = json.loads(old[0]) if old else {}
            settings.update(payload['defaults'])
            conn.execute('INSERT INTO app_settings(id,data) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data', (json.dumps(settings, ensure_ascii=False),))
        conn.execute('DELETE FROM generation_previews WHERE token = ?', (token,))
    return {'applied': True, 'message': '確認した生成案を反映しました。', 'stats': payload['stats']}
