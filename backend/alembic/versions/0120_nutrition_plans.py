"""Add private meal-planning state separate from consumed diary entries."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0120_nutrition_plans"
down_revision: str | None = "0119_exercise_setup_memory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Adds owner-scoped planned meal rows and idempotency metadata without changing "
    "food diary entries or existing nutrition tables."
)


def upgrade() -> None:
    op.create_table(
        "nutrition_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("plan_date", sa.Date(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("revision >= 0", name="ck_nutrition_plans_revision_nonnegative"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "plan_date", name="uq_nutrition_plans_user_date"),
    )
    op.create_index(
        "ix_nutrition_plans_user_date",
        "nutrition_plans",
        ["user_id", "plan_date"],
    )

    op.create_table(
        "nutrition_plan_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "plan_id",
            sa.Integer(),
            sa.ForeignKey("nutrition_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_template_id",
            sa.Integer(),
            sa.ForeignKey("nutrition_meal_templates.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "food_id",
            sa.Integer(),
            sa.ForeignKey("foods.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "recipe_id",
            sa.Integer(),
            sa.ForeignKey("recipes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("item_kind", sa.String(length=16), nullable=False),
        sa.Column("meal_type", sa.String(length=16), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(10, 3), nullable=False),
        sa.Column("amount_unit", sa.String(length=16), nullable=False),
        sa.Column("source_name", sa.String(length=256), nullable=False),
        sa.Column("source_brand", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "meal_type IN ('breakfast', 'lunch', 'dinner', 'snacks')",
            name="ck_nutrition_plan_items_meal_type",
        ),
        sa.CheckConstraint(
            "item_kind IN ('food', 'recipe')",
            name="ck_nutrition_plan_items_kind",
        ),
        sa.CheckConstraint(
            "amount_unit IN ('g', 'ml', 'serving')",
            name="ck_nutrition_plan_items_unit",
        ),
        sa.CheckConstraint("amount > 0", name="ck_nutrition_plan_items_amount_positive"),
        sa.CheckConstraint(
            "(item_kind = 'food' AND food_id IS NOT NULL AND recipe_id IS NULL) OR "
            "(item_kind = 'recipe' AND recipe_id IS NOT NULL AND food_id IS NULL AND amount_unit = 'g')",
            name="ck_nutrition_plan_items_single_source",
        ),
        sa.CheckConstraint("position >= 0", name="ck_nutrition_plan_items_position_nonnegative"),
        sa.CheckConstraint(
            "length(trim(source_name)) > 0",
            name="ck_nutrition_plan_items_source_name_not_blank",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "plan_id",
            "meal_type",
            "position",
            name="uq_nutrition_plan_items_position",
        ),
    )
    op.create_index(
        "ix_nutrition_plan_items_plan_meal_position",
        "nutrition_plan_items",
        ["plan_id", "meal_type", "position"],
    )

    op.create_table(
        "nutrition_plan_operations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("operation_kind", sa.String(length=16), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "operation_kind IN ('add', 'copy')",
            name="ck_nutrition_plan_operations_kind",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_nutrition_plan_operations_user_key",
        ),
    )
    op.create_index(
        "ix_nutrition_plan_operations_user_created",
        "nutrition_plan_operations",
        ["user_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_nutrition_plan_operations_user_created",
        table_name="nutrition_plan_operations",
    )
    op.drop_table("nutrition_plan_operations")
    op.drop_index(
        "ix_nutrition_plan_items_plan_meal_position",
        table_name="nutrition_plan_items",
    )
    op.drop_table("nutrition_plan_items")
    op.drop_index("ix_nutrition_plans_user_date", table_name="nutrition_plans")
    op.drop_table("nutrition_plans")
