from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from fitminiapp_api.schemas.coach_crm import CoachTaskSourceKind

CoachWorkflowEventKind = Literal[
    "check_in_submitted",
    "missed_workout",
    "review_due",
    "program_revision_ready",
]
CoachWorkflowProposalOutcome = Literal[
    "draft",
    "created",
    "already_processed",
]
CoachWorkflowTaskState = Literal["open", "completed"]
CoachWorkflowPriority = Literal["urgent", "soon"]


class CoachWorkflowProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(..., min_length=8, max_length=128, pattern=r"^[a-z0-9_:-]+$")
    event_kind: CoachWorkflowEventKind
    rule_id: str = Field(..., min_length=3, max_length=48, pattern=r"^[a-z0-9_-]+$")
    client_id: int = Field(..., gt=0)
    client_name: str = Field(..., min_length=1, max_length=128)
    source_kind: CoachTaskSourceKind
    source_id: int = Field(..., gt=0)
    occurred_at: datetime
    title: str = Field(..., min_length=1, max_length=240)
    reason: str = Field(..., min_length=1, max_length=240)
    priority: CoachWorkflowPriority
    outcome: CoachWorkflowProposalOutcome
    task_id: int | None = Field(default=None, gt=0)
    task_state: CoachWorkflowTaskState | None = None


class CoachWorkflowAutomationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ruleset_version: Literal["coach-workflow-v1"]
    mode: Literal["preview", "evaluated"]
    events_evaluated: int = Field(..., ge=0, le=100)
    proposals: list[CoachWorkflowProposal] = Field(default_factory=list, max_length=100)
    tasks_created: int = Field(..., ge=0, le=100)
    tasks_reused: int = Field(..., ge=0, le=100)
    generated_at: datetime


__all__ = [
    "CoachWorkflowAutomationResponse",
    "CoachWorkflowEventKind",
    "CoachWorkflowProposal",
    "CoachWorkflowProposalOutcome",
]
