"""Build transaction-safe rest uniqueness indexes and retire the legacy constraint."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0132_rest_interval_unique_swap"
down_revision: str | None = "0131_rest_interval_expand"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "rest_unique_swap"
online_rollout_notes = (
    "Single-slot only: all old backend and worker writers drained. "
    "Four unique indexes are created in the same bounded transaction before "
    "dropping the legacy one-rest-per-set constraint. Bounded 3s lock timeout "
    "and 30s statement timeout; lock duration requires PG16 verification. "
    "Never downgrade after recording multiple intervals for one source set."
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute(
            "CREATE UNIQUE INDEX uq_workout_rest_initial_source "
            "ON workout_rest_sessions (source_set_id) WHERE predecessor_id IS NULL"
        )
        op.execute(
            "CREATE UNIQUE INDEX uq_workout_rest_predecessor "
            "ON workout_rest_sessions (predecessor_id)"
        )
        op.execute(
            "CREATE UNIQUE INDEX uq_workout_rest_start_mutation "
            "ON workout_rest_sessions (workout_id, start_mutation_id)"
        )
        op.execute(
            "CREATE UNIQUE INDEX uq_workout_rest_running_workout "
            "ON workout_rest_sessions (workout_id) WHERE status = 'running'"
        )
        op.execute(
            "ALTER TABLE workout_rest_sessions DROP CONSTRAINT uq_workout_rest_source_set"
        )
    else:
        op.create_index(
            "uq_workout_rest_initial_source",
            "workout_rest_sessions",
            ["source_set_id"],
            unique=True,
            sqlite_where=sa.text("predecessor_id IS NULL"),
        )
        op.create_index(
            "uq_workout_rest_predecessor",
            "workout_rest_sessions",
            ["predecessor_id"],
            unique=True,
        )
        op.create_index(
            "uq_workout_rest_start_mutation",
            "workout_rest_sessions",
            ["workout_id", "start_mutation_id"],
            unique=True,
        )
        op.create_index(
            "uq_workout_rest_running_workout",
            "workout_rest_sessions",
            ["workout_id"],
            unique=True,
            sqlite_where=sa.text("status = 'running'"),
        )
        with op.batch_alter_table("workout_rest_sessions") as batch:
            batch.drop_constraint("uq_workout_rest_source_set", type_="unique")


def downgrade() -> None:
    bind = op.get_bind()
    duplicates = bind.execute(
        sa.text(
            "SELECT source_set_id FROM workout_rest_sessions "
            "GROUP BY source_set_id HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicates is not None:
        raise RuntimeError(
            "Unsafe downgrade: multiple rest intervals per source set exist; use forward-fix"
        )
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.create_unique_constraint(
            "uq_workout_rest_source_set", "workout_rest_sessions", ["source_set_id"]
        )
    else:
        with op.batch_alter_table("workout_rest_sessions") as batch:
            batch.create_unique_constraint("uq_workout_rest_source_set", ["source_set_id"])
    op.drop_index("uq_workout_rest_running_workout", table_name="workout_rest_sessions")
    op.drop_index("uq_workout_rest_start_mutation", table_name="workout_rest_sessions")
    op.drop_index("uq_workout_rest_predecessor", table_name="workout_rest_sessions")
    op.drop_index("uq_workout_rest_initial_source", table_name="workout_rest_sessions")
