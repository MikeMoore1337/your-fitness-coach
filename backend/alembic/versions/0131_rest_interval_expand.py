"""Add nullable workout rest lineage columns (transaction-safe expand)."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0131_rest_interval_expand"
down_revision: str | None = "0130_workout_rest_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Add three nullable metadata-only columns; preserve all historical rest records. "
    "Indexes and legacy uniqueness swap are a separately guarded single-slot step 0132."
)


def upgrade() -> None:
    op.add_column("workout_rest_sessions", sa.Column("predecessor_id", sa.Integer(), nullable=True))
    op.add_column("workout_rest_sessions", sa.Column("start_mutation_id", sa.String(64), nullable=True))
    op.add_column("workout_rest_sessions", sa.Column("start_fingerprint", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("workout_rest_sessions", "start_fingerprint")
    op.drop_column("workout_rest_sessions", "start_mutation_id")
    op.drop_column("workout_rest_sessions", "predecessor_id")
