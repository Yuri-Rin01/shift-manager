from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from data.calendar_period import period_bounds
from data.shift_symbols import get_valid_symbols, normalize_symbol
from db import shift_repository as repo
from db.settings_repository import get_settings
from db.staff_repository import get_staff, list_staff
from schemas.auto_shift import (
    AutoGeneratePreflightResponse,
    AutoGeneratePreflightWarning,
    ShiftGenerateRequest,
    ShiftGenerateResponse,
    ShiftGenerateResultSummary,
    ShiftGenerateStats,
    ShiftGenerateWarning,
)
from services.auto_generate_preflight import build_auto_generate_preflight
from schemas.shift import (
    ShiftCellResponse,
    ShiftHistoryRestore,
    ShiftCellUnlock,
    ShiftCellUpdate,
    ShiftClearRequest,
    ShiftClearResponse,
)
from schemas.generation_preview import GenerationPreviewRequest, GenerationApplyRequest
from services.auth import require_admin
from services.generation_preview import generation_context, create_preview, apply_preview
from services.morning_off import (
    apply_morning_off_after_night,
    clear_auto_morning_off_after_night,
    would_block_day_work_after_night,
)
from services.shift_generator import generate_shifts
from services.student_labor import (
    REASON_MESSAGES,
    can_assign_shift,
    format_hours,
    is_student_labor_restricted,
    normalize_student_labor_profile,
    summarize_staff_month,
    summarize_staff_week,
    summarize_staff_weeks,
    week_range_containing,
)
from data.student_labor_limits import normalize_student_labor_limits

router = APIRouter(prefix="/api/shifts", tags=["シフト"], dependencies=[Depends(require_admin)])


def _valid_symbols() -> set[str]:
    return get_valid_symbols(get_settings())


def _build_generate_message(raw: dict) -> str:
    stats = raw.get("stats") or {}
    scope = stats.get("scope_label") or f"{raw.get('year')}年{raw.get('month')}月"
    if raw.get("save_error"):
        return f"{scope}の生成結果を保存できませんでした。"
    if raw.get("preview"):
        generated = stats.get("generated_cells", 0)
        return f"{scope}のプレビューを作成しました（{generated} セル）。保存はしていません。"
    if raw.get("applied"):
        generated = stats.get("generated_cells", 0)
        return f"{scope}のシフトを生成しました（{generated} セル）。"
    errors = [w for w in raw.get("warnings", []) if w.get("level") == "error"]
    if errors:
        return errors[0].get("message", "自動生成に失敗しました。")
    return "自動生成を完了できませんでした。"


def _to_generate_response(raw: dict) -> ShiftGenerateResponse:
    stats = raw.get("stats") or {}
    warnings = []
    for item in raw.get("warnings", []):
        warnings.append(
            ShiftGenerateWarning(
                level=item.get("level", "info"),
                code=item.get("code", ""),
                message=item.get("message", ""),
                suggestion=item.get("suggestion"),
                href=item.get("href"),
                action_label=item.get("action_label"),
                staff_ids=item.get("staff_ids") or [],
                dates=item.get("dates") or [],
            )
        )
    summary_raw = raw.get("result_summary")
    result_summary = None
    if summary_raw:
        result_summary = ShiftGenerateResultSummary(**summary_raw)
    return ShiftGenerateResponse(
        year=raw["year"],
        month=raw["month"],
        preview=raw["preview"],
        applied=raw["applied"],
        ok=raw.get("ok", False),
        message=_build_generate_message(raw),
        stats=ShiftGenerateStats(**stats),
        warnings=warnings,
        result_summary=result_summary,
        priority_order=raw.get("priority_order", []),
        scope_day_count=raw.get("scope_day_count"),
        save_error=raw.get("save_error"),
    )


def _valid_symbols() -> set[str]:
    return get_valid_symbols(get_settings())


