from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class GenerationConditions(BaseModel):
    model_config = ConfigDict(extra='forbid')
    off_days_per_period: int | None = Field(default=None, ge=0, le=31)
    max_consecutive_days: int = Field(default=5, ge=1, le=14)
    max_night_per_week: int = Field(default=2, ge=0, le=7)
    min_staff_by_floor: dict[str, dict[str, int]] | None = None
    time_slot_staffing_rules: list[dict] | None = None


class GenerationPreviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    floor: str | None = None
    mode: Literal['auto', 'blank'] = 'auto'
    conditions: GenerationConditions | None = None
    night_counts: dict[int, int] = Field(default_factory=dict)
    save_defaults: bool = False


class GenerationApplyRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    token: str = Field(min_length=32, max_length=128)
