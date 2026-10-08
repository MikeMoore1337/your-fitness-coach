"""Add organizational labels to coach-client links."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0128_coach_client_labels"
down_revision: str | None = "0127_check_in_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Adds optional coach-owned organizational labels to existing coach-client links. "
    "Labels are workflow metadata only and do not classify health or medical cohorts."
)


def upgrade() -> None:
    op.add_column(
        "coach_clients",
        sa.Column("labels", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("coach_clients", "labels")
