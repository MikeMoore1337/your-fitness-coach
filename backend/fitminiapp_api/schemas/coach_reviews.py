from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from fitminiapp_api.schemas.coach_crm import CoachTaskResponse


class CoachCheckInReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response: str | None = Field(default=None, max_length=2000)
    follow_up_title: str | None = Field(default=None, max_length=240)
    follow_up_due_at: datetime | None = None
    follow_up_timezone: str | None = Field(default=None, min_length=1, max_length=64)
    fold: int = Field(default=0, ge=0, le=1)

    @model_validator(mode="after")
    def validate_follow_up(self) -> CoachCheckInReviewRequest:
        values = (self.follow_up_title, self.follow_up_due_at, self.follow_up_timezone)
        if any(value is not None for value in values) and not all(
            value is not None for value in values
        ):
            raise ValueError("Для follow-up укажите название, срок и timezone")
        if self.follow_up_title is not None and not self.follow_up_title.strip():
            raise ValueError("Название follow-up не может быть пустым")
        return self


class CoachCheckInReviewItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    client_id: int = Field(gt=0)
    client_name: str = Field(min_length=1, max_length=128)
    check_in_id: int = Field(gt=0)
    week_start: date
    week_end: date
    submitted_on: date
    status: Literal["completed", "skipped"]
    training_load: int | None = Field(default=None, ge=1, le=5)
    recovery: int | None = Field(default=None, ge=1, le=5)
    hunger: int | None = Field(default=None, ge=1, le=5)
    adherence_difficulty: int | None = Field(default=None, ge=1, le=5)
    note: str | None = None
    summary: dict[str, object]
    review_status: Literal["pending", "reviewed"]
    review_response: str | None = None
    reviewed_at: datetime | None = None
    follow_up: CoachTaskResponse | None = None
    created_at: datetime


class CoachCheckInReviewListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CoachCheckInReviewItem] = Field(default_factory=list, max_length=100)
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


__all__ = [
    "CoachCheckInReviewItem",
    "CoachCheckInReviewListResponse",
    "CoachCheckInReviewRequest",
]
