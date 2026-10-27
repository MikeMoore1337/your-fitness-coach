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
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.db.base import Base


class PublicShare(Base):
    """Immutable, owner-revocable public snapshot."""

    __tablename__ = "public_shares"
    __table_args__ = (
        CheckConstraint(
            "share_type IN ('progress', 'program')",
            name="ck_public_shares_type",
        ),
        CheckConstraint(
            "status IN ('active', 'revoked')",
            name="ck_public_shares_status",
        ),
        Index("ix_public_shares_share_id", "share_id", unique=True),
        Index("ix_public_shares_owner_created", "owner_user_id", "created_at"),
        Index("ix_public_shares_owner_status", "owner_user_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    share_id: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    share_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    public_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    private_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=now_msk_naive, server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PublicShareImport(Base):
    """Recipient-side provenance that bounds one import per public snapshot."""

    __tablename__ = "public_share_imports"
    __table_args__ = (
        UniqueConstraint(
            "public_share_id",
            "recipient_user_id",
            name="uq_public_share_imports_share_recipient",
        ),
        Index("ix_public_share_imports_recipient_created", "recipient_user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_share_id: Mapped[int | None] = mapped_column(
        ForeignKey("public_shares.id", ondelete="SET NULL"), nullable=True, index=True
    )
    recipient_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("program_templates.id", ondelete="SET NULL"), nullable=True
    )
    user_program_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_programs.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=now_msk_naive, server_default=func.now()
    )
