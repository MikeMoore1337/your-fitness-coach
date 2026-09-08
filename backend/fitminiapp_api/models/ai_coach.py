from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.db.base import Base


class AiCoachConsent(Base):
    """Current account decision for the separately gated personal AI Coach route."""

    __tablename__ = "ai_coach_consents"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_ai_coach_consents_user_id"),
        CheckConstraint(
            "status IN ('granted', 'revoked')",
            name="ck_ai_coach_consents_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="revoked")
    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_policy_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    consent_source: Mapped[str] = mapped_column(String(64), nullable=False)
    granted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=now_msk_naive, onupdate=now_msk_naive
    )


__all__ = ["AiCoachConsent"]
