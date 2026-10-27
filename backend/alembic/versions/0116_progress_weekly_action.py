"""Persist one server-selected weekly progress action and completion."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0116_progress_weekly_action"
down_revision: str | None = "0115_nutrition_repeat_preview"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Adds nullable weekly action state without backfilling private facts; existing rows remain "
    "readable and can use their stored summary for a safe fallback."
)


def upgrade() -> None:
    op.add_column(
        "weekly_check_ins",
        sa.Column("progress_action_kind", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "weekly_check_ins",
        sa.Column("progress_action_completed_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("weekly_check_ins", "progress_action_completed_at")
    op.drop_column("weekly_check_ins", "progress_action_kind")
