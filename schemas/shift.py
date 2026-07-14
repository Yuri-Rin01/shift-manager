from pydantic import BaseModel, Field


class ShiftCellUpdate(BaseModel):
    staff_id: int = Field(..., ge=1)
    year: int = Field(..., ge=2000, le=2100)
    month: int = Field(..., ge=1, le=12)
    day: int = Field(..., ge=1, le=31)
    symbol: str = Field(..., min_length=1, max_length=10)


class ShiftCellResponse(BaseModel):
    staff_id: int
    shift_date: str
    symbol: str
    source: str = "manual"
    related: list["ShiftCellResponse"] = Field(default_factory=list)


class ShiftCellUnlock(BaseModel):
    staff_id: int = Field(..., ge=1)
    year: int = Field(..., ge=2000, le=2100)
    month: int = Field(..., ge=1, le=12)
    day: int = Field(..., ge=1, le=31)


class ShiftClearRequest(BaseModel):
    year: int = Field(..., ge=2000, le=2100)
    month: int = Field(..., ge=1, le=12)


class ShiftClearResponse(BaseModel):
    year: int
    month: int
    period_start: str
    period_end: str
    deleted_count: int
