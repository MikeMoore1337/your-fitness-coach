"""Add owner-scoped weekly grocery lists derived from nutrition plans."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0125_grocery_lists"
down_revision: str | None = "0124_plan_item_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "constraint_swap"
online_rollout_constraint_table = "nutrition_plan_items"
online_rollout_constraint_name = "ck_nutrition_plan_items_single_source"
online_rollout_lock_timeout_seconds = 3
online_rollout_statement_timeout_seconds = 30
online_rollout_notes = (
    "Allows recipe plan rows to retain a stale source after recipe deletion and adds "
    "owner-scoped weekly grocery snapshots and manual items without changing diary rows."
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute(
            "ALTER TABLE nutrition_plan_items DROP CONSTRAINT IF EXISTS "
            "ck_nutrition_plan_items_single_source, ADD CONSTRAINT "
            "ck_nutrition_plan_items_single_source CHECK ("
            "(item_kind = 'food' AND food_id IS NOT NULL AND recipe_id IS NULL) OR "
            "(item_kind = 'recipe' AND food_id IS NULL AND amount_unit = 'g')) NOT VALID"
        )
        op.execute(
            "ALTER TABLE nutrition_plan_items VALIDATE CONSTRAINT "
            "ck_nutrition_plan_items_single_source"
        )
    op.create_table(
        "grocery_lists",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("generated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "week_start", name="uq_grocery_lists_user_week"),
    )
    op.create_index(
        "ix_grocery_lists_user_week",
        "grocery_lists",
        ["user_id", "week_start"],
    )

    op.create_table(
        "grocery_list_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "grocery_list_id",
            sa.Integer(),
            sa.ForeignKey("grocery_lists.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "food_id",
            sa.Integer(),
            sa.ForeignKey("foods.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_kind", sa.String(length=16), nullable=False),
        sa.Column("aggregation_key", sa.String(length=512), nullable=True),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("brand", sa.String(length=128), nullable=True),
        sa.Column("amount", sa.Numeric(12, 3), nullable=True),
        sa.Column("amount_unit", sa.String(length=16), nullable=True),
        sa.Column("checked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("owned", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "source_kind IN ('generated', 'manual')",
            name="ck_grocery_list_items_source_kind",
        ),
        sa.CheckConstraint(
            "(source_kind = 'generated' AND aggregation_key IS NOT NULL) OR "
            "(source_kind = 'manual' AND aggregation_key IS NULL)",
            name="ck_grocery_list_items_aggregation_key",
        ),
        sa.CheckConstraint(
            "amount IS NULL OR amount > 0",
            name="ck_grocery_list_items_amount_positive",
        ),
        sa.CheckConstraint(
            "(amount IS NULL AND amount_unit IS NULL) OR "
            "(amount IS NOT NULL AND amount_unit IN ('g', 'ml', 'piece', 'serving'))",
            name="ck_grocery_list_items_amount_unit",
        ),
        sa.CheckConstraint(
            "position >= 0",
            name="ck_grocery_list_items_position_nonnegative",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "grocery_list_id",
            "aggregation_key",
            name="uq_grocery_list_items_aggregation_key",
        ),
    )
    op.create_index(
        "ix_grocery_list_items_list_position",
        "grocery_list_items",
        ["grocery_list_id", "position", "id"],
    )

    op.create_table(
        "grocery_list_item_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "grocery_list_item_id",
            sa.Integer(),
            sa.ForeignKey("grocery_list_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "plan_item_id",
            sa.Integer(),
            sa.ForeignKey("nutrition_plan_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "recipe_id",
            sa.Integer(),
            sa.ForeignKey("recipes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("plan_date", sa.Date(), nullable=False),
        sa.Column("meal_type", sa.String(length=16), nullable=False),
        sa.Column("recipe_name", sa.String(length=256), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "grocery_list_item_id",
            "plan_item_id",
            name="uq_grocery_list_item_sources_plan_item",
        ),
    )
    op.create_index(
        "ix_grocery_list_item_sources_item_date",
        "grocery_list_item_sources",
        ["grocery_list_item_id", "plan_date"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_grocery_list_item_sources_item_date",
        table_name="grocery_list_item_sources",
    )
    op.drop_table("grocery_list_item_sources")
    op.drop_index(
        "ix_grocery_list_items_list_position",
        table_name="grocery_list_items",
    )
    op.drop_table("grocery_list_items")
    op.drop_index("ix_grocery_lists_user_week", table_name="grocery_lists")
    op.drop_table("grocery_lists")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute(
            "ALTER TABLE nutrition_plan_items DROP CONSTRAINT IF EXISTS "
            "ck_nutrition_plan_items_single_source, ADD CONSTRAINT "
            "ck_nutrition_plan_items_single_source CHECK ("
            "(item_kind = 'food' AND food_id IS NOT NULL AND recipe_id IS NULL) OR "
            "(item_kind = 'recipe' AND recipe_id IS NOT NULL AND food_id IS NULL AND "
            "amount_unit = 'g')) NOT VALID"
        )
        op.execute(
            "ALTER TABLE nutrition_plan_items VALIDATE CONSTRAINT "
            "ck_nutrition_plan_items_single_source"
        )
