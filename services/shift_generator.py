"""優先順位付きシフト自動生成。"""

from __future__ import annotations

import random
from collections import defaultdict
from datetime import date

from data.calendar_period import (
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
from db.shift_repository import bulk_upsert_shifts, delete_shifts_between, get_shifts_between
from db.staff_repository import list_staff
from services.morning_off import (
    block_work_after_night_enabled,
    is_morning_off_symbol,
    morning_off_symbol,
)

PRIORITY_ORDER = [
    "手動選択分",
    "希望休",
    "配置可能フロア",
    "夜勤必要人員（固定回数）",
    "夜勤回数",
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
def _warning(level: str, code: str, message: str) -> dict:
    from data.auto_generate_suggestions import enrich_warning

    return enrich_warning({"level": level, "code": code, "message": message})


def build_generate_result_summary(warnings: list[dict], stats: dict) -> dict:
    """生成結果を画面用に分類する（警告コードはそのまま保持）。"""
    from data.auto_generate_suggestions import enrich_warnings, unique_suggestions

    warnings = enrich_warnings(warnings)
    understaffed: list[str] = []
    unfilled_days: list[str] = []
    unmet_preferences: list[str] = []
    night_imbalance: list[str] = []
    off_imbalance: list[str] = []
    leader_issues: list[str] = []
    fix_needed: list[str] = []
    info: list[str] = []

    for item in warnings:
        level = item.get("level") or "info"
        code = item.get("code") or ""
        message = item.get("message") or ""
        suggestion = (item.get("suggestion") or "").strip()
        display = f"{message} → {suggestion}" if suggestion else message
        if level == "error":
            fix_needed.append(display)
            continue
        if code in {"understaffed", "time_slot_understaffed", "staff_capacity_low"}:
            understaffed.append(display)
            fix_needed.append(display)
        elif code in {"empty_cells_unfilled"}:
            unfilled_days.append(display)
            fix_needed.append(display)
        elif code in {"leader_on_night_missing"}:
            leader_issues.append(display)
            fix_needed.append(display)
        elif code in {"night_count_shortfall", "night_quota_capped"}:
            night_imbalance.append(display)
        elif code in {"off_count_shortfall", "off_count_excess"}:
            off_imbalance.append(display)
        elif code in {"staff_ratio_shortfall", "leave_priority_off"}:
            unmet_preferences.append(display)
        elif level == "info":
            info.append(message)
        else:
            unmet_preferences.append(display)

    return {
        "placed_cells": int(stats.get("generated_cells") or 0),
        "leave_kept": int(stats.get("leave_locked") or 0),
        "manual_kept": int(stats.get("manual_locked") or 0),
        "understaffed": understaffed,
        "unfilled_days": unfilled_days,
        "unmet_preferences": unmet_preferences,
        "night_imbalance": night_imbalance,
        "off_imbalance": off_imbalance,
        "leader_issues": leader_issues,
        "fix_needed": fix_needed,
        "info": info,
        "suggestions": unique_suggestions(warnings),
    }


def _base_work_key(key: str) -> str:
    return SEMI_TO_BASE.get(key, key)


def _symbol_work_key(symbol: str, settings: dict) -> str | None:
    key = symbol_to_key(symbol, settings)
    if not key:
        return None
    return _base_work_key(key)


def _enabled_work_keys(settings: dict) -> list[str]:
    enabled = {item["key"] for item in get_configurable_shift_types(settings)}
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
        # 夜勤は人数固定の別枠（フロア別 min_staff）から取る
        for floor_values in normalize_min_staff_by_floor(settings.get("min_staff_by_floor"), settings).values():
            reqs["night"] = max(reqs["night"], int(floor_values.get("night", 0)))
        for rule in settings.get("time_slot_staffing_rules") or []:
            if not isinstance(rule, dict):
                continue
            try:
                count = int(rule.get("min_staff", 0))
            except (TypeError, ValueError):
                continue
            start = str(rule.get("start_time", ""))
            end = str(rule.get("end_time", ""))
            if not start or not end or end < start:
                continue
            if start >= "12:00":
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


def _even_spread_dates(period_dates: list[str], count: int, blocked: set[str]) -> list[str]:
    """空き日へ休みを偏りなく均等配置。"""
    if count <= 0:
        return []
    candidates = [d for d in period_dates if d not in blocked]
    if not candidates:
        return []
    if count >= len(candidates):
        return list(candidates)
    step = len(candidates) / count
    return [candidates[int(index * step)] for index in range(count)]


def _random_pick_dates(
    period_dates: list[str],
    count: int,
    blocked: set[str],
    rng: random.Random,
) -> list[str]:
    if count <= 0:
        return []
    candidates = [d for d in period_dates if d not in blocked]
    if not candidates:
        return []
    if count >= len(candidates):
        return list(candidates)
    return rng.sample(candidates, count)


class _Generator:
    def __init__(self, year: int, month: int, settings: dict):
        self.year = year
        self.month = month
        self.settings = settings
        self.start_day = settings.get("calendar_start_day", 1)
        self.period_start, self.period_end = period_bounds(year, month, self.start_day)
        week_start = settings.get("week_start", "sunday")
        self.period_days = auto_generate_days(year, month, self.start_day, week_start=week_start)
        self.full_period_days = period_day_count(year, month, self.start_day)
        self.period_dates = [item["date"] for item in self.period_days]
        self.date_index = {d: i for i, d in enumerate(self.period_dates)}

        self.symbols = _symbol_map(settings)
        self.off_symbol = self.symbols.get("off") or "×"
        self.work_keys = _enabled_work_keys(settings)
        self.min_staff_by_floor = _min_staff_requirements(settings)
        self.floors = get_floor_labels()
        self.min_staff = _legacy_min_staff_totals(settings)
        self.staffing_mode = normalize_staffing_requirement_mode(settings.get("staffing_requirement_mode"))
        self.time_slot_rules = get_time_slot_rules(settings) if self.staffing_mode == "time_slot" else []
        # 時間帯配置は日中区分のみ（夜勤は別枠の _phase_night_assignments）
        if self.staffing_mode == "time_slot":
            self.assignable_work_types = [
                item
                for item in get_assignable_work_types(settings)
                if item.get("base_key") != "night"
            ]
        else:
            self.assignable_work_types = []
        self.staff_list = [s for s in list_staff() if not s.get("exclude_from_staffing")]
        self.staff_by_id = {s["id"]: s for s in self.staff_list}

        self.grid: dict[tuple[int, str], str] = {}
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
        return self.grid.get(self._cell_key(staff_id, shift_date))

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
        """明け翌日を公休（×）で固定。設定休み日数には含めない。"""
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

    def _morning_off_target_date(self, night_date: str) -> str | None:
        morning = morning_off_symbol(self.settings)
        if not morning:
            return None
        idx = self.date_index.get(night_date)
        if idx is None or idx + 1 >= len(self.period_dates):
            return None
        return self.period_dates[idx + 1]

    def _morning_off_blocked_by_leave(self, staff_id: int, night_date: str) -> bool:
        """明け日が希望休・確保済み公休なら夜勤を入れない（公休日数を守る）。"""
        next_date = self._morning_off_target_date(night_date)
        if next_date is None:
            return False
        lock = self.locks.get((staff_id, next_date))
        return lock in ("manual", "leave")

    def _sync_morning_off_after_night(self, staff_id: int, night_date: str) -> None:
        morning = morning_off_symbol(self.settings)
        if not morning:
            return
        next_date = self._morning_off_target_date(night_date)
        if next_date is None:
            return
        # 手動・公休ロックは明けで上書きしない（指定公休日数を維持）
        if self.locks.get((staff_id, next_date)) in ("manual", "leave"):
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

    def _set_symbol(self, staff_id: int, shift_date: str, symbol: str, lock: str | None = None) -> None:
        key = self._cell_key(staff_id, shift_date)
        previous = self.grid.get(key)
        if previous:
            self._adjust_counts_for_symbol(staff_id, shift_date, previous, -1)
            if _symbol_work_key(previous, self.settings) == "night" and _symbol_work_key(symbol, self.settings) != "night":
                self._clear_auto_night_chain(staff_id, shift_date)
        self.grid[key] = symbol
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
        return _base_work_key(key) in WORK_KEYS

    def _consecutive_work_days_before(self, staff_id: int, shift_date: str) -> int:
        idx = self.date_index.get(shift_date)
        if idx is None or idx == 0:
            return 0
        count = 0
        for day_index in range(idx - 1, -1, -1):
            previous_date = self.period_dates[day_index]
            symbol = self._get_symbol(staff_id, previous_date)
            if not symbol or not self._is_work_day_symbol(symbol):
                break
            count += 1
        return count

    def _would_exceed_consecutive(self, staff_id: int, shift_date: str) -> bool:
        max_days = int(self.settings.get("max_consecutive_days", 0))
        if max_days <= 0:
            return False
        return self._consecutive_work_days_before(staff_id, shift_date) + 1 > max_days

    def _can_be_night_leader(self, staff: dict) -> bool:
        """夜勤リーダー可は職員フラグのみ（役職とは独立）。"""
        return bool(staff.get("can_be_night_leader"))

    def _night_leader_groups(self) -> list[dict]:
        from data.placement_rules import normalize_night_leader_groups

        if not self.settings.get("require_leader_on_night"):
            return []
        return normalize_night_leader_groups(self.settings.get("night_leader_groups"))

    def _staff_covers_night_leader_group(self, staff: dict, group: dict) -> bool:
        floors = set(self._staff_floors(staff))
        return bool(floors & set(group.get("floors") or []))

    def _count_night_leaders_for_group(self, shift_date: str, group: dict) -> int:
        count = 0
        for (staff_id, shift_day), symbol in self.grid.items():
            if shift_day != shift_date:
                continue
            if _symbol_work_key(symbol, self.settings) != "night":
                continue
            staff = self.staff_by_id.get(staff_id)
            if not staff or not self._can_be_night_leader(staff):
                continue
            if self._staff_covers_night_leader_group(staff, group):
                count += 1
        return count

    def _night_staff_covers_floors(self, shift_date: str, floors: list[str]) -> bool:
        floor_set = set(floors or [])
        if not floor_set:
            return self._count_work_on_day(shift_date, "night") > 0
        for (staff_id, shift_day), symbol in self.grid.items():
            if shift_day != shift_date:
                continue
            if _symbol_work_key(symbol, self.settings) != "night":
                continue
            staff = self.staff_by_id.get(staff_id)
            if staff and set(self._staff_floors(staff)) & floor_set:
                return True
        return False

    def _night_leader_group_shortfalls(self, shift_date: str) -> list[dict]:
        groups = self._night_leader_groups()
        if not groups:
            # 空グループ＝施設全体でリーダー1人
            night_count = self._count_work_on_day(shift_date, "night")
            if night_count <= 0:
                return []
            if self._has_leader_on_night(shift_date):
                return []
            return [{"label": "施設全体", "floors": list(self.floors), "min_leaders": 1, "actual": 0}]
        shortfalls: list[dict] = []
        for group in groups:
            floors = list(group.get("floors") or [])
            if not self._night_staff_covers_floors(shift_date, floors):
                continue
            actual = self._count_night_leaders_for_group(shift_date, group)
            need = int(group.get("min_leaders", 1))
            if actual < need:
                shortfalls.append({**group, "actual": actual})
        return shortfalls

    def _night_leader_score_bonus(
        self,
        staff: dict,
        shift_date: str,
        *,
        target_floor: str | None = None,
    ) -> float:
        if not self.settings.get("require_leader_on_night") or not self._can_be_night_leader(staff):
            return 0.0
        groups = self._night_leader_groups()
        if not groups:
            if self._count_work_on_day(shift_date, "night") <= 0 and not target_floor:
                return 0.0
            if self._has_leader_on_night(shift_date):
                return 0.0
            return 1000.0

        bonus = 0.0
        for group in groups:
            floors = list(group.get("floors") or [])
            if not self._staff_covers_night_leader_group(staff, group):
                continue
            relevant = self._night_staff_covers_floors(shift_date, floors) or (
                bool(target_floor) and target_floor in floors
            )
            if not relevant:
                # 当日そのグループにまだ夜勤がなく、今埋めているフロアも対象外ならスキップ
                # ただしグループ内のいずれかに夜勤必要人数がある日は、最初の配置からリーダーを優先
                relevant = any(self._min_staff_for(floor, "night") > 0 for floor in floors)
                if target_floor and target_floor not in floors:
                    relevant = False
            if not relevant:
                continue
            actual = self._count_night_leaders_for_group(shift_date, group)
            need = int(group.get("min_leaders", 1))
            if actual < need:
                bonus += 1000.0 * (need - actual)
        return bonus

    def _has_leader_on_night(self, shift_date: str) -> bool:
        for (staff_id, shift_day), symbol in self.grid.items():
            if shift_day != shift_date:
                continue
            if _symbol_work_key(symbol, self.settings) != "night":
                continue
            staff = self.staff_by_id.get(staff_id)
            if staff and self._can_be_night_leader(staff):
                return True
        return False

    def _count_work_on_day(self, shift_date: str, work_key: str, *, floor: str | None = None) -> int:
        return sum(
            1
            for (staff_id, day), symbol in self.grid.items()
            if day == shift_date
            and _symbol_work_key(symbol, self.settings) == work_key
            and self._staff_on_floor(self.staff_by_id.get(staff_id, {}), floor)
        )

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
            self._set_symbol(staff_id, shift_date, symbol, lock=lock)
        return count

    def _scaled_off_days(self, target_off: int) -> int:
        scoped = len(self.period_dates)
        if scoped <= 0:
            return 0
        if scoped >= self.full_period_days:
            return max(0, target_off)
        return max(0, round(target_off * scoped / self.full_period_days))

    def _phase_leave(self) -> int:
        """希望休など既存の休み記号を leave ロック（公休の自動配置は _phase_exact_off）。"""
        count = 0
        for (sid, d), symbol in list(self.grid.items()):
            if symbol_to_key(symbol, self.settings) in LEAVE_KEYS and self.locks.get((sid, d)) != "manual":
                self.locks[(sid, d)] = "leave"
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
        staff = self.staff_by_id[staff_id]
        bad = set(staff.get("night_incompatible_ids") or [])
        return bool(assigned & bad)

    def _day_incompatible_on_day(self, staff_id: int, shift_date: str) -> bool:
        assigned = {
            other_id for (other_id, d) in self.grid if d == shift_date and other_id != staff_id
        }
        staff = self.staff_by_id[staff_id]
        bad = set(staff.get("day_incompatible_ids") or [])
        return bool(assigned & bad)

    def _blocked_after_night(self, staff_id: int, shift_date: str) -> bool:
        """明け（morning_off）の翌日は日勤系を入れない。"""
        if not block_work_after_night_enabled(self.settings):
            return False
        idx = self.date_index.get(shift_date)
        if idx is None or idx == 0:
            return False
        prev_date = self.period_dates[idx - 1]
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
            if self._night_incompatible_on_day(sid, shift_date):
                return False
            if self._morning_off_blocked_by_leave(sid, shift_date):
                return False
            max_week = int(self.settings.get("max_night_per_week", 7))
            week = self.period_days[self.date_index[shift_date]]["week_number"]
            if self.week_nights[(sid, week)] >= max_week:
                return False
            idx = self.date_index.get(shift_date)
            if idx is not None and idx > 0:
                prev_date = self.period_dates[idx - 1]
                prev_symbol = self._get_symbol(sid, prev_date)
                if _symbol_work_key(prev_symbol or "", self.settings) == "night":
                    return False
            return True
        if self._blocked_after_night(sid, shift_date):
            return False
        return True

    def _staff_floors(self, staff: dict) -> list[str]:
        floors = staff.get("placement_floors") or []
        if floors:
            return floors
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
        if floor:
            return int(self.min_staff_by_floor.get(floor, {}).get(work_key, 0))
        return max(
            int(values.get(work_key, 0))
            for values in self.min_staff_by_floor.values()
        ) if self.min_staff_by_floor else int(self.min_staff.get(work_key, 0))

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
        """期間中に必要な夜勤割当のおおよその総数（人数固定の別枠）。"""
        total = 0
        for floor in self.floors:
            per_day = self._min_staff_for(floor, "night")
            total += per_day * len(self.period_dates)
        return total

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
            for floor in self.floors:
                night_need = self._min_staff_for(floor, "night")
                if night_need > 0:
                    by_scope[floor] = max(by_scope.get(floor, 0), night_need)
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
        night_capable = len(self._night_capable_staff())
        demand = self._period_night_demand()
        if demand > 0 and night_capable > 0:
            fair = self._fair_night_cap_per_staff()
            over_fixed = [
                s["name"]
                for s in self._night_capable_staff()
                if s.get("fix_night_shift_count")
                and s.get("night_shift_count") is not None
                and int(s["night_shift_count"]) > fair
            ]
            if over_fixed:
                names = "、".join(over_fixed[:5])
                suffix = f" ほか {len(over_fixed) - 5} 人" if len(over_fixed) > 5 else ""
                self.warnings.append(
                    _warning(
                        "info",
                        "night_quota_capped",
                        f"夜勤の必要数（期間{demand}回）に合わせ、1人あたり最大{fair}回まで割り当てます（{names}{suffix}の固定回数は調整されます）。",
                    )
                )

    def _period_off_target(self, staff_id: int | None = None) -> int:
        from data.calendar_period import resolve_configured_period_off_days

        staff = self.staff_by_id.get(staff_id) if staff_id is not None else None
        if staff is not None and staff.get("off_days_per_period") is not None:
            return self._scaled_off_days(int(staff["off_days_per_period"]))

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
        if self.locks.get((staff_id, shift_date)) in ("rest", "padding"):
            return False
        return True

    def _count_off_toward_target(self, staff_id: int) -> int:
        return sum(
            1 for shift_date in self.period_dates if self._counts_toward_off_target(staff_id, shift_date)
        )

    def _off_slots_remaining(self, staff_id: int) -> int:
        return self._period_off_target(staff_id) - self._count_off_toward_target(staff_id)

    def _slot_a(self, staff_id: int) -> int:
        """A = 表示区間 − 手動マス数"""
        return max(0, len(self.period_dates) - self._manual_cell_count(staff_id))

    def _slot_b(self, staff_id: int) -> int:
        """B = A − 設定休み"""
        return max(0, self._slot_a(staff_id) - self._period_off_target(staff_id))

    def _manual_cell_count(self, staff_id: int) -> int:
        return sum(
            1
            for shift_date in self.period_dates
            if self.locks.get((staff_id, shift_date)) == "manual"
        )

    def _distribution_pool(self, staff: dict) -> int:
        """B = A − 設定休み（夜勤・昼勤の配分対象）"""
        return self._slot_b(staff["id"])

    def _day_capacity_for_staff(self, staff: dict) -> int:
        """D 目標 = B − 夜勤 − 明け − 明け翌日休"""
        night_target = self._night_target(staff)
        return max(0, self._slot_b(staff["id"]) - night_target - (night_target * 2))

    def _configured_night_target(self, staff: dict) -> int:
        """夜勤目標は固定回数のみ（勤務割合からは算出しない）。"""
        if not staff.get("can_work_night") and self.settings.get("consider_night_eligibility", True):
            return 0
        pool = self._distribution_pool(staff)
        if pool <= 0:
            return 0
        if staff.get("fix_night_shift_count") and staff.get("night_shift_count") is not None:
            target = int(staff["night_shift_count"])
            if len(self.period_dates) < self.full_period_days:
                target = self._scaled_off_days(target)
            return max(0, min(target, pool))
        return 0

    def _night_target(self, staff: dict) -> int:
        configured = self._configured_night_target(staff)
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
        target_pct = sum(
            v
            for k, v in basis.items()
            if _base_work_key(k) == work_key and _base_work_key(k) != "night"
        )
        if target_pct <= 0:
            return 0.0
        day_capacity = float(self._day_capacity_for_staff(staff))
        if day_capacity <= 0:
            return 0.0
        non_night_pct = sum(
            v for k, v in basis.items() if _base_work_key(k) in DAY_WORK_KEYS
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
            if _base_work_key(key) != work_key or pct <= 0:
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
            score += self._floor_score(staff, shift_date, target_floor=floor)
            if prefer_night_quota:
                target = self._night_target(staff)
                score += max(0, target - self.night_counts[staff["id"]]) * 5
            if work_key == "night" and self.settings.get("require_leader_on_night"):
                score += self._night_leader_score_bonus(staff, shift_date, target_floor=floor)
            score += self._ratio_deficit(staff, work_key) * 8
            score -= self._workload_balance_penalty(staff["id"])
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
            self._set_symbol(staff["id"], shift_date, symbol)
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
            score += self._floor_score(staff, shift_date, target_floor=floor)
            if prefer_night_quota:
                target = self._night_target(staff)
                score += max(0, target - self.night_counts[staff["id"]]) * 5
            if base_key == "night" and self.settings.get("require_leader_on_night"):
                score += self._night_leader_score_bonus(staff, shift_date, target_floor=floor)
            score += self._ratio_deficit(staff, base_key) * 8
            score -= self._workload_balance_penalty(staff["id"])
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
        for staff in self.staff_list:
            if floor and not self._staff_on_floor(staff, floor):
                continue
            if self._staff_covers_segment(staff["id"], calendar_date, segment, assignment_offset):
                covered.add(staff["id"])
        return len(covered), covered

    def _phase_time_slot_staffing(self) -> None:
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
        # 夜勤帯の前日割当は別枠のため、時間帯タスクは日中のみ
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
                    self._set_symbol(staff["id"], assign_date, work_type["symbol"])
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
                        f"{floor_label}「{slot_name}（{time_label}）」が必要人数 {sample_required} 人に足りない日があります（{len(rows)} 日: {dates}{suffix}）。",
                    )
                )
            return
        if not self.understaffed_shortfalls:
            return
        labels = {"early": "早番", "day": "日勤", "late": "遅出", "night": "夜勤"}
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
                    f"{floor_label}{label}が必要人数 {sample_required} 人に足りない日があります（{len(rows)} 日: {dates}{suffix}）。",
                )
            )

    def _staff_needs_night_on_day(self, staff: dict, shift_date: str) -> bool:
        for floor in self._staff_floors(staff):
            min_night = self._min_staff_for(floor, "night")
            if min_night > 0 and self._count_work_on_day(shift_date, "night", floor=floor) < min_night:
                return True
        return False

    def _phase_night_assignments(self) -> None:
        """夜勤を割当。フロアごとの必要人数を満たすよう、個人目標は枠内でランダム配置。"""
        if "night" not in self.work_keys:
            return
        has_floor_night = any(self._min_staff_for(floor, "night") > 0 for floor in self.floors)
        if not has_floor_night:
            return
        period_demand = self._period_night_demand()
        symbol = self.symbols.get("night")
        if not symbol:
            return

        night_staff = [s for s in self.staff_list if s.get("can_work_night")]
        self._rng.shuffle(night_staff)
        for staff in night_staff:
            target = self._night_target(staff)
            sid = staff["id"]
            candidates = [
                shift_date
                for shift_date in self.period_dates
                if self._can_work(staff, "night", shift_date)
                and self._staff_needs_night_on_day(staff, shift_date)
            ]
            self._rng.shuffle(candidates)
            for shift_date in candidates:
                if self.night_counts[sid] >= target:
                    break
                if period_demand > 0 and sum(self.night_counts.values()) >= period_demand:
                    break
                if not self._can_work(staff, "night", shift_date):
                    continue
                self._set_symbol(sid, shift_date, symbol)
            if staff.get("fix_night_shift_count") and self.night_counts[sid] < target:
                self.warnings.append(
                    _warning(
                        "warn",
                        "night_count_shortfall",
                        f"{staff['name']} の夜勤回数 {target} 回に対し {self.night_counts[sid]} 回しか割当できませんでした。",
                    )
                )

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

    def _phase_coverage_and_basis(self) -> None:
        for floor in self.floors:
            for work_key in ("early", "day", "late"):
                min_count = self._min_staff_for(floor, work_key)
                if min_count <= 0:
                    continue
                for shift_date in self.period_dates:
                    self._assign_for_day(shift_date, work_key, min_count, floor=floor)

    def _phase_capacity_day_assign(self) -> None:
        """枠計算（期間−休み−手動−夜勤−明け）に基づき、昼間勤務をランダム配置。"""
        work_order = [k for k in ("early", "day", "late") if k in self.work_keys]
        if not work_order:
            return
        staff_order = list(self.staff_list)
        self._rng.shuffle(staff_order)
        for staff in staff_order:
            sid = staff["id"]
            for work_key in work_order:
                expected = self._expected_work_count(staff, work_key)
                if expected <= 0:
                    continue
                target = max(0, round(expected))
                deficit = target - self._actual_work_count(sid, work_key)
                if deficit <= 0:
                    continue
                symbol = self._preferred_symbol_for_staff(staff, work_key)
                if not symbol:
                    continue
                candidates = [
                    shift_date
                    for shift_date in self.period_dates
                    if self._can_work(staff, work_key, shift_date)
                ]
                self._rng.shuffle(candidates)
                for shift_date in candidates:
                    if deficit <= 0:
                        break
                    self._set_symbol(sid, shift_date, symbol)
                    deficit -= 1

    def _validate_staff_ratio_results(self) -> None:
        labels = {"early": "早番", "day": "日勤", "late": "遅出", "night": "夜勤"}
        for staff in self.staff_list:
            sid = staff["id"]
            for work_key in WORK_KEYS:
                if work_key not in self.work_keys:
                    continue
                # 夜勤の割合検証は行わない（固定回数のみ）
                if work_key == "night" and not staff.get("fix_night_shift_count"):
                    continue
                expected = self._expected_work_count(staff, work_key)
                if expected < 1:
                    continue
                target = max(1, round(expected))
                actual = self._actual_work_count(sid, work_key)
                if actual >= target:
                    continue
                label = labels.get(work_key, work_key)
                if staff.get("fix_night_shift_count") and work_key == "night":
                    configured = self._configured_night_target(staff)
                    assignable = self._night_target(staff)
                    if configured > assignable:
                        reason = f"（夜勤上限により最大{assignable}回まで。固定{configured}回）"
                    else:
                        reason = "（必要人数・休み・夜勤明けルールのため）"
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
        """設定休み日数ちょうどになるよう公休を均等配置（先に確保して勤務で上書きしない）。"""
        count = 0
        for staff in self.staff_list:
            sid = staff["id"]
            remaining = self._off_slots_remaining(sid)
            if remaining <= 0:
                continue
            blocked = {d for (s, d) in self.grid if s == sid}
            candidates = [
                shift_date
                for shift_date in self.period_dates
                if not self._is_locked(sid, shift_date) and not self._get_symbol(sid, shift_date)
            ]
            for shift_date in _even_spread_dates(candidates, remaining, blocked):
                if self._off_slots_remaining(sid) <= 0:
                    break
                if self._is_locked(sid, shift_date) or self._get_symbol(sid, shift_date):
                    continue
                self._set_symbol(sid, shift_date, self.off_symbol, lock="leave")
                count += 1
        return count

    def _clear_auto_symbol(self, staff_id: int, shift_date: str) -> None:
        """自動配置の記号を削除（手動ロックは触らない）。"""
        key = self._cell_key(staff_id, shift_date)
        if self.locks.get(key) == "manual":
            return
        previous = self.grid.get(key)
        if previous:
            self._adjust_counts_for_symbol(staff_id, shift_date, previous, -1)
            if _symbol_work_key(previous, self.settings) == "night":
                self._clear_auto_night_chain(staff_id, shift_date)
            del self.grid[key]
        self.locks.pop(key, None)

    def _movable_leave_off_dates(self, staff_id: int) -> list[str]:
        """自動確保の公休（移動可能）の日付一覧。"""
        dates: list[str] = []
        for shift_date in self.period_dates:
            if self.locks.get((staff_id, shift_date)) != "leave":
                continue
            if not self._counts_toward_off_target(staff_id, shift_date):
                continue
            dates.append(shift_date)
        return dates

    def _try_assign_day_work(self, staff: dict, shift_date: str, work_order: list[str]) -> bool:
        ranked = sorted(
            work_order,
            key=lambda key: (
                self._ratio_deficit(staff, key),
                -self._workload_balance_penalty(staff["id"]),
            ),
            reverse=True,
        )
        for work_key in ranked:
            if not self._can_work(staff, work_key, shift_date):
                continue
            symbol = self._preferred_symbol_for_staff(staff, work_key)
            if not symbol:
                continue
            self._set_symbol(staff["id"], shift_date, symbol)
            return True
        return False

    def _try_fill_empty_by_relocating_off(
        self,
        staff: dict,
        empty_date: str,
        work_order: list[str],
    ) -> bool:
        """連勤上限などで勤務を入れられない空きに、別日の公休を移して空白を解消する。"""
        sid = staff["id"]
        donors = [d for d in self._movable_leave_off_dates(sid) if d != empty_date]
        if not donors:
            return False

        empty_idx = self.date_index[empty_date]

        def donor_score(donor: str) -> tuple:
            # 空き日に近い公休を優先（連勤の切れ目として自然）
            return (abs(self.date_index[donor] - empty_idx), -self.date_index[donor])

        for donor in sorted(donors, key=donor_score):
            donor_symbol = self._get_symbol(sid, donor)
            donor_lock = self.locks.get((sid, donor))
            # 1) 空きへ公休を移す
            self._clear_auto_symbol(sid, donor)
            self._set_symbol(sid, empty_date, self.off_symbol, lock="leave")
            # 2) 元の公休日を勤務で埋める
            if self._try_assign_day_work(staff, donor, work_order):
                return True
            # 失敗したら元に戻す
            self._clear_auto_symbol(sid, empty_date)
            self._clear_auto_symbol(sid, donor)
            if donor_symbol:
                self._set_symbol(sid, donor, donor_symbol, lock=donor_lock)
        return False

    def _phase_pad_empty(self) -> int:
        """公休確保後の空きセルを昼間勤務で埋める（公休の追加はしない）。連勤上限で入れられない場合は公休を別日へ移して空白を解消する。"""
        count = 0
        work_order = [k for k in ("early", "day", "late") if k in self.work_keys]
        if not work_order:
            return 0
        unfilled: list[str] = []
        for staff in self.staff_list:
            sid = staff["id"]
            for shift_date in self.period_dates:
                if self._is_locked(sid, shift_date) or self._get_symbol(sid, shift_date):
                    continue
                if self._try_assign_day_work(staff, shift_date, work_order):
                    count += 1
                    continue
                # 勤務制約（主に連勤上限）で入れられない → 公休をここに移し、元の公休枠を勤務へ
                if self._try_fill_empty_by_relocating_off(staff, shift_date, work_order):
                    count += 1
                    continue
                unfilled.append(f"{staff['name']}@{shift_date}")
        if unfilled:
            sample = "、".join(unfilled[:8])
            suffix = f" ほか {len(unfilled) - 8} 件" if len(unfilled) > 8 else ""
            self.warnings.append(
                _warning(
                    "warn",
                    "empty_cells_unfilled",
                    f"勤務制約のため埋められなかった空きがあります（{len(unfilled)} 件: {sample}{suffix}）。",
                )
            )
        return count

    def _validate_off_exact(self) -> None:
        for staff in self.staff_list:
            sid = staff["id"]
            target = self._period_off_target(sid)
            actual = self._count_off_toward_target(sid)
            if actual == target:
                continue
            if actual < target:
                self.warnings.append(
                    _warning(
                        "warn",
                        "off_count_shortfall",
                        f"{staff['name']} の休みは目標 {target} 日に対し {actual} 日です（必要人数・夜勤明け固定のため）。",
                    )
                )
            else:
                self.warnings.append(
                    _warning(
                        "warn",
                        "off_count_excess",
                        f"{staff['name']} の休みは目標 {target} 日に対し {actual} 日です（手動入力の休みを含みます）。",
                    )
                )

    def _validate_leader_on_night(self) -> None:
        if not self.settings.get("require_leader_on_night") or "night" not in self.work_keys:
            return
        for shift_date in self.period_dates:
            shortfalls = self._night_leader_group_shortfalls(shift_date)
            for group in shortfalls:
                label = str(group.get("label") or "・".join(group.get("floors") or [])).strip()
                need = int(group.get("min_leaders", 1))
                actual = int(group.get("actual", 0))
                self.warnings.append(
                    _warning(
                        "warn",
                        "leader_on_night_missing",
                        f"{shift_date} の夜勤リーダー（{label}）が不足しています（必要 {need} 人 / 実際 {actual} 人）。",
                    )
                )

    def run(self, existing: dict[tuple[int, str], dict]) -> dict:
        manual = self._phase_manual(existing)
        leave = self._phase_leave()
        self._validate_staff_capacity()
        # 公休を先に指定日数ぶん確保し、残りを勤務配置で埋める
        off_placed = self._phase_exact_off()
        leave += off_placed
        if self.staffing_mode == "time_slot":
            # 夜勤は人数固定の別枠。時間帯ルールは日中帯のみ充足する。
            self._phase_night_assignments()
            self._phase_morning_off_after_night()
            self._phase_time_slot_staffing()
            self._phase_capacity_day_assign()
        else:
            self._phase_night_assignments()
            self._phase_morning_off_after_night()
            self._phase_capacity_day_assign()
            self._phase_coverage_and_basis()
        # 勤務配置後に不足があれば空きへ公休を補充し、それでも残る空きは勤務で埋める
        leave += self._phase_exact_off()
        self._phase_pad_empty()
        self._validate_off_exact()
        self._validate_staff_ratio_results()
        self._validate_leader_on_night()
        self._emit_understaffed_warnings()

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


