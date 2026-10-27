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


class NutritionLabelDraft(Base):
    """Short-lived owner-scoped canonical draft; source bytes are never persisted."""

    __tablename__ = "nutrition_label_drafts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'confirmed', 'cancelled', 'expired')",
            name="ck_nutrition_label_drafts_status",
        ),
        CheckConstraint("revision > 0", name="ck_nutrition_label_drafts_revision"),
        UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_nutrition_label_drafts_user_idempotency",
        ),
        Index("ix_nutrition_label_drafts_user_status", "user_id", "status", "expires_at"),
        Index("ix_nutrition_label_drafts_expires_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft", server_default="draft"
    )
    canonical_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    product_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    product_brand: Mapped[str | None] = mapped_column(String(128), nullable=True)
    product_barcode: Mapped[str | None] = mapped_column(String(14), nullable=True)
    confirmed_visibility: Mapped[str | None] = mapped_column(String(24), nullable=True)
    confirmed_food_id: Mapped[int | None] = mapped_column(
        ForeignKey("foods.id", ondelete="SET NULL"), nullable=True
    )
    ocr_engine: Mapped[str] = mapped_column(String(32), nullable=False)
    ocr_engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source_mime: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=now_msk_naive, onupdate=now_msk_naive
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class NutritionCatalogContribution(Base):
    """A confirmed package-facts submission, separated from public catalog identity."""

    __tablename__ = "nutrition_catalog_contributions"
    __table_args__ = (
        CheckConstraint(
            "state IN ('accepted', 'duplicate', 'conflict')",
            name="ck_nutrition_catalog_contributions_state",
        ),
        CheckConstraint(
            "visibility = 'share_to_yfc_catalog'",
            name="ck_nutrition_catalog_contributions_visibility",
        ),
        UniqueConstraint(
            "food_id",
            "payload_digest",
            name="uq_nutrition_catalog_contributions_food_digest",
        ),
        Index(
            "ix_nutrition_catalog_contributions_food_created",
            "food_id",
            "created_at",
        ),
        Index(
            "ix_nutrition_catalog_contributions_contributor_created",
            "contributor_user_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    food_id: Mapped[int] = mapped_column(ForeignKey("foods.id", ondelete="CASCADE"), nullable=False)
    contributor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    visibility: Mapped[str] = mapped_column(
        String(24), nullable=False, default="share_to_yfc_catalog"
    )
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    payload_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=now_msk_naive, onupdate=now_msk_naive
    )
