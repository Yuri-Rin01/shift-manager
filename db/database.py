import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "shift.db"

CREATE_STAFF_TABLE = """
CREATE TABLE IF NOT EXISTS staff (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    department TEXT NOT NULL,
    job_type TEXT NOT NULL,
    position TEXT NOT NULL DEFAULT '',
    can_work_night INTEGER NOT NULL DEFAULT 0 CHECK (can_work_night IN (0, 1))
);
"""

CREATE_SETTINGS_TABLE = """
CREATE TABLE IF NOT EXISTS app_settings (
    id INTEGER PRIMARY KEY,
    data TEXT NOT NULL
);
"""

CREATE_SHIFT_TABLE = """
CREATE TABLE IF NOT EXISTS shift_assignments (
    staff_id INTEGER NOT NULL,
    shift_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'auto',
    PRIMARY KEY (staff_id, shift_date),
    FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE CASCADE
);
"""

CREATE_NIGHT_INCOMPATIBILITY_TABLE = """
CREATE TABLE IF NOT EXISTS staff_night_incompatibilities (
    staff_id INTEGER NOT NULL,
    incompatible_staff_id INTEGER NOT NULL,
    PRIMARY KEY (staff_id, incompatible_staff_id),
    FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE CASCADE,
    FOREIGN KEY (incompatible_staff_id) REFERENCES staff(id) ON DELETE CASCADE,
    CHECK (staff_id != incompatible_staff_id)
);
"""

CREATE_DAY_INCOMPATIBILITY_TABLE = """
CREATE TABLE IF NOT EXISTS staff_day_incompatibilities (
    staff_id INTEGER NOT NULL,
    incompatible_staff_id INTEGER NOT NULL,
    PRIMARY KEY (staff_id, incompatible_staff_id),
    FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE CASCADE,
    FOREIGN KEY (incompatible_staff_id) REFERENCES staff(id) ON DELETE CASCADE,
    CHECK (staff_id != incompatible_staff_id)
);
"""

CREATE_STAFF_FLOORS_TABLE = """
CREATE TABLE IF NOT EXISTS staff_floors (
    staff_id INTEGER NOT NULL,
    floor TEXT NOT NULL,
    PRIMARY KEY (staff_id, floor),
    FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE CASCADE
);
"""

CREATE_LEAVE_REQUESTS_TABLE = """
CREATE TABLE IF NOT EXISTS leave_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    staff_id INTEGER NOT NULL,
    shift_date TEXT NOT NULL,
    request_type TEXT NOT NULL CHECK (request_type IN ('off', 'paid_leave', 'half_leave')),
    note TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (staff_id) REFERENCES staff(id) ON DELETE CASCADE
);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    from db.settings_repository import get_settings, save_settings
    from data.settings_defaults import DEFAULT_SETTINGS

    with get_connection() as conn:
        conn.execute(CREATE_STAFF_TABLE)
        conn.execute(CREATE_SETTINGS_TABLE)
        conn.execute(CREATE_SHIFT_TABLE)
        conn.execute(CREATE_NIGHT_INCOMPATIBILITY_TABLE)
        conn.execute(CREATE_DAY_INCOMPATIBILITY_TABLE)
        conn.execute(CREATE_STAFF_FLOORS_TABLE)
        conn.execute(CREATE_LEAVE_REQUESTS_TABLE)
        _migrate_leave_requests_index(conn)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(staff)")}
        if "position" not in columns:
            conn.execute("ALTER TABLE staff ADD COLUMN position TEXT NOT NULL DEFAULT ''")
        if "staffing_basis" not in columns:
            conn.execute(
                "ALTER TABLE staff ADD COLUMN staffing_basis TEXT NOT NULL DEFAULT '[]'"
            )
        if "exclude_from_staffing" not in columns:
            conn.execute(
                "ALTER TABLE staff ADD COLUMN exclude_from_staffing INTEGER NOT NULL DEFAULT 0"
            )
        if "off_days_per_period" not in columns:
            conn.execute("ALTER TABLE staff ADD COLUMN off_days_per_period INTEGER")
        if "night_shift_count" not in columns:
            conn.execute("ALTER TABLE staff ADD COLUMN night_shift_count INTEGER")
        if "fix_night_shift_count" not in columns:
            conn.execute(
                "ALTER TABLE staff ADD COLUMN fix_night_shift_count INTEGER NOT NULL DEFAULT 0"
            )
            conn.execute(
                "UPDATE staff SET fix_night_shift_count = 1 WHERE night_shift_count IS NOT NULL"
            )
        _migrate_staff_floors(conn)
        _migrate_staffing_defaults(conn)
        _migrate_removed_staffing_basis(conn)
        _migrate_staffing_basis_catalog(conn)
        _migrate_staffing_basis_hours(conn)
        _migrate_min_staff_by_work_type(conn)
        _migrate_min_staff_by_floor(conn)
        _migrate_staffing_requirement_mode(conn)
        _migrate_shift_source(conn)
        conn.executemany(
            "UPDATE staff SET job_type = ? WHERE job_type = ?",
            [
                ("介護士", "介"),
                ("看護師", "看"),
                ("理学療法士", "療"),
            ],
        )
        row = conn.execute("SELECT id FROM app_settings WHERE id = 1").fetchone()
        if row is None:
            import json

            conn.execute(
                "INSERT INTO app_settings (id, data) VALUES (1, ?)",
                (json.dumps(DEFAULT_SETTINGS, ensure_ascii=False),),
            )
        _seed_staff_if_empty(conn)
        _sync_seed_staff_floors(conn)
        _sync_seed_staff_night_flags(conn)
        _migrate_departments_to_floors(conn)
        conn.commit()
    get_settings()


def _migrate_leave_requests_index(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_leave_requests_staff_date_active
        ON leave_requests (staff_id, shift_date)
        WHERE status IN ('pending', 'approved')
        """
    )


