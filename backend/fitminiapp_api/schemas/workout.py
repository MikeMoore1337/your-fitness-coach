from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from fitminiapp_api.schemas.data_quality import TrainingDataSufficiency
from fitminiapp_api.schemas.program import (
    EquipmentIdentifier,
    ExercisePrescriptionPlan,
    PrescriptionGroupKind,
    PrescriptionRole,
)

RirValue = Literal["0", "1", "2", "3", "4+"]
SetKind = Literal["warmup", "working", "drop"]
RIR_DESCRIPTION = (
    "Optional repetitions-in-reserve category after the set; 4+ means many repetitions "
    "remained, not an exact value of four"
)
WorkoutAdaptationReason = Literal[
    "limited_time",
    "unavailable_equipment",
    "replace_exercise",
    "different_environment",
    "pain_or_injury",
]
WorkoutCompletionFeedback = Literal["easier_than_expected", "as_expected", "harder_than_expected"]
WorkoutPersonalRecordKind = Literal["max_load", "best_set_volume"]
WORKOUT_COMPLETION_NOTE_MAX_LENGTH = 500


class WorkoutAdaptationRequest(BaseModel):
    reason: WorkoutAdaptationReason
    time_budget_minutes: int | None = Field(default=None, ge=10, le=240)
    target_workout_exercise_id: int | None = Field(default=None, ge=1)
    replacement_exercise_id: int | None = Field(default=None, ge=1)
    available_equipment_ids: list[EquipmentIdentifier] | None = Field(
        default=None,
        max_length=9,
    )

    @model_validator(mode="after")
    def validate_reason_fields(self):
        if self.available_equipment_ids is not None and len(
            set(self.available_equipment_ids)
        ) != len(self.available_equipment_ids):
            raise ValueError("Список доступного оборудования не должен содержать повторы")
        if self.reason == "limited_time" and self.time_budget_minutes is None:
            raise ValueError("Для ограничения по времени укажите бюджет в минутах")
        if self.reason == "unavailable_equipment" and (
            self.target_workout_exercise_id is None or self.available_equipment_ids is None
        ):
            raise ValueError("Выберите упражнение и доступное оборудование")
        if self.reason == "different_environment" and self.available_equipment_ids is None:
            raise ValueError("Укажите оборудование, доступное в новом месте")
        if self.reason == "replace_exercise" and (
            self.target_workout_exercise_id is None
            or self.replacement_exercise_id is None
            or self.available_equipment_ids is None
        ):
            raise ValueError("Выберите упражнение, замену и доступное оборудование")
        return self


class WorkoutAdaptationApplyRequest(WorkoutAdaptationRequest):
    preview_token: str = Field(min_length=64, max_length=64)


class WorkoutAdaptationExercise(BaseModel):
    workout_exercise_id: int | None = None
    exercise_id: int
    title: str
    equipment_ids: list[str]
    prescribed_sets: int
    prescribed_reps: str
    rest_seconds: int
    sort_order: int
    superset_group: int | None = None
    prescription: ExercisePrescriptionPlan | None = None
    priority: Literal["core", "priority", "accessory"]


class WorkoutAdaptationChange(BaseModel):
    kind: Literal["removed", "replaced"]
    workout_exercise_id: int
    from_exercise_id: int
    from_title: str
    to_exercise_id: int | None = None
    to_title: str | None = None
    transfer: Literal["compatible_with_load_reset", "blocked"] | None = None
    load_reset_required: bool = False
    reason_keys: list[str] = Field(default_factory=list)


class WorkoutAdaptationPreviewResponse(BaseModel):
    status: Literal["preview", "no_changes", "safety_stop"]
    workout_id: int
    reason: WorkoutAdaptationReason
    ruleset_version: str
    original_estimated_minutes: int
    adapted_estimated_minutes: int
    time_budget_minutes: int | None = None
    changes: list[WorkoutAdaptationChange]
    original_exercises: list[WorkoutAdaptationExercise]
    adapted_exercises: list[WorkoutAdaptationExercise]
    warnings: list[str]
    message: str
    preview_token: str | None = None


