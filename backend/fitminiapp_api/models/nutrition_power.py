from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
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


class NutritionMealTemplate(Base):
    __tablename__ = "nutrition_meal_templates"
    __table_args__ = (
        CheckConstraint(
            "length(trim(name)) > 0", name="ck_nutrition_meal_templates_name_not_blank"
        ),
        Index(
            "ix_nutrition_meal_templates_owner_updated",
            "owner_user_id",
            "updated_at",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
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

    items: Mapped[list[NutritionMealTemplateItem]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="NutritionMealTemplateItem.position",
    )


class NutritionMealTemplateItem(Base):
    __tablename__ = "nutrition_meal_template_items"
    __table_args__ = (
        CheckConstraint("position >= 0", name="ck_nutrition_meal_template_items_position"),
        CheckConstraint(
            "item_kind IN ('food', 'recipe')",
            name="ck_nutrition_meal_template_items_kind",
        ),
        CheckConstraint(
            "amount_unit IN ('g', 'ml', 'serving')",
            name="ck_nutrition_meal_template_items_unit",
        ),
        CheckConstraint("amount > 0", name="ck_nutrition_meal_template_items_amount_positive"),
        CheckConstraint(
            "(item_kind = 'food' AND food_id IS NOT NULL AND recipe_id IS NULL) OR "
            "(item_kind = 'recipe' AND recipe_id IS NOT NULL AND food_id IS NULL)",
            name="ck_nutrition_meal_template_items_single_source",
        ),
        CheckConstraint(
            "item_kind <> 'recipe' OR amount_unit = 'g'",
            name="ck_nutrition_meal_template_items_recipe_grams",
        ),
        CheckConstraint(
            "length(trim(source_name)) > 0",
            name="ck_nutrition_meal_template_items_source_name_not_blank",
        ),
        UniqueConstraint(
            "template_id",
            "position",
            name="uq_nutrition_meal_template_items_position",
        ),
        Index(
            "ix_nutrition_meal_template_items_template_position",
            "template_id",
            "position",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("nutrition_meal_templates.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    item_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    food_id: Mapped[int | None] = mapped_column(
        ForeignKey("foods.id", ondelete="SET NULL"), nullable=True
    )
    recipe_id: Mapped[int | None] = mapped_column(
        ForeignKey("recipes.id", ondelete="SET NULL"), nullable=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    amount_unit: Mapped[str] = mapped_column(String(16), nullable=False)
    source_name: Mapped[str] = mapped_column(String(256), nullable=False)
    source_brand: Mapped[str | None] = mapped_column(String(128), nullable=True)

    template: Mapped[NutritionMealTemplate] = relationship(back_populates="items")


class FoodSearchAlias(Base):
    __tablename__ = "food_search_aliases"
    __table_args__ = (
        CheckConstraint("length(trim(alias)) > 0", name="ck_food_search_aliases_alias_not_blank"),
        CheckConstraint(
            "length(trim(normalized_alias)) > 0",
            name="ck_food_search_aliases_normalized_not_blank",
        ),
        UniqueConstraint(
            "user_id",
            "normalized_alias",
            name="uq_food_search_aliases_user_normalized",
        ),
        Index("ix_food_search_aliases_user_alias", "user_id", "normalized_alias"),
        Index("ix_food_search_aliases_food", "food_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    alias: Mapped[str] = mapped_column(String(128), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(128), nullable=False)
    food_id: Mapped[int | None] = mapped_column(
        ForeignKey("foods.id", ondelete="SET NULL"), nullable=True
    )
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
