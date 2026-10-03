from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CoachCapacityBand = Literal["0_9", "10_29", "30_99", "100_plus"]
CoachCapacityBottleneckKey = Literal[
    "attention",
    "open_tasks",
    "without_program",
    "pending_invites",
]
CoachCapacityBottleneckAction = Literal[
    "attention",
    "tasks",
    "without_program",
    "pending",
]


class CoachCapacityBottleneck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: CoachCapacityBottleneckKey
    count: int = Field(ge=1)
    action: CoachCapacityBottleneckAction


class CoachCapacityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active_client_count: int = Field(ge=0)
    pending_invite_count: int = Field(ge=0)
    open_task_count: int = Field(ge=0)
    attention_item_count: int = Field(ge=0)
    attention_client_count: int = Field(ge=0)
    attention_items_returned: int = Field(ge=0)
    attention_items_truncated: bool
    clients_with_active_program_count: int = Field(ge=0)
    roster_coverage_percent: float | None = Field(default=None, ge=0, le=100)
    capacity_band: CoachCapacityBand
    next_capacity_boundary: int | None = Field(default=None, ge=1)
    scale_boundaries: tuple[int, int, int]
    bottlenecks: list[CoachCapacityBottleneck]
    generated_at: datetime


__all__ = [
    "CoachCapacityBand",
    "CoachCapacityBottleneck",
    "CoachCapacityResponse",
]
