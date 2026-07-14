from datetime import date

from fastapi import APIRouter, HTTPException, status

from data.calendar_period import period_bounds
from data.shift_symbols import get_valid_symbols, normalize_symbol
from db import shift_repository as repo
from db.settings_repository import get_settings
from db.staff_repository import get_staff
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
    ShiftCellUnlock,
    ShiftCellUpdate,
    ShiftClearRequest,
    ShiftClearResponse,
)
from services.morning_off import (
    apply_morning_off_after_night,
    clear_auto_morning_off_after_night,
    would_block_day_work_after_night,
)
from services.shift_generator import generate_shifts

router = APIRouter(prefix="/api/shifts", tags=["シフト"])


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
        result_summary=(
            ShiftGenerateResultSummary(**raw["result_summary"])
            if raw.get("result_summary")
            else None
        ),
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

    result = repo.upsert_shift_cell(
        data.staff_id,
        data.year,
        data.month,
        data.day,
        symbol,
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
def preflight_shift_generate(year: int, month: int):
    """自動生成前の確認サマリーと矛盾警告。"""
    if year < 2000 or year > 2100 or month < 1 or month > 12:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="年月が不正です")
    raw = build_auto_generate_preflight(year, month)
    return AutoGeneratePreflightResponse(
        **{
            **raw,
            "warnings": [AutoGeneratePreflightWarning(**item) for item in raw.get("warnings", [])],
        }
    )


@router.post("/generate", response_model=ShiftGenerateResponse, name="generate_shift_schedule")
def generate_shift_schedule(data: ShiftGenerateRequest):
    """シフト自動生成（カレンダー表示区間全体が対象）。"""
    return _to_generate_response(generate_shifts(data.year, data.month, preview=data.preview))
