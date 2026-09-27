"""Store idempotent targets for confirmed program-import revisions."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0097_program_import_revisions"
down_revision: str | None = "0096_nutrition_catalog_trust"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Adds nullable scalar confirmation fields to program_imports. No rows are scanned, no index "
    "or foreign key is added, and existing confirmed template imports remain readable."
)


def upgrade() -> None:
    op.add_column("program_imports", sa.Column("confirmed_program_id", sa.Integer(), nullable=True))
    op.add_column(
        "program_imports", sa.Column("confirmed_revision_number", sa.Integer(), nullable=True)
    )
    op.add_column(
        "program_imports", sa.Column("confirmed_workouts_updated", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("program_imports", "confirmed_workouts_updated")
    op.drop_column("program_imports", "confirmed_revision_number")
    op.drop_column("program_imports", "confirmed_program_id")
