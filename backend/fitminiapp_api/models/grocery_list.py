from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
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


class GroceryList(Base):
    __tablename__ = "grocery_lists"
    __table_args__ = (
        UniqueConstraint("user_id", "week_start", name="uq_grocery_lists_user_week"),
        Index("ix_grocery_lists_user_week", "user_id", "week_start"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
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

    items: Mapped[list[GroceryListItem]] = relationship(
        back_populates="grocery_list",
        cascade="all, delete-orphan",
        order_by="(GroceryListItem.position, GroceryListItem.id)",
    )


class GroceryListItem(Base):
    __tablename__ = "grocery_list_items"
    __table_args__ = (
        CheckConstraint(
            "source_kind IN ('generated', 'manual')",
            name="ck_grocery_list_items_source_kind",
        ),
        CheckConstraint(
            "(source_kind = 'generated' AND aggregation_key IS NOT NULL) OR "
            "(source_kind = 'manual' AND aggregation_key IS NULL)",
            name="ck_grocery_list_items_aggregation_key",
        ),
        CheckConstraint(
            "amount IS NULL OR amount > 0", name="ck_grocery_list_items_amount_positive"
        ),
        CheckConstraint(
            "(amount IS NULL AND amount_unit IS NULL) OR "
            "(amount IS NOT NULL AND amount_unit IN ('g', 'ml', 'piece', 'serving'))",
            name="ck_grocery_list_items_amount_unit",
        ),
        CheckConstraint("position >= 0", name="ck_grocery_list_items_position_nonnegative"),
        UniqueConstraint(
            "grocery_list_id",
            "aggregation_key",
            name="uq_grocery_list_items_aggregation_key",
        ),
        Index("ix_grocery_list_items_list_position", "grocery_list_id", "position", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    grocery_list_id: Mapped[int] = mapped_column(
        ForeignKey("grocery_lists.id", ondelete="CASCADE"),
        nullable=False,
    )
    food_id: Mapped[int | None] = mapped_column(
        ForeignKey("foods.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    aggregation_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(128), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    amount_unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    checked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    owned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
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

    grocery_list: Mapped[GroceryList] = relationship(back_populates="items")
    sources: Mapped[list[GroceryListItemSource]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="(GroceryListItemSource.plan_date, GroceryListItemSource.meal_type, "
        "GroceryListItemSource.plan_item_id)",
    )


class GroceryListItemSource(Base):
    __tablename__ = "grocery_list_item_sources"
    __table_args__ = (
        UniqueConstraint(
            "grocery_list_item_id",
            "plan_item_id",
            name="uq_grocery_list_item_sources_plan_item",
        ),
        Index(
            "ix_grocery_list_item_sources_item_date",
            "grocery_list_item_id",
            "plan_date",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    grocery_list_item_id: Mapped[int] = mapped_column(
        ForeignKey("grocery_list_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    plan_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("nutrition_plan_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    recipe_id: Mapped[int | None] = mapped_column(
        ForeignKey("recipes.id", ondelete="SET NULL"),
        nullable=True,
    )
    plan_date: Mapped[date] = mapped_column(Date, nullable=False)
    meal_type: Mapped[str] = mapped_column(String(16), nullable=False)
    recipe_name: Mapped[str] = mapped_column(String(256), nullable=False)

    item: Mapped[GroceryListItem] = relationship(back_populates="sources")