def _migrate_staff_floors(conn: sqlite3.Connection) -> None:
    rows = conn.execute("SELECT id, department FROM staff").fetchall()
    for row in rows:
        existing = conn.execute(
            "SELECT 1 FROM staff_floors WHERE staff_id = ? LIMIT 1",
            (row["id"],),
        ).fetchone()
        if existing or not row["department"]:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO staff_floors (staff_id, floor) VALUES (?, ?)",
            (row["id"], row["department"]),
        )


def _migrate_staffing_defaults(conn: sqlite3.Connection) -> None:
    import json

    from data.staffing_basis import equal_split_ratios, get_default_staffing_basis_ratios

    default_ratios = get_default_staffing_basis_ratios()
    default_json = json.dumps(default_ratios, ensure_ascii=False)
    conn.execute(
        """
        UPDATE staff
        SET staffing_basis = ?
        WHERE staffing_basis IS NULL OR staffing_basis = '' OR staffing_basis = '[]'
        """,
        (default_json,),
    )

    rows = conn.execute("SELECT id, staffing_basis FROM staff").fetchall()
    for row in rows:
        raw = row["staffing_basis"]
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            keys = [str(item).strip() for item in parsed if str(item).strip()]
            ratios = equal_split_ratios(keys) if keys else default_ratios
            conn.execute(
                "UPDATE staff SET staffing_basis = ? WHERE id = ?",
                (json.dumps(ratios, ensure_ascii=False), row["id"]),
            )


def _migrate_removed_staffing_basis(conn: sqlite3.Connection) -> None:
    import json

    from data.staffing_basis import (
        REMOVED_STAFFING_BASIS_KEYS,
        equal_split_ratios,
        normalize_staffing_basis_ratios,
    )

    settings_row = conn.execute("SELECT data FROM app_settings WHERE id = 1").fetchone()
    if settings_row:
        try:
            settings = json.loads(settings_row["data"])
        except json.JSONDecodeError:
            settings = {}
        options = settings.get("staffing_basis_options")
        if isinstance(options, list):
            filtered = [
                item
                for item in options
                if isinstance(item, dict)
                and str(item.get("key", "")).strip() not in REMOVED_STAFFING_BASIS_KEYS
            ]
            if filtered != options:
                settings["staffing_basis_options"] = filtered
                conn.execute(
                    "UPDATE app_settings SET data = ? WHERE id = 1",
                    (json.dumps(settings, ensure_ascii=False),),
                )

    rows = conn.execute("SELECT id, staffing_basis FROM staff").fetchall()
    for row in rows:
        raw = row["staffing_basis"]
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict):
            continue
        cleaned = {
            str(key): int(value)
            for key, value in parsed.items()
            if str(key).strip() and str(key).strip() not in REMOVED_STAFFING_BASIS_KEYS
        }
        if not cleaned:
            continue
        if sum(cleaned.values()) != 100:
            cleaned = normalize_staffing_basis_ratios(cleaned)
            if sum(cleaned.values()) != 100:
                cleaned = equal_split_ratios(list(cleaned.keys()))
        if cleaned != parsed:
            conn.execute(
                "UPDATE staff SET staffing_basis = ? WHERE id = ?",
                (json.dumps(cleaned, ensure_ascii=False), row["id"]),
            )


