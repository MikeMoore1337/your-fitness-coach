"""Trainer-owned review state for client weekly check-ins."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
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


class CoachCheckInReview(Base):
    __tablename__ = "coach_check_in_reviews"
    __table_args__ = (
        CheckConstraint("status IN ('reviewed')", name="ck_coach_check_in_reviews_status"),
        CheckConstraint(
            "response IS NULL OR length(response) <= 2000",
            name="ck_coach_check_in_reviews_response_length",
        ),
        UniqueConstraint(
            "coach_user_id",
            "check_in_id",
            name="uq_coach_check_in_reviews_coach_check_in",
        ),
        Index(
            "ix_coach_check_in_reviews_coach_status",
            "coach_user_id",
            "status",
            "reviewed_at",
        ),
        Index(
            "ix_coach_check_in_reviews_client_check_in",
            "client_user_id",
            "check_in_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    coach_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    client_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    check_in_id: Mapped[int] = mapped_column(
        ForeignKey("weekly_check_ins.id", ondelete="CASCADE"), nullable=False
    )
    follow_up_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("coach_tasks.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="reviewed", server_default="reviewed"
    )
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)


__all__ = ["CoachCheckInReview"]
