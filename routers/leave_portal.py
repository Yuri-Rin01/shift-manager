from datetime import date

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from data.facility import get_facility_context
from data.leave_request_config import get_portal_request_options
from db.settings_repository import get_settings
from schemas.leave_request import LeavePortalCalendarResponse, LeaveRequestCreate, LeaveRequestResponse
from services import leave_portal_service as portal_service

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")

router = APIRouter(tags=["休み希望ポータル"])


@router.get("/", response_class=HTMLResponse, name="leave_portal_home")
def leave_portal_page(request: Request):
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "portal/leave_request.html",
        {
            **get_facility_context(),
            "request_options": get_portal_request_options(settings),
            "portal_settings": {
                "cell_flick_input_enabled": bool(settings.get("cell_flick_input_enabled", True)),
                "cell_long_press_ms": int(settings.get("cell_long_press_ms", 450) or 450),
            },
        },
    )


@router.get("/api/staff")
def list_portal_staff():
    return portal_service.list_portal_staff()


@router.get("/api/calendar", response_model=LeavePortalCalendarResponse)
def get_portal_calendar(staff_id: int, year: int | None = None, month: int | None = None):
    today = date.today()
    resolved_year = year or today.year
    resolved_month = month or today.month
    if resolved_month < 1 or resolved_month > 12:
        resolved_month = today.month
    try:
        return portal_service.build_portal_calendar(staff_id, resolved_year, resolved_month)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.put("/api/requests", response_model=LeaveRequestResponse)
def upsert_leave_request(data: LeaveRequestCreate):
    try:
        return portal_service.save_leave_request(
            data.staff_id,
            data.shift_date,
            data.request_type,
            note=data.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/api/requests")
def delete_leave_request(staff_id: int, shift_date: date):
    try:
        removed = portal_service.remove_leave_request(staff_id, shift_date)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="希望が見つかりません。")
    return {"ok": True}
