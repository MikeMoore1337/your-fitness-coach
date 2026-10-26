from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

CardioActivityType = Literal[
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
CardioStatus = Literal["planned", "completed"]


class CardioSessionFields(BaseModel):
    activity_type: CardioActivityType
    duration_minutes: int = Field(ge=1, le=600)
    distance_km: Decimal | None = Field(
        default=None, gt=0, le=1000, max_digits=6, decimal_places=2, allow_inf_nan=False
    )
    average_heart_rate_bpm: int | None = Field(default=None, ge=30, le=250)
    heart_rate_zone: int | None = Field(default=None, ge=1, le=5)
    note: str | None = Field(default=None, max_length=500)
    scheduled_at: datetime
    status: CardioStatus = "completed"

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if any(ord(character) < 32 and character not in {"\n", "\t"} for character in normalized):
            raise ValueError("Заметка содержит недопустимые управляющие символы")
        return normalized


class CardioSessionCreate(CardioSessionFields):
    client_request_id: UUID


class CardioSessionUpdate(BaseModel):
    activity_type: CardioActivityType | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=600)
    distance_km: Decimal | None = Field(
        default=None, gt=0, le=1000, max_digits=6, decimal_places=2, allow_inf_nan=False
    )
    average_heart_rate_bpm: int | None = Field(default=None, ge=30, le=250)
    heart_rate_zone: int | None = Field(default=None, ge=1, le=5)
    note: str | None = Field(default=None, max_length=500)
    scheduled_at: datetime | None = None
    status: CardioStatus | None = None

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        return CardioSessionFields.normalize_note(value)

    @model_validator(mode="after")
    def require_change(self) -> CardioSessionUpdate:
        if not self.model_fields_set:
            raise ValueError("Укажите хотя бы одно изменение")
        required_fields = {"activity_type", "duration_minutes", "scheduled_at", "status"}
        if any(
            field in self.model_fields_set and getattr(self, field) is None
            for field in required_fields
        ):
            raise ValueError("Обязательные поля cardio-записи не могут быть пустыми")
        return self


class CardioSessionResponse(BaseModel):
    activity_type: CardioActivityType
    duration_minutes: int = Field(ge=1, le=600)
    distance_km: float | None = Field(default=None, gt=0, le=1000, allow_inf_nan=False)
    average_heart_rate_bpm: int | None = Field(default=None, ge=30, le=250)
    heart_rate_zone: int | None = Field(default=None, ge=1, le=5)
    note: str | None = Field(default=None, max_length=500)
    scheduled_at: datetime
    status: CardioStatus = "completed"
    id: int
    source: Literal["manual"]
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
