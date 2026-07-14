from datetime import date

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from pydantic import BaseModel, Field

from data.navigation import get_sidebar
from data.facility import get_facility_context
from schemas.leave_request import LeaveRequestResponse
from services import leave_request_admin_service as admin_service

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")

router = APIRouter(tags=["休み希望管理"])


class LeaveRequestSettingsUpdate(BaseModel):
    leave_request_visible_types: dict[str, bool] | None = None
    leave_request_max_total: int | None = Field(default=None, ge=0, le=31)
    leave_request_max_by_type: dict[str, int] | None = None
    leave_request_over_limit_message: str | None = Field(default=None, max_length=500)


class LeaveRequestBulkAction(BaseModel):
    ids: list[int] = Field(..., min_length=1)
    action: str = Field(..., description="approve / reject")


def _adjacent_month(year: int, month: int, delta: int) -> tuple[int, int]:
    month += delta
    while month < 1:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    return year, month


@router.get("/leave-requests", response_class=HTMLResponse, name="leave_requests_page")
def leave_requests_page(
    request: Request,
    year: int | None = None,
    month: int | None = None,
):
    today = date.today()
    resolved_year = year or today.year
    resolved_month = month or today.month
    if resolved_month < 1 or resolved_month > 12:
        resolved_year = today.year
        resolved_month = today.month
    prev_year, prev_month = _adjacent_month(resolved_year, resolved_month, -1)
    next_year, next_month = _adjacent_month(resolved_year, resolved_month, 1)
    page_data = admin_service.build_admin_page_data(resolved_year, resolved_month)
    context = {
        **get_facility_context(),
        "sidebar_menu": get_sidebar("leave-request"),
        "prev_year": prev_year,
        "prev_month": prev_month,
        "next_year": next_year,
        "next_month": next_month,
        **page_data,
    }
    return templates.TemplateResponse(request, "leave_requests/index.html", context)


@router.get("/api/leave-requests/overview")
def get_leave_requests_overview(year: int | None = None, month: int | None = None):
    today = date.today()
    resolved_year = year or today.year
    resolved_month = month or today.month
    if resolved_month < 1 or resolved_month > 12:
        resolved_month = today.month
    return admin_service.build_admin_page_data(resolved_year, resolved_month)


@router.put("/api/leave-requests/settings")
def update_leave_request_settings(data: LeaveRequestSettingsUpdate):
    payload = data.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="更新項目がありません。")
    return admin_service.update_leave_request_settings(payload)


@router.post("/api/leave-requests/{request_id}/approve", response_model=LeaveRequestResponse)
def approve_leave_request(request_id: int):
    try:
        return admin_service.approve_request(request_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/api/leave-requests/{request_id}/reject", response_model=LeaveRequestResponse)
def reject_leave_request(request_id: int):
    try:
        return admin_service.reject_request(request_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/api/leave-requests/bulk")
def bulk_leave_request_action(data: LeaveRequestBulkAction):
    try:
        return admin_service.bulk_update_requests(data.ids, data.action)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
