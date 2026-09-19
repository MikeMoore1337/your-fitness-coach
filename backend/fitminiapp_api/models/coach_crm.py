"""Trainer operations: business sessions, packages, payments and tasks."""

from __future__ import annotations

from datetime import date, datetime, time

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
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.db.base import Base


class CoachSessionSeries(Base):
    __tablename__ = "coach_session_series"
    __table_args__ = (
        CheckConstraint("recurrence_kind = 'weekly'", name="ck_coach_series_recurrence_kind"),
        CheckConstraint(
            "duration_minutes BETWEEN 15 AND 480",
            name="ck_coach_series_duration_minutes",
        ),
        CheckConstraint(
            "occurrence_count IS NULL OR occurrence_count BETWEEN 1 AND 52",
            name="ck_coach_series_occurrence_count",
        ),
        CheckConstraint(
            "recurrence_end_date IS NULL OR recurrence_end_date >= start_date",
            name="ck_coach_series_date_order",
        ),
        CheckConstraint(
            "format IN ('gym', 'online', 'other')",
            name="ck_coach_series_format",
        ),
        UniqueConstraint(
            "coach_user_id",
            "idempotency_key",
            name="uq_coach_session_series_coach_idempotency",
        ),
        Index("ix_coach_session_series_coach_status", "coach_user_id", "status", "start_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    coach_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    client_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    package_id: Mapped[int | None] = mapped_column(
        ForeignKey("coach_packages.id", ondelete="SET NULL"), nullable=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    recurrence_kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default="weekly", server_default="weekly"
    )
    weekdays: Mapped[list[int]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    recurrence_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    occurrence_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    format: Mapped[str] = mapped_column(String(16), nullable=False, default="other")
    location: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default="active"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)


class CoachBusinessSession(Base):
    __tablename__ = "coach_business_sessions"
    __table_args__ = (
        CheckConstraint(
            "duration_minutes BETWEEN 15 AND 480",
            name="ck_coach_business_sessions_duration_minutes",
        ),
        CheckConstraint(
            "status IN ('scheduled', 'completed', 'cancelled', 'no_show')",
            name="ck_coach_business_sessions_status",
        ),
        CheckConstraint(
            "format IN ('gym', 'online', 'other')",
            name="ck_coach_business_sessions_format",
        ),
        CheckConstraint(
            "private_note IS NULL OR length(private_note) <= 2000",
            name="ck_coach_business_sessions_private_note_length",
        ),
        UniqueConstraint(
            "series_id",
            "occurrence_key",
            name="uq_coach_business_sessions_series_occurrence",
        ),
        UniqueConstraint(
            "coach_user_id",
            "idempotency_key",
            name="uq_coach_business_sessions_coach_idempotency",
        ),
        Index(
            "ix_coach_business_sessions_coach_start_status",
            "coach_user_id",
            "starts_at_utc",
            "status",
        ),
        Index(
            "ix_coach_business_sessions_client_start_status",
            "client_user_id",
            "starts_at_utc",
            "status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    coach_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    client_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    series_id: Mapped[int | None] = mapped_column(
        ForeignKey("coach_session_series.id", ondelete="SET NULL"), nullable=True
    )
    package_id: Mapped[int | None] = mapped_column(
        ForeignKey("coach_packages.id", ondelete="SET NULL"), nullable=True
    )
    user_workout_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_workouts.id", ondelete="SET NULL"), nullable=True
    )
    occurrence_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    starts_at_utc: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    format: Mapped[str] = mapped_column(String(16), nullable=False, default="other")
    location: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="scheduled", server_default="scheduled"
    )
    private_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)


class CoachPackage(Base):
    __tablename__ = "coach_packages"
    __table_args__ = (
        CheckConstraint(
            "NOT counts_sessions OR included_sessions IS NOT NULL",
            name="ck_coach_packages_count_requires_total",
        ),
        CheckConstraint(
            "included_sessions IS NULL OR included_sessions BETWEEN 1 AND 1000",
            name="ck_coach_packages_included_sessions",
        ),
        CheckConstraint(
            "state IN ('active', 'finished', 'cancelled')",
            name="ck_coach_packages_state",
        ),
        CheckConstraint(
            "expires_on IS NULL OR starts_on IS NULL OR expires_on >= starts_on",
            name="ck_coach_packages_date_order",
        ),
        UniqueConstraint(
            "coach_user_id",
            "idempotency_key",
            name="uq_coach_packages_coach_idempotency",
        ),
        Index("ix_coach_packages_coach_client_state", "coach_user_id", "client_user_id", "state"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    coach_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    client_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    counts_sessions: Mapped[bool] = mapped_column(
        nullable=False, default=True, server_default="true"
    )
    included_sessions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    starts_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default="active"
    )
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)


class CoachPackageLedgerEntry(Base):
    __tablename__ = "coach_package_ledger"
    __table_args__ = (
        CheckConstraint(
            "entry_type IN ('charge', 'reversal')",
            name="ck_coach_package_ledger_entry_type",
        ),
        CheckConstraint("quantity > 0", name="ck_coach_package_ledger_quantity"),
        UniqueConstraint("idempotency_key", name="uq_coach_package_ledger_idempotency"),
        Index("ix_coach_package_ledger_package_created", "package_id", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    package_id: Mapped[int] = mapped_column(
        ForeignKey("coach_packages.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("coach_business_sessions.id", ondelete="SET NULL"), nullable=True
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    entry_type: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)


class CoachPayment(Base):
    __tablename__ = "coach_payments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('expected', 'partial', 'paid', 'cancelled')",
            name="ck_coach_payments_status",
        ),
        CheckConstraint("expected_amount_minor > 0", name="ck_coach_payments_expected_amount"),
        CheckConstraint(
            "paid_amount_minor >= 0 AND paid_amount_minor <= expected_amount_minor",
            name="ck_coach_payments_paid_amount",
        ),
        UniqueConstraint(
            "coach_user_id", "idempotency_key", name="uq_coach_payments_coach_idempotency"
        ),
        Index(
            "ix_coach_payments_coach_client_date", "coach_user_id", "client_user_id", "payment_date"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    coach_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    client_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    package_id: Mapped[int | None] = mapped_column(
        ForeignKey("coach_packages.id", ondelete="SET NULL"), nullable=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    expected_amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    paid_amount_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="expected", server_default="expected"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)


class CoachTask(Base):
    __tablename__ = "coach_tasks"
    __table_args__ = (
        CheckConstraint("state IN ('open', 'completed')", name="ck_coach_tasks_state"),
        CheckConstraint("length(trim(title)) BETWEEN 1 AND 240", name="ck_coach_tasks_title"),
        UniqueConstraint(
            "coach_user_id", "idempotency_key", name="uq_coach_tasks_coach_idempotency"
        ),
        Index("ix_coach_tasks_coach_state_due", "coach_user_id", "state", "due_at_utc"),
        Index("ix_coach_tasks_client_due", "client_user_id", "due_at_utc"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    coach_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    client_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    due_at_utc: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="open", server_default="open"
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)
