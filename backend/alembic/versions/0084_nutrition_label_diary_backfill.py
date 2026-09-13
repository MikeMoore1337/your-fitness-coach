"""Backfill legacy diary rows with their historical 100 g basis."""

from collections.abc import Sequence

from alembic import op

revision: str = "0084_nutrition_label_diary_backfill"
down_revision: str | None = "0083_nutrition_label_food_backfill"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "backfill"
online_rollout_notes = (
    "Idempotent legacy diary backfill fills only newly added nullable basis columns and keeps "
    "historical nutrient snapshots unchanged; the deployment gate bounds it to one UPDATE."
)
online_rollout_batch_size = 1000
online_rollout_idempotent = True


def upgrade() -> None:
    op.execute(
        """UPDATE food_diary_entries
        SET nutrition_basis_kind = 'per_100_g',
            nutrition_basis_amount = 100,
            nutrition_basis_unit = 'g'
        WHERE nutrition_basis_kind IS NULL
           OR nutrition_basis_amount IS NULL
           OR nutrition_basis_unit IS NULL"""
    )


def downgrade() -> None:
    pass
