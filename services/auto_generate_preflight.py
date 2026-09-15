"""自動生成前の確認・矛盾チェック。"""

from __future__ import annotations

from datetime import date

from data.auto_generate_defaults import FACILITY_NIGHT_FLOOR_MINS
from data.night_eligibility import staff_can_be_night_leader, staff_can_work_night
from data.night_staffing_guidance import build_night_staffing_guidance
from data.calendar_period import (
    auto_generate_days,
    clamp_scope_to_period,
    filter_period_days,
    auto_generate_bounds,
    format_scope_range,
    resolve_configured_period_off_days,
)
from data.auto_generate_suggestions import enrich_warnings, unique_suggestions
from data.placement_rules import (
    get_floor_labels,
    normalize_min_staff_by_floor,
    normalize_night_leader_groups,
    normalize_staffing_requirement_mode,
)
from db.settings_repository import get_settings
from db.shift_repository import get_shifts_between
from db.staff_repository import list_staff


def _staff_floors(staff: dict) -> list[str]:
    floors = staff.get("placement_floors") or []
    if floors:
        return list(floors)
    floors = staff.get("departments") or []
    if floors:
        return list(floors)
    department = staff.get("department")
    return [department] if department else []


def _active_staff() -> list[dict]:
    return [staff for staff in list_staff() if not staff.get("exclude_from_staffing")]


def _night_capable(staff_list: list[dict], settings: dict) -> list[dict]:
    if not settings.get("consider_night_eligibility", True):
        return list(staff_list)
    return [staff for staff in staff_list if staff_can_work_night(staff)]


def _night_leaders(staff_list: list[dict]) -> list[dict]:
    return [staff for staff in staff_list if staff_can_be_night_leader(staff)]


def _night_floor_capable(staff_list: list[dict], floor: str, settings: dict) -> list[dict]:
    return [staff for staff in _night_capable(staff_list, settings) if floor in _staff_floors(staff)]


def _count_leave_cells(
    scope_start: date,
    scope_end: date,
    staff_ids: set[int] | None = None,
) -> int:
    cells = get_shifts_between(scope_start, scope_end)
    total = 0
    for (staff_id, _), cell in cells.items():
        if staff_ids is not None and staff_id not in staff_ids:
            continue
        if cell.get("source") == "leave":
            total += 1
    return total


def _normalize_selected_floors(floors: list[str] | None) -> list[str]:
    available = get_floor_labels()
    if not floors:
        return list(available)
    wanted = {str(item).strip() for item in floors if str(item).strip()}
    selected = [floor for floor in available if floor in wanted]
    return selected or list(available)


def _staff_for_floors(staff_list: list[dict], floors: list[str]) -> list[dict]:
    floor_set = set(floors)
    if not floor_set:
        return list(staff_list)
    return [staff for staff in staff_list if set(_staff_floors(staff)) & floor_set]


