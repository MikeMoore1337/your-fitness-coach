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
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.db.base import Base


class ProgramImport(Base):
    """Owner-scoped, short-lived normalized draft for deterministic program import."""

    __tablename__ = "program_imports"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'confirmed', 'cancelled', 'expired')",
            name="ck_program_imports_status",
        ),
        # source_format is kept compatible with the original 0076 check.  New
        # document formats are stored in document_format until the old check can
        # be replaced by a separately approved schema migration.
        CheckConstraint("source_format IN ('csv', 'xlsx')", name="ck_program_imports_format"),
        Index("ix_program_imports_owner_status_expiry", "owner_user_id", "status", "expires_at"),
        Index("ix_program_imports_hash_status", "owner_user_id", "source_sha256", "status"),
        Index(
            "uq_program_imports_pending_hash",
            "owner_user_id",
            "source_sha256",
            unique=True,
            postgresql_where=text("status = 'pending'"),
            sqlite_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source_format: Mapped[str] = mapped_column(String(8), nullable=False)
    document_format: Mapped[str | None] = mapped_column(String(8), nullable=True)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    parser_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    draft_json: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    cell_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    blocking_issue_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    warning_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    confirmed_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("program_templates.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=now_msk_naive, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=now_msk_naive, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
