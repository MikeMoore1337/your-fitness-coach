from __future__ import annotations

from datetime import datetime, time

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.db.base import Base


class NotificationSetting(Base):
    __tablename__ = "notification_settings"
    __table_args__ = (
        CheckConstraint(
            "(quiet_hours_start IS NULL AND quiet_hours_end IS NULL) OR "
            "(quiet_hours_start IS NOT NULL AND quiet_hours_end IS NOT NULL)",
            name="ck_notification_settings_quiet_hours_pair",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    workout_reminders_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    weekly_check_in_reminders_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    measurement_reminders_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    meal_reminders_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=True
    )
    hydration_reminders_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=True
    )
    movement_reminders_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=True
    )
    telegram_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    reminder_hour: Mapped[int] = mapped_column(Integer, default=9)
    quiet_hours_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    quiet_hours_end: Mapped[time | None] = mapped_column(Time, nullable=True)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_notifications_dedupe_key"),
        CheckConstraint(
            "action_url IS NULL OR action_url = '/app' OR action_url LIKE '/app?%'",
            name="ck_notifications_internal_action_url",
        ),
        CheckConstraint(
            "event_kind IN ('reminder', 'transactional', 'security')",
            name="ck_notifications_event_kind",
        ),
        Index(
            "ix_notifications_due_queue",
            "scheduled_for_utc",
            "next_attempt_at",
            postgresql_where=text("status = 'queued'"),
            sqlite_where=text("status = 'queued'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    channel: Mapped[str] = mapped_column(String(32), default="telegram")
    category: Mapped[str] = mapped_column(String(48), default="custom_reminder")
    event_kind: Mapped[str] = mapped_column(String(24), default="reminder")
    title: Mapped[str] = mapped_column(String(128))
    body: Mapped[str] = mapped_column(Text)
    # scheduled_for остаётся локальным wall time для показа пользователю.
    # UTC-колонка используется worker-ом для индексируемого поиска срока доставки.
    scheduled_for: Mapped[datetime] = mapped_column(DateTime, index=True)
    scheduled_for_utc: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=now_msk_naive,
        server_default=func.now(),
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    action_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class WebPushSubscription(Base):
    """One browser capability owned by exactly one account."""

    __tablename__ = "web_push_subscriptions"
    __table_args__ = (
        UniqueConstraint("endpoint_hash", name="uq_web_push_subscriptions_endpoint_hash"),
        Index("ix_web_push_subscriptions_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # The endpoint is a bearer-like capability. It is never returned, logged, or exported.
    endpoint: Mapped[str] = mapped_column(String(2048), nullable=False)
    endpoint_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    p256dh: Mapped[str] = mapped_column(String(128), nullable=False)
    auth: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=now_msk_naive,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=now_msk_naive,
        onupdate=now_msk_naive,
        server_default=func.now(),
    )
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    failure_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_error: Mapped[str | None] = mapped_column(String(128), nullable=True)


class NotificationDelivery(Base):
    """Per-subscription delivery state for the canonical notification event."""

    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "notification_id",
            "subscription_id",
            name="uq_notification_deliveries_notification_subscription",
        ),
        CheckConstraint(
            "channel = 'web_push'",
            name="ck_notification_deliveries_web_push_channel",
        ),
        Index("ix_notification_deliveries_notification_id", "notification_id"),
        Index("ix_notification_deliveries_subscription_id", "subscription_id"),
        Index("ix_notification_deliveries_next_attempt_at", "next_attempt_at"),
        Index(
            "ix_notification_deliveries_due_queue",
            "status",
            "next_attempt_at",
            "id",
            postgresql_where=text("status = 'queued'"),
            sqlite_where=text("status = 'queued'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    notification_id: Mapped[int] = mapped_column(
        ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False
    )
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("web_push_subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[str] = mapped_column(
        String(32), nullable=False, default="web_push", server_default="web_push"
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="queued", server_default="queued"
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_error: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=now_msk_naive,
        server_default=func.now(),
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