def build_auto_generate_preflight(
    year: int,
    month: int,
    *,
    scope_start: date | str | None = None,
    scope_end: date | str | None = None,
    floors: list[str] | None = None,
) -> dict:
    settings = get_settings()
    start_day = int(settings.get("calendar_start_day", 1) or 1)
    week_start = settings.get("week_start", "sunday")
    period_start, period_end = auto_generate_bounds(year, month, start_day, week_start=week_start)
    resolved_start, resolved_end = clamp_scope_to_period(
        period_start, period_end, scope_start, scope_end
    )
    scope_days = filter_period_days(
        auto_generate_days(year, month, start_day, week_start=week_start),
        resolved_start,
        resolved_end,
    )
    scope_label = (
        format_scope_range(resolved_start, resolved_end)
        if resolved_start and resolved_end
        else f"{year}年{month}月"
    )

    available_floors = get_floor_labels()
    selected_floors = _normalize_selected_floors(floors)
    staff_list = _staff_for_floors(_active_staff(), selected_floors)
    night_capable = _night_capable(staff_list, settings)
    night_leaders = _night_leaders(night_capable)
    tracked_floors = [floor for floor in selected_floors]
    floor_caps = {
        floor: _night_floor_capable(staff_list, floor, settings) for floor in tracked_floors
    }

    leave_count = 0
    period_days = 0
    if resolved_start and resolved_end:
        leave_count = _count_leave_cells(
            resolved_start,
            resolved_end,
            {staff["id"] for staff in staff_list},
        )
        period_days = len(scope_days) if scope_days else (resolved_end - resolved_start).days + 1

    _, full_off_days, _ = resolve_configured_period_off_days(settings, year, month, start_day)
    full_period_days = len(auto_generate_days(year, month, start_day, week_start=week_start))
    if full_period_days > 0 and period_days < full_period_days:
        off_days = max(0, round(int(full_off_days) * period_days / full_period_days))
    else:
        off_days = full_off_days

    min_by_floor_all = normalize_min_staff_by_floor(settings.get("min_staff_by_floor"), settings)
    min_by_floor = {
        floor: values
        for floor, values in min_by_floor_all.items()
        if floor in selected_floors
    }
    mode = normalize_staffing_requirement_mode(settings.get("staffing_requirement_mode"))
    leader_required = bool(settings.get("require_leader_on_night", True))
    leader_groups = (
        normalize_night_leader_groups(settings.get("night_leader_groups")) if leader_required else []
    )
    if selected_floors and leader_groups:
        selected_set = set(selected_floors)
        leader_groups = [
            {
                **group,
                "floors": [floor for floor in (group.get("floors") or []) if floor in selected_set],
            }
            for group in leader_groups
            if set(group.get("floors") or []) & selected_set
        ]

    night_mins = {
        floor: int((values or {}).get("night") or 0) for floor, values in min_by_floor.items()
    }
    daily_night_slots = sum(night_mins.values())
    period_night_demand = daily_night_slots * period_days if period_days else 0

    max_night_week = int(settings.get("max_night_per_week", 0) or 0)
    max_consecutive = int(settings.get("max_consecutive_days", 0) or 0)
    fairness = settings.get("fairness_mode", "balance")

    advanced_used: list[str] = []
    if max_consecutive and max_consecutive != 5:
        advanced_used.append(f"連続勤務の上限 {max_consecutive} 日")
    if max_night_week not in (0, 2):
        advanced_used.append(f"週の夜勤上限 {max_night_week} 回")
    if mode == "time_slot":
        advanced_used.append("時間帯ごとの必要人数モード")
    if fairness == "balance":
        advanced_used.append("勤務の偏りを抑える")
    if leader_required:
        advanced_used.append("夜勤リーダーを毎日配置")
    if settings.get("consider_night_eligibility", True):
        advanced_used.append("夜勤可否を考慮")
    if set(selected_floors) != set(available_floors):
        advanced_used.append(f"対象フロア: {'、'.join(selected_floors)}")

    night_guidance = build_night_staffing_guidance(
        period_days=period_days,
        night_mins_by_floor=night_mins,
        night_floor_counts={floor: len(people) for floor, people in floor_caps.items()},
        night_capable_count=len(night_capable),
        night_leader_count=len(night_leaders),
        max_night_per_week=max_night_week,
        require_leader_on_night=leader_required,
        night_leader_groups=leader_groups,
    )

    warnings = enrich_warnings(
        _build_warnings(
            settings=settings,
            staff_list=staff_list,
            night_capable=night_capable,
            night_leaders=night_leaders,
            floor_caps=floor_caps,
            night_mins=night_mins,
            period_days=period_days,
            period_night_demand=period_night_demand,
            leave_count=leave_count,
            off_days=off_days,
            leader_required=leader_required,
            max_night_week=max_night_week,
            min_by_floor=min_by_floor,
        )
    )

    return {
        "year": year,
        "month": month,
        "scope_label": scope_label,
        "scope_start": resolved_start.isoformat() if resolved_start else None,
        "scope_end": resolved_end.isoformat() if resolved_end else None,
        "period_start": period_start.isoformat() if period_start else None,
        "period_end": period_end.isoformat() if period_end else None,
        "departments": selected_floors,
        "available_floors": available_floors,
        "selected_floors": selected_floors,
        "staff_count": len(staff_list),
        "leave_count": leave_count,
        "night_capable_count": len(night_capable),
        "night_leader_count": len(night_leaders),
        "night_floor_counts": {floor: len(people) for floor, people in floor_caps.items()},
        "off_days_per_period": off_days,
        "night_mins_by_floor": night_mins,
        "min_staff_by_floor": min_by_floor,
        "daily_night_slots": daily_night_slots,
        "period_night_demand": period_night_demand,
        "staffing_requirement_mode": mode,
        "require_leader_on_night": leader_required,
        "night_leader_groups": leader_groups,
        "max_consecutive_days": max_consecutive,
        "max_night_per_week": max_night_week,
        "fairness_mode": fairness,
        "advanced_settings_used": advanced_used,
        "night_guidance": night_guidance,
        "warnings": warnings,
        "suggestions": unique_suggestions(warnings),
        "can_generate": not any(item.get("blocking") for item in warnings),
        "staff_href": "/staff",
        "settings_auto_href": "/settings?panel=auto",
    }



