from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from fitminiapp_api.schemas.coach_attention import CoachAttentionClient, CoachAttentionEvidence

CoachInboxItemKind = Literal["attention", "check_in", "task", "session", "package", "payment"]
CoachInboxPriority = Literal["urgent", "soon", "normal"]
CoachInboxAction = Literal[
    "review_workout",
    "review_check_in",
    "assign_program",
    "review_program",
    "open_task",
    "open_schedule",
    "open_finance",
]


class CoachInboxItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(..., min_length=3, max_length=128, pattern=r"^[a-z0-9_:-]+$")
    kind: CoachInboxItemKind
    client: CoachAttentionClient
    title: str = Field(..., min_length=1, max_length=240)
    reason: str = Field(..., min_length=1, max_length=240)
    source_kind: str | None = Field(default=None, min_length=1, max_length=48)
    source_id: int | None = Field(default=None, gt=0)
    action: CoachInboxAction
    destination: str = Field(..., min_length=1, max_length=160)
    priority: CoachInboxPriority = "normal"
    created_at: datetime
    due_at: datetime | None = None
    evidence: list[CoachAttentionEvidence] = Field(default_factory=list, max_length=4)


class CoachInboxCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attention: int = Field(ge=0)
    pending_reviews: int = Field(ge=0)
    tasks: int = Field(ge=0)
    sessions: int = Field(ge=0)
    packages: int = Field(ge=0)
    payments: int = Field(ge=0)


class CoachInboxResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    timezone: str
    items: list[CoachInboxItem] = Field(default_factory=list, max_length=100)
    total: int = Field(ge=0)
    counts: CoachInboxCounts
    generated_at: datetime


__all__ = [
    "CoachInboxAction",
    "CoachInboxCounts",
    "CoachInboxItem",
    "CoachInboxItemKind",
    "CoachInboxPriority",
    "CoachInboxResponse",
]
