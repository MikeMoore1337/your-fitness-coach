from __future__ import annotations

from datetime import datetime, time

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.db.base import Base

REMINDER_TEMPLATE_KEYS = ("meal_logging", "hydration", "movement_break")


class ReminderTemplateSchedule(Base):
    """User-owned schedule configuration for one contextual reminder template."""

    __tablename__ = "reminder_template_schedules"
    __table_args__ = (
        CheckConstraint(
            "template_key IN ('meal_logging', 'hydration', 'movement_break')",
            name="ck_reminder_template_schedules_key",
        ),
        CheckConstraint(
            "template_version IN ('v1')",
            name="ck_reminder_template_schedules_version",
        ),
        CheckConstraint(
            "max_per_day BETWEEN 1 AND 8",
            name="ck_reminder_template_schedules_max_per_day",
        ),
        CheckConstraint(
            "minimum_spacing_minutes BETWEEN 15 AND 720",
            name="ck_reminder_template_schedules_spacing",
        ),
        CheckConstraint(
            "interval_minutes IS NULL OR interval_minutes BETWEEN 30 AND 360",
            name="ck_reminder_template_schedules_interval",
        ),
        CheckConstraint(
            "(window_start IS NULL AND window_end IS NULL) OR "
            "(window_start IS NOT NULL AND window_end IS NOT NULL AND window_start < window_end)",
            name="ck_reminder_template_schedules_window",
        ),
        UniqueConstraint(
            "user_id",
            "template_key",
            name="uq_reminder_template_schedules_user_key",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    template_key: Mapped[str] = mapped_column(String(32), nullable=False)
    template_version: Mapped[str] = mapped_column(String(16), nullable=False, default="v1")
    weekdays: Mapped[list[int]] = mapped_column(
        JSON,
        nullable=False,
        default=lambda: list(range(7)),
        server_default="[0,1,2,3,4,5,6]",
    )
    schedule_times: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    window_start: Mapped[time | None] = mapped_column(nullable=True)
    window_end: Mapped[time | None] = mapped_column(nullable=True)
    interval_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    minimum_spacing_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=120, server_default="120"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=now_msk_naive, onupdate=now_msk_naive
    )
