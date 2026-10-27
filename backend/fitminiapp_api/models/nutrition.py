from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    event,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.db.base import Base


class NutritionTarget(Base):
    __tablename__ = "nutrition_targets"
    __table_args__ = (
        CheckConstraint(
            "source IN ('calculated', 'manual', 'trainer', 'adaptive')",
            name="ck_nutrition_targets_source",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_nutrition_targets_effective_period",
        ),
        CheckConstraint("calories > 0", name="ck_nutrition_targets_calories_positive"),
        CheckConstraint("protein_g >= 0", name="ck_nutrition_targets_protein_nonnegative"),
        CheckConstraint("fat_g >= 0", name="ck_nutrition_targets_fat_nonnegative"),
        CheckConstraint("carbs_g >= 0", name="ck_nutrition_targets_carbs_nonnegative"),
        Index(
            "uq_nutrition_targets_active_user",
            "user_id",
            unique=True,
            postgresql_where=text("effective_to IS NULL"),
            sqlite_where=text("effective_to IS NULL"),
        ),
        Index(
            "ix_nutrition_targets_user_effective",
            "user_id",
            "effective_from",
            "effective_to",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    assigned_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    sex: Mapped[str | None] = mapped_column(String(16), nullable=True)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    height_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    age: Mapped[float | None] = mapped_column(Float, nullable=True)
    daily_activity_level: Mapped[str | None] = mapped_column(
        String(16), nullable=True, default="sedentary"
    )
    daily_routine: Mapped[str | None] = mapped_column(
        String(24), nullable=True, default="mostly_sitting"
    )
    steps_range: Mapped[str | None] = mapped_column(String(32), nullable=True, default="unknown")
    strength_trainings_per_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    strength_training_duration_minutes: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=60
    )
    strength_training_type: Mapped[str | None] = mapped_column(
        String(16), nullable=True, default="regular"
    )
    strength_rest: Mapped[str | None] = mapped_column(String(16), nullable=True)
    cardio_trainings_per_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cardio_training_duration_minutes: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=30
    )
    cardio_intensity: Mapped[str | None] = mapped_column(
        String(16), nullable=True, default="moderate"
    )
    cardio_trainings: Mapped[list[dict[str, object]] | None] = mapped_column(
        JSON, nullable=True, default=list
    )
    goal: Mapped[str | None] = mapped_column(String(32), nullable=True)

    bmr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tdee: Mapped[int | None] = mapped_column(Integer, nullable=True)
    calories: Mapped[int] = mapped_column(Integer, nullable=False)
    protein_g: Mapped[int] = mapped_column(Integer, nullable=False)
    fat_g: Mapped[int] = mapped_column(Integer, nullable=False)
    carbs_g: Mapped[int] = mapped_column(Integer, nullable=False)

    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="calculated")
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    superseded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("nutrition_targets.id", ondelete="SET NULL"), nullable=True
    )

    saved_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=now_msk_naive,
    )

    @property
    def created_by_user_id(self) -> int | None:
        """Canonical author field backed by the legacy assigned-by column."""
        return self.assigned_by_user_id

    @property
    def created_at(self) -> datetime:
        """Canonical creation timestamp backed by the legacy saved-at column."""
        return self.saved_at


@event.listens_for(NutritionTarget, "before_insert")
def _default_nutrition_target_effective_from(_mapper, _connection, target) -> None:
    if target.effective_from is None:
        created_at = target.saved_at or now_msk_naive()
        target.effective_from = created_at.date()


class EnergyCalibration(Base):
    __tablename__ = "energy_calibrations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('limited', 'no_change', 'pending', 'accepted', 'rejected', 'superseded')",
            name="ck_energy_calibrations_status",
        ),
        CheckConstraint(
            "sufficiency_status IN ('limited', 'sufficient')",
            name="ck_energy_calibrations_sufficiency_status",
        ),
        CheckConstraint(
            "period_end >= period_start",
            name="ck_energy_calibrations_period",
        ),
        CheckConstraint(
            "estimate_low_kcal <= estimated_expenditure_kcal AND "
            "estimated_expenditure_kcal <= estimate_high_kcal",
            name="ck_energy_calibrations_estimate_range",
        ),
        Index(
            "ix_energy_calibrations_user_created",
            "user_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    ruleset_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    sufficiency_status: Mapped[str] = mapped_column(String(16), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    goal: Mapped[str] = mapped_column(String(32), nullable=False)
    logged_day_count: Mapped[int] = mapped_column(Integer, nullable=False)
    eligible_day_count: Mapped[int] = mapped_column(Integer, nullable=False)
    weight_point_count: Mapped[int] = mapped_column(Integer, nullable=False)
    weight_span_days: Mapped[int] = mapped_column(Integer, nullable=False)
    average_intake_kcal: Mapped[int] = mapped_column(Integer, nullable=False)
    smoothed_start_weight_kg: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    smoothed_end_weight_kg: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    estimated_expenditure_kcal: Mapped[int] = mapped_column(Integer, nullable=False)
    estimate_low_kcal: Mapped[int] = mapped_column(Integer, nullable=False)
    estimate_high_kcal: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_target_calories: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_target_saved_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    proposed_target_calories: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sufficiency_counters: Mapped[dict[str, int | float]] = mapped_column(JSON, nullable=False)
    sufficiency_reason_keys: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    rationale_keys: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=now_msk_naive,
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