class WorkoutAlternativeItem(BaseModel):
    exercise_id: int
    title: str
    equipment_ids: list[str]
    score: int | None = None
    reason_keys: list[str] = Field(default_factory=list)


class WorkoutSetCreate(BaseModel):
    workout_exercise_id: int
    set_number: int
    actual_reps: int | None = None
    actual_weight: float | None = None
    rir: RirValue | None = Field(default=None, description=RIR_DESCRIPTION)
    set_kind: SetKind | None = "working"
    reached_failure: bool | None = None
    is_completed: bool = True


class WorkoutSetUpdate(BaseModel):
    actual_reps: int | None = Field(default=None, ge=0)
    actual_weight: float | None = Field(default=None, ge=0)
    duration_minutes: int | None = Field(default=None, ge=1, le=600)
    distance_km: float | None = Field(default=None, gt=0, le=1000, allow_inf_nan=False)
    average_heart_rate_bpm: int | None = Field(default=None, ge=30, le=250)
    heart_rate_zone: int | None = Field(default=None, ge=1, le=5)
    rir: RirValue | None = Field(default=None, description=RIR_DESCRIPTION)
    set_kind: SetKind | None = None
    reached_failure: bool | None = None
    is_completed: bool | None = None
    expected_version: int | None = Field(default=None, ge=1)
    mutation_id: str | None = Field(default=None, min_length=16, max_length=64)

    @model_validator(mode="after")
    def validate_offline_sync_fields(self):
        if (self.expected_version is None) != (self.mutation_id is None):
            raise ValueError("expected_version и mutation_id должны передаваться вместе")
        return self


class LoggedSetItem(BaseModel):
    id: int
    set_number: int
    actual_reps: int | None = None
    actual_weight: float | None = None
    duration_minutes: int | None = None
    distance_km: float | None = None
    average_heart_rate_bpm: int | None = None
    heart_rate_zone: int | None = None
    rir: RirValue | None = Field(default=None, description=RIR_DESCRIPTION)
    set_kind: SetKind | None = None
    reached_failure: bool | None = None
    is_completed: bool = True
    version: int = Field(default=1, ge=1)
    planned_role: PrescriptionRole | None = None
    planned_group_id: int | None = None
    planned_group_kind: PrescriptionGroupKind | None = None
    planned_position: int | None = None
    planned_round: int | None = None


class ProgressionSessionEvidence(BaseModel):
    workout_id: int
    scheduled_date: date
    working_set_count: int = Field(ge=0)
    load: float | None = Field(default=None, ge=0)
    load_unit: Literal["kg", "lb"]
    reps_min: int | None = Field(default=None, ge=0)
    reps_max: int | None = Field(default=None, ge=0)
    rir_recorded_set_count: int = Field(ge=0)
    rir_values: list[RirValue]
    reached_failure: bool
    completion_feedback: WorkoutCompletionFeedback | None = None


class ProgressionEvidence(BaseModel):
    target_reps_min: int | None = Field(default=None, ge=1)
    target_reps_max: int | None = Field(default=None, ge=1)
    prescribed_sets: int = Field(ge=1)
    comparable_session_count: int = Field(ge=0)
    required_session_count: int = Field(ge=2)
    working_set_count: int = Field(ge=0)
    rir_recorded_set_count: int = Field(ge=0)
    reason_keys: list[str]
    sessions: list[ProgressionSessionEvidence]


class ProgressionGuidance(BaseModel):
    ruleset_version: Literal["progression-guidance-v1"]
    outcome: Literal["consider_progressing", "hold", "review", "consider_reducing"]
    message: str
    detail: str
    suggested_increment: float | None = None
    suggested_weight: float | None = Field(default=None, ge=0)
    load_unit: Literal["kg", "lb"]
    evidence: ProgressionEvidence


