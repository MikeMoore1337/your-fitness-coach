from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import (
    BIGINT,
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fitminiapp_api.core.timezone import DEFAULT_TIMEZONE, now_msk_naive
from fitminiapp_api.db.base import Base
from fitminiapp_api.models.exercise import Muscle


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_user_id: Mapped[int | None] = mapped_column(
        BIGINT, unique=True, index=True, nullable=True
    )
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    custom_avatar_content_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    custom_avatar_image_bytes: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True, deferred=True
    )
    custom_avatar_byte_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    custom_avatar_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    custom_avatar_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    custom_avatar_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    custom_avatar_created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    custom_avatar_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_coach: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)

    profile = relationship(
        "UserProfile",
        back_populates="user",
        uselist=False,
        foreign_keys="UserProfile.user_id",
    )
    auth_identities = relationship(
        "AuthIdentity", back_populates="user", cascade="all, delete-orphan"
    )


class UserProfile(Base):
    __tablename__ = "user_profiles"
    __table_args__ = (
        CheckConstraint(
            "resting_heart_rate IS NULL OR resting_heart_rate BETWEEN 30 AND 120",
            name="ck_user_profiles_resting_heart_rate_range",
        ),
        CheckConstraint(
            "body_priority_mode IS NULL OR body_priority_mode IN ('balanced', 'muscle_groups')",
            name="ck_user_profiles_body_priority_mode",
        ),
        CheckConstraint(
            "preferred_workout_duration_min IS NULL OR "
            "preferred_workout_duration_min BETWEEN 10 AND 240",
            name="ck_user_profiles_preferred_duration_min",
        ),
        CheckConstraint(
            "preferred_workout_duration_max IS NULL OR "
            "preferred_workout_duration_max BETWEEN 10 AND 240",
            name="ck_user_profiles_preferred_duration_max",
        ),
        CheckConstraint(
            "preferred_workout_duration_min IS NULL OR "
            "preferred_workout_duration_max IS NULL OR "
            "preferred_workout_duration_min <= preferred_workout_duration_max",
            name="ck_user_profiles_preferred_duration_order",
        ),
        CheckConstraint(
            "training_preferences_note IS NULL OR length(training_preferences_note) <= 500",
            name="ck_user_profiles_training_preferences_note_length",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, unique=True)
    full_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    sex: Mapped[str | None] = mapped_column(String(16), nullable=True)
    goal: Mapped[str | None] = mapped_column(String(32), nullable=True)
    level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    height_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    workouts_per_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cardio_trainings_per_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resting_heart_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    body_priority_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    preferred_workout_duration_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preferred_workout_duration_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preferred_training_weekdays: Mapped[list[int]] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("'[]'")
    )
    preferred_training_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    training_location_profiles: Mapped[list[dict]] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("'[]'")
    )
    preferred_exercise_ids: Mapped[list[int]] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("'[]'")
    )
    avoided_exercises: Mapped[list[dict]] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("'[]'")
    )
    training_preferences_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    training_preferences_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    training_preferences_updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=DEFAULT_TIMEZONE,
        server_default=DEFAULT_TIMEZONE,
    )

    user = relationship("User", back_populates="profile", foreign_keys=[user_id])
    body_priority_links: Mapped[list[UserProfilePriorityMuscle]] = relationship(
        "UserProfilePriorityMuscle",
        back_populates="profile",
        cascade="all, delete-orphan",
        order_by="UserProfilePriorityMuscle.position",
        lazy="selectin",
    )


