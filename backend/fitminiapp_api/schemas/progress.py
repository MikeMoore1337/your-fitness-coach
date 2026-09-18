from datetime import date, datetime, time
from enum import IntEnum, StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from fitminiapp_api.schemas.daily_wellbeing import DailyWellbeingReport
from fitminiapp_api.schemas.data_quality import ProgressDataSufficiency
from fitminiapp_api.schemas.user import BodyPriorityPreference


class ProgressPeriodDays(IntEnum):
    DAYS_1 = 1
    DAYS_7 = 7
    DAYS_30 = 30
    DAYS_90 = 90
    DAYS_365 = 365


class NutritionReportPeriod(StrEnum):
    DAYS_1 = "days_1"
    DAYS_7 = "days_7"
    DAYS_30 = "days_30"
    DAYS_90 = "days_90"
    DAYS_365 = "days_365"
    CURRENT_WEEK = "current_week"
    CURRENT_MONTH = "current_month"
    PREVIOUS_MONTH = "previous_month"
    CUSTOM = "custom"


AdherenceStatus = Literal["available", "not_applicable", "insufficient_data", "unsupported"]


class AdherenceComponent(BaseModel):
    status: AdherenceStatus
    percent: float | None = None
    achieved: int = 0
    evaluated: int = 0
    weight: float
    reason: str | None = None


class AdherenceSummary(BaseModel):
    formula_version: str
    overall_percent: float | None = None
    included_components: list[str]
    workouts: AdherenceComponent
    cardio: AdherenceComponent
    calories: AdherenceComponent
    protein: AdherenceComponent


class NextWorkoutSummary(BaseModel):
    id: int
    scheduled_date: date
    scheduled_time: time | None = None
    title: str
    status: str


class TrainingPeriodSummary(BaseModel):
    planned_workouts: int
    completed_workouts: int
    skipped_workouts: int
    frequency_per_week: float
    volume_kg: float
    new_personal_records: int
    last_completed_workout_on: date | None = None
    next_workout: NextWorkoutSummary | None = None


class CardioZoneDuration(BaseModel):
    zone: int = Field(ge=1, le=5)
    duration_minutes: int = Field(ge=1)


class CardioPeriodSummary(BaseModel):
    completed_sessions: int = Field(ge=0)
    planned_sessions: int = Field(ge=0)
    frequency_per_week: float = Field(ge=0)
    duration_minutes: int = Field(ge=0)
    distance_km: float | None = Field(default=None, ge=0)
    zone_duration: list[CardioZoneDuration]


class NutritionPeriodSummary(BaseModel):
    visible: bool
    logged_days: int = 0
    complete_days: int = 0
    incomplete_days: int = 0
    fasted_days: int = 0
    unlogged_days: int = 0
    adherence_evaluated_days: int = 0
    average_calories: float | None = None
    target_calories: int | None = None
    average_protein_g: float | None = None
    target_protein_g: int | None = None
    target_effective_on: date | None = None


class NutritionReportMetricSummary(BaseModel):
    average: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    sample_days: int = Field(ge=0)


class NutritionReportTargetComparison(BaseModel):
    average_actual: float | None = None
    average_target: float | None = None
    average_deviation: float | None = None
    evaluated_days: int = Field(ge=0)


class NutritionReportDailyPoint(BaseModel):
    diary_date: date
    status: Literal["complete", "incomplete", "fasted", "missing"]
    is_current_day: bool
    calories: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    carbs_g: float | None = None
    target_calories: int | None = None
    target_protein_g: int | None = None
    target_fat_g: int | None = None
    target_carbs_g: int | None = None
    calorie_deviation: float | None = None
    protein_deviation_g: float | None = None
    fat_deviation_g: float | None = None
    carbs_deviation_g: float | None = None
    within_calorie_tolerance: bool | None = None
    meets_protein_target: bool | None = None
    target_changed: bool = False
    hydration_ml: int | None = None
    hydration_target_ml: int | None = None
    hydration_progress_percent: float | None = None


class HydrationReportSummary(BaseModel):
    total_ml: int = Field(ge=0)
    average_ml: float | None = None
    logged_days: int = Field(ge=0)
    eligible_days: int = Field(ge=1)
    coverage_percent: float = Field(ge=0, le=100)
    days_meeting_goal: int = Field(ge=0)
    goal_evaluated_days: int = Field(ge=0)
    trend_ml: float | None = None


class NutritionReportTargetChange(BaseModel):
    effective_from: date
    source: Literal["calculated", "manual", "trainer", "adaptive"]
    calories: int
    protein_g: int
    fat_g: int
    carbs_g: int


class NutritionReportSummary(BaseModel):
    logged_days: int = Field(ge=0)
    eligible_days: int = Field(ge=1)
    coverage_percent: float = Field(ge=0, le=100)
    complete_days: int = Field(ge=0)
    incomplete_days: int = Field(ge=0)
    fasted_days: int = Field(ge=0)
    missing_days: int = Field(ge=0)
    current_day_status: Literal["complete", "incomplete", "fasted", "missing"] | None = None
    calories: NutritionReportMetricSummary
    protein_g: NutritionReportMetricSummary
    fat_g: NutritionReportMetricSummary
    carbs_g: NutritionReportMetricSummary
    calorie_comparison: NutritionReportTargetComparison
    protein_comparison: NutritionReportTargetComparison
    fat_comparison: NutritionReportTargetComparison
    carbs_comparison: NutritionReportTargetComparison
    days_within_calorie_tolerance: int = Field(ge=0)
    calorie_tolerance_evaluated_days: int = Field(ge=0)
    days_meeting_protein_target: int = Field(ge=0)
    protein_target_evaluated_days: int = Field(ge=0)


