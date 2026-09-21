"""手動編集後の勤務表ルール確認（自動生成と同じ判定を可能な範囲で再利用）。"""

from __future__ import annotations

from datetime import date, timedelta

from data.calendar_period import period_bounds
from db.settings_repository import get_settings
from db.shift_repository import get_placements_between, get_shifts_between
from db.staff_repository import list_staff
from services.shift_generator import DAY_WORK_KEYS, _Generator, _symbol_work_key, _warning


def _load_engine(year: int, month: int) -> _Generator:
    settings = get_settings()
    start_day = settings.get("calendar_start_day", 1)
    start, end = period_bounds(year, month, start_day)
    # 境界判定用に前後数日も読む
    fetch_start = start - timedelta(days=2)
    fetch_end = end + timedelta(days=2)
    existing = get_shifts_between(fetch_start, fetch_end)
    placements = get_placements_between(fetch_start, fetch_end)
    staff = list_staff()
    engine = _Generator(year, month, settings, staff_members=staff)
    boundary = {
        key: value
        for key, value in existing.items()
        if key[1] not in engine.date_index
    }
    engine.boundary = boundary
    # week_nights を境界分から初期化
    first = engine.period_start
    week_offset = (first.weekday() + (1 if settings.get("week_start", "sunday") == "sunday" else 0)) % 7
    week_origin = first - timedelta(days=week_offset)
    for (sid, day), cell in boundary.items():
        if _symbol_work_key(cell.get("symbol", ""), settings) == "night":
            week = (date.fromisoformat(day) - week_origin).days // 7 + 1
            engine.week_nights[(sid, week)] += 1

    for (sid, day), cell in existing.items():
        if day not in engine.date_index:
            continue
        symbol = cell.get("symbol") or ""
        engine.grid[(sid, day)] = symbol
        source = cell.get("source") or "auto"
        engine.locks[(sid, day)] = source
        work_key = _symbol_work_key(symbol, settings)
        if work_key == "night":
            week = (date.fromisoformat(day) - week_origin).days // 7 + 1
            engine.week_nights[(sid, week)] += 1
            engine.night_counts[sid] += 1
        if work_key in {"early", "day", "late", "night"}:
            engine.work_counts[sid][work_key] += 1

    engine.placements = {
        key: dict(value)
        for key, value in placements.items()
        if key[1] in engine.date_index
    }
    return engine


def validate_period(year: int, month: int, *, focus_dates: list[str] | None = None) -> dict:
    """表示期間の現状を検証し、警告一覧を返す（配置は書き換えない）。"""
    engine = _load_engine(year, month)
    engine.warnings.clear()
    engine._validate_period_limits()
    engine._validate_off_exact()
    engine._validate_night_results()
    engine._validate_night_compatibility()
    for day in engine.period_dates:
        for sid in engine.staff_by_id:
            symbol = engine._get_symbol(sid, day) or ""
            if _symbol_work_key(symbol, engine.settings) in DAY_WORK_KEYS and engine._day_incompatible_on_day(sid, day):
                engine.warnings.append(
                    _warning(
                        "warn",
                        "day_incompatibility_conflict",
                        f"{engine.staff_by_id[sid]['name']} {day}: 日勤相性でNGの職員と同じ日に入っています。",
                        staff_ids=[sid],
                        dates=[day],
                    )
                )
    engine._validate_leader_on_night()
    engine._collect_staffing_shortfalls()
    engine._emit_understaffed_warnings()

    # 配置先未設定の勤務日
    for (sid, day), symbol in list(engine.grid.items()):
        if day not in engine.date_index:
            continue
        if not engine._is_work_day_symbol(symbol):
            continue
        if (sid, day) not in engine.placements:
            staff = engine.staff_by_id.get(sid) or {}
            engine.warnings.append(
                _warning(
                    "info",
                    "placement_missing",
                    f"{staff.get('name', sid)} {day}: 勤務はありますが配置先が未設定です。",
                    staff_ids=[sid],
                    dates=[day],
                )
            )

    warnings = engine.warnings
    if focus_dates:
        focus = set(focus_dates)
        focused = [w for w in warnings if not w.get("dates") or focus.intersection(w.get("dates") or [])]
        # 期間全体の不足も残す（人数チェック）
        others = [w for w in warnings if w.get("code") in {"understaffed", "time_slot_understaffed", "leader_on_night_missing"}]
        merged = {id(w): w for w in focused + others}
        warnings = list(merged.values())

    return {
        "year": year,
        "month": month,
        "period_start": engine.period_start.isoformat(),
        "period_end": engine.period_end.isoformat(),
        "warning_count": len(warnings),
        "warnings": warnings,
    }
