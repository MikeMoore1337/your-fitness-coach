from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CoachAttentionKind = Literal[
    "workout_feedback",
    "weekly_check_in",
    "missed_workout",
    "skipped_workout",
    "without_program",
]
CoachAttentionSourceKind = Literal["workout", "weekly_check_in", "client"]
CoachAttentionAction = Literal["review_workout", "review_check_in", "assign_program"]


class CoachAttentionClient(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(..., gt=0)
    name: str = Field(..., min_length=1, max_length=128)


class CoachAttentionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(
        ...,
        min_length=8,
        max_length=96,
        pattern=(
            r"^(?:workout_feedback|weekly_check_in|missed_workout|"
            r"skipped_workout|without_program):[1-9][0-9]*:[1-9][0-9]*$"
        ),
    )
    kind: CoachAttentionKind
    client: CoachAttentionClient
    title: str = Field(..., min_length=1, max_length=120)
    reason: str = Field(..., min_length=1, max_length=240)
    source_kind: CoachAttentionSourceKind
    source_id: int = Field(..., gt=0)
    source_state: str = Field(..., min_length=1, max_length=48, pattern=r"^[a-z0-9_:-]+$")
    action: CoachAttentionAction
    destination: str = Field(
        ...,
        min_length=12,
        max_length=160,
        pattern=r"^/coach\?client_id=[1-9][0-9]*(?:&(?:workout_id|focus)=[a-z0-9_:-]+)?$",
    )
    created_at: datetime


class CoachAttentionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CoachAttentionItem] = Field(default_factory=list, max_length=100)
    total: int = Field(..., ge=0)
    generated_at: datetime


__all__ = [
    "CoachAttentionAction",
    "CoachAttentionClient",
    "CoachAttentionItem",
    "CoachAttentionKind",
    "CoachAttentionResponse",
    "CoachAttentionSourceKind",
]
