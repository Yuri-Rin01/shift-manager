from pydantic import BaseModel, Field


class ShiftGenerateRequest(BaseModel):
    year: int = Field(..., ge=2000, le=2100)
    month: int = Field(..., ge=1, le=12)
    preview: bool = False


class ShiftGenerateWarning(BaseModel):
    level: str = Field(description="info | warn | error")
    code: str
    message: str


class ShiftGenerateStats(BaseModel):
    period_days: int = 0
    full_period_days: int = 0
    scope_start: str | None = None
    scope_end: str | None = None
    scope_label: str = ""
    staff_count: int = 0
    manual_locked: int = 0
    leave_locked: int = 0
    generated_cells: int = 0
    night_assignments: int = 0


class ShiftGenerateResponse(BaseModel):
    year: int
    month: int
    preview: bool
    applied: bool
    ok: bool = False
    message: str = ""
    stats: ShiftGenerateStats
    warnings: list[ShiftGenerateWarning]
    priority_order: list[str]
    scope_day_count: int | None = None
    save_error: str | None = None
