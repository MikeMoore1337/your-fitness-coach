from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.db.base import Base


class NutritionPlan(Base):
    __tablename__ = "nutrition_plans"
    __table_args__ = (
        CheckConstraint("revision >= 0", name="ck_nutrition_plans_revision_nonnegative"),
        UniqueConstraint("user_id", "plan_date", name="uq_nutrition_plans_user_date"),
        Index("ix_nutrition_plans_user_date", "user_id", "plan_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    plan_date: Mapped[date] = mapped_column(Date, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=now_msk_naive,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=now_msk_naive,
        onupdate=now_msk_naive,
    )

    items: Mapped[list[NutritionPlanItem]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="(NutritionPlanItem.meal_type, NutritionPlanItem.position)",
    )


class NutritionPlanItem(Base):
    __tablename__ = "nutrition_plan_items"
    __table_args__ = (
        CheckConstraint(
            "meal_type IN ('breakfast', 'lunch', 'dinner', 'snacks')",
            name="ck_nutrition_plan_items_meal_type",
        ),
        CheckConstraint(
            "item_kind IN ('food', 'recipe')",
            name="ck_nutrition_plan_items_kind",
        ),
        CheckConstraint(
            "amount_unit IN ('g', 'ml', 'serving')",
            name="ck_nutrition_plan_items_unit",
        ),
        CheckConstraint("amount > 0", name="ck_nutrition_plan_items_amount_positive"),
        CheckConstraint(
            "(item_kind = 'food' AND food_id IS NOT NULL AND recipe_id IS NULL) OR "
            "(item_kind = 'recipe' AND recipe_id IS NOT NULL AND food_id IS NULL AND amount_unit = 'g')",
            name="ck_nutrition_plan_items_single_source",
        ),
        CheckConstraint("position >= 0", name="ck_nutrition_plan_items_position_nonnegative"),
        CheckConstraint(
            "length(trim(source_name)) > 0",
            name="ck_nutrition_plan_items_source_name_not_blank",
        ),
        CheckConstraint(
            "status IN ('planned', 'consumed', 'skipped')",
            name="ck_nutrition_plan_items_status",
        ),
        CheckConstraint(
            "diary_entry_id IS NULL OR status = 'consumed'",
            name="ck_nutrition_plan_items_diary_link",
        ),
        UniqueConstraint(
            "plan_id",
            "meal_type",
            "position",
            name="uq_nutrition_plan_items_position",
        ),
        Index(
            "ix_nutrition_plan_items_plan_meal_position",
            "plan_id",
            "meal_type",
            "position",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("nutrition_plans.id", ondelete="CASCADE"), nullable=False
    )
    source_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("nutrition_meal_templates.id", ondelete="SET NULL"), nullable=True
    )
    food_id: Mapped[int | None] = mapped_column(
        ForeignKey("foods.id", ondelete="SET NULL"), nullable=True
    )
    recipe_id: Mapped[int | None] = mapped_column(
        ForeignKey("recipes.id", ondelete="SET NULL"), nullable=True
    )
    item_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    meal_type: Mapped[str] = mapped_column(String(16), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    amount_unit: Mapped[str] = mapped_column(String(16), nullable=False)
    source_name: Mapped[str] = mapped_column(String(256), nullable=False)
    source_brand: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="planned", server_default="planned"
    )
    diary_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("food_diary_entries.id", ondelete="SET NULL"), nullable=True
    )
    action_idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    action_request_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=now_msk_naive,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=now_msk_naive,
        onupdate=now_msk_naive,
    )

    plan: Mapped[NutritionPlan] = relationship(back_populates="items")


class NutritionPlanOperation(Base):
    __tablename__ = "nutrition_plan_operations"
    __table_args__ = (
        CheckConstraint(
            "operation_kind IN ('add', 'copy', 'fill')",
            name="ck_nutrition_plan_operations_kind",
        ),
        UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_nutrition_plan_operations_user_key",
        ),
        Index(
            "ix_nutrition_plan_operations_user_created",
            "user_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    operation_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=now_msk_naive,
    )
