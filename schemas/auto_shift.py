from pydantic import BaseModel, Field


class ShiftGenerateRequest(BaseModel):
    year: int = Field(..., ge=2000, le=2100)
    month: int = Field(..., ge=1, le=12)
    preview: bool = False


class ShiftGenerateWarning(BaseModel):
    level: str = Field(description="info | warn | error")
    code: str
    message: str
    suggestion: str | None = None
    href: str | None = None
    action_label: str | None = None


class ShiftGenerateSuggestion(BaseModel):
    code: str = ""
    level: str = "warn"
    message: str = ""
    suggestion: str = ""
    href: str = ""
    action_label: str = "開く"


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


class ShiftGenerateResultSummary(BaseModel):
    placed_cells: int = 0
    leave_kept: int = 0
    manual_kept: int = 0
    understaffed: list[str] = Field(default_factory=list)
    unfilled_days: list[str] = Field(default_factory=list)
    unmet_preferences: list[str] = Field(default_factory=list)
    night_imbalance: list[str] = Field(default_factory=list)
    off_imbalance: list[str] = Field(default_factory=list)
    leader_issues: list[str] = Field(default_factory=list)
    fix_needed: list[str] = Field(default_factory=list)
    info: list[str] = Field(default_factory=list)
    suggestions: list[ShiftGenerateSuggestion] = Field(default_factory=list)


class ShiftGenerateResponse(BaseModel):
    year: int
    month: int
    preview: bool
    applied: bool
    ok: bool = False
    message: str = ""
    stats: ShiftGenerateStats
    warnings: list[ShiftGenerateWarning]
    result_summary: ShiftGenerateResultSummary | None = None
    priority_order: list[str]
    scope_day_count: int | None = None
    save_error: str | None = None


class AutoGeneratePreflightWarning(BaseModel):
    level: str
    code: str
    message: str
    blocking: bool = False
    suggestion: str | None = None
    href: str | None = None
    action_label: str | None = None


class AutoGeneratePreflightResponse(BaseModel):
    year: int
    month: int
    scope_label: str
    scope_start: str | None = None
    scope_end: str | None = None
    departments: list[str] = Field(default_factory=list)
    staff_count: int = 0
    leave_count: int = 0
    night_capable_count: int = 0
    night_leader_count: int = 0
    night_floor_counts: dict[str, int] = Field(default_factory=dict)
    off_days_per_period: int | None = None
    night_mins_by_floor: dict[str, int] = Field(default_factory=dict)
    min_staff_by_floor: dict[str, dict[str, int]] = Field(default_factory=dict)
    daily_night_slots: int = 0
    period_night_demand: int = 0
    staffing_requirement_mode: str = "work_type"
    require_leader_on_night: bool = True
    night_leader_groups: list[dict] = Field(default_factory=list)
    max_consecutive_days: int = 5
    max_night_per_week: int = 2
    fairness_mode: str = "balance"
    advanced_settings_used: list[str] = Field(default_factory=list)
    warnings: list[AutoGeneratePreflightWarning] = Field(default_factory=list)
    suggestions: list[ShiftGenerateSuggestion] = Field(default_factory=list)
    can_generate: bool = True
    staff_href: str = "/staff"
    settings_auto_href: str = "/settings?panel=auto"
