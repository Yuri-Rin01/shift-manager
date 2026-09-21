"""Atomic cell edits and optimistic, exact undo/redo including off-screen cells."""
from datetime import date, timedelta
from db.database import get_connection
from data.shift_symbols import symbol_to_key, get_shift_symbols
from services.morning_off import is_night_work_symbol


def snapshot(conn, sid, day):
    row = conn.execute('SELECT symbol, source FROM shift_assignments WHERE staff_id=? AND shift_date=?', (sid, day)).fetchone()
    placement = conn.execute('SELECT floor, role FROM shift_placements WHERE staff_id=? AND shift_date=?', (sid, day)).fetchone()
    return dict(staff_id=sid, shift_date=day, symbol=row['symbol'] if row else '',
                source=row['source'] if row else '', placement=dict(placement) if placement else None)


def write(conn, cell):
    args = cell['staff_id'], cell['shift_date']
    if not cell['symbol']:
        conn.execute('DELETE FROM shift_assignments WHERE staff_id=? AND shift_date=?', args)
        return
    conn.execute('INSERT INTO shift_assignments(staff_id,shift_date,symbol,source) VALUES (?,?,?,?) '
                 'ON CONFLICT(staff_id,shift_date) DO UPDATE SET symbol=excluded.symbol,source=excluded.source',
                 (*args, cell['symbol'], cell['source']))
    conn.execute('DELETE FROM shift_placements WHERE staff_id=? AND shift_date=?', args)
    if cell.get('placement'):
        p = cell['placement']
        conn.execute('INSERT INTO shift_placements(staff_id,shift_date,floor,role) VALUES (?,?,?,?)', (*args, p['floor'], p['role']))


def edit_cell(sid, day, symbol, settings):
    from services.period_lock import assert_dates_editable

    dates = [day.isoformat(), (day + timedelta(days=1)).isoformat()]
    assert_dates_editable(dates, action="編集")
    with get_connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        before = [snapshot(conn, sid, d) for d in dates]
        primary, following = before
        placement = primary['placement'] if primary['symbol'] == symbol else None
        write(conn, dict(primary, symbol=symbol, source='manual', placement=placement))
        if is_night_work_symbol(symbol, settings):
            if following['source'] not in ('manual', 'leave') and symbol_to_key(following['symbol'], settings) not in ('paid_leave', 'half_leave', 'morning_off'):
                write(conn, dict(following, symbol=get_shift_symbols(settings)['morning_off'], source='auto', placement=None))
        elif following['source'] == 'auto' and symbol_to_key(following['symbol'], settings) == 'morning_off':
            write(conn, dict(following, symbol='', source='', placement=None))
        after = [snapshot(conn, sid, d) for d in dates]
        changed = [(a, b) for a, b in zip(before, after) if a != b]
        return dict(after[0], related=[b for a, b in changed if b['shift_date'] != dates[0]],
                    history_before=[a for a, b in changed], history_after=[b for a, b in changed])


def restore_cells(states, expected):
    from services.period_lock import assert_dates_editable

    def key(c):
        return c['staff_id'], c['shift_date']
    if not states or len({key(c) for c in states}) != len(states) or {key(c) for c in states} != {key(c) for c in expected}:
        raise ValueError('復元対象が一致しません。')
    assert_dates_editable([c['shift_date'] for c in states], action="取り消し／やり直し")
    with get_connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        for cell in expected:
            if snapshot(conn, *key(cell)) != cell:
                raise ValueError('勤務表が別の操作で変更されています。再読み込みして確認してください。')
        for cell in states:
            write(conn, cell)
    return states
