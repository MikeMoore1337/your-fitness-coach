from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from fitminiapp_api.db.base import Base

LIFECYCLE_MILESTONE_TYPES = (
    "onboarding_completed",
    "program_activated",
    "workout_started",
    "workout_completed",
    "nutrition_entry_confirmed",
    "weekly_review_completed",
    "recovery_action_confirmed",
    "progress_next_action_completed",
)


class LifecycleMilestone(Base):
    """Privacy-safe, server-confirmed evidence for the first-use product loop."""

    __tablename__ = "lifecycle_milestones"
    __table_args__ = (
        CheckConstraint(
            "milestone_type IN ("
            "'onboarding_completed', 'program_activated', 'workout_started', "
            "'workout_completed', 'nutrition_entry_confirmed', "
            "'weekly_review_completed', 'recovery_action_confirmed', "
            "'progress_next_action_completed'"
            ")",
            name="ck_lifecycle_milestones_type",
        ),
        CheckConstraint("schema_version >= 1", name="ck_lifecycle_milestones_schema_version"),
        CheckConstraint(
            "surface IN ('server')",
            name="ck_lifecycle_milestones_surface",
        ),
        CheckConstraint(
            "authoritative_outcome_status IN ('confirmed')",
            name="ck_lifecycle_milestones_outcome_status",
        ),
        Index(
            "ix_lifecycle_milestones_user_occurred",
            "user_id",
            "occurred_at",
        ),
        Index(
            "ix_lifecycle_milestones_type_occurred",
            "milestone_type",
            "occurred_at",
        ),
        UniqueConstraint(
            "user_id",
            "milestone_type",
            "occurred_at",
            name="uq_lifecycle_milestones_user_type_occurred",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    milestone_type: Mapped[str] = mapped_column(String(48), nullable=False)
    schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    surface: Mapped[str] = mapped_column(String(16), nullable=False, default="server")
    server_confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    authoritative_outcome_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="confirmed", server_default="confirmed"
    )
