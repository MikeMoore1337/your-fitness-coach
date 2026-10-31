from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from fitminiapp_api.schemas.program import PrescriptionRole
from fitminiapp_api.schemas.workout import (
    SetKind,
    WorkoutExecutionMode,
    WorkoutSide,
    WorkoutSideResults,
)


class WorkoutCopySet(BaseModel):
    set_number: int
    actual_reps: int | None = None
    actual_weight: float | None = None
    duration_minutes: int | None = None
    distance_km: float | None = None
    average_heart_rate_bpm: int | None = None
    heart_rate_zone: int | None = None
    set_kind: SetKind | None = None
    planned_role: PrescriptionRole | None = None
    is_completed: bool = True
    execution_mode: WorkoutExecutionMode | None = None
    first_side: WorkoutSide | None = None
    sides: WorkoutSideResults | None = None


class WorkoutCopyExercise(BaseModel):
    exercise_title: str
    metric_type: Literal["strength", "cardio"]
    sort_order: int
    sets: list[WorkoutCopySet]


class WorkoutCopyResponse(BaseModel):
    title: str
    scheduled_date: date
    completed_at: datetime | None = None
    exercises: list[WorkoutCopyExercise]
