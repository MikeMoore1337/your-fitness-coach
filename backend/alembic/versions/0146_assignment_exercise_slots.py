"""Add stable identities for exercises added to an assignment."""

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0146_assignment_exercise_slots"
down_revision: str | None = "0145_history_provider_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
online_rollout_phase = "expand"
online_rollout_notes = "Add nullable assignment slot identities without rewriting workout history."


def upgrade() -> None:
    op.add_column(
        "user_workout_exercises",
        sa.Column("source_assignment_slot_id", sa.String(36), nullable=True),
    )
    op.add_column(
        "workout_exercise_notes",
        sa.Column("source_assignment_slot_id", sa.String(36), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # A repeatable snapshot can predate the lock and hide committed writes.
        if bind.execute(sa.text("SHOW transaction_isolation")).scalar_one() != "read committed":
            raise RuntimeError("Unsafe downgrade: PostgreSQL READ COMMITTED isolation is required")
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute(
            "LOCK TABLE user_workout_exercises, workout_exercise_notes, program_revisions "
            "IN ACCESS EXCLUSIVE MODE"
        )
    elif bind.dialect.name == "sqlite":
        op.execute("UPDATE user_workout_exercises SET id = id WHERE 0")
        if not getattr(bind.connection.driver_connection, "in_transaction", False):
            raise RuntimeError("Unsafe downgrade: assignment slot locking requires a transaction")
    else:
        raise RuntimeError("Unsafe downgrade: assignment slot locking is unsupported")
    for table in ("user_workout_exercises", "workout_exercise_notes"):
        if bind.execute(
            sa.text(f"SELECT 1 FROM {table} WHERE source_assignment_slot_id IS NOT NULL LIMIT 1")
        ).first():
            raise RuntimeError("Cannot discard assignment exercise identities")

    def contains_slot(value: object) -> bool:
        if isinstance(value, dict):
            return value.get("source_assignment_slot_id") is not None or any(
                contains_slot(item) for item in value.values()
            )
        if isinstance(value, list):
            return any(contains_slot(item) for item in value)
        return False

    for row in bind.execute(sa.text("SELECT changed_fields, snapshot FROM program_revisions")):
        for value in row:
            if isinstance(value, str):
                value = json.loads(value)
            if contains_slot(value):
                raise RuntimeError("Cannot discard assignment exercise identities")
    op.drop_column("workout_exercise_notes", "source_assignment_slot_id")
    op.drop_column("user_workout_exercises", "source_assignment_slot_id")
