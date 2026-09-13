from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from fitminiapp_api.core.timezone import is_valid_timezone
from fitminiapp_api.schemas.nutrition import NutritionTargetResponse

ProfileGoal = Literal["muscle_gain", "fat_loss", "maintenance", "recomposition"]
TrainingLocation = Literal["gym", "home", "other"]
TrainingEquipmentIdentifier = Literal[
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
TrainingAvoidReason = Literal["not_enjoyable", "uncomfortable", "not_confident", "other"]


class TrainingLocationPreference(BaseModel):
    location: TrainingLocation
    equipment_ids: list[TrainingEquipmentIdentifier] = Field(default_factory=list, max_length=9)

    @field_validator("equipment_ids")
    @classmethod
    def validate_unique_equipment(
        cls, value: list[TrainingEquipmentIdentifier]
    ) -> list[TrainingEquipmentIdentifier]:
        if len(set(value)) != len(value):
            raise ValueError("equipment_ids must be unique")
        return value


class AvoidedExercisePreference(BaseModel):
    exercise_id: int = Field(ge=1)
    reason: TrainingAvoidReason | None = None


class TrainingPreferencesUpdate(BaseModel):
    preferred_duration_min: int | None = Field(default=None, ge=10, le=240)
    preferred_duration_max: int | None = Field(default=None, ge=10, le=240)
    preferred_weekdays: list[int] = Field(default_factory=list, max_length=7)
    preferred_time: time | None = None
    location_profiles: list[TrainingLocationPreference] = Field(default_factory=list, max_length=3)
    preferred_exercise_ids: list[int] = Field(default_factory=list, max_length=32)
    avoided_exercises: list[AvoidedExercisePreference] = Field(default_factory=list, max_length=32)
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_training_preferences(self):
        if (
            self.preferred_duration_min is not None
            and self.preferred_duration_max is not None
            and self.preferred_duration_min > self.preferred_duration_max
        ):
            raise ValueError("preferred_duration_min must not exceed preferred_duration_max")
        if any(day < 0 or day > 6 for day in self.preferred_weekdays):
            raise ValueError("preferred_weekdays values must be between 0 and 6")
        if len(set(self.preferred_weekdays)) != len(self.preferred_weekdays):
            raise ValueError("preferred_weekdays must be unique")
        locations = [profile.location for profile in self.location_profiles]
        if len(set(locations)) != len(locations):
            raise ValueError("location profiles must be unique")
        if len(set(self.preferred_exercise_ids)) != len(self.preferred_exercise_ids):
            raise ValueError("preferred_exercise_ids must be unique")
        avoided_ids = [item.exercise_id for item in self.avoided_exercises]
        if len(set(avoided_ids)) != len(avoided_ids):
            raise ValueError("avoided exercise ids must be unique")
        if set(self.preferred_exercise_ids) & set(avoided_ids):
            raise ValueError("an exercise cannot be both preferred and avoided")
        return self


class TrainingPreferencesEditorResponse(BaseModel):
    user_id: int
    display_name: str
    role: Literal["self", "trainer"]


class TrainingPreferencesConflictResponse(BaseModel):
    status: Literal["none", "review_required"] = "none"
    active_program_id: int | None = None
    reasons: list[str] = Field(default_factory=list)


class TrainingPreferencesResponse(TrainingPreferencesUpdate):
    updated_at: datetime | None = None
    updated_by: TrainingPreferencesEditorResponse | None = None
    conflict: TrainingPreferencesConflictResponse = Field(
        default_factory=TrainingPreferencesConflictResponse
    )


class BodyPriorityPreference(BaseModel):
    mode: Literal["balanced", "muscle_groups"]
    muscle_group_ids: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_mode_and_groups(self):
        if len(set(self.muscle_group_ids)) != len(self.muscle_group_ids):
            raise ValueError("muscle_group_ids must be unique")
        if self.mode == "balanced" and self.muscle_group_ids:
            raise ValueError("balanced priority cannot contain muscle groups")
        if self.mode == "muscle_groups" and not self.muscle_group_ids:
            raise ValueError("muscle_groups priority requires at least one group")
        return self


class BodyPriorityMuscleOption(BaseModel):
    id: str
    name: str


class BodyPriorityOptionsResponse(BaseModel):
    items: list[BodyPriorityMuscleOption]


class UserProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=128)
    birth_date: date | None = None
    sex: Literal["male", "female"] | None = None
    goal: ProfileGoal | None = None
    level: Literal["beginner", "intermediate", "advanced"] | None = None
    height_cm: int | None = Field(default=None, ge=100, le=250)
    weight_kg: float | None = Field(default=None, ge=20, le=350, allow_inf_nan=False)
    workouts_per_week: int | None = Field(default=None, ge=0, le=14)
    cardio_trainings_per_week: int | None = Field(default=None, ge=0, le=14)
    resting_heart_rate: int | None = Field(default=None, ge=30, le=120)
    body_priority: BodyPriorityPreference | None = None
    training_preferences: TrainingPreferencesUpdate | None = None
    timezone: str | None = Field(default=None, max_length=64)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value and not is_valid_timezone(value):
            raise ValueError("Unsupported timezone")
        return value

    @field_validator("birth_date")
    @classmethod
    def validate_birth_date(cls, value: date | None) -> date | None:
        if value is None:
            return value
        today = date.today()
        age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
        if age < 10 or age > 100:
            raise ValueError("Age must be between 10 and 100 years")
        return value


