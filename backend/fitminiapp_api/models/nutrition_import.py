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

from fitminiapp_api.db.base import Base


class NutritionImportDraft(Base):
    __tablename__ = "nutrition_import_drafts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'confirmed', 'cancelled')",
            name="ck_nutrition_import_draft_status",
        ),
        CheckConstraint("revision >= 1", name="ck_nutrition_import_draft_revision"),
        UniqueConstraint(
            "owner_user_id", "upload_key_hash", name="uq_nutrition_import_owner_upload"
        ),
        UniqueConstraint(
            "owner_user_id", "confirm_key_hash", name="uq_nutrition_import_owner_confirm"
        ),
        Index(
            "uq_nutrition_import_owner_catalog_confirm",
            "owner_user_id",
            "catalog_confirm_key_hash",
            unique=True,
        ),
        Index("ix_nutrition_import_owner_created", "owner_user_id", "created_at"),
        Index("ix_nutrition_import_expiry", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    upload_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    upload_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(64), nullable=False)
    adapter_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    document_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    document: Mapped[dict] = mapped_column(JSON, nullable=False)
    skipped_rows: Mapped[list] = mapped_column(JSON, nullable=False)
    resolutions: Mapped[dict] = mapped_column(JSON, nullable=False)
    confirm_key_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confirm_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    receipt: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    catalog_confirm_key_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    catalog_confirm_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    catalog_receipt: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class NutritionImportUploadAttempt(Base):
    __tablename__ = "nutrition_import_upload_attempts"
    __table_args__ = (
        Index("ix_nutrition_import_attempt_owner_time", "owner_user_id", "created_at"),
        Index("ix_nutrition_import_attempt_expiry", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
