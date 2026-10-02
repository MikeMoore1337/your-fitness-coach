from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from fitminiapp_api.schemas.progress import NutritionReportPeriod

ShareType = Literal["progress", "program"]
ShareStatus = Literal["active", "revoked"]
DataQualityStatus = Literal["sufficient", "limited", "insufficient"]


class PublicShareProgressExercise(BaseModel):
    exercise_title: str = Field(min_length=1, max_length=128)
    performed_session_count: int = Field(ge=0)
    completed_set_count: int = Field(ge=0)
    max_external_load_kg: float | None = Field(default=None, ge=0)
    external_load_volume_kg: float | None = Field(default=None, ge=0)


class PublicShareProgressQuality(BaseModel):
    workout_logging: DataQualityStatus
    working_sets: DataQualityStatus
    notes: list[str] = Field(min_length=1, max_length=4)


class PublicShareProgressSnapshot(BaseModel):
    kind: Literal["progress"] = "progress"
    period_start: date
    period_end: date
    planned_workouts: int = Field(ge=0)
    completed_workouts: int = Field(ge=0)
    frequency_per_week: float = Field(ge=0)
    completed_working_sets: int = Field(ge=0)
    new_personal_records: int = Field(ge=0)
    external_load_volume_kg: float | None = Field(default=None, ge=0)
    volume_recorded_sets: int = Field(ge=0)
    exercises: list[PublicShareProgressExercise] = Field(max_length=3)
    data_quality: PublicShareProgressQuality


class PublicShareProgramWeeklyPrescription(BaseModel):
    week_number: int = Field(ge=1, le=24)
    prescribed_sets: int = Field(ge=1, le=10)
    prescribed_reps: str = Field(min_length=1, max_length=32)
    prescribed_duration_minutes: int | None = Field(default=None, ge=1, le=600)
    rest_seconds: int = Field(ge=0, le=600)


class PublicShareProgramExercise(BaseModel):
    exercise_title: str = Field(min_length=1, max_length=128)
    metric_type: Literal["strength", "cardio"]
    prescribed_sets: int = Field(ge=1, le=10)
    prescribed_reps: str = Field(min_length=1, max_length=32)
    prescribed_duration_minutes: int | None = Field(default=None, ge=1, le=600)
    rest_seconds: int = Field(ge=0, le=600)
    weekly_prescriptions: list[PublicShareProgramWeeklyPrescription] = Field(max_length=24)


class PublicShareProgramDay(BaseModel):
    day_number: int = Field(ge=1, le=8)
    title: str = Field(min_length=1, max_length=128)
    exercises: list[PublicShareProgramExercise] = Field(min_length=1, max_length=20)


class PublicShareProgramSnapshot(BaseModel):
    kind: Literal["program"] = "program"
    title: str = Field(min_length=1, max_length=128)
    goal: str = Field(min_length=1, max_length=32)
    level: str = Field(min_length=1, max_length=32)
    duration_weeks: int = Field(ge=1, le=24)
    days: list[PublicShareProgramDay] = Field(min_length=1, max_length=8)


PublicShareSnapshot = Annotated[
    PublicShareProgressSnapshot | PublicShareProgramSnapshot,
    Field(discriminator="kind"),
]


class PublicSharePeriodRequest(BaseModel):
    period: NutritionReportPeriod
    date_from: date | None = None
    date_to: date | None = None

    @model_validator(mode="after")
    def validate_custom_period(self):
        if self.period == NutritionReportPeriod.CUSTOM and (
            self.date_from is None or self.date_to is None
        ):
            raise ValueError("custom period requires date_from and date_to")
        if self.period != NutritionReportPeriod.CUSTOM and (
            self.date_from is not None or self.date_to is not None
        ):
            raise ValueError("date_from/date_to are only valid for custom period")
        if (
            self.date_from is not None
            and self.date_to is not None
            and self.date_to < self.date_from
        ):
            raise ValueError("date_to must not precede date_from")
        return self


class PublicShareProgressCreateRequest(PublicSharePeriodRequest):
    preview_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


class PublicShareProgramPreviewRequest(BaseModel):
    template_id: int = Field(ge=1)


class PublicShareProgramCreateRequest(BaseModel):
    template_id: int = Field(ge=1)
    preview_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


class PublicSharePreviewResponse(BaseModel):
    share_type: ShareType
    preview_hash: str = Field(min_length=64, max_length=64)
    snapshot: PublicShareSnapshot


class PublicShareResponse(BaseModel):
    share_id: str = Field(min_length=32, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    share_type: ShareType
    status: ShareStatus = "active"
    created_at: datetime
    public_url: str
    preview_hash: str = Field(min_length=64, max_length=64)
    snapshot: PublicShareSnapshot


class PublicShareOwnerResponse(BaseModel):
    share_id: str = Field(min_length=32, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    share_type: ShareType
    status: ShareStatus
    created_at: datetime
    revoked_at: datetime | None = None
    public_url: str


class PublicShareImportRequest(BaseModel):
    preview_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    replace_active: bool = False


class PublicShareImportResponse(BaseModel):
    share_id: str = Field(min_length=32, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    status: Literal["imported", "already_imported"]
    template_id: int = Field(ge=1)
    user_program_id: int = Field(ge=1)
    workouts_created: int = Field(ge=0)
