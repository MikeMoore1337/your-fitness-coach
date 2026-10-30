from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
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


class WorkoutExerciseNote(Base):
    __tablename__ = "workout_exercise_notes"
    __table_args__ = (
        UniqueConstraint("workout_id", "context_key", name="uq_workout_exercise_notes_context"),
        CheckConstraint("version >= 1", name="ck_workout_exercise_notes_version"),
        CheckConstraint(
            "body IS NULL OR length(body) <= 500", name="ck_workout_exercise_notes_body_length"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workout_id: Mapped[int] = mapped_column(
        ForeignKey("user_workouts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Immutable occurrence identity survives a removed or replaced exercise row.
    workout_exercise_id: Mapped[int] = mapped_column(Integer, nullable=False)
    exercise_id: Mapped[int] = mapped_column(Integer, nullable=False)
    context_key: Mapped[str] = mapped_column(String(64), nullable=False)
    source_template_exercise_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    plan_revision_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    week_type: Mapped[str | None] = mapped_column(String(8), nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)


class WorkoutExerciseNoteMutation(Base):
    __tablename__ = "workout_exercise_note_mutations"
    __table_args__ = (
        UniqueConstraint("user_id", "mutation_id", name="uq_workout_exercise_note_mutation"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    note_id: Mapped[int] = mapped_column(
        ForeignKey("workout_exercise_notes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    mutation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    applied_version: Mapped[int] = mapped_column(Integer, nullable=False)