@router.get("/student-labor-summary")
def student_labor_summary(
    year: int = Query(...),
    month: int = Query(...),
    day: int | None = Query(default=None),
):
    """留学生シート用の週労働時間サマリー。"""
    if year < 2000 or year > 2100 or month < 1 or month > 12:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="年月が不正です")
    settings = get_settings()
    start_day = settings.get("calendar_start_day", 1)
    period_start, period_end = period_bounds(year, month, start_day)
    try:
        focus = date(year, month, day) if day else period_start
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="日付が不正です") from exc

    limits = normalize_student_labor_limits(settings.get("student_labor_limits"))
    week_start, week_end = week_range_containing(focus, limits["week_start"])
    first_week_start, _ = week_range_containing(period_start, limits["week_start"])
    _, last_week_end = week_range_containing(period_end, limits["week_start"])
    fetch_start = first_week_start - timedelta(days=1)
    fetch_end = last_week_end + timedelta(days=1)
    shifts = repo.get_shifts_between(fetch_start, fetch_end)

    rows = []
    for staff in list_staff():
        profile = normalize_student_labor_profile(
            staff.get("student_labor") or {},
            job_type=staff.get("job_type"),
        )
        if staff.get("job_type") != "留学生" and not is_student_labor_restricted(profile):
            continue
        assignments = [
            (date.fromisoformat(day_str), cell["symbol"])
            for (sid, day_str), cell in shifts.items()
            if sid == staff["id"] and cell.get("symbol")
        ]
        summary = summarize_staff_week(
            staff=staff,
            focus_day=focus,
            assignments=assignments,
            settings=settings,
        )
        summary["facility_week_hours_label"] = format_hours(summary["facility_week_minutes"])
        summary["other_job_hours_label"] = format_hours(summary["other_job_weekly_minutes"])
        summary["total_hours_label"] = format_hours(summary["total_week_minutes"])
        summary["limit_hours_label"] = format_hours(summary["limit_week_minutes"])
        summary["remaining_hours_label"] = format_hours(summary["remaining_minutes"])
        summary["weeks"] = summarize_staff_weeks(
            staff=staff,
            period_start=period_start,
            period_end=period_end,
            assignments=assignments,
            settings=settings,
        )
        rows.append(summary)

    return {
        "year": year,
        "month": month,
        "focus_day": focus.isoformat(),
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "rows": rows,
    }


@router.get("/student-labor-month")
def student_labor_month_summary(
    year: int = Query(...),
    month: int = Query(...),
):
    """留学生シート用の月別労働時間集計（確認用）。"""
    if year < 2000 or year > 2100 or month < 1 or month > 12:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="年月が不正です")
    settings = get_settings()
    start_day = settings.get("calendar_start_day", 1)
    period_start, period_end = period_bounds(year, month, start_day)
    fetch_start = period_start - timedelta(days=1)
    fetch_end = period_end + timedelta(days=1)
    shifts = repo.get_shifts_between(fetch_start, fetch_end)

    rows = []
    for staff in list_staff():
        profile = normalize_student_labor_profile(
            staff.get("student_labor") or {},
            job_type=staff.get("job_type"),
        )
        if staff.get("job_type") != "留学生" and not is_student_labor_restricted(profile):
            continue
        assignments = [
            (date.fromisoformat(day_str), cell["symbol"])
            for (sid, day_str), cell in shifts.items()
            if sid == staff["id"] and cell.get("symbol")
        ]
        rows.append(
            summarize_staff_month(
                staff=staff,
                year=year,
                month=month,
                assignments=assignments,
                settings=settings,
            )
        )

    return {"year": year, "month": month, "rows": rows}


