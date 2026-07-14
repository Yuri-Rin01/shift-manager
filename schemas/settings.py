from pydantic import BaseModel, Field, field_validator

from data.shift_symbols import DEFAULT_SHIFT_SYMBOLS, default_visible_work_types, normalize_visible_work_types
from data.leave_request_config import (
    normalize_leave_request_max_by_type,
    normalize_leave_request_visible_types,
)
from data.placement_rules import (
    normalize_min_staff_by_floor,
    normalize_min_staff_by_work_type,
    normalize_staffing_requirement_mode,
    normalize_time_slot_staffing_rules,
)
from data.staffing_basis import normalize_staffing_basis_options


class AppSettings(BaseModel):
    facility_name: str = Field(default="○○病院", max_length=100)
    facility_type: str = Field(default="all")
    admin_name: str = Field(default="管理者", max_length=50)

    default_color_cells: bool = True
    default_show_job_column: bool = True
    default_show_dept_column: bool = True
    default_show_summary: bool = True
    show_shift_legend: bool = True
    default_table_zoom: int = Field(default=100, ge=50, le=200)
    calendar_sort_mode: str = "dept"
    week_start: str = "sunday"
    calendar_start_day: int = Field(default=1, ge=1, le=28)
    off_days_per_period: int | None = Field(
        default=None,
        ge=0,
        le=31,
        description="1期間あたりの休み日数（全職員共通）。未設定時は土日数",
    )
    highlight_today: bool = False
    show_week_number: bool = False
    cell_flick_input_enabled: bool = True
    cell_long_press_ms: int = Field(default=450, ge=300, le=1500)

    print_paper: str = "A4 横"
    print_scale: str = "100%"
    print_color_cells: bool = True
    print_header_footer: bool = True
    print_page_numbers: bool = True

    min_early_staff: int = Field(default=1, ge=0, le=99)
    staffing_basis_options: list[dict] = Field(
        default_factory=lambda: normalize_staffing_basis_options(None)
    )
    min_day_staff: int = Field(default=2, ge=0, le=99)
    min_night_staff: int = Field(default=1, ge=0, le=99)
    min_staff_by_work_type: dict[str, int] = Field(default_factory=dict)
    min_staff_by_floor: dict[str, dict[str, int]] = Field(default_factory=dict)
    staffing_requirement_mode: str = Field(default="work_type")
    time_slot_staffing_rules: list[dict] = Field(default_factory=list)
    block_work_after_night: bool = True
    morning_off_after_night: bool = True
    night_shift_counts_as_two_days: bool = True
    max_consecutive_days: int = Field(default=5, ge=1, le=14)
    max_night_per_week: int = Field(default=2, ge=0, le=7)
    require_leader_on_night: bool = True

    leave_alert_threshold: int = Field(default=72, ge=0, le=168)
    leave_fulfill_target: int = Field(default=90, ge=0, le=100)
    warn_overstaffing: bool = True
    warn_understaffing: bool = True
    show_status_bar: bool = True

    prioritize_leave_requests: bool = True
    consider_night_eligibility: bool = True
    fairness_mode: str = "balance"
    confirm_after_generate: bool = True
    auto_fill_holidays: bool = False

    log_retention_days: int = Field(default=90, ge=7, le=3650)
    session_timeout_minutes: int = Field(default=60, ge=5, le=480)
    require_password_change_days: int = Field(default=0, ge=0, le=365)

    notify_shift_update: bool = True
    notify_alerts: bool = True
    notify_deadline: bool = True
    deadline_day_of_month: int = Field(default=20, ge=1, le=28)

    leave_request_visible_types: dict[str, bool] = Field(default_factory=dict)
    leave_request_max_total: int | None = Field(default=None, ge=0, le=31)
    leave_request_max_by_type: dict[str, int] = Field(default_factory=dict)
    leave_request_over_limit_message: str = Field(default="", max_length=500)

    allow_paid_leave_half: bool = True
    show_training_mark: bool = True
    visible_work_types: dict[str, bool] = Field(default_factory=default_visible_work_types)
    shift_symbols: dict[str, str] = Field(default_factory=lambda: dict(DEFAULT_SHIFT_SYMBOLS))

    @field_validator("visible_work_types")
    @classmethod
    def normalize_visible_work_types_field(cls, value: dict[str, bool]) -> dict[str, bool]:
        return normalize_visible_work_types({"visible_work_types": value})

    @field_validator("staffing_basis_options")
    @classmethod
    def normalize_staffing_basis(cls, value: list[dict]) -> list[dict]:
        return normalize_staffing_basis_options(value)

    @field_validator("min_staff_by_work_type")
    @classmethod
    def normalize_min_staff(cls, value: dict[str, int]) -> dict[str, int]:
        return normalize_min_staff_by_work_type(value)

    @field_validator("min_staff_by_floor")
    @classmethod
    def normalize_min_staff_by_floor_field(cls, value: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
        return normalize_min_staff_by_floor(value)

    @field_validator("staffing_requirement_mode")
    @classmethod
    def normalize_staffing_requirement_mode_field(cls, value: str) -> str:
        return normalize_staffing_requirement_mode(value)

    @field_validator("time_slot_staffing_rules")
    @classmethod
    def normalize_time_slot_rules(cls, value: list[dict]) -> list[dict]:
        return normalize_time_slot_staffing_rules(value)

    @field_validator("leave_request_visible_types")
    @classmethod
    def normalize_leave_request_visible_types_field(cls, value: dict[str, bool]) -> dict[str, bool]:
        return normalize_leave_request_visible_types(value)

    @field_validator("leave_request_max_by_type")
    @classmethod
    def normalize_leave_request_max_by_type_field(cls, value: dict[str, int]) -> dict[str, int]:
        return normalize_leave_request_max_by_type(value)

    @field_validator("block_work_after_night", "morning_off_after_night")
    @classmethod
    def enforce_fixed_morning_off_rules(cls, value: bool) -> bool:
        return True

    @field_validator("shift_symbols")
    @classmethod
    def normalize_shift_symbols(cls, value: dict[str, str]) -> dict[str, str]:
        return {
            key: symbol.strip()
            for key, symbol in value.items()
            if key != "public" and isinstance(symbol, str) and symbol.strip()
        }


class AppSettingsUpdate(AppSettings):
    pass
