"""Versioned trainer check-in templates and client responses."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.db.base import Base


class CoachCheckInTemplate(Base):
    __tablename__ = "coach_check_in_templates"
    __table_args__ = (
        CheckConstraint("length(name) BETWEEN 1 AND 128", name="ck_check_in_template_name"),
        CheckConstraint(
            "cadence IN ('weekly', 'biweekly', 'monthly')",
            name="ck_check_in_template_cadence",
        ),
        UniqueConstraint(
            "coach_user_id",
            "idempotency_key",
            name="uq_check_in_template_coach_idempotency",
        ),
        Index(
            "ix_check_in_template_coach_active_updated",
            "coach_user_id",
            "is_active",
            "updated_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    coach_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cadence: Mapped[str] = mapped_column(String(16), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    request_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)


class CoachCheckInTemplateVersion(Base):
    __tablename__ = "coach_check_in_template_versions"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_check_in_template_version_number"),
        UniqueConstraint("template_id", "version", name="uq_check_in_template_version_number"),
        UniqueConstraint(
            "template_id",
            "idempotency_key",
            name="uq_check_in_template_version_idempotency",
        ),
        Index("ix_check_in_template_version_template_version", "template_id", "version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("coach_check_in_templates.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    field_definitions: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    request_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)


class CoachCheckInAssignment(Base):
    __tablename__ = "coach_check_in_assignments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'revoked')",
            name="ck_check_in_assignment_status",
        ),
        UniqueConstraint(
            "template_id",
            "client_user_id",
            name="uq_check_in_assignment_template_client",
        ),
        UniqueConstraint(
            "coach_user_id",
            "idempotency_key",
            name="uq_check_in_assignment_coach_idempotency",
        ),
        Index("ix_check_in_assignment_coach_status", "coach_user_id", "status"),
        Index("ix_check_in_assignment_client_status", "client_user_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("coach_check_in_templates.id", ondelete="CASCADE"), nullable=False
    )
    template_version_id: Mapped[int] = mapped_column(
        ForeignKey("coach_check_in_template_versions.id", ondelete="RESTRICT"), nullable=False
    )
    coach_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    client_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default="active"
    )
    next_due_on: Mapped[date] = mapped_column(Date, nullable=False)
    last_response_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    request_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)


class CoachCheckInResponse(Base):
    __tablename__ = "coach_check_in_responses"
    __table_args__ = (
        UniqueConstraint(
            "assignment_id",
            "due_on",
            name="uq_check_in_response_assignment_due",
        ),
        UniqueConstraint(
            "client_user_id",
            "idempotency_key",
            name="uq_check_in_response_client_idempotency",
        ),
        Index(
            "ix_check_in_response_client_submitted",
            "client_user_id",
            "submitted_at",
        ),
        Index(
            "ix_check_in_response_coach_template",
            "coach_user_id",
            "template_id",
            "submitted_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("coach_check_in_assignments.id", ondelete="CASCADE"), nullable=False
    )
    template_id: Mapped[int] = mapped_column(
        ForeignKey("coach_check_in_templates.id", ondelete="CASCADE"), nullable=False
    )
    template_version_id: Mapped[int] = mapped_column(
        ForeignKey("coach_check_in_template_versions.id", ondelete="RESTRICT"), nullable=False
    )
    coach_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    client_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    due_on: Mapped[date] = mapped_column(Date, nullable=False)
    values: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)


__all__ = [
    "CoachCheckInAssignment",
    "CoachCheckInResponse",
    "CoachCheckInTemplate",
    "CoachCheckInTemplateVersion",
]
