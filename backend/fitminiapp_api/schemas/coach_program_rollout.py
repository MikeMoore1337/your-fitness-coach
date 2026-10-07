from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CoachProgramRolloutClassification = Literal[
    "compatible",
    "personalization_required",
    "manual_review_required",
]
CoachProgramRolloutChange = Literal["added", "updated", "removed"]
CoachProgramRolloutResultStatus = Literal["applied", "already_applied", "failed"]


class CoachProgramRolloutDiff(BaseModel):
    model_config = ConfigDict(extra="forbid")

    week_number: int = Field(..., ge=1, le=24)
    day_number: int = Field(..., ge=1, le=8)
    exercise_title: str = Field(..., min_length=1, max_length=128)
    change: CoachProgramRolloutChange
    current: str | None = Field(default=None, max_length=240)
    proposed: str | None = Field(default=None, max_length=240)


class CoachProgramRolloutClientPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: int = Field(..., gt=0)
    client_name: str = Field(..., min_length=1, max_length=128)
    program_id: int | None = Field(default=None, gt=0)
    current_revision_number: int | None = Field(default=None, ge=0)
    classification: CoachProgramRolloutClassification
    can_apply: bool
    reason_codes: list[str] = Field(default_factory=list, max_length=20)
    diff: list[CoachProgramRolloutDiff] = Field(default_factory=list, max_length=50)


class CoachProgramRolloutPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_id: int = Field(..., gt=0)
    client_ids: list[int] = Field(..., min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_unique_clients(self):
        if len(set(self.client_ids)) != len(self.client_ids):
            raise ValueError("client_ids must be unique")
        return self


class CoachProgramRolloutPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_id: int = Field(..., gt=0)
    template_title: str = Field(..., min_length=1, max_length=128)
    template_fingerprint: str = Field(..., min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    targets: list[CoachProgramRolloutClientPreview] = Field(..., max_length=100)
    generated_at: datetime


class CoachProgramRolloutTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: int = Field(..., gt=0)
    program_id: int = Field(..., gt=0)
    expected_revision_number: int = Field(..., ge=0)


class CoachProgramRolloutApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_id: int = Field(..., gt=0)
    template_fingerprint: str = Field(..., min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    targets: list[CoachProgramRolloutTarget] = Field(..., min_length=1, max_length=100)
    confirmed: bool = False
    reason: str = Field(..., min_length=1, max_length=500)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)

    @model_validator(mode="after")
    def validate_unique_targets(self):
        client_ids = [target.client_id for target in self.targets]
        if len(set(client_ids)) != len(client_ids):
            raise ValueError("targets must contain unique clients")
        if not self.reason.strip():
            raise ValueError("reason is required")
        return self


class CoachProgramRolloutResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: int = Field(..., gt=0)
    client_name: str = Field(..., min_length=1, max_length=128)
    program_id: int = Field(..., gt=0)
    status: CoachProgramRolloutResultStatus
    code: str = Field(..., min_length=2, max_length=48)
    detail: str = Field(..., min_length=1, max_length=240)
    workouts_updated: int = Field(default=0, ge=0)
    current_revision_number: int | None = Field(default=None, ge=0)


class CoachProgramRolloutApplyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rollout_id: str = Field(..., min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    template_id: int = Field(..., gt=0)
    results: list[CoachProgramRolloutResult] = Field(..., min_length=1, max_length=100)
    applied_count: int = Field(..., ge=0, le=100)
    already_applied_count: int = Field(..., ge=0, le=100)
    failed_count: int = Field(..., ge=0, le=100)
    completed_at: datetime


__all__ = [
    "CoachProgramRolloutApplyRequest",
    "CoachProgramRolloutApplyResponse",
    "CoachProgramRolloutChange",
    "CoachProgramRolloutClassification",
    "CoachProgramRolloutClientPreview",
    "CoachProgramRolloutDiff",
    "CoachProgramRolloutPreviewRequest",
    "CoachProgramRolloutPreviewResponse",
    "CoachProgramRolloutResult",
    "CoachProgramRolloutResultStatus",
    "CoachProgramRolloutTarget",
]