class WorkoutExerciseItem(BaseModel):
    id: int
    exercise_id: int
    exercise_title: str
    metric_type: Literal["strength", "cardio"]
    sort_order: int
    prescribed_sets: int
    prescribed_reps: str
    prescribed_duration_minutes: int | None = None
    rest_seconds: int
    notes: str | None = None
    superset_group: int | None = None
    superset_order: int | None = None
    prescription: ExercisePrescriptionPlan | None = None
    source_template_exercise_id: int | None = None
    source_weekly_prescription_id: int | None = None
    group_id: int | None = None
    group_kind: PrescriptionGroupKind | None = None
    group_order: int | None = None
    has_guide: bool = False
    media_state: Literal["approved_animated", "blocked"] | None = None
    media_thumbnail_url: str | None = None
    media_animation_url: str | None = None
    progression_guidance: ProgressionGuidance | None = None
    sets: list[LoggedSetItem]


class WorkoutCompletionExercise(BaseModel):
    workout_exercise_id: int
    exercise_id: int
    exercise_title: str
    metric_type: Literal["strength", "cardio"]
    completed_sets: int
    reps_total: int | None = None
    reps_recorded_sets: int
    max_load_kg: float | None = None
    load_recorded_sets: int
    duration_minutes: int | None = None
    distance_km: float | None = None
    average_heart_rate_bpm: int | None = None
    heart_rate_zone: int | None = None


class WorkoutPersonalRecord(BaseModel):
    exercise_id: int
    exercise_title: str
    kinds: list[WorkoutPersonalRecordKind]
    max_load_kg: float | None = None
    best_set_volume_kg: float | None = None


class WorkoutCompletionNextWorkout(BaseModel):
    id: int
    scheduled_date: date
    scheduled_time: time | None = None
    title: str


class WorkoutCompletionSummary(BaseModel):
    duration_seconds: int | None = Field(default=None, ge=0)
    performed_exercises: int = Field(ge=0)
    completed_sets: int = Field(ge=0)
    total_sets: int = Field(ge=0)
    reps_total: int | None = Field(default=None, ge=0)
    reps_recorded_sets: int = Field(ge=0)
    load_recorded_sets: int = Field(ge=0)
    exercises: list[WorkoutCompletionExercise]
    personal_records: list[WorkoutPersonalRecord]
    next_workout: WorkoutCompletionNextWorkout | None = None
    feedback: WorkoutCompletionFeedback | None = None
    note: str | None = None


class WorkoutTodayResponse(BaseModel):
    id: int
    scheduled_date: date
    scheduled_time: time | None = None
    title: str
    status: str
    day_number: int
    week_number: int = 1
    started_at: datetime | None = None
    completed_at: datetime | None = None
    exercises: list[WorkoutExerciseItem]
    completion_summary: WorkoutCompletionSummary | None = None


class WorkoutAdaptationApplyResponse(BaseModel):
    adaptation_id: int
    applied_at: datetime
    workout: WorkoutTodayResponse


class WorkoutStatusResponse(BaseModel):
    id: int
    set_number: int
    actual_reps: int | None = None
    actual_weight: float | None = None
    duration_minutes: int | None = None
    distance_km: float | None = None
    average_heart_rate_bpm: int | None = None
    heart_rate_zone: int | None = None
    rir: RirValue | None = Field(default=None, description=RIR_DESCRIPTION)
    set_kind: SetKind | None = None
    reached_failure: bool | None = None
    is_completed: bool
    version: int = Field(ge=1)
    planned_role: PrescriptionRole | None = None
    planned_group_id: int | None = None
    planned_group_kind: PrescriptionGroupKind | None = None
    planned_position: int | None = None
    planned_round: int | None = None


class WorkoutScheduleItem(BaseModel):
    id: int
    scheduled_date: date
    scheduled_time: time | None = None
    title: str
    status: str
    day_number: int
    week_number: int = 1


