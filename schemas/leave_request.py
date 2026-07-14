from datetime import date

from pydantic import BaseModel, Field, field_validator

from data.leave_request_types import LEAVE_REQUEST_TYPES


class LeaveRequestCreate(BaseModel):
    staff_id: int = Field(..., ge=1, description="職員ID")
    shift_date: date = Field(..., description="希望日")
    request_type: str = Field(..., description="off / paid_leave / half_leave")
    note: str = Field(default="", max_length=200)

    @field_validator("request_type")
    @classmethod
    def validate_request_type(cls, value: str) -> str:
        cleaned = str(value).strip()
        if cleaned not in LEAVE_REQUEST_TYPES:
            raise ValueError("休み希望の種別が不正です。")
        return cleaned

    @field_validator("note")
    @classmethod
    def validate_note(cls, value: str) -> str:
        return str(value or "").strip()[:200]


class LeaveRequestResponse(BaseModel):
    id: int
    staff_id: int
    shift_date: date
    request_type: str
    note: str
    status: str
    created_at: str
    updated_at: str


class LeavePortalLimitInfo(BaseModel):
    counts: dict[str, int] = Field(default_factory=dict)
    total: int = 0
    max_total: int = 0
    max_by_type: dict[str, int] = Field(default_factory=dict)
    is_over_limit: bool = False
    over_limit_message: str = ""


class LeavePortalCalendarResponse(BaseModel):
    staff_id: int
    staff_name: str
    year: int
    month: int
    period_label: str
    deadline_day_of_month: int
    is_past_deadline: bool
    request_options: list[dict]
    days: list[dict]
    requests: list[LeaveRequestResponse]
    limit_info: LeavePortalLimitInfo | None = None
