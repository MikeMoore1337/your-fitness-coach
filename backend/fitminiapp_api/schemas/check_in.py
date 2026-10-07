from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from fitminiapp_api.schemas.data_quality import ProgressDataSufficiency
from fitminiapp_api.schemas.food_diary import FoodDiaryNutrition, FoodDiaryTargets
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
    planning_review: WeeklyPlanningReviewSummary | None = None


class WeeklyPlanningDaySummary(BaseModel):
    diary_date: date
    observed: bool
    plan_status: Literal["no_plan", "planned", "partial", "complete"]
    plan_revision: int = Field(ge=0)
    planned_items: int = Field(ge=0)
    consumed_items: int = Field(ge=0)
    pending_items: int = Field(ge=0)
    skipped_items: int = Field(ge=0)
    planned: FoodDiaryNutrition
    consumed: FoodDiaryNutrition | None = None
    target: FoodDiaryTargets | None = None


class WeeklyPlanningProposal(BaseModel):
    source_date: date
    target_date: date
    source_revision: int = Field(ge=0)
    target_revision: int = Field(ge=0)
    pending_item_count: int = Field(gt=0)
    target_item_count: int = Field(ge=0)


class WeeklyPlanningReviewSummary(BaseModel):
    week_start: date
    week_end: date
    availability: Literal["available", "no_plan", "no_target", "no_data"]
    days: list[WeeklyPlanningDaySummary]
    planned_days: int = Field(ge=0)
    target_days: int = Field(ge=0)
    consumed_days: int = Field(ge=0)
    pending_days: int = Field(ge=0)
    repeated_miss_dates: list[date] = Field(default_factory=list)
    planned_total: FoodDiaryNutrition
    consumed_total: FoodDiaryNutrition | None = None
    target_total: FoodDiaryTargets | None = None
    proposals: list[WeeklyPlanningProposal] = Field(default_factory=list)


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


class WeeklyPlanningAdjustment(BaseModel):
    source_date: date
    target_date: date
    source_revision: int = Field(ge=0)
    target_revision: int = Field(ge=0)

    @model_validator(mode="after")
    def require_next_week_target(self) -> WeeklyPlanningAdjustment:
        if self.target_date != self.source_date + timedelta(days=7):
            raise ValueError("planning adjustments must target the same weekday next week")
        return self


class WeeklyPlanningReviewConfirmRequest(BaseModel):
    week_start: date
    adjustments: list[WeeklyPlanningAdjustment] = Field(min_length=1, max_length=7)

    @model_validator(mode="after")
    def validate_week_and_dates(self) -> WeeklyPlanningReviewConfirmRequest:
        if self.week_start.weekday() != 0:
            raise ValueError("week_start must be a Monday")
        source_dates = [item.source_date for item in self.adjustments]
        if len(source_dates) != len(set(source_dates)):
            raise ValueError("planning adjustments must use unique source dates")
        week_end = self.week_start + timedelta(days=6)
        if any(
            item.source_date < self.week_start or item.source_date > week_end
            for item in self.adjustments
        ):
            raise ValueError("planning adjustments must belong to the selected week")
        return self


class WeeklyPlanningReviewConfirmResponse(BaseModel):
    week_start: date
    week_end: date
    replayed: bool
    planning_review: WeeklyPlanningReviewSummary


class WeeklyCheckInHistoryResponse(BaseModel):
    items: list[WeeklyCheckInResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
