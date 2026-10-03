"""Add the coach task source-kind constraint safely online."""

from collections.abc import Sequence

from alembic import op

revision: str = "0111_source_kind_check"
down_revision: str | None = "0110_coach_task_kind_constraint"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "constraint_swap"
online_rollout_notes = (
    "Adds and validates the nullable coach task source-kind CHECK under a bounded lock and "
    "statement timeout; NULL remains the explicit no-source state."
)
online_rollout_constraint_table = "coach_tasks"
online_rollout_constraint_name = "ck_coach_tasks_source_kind"
online_rollout_lock_timeout_seconds = 3
online_rollout_statement_timeout_seconds = 30


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute(
            "ALTER TABLE coach_tasks DROP CONSTRAINT IF EXISTS ck_coach_tasks_source_kind, "
            "ADD CONSTRAINT ck_coach_tasks_source_kind CHECK (source_kind IS NULL OR "
            "source_kind IN ('weekly_check_in', 'workout', 'program', 'client', 'manual')) "
            "NOT VALID"
        )
        op.execute("ALTER TABLE coach_tasks VALIDATE CONSTRAINT ck_coach_tasks_source_kind")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_constraint("ck_coach_tasks_source_kind", table_name="coach_tasks", type_="check")
