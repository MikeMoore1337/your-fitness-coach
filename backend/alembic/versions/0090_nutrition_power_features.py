"""Add private nutrition meal templates, aliases and atomic diary batches."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0090_nutrition_power_features"
down_revision: str | None = "0089_nutrition_catalog_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Adds owner-scoped nutrition templates and aliases plus a content-free idempotency registry. "
    "All new references are nullable or cascade/set-null; the diary batch foreign key is added "
    "without rewriting existing entries."
)


def upgrade() -> None:
    op.create_table(
        "nutrition_meal_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_nutrition_meal_templates_name_not_blank",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name="nutrition_meal_templates_owner_user_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="nutrition_meal_templates_pkey"),
    )
    op.create_index(
        "ix_nutrition_meal_templates_owner_updated",
        "nutrition_meal_templates",
        ["owner_user_id", "updated_at", "id"],
    )
    op.create_table(
        "nutrition_meal_template_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("item_kind", sa.String(length=16), nullable=False),
        sa.Column("food_id", sa.Integer(), nullable=True),
        sa.Column("recipe_id", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("amount_unit", sa.String(length=16), nullable=False),
        sa.Column("source_name", sa.String(length=256), nullable=False),
        sa.Column("source_brand", sa.String(length=128), nullable=True),
        sa.CheckConstraint(
            "position >= 0",
            name="ck_nutrition_meal_template_items_position",
        ),
        sa.CheckConstraint(
            "item_kind IN ('food', 'recipe')",
            name="ck_nutrition_meal_template_items_kind",
        ),
        sa.CheckConstraint(
            "amount_unit IN ('g', 'ml', 'serving')",
            name="ck_nutrition_meal_template_items_unit",
        ),
        sa.CheckConstraint(
            "amount > 0",
            name="ck_nutrition_meal_template_items_amount_positive",
        ),
        sa.CheckConstraint(
            "(item_kind = 'food' AND food_id IS NOT NULL AND recipe_id IS NULL) OR "
            "(item_kind = 'recipe' AND recipe_id IS NOT NULL AND food_id IS NULL)",
            name="ck_nutrition_meal_template_items_single_source",
        ),
        sa.CheckConstraint(
            "item_kind <> 'recipe' OR amount_unit = 'g'",
            name="ck_nutrition_meal_template_items_recipe_grams",
        ),
        sa.CheckConstraint(
            "length(trim(source_name)) > 0",
            name="ck_nutrition_meal_template_items_source_name_not_blank",
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["nutrition_meal_templates.id"],
            name="nutrition_meal_template_items_template_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["food_id"],
            ["foods.id"],
            name="nutrition_meal_template_items_food_id_fkey",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["recipe_id"],
            ["recipes.id"],
            name="nutrition_meal_template_items_recipe_id_fkey",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="nutrition_meal_template_items_pkey"),
        sa.UniqueConstraint(
            "template_id",
            "position",
            name="uq_nutrition_meal_template_items_position",
        ),
    )
    op.create_index(
        "ix_nutrition_meal_template_items_template_position",
        "nutrition_meal_template_items",
        ["template_id", "position"],
    )
    op.create_table(
        "food_search_aliases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("alias", sa.String(length=128), nullable=False),
        sa.Column("normalized_alias", sa.String(length=128), nullable=False),
        sa.Column("food_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(alias)) > 0",
            name="ck_food_search_aliases_alias_not_blank",
        ),
        sa.CheckConstraint(
            "length(trim(normalized_alias)) > 0",
            name="ck_food_search_aliases_normalized_not_blank",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="food_search_aliases_user_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["food_id"],
            ["foods.id"],
            name="food_search_aliases_food_id_fkey",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="food_search_aliases_pkey"),
        sa.UniqueConstraint(
            "user_id",
            "normalized_alias",
            name="uq_food_search_aliases_user_normalized",
        ),
    )
    op.create_index(
        "ix_food_search_aliases_user_alias",
        "food_search_aliases",
        ["user_id", "normalized_alias"],
    )
    op.create_index("ix_food_search_aliases_food", "food_search_aliases", ["food_id"])
    op.create_table(
        "food_diary_batch_operations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("operation_kind", sa.String(length=24), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("diary_date", sa.Date(), nullable=False),
        sa.Column("meal_type", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "operation_kind IN ('meal_template', 'natural_input')",
            name="ck_food_diary_batch_operations_kind",
        ),
        sa.CheckConstraint(
            "meal_type IN ('breakfast', 'lunch', 'dinner', 'snacks')",
            name="ck_food_diary_batch_operations_meal_type",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="food_diary_batch_operations_user_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["nutrition_meal_templates.id"],
            name="food_diary_batch_operations_template_id_fkey",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="food_diary_batch_operations_pkey"),
        sa.UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_food_diary_batch_operations_user_key",
        ),
    )
    op.create_index(
        "ix_food_diary_batch_operations_user_created",
        "food_diary_batch_operations",
        ["user_id", "created_at", "id"],
    )
    with op.batch_alter_table("food_diary_entries") as batch_op:
        batch_op.add_column(sa.Column("batch_operation_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "food_diary_entries_batch_operation_id_fkey",
            "food_diary_batch_operations",
            ["batch_operation_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        "ix_food_diary_entries_batch_operation",
        "food_diary_entries",
        ["batch_operation_id", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_food_diary_entries_batch_operation", table_name="food_diary_entries")
    with op.batch_alter_table("food_diary_entries") as batch_op:
        batch_op.drop_constraint(
            "food_diary_entries_batch_operation_id_fkey",
            type_="foreignkey",
        )
        batch_op.drop_column("batch_operation_id")
    op.drop_index(
        "ix_food_diary_batch_operations_user_created",
        table_name="food_diary_batch_operations",
    )
    op.drop_table("food_diary_batch_operations")
    op.drop_index("ix_food_search_aliases_food", table_name="food_search_aliases")
    op.drop_index("ix_food_search_aliases_user_alias", table_name="food_search_aliases")
    op.drop_table("food_search_aliases")
    op.drop_index(
        "ix_nutrition_meal_template_items_template_position",
        table_name="nutrition_meal_template_items",
    )
    op.drop_table("nutrition_meal_template_items")
    op.drop_index(
        "ix_nutrition_meal_templates_owner_updated",
        table_name="nutrition_meal_templates",
    )
    op.drop_table("nutrition_meal_templates")
