from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from fitminiapp_api.schemas.coach_crm import CoachTaskResponse

ReviewWorkspaceState = Literal["available", "partial", "no_data"]


class CoachReviewTrainingFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planned_workouts: int | None = Field(default=None, ge=0)
    completed_workouts: int | None = Field(default=None, ge=0)
    adherence_percent: float | None = Field(default=None, ge=0, le=100)
    volume_kg: float | None = Field(default=None, ge=0)
    training_load: int | None = Field(default=None, ge=1, le=5)
    recovery: int | None = Field(default=None, ge=1, le=5)
    adherence_difficulty: int | None = Field(default=None, ge=1, le=5)


class CoachReviewProgressionFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    training_volume_kg: float | None = Field(default=None, ge=0)
    new_personal_records: int | None = Field(default=None, ge=0)


class CoachReviewNutritionFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    logged_days: int | None = Field(default=None, ge=0)
    complete_days: int | None = Field(default=None, ge=0)
    average_calories: float | None = Field(default=None, ge=0)
    target_calories: int | None = Field(default=None, ge=0)
    average_protein_g: float | None = Field(default=None, ge=0)
    target_protein_g: int | None = Field(default=None, ge=0)


class CoachReviewMeasurementFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weight_kg: float | None = Field(default=None, ge=0)
    weight_change_kg: float | None = None
    waist_cm: float | None = Field(default=None, ge=0)
    latest_measured_on: date | None = None


class CoachReviewCheckInSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(gt=0)
    week_start: date
    week_end: date
    submitted_on: date
    status: Literal["completed", "skipped"]
    training: CoachReviewTrainingFacts
    progression: CoachReviewProgressionFacts
    nutrition: CoachReviewNutritionFacts
    measurements: CoachReviewMeasurementFacts


class CoachReviewProgram(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=128)
    status: Literal["scheduled", "active", "paused", "completed", "terminated", "archived"]
    start_date: date
    duration_weeks: int = Field(ge=1)
    current_revision_number: int = Field(ge=0)
    workouts_total: int = Field(ge=0)
    workouts_completed: int = Field(ge=0)
    next_workout_date: date | None = None


class CoachReviewPrivateNote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: int = Field(gt=0)
    starts_at_utc: datetime
    status: Literal["scheduled", "completed", "cancelled", "no_show"]
    text: str = Field(min_length=1, max_length=2000)


class CoachReviewChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: Literal["training", "progression", "nutrition", "measurements"]
    key: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=128)
    previous: float | int | None = None
    current: float | int | None = None


class CoachReviewActionState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_status: Literal["pending", "reviewed", "no_check_in"]
    review_response: str | None = Field(default=None, max_length=2000)
    reviewed_at: datetime | None = None
    follow_up: CoachTaskResponse | None = None
    program_proposals: list[CoachTaskResponse] = Field(default_factory=list, max_length=20)
    next_reviews: list[CoachTaskResponse] = Field(default_factory=list, max_length=20)


class CoachReviewWorkspaceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: int = Field(gt=0)
    client_name: str = Field(min_length=1, max_length=128)
    state: ReviewWorkspaceState
    previous_check_in: CoachReviewCheckInSnapshot | None = None
    current_check_in: CoachReviewCheckInSnapshot | None = None
    training_actuals: CoachReviewTrainingFacts
    progression_facts: CoachReviewProgressionFacts
    nutrition: CoachReviewNutritionFacts
    measurements: CoachReviewMeasurementFacts
    current_program: CoachReviewProgram | None = None
    private_notes: list[CoachReviewPrivateNote] = Field(default_factory=list, max_length=10)
    meaningful_changes: list[CoachReviewChange] = Field(default_factory=list, max_length=20)
    actions: CoachReviewActionState


__all__ = [
    "CoachReviewActionState",
    "CoachReviewChange",
    "CoachReviewCheckInSnapshot",
    "CoachReviewMeasurementFacts",
    "CoachReviewNutritionFacts",
    "CoachReviewPrivateNote",
    "CoachReviewProgram",
    "CoachReviewProgressionFacts",
    "CoachReviewTrainingFacts",
    "CoachReviewWorkspaceResponse",
    "ReviewWorkspaceState",
]
