"""Trainer-owned onboarding and communication workflow templates."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
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


class CoachWorkflowTemplate(Base):
    __tablename__ = "coach_workflow_templates"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('onboarding', 'communication')",
            name="ck_coach_workflow_template_kind",
        ),
        CheckConstraint(
            "length(name) BETWEEN 1 AND 128",
            name="ck_coach_workflow_template_name",
        ),
        UniqueConstraint(
            "coach_user_id",
            "idempotency_key",
            name="uq_coach_workflow_template_coach_idempotency",
        ),
        Index(
            "ix_coach_workflow_template_coach_kind_updated",
            "coach_user_id",
            "kind",
            "updated_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    coach_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="true")
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    request_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)


class CoachWorkflowTemplateVersion(Base):
    __tablename__ = "coach_workflow_template_versions"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_coach_workflow_template_version_number"),
        UniqueConstraint(
            "template_id",
            "version",
            name="uq_coach_workflow_template_version_number",
        ),
        UniqueConstraint(
            "template_id",
            "idempotency_key",
            name="uq_coach_workflow_template_version_idempotency",
        ),
        Index(
            "ix_coach_workflow_template_version_template_version",
            "template_id",
            "version",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("coach_workflow_templates.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    request_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)


class CoachWorkflowAssignment(Base):
    __tablename__ = "coach_workflow_assignments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('assigned', 'completed', 'revoked')",
            name="ck_coach_workflow_assignment_status",
        ),
        UniqueConstraint(
            "coach_user_id",
            "idempotency_key",
            name="uq_coach_workflow_assignment_coach_idempotency",
        ),
        Index(
            "ix_coach_workflow_assignment_coach_template",
            "coach_user_id",
            "template_id",
            "created_at",
        ),
        Index(
            "ix_coach_workflow_assignment_client_created",
            "client_user_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("coach_workflow_templates.id", ondelete="CASCADE"), nullable=False
    )
    template_version_id: Mapped[int] = mapped_column(
        ForeignKey("coach_workflow_template_versions.id", ondelete="RESTRICT"), nullable=False
    )
    coach_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    client_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="assigned", server_default="assigned"
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    request_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)


class CoachCommunicationDraft(Base):
    __tablename__ = "coach_communication_drafts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'confirmed')",
            name="ck_coach_communication_draft_status",
        ),
        CheckConstraint(
            "length(trim(subject)) BETWEEN 1 AND 128",
            name="ck_coach_communication_draft_subject",
        ),
        CheckConstraint(
            "length(trim(body)) BETWEEN 1 AND 4000",
            name="ck_coach_communication_draft_body",
        ),
        UniqueConstraint(
            "coach_user_id",
            "idempotency_key",
            name="uq_coach_communication_draft_coach_idempotency",
        ),
        UniqueConstraint(
            "coach_user_id",
            "confirm_idempotency_key",
            name="uq_coach_communication_draft_confirm_idempotency",
        ),
        Index(
            "ix_coach_communication_draft_coach_client_updated",
            "coach_user_id",
            "client_user_id",
            "updated_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("coach_workflow_templates.id", ondelete="CASCADE"), nullable=False
    )
    template_version_id: Mapped[int] = mapped_column(
        ForeignKey("coach_workflow_template_versions.id", ondelete="RESTRICT"), nullable=False
    )
    coach_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    client_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    subject: Mapped[str] = mapped_column(String(128), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft", server_default="draft"
    )
    notification_id: Mapped[int | None] = mapped_column(
        ForeignKey("notifications.id", ondelete="SET NULL"), nullable=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    request_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confirm_idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    confirm_request_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)


__all__ = [
    "CoachCommunicationDraft",
    "CoachWorkflowAssignment",
    "CoachWorkflowTemplate",
    "CoachWorkflowTemplateVersion",
]
