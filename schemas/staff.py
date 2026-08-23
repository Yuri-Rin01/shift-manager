from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import Literal, Self

from data.night_eligibility import resolve_night_flags
from data.staffing_basis import (
    get_default_staffing_basis_ratios,
    validate_staffing_basis_ratios,
)
from data.masters import get_departments
from data.student_labor_limits import (
    default_student_labor_profile,
    normalize_student_labor_profile,
)


def _allowed_floors() -> set[str]:
    return {item["label"] for item in get_departments()}


def _normalize_floors(value: list[str], *, empty_message: str) -> list[str]:
    allowed = _allowed_floors()
    cleaned = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    if not cleaned:
        raise ValueError(empty_message)
    invalid = [item for item in cleaned if item not in allowed]
    if invalid:
        raise ValueError(f"無効なフロアです: {', '.join(invalid)}")
    order = {item["label"]: index for index, item in enumerate(get_departments())}
    return sorted(dict.fromkeys(cleaned), key=lambda item: order.get(item, 999))


def _normalize_single_floor(value: list[str]) -> list[str]:
    floors = _normalize_floors(value, empty_message="担当フロアを選択してください。")
    if len(floors) != 1:
        raise ValueError("担当フロアは1つだけ選択してください。")
    return floors


class StaffBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, description="名前")
    departments: list[str] = Field(..., min_length=1, max_length=1, description="担当フロア（表示用・1つのみ）")
    placement_floors: list[str] = Field(..., min_length=1, description="配置可能フロア（複数可）")
    job_type: str = Field(..., min_length=1, max_length=50, description="職種")
    position: str = Field(default="", max_length=50, description="役職")
    can_work_night: bool = Field(default=False, description="夜勤可否")
    can_be_night_leader: bool = Field(default=False, description="夜勤リーダー可")
    staffing_basis: dict[str, int] = Field(
        default_factory=get_default_staffing_basis_ratios,
        description="勤務割合（キー→割合%）",
    )
    exclude_from_staffing: bool = Field(default=False, description="人員に含めない")
    off_days_per_period: int | None = Field(
        default=None,
        ge=0,
        le=31,
        description="1期間あたりの休み日数（未設定時は施設の標準）",
    )
    night_shift_count: int | None = Field(
        default=None,
        ge=0,
        le=31,
        description="1ヶ月あたりの夜勤回数",
    )
    fix_night_shift_count: bool = Field(
        default=False,
        description="夜勤回数を固定する",
    )
    day_incompatible_ids: list[int] = Field(
        default_factory=list,
        description="日勤で組ませない職員ID",
    )
    night_incompatible_ids: list[int] = Field(
        default_factory=list,
        description="夜勤で組ませない職員ID",
    )
    student_labor: dict = Field(
        default_factory=default_student_labor_profile,
        description="留学生の在留資格・労働時間制限プロフィール",
    )

    @field_validator("departments")
    @classmethod
    def validate_departments(cls, value: list[str]) -> list[str]:
        return _normalize_single_floor(value)

    @field_validator("placement_floors")
    @classmethod
    def validate_placement_floors(cls, value: list[str]) -> list[str]:
        return _normalize_floors(value, empty_message="配置可能フロアを1つ以上選択してください。")

    @field_validator("staffing_basis")
    @classmethod
    def validate_staffing_basis(cls, value: dict[str, int]) -> dict[str, int]:
        return validate_staffing_basis_ratios(value)

    @field_validator("student_labor", mode="before")
    @classmethod
    def validate_student_labor(cls, value: object) -> dict:
        return normalize_student_labor_profile(value)

    @model_validator(mode="after")
    def night_leader_implies_night(self) -> Self:
        night, leader = resolve_night_flags(
            can_work_night=self.can_work_night,
            can_be_night_leader=self.can_be_night_leader,
        )
        self.can_work_night = night
        self.can_be_night_leader = leader
        self.student_labor = normalize_student_labor_profile(
            self.student_labor,
            job_type=self.job_type,
        )
        return self


class StaffCreate(StaffBase):
    pass


class StaffUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50, description="名前")
    departments: list[str] | None = Field(default=None, min_length=1, max_length=1, description="担当フロア（表示用・1つのみ）")
    placement_floors: list[str] | None = Field(default=None, min_length=1, description="配置可能フロア（複数可）")
    job_type: str | None = Field(default=None, min_length=1, max_length=50, description="職種")
    position: str | None = Field(default=None, max_length=50, description="役職")
    can_work_night: bool | None = Field(default=None, description="夜勤可否")
    can_be_night_leader: bool | None = Field(default=None, description="夜勤リーダー可")
    staffing_basis: dict[str, int] | None = Field(default=None, description="勤務割合（キー→割合%）")
    exclude_from_staffing: bool | None = Field(default=None, description="人員に含めない")
    off_days_per_period: int | None = Field(
        default=None,
        ge=0,
        le=31,
        description="1期間あたりの休み日数（未設定時は施設の標準）",
    )
    night_shift_count: int | None = Field(
        default=None,
        ge=0,
        le=31,
        description="1ヶ月あたりの夜勤回数",
    )
    fix_night_shift_count: bool | None = Field(
        default=None,
        description="夜勤回数を固定する",
    )
    day_incompatible_ids: list[int] | None = Field(
        default=None,
        description="日勤で組ませない職員ID",
    )
    night_incompatible_ids: list[int] | None = Field(
        default=None,
        description="夜勤で組ませない職員ID",
    )
    student_labor: dict | None = Field(
        default=None,
        description="留学生の在留資格・労働時間制限プロフィール",
    )

    @field_validator("departments")
    @classmethod
    def validate_departments(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return StaffBase.validate_departments(value)

    @field_validator("placement_floors")
    @classmethod
    def validate_placement_floors(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return StaffBase.validate_placement_floors(value)

    @field_validator("staffing_basis")
    @classmethod
    def validate_staffing_basis(cls, value: dict[str, int] | None) -> dict[str, int] | None:
        if value is None:
            return None
        return StaffBase.validate_staffing_basis(value)

    @field_validator("student_labor", mode="before")
    @classmethod
    def validate_student_labor(cls, value: object) -> dict | None:
        if value is None:
            return None
        return normalize_student_labor_profile(value)

    @model_validator(mode="after")
    def night_leader_implies_night(self) -> Self:
        if self.can_be_night_leader:
            self.can_work_night = True
        return self


class StaffResponse(StaffBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    department: str = Field(description="主担当フロア（並び順用）")


class StaffBulkUpdate(BaseModel):
    ids: list[int] = Field(..., min_length=1, description="一括更新対象の職員ID")
    departments_mode: Literal["replace", "add"] = Field(
        default="replace",
        description="フロアの適用方法",
    )
    job_type: str | None = Field(default=None, min_length=1, max_length=50, description="職種")
    position: str | None = Field(default=None, max_length=50, description="役職")
    departments: list[str] | None = Field(default=None, min_length=1, max_length=1, description="担当フロア（表示用・1つのみ）")
    placement_floors: list[str] | None = Field(default=None, min_length=1, description="配置可能フロア（複数可）")
    can_work_night: bool | None = Field(default=None, description="夜勤可否")
    can_be_night_leader: bool | None = Field(default=None, description="夜勤リーダー可")
    staffing_basis: dict[str, int] | None = Field(default=None, description="勤務割合（キー→割合%）")
    exclude_from_staffing: bool | None = Field(default=None, description="人員に含めない")
    off_days_per_period: int | None = Field(
        default=None,
        ge=0,
        le=31,
        description="1期間あたりの休み日数（未設定時は施設の標準）",
    )
    night_shift_count: int | None = Field(
        default=None,
        ge=0,
        le=31,
        description="1ヶ月あたりの夜勤回数",
    )
    fix_night_shift_count: bool | None = Field(
        default=None,
        description="夜勤回数を固定する",
    )

    @field_validator("departments")
    @classmethod
    def validate_departments(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return StaffBase.validate_departments(value)

    @field_validator("placement_floors")
    @classmethod
    def validate_placement_floors(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return StaffBase.validate_placement_floors(value)

    @field_validator("staffing_basis")
    @classmethod
    def validate_staffing_basis(cls, value: dict[str, int] | None) -> dict[str, int] | None:
        if value is None:
            return None
        return StaffBase.validate_staffing_basis(value)

    @model_validator(mode="after")
    def night_leader_implies_night(self) -> Self:
        if self.can_be_night_leader:
            self.can_work_night = True
        return self


class StaffBulkUpdateResponse(BaseModel):
    updated: int
    staff: list[StaffResponse]
    not_found: list[int] = Field(default_factory=list)