def _build_warnings(
    *,
    settings: dict,
    staff_list: list[dict],
    night_capable: list[dict],
    night_leaders: list[dict],
    floor_caps: dict[str, list[dict]],
    night_mins: dict[str, int],
    period_days: int,
    period_night_demand: int,
    leave_count: int,
    off_days: int | None,
    leader_required: bool,
    max_night_week: int,
    min_by_floor: dict,
) -> list[dict]:
    warnings: list[dict] = []

    if not staff_list:
        warnings.append(
            {
                "level": "error",
                "code": "no_staff",
                "blocking": True,
                "message": "人員に含める職員が0人です。職員管理で「人員に含めない」を外すか、職員を登録してください。",
            }
        )
        return warnings

    if period_days <= 0:
        warnings.append(
            {
                "level": "error",
                "code": "empty_scope",
                "blocking": True,
                "message": "自動生成の対象日がありません。カレンダーの表示期間を確認してください。",
            }
        )
        return warnings

    for floor, values in min_by_floor.items():
        peak = max((int(values.get(key) or 0) for key in ("early", "day", "late", "night")), default=0)
        available = sum(1 for staff in staff_list if floor in _staff_floors(staff))
        if peak > 0 and available < peak:
            warnings.append(
                {
                    "level": "warn",
                    "code": "floor_capacity_low",
                    "blocking": False,
                    "message": (
                        f"{floor}の必要人数（最大{peak}人/日）に対し、配置可能な職員は{available}人です。"
                        f"職員管理で「配置可能フロア」に{floor}を追加するか、必要人数を減らしてください。"
                    ),
                }
            )

    for floor, need in night_mins.items():
        if need <= 0:
            continue
        capable = floor_caps.get(floor) or []
        if len(capable) < need:
            warnings.append(
                {
                    "level": "error" if floor in FACILITY_NIGHT_FLOOR_MINS and not capable else "warn",
                    "code": "night_floor_short",
                    "blocking": floor in FACILITY_NIGHT_FLOOR_MINS and not capable,
                    "message": (
                        f"{floor}の夜勤必要人数は1日{need}人ですが、{floor}夜勤対応可能者は{len(capable)}人です。"
                        f"職員管理で「夜勤に入れる」をONにし、配置可能フロアに{floor}を含めてください。"
                    ),
                }
            )

    if sum(night_mins.values()) > 0 and not night_capable:
        warnings.append(
            {
                "level": "error",
                "code": "no_night_capable",
                "blocking": True,
                "message": (
                    "夜勤の必要枠がありますが、夜勤可能な職員が登録されていません。"
                    "職員管理で「夜勤に入れる」にチェックを入れてください。"
                ),
            }
        )

    if leader_required and sum(night_mins.values()) > 0:
        if not night_leaders:
            warnings.append(
                {
                    "level": "error",
                    "code": "no_night_leader",
                    "blocking": True,
                    "message": (
                        "夜勤リーダー配置が必須ですが、夜勤リーダー可能者がいません。"
                        "職員管理で「夜勤リーダー可」を追加するか、自動生成設定でリーダー必須をオフにしてください。"
                    ),
                }
            )
        elif len(night_leaders) == 1 and period_days > 14:
            warnings.append(
                {
                    "level": "warn",
                    "code": "few_night_leaders",
                    "blocking": False,
                    "message": (
                        "夜勤リーダー可能者が1名しか登録されていないため、1か月分の夜勤を安定して置けない可能性があります。"
                        "リーダー可能者を追加するか、対象職員の夜勤回数上限を見直してください。"
                    ),
                }
            )

    if period_night_demand > 0 and night_capable and max_night_week > 0:
        weeks = max(1, (period_days + 6) // 7)
        capacity = len(night_capable) * max_night_week * weeks
        if capacity < period_night_demand:
            warnings.append(
                {
                    "level": "warn",
                    "code": "night_cap_insufficient",
                    "blocking": False,
                    "message": (
                        f"期間の夜勤枠は約{period_night_demand}回必要ですが、"
                        f"週あたり夜勤上限{max_night_week}回では最大でも約{capacity}回までです。"
                        "週の夜勤上限を上げるか、夜勤可能者を増やすか、フロアの夜勤必要人数を減らしてください。"
                    ),
                }
            )

    if off_days is not None and period_days > 0 and int(off_days) >= period_days:
        warnings.append(
            {
                "level": "warn",
                "code": "off_days_impossible",
                "blocking": False,
                "message": (
                    f"月間公休数（{off_days}日）が表示期間（{period_days}日）以上です。"
                    "公休数を減らしてください。"
                ),
            }
        )

    if leave_count > len(staff_list) * max(1, period_days // 2):
        warnings.append(
            {
                "level": "warn",
                "code": "many_leave_requests",
                "blocking": False,
                "message": (
                    f"希望休が{leave_count}件あります。希望休が多い日は必要人数を満たせないことがあります。"
                    "該当日は生成後の結果で確認し、必要なら手動で調整してください。"
                ),
            }
        )

    unset_placement = [staff["name"] for staff in staff_list if not _staff_floors(staff)]
    if unset_placement:
        names = "、".join(unset_placement[:5])
        suffix = f" ほか{len(unset_placement) - 5}名" if len(unset_placement) > 5 else ""
        warnings.append(
            {
                "level": "warn",
                "code": "missing_placement_floors",
                "blocking": False,
                "message": (
                    f"配置可能フロアが未設定の職員がいます（{names}{suffix}）。"
                    "職員管理で1Fまたは2Fなど対応フロアを設定してください。"
                ),
            }
        )

    return warnings