def _migrate_staffing_basis_catalog(conn: sqlite3.Connection) -> None:
    import json

    from data.staffing_basis import DEFAULT_STAFFING_BASIS_CATALOG, REMOVED_STAFFING_BASIS_KEYS

    settings_row = conn.execute("SELECT data FROM app_settings WHERE id = 1").fetchone()
    if not settings_row:
        return
    try:
        settings = json.loads(settings_row["data"])
    except json.JSONDecodeError:
        settings = {}

    options = settings.get("staffing_basis_options")
    if not isinstance(options, list):
        return

    existing_keys = {
        str(item.get("key", "")).strip()
        for item in options
        if isinstance(item, dict) and str(item.get("key", "")).strip()
    }
    updated = False
    for item in DEFAULT_STAFFING_BASIS_CATALOG:
        key = item["key"]
        if key in REMOVED_STAFFING_BASIS_KEYS or key in existing_keys:
            continue
        options.append(dict(item))
        existing_keys.add(key)
        updated = True

    if updated:
        from data.staffing_basis import sort_staffing_basis_options

        settings["staffing_basis_options"] = sort_staffing_basis_options(options)
        conn.execute(
            "UPDATE app_settings SET data = ? WHERE id = 1",
            (json.dumps(settings, ensure_ascii=False),),
        )


def _migrate_staffing_basis_hours(conn: sqlite3.Connection) -> None:
    import json

    from data.staffing_basis import normalize_staffing_basis_option, sort_staffing_basis_options

    settings_row = conn.execute("SELECT data FROM app_settings WHERE id = 1").fetchone()
    if not settings_row:
        return
    try:
        settings = json.loads(settings_row["data"])
    except json.JSONDecodeError:
        settings = {}

    options = settings.get("staffing_basis_options")
    if not isinstance(options, list):
        return

    normalized_options: list[dict] = []
    updated = False
    for item in options:
        if not isinstance(item, dict):
            continue
        normalized = normalize_staffing_basis_option(item)
        if normalized:
            if normalized != item:
                updated = True
            normalized_options.append(normalized)

    if updated and normalized_options:
        settings["staffing_basis_options"] = sort_staffing_basis_options(normalized_options)
        conn.execute(
            "UPDATE app_settings SET data = ? WHERE id = 1",
            (json.dumps(settings, ensure_ascii=False),),
        )


def _migrate_min_staff_by_work_type(conn: sqlite3.Connection) -> None:
    import json

    from data.placement_rules import normalize_min_staff_by_work_type

    settings_row = conn.execute("SELECT data FROM app_settings WHERE id = 1").fetchone()
    if not settings_row:
        return
    try:
        settings = json.loads(settings_row["data"])
    except json.JSONDecodeError:
        settings = {}

    current = settings.get("min_staff_by_work_type")
    normalized = normalize_min_staff_by_work_type(current if isinstance(current, dict) else None, settings)
    if current == normalized:
        return

    settings["min_staff_by_work_type"] = normalized
    conn.execute(
        "UPDATE app_settings SET data = ? WHERE id = 1",
        (json.dumps(settings, ensure_ascii=False),),
    )


def _migrate_min_staff_by_floor(conn: sqlite3.Connection) -> None:
    import json

    from data.placement_rules import normalize_min_staff_by_floor

    settings_row = conn.execute("SELECT data FROM app_settings WHERE id = 1").fetchone()
    if not settings_row:
        return
    try:
        settings = json.loads(settings_row["data"])
    except json.JSONDecodeError:
        settings = {}

    current = settings.get("min_staff_by_floor")
    normalized = normalize_min_staff_by_floor(current if isinstance(current, dict) else None, settings)
    if current == normalized:
        return

    settings["min_staff_by_floor"] = normalized
    conn.execute(
        "UPDATE app_settings SET data = ? WHERE id = 1",
        (json.dumps(settings, ensure_ascii=False),),
    )


