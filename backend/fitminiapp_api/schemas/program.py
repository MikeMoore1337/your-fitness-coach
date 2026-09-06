from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from fitminiapp_api.schemas.nutrition import NutritionTargetResponse
from fitminiapp_api.schemas.user import BodyPriorityPreference, TrainingPreferencesResponse

ProgramRecommendationGoal = Literal[
    "fat_loss", "recomposition", "maintenance", "muscle_gain", "strength"
]
ProgramExperience = Literal["beginner", "intermediate", "advanced"]
ProgramSplitType = Literal["full_body", "upper_lower", "push_pull_legs", "body_part", "hybrid"]
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
    "arm_curl",
    "calf",
    "cardio_row",
    "chest_fly",
    "chest_press",
    "cycling",
    "glute",
    "grip",
    "hinge",
    "leg_isolation",
    "lunge",
    "pullover",
    "row",
    "running",
    "shoulder_press",
    "squat",
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


class ProgramTemplateExerciseCreate(BaseModel):
    exercise_id: int = Field(ge=1)
    prescribed_sets: int | None = Field(default=None, ge=1, le=10)
    prescribed_reps: str | None = Field(default=None, min_length=1, max_length=32)
    prescribed_duration_minutes: int | None = Field(default=None, ge=1, le=600)
    rest_seconds: int = Field(default=90, ge=0, le=600)
    notes: str | None = Field(default=None, max_length=2000)
    superset_group: int | None = Field(default=None, ge=1)
    superset_order: int | None = Field(default=None, ge=1, le=2)

    @model_validator(mode="after")
    def validate_superset_pair(self):
        if (self.superset_group is None) != (self.superset_order is None):
            raise ValueError("superset_group and superset_order must be provided together")
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
    goal: Literal["muscle_gain", "fat_loss", "maintenance", "recomposition"]
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
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_superset_pair(self):
        if (self.superset_group is None) != (self.superset_order is None):
            raise ValueError("superset_group and superset_order must be provided together")
        return self


class CoachProgramExerciseAssignmentResponse(BaseModel):
    workouts_updated: int
    current_revision_number: int


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
    type: Literal["image"]
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
    weight_kg: int | None = None
    workouts_per_week: int | None = None
    cardio_trainings_per_week: int | None = None
    resting_heart_rate: int | None = None
    body_priority: BodyPriorityPreference | None = None
    training_preferences: TrainingPreferencesResponse | None = None
    timezone: str | None = None
    kbju: NutritionTargetResponse | None = None
    status: Literal["active", "pending"]
