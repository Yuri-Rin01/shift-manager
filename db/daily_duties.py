"""Daily duties are separate from staffing assignments and survive regeneration."""
import json

DEFAULT_ROLES = ['BB', 'L', '着脱', '入浴準備', 'おむつ・配茶', '物品補充', '居室整理', 'シーツ・ゴミ捨て']


def init_daily_tables(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS daily_duties (
        staff_id INTEGER NOT NULL REFERENCES staff(id) ON DELETE CASCADE,
        shift_date TEXT NOT NULL, am TEXT NOT NULL DEFAULT '', pm TEXT NOT NULL DEFAULT '',
        shift_signature TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
        PRIMARY KEY(staff_id, shift_date))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS daily_duty_options (
        id INTEGER PRIMARY KEY CHECK(id=1), labels TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1)''')
    conn.execute('INSERT OR IGNORE INTO daily_duty_options(id,labels) VALUES(1,?)', (json.dumps(DEFAULT_ROLES, ensure_ascii=False),))
