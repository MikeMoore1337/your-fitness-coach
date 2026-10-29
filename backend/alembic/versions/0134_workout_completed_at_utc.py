"""Record unambiguous completion instants for new workouts."""

import sqlalchemy as sa

from alembic import op

revision = "0134_workout_completed_at_utc"
down_revision = "0133_profile_height_numeric"
branch_labels = None
depends_on = None
online_rollout_phase = "expand"
online_rollout_notes = "Nullable UTC completion instant; existing timestamps remain unchanged."


def upgrade():
    op.add_column("user_workouts", sa.Column("completed_at_utc", sa.DateTime(), nullable=True))


def downgrade():
    if (
        op.get_bind()
        .execute(sa.text("SELECT 1 FROM user_workouts WHERE completed_at_utc IS NOT NULL LIMIT 1"))
        .first()
    ):
        raise RuntimeError("Cannot discard recorded UTC workout completion instants")
    op.drop_column("user_workouts", "completed_at_utc")
