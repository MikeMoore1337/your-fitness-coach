from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from fitminiapp_api.schemas.data_quality import ProgressDataSufficiency
from fitminiapp_api.schemas.nutrition import EnergyCalibrationResponse
from fitminiapp_api.schemas.progress import (
    AdherenceComponent,
    BodyMetricTrend,
)
from fitminiapp_api.schemas.user import BodyPriorityPreference


class WeeklyCheckInTrainingSummary(BaseModel):
    planned_workouts: int = Field(ge=0)
    completed_workouts: int = Field(ge=0)
    adherence: AdherenceComponent


class WeeklyCheckInTargetSummary(BaseModel):
    effective_from: date
    source: Literal["calculated", "manual", "trainer", "adaptive"]
    calories: int = Field(ge=0)
    protein_g: int = Field(ge=0)
    fat_g: int = Field(ge=0)
    carbs_g: int = Field(ge=0)


class WeeklyCheckInSuspiciousNutritionDay(BaseModel):
    diary_date: date
    calories: int = Field(ge=0)
    target_calories: int = Field(ge=0)


class WeeklyCheckInNutritionSummary(BaseModel):
    logged_days: int = Field(ge=0)
    complete_days: int = Field(default=0, ge=0)
    incomplete_days: int = Field(default=0, ge=0)
    fasted_days: int = Field(default=0, ge=0)
    unlogged_days: int = Field(default=0, ge=0)
    average_calories: float | None = None
    target_calories: int | None = None
    average_protein_g: float | None = None
    target_protein_g: int | None = None
    calories_adherence: AdherenceComponent
    protein_adherence: AdherenceComponent
    current_target: WeeklyCheckInTargetSummary | None = None
    suspicious_low_days: list[WeeklyCheckInSuspiciousNutritionDay] = Field(default_factory=list)
    exact_entry_count: int | None = Field(default=0, ge=0)
    approximate_entry_count: int | None = Field(default=0, ge=0)
    partial_entry_count: int | None = Field(default=0, ge=0)


class WeeklyCheckInAdaptiveSummary(BaseModel):
    decision: Literal["accepted", "kept", "deferred", "no_change", "not_available"]
    calibration: EnergyCalibrationResponse


class WeeklyCheckInProgressionSummary(BaseModel):
    training_volume_kg: float = Field(ge=0)
    new_personal_records: int = Field(ge=0)


class WeeklyCheckInSummary(BaseModel):
    ruleset_version: Literal["weekly-check-in-summary-v1", "weekly-review-summary-v2"]
    period_start: date
    period_end: date
    goal: str | None = None
    training: WeeklyCheckInTrainingSummary
    nutrition: WeeklyCheckInNutritionSummary
    weight_trend: BodyMetricTrend | None = None
    anthropometry_trends: list[BodyMetricTrend]
    body_priority: BodyPriorityPreference | None = None
    progression: WeeklyCheckInProgressionSummary
    data_sufficiency: ProgressDataSufficiency
    adaptive_energy: WeeklyCheckInAdaptiveSummary | None = None


class WeeklyCheckInSubmitRequest(BaseModel):
    status: Literal["completed", "skipped"] = "completed"
    training_load: int | None = Field(default=None, ge=1, le=5)
    recovery: int | None = Field(default=None, ge=1, le=5)
    hunger: int | None = Field(default=None, ge=1, le=5)
    adherence_difficulty: int | None = Field(default=None, ge=1, le=5)
    note: str | None = Field(default=None, max_length=2000)
    energy_calibration_id: int | None = Field(default=None, ge=1)


class WeeklyCheckInResponse(BaseModel):
    id: int
    user_id: int
    week_start: date
    week_end: date
    submitted_on: date
    timezone: str
    status: Literal["completed", "skipped"]
    summary_version: Literal["weekly-check-in-summary-v1", "weekly-review-summary-v2"]
    summary: WeeklyCheckInSummary
    training_load: int | None = None
    recovery: int | None = None
    hunger: int | None = None
    adherence_difficulty: int | None = None
    note: str | None = None
    progress_action_kind: Literal["workout", "nutrition", "measurement", "none"] | None = None
    progress_action_completed_at: datetime | None = None
    created_at: datetime


class ProgressWeeklyActionResponse(BaseModel):
    kind: Literal["weekly_review", "workout", "nutrition", "measurement", "none"]
    status: Literal["available", "completed", "unavailable"]
    target: Literal["today", "nutrition", "body", "progress", "weekly_review"]
    reason: Literal[
        "review_required",
        "scheduled_training_gap",
        "nutrition_coverage_gap",
        "weight_trend_insufficient",
        "no_supported_action",
    ]
    title: str
    detail: str
    completed_at: datetime | None = None


class WeeklyCheckInCurrentResponse(BaseModel):
    week_start: date
    week_end: date
    submitted_on: date
    timezone: str
    existing: WeeklyCheckInResponse | None = None
    summary: WeeklyCheckInSummary
    progress_action: ProgressWeeklyActionResponse


class WeeklyCheckInHistoryResponse(BaseModel):
    items: list[WeeklyCheckInResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
