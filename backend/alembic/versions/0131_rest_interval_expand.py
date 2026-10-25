"""Add nullable rest interval identity without rewriting historical facts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0131_rest_interval_expand"
down_revision: str | None = "0130_workout_rest_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Only nullable columns. Existing rest rows retain their IDs, times and statuses. "
    "Indexes and uniqueness replacement are applied transactionally in 0132 during "
    "the authorized single-slot release, avoiding loss of Alembic's transaction lock."
)


def upgrade() -> None:
    op.add_column("workout_rest_sessions", sa.Column("predecessor_id", sa.Integer(), nullable=True))
    op.add_column("workout_rest_sessions", sa.Column("start_mutation_id", sa.String(64), nullable=True))
    op.add_column("workout_rest_sessions", sa.Column("start_fingerprint", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("workout_rest_sessions", "start_fingerprint")
    op.drop_column("workout_rest_sessions", "start_mutation_id")
    op.drop_column("workout_rest_sessions", "predecessor_id")
