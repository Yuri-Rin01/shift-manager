"""優先順位付きシフト自動生成。"""

from __future__ import annotations

from data.staffing_basis import base_work_key as resolve_base_work_key

import random
from collections import defaultdict
from datetime import date, timedelta

from data.calendar_period import (
    clamp_scope_to_period,
    filter_period_days,
    auto_generate_bounds,
    auto_generate_days,
    format_month_label,
    format_scope_range,
    period_bounds,
    period_day_count,
)
from data.placement_rules import (
    get_floor_labels,
    normalize_min_staff_by_floor,
    normalize_min_staff_by_work_type,
    normalize_staffing_requirement_mode,
)
from data.time_coverage import (
    get_assignable_work_types,
    get_time_slot_rules,
    rule_segments_on_calendar_day,
    work_types_for_segment,
)
from data.shift_symbols import get_configurable_shift_types, get_shift_symbols, symbol_to_key
from db.settings_repository import get_settings
from db.shift_repository import get_shifts_between, get_placements_between, save_placements
from db.staff_repository import list_staff
from services.morning_off import (
    block_work_after_night_enabled,
    is_morning_off_symbol,
    morning_off_symbol,
)

PRIORITY_ORDER = [
    "手動選択分",
    "希望休",
    "担当フロア",
    "夜勤相性（NGの組み合わせを避ける）",
    "夜勤必要人員（勤務割合）",
    "夜勤回数",
    "公休の確保・均等配置（夜勤明け翌日の公休を含む）",
    "各時間の必要人員数と勤務割合",
    "日勤各割合ごとの配置",
]

LEAVE_KEYS = frozenset({"off", "paid_leave", "half_leave"})
WORK_KEYS = ("early", "day", "late", "night")
DAY_WORK_KEYS = frozenset({"early", "day", "late"})
SEMI_TO_BASE = {
    "semi_early": "early",
    "semi_day": "day",
    "semi_late": "late",
    "semi_night": "night",
}
LEADER_OR_ABOVE_POSITIONS = frozenset(
    {
        "施設長",
        "管理者",
        "主任",
        "リーダー",
        "サブリーダー",
        "院長",
        "副院長",
        "部長",
        "師長",
    }
)


def _warning(level: str, code: str, message: str, *, staff_ids=None, dates=None) -> dict:
    return {"level": level, "code": code, "message": message, "staff_ids": staff_ids or [], "dates": dates or []}


def _base_work_key(key: str, settings: dict | None = None) -> str:
    return resolve_base_work_key(key, settings)


def _symbol_work_key(symbol: str, settings: dict) -> str | None:
    key = symbol_to_key(symbol, settings)
    if not key:
        return None
    return _base_work_key(key, settings)


def _enabled_work_keys(settings: dict) -> list[str]:
    enabled = {_base_work_key(item["key"], settings) for item in get_configurable_shift_types(settings)}
    return [key for key in WORK_KEYS if key in enabled]


def _symbol_map(settings: dict) -> dict[str, str]:
    symbols = get_shift_symbols(settings)
    return {key: symbols[key] for key in WORK_KEYS if key in symbols}


def _min_staff_requirements(settings: dict) -> dict[str, dict[str, int]]:
    return normalize_min_staff_by_floor(settings.get("min_staff_by_floor"), settings)


def _legacy_min_staff_totals(settings: dict) -> dict[str, int]:
    mode = normalize_staffing_requirement_mode(settings.get("staffing_requirement_mode"))
    if mode == "time_slot":
        reqs: dict[str, int] = defaultdict(int)
        for rule in settings.get("time_slot_staffing_rules") or []:
            if not isinstance(rule, dict):
                continue
            try:
                count = int(rule.get("min_staff", 0))
            except (TypeError, ValueError):
                continue
            start = str(rule.get("start_time", ""))
            end = str(rule.get("end_time", ""))
            if not start or not end:
                continue
            if end < start or start >= "16:00" or end <= "09:00":
                reqs["night"] = max(reqs["night"], count)
            elif start >= "12:00":
                reqs["late"] = max(reqs["late"], count)
            elif start <= "08:00":
                reqs["early"] = max(reqs["early"], count)
            else:
                reqs["day"] = max(reqs["day"], count)
        return dict(reqs)
    totals: dict[str, int] = defaultdict(int)
    for floor_values in normalize_min_staff_by_floor(settings.get("min_staff_by_floor"), settings).values():
        for key, count in floor_values.items():
            totals[key] = max(totals[key], count)
    if totals:
        return dict(totals)
    return normalize_min_staff_by_work_type(settings.get("min_staff_by_work_type"), settings)


