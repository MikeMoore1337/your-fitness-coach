"""Backfill the default duration for existing program templates.

Revision ID: 0078_backfill_program_duration
Revises: 0077_periodized_templates
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0078_backfill_program_duration"
down_revision: str | None = "0077_periodized_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "backfill"
online_rollout_batch_size = 1000
online_rollout_idempotent = True
online_rollout_notes = (
    "Backfills only NULL duration values in program_templates with one week; the explicit "
    "predicate makes reruns idempotent and limits writes to rows exposed by 0077."
)


def upgrade() -> None:
    op.execute(
        "UPDATE program_templates "
        "SET default_duration_weeks = 1 "
        "WHERE default_duration_weeks IS NULL"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE program_templates "
        "SET default_duration_weeks = NULL "
        "WHERE default_duration_weeks = 1"
    )
