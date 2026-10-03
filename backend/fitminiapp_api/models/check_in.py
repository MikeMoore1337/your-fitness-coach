from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.db.base import Base


class WeeklyCheckIn(Base):
    __tablename__ = "weekly_check_ins"
    __table_args__ = (
        UniqueConstraint("user_id", "week_start", name="uq_weekly_check_ins_user_week"),
        CheckConstraint(
            "status IN ('completed', 'skipped')",
            name="ck_weekly_check_ins_status",
        ),
        CheckConstraint(
            "training_load IS NULL OR training_load BETWEEN 1 AND 5",
            name="ck_weekly_check_ins_training_load",
        ),
        CheckConstraint(
            "recovery IS NULL OR recovery BETWEEN 1 AND 5",
            name="ck_weekly_check_ins_recovery",
        ),
        CheckConstraint(
            "hunger IS NULL OR hunger BETWEEN 1 AND 5",
            name="ck_weekly_check_ins_hunger",
        ),
        CheckConstraint(
            "adherence_difficulty IS NULL OR adherence_difficulty BETWEEN 1 AND 5",
            name="ck_weekly_check_ins_adherence_difficulty",
        ),
        CheckConstraint(
            "progress_action_kind IS NULL OR progress_action_kind IN "
            "('workout', 'nutrition', 'measurement', 'none')",
            name="ck_weekly_check_ins_progress_action_kind",
        ),
        Index("ix_weekly_check_ins_user_created", "user_id", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    week_end: Mapped[date] = mapped_column(Date, nullable=False)
    submitted_on: Mapped[date] = mapped_column(Date, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    summary_version: Mapped[str] = mapped_column(String(32), nullable=False)
    summary: Mapped[dict] = mapped_column(JSON, nullable=False)
    training_load: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recovery: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hunger: Mapped[int | None] = mapped_column(Integer, nullable=True)
    adherence_difficulty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress_action_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    progress_action_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)
