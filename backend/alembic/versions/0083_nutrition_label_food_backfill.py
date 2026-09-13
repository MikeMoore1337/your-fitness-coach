"""Backfill legacy food rows with their historical 100 g basis."""

from collections.abc import Sequence

from alembic import op

revision: str = "0083_nutrition_food_backfill"
down_revision: str | None = "0082_basis_aware_food_diary"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "backfill"
online_rollout_notes = (
    "Idempotent legacy foods backfill fills only newly added nullable columns and preserves the "
    "historical 100 g projection; the deployment gate bounds it to a single UPDATE with a WHERE."
)
online_rollout_batch_size = 1000
online_rollout_idempotent = True


def upgrade() -> None:
    op.execute(
        """UPDATE foods
        SET nutrition_basis_kind = 'per_100_g',
            nutrition_basis_amount = 100,
            nutrition_basis_unit = 'g',
            canonical_complete = TRUE,
            catalog_quality = CASE WHEN food_type = 'user' THEN 'private' ELSE 'verified' END
        WHERE nutrition_basis_kind IS NULL
           OR nutrition_basis_amount IS NULL
           OR nutrition_basis_unit IS NULL
           OR canonical_complete IS NULL
           OR catalog_quality IS NULL"""
    )


def downgrade() -> None:
    pass
