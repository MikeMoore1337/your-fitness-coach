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
    "Adds nullable basis, snapshot, and canonical weight fields to diary entries without rewriting populated rows, "
    "changing existing nullability, or changing existing constraints during the expand rollout."
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
    op.add_column(
        "food_diary_entries",
        sa.Column("nutrition_weight_g", sa.Numeric(precision=10, scale=3), nullable=True),
    )
    op.add_column(
        "food_diary_entries",
        sa.Column(
            "nutrition_energy_kcal_per_100g", sa.Numeric(precision=10, scale=2), nullable=True
        ),
    )
    op.add_column(
        "food_diary_entries",
        sa.Column("nutrition_protein_g_per_100g", sa.Numeric(precision=8, scale=3), nullable=True),
    )
    op.add_column(
        "food_diary_entries",
        sa.Column("nutrition_fat_g_per_100g", sa.Numeric(precision=8, scale=3), nullable=True),
    )
    op.add_column(
        "food_diary_entries",
        sa.Column("nutrition_carbs_g_per_100g", sa.Numeric(precision=8, scale=3), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("food_diary_entries", "nutrition_amount")
    op.drop_column("food_diary_entries", "nutrition_snapshot")
    op.drop_column("food_diary_entries", "nutrition_weight_g")
    op.drop_column("food_diary_entries", "nutrition_carbs_g_per_100g")
    op.drop_column("food_diary_entries", "nutrition_fat_g_per_100g")
    op.drop_column("food_diary_entries", "nutrition_protein_g_per_100g")
    op.drop_column("food_diary_entries", "nutrition_energy_kcal_per_100g")
    op.drop_column("food_diary_entries", "nutrition_basis_unit")
    op.drop_column("food_diary_entries", "nutrition_basis_amount")
    op.drop_column("food_diary_entries", "nutrition_basis_kind")
