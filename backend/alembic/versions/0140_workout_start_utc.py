"""Preserve the actual UTC start time of new workout occurrences."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0140_workout_start_utc"
down_revision: str | None = "0139_workout_exercise_notes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
online_rollout_phase = "expand"
online_rollout_notes = "Add nullable UTC workout start times without guessing historical offsets."


def upgrade() -> None:
    op.add_column("user_workouts", sa.Column("started_at_utc", sa.DateTime(), nullable=True))


def downgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        connection.execute(sa.text("LOCK TABLE user_workouts IN ACCESS EXCLUSIVE MODE"))
    if connection.execute(
        sa.text("SELECT 1 FROM user_workouts WHERE started_at_utc IS NOT NULL LIMIT 1")
    ).first():
        raise RuntimeError("Unsafe downgrade: UTC workout start times exist; use a forward fix")
    op.drop_column("user_workouts", "started_at_utc")
