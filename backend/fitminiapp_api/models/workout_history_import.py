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


class WorkoutHistoryImportDraft(Base):
    __tablename__ = "workout_history_import_drafts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'confirmed', 'cancelled', 'expired')",
            name="ck_workout_history_import_draft_status",
        ),
        CheckConstraint("version >= 1", name="ck_workout_history_import_draft_version"),
        Index("ix_workout_history_import_drafts_expiry", "expires_at"),
        Index("ix_workout_history_import_drafts_owner", "owner_user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    parser_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    draft_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class ImportedWorkout(Base):
    __tablename__ = "imported_workouts"
    __table_args__ = (
        UniqueConstraint(
            "owner_user_id", "provider", "source_ref_hash", name="uq_imported_workouts_source"
        ),
        UniqueConstraint("owner_user_id", "fact_hash", name="uq_imported_workouts_facts"),
        Index("ix_imported_workouts_owner", "owner_user_id"),
    )

    workout_id: Mapped[int] = mapped_column(
        ForeignKey("user_workouts.id", ondelete="CASCADE"), primary_key=True
    )
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    source_ref_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    fact_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(32), nullable=False)
    source_timezone: Mapped[str] = mapped_column(String(128), nullable=False)