class WorkoutRescheduleRequest(BaseModel):
    scheduled_date: date
    scheduled_time: time | None = None


class WorkoutFinishRequest(BaseModel):
    confirm_incomplete: bool = False


class WorkoutCompletionFeedbackUpdate(BaseModel):
    feedback: WorkoutCompletionFeedback | None = None
    note: str | None = Field(default=None, max_length=WORKOUT_COMPLETION_NOTE_MAX_LENGTH)

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized:
            return None
        if any(ord(character) < 32 and character not in {"\n", "\t"} for character in normalized):
            raise ValueError("Заметка содержит недопустимые управляющие символы")
        return normalized


class WorkoutHistoryItem(BaseModel):
    id: int
    scheduled_date: date
    scheduled_time: time | None = None
    title: str
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    completed_sets: int
    volume_kg: float
    completion_feedback: WorkoutCompletionFeedback | None = None
    completion_note: str | None = None
    exercises: list[WorkoutHistoryExerciseItem]
    adaptations: list[WorkoutAdaptationHistoryItem]


class WorkoutHistoryExerciseItem(BaseModel):
    workout_exercise_id: int
    exercise_id: int
    title: str
    prescribed_sets: int
    prescribed_reps: str
    sort_order: int


class WorkoutAdaptationHistoryItem(BaseModel):
    id: int
    reason: Literal[
        "limited_time",
        "unavailable_equipment",
        "replace_exercise",
        "different_environment",
    ]
    ruleset_version: str
    applied_at: datetime
    changes: list[WorkoutAdaptationChange]


class WorkoutHistorySummary(BaseModel):
    workouts_completed: int
    completed_sets: int
    volume_kg: float


class ProgressWeightPoint(BaseModel):
    measured_on: date
    weight_kg: float


class ProgressVolumePoint(BaseModel):
    week_start: date
    completed_workouts: int
    volume_kg: float


class ExerciseProgressItem(BaseModel):
    exercise_id: int
    exercise_title: str
    max_weight_kg: float | None = None
    best_set_volume_kg: float
    last_performed_on: date


class WorkoutProgressResponse(BaseModel):
    workouts_total: int
    workouts_completed: int
    workouts_skipped: int
    workouts_missed: int
    adherence_percent: float
    current_streak: int
    weight_change_kg: float | None = None
    weights: list[ProgressWeightPoint]
    weekly_volume: list[ProgressVolumePoint]
    personal_records: list[ExerciseProgressItem]


class TrainingAnalyticsSet(BaseModel):
    model_config = ConfigDict(extra="allow")

    set_number: int
    reps: int | None = None
    external_load_kg: float | None = None
    external_load_volume_kg: float | None = None
    rir: RirValue | None = Field(default=None, description=RIR_DESCRIPTION)
    set_kind: SetKind | None = None
    reached_failure: bool | None = None


class ExerciseTrainingSession(BaseModel):
    workout_id: int
    workout_exercise_id: int
    performed_on: date
    completed_set_count: int
    reps_total: int | None = None
    reps_recorded_sets: int
    max_external_load_kg: float | None = None
    external_load_volume_kg: float | None = None
    volume_recorded_sets: int
    sets: list[TrainingAnalyticsSet]


class ExerciseTrainingProgression(BaseModel):
    exercise_id: int
    exercise_title: str
    uses_bodyweight_equipment: bool
    performed_session_count: int
    completed_set_count: int
    first_performed_on: date
    last_performed_on: date
    reps_total: int | None = None
    reps_recorded_sets: int
    max_external_load_kg: float | None = None
    best_set_volume_kg: float | None = None
    external_load_volume_kg: float | None = None
    volume_recorded_sets: int
    history_truncated: bool
    sessions: list[ExerciseTrainingSession]


class RirDistributionBucket(BaseModel):
    value: RirValue
    completed_set_count: int


class RirTrainingAnalytics(BaseModel):
    completed_set_count: int
    recorded_set_count: int
    missing_set_count: int
    distribution: list[RirDistributionBucket]