class UserProfilePriorityMuscle(Base):
    __tablename__ = "user_profile_priority_muscles"
    __table_args__ = (
        UniqueConstraint(
            "profile_id",
            "position",
            name="uq_user_profile_priority_muscle_position",
        ),
        CheckConstraint(
            "position >= 0",
            name="ck_user_profile_priority_muscle_position",
        ),
    )

    profile_id: Mapped[int] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"), primary_key=True
    )
    muscle_id: Mapped[int] = mapped_column(
        ForeignKey("muscles.id", ondelete="RESTRICT"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    profile: Mapped[UserProfile] = relationship("UserProfile", back_populates="body_priority_links")
    muscle: Mapped[Muscle] = relationship("Muscle", lazy="joined")


class BodyMeasurement(Base):
    __tablename__ = "body_measurements"
    __table_args__ = (
        UniqueConstraint("user_id", "measured_on", name="uq_body_measurement_user_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    measured_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    chest_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    waist_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    hips_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    biceps_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    thigh_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)
    custom_values: Mapped[list[BodyMeasurementCustomValue]] = relationship(
        "BodyMeasurementCustomValue",
        back_populates="measurement",
        cascade="all, delete-orphan",
        order_by="BodyMeasurementCustomValue.definition_id",
        lazy="selectin",
    )


class BodyMeasurementDefinition(Base):
    __tablename__ = "body_measurement_definitions"
    __table_args__ = (
        CheckConstraint(
            "length(trim(label)) BETWEEN 1 AND 64",
            name="ck_body_measurement_definitions_label_length",
        ),
        CheckConstraint(
            "length(trim(normalized_label)) BETWEEN 1 AND 64",
            name="ck_body_measurement_definitions_normalized_label_length",
        ),
        CheckConstraint("unit = 'cm'", name="ck_body_measurement_definitions_unit"),
        UniqueConstraint(
            "user_id",
            "normalized_label",
            name="uq_body_measurement_definition_user_label",
        ),
        Index(
            "ix_body_measurement_definitions_user_archived",
            "user_id",
            "archived_at",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_label: Mapped[str] = mapped_column(String(64), nullable=False)
    unit: Mapped[str] = mapped_column(String(8), nullable=False, default="cm", server_default="cm")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)

    values: Mapped[list[BodyMeasurementCustomValue]] = relationship(
        "BodyMeasurementCustomValue",
        back_populates="definition",
        order_by="BodyMeasurementCustomValue.measurement_id",
        lazy="selectin",
    )


class BodyMeasurementCustomValue(Base):
    __tablename__ = "body_measurement_custom_values"
    __table_args__ = (
        CheckConstraint(
            "value > 0 AND value <= 300",
            name="ck_body_measurement_custom_values_range",
        ),
        UniqueConstraint(
            "measurement_id",
            "definition_id",
            name="uq_body_measurement_custom_value_measurement_definition",
        ),
        Index(
            "ix_body_measurement_custom_values_definition_measurement",
            "definition_id",
            "measurement_id",
        ),
        Index(
            "ix_body_measurement_custom_values_measurement",
            "measurement_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    measurement_id: Mapped[int] = mapped_column(
        ForeignKey("body_measurements.id", ondelete="CASCADE"), nullable=False
    )
    definition_id: Mapped[int] = mapped_column(
        ForeignKey("body_measurement_definitions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    value: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)

    measurement: Mapped[BodyMeasurement] = relationship(
        "BodyMeasurement", back_populates="custom_values"
    )
    definition: Mapped[BodyMeasurementDefinition] = relationship(
        "BodyMeasurementDefinition", back_populates="values", lazy="joined"
    )


class CoachClient(Base):
    __tablename__ = "coach_clients"
    __table_args__ = (
        Index(
            "uq_coach_clients_one_active_per_client",
            "client_user_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
        Index(
            "ix_coach_clients_coach_status_client",
            "coach_user_id",
            "status",
            "client_user_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    coach_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    client_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    private_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default="active"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, default=now_msk_naive
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)


class CoachClientInvite(Base):
    __tablename__ = "coach_client_invites"
    __table_args__ = (
        Index(
            "uq_coach_client_invites_pending_pair",
            "coach_user_id",
            "client_user_id",
            unique=True,
            postgresql_where=text("status = 'pending' AND client_user_id IS NOT NULL"),
            sqlite_where=text("status = 'pending' AND client_user_id IS NOT NULL"),
        ),
        CheckConstraint(
            "status <> 'pending' OR token_hash IS NOT NULL",
            name="ck_coach_client_invites_pending_token",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    coach_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    client_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    telegram_user_id: Mapped[int | None] = mapped_column(BIGINT, nullable=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    token_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="username_search", server_default="username_search"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    declined_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CoachRoleApplication(Base):
    __tablename__ = "coach_role_applications"
    __table_args__ = (
        Index(
            "uq_coach_role_applications_pending_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
            sqlite_where=text("status = 'pending'"),
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'cancelled')",
            name="ck_coach_role_applications_status",
        ),
        CheckConstraint(
            "source IN ('web', 'telegram')",
            name="ck_coach_role_applications_source",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    source: Mapped[str] = mapped_column(
        String(16), nullable=False, default="web", server_default="web"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
