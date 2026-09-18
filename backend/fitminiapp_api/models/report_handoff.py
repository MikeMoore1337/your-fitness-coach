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
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.db.base import Base


class ReportHandoff(Base):
    """Metadata for one explicit, authenticated report handoff.

    The report itself remains live and is rebuilt after authorization checks. This table stores
    only the relationship, selected period, contract metadata and delivery state needed to reopen
    the same authorized view without retaining a second report payload.
    """

    __tablename__ = "report_handoffs"
    __table_args__ = (
        CheckConstraint(
            "period IN ('days_1', 'days_7', 'days_30', 'days_90', 'days_365', "
            "'current_week', 'current_month', 'previous_month', 'custom')",
            name="ck_report_handoffs_period",
        ),
        CheckConstraint("period_end >= period_start", name="ck_report_handoffs_period_order"),
        CheckConstraint("delivery_attempt >= 1", name="ck_report_handoffs_delivery_attempt"),
        CheckConstraint(
            "delivery_status IN ('delivered', 'pending', 'failed')",
            name="ck_report_handoffs_delivery_status",
        ),
        UniqueConstraint(
            "sender_user_id",
            "idempotency_key",
            name="uq_report_handoffs_sender_idempotency",
        ),
        UniqueConstraint(
            "sender_user_id",
            "trainer_user_id",
            "relationship_id",
            "period_start",
            "period_end",
            "report_contract_version",
            "report_revision",
            name="uq_report_handoffs_revision",
        ),
        UniqueConstraint("notification_id", name="uq_report_handoffs_notification"),
        Index("ix_report_handoffs_sender_created", "sender_user_id", "created_at"),
        Index("ix_report_handoffs_trainer_created", "trainer_user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sender_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trainer_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relationship_id: Mapped[int] = mapped_column(
        ForeignKey("coach_clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period: Mapped[str] = mapped_column(String(32), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    report_contract_version: Mapped[str] = mapped_column(String(64), nullable=False)
    included_section_ids: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    report_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    client_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    notification_id: Mapped[int | None] = mapped_column(
        ForeignKey("notifications.id", ondelete="SET NULL"), nullable=True, index=True
    )
    delivery_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    delivery_attempt: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    last_retry_idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=now_msk_naive, server_default=func.now()
    )
