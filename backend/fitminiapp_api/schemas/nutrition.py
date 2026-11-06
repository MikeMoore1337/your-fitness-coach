from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

DailyRoutine = Literal["mostly_sitting", "mixed", "mostly_on_feet", "physical_work"]
StepsRange = Literal[
    "up_to_4000",
    "from_4000_to_7000",
    "from_7000_to_10000",
    "from_10000_to_14000",
    "over_14000",
    "unknown",
]
StrengthTrainingType = Literal["calm", "regular", "heavy", "dense", "circuit"]
StrengthRest = Literal["under_60", "one_to_two", "two_to_three", "over_three", "varied"]
CardioKind = Literal[
    "walking",
    "running",
    "elliptical",
    "stationary_bike",
    "cycling",
    "rowing",
    "stepper",
    "swimming",
    "other",
]
CardioIntensity = Literal["very_light", "light", "moderate", "hard", "very_hard"]


class CardioTraining(BaseModel):
    kind: CardioKind
    trainings_per_week: int = Field(ge=1, le=14)
    duration_minutes: int = Field(ge=10, le=300)
    intensity: CardioIntensity


class NutritionTargetSave(BaseModel):
    target_telegram_user_id: int | None = Field(default=None, ge=1)
    effective_from: date | None = None
    note: str | None = Field(default=None, max_length=500)
    # Avoid turning an unchanged calculator default into a fabricated weigh-in.
    record_weight_measurement: bool = False
    sex: Literal["male", "female"]
    weight_kg: Decimal = Field(ge=20, le=350, max_digits=5, decimal_places=2, allow_inf_nan=False)
    height_cm: Decimal = Field(ge=100, le=250, max_digits=5, decimal_places=2, allow_inf_nan=False)
    age: float = Field(ge=18, le=100, allow_inf_nan=False)
    daily_routine: DailyRoutine | None = None
    steps_range: StepsRange | None = None
    strength_trainings_per_week: int = Field(ge=0, le=14)
    strength_training_duration_minutes: int = Field(default=60, ge=10, le=300)
    strength_training_type: StrengthTrainingType | None = None
    strength_rest: StrengthRest | None = None
    cardio_trainings: list[CardioTraining] | None = Field(default=None, max_length=10)
    goal: Literal["fat_loss", "muscle_gain", "maintenance", "recomposition"]

    # Transitional fields keep already deployed clients compatible while the
    # form migrates to the more expressive inputs above.
    daily_activity_level: Literal["sedentary", "low", "moderate", "high"] | None = "sedentary"
    cardio_trainings_per_week: int | None = Field(default=0, ge=0, le=14)
    cardio_training_duration_minutes: int | None = Field(default=30, ge=10, le=300)
    cardio_intensity: Literal["low", "moderate", "high"] | None = "moderate"

    @model_validator(mode="after")
    def validate_activity_details(self) -> NutritionTargetSave:
        has_new_daily_activity = self.daily_routine is not None or self.steps_range is not None
        if has_new_daily_activity and (self.daily_routine is None or self.steps_range is None):
            raise ValueError("daily_routine and steps_range must be provided together")
        if has_new_daily_activity:
            if self.strength_trainings_per_week > 0 and self.strength_training_type is None:
                raise ValueError("strength_training_type is required for strength trainings")
            if "cardio_trainings" not in self.model_fields_set:
                raise ValueError("cardio_trainings is required for detailed activity")
        if self.cardio_trainings is not None:
            legacy_cardio_fields = {
                "cardio_trainings_per_week",
                "cardio_training_duration_minutes",
                "cardio_intensity",
            }
            if self.model_fields_set & legacy_cardio_fields:
                raise ValueError("use cardio_trainings instead of legacy cardio fields")
        return self


class NutritionManualTargetSave(BaseModel):
    target_telegram_user_id: int | None = Field(default=None, ge=1)
    calories: int = Field(ge=800, le=6000)
    protein_g: int = Field(ge=0, le=400)
    fat_g: int = Field(ge=0, le=250)
    carbs_g: int = Field(ge=0, le=800)
    effective_from: date | None = None
    note: str | None = Field(default=None, max_length=500)
    confirm_energy_mismatch: bool = False


class NutritionDateOverrideSave(NutritionManualTargetSave):
    effective_from: date
    day_type: Literal["training", "rest", "recovery"] | None = None
    expected_target_id: int | None = Field(default=None, ge=1)


class NutritionScheduleRuleSave(NutritionManualTargetSave):
    effective_from: date
    program_id: int = Field(ge=1)
    revision_number: int = Field(ge=1)
    scope: Literal["template", "future", "recovery"]
    day_type: Literal["training", "rest", "recovery"]
    week_type: Literal["light", "medium", "heavy"] | None = None
    expected_binding_id: int | None = Field(default=None, ge=1)
    expected_target_version: int | None = Field(default=None, ge=1)


class NutritionScheduleRulePreviewRequest(NutritionScheduleRuleSave):
    date_from: date
    date_to: date


class NutritionScheduleBindingRequest(BaseModel):
    target_telegram_user_id: int | None = Field(default=None, ge=1)
    program_id: int = Field(ge=1)
    revision_number: int = Field(ge=1)
    effective_from: date
    expected_binding_id: int | None = Field(default=None, ge=1)
    expected_target_version: int | None = Field(default=None, ge=1)


class NutritionScheduleBindingConfirm(NutritionScheduleBindingRequest):
    confirm: Literal[True]


