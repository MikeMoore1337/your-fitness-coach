from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SessionStatus = Literal["scheduled", "completed", "cancelled", "no_show"]
SessionFormat = Literal["gym", "online", "other"]
PackageState = Literal["active", "finished", "cancelled"]
PaymentStatus = Literal["expected", "partial", "paid", "cancelled"]


class CoachSessionRecurrence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weekdays: list[int] = Field(min_length=1, max_length=7)
    until: date | None = None
    occurrence_count: int | None = Field(default=None, ge=1, le=52)

    @field_validator("weekdays")
    @classmethod
    def validate_weekdays(cls, value: list[int]) -> list[int]:
        normalized = sorted(set(value))
        if len(normalized) != len(value) or any(day < 0 or day > 6 for day in normalized):
            raise ValueError("Дни недели должны быть уникальными значениями от 0 до 6")
        return normalized

    @model_validator(mode="after")
    def validate_bound(self) -> CoachSessionRecurrence:
        if self.until is None and self.occurrence_count is None:
            raise ValueError("Для повторения укажите дату окончания или число занятий")
        return self


class CoachSessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: int = Field(gt=0)
    starts_at: datetime
    timezone: str = Field(min_length=1, max_length=64)
    fold: int = Field(default=0, ge=0, le=1)
    duration_minutes: int = Field(default=60, ge=15, le=480)
    format: SessionFormat = "other"
    location: str | None = Field(default=None, max_length=256)
    private_note: str | None = Field(default=None, max_length=2000)
    package_id: int | None = Field(default=None, gt=0)
    user_workout_id: int | None = Field(default=None, gt=0)
    recurrence: CoachSessionRecurrence | None = None


class CoachSessionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    starts_at: datetime | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    fold: int = Field(default=0, ge=0, le=1)
    duration_minutes: int | None = Field(default=None, ge=15, le=480)
    format: SessionFormat | None = None
    location: str | None = Field(default=None, max_length=256)
    private_note: str | None = Field(default=None, max_length=2000)
    status: SessionStatus | None = None
    apply_to: Literal["occurrence", "series"] = "occurrence"
    charge_package: bool | None = None


class CoachSessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    client_id: int
    client_name: str
    starts_at: datetime
    starts_at_utc: datetime
    timezone: str
    duration_minutes: int
    format: SessionFormat
    location: str | None
    status: SessionStatus
    private_note: str | None
    package_id: int | None
    package_balance: int | None
    user_workout_id: int | None
    series_id: int | None
    occurrence_key: str | None
    created_at: datetime
    updated_at: datetime


class CoachAgendaResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date_from: date
    date_to: date
    timezone: str
    items: list[CoachSessionResponse]


class CoachClientOperationalStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operational_status: Literal["active", "paused", "archived"]


class CoachPackageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=128)
    counts_sessions: bool = True
    included_sessions: int | None = Field(default=None, ge=1, le=1000)
    starts_on: date | None = None
    expires_on: date | None = None
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_package(self) -> CoachPackageCreate:
        if self.counts_sessions and self.included_sessions is None:
            raise ValueError("Для пакета с занятиями укажите их число")
        if self.expires_on and self.starts_on and self.expires_on < self.starts_on:
            raise ValueError("Дата окончания пакета раньше даты начала")
        return self


class CoachPackageStateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: PackageState


class CoachPackageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    client_id: int
    client_name: str
    name: str
    counts_sessions: bool
    included_sessions: int | None
    charged_sessions: int
    reversed_sessions: int
    balance: int | None
    starts_on: date | None
    expires_on: date | None
    state: PackageState
    note: str | None
    created_at: datetime
    updated_at: datetime


class CoachPaymentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: int = Field(gt=0)
    package_id: int | None = Field(default=None, gt=0)
    expected_amount_minor: int = Field(gt=0)
    paid_amount_minor: int = Field(default=0, ge=0)
    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    payment_date: date | None = None
    method: str | None = Field(default=None, max_length=32)
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_paid_amount(self) -> CoachPaymentCreate:
        if self.paid_amount_minor > self.expected_amount_minor:
            raise ValueError("Оплата не может быть больше ожидаемой суммы")
        return self


class CoachPaymentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_amount_minor: int | None = Field(default=None, gt=0)
    paid_amount_minor: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    payment_date: date | None = None
    method: str | None = Field(default=None, max_length=32)
    note: str | None = Field(default=None, max_length=1000)
    status: Literal["expected", "partial", "paid", "cancelled"] | None = None

    @model_validator(mode="after")
    def validate_paid_amount(self) -> CoachPaymentUpdate:
        if (
            self.expected_amount_minor is not None
            and self.paid_amount_minor is not None
            and self.paid_amount_minor > self.expected_amount_minor
        ):
            raise ValueError("Оплата не может быть больше ожидаемой суммы")
        return self


class CoachPaymentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    client_id: int
    client_name: str
    package_id: int | None
    expected_amount_minor: int
    paid_amount_minor: int
    currency: str
    payment_date: date | None
    method: str | None
    note: str | None
    status: PaymentStatus
    created_at: datetime
    updated_at: datetime


class CoachTaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=240)
    due_at: datetime
    timezone: str = Field(min_length=1, max_length=64)
    fold: int = Field(default=0, ge=0, le=1)


class CoachTaskStateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Literal["open", "completed"]


class CoachTaskResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    client_id: int
    client_name: str
    title: str
    due_at: datetime
    due_at_utc: datetime
    timezone: str
    state: Literal["open", "completed"]
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CoachClientOperationsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sessions: list[CoachSessionResponse]
    packages: list[CoachPackageResponse]
    payments: list[CoachPaymentResponse]
    tasks: list[CoachTaskResponse]


class CoachOperationsTodayResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    timezone: str
    sessions: list[CoachSessionResponse]
    overdue_tasks: list[CoachTaskResponse]
    due_tasks: list[CoachTaskResponse]
    low_packages: list[CoachPackageResponse]
    payment_facts: list[CoachPaymentResponse]


__all__ = [
    "CoachAgendaResponse",
    "CoachClientOperationalStatusUpdate",
    "CoachClientOperationsResponse",
    "CoachOperationsTodayResponse",
    "CoachPackageCreate",
    "CoachPackageResponse",
    "CoachPackageStateUpdate",
    "CoachPaymentCreate",
    "CoachPaymentResponse",
    "CoachPaymentUpdate",
    "CoachSessionCreate",
    "CoachSessionRecurrence",
    "CoachSessionResponse",
    "CoachSessionUpdate",
    "CoachTaskCreate",
    "CoachTaskResponse",
    "CoachTaskStateUpdate",
]
