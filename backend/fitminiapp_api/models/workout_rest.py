"""Measured between-set rest intervals, independent of planned exercise prescriptions."""

from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from fitminiapp_api.db.base import Base


def utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class WorkoutRestSession(Base):
    __tablename__ = "workout_rest_sessions"
    __table_args__ = (
        # Existing sessions have predecessor_id=NULL and retain their original IDs.
        # Partial uniqueness lets a finished interval have one new successor.
        Index(
            "uq_workout_rest_initial_source",
            "source_set_id",
            unique=True,
            postgresql_where=text("predecessor_id IS NULL"),
            sqlite_where=text("predecessor_id IS NULL"),
        ),
        Index("uq_workout_rest_predecessor", "predecessor_id", unique=True),
        Index("uq_workout_rest_start_mutation", "workout_id", "start_mutation_id", unique=True),
        Index(
            "uq_workout_rest_running_workout",
            "workout_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
            sqlite_where=text("status = 'running'"),
        ),
        CheckConstraint("planned_seconds > 0", name="ck_workout_rest_plan_positive"),
        CheckConstraint("adjusted_seconds > 0", name="ck_workout_rest_adjusted_positive"),
        CheckConstraint("version >= 1", name="ck_workout_rest_version_positive"),
        CheckConstraint(
            "status IN ('running','completed','skipped','interrupted','unknown')",
            name="ck_workout_rest_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    workout_id: Mapped[int] = mapped_column(
        ForeignKey("user_workouts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_set_id: Mapped[int] = mapped_column(
        ForeignKey("user_workout_sets.id", ondelete="CASCADE"), nullable=False
    )
    predecessor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_mutation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    start_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    planned_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    adjusted_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    measured_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    quality: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, nullable=False)


class WorkoutRestAction(Base):
    __tablename__ = "workout_rest_actions"
    __table_args__ = (
        UniqueConstraint("session_id", "mutation_id", name="uq_workout_rest_action_mutation"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("workout_rest_sessions.id", ondelete="CASCADE"), nullable=False
    )
    mutation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    applied_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, nullable=False)
