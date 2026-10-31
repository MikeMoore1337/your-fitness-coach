"""Constrain side metadata without rewriting existing workout facts."""

import sqlite3
from collections.abc import Sequence

from alembic import op

revision: str = "0144_workout_side_metadata_ck"
down_revision: str | None = "0143_workout_set_sides"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
online_rollout_phase = "constraint_swap"
online_rollout_notes = (
    "Add the side metadata CHECK under bounded PostgreSQL lock and validation timeouts."
)
online_rollout_constraint_table = "user_workout_sets"
online_rollout_constraint_name = "ck_user_workout_sets_side_metadata"
online_rollout_lock_timeout_seconds = 3
online_rollout_statement_timeout_seconds = 30


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute(
            "ALTER TABLE user_workout_sets DROP CONSTRAINT IF EXISTS ck_user_workout_sets_side_metadata, "
            "ADD CONSTRAINT ck_user_workout_sets_side_metadata CHECK ((execution_mode IS NULL OR execution_mode IN ('bilateral', 'per_side', 'alternating')) AND (first_side IS NULL OR first_side IN ('left', 'right'))) NOT VALID"
        )
        op.execute(
            "ALTER TABLE user_workout_sets VALIDATE CONSTRAINT ck_user_workout_sets_side_metadata"
        )
    else:
        if bind.dialect.name != "sqlite" or bind.connection.driver_connection.getconfig(
            sqlite3.SQLITE_DBCONFIG_ENABLE_FKEY
        ):
            raise RuntimeError("SQLite migration requires a connection with foreign keys disabled")
        with op.batch_alter_table("user_workout_sets") as batch:
            batch.create_check_constraint(
                "ck_user_workout_sets_side_metadata",
                "(execution_mode IS NULL OR execution_mode IN ('bilateral', 'per_side', 'alternating')) AND (first_side IS NULL OR first_side IN ('left', 'right'))",
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.drop_constraint("ck_user_workout_sets_side_metadata", "user_workout_sets", type_="check")
    else:
        if bind.dialect.name != "sqlite" or bind.connection.driver_connection.getconfig(
            sqlite3.SQLITE_DBCONFIG_ENABLE_FKEY
        ):
            raise RuntimeError("SQLite migration requires a connection with foreign keys disabled")
        with op.batch_alter_table("user_workout_sets") as batch:
            batch.drop_constraint("ck_user_workout_sets_side_metadata", type_="check")