class AccountDeleteRequest(BaseModel):
    confirmation: Literal["DELETE"]


class AccountExportStatusResponse(BaseModel):
    status: Literal["none", "generating", "ready", "expired", "error"]
    export_id: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None
    expires_at: datetime | None = None
    filename: str | None = None
    content_size_bytes: int | None = None
    error_code: str | None = None


class AccountExportDownloadLinkResponse(BaseModel):
    url: str
    filename: str
    expires_at: datetime


class AvatarMetadataResponse(BaseModel):
    content_type: Literal["image/webp"]
    byte_size: int = Field(gt=0, le=1024 * 1024)
    width: Literal[512]
    height: Literal[512]
    updated_at: datetime


class TelegramLinkCreateResponse(BaseModel):
    telegram_url: str
    expires_in_seconds: int


class OAuthLinkCreateResponse(BaseModel):
    oauth_url: str
    expires_in_seconds: int


class HeartRateZoneResponse(BaseModel):
    zone: int
    title: str
    min_bpm: int
    max_bpm: int


class HeartRateRangeResponse(BaseModel):
    min_bpm: int
    max_bpm: int


class HeartRatePreviewRequest(BaseModel):
    birth_date: date
    resting_heart_rate: int | None = Field(default=None, ge=30, le=120)
    goal: ProfileGoal | None = None

    @field_validator("birth_date")
    @classmethod
    def validate_birth_date(cls, value: date) -> date:
        today = date.today()
        age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
        if age < 10 or age > 100:
            raise ValueError("Age must be between 10 and 100 years")
        return value


class HeartRatePreviewResponse(BaseModel):
    estimated_max_heart_rate: int
    heart_rate_reserve: int | None = None
    heart_rate_calculation_method: Literal["heart_rate_reserve", "percent_maximum"]
    heart_rate_zones: list[HeartRateZoneResponse]
    recommended_cardio_range: HeartRateRangeResponse | None = None


class UserProfileResponse(BaseModel):
    full_name: str | None = None
    birth_date: date | None = None
    sex: Literal["male", "female"] | None = None
    goal: str | None = None
    level: str | None = None
    height_cm: int | None = None
    weight_kg: float | None = None
    workouts_per_week: int | None = None
    cardio_trainings_per_week: int | None = None
    resting_heart_rate: int | None = None
    body_priority: BodyPriorityPreference | None = None
    training_preferences: TrainingPreferencesResponse | None = None
    timezone: str = "Europe/Moscow"
    estimated_max_heart_rate: int | None = None
    heart_rate_reserve: int | None = None
    heart_rate_calculation_method: Literal["heart_rate_reserve", "percent_maximum"] | None = None
    heart_rate_zones: list[HeartRateZoneResponse] = Field(default_factory=list)
    recommended_cardio_range: HeartRateRangeResponse | None = None
    kbju: NutritionTargetResponse | None = None


OnboardingField = Literal["goal"]


class OnboardingStateResponse(BaseModel):
    status: Literal["required", "complete"]
    required_fields: list[OnboardingField]
    missing_fields: list[OnboardingField]


class TrainerResponse(BaseModel):
    id: int
    telegram_user_id: int | None = None
    username: str | None = None
    full_name: str | None = None
    can_open_chat: bool = False
    chat_url: str | None = None
    chat_unavailable_reason: str | None = None


class UserResponse(BaseModel):
    id: int
    telegram_user_id: int | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    photo_url: str | None = None
    custom_avatar: AvatarMetadataResponse | None = None
    is_coach: bool = False
    is_admin: bool = False
    is_root: bool = False
    has_active_program: bool = False
    has_workout_history: bool = False
    has_food_history: bool | None = None
    auth_providers: list[str] = Field(default_factory=list)
    onboarding: OnboardingStateResponse
    profile: UserProfileResponse | None = None
    trainer: TrainerResponse | None = None
