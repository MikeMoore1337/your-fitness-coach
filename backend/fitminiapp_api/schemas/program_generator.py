from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from fitminiapp_api.schemas.program import (
    EquipmentIdentifier,
    ExerciseMetricType,
    ExerciseMovementPattern,
    PrescriptionGroupKind,
    ProgramExperience,
    ProgramProvenanceType,
    ProgramRecommendationGoal,
    ProgramSplitType,
    ProgramTemplateResponse,
    TrainingLocation,
)


class ProgramGeneratorRequest(BaseModel):
    goal: ProgramRecommendationGoal
    experience: ProgramExperience
    days_per_week: int = Field(ge=2, le=6)
    preferred_session_duration_minutes: int = Field(ge=10, le=240)
    training_location: TrainingLocation
    available_equipment_ids: list[EquipmentIdentifier] = Field(default_factory=list, max_length=9)
    priority_muscle_ids: list[str] = Field(default_factory=list, max_length=20)
    preferred_exercise_ids: list[int] = Field(default_factory=list, max_length=32)
    excluded_exercise_ids: list[int] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_unique_inputs(self):
        collections = (
            ("available_equipment_ids", self.available_equipment_ids),
            ("priority_muscle_ids", self.priority_muscle_ids),
            ("preferred_exercise_ids", self.preferred_exercise_ids),
            ("excluded_exercise_ids", self.excluded_exercise_ids),
        )
        for name, values in collections:
            if len(set(values)) != len(values):
                raise ValueError(f"{name} must be unique")
        if set(self.preferred_exercise_ids) & set(self.excluded_exercise_ids):
            raise ValueError("an exercise cannot be both preferred and excluded")
        return self


class ProgramGeneratorConfirmRequest(BaseModel):
    draft_token: str = Field(min_length=1, max_length=16_384)
    start_date: date | None = None
    duration_weeks: int | None = Field(default=None, ge=1, le=24)
    replace_active: bool = False


class ProgramGeneratorSource(BaseModel):
    template_id: int
    slug: str
    title: str
    goal: ProgramRecommendationGoal
    level: ProgramExperience
    split_type: ProgramSplitType | None = None
    provenance_type: ProgramProvenanceType = "CUSTOM"


class ProgramGeneratorExercise(BaseModel):
    exercise_id: int
    exercise_title: str
    metric_type: ExerciseMetricType
    movement_pattern: ExerciseMovementPattern | None = None
    prescribed_sets: int
    prescribed_reps: str
    prescribed_duration_minutes: int | None = None
    rest_seconds: int
    notes: str | None = None
    superset_group: int | None = None
    superset_order: int | None = None
    prescription: dict[str, object] | None = None
    group_id: int | None = None
    group_kind: PrescriptionGroupKind | None = None
    group_order: int | None = None
    source_exercise_id: int | None = None


class ProgramGeneratorDay(BaseModel):
    day_number: int
    title: str
    estimated_duration_minutes: int
    exercises: list[ProgramGeneratorExercise]


class ProgramGeneratorProgram(BaseModel):
    title: str
    goal: ProgramRecommendationGoal
    level: ProgramExperience
    split_type: ProgramSplitType | None = None
    days: list[ProgramGeneratorDay]
    estimated_duration_minutes: int


class ProgramGeneratorAdaptation(BaseModel):
    code: Literal[
        "equipment_substitution",
        "duration_accessory_reduction",
        "schedule_representation",
    ]
    message: str
    day_number: int | None = None
    source_exercise_id: int | None = None
    replacement_exercise_id: int | None = None


class ProgramGeneratorActiveProgram(BaseModel):
    program_id: int
    revision_number: int
    status: Literal["scheduled", "active", "paused", "completed", "terminated", "archived"]
    assigned_by_user_id: int | None = None
    trainer_owned: bool = False


class ProgramGeneratorPreviewResponse(BaseModel):
    status: Literal["preview", "no_compatible"]
    selection_policy_version: str
    input_fingerprint: str
    message: str
    draft_token: str | None = None
    source: ProgramGeneratorSource | None = None
    program: ProgramGeneratorProgram | None = None
    fit_reasons: list[str] = Field(default_factory=list)
    tradeoffs: list[str] = Field(default_factory=list)
    adaptations: list[ProgramGeneratorAdaptation] = Field(default_factory=list)
    unresolved_constraints: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    active_program: ProgramGeneratorActiveProgram | None = None


class ProgramGeneratorConfirmResponse(BaseModel):
    status: Literal["confirmed"]
    idempotent: bool = False
    assigned_program_id: int
    workouts_created: int
    template: ProgramTemplateResponse