class MuscleSetExposure(BaseModel):
    muscle_id: str
    muscle_name: str
    completed_set_count: int


class TrainingAnalyticsResponse(BaseModel):
    period_days: int
    period_start: date
    period_end: date
    exercise_history_limit: int
    completed_set_count: int
    reps_total: int | None = None
    reps_recorded_sets: int
    external_load_volume_kg: float | None = None
    volume_recorded_sets: int
    exercises: list[ExerciseTrainingProgression]
    rir: RirTrainingAnalytics
    primary_muscle_exposure: list[MuscleSetExposure]
    secondary_muscle_exposure: list[MuscleSetExposure]
    completed_sets_without_muscle_metadata: int
    data_sufficiency: TrainingDataSufficiency


class WorkoutTimelineSet(BaseModel):
    model_config = ConfigDict(extra="allow")

    set_number: int
    actual_reps: int | None = None
    actual_weight: float | None = None
    rir: RirValue | None = Field(default=None, description=RIR_DESCRIPTION)
    set_kind: SetKind | None = None
    reached_failure: bool | None = None
    is_completed: bool


class WorkoutTimelineExercise(BaseModel):
    workout_exercise_id: int
    exercise_id: int
    exercise_title: str
    notes: str | None = None
    superset_group: int | None = None
    superset_order: int | None = None
    sets: list[WorkoutTimelineSet]


class WorkoutTimelineItem(BaseModel):
    id: int
    scheduled_date: date
    scheduled_time: time | None = None
    title: str
    status: str
    completed_at: datetime | None = None
    completed_sets: int
    volume_kg: float
    completion_feedback: WorkoutCompletionFeedback | None = None
    completion_note: str | None = None
    exercises: list[WorkoutTimelineExercise]


class BodyMeasurementCustomValueSave(BaseModel):
    definition_id: int = Field(ge=1)
    value: float | None = Field(default=None, gt=0, le=300, allow_inf_nan=False)


class BodyMeasurementDefinitionCreate(BaseModel):
    label: str = Field(min_length=1, max_length=64)

    @field_validator("label")
    @classmethod
    def normalize_label(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("Название показателя не может быть пустым")
        return normalized


class BodyMeasurementDefinitionUpdate(BodyMeasurementDefinitionCreate):
    pass


class BodyMeasurementDefinitionResponse(BaseModel):
    id: int
    label: str
    unit: Literal["cm"] = "cm"
    archived: bool
    created_at: datetime
    updated_at: datetime


class BodyMeasurementCustomValueResponse(BaseModel):
    definition_id: int
    label: str
    unit: Literal["cm"] = "cm"
    value: float
    archived: bool = False


class BodyMeasurementSave(BaseModel):
    measured_on: date | None = None
    weight_kg: float | None = Field(default=None, ge=20, le=350, allow_inf_nan=False)
    chest_cm: float | None = Field(default=None, gt=0, le=300, allow_inf_nan=False)
    waist_cm: float | None = Field(default=None, gt=0, le=300, allow_inf_nan=False)
    hips_cm: float | None = Field(default=None, gt=0, le=300, allow_inf_nan=False)
    biceps_cm: float | None = Field(default=None, gt=0, le=150, allow_inf_nan=False)
    thigh_cm: float | None = Field(default=None, gt=0, le=200, allow_inf_nan=False)
    note: str | None = Field(default=None, max_length=500)
    custom_values: list[BodyMeasurementCustomValueSave] = Field(default_factory=list, max_length=32)


class BodyMeasurementResponse(BaseModel):
    id: int
    measured_on: date
    weight_kg: float | None = None
    chest_cm: float | None = None
    waist_cm: float | None = None
    hips_cm: float | None = None
    biceps_cm: float | None = None
    thigh_cm: float | None = None
    note: str | None = None
    created_at: datetime | None = None
    custom_values: list[BodyMeasurementCustomValueResponse] = Field(default_factory=list)
