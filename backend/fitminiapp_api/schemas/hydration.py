from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator


class HydrationBeverageType(StrEnum):
    WATER = "water"
    TEA = "tea"
    COFFEE = "coffee"
    MILK = "milk"
    JUICE = "juice"
    OTHER = "other"


class HydrationGoalSource(StrEnum):
    NATIONAL_ACADEMIES_BEVERAGES = "national_academies_beverages"
    MANUAL = "manual"


class HydrationGoalSave(BaseModel):
    enabled: bool = True
    target_ml: int | None = Field(default=None, ge=250, le=10000)
    source: HydrationGoalSource
    sex: str | None = Field(default=None, pattern="^(male|female)$")
    adult_confirmed: bool | None = None
    save_sex_to_profile: bool = False
    effective_from: date | None = None

    @model_validator(mode="after")
    def validate_goal(self):
        if not self.enabled:
            return self
        if self.source == HydrationGoalSource.MANUAL and self.target_ml is None:
            raise ValueError("Для ручной цели укажите объём")
        if self.source == HydrationGoalSource.NATIONAL_ACADEMIES_BEVERAGES:
            if self.sex not in {"male", "female"}:
                raise ValueError("Для расчётной цели укажите пол")
            if self.adult_confirmed is not True:
                raise ValueError("Расчётная цель доступна только после подтверждения возраста 18+")
        if self.save_sex_to_profile and self.sex is None:
            raise ValueError("Чтобы сохранить пол в профиль, сначала укажите его")
        return self


class HydrationGoalResponse(BaseModel):
    id: int
    enabled: bool
    target_ml: int | None
    source: HydrationGoalSource
    method_version: str
    reference_scope: str
    sex: str | None
    adult_confirmed: bool | None
    effective_from: date
    effective_to: date | None
    created_at: datetime


class HydrationEntryCreate(BaseModel):
    volume_ml: int = Field(ge=1, le=5000)
    beverage_type: HydrationBeverageType = HydrationBeverageType.WATER
    occurred_at: datetime | None = None
    diary_date: date | None = None
    source: str = Field(default="manual", pattern="^(quick_preset|manual)$")


class HydrationEntryUpdate(BaseModel):
    volume_ml: int = Field(ge=1, le=5000)
    beverage_type: HydrationBeverageType
    occurred_at: datetime


class HydrationEntryDelete(BaseModel):
    created_at: datetime
    updated_at: datetime
    diary_date: date

    @field_validator("created_at", "updated_at")
    @classmethod
    def require_naive_version(cls, value: datetime) -> datetime:
        if value.utcoffset() is not None:
            raise ValueError("Версия записи должна быть без часового пояса")
        return value


class HydrationEntryResponse(BaseModel):
    id: int
    volume_ml: int
    beverage_type: HydrationBeverageType
    occurred_at: datetime
    diary_date: date
    timezone: str
    source: str
    created_at: datetime
    updated_at: datetime


class HydrationPresetSave(BaseModel):
    label: str = Field(min_length=1, max_length=40)
    volume_ml: int = Field(ge=1, le=5000)
    beverage_type: HydrationBeverageType = HydrationBeverageType.WATER


class HydrationPresetResponse(BaseModel):
    id: int | None = None
    label: str
    volume_ml: int
    beverage_type: HydrationBeverageType
    is_default: bool = False


class HydrationDayResponse(BaseModel):
    diary_date: date
    timezone: str
    total_ml: int
    goal: HydrationGoalResponse | None
    progress_percent: float | None
    entries: list[HydrationEntryResponse]
    presets: list[HydrationPresetResponse]
    last_logged_at: datetime | None
    reminder_suppression_key: str | None
    action_url: str
