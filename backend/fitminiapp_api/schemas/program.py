from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from fitminiapp_api.schemas.nutrition import NutritionTargetResponse
from fitminiapp_api.schemas.user import BodyPriorityPreference, TrainingPreferencesResponse

ProgramRecommendationGoal = Literal[
    "fat_loss", "recomposition", "maintenance", "muscle_gain", "strength"
]
ProgramExperience = Literal["beginner", "intermediate", "advanced"]
ProgramSplitType = Literal["full_body", "upper_lower", "push_pull_legs", "body_part", "hybrid"]
ProgramProvenanceType = Literal["YFC_GENERIC", "SOURCE_ADAPTATION", "CUSTOM"]
TrainingLocation = Literal["gym", "home", "other"]
EquipmentIdentifier = Literal[
    "bodyweight",
    "dumbbell",
    "barbell",
    "bench",
    "cable",
    "machine",
    "kettlebell",
    "cardio",
    "other",
]
ExerciseMetricType = Literal["strength", "cardio"]
ExerciseMovementPattern = Literal[
    "anti_extension",
    "anti_rotation",
    "arm_curl",
    "calf",
    "cardio_row",
    "carry",
    "chest_fly",
    "chest_press",
    "conditioning",
    "cycling",
    "glute",
    "grip",
    "hinge",
    "leg_isolation",
    "lunge",
    "pullover",
    "row",
    "running",
    "olympic_lift",
    "shoulder_raise",
    "shoulder_press",
    "shoulder_rotation",
    "squat",
    "trunk_flexion",
    "trunk_rotation",
    "triceps",
    "vertical_pull",
    "wrist",
]
ExerciseMachineVariantTag = Literal[
    "selectorized",
    "plate_loaded",
    "lever",
    "independent",
    "converging",
    "diverging",
    "smith",
]
ExerciseExecutionVariantTag = Literal[
    "bilateral",
    "unilateral",
    "alternating",
    "isometric",
    "cyclic",
    "multi_stage",
]

PrescriptionRole = Literal[
    "warmup",
    "working",
    "top",
    "backoff",
    "drop",
    "activation",
    "mini_set",
    "cluster_member",
]
PrescriptionGroupKind = Literal[
    "sequence",
    "superset",
    "rest_pause",
    "myo_reps",
    "cluster",
    "drop_chain",
    "circuit",
]
PrescriptionLoadKind = Literal[
    "user_selected",
    "absolute",
    "percent_1rm",
    "percent_training_max",
    "relative_to_top",
    "relative_to_previous",
]
PrescriptionEffortKind = Literal["none", "rir", "rpe", "failure"]


class PrescriptionRepTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["exact", "range", "amrap"]
    value: int | None = Field(default=None, ge=1, le=1_000)
    min_reps: int | None = Field(default=None, ge=1, le=1_000)
    max_reps: int | None = Field(default=None, ge=1, le=1_000)
    cap_reps: int | None = Field(default=None, ge=1, le=1_000)

    @model_validator(mode="after")
    def validate_shape(self):
        if self.kind == "exact" and self.value is None:
            raise ValueError("exact rep target requires value")
        if self.kind == "range" and (
            self.min_reps is None or self.max_reps is None or self.max_reps < self.min_reps
        ):
            raise ValueError("range rep target requires an ordered min/max")
        if self.kind != "exact" and self.value is not None:
            raise ValueError("value is only valid for an exact rep target")
        if self.kind != "range" and (self.min_reps is not None or self.max_reps is not None):
            raise ValueError("min_reps/max_reps are only valid for a range rep target")
        if self.kind != "amrap" and self.cap_reps is not None:
            raise ValueError("cap_reps is only valid for an AMRAP target")
        return self


class PrescriptionDurationTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["exact", "range"] = "exact"
    value_minutes: int | None = Field(default=None, ge=1, le=600)
    min_minutes: int | None = Field(default=None, ge=1, le=600)
    max_minutes: int | None = Field(default=None, ge=1, le=600)

    @model_validator(mode="after")
    def validate_shape(self):
        if self.kind == "exact" and self.value_minutes is None:
            raise ValueError("exact duration target requires value_minutes")
        if self.kind == "range" and (
            self.min_minutes is None
            or self.max_minutes is None
            or self.max_minutes < self.min_minutes
        ):
            raise ValueError("range duration target requires an ordered min/max")
        if self.kind != "exact" and self.value_minutes is not None:
            raise ValueError("value_minutes is only valid for an exact duration target")
        if self.kind != "range" and (self.min_minutes is not None or self.max_minutes is not None):
            raise ValueError("min_minutes/max_minutes are only valid for a range target")
        return self


class PrescriptionLoadTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: PrescriptionLoadKind = "user_selected"
    value: float | None = Field(default=None, ge=0, le=100_000)

    @model_validator(mode="after")
    def validate_value(self):
        if self.kind == "user_selected" and self.value is not None:
            raise ValueError("user_selected load must not carry a fixed value")
        if self.kind != "user_selected" and self.value is None:
            raise ValueError("non-user-selected load requires value")
        if (
            self.kind in {"percent_1rm", "percent_training_max"}
            and self.value is not None
            and self.value > 200
        ):
            raise ValueError(f"{self.kind} must not exceed 200")
        return self


class PrescriptionEffortTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: PrescriptionEffortKind = "none"
    value: float | Literal["4+"] | None = None

    @model_validator(mode="after")
    def validate_value(self):
        if self.kind in {"none", "failure"} and self.value is not None:
            raise ValueError("this effort target does not accept a value")
        if self.kind == "rir" and not (
            (isinstance(self.value, (int, float)) and 0 <= float(self.value) <= 10)
            or self.value == "4+"
        ):
            raise ValueError("RIR must be between 0 and 10 or 4+")
        if self.kind == "rpe" and not (
            isinstance(self.value, (int, float)) and 1 <= float(self.value) <= 10
        ):
            raise ValueError("RPE must be between 1 and 10")
        return self


class PrescriptionSegment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: int = Field(ge=1, le=100)
    role: PrescriptionRole
    rep_target: PrescriptionRepTarget | None = None
    duration_target: PrescriptionDurationTarget | None = None
    load_target: PrescriptionLoadTarget = Field(default_factory=PrescriptionLoadTarget)
    effort_target: PrescriptionEffortTarget = Field(default_factory=PrescriptionEffortTarget)
    rest_after_seconds: int = Field(default=90, ge=0, le=600)
    group_id: int | None = Field(default=None, ge=1)
    group_position: int | None = Field(default=None, ge=1, le=100)
    round_number: int | None = Field(default=None, ge=1, le=100)


class PrescriptionGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_id: int = Field(ge=1)
    kind: PrescriptionGroupKind
    intra_group_rest_seconds: int = Field(default=0, ge=0, le=600)
    rest_after_group_seconds: int = Field(default=90, ge=0, le=600)
    rounds: int | None = Field(default=None, ge=1, le=100)
    exercise_slot: int | None = Field(default=None, ge=1, le=20)


class ExercisePrescriptionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    metric_type: ExerciseMetricType
    segments: list[PrescriptionSegment] = Field(min_length=1, max_length=100)
    groups: list[PrescriptionGroup] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_plan(self):
        positions = [segment.position for segment in self.segments]
        if positions != list(range(1, len(positions) + 1)):
            raise ValueError("prescription segment positions must be contiguous and ordered")
        group_ids = {group.group_id for group in self.groups}
        if len(group_ids) != len(self.groups):
            raise ValueError("prescription group ids must be unique")
        for segment in self.segments:
            if self.metric_type == "strength":
                if segment.rep_target is None or segment.duration_target is not None:
                    raise ValueError("strength segments require rep targets only")
            elif segment.duration_target is None or segment.rep_target is not None:
                raise ValueError("cardio segments require duration targets only")
            if segment.group_id is not None and segment.group_id not in group_ids:
                raise ValueError("segment references an unknown prescription group")
            if segment.group_id is not None and segment.group_position is None:
                raise ValueError("grouped segments require group_position")
        return self