class NutritionReportResponse(BaseModel):
    period: NutritionReportPeriod
    period_start: date
    period_end: date
    timezone: str
    summary: NutritionReportSummary
    daily: list[NutritionReportDailyPoint]
    target_changes: list[NutritionReportTargetChange]
    hydration: HydrationReportSummary | None = None


class BodyMetricPoint(BaseModel):
    measured_on: date
    value: float


class BodyMetricTrend(BaseModel):
    metric: str
    label: str = ""
    unit: Literal["kg", "cm"] = "cm"
    definition_id: int | None = Field(default=None, ge=1)
    first_value: float
    latest_value: float
    change: float | None = None
    first_measured_on: date
    latest_measured_on: date
    point_count: int = Field(ge=1)
    span_days: int = Field(ge=0)
    interpretation_status: Literal[
        "single_point", "insufficient_points", "insufficient_period", "available"
    ]
    points: list[BodyMetricPoint]


class LatestCustomBodyMeasurement(BaseModel):
    definition_id: int = Field(ge=1)
    label: str
    unit: Literal["cm"] = "cm"
    value: float
    measured_on: date
    archived: bool = False


class LatestBodyMeasurement(BaseModel):
    measured_on: date
    weight_kg: float | None = None
    chest_cm: float | None = None
    waist_cm: float | None = None
    hips_cm: float | None = None
    biceps_cm: float | None = None
    thigh_cm: float | None = None
    custom_measurements: list[LatestCustomBodyMeasurement] = Field(default_factory=list)


class BodyMeasurementGuidance(BaseModel):
    comparison_basis: Literal["self"] = "self"
    minimum_points_for_interpretation: int = Field(ge=2)
    minimum_span_days_for_interpretation: int = Field(ge=1)
    consistency_tips: list[str]
    circumference_limitations: list[str]


class BodyPeriodSummary(BaseModel):
    latest_measurement: LatestBodyMeasurement | None = None
    trends: list[BodyMetricTrend]
    priority: BodyPriorityPreference | None = None
    guidance: BodyMeasurementGuidance


class ProgressSummaryResponse(BaseModel):
    user_id: int
    period_days: int = Field(ge=1, le=366)
    period_start: date
    period_end: date
    training: TrainingPeriodSummary
    cardio: CardioPeriodSummary
    nutrition: NutritionPeriodSummary
    body: BodyPeriodSummary
    adherence: AdherenceSummary
    data_sufficiency: ProgressDataSufficiency


class TrainerClientProgressSummary(ProgressSummaryResponse):
    client_name: str | None = None


class TrainerClientProgressListResponse(BaseModel):
    items: list[TrainerClientProgressSummary]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class ProgressReportSubject(BaseModel):
    name: str
    role: Literal["self", "client"]
    goal: str | None = None


class ProgressReportExerciseSession(BaseModel):
    performed_on: date
    completed_set_count: int = Field(ge=0)
    max_external_load_kg: float | None = None
    external_load_volume_kg: float | None = None


class ProgressReportExerciseTrend(BaseModel):
    exercise_title: str
    performed_session_count: int = Field(ge=0)
    completed_set_count: int = Field(ge=0)
    first_performed_on: date
    last_performed_on: date
    reps_total: int | None = Field(default=None, ge=0)
    max_external_load_kg: float | None = None
    external_load_volume_kg: float | None = None
    volume_recorded_sets: int = Field(ge=0)
    sessions: list[ProgressReportExerciseSession]


class ProgressReportTraining(BaseModel):
    planned_workouts: int = Field(ge=0)
    completed_workouts: int = Field(ge=0)
    skipped_workouts: int = Field(ge=0)
    frequency_per_week: float = Field(ge=0)
    completed_working_sets: int = Field(ge=0)
    external_load_volume_kg: float | None = None
    volume_recorded_sets: int = Field(ge=0)
    new_personal_records: int = Field(ge=0)
    exercises: list[ProgressReportExerciseTrend]


class ProgressReportProgramChange(BaseModel):
    changed_on: date
    change_kind: Literal[
        "assigned",
        "program_archived",
        "plan_updated",
        "block_created",
        "block_updated",
        "block_status_changed",
    ]


class ProgressReportTrainingBlock(BaseModel):
    title: str
    start_date: date
    end_date: date
    purpose: str
    is_deload: bool
    status: Literal["planned", "active", "completed", "archived"]


class ProgressReportProgram(BaseModel):
    title: str
    status: Literal["scheduled", "active", "completed", "archived"]
    start_date: date
    duration_weeks: int = Field(ge=1)
    active_block: ProgressReportTrainingBlock | None = None
    changes: list[ProgressReportProgramChange]


class ProgressReportCheckIn(BaseModel):
    week_start: date
    week_end: date
    submitted_on: date
    status: Literal["completed", "skipped"]
    training_load: int | None = Field(default=None, ge=1, le=5)
    recovery: int | None = Field(default=None, ge=1, le=5)
    hunger: int | None = Field(default=None, ge=1, le=5)
    adherence_difficulty: int | None = Field(default=None, ge=1, le=5)
    note: str | None = None


class ProgressReportResponse(BaseModel):
    generated_at: datetime
    period: NutritionReportPeriod
    period_start: date
    period_end: date
    timezone: str
    subject: ProgressReportSubject
    training: ProgressReportTraining
    cardio: CardioPeriodSummary
    body: BodyPeriodSummary
    nutrition: NutritionReportResponse
    adherence: AdherenceSummary
    data_sufficiency: ProgressDataSufficiency
    program: ProgressReportProgram | None = None
    check_ins: list[ProgressReportCheckIn]
    wellbeing: DailyWellbeingReport | None = None


class ProgressReportDownloadLinkResponse(BaseModel):
    url: str
    filename: str
    expires_at: datetime
