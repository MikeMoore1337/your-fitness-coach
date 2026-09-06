from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.db.base import Base
from fitminiapp_api.models.exercise import Exercise, Muscle


class ProgramTemplate(Base):
    __tablename__ = "program_templates"
    __table_args__ = (
        CheckConstraint(
            "split_type IS NULL OR split_type IN "
            "('full_body', 'upper_lower', 'push_pull_legs', 'body_part', 'hybrid')",
            name="ck_program_templates_split_type",
        ),
        CheckConstraint(
            "default_duration_weeks >= 1 AND default_duration_weeks <= 24",
            name="ck_program_templates_default_duration_weeks",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(128))
    goal: Mapped[str] = mapped_column(String(32))
    level: Mapped[str] = mapped_column(String(32))
    split_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=True
    )
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    # The online expand keeps this column nullable; legacy NULL rows use the effective
    # one-week value below while creation/update paths provide a validated default.
    default_duration_weeks: Mapped[int] = mapped_column(
        Integer, nullable=True, default=1, server_default="1"
    )

    @property
    def effective_duration_weeks(self) -> int:
        return self.default_duration_weeks or 1

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=now_msk_naive,
        server_default=func.now(),
    )

    days: Mapped[list[ProgramTemplateDay]] = relationship(
        "ProgramTemplateDay",
        back_populates="program",
        cascade="all, delete-orphan",
        order_by="ProgramTemplateDay.day_number",
    )


class HiddenProgramTemplate(Base):
    """A system example hidden from one user's personal library."""

    __tablename__ = "hidden_program_templates"
    __table_args__ = (
        UniqueConstraint("user_id", "template_id", name="uq_hidden_program_template"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("program_templates.id"), nullable=False, index=True
    )
    hidden_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=now_msk_naive,
        server_default=func.now(),
    )


class ProgramTemplateDay(Base):
    __tablename__ = "program_template_days"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    program_id: Mapped[int] = mapped_column(ForeignKey("program_templates.id"), index=True)
    day_number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(128))

    program: Mapped[ProgramTemplate] = relationship("ProgramTemplate", back_populates="days")
    exercises: Mapped[list[ProgramTemplateExercise]] = relationship(
        "ProgramTemplateExercise",
        back_populates="day",
        cascade="all, delete-orphan",
        order_by="ProgramTemplateExercise.sort_order",
    )