class _Generator:
    def __init__(
        self,
        year: int,
        month: int,
        settings: dict,
        *,
        scope_start=None,
        scope_end=None,
        floors=None,
        staff_members: list[dict] | None = None,
    ):
        self.year = year
        self.month = month
        self.settings = settings
        self.start_day = settings.get("calendar_start_day", 1)
        self.period_start, self.period_end = period_bounds(year, month, self.start_day)
        week_start = settings.get("week_start", "sunday")
        full_days = auto_generate_days(year, month, self.start_day, week_start=week_start)
        self.full_period_days = period_day_count(year, month, self.start_day)
        full_start, full_end = period_bounds(year, month, self.start_day)
        resolved_start, resolved_end = clamp_scope_to_period(
            full_start, full_end, scope_start, scope_end
        )
        self.period_days = filter_period_days(full_days, resolved_start, resolved_end)
        if resolved_start and resolved_end:
            self.period_start, self.period_end = resolved_start, resolved_end
        self.period_dates = [item["date"] for item in self.period_days]
        self.date_index = {d: i for i, d in enumerate(self.period_dates)}

        self.symbols = _symbol_map(settings)
        self.off_symbol = get_shift_symbols(settings)["off"]
        self.work_keys = _enabled_work_keys(settings)
        self.min_staff_by_floor = _min_staff_requirements(settings)
        self.floors = get_floor_labels()
        self.min_staff = _legacy_min_staff_totals(settings)
        self.staffing_mode = normalize_staffing_requirement_mode(settings.get("staffing_requirement_mode"))
        self.time_slot_rules = get_time_slot_rules(settings) if self.staffing_mode == "time_slot" else []
        self.assignable_work_types = (
            get_assignable_work_types(settings) if self.staffing_mode == "time_slot" else []
        )
        available_floors = get_floor_labels()
        if floors:
            wanted = {str(item).strip() for item in floors if str(item).strip()}
            selected = [floor for floor in available_floors if floor in wanted]
            self.floors = selected or list(available_floors)
        else:
            self.floors = list(available_floors)
        if set(self.floors) != set(available_floors):
            self.min_staff_by_floor = {
                floor: values
                for floor, values in self.min_staff_by_floor.items()
                if floor in self.floors
            }
            self.min_staff = {
                key: sum(int((values or {}).get(key, 0) or 0) for values in self.min_staff_by_floor.values())
                for key in ("early", "day", "late", "night")
            }
        floor_set = set(self.floors)

        def _floors_of(staff: dict) -> set[str]:
            vals = staff.get("placement_floors") or staff.get("departments") or []
            if vals:
                return set(vals)
            department = staff.get("department")
            return {department} if department else set()

        source_staff = list_staff() if staff_members is None else staff_members
        self.staff_list = [
            s
            for s in source_staff
            if not s.get("exclude_from_staffing")
            and (not floor_set or _floors_of(s) & floor_set)
        ]
        self.staff_by_id = {s["id"]: s for s in self.staff_list}
        # 保存された選択は片方向でも、同じ夜勤のNGペアとして両方向に適用する。
        # 日勤相性は夜勤にも適用する既存の設定ルールを、古いデータにも反映する。
        self.day_incompatible_by_staff: dict[int, set[int]] = defaultdict(set)
        self.night_incompatible_by_staff: dict[int, set[int]] = defaultdict(set)
        for staff in self.staff_list:
            sid = staff["id"]
            for other_id in staff.get('day_incompatible_ids') or []:
                if other_id != sid and other_id in self.staff_by_id:
                    self.day_incompatible_by_staff[sid].add(other_id)
                    self.day_incompatible_by_staff[other_id].add(sid)
            selected = set(staff.get("night_incompatible_ids") or []) | set(staff.get("day_incompatible_ids") or [])
            for other_id in selected:
                if other_id == sid or other_id not in self.staff_by_id:
                    continue
                self.night_incompatible_by_staff[sid].add(other_id)
                self.night_incompatible_by_staff[other_id].add(sid)

        self.boundary: dict[tuple[int, str], dict] = {}
        self.grid: dict[tuple[int, str], str] = {}
        # Eligibility (staff_floors) is distinct from a single assignment's location.
        self.placements: dict[tuple[int, str], dict] = {}
        self.locks: dict[tuple[int, str], str] = {}
        self.warnings: list[dict] = []

        self.night_counts: dict[int, int] = defaultdict(int)
        self.work_counts: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.week_nights: dict[tuple[int, int], int] = defaultdict(int)
        self.understaffed_shortfalls: list[tuple[str, str, str, int, int]] = []
        self.time_slot_shortfalls: list[tuple[str, str, str, str, str, int, int]] = []
        self._rng = random.Random()

    def _cell_key(self, staff_id: int, shift_date: str) -> tuple[int, str]:
        return staff_id, shift_date

    def _is_locked(self, staff_id: int, shift_date: str) -> bool:
        return self._cell_key(staff_id, shift_date) in self.locks

    def _get_symbol(self, staff_id: int, shift_date: str) -> str | None:
        return self.grid.get(self._cell_key(staff_id, shift_date), self.boundary.get((staff_id, shift_date), {}).get("symbol"))

    def _adjust_counts_for_symbol(
        self,
        staff_id: int,
        shift_date: str,
        symbol: str,
        delta: int,
    ) -> None:
        work_key = _symbol_work_key(symbol, self.settings)
        if work_key == "night":
            self.night_counts[staff_id] += delta
            week = self.period_days[self.date_index[shift_date]]["week_number"]
            self.week_nights[(staff_id, week)] += delta
        if work_key in WORK_KEYS:
            self.work_counts[staff_id][work_key] += delta

    def _clear_auto_night_chain(self, staff_id: int, night_date: str) -> None:
        idx = self.date_index.get(night_date)
        if idx is None:
            return
        if idx + 1 < len(self.period_dates):
            morning_date = self.period_dates[idx + 1]
            if self.locks.get((staff_id, morning_date)) != "manual":
                existing = self._get_symbol(staff_id, morning_date)
                if existing and is_morning_off_symbol(existing, self.settings):
                    key = self._cell_key(staff_id, morning_date)
                    self._adjust_counts_for_symbol(staff_id, morning_date, existing, -1)
                    del self.grid[key]
                    self.locks.pop(key, None)
            if idx + 2 < len(self.period_dates):
                rest_date = self.period_dates[idx + 2]
                if self.locks.get((staff_id, rest_date)) == "rest":
                    key = self._cell_key(staff_id, rest_date)
                    existing = self.grid.get(key)
                    if existing:
                        self._adjust_counts_for_symbol(staff_id, rest_date, existing, -1)
                    del self.grid[key]
                    self.locks.pop(key, None)

    def _clear_auto_morning_off_after_night(self, staff_id: int, night_date: str) -> None:
        self._clear_auto_night_chain(staff_id, night_date)

    def _sync_rest_after_morning_off(self, staff_id: int, morning_off_date: str) -> None:
        """明け翌日を公休で固定し、設定休み日数に含める。"""
        idx = self.date_index.get(morning_off_date)
        if idx is None or idx + 1 >= len(self.period_dates):
            return
        rest_date = self.period_dates[idx + 1]
        if self.locks.get((staff_id, rest_date)) == "manual":
            return
        existing = self._get_symbol(staff_id, rest_date)
        if existing and self.locks.get((staff_id, rest_date)) == "rest":
            return
        if existing:
            existing_key = symbol_to_key(existing, self.settings)
            if existing_key in {"paid_leave", "half_leave"}:
                return
            if existing_key == "off" and self.locks.get((staff_id, rest_date)) != "rest":
                return
            if existing_key not in LEAVE_KEYS and not is_morning_off_symbol(existing, self.settings):
                return
        self.locks.pop((staff_id, rest_date), None)
        self._set_symbol(staff_id, rest_date, self.off_symbol, lock="rest")

    def _sync_morning_off_after_night(self, staff_id: int, night_date: str) -> None:
        morning = morning_off_symbol(self.settings)
        if not morning:
            return
        idx = self.date_index.get(night_date)
        if idx is None or idx + 1 >= len(self.period_dates):
            return
        next_date = self.period_dates[idx + 1]
        if self._is_locked(staff_id, next_date):
            if is_morning_off_symbol(self._get_symbol(staff_id, next_date) or "", self.settings):
                self._sync_rest_after_morning_off(staff_id, next_date)
            return
        existing = self._get_symbol(staff_id, next_date)
        if existing and is_morning_off_symbol(existing, self.settings):
            self._sync_rest_after_morning_off(staff_id, next_date)
            return
        if existing:
            existing_key = symbol_to_key(existing, self.settings)
            if existing_key in {"paid_leave", "half_leave"}:
                return
        self.locks.pop((staff_id, next_date), None)
        self._set_symbol(staff_id, next_date, morning)
        self._sync_rest_after_morning_off(staff_id, next_date)

    def _set_symbol(self, staff_id: int, shift_date: str, symbol: str, lock: str | None = None,
                    *, floor: str | None = None, role: str = 'floor') -> None:
        key = self._cell_key(staff_id, shift_date)
        previous = self.grid.get(key)
        if previous:
            self._adjust_counts_for_symbol(staff_id, shift_date, previous, -1)
            if _symbol_work_key(previous, self.settings) == "night" and _symbol_work_key(symbol, self.settings) != "night":
                self._clear_auto_night_chain(staff_id, shift_date)
        self.grid[key] = symbol
        self.placements.pop(key, None)
        if self._is_work_day_symbol(symbol):
            self.placements[key] = {'role': role, 'floor': '' if role == 'night_leader'
                                    else floor or self._choose_assignment_floor(staff_id, shift_date)}
        if lock:
            self.locks[key] = lock
        elif key in self.locks and self.locks[key] == "rest" and symbol_to_key(symbol, self.settings) != "off":
            self.locks.pop(key, None)
        self._adjust_counts_for_symbol(staff_id, shift_date, symbol, 1)
        if _symbol_work_key(symbol, self.settings) == "night":
            self._sync_morning_off_after_night(staff_id, shift_date)

    def _is_work_day_symbol(self, symbol: str) -> bool:
        key = symbol_to_key(symbol, self.settings)
        if not key or key in LEAVE_KEYS or key == "morning_off":
            return False
        return _base_work_key(key, self.settings) in WORK_KEYS

    def _consecutive_work_days_before(self, staff_id: int, shift_date: str) -> int:
        count = 0
        day = date.fromisoformat(shift_date) - timedelta(days=1)
        while self._is_work_day_symbol(self._get_symbol(staff_id, day.isoformat()) or ""):
            count += 1
            day -= timedelta(days=1)
        return count

    def _would_exceed_consecutive(self, staff_id: int, shift_date: str) -> bool:
        max_days = int(self.settings.get("max_consecutive_days", 0))
        if max_days <= 0:
            return False
        count = self._consecutive_work_days_before(staff_id, shift_date) + 1
        day = date.fromisoformat(shift_date) + timedelta(days=1)
        while self._is_work_day_symbol(self._get_symbol(staff_id, day.isoformat()) or ""):
            count += 1
            day += timedelta(days=1)
        return count > max_days

    def _is_leader_or_above(self, staff: dict) -> bool:
        position = (staff.get("position") or "").strip()
        return bool(position) and position in LEADER_OR_ABOVE_POSITIONS

    def _can_lead_floors(self, staff: dict) -> bool:
        """The shared leader must be eligible for all floors requiring night staff."""
        if not self._is_leader_or_above(staff):
            return False
        if self.staffing_mode == 'time_slot':
            required = {f for f in self.floors if self._min_staff_for(f, 'night') > 0}
            required.update(
                r['floor'] for r in self.time_slot_rules if r.get('floor')
                and r.get('min_staff', 0) > 0
                and (r['end_time'] < r['start_time'] or r['start_time'] >= '16:00' or r['end_time'] <= '09:00')
            )
        else:
            required = {f for f in self.floors if self._min_staff_for(f, 'night') > 0}
        return required.issubset(self._staff_floors(staff))

    def _has_leader_on_night(self, shift_date: str) -> bool:
        for (staff_id, shift_day), symbol in self.grid.items():
            if shift_day != shift_date:
                continue
            if _symbol_work_key(symbol, self.settings) != "night":
                continue
            staff = self.staff_by_id.get(staff_id)
            if (staff and self._can_lead_floors(staff)
                    and self.placements.get((staff_id, shift_date), {}).get('role') == 'night_leader'):
                return True
        return False

    def _count_work_on_day(self, shift_date: str, work_key: str, *, floor: str | None = None) -> int:
        return sum(
            1
            for (staff_id, day), symbol in self.grid.items()
            if day == shift_date
            and _symbol_work_key(symbol, self.settings) == work_key
            and (not floor or self._assigned_on_floor(staff_id, shift_date, floor))
        )

    def _assigned_on_floor(self, staff_id: int, shift_date: str, floor: str) -> bool:
        placement = self.placements.get((staff_id, shift_date), {})
        return placement.get('role') == 'floor' and placement.get('floor') == floor

    def _choose_assignment_floor(self, staff_id: int, shift_date: str) -> str:
        staff = self.staff_by_id[staff_id]
        allowed = self._staff_floors(staff)
        floors = [f for f in allowed if f in self.floors] or allowed
        if not floors:
            return ''
        key = _symbol_work_key(self.grid.get((staff_id, shift_date), ''), self.settings)
        def deficit(floor):
            if self.staffing_mode == 'time_slot':
                # Prefer floors with unmet rules this actual shift can cover.
                total = 0
                idx = self.date_index[shift_date]
                for rule in self.time_slot_rules:
                    if rule.get('floor') != floor:
                        continue
                    for start, end, offset in rule_segments_on_calendar_day(rule['start_time'], rule['end_time']):
                        cal_idx = idx - offset
                        if not 0 <= cal_idx < len(self.period_dates):
                            continue
                        day = self.period_dates[cal_idx]
                        if self._staff_covers_segment(staff_id, day, (start, end), offset):
                            count, _ = self._count_segment_staff(day, (start, end), offset, floor=floor)
                            total += max(0, rule['min_staff'] - count)
                return total
            return self._min_staff_for(floor, key) - self._count_work_on_day(shift_date, key, floor=floor)
        return max(floors, key=deficit)

    def _place_fixed_work(self) -> None:
        # Older databases contain symbols but no locations. Allocate those once,
        # placing single-floor staff first so flexible staff can fill other floors.
        cells = sorted(self.grid, key=lambda cell: (cell[1], len(self._staff_floors(self.staff_by_id[cell[0]])), cell[0]))
        for sid, day in cells:
            symbol = self.grid[(sid, day)]
            if not self._is_work_day_symbol(symbol):
                self.placements.pop((sid, day), None)
                continue
            old = self.placements.get((sid, day))
            staff = self.staff_by_id[sid]
            if old and ((old.get('role') == 'floor' and old.get('floor') in self._staff_floors(staff))
                        or (old.get('role') == 'night_leader' and _symbol_work_key(symbol, self.settings) == 'night'
                            and self._is_leader_or_above(staff))):
                continue
            self.placements.pop((sid, day), None)
            leader = (self.settings.get('require_leader_on_night') and _symbol_work_key(symbol, self.settings) == 'night'
                      and self._can_lead_floors(staff) and not self._has_leader_on_night(day))
            self.placements[(sid, day)] = {'role': 'night_leader' if leader else 'floor',
                                           'floor': '' if leader else self._choose_assignment_floor(sid, day)}

    def _phase_night_leaders(self) -> None:
        """Reserve an additional person, never borrow a floor's required worker."""
        if not self.settings.get('require_leader_on_night') or 'night' not in self.work_keys:
            return
        demand = self._period_night_demand() > 0
        for day in self.period_dates:
            if self._has_leader_on_night(day):
                continue
            if not demand and not self._count_work_on_day(day, 'night'):
                continue
            candidates = [s for s in self.staff_list if self._can_lead_floors(s) and self._can_work(s, 'night', day)]
            if candidates:
                staff = max(candidates, key=lambda s: (self._night_quota_priority(s, day), -self.night_counts[s['id']], -s['id']))
                symbol = self._preferred_symbol_for_staff(staff, 'night')
                if symbol:
                    self._set_symbol(staff['id'], day, symbol, role='night_leader')

    def _phase_manual(self, existing: dict[tuple[int, str], dict]) -> int:
        count = 0
        for (staff_id, shift_date), cell in existing.items():
            if shift_date not in self.date_index:
                continue
            if staff_id not in self.staff_by_id:
                continue
            source = cell.get("source", "auto")
            if source not in ("manual", "leave"):
                continue
            symbol = cell["symbol"]
            lock = "manual" if source == "manual" else "leave"
            if source == "manual":
                count += 1
            # 全固定セルを先に読み込む。夜勤連鎖の反映順で希望休を消さない。
            self.grid[(staff_id, shift_date)] = symbol
            self.locks[(staff_id, shift_date)] = lock
            self._adjust_counts_for_symbol(staff_id, shift_date, symbol, 1)
        self._place_fixed_work()
        self._phase_morning_off_after_night()
        return count

    def _scaled_off_days(self, target_off: int) -> int:
        scoped = len(self.period_dates)
        if scoped <= 0:
            return 0
        if scoped >= self.full_period_days:
            return max(0, target_off)
        return max(0, round(target_off * scoped / self.full_period_days))

    def _phase_leave(self) -> int:
        """入力済みの希望休だけを集計。自動の夜勤後公休は希望休に変換しない。"""
        count = 0
        for (sid, d), symbol in list(self.grid.items()):
            if symbol_to_key(symbol, self.settings) in LEAVE_KEYS and self.locks.get((sid, d)) == "leave":
                count += 1
        if not self.settings.get("prioritize_leave_requests", True):
            self.warnings.append(
                _warning("info", "leave_priority_off", "希望休優先がオフのため、休み日数は最低限のみ反映しました。")
            )
        return count

    def _night_incompatible_on_day(self, staff_id: int, shift_date: str) -> bool:
        assigned = {
            other_id
            for (other_id, d), symbol in self.grid.items()
            if d == shift_date and _symbol_work_key(symbol, self.settings) == "night"
        }
        return bool(assigned & self.night_incompatible_by_staff[staff_id])

    def _day_incompatible_on_day(self, staff_id: int, shift_date: str) -> bool:
        assigned = {
            other_id for (other_id, d), symbol in self.grid.items()
            if d == shift_date and other_id != staff_id
            and _symbol_work_key(symbol, self.settings) in DAY_WORK_KEYS
        }
        bad = self.day_incompatible_by_staff[staff_id]
        return bool(assigned & bad)

    def _blocked_after_night(self, staff_id: int, shift_date: str) -> bool:
        """明け（morning_off）の翌日は日勤系を入れない。"""
        if not block_work_after_night_enabled(self.settings):
            return False
        prev_date = (date.fromisoformat(shift_date) - timedelta(days=1)).isoformat()
        prev_symbol = self._get_symbol(staff_id, prev_date) or ""
        return is_morning_off_symbol(prev_symbol, self.settings)

    def _is_unavailable_for_work(self, staff_id: int, shift_date: str) -> bool:
        symbol = self._get_symbol(staff_id, shift_date)
        if not symbol:
            return False
        if is_morning_off_symbol(symbol, self.settings):
            return True
        if self.locks.get((staff_id, shift_date)) == "rest":
            return True
        return False

    def _can_work(self, staff: dict, work_key: str, shift_date: str) -> bool:
        sid = staff["id"]
        if self._is_locked(sid, shift_date):
            return False
        if self._get_symbol(sid, shift_date):
            return False
        if self._would_exceed_consecutive(sid, shift_date):
            return False
        if work_key in DAY_WORK_KEYS and self._day_incompatible_on_day(sid, shift_date):
            return False
        if work_key == "night":
            if not staff.get("can_work_night"):
                return False
            if staff.get("fix_night_shift_count") and staff.get("night_shift_count") is not None:
                if self.night_counts[sid] >= self._configured_night_target(staff):
                    return False
            if self._night_incompatible_on_day(sid, shift_date):
                return False
            max_week = int(self.settings.get("max_night_per_week", 7))
            week = self.period_days[self.date_index[shift_date]]["week_number"]
            if self.week_nights[(sid, week)] >= max_week:
                return False
            idx = self.date_index.get(shift_date)
            if idx is not None:
                prev_date = (date.fromisoformat(shift_date) - timedelta(days=1)).isoformat()
                prev_symbol = self._get_symbol(sid, prev_date)
                if _symbol_work_key(prev_symbol or "", self.settings) == "night":
                    return False
                if is_morning_off_symbol(prev_symbol or "", self.settings):
                    return False
            # 翌日の明け・翌々日の公休まで確保できる夜勤だけを追加する。
            if idx is not None:
                for offset in (1, 2):
                    following_date = (date.fromisoformat(shift_date) + timedelta(days=offset)).isoformat()
                    following = self._get_symbol(sid, following_date)
                    if not following:
                        continue
                    following_key = symbol_to_key(following, self.settings)
                    if offset == 1 and following_key != "morning_off":
                        return False
                    if offset == 2 and following_key not in LEAVE_KEYS:
                        return False
            return True
        if self._blocked_after_night(sid, shift_date):
            return False
        return True

    def _staff_floors(self, staff: dict) -> list[str]:
        floors = staff.get("departments") or []
        if floors:
            return floors
        department = staff.get("department")
        return [department] if department else []

    def _staff_on_floor(self, staff: dict, floor: str | None) -> bool:
        if not floor:
            return True
        return floor in self._staff_floors(staff)

    def _min_staff_for(self, floor: str | None, work_key: str) -> int:
        def total(values: dict) -> int:
            return sum(int(count) for key, count in values.items()
                       if _base_work_key(key, self.settings) == work_key)
        if floor:
            return total(self.min_staff_by_floor.get(floor, {}))
        return max((total(values) for values in self.min_staff_by_floor.values()),
                   default=total(self.min_staff))

    def _floor_score(self, staff: dict, shift_date: str, *, target_floor: str | None = None) -> int:
        floors = self._staff_floors(staff)
        if not floors:
            return 0
        if target_floor:
            return 50 if target_floor in floors else 0
        idx = self.date_index[shift_date]
        target = floors[idx % len(floors)]
        return 10 if target in floors else 0

    def _night_capable_staff(self) -> list[dict]:
        if self.settings.get("consider_night_eligibility", True):
            return [s for s in self.staff_list if s.get("can_work_night")]
        return list(self.staff_list)

    def _period_night_demand(self) -> int:
        """期間中に必要な夜勤割当のおおよその総数。"""
        floor_per_day = sum(self._min_staff_for(floor, "night") for floor in self.floors)
        slot_per_day = 0
        if self.staffing_mode == "time_slot":
            for rule in self.time_slot_rules:
                start = str(rule.get("start_time", ""))
                end = str(rule.get("end_time", ""))
                if not start or not end:
                    continue
                try:
                    count = int(rule.get("min_staff", 0))
                except (TypeError, ValueError):
                    continue
                if end < start or start >= "16:00" or end <= "09:00":
                    slot_per_day += count
        per_day = max(floor_per_day, slot_per_day)
        if per_day and self.settings.get("require_leader_on_night"):
            per_day += 1
        return per_day * len(self.period_dates)

    def _fair_night_cap_per_staff(self) -> int:
        capable = self._night_capable_staff()
        if not capable:
            return 0
        demand = self._period_night_demand()
        if demand <= 0:
            return 0
        return max(1, (demand + len(capable) - 1) // len(capable))

    def _count_available_staff(
        self,
        shift_date: str,
        work_key: str,
        *,
        exclude_ids: set[int] | None = None,
        floor: str | None = None,
    ) -> int:
        exclude_ids = exclude_ids or set()
        return sum(
            1
            for staff in self.staff_list
            if staff["id"] not in exclude_ids
            and self._staff_on_floor(staff, floor)
            and self._can_work(staff, work_key, shift_date)
        )

    def _count_available_for_work_types(
        self,
        shift_date: str,
        work_types: list[dict],
        exclude_ids: set[int],
        *,
        floor: str | None = None,
    ) -> int:
        available: set[int] = set()
        for work_type in work_types:
            base_key = work_type["base_key"]
            for staff in self.staff_list:
                if staff["id"] in exclude_ids:
                    continue
                if not self._staff_on_floor(staff, floor):
                    continue
                if self._can_work(staff, base_key, shift_date):
                    available.add(staff["id"])
        return len(available)

    def _staff_count_on_floor(self, floor: str) -> int:
        return sum(1 for staff in self.staff_list if self._staff_on_floor(staff, floor))

    def _peak_assignments_per_day_time_slot(self) -> int:
        """同一割当日に重なる時間帯ルールの必要人数合計（上限目安）。"""
        peak = 0
        for assign_date in self.period_dates:
            assign_idx = self.date_index[assign_date]
            total = 0
            for rule in self.time_slot_rules:
                try:
                    min_staff = int(rule.get("min_staff", 0))
                except (TypeError, ValueError):
                    continue
                if min_staff <= 0:
                    continue
                start = str(rule.get("start_time", ""))
                end = str(rule.get("end_time", ""))
                if not start or not end:
                    continue
                for _seg_start, _seg_end, assign_offset in rule_segments_on_calendar_day(start, end):
                    if assign_offset != 0:
                        continue
                    cal_idx = assign_idx + assign_offset
                    if cal_idx < 0 or cal_idx >= len(self.period_dates):
                        continue
                    if self.period_dates[cal_idx] == assign_date:
                        total += min_staff
                        break
            peak = max(peak, total)
        return peak

    def _validate_staff_capacity(self) -> None:
        if not self.staff_list:
            return
        staff_count = len(self.staff_list)
        if self.staffing_mode == "time_slot" and self.time_slot_rules:
            by_scope: dict[str, int] = defaultdict(int)
            for rule in self.time_slot_rules:
                floor = str(rule.get("floor", "")).strip()
                try:
                    min_staff = int(rule.get("min_staff", 0))
                except (TypeError, ValueError):
                    continue
                key = floor or "__all__"
                by_scope[key] = max(by_scope[key], min_staff)
            for scope, peak in by_scope.items():
                available = (
                    self._staff_count_on_floor(scope)
                    if scope != "__all__"
                    else staff_count
                )
                if peak > available:
                    label = scope if scope != "__all__" else "施設全体"
                    self.warnings.append(
                        _warning(
                            "warn",
                            "staff_capacity_low",
                            f"{label}の必要人数（最大{peak}人）に対し、配置対象は{available}人です。入れられる分だけ割り当てます。",
                        )
                    )
        else:
            for floor in self.floors:
                peak = max(
                    (
                        int(self._min_staff_for(floor, work_key))
                        for work_key in ("early", "day", "late", "night")
                    ),
                    default=0,
                )
                available = self._staff_count_on_floor(floor)
                if peak > 0 and available < peak:
                    self.warnings.append(
                        _warning(
                            "warn",
                            "staff_capacity_low",
                            f"{floor}の必要人数（最大{peak}人）に対し、担当職員は{available}人です。入れられる分だけ割り当てます。",
                        )
                    )

    def _period_off_target(self) -> int:
        from data.calendar_period import resolve_configured_period_off_days

        _, target_off, _ = resolve_configured_period_off_days(
            self.settings, self.year, self.month, self.start_day
        )
        return self._scaled_off_days(int(target_off))

    def _is_public_off_symbol(self, symbol: str) -> bool:
        return symbol_to_key(symbol, self.settings) == "off"

    def _counts_toward_off_target(self, staff_id: int, shift_date: str) -> bool:
        symbol = self._get_symbol(staff_id, shift_date)
        if not symbol or not self._is_public_off_symbol(symbol):
            return False
        return True

    def _count_off_toward_target(self, staff_id: int) -> int:
        return sum(
            1 for shift_date in self.period_dates if self._counts_toward_off_target(staff_id, shift_date)
        )

    def _off_slots_remaining(self, staff_id: int) -> int:
        return self._period_off_target() - self._count_off_toward_target(staff_id)

    def _distribution_pool(self, staff: dict) -> int:
        """手動勤務も月間目標の内数。有休等だけを公休と別に差し引く。"""
        other_leave = sum(
            1 for day in self.period_dates
            if (symbol := self._get_symbol(staff["id"], day))
            and not self._is_work_day_symbol(symbol)
            and symbol_to_key(symbol, self.settings) not in {"off", "morning_off"}
        )
        return max(0, len(self.period_dates) - self._period_off_target() - other_leave)

    def _day_capacity_for_staff(self, staff: dict) -> int:
        """実際の夜勤・明けを差し引く。明け翌日の公休は二重控除しない。"""
        sid = staff["id"]
        mornings = sum(
            is_morning_off_symbol(self._get_symbol(sid, day) or "", self.settings)
            for day in self.period_dates
        )
        return max(0, self._distribution_pool(staff) - self.night_counts[sid] - mornings)

    def _configured_night_target(self, staff: dict) -> int:
        # 固定値は空き枠数や均等割りの平均値で書き換えない。
        if staff.get("fix_night_shift_count") and staff.get("night_shift_count") is not None:
            return self._scaled_off_days(int(staff["night_shift_count"]))
        if not staff.get("can_work_night") and self.settings.get("consider_night_eligibility", True):
            return 0
        pool = self._distribution_pool(staff)
        if pool <= 0:
            return 0
        basis = staff.get("staffing_basis") or {}
        night_ratio = sum(v for k, v in basis.items() if _base_work_key(k, self.settings) == "night")
        if night_ratio <= 0:
            return 0
        return max(0, round(pool * night_ratio / 100))

    def _night_target(self, staff: dict) -> int:
        configured = self._configured_night_target(staff)
        if staff.get("fix_night_shift_count") and staff.get("night_shift_count") is not None:
            return configured
        if configured <= 0:
            return 0
        fair_cap = self._fair_night_cap_per_staff()
        if fair_cap <= 0:
            return 0
        return min(configured, fair_cap)

    def _expected_work_count(self, staff: dict, work_key: str) -> float:
        if work_key == "night":
            return float(self._night_target(staff))
        basis = staff.get("staffing_basis") or {}
        target_pct = sum(v for k, v in basis.items() if _base_work_key(k, self.settings) == work_key)
        if target_pct <= 0:
            return 0.0
        day_capacity = float(self._day_capacity_for_staff(staff))
        if day_capacity <= 0:
            return 0.0
        non_night_pct = sum(
            v for k, v in basis.items() if _base_work_key(k, self.settings) in DAY_WORK_KEYS
        )
        if non_night_pct <= 0:
            return 0.0
        return day_capacity * target_pct / non_night_pct

    def _actual_work_count(self, staff_id: int, work_key: str) -> int:
        if work_key == "night":
            return self.night_counts[staff_id]
        return self.work_counts[staff_id][work_key]

    def _preferred_symbol_for_staff(self, staff: dict, work_key: str) -> str | None:
        basis = staff.get("staffing_basis") or {}
        best_key: str | None = None
        best_ratio = -1
        for key, pct in basis.items():
            if _base_work_key(key, self.settings) != work_key or pct <= 0:
                continue
            if pct > best_ratio:
                best_ratio = pct
                best_key = key
        if best_key:
            from data.shift_symbols import get_shift_symbols

            return get_shift_symbols(self.settings).get(best_key)
        return self.symbols.get(work_key)

    def _ratio_deficit(self, staff: dict, work_key: str) -> float:
        expected = self._expected_work_count(staff, work_key)
        if expected <= 0:
            return 0.0
        actual = self._actual_work_count(staff["id"], work_key)
        return expected - actual

    def _workload_balance_penalty(self, staff_id: int) -> float:
        """公平性: すでに勤務が多い職員のスコアを下げて偏りを抑える。"""
        if self.settings.get("fairness_mode", "balance") != "balance":
            return 0.0
        total = sum(self.work_counts[staff_id].values()) + self.night_counts[staff_id]
        return total * 1.5

    def _night_quota_priority(self, staff: dict, shift_date: str) -> float:
        """残り回数に対して候補日が少ない職員を先に配置する。"""
        remaining = max(0, self._night_target(staff) - self.night_counts[staff["id"]])
        if not remaining:
            return 0.0
        available = sum(
            self._can_work(staff, "night", day)
            for day in self.period_dates[self.date_index[shift_date]:]
        )
        return 100 * remaining / max(1, available)

    def _pick_staff(
        self,
        shift_date: str,
        work_key: str,
        *,
        floor: str | None = None,
        prefer_night_quota: bool = False,
    ) -> dict | None:
        candidates: list[tuple[float, dict]] = []
        for staff in self.staff_list:
            if floor and not self._staff_on_floor(staff, floor):
                continue
            if not self._can_work(staff, work_key, shift_date):
                continue
            score = 0.0
            score -= len(self._staff_floors(staff)) * 20
            score += self._floor_score(staff, shift_date, target_floor=floor)
            if prefer_night_quota:
                score += self._night_quota_priority(staff, shift_date)
            if work_key == "night" and self.settings.get("require_leader_on_night"):
                if not self._has_leader_on_night(shift_date) and self._is_leader_or_above(staff):
                    score += 1000
            score += self._ratio_deficit(staff, work_key) * 8
            score -= self._workload_balance_penalty(staff["id"])
            score += self._rng.random()
            candidates.append((score, staff))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    def _assign_for_day(
        self,
        shift_date: str,
        work_key: str,
        count: int,
        *,
        floor: str | None = None,
        prefer_night_quota: bool = False,
    ) -> int:
        if work_key not in self.work_keys:
            return 0
        symbol = self.symbols.get(work_key)
        if not symbol:
            return 0
        assigned = 0
        current = self._count_work_on_day(shift_date, work_key, floor=floor)
        available = self._count_available_staff(shift_date, work_key, floor=floor)
        effective_count = min(count, current + available)
        need = max(0, effective_count - current)
        for _ in range(need):
            staff = self._pick_staff(
                shift_date,
                work_key,
                floor=floor,
                prefer_night_quota=prefer_night_quota,
            )
            if staff is None:
                actual = current + assigned
                self.understaffed_shortfalls.append((shift_date, work_key, floor or "", count, actual))
                break
            self._set_symbol(staff["id"], shift_date, symbol, floor=floor)
            assigned += 1
        return assigned

    def _pick_staff_for_work_type(
        self,
        shift_date: str,
        work_type: dict,
        *,
        floor: str | None = None,
        prefer_night_quota: bool = False,
        exclude_ids: set[int] | None = None,
    ) -> dict | None:
        exclude_ids = exclude_ids or set()
        candidates: list[tuple[float, dict]] = []
        base_key = work_type["base_key"]
        for staff in self.staff_list:
            if staff["id"] in exclude_ids:
                continue
            if floor and not self._staff_on_floor(staff, floor):
                continue
            if not self._can_work(staff, base_key, shift_date):
                continue
            score = 0.0
            score -= len(self._staff_floors(staff)) * 20
            score += self._floor_score(staff, shift_date, target_floor=floor)
            if prefer_night_quota:
                score += self._night_quota_priority(staff, shift_date)
            if base_key == "night" and self.settings.get("require_leader_on_night"):
                if not self._has_leader_on_night(shift_date) and self._is_leader_or_above(staff):
                    score += 1000
            score += self._ratio_deficit(staff, base_key) * 8
            score -= self._workload_balance_penalty(staff["id"])
            score += self._rng.random()
            candidates.append((score, staff))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    def _staff_covers_segment(
        self,
        staff_id: int,
        calendar_date: str,
        segment: tuple[int, int],
        assignment_offset: int,
    ) -> bool:
        from datetime import date as date_cls

        from data.time_coverage import work_type_covers_segment

        cal_idx = self.date_index.get(calendar_date)
        if cal_idx is None:
            return False
        assign_idx = cal_idx + assignment_offset
        if assign_idx < 0 or assign_idx >= len(self.period_dates):
            return False
        assign_date = self.period_dates[assign_idx]
        symbol = self._get_symbol(staff_id, assign_date)
        if not symbol or not self._is_work_day_symbol(symbol):
            return False
        key = symbol_to_key(symbol, self.settings)
        if not key:
            return False
        cal = date_cls.fromisoformat(calendar_date)
        for work_type in self.assignable_work_types:
            if work_type["key"] != key:
                continue
            return work_type_covers_segment(work_type, cal, segment, assignment_offset)
        return False

    def _count_segment_staff(
        self,
        calendar_date: str,
        segment: tuple[int, int],
        assignment_offset: int,
        *,
        floor: str | None = None,
    ) -> tuple[int, set[int]]:
        covered: set[int] = set()
        assign_idx = self.date_index[calendar_date] + assignment_offset
        if not 0 <= assign_idx < len(self.period_dates):
            return 0, covered
        assign_date = self.period_dates[assign_idx]
        for staff in self.staff_by_id.values():
            if floor and not self._assigned_on_floor(staff['id'], assign_date, floor):
                continue
            if self._staff_covers_segment(staff["id"], calendar_date, segment, assignment_offset):
                covered.add(staff["id"])
        return len(covered), covered

    def _phase_time_slot_staffing(self, *, night_only: bool = False) -> None:
        if not self.time_slot_rules or not self.assignable_work_types:
            self.warnings.append(
                _warning(
                    "warn",
                    "time_slot_rules_empty",
                    "時間帯ごとの必要人数が未設定のため、時間帯配置をスキップしました。",
                )
            )
            return

        from datetime import date as date_cls

        slot_tasks: list[tuple[str, date_cls, dict, str, tuple[int, int], int]] = []
        for calendar_date in self.period_dates:
            cal = date_cls.fromisoformat(calendar_date)
            for rule in self.time_slot_rules:
                min_staff = int(rule.get("min_staff", 0))
                if min_staff <= 0:
                    continue
                label = str(rule.get("label", "")).strip() or f"{rule['start_time']}〜{rule['end_time']}"
                for seg_start, seg_end, assign_offset in rule_segments_on_calendar_day(
                    rule["start_time"], rule["end_time"]
                ):
                    slot_tasks.append(
                        (calendar_date, cal, rule, label, (seg_start, seg_end), assign_offset)
                    )
        # 夜勤帯の前日割当（offset -1）を先に処理し、翌日の日勤配置との競合を防ぐ
        slot_tasks.sort(key=lambda item: (item[5], item[0]))

        for calendar_date, cal, rule, label, segment, assign_offset in slot_tasks:
            min_staff = int(rule.get("min_staff", 0))
            if min_staff <= 0:
                continue
            floor = str(rule.get("floor", "")).strip() or None
            cal_idx = self.date_index[calendar_date]
            assign_idx = cal_idx + assign_offset
            if assign_idx < 0 or assign_idx >= len(self.period_dates):
                continue
            assign_date = self.period_dates[assign_idx]
            count, covered = self._count_segment_staff(
                calendar_date,
                segment,
                assign_offset,
                floor=floor,
            )
            candidates = work_types_for_segment(
                self.assignable_work_types,
                cal,
                segment,
                assign_offset,
            )
            if night_only and (not candidates or candidates[0]["base_key"] != "night"):
                continue
            candidates = [
                item for item in candidates
                if (item["base_key"] == "night") == night_only
            ]
            available = self._count_available_for_work_types(
                assign_date,
                candidates,
                covered,
                floor=floor,
            )
            target = min(min_staff, count + available)
            while count < target:
                if not candidates:
                    break
                assigned = False
                for work_type in candidates:
                    staff = self._pick_staff_for_work_type(
                        assign_date,
                        work_type,
                        floor=floor,
                        prefer_night_quota=work_type["base_key"] == "night",
                        exclude_ids=covered,
                    )
                    if staff is None:
                        continue
                    self._set_symbol(staff["id"], assign_date, work_type["symbol"], floor=floor)
                    covered.add(staff["id"])
                    count += 1
                    assigned = True
                    break
                if not assigned:
                    if count < min_staff:
                        self.time_slot_shortfalls.append(
                            (
                                calendar_date,
                                label,
                                rule["start_time"],
                                rule["end_time"],
                                floor or "",
                                min_staff,
                                count,
                            )
                        )
                    break

        if night_only:
            self._phase_night_assignments()

    def _emit_understaffed_warnings(self) -> None:
        if self.time_slot_shortfalls:
            by_rule: dict[str, list[tuple[str, int, int]]] = defaultdict(list)
            for calendar_date, label, start, end, floor, required, actual in self.time_slot_shortfalls:
                key = f"{floor}|{label}|{start}|{end}"
                by_rule[key].append((calendar_date, required, actual))
            for key, rows in sorted(by_rule.items()):
                floor, label, start, end = key.split("|", 3)
                time_label = f"{start}〜{end}" if end < start else f"{start}〜{end}"
                slot_name = label if label else time_label
                floor_label = f"{floor} " if floor else ""
                dates = "、".join(row[0] for row in rows[:8])
                suffix = f" ほか {len(rows) - 8} 日" if len(rows) > 8 else ""
                sample_required = rows[0][1]
                self.warnings.append(
                    _warning(
                        "warn",
                        "time_slot_understaffed",
                        f"{floor_label}「{slot_name}（{time_label}）」が必要人数 {sample_required} 人に足りない日があります（{len(rows)} 日: {dates}{suffix}）。", dates=[r[0] for r in rows],
                    )
                )
            return
        if not self.understaffed_shortfalls:
            return
        labels = {item["key"]: item["label"] for item in get_assignable_work_types(self.settings)}
        by_key: dict[str, list[tuple[str, int, int]]] = defaultdict(list)
        for shift_date, work_key, floor, required, actual in self.understaffed_shortfalls:
            key = f"{floor}|{work_key}"
            by_key[key].append((shift_date, required, actual))
        for key, rows in sorted(by_key.items(), key=lambda item: item[0]):
            floor, work_key = key.split("|", 1)
            label = labels.get(work_key, work_key)
            floor_label = f"{floor} " if floor else ""
            dates = "、".join(row[0] for row in rows[:8])
            suffix = f" ほか {len(rows) - 8} 日" if len(rows) > 8 else ""
            sample_required = rows[0][1]
            self.warnings.append(
                _warning(
                    "warn",
                    "understaffed",
                    f"{floor_label}{label}が必要人数 {sample_required} 人に足りない日があります（{len(rows)} 日: {dates}{suffix}）。", dates=[r[0] for r in rows],
                )
            )

    def _emit_student_labor_warnings(self) -> None:
        blocks = getattr(self, "student_labor_blocks", None) or []
        if not blocks:
            return
        names = list(dict.fromkeys(str(item.get("name") or "留学生") for item in blocks))
        sample = "、".join(names[:5])
        suffix = f" ほか {len(names) - 5}名" if len(names) > 5 else ""
        self.warnings.append(
            _warning(
                "warn",
                "student_labor_limit",
                f"留学生の労働時間制限により必要人数を満たせません（{sample}{suffix}）。",
                staff_ids=[
                    int(item["staff_id"])
                    for item in blocks
                    if item.get("staff_id") is not None
                ],
            )
        )

    def _staff_needs_night_on_day(self, staff: dict, shift_date: str) -> bool:
        for floor in self._staff_floors(staff):
            min_night = self._min_staff_for(floor, "night")
            if min_night > 0 and self._count_work_on_day(shift_date, "night", floor=floor) < min_night:
                return True
        return False

    def _phase_night_assignments(self) -> None:
        """固定回数を上限として、日付・フロアごとの夜勤必要人数を配置。"""
        if "night" not in self.work_keys:
            return
        for shift_date in self.period_dates:
            for floor in self.floors:
                min_night = self._min_staff_for(floor, "night")
                if min_night <= 0:
                    continue
                self._assign_for_day(
                    shift_date,
                    "night",
                    min_night,
                    floor=floor,
                    prefer_night_quota=True,
                )

    def _phase_fixed_night_quotas(self) -> None:
        """必要人数の配置後、指定された固定回数の不足を補う。"""
        if "night" not in self.work_keys:
            return
        staff_order = [
            s for s in self.staff_list
            if s.get("fix_night_shift_count") and s.get("night_shift_count") is not None
        ]
        self._rng.shuffle(staff_order)
        staff_order.sort(key=lambda s: sum(self._can_work(s, "night", d) for d in self.period_dates)
                         - max(0, self._night_target(s) - self.night_counts[s["id"]]))
        for staff in staff_order:
            sid = staff["id"]
            symbol = self._preferred_symbol_for_staff(staff, "night")
            if not symbol:
                continue
            for day in self._fixed_night_dates(staff):
                self._set_symbol(sid, day, symbol)

    def _fixed_night_dates(self, staff: dict) -> list[str]:
        """週上限と3日連鎖を同時に満たす追加日を選ぶ。先着順で枠を潰さない。"""
        sid = staff["id"]
        remaining = max(0, self._night_target(staff) - self.night_counts[sid])
        if not remaining:
            return []
        candidates = [day for day in self.period_dates if self._can_work(staff, "night", day)]
        if not candidates:
            return []
        costs = {
            day: -10000 * self._staff_needs_night_on_day(staff, day)
            + 8 * self._count_work_on_day(day, "night") + self._rng.random()
            for day in candidates
        }
        max_week = int(self.settings.get("max_night_per_week", 7))
        # 状態 = (追加回数, 最後の夜勤からの日数, この週の追加回数)。
        states: dict[tuple[int, int, int], tuple[float, list[str]]] = {(0, 2, 0): (0.0, [])}
        previous_week = None
        for info in self.period_days:
            day, week = info["date"], info["week_number"]
            fixed_night = _symbol_work_key(self._get_symbol(sid, day) or "", self.settings) == "night"
            following: dict[tuple[int, int, int], tuple[float, list[str]]] = {}

            def keep(key: tuple[int, int, int], cost: float, days: list[str]) -> None:
                if key not in following or cost < following[key][0]:
                    following[key] = (cost, days)

            for (added, gap, week_added), (cost, days) in states.items():
                if previous_week != week:
                    week_added = 0
                if fixed_night:
                    keep((added, 0, week_added), cost, days)
                else:
                    keep((added, gap + 1, week_added), cost + 2 * gap + 1, days)
                if (day in costs and added < remaining and gap >= 2
                        and self.week_nights[(sid, week)] + week_added < max_week):
                    keep((added + 1, 0, week_added + 1), cost + costs[day], [*days, day])
            states = following
            previous_week = week
        _, (_, selected) = min(states.items(), key=lambda item: (-item[0][0], item[1][0]))
        return selected

    def _phase_variant_staffing(self, *, night_only: bool) -> None:
        """追加勤務・準勤務の必要人数をその勤務記号で確保する。"""
        variants = [item for item in get_assignable_work_types(self.settings)
                    if item["key"] not in WORK_KEYS
                    and (item["base_key"] == "night") == night_only]
        for work_type in variants:
            for floor in self.floors:
                required = self.min_staff_by_floor.get(floor, {}).get(work_type["key"], 0)
                for day in self.period_dates:
                    actual = sum(
                        symbol_to_key(self._get_symbol(staff["id"], day) or "", self.settings) == work_type["key"]
                        for staff in self.staff_by_id.values() if self._assigned_on_floor(staff['id'], day, floor)
                    )
                    for _ in range(max(0, required - actual)):
                        staff = self._pick_staff_for_work_type(day, work_type, floor=floor,
                                                             prefer_night_quota=night_only)
                        if staff is None:
                            break
                        self._set_symbol(staff["id"], day, work_type["symbol"], floor=floor)

    def _phase_coverage_and_basis(self) -> None:
        for floor in self.floors:
            for work_key in ("early", "day", "late"):
                min_count = self._min_staff_for(floor, work_key)
                if min_count <= 0:
                    continue
                for shift_date in self.period_dates:
                    self._assign_for_day(shift_date, work_key, min_count, floor=floor)

    def _phase_capacity_day_assign(self) -> None:
        """公休確保後の空き枠を、勤務割合の不足が大きい区分から埋める。"""
        work_order = [k for k in ("early", "day", "late") if k in self.work_keys]
        if not work_order:
            return
        staff_order = list(self.staff_list)
        self._rng.shuffle(staff_order)
        for staff in staff_order:
            sid = staff["id"]
            for shift_date in self.period_dates:
                choices = [
                    key for key in work_order
                    if self._expected_work_count(staff, key) > 0
                    and self._can_work(staff, key, shift_date)
                ]
                if not choices:
                    continue
                work_key = max(choices, key=lambda key: self._ratio_deficit(staff, key))
                symbol = self._preferred_symbol_for_staff(staff, work_key)
                if symbol:
                    self._set_symbol(sid, shift_date, symbol)

    def _validate_staff_ratio_results(self) -> None:
        labels = {"early": "早番", "day": "日勤", "late": "遅出", "night": "夜勤"}
        for staff in self.staff_list:
            sid = staff["id"]
            for work_key in WORK_KEYS:
                if work_key == "night" and staff.get("fix_night_shift_count"):
                    continue  # 固定回数の不足・超過は最終結果に対して一度だけ検証する。
                if work_key not in self.work_keys:
                    continue
                expected = self._expected_work_count(staff, work_key)
                if expected < 1:
                    continue
                target = max(1, round(expected))
                actual = self._actual_work_count(sid, work_key)
                if actual >= target:
                    continue
                label = labels.get(work_key, work_key)
                if work_key == "night":
                    reason = "（必要人数・夜勤上限のため）"
                else:
                    reason = "（必要人数・休み・夜勤明けルールのため）"
                self.warnings.append(
                    _warning(
                        "warn",
                        "staff_ratio_shortfall",
                        f"{staff['name']} の{label}は目標 {target} 回に対し {actual} 回です{reason}",
                    )
                )

    def _phase_morning_off_after_night(self) -> None:
        if not morning_off_symbol(self.settings):
            return
        for (staff_id, shift_date), sym in list(self.grid.items()):
            if _symbol_work_key(sym, self.settings) != "night":
                continue
            self._sync_morning_off_after_night(staff_id, shift_date)

    def _phase_exact_off(self) -> int:
        """固定休・明けを含む実日付で間隔を評価し、日勤より先に公休を確保。"""
        count = 0
        staff_order = list(self.staff_list)
        self._rng.shuffle(staff_order)
        for staff in staff_order:
            sid = staff["id"]
            empty_days = [d for d in self.period_dates if not self._get_symbol(sid, d)]
            remaining = min(self._off_slots_remaining(sid), len(empty_days))
            if remaining <= 0:
                continue
            off_costs = {day: self._off_placement_cost(staff, day) for day in empty_days}
            max_days = int(self.settings.get("max_consecutive_days", 0))
            # 状態 = (追加公休数, 連勤長)。区間ごとの連勤長の二乗和を最小化し、
            # 希望休や夜勤明けの近くに公休が固まることを避ける。
            states: dict[tuple[int, int], tuple[float, list[str]]] = {(0, self._consecutive_work_days_before(sid, self.period_dates[0])): (0.0, [])}
            for day in self.period_dates:
                symbol = self._get_symbol(sid, day)
                following: dict[tuple[int, int], tuple[float, list[str]]] = {}
                def keep(key: tuple[int, int], cost: float, days: list[str]) -> None:
                    if key not in following or cost < following[key][0]:
                        following[key] = (cost, days)
                for (off_count, streak), (cost, days) in states.items():
                    if not symbol and off_count < remaining:
                        keep((off_count + 1, 0), cost + off_costs[day], [*days, day])
                    if symbol and not self._is_work_day_symbol(symbol):
                        keep((off_count, 0), cost, days)
                    else:
                        new_streak = streak + 1
                        penalty = 10000 if max_days > 0 and new_streak > max_days else 0
                        keep((off_count, new_streak), cost + 2 * streak + 1 + penalty, days)
                states = following
            _, selected = min(
                (value for (off_count, _), value in states.items() if off_count == remaining),
                key=lambda value: value[0],
            )
            for shift_date in selected:
                self._set_symbol(sid, shift_date, self.off_symbol, lock="off")
                count += 1
        return count

    def _off_placement_cost(self, staff: dict, shift_date: str) -> float:
        """同日の休みの集中と、その公休が増やす配置不足を抑える。"""
        unavailable = sum(
            bool(symbol := self._get_symbol(s["id"], shift_date))
            and not self._is_work_day_symbol(symbol)
            for s in self.staff_list
        )
        cost = unavailable * 8 + self._rng.random()
        if self.staffing_mode == "time_slot":
            requirements: dict[str, int] = defaultdict(int)
            for rule in self.time_slot_rules:
                if rule["end_time"] < rule["start_time"] or rule["start_time"] >= "16:00":
                    continue
                floor = str(rule.get("floor", ""))
                requirements[floor] = max(requirements[floor], int(rule.get("min_staff", 0)))
        else:
            requirements = {
                floor: sum(self._min_staff_for(floor, key) for key in DAY_WORK_KEYS)
                for floor in self.floors
            }
        for floor, required in requirements.items():
            if not self._staff_on_floor(staff, floor or None):
                continue
            available = sum(
                1 for other in self.staff_list
                if other["id"] != staff["id"] and self._staff_on_floor(other, floor or None)
                and (not (symbol := self._get_symbol(other["id"], shift_date))
                     or _symbol_work_key(symbol, self.settings) in DAY_WORK_KEYS)
            )
            if available < required:
                cost += 10000 * (required - available)
        return cost

    def _phase_pad_empty(self) -> int:
        """勤務を配置できなかった空き枠は公休にし、超過を最終検証で報告。"""
        count = 0
        for staff in self.staff_list:
            sid = staff["id"]
            for shift_date in self.period_dates:
                if self._is_locked(sid, shift_date) or self._get_symbol(sid, shift_date):
                    continue
                self._set_symbol(sid, shift_date, self.off_symbol, lock="padding")
                count += 1
        return count

    def _validate_off_exact(self) -> None:
        for staff in self.staff_list:
            sid = staff["id"]
            target = self._period_off_target()
            actual = self._count_off_toward_target(sid)
            if actual == target:
                continue
            if actual < target:
                self.warnings.append(
                    _warning(
                        "warn",
                        "off_count_shortfall",
                        f"{staff['name']} の休みは目標 {target} 日に対し {actual} 日です（必要人数・夜勤明け固定のため）。", staff_ids=[sid],
                    )
                )
            else:
                self.warnings.append(
                    _warning(
                        "warn",
                        "off_count_excess",
                        f"{staff['name']} の公休は設定 {target} 日に対し {actual} 日です（希望休・夜勤明け翌日の公休・勤務を配置できない空き枠を含みます）。", staff_ids=[sid],
                    )
                )

    def _validate_night_results(self) -> None:
        for staff in self.staff_list:
            sid = staff["id"]
            if staff.get("fix_night_shift_count") and staff.get("night_shift_count") is not None:
                target = self._configured_night_target(staff)
                actual = self.night_counts[sid]
                if actual != target:
                    code = "night_count_shortfall" if actual < target else "night_count_excess"
                    reason = "希望休・夜勤相性・配置条件・週の上限・夜勤明けルールを確認してください。" if actual < target else "手動入力分が固定回数を超えています。"
                    self.warnings.append(_warning("warn", code,
                        f"{staff['name']} の夜勤は固定 {target} 回に対し {actual} 回です。{reason}", staff_ids=[sid]))
            for idx, day in enumerate(self.period_dates):
                if _symbol_work_key(self._get_symbol(sid, day) or "", self.settings) != "night":
                    continue
                for offset, allowed in ((1, {"morning_off"}), (2, LEAVE_KEYS)):
                    following = (date.fromisoformat(day) + timedelta(days=offset)).isoformat()
                    saved = self._get_symbol(sid, following)
                    if following not in self.date_index and not saved:
                        continue
                    key = symbol_to_key(saved or "", self.settings)
                    if key not in allowed:
                        self.warnings.append(_warning("warn", "night_chain_conflict",
                            f"{staff['name']} の {day} の夜勤後（{following}）に明け・公休を確保できません。手動入力・希望休を確認してください。", staff_ids=[sid], dates=[day]))

    def _validate_night_compatibility(self) -> None:
        """手動入力で残ったNGペアも、日付と双方の名前を付けて報告する。"""
        conflicts: dict[tuple[int, int], list[str]] = defaultdict(list)
        for day in self.period_dates:
            assigned = {
                sid for sid in self.staff_by_id
                if _symbol_work_key(self._get_symbol(sid, day) or "", self.settings) == "night"
            }
            for sid in assigned:
                for other_id in assigned & self.night_incompatible_by_staff[sid]:
                    if sid < other_id:
                        conflicts[(sid, other_id)].append(day)
        for (left_id, right_id), days in sorted(conflicts.items()):
            names = f"{self.staff_by_id[left_id]['name']} と {self.staff_by_id[right_id]['name']}"
            dates = "、".join(days[:8])
            suffix = f" ほか {len(days) - 8} 日" if len(days) > 8 else ""
            self.warnings.append(
                _warning(
                    "warn",
                    "night_incompatibility_conflict",
                    f"夜勤相性でNGの {names} が同じ夜勤になっています（{len(days)} 日: {dates}{suffix}）。手動入力・相性設定を確認してください。", staff_ids=[left_id, right_id], dates=days,
                )
            )

    def _collect_staffing_shortfalls(self) -> None:
        """候補人数で必要数を切り下げず、最終的な配置を必要数と比較する。"""
        self.understaffed_shortfalls.clear()
        self.time_slot_shortfalls.clear()
        if self.staffing_mode != "time_slot":
            for day in self.period_dates:
                for floor in self.floors:
                    for key in WORK_KEYS:
                        required = self._min_staff_for(floor, key)
                        actual = self._count_work_on_day(day, key, floor=floor)
                        if actual < required:
                            self.understaffed_shortfalls.append((day, key, floor, required, actual))
            for work_type in get_assignable_work_types(self.settings):
                if work_type["key"] in WORK_KEYS:
                    continue
                for day in self.period_dates:
                    for floor in self.floors:
                        required = self.min_staff_by_floor.get(floor, {}).get(work_type["key"], 0)
                        actual = sum(symbol_to_key(self._get_symbol(staff["id"], day) or "", self.settings) == work_type["key"]
                                     for staff in self.staff_by_id.values() if self._assigned_on_floor(staff['id'], day, floor))
                        if actual < required:
                            self.understaffed_shortfalls.append((day, work_type["key"], floor, required, actual))
            return
        for day in self.period_dates:
            for rule in self.time_slot_rules:
                floor = str(rule.get("floor", ""))
                required = int(rule.get("min_staff", 0))
                for start, end, offset in rule_segments_on_calendar_day(rule["start_time"], rule["end_time"]):
                    if not 0 <= self.date_index[day] + offset < len(self.period_dates):
                        continue
                    actual, _ = self._count_segment_staff(day, (start, end), offset, floor=floor or None)
                    if actual < required:
                        self.time_slot_shortfalls.append((day, str(rule.get("label", "")),
                            rule["start_time"], rule["end_time"], floor, required, actual))
                        break

    def _validate_leader_on_night(self) -> None:
        if not self.settings.get("require_leader_on_night") or "night" not in self.work_keys:
            return
        for shift_date in self.period_dates:
            night_count = self._count_work_on_day(shift_date, "night")
            if night_count <= 0 and self._period_night_demand() <= 0:
                continue
            if self._has_leader_on_night(shift_date):
                continue
            self.warnings.append(
                _warning(
                    "warn",
                    "leader_on_night_missing",
                    f"{shift_date} の夜勤リーダー（フロア担当とは別に1人）を配置できませんでした。役職・担当可能フロア・夜勤回数・相性を確認してください。", dates=[shift_date],
                )
            )

    def _validate_period_limits(self) -> None:
        for staff in self.staff_list:
            sid = staff['id']
            max_days = int(self.settings.get('max_consecutive_days', 0))
            conflicts = [day for day in self.period_dates if self._is_work_day_symbol(self._get_symbol(sid, day) or '')
                         and max_days > 0 and self._would_exceed_consecutive(sid, day)]
            if conflicts:
                self.warnings.append(_warning('warn', 'consecutive_conflict',
                    f"{staff['name']} は固定入力と前後期間の勤務を含めると連勤上限 {max_days} 日を超えています。",
                    staff_ids=[sid], dates=conflicts))
            for week in {item['week_number'] for item in self.period_days}:
                if self.week_nights[(sid, week)] > int(self.settings.get('max_night_per_week', 7)):
                    days = [item['date'] for item in self.period_days if item['week_number'] == week]
                    self.warnings.append(_warning('warn', 'weekly_night_conflict',
                        f"{staff['name']} の {days[0]} を含む週は前後期間・固定入力を含めて夜勤上限を超えています。",
                        staff_ids=[sid], dates=days))

    def _apply_boundary_rest(self) -> None:
        # Outside cells are read-only. Carry their obligations into this period.
        for staff in self.staff_list:
            sid = staff['id']
            for day in self.period_dates[:2]:
                d = date.fromisoformat(day)
                previous = self._get_symbol(sid, (d - timedelta(days=1)).isoformat()) or ''
                earlier = self._get_symbol(sid, (d - timedelta(days=2)).isoformat()) or ''
                required = None
                if _symbol_work_key(previous, self.settings) == 'night':
                    required = morning_off_symbol(self.settings)
                elif is_morning_off_symbol(previous, self.settings) or _symbol_work_key(earlier, self.settings) == 'night':
                    required = self.off_symbol
                if not required:
                    continue
                current = self._get_symbol(sid, day)
                valid = current == required or (required == self.off_symbol and symbol_to_key(current or '', self.settings) in LEAVE_KEYS)
                if self._is_locked(sid, day):
                    if not valid:
                        self.warnings.append(_warning('warn', 'boundary_rest_conflict', f"{staff['name']} {day}: 前期間の夜勤後に必要な明け・休みと固定入力が競合しています。", staff_ids=[sid], dates=[day]))
                else:
                    self._set_symbol(sid, day, required, lock='rest' if required == self.off_symbol else 'boundary')

    def run(self, existing: dict[tuple[int, str], dict], placements: dict | None = None,
            boundary: dict | None = None) -> dict:
        self.boundary = {k: v for k, v in (boundary or {}).items() if k[1] not in self.date_index}
        first = self.period_start
        week_offset = (first.weekday() + (1 if self.settings.get('week_start', 'sunday') == 'sunday' else 0)) % 7
        week_origin = first - timedelta(days=week_offset)
        for (sid, day), cell in self.boundary.items():
            if _symbol_work_key(cell.get('symbol', ''), self.settings) == 'night':
                week = (date.fromisoformat(day) - week_origin).days // 7 + 1
                self.week_nights[(sid, week)] += 1
        self.placements = {key: dict(value) for key, value in (placements or {}).items()
                           if key in existing and existing[key].get('source') in ('manual', 'leave')}
        manual = self._phase_manual(existing)
        self._apply_boundary_rest()
        leave = self._phase_leave()
        self._validate_staff_capacity()
        self._phase_night_leaders()
        if self.staffing_mode == "time_slot":
            self._phase_time_slot_staffing(night_only=True)
        else:
            self._phase_variant_staffing(night_only=True)
        # 夜勤は時間帯モードでもフロア別の固定人数として必ず充足する。
        # 旧データに夜勤時間帯ルールが残っている場合は上の処理結果を数えて重複しない。
        self._phase_night_assignments()
        self._phase_fixed_night_quotas()
        # Quota-only nights also need a separate leader.
        self._phase_night_leaders()
        self._phase_morning_off_after_night()
        self._phase_exact_off()
        if self.staffing_mode == "time_slot":
            self._phase_time_slot_staffing()
        else:
            self._phase_variant_staffing(night_only=False)
            self._phase_coverage_and_basis()
        self._phase_capacity_day_assign()
        self._phase_pad_empty()
        self._validate_period_limits()
        self._validate_off_exact()
        self._validate_night_results()
        self._validate_night_compatibility()
        for day in self.period_dates:
            for sid in self.staff_by_id:
                if _symbol_work_key(self._get_symbol(sid, day) or '', self.settings) in DAY_WORK_KEYS and self._day_incompatible_on_day(sid, day):
                    self.warnings.append(_warning('warn', 'day_incompatibility_conflict',
                        f"{self.staff_by_id[sid]['name']} {day}: 日勤相性でNGの職員と同じ日に固定入力されています。", staff_ids=[sid], dates=[day]))
        self._validate_staff_ratio_results()
        self._validate_leader_on_night()
        self._collect_staffing_shortfalls()
        self._emit_understaffed_warnings()
        self._emit_student_labor_warnings()

        if not self.staff_list:
            self.warnings.append(_warning("error", "no_staff", "人員に含める職員が0人です。"))
        if not self.period_dates:
            self.warnings.append(
                _warning("error", "empty_scope", "自動生成の対象日がありません。")
            )

        generated = len(self.grid) - manual
        return {
            "stats": {
                "period_days": len(self.period_dates),
                "full_period_days": self.full_period_days,
                "scope_start": self.period_dates[0] if self.period_dates else None,
                "scope_end": self.period_dates[-1] if self.period_dates else None,
                "scope_label": format_scope_range(self.period_start, self.period_end),
                "staff_count": len(self.staff_list),
                "manual_locked": manual,
                "leave_locked": leave,
                "generated_cells": max(0, generated),
                "night_assignments": sum(
                    1
                    for sym in self.grid.values()
                    if _symbol_work_key(sym, self.settings) == "night"
                ),
            },
            "warnings": self.warnings,
            "placements": [dict(staff_id=sid, date=day, **value)
                           for (sid, day), value in sorted(self.placements.items())
                           if self._is_work_day_symbol(self.grid.get((sid, day), ''))],
            "assignments": [
                (staff_id, shift_date, symbol, self._assignment_source(staff_id, shift_date))
                for (staff_id, shift_date), symbol in self.grid.items()
            ],
        }

    def _assignment_source(self, staff_id: int, shift_date: str) -> str:
        lock = self.locks.get((staff_id, shift_date))
        if lock == "manual":
            return "manual"
        if lock == "leave":
            return "leave"
        return "auto"


def generate_shifts(
    year: int,
    month: int,
    *,
    preview: bool = False,
    scope_start=None,
    scope_end=None,
    floors=None,
) -> dict:
    settings = get_settings()
    start_day = settings.get("calendar_start_day", 1)
    week_start = settings.get("week_start", "sunday")
    period_start, period_end = auto_generate_bounds(
        year, month, start_day, week_start=week_start
    )
    scope_start, scope_end = clamp_scope_to_period(
        period_start, period_end, scope_start, scope_end
    )
    scope_days = filter_period_days(
        auto_generate_days(year, month, start_day, week_start=week_start),
        scope_start,
        scope_end,
    )

    if scope_start is None or scope_end is None:
        return {
            "year": year,
            "month": month,
            "preview": preview,
            "applied": False,
            "stats": {
                "period_days": 0,
                "full_period_days": period_day_count(year, month, start_day),
                "scope_start": None,
                "scope_end": None,
                "scope_label": format_month_label(year, month, start_day),
                "staff_count": 0,
                "manual_locked": 0,
                "leave_locked": 0,
                "generated_cells": 0,
                "night_assignments": 0,
            },
            "warnings": [
                _warning(
                    "error",
                    "empty_scope",
                    f"表示期間に自動生成できる日がありません。",
                )
            ],
            "priority_order": PRIORITY_ORDER,
            "scope_day_count": 0,
            "ok": False,
            "save_error": None,
        }

    existing = get_shifts_between(scope_start, scope_end)
    if not preview:
        existing = {
            key: cell
            for key, cell in existing.items()
            if cell.get("source") in ("manual", "leave")
        }

    engine = _Generator(
        year,
        month,
        settings,
        scope_start=scope_start,
        scope_end=scope_end,
        floors=floors,
    )
    result = engine.run(existing, get_placements_between(scope_start, scope_end),
                        get_shifts_between(scope_start - timedelta(days=14), scope_end + timedelta(days=14)))

    applied = False
    save_error: str | None = None
    if not preview and result["assignments"]:
        try:
            staff_ids = [staff["id"] for staff in engine.staff_list]
            available = get_floor_labels()
            selected = list(engine.floors)
            from db.database import get_connection
            with get_connection() as conn:
                conn.execute('BEGIN IMMEDIATE')
                if floors is not None and set(selected) != set(available):
                    placeholders = ",".join("?" for _ in staff_ids)
                    if staff_ids:
                        conn.execute(
                            f"DELETE FROM shift_assignments WHERE shift_date BETWEEN ? AND ? "
                            f"AND staff_id IN ({placeholders})",
                            (scope_start.isoformat(), scope_end.isoformat(), *staff_ids),
                        )
                else:
                    conn.execute(
                        "DELETE FROM shift_assignments WHERE shift_date BETWEEN ? AND ?",
                        (scope_start.isoformat(), scope_end.isoformat()),
                    )
                conn.executemany('INSERT INTO shift_assignments(staff_id,shift_date,symbol,source) VALUES (?,?,?,?)',
                                 result['assignments'])
                save_placements(conn, result['placements'])
            applied = True
        except Exception as exc:
            save_error = str(exc)
            result["warnings"].append(
                _warning(
                    "error",
                    "save_failed",
                    f"生成結果の保存に失敗しました: {exc}",
                )
            )

    error_count = sum(1 for item in result["warnings"] if item["level"] == "error")

    return {
        "year": year,
        "month": month,
        "preview": preview,
        "applied": applied,
        "ok": applied and error_count == 0,
        "stats": result["stats"],
        "warnings": result["warnings"],
        "priority_order": PRIORITY_ORDER,
        "scope_day_count": len(scope_days),
        "save_error": save_error,
    }