class ProgramTemplateExerciseCreate(BaseModel):
    exercise_id: int = Field(ge=1)
    prescribed_sets: int | None = Field(default=None, ge=1, le=10)
    prescribed_reps: str | None = Field(default=None, min_length=1, max_length=32)
    prescribed_duration_minutes: int | None = Field(default=None, ge=1, le=600)
    rest_seconds: int = Field(default=90, ge=0, le=600)
    notes: str | None = Field(default=None, max_length=2000)
    superset_group: int | None = Field(default=None, ge=1)
    superset_order: int | None = Field(default=None, ge=1, le=2)
    prescription: ExercisePrescriptionPlan | None = None
    group_id: int | None = Field(default=None, ge=1)
    group_kind: PrescriptionGroupKind | None = None
    group_order: int | None = Field(default=None, ge=1, le=100)

    @model_validator(mode="after")
    def validate_superset_pair(self):
        if (self.superset_group is None) != (self.superset_order is None):
            raise ValueError("superset_group and superset_order must be provided together")
        group_values = (self.group_id, self.group_kind, self.group_order)
        if any(value is not None for value in group_values) and any(
            value is None for value in group_values
        ):
            raise ValueError("group_id, group_kind and group_order must be provided together")
        return self


class ProgramTemplateDayCreate(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    exercises: list[ProgramTemplateExerciseCreate] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_supersets(self):
        groups: dict[int, list[int]] = {}
        for exercise in self.exercises:
            if exercise.superset_group is not None and exercise.superset_order is not None:
                groups.setdefault(exercise.superset_group, []).append(exercise.superset_order)
        if any(sorted(orders) != [1, 2] for orders in groups.values()):
            raise ValueError("each superset must contain exactly two exercises ordered 1 and 2")
        return self


class ProgramTemplateCreate(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    goal: ProgramRecommendationGoal
    level: Literal["beginner", "intermediate", "advanced"]
    mode: Literal["self", "coach"] = "self"
    target_telegram_user_id: int | None = Field(default=None, ge=1)
    target_full_name: str | None = Field(default=None, max_length=128)
    days: list[ProgramTemplateDayCreate] = Field(min_length=1, max_length=8)
    assign_after_create: bool = True
    start_date: date | None = None
    duration_weeks: int = Field(default=1, ge=1, le=24)
    schedule_weekdays: list[int] | None = Field(default=None, min_length=1, max_length=7)
    replace_active: bool = False

    @model_validator(mode="after")
    def validate_assignment_schedule(self):
        if self.schedule_weekdays is None:
            return self
        if len(self.schedule_weekdays) != len(self.days):
            raise ValueError("schedule_weekdays must contain one weekday per program day")
        if any(day < 0 or day > 6 for day in self.schedule_weekdays):
            raise ValueError("schedule_weekdays values must be between 0 and 6")
        if len(set(self.schedule_weekdays)) != len(self.schedule_weekdays):
            raise ValueError("schedule_weekdays must be unique")
        return self


class ProgramTemplateExerciseWeekResponse(BaseModel):
    exercise_id: int = Field(ge=1)
    week_number: int = Field(ge=1, le=24)
    prescribed_sets: int = Field(ge=1, le=10)
    prescribed_reps: str = Field(max_length=32)
    prescribed_duration_minutes: int | None = Field(default=None, ge=1, le=600)
    rest_seconds: int = Field(ge=0, le=600)
    prescription: ExercisePrescriptionPlan | None = None


class ProgramTemplateExerciseResponse(BaseModel):
    id: int
    exercise_id: int
    exercise_title: str
    metric_type: ExerciseMetricType
    prescribed_sets: int
    prescribed_reps: str
    prescribed_duration_minutes: int | None = None
    rest_seconds: int
    notes: str | None = None
    superset_group: int | None = None
    superset_order: int | None = None
    prescription: ExercisePrescriptionPlan | None = None
    group_id: int | None = None
    group_kind: PrescriptionGroupKind | None = None
    group_order: int | None = None
    has_guide: bool = False
    weekly_prescriptions: list[ProgramTemplateExerciseWeekResponse] = Field(default_factory=list)


class ProgramTemplateDayResponse(BaseModel):
    id: int
    day_number: int
    title: str
    exercises: list[ProgramTemplateExerciseResponse]


class ProgramTemplateResponse(BaseModel):
    id: int
    title: str
    slug: str
    goal: str
    level: str
    split_type: ProgramSplitType | None = None
    owner_user_id: int | None = None
    owner_telegram_user_id: int | None = None
    owner_full_name: str | None = None
    created_by_user_id: int | None = None
    is_public: bool = False
    is_example: bool = False
    is_assigned_to_current_user: bool = False
    is_active_for_current_user: bool = False
    can_edit: bool = False
    assigned_by_user_id: int | None = None
    assigned_by_full_name: str | None = None
    assigned_program_id: int | None = None
    assigned_program_status: Literal["scheduled", "active", "completed", "archived"] | None = None
    assigned_program_start_date: date | None = None
    assigned_program_duration_weeks: int | None = None
    current_revision_number: int | None = None
    default_duration_weeks: int = Field(default=1, ge=1, le=24)
    provenance_type: ProgramProvenanceType = "CUSTOM"
    provenance: dict[str, object] | None = None
    program_metadata: dict[str, object] | None = None
    days: list[ProgramTemplateDayResponse]


class ProgramRecommendationRequest(BaseModel):
    goal: ProgramRecommendationGoal | None = None
    experience: ProgramExperience | None = None
    workouts_per_week: int | None = Field(default=None, ge=1, le=8)
    training_location: TrainingLocation | None = None
    available_equipment_ids: list[EquipmentIdentifier] | None = Field(
        default=None,
        max_length=9,
    )

    @model_validator(mode="after")
    def validate_equipment_is_unique(self):
        if self.available_equipment_ids is not None and len(
            set(self.available_equipment_ids)
        ) != len(self.available_equipment_ids):
            raise ValueError("available_equipment_ids must be unique")
        return self


class ProgramRecommendationCriteria(BaseModel):
    goal: ProgramRecommendationGoal | None = None
    experience: ProgramExperience | None = None
    workouts_per_week: int | None = None
    training_location: TrainingLocation | None = None
    available_equipment_ids: list[EquipmentIdentifier] | None = None
    profile_fields_used: list[
        Literal[
            "goal",
            "experience",
            "workouts_per_week",
            "training_location",
            "available_equipment",
            "preferred_exercises",
            "avoided_exercises",
        ]
    ]


class ProgramRecommendationItem(BaseModel):
    template: ProgramTemplateResponse
    reason: str
    fit_facts: list[str]
    limitations: list[str]


class ProgramRecommendationResponse(BaseModel):
    status: Literal["recommended", "needs_input", "no_match"]
    criteria: ProgramRecommendationCriteria
    missing_fields: list[Literal["goal", "experience", "workouts_per_week"]]
    message: str
    recommendation: ProgramRecommendationItem | None = None
    alternatives: list[ProgramRecommendationItem] = Field(default_factory=list)
    requires_explicit_start: bool = True


class ProgramTargetUserResponse(BaseModel):
    id: int
    telegram_user_id: int | None = None
    full_name: str | None = None


class ProgramTemplateCreateResponse(BaseModel):
    template: ProgramTemplateResponse
    assigned_program_id: int | None = None
    workouts_created: int = 0
    target_user: ProgramTargetUserResponse


class ProgramAssignmentResponse(BaseModel):
    user_program_id: int
    workouts_created: int
    status: Literal["scheduled", "active", "completed", "archived"]
    start_date: date
    duration_weeks: int


class CoachAssignedProgramResponse(BaseModel):
    id: int
    client_id: int
    client_telegram_user_id: int | None = None
    client_username: str | None = None
    client_full_name: str | None = None
    template_id: int | None = None
    title: str
    goal: str | None = None
    level: str | None = None
    assigned_at: datetime
    is_active: bool
    status: Literal["scheduled", "active", "completed", "archived"]
    start_date: date
    duration_weeks: int
    schedule_weekdays: list[int]
    completed_at: datetime | None = None
    workouts_total: int
    workouts_completed: int
    workouts_planned: int
    next_workout_date: date | None = None
    current_revision_number: int


ProgramRevisionActorRole = Literal["self", "trainer", "admin", "system"]
ProgramRevisionChangeKind = Literal[
    "assigned",
    "program_archived",
    "plan_updated",
    "block_created",
    "block_updated",
    "block_status_changed",
    "exercise_replaced",
    "prescription_updated",
]
TrainingBlockStatus = Literal["planned", "active", "completed", "archived"]


class ProgramRevisionResponse(BaseModel):
    id: int
    user_program_id: int
    revision_number: int
    changed_by_user_id: int | None = None
    actor_role: ProgramRevisionActorRole
    change_kind: ProgramRevisionChangeKind
    reason: str | None = None
    changed_fields: dict
    snapshot: dict
    created_at: datetime


class TrainingBlockCreate(BaseModel):
    expected_revision_number: int = Field(ge=0)
    title: str = Field(min_length=1, max_length=128)
    start_date: date
    end_date: date
    purpose: str = Field(min_length=1, max_length=500)
    priority_muscle_ids: list[str] = Field(default_factory=list, max_length=20)
    notes: str | None = Field(default=None, max_length=2000)
    is_deload: bool = False
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_dates_and_muscles(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        if len(set(self.priority_muscle_ids)) != len(self.priority_muscle_ids):
            raise ValueError("priority_muscle_ids must be unique")
        return self


class TrainingBlockUpdate(BaseModel):
    expected_revision_number: int = Field(ge=0)
    title: str | None = Field(default=None, min_length=1, max_length=128)
    start_date: date | None = None
    end_date: date | None = None
    purpose: str | None = Field(default=None, min_length=1, max_length=500)
    priority_muscle_ids: list[str] | None = Field(default=None, max_length=20)
    notes: str | None = Field(default=None, max_length=2000)
    is_deload: bool | None = None
    status: TrainingBlockStatus | None = None
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_update(self):
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.end_date < self.start_date
        ):
            raise ValueError("end_date must be on or after start_date")
        if self.priority_muscle_ids is not None and len(set(self.priority_muscle_ids)) != len(
            self.priority_muscle_ids
        ):
            raise ValueError("priority_muscle_ids must be unique")
        change_fields = self.model_fields_set - {"expected_revision_number", "reason"}
        if not change_fields:
            raise ValueError("at least one block field must be changed")
        return self


class TrainingBlockResponse(BaseModel):
    id: int
    user_program_id: int
    title: str
    start_date: date
    end_date: date
    duration_days: int
    purpose: str
    priority_muscle_ids: list[str]
    notes: str | None = None
    is_deload: bool
    status: TrainingBlockStatus
    created_by_user_id: int | None = None
    created_at: datetime
    updated_at: datetime | None = None


class TrainingBlockMutationResponse(BaseModel):
    block: TrainingBlockResponse
    current_revision_number: int


class CoachProgramExerciseCreate(BaseModel):
    expected_revision_number: int = Field(ge=0)
    exercise_id: int = Field(ge=1)
    day_number: int | None = Field(default=None, ge=1, le=14)
    prescribed_sets: int | None = Field(default=None, ge=1, le=10)
    prescribed_reps: str | None = Field(default=None, min_length=1, max_length=32)
    prescribed_duration_minutes: int | None = Field(default=None, ge=1, le=600)
    rest_seconds: int = Field(default=90, ge=0, le=600)
    notes: str | None = Field(default=None, max_length=2000)
    superset_group: int | None = Field(default=None, ge=1)
    superset_order: int | None = Field(default=None, ge=1, le=2)
    prescription: ExercisePrescriptionPlan | None = None
    group_id: int | None = Field(default=None, ge=1)
    group_kind: PrescriptionGroupKind | None = None
    group_order: int | None = Field(default=None, ge=1, le=100)
    target_template_exercise_id: int | None = Field(default=None, ge=1)
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_superset_pair(self):
        if (self.superset_group is None) != (self.superset_order is None):
            raise ValueError("superset_group and superset_order must be provided together")
        group_values = (self.group_id, self.group_kind, self.group_order)
        if any(value is not None for value in group_values) and any(
            value is None for value in group_values
        ):
            raise ValueError("group_id, group_kind and group_order must be provided together")
        return self


class CoachProgramExerciseAssignmentResponse(BaseModel):
    workouts_updated: int
    current_revision_number: int


class TemplateExerciseReplacementRequest(BaseModel):
    replacement_exercise_id: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=500)


class AssignTemplateRequest(BaseModel):
    target_telegram_user_id: int = Field(ge=1)
    target_full_name: str | None = Field(default=None, max_length=128)


class AssignmentScheduleRequest(BaseModel):
    start_date: date | None = None
    duration_weeks: int = Field(default=1, ge=1, le=24)
    schedule_weekdays: list[int] | None = Field(default=None, min_length=1, max_length=7)
    replace_active: bool = False

    @model_validator(mode="after")
    def validate_weekdays(self):
        weekdays = self.schedule_weekdays
        if weekdays is None:
            return self
        if any(day < 0 or day > 6 for day in weekdays):
            raise ValueError("schedule_weekdays values must be between 0 and 6")
        if len(set(weekdays)) != len(weekdays):
            raise ValueError("schedule_weekdays must be unique")
        return self


class AssignTemplateSelfRequest(AssignmentScheduleRequest):
    pass


class AssignTemplateToClientRequest(AssignmentScheduleRequest):
    pass


class ProgramAssignedResponse(BaseModel):
    program_id: int
    title: str
    workouts_created: int


class ExerciseGuideMuscle(BaseModel):
    identifier: str | None = None
    name: str
    role_id: Literal["primary", "secondary"]
    role: str
    function: str


class ExerciseTaxonomyItem(BaseModel):
    identifier: str
    name: str


class ExerciseAlternativeItem(BaseModel):
    id: int
    slug: str
    title: str


class ExerciseGuideImage(BaseModel):
    phase: str
    url: str
    alt: str


class ExerciseGuideMediaSource(BaseModel):
    url: str
    mime_type: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    byte_size: int = Field(gt=0)


class ExerciseGuideMedia(BaseModel):
    type: Literal["image", "animation"]
    url: str
    poster: str
    phase_id: str
    phase: str
    alt: str
    asset_id: str | None = None
    asset_version: str | None = None
    variant_key: str | None = None
    source_name: str
    source_url: str
    source_license: str
    source_license_url: str | None = None
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    byte_size: int = Field(gt=0)
    sort_order: int = Field(ge=0)
    sources: list[ExerciseGuideMediaSource] = Field(min_length=1)


class ExerciseGuide(BaseModel):
    technique_steps: list[str]
    breathing: str
    common_mistakes: list[str]
    muscles: list[ExerciseGuideMuscle]
    equipment: list[ExerciseTaxonomyItem]
    safety_notes: list[str]
    alternatives: list[ExerciseAlternativeItem]
    media: list[ExerciseGuideMedia]
    images: list[ExerciseGuideImage]
    media_reference: str
    source_name: str
    source_url: str
    source_license: str
    source_license_url: str | None = None


class ExerciseCatalogItem(BaseModel):
    id: int
    title: str
    primary_muscle: str | None = None
    equipment: str | None = None
    metric_type: ExerciseMetricType
    primary_muscle_ids: list[str]
    secondary_muscle_ids: list[str]
    equipment_ids: list[str]
    aliases: list[str] = Field(default_factory=list)
    movement_pattern: ExerciseMovementPattern | None = None
    machine_variant_tags: list[ExerciseMachineVariantTag] = Field(default_factory=list)
    execution_variant_tags: list[ExerciseExecutionVariantTag] = Field(default_factory=list)
    alternatives: list[ExerciseAlternativeItem]
    difficulty_level: Literal["beginner", "intermediate", "advanced"]
    edit_target_id: int | None = None
    slug: str | None = None
    canonical_slug: str | None = None
    is_custom: bool = False
    is_personalized: bool = False
    created_by_user_id: int | None = None
    source_exercise_id: int | None = None
    has_guide: bool = False
    media_state: Literal["approved_animated", "blocked"] | None = None
    media_thumbnail_url: str | None = None
    media_animation_url: str | None = None
    guide: ExerciseGuide | None = None


class ExerciseCatalogCreate(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    primary_muscle: str | None = Field(default=None, max_length=64)
    equipment: str | None = Field(default=None, max_length=64)
    metric_type: ExerciseMetricType | None = None
    difficulty_level: Literal["beginner", "intermediate", "advanced"] = "intermediate"
    target_telegram_user_id: int | None = Field(default=None, ge=1)


class ExerciseCatalogCreateResponse(ExerciseCatalogItem):
    slug: str


class ClientResponse(BaseModel):
    id: int | None = None
    invite_id: int | None = None
    telegram_user_id: int | None = None
    username: str | None = None
    full_name: str | None = None
    birth_date: date | None = None
    goal: str | None = None
    level: str | None = None
    height_cm: int | None = None
    weight_kg: float | None = Field(default=None, ge=20, le=350, allow_inf_nan=False)
    workouts_per_week: int | None = None
    cardio_trainings_per_week: int | None = None
    resting_heart_rate: int | None = None
    body_priority: BodyPriorityPreference | None = None
    training_preferences: TrainingPreferencesResponse | None = None
    timezone: str | None = None
    kbju: NutritionTargetResponse | None = None
    status: Literal["active", "pending"]
    operational_status: Literal["active", "paused", "archived"] = "active"
