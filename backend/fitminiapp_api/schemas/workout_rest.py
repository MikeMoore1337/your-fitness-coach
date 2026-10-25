"""Typed API contracts for rest measurement; unknown is never serialized as zero."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

RestStatus = Literal["running", "completed", "skipped", "interrupted", "unknown"]
RestActionName = Literal["add30", "add60", "complete", "skip", "interrupt", "unknown"]


class RestStartRequest(BaseModel):
    source_set_id: int = Field(ge=1)
    started_at: datetime
    mutation_id: str = Field(min_length=8, max_length=64)


class RestRestartRequest(BaseModel):
    started_at: datetime
    mutation_id: str = Field(min_length=8, max_length=64)


class RestActionRequest(BaseModel):
    action: RestActionName
    mutation_id: str = Field(min_length=8, max_length=64)
    expected_version: int = Field(ge=1)
    ended_at: datetime | None = None
    occurred_at: datetime | None = None
    corrected: bool = False
    corrected_seconds: int | None = Field(default=None, ge=0, le=86400)


class RestSessionResponse(BaseModel):
    id: int
    workout_id: int
    source_set_id: int
    started_at: datetime
    ended_at: datetime | None
    planned_seconds: int
    adjusted_seconds: int
    measured_seconds: int | None
    status: RestStatus
    source: str | None
    quality: str
    version: int
    start_mutation_id: str | None = None
