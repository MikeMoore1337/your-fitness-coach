"""Drop legacy one-rest-per-set uniqueness after replacement indexes (single-slot only)."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0132_rest_interval_unique_swap"
down_revision: str | None = "0131_rest_interval_expand"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "rest_unique_swap"
online_rollout_notes = (
    "Single-slot only: old backend cannot read multiple rests for one source set. "
    "First build and verify replacement indexes in 0131; stop all old backend/worker "
    "writers before this fast metadata-only DROP CONSTRAINT. "
    "Lock timeout 3s, statement timeout 30s. Never downgrade after successor rows."
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute(
            "ALTER TABLE workout_rest_sessions DROP CONSTRAINT uq_workout_rest_source_set"
        )
    else:
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
