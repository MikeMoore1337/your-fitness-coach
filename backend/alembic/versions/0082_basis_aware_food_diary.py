"""Make food diary snapshots basis-aware while preserving legacy 100 g columns.

Revision ID: 0082_basis_aware_food_diary
Revises: 0081_nutrition_label_catalog
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0082_basis_aware_food_diary"
down_revision: str | None = "0081_nutrition_label_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Adds basis/snapshot fields to diary entries and permits ml amounts; existing rows are "
    "backfilled as per_100_g with their historical 100 g projection."
)


def upgrade() -> None:
    op.add_column(
        "food_diary_entries",
        sa.Column("nutrition_basis_kind", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "food_diary_entries",
        sa.Column("nutrition_basis_amount", sa.Numeric(precision=10, scale=3), nullable=True),
    )
    op.add_column(
        "food_diary_entries",
        sa.Column("nutrition_basis_unit", sa.String(length=16), nullable=True),
    )
    op.add_column("food_diary_entries", sa.Column("nutrition_snapshot", sa.JSON(), nullable=True))
    op.add_column("food_diary_entries", sa.Column("nutrition_amount", sa.JSON(), nullable=True))
    op.execute(
        sa.text(
            "UPDATE food_diary_entries SET nutrition_basis_kind = 'per_100_g', "
            "nutrition_basis_amount = 100, nutrition_basis_unit = 'g' "
            "WHERE nutrition_basis_kind IS NULL"
        )
    )
    with op.batch_alter_table("food_diary_entries") as batch_op:
        batch_op.alter_column(
            "weight_g",
            existing_type=sa.Numeric(precision=10, scale=3),
            nullable=True,
        )
        for column in (
            "energy_kcal_per_100g",
            "protein_g_per_100g",
            "fat_g_per_100g",
            "carbs_g_per_100g",
        ):
            batch_op.alter_column(column, nullable=True)
        batch_op.drop_constraint("ck_food_diary_entries_serving_complete", type_="check")
        batch_op.drop_constraint("ck_food_diary_entries_amount_unit", type_="check")
        batch_op.drop_constraint("ck_food_diary_entries_weight_positive", type_="check")
        batch_op.drop_constraint("ck_food_diary_entries_gram_amount_weight", type_="check")
        batch_op.create_check_constraint(
            "ck_food_diary_entries_amount_unit", "amount_unit IN ('g', 'ml', 'serving')"
        )
        batch_op.create_check_constraint(
            "ck_food_diary_entries_weight_positive", "weight_g IS NULL OR weight_g > 0"
        )
        batch_op.create_check_constraint(
            "ck_food_diary_entries_gram_amount_weight",
            "amount_unit <> 'g' OR (weight_g IS NOT NULL AND amount = weight_g)",
        )
        batch_op.create_check_constraint(
            "ck_food_diary_entries_serving_complete",
            "(serving_amount IS NULL AND serving_unit IS NULL AND serving_weight_g IS NULL) OR "
            "(serving_amount > 0 AND serving_unit IN ('g', 'ml', 'piece', 'serving') AND "
            "((serving_unit = 'g' AND serving_weight_g > 0) OR "
            "(serving_unit IN ('ml', 'piece', 'serving') AND "
            "(serving_weight_g IS NULL OR serving_weight_g > 0))))",
        )


def downgrade() -> None:
    with op.batch_alter_table("food_diary_entries") as batch_op:
        batch_op.drop_constraint("ck_food_diary_entries_serving_complete", type_="check")
        batch_op.drop_constraint("ck_food_diary_entries_gram_amount_weight", type_="check")
        batch_op.drop_constraint("ck_food_diary_entries_weight_positive", type_="check")
        batch_op.drop_constraint("ck_food_diary_entries_amount_unit", type_="check")
        batch_op.create_check_constraint(
            "ck_food_diary_entries_amount_unit", "amount_unit IN ('g', 'serving')"
        )
        batch_op.create_check_constraint("ck_food_diary_entries_weight_positive", "weight_g > 0")
        batch_op.create_check_constraint(
            "ck_food_diary_entries_gram_amount_weight", "amount_unit <> 'g' OR amount = weight_g"
        )
        batch_op.create_check_constraint(
            "ck_food_diary_entries_serving_complete",
            "serving_amount IS NULL AND serving_unit IS NULL AND serving_weight_g IS NULL OR "
            "serving_amount > 0 AND serving_unit IN ('g', 'ml', 'piece', 'serving') AND "
            "serving_weight_g > 0",
        )
        batch_op.drop_column("nutrition_amount")
        batch_op.drop_column("nutrition_snapshot")
        batch_op.drop_column("nutrition_basis_unit")
        batch_op.drop_column("nutrition_basis_amount")
        batch_op.drop_column("nutrition_basis_kind")
        batch_op.alter_column("weight_g", nullable=False)
        for column in (
            "energy_kcal_per_100g",
            "protein_g_per_100g",
            "fat_g_per_100g",
            "carbs_g_per_100g",
        ):
            batch_op.alter_column(column, nullable=False)
