from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.db.base import Base


class NutritionNotesConsent(Base):
    __tablename__ = "nutrition_notes_consents"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_nutrition_notes_consent_user"),
        CheckConstraint(
            "status IN ('enabled', 'disabled', 'revoked', 'recovery_hold')",
            name="ck_nutrition_notes_consent_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(32), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class NutritionMealNote(Base):
    __tablename__ = "nutrition_meal_notes"
    __table_args__ = (
        UniqueConstraint("user_id", "local_date", "meal_type", name="uq_nutrition_meal_note_group"),
        CheckConstraint(
            "meal_type IN ('breakfast', 'lunch', 'dinner', 'snacks')",
            name="ck_nutrition_meal_note_type",
        ),
        CheckConstraint(
            "hunger_before IS NULL OR hunger_before IN ('none', 'low', 'medium', 'high')",
            name="ck_nutrition_meal_note_hunger",
        ),
        CheckConstraint(
            "fullness_after IS NULL OR fullness_after IN ('none', 'low', 'medium', 'high')",
            name="ck_nutrition_meal_note_fullness",
        ),
        CheckConstraint(
            "energy IS NULL OR energy IN ('low', 'normal', 'high')",
            name="ck_nutrition_meal_note_energy",
        ),
        CheckConstraint(
            "note IS NULL OR length(note) <= 500", name="ck_nutrition_meal_note_text_length"
        ),
        CheckConstraint(
            "hunger_before IS NOT NULL OR fullness_after IS NOT NULL OR energy IS NOT NULL OR note IS NOT NULL",
            name="ck_nutrition_meal_note_nonempty",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    meal_type: Mapped[str] = mapped_column(String(16), nullable=False)
    timezone_at_entry: Mapped[str] = mapped_column(String(64), nullable=False)
    hunger_before: Mapped[str | None] = mapped_column(String(16), nullable=True)
    fullness_after: Mapped[str | None] = mapped_column(String(16), nullable=True)
    energy: Mapped[str | None] = mapped_column(String(16), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=now_msk_naive, onupdate=now_msk_naive
    )