@router.put("/cell", response_model=ShiftCellResponse)
def update_shift_cell(data: ShiftCellUpdate):
    settings = get_settings()
    symbol = normalize_symbol(data.symbol, settings) if data.symbol else ""
    if symbol and symbol not in _valid_symbols():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"無効なシフト記号です: {data.symbol}",
        )
    staff = get_staff(data.staff_id)
    if staff is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="職員が見つかりません")

    if symbol and would_block_day_work_after_night(
        data.staff_id,
        data.year,
        data.month,
        data.day,
        symbol,
        settings,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="明けの翌日は早番・日勤・遅出を割り当てできません（固定ルール）。",
        )

    try:
        shift_date = date(data.year, data.month, data.day)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="日付が不正です") from exc

    profile = normalize_student_labor_profile(
        staff.get("student_labor") or {},
        job_type=staff.get("job_type"),
    )
    if is_student_labor_restricted(profile) and symbol:
        limits = normalize_student_labor_limits(settings.get("student_labor_limits"))
        week_start, week_end = week_range_containing(shift_date, limits["week_start"])
        fetch_start = week_start - timedelta(days=1)
        fetch_end = week_end + timedelta(days=1)
        existing_map = repo.get_shifts_between(fetch_start, fetch_end)
        existing = [
            (date.fromisoformat(day_str), cell["symbol"])
            for (sid, day_str), cell in existing_map.items()
            if sid == data.staff_id and cell.get("symbol") and day_str != shift_date.isoformat()
        ]
        ok, reason, detail = can_assign_shift(
            staff=staff,
            work_date=shift_date,
            symbol=symbol,
            existing_assignments=existing,
            settings=settings,
        )
        if not ok:
            week_label = f"{detail.get('week_start')}～{detail.get('week_end')}"
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "保存できません。\n"
                    f"対象職員：{staff.get('name')}\n"
                    f"対象週：{week_label}\n"
                    f"自施設の勤務時間：{format_hours(detail.get('facility_week_minutes') or 0)}\n"
                    f"他勤務先の勤務時間：{format_hours(detail.get('other_job_weekly_minutes') or 0)}\n"
                    f"合計：{format_hours(detail.get('total_week_minutes') or 0)}\n"
                    f"上限：{format_hours(detail.get('limit_week_minutes') or 0)}\n"
                    f"超過：{format_hours(max(0, -(detail.get('remaining_minutes') or 0)))}\n"
                    f"理由：{REASON_MESSAGES.get(reason or '', reason or '上限超過')}"
                ),
            )

    related: list[dict] = []
    related.extend(
        clear_auto_morning_off_after_night(
            data.staff_id,
            data.year,
            data.month,
            data.day,
            symbol,
            settings,
        )
    )

    if not symbol:
        repo.delete_shift_cell(data.staff_id, shift_date)
        return ShiftCellResponse(
            staff_id=data.staff_id,
            shift_date=shift_date.isoformat(),
            symbol="",
            source="",
            related=[ShiftCellResponse(**item) for item in related],
        )

    result = repo.upsert_shift_cell(
        data.staff_id,
        data.year,
        data.month,
        data.day,
        symbol,
    )
    related.extend(
        apply_morning_off_after_night(
            data.staff_id,
            data.year,
            data.month,
            data.day,
            symbol,
            settings,
        )
    )
    return ShiftCellResponse(
        **result,
        related=[ShiftCellResponse(**item) for item in related],
    )


@router.post("/history/restore")
def restore_shift_history(data: ShiftHistoryRestore):
    from services.shift_edit import restore_cells

    states = [cell.model_dump(mode="json") for cell in data.states]
    expected = [cell.model_dump(mode="json") for cell in data.expected]
    valid = _valid_symbols()
    for cell in states:
        if cell["symbol"] and (cell["symbol"] not in valid or not cell["source"]):
            raise HTTPException(
                status_code=400,
                detail="勤務記号または入力元が無効です。設定変更後は再読み込みしてください。",
            )
        if not cell["symbol"] and (cell["source"] or cell["placement"]):
            raise HTTPException(status_code=400, detail="空欄の復元データが不正です。")
    try:
        return {"cells": restore_cells(states, expected)}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/cell/unlock", response_model=ShiftCellResponse)