def _migrate_staffing_requirement_mode(conn: sqlite3.Connection) -> None:
    import json

    from data.placement_rules import (
        normalize_staffing_requirement_mode,
        normalize_time_slot_staffing_rules,
    )

    settings_row = conn.execute("SELECT data FROM app_settings WHERE id = 1").fetchone()
    if not settings_row:
        return
    try:
        settings = json.loads(settings_row["data"])
    except json.JSONDecodeError:
        settings = {}

    updated = False
    mode = normalize_staffing_requirement_mode(settings.get("staffing_requirement_mode"))
    if settings.get("staffing_requirement_mode") != mode:
        settings["staffing_requirement_mode"] = mode
        updated = True

    rules = normalize_time_slot_staffing_rules(settings.get("time_slot_staffing_rules"))
    if settings.get("time_slot_staffing_rules") != rules:
        settings["time_slot_staffing_rules"] = rules
        updated = True

    if updated:
        conn.execute(
            "UPDATE app_settings SET data = ? WHERE id = 1",
            (json.dumps(settings, ensure_ascii=False),),
        )


def _migrate_shift_source(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(shift_assignments)")}
    if "source" not in columns:
        conn.execute(
            "ALTER TABLE shift_assignments ADD COLUMN source TEXT NOT NULL DEFAULT 'auto'"
        )


def _migrate_departments_to_floors(conn: sqlite3.Connection) -> None:
    from data.masters import LEGACY_DEPARTMENT_TO_FLOOR

    for old_label, floor in LEGACY_DEPARTMENT_TO_FLOOR.items():
        conn.execute(
            "UPDATE staff SET department = ? WHERE department = ?",
            (floor, old_label),
        )
        conn.execute(
            "UPDATE staff_floors SET floor = ? WHERE floor = ?",
            (floor, old_label),
        )


def _staff_seed_floors(row: dict) -> list[str]:
    floors = row.get("departments")
    if floors:
        return list(dict.fromkeys(floors))
    department = row.get("department")
    return [department] if department else []


def _seed_staff_if_empty(conn: sqlite3.Connection) -> None:
    from data.staff_seed import SEED_STAFF

    existing = {row[0] for row in conn.execute("SELECT name FROM staff").fetchall()}
    to_insert = [row for row in SEED_STAFF if row["name"] not in existing]
    if not to_insert:
        return

    for row in to_insert:
        floors = _staff_seed_floors(row)
        primary = floors[0] if floors else row["department"]
        cursor = conn.execute(
            """
            INSERT INTO staff (name, department, job_type, position, can_work_night)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                row["name"],
                primary,
                row["job_type"],
                row["position"],
                int(row["can_work_night"]),
            ),
        )
        staff_id = cursor.lastrowid
        for floor in floors:
            conn.execute(
                "INSERT OR IGNORE INTO staff_floors (staff_id, floor) VALUES (?, ?)",
                (staff_id, floor),
            )


def _sync_seed_staff_floors(conn: sqlite3.Connection) -> None:
    from data.staff_seed import SEED_STAFF

    seed_by_name = {row["name"]: row for row in SEED_STAFF}
    for staff in conn.execute("SELECT id, name, department FROM staff").fetchall():
        seed = seed_by_name.get(staff["name"])
        if not seed:
            continue
        floors = _staff_seed_floors(seed)
        if not floors:
            continue
        for floor in floors:
            conn.execute(
                "INSERT OR IGNORE INTO staff_floors (staff_id, floor) VALUES (?, ?)",
                (staff["id"], floor),
            )
        primary = floors[0]
        if primary and staff["department"] != primary:
            conn.execute(
                "UPDATE staff SET department = ? WHERE id = ?",
                (primary, staff["id"]),
            )


def _sync_seed_staff_night_flags(conn: sqlite3.Connection) -> None:
    """テスト要因: シード定義の夜勤可否を既存レコードへ反映する。"""
    from data.staff_seed import SEED_STAFF

    for row in SEED_STAFF:
        conn.execute(
            "UPDATE staff SET can_work_night = ? WHERE name = ?",
            (int(row["can_work_night"]), row["name"]),
        )