def generate_shifts(year: int, month: int, *, preview: bool = False) -> dict:
    settings = get_settings()
    start_day = settings.get("calendar_start_day", 1)
    week_start = settings.get("week_start", "sunday")
    scope_start, scope_end = auto_generate_bounds(
        year, month, start_day, week_start=week_start
    )
    scope_days = auto_generate_days(year, month, start_day, week_start=week_start)

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
            "result_summary": build_generate_result_summary(
                [
                    _warning(
                        "error",
                        "empty_scope",
                        "表示期間に自動生成できる日がありません。",
                    )
                ],
                {
                    "generated_cells": 0,
                    "leave_locked": 0,
                    "manual_locked": 0,
                },
            ),
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

    engine = _Generator(year, month, settings)
    result = engine.run(existing)

    applied = False
    save_error: str | None = None
    if not preview and result["assignments"]:
        try:
            delete_shifts_between(scope_start, scope_end)
            bulk_upsert_shifts(result["assignments"])
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
    summary = build_generate_result_summary(result["warnings"], result["stats"])

    return {
        "year": year,
        "month": month,
        "preview": preview,
        "applied": applied,
        "ok": applied and error_count == 0,
        "stats": result["stats"],
        "warnings": result["warnings"],
        "result_summary": summary,
        "priority_order": PRIORITY_ORDER,
        "scope_day_count": len(scope_days),
        "save_error": save_error,
    }
