"""Backfill the default kind for legacy coach tasks."""

from collections.abc import Sequence

from alembic import op

revision: str = "0109_coach_task_kind_backfill"
down_revision: str | None = "0108_trainer_workspace_reviews"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "backfill"
online_rollout_notes = (
    "Idempotently fills the newly added coach task kind for legacy rows only. The single UPDATE "
    "has an explicit NULL predicate and leaves already populated task provenance unchanged."
)
online_rollout_batch_size = 1000
online_rollout_idempotent = True


def upgrade() -> None:
    op.execute("UPDATE coach_tasks SET kind = 'other' WHERE kind IS NULL")


def downgrade() -> None:
    pass