class NutritionSchedulePreviewRequest(NutritionScheduleBindingRequest):
    date_from: date
    date_to: date


class NutritionAssignedByResponse(BaseModel):
    id: int
    telegram_user_id: int | None = None
    username: str | None = None
    full_name: str | None = None


class NutritionTargetResponse(BaseModel):
    id: int
    user_id: int
    telegram_user_id: int | None = None
    effective_from: date
    effective_to: date | None = None
    source: Literal["calculated", "manual", "trainer", "adaptive"]
    created_at: datetime
    note: str | None = None
    superseded_by_id: int | None = None
    sex: str | None = None
    weight_kg: float | None = None
    height_cm: float | None = None
    age: float | None = None
    daily_routine: str | None = None
    steps_range: str | None = None
    strength_trainings_per_week: int | None = None
    strength_training_duration_minutes: int | None = None
    strength_training_type: str | None = None
    strength_rest: str | None
    cardio_trainings: list[CardioTraining] = Field(default_factory=list)
    goal: str | None = None
    bmr: int | None = None
    tdee: int | None = None
    calories: int
    protein_g: int
    fat_g: int
    carbs_g: int
    saved_at: datetime
    created_by: NutritionAssignedByResponse | None = None
    assigned_by: NutritionAssignedByResponse | None = None

    # Returned during the transition so an older frontend can still render a
    # target saved by a newer server.
    daily_activity_level: str | None = None
    cardio_trainings_per_week: int | None = None
    cardio_training_duration_minutes: int | None = None
    cardio_intensity: str | None = None


class NutritionTargetHistoryResponse(BaseModel):
    items: list[NutritionTargetResponse]


class NutritionDateOverrideResponse(BaseModel):
    date: date
    day_type: Literal["training", "rest", "recovery"] | None = None
    target: NutritionTargetResponse


class NutritionResolvedTargetResponse(BaseModel):
    date: date
    target: NutritionTargetResponse | None
    origin: Literal["base", "schedule", "date", "none"]
    day_type: Literal["training", "rest", "recovery"] | None
    week_type: Literal["light", "medium", "heavy"] | None
    frozen: bool


class NutritionScheduleRuleResponse(BaseModel):
    id: int
    scope: Literal["template", "future", "recovery"]
    day_type: Literal["training", "rest", "recovery"]
    week_type: Literal["light", "medium", "heavy"] | None
    effective_from: date
    program_id: int | None
    source_cycle_week: int | None
    cycle_boundary: int | None
    weekday: int | None
    target: NutritionTargetResponse


class NutritionScheduleBindingResponse(BaseModel):
    id: int
    program_id: int
    revision_number: int
    effective_from: date


class NutritionScheduleBindingStatus(NutritionScheduleBindingResponse):
    current_revision_number: int
    program_changed: bool


class NutritionScheduleProgramContext(BaseModel):
    program_id: int
    revision_number: int
    title: str
    start_date: date
    duration_weeks: int
    schedule_mode: Literal["calendar", "rotation"]
    week_types: list[Literal["light", "medium", "heavy"]]


class NutritionSchedulePreviewTarget(BaseModel):
    id: int
    calories: int
    protein_g: int
    fat_g: int
    carbs_g: int


class NutritionSchedulePreviewChange(BaseModel):
    date: date
    before: NutritionSchedulePreviewTarget | None
    after: NutritionSchedulePreviewTarget | None


class NutritionSchedulePreviewResponse(BaseModel):
    expected_binding_id: int | None
    expected_target_version: int | None
    program_id: int
    revision_number: int
    effective_from: date
    date_from: date
    date_to: date
    changes: list[NutritionSchedulePreviewChange]


class NutritionProgramDayResponse(BaseModel):
    date: date
    program_id: int
    revision_number: int
    day_type: Literal["training", "rest"] | None
    week_type: Literal["light", "medium", "heavy"] | None


EnergyCalibrationStatus = Literal[
    "insufficient",
    "limited",
    "no_change",
    "pending",
    "accepted",
    "rejected",
    "superseded",
]


class EnergyCalibrationSufficiency(BaseModel):
    status: Literal["insufficient", "limited", "sufficient"]
    counters: dict[str, int | float]
    reason_keys: list[str]


class EnergyCalibrationResponse(BaseModel):
    id: int | None = None
    status: EnergyCalibrationStatus
    ruleset_version: str
    period_start: date
    period_end: date
    sufficiency: EnergyCalibrationSufficiency
    average_intake_kcal: int | None = None
    smoothed_start_weight_kg: float | None = None
    smoothed_end_weight_kg: float | None = None
    estimated_expenditure_kcal: int | None = None
    estimate_low_kcal: int | None = None
    estimate_high_kcal: int | None = None
    goal: str
    current_target_calories: int | None = None
    current_target_protein_g: int | None = None
    current_target_fat_g: int | None = None
    current_target_carbs_g: int | None = None
    proposed_target_calories: int | None = None
    proposed_target_protein_g: int | None = None
    proposed_target_fat_g: int | None = None
    proposed_target_carbs_g: int | None = None
    proposed_effective_from: date | None = None
    rationale: list[str]
    created_at: datetime | None = None
    decided_at: datetime | None = None


class EnergyCalibrationHistoryResponse(BaseModel):
    items: list[EnergyCalibrationResponse]


class EnergyCalibrationDecision(BaseModel):
    decision: Literal["accept", "reject"]
