from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.db.base import Base


class ExerciseSetupMemory(Base):
    """One private, client-owned setup reminder for a canonical exercise."""

    __tablename__ = "exercise_setup_memories"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "exercise_id",
            name="uq_exercise_setup_memories_user_exercise",
        ),
        CheckConstraint(
            "length(body) BETWEEN 1 AND 240",
            name="ck_exercise_setup_memories_body_length",
        ),
        CheckConstraint("version >= 1", name="ck_exercise_setup_memories_version_positive"),
        Index("ix_exercise_setup_memories_exercise_user", "exercise_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    exercise_id: Mapped[int] = mapped_column(
        ForeignKey("exercises.id", ondelete="CASCADE"), nullable=False, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=now_msk_naive, onupdate=now_msk_naive
    )