def unlock_shift_cell(data: ShiftCellUnlock):
    """手動確定を解除し、自動生成で上書き可能な状態に戻す（記号は維持）。"""
    staff = get_staff(data.staff_id)
    if staff is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="職員が見つかりません")

    try:
        shift_date = date(data.year, data.month, data.day)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="日付が不正です") from exc

    existing = repo.get_shift_cell(data.staff_id, shift_date)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="シフトが見つかりません")
    if existing["source"] != "manual":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="手動確定されていないセルです",
        )

    result = repo.upsert_shift_cell(
        data.staff_id,
        data.year,
        data.month,
        data.day,
        existing["symbol"],
        source="auto",
    )
    return ShiftCellResponse(**result)


@router.post("/clear", response_model=ShiftClearResponse)
def clear_shift_schedule(data: ShiftClearRequest):
    """表示期間のシフト割当をすべて削除する（セルを空白に戻す）。"""
    settings = get_settings()
    start_day = settings.get("calendar_start_day", 1)
    period_start, period_end = period_bounds(data.year, data.month, start_day)
    deleted = repo.delete_shifts_between(period_start, period_end)
    return ShiftClearResponse(
        year=data.year,
        month=data.month,
        period_start=period_start.isoformat(),
        period_end=period_end.isoformat(),
        deleted_count=deleted,
    )


@router.get(
    "/generate/preflight",
    response_model=AutoGeneratePreflightResponse,
    name="preflight_shift_generate",
)
def preflight_shift_generate(
    year: int,
    month: int,
    scope_start: str | None = None,
    scope_end: str | None = None,
    floors: Annotated[
        str | None,
        Query(description="対象フロア（カンマ区切り）。未指定なら全フロア。"),
    ] = None,
):
    """自動生成前の確認サマリーと矛盾警告。"""
    if year < 2000 or year > 2100 or month < 1 or month > 12:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="年月が不正です")
    floor_list = None
    if isinstance(floors, str) and floors.strip():
        floor_list = [part.strip() for part in floors.split(",") if part.strip()]
    raw = build_auto_generate_preflight(
        year,
        month,
        scope_start=scope_start,
        scope_end=scope_end,
        floors=floor_list,
    )
    return AutoGeneratePreflightResponse(
        **{
            **raw,
            "warnings": [
                AutoGeneratePreflightWarning(
                    level=item.get("level", "warn"),
                    code=item.get("code", ""),
                    message=item.get("message", ""),
                    blocking=bool(item.get("blocking")),
                    suggestion=item.get("suggestion"),
                    href=item.get("href"),
                    action_label=item.get("action_label"),
                )
                for item in raw.get("warnings", [])
            ],
            "suggestions": raw.get("suggestions") or [],
        }
    )


@router.get("/labor-hours")
def get_labor_hours(year: int, month: int):
    from services.labor_hours import summarize_labor_hours

    try:
        return summarize_labor_hours(year, month)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"労働時間の集計に失敗しました: {exc}") from exc


@router.post("/generate", response_model=ShiftGenerateResponse, name="generate_shift_schedule")
def generate_shift_schedule(data: ShiftGenerateRequest):
    """シフト自動生成（確認画面で選んだ範囲・フロアが対象）。"""
    return _to_generate_response(
        generate_shifts(
            data.year,
            data.month,
            preview=data.preview,
            scope_start=data.scope_start,
            scope_end=data.scope_end,
            floors=data.floors,
        )
    )


@router.get("/generation/context")
def get_generation_context():
    return generation_context()


@router.post("/generation/preview")
def preview_generation(data: GenerationPreviewRequest):
    try:
        return create_preview(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/generation/apply")
def apply_generation(data: GenerationApplyRequest):
    try:
        return apply_preview(data.token)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
