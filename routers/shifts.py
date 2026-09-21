from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status

from data.calendar_period import period_bounds
from data.shift_symbols import get_valid_symbols, normalize_symbol
from db import shift_repository as repo
from db.settings_repository import get_settings
from db.staff_repository import get_staff
from schemas.auto_shift import (
    ShiftGenerateRequest,
    ShiftGenerateResponse,
    ShiftGenerateStats,
    ShiftGenerateWarning,
)
from schemas.shift import (
    ShiftCellResponse,
    ShiftHistoryRestore,
    ShiftCellUnlock,
    ShiftCellUpdate,
    ShiftClearRequest,
    ShiftClearResponse,
)
from services.auth import require_admin
from services.morning_off import (
    would_block_day_work_after_night,
)
from services.shift_generator import generate_shifts
from schemas.generation_preview import GenerationPreviewRequest, GenerationApplyRequest
from services.generation_preview import generation_context, create_preview, apply_preview

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
    return ShiftGenerateResponse(
        year=raw["year"],
        month=raw["month"],
        preview=raw["preview"],
        applied=raw["applied"],
        ok=raw.get("ok", False),
        message=_build_generate_message(raw),
        stats=ShiftGenerateStats(**stats),
        warnings=[ShiftGenerateWarning(**item) for item in raw.get("warnings", [])],
        priority_order=raw.get("priority_order", []),
        scope_day_count=raw.get("scope_day_count"),
        save_error=raw.get("save_error"),
    )


@router.put("/cell", response_model=ShiftCellResponse)
def update_shift_cell(data: ShiftCellUpdate):
    settings = get_settings()
    symbol = normalize_symbol(data.symbol, settings)
    if symbol not in _valid_symbols():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"無効なシフト記号です: {data.symbol}",
        )
    staff = get_staff(data.staff_id)
    if staff is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="職員が見つかりません")

    if would_block_day_work_after_night(
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

    from services.shift_edit import edit_cell
    from datetime import timedelta as _td
    from services.shift_validate import validate_period

    try:
        day = date(data.year, data.month, data.day)
    except ValueError as exc:
        raise HTTPException(400, '日付が不正です') from exc
    try:
        result = edit_cell(data.staff_id, day, symbol, settings)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    try:
        validation = validate_period(
            data.year,
            data.month,
            focus_dates=[day.isoformat(), (day + _td(days=1)).isoformat()],
        )
        result = dict(result)
        result["validation"] = {
            "warning_count": validation["warning_count"],
            "warnings": validation["warnings"][:30],
        }
    except Exception:
        pass
    return result


@router.post('/history/restore')
def restore_shift_history(data: ShiftHistoryRestore):
    from services.shift_edit import restore_cells
    states = [c.model_dump(mode='json') for c in data.states]
    expected = [c.model_dump(mode='json') for c in data.expected]
    valid = _valid_symbols()
    for cell in states:
        if cell['symbol'] and (cell['symbol'] not in valid or not cell['source']):
            raise HTTPException(400, '勤務記号または入力元が無効です。設定変更後は再読み込みしてください。')
        if not cell['symbol'] and (cell['source'] or cell['placement']):
            raise HTTPException(400, '空欄の復元データが不正です。')
    try:
        return {'cells': restore_cells(states, expected)}
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/cell/unlock", response_model=ShiftCellResponse)
def unlock_shift_cell(data: ShiftCellUnlock):
    """手動確定を解除し、自動生成で上書き可能な状態に戻す（記号は維持）。"""
    from services.period_lock import assert_dates_editable

    staff = get_staff(data.staff_id)
    if staff is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="職員が見つかりません")

    try:
        shift_date = date(data.year, data.month, data.day)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="日付が不正です") from exc

    try:
        assert_dates_editable([shift_date], action="固定解除")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

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
    try:
        deleted = repo.delete_shifts_between(period_start, period_end)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return ShiftClearResponse(
        year=data.year,
        month=data.month,
        period_start=period_start.isoformat(),
        period_end=period_end.isoformat(),
        deleted_count=deleted,
    )


@router.post("/generate", response_model=ShiftGenerateResponse, name="generate_shift_schedule")
def generate_shift_schedule(data: ShiftGenerateRequest):
    """シフト自動生成（カレンダー表示区間全体が対象）。"""
    return _to_generate_response(generate_shifts(data.year, data.month, preview=data.preview))



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


@router.get("/validate")
def validate_shift_period(year: int, month: int, focus_date: str | None = None):
    from services.shift_validate import validate_period

    focus = [focus_date] if focus_date else None
    try:
        return validate_period(year, month, focus_dates=focus)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"検証に失敗しました: {exc}") from exc


@router.get("/labor-hours")
def get_labor_hours(year: int, month: int):
    from services.labor_hours import summarize_labor_hours

    try:
        return summarize_labor_hours(year, month)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"労働時間の集計に失敗しました: {exc}") from exc


@router.get("/period-lock")
def get_period_lock_status(year: int, month: int):
    from services.period_lock import period_status

    settings = get_settings()
    start_day = settings.get("calendar_start_day", 1)
    start, end = period_bounds(year, month, start_day)
    return period_status(start, end)


@router.post("/period-lock")
def lock_current_period(year: int, month: int, note: str = ""):
    from services.period_lock import lock_period

    settings = get_settings()
    start_day = settings.get("calendar_start_day", 1)
    start, end = period_bounds(year, month, start_day)
    try:
        return lock_period(start, end, note=note or f"{year}年{month}月の確定")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/period-unlock")
def unlock_current_period(year: int, month: int, confirm: bool = False):
    from services.period_lock import unlock_period

    settings = get_settings()
    start_day = settings.get("calendar_start_day", 1)
    start, end = period_bounds(year, month, start_day)
    try:
        return unlock_period(start, end, confirm=confirm)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
