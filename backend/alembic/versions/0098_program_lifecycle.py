"""Add the nullable program restart lineage identifier."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0098_program_lifecycle"
down_revision: str | None = "0097_program_import_revisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Adds one nullable scalar restart lineage identifier without scanning existing rows, adding "
    "constraints, or creating an index. Existing program and revision rows remain readable."
)


def upgrade() -> None:
    op.add_column(
        "user_programs", sa.Column("restarted_from_program_id", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("user_programs", "restarted_from_program_id")