class ProgramTemplateExercise(Base):
    __tablename__ = "program_template_exercises"
    __table_args__ = (
        UniqueConstraint(
            "day_id",
            "superset_group",
            "superset_order",
            name="uq_program_template_exercises_superset_order",
        ),
        CheckConstraint(
            "(superset_group IS NULL AND superset_order IS NULL) OR "
            "(superset_group IS NOT NULL AND superset_order IS NOT NULL AND "
            "superset_group >= 1 AND superset_order IN (1, 2))",
            name="ck_program_template_exercises_superset",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day_id: Mapped[int] = mapped_column(ForeignKey("program_template_days.id"), index=True)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"), index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=1)
    prescribed_sets: Mapped[int] = mapped_column(Integer)
    prescribed_reps: Mapped[str] = mapped_column(String(32))
    prescribed_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rest_seconds: Mapped[int] = mapped_column(Integer, default=90)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    superset_group: Mapped[int | None] = mapped_column(Integer, nullable=True)
    superset_order: Mapped[int | None] = mapped_column(Integer, nullable=True)

    day: Mapped[ProgramTemplateDay] = relationship("ProgramTemplateDay", back_populates="exercises")
    exercise: Mapped[Exercise] = relationship("Exercise")
    weekly_prescriptions: Mapped[list[ProgramTemplateExerciseWeekPrescription]] = relationship(
        "ProgramTemplateExerciseWeekPrescription",
        back_populates="template_exercise",
        cascade="all, delete-orphan",
        order_by="ProgramTemplateExerciseWeekPrescription.week_number",
    )


class ProgramTemplateExerciseWeekPrescription(Base):
    __tablename__ = "program_template_exercise_weeks"
    __table_args__ = (
        UniqueConstraint(
            "template_exercise_id",
            "week_number",
            name="uq_program_template_exercise_week",
        ),
        CheckConstraint(
            "week_number >= 1 AND week_number <= 24",
            name="ck_program_template_exercise_weeks_number",
        ),
        CheckConstraint(
            "prescribed_sets >= 1 AND prescribed_sets <= 10",
            name="ck_program_template_exercise_weeks_sets",
        ),
        CheckConstraint(
            "prescribed_duration_minutes IS NULL OR prescribed_duration_minutes >= 1",
            name="ck_program_template_exercise_weeks_duration",
        ),
        CheckConstraint(
            "rest_seconds >= 0 AND rest_seconds <= 600",
            name="ck_program_template_exercise_weeks_rest",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_exercise_id: Mapped[int] = mapped_column(
        ForeignKey("program_template_exercises.id", ondelete="CASCADE"), index=True
    )
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"), index=True)
    week_number: Mapped[int] = mapped_column(Integer)
    prescribed_sets: Mapped[int] = mapped_column(Integer)
    prescribed_reps: Mapped[str] = mapped_column(String(32))
    prescribed_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rest_seconds: Mapped[int] = mapped_column(Integer, default=90)

    template_exercise: Mapped[ProgramTemplateExercise] = relationship(
        "ProgramTemplateExercise", back_populates="weekly_prescriptions"
    )
    exercise: Mapped[Exercise] = relationship("Exercise")


class UserProgram(Base):
    __tablename__ = "user_programs"
    __table_args__ = (
        Index(
            "uq_user_programs_one_active_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("is_active"),
            sqlite_where=text("is_active = 1"),
        ),
        CheckConstraint(
            "status IN ('scheduled', 'active', 'completed', 'archived')",
            name="ck_user_programs_status",
        ),
        CheckConstraint("duration_weeks >= 1", name="ck_user_programs_duration_weeks"),
        CheckConstraint(
            "current_revision_number >= 0",
            name="ck_user_programs_current_revision_number",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # Назначение и история должны переживать архивирование исходного шаблона.
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("program_templates.id"), index=True, nullable=True
    )
    assigned_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=now_msk_naive,
        server_default=func.now(),
    )
    start_date: Mapped[date] = mapped_column(
        Date, nullable=False, default=date.today, server_default=func.current_date()
    )
    duration_weeks: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    schedule_weekdays: Mapped[list[int]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default="active"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    current_revision_number: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    template: Mapped[ProgramTemplate | None] = relationship("ProgramTemplate")
    workouts: Mapped[list[UserWorkout]] = relationship(
        "UserWorkout", back_populates="user_program", cascade="all, delete-orphan"
    )
    revisions: Mapped[list[ProgramRevision]] = relationship(
        "ProgramRevision",
        back_populates="user_program",
        cascade="all, delete-orphan",
        order_by="ProgramRevision.revision_number",
    )
    training_blocks: Mapped[list[TrainingBlock]] = relationship(
        "TrainingBlock",
        back_populates="user_program",
        cascade="all, delete-orphan",
        order_by="TrainingBlock.start_date, TrainingBlock.id",
    )


class ProgramRevision(Base):
    __tablename__ = "program_revisions"
    __table_args__ = (
        UniqueConstraint(
            "user_program_id",
            "revision_number",
            name="uq_program_revisions_program_number",
        ),
        CheckConstraint("revision_number >= 1", name="ck_program_revisions_number"),
        CheckConstraint(
            "actor_role IN ('self', 'trainer', 'admin', 'system')",
            name="ck_program_revisions_actor_role",
        ),
        CheckConstraint(
            "change_kind IN "
            "('assigned', 'program_archived', 'plan_updated', 'block_created', "
            "'block_updated', 'block_status_changed')",
            name="ck_program_revisions_change_kind",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_program_id: Mapped[int] = mapped_column(
        ForeignKey("user_programs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    changed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_role: Mapped[str] = mapped_column(String(16), nullable=False)
    change_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    changed_fields: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=now_msk_naive,
        server_default=func.now(),
    )

    user_program: Mapped[UserProgram] = relationship("UserProgram", back_populates="revisions")


class TrainingBlock(Base):
    __tablename__ = "training_blocks"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="ck_training_blocks_dates"),
        CheckConstraint("length(trim(title)) >= 1", name="ck_training_blocks_title"),
        CheckConstraint("length(trim(purpose)) >= 1", name="ck_training_blocks_purpose"),
        CheckConstraint(
            "status IN ('planned', 'active', 'completed', 'archived')",
            name="ck_training_blocks_status",
        ),
        Index(
            "uq_training_blocks_one_active_per_program",
            "user_program_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
        Index(
            "ix_training_blocks_program_dates",
            "user_program_id",
            "start_date",
            "end_date",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_program_id: Mapped[int] = mapped_column(
        ForeignKey("user_programs.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    purpose: Mapped[str] = mapped_column(String(500), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deload: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="planned", server_default="planned"
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=now_msk_naive,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user_program: Mapped[UserProgram] = relationship(
        "UserProgram", back_populates="training_blocks"
    )
    priority_links: Mapped[list[TrainingBlockPriorityMuscle]] = relationship(
        "TrainingBlockPriorityMuscle",
        back_populates="training_block",
        cascade="all, delete-orphan",
        order_by="TrainingBlockPriorityMuscle.position",
    )


class TrainingBlockPriorityMuscle(Base):
    __tablename__ = "training_block_priority_muscles"
    __table_args__ = (
        UniqueConstraint(
            "training_block_id",
            "position",
            name="uq_training_block_priority_position",
        ),
        CheckConstraint("position >= 0", name="ck_training_block_priority_position"),
    )

    training_block_id: Mapped[int] = mapped_column(
        ForeignKey("training_blocks.id", ondelete="CASCADE"), primary_key=True
    )
    muscle_id: Mapped[int] = mapped_column(
        ForeignKey("muscles.id", ondelete="RESTRICT"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    training_block: Mapped[TrainingBlock] = relationship(
        "TrainingBlock", back_populates="priority_links"
    )
    muscle: Mapped[Muscle] = relationship("Muscle")


class UserWorkout(Base):
    __tablename__ = "user_workouts"
    __table_args__ = (
        Index(
            "ix_user_workouts_program_date_status",
            "user_program_id",
            "scheduled_date",
            "status",
        ),
        CheckConstraint(
            "completion_feedback IS NULL OR completion_feedback IN "
            "('easier_than_expected', 'as_expected', 'harder_than_expected')",
            name="ck_user_workouts_completion_feedback",
        ),
        CheckConstraint(
            "completion_note IS NULL OR length(completion_note) <= 500",
            name="ck_user_workouts_completion_note_length",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_program_id: Mapped[int] = mapped_column(ForeignKey("user_programs.id"), index=True)
    scheduled_date: Mapped[date] = mapped_column(Date, index=True)
    scheduled_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    day_number: Mapped[int] = mapped_column(Integer)
    week_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    title: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="planned")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completion_feedback: Mapped[str | None] = mapped_column(String(24), nullable=True)
    completion_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    completion_feedback_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user_program: Mapped[UserProgram] = relationship("UserProgram", back_populates="workouts")
    exercises: Mapped[list[UserWorkoutExercise]] = relationship(
        "UserWorkoutExercise",
        back_populates="workout",
        cascade="all, delete-orphan",
        order_by="UserWorkoutExercise.sort_order",
    )
    adaptations: Mapped[list[WorkoutAdaptation]] = relationship(
        "WorkoutAdaptation",
        back_populates="workout",
        cascade="all, delete-orphan",
        order_by="WorkoutAdaptation.applied_at, WorkoutAdaptation.id",
    )


class WorkoutAdaptation(Base):
    __tablename__ = "workout_adaptations"
    __table_args__ = (
        CheckConstraint(
            "reason IN ('limited_time', 'unavailable_equipment', "
            "'replace_exercise', 'different_environment')",
            name="ck_workout_adaptations_reason",
        ),
        Index(
            "ix_workout_adaptations_workout_applied",
            "workout_id",
            "applied_at",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workout_id: Mapped[int] = mapped_column(
        ForeignKey("user_workouts.id", ondelete="CASCADE"), nullable=False
    )
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    preview_token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    request_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    original_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    applied_diff: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    ruleset_version: Mapped[str] = mapped_column(String(32), nullable=False)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=now_msk_naive,
        server_default=func.now(),
    )

    workout: Mapped[UserWorkout] = relationship("UserWorkout", back_populates="adaptations")


class UserWorkoutExercise(Base):
    __tablename__ = "user_workout_exercises"
    __table_args__ = (
        UniqueConstraint(
            "workout_id",
            "superset_group",
            "superset_order",
            name="uq_user_workout_exercises_superset_order",
        ),
        CheckConstraint(
            "(superset_group IS NULL AND superset_order IS NULL) OR "
            "(superset_group IS NOT NULL AND superset_order IS NOT NULL AND "
            "superset_group >= 1 AND superset_order IN (1, 2))",
            name="ck_user_workout_exercises_superset",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workout_id: Mapped[int] = mapped_column(ForeignKey("user_workouts.id"), index=True)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"), index=True)
    metric_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=1)
    prescribed_sets: Mapped[int] = mapped_column(Integer)
    prescribed_reps: Mapped[str] = mapped_column(String(32))
    prescribed_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rest_seconds: Mapped[int] = mapped_column(Integer, default=90)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    superset_group: Mapped[int | None] = mapped_column(Integer, nullable=True)
    superset_order: Mapped[int | None] = mapped_column(Integer, nullable=True)

    workout: Mapped[UserWorkout] = relationship("UserWorkout", back_populates="exercises")
    exercise: Mapped[Exercise] = relationship("Exercise")
    sets: Mapped[list[UserWorkoutSet]] = relationship(
        "UserWorkoutSet",
        back_populates="workout_exercise",
        cascade="all, delete-orphan",
        order_by="UserWorkoutSet.set_number",
    )


class UserWorkoutSet(Base):
    __tablename__ = "user_workout_sets"
    __table_args__ = (
        UniqueConstraint(
            "workout_exercise_id",
            "set_number",
            name="uq_user_workout_sets_exercise_number",
        ),
        CheckConstraint(
            "rir IS NULL OR rir IN ('0', '1', '2', '3', '4+')",
            name="ck_user_workout_sets_rir",
        ),
        CheckConstraint(
            "set_kind IS NULL OR set_kind IN ('warmup', 'working', 'drop')",
            name="ck_user_workout_sets_kind",
        ),
        CheckConstraint("version >= 1", name="ck_user_workout_sets_version_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workout_exercise_id: Mapped[int] = mapped_column(
        ForeignKey("user_workout_exercises.id"), index=True
    )
    set_number: Mapped[int] = mapped_column(Integer)
    actual_reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    distance_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    average_heart_rate_bpm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    heart_rate_zone: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rir: Mapped[str | None] = mapped_column(String(2), nullable=True)
    set_kind: Mapped[str | None] = mapped_column(String(16), nullable=True, default="working")
    reached_failure: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    workout_exercise: Mapped[UserWorkoutExercise] = relationship(
        "UserWorkoutExercise", back_populates="sets"
    )


class WorkoutSetMutation(Base):
    __tablename__ = "workout_set_mutations"
    __table_args__ = (
        UniqueConstraint(
            "workout_set_id",
            "mutation_id",
            name="uq_workout_set_mutations_set_mutation",
        ),
        CheckConstraint(
            "applied_version >= 1",
            name="ck_workout_set_mutations_version_positive",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workout_set_id: Mapped[int] = mapped_column(
        ForeignKey("user_workout_sets.id", ondelete="CASCADE"), nullable=False
    )
    mutation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    applied_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=now_msk_naive,
        server_default=func.now(),
    )
