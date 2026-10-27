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
    "workout_missed",
    "nutrition_entry_confirmed",
    "weekly_review_completed",
    "recovery_action_confirmed",
    "progress_next_action_completed",
)

# Version 1 is retained for rows written by the first Product v7 stage.  New
# writes use version 2 after the instance-scoped recovery fields were added.
# Reporting treats anything outside this allowlist as malformed instead of
# silently interpreting a future schema as current data.
LIFECYCLE_MILESTONE_SCHEMA_VERSIONS = frozenset({1, 2})
LIFECYCLE_MILESTONE_CURRENT_SCHEMA_VERSION = 2


class LifecycleMilestone(Base):
    """Privacy-safe, server-confirmed evidence for the first-use product loop."""

    __tablename__ = "lifecycle_milestones"
    __table_args__ = (
        CheckConstraint(
            "milestone_type IN ("
            "'onboarding_completed', 'program_activated', 'workout_started', "
            "'workout_completed', 'workout_missed', 'nutrition_entry_confirmed', "
            "'weekly_review_completed', 'recovery_action_confirmed', "
            "'progress_next_action_completed'"
            ") AND (workout_id IS NULL OR workout_id >= 1) "
            "AND (program_id IS NULL OR program_id >= 1) "
            "AND (program_revision_number IS NULL OR program_revision_number >= 0)",
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
        Index(
            "ix_lifecycle_milestones_type_workout",
            "milestone_type",
            "workout_id",
        ),
        UniqueConstraint(
            "user_id",
            "milestone_type",
            "occurred_at",
            name="uq_lifecycle_milestones_user_type_occurred",
        ),
        Index(
            "uq_lifecycle_milestones_user_type_workout",
            "user_id",
            "milestone_type",
            "workout_id",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    milestone_type: Mapped[str] = mapped_column(String(48), nullable=False)
    schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # These are internal, server-owned identifiers only. They let recovery
    # metrics join one authoritative workout instance without storing schedule
    # payloads, exercise data, or free text in the lifecycle ledger.
    workout_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    program_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    program_revision_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    missed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    surface: Mapped[str] = mapped_column(String(16), nullable=False, default="server")
    server_confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    authoritative_outcome_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="confirmed", server_default="confirmed"
    )
