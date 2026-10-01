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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.db.base import Base


class PhotoMealDraft(Base):
    """Short-lived owner-scoped meal draft; the source photo is never persisted."""

    __tablename__ = "photo_meal_drafts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'confirmed', 'cancelled', 'expired')",
            name="ck_photo_meal_drafts_status",
        ),
        CheckConstraint("revision > 0", name="ck_photo_meal_drafts_revision"),
        UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_photo_meal_drafts_user_idempotency",
        ),
        Index("ix_photo_meal_drafts_user_status", "user_id", "status", "expires_at"),
        Index("ix_photo_meal_drafts_expires_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft", server_default="draft"
    )
    canonical_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_mime: Mapped[str] = mapped_column(String(64), nullable=False)
    confirmed_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("food_diary_entries.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=now_msk_naive, onupdate=now_msk_naive
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
