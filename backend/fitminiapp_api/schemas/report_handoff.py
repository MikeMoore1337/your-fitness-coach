from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from fitminiapp_api.schemas.progress import (
    NutritionReportPeriod,
    ProgressReportResponse,
)

ReportHandoffDeliveryStatus = Literal["delivered", "pending", "failed"]


class ReportHandoffCreateRequest(BaseModel):
    period: NutritionReportPeriod
    date_from: date | None = None
    date_to: date | None = None
    client_comment: str | None = Field(default=None, max_length=2000)

    @field_validator("client_comment")
    @classmethod
    def normalize_client_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ReportHandoffTrainer(BaseModel):
    id: int = Field(ge=1)
    full_name: str | None = None
    username: str | None = None


class ReportHandoffResponse(BaseModel):
    id: int = Field(ge=1)
    trainer: ReportHandoffTrainer
    period: NutritionReportPeriod
    period_start: date
    period_end: date
    timezone: str
    report_contract_version: str
    included_section_ids: list[str] = Field(min_length=1)
    created_at: datetime
    delivery_status: ReportHandoffDeliveryStatus
    delivery_attempt: int = Field(ge=1)
    client_comment: str | None = None
    live: Literal[True] = True


class ReportHandoffCheckIn(BaseModel):
    week_start: date
    week_end: date
    submitted_on: date
    status: Literal["completed", "skipped"]
    training_load: int | None = Field(default=None, ge=1, le=5)
    recovery: int | None = Field(default=None, ge=1, le=5)
    hunger: int | None = Field(default=None, ge=1, le=5)
    adherence_difficulty: int | None = Field(default=None, ge=1, le=5)


class ReportHandoffProgressReport(ProgressReportResponse):
    check_ins: list[ReportHandoffCheckIn]


class ReportHandoffViewResponse(BaseModel):
    handoff: ReportHandoffResponse
    report: ReportHandoffProgressReport
    data_changed_since_send: bool
