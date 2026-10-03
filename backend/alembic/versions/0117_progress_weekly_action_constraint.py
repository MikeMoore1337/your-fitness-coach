"""Add the progress weekly action value constraint safely online."""

from collections.abc import Sequence

from alembic import op

revision: str = "0117_weekly_action_constraint"
down_revision: str | None = "0116_progress_weekly_action"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "constraint_swap"
online_rollout_notes = (
    "Adds and validates the nullable weekly progress action CHECK under bounded PostgreSQL "
    "lock and statement timeouts; NULL remains the explicit pre-review state."
)
online_rollout_constraint_table = "weekly_check_ins"
online_rollout_constraint_name = "ck_weekly_check_ins_progress_action_kind"
online_rollout_lock_timeout_seconds = 3
online_rollout_statement_timeout_seconds = 30


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute(
            "ALTER TABLE weekly_check_ins DROP CONSTRAINT IF EXISTS "
            "ck_weekly_check_ins_progress_action_kind, ADD CONSTRAINT "
            "ck_weekly_check_ins_progress_action_kind CHECK (progress_action_kind IS NULL OR "
            "progress_action_kind IN ('workout', 'nutrition', 'measurement', 'none')) NOT VALID"
        )
        op.execute(
            "ALTER TABLE weekly_check_ins VALIDATE CONSTRAINT "
            "ck_weekly_check_ins_progress_action_kind"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE weekly_check_ins DROP CONSTRAINT IF EXISTS "
            "ck_weekly_check_ins_progress_action_kind"
        )
